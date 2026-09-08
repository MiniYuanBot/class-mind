# Skills（可插拔技能）

ClassMind 支持把**可插拔技能**放进仓库根 `skills/<name>/`（或经 `--skills` / `input/skills/`）。
未来你想让 agent 学会一件新的事（例如“从讲义/PDF 里提取干净插图”——参见
[figure-extractor](https://github.com/Sunrich-HT/figure-extractor.git)），就新建一个技能目录，
无需改动流水线代码。

## 1. 技能 = 一个目录（SKILL.md + 可选脚本）

```
skills/<skill-name>/
├── SKILL.md        # 元数据头 + 说明/指令正文（prompt 型时注入提示词）
└── …               # 可选：脚本/资源（tool 型入口引用）
```

### 1.1 SKILL.md 格式（零依赖 front matter）

文件头用 `---` 行包裹 `key: value`（多值逗号分隔），其余为正文：

```markdown
---
name: teacher-style            # 技能名（缺省：目录名 / 文件名）
kind: prompt                   # prompt（默认，注入提示词）| tool（执行工具）
description: 本课程的笔记风格要求
stages: plan,draft,polish      # prompt 型：生效写作阶段（缺省全部）
hook: enrich                   # tool 型：流水线触发点（enrich=素材富集，缺省不自动触发）
entry: python3 extract.py      # tool 型：可执行命令（相对本目录）
---
正文：prompt 型时这段文字会按“用户技能与补充要求（优先级最高）”注入每个 LLM 提示词。
```

### 1.2 两类技能

| kind | 行为 | 典型用途 |
| :--- | :--- | :--- |
| `prompt` | 正文注入每个（对应阶段的）LLM 提示词，最高优先级 | 笔记风格/术语表/老师偏好/禁止事项 |
| `tool` | 由流水线在 `hook` 对应阶段执行 `entry`；失败自动降级跳过 | 图提取、格式转换、校对工具 |

### 1.3 来源与优先级（同名去重，先到先得）

1. 环境变量 `CLASSMIND_SKILLS` / CLI `--skills <file|dir>`；
2. 输入包内 `input/skills/*.md`（随课堂材料打包）；
3. 仓库根 `skills/<name>/SKILL.md`（自动发现；tool 型必须放这里）。

## 2. 查看与管理

```bash
classmind skills list              # 列出发现的全部技能（来源+类型+钩子）
classmind skills show <name>       # 查看某技能全文
```

`prompt` 型技能可用 `classmind prompts show plan|draft|polish|fix` 预览注入效果；
`tool` 型技能可在流水线对应阶段被调用（当前挂点：`hook: enrich`，P2.6 素材富集）。

## 3. 写一个 tool 技能（素材富集示例）

P2 讲义解析后、P4 对齐前，流水线会执行所有声明 `hook: enrich` 的 tool 技能，
参数为 `(input_dir, assets_dir)`。产物写入 `assets_dir`；若额外写出
`assets/figure_index.json`（`[{asset, page, caption}]`），流水线会把对应图片引用/图注
并入第 `page` 页讲义正文：

```python
# skills/figures/extract.py —— 入口：python3 extract.py <input_dir> <assets_dir>
import json, pathlib, sys
src, assets = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
assets.mkdir(parents=True, exist_ok=True)
# …真实提取逻辑（例如调用 figure-extractor 之类外部工具）…
(assets / "figure_index.json").write_text(
    json.dumps([{"asset": "fig1.png", "page": 3, "caption": "网络架构示意"}]), encoding="utf-8")
```

对应 `skills/figures/SKILL.md`：

```markdown
---
name: figures
kind: tool
description: 从讲义 PDF 中提取干净插图并给出图注
hook: enrich
entry: python3 extract.py
---
本技能在 P2 解析后运行：把讲义 PDF 中的插图以 PNG 提取到 assets 目录，
并通过 figure_index.json 说明每张图所属讲义页与一句话图注。
```

技能缺失、入口不存在或执行失败都会优雅降级（日志提示，不中断生成）。

## 4. 检查清单：添加一个新技能

1. 建目录 `skills/<name>/SKILL.md`（tool 型附脚本）；
2. `classmind skills list` 确认被发现；
3. prompt 型：跑一次 `generate` 观察提示词注入；tool 型：看运行日志中的 `[P2.6 Skill]` 行；
4. 技能要“在合适的时机做合适的事”：prompt 型管写、tool 型管取材料，不要把 prompt 型写成流程编排。
