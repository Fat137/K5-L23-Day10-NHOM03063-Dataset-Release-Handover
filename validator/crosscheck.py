"""Đối chiếu detection (labels/ YOLO) với panoptic (panoptic.json + masks/) của cùng ảnh.

Sinh ỨNG VIÊN lỗi gán nhãn. Ứng viên chưa phải lỗi: người trong nhóm phải mở ảnh xác nhận.

Ghép box với segment thing qua IoU của bbox; lớp ghép qua TÊN (classes.txt <-> categories).
Bbox của segment lấy từ pixel thật của mask (không tin bbox khai trong segments_info).

Dấu hiệu:
- class_or_category_swap: box và segment trùng vị trí (IoU cao) nhưng khác lớp, không bên nào có
  bạn cùng lớp ở đó. Người xem ảnh quyết định class_swap (detection sai) hay category_swap (panoptic sai).
- bbox_drift: box cùng lớp ghép tốt nhất với segment nhưng IoU thấp hơn hẳn mức tự nhiên.
- missing_box: segment thing lớn không có box nào phủ.
- instance_merge: một segment chứa >= 2 box cùng lớp, bbox segment ≈ hợp các box đó.

Chỉ thư viện chuẩn + scripts/pngutil.py (qua common.Delivery).
"""

from __future__ import annotations

from common import Delivery

