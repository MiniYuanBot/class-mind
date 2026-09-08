"""端到端集成测试：demo 素材 -> Pipeline P1-P7（LLM v2，进程内 Fake LLM，无网络）。"""

import json
import unittest
from pathlib import Path

from classmind.generator.note_generator import NoteGenerator
from classmind.models import NoteProduct
from classmind.pipeline import Pipeline

from tests._util import TempInput, workspace_tempdir


class TestPipelineEndToEnd(unittest.TestCase):
    def test_layered_v2_render_order(self):
        """LLM v2 组装：头部块之后按 section_XX 顺序拼接各节正文。"""
        product = NoteProduct(
            course_title="测试课程",
            engine="llm:mock",
            mode="layered_md",
            doc_header="# 测试课程\n\n> **课程**：测试",
            layers={
                "plan": '{"doc_title": "测试课程", "sections": []}',
                "section_00": "## 概念甲\n\n**定义**：...\n\n**核心思想**：...",
                "section_01": "## 概念乙\n\n**要点**：...",
            },
        )
        with workspace_tempdir("classmind_gen_") as out:
            gen = NoteGenerator(Path(out))
            md = gen._render_layered(None, product)
            self.assertLess(md.find("# 测试课程"), md.find("## 概念甲"))
            self.assertLess(md.find("## 概念甲"), md.find("## 概念乙"))
            self.assertNotIn("本讲框架", md)
            self.assertNotIn("知识点精读", md)

    def test_layered_strip_repeated_title(self):
        """组装后应删除头部后“孤立重复”的 ## 文档标题 空块；有正文的同名节应保留。"""
        with workspace_tempdir("classmind_gen_") as out:
            gen = NoteGenerator(Path(out))
            # 重复标题孤立块 + --- 分隔 -> 删除
            md = gen._render_layered(None, NoteProduct(
                mode="layered_md",
                doc_header="# 测试课程",
                layers={"plan": "{}", "section_00": "## 测试课程\n\n---\n\n## 概念甲\n\n**定义**：正文内容。"},
            ))
            self.assertNotIn("\n## 测试课程\n", md)
            self.assertIn("## 概念甲", md)
            # 同名节但有正文 -> 保留
            md2 = gen._render_layered(None, NoteProduct(
                mode="layered_md",
                doc_header="# 测试课程",
                layers={"plan": "{}", "section_00": "## 测试课程\n\n**定义**：该节正文。\n\n内容。"},
            ))
            self.assertIn("## 测试课程", md2)

    def test_llm_layered_end_to_end(self):
        """LLM v2 链路端到端（进程内 Fake LLM，无网络）：Plan -> Draft -> 中文成稿 + 英文文件名。"""

        class FakeLLM:
            model = "fake-llm"

            def complete(self, prompt: str) -> str:
                if "L1 课程规划" in prompt:
                    return (
                        "```json\n"
                        "{\n"
                        '  "doc_title": "第2讲：反向传播（Backpropagation）",\n'
                        '  "sections": [\n'
                        '    {"heading": "梯度下降（Gradient Descent）", "pages": [1, 2]},\n'
                        '    {"heading": "反向传播的核心思想", "pages": [3, 4]}\n'
                        "  ]\n"
                        "}\n"
                        "```"
                    )
                if "L2 分节精写" in prompt:
                    both = "梯度下降（Gradient Descent）" in prompt and "反向传播的核心思想" in prompt
                    if both or "反向传播的核心思想" not in prompt:
                        return ("## 梯度下降（Gradient Descent）\n\n"
                                "**定义**：沿损失函数下降最快的方向迭代更新参数。\n\n"
                                "**核心思想**：w 沿负梯度方向更新。\n\n"
                                + ("## 反向传播的核心思想\n\n**定义**：高效传播误差的算法。" if both else ""))
                    return ("## 反向传播的核心思想\n\n"
                            "**定义**：从输出层向输入层传播误差的高效梯度算法。\n\n"
                            "**教师强调**：反向传播不是新优化算法，只是高效求梯度。")
                return ""

        with TempInput() as inp, workspace_tempdir("classmind_out_") as out_tmp:
            result = Pipeline(input_dir=Path(inp), output_dir=Path(out_tmp), engine="llm",
                              llm_client=FakeLLM()).run()
            self.assertEqual(result.product.mode, "layered_md")
            self.assertIn("plan", result.product.layers)
            note = Path(result.outputs["note_path"])
            self.assertTrue(note.exists())
            self.assertRegex(note.name, r"^[a-z0-9\-]+\.md$")
            md = note.read_text(encoding="utf-8")
            self.assertLess(md.find("## 梯度下降（Gradient Descent）"), md.find("## 反向传播的核心思想"))
            self.assertIn("反向传播", md)
            # 中文正文 + 无逐页/溯源痕迹
            for forbidden in ("**溯源**", "[Slide", "课件原文", "```json"):
                self.assertNotIn(forbidden, md)
            # plan 落进 meta/course_outline.json
            outline = json.loads((Path(out_tmp) / "meta" / "course_outline.json").read_text(encoding="utf-8"))
            self.assertEqual(len(outline["sections"]), 2)
            self.assertEqual(outline["sections"][0]["heading"], "梯度下降（Gradient Descent）")

    def test_english_note_stem_rules(self):
        from classmind.generator.note_generator import _english_note_stem
        from classmind.models import CourseMeta

        # 1) 显式 file_stem 优先
        m = CourseMeta(course_name="X", chapter_no="3", course_code="cs162", file_stem="cs162-lecture2-notes")
        self.assertEqual(_english_note_stem(m), "cs162-lecture2-notes")
        # 2) course_code + 数字章节 -> <code>-lecture<no>-notes
        m2 = CourseMeta(course_name="操作系统（Operating Systems）", chapter_no="2", course_code="CS162")
        self.assertEqual(_english_note_stem(m2), "cs162-lecture2-notes")
        # 3) ASCII 词拼接回退
        m3 = CourseMeta(course_name="Machine Learning Intro", chapter_title="Backprop")
        self.assertEqual(_english_note_stem(m3), "machine-learning-intro-backprop")

    def test_missing_key_raises_helpful_error(self):
        """纯 LLM 模式：未配置 client/Key 时应给出清晰提示（不再走确定性引擎）。"""
        from classmind.core.llm import LLMError

        with TempInput() as inp, workspace_tempdir("classmind_out_") as out_tmp:
            with self.assertRaisesRegex(LLMError, "API Key"):
                Pipeline(input_dir=Path(inp), output_dir=Path(out_tmp)).run()


if __name__ == "__main__":
    unittest.main()
