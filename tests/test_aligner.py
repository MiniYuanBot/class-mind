"""P4 对齐层单元测试（构造最小 Slides + Transcript）。"""

import unittest

from classmind.alignment.aligner import Aligner
from classmind.alignment.aligner import Aligner
from classmind.models import (
    Confidence,
    ParsedSlides,
    ProcessedTranscript,
    Slide,
    SlideIndexEntry,
    TopicSegment,
)


def _fake_slides() -> ParsedSlides:
    ps = ParsedSlides(source_file="demo")
    rows = [
        ("梯度下降（Gradient Descent）", "更新规则 w 减去学习率乘以梯度，沿下降最快方向"),
        ("反向传播（Backpropagation）", "从输出层向输入层传播误差，核心是链式法则"),
        ("损失函数（Loss Function）", "衡量模型预测与真实标签的差距"),
    ]
    for i, (title, raw) in enumerate(rows, start=1):
        ps.slides.append(Slide(index=i, title=title, raw_text=raw, body_md=raw))
        ps.index.append(SlideIndexEntry(page=i, title=title, keywords=["梯度", "反向传播", "损失"]))
    return ps


def _fake_transcript() -> ProcessedTranscript:
    texts = [
        "大家看第 2 页，梯度下降是沿着损失下降最快的方向更新参数。",
        "反向传播的核心是链式法则，注意，重点是把误差从输出层传回输入层。",
        "我们总结一下，损失函数用来衡量预测和真实标签的差距。",
        "今天天气不错，我们下课聊。",
    ]
    segs = [TopicSegment(index=i + 1, keywords=["梯度", "反向传播", "损失", "天气"], text=t) for i, t in enumerate(texts)]
    t = ProcessedTranscript(clean_text="\n".join(texts), topic_segments=segs)
    return t


class TestAligner(unittest.TestCase):
    def test_explicit_page_ref_and_keyword_alignment(self):
        res = Aligner().align(_fake_slides(), _fake_transcript())
        by_slide = {c.slide_id: c for c in res.chunks}
        self.assertIn(2, by_slide)
        self.assertEqual(by_slide[2].confidence, Confidence.HIGH)
        self.assertIn(3, by_slide)
        # 天气闲聊段未对齐
        self.assertTrue(res.unaligned_segments, "闲聊段应标记为未对齐")
        self.assertGreater(res.coverage, 0.5)
        # 每页只产出一个融合块
        self.assertLessEqual(len(res.chunks), 3)

    def test_empty_input_ok(self):
        res = Aligner().align(ParsedSlides(), ProcessedTranscript())
        self.assertEqual(res.chunks, [])
        self.assertEqual(res.coverage, 0.0)


if __name__ == "__main__":
    unittest.main()
