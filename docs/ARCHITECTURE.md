# 统一参考架构（ClassMind × PaperMind 镜像）

> 本文件在两个仓库（`class-mind/` 与 `paper-mind/`）各存一份、内容保持一致，是两库
> "镜像同一套参考结构"的权威说明。两库目标相似：**一份多模态输入 → 一篇中文教学式
> Markdown 笔记**，纯 LLM 驱动、Prompt-as-Product、诚实溯源、可插拔 skills。
> 差异只在输入侧与素材侧：class-mind 处理**课件/讲义 + 课堂讲稿**（含 页面↔讲述 对齐），
> paper-mind 处理**论文 PDF**（含图裁剪与视觉核读）。

## 0. 一致性承诺

- 顶层目录契约、阶段命名、产物 JSON、提示词组织、skills 规范在两库**同名同构**；
- 领域差异点集中在本文件 §8 与各库 README，禁止在代码/提示词层另起炉灶；
- 两库共用一套测试约定（unittest、工作区内临时目录）。

## 1. 顶层布局契约（两库一致）

```
<repo>/                       # class-mind | paper-mind（各自独立 git 仓库）
├── README.md                 # 使用指南 + 目录 + 设计原则
├── WORKFLOW.md               # 阶段详解 + 质量契约
├── docs/ARCHITECTURE.md      # 本文件（镜像）
├── agent/AGENT.md            # Agent 定义（能力/通道/阶段/交付）
├── input/                    # ★ 用户材料（gitignore；约定保留 meta 样例等）
├── output/                   # ★ 单一交付：<stem>_note.md + assets/ + meta/（gitignore）
├── work/                     # 中间件（gitignore）：curated/（可复用缓存）与 run/（临时）
├── prompts/                  # Prompt-as-Product
│   ├── catalog.json          #   阶段声明（层号/标签/模板/描述）
│   ├── templates/            #   universal_*、layer_l{1..4}_*、领域/视觉/材料模板
│   └── references/           #   markdown.md / pseudocode.md / （骨架规范，领域相关）
├── config/
│   ├── *.json                #   领域骨架（机器可读，驱动分节写作）+ 类型路由
│   └── .env.example          #   Key 模板：两库统一 config/.env + DEEPSEEK_*/KIMI_* 规范变量
├── skills/                   # ★ 可插拔技能（SKILL.md + 可选脚本），见 skills/README.md
├── <pkg>/                    # classmind/ | papermind/：代码包（模块树一致，见 §7）
├── tests/                    # unittest（纯逻辑为主；端到端用进程内 Fake LLM）
└── pyproject.toml / .gitignore / .env(.example)
```

产物与中间件约定：

| 概念 | 约定 |
| :--- | :--- |
| 最终交付 | `output/<stem>_note.md`（唯一 .md 交付物；class-mind 的 stem 来自课程元数据） |
| 图资源 | `output/assets/`（最终笔记引用的图；相对引用 `assets/…`） |
| 机器可读元数据 | `output/meta/{qa_report.json, outline.json, <领域>…json}` |
| 复用缓存 | `work/curated/<stem>/`（解析/素材/视觉缓存，版本头失效重建） |
| 本次运行临时 | `work/run/<stem>/`（cleanup 删除） |

## 2. 阶段表（P1..P7 映射）

| 阶段 | class-mind（课程笔记） | paper-mind（论文笔记） | 说明 |
| :--- | :--- | :--- | :--- |
| P1 输入网关 | `gateway/input_gateway`：扫描课件/讲稿 + meta.json 三源合并 | `gateway/input_gateway`：定位 PDF + pdfinfo 元数据 | 输入材料契约 |
| P2 素材转 MD | `parsing/slide_parser`（pdf/pptx→分页 MD + 图资源） | `parsing/pdf2md`（pdf→MD 基线） | 文本/素材层 |
| P2.5 视觉补充 | `vision/captioner`（图→语义图注，可选）＋ P2.6 skills 富集 | `vision/cropper`（确定性裁剪；可被 skills tool 替换） | 图处理 |
| P3 素材处理 | `parsing/transcript_processor`（去噪/分段/重点） | `parsing/chunker`（语义分块，read 按节消费） | 材料加工 |
| P4 对齐/路由 | `alignment/aligner`（页↔讲述 对齐 + 覆盖率） | `config/routing.json`（类型→focus/domain） | 关联与路由 |
| P5 提示词编排 | `prompts/orchestrator`（catalog + {{var}} 渲染） | `prompts/orchestrator`（catalog + 资产装载） | Prompt-as-Product |
| P6 笔记核心 | `core/llm_builder`：Plan→Draft(+Polish)；prompt 型 skills 按阶段注入 | `core/note_builder`：L1→图筛选→视觉→分节→QA 修订 | LLM 写作链 |
| P7 笔记生成 | `generator/note_generator`（组装/命名/meta 落盘） | `generator/note_generator`（组装/嵌图/meta 落盘） | 交付物 |
| QA | `quality/checks`（报告 meta/qa_report.json） | `quality/checks`（ERROR 回喂修订闭环） | 机器质检 |

