"""ClassMind 图像语义描述（Vision Captioning）。

讲义 / 论文中的图片常含信息但文本流无法表达。本模块通过 OpenAI 兼容的
**多模态** Chat Completions（如 Moonshot Kimi：base64 data URL 图片消息）
为每张讲义图片生成简短中文语义描述，随后并入该页材料，供 Plan / Draft 使用。

配置（均可选，未配置则自动跳过图片描述）：
  CLASSMIND_VISION_API_KEY   必填，触发视觉功能
  CLASSMIND_VISION_BASE_URL  默认 https://api.moonshot.cn
  CLASSMIND_VISION_MODEL     默认 kimi-k3
命令行：generate --vision-key/--vision-base-url/--vision-model
"""

from __future__ import annotations

import base64
import mimetypes
import os
import re
from pathlib import Path
from typing import Optional

from classmind.errors import ClassMindError

DEFAULT_VISION_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_VISION_MODEL = "kimi-k3"

_IMAGE_REF_RE = re.compile(r"!\[([^\]]*)\]\((assets/[^)\s]+)\)")

IMAGE_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
             "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}


class VisionError(ClassMindError):
    pass


def _env_or(*keys: str, default: Optional[str] = None) -> Optional[str]:
    for k in keys:
        v = os.environ.get(k)
        if v:
            return v
    return default


def find_image_refs(md_text: str) -> list:
    """从一页讲义 Markdown 中找出 ![…](assets/…) 图片引用。"""
    return [(m.group(1), m.group(2)) for m in _IMAGE_REF_RE.finditer(md_text or "")]


def image_data_url(path: Path) -> str:
    """读图片 -> data URL（OpenAI 多模态 image_url 格式）。"""
    ext = path.suffix.lower().lstrip(".")
    mime = IMAGE_EXT.get(ext) or mimetypes.guess_type(path.name)[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def build_messages(prompt: str, image_data_urls: list) -> list:
    """构造 OpenAI 兼容多模态 messages（纯 user 消息：文本 + image_url 列表）。"""
    content: list = [{"type": "text", "text": prompt}]
    for url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return [{"role": "user", "content": content}]


class ImageCaptioner:
    """为讲义图片生成中文语义描述的客户端（OpenAI 兼容多模态）。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 120,
        temperature: float = 1.0,
    ) -> None:
        self.api_key = api_key or _env_or("CLASSMIND_VISION_API_KEY") or ""
        self.base_url = (base_url or _env_or("CLASSMIND_VISION_BASE_URL") or DEFAULT_VISION_BASE_URL).rstrip("/")
        self.model = model or _env_or("CLASSMIND_VISION_MODEL") or DEFAULT_VISION_MODEL
        self.timeout = timeout
        self.temperature = temperature
        if not self.api_key:
            raise VisionError("未配置视觉 API Key：设置 CLASSMIND_VISION_API_KEY 或 --vision-key")

    def describe(self, image_path: Path, context: str = "", max_len: int = 160) -> str:
        """对单张图片生成中文描述；失败抛 VisionError（由调用方降级处理）。"""
        url = image_data_url(image_path)
        prompt = (
            "请以中文为这张课堂讲义图片写一段简洁、信息准确的**语义描述**"
            "（结构/关键元素/传达的信息，可含图中文字要点），"
            f"不超过 {max_len} 字；只描述图片中确实可见的内容，不要推测。"
        )
        if context:
            prompt += f"\n\n页面上下文：{context[:300]}"
        content = build_messages(prompt, [url])
        data = self._post(content)
        return self._extract(data)

    def _post(self, messages: list) -> dict:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise VisionError("视觉功能需要 requests") from exc
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": 600,
            "stream": False,
        }
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except Exception as exc:  # noqa: BLE001
            raise VisionError(f"视觉 API 请求失败: {exc}") from exc
        if resp.status_code != 200:
            raise VisionError(f"视觉 API HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise VisionError("视觉 API 返回非法 JSON") from exc

    @staticmethod
    def _extract(data: dict) -> str:
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:  # noqa: BLE001
            raise VisionError("视觉 API 返回缺少内容") from exc
        # 兼容纯文本与分段多模态返回
        if isinstance(text, list):
            parts = [c.get("text", "") for c in text if isinstance(c, dict) and c.get("type") == "text"]
            text = "".join(parts)
        return (text or "").strip()


def caption_slide_images(
    body_md: str,
    raw_text: str,
    assets_dir: Path,
    captioner: "ImageCaptioner",
    page_title: str = "",
    page_id: int = 0,
) -> tuple:
    """为该页讲义中的每张图片生成图注并改写正文。

    返回 (body_md, raw_text)：图片行替换为 [图片语义描述] 段落（保留 assets 相对引用便于核对）。
    任一张图失败时降级为不替换并返回原文本（不中断流水线）。
    """
    refs = find_image_refs(body_md)
    if not refs:
        return body_md, raw_text
    new_body = body_md
    notes: list = []
    for alt, rel in refs:
        img = (assets_dir / Path(rel).name) if assets_dir else None
        if img is None or not img.exists():
            continue
        try:
            cap = captioner.describe(img, context=f"第 {page_id} 页《{page_title}》", max_len=160)
        except VisionError as exc:
            print(f"  [P2 Vision] 第 {page_id} 页图片描述失败，已跳过: {exc}", file=__import__("sys").stderr)
            continue
        if not cap:
            continue
        notes.append(cap)
        # 图片行 -> 自然语言的图注行（保留资源路径便于人工核对）
        line_re = re.compile(r"^\s*!\[[^\]]*\]\(" + re.escape(rel) + r"\)\s*$", re.M)
        new_body = line_re.sub(f"**{alt}**：{cap}（资源：{rel}）", new_body, count=1)
    if not notes:
        return body_md, raw_text
    extra = "\n\n" + "\n".join(f"- 【图】{n}" for n in notes)
    return new_body, (raw_text + extra).strip()
