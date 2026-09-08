"""work/ 目录约定（与 paper-mind 镜像的中间文件组织）。

布局（在生成时自动落盘，均为可再生产物，不入 git）：
  <work_dir>/run/<stem>/     本次运行临时：run_state/manifest、slides.md、transcript.txt、
                             highlights.json、alignment.json、plan.json、draft/（分节草稿）、note_draft.md
  <work_dir>/curated/<stem>/ 可复用快照：解析 slides.md、transcript、alignment/highlights、plan、course_meta

默认 <work_dir> = 环境变量 CLASSMIND_WORK_DIR，否则 <output_dir 的父目录>/work
（class-mind 仓库内运行 input→output 时即仓库根 work/，与 paper-mind 相同）。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from classmind.generator.note_generator import english_note_stem
from classmind.models import CourseMeta, dump_json, to_jsonable


def default_work_dir(output_dir: Path) -> Path:
    env = os.environ.get("CLASSMIND_WORK_DIR")
    if env:
        return Path(env)
    out = Path(output_dir)
    return out.parent / "work"


def stem_for(meta: CourseMeta) -> str:
    """本次运行的 stem（与最终笔记文件名一致），用作 run/curated 子目录名。"""
    return english_note_stem(meta)


def dirs_for(work_dir: Path, stem: str) -> tuple:
    """返回 (curated_dir, run_dir)；只计算路径，不创建。"""
    work = Path(work_dir)
    return work / "curated" / stem, work / "run" / stem


def reset_run(run_dir: Path) -> None:
    """清理旧的本次运行目录并重建（每次 run 从干净状态开始）。"""
    run_dir = Path(run_dir)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)


def alignment_payload(alignment) -> dict:
    """AlignmentResult → 可 JSON 落盘的摘要（与 paper-mind alignment 类产物对齐）。"""
    return {
        "coverage": round(float(getattr(alignment, "coverage", 0.0) or 0.0), 4),
        "records": to_jsonable(getattr(alignment, "records", [])),
        "unaligned": to_jsonable(getattr(alignment, "unaligned_segments", [])),
    }


def write_text_or_json(text: str, path: Path) -> None:
    """优先把内容按 JSON 落盘；解析失败则原文落盘。"""
    import json as _json

    p = Path(path)
    if text.strip():
        try:
            _json.loads(text)
            p.write_text(text, encoding="utf-8")
            return
        except _json.JSONDecodeError:
            pass
    p.write_text(text, encoding="utf-8")


def write_curated_snapshot(curated_dir: Path, stem: str, *, slides_md: str = "",
                           transcript_text: str = "", transcript_md: str = "",
                           highlights: Optional[list] = None, alignment=None,
                           plan: Optional[str] = None, meta: Optional[CourseMeta] = None) -> None:
    """成功后把可复用的加工产物写入 curated/<stem>/（等价 paper-mind curated 缓存）。"""
    curated = Path(curated_dir)
    try:
        curated.mkdir(parents=True, exist_ok=True)
        if slides_md:
            (curated / "slides.md").write_text(slides_md, encoding="utf-8")
        if transcript_text:
            (curated / "transcript.txt").write_text(transcript_text, encoding="utf-8")
        if transcript_md:
            (curated / "transcript.md").write_text(transcript_md, encoding="utf-8")
        if highlights:
            dump_json(to_jsonable(highlights), curated / "highlights.json")
        if alignment is not None:
            dump_json(alignment_payload(alignment), curated / "alignment.json")
        if plan:
            write_text_or_json(plan, curated / "plan.json")
        if meta is not None:
            dump_json(to_jsonable(meta), curated / "course_meta.json")
        (curated / ".stem").write_text(stem, encoding="utf-8")
    except OSError:
        pass  # 快照失败不阻断生成


def cleanup(work_dir: Path, keep_curated: bool = True) -> int:
    """清理 work/run（保留 curated）；返回删除的运行数。与 paper-mind cleanup 语义一致。"""
    work = Path(work_dir)
    run_root = work / "run"
    removed = 0
    if run_root.exists():
        for d in sorted(run_root.iterdir()):
            if d.is_dir():
                shutil.rmtree(d)
                removed += 1
    return removed


def describe(work_dir: Path) -> str:
    """work/ 状态文本（report 用）。"""
    work = Path(work_dir)
    lines = [f"work_dir: {work}"]
    curated = work / "curated"
    run_root = work / "run"
    if curated.exists():
        for d in sorted(curated.iterdir()):
            if d.is_dir():
                lines.append(f"  curated/{d.name}/")
    if run_root.exists():
        for d in sorted(run_root.iterdir()):
            if d.is_dir():
                lines.append(f"  run/{d.name}/")
    return "\n".join(lines)
