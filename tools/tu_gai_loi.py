"""Tự gài lỗi gán nhãn lên lô sạch rồi đo crosscheck, để chọn ngưỡng mà không dùng _private.

  python tools/tu_gai_loi.py . runs/clean/delivery 8 --show
  python tools/tu_gai_loi.py . runs/clean/delivery 6 --drift 0.05,0.15 --min-area 0.001 --min-seg 200   # mức lỗi khó hơn

Mỗi vòng: chép lô sạch (50 ảnh calib) ra thư mục tạm, tự gài 2 lỗi mỗi loại (class_swap, category_swap,
bbox_drift, missing_box, instance_merge) theo định nghĩa ở docs/DELIVERY.md, tự ghi đáp án, chạy
crosscheck.find_candidates rồi đếm bắt được bao nhiêu và báo thừa bao nhiêu ảnh. Không đụng runs/.
"""
import argparse
import json
import math
import random
import shutil
import sys
import tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("repo"); ap.add_argument("clean"); ap.add_argument("rounds", type=int)
ap.add_argument("--drift", default="0.08,0.35"); ap.add_argument("--min-area", type=float, default=0.002)
ap.add_argument("--min-seg", type=int, default=400)
ap.add_argument("--show", action="store_true")
a = ap.parse_args()
repo = Path(a.repo)
sys.path.insert(0, str(repo / "validator")); sys.path.insert(0, str(repo / "scripts"))
import pngutil
import crosscheck
from common import Delivery

CONF = [["car", "truck", "bus"], ["bicycle", "motorcycle"], ["cat", "dog"], ["horse", "cow", "sheep"],
        ["cup", "wine glass", "bowl"], ["chair", "couch", "bench"], ["knife", "fork", "spoon"], ["laptop", "tv"],
        ["cell phone", "remote"], ["handbag", "backpack", "suitcase"], ["orange", "apple"], ["donut", "cake"], ["bird", "kite"]]
dlo, dhi = map(float, a.drift.split(","))
TYPES = ["class_swap", "category_swap", "bbox_drift", "missing_box", "instance_merge"]
stats = {t: [0, 0] for t in TYPES}  # found, total
fp_total = 0; cand_total = 0

