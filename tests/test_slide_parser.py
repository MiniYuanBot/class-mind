"""P2 课件解析器单元测试（PPTX 真实样例 + PDF 运行时生成）。"""

import unittest
from pathlib import Path

from classmind.parsing.slide_parser import Slide2MDParser

from tests._util import TempInput, workspace_tempdir


class TestSlideParserPPTX(unittest.TestCase):
    def test_parse_demo_pptx(self):
        with TempInput() as inp, workspace_tempdir("classmind_out_") as out:
            pptx = next(p for p in inp.glob("*.pptx"))
            parsed = Slide2MDParser(Path(out)).parse(pptx)
        self.assertEqual(len(parsed.slides), 7)
        first = parsed.slides[0]
        self.assertIn("机器学习", first.title)
        # 页级锚点 + 标题
        self.assertIn("<!-- slide: id=1", parsed.slides_md)
        self.assertIn("## 梯度下降", parsed.slides_md)
        # 步骤拆解页产生 step 锚点
        self.assertIn("step=", parsed.slides_md)
        # 页面索引完整性
        self.assertEqual(len(parsed.index), 7)
        self.assertTrue(parsed.index[1].keywords)

    def test_parse_missing_file_raises(self):
        from classmind.errors import ParseError

        with self.assertRaises(ParseError):
            Slide2MDParser(Path(".")).parse(Path("no_such.pptx"))


class TestSlideParserPDF(unittest.TestCase):
    def _make_pdf(self, path: Path) -> None:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:  # pragma: no cover
            self.skipTest("reportlab 未安装")

        c = canvas.Canvas(str(path), pagesize=A4)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(72, 760, "Linear Regression")
        c.setFont("Helvetica", 12)
        c.drawString(72, 730, "y = w*x + b is the linear model.")
        c.drawString(72, 710, "Loss function: L(w) = sum (y_i - yhat_i)^2")
        c.showPage()
        c.setFont("Helvetica-Bold", 20)
        c.drawString(72, 760, "Gradient Descent")
        c.setFont("Helvetica", 12)
        c.drawString(72, 730, "w <- w - eta * dL/dw")
        c.drawString(72, 710, "learning rate eta controls step size.")
        c.save()

    def test_parse_pdf_pages(self):
        with workspace_tempdir("classmind_pdf_") as tmp:
            pdf = Path(tmp) / "lecture.pdf"
            self._make_pdf(pdf)
            parsed = Slide2MDParser(Path(tmp) / "assets").parse(pdf)
        self.assertGreaterEqual(len(parsed.slides), 2)
        titles = [s.title for s in parsed.slides]
        self.assertTrue(any("Regression" in t for t in titles))
        # 文本可提取（页 1 正文含模型表达式）
        raw = " ".join(s.raw_text for s in parsed.slides)
        self.assertIn("linear", raw.lower())


if __name__ == "__main__":
    unittest.main()
