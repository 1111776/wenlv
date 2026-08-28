"""网页有害内容过滤（说明书 13.3 / S30：与注入防御独立）。

职责：识别并过滤违法/色情/暴力等有害内容，命中则不进上下文、不进报告。
与 PromptInjectionDetector 分开，各自独立判定。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SafetyVerdict:
    """有害内容判定结果。"""

    blocked: bool = False
    category: str | None = None
    snippet: str = ""


# 有害内容关键词规则（MVP 用关键词规则，可替换为分类模型）
_SAFETY_RULES: list[tuple[str, re.Pattern]] = [
    ("违法", re.compile(r"(毒品|枪支|违禁品|洗钱|诈骗)", re.I)),
    ("色情", re.compile(r"(色情|淫秽|裸照|成人视频)", re.I)),
    ("暴力", re.compile(r"(血腥|暴力恐怖|袭击策划)", re.I)),
    ("赌博", re.compile(r"(赌博|博彩|赌场)", re.I)),
]


class ContentSafetyFilter:
    """有害内容过滤器（无状态）。"""

    def check(self, text: str) -> SafetyVerdict:
        """检查文本是否含有害内容。"""
        if not text:
            return SafetyVerdict()
        for category, pattern in _SAFETY_RULES:
            m = pattern.search(text)
            if m:
                s = max(0, m.start() - 40)
                return SafetyVerdict(
                    blocked=True,
                    category=category,
                    snippet=text[s : s + 100],
                )
        return SafetyVerdict()
