#!/usr/bin/env python3
"""Unit test cho scripts/trace_query.py."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from trace_query import query_trace


class TestTraceQuery(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.delivery = Path(self.temp_dir) / "delivery"
        (self.delivery / "guideline").mkdir(parents=True)
        (self.delivery / "incoming").mkdir(parents=True)
        (self.delivery / "labels").mkdir(parents=True)

        # 1. changelog
        (self.delivery / "guideline" / "changelog.md").write_text(
            "# Changelog guideline\n\n"
            "## v1.3\n"
            "- Lớp `car`: vật bị che trên 50% hoặc cắt ở mép ảnh **vẫn phải gán box** "
            "(v1.2 cho phép bỏ qua). Áp dụng cho mọi job tạo sau khi v1.3 ban hành.\n"
            "- Không đổi quy tắc của lớp khác.\n\n"
            "## v1.2\n- Bản dùng cho các job đầu của lô.\n",
            encoding="utf-8",
        )

        # 2. ticket
        (self.delivery / "incoming" / "ticket.md").write_text(
            "# Báo lỗi từ team AI\n\n"
            "Model train trên lô này hay bỏ sót `car` bị che hoặc ở mép ảnh. "
            "Bọn mình xem tay thấy rõ ở scene_101 và scene_102: nhiều `car` bị che không có box. "
            "Nhờ team dữ liệu kiểm tra và cho biết còn ảnh nào khác bị như vậy không.\n",
            encoding="utf-8",
        )

        # 3. classes.txt
        (self.delivery / "classes.txt").write_text(
            "0 person\n1 bicycle\n2 car\n3 motorcycle\n", encoding="utf-8"
        )

        # 4. jobs.csv
        (self.delivery / "jobs.csv").write_text(
            "job_id,annotator,reviewer,guideline\n"
            "job_01,userA,userR1,v1.2\n"
            "job_02,userB,userR2,v1.2\n"
            "job_03,userC,userR3,v1.3\n",
            encoding="utf-8",
        )

        # 5. metadata.json
        meta_items = [
            {"image": "img_01", "scene_id": "scene_101", "job_id": "job_01", "split": "train"},
            {"image": "img_02", "scene_id": "scene_102", "job_id": "job_01", "split": "train"},
            {"image": "img_03", "scene_id": "scene_103", "job_id": "job_02", "split": "train"},
            {"image": "img_04", "scene_id": "scene_104", "job_id": "job_02", "split": "train"},
            {"image": "img_05", "scene_id": "scene_101", "job_id": "job_03", "split": "train"},
            {"image": "img_06", "scene_id": "scene_102", "job_id": "job_01", "split": "train"},
        ]
        (self.delivery / "metadata.json").write_text(
            json.dumps({"items": meta_items}), encoding="utf-8"
        )

        # 6. labels
        # img_01: has car (class 2), scene_101 (in ticket), job_01 (v1.2) -> tier_a
        (self.delivery / "labels" / "img_01.txt").write_text("2 0.5 0.5 0.2 0.2\n", encoding="utf-8")
        # img_02: has car, scene_102 (in ticket), job_01 (v1.2) -> tier_a
        (self.delivery / "labels" / "img_02.txt").write_text("2 0.4 0.4 0.1 0.1\n", encoding="utf-8")
        # img_03: has car, scene_103 (NOT in ticket), job_02 (v1.2) -> tier_b
        (self.delivery / "labels" / "img_03.txt").write_text("2 0.6 0.6 0.3 0.3\n", encoding="utf-8")
        # img_04: person (class 0), NO car -> ignored
        (self.delivery / "labels" / "img_04.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
        # img_05: has car, scene_101, BUT job_03 is v1.3 (new guideline) -> ignored
        (self.delivery / "labels" / "img_05.txt").write_text("2 0.5 0.5 0.2 0.2\n", encoding="utf-8")
        # img_06: empty label -> ignored
        (self.delivery / "labels" / "img_06.txt").write_text("", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_query_trace(self):
        res = query_trace(self.delivery)
        self.assertEqual(res["rule_class"], "car")
        self.assertEqual(res["reported_scenes"], ["scene_101", "scene_102"])
        self.assertEqual(res["tier_a"], ["img_01", "img_02"])
        self.assertEqual(res["tier_b"], ["img_03"])
        self.assertEqual(res["notify"], ["userA", "userB", "userR1", "userR2"])

        # Kiểm tra theo tiêu chuẩn H16 của check_handover.py:
        # 1. tier_a, tier_b, notify đều là list
        for k in ("tier_a", "tier_b", "notify"):
            self.assertIsInstance(res[k], list)
        # 2. tier_a và notify không được rỗng
        self.assertTrue(len(res["tier_a"]) > 0)
        self.assertTrue(len(res["notify"]) > 0)
        # 3. Tất cả ảnh thuộc tập ảnh trong lô
        all_imgs = {"img_01", "img_02", "img_03", "img_04", "img_05", "img_06"}
        self.assertTrue(set(res["tier_a"] + res["tier_b"]).issubset(all_imgs))
        # 4. Tất cả mã người thuộc jobs.csv
        all_people = {"userA", "userR1", "userB", "userR2", "userC", "userR3"}
        self.assertTrue(set(res["notify"]).issubset(all_people))


if __name__ == "__main__":
    unittest.main()
