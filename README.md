# ClassMind

**ClassMind** is an end-to-end classroom-note generator. Give it a lecture package — the
handout/slides plus the classroom transcript (dictation) — and it produces **one structured
Chinese Markdown course note** ready for review and sharing, plus machine-readable metadata.

```
slides/handout + transcript  ->  P1 Input Gateway  ->  P2 Slide2MD (+ optional P2.5 vision captions)
   ->  P3 Transcript Processing  ->  P4 Multimodal Alignment
   ->  P5 Prompt Orchestration  ->  P6 Plan→Draft note core  ->  P7 Note Generator  ->  output/<name>.md
```

Everything the user touches is English (README, CLI, logs, prompt catalog keys, metadata files);
the **final note is the one Chinese artifact** (Chinese structure with English terms glossed),
following the note-format guide `prompts/references/markdown.md`.

---

## 1. Requirements & install

- Python 3.10+
- Optional parsers/backends: `PyMuPDF` (PDF), `python-pptx` (PPTX), `python-docx` (DOCX),
  `requests` (LLM / vision API), `reportlab` (demo generation)

```powershell
cd D:\__Coding__\repos\class-mind
python -m pip install -e ".[full]"
```

Not installed? Replace `classmind` below with `python -m classmind`.

---

## 2. Quick start

### 2.1 Quick run

```powershell
classmind demo --run     # writes input-sample/ + output-sample/ and runs generation (LLM, §2.7)
classmind generate input output    # your own package:  handout + transcript -> output/<name>.md
```

`demo` builds a small "machine-learning lecture" package (PPTX + DOCX + `meta.json`). Generation
is **LLM-only** (no deterministic offline engine): you need the API key configured in `config/.env` (§2.7).

### 2.2 Use your own lecture package

Put your materials in one directory (e.g. `input/`). The layout in this repo looks like:

```
input/
├── 2-1up.pdf          # handout / slides (.pdf/.pptx)     <- local-only example
├── L02_原文.docx      # classroom transcript / dictation  <- local-only example
├── skills/            # optional: extra writing requirements (*.md), see §2.5
├── meta.json          # tracked schema example ONLY (no real info; edit for your course)
└── meta.cs162.json    # local-only real metadata (untracked) — copy to meta.json to reproduce
```

Important: everything under `input/` is **gitignored except `meta.json`** (kept as a field example,
with placeholder values — fill in your own). If you have the CS162 materials locally, restore the
real metadata with `Copy-Item input\meta.cs162.json input\meta.json` before running.

### 2.3 Generation (Plan → Draft, fully Chinese systematized notes)

Generation is LLM-only. The old "skeleton + knowledge cards" prompt chain is gone; v2 works like a
real writer:

- **L1 Plan** – the model reads a digest of the whole lesson (per-page handout text + aligned
  teacher dictation) and returns a **machine-readable plan**: final-note title + ordered `##`
  sections, each mapped to the handout pages that feed it (teaching order, not deck order).
- **L2 Draft** – sections are grouped into budgeted batches; each batch call receives the *real*
  handout text and dictation of exactly those pages and writes fluent Chinese note sections
  (definitions, intuition, formulas + symbol tables, teacher emphasis, pitfalls, Q&A) following
  `prompts/references/markdown.md`.
- Assembly – header block + sections in plan order ⇒ **one coherent finished `.md`** with no
  scaffolding ("本讲框架" wrappers, page markers or QA text inside the body).
- Optional **L3 Polish** – whole-document consistency review (not run by default).

```powershell
# Option A: keys in repo-root config/.env (auto-loaded, see §2.7) — no extra flags
classmind generate input output

# Option B: inline flags
classmind generate input output --api-key sk-... --base-url https://api.deepseek.com
```

With real metadata in place (e.g. restoring `input/meta.cs162.json` ⇒ `course_code: "cs162"`,
`chapter_no: "2"`), the note is written to `output/cs162-lecture2-notes.md`. Without a custom
`meta.json`, naming falls back to the generic `course_code`/chapter rule (see §2.6).

### 2.4 Optional: slide-image captions through a vision API (Kimi, etc.)

If a handout page contains images, their semantic content is invisible to a text-only model.
Set a vision API key (any OpenAI-compatible multimodal endpoint — Moonshot Kimi by default) and
ClassMind captions each extracted figure in Chinese before alignment/drafting:

```powershell
$env:KIMI_API_KEY = "sk-..."                               # enables captions automatically (alias CLASSMIND_VISION_API_KEY)
$env:KIMI_BASE_URL = "https://api.moonshot.cn/v1"          # optional (default)
$env:KIMI_MODEL = "kimi-k3"                                # optional (default; some keys need another model, see `GET /v1/models`)
classmind generate input output
```

Or inline: `--vision-key/--vision-base-url/--vision-model`. Without a key the step is skipped.

### 2.5 User skills (extra writing requirements)

Any `.md` files supplied this way are appended to every LLM prompt as the highest-priority
"user skills / requirements" section — e.g. course-specific note rules, term glossaries,
instructor preferences:

- CLI: `classmind generate input output --skills .\my-rules.md` (file or folder)
- env: `CLASSMIND_SKILLS=path1;path2` (OS path separator)
- convention: put them in the input package under `input/skills/*.md`

**Pluggable skills registry (v0.4+).** Skills may also live under repo-root `skills/<name>/SKILL.md`
with `---` front matter:

```markdown
---
name: teacher-style      # skill name
kind: prompt             # prompt (injected into prompts, default) | tool (executed at a hook)
stages: draft,polish     # prompt: which writing stages it applies to (default all)
hook: enrich             # tool: pipeline hook (enrich = P2.6 material enrichment)
entry: python3 x.py      # tool: command relative to the skill dir
---
<instructions body — for prompt-kind skills this is injected verbatim>
```

Inspect with `classmind skills list` / `classmind skills show <name>`. A `tool` skill with
`hook: enrich` runs after P2 with `(input_dir, assets_dir)`; it may write images plus an optional
`assets/figure_index.json` (`[{asset, page, caption}]`) that the pipeline merges into the matching
slide. Tool failures degrade gracefully. Full spec: `skills/README.md`.

### 2.6 Inspect the output & run tests

```
output/
├── cs162-lecture2-notes.md   # final note (pure-English file name, Chinese content)
├── assets/                   # figures extracted from slides (+ used by vision captions)
└── meta/
    ├── course_outline.json    # machine-readable plan (title + sections + page coverage)
    ├── alignment_map.json     # slide <-> transcript mapping + coverage
    ├── highlights.json        # instructor emphasis points
    └── qa_report.json         # QA checks (headings / consistency / coverage / ...)
```

File naming priority: `meta.json` `file_stem` (e.g. `cs162-lecture2-notes`) → `course_code` +
numeric `chapter_no` (`cs162` + `2` ⇒ `cs162-lecture2-notes.md`) → ASCII words of the
course/chapter title → `course-<n>.md`.

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

### 2.7 Where API keys live (config/.env)

Keys are **never** hard-coded or committed. Put them in `config/.env` at the repo root — the CLI
auto-loads it (`classmind/envfile.py`; legacy repo-root `.env` is still honored), and real OS
environment variables always win over the file. **The variable names are shared with the sibling
repo paper-mind**, so one `config/.env` can serve both tools:

```
# config/.env (gitignored — copy from config/.env.example)
DEEPSEEK_API_KEY=sk-...            # text LLM (aliases: CLASSMIND_API_KEY / OPENAI_API_KEY)
KIMI_API_KEY=sk-...                # optional, figure captions (alias: CLASSMIND_VISION_API_KEY)
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_MODEL=kimi-k3
```

`config/.env.example` (tracked) documents every variable. Equivalently, set the variables in your
shell / system environment and skip the file entirely.

---

## 3. Commands

| Command | Purpose |
| :--- | :--- |
| `classmind generate <in> <out>` | Zero-config pipeline over `<in>` into `<out>` |
| `classmind demo [--run]` | Generate a sample package (optionally run the pipeline) |
| `classmind prompts list` / `classmind prompts show <plan\|draft\|polish\|fix>` | Prompt catalog (Prompt Transparency) |
| `classmind skills list` / `classmind skills show <name>` | Pluggable skills registry (prompt & tool kinds) |
| `classmind version` | Print version |

### `generate` options

