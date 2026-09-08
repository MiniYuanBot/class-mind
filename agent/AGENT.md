# ClassMind Agent Definition (AGENT.md)

> 定义 "ClassMind 课程笔记 Agent"：输入一个课堂包（讲义 slides/handout + 课堂讲稿 transcript），
> 输出**一篇**结构化中文 Markdown 课程笔记 + 机器可读元数据。
> 依据：`prompts/catalog.json`（阶段/类型/模板声明）· `prompts/templates/` · `prompts/references/`
> · `skills/`（可插拔技能）· `input/meta.json`（课程元数据）。端到端指令见 README/WORKFLOW。

## 1. 一句话

ClassMind 是端到端课堂笔记生成器：`课件/讲义 + 课堂讲稿 → 页↔讲述对齐 → Plan→Draft
（中文系统化笔记）→ 单文件交付`。核心是 **Prompt-as-Product**（catalog.json + templates 驱动，
代码只编排与质检）+ **纯 LLM**（确定性引擎已移除）。

## 2. 能力边界与通道

- **文字 LLM（DeepSeek / OpenAI 兼容，必需）**：P6 Plan(L1 JSON 大纲) → 分批 Draft(L2 精写) →
  可选 Polish(L3 审校)；QA 修订闭环（L4 QA-Fix，`--fix-rounds N`）经 `classmind/core/llm.py` 调用。
- **视觉图注（Kimi / 多模态端点，可选）**：P2.5 为讲义每张图生成中文语义描述并入写作素材
  （`classmind/vision/captioner.py`）；未配 Key 自动跳过。
- **Skills（可插拔）**：prompt 型（写作要求，注入提示词，按 stages 过滤）；tool 型（P2.6 素材
  富集 hook=enrich，执行 entry，失败优雅降级）——详见 `skills/README.md`。
- **本地加工**：pdf/pptx → 分页 MD + 图资源；docx/txt/md 讲稿去噪、分段、抽取重点；页↔讲述对齐。

## 3. 阶段编排与产物

| 阶段 | 模块 | 产物 |
| :--- | :--- | :--- |
| P1 | gateway/input_gateway | Manifest + CourseMeta（CLI > meta.json > 文件名启发） |
| P2/P2.5/P2.6 | parsing/slide_parser + vision/captioner + skills enrich | 分页素材（含图注）；可选富集 |
| P3 | parsing/transcript_processor | 干净讲稿 + 重点 + 话题分段 |
| P4 | alignment/aligner | 页↔讲述对齐 + 覆盖率 |
| P5 | prompts/orchestrator | 按阶段渲染提示词（catalog + {{var}}） |
| P6 | core/note_core + core/llm_builder | NoteProduct.layers（plan/section_*/polish） |
| P7 | generator/note_generator | `output/<stem>.md` + assets/ + meta/ |
| QA | quality/checks + quality/fixer | meta/qa_report.json；ERROR 可回喂修订 |

## 4. 笔记质量契约

- 结构由 L1 Plan 决定（教学顺序分节，覆盖全部讲义页），非页序罗列；正文无脚手架痕迹；
- 每节：定义/动机/直觉优先，公式带符号说明，教师强调/易错点入正文，小节以高质量 Q&A 收束；
- 语言：最终笔记为中文（英文术语首次括注、全文统一）；缺失信息标 `[材料未明确]`；
- 图：先语义描述再讲结论；QA FIGURE 项核对图完整性；
- 机器检查落 `meta/qa_report.json`，人工通读确认“老师重新讲清这一课”。

## 5. 交付（本仓库）

- pip 包：`pyproject.toml` + console entry `classmind`；`input/`（除 meta.json 样例）与
  `output/` 均 gitignore；仓库根 `prompts/` 是 Prompt-as-Product 资产（可 --prompt-dir 覆盖）。
- 与论文笔记兄弟仓库 paper-mind 镜像同一参考架构，差异见 `docs/ARCHITECTURE.md` §8。
