"""异常定义。"""

from __future__ import annotations


class ClassMindError(Exception):
    """所有 ClassMind 错误的基类。"""


class InputError(ClassMindError):
    """输入目录 / 文件层面错误。"""


class ParseError(ClassMindError):
    """解析失败（课件或讲述无法提取有效内容）。"""


class UnsupportedFormatError(InputError):
    """缺失可选依赖或格式不支持。"""


class AlignmentFailure(ClassMindError):
    """对齐阶段失败。"""


class PromptError(ClassMindError):
    """提示词模板问题。"""
