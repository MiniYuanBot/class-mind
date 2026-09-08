"""L4 质检修订闭环（QA Fix Loop）。

与 paper-mind 的修订闭环同构：成稿 → run_qa → 存在可机修问题(HEADINGS/MATH/CODEBLOCK/
SCAFFOLD/CONSISTENCY 等)时，把问题清单回喂 LLM 修订整篇 → 重新质检，最多 rounds 轮。
只修“机器可判定”的问题；COVERAGE/FIGURE 类仅提示，不触发回喂。
"""

from __future__ import annotations

from classmind.core.llm import LLMError
from classmind.models import (
    AlignmentResult,
    CourseMeta,
    NoteProduct,
    ParsedSlides,
    ProcessedTranscript,
)
from classmind.prompts.orchestrator import PromptOrchestrator
from classmind.quality.checks import run_qa

# 机器可修（回喂触发）与仅提示的检查码
FIXABLE_CODES = ("HEADINGS", "MATH", "CODEBLOCK", "SCAFFOLD", "CONSISTENCY")
TRUNCATED_MARK = "<!-- [classmind] response truncated by max_tokens -->"
MIN_NOTE_CHARS = 600


def _actionable(report: list) -> list:
    return [r for r in report if r.get("level") != "OK" and r.get("code") in FIXABLE_CODES]


class NoteFixer:
    """P7.5 质检修订器：需要 LLM client；无 client 或 rounds=0 时跳过。"""

    def __init__(
        self,
        client,
        orchestrator: PromptOrchestrator | None = None,
        skills=None,
        skill_text: str = "",
    ) -> None:
        self.client = client
        self.orchestrator = orchestrator or PromptOrchestrator()
        self.skills = skills or []
        self.skill_text = (skill_text or "").strip()

    # ------------------------------------------------------------------
    def fix(
        self,
        meta: CourseMeta,
        note_md: str,
        slides: ParsedSlides,
        transcript: ProcessedTranscript,
        alignment: AlignmentResult,
        product: NoteProduct,
        rounds: int = 1,
    ) -> tuple:
        """回喂修订。返回 (final_md, final_report)。无 client / rounds<=0 / 无问题时不调用 LLM。"""
        if self.client is None or rounds <= 0:
            report = run_qa(slides, transcript, alignment, product, note_md)
            return note_md, report
        report = run_qa(slides, transcript, alignment, product, note_md)
        md = note_md
        for rnd in range(rounds):
            issues = _actionable(report)
            if not issues:
                break
            print(f"  [QA-Fix] 第 {rnd + 1}/{rounds} 轮修订（{len(issues)} 项可机修问题）…")
            prompt = self._render_fix_prompt(meta, md, issues)
            revised = self._complete(prompt, original_len=len(md))
            if revised is None:
                print("  [QA-Fix] 修订输出疑似截断/过短，保留上一版并停止。")
                break
            md = revised
            report = run_qa(slides, transcript, alignment, product, md)
            product.qa_warnings = [r["message"] for r in report if r["level"] == "WARN"]
        if _actionable(report):
            print("  [QA-Fix] 注意：仍有可机修问题（可提高 --fix-rounds 或人工修订）。")
        return md, report

    # ------------------------------------------------------------------
    def _render_fix_prompt(self, meta: CourseMeta, note_md: str, issues: list) -> str:
        variables = {
            "qa_issues": _format_issues(issues),
            "note_md": note_md[:120_000],
        }
        prompt = self.orchestrator.render("fix", meta, variables)
        skills_md = _skills_text(self.skills, self.skill_text)
        if skills_md:
            prompt += "\n\n## 用户技能与补充要求（User Skills — 优先级最高，必须遵循）\n\n" + skills_md
        return prompt

    def _complete(self, prompt: str, original_len: int) -> str | None:
        try:
            out = self.client.complete(prompt).strip()
        except LLMError as exc:
            print(f"  [QA-Fix] LLM 调用失败: {exc}")
            return None
        if TRUNCATED_MARK in out:
            out = out.replace(TRUNCATED_MARK, "").strip()
        if len(out) < max(MIN_NOTE_CHARS, int(original_len * 0.5)):
            return None
        return out


# ---------------------------------------------------------------------------
def _skills_text(skills: list, fallback: str) -> str:
    parts = [
        f"### {sk.name}\n\n{sk.text}"
        for sk in skills
        if getattr(sk, "kind", "prompt") == "prompt" and sk.applies_to("fix")
    ]
    if parts:
        return "\n\n".join(parts)
    return fallback


def _format_issues(issues: list) -> str:
    return "\n".join(
        f"- [{r.get('code')}] {r.get('message', '')}" for r in issues
    )
