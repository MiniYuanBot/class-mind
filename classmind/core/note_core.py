"""P6 AI 笔记核心（AI Note Core）。

LLM 写作链（v2）：Plan（课程规划）-> Draft（分节精写）-> 可选 Polish（整篇审校）。
需要 OpenAI 兼容文本 API（DeepSeek 等）；Key 从 .env / 环境变量 / --api-key 提供。
（legacy 确定性引擎已移除，工具为纯 LLM 模式。）
"""

from __future__ import annotations

from classmind.core.llm import LLMError
from classmind.core.llm_builder import LLMLayeredBuilder
from classmind.models import AlignmentResult, CourseMeta, NoteProduct, ParsedSlides, ProcessedTranscript
from classmind.prompts.orchestrator import PromptOrchestrator


class NoteCore:
    """P6 笔记核心（LLM）。"""

    def __init__(
        self,
        meta: CourseMeta,
        orchestrator: PromptOrchestrator,
        client=None,
        skill_text: str = "",
    ) -> None:
        self.meta = meta
        self.orchestrator = orchestrator
        self.client = client
        self.skill_text = skill_text

    # ------------------------------------------------------------------
    def build(
        self,
        slides: ParsedSlides,
        transcript: ProcessedTranscript,
        alignment: AlignmentResult,
    ) -> NoteProduct:
        if self.client is None:
            raise LLMError(
                "ClassMind 需要 LLM API Key：请检查仓库根目录 .env（CLASSMIND_API_KEY）"
                "或系统环境变量 / --api-key。（确定性离线引擎已移除，工具为纯 LLM 模式。）"
            )
        return LLMLayeredBuilder(self.meta, self.orchestrator, self.client,
                                 skill_text=self.skill_text).build(slides, transcript, alignment)
