"""Demo package generator: writes a small sample course into a directory.

Content: "Introduction to Machine Learning", Lecture 2 "Backpropagation & Gradient Descent" (theory type)
  - slides_backpropagation.pptx  (7 slides, one page demonstrates step splitting)
  - transcript_backpropagation.docx (timestamps / filler words / emphasis cues / a student question)
  - meta.json                    (course metadata)
"""

from __future__ import annotations

import json
from pathlib import Path

PPTX_SLIDES = [
    {
        "title": "机器学习基础回顾（Linear Regression Recap）",
        "body": [
            "目标：从数据中学习输入到输出的映射 f(x; w)",
            "- 线性模型：y = w·x + b",
            "- 损失函数（Loss Function）：L(w) = (1/n)·Σ (y_i - ŷ_i)²",
            "- 训练：寻找使 L(w) 最小的参数 w",
        ],
        "notes": "本节假设学生已掌握线性代数基础，重点是引出优化问题。",
    },
    {
        "title": "梯度下降（Gradient Descent）",
        "body": [
            "核心思想：沿损失函数下降最快的方向更新参数",
            "- 更新规则：w ← w - η·∂L/∂w",
            "- η（学习率 Learning Rate）：控制每步步长",
            "- 收敛条件：梯度接近 0 或达到最大迭代次数",
        ],
        "notes": "强调学习率是超参数（Hyperparameter），过大会震荡不收敛。",
    },
    {
        "title": "链式法则（Chain Rule）",
        "body": [
            "复合函数求导的核心工具",
            "- 若 z = f(y)，y = g(x)，则 ∂z/∂x = ∂z/∂y · ∂y/∂x",
            "- 意义：把复杂函数逐层分解为简单函数的乘积",
        ],
        "notes": "易错点：忘记中间变量 y 的梯度连接。",
    },
    {
        "title": "反向传播（Backpropagation）",
        "body": [
            "核心思想：从输出层出发，把误差逐层向输入方向传播",
            "- 输出层先算损失对输出的梯度",
            "- 利用链式法则回传误差到每一层的参数",
            "- 复杂度：一次前向 + 一次反向，远小于数值差分",
        ],
        "notes": "注意：反向传播不是新优化算法，而是高效计算梯度的方法。",
    },
    {
        "title": "示例：单神经元网络",
        "body": [
            "步骤 1：前向传播，计算预测与损失",
            "步骤 2：按链式法则求 ∂L/∂w 与 ∂L/∂b",
            "步骤 3：用梯度下降更新参数 w ← w - η·∂L/∂w",
            "步骤 4：重复直到损失收敛",
            "- 例题：给定单个样本 (x=2, y=3)，w=1，η=0.5，求一步更新后的 w",
        ],
        "notes": "板书推导可参考：L=(y-wx)²，∂L/∂w=-2x(y-wx)。",
    },
    {
        "title": "常见问题与易错点（Common Pitfalls）",
        "body": [
            "- 易错点 1：学习率过大导致震荡不收敛",
            "- 易错点 2：忘记对 w 和 b 分别求梯度",
            "- 易错点 3：把梯度方向当上升方向（应为下降）",
            "- 注意：梯度消失（Gradient Vanishing）问题将在深层网络中讨论",
        ],
        "notes": "",
    },
    {
        "title": "本节小结（Summary）",
        "body": [
            "- 损失函数量化预测误差",
            "- 梯度下降利用一阶导数迭代优化",
            "- 链式法则是反向传播的数学基础",
            "- 反向传播高效计算深度模型的梯度",
        ],
        "notes": "",
    },
]

