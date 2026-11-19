#!/usr/bin/env python3
"""Dựng lô v2 (detection) từ delivery v1 + errors.json đã chốt, rồi đóng gói.

  py -X utf8 tools/build_v2.py --run runs/r3063007 --errors runs/r3063007/errors.json

Không sửa gì trong <run>/delivery. Ghi <run>/handover/<release_id>_v2/ (xoá bản cũ rồi dựng lại),
sau đó gọi scripts/pack_release.py. Chạy lại được bất cứ lúc nào errors.json thay đổi.

Quy tắc (GUIDE Pha 4):
- Lỗi nhãn detection hoặc thiếu file -> rework_queue.csv, ảnh rời v2.
- wrong_hash: mở ảnh bằng Pillow; mở được thì giữ ảnh, manifest.csv ghi hash mới; hỏng thì rework.
- guideline_mismatch: truyvet.csv lấy guideline theo job. scene_leak: cả cảnh về split đa số.
- Lỗi chỉ ở panoptic: ảnh ở lại v2, ghi vào README để báo team panoptic.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

DET_REWORK = {"missing_image", "invalid_class", "bbox_out_of_bounds", "duplicate_box",
              "class_swap", "bbox_drift", "missing_box"}
PANOPTIC_ONLY = {"invalid_category_id", "thing_overlap", "category_swap", "instance_merge"}
ACTION = {
    "missing_image": "bổ sung lại file ảnh rồi gán lại",
    "invalid_class": "sửa class_id ngoài 0-79",
    "bbox_out_of_bounds": "kẻ lại box tràn ra ngoài ảnh",
    "duplicate_box": "xoá box lặp",
    "class_swap": "gán lại đúng lớp",
    "bbox_drift": "kẻ lại box ôm sát vật",
    "missing_box": "thêm box còn thiếu",
    "wrong_hash": "ảnh không mở được: lấy lại ảnh gốc rồi gán lại",
}
THRESHOLD = 0.02
ROOT = Path(__file__).resolve().parent.parent


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def image_ok(p: Path) -> bool:
    try:
        from PIL import Image
        with Image.open(p) as im:
            im.load()
        return True
    except Exception:
        return False


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    # Không BOM: check_handover.py đọc bằng utf-8 thường.
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def job_ranges(jobs: dict) -> str:
    by = {}
    for jid in sorted(jobs):
        by.setdefault(jobs[jid]["guideline"], []).append(jid)
    return ", ".join(f"{g} ({ids[0]}-{ids[-1]})" if len(ids) > 1 else f"{g} ({ids[0]})" for g, ids in sorted(by.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description="Dựng lô v2 từ errors.json")
    ap.add_argument("--run", required=True)
    ap.add_argument("--errors", required=True)
    ap.add_argument("--no-pack", action="store_true")
    a = ap.parse_args()

    run = Path(a.run)
    d = run / "delivery"
    rid = json.loads((d / "release.json").read_text(encoding="utf-8"))["release_id"]
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta = {m["image"]: m for m in json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]}
    with (d / "jobs.csv").open(encoding="utf-8-sig", newline="") as f:
        jobs = {r["job_id"]: r for r in csv.DictReader(f)}
    names = {}
    for ln in (d / "classes.txt").read_text(encoding="utf-8").splitlines():
        if ln.strip():
            i, n = ln.split(" ", 1)
            names[int(i)] = n.strip()
    errors = json.loads(Path(a.errors).read_text(encoding="utf-8"))["errors"]

    # Ảnh nào vào rework, vì lỗi gì
    rework: dict[str, str] = {}
    fixed_hash, broken_hash, panoptic, mismatch, leaks = [], [], [], [], []
    for e in errors:
        t, tg = e["type"], e["target"]
        if t in DET_REWORK and tg in man:
            rework.setdefault(tg, t)
        elif t == "wrong_hash" and tg in man:
            if image_ok(d / man[tg]["image"]):
                fixed_hash.append(tg)
            else:
                broken_hash.append(tg)
                rework.setdefault(tg, t)
        elif t in PANOPTIC_ONLY:
            panoptic.append(f"{tg} ({t})")
        elif t == "guideline_mismatch":
            mismatch.append(tg)
        elif t == "scene_leak":
            leaks.append(tg)

    # Split đa số của từng cảnh (tính trên toàn v1)
    scene_split = {}
    by_scene = {}
    for m in meta.values():
        by_scene.setdefault(m["scene_id"], []).append(m["split"])
    for sc, sp in by_scene.items():
        cnt = Counter(sp)
        scene_split[sc] = max(sorted(cnt), key=lambda s: (cnt[s], s == "train"))

    v2 = run / "handover" / f"{rid}_v2"
    if v2.exists():
        shutil.rmtree(v2)
    (v2 / "images").mkdir(parents=True)
    (v2 / "labels").mkdir()

    kept = []
    for name in sorted(man):
        it = man[name]
        if name in rework or not (d / it["image"]).is_file():
            continue
        shutil.copy2(d / it["image"], v2 / "images" / Path(it["image"]).name)
        shutil.copy2(d / it["label"], v2 / "labels" / Path(it["label"]).name)
        kept.append(name)

    # rework_queue.csv
    rows = []
    for name in sorted(rework):
        job = jobs[meta[name]["job_id"]]
        rows.append([name, rework[name], job["annotator"], job["reviewer"], ACTION.get(rework[name], "gán lại")])
    write_csv(v2 / "rework_queue.csv", ["image", "type", "annotator", "reviewer", "action"], rows)

    # manifest.csv
    rows = [[p.relative_to(v2).as_posix(), sha(p)]
            for sub in ("images", "labels") for p in sorted((v2 / sub).iterdir()) if p.is_file()]
    write_csv(v2 / "manifest.csv", ["file", "sha256"], rows)

    # label_summary.csv
    counts = Counter()
    for name in kept:
        for ln in (v2 / "labels" / f"{name}.txt").read_text(encoding="utf-8").splitlines():
            if ln.strip():
                counts[int(float(ln.split()[0]))] += 1
    rows = [[names.get(c, str(c)), counts[c]] for c in sorted(counts)]
    total = sum(counts.values())
    rows.append(["TOTAL", total])
    write_csv(v2 / "label_summary.csv", ["class", "count"], rows)

    # truyvet.csv
    rows = []
    for name in kept:
        m = meta[name]
        job = jobs[m["job_id"]]
        rows.append([name, m["scene_id"], scene_split[m["scene_id"]], m["job_id"],
                     job["annotator"], job["reviewer"], job["guideline"]])
    write_csv(v2 / "truyvet.csv", ["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"], rows)

    # README.txt
    n_err = len({e["target"] for e in errors})
    rate = n_err / len(man)
    v1 = "Hold" if rate > THRESHOLD else "Release"
    owners = sorted({f"{r[2]}/{r[3]}" for r in csv.reader((v2 / "rework_queue.csv").open(encoding="utf-8"))
                     if r[0] != "image"})
    leak_note = "; ".join(f"{sc} về {scene_split[sc]}" for sc in leaks) or "không có"
    notes = [
        f"split: đưa cả cảnh về split đa số ({leak_note})",
        f"hash: {len(fixed_hash)} ảnh sai hash đã mở kiểm bằng Pillow (đọc được toàn bộ), ảnh còn nguyên nên giữ và ghi hash mới trong manifest.csv"
        + (f" ({', '.join(fixed_hash)})" if fixed_hash else "")
        + (f"; {len(broken_hash)} ảnh hỏng chuyển rework ({', '.join(broken_hash)})" if broken_hash else ""),
        f"guideline: truyvet.csv lấy guideline theo job trong jobs.csv ({len(mismatch)} ảnh metadata ghi sai"
        + (f": {', '.join(mismatch)}" if mismatch else "") + ")",
        f"rework: {len(rework)} ảnh lỗi nhãn detection/thiếu file trong rework_queue.csv, giao lại đúng người gán/kiểm theo job"
        + (f" ({', '.join(owners)})" if owners else ""),
        "panoptic: ảnh chỉ lỗi panoptic ở lại v2, báo team panoptic sửa: " + (", ".join(panoptic) or "không có"),
    ]
    readme = [
        f"Release: {rid}_v2",
        f"Parent: {rid}",
        f"Số ảnh: {len(kept)}",
        f"Số nhãn: {total}",
        f"Guideline: {job_ranges(jobs)}",
        f"QC v1: {n_err}/{len(man)} = {rate * 100:.1f}%".replace(".", ","),
        f"Kết luận v1: {v1} — {rate * 100:.1f}% ảnh/cảnh lỗi ".replace(".", ",")
        + ("vượt ngưỡng 2%" if v1 == "Hold" else "không vượt ngưỡng 2%"),
        f"Kết luận v2: Release — đã tách {len(rework)} ảnh lỗi detection sang rework, sửa split/hash/guideline; "
        f"còn {len(panoptic)} ảnh lỗi panoptic chờ team panoptic (không ảnh hưởng nhãn detection)",
        "Ghi chú: " + " | ".join(notes),
    ]
    (v2 / "README.txt").write_text("\n".join(readme) + "\n", encoding="utf-8")

    print(f"{v2}: {len(kept)} ảnh, {total} nhãn, rework {len(rework)}, QC v1 {n_err}/{len(man)} = {rate:.1%} -> {v1}")
    if not a.no_pack:
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "pack_release.py"), str(v2)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
