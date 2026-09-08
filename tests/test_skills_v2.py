"""skills 注册表 v2 单元测试：front matter / 两类技能 / 工具执行 / 去重 / QA-Fix 闭环。"""

import unittest

from classmind.quality.fixer import FIXABLE_CODES, NoteFixer
from classmind.skills import (
    SkillError,
    load_skill_text,
    load_skills,
    load_tool_skills,
    run_tool_skill,
)

from tests._util import workspace_tempdir

PROMPT_SKILL_MD = """---
name: teacher-style
kind: prompt
description: 该课程的笔记风格要求
stages: draft, polish
---
术语一律先给中文再括英文；每节至少一组 Q&A；禁止照抄讲义原文。
"""

TOOL_SKILL_MD = """---
name: figures
kind: tool
description: 假图提取工具（测试用）
hook: enrich
entry: python3 extract.py
---
把 input 里的图复制到 assets。
"""


class TestSkillRegistry(unittest.TestCase):
    def test_prompt_skill_front_matter(self):
        with workspace_tempdir("classmind_sk_") as d:
            root = __import__("pathlib").Path(d)
            sk_dir = root / "skills" / "teacher-style"
            sk_dir.mkdir(parents=True)
            (sk_dir / "SKILL.md").write_text(PROMPT_SKILL_MD, encoding="utf-8")
            skills = load_skills(repo_root=root)
            self.assertEqual(len(skills), 1)
            sk = skills[0]
            self.assertEqual(sk.kind, "prompt")
            self.assertEqual(sk.stages, ["draft", "polish"])
            self.assertTrue(sk.applies_to("draft"))
            self.assertFalse(sk.applies_to("plan"))
            self.assertIn("术语一律先给中文", sk.text)

    def test_tool_skill_discovery_and_execution(self):
        with workspace_tempdir("classmind_sk_") as d:
            root = __import__("pathlib").Path(d)
            sk_dir = root / "skills" / "figures"
            sk_dir.mkdir(parents=True)
            (sk_dir / "SKILL.md").write_text(TOOL_SKILL_MD, encoding="utf-8")
            (sk_dir / "extract.py").write_text(
                "import sys, pathlib\n"
                "assets = pathlib.Path(sys.argv[2])\n"
                "assets.mkdir(parents=True, exist_ok=True)\n"
                "(assets / 'made.txt').write_text('ok')\n",
                encoding="utf-8",
            )
            tools = load_tool_skills(root)
            self.assertEqual(len(tools), 1)
            self.assertEqual(tools[0].hook, "enrich")
            assets = __import__("pathlib").Path(d) / "out_assets"
            out = run_tool_skill(tools[0], ["in", str(assets)])
            self.assertEqual(out.strip(), "")
            self.assertTrue((assets / "made.txt").exists())

    def test_tool_skill_failure_raises(self):
        with workspace_tempdir("classmind_sk_") as d:
            root = __import__("pathlib").Path(d)
            sk_dir = root / "skills" / "bad"
            sk_dir.mkdir(parents=True)
            (sk_dir / "SKILL.md").write_text(
                "---\nname: bad\nkind: tool\nentry: python3 nope.py\n---\nx\n", encoding="utf-8")
            tools = load_tool_skills(root)
            with self.assertRaises(SkillError):
                run_tool_skill(tools[0])

    def test_dedupe_and_kind_filter_and_legacy_text(self):
        with workspace_tempdir("classmind_sk_") as d:
            root = __import__("pathlib").Path(d)
            sk_dir = root / "skills" / "teacher-style"
            sk_dir.mkdir(parents=True)
            (sk_dir / "SKILL.md").write_text(PROMPT_SKILL_MD, encoding="utf-8")
            # 同名文件再次出现（低优先级来源）应被去重
            dup = root / "dup.md"
            dup.write_text(PROMPT_SKILL_MD, encoding="utf-8")
            skills = load_skills(str(dup), repo_root=root)
            self.assertEqual(len(skills), 1)
            # legacy 拼接文本保留
            text = load_skill_text(str(dup), repo_root=root, stage="draft")
            self.assertIn("### teacher-style", text)
            self.assertEqual(load_skill_text(repo_root=root, stage="plan"), "")


class TestQAFixLoop(unittest.TestCase):
    BODY = "正文段落，讲解某个知识点，教师强调：xxx。\n" * 90   # 足够长以通过修订护栏

    def _run_fixer(self, fake_returns=None):
        from classmind.models import CourseMeta, NoteProduct
        from classmind.prompts.orchestrator import PromptOrchestrator

        class FakeLLM:
            model = "fake"
            calls = 0

            def complete(self, prompt: str) -> str:
                FakeLLM.calls += 1
                return fake_returns or prompt

        product = NoteProduct(engine="llm:fake", doc_header="# T")
        md = "# T\n\n" + self.BODY + "\n\n教师讲述：xxx\n\n<!-- slide: id=1 -->\n"
        meta = CourseMeta(course_name="测试课", chapter_title="第 1 讲")
        fixer = NoteFixer(FakeLLM(), PromptOrchestrator())
        return fixer, product, meta, md

    def test_fix_loop_triggers_and_rewrites(self):
        clean = "# T\n\n## 小节\n\n" + self.BODY
        fixer, product, meta, md = self._run_fixer(fake_returns=clean)
        from classmind.models import AlignmentResult, ParsedSlides, ProcessedTranscript

        final_md, report = fixer.fix(meta, md, ParsedSlides(), ProcessedTranscript(),
                                     AlignmentResult(), product, rounds=2)
        self.assertNotIn("教师讲述：", final_md)
        self.assertNotIn("<!-- slide:", final_md)
        bad = {r["code"] for r in report if r["level"] != "OK"} & set(FIXABLE_CODES)
        self.assertFalse(bad, f"still fixable: {bad}")
        self.assertEqual(fixer.client.calls, 1)

    def test_no_fixable_issues_no_llm_call(self):
        fixer, product, meta, _md = self._run_fixer()
        from classmind.models import AlignmentResult, ParsedSlides, ProcessedTranscript

        clean_md = "# T\n\n## 小节\n\n" + self.BODY + "\n\n$$x = 1$$\n\n"
        _, report = fixer.fix(meta, clean_md, ParsedSlides(), ProcessedTranscript(),
                              AlignmentResult(), product, rounds=2)
        bad = {r["code"] for r in report if r["level"] != "OK"} & set(FIXABLE_CODES)
        self.assertFalse(bad, f"unexpected fixable: {bad}")
        self.assertEqual(fixer.client.calls, 0)

    def test_no_client_or_zero_rounds_skips(self):
        from classmind.models import AlignmentResult, ParsedSlides, ProcessedTranscript
        from classmind.quality.fixer import NoteFixer

        fixer = NoteFixer(None)
        md, report = fixer.fix(
            None, "x", ParsedSlides(), ProcessedTranscript(), AlignmentResult(),
            None, rounds=3,
        )
        self.assertEqual(md, "x")


if __name__ == "__main__":
    unittest.main()
