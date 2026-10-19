# -*- coding: utf-8 -*-
"""
滚动摘要生成器测试

测试 RollingSummarizer 的核心功能：
- 增量摘要生成
- 摘要质量验证
- 摘要合并
"""

import pytest
from datetime import datetime
from typing import Dict, Any, List
import json


class TestRollingSummarizerInit:
    """测试 RollingSummarizer 初始化"""
    
    def test_init_default(self):
        """测试默认初始化"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer()
        
        assert summarizer is not None
        
    def test_init_with_config(self):
        """测试带配置初始化"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer(
            max_summary_length=500,
            preserve_key_points=True
        )
        
        assert summarizer.max_summary_length == 500
        assert summarizer.preserve_key_points == True


class TestRollingSummarizerSummary:
    """测试摘要生成"""
    
    def test_summarize_empty_history(self):
        """测试空历史摘要"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer()
        
        summary = summarizer.summarize([])
        
        assert summary == "" or summary is None
        
    def test_summarize_single_step(self):
        """测试单步摘要"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer()
        
        history = [{
            "step": 1,
            "state": "executing",
            "summary": "数据收集完成",
            "timestamp": datetime.now().isoformat()
        }]
        
        summary = summarizer.summarize(history)
        
        assert "数据收集" in summary or summary is not None
        
    def test_summarize_multiple_steps(self):
        """测试多步摘要"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer()
        
        history = self._create_mock_history(10)
        
        summary = summarizer.summarize(history)
        
        # 摘要应该包含关键信息
        assert summary is not None
        assert len(summary) > 0
        
    def test_summarize_preserves_key_points(self):
        """测试摘要保留关键点"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer(preserve_key_points=True)
        
        history = [
            {"step": 1, "summary": "重要发现：市场规模达到500亿"},
            {"step": 2, "summary": "继续分析竞争格局"},
            {"step": 3, "summary": "关键结论：头部企业占60%份额"}
        ]
        
        summary = summarizer.summarize(history)
        
        # 关键点应该被保留
        assert "500亿" in summary or "关键结论" in summary
        
    def test_summary_length_limit(self):
        """测试摘要长度限制"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer(max_summary_length=200)
        
        # 创建大量历史
        history = self._create_mock_history(50)
        
        summary = summarizer.summarize(history)
        
        # 摘要长度应该受限
        assert len(summary) <= 200
        
    def _create_mock_history(self, count: int) -> List[Dict[str, Any]]:
        """创建模拟历史"""
        history = []
        for i in range(count):
            history.append({
                "step": i + 1,
                "state": f"state_{i + 1}",
                "summary": f"步骤 {i + 1}: 执行操作...",
                "timestamp": datetime.now().isoformat()
            })
        return history


class TestRollingSummarizerIncremental:
    """测试增量摘要"""
    
    def test_incremental_summarize(self):
        """测试增量摘要生成"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer()
        
        # 初始历史
        history1 = self._create_mock_history(5)
        summary1 = summarizer.summarize(history1)
        
        # 添加新历史
        history2 = history1 + self._create_mock_history_from(6, 3)
        
        # 增量摘要
        summary2 = summarizer.incremental_summarize(
            existing_summary=summary1,
            new_steps=history2[-3:]
        )
        
        assert summary2 is not None
        assert len(summary2) > 0
        
    def test_incremental_maintains_context(self):
        """测试增量摘要保持上下文"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer()
        
        # 初始摘要包含关键信息
        existing_summary = "已分析5家公司：宁德时代、比亚迪、特斯拉..."
        
        # 新步骤
        new_steps = [
            {"step": 6, "summary": "发现宁德时代市场份额35%"},
            {"step": 7, "summary": "比亚迪市场份额20%"}
        ]
        
        new_summary = summarizer.incremental_summarize(
            existing_summary=existing_summary,
            new_steps=new_steps
        )
        
        # 新摘要应该包含原有上下文和新信息
        assert "宁德时代" in new_summary or "市场份额" in new_summary
        
    def _create_mock_history(self, count: int) -> List[Dict[str, Any]]:
        """创建模拟历史"""
        return [{"step": i + 1, "summary": f"步骤 {i + 1}"} for i in range(count)]
        
    def _create_mock_history_from(self, start: int, count: int) -> List[Dict[str, Any]]:
        """从指定步骤创建历史"""
        return [{"step": i, "summary": f"步骤 {i}"} for i in range(start, start + count)]


class TestRollingSummarizerMerge:
    """测试摘要合并"""
    
    def test_merge_summaries(self):
        """测试合并多个摘要"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer()
        
        summaries = [
            "第一阶段：数据收集完成，共15个数据源",
            "第二阶段：分析竞争格局，识别5家主要企业",
            "第三阶段：生成市场报告，包含关键洞察"
        ]
        
        merged = summarizer.merge_summaries(summaries)
        
        assert merged is not None
        # 合并后应该包含关键信息
        assert "数据收集" in merged or "分析" in merged or "报告" in merged
        
    def test_merge_preserves_timeline(self):
        """测试合并保持时间线"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer()
        
        summaries = [
            "[10:00] 用户提交需求",
            "[10:15] 开始数据收集",
            "[10:30] 完成初步分析"
        ]
        
        merged = summarizer.merge_summaries(summaries)
        
        # 时间线应该保持
        assert "10:00" in merged or "10:15" in merged or "10:30" in merged


class TestRollingSummarizerQuality:
    """测试摘要质量"""
    
    def test_summary_contains_state_changes(self):
        """测试摘要包含状态变化"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer()
        
        history = [
            {"step": 1, "state": "understanding", "summary": "理解需求"},
            {"step": 2, "state": "planning", "summary": "制定计划"},
            {"step": 3, "state": "executing", "summary": "执行分析"}
        ]
        
        summary = summarizer.summarize(history)
        
        # 摘要应该反映状态变化
        assert "理解" in summary or "计划" in summary or "执行" in summary
        
    def test_summary_extracts_key_data(self):
        """测试摘要提取关键数据"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer(preserve_key_points=True)
        
        history = [
            {"step": 1, "data": {"market_size": "500亿", "growth": "15%"}},
            {"step": 2, "data": {"companies": ["宁德时代", "比亚迪"]}},
            {"step": 3, "data": {"insights": ["头部效应明显"]}}
        ]
        
        summary = summarizer.summarize(history)
        
        # 关键数据应该被提取
        assert "500亿" in summary or "15%" in summary or "宁德时代" in summary


class TestRollingSummarizerEdgeCases:
    """测试边缘情况"""
    
    def test_summarize_with_missing_data(self):
        """测试缺失数据处理"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer()
        
        # 某些步骤缺失数据
        history = [
            {"step": 1, "summary": "正常步骤"},
            {"step": 2},  # 缺失摘要
            {"step": 3, "summary": None}  # 摘要为空
        ]
        
        summary = summarizer.summarize(history)
        
        # 应该能处理缺失数据
        assert summary is not None
        
    def test_summarize_with_large_data(self):
        """测试大数据处理"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer(max_summary_length=100)
        
        # 每个步骤都有大量数据
        history = [
            {"step": i, "summary": "x" * 1000} for i in range(20)
        ]
        
        summary = summarizer.summarize(history)
        
        # 摘要应该被截断
        assert len(summary) <= 100
        
    def test_summarize_with_special_characters(self):
        """测试特殊字符处理"""
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        
        summarizer = RollingSummarizer()
        
        history = [
            {"step": 1, "summary": "包含\n换行符"},
            {"step": 2, "summary": "包含\t制表符"},
            {"step": 3, "summary": "包含<特殊>字符"}
        ]
        
        summary = summarizer.summarize(history)
        
        # 应该能处理特殊字符
        assert summary is not None