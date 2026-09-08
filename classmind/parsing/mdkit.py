"""课件 -> Markdown 的共用构建工具（列表 / 表格 / 公式 / 锚点）。"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from classmind.util import looks_like_formula_line

# 常见 Unicode 数学字符 -> LaTeX
_UNICODE_TO_LATEX = {
    "×": r"\times", "÷": r"\div", "±": r"\pm", "∓": r"\mp",
    "·": r"\cdot", "−": "-", "–": "-", "—": "---",
    "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx",
    "∞": r"\infty", "∂": r"\partial", "∇": r"\nabla",
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int",
    "√": r"\sqrt", "∈": r"\in", "∉": r"\notin",
    "∀": r"\forall", "∃": r"\exists", "∅": r"\emptyset",
    "→": r"\rightarrow", "←": r"\leftarrow", "⇒": r"\Rightarrow",
    "⇔": r"\Leftrightarrow", "∘": r"\circ", "⊕": r"\oplus", "⊗": r"\otimes",
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\epsilon", "θ": r"\theta", "λ": r"\lambda", "μ": r"\mu",
    "ν": r"\nu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma",
    "τ": r"\tau", "φ": r"\phi", "ψ": r"\psi", "ω": r"\omega",
    "η": r"\eta", "κ": r"\kappa", "Γ": r"\Gamma", "Δ": r"\Delta",
    "Θ": r"\Theta", "Λ": r"\Lambda", "Π": r"\Pi", "Σ": r"\Sigma",
    "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
}

_BULLET_RE = re.compile(r"^\s*(?:[•●◦▪‣–—\-*·]|(?:[①-⑳])|(?:\(\d\)|\d+[.、)]))\s*(.*)$")


def latexify(text: str) -> str:
    for uni, latex in _UNICODE_TO_LATEX.items():
        text = text.replace(uni, latex)
    return text


def is_formula(text: str) -> bool:
    return looks_like_formula_line(text)


def page_anchor(slide_id: int, title: str, step: Optional[int] = None) -> str:
    if step is not None:
        return f'<!-- slide: id={slide_id}, step={step} -->'
    return f'<!-- slide: id={slide_id}, title="{title}" -->'


def block_to_md(title: str, lines: list, slide_id: int = 0) -> str:
    """将按行切分的文本块转成紧凑 Markdown（标题 + 列表 / 公式识别）。"""
    out: list = []
    if title:
        out.append(f"## {title}")
    pending_code: list = []
    code_open = False

    def flush_code() -> None:
        nonlocal code_open
        if code_open:
            out.append("```")
            code_open = False
        pending_code.clear()

    for raw in lines:
        line = raw.rstrip()
        s = line.strip()
        if not s:
            continue
        m = _BULLET_RE.match(line)
        if m and not code_open:
            flush_code()
            out.append(f"- {m.group(1).strip()}")
        elif is_formula(s):
            flush_code()
            out.append("$$")
            out.append(latexify(s))
            out.append("$$")
        elif _looks_like_code(s):
            flush_code()
            code_open = True
            out.append("```text")
            out.append(line)
        else:
            if code_open:
                out.append(line)
            else:
                out.append(line)
    flush_code()
    return "\n".join(out)


_CODE_KEYWORDS = ("def ", "function ", "class ", "import ", "int ", "void ", "for(", "while(", "if(", "return ", "print(")


def _looks_like_code(line: str) -> bool:
    low = line.lower()
    return any(k in low for k in _CODE_KEYWORDS) and len(line) < 200


def table_to_md(headers: list, rows: Iterable[list], align: Optional[list] = None) -> str:
    """二维数据 -> 标准 Markdown 表格（紧凑风格）。"""
    headers = [str(h).strip() for h in headers]
    body = [[str(c).strip().replace("|", "\\|") for c in row] for row in rows]
    width = max(len(headers), max((len(r) for r in body), default=0))
    headers += [""] * (width - len(headers))
    body = [r + [""] * (width - len(r)) for r in body]
    if align is None:
        align = [":---"] * width
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(align) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
