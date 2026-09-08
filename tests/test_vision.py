"""Vision 图注模块单元测试（不联网：Fake captioner / 纯函数）。"""

import unittest
from pathlib import Path

from classmind.vision.captioner import (
    build_messages,
    caption_slide_images,
    find_image_refs,
)

from tests._util import workspace_tempdir


def _tiny_png(path: Path) -> None:
    # 1x1 透明 PNG（仅用于“文件存在”与数据 URL 构造）
    path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d494844520000000100000001080600000"
            "01f15c4890000000d4944415478da63fcffff3f030005fe02fea73f1b"
            "cd0000000049454e44ae426082"
        )
    )


class FakeCaptioner:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = 0

    def describe(self, image_path, context="", max_len=160):
        self.calls += 1
        if not self.ok:
            from classmind.vision.captioner import VisionError

            raise VisionError("fake failure")
        return f"图中展示的示意图：{Path(image_path).name}"


class TestFindRefs(unittest.TestCase):
    def test_find_image_refs(self):
        md = "正文\n![图 3 第1张图](assets/slide_03_fig1.png)\n\nmore"
        refs = find_image_refs(md)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0][1], "assets/slide_03_fig1.png")

    def test_none(self):
        self.assertEqual(find_image_refs("没有图片"), [])


class TestBuildMessages(unittest.TestCase):
    def test_multimodal_structure(self):
        msgs = build_messages("描述这张图", ["data:image/png;base64,AAA"])
        content = msgs[0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertEqual(content[1]["image_url"]["url"], "data:image/png;base64,AAA")


class TestCaptionSlideImages(unittest.TestCase):
    def test_success_replaces_image_line(self):
        with workspace_tempdir("classmind_vis_") as tmp:
            assets = Path(tmp) / "assets"
            assets.mkdir()
            img = assets / "slide_03_fig1.png"
            _tiny_png(img)
            body = "标题\n\n![图 3](assets/slide_03_fig1.png)\n\n结尾"
            raw = "标题 正文"
            cap = FakeCaptioner(ok=True)
            nb, nr = caption_slide_images(body, raw, assets, cap, page_title="T", page_id=3)
            self.assertEqual(cap.calls, 1)
            self.assertIn("图中展示的示意图", nb)
            self.assertNotIn("![]", nb)
            self.assertIn("【图】", nr)  # raw 追加图注，供 digest/draft 使用

    def test_failure_returns_original(self):
        with workspace_tempdir("classmind_vis_") as tmp:
            assets = Path(tmp) / "assets"
            assets.mkdir()
            img = assets / "slide_03_fig1.png"
            _tiny_png(img)
            body = "![图](assets/slide_03_fig1.png)"
            raw = "x"
            nb, nr = caption_slide_images(body, raw, assets, FakeCaptioner(ok=False))
            self.assertEqual(nb, body)
            self.assertEqual(nr, raw)


if __name__ == "__main__":
    unittest.main()
