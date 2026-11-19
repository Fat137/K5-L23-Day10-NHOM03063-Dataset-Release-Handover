"""Đọc một thư mục delivery/ thành một đối tượng dùng chung cho rules.py và crosscheck.py.

Chỉ dùng thư viện chuẩn và scripts/pngutil.py. Chỉ đọc thư mục delivery được truyền vào.
"""

from __future__ import annotations

import csv
import json
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pngutil  # noqa: E402


def read_csv(path: Path) -> list[dict]:
    # utf-8-sig: chịu được file có BOM (lưu từ Excel)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def png_size(path: Path) -> tuple[int, int] | None:
    """Đọc width, height từ IHDR của PNG, không giải nén ảnh."""
    try:
        head = path.read_bytes()[:24]
    except OSError:
        return None
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


class Delivery:
    def __init__(self, root: Path):
        self.root = Path(root)
        r = self.root
        # classes.txt: "id tên" (tên có thể có dấu cách, ví dụ "traffic light")
        self.classes: dict[int, str] = {}
        for line in (r / "classes.txt").read_text(encoding="utf-8").splitlines():
            if line.strip():
                idx, name = line.strip().split(" ", 1)
                self.classes[int(idx)] = name.strip()

        self.manifest: dict[str, dict] = json.loads((r / "manifest.json").read_text(encoding="utf-8"))["items"]
        self.meta: dict[str, dict] = {
            row["image"]: row for row in json.loads((r / "metadata.json").read_text(encoding="utf-8"))["items"]
        }
        self.jobs: dict[str, dict] = {row["job_id"]: row for row in read_csv(r / "jobs.csv")}

        pan = json.loads((r / "panoptic.json").read_text(encoding="utf-8"))
        self.categories: dict[int, dict] = {c["id"]: c for c in pan["categories"]}
        images_by_id = {im["id"]: im for im in pan["images"]}
        # panoptic: ghép theo tên file (stem), không theo image_id
        self.pan_image: dict[str, dict] = {Path(im["file_name"]).stem: im for im in pan["images"]}
        self.pan_ann: dict[str, dict] = {}
        for ann in pan["annotations"]:
            stem = Path(ann["file_name"]).stem
            if ann.get("image_id") in images_by_id:
                stem = Path(images_by_id[ann["image_id"]]["file_name"]).stem
            self.pan_ann[stem] = ann

        # Danh sách ảnh: hợp của manifest và metadata (giữ thứ tự manifest)
        self.images: list[str] = list(self.manifest) + [n for n in self.meta if n not in self.manifest]
        self._labels: dict[str, list[list[str]]] = {}
        self._counts: dict[str, Counter] = {}

    # ---------------------------------------------------------------- đường dẫn
    def path(self, name: str, kind: str) -> Path:
        """kind = image | label | mask. Ưu tiên đường dẫn ghi trong manifest."""
        rel = self.manifest.get(name, {}).get(kind)
        if rel:
            return self.root / rel
        folder, ext = {"image": ("images", ".jpg"), "label": ("labels", ".txt"), "mask": ("masks", ".png")}[kind]
        return self.root / folder / f"{name}{ext}"

    # ---------------------------------------------------------------- kích thước
    def size(self, name: str) -> tuple[int, int] | None:
        im = self.pan_image.get(name)
        if im and im.get("width") and im.get("height"):
            return int(im["width"]), int(im["height"])
        return png_size(self.path(name, "mask"))

    # ---------------------------------------------------------------- nhãn YOLO
    def label_rows(self, name: str) -> list[list[str]]:
        """Các dòng của file nhãn, mỗi dòng là list token (chưa ép kiểu)."""
        if name not in self._labels:
            p = self.path(name, "label")
            text = p.read_text(encoding="utf-8") if p.is_file() else ""
            self._labels[name] = [line.split() for line in text.splitlines() if line.strip()]
        return self._labels[name]

    def boxes(self, name: str) -> list[dict]:
        """Box hợp lệ về cú pháp: {cls, x, y, w, h} (chuẩn hoá 0-1), kèm px nếu biết kích thước ảnh."""
        out = []
        size = self.size(name)
        for i, row in enumerate(self.label_rows(name)):
            if len(row) != 5:
                continue
            try:
                cls = int(row[0])
                x, y, w, h = (float(v) for v in row[1:5])
            except ValueError:
                continue
            box = {"i": i, "cls": cls, "x": x, "y": y, "w": w, "h": h}
            if size:
                W, H = size
                box["px"] = ((x - w / 2) * W, (y - h / 2) * H, (x + w / 2) * W, (y + h / 2) * H)
            out.append(box)
        return out

    # ---------------------------------------------------------------- mask panoptic
    def mask(self, name: str) -> tuple[int, int, bytearray] | None:
        p = self.path(name, "mask")
        if not p.is_file():
            return None
        return pngutil.read_rgb(p)

    def segment_pixel_counts(self, name: str) -> Counter:
        """Số pixel của từng segment id trong mask (id = R + G*256 + B*256^2), không tính id 0."""
        if name not in self._counts:
            m = self.mask(name)
            counts: Counter = Counter()
            if m:
                _, _, px = m
                # zip + Counter chạy trong C, nhanh hơn vòng for theo từng pixel
                for (r, g, b), n in Counter(zip(px[0::3], px[1::3], px[2::3])).items():
                    sid = r + g * 256 + b * 65536
                    if sid:
                        counts[sid] = n
            self._counts[name] = counts
        return self._counts[name]
