"""ClassMind CLI.

Usage:
  classmind generate <input_dir> <output_dir> [options]    # zero-config note generation
  classmind demo [--input-dir ...] [--output-dir ...]      # build sample input, optionally run
  classmind prompts list                                   # list prompt stages (Prompt Transparency)
  classmind prompts show <stage> [--type theory]           # print a rendered prompt
  classmind version                                        # version info
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from classmind import __version__
from classmind.core.llm import LLMClient, env_or
from classmind.models import CourseMeta, CourseType
from classmind.prompts.orchestrator import PromptOrchestrator


def _vision_key_set() -> bool:
    """视觉通道是否已配置 Key（KIMI_API_KEY 或兼容别名 CLASSMIND_VISION_API_KEY）。"""
    return bool(env_or("KIMI_API_KEY", "CLASSMIND_VISION_API_KEY"))


def main(argv: list | None = None) -> int:
    # 装载密钥：仓库根 config/.env（统一布局）→ 旧根 .env / cwd .env；真实环境变量优先
    from classmind.envfile import load as load_envfile

    load_envfile()
    _ensure_utf8()
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.cmd == "generate":
            return _cmd_generate(args)
        if args.cmd == "demo":
            return _cmd_demo(args)
        if args.cmd == "prompts":
            return _cmd_prompts(args)
        if args.cmd == "skills":
            return _cmd_skills(args)
        if args.cmd == "cleanup":
            return _cmd_cleanup(args)
        if args.cmd == "report":
            return _cmd_report(args)
        if args.cmd == "version":
            print(f"classmind {__version__}")
            return 0
        parser.print_help()
        return 1
    except KeyboardInterrupt:
        print("\n[interrupted] cancelled by user.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="classmind",
        description="ClassMind - turn slides + lecture transcript into structured Markdown course notes",
    )
    sub = parser.add_subparsers(dest="cmd")

    g = sub.add_parser("generate", help="generate course notes from input/ into output/ (P1-P7)")
    g.add_argument("input_dir", type=Path, help="input directory (slides .pdf/.pptx, transcript .docx/.txt/.md, optional meta.json)")
    g.add_argument("output_dir", type=Path, help="output directory (note .md + assets/ + meta/)")
    g.add_argument("--course-name", help="course name (overrides auto-detection)")
    g.add_argument("--instructor", help="instructor name")
    g.add_argument("--chapter-no", help="chapter / lecture number")
    g.add_argument("--chapter-title", help="chapter title")
    g.add_argument("--subject", help="subject area (e.g. operating systems, mathematics)")
    g.add_argument("--course-code", help="course code for the output file name (e.g. cs162)")
    g.add_argument("--lecture-date", help="lecture date shown in the note header (e.g. 2026-09-01)")
    g.add_argument("--file-stem", help="output note file stem, e.g. cs162-lecture2-notes (overrides auto naming)")
    g.add_argument("--type", dest="course_type", choices=[t.value for t in CourseType],
                   help="course type: theory / lab / tutorial / seminar")
    g.add_argument("--api-key", help="LLM API key (or env DEEPSEEK_API_KEY / repo-root config/.env)")
    g.add_argument("--base-url", help="LLM endpoint (default https://api.deepseek.com)")
    g.add_argument("--model", help="LLM model (default deepseek-chat)")
    g.add_argument("--vision-key", help="Vision API key for slide-image captions, e.g. Kimi (or env KIMI_API_KEY)")
    g.add_argument("--vision-base-url", help="Vision endpoint (default https://api.moonshot.cn/v1)")
    g.add_argument("--vision-model", help="Vision model (default kimi-k3, Moonshot /v1 endpoint)")
    g.add_argument("--skills", type=Path,
                   help="extra skill/requirements file or directory (or env CLASSMIND_SKILLS / input/skills/*.md)")
    g.add_argument("--prompt-dir", type=Path, help="custom prompt template directory (overrides built-in templates)")
    g.add_argument("--coverage-threshold", type=float, default=0.7, help="transcript coverage warning threshold (default 0.7)")
    g.add_argument("--fix-rounds", type=int, default=0,
                   help="QA revision loop: after assembly, feed machine-fixable QA issues back to the LLM up to N rounds (default 0 = off)")
    g.add_argument("--work-dir", type=Path, default=None,
                   help="intermediate dir root (run/ + curated/; default <output 父目录>/work or env CLASSMIND_WORK_DIR)")
    g.add_argument("--verbose", "-v", action="store_true", help="print more intermediate information")

    d = sub.add_parser("demo", help="generate a sample course package (optionally run the pipeline)")
    d.add_argument("--input-dir", type=Path, default=Path("input-sample"))
    d.add_argument("--output-dir", type=Path, default=Path("output-sample"))
    d.add_argument("--run", action="store_true", help="run LLM generation right after creating the sample package")
    d.add_argument("--work-dir", type=Path, default=None, help="intermediate dir root (default <output 父目录>/work)")
    d.add_argument("--verbose", "-v", action="store_true")

    w = sub.add_parser("cleanup", help="remove work/run intermediates (keep curated/ and output/)")
    w.add_argument("--output-dir", type=Path, default=Path("output"), help="derive default work dir from this output dir")
    w.add_argument("--work-dir", type=Path, default=None, help="intermediate dir root (default <output 父目录>/work)")

    r = sub.add_parser("report", help="show input/output/work state")
    r.add_argument("--input-dir", type=Path, default=Path("input"))
    r.add_argument("--output-dir", type=Path, default=Path("output"))
    r.add_argument("--work-dir", type=Path, default=None, help="intermediate dir root (default <output 父目录>/work)")

    p = sub.add_parser("prompts", help="prompt catalog / preview (Prompt Transparency)")
    p.add_argument("action", choices=["list", "show"])
    p.add_argument("stage", nargs="?", help="stage: plan / draft / polish / fix")
    p.add_argument("--type", dest="course_type", default="theory", help="course type")
    p.add_argument("--prompt-dir", type=Path, help="custom prompt template directory")

    s = sub.add_parser("skills", help="skill registry (list / show, kinds: prompt & tool)")
    s.add_argument("action", choices=["list", "show"])
    s.add_argument("name", nargs="?", help="skill name (for 'show')")
    s.add_argument("--skills", type=Path, help="extra skill file/dir (same as generate --skills)")

    sub.add_parser("version", help="show version")
    return parser


# ---------------------------------------------------------------------------
def _cmd_generate(args) -> int:
    from classmind.pipeline import Pipeline

    overrides = {
        "course_name": args.course_name,
        "instructor": args.instructor,
        "chapter_no": args.chapter_no,
        "chapter_title": args.chapter_title,
        "subject": args.subject,
        "course_type": args.course_type,
        "course_code": args.course_code,
        "lecture_date": args.lecture_date,
        "file_stem": args.file_stem,
    }
    overrides = {k: v for k, v in overrides.items() if v is not None}

    llm_client = LLMClient(api_key=args.api_key, base_url=args.base_url, model=args.model)
    # 视觉图注：显式给出 --vision-key 或已配置 KIMI_API_KEY 时启用
    captioner = None
    if args.vision_key or _vision_key_set():
        from classmind.vision.captioner import ImageCaptioner

        captioner = ImageCaptioner(
            api_key=args.vision_key,
            base_url=args.vision_base_url,
            model=args.vision_model,
        )

    pipeline = Pipeline(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        overrides=overrides,
        llm_client=llm_client,
        prompt_dir=args.prompt_dir,
        coverage_threshold=args.coverage_threshold,
        verbose=args.verbose,
        captioner=captioner,
        skills=args.skills,
        fix_rounds=args.fix_rounds,
        work_dir=args.work_dir,
    )
    result = pipeline.run()
    _print_summary(result, args)
    return 0


def _cmd_demo(args) -> int:
    from classmind import demo as demo_mod

    print(f"[demo] writing sample input -> {args.input_dir}")
    demo_mod.generate_demo_input(args.input_dir)
    if not args.run:
        print("[demo] sample package ready. Run 'classmind generate' on it, or add --run to go end-to-end.")
        return 0
    from classmind.core.llm import LLMClient
    from classmind.pipeline import Pipeline
    from classmind.vision.captioner import ImageCaptioner

    captioner = ImageCaptioner() if _vision_key_set() else None
    pipeline = Pipeline(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        llm_client=LLMClient(),
        captioner=captioner,
        coverage_threshold=0.7,
        verbose=args.verbose,
        work_dir=args.work_dir,
    )
    result = pipeline.run()
    _print_summary(result, args)
    return 0


def _cmd_cleanup(args) -> int:
    from classmind import workdir as wd
    from classmind.pipeline import Pipeline

    work_dir = Path(args.work_dir) if args.work_dir else wd.default_work_dir(args.output_dir)
    Pipeline(input_dir=args.output_dir, output_dir=args.output_dir, work_dir=work_dir).cleanup()
    return 0


def _cmd_report(args) -> int:
    from classmind import workdir as wd
    from classmind.pipeline import Pipeline

    work_dir = Path(args.work_dir) if args.work_dir else wd.default_work_dir(args.output_dir)
    Pipeline(input_dir=args.input_dir, output_dir=args.output_dir, work_dir=work_dir).report()
    return 0


def _cmd_skills(args) -> int:
    """skill 注册表查看：list / show <name>。"""
    from classmind.skills import find_repo_root, load_skills

    skills = load_skills(args.skills, repo_root=find_repo_root())
    if args.action == "list":
        if not skills:
            print("(no skills found — add SKILL.md under repo-root skills/ or pass --skills)")
            return 0
        for sk in skills:
            extra = ""
            if sk.kind == "tool":
                extra = f"  hook={sk.hook or '-'}  entry={sk.entry or '-'}"
            elif sk.stages:
                extra = f"  stages={','.join(sk.stages)}"
            print(f"[{sk.kind}] {sk.name}{extra}")
            if sk.description:
                print(f"      {sk.description}")
            print(f"      source: {sk.source}")
        return 0
    # show
    if not args.name:
        print("[error] 'skills show' requires a skill name", file=sys.stderr)
        return 1
    sk = next((s for s in skills if s.name == args.name), None)
    if sk is None:
        print(f"[error] skill not found: {args.name}", file=sys.stderr)
        return 1
    print(f"== {sk.name}  [{sk.kind}] ==")
    if sk.description:
        print(f"description: {sk.description}")
    print(f"source: {sk.source}")
    print("---")
    print(sk.body)
    return 0


def _cmd_prompts(args) -> int:
    orchestrator = PromptOrchestrator(args.prompt_dir) if args.prompt_dir else PromptOrchestrator()
    catalog = orchestrator.catalog
    if args.action == "list":
        print(f"ClassMind prompt catalog version: {catalog.get('version')}")
        print(f"template directory: {orchestrator.template_dir}")
        types_str = ", ".join(f"{k}({v['label']})" for k, v in catalog["course_types"].items())
        print(f"course types: {types_str}")
        print("\nlayered prompt stages:")
        print(orchestrator.describe())
        return 0
    if args.action == "show":
        if not args.stage:
            print("[error] 'prompts show' requires a stage (plan/draft/polish)", file=sys.stderr)
            return 1
        meta = CourseMeta(
            course_name="Example Course",
            chapter_title="Example Chapter",
            subject="Machine Learning",
            course_type=CourseType.parse(args.course_type) or CourseType.THEORY,
        )
        print(orchestrator.render(args.stage, meta))
        return 0
    return 1


# ---------------------------------------------------------------------------
def _print_summary(result, args) -> None:
    m = result.manifest
    s = result.slides
    t = result.transcript
    a = result.alignment
    p = result.product
    out = result.outputs

    print("\n===== ClassMind run report =====")
    print(f"course: {m.course_meta.course_name}   type: {m.course_meta.course_type.value}"
          + (f"   instructor: {m.course_meta.instructor}" if m.course_meta.instructor else ""))
    if m.course_meta.chapter_title or m.course_meta.chapter_no:
        print(f"chapter: {m.course_meta.chapter_no} {m.course_meta.chapter_title}".rstrip())

    print("\n[P1] input manifest")
    print(f"  - slides: {len(m.slides)}, transcripts: {len(m.transcripts)}, images: {len(m.assets)}")
    for q in m.quality_issues:
        print(f"  {q}")

    print("\n[P2] slide parsing")
    print(f"  - pages: {len(s.slides)}  images: {sum(x.image_count for x in s.slides)}  tables: {sum(x.table_count for x in s.slides)}")
    preview = "、".join(f"{e.page}:{e.title[:12]}" for e in s.index[:6])
    print(f"  - page index: {preview}{'...' if len(s.index) > 6 else ''}")

    print("\n[P3] transcript processing")
    print(f"  - clean chars: {len(t.clean_text)}  topic segments: {len(t.topic_segments)}  highlights: {len(t.highlights)}")

    print("\n[P4] alignment")
    extra = f"  unaligned: {len(a.unaligned_segments)}" if a.unaligned_segments else "  unaligned: 0"
    print(f"  - aligned chunks: {len(a.chunks)}  coverage: {a.coverage:.0%}  {extra}")

    print("\n[P6] note core")
    n_sections = len([k for k in p.layers if k.startswith("section_")])
    print(f"  - engine: {p.engine}  plan→draft 节数: {n_sections}" + ("  (+polish)" if p.layers.get("polish") else ""))

    print("\n[P7] outputs")
    note = out.get("note_path")
    if note:
        print(f"  - note: {note}")
    print("  - meta: course_outline.json / alignment_map.json / highlights.json / qa_report.json")
    levels = {}
    for r in out.get("qa_report", []):
        levels[r["level"]] = levels.get(r["level"], 0) + 1
    summary = "  ".join(f"{k}:{v}" for k, v in sorted(levels.items())) or "OK:0"
    print(f"  - QA report: {summary}")
    for r in out.get("qa_report", []):
        if r["level"] != "OK":
            print(f"      [{r['code']}] {r['message']}")
    print("==============================")


def _ensure_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    raise SystemExit(main())