TRANSCRIPT_PARAGRAPHS = [
    "[00:00:02] 教师：好，同学们，我们开始上课。这节课我们继续讲机器学习，重点是反向传播算法，嗯大家先看第 1 页，回顾一下线性回归。",
    "[00:00:40] 教师：我们我们回忆一下，线性模型就是 y 等于 w 乘 x 加 b，那么损失函数呢，衡量模型预测和真实值的差距，啊本质上就是一个优化问题。",
    "[00:01:20] 学生：老师，损失函数为什么用平方误差而不是绝对误差？",
    "[00:01:45] 教师：好问题。平方误差处处可导，方便用梯度方法优化，这个后面你会更清楚。",
    "[00:02:10] 教师：接下来看第 2 页，梯度下降。核心思想就是沿着损失下降最快的方向走，更新规则是 w 减去 eta 乘以损失对 w 的偏导。",
    "[00:03:00] 教师：注意，学习率 eta 非常重要，重点强调，它是我们手动设置的超参数，太大会震荡，太小收敛慢。",
    "[00:04:05] 教师：下面我们看第 3 页，链式法则。复合函数求导，z 对 x 的导数等于 z 对 y 的导数乘以 y 对 x 的导数，这就是反向传播的数学基础。",
    "[00:05:00] 教师：易错点是大家经常会忘记中间变量，求导的时候丢掉一环，这个考试会考，一定要记住。",
    "[00:06:00] 教师：接下来我们进入重点，看第 4 页，反向传播。它的核心思想是从输出层开始，把误差逐层向输入方向传播。",
    "[00:07:10] 教师：注意，反向传播不是一个新的优化算法，它只是高效计算梯度的方法，这个区分很关键，很多同学会混淆。",
    "[00:08:20] 教师：好，现在我们看第 5 页，用一个单神经元网络的例子走一遍完整流程。步骤一前向传播算损失，步骤二用链式法则求梯度，步骤三梯度下降更新参数，步骤四重复直到收敛。",
    "[00:10:00] 教师：我们来做一道例题：给定样本 x 等于 2，y 等于 3，初始权重 w 等于 1，学习率 0.5，求一步更新之后的 w。先算损失对 w 的梯度，负 2 乘 x 乘括号 y 减 w x，代入得负 4，然后 w 更新为 1 减 0.5 乘负 4 等于 3。",
    "[00:12:30] 教师：同学们注意，这里容易出错的地方就是把梯度方向搞反，梯度下降一定是往负梯度方向走。",
    "[00:13:40] 教师：然后看第 6 页，常见问题。学习率过大会震荡不收敛，这个实验中你们会亲眼看到。",
    "[00:15:00] 学生：老师，梯度消失是什么意思？",
    "[00:15:32] 教师：梯度消失指的是深层网络中，误差传到前面几层的时候梯度变得非常小，几乎没法更新，我们会在后面章节专门讨论，现在先记住这个概念。",
    "[00:17:00] 教师：最后我们总结一下，看第 7 页。损失函数量化误差，梯度下降迭代优化，链式法则提供数学基础，反向传播高效求梯度。",
    "[00:18:20] 教师：今天的重点就是反向传播和梯度下降的关系，课后请大家完成练习：推导两层网络的梯度更新公式。",
]


def generate_demo_input(input_dir: Path) -> Path:
    """Write sample slides + transcript + meta into `input_dir`, return the directory."""
    input_dir = Path(input_dir)
    input_dir.mkdir(parents=True, exist_ok=True)
    _make_pptx(input_dir / "slides_backpropagation.pptx")
    _make_docx(input_dir / "transcript_backpropagation.docx")
    meta = {
        "course": "机器学习导论",
        "instructor": "王教授",
        "chapter_no": "2",
        "chapter_title": "反向传播与梯度下降",
        "subject": "人工智能 / 机器学习",
        "course_type": "theory",
    }
    (input_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return input_dir


def _make_pptx(path: Path) -> None:
    from pptx import Presentation
    from pptx.util import Emu, Pt

    prs = Presentation()
    prs.slide_width = Emu(12192000)  # 13.33in 16:9
    prs.slide_height = Emu(6858000)
    blank = prs.slide_layouts[6]
    for i, slide_cfg in enumerate(PPTX_SLIDES, start=1):
        slide = prs.slides.add_slide(blank)
        # 标题
        tb_title = slide.shapes.add_textbox(Emu(457200), Emu(228600), Emu(11277600), Emu(762000))
        tf = tb_title.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = slide_cfg["title"]
        r.font.size = Pt(30)
        r.font.bold = True
        # 正文
        tb_body = slide.shapes.add_textbox(Emu(685800), Emu(1219200), Emu(10515600), Emu(4876800))
        tf2 = tb_body.text_frame
        tf2.word_wrap = True
        first = True
        for line in slide_cfg["body"]:
            para = tf2.paragraphs[0] if first else tf2.add_paragraph()
            first = False
            para.text = line
            para.space_after = Pt(8)
            for run in para.runs:
                run.font.size = Pt(18 if not line.startswith(("步骤", "例题")) else 20)
        if slide_cfg.get("notes"):
            slide.notes_slide.notes_text_frame.text = slide_cfg["notes"]
    prs.save(str(path))


def _make_docx(path: Path) -> None:
    from docx import Document

    doc = Document()
    doc.add_heading("课堂讲述转录：反向传播与梯度下降", level=0)
    for para in TRANSCRIPT_PARAGRAPHS:
        doc.add_paragraph(para)
    doc.save(str(path))
