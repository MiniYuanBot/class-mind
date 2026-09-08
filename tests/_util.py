"""Shared test utilities: temp input directories and sample materials.

Note: the DSH sandbox only allows writes under the workspace and rejects the
0o700 permissions that stdlib `tempfile.TemporaryDirectory` applies, so test
directories are created with plain mkdir under the current working directory.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from classmind import demo as demo_mod

DEMO_META = {
    "course": "机器学习导论",
    "instructor": "王教授",
    "chapter_no": "2",
    "chapter_title": "反向传播与梯度下降",
    "subject": "人工智能 / 机器学习",
    "course_type": "theory",
}


class WorkspaceTempDir:
    """A temporary directory under the current working directory.

    Mimics the small part of the stdlib TemporaryDirectory API used by tests
    (`.name`, `.cleanup()`) and supports `with ... as path_str`.
    """

    def __init__(self, prefix: str = "classmind_test_") -> None:
        self.name = str(Path.cwd() / f"{prefix}{uuid.uuid4().hex[:8]}")
        Path(self.name).mkdir(parents=True, exist_ok=False)

    def __enter__(self):
        return self.name

    def __exit__(self, *exc) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        shutil.rmtree(self.name, ignore_errors=True)


def workspace_tempdir(prefix: str = "classmind_test_"):
    """Return a workspace-scoped temp dir (context manager)."""
    return WorkspaceTempDir(prefix)


class TempInput:
    """A temp input dir with demo materials (pptx + docx + meta.json), inside the workspace."""

    def __enter__(self) -> Path:
        self._tmp = WorkspaceTempDir("classmind_in_")
        self.path = Path(self._tmp.name)
        demo_mod.generate_demo_input(self.path)
        return self.path

    def __exit__(self, *exc) -> None:
        self._tmp.cleanup()


SAMPLE_TRANSCRIPT_TXT = """[00:00:02] 教师：好，同学们，我们开始上课，嗯今天我们讲哈希表（Hash Table）。
[00:00:30] 教师：那个那个，哈希表本质上就是一个键值对的映射结构，对吧。
[00:01:00] 学生：老师，哈希表的查找复杂度是多少？
[00:01:20] 教师：好问题，平均是常数时间，这个后面我们仔细讲，注意哈希冲突是重点，考试会考。
[00:02:00] 教师：接下来我们看冲突解决方法，重点是链地址法（Separate Chaining）和开放定址法。
[00:03:10] 教师：易错点是很多人会混淆负载因子和装填因子，其实它们是同一个概念。
[00:04:00] 教师：最后我们总结一下：哈希表用空间换时间，注意装载因子过高时要扩容。
"""
