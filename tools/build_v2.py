#!/usr/bin/env python3
"""Dựng lô v2 (sản phẩm detection) từ lô v1 + errors.json cuối, KHÔNG sửa gì trong delivery/.

  python tools/build_v2.py --run runs/r3063007
  python tools/build_v2.py --run runs/r3063007 --hong 000000001234      # ảnh wrong_hash đã mở ra thấy hỏng

Ghi runs/<run>/handover/<release_id>_v2/: images/, labels/, rework_queue.csv, manifest.csv,
label_summary.csv, truyvet.csv, README.txt. Sau đó chạy scripts/pack_release.py và lineage (xem GUIDE Pha 4).

Cách xử lý từng loại lỗi (GUIDE Pha 4):
  - Sửa ngay trong v2: wrong_hash (ảnh còn nguyên -> ghi hash mới), guideline_mismatch (guideline theo job),
    scene_leak (cả cảnh về một split, theo split đa số của cảnh).
  - Lỗi ở nhãn detection hoặc thiếu file: vào rework_queue và rời v2.
  - Lỗi chỉ ở panoptic: ảnh ở lại v2 (nhãn detection vẫn đúng), ghi vào Ghi chú để báo team panoptic.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

DET_REWORK = {"missing_image", "invalid_class", "bbox_out_of_bounds", "duplicate_box", "class_swap", "bbox_drift", "missing_box"}
PANOPTIC_ONLY = {"invalid_category_id", "thing_overlap", "category_swap", "instance_merge"}
FIX_IN_V2 = {"wrong_hash", "guideline_mismatch", "scene_leak"}
THRESHOLD = 0.02
ROOT = Path(__file__).resolve().parent.parent
ACTION = {
    "missing_image": "giao lại file ảnh rồi gán lại nhãn",
    "wrong_hash": "ảnh hỏng: thay ảnh gốc rồi gán lại nhãn",
    "invalid_class": "sửa class_id ngoài 0-79",
    "bbox_out_of_bounds": "sửa box tràn ra ngoài ảnh",
    "duplicate_box": "xoá box bị lặp",
    "class_swap": "sửa lớp của box gán nhầm",
    "bbox_drift": "vẽ lại box bị lệch khỏi vật",
    "missing_box": "thêm box còn thiếu",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jpeg_ok(path: Path, size: tuple[int, int] | None) -> tuple[bool, str]:
    """Kiểm cấu trúc JPEG bằng thư viện chuẩn: SOI, EOI, kích thước trong SOF khớp kích thước ảnh trong lô.
    Đây chỉ là kiểm máy; GUIDE yêu cầu NGƯỜI mở ảnh xem trước khi kết luận ảnh còn nguyên."""
    data = path.read_bytes()
    if not data.startswith(b"\xff\xd8"):
        return False, "không bắt đầu bằng FFD8"
    if b"\xff\xd9" not in data[-64:]:
        return False, "không có FFD9 ở cuối file"
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            if size and (w, h) != tuple(size):
                return False, f"kích thước {w}x{h} khác {size[0]}x{size[1]}"
            return True, f"JPEG {w}x{h}"
        i += 2 + seg_len
    return False, "không thấy SOF"


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def ranges(job_ids: list[str]) -> str:
    js = sorted(job_ids)
    return js[0] if len(js) == 1 else f"{js[0]}-{js[-1]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Dựng lô v2 không ghi đè v1")
    ap.add_argument("--run", required=True, help="thư mục runs/r<seed> (có delivery/ và errors.json)")
    ap.add_argument("--hong", default="", help="ảnh wrong_hash đã mở ra thấy HỎNG, cách nhau dấu phẩy (đưa vào rework)")
    ap.add_argument("--errors", default="", help="đường dẫn errors.json (mặc định <run>/errors.json)")
    ap.add_argument("--no-pack", action="store_true", help="không tự chạy scripts/pack_release.py ở cuối")
    args = ap.parse_args()
    run = Path(args.run)
    d = run / "delivery"
    rid = json.loads((d / "release.json").read_text(encoding="utf-8"))["release_id"]
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta = {m["image"]: m for m in json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]}
    with (d / "jobs.csv").open(encoding="utf-8-sig", newline="") as f:
        jobs = {row["job_id"]: row for row in csv.DictReader(f)}
    classes = {}
    for line in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            i, n = line.strip().split(" ", 1)
            classes[int(i)] = n.strip()
    pan = json.loads((d / "panoptic.json").read_text(encoding="utf-8"))
    sizes = {Path(im["file_name"]).stem: (im["width"], im["height"]) for im in pan["images"]}
    errors_path = Path(args.errors) if args.errors else run / "errors.json"
    errors = json.loads(errors_path.read_text(encoding="utf-8"))["errors"]
    hong = {x.strip() for x in args.hong.split(",") if x.strip()}

    # Phân loại lỗi theo ảnh
    by_image: dict[str, list[str]] = defaultdict(list)
    leak_scenes = set()
    for e in errors:
        if e["type"] == "scene_leak":
            leak_scenes.add(e["target"])
        else:
            by_image[e["target"]].append(e["type"])

    rework, panoptic_notes, hash_fixed, guideline_fixed = [], [], [], []
    for name, kinds in sorted(by_image.items()):
        if name not in man:
            print(f"BỎ QUA: {name} không có trong manifest v1")
            continue
        job = jobs[meta[name]["job_id"]]
        det = [k for k in kinds if k in DET_REWORK]
        if "wrong_hash" in kinds:
            ok, why = jpeg_ok(d / man[name]["image"], sizes.get(name))
            if name in hong or not ok:
                det.append("wrong_hash")
                print(f"wrong_hash {name}: đưa vào rework ({'nhóm đánh dấu hỏng' if name in hong else why})")
            else:
                hash_fixed.append(name)
                print(f"wrong_hash {name}: {why}, ảnh đọc được -> giữ, ghi hash mới. NHỚ MỞ ẢNH XEM TRƯỚC KHI CHỐT.")
        if det:
            rework.append([name, det[0], job["annotator"], job["reviewer"], ACTION[det[0]]])
        if "guideline_mismatch" in kinds:
            guideline_fixed.append(name)
        for k in kinds:
            if k in PANOPTIC_ONLY:
                panoptic_notes.append(f"{name} ({k})")
    rework_names = {r[0] for r in rework}

    # Split của cả cảnh theo đa số trong v1 (cảnh rò: chỉ một ảnh bị đặt lệch)
    scene_votes: dict[str, Counter] = defaultdict(Counter)
    for m in meta.values():
        scene_votes[m["scene_id"]][m["split"]] += 1
    scene_split = {sc: v.most_common(1)[0][0] for sc, v in scene_votes.items()}
    leak_fixed = []
    for sc in sorted(leak_scenes):
        moved = [m["image"] for m in meta.values() if m["scene_id"] == sc and m["split"] != scene_split[sc]]
        votes_txt = ", ".join(f"{k} {n}" for k, n in scene_votes[sc].most_common())
        leak_fixed.append(f"{sc}: {', '.join(moved)} ({votes_txt}) -> {scene_split[sc]}")

    # Ghi lô v2
    v2 = run / "handover" / f"{rid}_v2"
    if v2.exists():
        shutil.rmtree(v2)
    (v2 / "images").mkdir(parents=True)
    (v2 / "labels").mkdir()
    keep = [n for n in man if n not in rework_names]
    for n in keep:
        shutil.copyfile(d / man[n]["image"], v2 / "images" / Path(man[n]["image"]).name)
        shutil.copyfile(d / man[n]["label"], v2 / "labels" / Path(man[n]["label"]).name)

    write_csv(v2 / "rework_queue.csv", ["image", "type", "annotator", "reviewer", "action"], rework)
    files = sorted(p for sub in ("images", "labels") for p in (v2 / sub).iterdir() if p.is_file())
    write_csv(v2 / "manifest.csv", ["file", "sha256"], [[p.relative_to(v2).as_posix(), sha(p)] for p in files])

    counts: Counter = Counter()
    for n in keep:
        for line in (v2 / "labels" / Path(man[n]["label"]).name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = int(float(line.split()[0]))
                counts[classes.get(c, str(c))] += 1
    order = {name: i for i, name in classes.items()}
    summary = sorted(counts.items(), key=lambda kv: order.get(kv[0], 999))
    write_csv(v2 / "label_summary.csv", ["class", "count"], [[k, v] for k, v in summary] + [["TOTAL", sum(counts.values())]])

    write_csv(v2 / "truyvet.csv", ["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"],
              [[n, meta[n]["scene_id"], scene_split[meta[n]["scene_id"]], meta[n]["job_id"],
                jobs[meta[n]["job_id"]]["annotator"], jobs[meta[n]["job_id"]]["reviewer"], jobs[meta[n]["job_id"]]["guideline"]]
               for n in keep])

    by_version: dict[str, list[str]] = defaultdict(list)
    for j, row in jobs.items():
        by_version[row["guideline"]].append(j)
    guideline_line = ", ".join(f"{v} ({ranges(js)})" for v, js in sorted(by_version.items()))
    n_err = len({e["target"] for e in errors})
    rate = n_err / len(man)
    v1_decision = "Hold" if rate > THRESHOLD else "Release"
    rework_by_person = Counter(f"{r[2]}/{r[3]}" for r in rework)
    pct = f"{rate * 100:.1f}".replace(".", ",") + "%"
    lineage = run.parent / "lineage.jsonl"
    trained = sorted({e.get("run_id") for e in (json.loads(x) for x in lineage.read_text(encoding="utf-8").splitlines() if x.strip())
                      if e.get("event") == "train" and e.get("release_id") == rid}) if lineage.is_file() else []
    runs_txt = ", ".join(trained) + " đã train trên v1 phải xem lại hoặc train lại" if trained else "chưa có run nào train trên v1"
    readme = [
        f"Release: {rid}_v2",
        f"Parent: {rid}",
        f"Số ảnh: {len(keep)}",
        f"Số nhãn: {sum(counts.values())}",
        f"Guideline: {guideline_line}",
        f"QC v1: {n_err}/{len(man)} = {pct}",
        f"Kết luận v1: {v1_decision} — {n_err} ảnh/cảnh lỗi trên {len(man)} ảnh = {pct}, "
        + (f"vượt ngưỡng 2% nên không Release; {runs_txt}" if rate > THRESHOLD else "không vượt ngưỡng 2%"),
        f"Kết luận v2: Release — sản phẩm detection: tách {len(rework)} ảnh lỗi nhãn detection/thiếu file sang rework_queue, "
        f"sửa {len(hash_fixed)} hash, {len(guideline_fixed)} guideline, {len(leak_scenes)} cảnh rò split; nhãn detection còn lại giữ nguyên như v1",
        "Ghi chú: "
        + (f"Hash: {', '.join(hash_fixed)} đã mở ảnh kiểm, ảnh còn nguyên, ghi sha256 mới trong manifest.csv. " if hash_fixed else "")
        + (f"Guideline: {', '.join(guideline_fixed)} ghi lại theo guideline của job trong truyvet.csv. " if guideline_fixed else "")
        + (f"Split: {'; '.join(leak_fixed)} (cả cảnh về split đa số). " if leak_fixed else "")
        + (f"Rework giao lại người gán/người kiểm của job: {', '.join(f'{k} ({v} ảnh)' for k, v in sorted(rework_by_person.items()))}. " if rework else "")
        + (f"Lỗi chỉ ở panoptic, ảnh ở lại v2 vì nhãn detection đúng, báo team panoptic: {', '.join(panoptic_notes)}." if panoptic_notes else ""),
    ]
    (v2 / "README.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(f"v2: {len(keep)} ảnh, {sum(counts.values())} nhãn, rework {len(rework)} -> {v2}")
    print("\n".join(readme))
    if not args.no_pack:
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "pack_release.py"), str(v2)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
