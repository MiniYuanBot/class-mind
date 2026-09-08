"""用户 Skills 注册表（可插拔技能）。

技能 = 一个说明文件（SKILL.md）+ 可选脚本资源。两类：
  * prompt 型（默认）：SKILL.md 正文作为“用户技能 / 补充要求”注入每个 LLM 提示词，
    与旧版 `--skills file|dir` / `input/skills/*.md` 行为一致（向后兼容）。
  * tool  型：SKILL.md 声明 `kind: tool` + `entry:` 可执行命令；由流水线在
    合适的阶段（如 P2.6 素材富集）通过 `run_tool_skill()` 调用；失败优雅降级。

SKILL.md 元数据约定（依赖零，无需 yaml）：文件头以 `---` 行包裹的 `key: value`
段（value 多个取值用逗号分隔）：

    ---
    name: figures
    kind: tool                 # prompt | tool（缺省 prompt）
    description: 从 PDF/讲义中提取干净插图
    stages: draft,polish       # prompt 型生效的写作阶段（缺省全部）
    hook: enrich               # tool 型触发点（缺省：不自动触发）
    entry: python extract.py   # tool 型可执行命令（相对 skill 目录）
    ---
    <SKILL.md 正文，prompt 型时原样注入提示词>

来源（同名去重，先到先得）：
  1. 环境变量 CLASSMIND_SKILLS / CLI --skills（文件或目录）
  2. 输入包内 input/skills/*.md（自动，约定位置）
  3. 仓库根 skills/<name>/SKILL.md（自动发现；tool 型只能放这里）
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from classmind.errors import ClassMindError

SKILLS_DIR_NAME = "skills"                  # input/skills 与仓库根 skills 目录名
_FM_START = "---"
_PROMPT_EXTS = (".md", ".txt")


class SkillError(ClassMindError):
    pass


@dataclass
class Skill:
    """一条技能：来源文件、元数据与正文。"""

    name: str
    kind: str = "prompt"                    # prompt | tool
    description: str = ""
    stages: list = field(default_factory=list)   # prompt 型：生效写作阶段（空=全部）
    hook: str = ""                          # tool 型：流水线触发点（如 enrich/figures）
    entry: str = ""                         # tool 型：相对 source_dir 的可执行命令
    body: str = ""                          # SKILL.md 正文（prompt 型注入内容）
    source: Path = None                    # type: ignore[assignment]
    source_dir: Path = None                # type: ignore[assignment]

    # ------------------------------------------------------------------
    @property
    def text(self) -> str:
        """注入用文本：带名头的正文。"""
        return self.body.strip()

    def applies_to(self, stage: str) -> bool:
        """prompt 型技能是否应在某写作阶段注入。"""
        if self.kind != "prompt":
            return False
        return (not self.stages) or (stage in self.stages)


def _parse_front_matter(text: str) -> tuple:
    """解析 SKILL.md：返回 (meta dict, body)。无 front matter 时 meta 为空。"""
    if not text.startswith(_FM_START):
        return {}, text
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FM_START:
            end = i
            break
    if end is None:
        return {}, text
    meta: dict = {}
    for ln in lines[1:end]:
        if ":" not in ln:
            continue
        k, _, v = ln.partition(":")
        meta[k.strip().lower()] = v.strip()
    body = "\n".join(lines[end + 1:]).strip()
    return meta, body


def _skill_from_file(path: Path) -> Optional[Skill]:
    """把一个 .md/.txt 文件解析成 Skill；无法读取则返回 None。

    名称规则：front matter 声明 name 优先；否则 SKILL.md 用所在目录名，
    普通文件用文件名（含扩展名，兼容旧版按文件名分节的行为）。
    """
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    meta, body = _parse_front_matter(raw)
    if meta.get("name"):
        name = str(meta["name"]).strip()
    elif path.name.lower() == "skill.md":
        name = path.parent.name
    else:
        name = path.name
    kind = str(meta.get("kind") or "prompt").strip().lower()
    if kind not in ("prompt", "tool"):
        kind = "prompt"
    stages = [
        s.strip() for s in str(meta.get("stages") or "").split(",") if s.strip()
    ]
    skill = Skill(
        name=name,
        kind=kind,
        description=str(meta.get("description") or "").strip(),
        stages=stages,
        hook=str(meta.get("hook") or "").strip(),
        entry=str(meta.get("entry") or "").strip(),
        body=body or raw.strip(),
        source=path,
        source_dir=path.parent,
    )
    return skill if skill.text else None


def _collect_files(sources: list, include_subdirs: bool = True) -> list:
    """把 文件/目录 来源展开为候选 .md/.txt 文件列表。"""
    files: list = []
    for src in sources:
        p = Path(src)
        if p.is_file() and p.suffix.lower() in _PROMPT_EXTS:
            files.append(p)
        elif p.is_dir():
            it = p.rglob("*") if include_subdirs else p.glob("*")
            files.extend(
                f for f in sorted(it)
                if f.is_file() and f.suffix.lower() in _PROMPT_EXTS
            )
    return files


def _dedupe(skills: list) -> list:
    seen: dict = {}
    for sk in skills:
        if sk and sk.name not in seen:
            seen[sk.name] = sk
    return list(seen.values())


def _env_sources(env_name: str) -> list:
    env = os.environ.get(env_name)
    return [p for p in env.split(os.pathsep) if p] if env else []


def load_skills(
    skills_path=None,
    input_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    kinds: tuple = ("prompt", "tool"),
) -> list:
    """装载全部技能（按来源优先级去重）。向后兼容：旧来源仍然有效。"""
    sources = []
    sources += _env_sources("CLASSMIND_SKILLS")
    if skills_path:
        sources += str(skills_path).split(os.pathsep) if os.pathsep in str(skills_path) else [str(skills_path)]
    found: list = []
    for f in _collect_files(sources):
        sk = _skill_from_file(f)
        if sk:
            found.append(sk)
    if input_dir is not None:
        auto = Path(input_dir) / SKILLS_DIR_NAME
        if auto.is_dir():
            for f in _collect_files([auto]):
                sk = _skill_from_file(f)
                if sk:
                    found.append(sk)
    if repo_root is not None:
        repo_skills = Path(repo_root) / SKILLS_DIR_NAME
        if repo_skills.is_dir():
            for f in _collect_files([repo_skills]):
                sk = _skill_from_file(f)
                if sk:
                    found.append(sk)
    return [sk for sk in _dedupe(found) if sk.kind in kinds]


def load_prompt_skills(
    skills_path=None,
    input_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    stage: Optional[str] = None,
) -> list:
    """prompt 型技能列表（可选按写作阶段过滤）。"""
    out = load_skills(skills_path, input_dir, repo_root, kinds=("prompt",))
    if stage:
        out = [sk for sk in out if sk.applies_to(stage)]
    return out


def load_tool_skills(repo_root: Optional[Path] = None, hook: Optional[str] = None) -> list:
    """tool 型技能列表（可选按触发点过滤）。"""
    out = load_skills(None, None, repo_root, kinds=("tool",))
    if hook:
        out = [sk for sk in out if sk.hook == hook]
    return out


def load_skill_text(
    skills_path=None,
    input_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    stage: Optional[str] = None,
) -> str:
    """（旧接口保留）把全部适用的 prompt 型技能拼接为注入文本；无则空串。"""
    parts: list = []
    for sk in load_prompt_skills(skills_path, input_dir, repo_root, stage=stage):
        parts.append(f"### {sk.name}\n\n{sk.text}")
    return "\n\n".join(parts)


def find_repo_root() -> Optional[Path]:
    """仓库根（含 skills/ 与 prompts/ 的约定位置）：skills.py -> classmind/ -> 仓库根。"""
    here = Path(__file__).resolve()                 # .../classmind/skills.py
    cand = here.parent.parent                       # 仓库根
    return cand if (cand / "prompts").is_dir() else None


def run_tool_skill(skill: Skill, argv: Optional[list] = None, timeout: int = 600) -> str:
    """执行一条 tool 型技能（entry 相对 skill 目录），成功返回 stdout，失败抛 SkillError。

    设计契约：技能作者负责入口的健壮性；调用方（流水线）应捕获 SkillError 优雅降级。
    """
    if skill.kind != "tool":
        raise SkillError(f"技能 {skill.name} 不是 tool 型（kind={skill.kind}）")
    if not skill.entry:
        raise SkillError(f"tool 技能 {skill.name} 缺少 entry 声明")
    base = skill.source_dir or Path(".")
    cmd = skill.entry.split()
    cmd += list(argv or [])
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise SkillError(f"技能 {skill.name} 入口不存在（{cmd[0]}）：{exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SkillError(f"技能 {skill.name} 执行超时（>{timeout}s）") from exc
    if proc.returncode != 0:
        raise SkillError(
            f"技能 {skill.name} 执行失败 rc={proc.returncode}：{proc.stderr.strip()[:400]}"
        )
    return proc.stdout
