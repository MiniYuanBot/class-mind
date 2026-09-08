"""P3 讲述处理器单元测试。"""

import unittest

from classmind.parsing.transcript_processor import (
    TranscriptProcessor,
    _classify_speaker,
    _denoise,
    _extract_timestamp,
)

from tests._util import SAMPLE_TRANSCRIPT_TXT


class TestTranscriptProcessor(unittest.TestCase):
    def test_denoise_removes_fillers_and_duplicates(self):
        noisy = "嗯那个那个，我们我们来看一下这个哈希表对吧，它本质上就是就是键值对。"
        cleaned = _denoise(noisy)
        self.assertNotIn("嗯", cleaned)
        self.assertNotIn("对吧", cleaned)
        self.assertNotIn("我们我们", cleaned)
        self.assertIn("哈希表", cleaned)

    def test_classify_speaker(self):
        who_t, content_t = _classify_speaker("教师：我们开始讲反向传播")
        self.assertEqual(who_t, "teacher")
        who_s, content_s = _classify_speaker("学生：为什么用平方误差？")
        self.assertEqual(who_s, "student")
        who_plain, _ = _classify_speaker("损失函数衡量预测误差")
        self.assertEqual(who_plain, "teacher")

    def test_timestamp_extraction(self):
        self.assertEqual(_extract_timestamp("[00:15:32] 教师：看第 4 页"), "00:15:32")
        self.assertEqual(_extract_timestamp("00:01:05 接下来看第 2 页"), "00:01:05")
        self.assertIsNone(_extract_timestamp("我们开始上课"))

    def test_process_text_full(self):
        proc = TranscriptProcessor()
        res = proc.process_text(SAMPLE_TRANSCRIPT_TXT)
        # 学生提问被保留为引用块、非教学噪音被剔除
        self.assertIn("> 学生提问：", res.clean_md)
        self.assertIn("学生提问：老师，哈希表的查找复杂度是多少？".split("学生提问：")[1].strip(), res.clean_md)
        # 去噪成功：教师旁白保留
        self.assertIn("哈希表", res.clean_text)
        self.assertNotIn("对吧", res.clean_text)
        # 重点与易错点标记
        self.assertIn("**重点**", res.clean_md)
        self.assertIn("**易错点**", res.clean_md)
        self.assertTrue(res.highlights, "应识别出重点标记")
        # 时间戳锚点保留
        self.assertIn("<!-- timestamp:", res.clean_md)
        # 话题分段非空且带关键词
        self.assertTrue(len(res.topic_segments) >= 2)
        self.assertTrue(all(sg.keywords for sg in res.topic_segments))


if __name__ == "__main__":
    unittest.main()
