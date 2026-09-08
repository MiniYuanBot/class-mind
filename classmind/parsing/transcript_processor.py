"""P3 讲述处理器（Transcript Processor）。

输入：DOCX / TXT / MD 的课堂讲述（可含时间戳与说话人前缀）
处理链：
  S1 口语去噪（口头禅 / 重复 / 自我修正，保留逻辑停顿 --）
  S2 说话人分离（教师讲解为主干，学生提问保留为引用块）
  S3 重点标记（强调信号 -> **重点** / **易错点**）
  S4 时间戳锚点（<!-- timestamp: hh:mm:ss -->）
  +  话题分段（topic_segments，含关键词）
输出：ProcessedTranscript（transcript_clean + highlights[] + topic_segments[]）
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from classmind.errors import ParseError, UnsupportedFormatError
from classmind.models import Highlight, ProcessedTranscript, TopicSegment
from classmind.util import HIGHLIGHT_CUES, HIGHLIGHT_CUES_EN, normalize_whitespace, split_sentences, strip_fillers_text, tokenize_keywords

# 说话人前缀
_SPEAKER_PREFIX = re.compile(
    r"^\s*(?:\[([^\]]+)\]\s*)?"
    r"(?P<who>教师|老师|教授|讲师|学生|同学|提问|答|助教|TA|主持人|学生[ABC]?|甲|乙|[Tt]eacher|[Ss]tudent|[Qq]:|[Aa]:|[Tt]:)?\s*[:：]\s*"
)
_TS_PREFIX = re.compile(r"^\s*\[?(?:(?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{2})\]?\s*")
_TS_INLINE = re.compile(r"\[(?:(?:(\d{1,2}):)?(\d{1,2}):(\d{2}))\]")

_STUDENT_HINTS = ("学生", "提问", "同学", "[Qq]", "[Aa]", "甲", "乙")
_DISCUSSION_HINTS = ("讨论", "小组", "多人")

_TOPIC_CUES = (
    "接下来", "下面", "然后我们", "现在我们", "我们来看", "我们进入", "第二部分", "第三部分",
    "第一部分", "首先", "其次", "最后", "下一部分", "进入下一", "现在我们讲", "接下来讲",
    "好了，", "好的，", "那好", "这一节", "这节课我们",
)

STOP_SEGMENT = None


class TranscriptProcessor:
    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    def process(self, path: Path) -> ProcessedTranscript:
        text = _read_transcript_file(path)
        return self.process_text(text, source=path.name)

    # ------------------------------------------------------------------
    def process_text(self, raw_text: str, source: str = "") -> ProcessedTranscript:
        result = ProcessedTranscript(source_file=source)
        if not raw_text or not raw_text.strip():
            raise ParseError("讲述文本为空")

        lines = _split_into_utterances(raw_text)
        if not lines:
            result.warnings.append("[FAIL] 讲述文本未包含有效教学内容")
            return result

        utterances: list = []
        for ln in lines:
            ts = _extract_timestamp(ln)
            who, content = _classify_speaker(ln)
            utt = {"ts": ts, "who": who, "raw": content, "clean": ""}
            utterances.append(utt)

        # ---- S1 去噪 + S3 重点检测 ----
        md_lines: list = []
        teacher_paras: list = []
        for i, utt in enumerate(utterances):
            if utt["who"] == "discussion":
                continue
            clean = _denoise(utt["raw"])
            utt["clean"] = clean
            if not clean:
                continue

            ts = utt["ts"]
            ts_anchor = f"<!-- timestamp: {ts} -->\n" if ts else ""

            if utt["who"] == "student":
                if re.search(r"[?？]$", clean) or clean.startswith(("为什么", "怎么", "如何", "能否", "请")):
                    md_lines.append(f"{ts_anchor}> 学生提问：{clean}")
                # 非提问的学生发言视为课堂讨论噪音，跳过
                continue

            label, triggers = _detect_highlight(clean)
            if label == "易错点":
                md_lines.append(f"{ts_anchor}**易错点**：{clean}")
            elif label == "重点":
                md_lines.append(f"{ts_anchor}**重点**：{clean}")
                result.highlights.append(
                    Highlight(text=clean, triggers=triggers, label=label, timestamp=ts, line_no=i + 1)
                )
            else:
                md_lines.append(f"{ts_anchor}{clean}")
            teacher_paras.append((ts, clean))

        result.clean_text = normalize_whitespace("\n".join(p[1] for p in teacher_paras))
        result.clean_md = "\n\n".join(md_lines)

        # ---- 话题分段 ----
        result.topic_segments = _segment_topics(teacher_paras)

        # ---- 数据质量 ----
        if not teacher_paras:
            result.warnings.append("[FAIL] 去除噪音后无教师讲解内容")
        if len(result.clean_text) < 20:
            result.warnings.append("[WARN] 讲述内容过短，可能缺少有效教学信息")
        return result


# ---------------------------------------------------------------------------
# 文件读取
# ---------------------------------------------------------------------------
def _read_transcript_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        try:
            return path.read_text(encoding="utf-8-sig", errors="replace")
        except UnicodeDecodeError:
            return path.read_text(encoding="gb18030", errors="replace")
    if ext == ".docx":
        try:
            from docx import Document  # type: ignore

            doc = Document(str(path))
            parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" ".join(c.text for c in row.cells))
            return "\n".join(parts)
        except ImportError as exc:  # pragma: no cover
            raise UnsupportedFormatError("解析 DOCX 需要 python-docx，请执行: pip install classmind[docx]") from exc
        except Exception as exc:  # noqa: BLE001
            raise ParseError(f"无法读取 DOCX {path.name}: {exc}") from exc
    raise UnsupportedFormatError(f"讲述文本格式不支持: {ext}（仅支持 .txt / .md / .docx）")


def _split_into_utterances(text: str) -> list:
    """把原始文本切成“语句/段落”单元，每条视为一次发言。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts: list = []
    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            continue
        parts.append(s)
    return parts


