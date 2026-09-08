"""work/ 落盘集成测试：纯文本讲稿（无需 pptx/pdf/fitz 等可选依赖）。

用 Fake LLM 走完整 P1..P7，验证 run/ 中间产物与 curated/ 快照真的落盘。
"""

import json
import unittest
from pathlib import Path

from classmind.pipeline import Pipeline

from tests._util import workspace_tempdir

TRANSCRIPT = """[00:00:02] 教师：好，我们开始上课，今天我们讲哈希表（Hash Table）。
[00:00:30] 教师：哈希表本质上就是一个键值对的映射结构。
[00:01:00] 教师：注意哈希冲突是重点，考试会考。
[00:02:00] 教师：冲突解决方法重点是链地址法（Separate Chaining）。
[00:03:00] 教师：易错点是混淆负载因子和装填因子，其实它们是同一个概念。
[00:04:00] 教师：总结：哈希表用空间换时间，装载因子过高时要扩容。
"""

META = {"course": "Demo Course", "chapter_no": "2", "chapter_title": "Hash Tables",
        "subject": "CS", "course_type": "theory", "course_code": "demo"}


class FakeLLM:
    model = "fake-llm"

    def complete(self, prompt: str) -> str:
        if "L1 课程规划" in prompt:
            return ('{"doc_title": "哈希表", "sections": ['
                    '{"heading": "哈希表基础", "pages": []},'
                    '{"heading": "冲突解决", "pages": []}]}')
        if "L2 分节精写" in prompt:
            return "## 哈希表基础\n\n**定义**：…\n\n## 冲突解决\n\n**定义**：…\n"
        return ""


class TestPipelineWorkDir(unittest.TestCase):
    def test_run_journals_workdir(self):
        with workspace_tempdir("cm_in_") as in_tmp, workspace_tempdir("cm_out_") as out_tmp:
            inp = Path(in_tmp)
            (inp / "transcript.txt").write_text(TRANSCRIPT, encoding="utf-8")
            (inp / "meta.json").write_text(json.dumps(META, ensure_ascii=False), encoding="utf-8")
            out = Path(out_tmp)
            result = Pipeline(input_dir=inp, output_dir=out, engine="llm",
                              llm_client=FakeLLM(), work_dir=out / "work").run()
            note = Path(result.outputs["note_path"])
            self.assertTrue(note.exists())
            stem = note.stem
            run_dir = out / "work" / "run" / stem
            curated = out / "work" / "curated" / stem
            for rel in ("run_state.json", "manifest.json", "transcript.txt",
                        "highlights.json", "alignment.json", "plan.json", "note_draft.md"):
                self.assertTrue((run_dir / rel).exists(), f"missing {run_dir / rel}")
            draft = run_dir / "draft"
            self.assertTrue(any(draft.glob("section_*.md")), "缺分节草稿")
            # 纯讲稿路径无课件 → curated 不写 slides.md
            for rel in ("transcript.txt", "alignment.json", "course_meta.json", "plan.json"):
                self.assertTrue((curated / rel).exists(), f"missing curated {rel}")
            self.assertFalse((curated / "slides.md").exists())

    def test_cleanup_removes_run_only(self):
        with workspace_tempdir("cm_in_") as in_tmp, workspace_tempdir("cm_out_") as out_tmp:
            inp = Path(in_tmp)
            (inp / "transcript.txt").write_text(TRANSCRIPT, encoding="utf-8")
            (inp / "meta.json").write_text(json.dumps(META, ensure_ascii=False), encoding="utf-8")
            out = Path(out_tmp)
            pipe = Pipeline(input_dir=inp, output_dir=out, engine="llm",
                            llm_client=FakeLLM(), work_dir=out / "work")
            pipe.run()
            note = next(out.glob("*.md"))
            stem = note.stem
            pipe.cleanup()
            self.assertFalse((out / "work" / "run" / stem).exists())
            self.assertTrue((out / "work" / "curated" / stem).exists())
            self.assertTrue(note.exists())


if __name__ == "__main__":
    unittest.main()
