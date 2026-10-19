# -*- coding: utf-8 -*-
"""
滚动摘要生成器

为对话历史生成摘要，保留核心信息：
- 用户需求和意图
- 研究主题和方向
- 框架内容和修订
- 关键决策和结论

设计原则：
- 基于 role + content 字段（实际对话消息结构）
- 保留核心信息（研究主题、框架、用户需求）
- 摘要长度可控（默认 1000 字符）
"""

__all__ = ["RollingSummarizer"]

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class RollingSummarizer:
    """
    滚动摘要生成器

    核心功能：
    - 将对话历史压缩为精简摘要
    - 保留用户需求、研究主题、框架等核心信息
    - 支持增量摘要更新
    - 支持多个摘要合并

    设计目标：
    - 摘要长度可控（默认 1000 字符）
    - 保留关键信息（用户需求、研究主题、框架、决策）
    - 保持上下文连贯性
    """

    DEFAULT_SUMMARY_LENGTH = 1000

    KEY_TOPIC_INDICATORS = [
        "研究", "分析", "调查", "评估", "市场", "行业", "企业", "竞争",
        "research", "analysis", "market", "industry", "company", "competitive",
    ]

    KEY_DECISION_INDICATORS = [
        "确认", "同意", "决定", "选择", "修改", "增加", "删除", "调整",
        "confirm", "agree", "decide", "choose", "modify", "add", "remove", "adjust",
    ]

    def __init__(
        self,
        max_summary_length: int = DEFAULT_SUMMARY_LENGTH,
        preserve_key_points: bool = True,
    ):
        self.max_summary_length = max_summary_length
        self.preserve_key_points = preserve_key_points

    def summarize(self, history: List[Dict[str, Any]]) -> str:
        """
        生成对话历史摘要

        算法：
        1. 提取用户消息中的需求和意图
        2. 提取助手消息中的建议和框架
        3. 识别关键决策和确认
        4. 构建结构化摘要
        5. 截断到最大长度

        Args:
            history: 对话历史列表，每条包含 role, content, timestamp

        Returns:
            摘要文本
        """
        if not history:
            return ""

        user_messages = []
        assistant_messages = []
        decisions = []

        for msg in history:
            if msg.get("type") == "context_summary":
                continue
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not content:
                content = msg.get("summary", "")
            if not content and msg.get("state"):
                content = f"状态: {msg['state']}"
            if not content and msg.get("data"):
                content = str(msg["data"])
            if not content:
                continue

            if role == "user":
                user_messages.append(content)
                if self._contains_decision(content):
                    decisions.append(f"用户: {self._truncate(content, 100)}")
            else:
                assistant_messages.append(content)
                if self._contains_decision(content):
                    decisions.append(f"助手: {self._truncate(content, 100)}")

        summary_parts = []

        if user_messages:
            summary_parts.append("【用户需求】")
            for i, msg in enumerate(user_messages[:5]):
                summary_parts.append(f"  {i+1}. {self._truncate(msg, 150)}")
            if len(user_messages) > 5:
                summary_parts.append(f"  ...另有{len(user_messages) - 5}条用户消息")

        if assistant_messages:
            summary_parts.append("【助手回应要点】")
            for i, msg in enumerate(assistant_messages[:3]):
                summary_parts.append(f"  {i+1}. {self._truncate(msg, 200)}")
            if len(assistant_messages) > 3:
                summary_parts.append(f"  ...另有{len(assistant_messages) - 3}条助手消息")

        if decisions:
            summary_parts.append("【关键决策】")
            for d in decisions[:5]:
                summary_parts.append(f"  - {d}")

        summary = "\n".join(summary_parts)
        return self._truncate_summary(summary)

    def incremental_summarize(
        self,
        existing_summary: str,
        new_steps: List[Dict[str, Any]],
    ) -> str:
        """
        增量摘要生成

        在现有摘要基础上，添加新步骤的信息

        Args:
            existing_summary: 已有摘要
            new_steps: 新增步骤

        Returns:
            更新后的摘要
        """
        if not new_steps:
            return existing_summary

        new_summary = self.summarize(new_steps)
        if not new_summary:
            return existing_summary

        merged = existing_summary + "\n\n【新增内容】\n" + new_summary
        return self._truncate_summary(merged)

    def merge_summaries(self, summaries: List[str]) -> str:
        """
        合并多个摘要

        Args:
            summaries: 摘要列表

        Returns:
            合并后的摘要
        """
        if not summaries:
            return ""

        merged = "\n\n---\n\n".join(s for s in summaries if s)
        return self._truncate_summary(merged)

    def _contains_decision(self, text: str) -> bool:
        for indicator in self.KEY_DECISION_INDICATORS:
            if indicator in text.lower():
                return True
        return False

    def _truncate(self, text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."

    def _truncate_summary(self, summary: str) -> str:
        if len(summary) <= self.max_summary_length:
            return summary
        return summary[:self.max_summary_length - 3] + "..."
