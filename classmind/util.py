"""工具函数：中文文本处理、关键词、术语、公式启发等。"""

from __future__ import annotations

import re
from collections import Counter

# ---------------------------------------------------------------------------
# 基本文本处理
# ---------------------------------------------------------------------------
CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_\-.]*")
NUMBER = re.compile(r"\d+")

STOPWORDS_CN = {
    "这个", "那个", "就是", "然后", "因为", "所以", "我们", "你们", "他们", "大家",
    "一个", "一种", "一下", "这里", "那里", "这样", "那样", "什么", "怎么", "可以",
    "需要", "进行", "通过", "对于", "关于", "如果", "那么", "还有", "以及", "或者",
    "时候", "知道", "应该", "可能", "非常", "比较", "主要", "现在", "今天", "咱们",
    "对吧", "等于", "不是", "没有", "这个这个", "叫做", "称为", "指的是", "看这个",
}
STOPWORDS_EN = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "with",
    "that", "this", "is", "are", "was", "were", "be", "by", "as", "at", "it",
    "we", "you", "they", "can", "will", "its", "their",
}

FILLERS = [
    "嗯", "呃", "啊", "哦", "呐", "那个", "这个", "就是说", "就是那个", "对吧",
    "对不对", "那么", "然后呢", "就是说呢", "那那个", "哎", "诶", "来我们", "我们我们",
    "大家大家", "你看你看", "就是就是", "对吧对吧",
]

HIGHLIGHT_CUES = {
    "重点": "重点",
    "注意": "重点",
    "记住": "重点",
    "关键": "重点",
    "非常重要": "重点",
    "很重要": "重点",
    "考试会考": "重点",
    "常考": "重点",
    "必考": "重点",
    "核心": "重点",
    "易错": "易错点",
    "别忘": "易错点",
    "千万不要": "易错点",
    "容易出错": "易错点",
    "常见错误": "易错点",
    "坑": "易错点",
}

# 英文强调信号（大小写不敏感）
HIGHLIGHT_CUES_EN = {
    "important": "重点",
    "note that": "重点",
    "remember": "重点",
    "key": "重点",
    "the key": "重点",
    "critical": "重点",
    "crucial": "重点",
    "very important": "重点",
    "essential": "重点",
    "be careful": "易错点",
    "common mistake": "易错点",
    "common pitfall": "易错点",
    "don't": "易错点",
    "do not": "易错点",
    "avoid": "易错点",
    "easily confused": "易错点",
    "make sure": "重点",
    "pay attention": "重点",
    "this is the point": "重点",
}


def is_ascii_math_char(ch: str) -> bool:
    return ch in "∑∫√∏±×÷≤≥≈≠∞∂∇∈∀∃→←⇒⇔·λβαγδεθπσφψωηξμνκρτωΦΛΔΓΘΠΣΩαβ"

def split_sentences(text: str) -> list:
    """中英双语按句切分：中文句号/感叹/问号，英文 .!? + 空白，以及换行。"""
    if not text:
        return []
    # 英文缩写兜底：不切分常见缩写（等保真即可）
    parts: list = []
    for seg in re.split(r"\n+", text):
        seg = seg.strip()
        if not seg:
            continue
        seg = re.sub(r"[ \t]+", " ", seg)
        # 中文标点直接切
        zh_parts = re.split(r"(?<=[。！？；!?])", seg)
        for zhp in zh_parts:
            zhp = zhp.strip()
            if not zhp:
                continue
            # 英文句子切分：'. ' '! ' '? ' 后跟大写或空行
            en_parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"'(])", zhp)
            for ep in en_parts:
                ep = ep.strip()
                if ep:
                    parts.append(ep)
    return parts


def cjk_bigrams(text: str) -> list:
    """CJK 连续片段的双字二元组 + 拉丁词 + 数字 token，用于无分词情况下的相似度。"""
    tokens: list = []
    for run in CJK_RUN.findall(text):
        if len(run) == 1:
            tokens.append(run)
        for i in range(len(run) - 1):
            tokens.append(run[i : i + 2])
        # 单字 token 不加入，避免噪声
    for w in LATIN_WORD.findall(text):
        if w.lower() not in STOPWORDS_EN:
            tokens.append(w.lower())
    return tokens


