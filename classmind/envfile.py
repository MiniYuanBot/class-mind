"""极简 `.env` 装载（无第三方依赖）——与 paper-mind 统一：密钥文件为 `<repo>/config/.env`。

规则：
  - 查找顺序（同名键先到先得）：仓库根 `config/.env` → 仓库根 `.env`（旧布局兼容）→
    cwd 向上若干级的 `.env`；真实环境变量始终优先于文件
  - 只解析 `KEY=VALUE`（忽略 # 注释与空行），引号会被剥离
  - `config/.env` 与 `.env` 均已被 .gitignore 忽略；仓库提交 `config/.env.example`
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_REPO_ROOT = Path(__file__).resolve().parent.parent  # 仓库根目录（classmind 包的上级）


def _candidate_env_files() -> list:
    files: list = []
    seen: set = set()

    def add(p: Path):
        if p.is_file() and str(p.resolve()) not in seen:
            seen.add(str(p.resolve()))
            files.append(p)

    # 1) 统一布局：config/.env（与 paper-mind 同一约定，可共用同一份 Key）
    add(_REPO_ROOT / "config" / ".env")
    # 2) 旧布局兼容：仓库根 .env
    add(_REPO_ROOT / ".env")
    # 3) cwd 及向上 5 级（开发便利）
    cur = Path.cwd()
    for _ in range(6):
        add(cur / ".env")
        if cur.parent == cur:
            break
        cur = cur.parent
    return files


def load(force: bool = False) -> dict:
    """装载 .env（未设置才生效；force=True 时覆盖已有同名变量），返回新设置项。"""
    loaded: dict = {}
    for env_file in _candidate_env_files():
        try:
            text = env_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if not _KEY_RE.match(key) or not value:
                continue
            if force or not os.environ.get(key):
                os.environ[key] = value
                loaded[key] = value
    return loaded
