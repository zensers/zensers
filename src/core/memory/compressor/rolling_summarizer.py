# -*- coding: utf-8 -*-
"""
滚动摘要生成器

实现 Layer 2 工作上下文的摘要生成功能：
- 增量摘要生成
- 关键点提取
- 摘要合并

设计参考：CONTEXT_COMPRESSION.md 第 3.4 节差分压缩算法
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
    - 将历史步骤压缩为精简摘要
    - 提取关键点和重要信息
    - 支持增量摘要更新
    - 支持多个摘要合并
    
    设计目标：
    - 摘要长度可控（默认 500 字符）
    - 保留关键信息（数值、结论、决策）
    - 保持上下文连贯性
    
    参考：Claude Code 的历史压缩策略
    """
    
    # 默认配置
    DEFAULT_SUMMARY_LENGTH = 500       # 默认摘要长度
    DEFAULT_PRESERVE_KEY_POINTS = True # 默认保留关键点
    
    # 关键信息提取模式
    KEY_POINT_PATTERNS = [
        "重要结论",
        "关键发现",
        "市场规模",
        "增长率",
        "市场份额",
        "主要企业",
        "竞争格局",
        "投资机会",
        "政策影响",
        "数据来源"
    ]
    
    def __init__(
        self,
        max_summary_length: int = DEFAULT_SUMMARY_LENGTH,
        preserve_key_points: bool = DEFAULT_PRESERVE_KEY_POINTS
    ):
        """
        初始化滚动摘要生成器
        
        Args:
            max_summary_length: 最大摘要长度（字符）
            preserve_key_points: 是否保留关键点
        """
        self.max_summary_length = max_summary_length
        self.preserve_key_points = preserve_key_points
        
        logger.info(
            f"RollingSummarizer initialized: "
            f"max_length={max_summary_length}, preserve_keys={preserve_key_points}"
        )
    
    # ========== 摘要生成接口 ==========
    
    def summarize(
        self, 
        history: List[Dict[str, Any]]
    ) -> str:
        """
        生成历史摘要
        
        算法：
        1. 提取每个步骤的摘要/关键信息
        2. 合并关键点
        3. 去除冗余信息
        4. 截断到最大长度
        
        Args:
            history: 历史记录列表
            
        Returns:
            摘要文本
        """
        if not history:
            return ""
        
        # 提取各步骤的关键信息
        key_info = self._extract_key_info(history)
        
        # 构建摘要
        summary = self._build_summary(key_info)
        
        # 截断到最大长度
        summary = self._truncate_summary(summary)
        
        return summary
    
    def incremental_summarize(
        self,
        existing_summary: str,
        new_steps: List[Dict[str, Any]]
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
        
        # 提取新步骤的关键信息
        new_info = self._extract_key_info(new_steps)
        
        # 合并到现有摘要
        merged = self._merge_summary_with_new_info(existing_summary, new_info)
        
        # 截断到最大长度
        summary = self._truncate_summary(merged)
        
        return summary
    
    def merge_summaries(
        self, 
        summaries: List[str]
    ) -> str:
        """
        合并多个摘要
        
        Args:
            summaries: 摘要列表
            
        Returns:
            合并后的摘要
        """
        if not summaries:
            return ""
        
        # 直接合并，保留分隔
        merged = " | ".join(summaries)
        
        # 截断到最大长度
        summary = self._truncate_summary(merged)
        
        return summary
    
    # ========== 私有方法 ==========
    
    def _extract_key_info(
        self, 
        history: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        提取历史中的关键信息
        
        Args:
            history: 历史记录
            
        Returns:
            关键信息列表
        """
        key_info = []
        
        for step in history:
            info = {
                "step": step.get("step", 0),
                "state": step.get("state", ""),
                "timestamp": step.get("timestamp", ""),
            }
            
            # 提取摘要文本
            if "summary" in step:
                info["summary"] = step["summary"]
            
            # 提取关键数据点
            if "data" in step:
                data = step["data"]
                # 尝试提取数值型数据
                for key, value in data.items():
                    if isinstance(value, (int, float, str)):
                        info[f"data_{key}"] = value
            
            # 标记是否包含关键点
            if self.preserve_key_points:
                step_text = step.get("summary", "") + " " + str(step.get("data", {}))
                info["is_key_point"] = self._is_key_point(step_text)
            
            key_info.append(info)
        
        return key_info
    
    def _is_key_point(self, text: str) -> bool:
        """
        判断文本是否包含关键点
        
        Args:
            text: 文本内容
            
        Returns:
            是否为关键点
        """
        for pattern in self.KEY_POINT_PATTERNS:
            if pattern in text:
                return True
        return False
    
    def _build_summary(
        self, 
        key_info: List[Dict[str, Any]]
    ) -> str:
        """
        构建摘要文本
        
        Args:
            key_info: 关键信息列表
            
        Returns:
            摘要文本
        """
        if not key_info:
            return ""
        
        # 分类处理：关键点 vs 普通信息
        key_points = []
        normal_info = []
        
        for info in key_info:
            if info.get("is_key_point"):
                key_points.append(info)
            else:
                normal_info.append(info)
        
        # 优先保留关键点
        summary_parts = []
        
        if key_points:
            # 关键点：保留完整信息
            for kp in key_points[:5]:  # 最多保留5个关键点
                if "summary" in kp:
                    summary_parts.append(kp["summary"])
        
        if normal_info:
            # 普通信息：保留步骤概览
            step_range = f"步骤 {normal_info[0].get('step', 1)}-{normal_info[-1].get('step', len(normal_info))}"
            summary_parts.append(step_range)
            
            # 提取状态变化概要
            states = set(info.get("state", "") for info in normal_info if info.get("state"))
            if states:
                summary_parts.append(f"状态: {', '.join(states)}")
        
        # 构建摘要
        summary = "; ".join(summary_parts)
        
        return summary
    
    def _merge_summary_with_new_info(
        self, 
        existing_summary: str, 
        new_info: List[Dict[str, Any]]
    ) -> str:
        """
        合并现有摘要和新信息
        
        Args:
            existing_summary: 现有摘要
            new_info: 新信息
            
        Returns:
            合合后的摘要
        """
        # 提取新信息的关键点
        new_key_points = []
        for info in new_info:
            if info.get("is_key_point") and "summary" in info:
                new_key_points.append(info["summary"])
        
        # 合合
        if new_key_points:
            merged = existing_summary + " + " + "; ".join(new_key_points[:3])
        else:
            # 无新关键点，仅添加步骤数
            step_count = len(new_info)
            merged = existing_summary + f" (+{step_count}步)"
        
        return merged
    
    def _truncate_summary(self, summary: str) -> str:
        """
        截断摘要到最大长度
        
        Args:
            summary: 摘要文本
            
        Returns:
            截断后的摘要
        """
        if len(summary) <= self.max_summary_length:
            return summary
        
        # 截断并添加省略号
        truncated = summary[:self.max_summary_length - 3] + "..."
        
        return truncated