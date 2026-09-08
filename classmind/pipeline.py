"""端到端流水线总控（Zero-Config Pipeline）。

串联 P1 -> P2/P3 -> P4 -> P5/P6 -> P7：
  input/  --> 解析/处理 --> 对齐 --> 提示词 --> 笔记 --> output/
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from classmind.alignment.aligner import Aligner
from classmind.core.note_core import NoteCore
from classmind.gateway.input_gateway import InputGateway, Manifest
from classmind.generator.note_generator import NoteGenerator
from classmind.models import AlignmentResult, NoteProduct, ParsedSlides, ProcessedTranscript, dump_json
from classmind.parsing.slide_parser import Slide2MDParser
from classmind.parsing.transcript_processor import TranscriptProcessor
from classmind.prompts.orchestrator import PromptOrchestrator


@dataclass
class RunResult:
    manifest: Manifest = field(default_factory=Manifest)
    slides: ParsedSlides = field(default_factory=ParsedSlides)
    transcript: ProcessedTranscript = field(default_factory=ProcessedTranscript)
    alignment: AlignmentResult = field(default_factory=AlignmentResult)
    product: NoteProduct = field(default_factory=NoteProduct)
    outputs: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


class Pipeline:
    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        overrides: dict | None = None,
        engine: str = "llm",
        llm_client=None,
        prompt_dir: Path | None = None,
        coverage_threshold: float = 0.7,
        verbose: bool = False,
        captioner=None,
        skills=None,
        fix_rounds: int = 0,
    ) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.overrides = overrides or {}
        self.engine = engine or "llm"       # 保留：legacy 参数，纯 LLM 模式固定为 llm
        self.llm_client = llm_client
        self.prompt_dir = Path(prompt_dir) if prompt_dir else None
        self.coverage_threshold = coverage_threshold
        self.verbose = verbose
        self.captioner = captioner          # 视觉图注（ImageCaptioner 或 None）
        self.skills = skills                # 技能来源（文件/目录/None）
        self.fix_rounds = int(fix_rounds or 0)   # QA 修订闭环轮数（0=关闭）
        self._skills_cache = None

    # ------------------------------------------------------------------
    def run(self) -> RunResult:
        result = RunResult()

        # ---------- P1 输入网关 ----------
        gateway = InputGateway(self.input_dir, self.overrides)
        manifest = gateway.scan()
        result.manifest = manifest
        self._log_issues(manifest.quality_issues, phase="P1 Input Gateway")
        if not manifest.has_material:
            from classmind.errors import InputError

            raise InputError("输入中没有课件或讲述文本，无法生成笔记。")

        assets_dir = self.output_dir / "assets"

        # ---------- P2 课件解析 ----------
        parser = Slide2MDParser(assets_dir)
        if manifest.slides:
            deck = parser.parse(manifest.slides[0])
            for extra in manifest.slides[1:]:
                other = parser.parse(extra)
                deck.warnings.append(
                    f"[WARN] 发现多份课件，已采用主课件《{manifest.slides[0].name}》，"
                    f"忽略《{extra.name}》（如需合并请手动拼接）"
                )
                deck.warnings.extend(other.warnings)
            result.slides = deck
            self._log_issues(deck.warnings, phase="P2 Slide2MD")
            if self.captioner is not None:
                self._caption_deck(deck, assets_dir)
            # P2.6 素材富集：仓库根 skills/ 下声明 hook=enrich 的 tool 技能
            self._enrich_from_skills(deck, assets_dir)
        else:
            result.slides = ParsedSlides()
            self._log_issues(["[WARN] 无课件，仅依据讲述生成笔记"], phase="P2 Slide2MD")

        # ---------- P3 讲述处理 ----------
        tp = TranscriptProcessor()
        if manifest.transcripts:
            processed = tp.process(manifest.transcripts[0])
            for extra in manifest.transcripts[1:]:
                other = tp.process(extra)
                processed.clean_md += "\n\n" + other.clean_md
                processed.clean_text += "\n" + other.clean_text
                processed.highlights.extend(other.highlights)
                processed.warnings.extend(other.warnings)
            result.transcript = processed
            self._log_issues(processed.warnings, phase="P3 Transcript Processor")
        else:
            result.transcript = ProcessedTranscript()

        # ---------- P4 对齐 ----------
        aligner = Aligner(coverage_threshold=self.coverage_threshold)
        alignment = aligner.align(result.slides, result.transcript)
        result.alignment = alignment
        self._log_issues(alignment.warnings, phase="P4 Alignment")

        # ---------- P5/P6 笔记核心 ----------
        meta = manifest.course_meta
        result.meta["course_meta"] = meta
        orchestrator = PromptOrchestrator(self.prompt_dir) if self.prompt_dir else PromptOrchestrator()
        skills = self._load_skills()

        core = NoteCore(meta=meta, orchestrator=orchestrator, client=self.llm_client,
                        skill_text="", skills=skills)
        product = core.build(result.slides, result.transcript, alignment)
        result.product = product

        # ---------- P7 笔记生成 ----------
        generator = NoteGenerator(self.output_dir, coverage_threshold=self.coverage_threshold)
        outputs = generator.generate(meta, product, result.slides, result.transcript, alignment)
        result.outputs = outputs

        # ---------- P7.5 质检修订闭环（--fix-rounds N） ----------
        if self.fix_rounds and self.llm_client is not None and outputs.get("note_path"):
            from classmind.quality.fixer import NoteFixer

            fixer = NoteFixer(self.llm_client, orchestrator, skills=skills)
            final_md, final_report = fixer.fix(
                meta, outputs.get("note_md", ""),
                result.slides, result.transcript, alignment, product,
                rounds=self.fix_rounds,
            )
            if final_md != outputs.get("note_md"):
                note_path = Path(outputs["note_path"])
                note_path.write_text(final_md + "\n", encoding="utf-8")
                outputs["note_md"] = final_md
                outputs["qa_report"] = final_report
                dump_json(final_report, self.output_dir / "meta" / "qa_report.json")
        return result

    # ------------------------------------------------------------------
    def _caption_deck(self, deck, assets_dir: Path) -> None:
        """P2.5 视觉图注：为有图片的页生成中文语义描述并入该页材料。"""
        from classmind.vision.captioner import caption_slide_images, find_image_refs

        done = skipped = 0
        for s in deck.slides:
            if not find_image_refs(s.body_md or ""):
                continue
            nb, nr = caption_slide_images(
                s.body_md or "",
                s.raw_text or "",
                assets_dir,
                self.captioner,
                page_title=s.title,
                page_id=s.index,
            )
            if nb != (s.body_md or ""):
                s.body_md, s.raw_text = nb, nr
                done += 1
            else:
                skipped += 1
        if done:
            print(f"  [P2 Vision] 已为 {done} 页讲义生成图片语义描述。", file=sys.stderr)
        if skipped:
            print(f"  [P2 Vision] {skipped} 页含图但未能描述（图片缺失或 API 失败）。", file=sys.stderr)

    # ------------------------------------------------------------------
    def _load_skills(self) -> list:
        """装载全部技能（来源去重）：--skills/env/input/skills + 仓库根 skills/。"""
        if self._skills_cache is not None:
            return self._skills_cache
        from classmind.skills import find_repo_root, load_skills

        self._skills_cache = load_skills(
            self.skills,
            input_dir=self.input_dir,
            repo_root=find_repo_root(),
        )
        return self._skills_cache

    # ------------------------------------------------------------------
    def _enrich_from_skills(self, deck, assets_dir: Path) -> None:
        """P2.6 素材富集：执行仓库根 skills/ 下声明 hook=enrich 的 tool 技能。

        技能约定：入口以 (input_dir, assets_dir) 为参数运行；产物写入 assets_dir。
        若额外写出 assets/figure_index.json：[{asset, page, caption}]，
        则把对应图片引用/图注行并入第 page 页讲义正文（与 P2.5 图注同构）。
        技能缺失/执行失败一律优雅降级（记录日志，不中断流水线）。
        """
        from classmind.skills import find_repo_root, load_tool_skills, run_tool_skill
        from classmind.skills import SkillError as ToolSkillError

        skills = load_tool_skills(find_repo_root(), hook="enrich")
        if not skills:
            return
        slides_by_index = {s.index: s for s in deck.slides}
        for sk in skills:
            try:
                run_tool_skill(sk, [str(self.input_dir), str(assets_dir)])
            except ToolSkillError as exc:
                print(f"  [P2.6 Skill] 技能 {sk.name} 执行失败（降级跳过）: {exc}", file=sys.stderr)
                continue
            except Exception as exc:  # noqa: BLE001
                print(f"  [P2.6 Skill] 技能 {sk.name} 异常（降级跳过）: {exc}", file=sys.stderr)
                continue
            applied = self._apply_figure_index(slides_by_index, assets_dir)
            print(f"  [P2.6 Skill] 技能 {sk.name} 完成，应用 {applied} 条图片富集。", file=sys.stderr)

    @staticmethod
    def _apply_figure_index(slides_by_index: dict, assets_dir: Path) -> int:
        idx = assets_dir / "figure_index.json"
        if not idx.exists():
            return 0
        import json as _json

        try:
            entries = _json.loads(idx.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return 0
        applied = 0
        for e in entries if isinstance(entries, list) else []:
            asset = str(e.get("asset") or "")
            page = int(e.get("page") or 0)
            slide = slides_by_index.get(page)
            if not asset or slide is None or not (assets_dir / asset).exists():
                continue
            caption = str(e.get("caption") or "").strip()
            line = f"![{asset}](assets/{asset})"
            if caption:
                line = f"**{asset}**：{caption}（资源：assets/{asset}）"
            if line not in slide.body_md:
                slide.body_md = (slide.body_md.rstrip() + "\n\n" + line).strip()
            applied += 1
        return applied

    # ------------------------------------------------------------------
    @staticmethod
    def _log_issues(issues: list, phase: str) -> None:
        for msg in issues:
            print(f"  [{phase}] {msg}", file=sys.stderr)
