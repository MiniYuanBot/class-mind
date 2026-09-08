"""用户 Skills（补充写作要求）装载单元测试。"""

import os
import unittest
from pathlib import Path

from classmind.skills import load_skill_text

from tests._util import workspace_tempdir


class TestSkillLoader(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("CLASSMIND_SKILLS", None)

    def test_auto_input_skills_dir(self):
        with workspace_tempdir("classmind_sk_") as tmp:
            inp = Path(tmp) / "input"
            (inp / "skills").mkdir(parents=True)
            (inp / "skills" / "zh.md").write_text("术语一律先中后英", encoding="utf-8")
            (inp / "skills" / "style.md").write_text("少用列表，多用小标题", encoding="utf-8")
            text = load_skill_text(input_dir=inp)
            self.assertIn("zh.md", text)
            self.assertIn("术语一律先中后英", text)
            self.assertIn("style.md", text)

    def test_explicit_file_and_dir(self):
        with workspace_tempdir("classmind_sk_") as tmp:
            base = Path(tmp)
            (base / "custom").mkdir()
            (base / "custom" / "a.md").write_text("要求A", encoding="utf-8")
            (base / "b.md").write_text("要求B", encoding="utf-8")
            text = load_skill_text(skills_path=base / "b.md")
            self.assertIn("要求B", text)
            self.assertNotIn("要求A", text)
            text2 = load_skill_text(skills_path=base / "custom")
            self.assertIn("要求A", text2)

    def test_empty(self):
        self.assertEqual(load_skill_text(), "")

    def test_pipeline_injects_skill_into_prompt(self):
        """端到端：LLM 流水线会把 input/skills 内容并入每个提示词（Fake LLM 记录 prompt）。"""
        from pathlib import Path

        from classmind.pipeline import Pipeline

        from tests._util import TempInput, workspace_tempdir

        prompts: list = []

        class RecordingLLM:
            model = "fake-llm"

            def complete(self, prompt: str) -> str:
                prompts.append(prompt)
                if "L1 课程规划" in prompt:
                    return ('{"doc_title": "T", "sections": [{"heading": "知识点一", "pages": []}]}')
                if "L2 分节精写" in prompt:
                    return "## 知识点一\n\n**定义**：示例内容。"
                return ""

        with TempInput() as inp, workspace_tempdir("classmind_sk_") as out:
            skills_dir = Path(inp) / "skills"
            skills_dir.mkdir()
            (skills_dir / "teacher.md").write_text("教师要求：结尾必须附知识图谱", encoding="utf-8")
            result = Pipeline(input_dir=Path(inp), output_dir=Path(out), engine="llm",
                              llm_client=RecordingLLM(), work_dir=Path(out) / "work").run()
            self.assertTrue(result.product.layers, "应生成分层产物")
            self.assertTrue(prompts, "应产生至少一次 LLM 调用")
            self.assertTrue(any("教师要求：结尾必须附知识图谱" in p for p in prompts),
                            "skill 内容应出现在提示词中")


if __name__ == "__main__":
    unittest.main()
