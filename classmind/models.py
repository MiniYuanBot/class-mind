"""ClassMind 数据模型（Data Models）

集中定义流水线各阶段（P1-P7）之间传递的结构化对象：
  - course_meta / file_manifest / course_type        (P1)
  - slides_md / slide_assets / slide_index            (P2)
  - transcript_clean / highlights / topic_segments    (P3)
  - aligned_chunks / alignment_map / unaligned        (P4)
  - plan / sections（LLM 写作产物）                     (P6)
  - 最终笔记 / meta 产物                                (P7)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------
class CourseType(str, Enum):
    """课程类型（P1 识别 / P5 路由）。"""

    THEORY = "theory"        # 理论课
    LAB = "lab"              # 实验课
    TUTORIAL = "tutorial"    # 习题课
    SEMINAR = "seminar"      # 研讨课

    @property
    def label_cn(self) -> str:
        return {
            CourseType.THEORY: "理论课",
            CourseType.LAB: "实验课",
            CourseType.TUTORIAL: "习题课",
            CourseType.SEMINAR: "研讨课",
        }[self]

    @classmethod
    def parse(cls, value: Optional[str]) -> "Optional[CourseType]":
        if not value:
            return None
        v = str(value).strip().lower()
        alias = {
            "theory": cls.THEORY, "theoretical": cls.THEORY, "理论": cls.THEORY, "理论课": cls.THEORY,
            "lab": cls.LAB, "experiment": cls.LAB, "实验": cls.LAB, "实验课": cls.LAB,
            "tutorial": cls.TUTORIAL, "exercise": cls.TUTORIAL, "习题": cls.TUTORIAL, "习题课": cls.TUTORIAL,
            "seminar": cls.SEMINAR, "研讨": cls.SEMINAR, "研讨课": cls.SEMINAR, "discussion": cls.SEMINAR,
        }
        return alias.get(v)


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# P1 输入网关产物
# ---------------------------------------------------------------------------
@dataclass
class CourseMeta:
    """course_meta：课程名称、教师、章节/课时编号、学科领域、课程类型。"""

    course_name: str = "未命名课程"
    instructor: str = ""
    chapter_no: str = ""            # 章节 / 课时编号
    chapter_title: str = ""
    subject: str = ""               # 学科领域（数学/计算机/…）
    course_type: CourseType = CourseType.THEORY
    source: str = ""                # 元数据来源（meta 文件 / 文件名启发 / CLI）
    course_code: str = ""           # 课程代码（如 CS162），用于英文文件名
    lecture_date: str = ""          # 上课日期（可选，显示在笔记头部）
    file_stem: str = ""             # 输出文件名主干（如 cs162-lecture2-notes）；优先于启发

    def display_title(self) -> str:
        chapter = self.chapter_title or self.chapter_no
        if chapter:
            return f"{self.course_name} - {chapter}"
        return self.course_name


# ---------------------------------------------------------------------------
# P2 课件解析产物
# ---------------------------------------------------------------------------
@dataclass
class Slide:
    """单页课件。"""

    index: int                       # 页序号（1 起）
    title: str                       # 页面大标题
    body_md: str = ""                # 页面正文 Markdown（不含标题行）
    raw_text: str = ""               # 纯文本（用于对齐与关键词）
    image_count: int = 0
    table_count: int = 0
    source_name: str = ""            # 来源文件
    source_page: int = 1             # PDF/PPT 原始页号
    notes: str = ""                  # PPT 备注 / PDF 页注释（可选）

    @property
    def markdown(self) -> str:
        """页级 Markdown（带页面锚点注释）。"""
        header = f'<!-- slide: id={self.index}, title="{self.title}" -->'
        title = f"## {self.title}" if self.title else f"## 第 {self.index} 页"
        body = self.body_md.strip()
        return f"{header}\n{title}\n\n{body}" if body else f"{header}\n{title}"


@dataclass
class SlideAsset:
    """从课件中提取的独立资源（图片/截图/板书照片）。"""

    slide_id: int
    path: Path
    kind: str = "image"              # image / table / board
    description: str = ""            # 后续由 AI/规则生成


@dataclass
class SlideIndexEntry:
    """slide_index：页码 ↔ 标题 ↔ 核心关键词。"""

    page: int
    title: str
    keywords: list


@dataclass
class ParsedSlides:
    slides_md: str = ""              # 按页组织的完整 Markdown
    slides: list = field(default_factory=list)          # list[Slide]
    assets: list = field(default_factory=list)          # list[SlideAsset]
    index: list = field(default_factory=list)           # list[SlideIndexEntry]
    warnings: list = field(default_factory=list)
    source_file: str = ""


# ---------------------------------------------------------------------------
# P3 讲述处理产物
# ---------------------------------------------------------------------------
@dataclass
class Highlight:
    """重点片段（含时间戳与原文引用）。"""

    text: str
    triggers: list = field(default_factory=list)   # 命中的强调信号
    label: str = "重点"                            # 重点 / 易错点
    timestamp: Optional[str] = None
    line_no: int = 0


@dataclass
class TopicSegment:
    """话题分段：标记每段讲述的主题关键词。"""

    index: int
    keywords: list = field(default_factory=list)
    text: str = ""
    timestamp_start: Optional[str] = None
    timestamp_end: Optional[str] = None


@dataclass
class ProcessedTranscript:
    clean_md: str = ""               # 去噪讲述 Markdown（含时间戳锚点/引用块）
    clean_text: str = ""             # 去噪纯文本
    highlights: list = field(default_factory=list)    # list[Highlight]
    topic_segments: list = field(default_factory=list)  # list[TopicSegment]
    warnings: list = field(default_factory=list)
    source_file: str = ""

    def text_for_alignment(self) -> str:
        """供对齐层使用的纯文本（含行号占位无所谓）。"""
        return self.clean_text


# ---------------------------------------------------------------------------
# P4 对齐产物
# ---------------------------------------------------------------------------
@dataclass
class AlignedChunk:
    """对齐后的融合文本块：slide_id + transcript_seg + 讲述原文。"""

    slide_id: int
    transcript_seg: int              # topic_segments 下标（0 起）
    confidence: Confidence
    slide_title: str = ""
    transcript_text: str = ""        # 对应讲述片段（原文引用，下游写作素材源）
    signals: list = field(default_factory=list)  # 命中的对齐信号


@dataclass
class AlignmentRecord:
    slide_id: int
    slide_title: str
    seg_index: int
    confidence: str
    signals: list = field(default_factory=list)


@dataclass
class AlignmentResult:
    chunks: list = field(default_factory=list)      # list[AlignedChunk]
    records: list = field(default_factory=list)     # list[AlignmentRecord]
    unaligned_segments: list = field(default_factory=list)  # list[dict]
    coverage: float = 0.0            # 讲述覆盖度 0..1
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# P6 笔记产物
# ---------------------------------------------------------------------------
@dataclass
class NoteProduct:
    """LLM 写作链产物（plan 计划 + 逐节精写 markdown + 头部块）。"""

    course_title: str = ""
    engine: str = ""                   # llm:<model>
    mode: str = "layered_md"           # 唯一模式（兼容保留）
    layers: dict = field(default_factory=dict)        # {plan|section_NN|polish: markdown}
    doc_header: str = ""               # 最终笔记头部块（标题 + 课程信息行）
    qa_warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# 通用
# ---------------------------------------------------------------------------
def to_jsonable(obj: Any) -> Any:
    """递归把 dataclass / Enum / Path 转为可 JSON 序列化的结构。"""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value if not isinstance(obj.value, str) else obj.value
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "__dataclass_fields__"):
        return to_jsonable(asdict(obj))
    return str(obj)


def dump_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
