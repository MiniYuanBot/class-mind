"""LLM v2 计划/分批单元测试（plan JSON 解析、规整、批次划分）。"""

import unittest

from classmind.core.llm_builder import (
    PageUnit,
    PlanSection,
    _batch_sections,
    _extract_plan_json,
    _normalize_plan,
)


class TestPlanJsonExtract(unittest.TestCase):
    def test_fenced_json(self):
        text = "结构计划如下：\n```json\n{\"doc_title\": \"T\", \"sections\": [{\"heading\": \"A\"}]}\n```"
        plan = _extract_plan_json(text)
        self.assertEqual(plan["doc_title"], "T")
        self.assertEqual(plan["sections"][0]["heading"], "A")

    def test_bare_json_after_prose(self):
        text = '介绍文字。{"doc_title": "X", "sections": [{"heading": "一", "pages": [1]}]} 结尾文字'
        plan = _extract_plan_json(text)
        self.assertEqual(plan["doc_title"], "X")

    def test_garbage_returns_none(self):
        self.assertIsNone(_extract_plan_json("没有 json"))
        self.assertIsNone(_extract_plan_json(""))


class TestNormalizePlan(unittest.TestCase):
    def test_partition_and_missing_page_assignment(self):
        plan = {
            "doc_title": "第 2 讲",
            "sections": [
                {"heading": "## 概念甲", "pages": [1, 2]},
                {"heading": "概念乙", "pages": "4-5"},
                {"heading": "常见疑问", "pages": []},
            ],
        }
        norm = _normalize_plan(plan, max_page=6)
        self.assertEqual(norm["doc_title"], "第 2 讲")
        secs = norm["sections"]
        self.assertEqual(secs[0].heading, "概念甲")          # '## ' 前缀被剥掉
        # "4-5" 区间解析；缺失页 6 被就近吸收进本节 -> [4, 5, 6]
        self.assertEqual(secs[0].pages, [1, 2, 3])
        self.assertEqual(secs[1].pages, [4, 5, 6])
        # 每页 1..6 至少被某节覆盖
        covered = {p for s in secs for p in s.pages}
        self.assertEqual(covered, {1, 2, 3, 4, 5, 6})

    def test_duplicate_heading_deduped(self):
        plan = {"doc_title": "T", "sections": [{"heading": "A", "pages": [1]}, {"heading": "A", "pages": [2]}]}
        secs = _normalize_plan(plan, max_page=2)["sections"]
        self.assertEqual(len(secs), 2)
        self.assertNotEqual(secs[0].heading, secs[1].heading)


class TestBatchSections(unittest.TestCase):
    @staticmethod
    def _pages(seed: int) -> list:
        # 每页约 20000 字符口述 -> 单节估算超过批次上限 1/3
        big = "word " * 4000
        return [PageUnit(index=i, title=f"P{i}", body_md="", narration=big) for i in range(seed, seed + 5)]

    def test_batch_by_material_estimate(self):
        pages = self._pages(1)
        sections = [PlanSection(heading=f"S{p.index}", pages=[p.index]) for p in pages]
        batches = _batch_sections(sections, pages)
        # 单节估算 = 600 + min(正文,1800) + min(口述,3200)≈7000；批次上限 30000
        # -> 每批最多 4 节：批次划分为 4 + 1
        self.assertEqual(len(batches), 2)
        self.assertEqual([len(b) for b in batches], [4, 1])
        # 顺序保持
        all_heads = [s.heading for b in batches for s in b]
        self.assertEqual(all_heads, [f"S{p.index}" for p in pages])

    def test_empty_review_section_gets_own_batch(self):
        pages = self._pages(1)
        sections = [
            PlanSection(heading="正课", pages=[1]),
            PlanSection(heading="常见疑问（FAQ）", pages=[]),
        ]
        batches = _batch_sections(sections, pages)
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[1][0].pages, [])


if __name__ == "__main__":
    unittest.main()
