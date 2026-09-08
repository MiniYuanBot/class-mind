"""ClassMind 视觉（图像语义描述）子包。"""

from classmind.vision.captioner import (
    DEFAULT_VISION_BASE_URL,
    DEFAULT_VISION_MODEL,
    ImageCaptioner,
    VisionError,
    build_messages,
    caption_slide_images,
    find_image_refs,
    image_data_url,
)

__all__ = [
    "ImageCaptioner",
    "VisionError",
    "build_messages",
    "caption_slide_images",
    "find_image_refs",
    "image_data_url",
    "DEFAULT_VISION_BASE_URL",
    "DEFAULT_VISION_MODEL",
]
