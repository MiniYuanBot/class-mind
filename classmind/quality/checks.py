"""质量保障机制（LLM v2 成稿 + 对齐/覆盖）。

结果汇总为 list[dict{level, code, message}]，由 P7 落盘为 meta/qa_report.json。
检查项：讲述覆盖度、图表完整性、讲义-讲述一致性、成稿结构（标题层级/公式/脚手架残留）。
"""

from __future__ import annotations

import re

from classmind.models import AlignmentResult, NoteProduct, ParsedSlides, ProcessedTranscript


def run_qa(
    slides: ParsedSlides,
    transcript: ProcessedTranscript,
    alignment: AlignmentResult,
    product: NoteProduct,
    final_md: str,
    coverage_threshold: float = 0.7,
) -> list:
    """执行全部质量检查，返回结构化报告条目。"""
    report: list = []

    # ---- 讲述覆盖度 ----
    if alignment.coverage < coverage_threshold:
        report.append({
            "level": "WARN",
            "code": "COVERAGE",
            "message": (
                f"讲述覆盖度 {alignment.coverage:.0%} 低于阈值 {coverage_threshold:.0%}，"
                f"存在 {len(alignment.unaligned_segments)} 段未对齐讲述片段，可能为课外闲聊或设备杂音。"
            ),
        })
    else:
        report.append({
            "level": "OK",
            "code": "COVERAGE",
            "message": f"讲述覆盖度 {alignment.coverage:.0%} >= {coverage_threshold:.0%}。",
        })

    # ---- 图表完整性 ----
    total_images = sum(s.image_count for s in slides.slides)
    if total_images:
        described = sum(
            1 for s in slides.slides
            if s.image_count and (("【图】" in s.raw_text) or ("（资源：" in s.body_md))
        )
        report.append({
            "level": "WARN" if described < total_images else "OK",
            "code": "FIGURE",
            "message": (
                f"课件共提取 {total_images} 张图片；其中 {described} 页含语义图注。"
                "未配置视觉 API 时图片仅有占位说明。"
            ),
        })
    teacher_fig_refs = [
        m.group(0)
        for c in alignment.chunks
        for m in re.finditer(r"如图\s*\d*|看(?:这个)?图", c.transcript_text or "")
    ]
    if teacher_fig_refs and total_images == 0:
        report.append({
            "level": "WARN",
            "code": "FIGURE",
            "message": f"讲述中出现 {len(teacher_fig_refs)} 处“如图/看图”表述，但课件中未提取到任何图片资源，可能影响理解。",
        })

    # ---- 一致性：有内容的页未进入任意对齐块（讲述未覆盖）----
    chunk_slides = {c.slide_id for c in alignment.chunks}
    missing = [
        s.index for s in slides.slides
        if s.index not in chunk_slides and (s.raw_text.strip() or s.body_md.strip())
    ]
    if missing:
        preview = ", ".join(str(x) for x in missing[:12]) + ("…" if len(missing) > 12 else "")
        report.append({
            "level": "WARN",
            "code": "CONSISTENCY",
            "message": f"以下讲义页有内容但讲述未覆盖，未并入写作材料（可人工复核）: 第 {preview} 页。",
        })

    # ---- 溯源说明 ----
    report.append({
        "level": "OK",
        "code": "TRACE",
        "message": "溯源信息存于 meta/alignment_map.json 与 course_outline.json，笔记正文不含页码注释。",
    })

    # ---- 成稿机器检查 ----
    h2 = re.findall(r"(?m)^##\s+\S", final_md)
    if not h2:
        report.append({"level": "WARN", "code": "HEADINGS", "message": "成稿中没有二级标题（## ），结构可能缺失。"})
    else:
        report.append({"level": "OK", "code": "HEADINGS", "message": f"成稿含 {len(h2)} 个二级小节。"})
    dd = final_md.count("$$")
    if dd and dd % 2 != 0:
        report.append({"level": "WARN", "code": "MATH", "message": "公式定界符 $$ 数量为奇数，可能存在未闭合的公式块。"})
    scaffold = ("[Slide", "课件原文", "教师讲述：", "<!-- ", "```json")
    found = [s for s in scaffold if s in final_md]
    if found:
        report.append({"level": "WARN", "code": "SCAFFOLD", "message": f"成稿残留中间产物痕迹: {found}，请用 Polish 阶段清理。"})
    if "```" in final_md and final_md.count("```") % 2 != 0:
        report.append({"level": "WARN", "code": "CODEBLOCK", "message": "代码块围栏 ``` 数量为奇数，可能存在未闭合代码块。"})

    return report
