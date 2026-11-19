#!/usr/bin/env python3
"""Unit test cho scripts/review_tool.py."""

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from review_tool import load_classes, load_yolo_boxes, append_review_log, generate_html_viewer, render_image


class TestReviewTool(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.delivery = Path(self.temp_dir) / "delivery"
        (self.delivery / "images").mkdir(parents=True)
        (self.delivery / "labels").mkdir(parents=True)

        # 1. classes.txt
        (self.delivery / "classes.txt").write_text("0 person\n1 car\n2 truck\n", encoding="utf-8")

        # 2. labels/test_img.txt (YOLO format: class x_center y_center width height)
        # 100x100 image: box center=(50, 50), w=20, h=20 -> x1=40, y1=40, x2=60, y2=60
        (self.delivery / "labels" / "test_img.txt").write_text("1 0.5 0.5 0.2 0.2\n", encoding="utf-8")

        # 3. Create a synthetic test image using PIL
        from PIL import Image
        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        img.save(self.delivery / "images" / "test_img.jpg")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_classes(self):
        classes = load_classes(self.delivery)
        self.assertEqual(classes[0], "person")
        self.assertEqual(classes[1], "car")
        self.assertEqual(classes[2], "truck")

    def test_load_yolo_boxes(self):
        boxes = load_yolo_boxes(self.delivery / "labels" / "test_img.txt", 100, 100)
        self.assertEqual(len(boxes), 1)
        b = boxes[0]
        self.assertEqual(b["class_id"], 1)
        self.assertEqual((b["x1"], b["y1"], b["x2"], b["y2"]), (40, 40, 60, 60))

    def test_append_review_log(self):
        csv_path = Path(self.temp_dir) / "review_log.csv"
        append_review_log(csv_path, "test_img", "class_swap", "confirmed", "Xe tải mui kín nhưng gán nhầm sang car")
        append_review_log(csv_path, "test_img_2", "bbox_drift", "rejected", "Vật bị che khuất tự nhiên của COCO")

        with csv_path.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["image"], "test_img")
        self.assertEqual(rows[0]["verdict"], "confirmed")
        self.assertEqual(rows[1]["verdict"], "rejected")

    def test_render_image(self):
        out_render = Path(self.temp_dir) / "rendered.jpg"
        img = render_image(self.delivery, "test_img", out_path=out_render, show=False)
        self.assertIsNotNone(img)
        self.assertTrue(out_render.is_file())

    def test_generate_html_viewer(self):
        cand_path = Path(self.temp_dir) / "candidates.json"
        cand_path.write_text(json.dumps({
            "candidates": [
                {"image": "test_img", "type": "class_swap", "details": "Nghi vấn car/truck"}
            ]
        }), encoding="utf-8")

        out_html = Path(self.temp_dir) / "viewer.html"
        generate_html_viewer(self.delivery, cand_path, out_html)
        self.assertTrue(out_html.is_file())
        content = out_html.read_text(encoding="utf-8")
        self.assertIn("test_img", content)
        self.assertIn("class_swap", content)
        self.assertIn("char-indicator", content)


if __name__ == "__main__":
    unittest.main()