## 3. 命令表（同名命令族）

| 命令 | class-mind | paper-mind | 说明 |
| :--- | :--- | :--- | :--- |
| 端到端 | `classmind generate <in> <out>` | `papermind generate/e2e [pdf]` | 一键出笔记 |
| 准备/解析 | `classmind demo`（样例包）等 | `papermind prepare` / `figures` | 分步（paper-mind 细分步） |
| QA | `--fix-rounds N`（生成期修订） | `papermind check`（+ 生成期修订） | 机器质检/修订 |
| 查看 | `classmind prompts list/show`、`skills list/show`、`version` | `papermind prompts/skills/report/keys/version` | 透明化 |
| 清理 | 输出目录可安全删除（可再生） | `papermind cleanup` | 中间件清理 |

## 4. 提示词组织（两库同构）

- `prompts/catalog.json`：`version / stages{layer,label,template,description} / references / universal`；
- `prompts/templates/`：`universal_role|input|output|hallucination`（或 `universal_constraints`）、
  `layer_l{1..4}_*`（plan/draft/polish/fix 或 abstract/deep/critical）、领域模板（`domain_*`）、
  视觉/材料模板（figure/transcript 处理）；
- `prompts/references/`：`markdown.md`（笔记格式规范）、`pseudocode.md`（伪代码风格）——
  两库同一语义规范（历史上互为中英译版，结构以本仓库为准，防止再次漂移）；
- 写作骨架：代码**不硬编码分节**——由 `config/note_structure.json`（paper-mind）或
  `prompts/catalog.json` stages（class-mind）等机器文件驱动；
- 可覆盖：`--prompt-dir`（class-mind）等效机制（paper-mind：`PAPERMIND_PROMPT_DIR`）。

## 5. skills 规范（两库一致，见各库 skills/README.md）

- 目录：仓库根 `skills/<name>/SKILL.md`（tool 型必须在此）；另支持 `--skills`/环境变量/`input/skills/`；
- SKILL.md：`---` front matter（`name/kind[prompt|tool]/description/stages/hook/entry`）+ 正文；
- prompt 型：正文按"用户技能与补充要求（优先级最高）"注入对应写作阶段提示词；
- tool 型：在 `hook` 对应阶段执行 `entry`（相对技能目录），失败优雅回退内置实现；
- CLI：`skills list|show <name>` 两库均有。

## 6. 质量契约与诚实原则

- 机检：标题层级、占位/禁语、搬运性独立章节、Q&A/公式/表格/术语等廉价代理指标 →
  结构化报告 `output/meta/qa_report.json`；ERROR 回喂 LLM 修订（有界轮数）；
- 诚实：数字结论必须溯源（论文 `[Sec x]`；课堂"材料未明确"标注）；图内容不臆造；
  无视觉通道时仅图注级/占位级描述；
- 成品正文不含中间产物痕迹（页码/标签/时间戳/对话原文），溯源信息留在 meta/。

## 7. 代码包模块树（镜像）

```
<pkg>/  (classmind | papermind)
├── cli.py  pipeline.py  models.py  skills.py  util.py  envfile.py  errors.py
├── gateway/   输入网关（P1）
├── parsing/   素材转 MD / 材料处理（P2/P3）
├── alignment/ 对齐（class-mind 专有）
├── vision/    视觉（P2.5）
├── prompts/   orchestrator（P5，资产装载）
├── core/      llm 客户端 + 笔记写作链（P6）
├── generator/ 笔记生成 + meta 落盘（P7）
└── quality/   机器质检（QA）
```

## 8. 领域差异清单（有意保留，不做强制抹平）

| 维度 | class-mind | paper-mind |
| :--- | :--- | :--- |
| 输入 | 课件(pdf/pptx)+讲稿(docx/txt)+meta.json | 单篇论文 PDF |
| 素材侧 | 页面↔讲述对齐、话题分段、重点抽取 | 语义分块、图裁剪、图注筛选 |
| 视觉用途 | 讲义图→中文语义图注（进入写作素材） | 论文图→『图 N 视觉核实』块（嵌入最终笔记） |
| LLM 链 | Plan(JSON 大纲)→Draft→可选 Polish | L1 摘要→6 分节（config 驱动）→QA 修订 |
| 命名 | 课程英文文件名（file_stem 优先） | `<stem>_note.md`（stem 来自 PDF 名） |
| QA 修订 | `--fix-rounds`（QA-Fix 阶段） | 修订轮数参数（默认 1） |

> 两库改动请同步更新本文件与各自 README/WORKFLOW/AGENT；共享规范文件（markdown.md /
> pseudocode.md 语义）如需演进，先在 class-mind 修订并翻译回 paper-mind 或反之，保持语义一致。
