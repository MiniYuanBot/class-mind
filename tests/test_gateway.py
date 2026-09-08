"""P1 输入网关单元测试。"""

import json
import unittest
from pathlib import Path

from classmind.gateway.input_gateway import InputGateway, _detect_type_from_text
from classmind.models import CourseType

from tests._util import SAMPLE_TRANSCRIPT_TXT, workspace_tempdir


class TestInputGateway(unittest.TestCase):
    def setUp(self):
        self._tmp = workspace_tempdir("classmind_gw_")
        self.dir = Path(self._tmp.name)
        (self.dir / "讲述_哈希表.txt").write_text(SAMPLE_TRANSCRIPT_TXT, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_detect_type_from_hint(self):
        self.assertEqual(_detect_type_from_text("实验课-神经网络"), CourseType.LAB)
        self.assertEqual(_detect_type_from_text("习题课-线性代数"), CourseType.TUTORIAL)
        self.assertIsNone(_detect_type_from_text("随便一份材料"))

    def test_scan_txt_only(self):
        gw = InputGateway(self.dir)
        m = gw.scan()
        self.assertTrue(m.has_material)
        self.assertEqual(len(m.transcripts), 1)
        self.assertEqual(len(m.slides), 0)
        self.assertTrue(any("WARN" in q for q in m.quality_issues))  # 缺课件提示

    def test_meta_json_overrides_heuristics(self):
        (self.dir / "meta.json").write_text(
            json.dumps({"course": "数据结构", "course_type": "theory", "subject": "计算机"}, ensure_ascii=False),
            encoding="utf-8",
        )
        m = InputGateway(self.dir).scan()
        self.assertEqual(m.course_meta.course_name, "数据结构")
        self.assertEqual(m.course_meta.course_type, CourseType.THEORY)
        self.assertEqual(m.course_meta.subject, "计算机")

    def test_cli_overrides_win(self):
        (self.dir / "meta.json").write_text(
            json.dumps({"course": "数据结构", "course_type": "theory"}, ensure_ascii=False), encoding="utf-8"
        )
        m = InputGateway(self.dir, overrides={"course_name": "编译原理", "course_type": "theory"}).scan()
        self.assertEqual(m.course_meta.course_name, "编译原理")

    def test_empty_input_flags_issue(self):
        empty = self.dir / "empty"
        empty.mkdir()
        m = InputGateway(empty).scan()
        self.assertFalse(m.has_material)
        self.assertTrue(any("FAIL" in q for q in m.quality_issues))

    def test_missing_dir_raises(self):
        from classmind.errors import InputError

        with self.assertRaises(InputError):
            InputGateway(self.dir / "nope").scan()


if __name__ == "__main__":
    unittest.main()
