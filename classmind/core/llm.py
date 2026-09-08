"""LLM 客户端（OpenAI 兼容 Chat Completions）。

统一配置（与 paper-mind 同一套规范变量，Key 放仓库根 `config/.env`）：
  DEEPSEEK_API_KEY / --api-key            （兼容别名：CLASSMIND_API_KEY / OPENAI_API_KEY）
  DEEPSEEK_BASE_URL / --base-url          （默认 https://api.deepseek.com；别名 CLASSMIND_LLM_BASE_URL）
  DEEPSEEK_MODEL / --model                （默认 deepseek-chat；别名 CLASSMIND_LLM_MODEL）
  DEEPSEEK_MAX_TOKENS                     （别名 CLASSMIND_LLM_MAX_TOKENS，默认 8192）
"""

from __future__ import annotations

import json
import os
from typing import Optional

from classmind.errors import ClassMindError

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_MAX_TOKENS = 8192


def env_or(*keys: str, default: Optional[str] = None) -> Optional[str]:
    for k in keys:
        v = os.environ.get(k)
        if v:
            return v
    return default


class LLMError(ClassMindError):
    pass


class LLMClient:
    """极简 OpenAI 兼容客户端（依赖 requests）。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
        timeout: int = 180,
    ) -> None:
        self.api_key = api_key or env_or("DEEPSEEK_API_KEY", "CLASSMIND_API_KEY", "OPENAI_API_KEY") or ""
        self.base_url = (base_url or env_or("DEEPSEEK_BASE_URL", "CLASSMIND_LLM_BASE_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or env_or("DEEPSEEK_MODEL", "CLASSMIND_LLM_MODEL") or DEFAULT_MODEL
        self.temperature = temperature
        self.max_tokens = int(
            max_tokens
            or env_or("DEEPSEEK_MAX_TOKENS", "CLASSMIND_LLM_MAX_TOKENS")
            or DEFAULT_MAX_TOKENS
        )
        self.timeout = timeout
        if not self.api_key:
            raise LLMError(
                "未配置 API Key：请设置环境变量 DEEPSEEK_API_KEY（或 CLASSMIND_API_KEY），"
                "或把 Key 放入仓库根 config/.env（见 config/.env.example）"
            )

    # ------------------------------------------------------------------
    def complete(self, prompt: str) -> str:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise LLMError("LLM 模式需要 requests，请执行: pip install requests") from exc

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                if resp.status_code != 200:
                    raise LLMError(f"LLM 调用失败 HTTP {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if not content or not content.strip():
                    raise LLMError("LLM 返回空内容")
                return content.strip()
            except (LLMError, KeyError, json.JSONDecodeError) as exc:
                last_err = exc
                if isinstance(exc, LLMError) and "HTTP" in str(exc):
                    break
            except Exception as exc:  # noqa: BLE001 网络类错误重试一次
                last_err = exc
        raise LLMError(f"LLM 调用失败: {last_err}")

    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: dict) -> "LLMClient":
        return cls(
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
            model=config.get("model"),
            temperature=config.get("temperature", 0.2),
            max_tokens=config.get("max_tokens", 8192),
        )
