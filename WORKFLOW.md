# WORKFLOW — ClassMind 端到端流水线（阶段详解 / 质量契约 / 产物）

> Goal: lecture package (slides/handout + transcript) → one structured Chinese Markdown
> course note under `output/`, plus machine-readable metadata. Pure-LLM (no offline engine);
> text API key required; vision API optional for slide-image captions.

## 一、一键指令

```bash
classmind generate input output          # zero-config P1..P7 (+ P2.5 vision captions, optional)
classmind demo --run                    # sample package + end-to-end run
```

## 二、阶段详解

| 阶段 | 模块 | 产物 |
| :--- | :--- | :--- |
| P1 输入网关 | `gateway/input_gateway` | `Manifest`（course_meta 三源合并：CLI > meta.json > 文件名启发） |
| P2 课件转 MD | `parsing/slide_parser`（pdf/pptx） | `ParsedSlides`（分页 MD + 图资源 + 索引） |
| P2.5 视觉图注 | `vision/captioner`（Kimi，可选） | 图 → 中文语义图注并入页面素材 |
| P2.6 skills 富集 | `pipeline._enrich_from_skills`（hook=enrich 的 tool 技能，可选） | 素材图/图注按 `figure_index.json` 并入对应页 |
| P3 讲稿处理 | `parsing/transcript_processor` | 去噪 MD/文本、重点、话题分段 |
| P4 对齐 | `alignment/aligner` | 页↔讲述对齐 + 覆盖率（对齐块是写作素材源） |
| P5 提示词编排 | `prompts/orchestrator`（catalog + templates + references） | 每阶段完整提示词（`{{var}}` 填充） |
| P6 笔记核心 | `core/llm_builder`：Plan(L1 JSON) → 分批 Draft(L2) → 可选 Polish(L3) | `NoteProduct.layers{plan, section_*, polish}` |
| P7 生成 | `generator/note_generator` | `output/<stem>.md` + `assets/` + `meta/` |
| QA | `quality/checks` + 可选 `quality/fixer`（--fix-rounds N） | `meta/qa_report.json`（+修订后的成稿） |

## 三、产物契约

```
output/
├── <english-stem>.md       # 唯一交付（中文内容）；命名：file_stem → course_code+chapter → ASCII 回退
├── assets/                 # 讲义提取图（+ vision 图注用）
└── meta/
    ├── course_outline.json   # 结构计划（标题 + 章节 + 页码覆盖）
    ├── alignment_map.json    # 页↔讲述对齐 + 覆盖率
    ├── highlights.json       # 教师重点
    └── qa_report.json        # QA 检查（COVERAGE/FIGURE/HEADINGS/SCAFFOLD/…）

# 中间文件（与 paper-mind 同构；可再生产物，不入 git）
work/
├── run/<stem>/             # 本次运行：run_state/manifest、slides.md、transcript、
│                           #   highlights/alignment.json、plan.json、draft/section_XX.md、note_draft.md
└── curated/<stem>/         # 成功后的可复用快照（slides/transcript/alignment/plan/course_meta）
```
`classmind cleanup` 清除 work/run（保留 curated 与 output/）；`classmind report` 查看状态。

## 四、质量契约

- QA 只落 `meta/qa_report.json`，正文保持成品形态；`SCAFFOLD` 检查防止中间产物泄漏；
- 机器可修问题（HEADINGS/MATH/CODEBLOCK/SCAFFOLD/CONSISTENCY）可用 `--fix-rounds N` 回喂修订
  （L4 QA-Fix 阶段，有界轮数 + 截断/过短护栏）；
- 覆盖度/图表类为 WARN 提示；人工通读重点：无孤立术语、公式都有符号说明、能讲清本讲主线。

## 五、Skills（可插拔）

- 仓库根 `skills/<name>/SKILL.md`：prompt 型注入提示词（按 stages 过滤），tool 型在
  `hook` 对应阶段执行（P2.6 enrich），失败优雅降级；详见 `skills/README.md`；
- 查看：`classmind skills list|show <name>`。

## 六、布局契约（与 paper-mind 镜像，见 docs/ARCHITECTURE.md）

| 路径 | 角色 |
| :--- | :--- |
| `input/` | 课件/讲稿 + 可选 `skills/` + `meta.json`（gitignore 除外） |
| `output/` | note + `assets/` + `meta/`（gitignore） |
| `prompts/` | catalog.json + templates/ + references/（Prompt-as-Product） |
| `config/` | `.env(.example)`（密钥，与 paper-mind 同一套 `DEEPSEEK_*`/`KIMI_*` 规范） |
| `classmind/` | Python 包（gateway/parsing/alignment/vision/prompts/core/generator/quality + cli/pipeline/models/skills/…） |
| `skills/` | 可插拔技能 |
| `tests/` | unittest（进程内 Fake LLM，无网络） |