def _extract_timestamp(line: str) -> Optional[str]:
    m = _TS_PREFIX.match(line)
    if m:
        h, mi, s = m.group("h"), m.group("m"), m.group("s")
        return f"{int(h or 0):02d}:{int(mi):02d}:{s}"
    m = _TS_INLINE.search(line)
    if m:
        h, mi, s = m.group(1), m.group(2), m.group(3)
        return f"{int(h or 0):02d}:{int(mi):02d}:{s}"
    return None


def _classify_speaker(line: str):
    """返回 (who, content)。who ∈ teacher / student / discussion / unknown。"""
    stripped = _TS_PREFIX.sub("", line).strip()
    m = _SPEAKER_PREFIX.match(stripped)
    if m:
        who_raw = (m.group("who") or "").lower()
        content = stripped[m.end():].strip()
        if any(h in who_raw for h in ("学生", "同学", "[q", "[a", "student", "甲", "乙", "提问")):
            return ("student", content or stripped)
        if any(h in who_raw for h in ("discussion", "小组", "多人", "讨论")):
            return ("discussion", content or stripped)
        # 教师 / 老师 / TA / 主持人 / 教授 -> teacher
        return ("teacher", content or stripped)
    # 无前缀：默认视为教师
    low = stripped.lower()
    if low.startswith(("q:", "问题：")):
        return ("student", re.sub(r"^(q:|问题：)", "", stripped, flags=re.I))
    return ("teacher", stripped)


def _denoise(text: str) -> str:
    """S1 口语去噪：移除口头禅、重复与自我修正，保留 -- 停顿与标点。"""
    s = strip_fillers_text(text)
    # 保留逻辑停顿标记 --，去掉两侧多余空白
    s = re.sub(r"\s*--\s*", " -- ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    # 破折号结尾的未完成句与开场寒暄剔除
    s = re.sub(r"^(好，)?(那么)?(好的)?(同学们)?(大家好)?[,，:：]?\s*", "", s)
    return s.strip()


def _detect_highlight(text: str):
    """S3 重点检测（中英双语信号）：返回 (label, triggers)。"""
    hits = [cue for cue in HIGHLIGHT_CUES if cue in text]
    low = text.lower()
    for cue in HIGHLIGHT_CUES_EN:
        if re.search(r"(?<![a-z])" + re.escape(cue) + r"(?![a-z])", low):
            hits.append(cue)
    if not hits:
        return ("", [])
    labels = [HIGHLIGHT_CUES.get(c, HIGHLIGHT_CUES_EN.get(c, "重点")) for c in hits]
    if "易错点" in labels:
        return ("易错点", hits)
    return ("重点", hits)


def _is_topic_boundary(para: str) -> bool:
    return any(para.startswith(cue) for cue in _TOPIC_CUES)


def _has_page_ref(para: str) -> bool:
    """段落显式翻页（“看第 N 页 / slide N”）视为新话题边界，便于逐页对齐。"""
    return bool(re.search(r"(?:看|翻到|打开|回到|对照|在)?\s*第\s*[0-9一二三四五六七八九十]+\s*[页张]|(?:看|去)?\s*[Ss]lide\s*\d+", para))


def _segment_topics(paras: list) -> list:
    """话题分段：按语篇提示词切分 + 关键词抽取。"""
    segs: list = []
    current: list = []
    current_ts = None

    def flush():
        nonlocal current, current_ts
        if current:
            text = " ".join(current)
            segs.append(
                TopicSegment(
                    index=len(segs) + 1,
                    keywords=tokenize_keywords(text, 6),
                    text=text,
                    timestamp_start=current_ts,
                )
            )
        current = []
        current_ts = None

    for ts, para in paras:
        if ts and not current_ts:
            current_ts = ts
        if current and (_is_topic_boundary(para) or _has_page_ref(para)):
            flush()
            current_ts = ts
        current.append(para)
    flush()
    # 时间戳结束补齐
    for i in range(len(segs) - 1):
        segs[i].timestamp_end = segs[i + 1].timestamp_start
    if segs:
        segs[-1].timestamp_end = ""
    if not segs:
        segs.append(TopicSegment(index=1, keywords=[], text="", timestamp_start=None))
    # 英文 / 无中文语篇提示词时：未触发任何切分则退回按自然段分段，避免单巨段吞掉主题
    if len(segs) == 1 and len(paras) >= 3:
        segs = []
        for ts, para in paras:
            segs.append(
                TopicSegment(
                    index=len(segs) + 1,
                    keywords=tokenize_keywords(para, 6),
                    text=para,
                    timestamp_start=ts,
                )
            )
        for i in range(len(segs) - 1):
            segs[i].timestamp_end = segs[i + 1].timestamp_start
        if segs:
            segs[-1].timestamp_end = ""
    return segs
