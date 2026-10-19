# -*- coding: utf-8 -*-
"""
质量控制模块测试
================

测试质量控制模块的各个组件：
1. QualityMetadataExtractor - 元数据提取
2. QualityChecker - 质量检查器
3. QualityFeedbackExecutor - 反馈执行器
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any

from src.core.quality import (
    QualityMetadataExtractor,
    QualityMetadata,
    QualityCheckerBase,
    QualityResult,
    DataCollectionQualityChecker,
    AnalysisQualityChecker,
    ReportQualityChecker,
    QualityFeedbackExecutor,
    AttemptRecord,
)


class TestQualityMetadataExtractor:
    """测试质量元数据提取器"""
    
    def test_extract_basic(self):
        """测试基本提取"""
        extractor = QualityMetadataExtractor()
        
        raw_output = {
            "results": [
                {"title": "测试结果1", "url": "https://gov.cn/test"},
                {"title": "测试结果2", "url": "https://example.com/test"},
            ],
            "quality_score": 80,
        }
        
        metadata = extractor.extract(raw_output, skill_name="test_skill")
        
        assert metadata.quality_score == 80
        assert metadata.data_volume == 2
        assert len(metadata.sources) == 2
        assert metadata.skill_name == "test_skill"
    
    def test_extract_credibility(self):
        """测试来源可信度判断"""
        extractor = QualityMetadataExtractor()
        
        raw_output = {
            "results": [
                {"url": "https://gov.cn/policy"},
                {"url": "https://reuters.com/news"},
                {"url": "https://blog.example.com/post"},
            ],
        }
        
        metadata = extractor.extract(raw_output)
        
        # gov.cn 应该是 tier1
        assert any(s.credibility == "tier1" for s in metadata.sources)
        # reuters 应该是 tier2
        assert any(s.credibility == "tier2" for s in metadata.sources)
        # blog 应该是 tier3
        assert any(s.credibility == "tier3" for s in metadata.sources)
    
    def test_extract_empty(self):
        """测试空数据提取"""
        extractor = QualityMetadataExtractor()
        
        metadata = extractor.extract({}, skill_name="empty")
        
        assert metadata.quality_score == 50  # 默认值
        assert metadata.data_volume == 0
        assert len(metadata.sources) == 0


class TestQualityCheckers:
    """测试质量检查器"""
    
    def test_data_collection_checker_pass(self):
        """测试数据收集检查器 - 通过"""
        checker = DataCollectionQualityChecker(threshold=70)
        
        data = {
            "quality_metadata": {
                "quality_score": 80,
                "data_volume": 10,
                "sources": [
                    {"url": "https://gov.cn/test", "credibility": "tier1"},
                ],
            }
        }
        
        result = checker.check(data)
        
        assert result.checker_type == "data_collection"
        assert result.threshold == 70
        assert result.passed is True
        assert result.score >= 70
    
    def test_data_collection_checker_fail(self):
        """测试数据收集检查器 - 不通过"""
        checker = DataCollectionQualityChecker(threshold=70)
        
        data = {
            "quality_metadata": {
                "quality_score": 40,
                "data_volume": 1,
                "sources": [],
            }
        }
        
        result = checker.check(data)
        
        assert result.passed is False
        assert len(result.issues) > 0
        assert len(result.suggestions) > 0
    
    def test_analysis_checker(self):
        """测试分析检查器"""
        checker = AnalysisQualityChecker(threshold=70)
        
        data = {
            "insights": [
                {"title": "洞察1", "data_reference": "ref1"},
                {"title": "洞察2", "data_reference": None},  # 无支撑
            ],
            "deep_analysis": True,
        }
        
        result = checker.check(data)
        
        assert result.checker_type == "analysis"
        assert result.details["unsupported_insights"] == 1
    
    def test_report_checker(self):
        """测试报告检查器"""
        checker = ReportQualityChecker(threshold=80)
        
        data = {
            "report_data": {
                "sections": [
                    {"id": "executive_summary", "title": "执行摘要", "content": "内容...", "data_references": ["ref1"]},
                    {"id": "market_overview", "title": "市场概况", "content": "内容...", "data_references": ["ref2"]},
                    {"id": "market_size", "title": "市场规模", "content": "内容...", "data_references": []},
                ],
            }
        }
        
        result = checker.check(data)
        
        assert result.checker_type == "report"
        assert result.details["sections_count"] == 3


class TestQualityFeedbackExecutor:
    """测试反馈执行器"""
    
    @pytest.mark.asyncio
    async def test_execute_pass_first_try(self):
        """测试第一次就通过"""
        executor = QualityFeedbackExecutor(max_retries=3)
        checker = DataCollectionQualityChecker(threshold=70)
        
        async def execute_func(context):
            return {
                "quality_metadata": {
                    "quality_score": 80,
                    "data_volume": 10,
                    "sources": [{"url": "https://test.com", "credibility": "tier1"}],
                }
            }
        
        data, result = await executor.execute_with_retry(
            stage="data_collection",
            execute_func=execute_func,
            checker=checker,
            context={},
        )
        
        assert result.passed is True
        assert len(executor.get_attempts("data_collection")) == 1
    
    @pytest.mark.asyncio
    async def test_execute_retry_then_pass(self):
        """测试重试后通过"""
        executor = QualityFeedbackExecutor(max_retries=3)
        checker = DataCollectionQualityChecker(threshold=70)
        
        call_count = 0
        
        async def execute_func(context):
            nonlocal call_count
            call_count += 1
            
            # 第一次失败，第二次通过
            if call_count == 1:
                return {
                    "quality_metadata": {
                        "quality_score": 50,
                        "data_volume": 1,
                        "sources": [],
                    }
                }
            else:
                return {
                    "quality_metadata": {
                        "quality_score": 80,
                        "data_volume": 10,
                        "sources": [{"url": "https://test.com", "credibility": "tier1"}],
                    }
                }
        
        data, result = await executor.execute_with_retry(
            stage="data_collection",
            execute_func=execute_func,
            checker=checker,
            context={},
        )
        
        assert result.passed is True
        assert len(executor.get_attempts("data_collection")) == 2
    
    @pytest.mark.asyncio
    async def test_execute_best_effort(self):
        """测试使用最佳结果"""
        executor = QualityFeedbackExecutor(max_retries=2, min_data_volume=3)
        checker = DataCollectionQualityChecker(threshold=80)  # 高阈值
        
        async def execute_func(context):
            return {
                "quality_metadata": {
                    "quality_score": 65,  # 低于阈值但有数据
                    "data_volume": 5,
                    "sources": [{"url": "https://test.com", "credibility": "tier2"}],
                }
            }
        
        data, result = await executor.execute_with_retry(
            stage="data_collection",
            execute_func=execute_func,
            checker=checker,
            context={},
        )
        
        # 应该使用最佳结果输出
        assert data.get("quality_note") is not None
        assert "低于阈值" in data["quality_note"]["message"]
    
    @pytest.mark.asyncio
    async def test_execute_degrade(self):
        """测试降级处理"""
        executor = QualityFeedbackExecutor(max_retries=2, min_data_volume=3)
        checker = DataCollectionQualityChecker(threshold=70)
        
        async def execute_func(context):
            return {
                "quality_metadata": {
                    "quality_score": 30,
                    "data_volume": 0,  # 无数据
                    "sources": [],
                }
            }
        
        data, result = await executor.execute_with_retry(
            stage="data_collection",
            execute_func=execute_func,
            checker=checker,
            context={},
        )
        
        # 应该降级
        assert data.get("degraded") is True
        assert data.get("reason") == "数据不足"


class TestQualityConfig:
    """测试质量配置"""
    
    def test_config_loading(self):
        """测试配置加载"""
        from src.config.settings import settings
        
        # 检查质量配置是否存在
        assert hasattr(settings, 'quality')
        assert settings.quality.threshold_data_collection == 70
        assert settings.quality.threshold_analysis == 70
        assert settings.quality.threshold_report == 80
        assert settings.quality.max_retries == 3
    
    def test_get_threshold(self):
        """测试获取阈值"""
        from src.config.settings import settings
        
        assert settings.quality.get_threshold("data_collection") == 70
        assert settings.quality.get_threshold("analysis") == 70
        assert settings.quality.get_threshold("report") == 80
        assert settings.quality.get_threshold("unknown") == 70  # 默认值


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
