"""Đối chiếu detection <-> panoptic của cùng một ảnh để sinh ứng viên lỗi gán nhãn.

Ứng viên KHÔNG phải lỗi: người trong nhóm phải mở ảnh rồi ghi confirmed/rejected.

Ý tưởng: COCO panoptic tách từ cùng annotation với detection, nên với một vật đúng thì
  - box và segment cùng lớp gần như trùng bbox (IoU cao), và
  - gần như toàn bộ pixel của segment nằm trong box.
Khi một trong hai nguồn bị sửa, cặp đó vỡ theo những kiểu khác nhau:
  class_swap / category_swap : box trùng vị trí một segment KHÁC lớp, và không có segment cùng lớp nào khớp
  bbox_drift                 : segment cùng lớp có một phần pixel rơi ra ngoài box
  instance_merge             : một segment phủ HAI box cùng lớp
  missing_box                : segment thing không có box nào phủ
"""

from __future__ import annotations

import math
from collections import Counter

from common import Delivery

# Một cặp box-segment được coi là "khớp" khi IoU bbox và tỉ lệ pixel nằm trong box đều cao.
# Đo trên lô sạch (runs/clean, 50 ảnh, 435 box): mọi cặp đúng chứa 100% pixel của segment trong box;
# IoU dưới 0,8 chỉ gặp ở box tí hon (< 160 pixel), nơi vài pixel rasterize đã đủ làm IoU tụt.
MATCH_IOU = 0.5
MATCH_COVER = 0.98
MATCH_IOU_BIG = 0.8      # box từ BIG_BOX_PX trở lên phải khớp chặt hơn
BIG_BOX_PX = 400
# Box và segment khác lớp được coi là "cùng một vật" khi bbox gần như trùng.
SWAP_IOU = 0.6
# Gộp instance: mỗi box phải chứa một phần đáng kể của segment, và các box cộng lại chứa gần hết segment.
MERGE_PART = 0.10   # box chứa >= 10% pixel của segment
MERGE_FILL = 0.30   # hoặc pixel của segment lấp >= 30% diện tích box (vật nhỏ bị gộp vào vật lớn)
MERGE_TOTAL = 0.85
# Thiếu box: chỉ xét segment đủ lớn để nhìn thấy (tỉ lệ diện tích ảnh).
MISSING_MIN_FRAC = 0.002
DEDUP_IOU = 0.7
# Box lệch: bỏ qua box quá nhỏ (vài chục pixel), lệch rasterize không có ý nghĩa.
DRIFT_MIN_PX = 150


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def rect_counts(px: bytearray, W: int, H: int, rect, slack: int = 1) -> dict[int, int]:
    """Đếm pixel của từng segment id nằm trong một hình chữ nhật (nới 1 pixel cho sai số rasterize)."""
    x0 = max(0, math.floor(rect[0]) - slack)
    y0 = max(0, math.floor(rect[1]) - slack)
    x1 = min(W, math.ceil(rect[2]) + slack)
    y1 = min(H, math.ceil(rect[3]) + slack)
    c: Counter = Counter()
    for y in range(y0, y1):
        row = px[(y * W + x0) * 3:(y * W + x1) * 3]
        c.update(zip(row[0::3], row[1::3], row[2::3]))
    return {r + g * 256 + b * 65536: n for (r, g, b), n in c.items()}


def load_image(d: Delivery, name: str):
    m = d.mask(name)
    ann = d.pan_ann.get(name)
    if m is None or ann is None:
        return None
    W, H, px = m
    totals = d.segment_pixel_counts(name)
    segs = []
    for s in ann.get("segments_info", []):
        cat = d.categories.get(s.get("category_id"))
        if not cat or not cat.get("isthing") or s.get("iscrowd"):
            continue
        x, y, w, h = s["bbox"]
        segs.append({"id": s["id"], "name": cat["name"], "rect": (x, y, x + w, y + h), "tot": totals.get(s["id"], 0)})
    boxes = []
    for b in d.boxes(name):
        if b["cls"] not in d.classes or "px" not in b:
            continue
        b = dict(b)
        b["name"] = d.classes[b["cls"]]
        b["inside"] = rect_counts(px, W, H, b["px"])
        l, t, r, bt = b["px"]
        b["area"] = max(0.0, (r - l) * (bt - t))
        boxes.append(b)
    return W, H, segs, boxes


