"""P4 多模态对齐层（Multimodal Alignment）。

把“视觉课件”与“口述讲述”在语义层面对齐，解决“教师讲第 N 页时到底在讲什么”。
对齐信号：
  1. 显式页码引用（“看第 3 页”、“Slide 5” / "page 3"） -> 直接映射 slide_id
  2. 图表引用（“如图 1 所示”）                          -> 映射到含对应图片的页
  3. 关键词匹配（术语高度相似）                          -> 软对齐
  4. 顺序一致性（课件顺序与讲述时间线大致一致）           -> 单调前向 + 回看
实现：以“句”为对齐单元（中英双语切分），对每页累积其讲述句，避免大段落稀释相似度。
输出：aligned_chunks[] + alignment_map + unaligned_segments[] + coverage
"""

from __future__ import annotations

import re
from collections import Counter, OrderedDict

from classmind.models import (
    AlignedChunk,
    AlignmentRecord,
    AlignmentResult,
    Confidence,
    ParsedSlides,
    ProcessedTranscript,
)
from classmind.util import cjk_bigrams, split_sentences

_PAGE_REF = re.compile(
    r"(?:第\s*(\d+)\s*[页张]|page\s*#?\s*(\d+)|[Ss]lide\s*#?\s*(\d+)|[Ss]\s*(\d+)\s*页)"
)
_FIGURE_REF = re.compile(r"(?:如\s*(?:上|[此这])?图|看\s*图|参见图|见图|as shown in (?:the )?(?:figure|fig(?:ure)?\.?)\s*(\d+)?)", re.I)
_RECAP_HINTS = ("刚才", "之前", "上一页", "上一张", "前面讲", "回顾", "复习", "earlier", "previously", "as we said", "we said before", "recall that", "remind")

_MIN_SLIDE_WORDS = 4  # 页特征不足时不参与软对齐


