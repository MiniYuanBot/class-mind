"""P5 提示词编排引擎（Prompt Orchestrator）。

提示词即产品（Prompt-as-Product）——所有提示词模板统一放在仓库根目录 `prompts/`：
  prompts/
  ├── catalog.json        # 阶段/课程类型/通用约束声明
  └── templates/*.md      # 提示词模板（角色/输入/输出/幻觉禁止/领域/分层任务）

默认定位顺序：
  1. 环境变量 CLASSMIND_PROMPT_DIR
  2. 仓库根目录下的 prompts/（与 classmind 包同级）
  3. 随包安装的 classmind/prompts/templates（若以旧结构分发）
自定义覆盖：generate --prompt-dir <dir> / prompts show --prompt-dir <dir>。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from classmind.errors import PromptError
from classmind.models import CourseMeta, CourseType

_PKG_DIR = Path(__file__).resolve().parent                 # .../classmind/prompts
_REPO_ROOT = _PKG_DIR.parent.parent                        # 仓库根目录
_ROOT_PROMPTS = _REPO_ROOT / "prompts"                     # 根级 prompts/
_LEGACY_INSTALL = _PKG_DIR / "templates"                   # 旧结构随包目录（可选）

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def find_default_prompt_dir() -> Path:
    """按优先级定位默认 prompts 目录（含 catalog.json + templates/）。"""
    env_dir = os.environ.get("CLASSMIND_PROMPT_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)
    for cand in (_ROOT_PROMPTS, _PKG_DIR):
        if (cand / "catalog.json").exists() and (cand / "templates").is_dir():
            return cand
    raise PromptError(
        "未找到提示词目录：请把 prompts/（含 catalog.json 与 templates/）放在仓库根目录，"
        "或通过 CLASSMIND_PROMPT_DIR / --prompt-dir 指定。"
    )


def load_catalog(base_dir: Path) -> dict:
    p = base_dir / "catalog.json"
    if not p.exists():
        for cand in (_ROOT_PROMPTS, _PKG_DIR):
            if (cand / "catalog.json").exists():
                p = cand / "catalog.json"
                break
    if not p.exists():
        raise PromptError(f"缺少提示词目录声明: catalog.json（在 {base_dir} 下未找到）")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


class PromptOrchestrator:
    """按课程类型与阶段组装分层提示词。"""

    def __init__(self, template_dir: Optional[Path] = None) -> None:
        self.base_dir = Path(template_dir) if template_dir else find_default_prompt_dir()
        # 兼容两种布局：<dir>/templates/*.md（根级）或 <dir>/*.md（扁平覆盖目录）
        sub = self.base_dir / "templates"
        self.template_dir = sub if sub.is_dir() else self.base_dir
        if not self.template_dir.is_dir():
            raise PromptError(f"提示词模板目录不存在: {self.template_dir}")
        self.catalog = load_catalog(self.base_dir)
        # 覆盖目录未提供某模板时，回落默认目录
        try:
            self._fallback_template_dir = find_default_prompt_dir() / "templates"
            if not self._fallback_template_dir.is_dir():
                self._fallback_template_dir = find_default_prompt_dir()
        except PromptError:
            self._fallback_template_dir = None

    # ------------------------------------------------------------------
    def _read_template(self, name: str) -> str:
        p = self.template_dir / name
        if p.exists():
            return p.read_text(encoding="utf-8")
        if self._fallback_template_dir and (self._fallback_template_dir / name).exists():
            return (self._fallback_template_dir / name).read_text(encoding="utf-8")
        raise PromptError(f"缺少提示词模板: {name}（目录 {self.template_dir}）")

    @staticmethod
    def fill(text: str, variables: dict) -> str:
        def repl(m: re.Match) -> str:
            key = m.group(1)
            if key in variables and variables[key] is not None:
                return str(variables[key])
            return f"{{{{ {key} }}}}"

        return _VAR_RE.sub(repl, text)

    # ------------------------------------------------------------------
    def render(
        self,
        stage: str,
        meta: CourseMeta,
        variables: Optional[dict] = None,
    ) -> str:
        """stage ∈ catalog['stages']（skeleton / knowledge_card / problem_card / summary）。"""
        stages = self.catalog.get("stages", {})
        if stage not in stages:
            raise PromptError(f"未知提示词阶段: {stage}（可用: {', '.join(stages)}）")
        stage_cfg = stages[stage]
        ct = meta.course_type if meta.course_type else CourseType.THEORY
        ct_key = ct.value
        type_cfg = self.catalog["course_types"].get(ct_key, self.catalog["course_types"]["theory"])

        variables = dict(variables or {})
        variables.setdefault("course_name", meta.course_name or "未命名课程")
        variables.setdefault("chapter_title", meta.chapter_title or meta.chapter_no or "")
        variables.setdefault("subject", meta.subject or "通用")
        variables.setdefault("course_type_label", f"{type_cfg['label']}（{ct_key}）")

        parts: list = []
        parts.append(f"# ClassMind · {stage_cfg['layer']} {stage_cfg['label']}")
        parts.append("## 一、角色")
        parts.append(self.fill(self._read_template(self.catalog["universal"]["role"]), variables))
        parts.append("## 二、输入")
        parts.append(self.fill(self._read_template(self.catalog["universal"]["input_declaration"]), variables))
        parts.append("## 三、输出约束")
        parts.append(self._read_template(self.catalog["universal"]["output_declaration"]))
        parts.append("## 四、幻觉禁止与溯源")
        parts.append(self._read_template(self.catalog["universal"]["hallucination_ban"]))
        parts.append("## 五、课程类型专用要求")
        parts.append(self._read_template(type_cfg["template"]))
        parts.append("## 六、材料处理模式")
        parts.append(self._read_template(self.catalog["patterns"]["figure_handling"]))
        parts.append(self._read_template(self.catalog["patterns"]["transcript_handling"]))
        parts.append("## 七、本阶段任务")
        parts.append(self.fill(self._read_template(stage_cfg["template"]), variables))
        if not stage_cfg.get("skip_references", False):
            appendix = self._reference_docs()
            if appendix:
                parts.append("## 附录 · 参考规范")
                parts.append(appendix)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    def _reference_docs(self) -> str:
        """把 references/ 下的规范全文附加进提示词（笔记格式 markdown.md、伪代码 pseudocode.md）。"""
        names = self.catalog.get("references") or ["markdown.md", "pseudocode.md"]
        headers = {
            "markdown.md": "### 附录 A · 中文笔记 Markdown 格式规范（markdown.md 全文）\n最终中文笔记必须严格遵循以下格式规范。",
            "pseudocode.md": "### 附录 B · 算法 / 伪代码风格参考（pseudocode.md 全文）\n当笔记涉及分布式算法、协议或系统伪代码时，一律按以下规范书写伪代码；否则可忽略。",
        }
        bases = [self.base_dir]
        try:
            fb = find_default_prompt_dir()
            if fb not in bases:
                bases.append(fb)
        except PromptError:
            pass
        chunks: list = []
        for name in names:
            found = None
            for base in bases:
                p = base / "references" / name
                if p.exists():
                    found = p
                    break
            if found is None:
                continue
            head = headers.get(name, f"### 附录 · {name}")
            body = found.read_text(encoding="utf-8").strip()
            chunks.append(f"{head}\n\n{body}")
        return "\n\n---\n\n".join(chunks)

    # ------------------------------------------------------------------
    def describe(self, stage: Optional[str] = None) -> str:
        stages = self.catalog["stages"]
        if stage:
            cfg = stages.get(stage)
            if not cfg:
                raise PromptError(f"未知阶段: {stage}")
            return f"[{cfg['layer']}] {cfg['label']}：{cfg.get('description', '')}（模板 {cfg['template']}）"
        return "\n".join(
            f"[{cfg['layer']}] {name}：{cfg.get('description', '')}"
            for name, cfg in stages.items()
        )
