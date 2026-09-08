"""P6 AI 笔记核心（LLM 模式，v2：Plan → Draft 分节写作链）。

v1 的分层链（L1 骨架 -> 按对齐 chunk 批量生成知识卡片 -> L3/L4）产出的笔记碎片化、
标题与正文脱节、质量不可控，已废弃。v2 改为「先定整份结构，再逐节精写」：

  Step 0  LectureMaterial：把 讲义页 + 对齐口述 组织为按页资料单元
  Step 1  Plan（L1）：通读全课材料摘录，产出整份笔记的结构计划
           （doc_title + 有序 sections，每节 = heading + 覆盖的讲义页码列表），
           machine-readable JSON；
  Step 2  Draft（L2）：按计划把章节分批，每批一次调用，用该批 real 材料
           （讲义正文 + 教师口述）精写出可直接进最终笔记的 Markdown 小节；
  Step 3  Polish（L3，可选）：对整篇草稿做一次整篇审校修订。

产物保存在 NoteProduct.layers：{"plan": <json>, "section_00": <md>, ...}，
由 NoteGenerator 组装为最终单文件笔记。确定性（无 API）引擎不受影响。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from classmind.core.llm import LLMError
from classmind.models import (
    AlignmentResult,
    CourseMeta,
    NoteProduct,
    ParsedSlides,
    ProcessedTranscript,
)
from classmind.prompts.orchestrator import PromptOrchestrator

# ---------------------------------------------------------------------------
# 常量：预算 / 截断 / 批次
# ---------------------------------------------------------------------------
_PAGE_BODY_MAX = 1800            # 每页讲义正文喂给 Draft 的最大字符数
_PAGE_NARR_MAX = 3200            # 每页口述喂给 Draft 的最大字符数
_DIGEST_PAGE_BODY = 320          # Plan 摘录：每页讲义正文字符数
_DIGEST_PAGE_NARR = 520          # Plan 摘录：每页口述字符数
_DIGEST_TIMELINE_MAX = 24000     # Plan 摘录：讲述时间线总字符数
_DIGEST_REVIEW_PAGE = 120        # 收尾类节（无页码）的全课速览每页字符数
_BATCH_EST_CHARS = 30000         # Draft 每批材料（字符）估算上限
_BATCH_MAX_SECTIONS = 4          # Draft 每批小节数上限
_OUTPUT_BUDGET_MIN = 2600        # Draft 每批正文字数（汉字）下限
_OUTPUT_BUDGET_FACTOR = 0.5      # 输出字数约按材料规模的该比例估算
_OUTPUT_BUDGET_MAX = 9000

_REVIEW_HEADINGS = ("FAQ", "易错点", "自测", "检查清单", "复习", "答疑", "常问", "错点", "checklist")


@dataclass
class PageUnit:
    """一页讲义及其对齐口述（Draft / Plan 的最小材料单元）。"""

    index: int
    title: str
    body_md: str = ""
    raw_text: str = ""
    narration: str = ""
    source: str = "slide"          # slide | pseudo(无讲义时按讲述分段) 

    @property
    def material_chars(self) -> int:
        return len(self.body_md) + len(self.narration)

    def body_excerpt(self, limit: int = _PAGE_BODY_MAX) -> str:
        t = self.body_md.strip()
        return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + " …"

    def narration_excerpt(self, limit: int = _PAGE_NARR_MAX) -> str:
        t = (self.narration or "").strip()
        return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + " …"


@dataclass
class PlanSection:
    heading: str
    pages: list = field(default_factory=list)     # 讲义页号（可为空：收尾/综述节）
    instructor_note: str = ""


class LLMLayeredBuilder:
    """v2 LLM 笔记核心（plan -> draft）。"""

    def __init__(
        self,
        meta: CourseMeta,
        orchestrator: PromptOrchestrator,
        client,
        polish: bool = False,
        skill_text: str = "",
    ) -> None:
        self.meta = meta
        self.orchestrator = orchestrator
        self.client = client
        self.polish = polish
        self.skill_text = (skill_text or "").strip()

    # ------------------------------------------------------------------
    def build(
        self,
        slides: ParsedSlides,
        transcript: ProcessedTranscript,
        alignment: AlignmentResult,
    ) -> NoteProduct:
        product = NoteProduct(
            course_title=self.meta.display_title(),
            engine=f"llm:{self.client.model}",
            mode="layered_md",
        )
        pages = _build_page_units(slides, transcript, alignment)
        if not pages:
            raise LLMError("既无讲义页文本也无讲述内容，无法生成笔记。")

        # ---------------- Step 1 · Plan ----------------
        plan = self._call_plan(pages)
        product.layers["plan"] = json.dumps(_plan_to_jsonable(plan), ensure_ascii=False, indent=2)
        product.doc_header = _doc_header(self.meta, plan.get("doc_title") or "")

        # ---------------- Step 2 · Draft（分批） ----------------
        review_digest = _review_digest(pages)
        for batch_no, group in enumerate(_batch_sections(plan["sections"], pages)):
            material_md = _section_material_md(group, pages, review_digest)
            plan_md = _plan_preview_md(plan)
            headings = "\n".join(f"- {s.heading}" for s in group)
            est = sum(_estimate_section_chars(s, pages) for s in group)
            budget = max(_OUTPUT_BUDGET_MIN, min(int(est * _OUTPUT_BUDGET_FACTOR), _OUTPUT_BUDGET_MAX))
            out = self._call(
                "draft",
                {
                    "plan_md": plan_md,
                    "sections_to_write": headings,
                    "material_md": material_md,
                    "output_budget": f"{budget}",
                },
            )
            product.layers[f"section_{batch_no:02d}"] = out

        # ---------------- Step 3 · Polish（可选） ----------------
        if self.polish:
            draft_md = _join_sections([product.layers[k] for k in sorted(product.layers)
                                       if k.startswith("section_")])
            product.layers["polish"] = self._call(
                "polish",
                {"plan_md": _plan_preview_md(plan), "draft_md": draft_md},
            )
        return product

    # ------------------------------------------------------------------
    def _call_plan(self, pages: list) -> dict:
        slides_digest = "\n".join(_page_digest(p) for p in pages)
        timeline = _timeline_digest(pages)
        # 首次尝试
        raw = self._call(
            "plan",
            {"slides_digest": slides_digest, "transcript_digest": timeline, "strict_json": ""},
        )
        plan = _extract_plan_json(raw)
        if plan is None:
            # 重试一次：严格 JSON 输出
            raw2 = self._call(
                "plan",
                {
                    "slides_digest": slides_digest,
                    "transcript_digest": timeline,
                    "strict_json": "只允许输出一个 JSON 对象本身，禁止代码块、禁止任何额外文字。",
                },
            )
            plan = _extract_plan_json(raw2)
        if plan is None:
            raise LLMError("Plan 阶段未能返回可解析的结构计划 JSON。请重试或检查模型输出。")
        return _normalize_plan(plan, max_page=max(p.index for p in pages))

    def _call(self, stage: str, variables: dict) -> str:
        prompt = self.orchestrator.render(stage, self.meta, variables)
        if self.skill_text:
            prompt += (
                "\n\n## 八、用户提供的技能 / 补充要求（优先级最高，必须遵循）\n\n"
                + self.skill_text
            )
        return self.client.complete(prompt)


# ---------------------------------------------------------------------------
# Step 0 · 页资料构造
# ---------------------------------------------------------------------------
def _build_page_units(slides: ParsedSlides, transcript: ProcessedTranscript,
                      alignment: AlignmentResult) -> list:
    """把 讲义页 + 对齐口述 合并成有序 PageUnit 列表。"""
    narration_by_slide = {c.slide_id: c.transcript_text or "" for c in alignment.chunks}
    pages: list = []
    for s in slides.slides:
        pages.append(PageUnit(
            index=s.index,
            title=(s.title or f"第 {s.index} 页").strip(),
            body_md=s.body_md or "",
            raw_text=s.raw_text or "",
            narration=narration_by_slide.get(s.index, "") or "",
        ))
    if not pages:
        # 无讲义：把讲述 topic 分段转成“伪页”，保证 Plan/Draft 仍按节写作
        for sg in transcript.topic_segments:
            text = (sg.text or "").strip()
            if not text:
                continue
            kw = "、".join(str(k) for k in (sg.keywords or [])[:4]) or "讲述片段"
            pages.append(PageUnit(
                index=len(pages) + 1,
                title=f"讲述片段 {len(pages) + 1}（{kw}）",
                body_md="",
                narration=text,
                source="pseudo",
            ))
    return pages


# ---------------------------------------------------------------------------
# Step 1 · 摘录与 Plan
# ---------------------------------------------------------------------------
def _page_digest(p: PageUnit) -> str:
    """Plan 用逐页摘录：标题 + 讲义要点 + 该页口述片段。"""
    title = _one_line(p.title, 90)
    body = _one_line(p.raw_text or p.body_md, _DIGEST_PAGE_BODY)
    narr = _one_line(p.narration, _DIGEST_PAGE_NARR)
    lines = [f"## 第 {p.index} 页｜{title}"]
    if body:
        lines.append(f"- 讲义：{body}")
    if narr:
        lines.append(f"- 教师口述：{narr}")
    else:
        lines.append("- 教师口述：（该页无对齐口述）")
    return "\n".join(lines)


def _timeline_digest(pages: list) -> str:
    """Plan 用讲述脉络摘录：按口述时间先后给出各段内容定位。"""
    chunks = []
    for p in pages:
        if p.narration:
            chunks.append(p)
    if not chunks:
        return "（无口述内容，请仅依据讲义组织结构）"
    # 口述量大的页往前放，便于 Plan 理解讲授重心
    order = sorted(chunks, key=lambda p: -len(p.narration))
    parts: list = []
    budget = _DIGEST_TIMELINE_MAX
    for p in order:
        if budget <= 0:
            parts.append("（其余讲述内容与讲义页对齐，详见逐页口述摘录）")
            break
        snippet = _one_line(p.narration, min(300, budget))
        budget -= len(snippet) + 24
        parts.append(f"第 {p.index} 页《{_one_line(p.title, 60)}》重点口述：{snippet}")
    return "\n".join(parts)


def _review_digest(pages: list) -> str:
    """收尾节（FAQ / 易错点 / 自测清单）使用的全课速览。"""
    parts = []
    for p in pages:
        title = _one_line(p.title, 70)
        body = _one_line(p.raw_text or p.body_md, _DIGEST_REVIEW_PAGE)
        narr = _one_line(p.narration, _DIGEST_REVIEW_PAGE)
        parts.append(f"- P{p.index}《{title}》：{body or '—'}{'；口述：' + narr if narr else ''}")
    return "\n".join(parts)


def _one_line(text: str, limit: int) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if not t:
        return ""
    if len(t) <= limit:
        return t
    cut = t[:limit]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut


def _extract_plan_json(text: str) -> Optional[dict]:
    """从 LLM 回复中稳健抽取计划 JSON（先 fenced，再逐候选 '{' 尝试）。"""
    if not text:
        return None
    # 优先 fenced ```json
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 从前往后逐个候选 '{' 做 raw_decode：优先“看起来像计划根对象”的结果
    decoder = json.JSONDecoder()
    for i in range(len(text)):
        if text[i] != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and ("doc_title" in obj or "sections" in obj):
            return obj
    return None


def _normalize_plan(plan: dict, max_page: int) -> dict:
    """校验 / 规整 Plan JSON：doc_title、sections、页码范围。"""
    doc_title = str(plan.get("doc_title") or "").strip()
    raw_sections = plan.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise LLMError("Plan JSON 缺少非空 sections 列表。")
    sections: list = []
    seen: set = set()
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        heading = re.sub(r"^#{1,6}\s*", "", str(item.get("heading") or "")).strip()
        if not heading:
            continue
        if heading in seen:                       # 去重：追加序号
            heading = f"{heading}（续）"
        seen.add(heading)
        pages = _normalize_pages(item.get("pages"), max_page)
        sections.append(PlanSection(
            heading=heading,
            pages=pages,
            instructor_note=str(item.get("instructor_note") or "").strip(),
        ))
    if not sections:
        raise LLMError("Plan JSON 解析后无有效章节。")

    # 讲义页兜底分配：未出现在任何章节的页 -> 归入最“近”的章节（空页综述节不参与吸收）
    assigned: Counter = Counter()
    for s in sections:
        assigned.update(s.pages)
    missing = [p for p in range(1, max_page + 1) if assigned[p] == 0]
    for p in missing:
        best = min(
            sections,
            key=lambda s: min((abs(p - q) for q in s.pages), default=10**9) if s.pages else 10**9,
        )
        best.pages.append(p)

    # 所有页都空（纯口述无讲义也覆盖不到）：不再处理，Draft 会喂 review digest
    for s in sections:
        s.pages = sorted({int(x) for x in s.pages if 1 <= int(x) <= max_page})
    return {"doc_title": doc_title, "sections": sections}


def _normalize_pages(raw, max_page: int) -> list:
    out: list = []
    if raw is None:
        return out
    if isinstance(raw, str):
        raw = re.split(r"[,\s;，；]+", raw)
    if not isinstance(raw, list):
        return out
    for x in raw:
        s = str(x).strip()
        if not s:
            continue
        if "-" in s and not s.startswith("-"):
            a, _, b = s.partition("-")
            try:
                lo, hi = int(a), int(b)
            except ValueError:
                continue
            out.extend(range(lo, hi + 1))
        else:
            try:
                out.append(int(s))
            except ValueError:
                continue
    return sorted({p for p in out if 1 <= p <= max_page})


# ---------------------------------------------------------------------------
# Step 2 · 批次与材料
# ---------------------------------------------------------------------------
def _estimate_section_chars(s: PlanSection, pages: list) -> int:
    by_index = {p.index: p for p in pages}
    total = 600
    for pid in s.pages:
        p = by_index.get(pid)
        if p:
            total += min(len(p.body_md), 2 * _PAGE_BODY_MAX) + min(len(p.narration), 2 * _PAGE_NARR_MAX)
    return total


def _batch_sections(sections: list, pages: list) -> list:
    """按材料量把章节分批：每批预估字符 <= 上限且小节数 <= 上限。"""
    batches: list = []
    cur: list = []
    cur_chars = 0
    for s in sections:
        est = _estimate_section_chars(s, pages)
        empty = not s.pages                       # 收尾/综述节：单独成批（喂全课速览）
        if cur and (len(cur) >= _BATCH_MAX_SECTIONS or (not empty and cur_chars + est > _BATCH_EST_CHARS) or empty):
            batches.append(cur)
            cur, cur_chars = [], 0
        cur.append(s)
        cur_chars += min(est, _BATCH_EST_CHARS)
    if cur:
        batches.append(cur)
    return batches


def _section_material_md(sections: list, pages: list, review_digest: str) -> str:
    """组材料：普通节 -> 其页码的讲义正文+口述；空页码节 -> 全课速览。"""
    by_index = {p.index: p for p in pages}
    blocks: list = []
    only_review = all(not s.pages for s in sections)
    for s in sections:
        if not s.pages:
            continue
        parts = [f"### 材料：{s.heading}（讲义页 {_fmt_pages(s.pages)}）"]
        for pid in s.pages:
            p = by_index.get(pid)
            if p is None:
                continue
            sub = [f"**第 {pid} 页《{_one_line(p.title, 90)}》**"]
            body = p.body_excerpt()
            if body:
                sub.append(f"- 讲义：\n{_indent(body, 2)}")
            narr = p.narration_excerpt()
            if narr:
                sub.append(f"- 教师口述：\n{_indent(narr, 2)}")
            parts.append("\n".join(sub))
        blocks.append("\n\n".join(parts))
    if not blocks:
        # 本批全部是收尾/综述节：提供全课速览作锚点
        blocks.append("### 全课速览（供收尾/综述节引用，只围绕其中真实出现的主题）\n" + review_digest)
    elif only_review:
        blocks.append("### 全课速览（供收尾/综述节引用）\n" + review_digest)
    return "\n\n---\n\n".join(blocks)


def _fmt_pages(pages: list) -> str:
    pages = sorted(pages)
    if not pages:
        return "无"
    parts: list = []
    start = prev = pages[0]
    for x in pages[1:]:
        if x == prev + 1:
            prev = x
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = x
    parts.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(parts)


def _indent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + ln for ln in text.splitlines())


def _plan_preview_md(plan: dict) -> str:
    lines = [f"文档标题：{plan.get('doc_title') or '（见各节）'}", ""]
    for i, s in enumerate(plan["sections"], start=1):
        pages = _fmt_pages(s.pages)
        lines.append(f"{i}. ## {s.heading}" + (f"（覆盖讲义页：{pages}）" if pages else "（综合全课）"))
    return "\n".join(lines)


def _plan_to_jsonable(plan: dict) -> dict:
    """把含 PlanSection 对象的 plan 转为可 JSON 序列化的 dict。"""
    return {
        "doc_title": plan.get("doc_title") or "",
        "sections": [
            {
                "heading": s.heading,
                "pages": list(s.pages),
                "instructor_note": s.instructor_note or "",
            }
            for s in plan.get("sections", [])
        ],
    }


def _doc_header(meta: CourseMeta, doc_title: str) -> str:
    """最终笔记头部块（# 标题 + 课程信息行）。"""
    title = doc_title or meta.display_title()
    bits: list = []
    if meta.course_name:
        bits.append(f"**课程（Course）**：{meta.course_name}"
                    + (f" / {meta.course_code}" if meta.course_code else ""))
    if meta.instructor:
        bits.append(f"**讲师（Instructor）**：{meta.instructor}")
    if meta.lecture_date:
        bits.append(f"**日期（Date）**：{meta.lecture_date}")
    bits.append("**来源（Source）**：课堂讲义 + 教师口述转录")
    header = [f"# {title}", ""]
    if bits:
        header.append("> " + "　|　".join(bits))
    return "\n".join(header)


def _join_sections(parts: list) -> str:
    return "\n\n---\n\n".join(x.strip() for x in parts if x and x.strip())