| Option | Meaning |
| :--- | :--- |
| `--course-name`, `--instructor`, `--chapter-no`, `--chapter-title`, `--subject` | Override metadata auto-detection |
| `--course-code`, `--lecture-date`, `--file-stem` | Control the English output file name (`--course-code cs162 --chapter-no 2` ⇒ `cs162-lecture2-notes.md`; `--file-stem` wins) |
| `--type theory\|lab\|tutorial\|seminar` | Override course-type routing |
| `--api-key`, `--base-url`, `--model` | LLM connection override (env / `config/.env`: `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`; completion size via `DEEPSEEK_MAX_TOKENS`, default 8192; legacy aliases `CLASSMIND_LLM_*`) |
| `--vision-key`, `--vision-base-url`, `--vision-model` | Optional slide-image captions (env `KIMI_*`; legacy aliases `CLASSMIND_VISION_*`, Kimi-compatible by default) |
| `--skills <file\|dir>` | Extra user requirements appended to prompts (env `CLASSMIND_SKILLS`, or `input/skills/*.md`) |
| `--prompt-dir <dir>` | Override prompt templates (same file names; env `CLASSMIND_PROMPT_DIR`) |
| `--coverage-threshold 0.7` | Transcript-coverage warning threshold |
| `--fix-rounds N` | QA revision loop: after assembly, feed machine-fixable QA issues back to the LLM up to N rounds (default 0 = off; stage `fix`, see L4) |
| `-v / --verbose` | More intermediate output |

### Course types

| Type | Routed focus |
| :--- | :--- |
| `theory` | definitions, theorems, proofs, derivations |
| `lab` | experiment steps, environment, code, result analysis |
| `tutorial` | problem types, strategies, common mistakes, variants |
| `seminar` | viewpoints, critique, state of the art |

Auto-detection falls back to file-name hints then a transcript sample; `meta.json` wins over
heuristics, CLI flags win over `meta.json`.

---

## 4. Input package contract

| Entry | Extensions | Role |
| :--- | :--- | :--- |
| Handout / slides | `.pdf`, `.pptx` | parsed into per-page Markdown; images extracted |
| Transcript | `.docx`, `.txt`, `.md` | denoised, segmented, aligned |
| Auxiliary images | `.png`, `.jpg`, ... | kept as figure assets |
| Skills (optional) | `skills/*.md` | extra user writing requirements (see §2.5) |
| Metadata (optional) | `meta.json` | see below |

`meta.json` keys: `course`, `instructor`, `chapter_no`, `chapter_title`, `subject`,
`course_type` (theory/lab/tutorial/seminar), `course_code` (e.g. `cs162`), `lecture_date`,
`file_stem`. Quality pre-checks: ≥1 handout or transcript must exist; the deck must yield text;
an empty/noise transcript is flagged.

---

## 5. Project layout

```
classmind/                  # Python package
├── cli.py                  # CLI entry point
├── pipeline.py             # orchestrates P1..P7 (+ P2.5 vision captions, P2.6 skills, P7.5 QA-fix)
├── models.py               # dataclasses shared across stages
├── skills.py               # skills registry (prompt & tool kinds; SKILL.md front matter)
├── gateway/                # P1 input gateway
├── parsing/                # P2 slide parser (pdf/pptx), P3 transcript processor
├── alignment/              # P4 multimodal alignment
├── vision/                 # optional image captioning (Kimi / OpenAI-compatible)
├── prompts/                # P5 orchestration code (templates live in repo-root prompts/)
├── core/                   # P6: LLM Plan→Draft builder + LLM client
├── generator/              # P7 note generator (assembly, naming, meta dump)
├── quality/                # QA checks + L4 QA-fix revision loop (quality/fixer.py)
└── demo.py                 # sample package generator (`classmind demo`)
prompts/                    # ALL prompt assets
├── catalog.json            # stage/type/pattern declarations (plan/draft/polish/fix)
├── templates/*.md          # universal role/input/output/hallucination, domain, layer tasks
└── references/*.md         # markdown.md (format spec) + pseudocode.md
skills/                     # pluggable skills (SKILL.md + optional scripts) — see skills/README.md
agent/AGENT.md              # agent definition (mirrored layout with paper-mind)
WORKFLOW.md                 # stage detail + quality contract (mirrored layout)
docs/ARCHITECTURE.md        # shared twin-repo architecture spec (kept in sync with paper-mind)
config/.env(.example)      # local API keys (ignored) + tracked template — shared naming with paper-mind
input/                      # your lecture package (gitignored except meta.json)
output/                     # generated note + assets + meta (gitignored)
tests/                      # unittest suite (workspace-scoped temp dirs)
```

---

## 6. Output language notes

- The **final note** is Chinese (structure in Chinese, original English kept verbatim when the
  source material is English) — the one Chinese artifact.
- Prompt templates instruct the LLM in Chinese note writing; file names / catalog keys are English.
- Generation is LLM-only: fully paraphrased/translated Chinese notes need the text API key (§2.7);
  the old no-API deterministic engine was removed.

## 7. License

MIT — see [LICENSE](LICENSE).
