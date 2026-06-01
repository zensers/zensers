"""
多源交叉验证测试 - TDD模式
测试 CrossValidator 类
"""

import pytest
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


class TestCrossValidator:
    """测试多源交叉验证器"""
    
    @pytest.fixture
    def validator(self):
        """创建验证器实例"""
        from src.core.harness.cross_validator import CrossValidator
        return CrossValidator()
    
    # ========== 基础验证测试 ==========
    
    def test_validate_single_source(self, validator):
        """测试单源验证 - 应该返回需要更多来源"""
        sources = [
            {"name": "艾瑞咨询", "value": "1.2万亿", "url": "https://www.iresearch.cn"}
        ]
        
        result = validator.validate(
            claim="2025年新能源汽车市场规模",
            sources=sources
        )
        
        assert result.status == "insufficient_sources"
        assert "至少需要2个来源" in result.message
    
    def test_validate_two_consistent_sources(self, validator):
        """测试两个一致来源 - 应该通过"""
        sources = [
            {"name": "艾瑞咨询", "value": "1.2万亿", "url": "https://www.iresearch.cn"},
            {"name": "中汽协", "value": "1.18万亿", "url": "https://www.caam.org.cn"}
        ]
        
        result = validator.validate(
            claim="2025年新能源汽车市场规模",
            sources=sources,
            tolerance=0.1  # 10% 容差
        )
        
        assert result.status == "verified"
        assert result.confidence == "high"
    
    def test_validate_inconsistent_sources(self, validator):
        """测试不一致来源 - 应该标记冲突"""
        sources = [
            {"name": "来源A", "value": "1.2万亿", "url": "https://source-a.com"},
            {"name": "来源B", "value": "0.5万亿", "url": "https://source-b.com"}  # 差异超过10%
        ]
        
        result = validator.validate(
            claim="2025年新能源汽车市场规模",
            sources=sources,
            tolerance=0.1
        )
        
        assert result.status == "inconsistent"
        assert len(result.conflicts) > 0
    
    def test_validate_three_sources_majority(self, validator):
        """测试三源验证 - 多数一致"""
        sources = [
            {"name": "来源A", "value": "1.2万亿", "url": "https://source-a.com"},
            {"name": "来源B", "value": "1.18万亿", "url": "https://source-b.com"},
            {"name": "来源C", "value": "1.22万亿", "url": "https://source-c.com"}
        ]
        
        result = validator.validate(
            claim="2025年新能源汽车市场规模",
            sources=sources,
            tolerance=0.1
        )
        
        assert result.status == "verified"
        assert result.confidence == "high"
    
    # ========== 数值一致性检查 ==========
    
    def test_check_numerical_consistency(self, validator):
        """测试数值一致性检查"""
        # 一致
        assert validator.check_numerical_consistency(
            ["1.2万亿", "1.18万亿", "1.22万亿"],
            tolerance=0.1
        ) is True
        
        # 不一致
        assert validator.check_numerical_consistency(
            ["1.2万亿", "0.5万亿"],
            tolerance=0.1
        ) is False
    
    def test_extract_numeric_value(self, validator):
        """测试数值提取"""
        assert validator.extract_numeric_value("1.2万亿") == 12000.0
        assert validator.extract_numeric_value("5000亿") == 5000.0
        assert validator.extract_numeric_value("35%") == 35.0
        assert validator.extract_numeric_value("1000万辆") == 1000.0
    
    # ========== 时间一致性检查 ==========
    
    def test_check_time_consistency(self, validator):
        """测试时间一致性检查"""
        # 一致
        sources = [
            {"time": "2025年"},
            {"time": "2025"},
            {"time": "2025年度"}
        ]
        assert validator.check_time_consistency(sources) is True
        
        # 不一致
        sources = [
            {"time": "2024年"},
            {"time": "2025年"}
        ]
        assert validator.check_time_consistency(sources) is False
    
    # ========== 验证报告 ==========
    
    def test_generate_validation_report(self, validator):
        """测试生成验证报告"""
        sources = [
            {"name": "艾瑞咨询", "value": "1.2万亿", "url": "https://www.iresearch.cn", "time": "2025年"},
            {"name": "中汽协", "value": "1.18万亿", "url": "https://www.caam.org.cn", "time": "2025年"}
        ]
        
        report = validator.generate_report(
            claim="2025年新能源汽车市场规模",
            sources=sources,
            tolerance=0.1
        )
        
        assert report["status"] == "verified"
        assert report["source_count"] == 2
        assert "numerical_consistency" in report["checks"]
        assert "time_consistency" in report["checks"]
    
    # ========== 置信度计算 ==========
    
    def test_calculate_confidence(self, validator):
        """测试置信度计算"""
        # 高置信度：多源一致 + 权威来源
        confidence = validator.calculate_confidence(
            source_count=3,
            consistency_score=0.95,
            source_tiers=["tier1", "tier1", "tier2"]
        )
        assert confidence == "high"
        
        # 中置信度：2源一致
        confidence = validator.calculate_confidence(
            source_count=2,
            consistency_score=0.90,
            source_tiers=["tier2", "tier2"]
        )
        assert confidence == "medium"
        
        # 低置信度：单源或冲突
        confidence = validator.calculate_confidence(
            source_count=1,
            consistency_score=1.0,
            source_tiers=["tier3"]
        )
        assert confidence == "low"
    
    # ========== 边界情况 ==========
    
    def test_validate_empty_sources(self, validator):
        """测试空来源列表"""
        result = validator.validate(
            claim="某个数据",
            sources=[]
        )
        
        assert result.status == "insufficient_sources"
    
    def test_validate_missing_value(self, validator):
        """测试缺少数值的来源"""
        sources = [
            {"name": "来源A", "url": "https://source-a.com"}  # 缺少 value
        ]
        
        result = validator.validate(
            claim="某个数据",
            sources=sources
        )
        
        assert result.status == "insufficient_sources"
    
    def test_validate_with_none_values(self, validator):
        """测试包含 None 值的来源"""
        sources = [
            {"name": "来源A", "value": "1.2万亿", "url": "https://source-a.com"},
            {"name": "来源B", "value": None, "url": "https://source-b.com"}
        ]
        
        result = validator.validate(
            claim="某个数据",
            sources=sources,
            tolerance=0.1
        )
        
        # 应该只使用有效来源
        assert result.status == "insufficient_sources"  # 只有1个有效来源