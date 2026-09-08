"""用户自定义 Skills（补充写作要求）装载。

用户可随课堂材料提供额外的“技能/要求”说明（例如某课程的特定笔记规范、术语表、
老师偏好等）。来源（可叠加，去重）：
  1. CLI `--skills <file-or-dir>` 或环境变量 CLASSMIND_SKILLS（路径分隔用 os.pathsep）
  2. 输入目录下 input/skills/*.md（约定位置，随材料打包最方便）

这些文件的内容会被并入每个 LLM 提示词的“用户补充要求”一节，优先级最高。
"""

from __future__ import annotations

import os
from pathlib import Path

SKILLS_DIR_NAME = "skills"


def _read_md_files(sources: list) -> list:
    files: list = []
    seen: set = set()
    for src in sources:
        p = Path(src)
        if p.is_file() and p.suffix.lower() in (".md", ".txt"):
            cand = [p]
        elif p.is_dir():
            cand = sorted(p.rglob("*"))
        else:
            continue
        for f in cand:
            if f.is_file() and f.suffix.lower() in (".md", ".txt"):
                key = str(f.resolve())
                if key not in seen:
                    seen.add(key)
                    files.append(f)
    return files


def load_skill_text(skills_path=None, input_dir=None) -> str:
    """装载全部技能文本并拼接为 Markdown；无技能时返回空字符串。"""
    sources: list = []
    env = os.environ.get("CLASSMIND_SKILLS")
    if env:
        sources.extend(p for p in env.split(os.pathsep) if p)
    if skills_path:
        sources.extend(str(skills_path).split(os.pathsep) if os.pathsep in str(skills_path) else [str(skills_path)])
    files: list = _read_md_files(sources)
    if input_dir is not None:
        auto = Path(input_dir) / SKILLS_DIR_NAME
        if auto.is_dir():
            for f in sorted(auto.rglob("*")):
                if f.is_file() and f.suffix.lower() in (".md", ".txt") and f.resolve() not in {x.resolve() for x in files}:
                    files.append(f)
    if not files:
        return ""
    parts: list = []
    for f in files:
        try:
            body = f.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if body:
            parts.append(f"### {f.name}\n\n{body}")
    return "\n\n".join(parts)
