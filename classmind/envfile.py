"""极简 `.env` 装载（无第三方依赖）。

规则：
  - 查找顺序：当前工作目录起向上若干级、以及包仓库根目录的 `.env`
  - 只解析 `KEY=VALUE`（忽略 # 注释与空行），引号会被剥离
  - 仅在环境变量尚未设置时写入（真实环境优先于 .env）
  - `.env` 已被 .gitignore 忽略；仓库提交的是 `.env.example` 占位模板
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
    # cwd 及向上 5 级，再补包仓库根目录
    cur = Path.cwd()
    for _ in range(6):
        p = cur / ".env"
        if p.is_file() and str(p.resolve()) not in seen:
            seen.add(str(p.resolve()))
            files.append(p)
        if cur.parent == cur:
            break
        cur = cur.parent
    p = _REPO_ROOT / ".env"
    if p.is_file() and str(p.resolve()) not in seen:
        seen.add(str(p.resolve()))
        files.append(p)
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
