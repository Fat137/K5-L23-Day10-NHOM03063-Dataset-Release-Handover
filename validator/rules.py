"""Chín lỗi luật (docs/DELIVERY.md mục 2). Mỗi hàm trả về list {type, target, detail}.

Lỗi luật chứng minh được bằng chính các file trong delivery, không cần xem ảnh.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

from common import Delivery

# Box tràn mép: cho phép sai số làm tròn 0,5 pixel (nhãn ghi 6 chữ số thập phân).
OOB_TOL_PX = 0.5
# Box lặp: cùng lớp, cùng kích thước (sai số làm tròn), tâm lệch không quá vài pixel.
DUP_SIZE_TOL_PX = 0.5
DUP_SHIFT_MAX_PX = 3.0


def finding(kind: str, target: str, detail: str) -> dict:
    return {"type": kind, "target": target, "detail": detail}


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:  # bytes, không phải text
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ file
def check_files(d: Delivery) -> list[dict]:
    """missing_image: manifest có ảnh mà thiếu file. wrong_hash: sha256 thật khác sha256 trong manifest."""
    out = []
    for name, item in d.manifest.items():
        img = d.path(name, "image")
        if not img.is_file():
            out.append(finding("missing_image", name, f"thiếu {item.get('image')}"))
            continue
        bad = []
        for kind in ("image", "label", "mask"):
            want = (item.get(f"{kind}_sha256") or "").lower()
            p = d.path(name, kind)
            if want and p.is_file() and sha256_file(p) != want:
                bad.append(kind)
        if bad:
            out.append(finding("wrong_hash", name, "sha256 không khớp manifest: " + ", ".join(bad)))
    return out


# ------------------------------------------------------------------ nhãn detection
def check_labels(d: Delivery) -> list[dict]:
    """invalid_class, bbox_out_of_bounds, duplicate_box."""
    out = []
    n_cls = len(d.classes)
    for name in d.images:
        rows = d.label_rows(name)
        size = d.size(name)
        W, H = size if size else (None, None)

        # invalid_class: class_id không phải số nguyên trong 0..n_cls-1, hoặc dòng sai cú pháp
        bad_cls = []
        for row in rows:
            try:
                ok = len(row) == 5 and 0 <= int(row[0]) < n_cls
            except ValueError:
                ok = False
            if not ok:
                bad_cls.append(row[0] if row else "?")
        if bad_cls:
            out.append(finding("invalid_class", name, f"class_id ngoài 0-{n_cls - 1}: {bad_cls}"))

        boxes = [b for b in d.boxes(name) if 0 <= b["cls"] < n_cls]

        # bbox_out_of_bounds: cạnh box vượt ra ngoài ảnh quá sai số làm tròn
        tol_x = OOB_TOL_PX / W if W else 1e-4
        tol_y = OOB_TOL_PX / H if H else 1e-4
        oob = []
        for b in boxes:
            left, right = b["x"] - b["w"] / 2, b["x"] + b["w"] / 2
            top, bottom = b["y"] - b["h"] / 2, b["y"] + b["h"] / 2
            if b["w"] <= 0 or b["h"] <= 0 or left < -tol_x or top < -tol_y or right > 1 + tol_x or bottom > 1 + tol_y:
                oob.append(f"dòng {b['i'] + 1} [{left:.3f},{top:.3f},{right:.3f},{bottom:.3f}]")
        if oob:
            out.append(finding("bbox_out_of_bounds", name, "; ".join(oob)))

        # duplicate_box: cùng lớp, cùng kích thước, tâm lệch <= vài pixel.
        # Không dùng IoU: cặp box tự nhiên của COCO có thể chồng nhau tới IoU ~0,66 nhưng khác kích thước.
        if W and H:
            dups = []
            for i, a in enumerate(boxes):
                for b in boxes[i + 1:]:
                    if a["cls"] != b["cls"]:
                        continue
                    same_size = abs(a["w"] - b["w"]) * W <= DUP_SIZE_TOL_PX and abs(a["h"] - b["h"]) * H <= DUP_SIZE_TOL_PX
                    dx, dy = abs(a["x"] - b["x"]) * W, abs(a["y"] - b["y"]) * H
                    if same_size and dx <= DUP_SHIFT_MAX_PX and dy <= DUP_SHIFT_MAX_PX:
                        dups.append(f"dòng {a['i'] + 1} và {b['i'] + 1} lớp {d.classes[a['cls']]} lệch ({dx:.1f},{dy:.1f}) px")
            if dups:
                out.append(finding("duplicate_box", name, "; ".join(dups)))
    return out


# ------------------------------------------------------------------ metadata
def check_metadata(d: Delivery) -> list[dict]:
    """scene_leak (target = scene_id) và guideline_mismatch (so với guideline của job)."""
    out = []
    by_scene: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for name, row in d.meta.items():
        by_scene[row["scene_id"]][row["split"]].append(name)
    for scene, splits in sorted(by_scene.items()):
        if len(splits) > 1:
            parts = ", ".join(f"{s}: {len(v)} ảnh" for s, v in sorted(splits.items()))
            minority = min(splits.values(), key=len)
            out.append(finding("scene_leak", scene, f"{parts}; ảnh lệch split: {minority}"))

    for name, row in d.meta.items():
        job = d.jobs.get(row.get("job_id"))
        if job is None:
            continue
        if row.get("guideline_version") != job.get("guideline"):
            out.append(finding("guideline_mismatch", name,
                               f"ảnh ghi {row.get('guideline_version')}, job {job['job_id']} ghi {job.get('guideline')}"))
    return out


# ------------------------------------------------------------------ panoptic
def check_panoptic(d: Delivery) -> list[dict]:
    """invalid_category_id và thing_overlap (area khai > số pixel thật của segment)."""
    out = []
    for name in d.images:
        ann = d.pan_ann.get(name)
        if not ann:
            continue
        segs = ann.get("segments_info", [])
        bad = [s["category_id"] for s in segs if s.get("category_id") not in d.categories]
        if bad:
            out.append(finding("invalid_category_id", name, f"category_id không có trong categories: {bad}"))

        counts = d.segment_pixel_counts(name)
        over = []
        for s in segs:
            real = counts.get(s["id"], 0)
            declared = int(s.get("area", 0))
            if declared > real:
                over.append(f"segment {s['id']} area={declared} > {real} pixel")
        if over:
            out.append(finding("thing_overlap", name, "; ".join(over)))
    return out


def run_all(d: Delivery) -> list[dict]:
    return check_files(d) + check_labels(d) + check_metadata(d) + check_panoptic(d)
