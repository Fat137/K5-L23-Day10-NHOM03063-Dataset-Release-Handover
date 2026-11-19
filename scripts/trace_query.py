#!/usr/bin/env python3
"""Script tự động hóa truy vết ticket từ team AI (Pha 5 và Đề ẩn).

Sử dụng:
  python scripts/trace_query.py --delivery <thư_mục_delivery> --out <trace.json>

Logic truy vết:
  1. Trích xuất lớp bị đổi quy tắc (rule_class) từ guideline/changelog.md hoặc incoming/ticket.md.
  2. Trích xuất các cảnh team AI đã báo (reported scenes) từ incoming/ticket.md.
  3. Lọc các job thuộc guideline cũ (v1.2) từ jobs.csv.
  4. Quét labels/*.txt của các ảnh thuộc job cũ:
     - tier_a: ảnh nằm trong scene team AI nêu, job guideline cũ, có box detection của lớp đổi quy tắc.
     - tier_b: ảnh khác (không thuộc scene team AI nêu), job guideline cũ, có box detection của lớp đổi quy tắc.
  5. notify: danh sách người gán (annotator) và người kiểm (reviewer) của các job chứa ảnh tầng a và b.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def extract_rule_class(delivery_dir: Path) -> str | None:
    """Trích xuất tên lớp bị đổi quy tắc từ changelog.md hoặc ticket.md."""
    changelog_path = delivery_dir / "guideline" / "changelog.md"
    if changelog_path.is_file():
        text = changelog_path.read_text(encoding="utf-8")
        # Khớp: "- Lớp `car`: vật bị che..." hoặc "- Lớp car:"
        m = re.search(r"-\s*Lớp\s*[`'\"]?([a-zA-Z0-9_\s-]+?)[`'\"]?\s*:", text)
        if m:
            return m.group(1).strip()

    ticket_path = delivery_dir / "incoming" / "ticket.md"
    if ticket_path.is_file():
        text = ticket_path.read_text(encoding="utf-8")
        m = re.search(r"bỏ sót\s*[`'\"]?([a-zA-Z0-9_\s-]+?)[`'\"]?\s*(?:bị che|ở mép)", text)
        if m:
            return m.group(1).strip()

    return None


def extract_reported_scenes(delivery_dir: Path) -> list[str]:
    """Trích xuất danh sách scene_id được team AI báo trong ticket.md."""
    ticket_path = delivery_dir / "incoming" / "ticket.md"
    if not ticket_path.is_file():
        return []
    text = ticket_path.read_text(encoding="utf-8")
    scenes = re.findall(r"\b(scene_\w+)\b", text)
    return sorted(set(scenes))


def load_classes(delivery_dir: Path) -> dict[str, int]:
    """Đọc classes.txt trả về map {tên_lớp: class_id}."""
    path = delivery_dir / "classes.txt"
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[0].isdigit():
            out[parts[1].strip()] = int(parts[0])
    return out


def load_jobs(delivery_dir: Path) -> dict[str, dict[str, str]]:
    """Đọc jobs.csv trả về {job_id: {annotator, reviewer, guideline}}."""
    path = delivery_dir / "jobs.csv"
    jobs = {}
    if not path.is_file():
        return jobs
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jid = row.get("job_id", "").strip()
            if jid:
                jobs[jid] = {
                    "annotator": row.get("annotator", "").strip(),
                    "reviewer": row.get("reviewer", "").strip(),
                    "guideline": row.get("guideline", "").strip(),
                }
    return jobs


def load_metadata(delivery_dir: Path) -> dict[str, dict]:
    """Đọc metadata.json trả về {tên_ảnh: {scene_id, job_id, split}}."""
    path = delivery_dir / "metadata.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    out = {}
    for it in items:
        img = it.get("image", "").strip()
        if img:
            out[img] = {
                "scene_id": it.get("scene_id", "").strip(),
                "job_id": it.get("job_id", "").strip(),
                "split": it.get("split", "").strip(),
            }
    return out


def image_has_class(label_path: Path, target_class_id: int) -> bool:
    """Kiểm tra file nhãn YOLO có chứa box thuộc target_class_id không."""
    if not label_path.is_file():
        return False
    for line in label_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if parts:
            try:
                c = int(float(parts[0]))
                if c == target_class_id:
                    return True
            except ValueError:
                continue
    return False


def query_trace(delivery_dir: Path) -> dict:
    """Thực hiện truy vết toàn diện theo quy tắc của Day 10 lab."""
    rule_class = extract_rule_class(delivery_dir)
    if not rule_class:
        raise ValueError("Không tìm thấy tên lớp bị đổi quy tắc trong changelog.md hoặc ticket.md")

    reported_scenes = extract_reported_scenes(delivery_dir)
    classes = load_classes(delivery_dir)
    if rule_class not in classes:
        raise ValueError(f"Lớp '{rule_class}' không tồn tại trong classes.txt")
    target_class_id = classes[rule_class]

    jobs = load_jobs(delivery_dir)
    meta = load_metadata(delivery_dir)

    # Lọc job cũ (v1.2) theo jobs.csv
    old_jobs = {jid for jid, info in jobs.items() if info["guideline"] == "v1.2"}

    tier_a = []
    tier_b = []
    labels_dir = delivery_dir / "labels"

    for img_name, info in meta.items():
        job_id = info["job_id"]
        # Phải thuộc job guideline cũ
        if job_id not in old_jobs:
            continue

        label_file = labels_dir / f"{img_name}.txt"
        if image_has_class(label_file, target_class_id):
            if info["scene_id"] in reported_scenes:
                tier_a.append(img_name)
            else:
                tier_b.append(img_name)

    tier_a = sorted(tier_a)
    tier_b = sorted(tier_b)

    # Notify: annotator + reviewer của mọi job có ảnh trong tier_a và tier_b
    affected_jobs = {meta[img]["job_id"] for img in (tier_a + tier_b) if img in meta}
    notify_set = set()
    for jid in affected_jobs:
        if jid in jobs:
            if jobs[jid]["annotator"]:
                notify_set.add(jobs[jid]["annotator"])
            if jobs[jid]["reviewer"]:
                notify_set.add(jobs[jid]["reviewer"])

    notify = sorted(notify_set)

    return {
        "rule_class": rule_class,
        "reported_scenes": reported_scenes,
        "tier_a": tier_a,
        "tier_b": tier_b,
        "notify": notify,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Tự động truy vết ticket cho Day 10 lab")
    parser.add_argument("--delivery", required=True, help="Đường dẫn tới thư mục delivery")
    parser.add_argument("--out", required=True, help="Đường dẫn file trace.json đầu ra")
    args = parser.parse_args()

    delivery_dir = Path(args.delivery).resolve()
    if not delivery_dir.is_dir():
        print(f"Lỗi: Thư mục delivery không tồn tại: {delivery_dir}", file=sys.stderr)
        return 1

    try:
        result = query_trace(delivery_dir)
    except Exception as e:
        print(f"Lỗi khi thực hiện truy vết: {e}", file=sys.stderr)
        return 1

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    trace_doc = {
        "tier_a": result["tier_a"],
        "tier_b": result["tier_b"],
        "notify": result["notify"],
    }

    out_path.write_text(json.dumps(trace_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Truy vết thành công!")
    print(f"- Lớp bị đổi quy tắc: {result['rule_class']}")
    print(f"- Các scene được báo: {result['reported_scenes']}")
    print(f"- tier_a: {len(result['tier_a'])} ảnh")
    print(f"- tier_b: {len(result['tier_b'])} ảnh")
    print(f"- notify: {len(result['notify'])} người ({', '.join(result['notify'])})")
    print(f"Đã lưu kết quả tại: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