# Ngưỡng (đo trên lô sạch runs/clean và seed luyện tập, xem REPORT.md)
SWAP_IOU = 0.45         # box và segment khác lớp trùng nhau ít nhất mức này
DRIFT_LO, DRIFT_HI = 0.1, 0.8   # IoU box-segment cùng lớp nằm trong khoảng này: nghi lệch
MISS_FRAC = 0.004       # segment chiếm ít nhất 1% ảnh mới tính là "vật đáng kể"
MISS_IOU = 0.4         # không box nào (mọi lớp) đạt IoU này với segment -> thiếu box
MERGE_UNION_IOU = 0.7   # hợp hai box cùng lớp khớp bbox segment
MERGE_SINGLE_MAX = 0.75  # mỗi box riêng lẻ khớp segment kém


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def union_box(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def pixel_bboxes(d: Delivery, name: str) -> dict[int, tuple[float, float, float, float]]:
    """bbox (x0, y0, x1, y1) theo pixel thật của từng segment id trong mask."""
    m = d.mask(name)
    if not m:
        return {}
    W, H, px = m
    out: dict[int, list[int]] = {}
    row_bytes = W * 3
    for y in range(H):
        row = px[y * row_bytes:(y + 1) * row_bytes]
        ids = {}
        # gom theo màu trong một hàng
        for x, rgb in enumerate(zip(row[0::3], row[1::3], row[2::3])):
            if rgb != (0, 0, 0):
                if rgb in ids:
                    ids[rgb][1] = x
                else:
                    ids[rgb] = [x, x]
        for (r, g, b), (x0, x1) in ids.items():
            sid = r + g * 256 + b * 65536
            bb = out.get(sid)
            if bb is None:
                out[sid] = [x0, y, x1, y]
            else:
                if x0 < bb[0]:
                    bb[0] = x0
                if x1 > bb[2]:
                    bb[2] = x1
                bb[3] = y
    return {k: (v[0], v[1], v[2] + 1, v[3] + 1) for k, v in out.items()}


def find_candidates(d: Delivery) -> list[dict]:
    cands: list[dict] = []
    for name in d.images:
        ann = d.pan_ann.get(name)
        size = d.size(name)
        if not ann or not size or not d.path(name, "mask").is_file():
            continue
        W, H = size
        boxes = [b for b in d.boxes(name) if "px" in b and b["cls"] in d.classes]
        pix = pixel_bboxes(d, name)
        segs = []
        for s in ann.get("segments_info", []):
            cat = d.categories.get(s.get("category_id"))
            if not cat or not cat.get("isthing") or s.get("iscrowd"):
                continue
            if s["id"] not in pix:
                continue
            segs.append({"id": s["id"], "name": cat["name"], "bb": pix[s["id"]],
                         "area": d.segment_pixel_counts(name).get(s["id"], 0)})
        crowd = []
        for s in ann.get("segments_info", []):
            cat = d.categories.get(s.get("category_id"))
            if s.get("iscrowd") and cat and s["id"] in pix:
                crowd.append((cat["name"], pix[s["id"]]))

        found: list[tuple[str, str, float]] = []  # (type, detail, score)

        def bname(b):
            return d.classes[b["cls"]]

        # IoU ma trận
        M = [[iou(b["px"], s["bb"]) for s in segs] for b in boxes]

        # 1. khác lớp tại cùng vị trí
        for i, b in enumerate(boxes):
            for j, s in enumerate(segs):
                if M[i][j] < SWAP_IOU or bname(b) == s["name"]:
                    continue
                same_seg = any(segs[k]["name"] == bname(b) and M[i][k] >= 0.3 for k in range(len(segs)))
                same_box = any(bname(boxes[k]) == s["name"] and M[k][j] >= 0.3 for k in range(len(boxes)))
                in_crowd = any(cn == bname(b) and iou(b["px"], cb) > 0 for cn, cb in crowd)
                if not same_seg and not same_box and not in_crowd:
                    found.append(("class_swap",
                                  f"box#{b['i']} detection={bname(b)} <-> segment {s['id']} panoptic={s['name']} "
                                  f"IoU={M[i][j]:.2f} (class_swap hay category_swap: xem ảnh)", M[i][j]))

        # 2. lệch box: segment cùng lớp, ghép tốt nhất nhưng IoU thấp
        for j, s in enumerate(segs):
            same = [(M[i][j], i) for i, b in enumerate(boxes) if bname(b) == s["name"]]
            if not same:
                continue
            best, i = max(same)
            # box đó có segment khác cùng lớp khớp tốt hơn không?
            better = max((M[i][k] for k in range(len(segs)) if k != j and segs[k]["name"] == s["name"]), default=0)
            if DRIFT_LO <= best < DRIFT_HI and better < best and s["area"] >= 0.002 * W * H:
                bb = boxes[i]["px"]
                found.append(("bbox_drift",
                              f"box#{boxes[i]['i']} {s['name']} IoU={best:.2f} với segment {s['id']} "
                              f"box=({bb[0]:.0f},{bb[1]:.0f},{bb[2]:.0f},{bb[3]:.0f}) "
                              f"seg=({s['bb'][0]:.0f},{s['bb'][1]:.0f},{s['bb'][2]:.0f},{s['bb'][3]:.0f})",
                              1 - best))

        # 3. thiếu box: segment lớn không box nào phủ
        for j, s in enumerate(segs):
            if s["area"] < MISS_FRAC * W * H:
                continue
            best = max((M[i][j] for i in range(len(boxes))), default=0)
            if best < MISS_IOU:
                found.append(("missing_box",
                              f"segment {s['id']} {s['name']} {s['area']} px ({100 * s['area'] / (W * H):.1f}% ảnh) "
                              f"không có box (IoU tốt nhất {best:.2f})", s["area"] / (W * H)))

        # 4. gộp: một segment ≈ hợp hai box cùng lớp
        for j, s in enumerate(segs):
            same = [i for i, b in enumerate(boxes) if bname(b) == s["name"] and M[i][j] > 0.05]
            hit = None
            for a in range(len(same)):
                for c in range(a + 1, len(same)):
                    ia, ic = same[a], same[c]
                    u = iou(union_box(boxes[ia]["px"], boxes[ic]["px"]), s["bb"])
                    if u >= MERGE_UNION_IOU and max(M[ia][j], M[ic][j]) < MERGE_SINGLE_MAX:
                        # hai box này không có segment riêng nào khác khớp tốt
                        own = [max((M[x][k] for k in range(len(segs)) if k != j and segs[k]["name"] == s["name"]),
                                   default=0) for x in (ia, ic)]
                        if max(own) < 0.5 and (hit is None or u > hit[0]):
                            hit = (u, ia, ic)
            if hit:
                u, ia, ic = hit
                found.append(("instance_merge",
                              f"segment {s['id']} {s['name']} phủ box#{boxes[ia]['i']} và box#{boxes[ic]['i']} "
                              f"(IoU hợp hai box = {u:.2f})", u))

        # 4b. gộp (cách 2): box cùng lớp không có segment riêng, nằm gọn trong segment của box khác
        for i, b in enumerate(boxes):
            own = max((M[i][k] for k in range(len(segs)) if segs[k]["name"] == bname(b)), default=0)
            if own >= 0.5:
                continue
            ab = (b["px"][2] - b["px"][0]) * (b["px"][3] - b["px"][1])
            if ab <= 0:
                continue
            for j, s in enumerate(segs):
                if s["name"] != bname(b):
                    continue
                sb = s["bb"]
                ix = max(0.0, min(b["px"][2], sb[2]) - max(b["px"][0], sb[0]))
                iy = max(0.0, min(b["px"][3], sb[3]) - max(b["px"][1], sb[1]))
                if ix * iy / ab < 0.6:
                    continue
                others = [k for k in range(len(boxes)) if k != i and bname(boxes[k]) == s["name"] and M[k][j] >= 0.3]
                for k in others:
                    u = iou(union_box(b["px"], boxes[k]["px"]), sb)
                    if u >= 0.5 and u > M[k][j]:
                        found.append(("instance_merge",
                                      f"segment {s['id']} {s['name']} phủ box#{boxes[k]['i']} và box#{b['i']} "
                                      f"(box#{b['i']} không có segment riêng; IoU hợp = {u:.2f})", u))
                        break

        if not found:
            continue
        # mỗi ảnh nhiều nhất một lỗi: giữ dấu hiệu mạnh nhất theo thứ tự ưu tiên
        prio = {"instance_merge": 0, "class_swap": 1, "missing_box": 2, "bbox_drift": 3}
        found.sort(key=lambda f: (prio[f[0]], -f[2]))
        t, detail, _ = found[0]
        others = "; ".join(f"{f[0]}: {f[1]}" for f in found[1:3])
        cands.append({"type": t, "target": name, "detail": detail + (f" | khác: {others}" if others else "")})
    return cands
