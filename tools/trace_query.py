"""Truy vết ticket của team AI: sinh trace.json (tier_a, tier_b, notify) cho lô bất kỳ.

    py -X utf8 tools/trace_query.py <thư_mục_delivery> --out <trace.json>

Không ghi cứng lớp hay scene: đọc từ incoming/ticket.md và guideline/changelog.md.
- Lớp bị đổi quy tắc: lớp (trong backtick) được nêu ở mục phiên bản MỚI NHẤT của changelog
  và cũng có trong classes.txt; nếu ticket nêu lớp thì ưu tiên lớp có trong cả hai.
- Guideline "cũ": mọi phiên bản nhỏ hơn phiên bản mới nhất đó.
- Guideline của ảnh lấy theo JOB (jobs.csv qua job_id trong metadata), không theo
  guideline_version của ảnh (có thể chính là lỗi guideline_mismatch).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def read_classes(path: Path) -> dict[str, int]:
    out = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            out[parts[1].strip()] = int(parts[0])
    return out


def parse_changelog(text: str) -> tuple[str, list[str]]:
    """Trả về (phiên bản mới nhất, các lớp trong backtick ở mục đó)."""
    sections: dict[str, str] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^#{2,}\s*(v\d+(?:\.\d+)*)", line.strip())
        if m:
            cur = m.group(1)
            sections[cur] = ""
        elif cur:
            sections[cur] += line + "\n"
    if not sections:
        raise SystemExit("changelog.md không có mục phiên bản (## vX.Y)")
    newest = max(sections, key=vkey)
    names = re.findall(r"`([^`]+)`", sections[newest])
    return newest, names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("delivery")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    d = Path(args.delivery)

    classes = read_classes(d / "classes.txt")
    ticket = (d / "incoming" / "ticket.md").read_text(encoding="utf-8-sig")
    newest, changed = parse_changelog((d / "guideline" / "changelog.md").read_text(encoding="utf-8-sig"))
    ticket_names = re.findall(r"`([^`]+)`", ticket)
    changed = [c for c in changed if c in classes]
    both = [c for c in changed if c in ticket_names]
    targets = sorted(set(both or changed))
    if not targets:
        raise SystemExit("Không tìm thấy lớp bị đổi quy tắc trong changelog")
    class_ids = {classes[c] for c in targets}
    scenes = set(re.findall(r"scene_\d+", ticket))

    jobs = {}
    with (d / "jobs.csv").open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            jobs[row["job_id"].strip()] = row
    old_jobs = {j for j, r in jobs.items() if vkey(r["guideline"]) < vkey(newest)}

    meta = json.loads((d / "metadata.json").read_text(encoding="utf-8-sig"))
    items = meta["items"] if isinstance(meta, dict) else meta

    tier_a, tier_b, notify = [], [], set()
    for it in items:
        img, job = it["image"], str(it.get("job_id", "")).strip()
        if job not in old_jobs:
            continue
        lab = d / "labels" / f"{img}.txt"
        if not lab.exists():
            continue
        has = False
        for line in lab.read_text(encoding="utf-8-sig").splitlines():
            p = line.split()
            if p and p[0].lstrip("-").isdigit() and int(p[0]) in class_ids:
                has = True
                break
        if not has:
            continue
        (tier_a if it.get("scene_id") in scenes else tier_b).append(img)
        notify.update({jobs[job]["annotator"].strip(), jobs[job]["reviewer"].strip()})

    out = {"tier_a": sorted(tier_a), "tier_b": sorted(tier_b), "notify": sorted(notify)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Lớp đổi quy tắc: {targets} (guideline mới {newest}; job cũ: {sorted(old_jobs)})")
    print(f"Scene ticket nêu: {sorted(scenes)}")
    print(f"tier_a={len(tier_a)} tier_b={len(tier_b)} notify={out['notify']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
