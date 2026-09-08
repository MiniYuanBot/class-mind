"""P5 提示词编排引擎单元测试（catalog v2：plan / draft / polish）。"""

import unittest
from pathlib import Path

from classmind.models import CourseMeta, CourseType
from classmind.prompts.orchestrator import PromptOrchestrator

from tests._util import workspace_tempdir


class TestPromptOrchestrator(unittest.TestCase):
    def setUp(self):
        self.orch = PromptOrchestrator()
        self.meta = CourseMeta(
            course_name="机器学习导论",
            chapter_title="反向传播与梯度下降",
            subject="机器学习",
            course_type=CourseType.THEORY,
        )

    def test_catalog_loaded(self):
        self.assertEqual(self.orch.catalog["version"], "v2.0")
        stages = self.orch.catalog["stages"]
        for s in ("plan", "draft", "polish"):
            self.assertIn(s, stages)
        self.assertIn("markdown.md", self.orch.catalog.get("references", []))

    def test_render_contains_universal_four(self):
        prompt = self.orch.render("plan", self.meta, {"slides_digest": "幻灯片", "transcript_digest": "讲述"})
        # 四要素
        self.assertIn("20 年教学经验", prompt)
        self.assertIn("讲义的按页 Markdown 转写", prompt)
        self.assertIn("公式用 LaTeX", prompt)
        self.assertIn("材料未明确", prompt)
        # 课程类型路由 + 输入替换
        self.assertIn("理论课", prompt)
        self.assertIn("幻灯片", prompt)
        self.assertIn("讲述", prompt)

    def test_missing_variable_keeps_placeholder(self):
        prompt = self.orch.render("draft", self.meta, {"sections_to_write": "内容"})
        self.assertIn("{{ plan_md }}", prompt)     # 未提供的变量保留占位
        self.assertIn("{{ material_md }}", prompt)
        self.assertIn("内容", prompt)

    def test_plan_stage_skips_reference_appendix(self):
        p_plan = self.orch.render("plan", self.meta, {"slides_digest": "x", "transcript_digest": "y"})
        p_draft = self.orch.render("draft", self.meta,
                                   {"plan_md": "a", "sections_to_write": "b", "material_md": "c"})
        # plan 阶段不需要整份格式附录；draft 阶段必须携带（规范约束）
        self.assertNotIn("附录 A", p_plan)
        self.assertIn("附录 A", p_draft)

    def test_override_template_dir(self):
        with workspace_tempdir("classmind_pr_") as tmp:
            Path(tmp, "universal_role.md").write_text("自定义角色 {{subject}}", encoding="utf-8")
            orch = PromptOrchestrator(Path(tmp))
            prompt = orch.render("plan", self.meta, {})
            self.assertIn("自定义角色 机器学习", prompt)

    def test_all_stages_render_without_error(self):
        vars_map = {
            "plan": {"slides_digest": "x", "transcript_digest": "y", "strict_json": ""},
            "draft": {"plan_md": "x", "sections_to_write": "x", "material_md": "x", "output_budget": "5000"},
            "polish": {"plan_md": "x", "draft_md": "x"},
        }
        for stage in ("plan", "draft", "polish"):
            p = self.orch.render(stage, self.meta, vars_map[stage])
            self.assertTrue(p.startswith("# ClassMind"), stage)
            self.assertIn(stage, p.lower())


if __name__ == "__main__":
    unittest.main()
