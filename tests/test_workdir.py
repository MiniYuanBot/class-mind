"""work/ 中间文件约定（与 paper-mind 镜像）单元测试。"""

import json
import unittest

from classmind.models import CourseMeta
from classmind.workdir import (
    alignment_payload,
    cleanup,
    default_work_dir,
    dirs_for,
    reset_run,
    stem_for,
    write_curated_snapshot,
    write_text_or_json,
)

from tests._util import workspace_tempdir


class _FakeAlignment:
    coverage = 0.95
    records = [{"slide_id": 1, "confidence": "HIGH"}]
    unaligned_segments = [{"i": 3}]


class TestWorkDir(unittest.TestCase):
    def test_default_work_dir_is_output_parent_work(self):
        self.assertEqual(default_work_dir(__import__("pathlib").Path("a/b/out")),
                         __import__("pathlib").Path("a/b/work"))

    def test_stem_matches_note_stem(self):
        m = CourseMeta(course_code="cs162", chapter_no="2")
        self.assertEqual(stem_for(m), "cs162-lecture2-notes")

    def test_dirs_for_and_reset(self):
        with workspace_tempdir("cm_work_") as d:
            import pathlib
            base = pathlib.Path(d)
            curated, run = dirs_for(base, "cs162-lecture2-notes")
            self.assertEqual(curated.name, "cs162-lecture2-notes")
            self.assertEqual(run.parent.name, "run")
            run.mkdir(parents=True)
            (run / "old.txt").write_text("x", encoding="utf-8")
            reset_run(run)
            self.assertTrue(run.is_dir())
            self.assertFalse((run / "old.txt").exists())

    def test_alignment_payload(self):
        payload = alignment_payload(_FakeAlignment())
        self.assertEqual(payload["coverage"], 0.95)
        self.assertEqual(len(payload["records"]), 1)

    def test_write_text_or_json(self):
        with workspace_tempdir("cm_work_") as d:
            import pathlib
            base = pathlib.Path(d)
            p = base / "plan.json"
            write_text_or_json('{"doc_title": "T", "sections": []}', p)
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["doc_title"], "T")
            p2 = base / "raw.txt"
            write_text_or_json("不是 json 的内容", p2)
            self.assertEqual(p2.read_text(encoding="utf-8"), "不是 json 的内容")

    def test_cleanup_keeps_curated(self):
        with workspace_tempdir("cm_work_") as d:
            import pathlib
            base = pathlib.Path(d)
            curated, run = dirs_for(base, "s")
            curated.mkdir(parents=True)
            run.mkdir(parents=True)
            (curated / "keep.md").write_text("k", encoding="utf-8")
            removed = cleanup(base)
            self.assertEqual(removed, 1)
            self.assertTrue(curated.exists())
            self.assertFalse(run.exists())

    def test_write_curated_snapshot(self):
        with workspace_tempdir("cm_work_") as d:
            import pathlib
            base = pathlib.Path(d)
            curated, _ = dirs_for(base, "cs162-lecture2-notes")
            write_curated_snapshot(
                curated, "cs162-lecture2-notes",
                slides_md="# 页1", transcript_text="口述", highlights=[{"text": "重点"}],
                alignment=_FakeAlignment(), plan='{"doc_title": "T"}',
                meta=CourseMeta(course_code="cs162", chapter_no="2"),
            )
            self.assertTrue((curated / "slides.md").exists())
            self.assertTrue((curated / "transcript.txt").exists())
            self.assertTrue((curated / "alignment.json").exists())
            self.assertTrue((curated / "course_meta.json").exists())
            self.assertEqual((curated / ".stem").read_text(encoding="utf-8"), "cs162-lecture2-notes")


if __name__ == "__main__":
    unittest.main()