def cover(box, seg) -> float:
    """Tỉ lệ pixel của segment nằm trong box."""
    return box["inside"].get(seg["id"], 0) / seg["tot"] if seg["tot"] else 0.0


def fill(box, seg) -> float:
    """Tỉ lệ diện tích box bị pixel của segment lấp."""
    return box["inside"].get(seg["id"], 0) / box["area"] if box["area"] else 0.0


def matched(box, seg) -> bool:
    need = MATCH_IOU_BIG if box["area"] >= BIG_BOX_PX else MATCH_IOU
    return box["name"] == seg["name"] and iou(box["px"], seg["rect"]) >= need and cover(box, seg) >= MATCH_COVER


def box_label(b) -> str:
    l, t, r, bt = b["px"]
    return f"box {b['name']} dòng {b['i'] + 1} [{l:.0f},{t:.0f},{r:.0f},{bt:.0f}]"


def seg_label(s) -> str:
    l, t, r, bt = s["rect"]
    return f"segment {s['name']} id {s['id']} [{l:.0f},{t:.0f},{r:.0f},{bt:.0f}] {s['tot']} px"


def check_image(d: Delivery, name: str) -> list[dict]:
    loaded = load_image(d, name)
    if loaded is None:
        return []
    W, H, segs, boxes = loaded
    ok_boxes = {id(b) for b in boxes if any(matched(b, s) for s in segs)}
    ok_segs = {s["id"] for s in segs if any(matched(b, s) for b in boxes)}
    bad_boxes = [b for b in boxes if id(b) not in ok_boxes]
    bad_segs = [s for s in segs if s["id"] not in ok_segs]
    out: list[dict] = []
    used_boxes, used_segs = set(), set()

    # 1. Khác lớp: box chưa khớp nằm đúng chỗ một segment khác lớp cũng chưa khớp.
    for b in bad_boxes:
        best = max((s for s in bad_segs if s["name"] != b["name"]), key=lambda s: iou(b["px"], s["rect"]), default=None)
        if best and iou(b["px"], best["rect"]) >= SWAP_IOU and cover(b, best) >= MATCH_COVER:
            out.append({"type": "class_swap", "alt": "category_swap", "target": name,
                        "detail": f"{box_label(b)} trùng vị trí {seg_label(best)} (IoU {iou(b['px'], best['rect']):.2f}). "
                                  f"Detection ghi {b['name']}, panoptic ghi {best['name']}: xem ảnh, detection sai thì class_swap, panoptic sai thì category_swap",
                        "boxes": [b["i"]], "segments": [best["id"]]})
            used_boxes.add(id(b))
            used_segs.add(best["id"])

    # 2. Gộp instance: một segment cùng lớp chiếm phần lớn >= 2 box, trong đó có box "mồ côi"
    #    (box chưa khớp segment nào: segment của nó đã bị gộp vào segment kia).
    for s in segs:
        if s["id"] in used_segs or not s["tot"]:
            continue
        parts = [b for b in boxes if b["name"] == s["name"] and (cover(b, s) >= MERGE_PART or fill(b, s) >= MERGE_FILL)]
        # Box mồ côi thật: không còn segment cùng lớp nào khác chồng lên nó. Nếu còn, đó là box lệch
        # khỏi segment của chính nó (bbox_drift) chứ không phải bị gộp.
        orphans = [b for b in parts if id(b) not in ok_boxes and id(b) not in used_boxes
                   and not any(t["id"] != s["id"] and t["name"] == b["name"] and iou(b["px"], t["rect"]) >= 0.3 for t in segs)]
        if len(parts) < 2 or not orphans:
            continue
        total = min(1.0, sum(cover(b, s) for b in parts))
        if total >= MERGE_TOTAL:
            out.append({"type": "instance_merge", "target": name,
                        "detail": f"{seg_label(s)} phủ {len(parts)} box {s['name']}: "
                                  + ", ".join(f"{box_label(b)} chứa {cover(b, s):.0%}" for b in parts)
                                  + ". Xem ảnh: có phải hai vật riêng bị gộp làm một segment?",
                        "boxes": [b["i"] for b in parts], "segments": [s["id"]]})
            used_segs.add(s["id"])
            used_boxes.update(id(b) for b in parts)

    # 3. Box lệch: box chưa khớp, segment cùng lớp gần nhất có một phần pixel rơi ra ngoài box.
    for b in bad_boxes:
        if id(b) in used_boxes or b["area"] < DRIFT_MIN_PX:
            continue
        same = [s for s in segs if s["name"] == b["name"] and s["id"] not in used_segs]
        s = max(same, key=lambda s: iou(b["px"], s["rect"]), default=None)
        if s is None or iou(b["px"], s["rect"]) == 0:
            # không có segment cùng lớp nào chồng lên box: box ghi sai lớp hoặc box trên chỗ trống
            under = max(segs, key=lambda t: iou(b["px"], t["rect"]), default=None)
            hint = f"; nằm trên {seg_label(under)}" if under and iou(b["px"], under["rect"]) > 0.3 else ""
            out.append({"type": "class_swap", "alt": "category_swap", "target": name,
                        "detail": f"{box_label(b)} không có segment {b['name']} nào chồng lên{hint}. Xem ảnh: vật trong box là gì?",
                        "boxes": [b["i"]], "segments": [under["id"]] if hint else []})
            used_boxes.add(id(b))
            continue
        c = cover(b, s)
        out.append({"type": "bbox_drift", "target": name,
                    "detail": f"{box_label(b)} so với {seg_label(s)}: IoU {iou(b['px'], s['rect']):.2f}, "
                              f"{1 - c:.0%} pixel của segment nằm ngoài box. Xem ảnh: box có lệch khỏi vật?",
                    "boxes": [b["i"]], "segments": [s["id"]]})
        used_boxes.add(id(b))
        used_segs.add(s["id"])

    # 4. Thiếu box: segment thing đủ lớn mà không box nào phủ phần lớn.
    for s in bad_segs:
        if s["id"] in used_segs or s["tot"] < MISSING_MIN_FRAC * W * H:
            continue
        # Box của vật khác (to hơn, khác lớp) có thể chứa trọn segment, ví dụ ghế nằm trong box người:
        # chỉ coi là "đã có box" khi box cùng lớp phủ phần lớn segment, hoặc box nào đó trùng vị trí segment.
        # Box đã khớp với segment của chính nó thì không "giải thích" được segment này.
        free = [b for b in boxes if id(b) not in ok_boxes]
        same_cover = max((cover(b, s) for b in free if b["name"] == s["name"]), default=0.0)
        best_iou = max((iou(b["px"], s["rect"]) for b in free), default=0.0)
        if same_cover >= 0.5 or best_iou >= MATCH_IOU:
            continue
        # Hai vật cùng lớp có bbox gần trùng nhau mà chỉ còn một box: COCO vốn hay có cặp box trùng
        # và lô giao đã bỏ bớt box trùng (IoU > 0,7). Gặp lặp lại ở mọi seed trên cùng ảnh, nên không báo.
        if any(b["name"] == s["name"] and iou(b["px"], s["rect"]) >= DEDUP_IOU for b in boxes):
            continue
        out.append({"type": "missing_box", "target": name,
                    "detail": f"{seg_label(s)} không có box {s['name']} nào phủ (box cùng lớp phủ nhiều nhất chứa {same_cover:.0%}). "
                              f"Xem ảnh: có {s['name']} rõ ràng mà detection thiếu box?",
                    "boxes": [], "segments": [s["id"]]})
        used_segs.add(s["id"])
    return out


def find_candidates(d: Delivery) -> list[dict]:
    """Mỗi ảnh tối đa một ứng viên (mỗi ảnh mang nhiều nhất một lỗi); các dấu hiệu khác ghi thêm vào detail."""
    result = []
    for name in d.images:
        found = check_image(d, name)
        if not found:
            continue
        first = dict(found[0])
        if len(found) > 1:
            first["detail"] += " | Dấu hiệu khác: " + " / ".join(f"{f['type']}: {f['detail']}" for f in found[1:])
            first["boxes"] = sorted({i for f in found for i in f["boxes"]})
            first["segments"] = sorted({i for f in found for i in f["segments"]})
        result.append(first)
    return result