def tokenize_keywords(text: str, top_k: int = 8) -> list:
    """简易关键词抽取：bigram + 拉丁词频次统计，去停用词。"""
    counter: Counter = Counter()
    for run in CJK_RUN.findall(text):
        if len(run) >= 4 and run not in STOPWORDS_CN:
            counter[run] += 1
        for i in range(max(0, len(run) - 1)):
            bigram = run[i : i + 2]
            if bigram not in STOPWORDS_CN:
                counter[bigram] += 1
    for w in LATIN_WORD.findall(text):
        low = w.lower()
        if low not in STOPWORDS_EN and len(w) >= 3:
            counter[low] += 1
    # 常见泛化词过滤
    drop = {
        "这个", "那个", "我们", "大家", "进行", "一个", "可以", "因为", "所以",
        "如果", "就是", "然后", "这种", "一种", "对于", "根据", "通过", "如何",
        "问题", "方法", "内容", "课件", "大家", "同学们", "对不对", "时候",
    }
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    out: list = []
    for tok, _ in ranked:
        if tok in drop:
            continue
        out.append(tok)
        if len(out) >= top_k:
            break
    return out


def english_terms(text: str) -> list:
    """抽取疑似英文术语（首字母大写单词 / 括号内英文）。"""
    found: list = []
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9\-]{1,}(?:\s+[A-Za-z][A-Za-z0-9\-]{1,})?", text):
        w = m.group(0).strip()
        if len(w) < 2 or w.lower() in STOPWORDS_EN:
            continue
        found.append(w)
    seen: list = []
    for w in found:
        if w not in seen:
            seen.append(w)
    return seen[:12]


def looks_like_formula_line(line: str) -> bool:
    """启发式：一行是否更像数学公式（而非散文）。"""
    s = line.strip()
    if not s or len(s) > 220:
        return False
    math_chars = sum(1 for ch in s if is_ascii_math_char(ch))
    has_equals = ("=" in s or "≈" in s or "≤" in s or "≥" in s or "<" in s or ">" in s)
    has_latin_dense = len(LATIN_WORD.findall(s)) >= 2
    return (math_chars >= 2 or (has_equals and has_latin_dense and len(s) < 140))


def unwrap_paren_english(text: str) -> list:
    """从「中文（English Term）」或「中文 (English Term)」中提取英文。"""
    return [
        m.group(1).strip()
        for m in re.finditer(r"[（(]\s*([A-Za-z][A-Za-z0-9\s\-,.]{1,60}?)\s*[)）]", text)
    ]


def normalize_whitespace(text: str) -> str:
    text = text.replace("\u3000", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).rstrip() for ln in text.splitlines()]
    return "\n".join(lines).strip()


def strip_fillers_text(text: str) -> str:
    """去除单段文本中的口头禅 / 语气词。"""
    for f in sorted(FILLERS, key=len, reverse=True):
        text = text.replace(f, "")
    # 去除孤立的单个语气字（前后为空格/标点/边界），但保留作为语素的情形
    text = re.sub(r"(?<=[\s，。！？、；：,.!?;:（）()“”\"'])[嗯啊呃哦诶哎](?=[\s，。！？、；：,.!?;:（）()“”\"'])", "", text)
    # 相邻重复字/词去重（自我修正）：我们我们 -> 我们；走走走 -> 走
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    for w in re.findall(r"[\u4e00-\u9fff]{2,6}", text):
        d = 2
        while len(w) % d == 0 and d <= len(w) // 2:
            unit = w[: len(w) // d]
            if unit * d == w and len(unit) >= 2:
                text = text.replace(w, unit)
                break
            d += 1
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([，。！？、；：,.!?;:])", r"\1", text)
    return text.strip()
