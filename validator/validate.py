#!/usr/bin/env python3
"""Validator của nhóm 03063.

  python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]

--out          : lỗi luật (9 loại), mỗi mục {type, target, detail}.
--candidates   : ứng viên lỗi gán nhãn từ đối chiếu detection <-> panoptic (validator/crosscheck.py),
                 phải được người xem ảnh xác nhận trước khi đưa vào errors.json cuối.

Chỉ đọc thư mục delivery được truyền vào, chỉ dùng thư viện chuẩn (+ scripts/pngutil.py), không dùng mạng.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Delivery  # noqa: E402
import rules  # noqa: E402


def write_json(path: Path, key: str, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({key: items}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def summary(items: list[dict]) -> str:
    c = Counter(i["type"] for i in items)
    return ", ".join(f"{k}={v}" for k, v in sorted(c.items())) or "không có"


def main() -> int:
    ap = argparse.ArgumentParser(description="Validator lô bàn giao (nhóm 03063)")
    ap.add_argument("delivery", help="thư mục delivery/")
    ap.add_argument("--out", required=True, help="file errors.json (lỗi luật)")
    ap.add_argument("--candidates", help="file candidates.json (ứng viên lỗi gán nhãn)")
    args = ap.parse_args()

    root = Path(args.delivery)
    if not (root / "manifest.json").is_file():
        raise SystemExit(f"{root} không phải thư mục delivery (thiếu manifest.json)")
    d = Delivery(root)

    errors = rules.run_all(d)
    errors.sort(key=lambda e: (e["type"], e["target"]))
    write_json(Path(args.out), "errors", errors)
    print(f"{len(d.images)} ảnh. Lỗi luật: {len(errors)} ({summary(errors)}) -> {args.out}")

    if args.candidates:
        try:
            import crosscheck  # validator/crosscheck.py (phần đối chiếu)
        except ImportError:
            print("CHƯA CÓ validator/crosscheck.py: ghi candidates rỗng", file=sys.stderr)
            cands = []
        else:
            cands = crosscheck.find_candidates(d)
        # Ảnh đã có lỗi luật thì không đưa vào hàng đợi (mỗi ảnh mang nhiều nhất một lỗi)
        rule_images = {e["target"] for e in errors}
        cands = [c for c in cands if c["target"] not in rule_images]
        cands.sort(key=lambda c: (c["target"], c["type"]))
        write_json(Path(args.candidates), "candidates", cands)
        print(f"Ứng viên lỗi gán nhãn: {len(cands)} ({summary(cands)}) -> {args.candidates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
