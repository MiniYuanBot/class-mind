"""P7 笔记生成器（Note Generator）。

LLM 模式（v2）：组装最终单文件 Markdown 课程笔记（头部块 + 按 plan 顺序拼接的各节精写正文），
并落盘 meta/ 产物：course_outline.json、alignment_map.json、highlights.json、qa_report.json。
（legacy 确定性引擎已移除，生成器只保留成稿式组装路径。）
"""

from __future__ import annotations

import re
from pathlib import Path

from classmind.models import (
    AlignmentResult,
    CourseMeta,
    NoteProduct,
    ParsedSlides,
    ProcessedTranscript,
    dump_json,
)
from classmind.quality.checks import run_qa


class NoteGenerator:
    def __init__(self, output_dir: Path, coverage_threshold: float = 0.7) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir = self.output_dir / "assets"
        self.meta_dir = self.output_dir / "meta"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.coverage_threshold = coverage_threshold

    # ------------------------------------------------------------------
    def generate(
        self,
        meta: CourseMeta,
        product: NoteProduct,
        slides: ParsedSlides,
        transcript: ProcessedTranscript,
        alignment: AlignmentResult,
    ) -> dict:
        md = self._render_layered(meta, product)

        # 质量检查（QA 只落在 meta/，笔记正文保持“成品”形态）
        qa_report = run_qa(slides, transcript, alignment, product, md, self.coverage_threshold)
        product.qa_warnings = [r["message"] for r in qa_report if r["level"] == "WARN"]

        note_path = self._write_note(md, meta)
        self._write_meta(meta, product, alignment, transcript, qa_report, slides)

        return {
            "note_path": note_path,
            "qa_report": qa_report,
            "note_md": md,
        }

    # ------------------------------------------------------------------
    # 组装
    # ------------------------------------------------------------------
    def _render_layered(self, meta: CourseMeta, product: NoteProduct) -> str:
        """头部块 + 按 plan 顺序拼接的各节精写正文（或整篇 polish 结果）。"""
        if product.layers.get("polish"):
            return _strip_repeated_title(product.layers["polish"].strip())
        parts: list = []
        if product.doc_header:
            parts.append(product.doc_header.strip())
        else:
            parts.append(f"# {product.course_title}")
        keys = sorted(k for k in product.layers if k.startswith("section_"))
        for key in keys:
            md = (product.layers[key] or "").strip()
            if md:
                parts.append(md)
        md = "\n\n---\n\n".join(p for p in parts if p)
        return _strip_repeated_title(md)

    # ------------------------------------------------------------------
    # 落盘
    # ------------------------------------------------------------------
    def _write_note(self, md: str, meta: CourseMeta) -> Path:
        name = f"{_english_note_stem(meta)}.md"
        path = self.output_dir / name
        path.write_text(md + "\n", encoding="utf-8")
        return path

    def _write_meta(self, meta: CourseMeta, product: NoteProduct, alignment: AlignmentResult,
                    transcript: ProcessedTranscript, qa_report: list, slides: ParsedSlides) -> None:
        dump_json(_layered_outline(meta, product), self.meta_dir / "course_outline.json")

        dump_json(
            {
                "coverage": round(alignment.coverage, 4),
                "records": alignment.records,
                "unaligned": alignment.unaligned_segments,
            },
            self.meta_dir / "alignment_map.json",
        )
        dump_json(
            [
                {
                    "text": h.text,
                    "label": h.label,
                    "timestamp": h.timestamp,
                    "triggers": h.triggers,
                }
                for h in transcript.highlights
            ],
            self.meta_dir / "highlights.json",
        )
        dump_json(qa_report, self.meta_dir / "qa_report.json")


# ---------------------------------------------------------------------------
def _layered_outline(meta: CourseMeta, product: NoteProduct) -> dict:
    """course_outline.json：结构计划 + 写作引擎信息。"""
    base = {
        "course": meta.course_name,
        "chapter": meta.chapter_title or meta.chapter_no,
        "engine": product.engine,
        "doc_title": product.course_title,
    }
    raw = product.layers.get("plan", "")
    try:
        import json as _json

        plan = _json.loads(raw)
        base["doc_title"] = plan.get("doc_title") or product.course_title
        base["sections"] = [
            {
                "heading": str(s.get("heading", "")),
                "pages": list(s.get("pages", []) or []),
                "instructor_note": str(s.get("instructor_note") or ""),
            }
            for s in plan.get("sections", [])
        ]
        base["n_sections"] = len(base["sections"])
    except Exception:  # noqa: BLE001
        base["sections_raw"] = raw
    return base


def _strip_repeated_title(md: str) -> str:
    """删除头部之后“孤立重复”的 `## <文档标题>` 空块（Draft 偶发产物）。"""
    lines = (md or "").splitlines()
    title = next((ln[2:].strip() for ln in lines if ln.startswith("# ") and ln[2:].strip()), None)
    if not title:
        return md
    marker = f"## {title}"
    out: list = []
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if ln.strip() == marker:
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            following = lines[j].strip() if j < n else ""
            prev = next((lines[k].strip() for k in range(i - 1, -1, -1) if lines[k].strip()), "")
            standalone = (not following or following == "---" or following.startswith("## "))
            if standalone and (prev in ("", "---")):
                if following == "---":       # 连同其后分隔符一起吞掉
                    i = j + 1
                else:
                    i = j
                continue
        out.append(ln)
        i += 1
    return "\n".join(out)


def _english_note_stem(meta: CourseMeta) -> str:
    """最终笔记文件名主干：纯英文（仅 [a-z0-9-]），优先级见下方注释。"""
    # 1) meta.file_stem 显式指定；2) course_code + 数字章节号 -> <code>-lecture<no>-notes；
    # 3) 抽课程名/章节名 ASCII 词；4) 回退 course[-<章节号>]
    if meta.file_stem:
        stem = _sanitize_stem(meta.file_stem)
        if stem:
            return stem
    code = re.sub(r"[^A-Za-z0-9]", "", meta.course_code or "").lower()
    no = (meta.chapter_no or "").strip()
    if code and no.isdigit():
        return f"{code}-lecture{int(no)}-notes"
    parts: list = []
    for chunk in (meta.course_name or "", meta.chapter_title or ""):
        for w in re.findall(r"[A-Za-z][A-Za-z0-9]*", chunk):
            low = w.lower()
            if low not in parts:
                parts.append(low)
    if not parts:
        parts = ["course"]
        if no.isdigit():
            parts.append(no)
    stem = "-".join(parts)[:120].strip("-")
    return stem or "course-notes"


def _sanitize_stem(stem: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(stem)).strip("-").lower()
    return re.sub(r"-{2,}", "-", s)[:120].strip("-")