for rnd in range(a.rounds):
    rng = random.Random(1000 + rnd)
    tmp = Path(tempfile.mkdtemp()) / "delivery"
    shutil.copytree(a.clean, tmp)
    d = Delivery(tmp)
    names80 = d.classes; idx_of = {v: k for k, v in names80.items()}
    cat_by_name = {c["name"]: c["id"] for c in d.categories.values()}
    things = [c for c in d.categories.values() if c["isthing"]]
    pan = json.loads((tmp / "panoptic.json").read_text(encoding="utf-8"))
    ann_by = {Path(x["file_name"]).stem: x for x in pan["annotations"]}
    free = list(d.images); rng.shuffle(free)
    truth = []

    def partner(name, pool):
        for g in CONF:
            if name in g:
                c = [x for x in g if x != name and x in pool]
                if c: return rng.choice(c)
        return rng.choice([x for x in pool if x != name])

    def lab_path(n): return tmp / "labels" / f"{n}.txt"
    def rows(n): return [l.split() for l in lab_path(n).read_text().splitlines() if l.strip()]
    def write(n, rs): lab_path(n).write_text("".join(" ".join(r) + "\n" for r in rs))

    for kind in TYPES * 2:
        for _ in range(30):
            if not free: break
            n = free.pop()
            W, H = d.size(n); rs = rows(n)
            segs = [s for s in ann_by[n]["segments_info"] if d.categories[s["category_id"]]["isthing"] and not s.get("iscrowd")]
            ok = False
            if kind == "class_swap":
                big = [r for r in rs if float(r[3]) * float(r[4]) >= a.min_area]
                if big:
                    r = rng.choice(big); new = partner(names80[int(r[0])], list(idx_of)); r[0] = str(idx_of[new]); write(n, rs); ok = True
            elif kind == "bbox_drift":
                big = [r for r in rs if float(r[3]) > 0.05 and float(r[4]) > 0.05 and float(r[3]) * float(r[4]) >= a.min_area]
                if big:
                    r = rng.choice(big); x, y, w, h = map(float, r[1:5]); ang = rng.uniform(0, 2 * math.pi); mag = rng.uniform(dlo, dhi)
                    if rng.random() < 0.5:
                        s_ = 1 + rng.uniform(-0.25, 0.25); w, h = min(1, w * s_), min(1, h * s_)
                    x = min(1 - w / 2, max(w / 2, x + math.cos(ang) * mag * w)); y = min(1 - h / 2, max(h / 2, y + math.sin(ang) * mag * h))
                    r[1:5] = [f"{x:.6f}", f"{y:.6f}", f"{w:.6f}", f"{h:.6f}"]; write(n, rs); ok = True
            elif kind == "missing_box":
                big = [r for r in rs if float(r[3]) * float(r[4]) > a.min_area * 2]
                if len(rs) >= 2 and big:
                    rs.remove(rng.choice(big)); write(n, rs); ok = True
            elif kind == "category_swap":
                cnt = d.segment_pixel_counts(n)
                big = [s for s in segs if cnt.get(s["id"], 0) >= a.min_seg]
                if big:
                    s = rng.choice(big); new = partner(d.categories[s["category_id"]]["name"], [c["name"] for c in things])
                    s["category_id"] = cat_by_name[new]; ok = True
            elif kind == "instance_merge":
                cnt = d.segment_pixel_counts(n); g = {}
                for s in segs: g.setdefault(s["category_id"], []).append(s)
                pairs = [v for v in g.values() if len(v) >= 2 and sorted(cnt.get(s["id"], 0) for s in v)[0] >= a.min_seg // 2]
                if pairs:
                    pr = sorted(rng.choice(pairs), key=lambda s: cnt.get(s["id"], 0)); rem, keep = pr[0], pr[-1]
                    Wm, Hm, px = pngutil.read_rgb(tmp / "masks" / f"{n}.png"); px = bytearray(px)
                    kr = bytes(pngutil.segment_rgb(keep["id"]))
                    for i in range(0, len(px), 3):
                        if pngutil.segment_id(px, i) == rem["id"]: px[i:i + 3] = kr
                    pngutil.write_rgb(tmp / "masks" / f"{n}.png", Wm, Hm, bytes(px))
                    xs, ys = [], []
                    for i in range(0, len(px), 3):
                        if pngutil.segment_id(px, i) == keep["id"]: xs.append((i // 3) % Wm); ys.append((i // 3) // Wm)
                    keep["area"] = len(xs); keep["bbox"] = [min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1]
                    ann_by[n]["segments_info"] = [s for s in ann_by[n]["segments_info"] if s["id"] != rem["id"]]
                    ok = True
            if ok:
                truth.append((kind, n)); break
    (tmp / "panoptic.json").write_text(json.dumps(pan), encoding="utf-8")
    cands = crosscheck.find_candidates(Delivery(tmp))
    got = {}
    for c in cands: got[c["target"]] = c
    cand_total += len(cands)
    tnames = {n for _, n in truth}
    for kind, n in truth:
        stats[kind][1] += 1
        c = got.get(n)
        hit = c is not None
        if hit: stats[kind][0] += 1
        if a.show and (not hit or (c["type"] != kind and c.get("alt") != kind)):
            extra = ""
            if kind == "bbox_drift":
                W_, H_, segs_, boxes_ = crosscheck.load_image(Delivery(tmp), n)
                fs = []
                for b in boxes_:
                    same = [s for s in segs_ if s["name"] == b["name"]]
                    if same:
                        s = max(same, key=lambda s: crosscheck.iou(b["px"], s["rect"]))
                        fs.append((round(crosscheck.iou(b["px"], s["rect"]), 2), round(crosscheck.cover(b, s), 3)))
                extra = " worst(iou,cover)=" + str(sorted(fs)[:2])
            print("  MISS" if not hit else f"  TYPE {c['type']}", kind, n, ("" if not hit else c["detail"][:160]) + extra)
    fps = [c for c in cands if c["target"] not in tnames]
    fp_total += len(fps)
    if a.show:
        for c in fps: print("  FP", c["type"], c["target"], c["detail"][:160])
    shutil.rmtree(tmp.parent)

print("recall theo loại:", {k: f"{v[0]}/{v[1]}" for k, v in stats.items()})
print(f"ứng viên {cand_total}, báo thừa (ảnh không gài lỗi) {fp_total}")