def _dice(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return 2 * inter / (len(a) + len(b))


def _words(text: str) -> list:
    """英文字词 + 中文 bigram 的混合 token 序列。"""
    return cjk_bigrams(text or "")


def _tokens(text: str) -> set:
    """token 集合：单词/bigram + 连续双词短语（英文增强）。"""
    ws = _words(text)
    toks = set(ws)
    for i in range(len(ws) - 1):
        a, b = ws[i], ws[i + 1]
        if a.isascii() and b.isascii():
            toks.add(f"{a} {b}")
    return toks


class Aligner:
    def __init__(self, coverage_threshold: float = 0.7) -> None:
        self.coverage_threshold = coverage_threshold

    # ------------------------------------------------------------------
    def align(self, slides: ParsedSlides, transcript: ProcessedTranscript) -> AlignmentResult:
        result = AlignmentResult()
        if not slides.slides:
            return result

        n_slides = len(slides.slides)
        slide_feats: list = []
        for s in slides.slides:
            feats: set = set()
            feats |= _tokens(s.title)
            entry = next((e for e in slides.index if e.page == s.index), None)
            if entry:
                for kw in entry.keywords:
                    feats |= _tokens(str(kw))
            feats |= _tokens(s.raw_text[:900])
            slide_feats.append(feats)

        # ---- 句级对齐单元 ----
        units: list = []  # {text, seg}
        for sg in transcript.topic_segments:
            for sent in split_sentences(sg.text or ""):
                if len(sent.strip()) >= 3:
                    units.append({"text": sent.strip(), "seg": sg.index})
        if not units:
            result.warnings.append("[WARN] 讲述无可对齐语句，跳过对齐")
            return result

        # ---- 句级全局最优分配（允许跳页/回顾，讲述时间线不强制单调）----
        assignments: dict = {}           # unit_idx -> slide_id（-1 未对齐）
        by_slide: "OrderedDict[int, list]" = OrderedDict()

        for i, unit in enumerate(units):
            text = unit["text"]
            sid = _explicit_target(text, n_slides)
            if sid is None:
                sid, score = self._best_slide_global(text, slide_feats, n_slides)
                if score <= 0.0:
                    assignments[i] = -1
                    continue
            assignments[i] = sid
            by_slide.setdefault(sid, []).append(i)

        # ---- 按页汇总 chunk ----
        explicit_units = {
            i: sid for i, sid in assignments.items()
            if sid >= 1 and _explicit_target(units[i]["text"], n_slides) == sid
        }
        for slide_id, unit_ids in by_slide.items():
            slide = slides.slides[slide_id - 1]
            texts = [units[i]["text"] for i in unit_ids]
            first_seg = units[unit_ids[0]]["seg"]
            joined = " ".join(texts)[:2200]
            high = (slide_id in explicit_units.values()
                    or _dice(_tokens(joined[:800]), slide_feats[slide_id - 1]) >= 0.30)
            conf = Confidence.HIGH if high else Confidence.MEDIUM
            signals = _gather_signals(texts, slide_id)
            chunks = AlignedChunk(
                slide_id=slide_id,
                transcript_seg=first_seg,
                confidence=conf,
                slide_title=slide.title,
                transcript_text=joined,
                signals=signals,
            )
            result.chunks.append(chunks)
            result.records.append(AlignmentRecord(
                slide_id=slide_id,
                slide_title=slide.title,
                seg_index=first_seg,
                confidence=conf.value,
                signals=signals,
            ))

        result.chunks.sort(key=lambda c: c.slide_id)

        # ---- 未对齐句 ----
        for i, unit in enumerate(units):
            if assignments.get(i, -1) < 1:
                result.unaligned_segments.append({
                    "seg_index": unit["seg"],
                    "snippet": unit["text"][:150],
                    "reason": "关键词相似度不足，可能为即兴发挥、课堂讨论或设备杂音",
                })

        # ---- 覆盖率（对齐句字符数 / 全句字符数）----
        result.coverage = _char_coverage(
            "".join(units[i]["text"] for i, sid in assignments.items() if sid >= 1),
            "".join(u["text"] for u in units),
        )
        if result.coverage < self.coverage_threshold:
            result.warnings.append(
                f"[WARN] 讲述覆盖度 {result.coverage:.0%} 低于阈值 {self.coverage_threshold:.0%}，"
                f"存在 {len(result.unaligned_segments)} 段未对齐讲述，可能为课外闲聊或设备杂音。"
            )
        return result

    # ------------------------------------------------------------------
    def _best_slide_global(self, text: str, slide_feats: list, n: int):
        """全页范围 argmax（不依赖讲述顺序）。返回 (slide_id, score)。"""
        tok = _tokens(text)
        if not tok:
            return -1, 0.0
        best_sid, best_sc = -1, 0.0
        for sid in range(1, n + 1):
            if sid - 1 >= len(slide_feats):
                continue
            sc = _dice(tok, slide_feats[sid - 1])
            if sc > best_sc:
                best_sc, best_sid = sc, sid
        return best_sid, best_sc


# ---------------------------------------------------------------------------
def _explicit_target(text: str, n_slides: int):
    for m in _PAGE_REF.finditer(text):
        g = next((x for x in m.groups() if x), None)
        if g:
            target = int(g)
            if 1 <= target <= n_slides:
                return target
    return None


def _gather_signals(texts: list, slide_id: int) -> list:
    signals: list = []
    for t in texts:
        if _explicit_target(t, 10**6) is not None:
            signals.append("显式页码引用")
        elif _FIGURE_REF.search(t):
            signals.append("图表引用")
        else:
            signals.append("关键词匹配")
    out: list = []
    for s in signals:
        if s not in out:
            out.append(s)
    return out or ["关键词匹配"]


def _char_coverage(a: str, b: str) -> float:
    """按字母/数字/汉字字符计覆盖比例。"""

    def chars(s: str):
        return re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", s)

    ca, cb = chars(a), chars(b)
    if not cb:
        return 1.0
    need = Counter(cb)
    have = Counter(ca)
    matched = sum(min(need[k], have[k]) for k in need)
    return matched / len(cb)
