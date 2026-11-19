#!/usr/bin/env python3
"""Gộp các file review của từng người (review_<mã>.csv) thành một review_log.csv.

  python tools/gop_review.py --dir work --out runs/r3063007/review_log.csv --candidates runs/r3063007/candidates.json
  python tools/gop_review.py --dir work/de_an --out submission/de_an/review_log.csv --candidates submission/de_an/candidates.json

Mỗi file có cột image,type,verdict,note. Script KHÔNG tự quyết verdict: chỉ ghép, kiểm định dạng và báo
chỗ cần người chốt (hai người ghi khác nhau, ghi chú quá ngắn hoặc chép giống nhau, ứng viên chưa ai xem).
Ghi ra UTF-8 không BOM để scripts/merge_review.py đọc được.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

SEMANTIC = {"class_swap", "bbox_drift", "missing_box", "category_swap", "instance_merge"}
VERDICTS = {"confirmed", "rejected"}
FIELDS = ["image", "type", "verdict", "note"]
MIN_NOTE = 20


def main() -> int:
    ap = argparse.ArgumentParser(description="Gộp review của cả nhóm thành review_log.csv")
    ap.add_argument("--dir", required=True, help="thư mục chứa review_*.csv")
    ap.add_argument("--out", required=True, help="review_log.csv đầu ra")
    ap.add_argument("--candidates", help="candidates.json, để báo ứng viên chưa ai xem")
    args = ap.parse_args()

    files = sorted(Path(args.dir).glob("review_*.csv"))
    if not files:
        raise SystemExit(f"không có file review_*.csv trong {args.dir}")

    problems: list[str] = []
    rows: list[dict] = []
    for f in files:
        with f.open(encoding="utf-8-sig", newline="") as handle:  # bỏ BOM nếu file lưu từ Excel
            reader = csv.DictReader(handle)
            if [h.strip() for h in (reader.fieldnames or [])] != FIELDS:
                problems.append(f"{f.name}: tiêu đề phải là {','.join(FIELDS)}, đang là {reader.fieldnames}")
                continue
            for line_no, raw in enumerate(reader, start=2):
                row = {k: (raw.get(k) or "").strip() for k in FIELDS}
                if not any(row.values()):
                    continue
                where = f"{f.name}:{line_no}"
                if row["verdict"] not in VERDICTS:
                    problems.append(f"{where}: verdict '{row['verdict']}' phải là confirmed hoặc rejected")
                if row["type"] not in SEMANTIC:
                    problems.append(f"{where}: type '{row['type']}' không phải lỗi gán nhãn")
                if len(row["note"]) < MIN_NOTE:
                    problems.append(f"{where}: ghi chú dưới {MIN_NOTE} ký tự, phải nói rõ thấy gì")
                if not row["note"].startswith("["):
                    problems.append(f"{where}: ghi chú nên mở đầu bằng [mã người xem]")
                row["_from"] = where
                rows.append(row)

    # Cùng (ảnh, type) xuất hiện nhiều lần: cùng verdict thì giữ dòng đầu, khác verdict thì phải chốt
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_key[(row["image"], row["type"])].append(row)
    merged = []
    for (image, kind), group in sorted(by_key.items()):
        verdicts = {r["verdict"] for r in group}
        if len(verdicts) > 1:
            problems.append(f"{image} {kind}: ghi khác nhau ({', '.join(r['_from'] + '=' + r['verdict'] for r in group)}), cần chốt")
        merged.append(group[0])

    # Mỗi ảnh mang nhiều nhất một lỗi
    confirmed_types = defaultdict(list)
    for row in merged:
        if row["verdict"] == "confirmed":
            confirmed_types[row["image"]].append(row["type"])
    for image, kinds in confirmed_types.items():
        if len(kinds) > 1:
            problems.append(f"{image}: confirmed {len(kinds)} lỗi {kinds}, mỗi ảnh chỉ mang một lỗi, cần chốt")

    notes = defaultdict(list)
    for row in merged:
        notes[row["note"]].append(row["image"])
    for note, images in notes.items():
        if len(images) > 1:
            problems.append(f"ghi chú chép giống nhau ở {images}: '{note[:40]}...'")

    if args.candidates:
        cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))["candidates"]
        seen = {row["image"] for row in merged}
        missing = sorted({c["target"] for c in cands} - seen)
        if missing:
            problems.append(f"{len(missing)} ảnh ứng viên chưa ai xem: {missing[:10]}{' ...' if len(missing) > 10 else ''}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:  # không BOM
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged)

    n_conf = sum(r["verdict"] == "confirmed" for r in merged)
    print(f"{len(files)} file, {len(merged)} dòng ({n_conf} confirmed, {len(merged) - n_conf} rejected) -> {out}")
    if problems:
        print(f"\nCẦN XỬ LÝ ({len(problems)}):")
        for p in problems:
            print(" -", p)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
