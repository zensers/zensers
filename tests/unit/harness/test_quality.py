"""
质量闸门测试 - TDD模式
测试 QualityGate 和 ConfidenceGrader
"""

import pytest
from datetime import datetime
from pathlib import Path
import tempfile
import shutil


class TestConfidenceGrader:
    """测试置信度分级器"""
    
    @pytest.fixture
    def grader(self):
        """创建分级器实例"""
        from src.core.harness.quality import ConfidenceGrader
        return ConfidenceGrader()
    
    def test_grade_high_confidence(self, grader):
        """测试高置信度分级"""
        result = grader.grade(
            has_source=True,
            source_tier="tier1",
            cross_verified=True,
            data_fresh_days=5
        )
        assert result["level"] == "high"
        assert result["score"] >= 80
    
    def test_grade_medium_confidence(self, grader):
        """测试中置信度分级"""
        result = grader.grade(
            has_source=True,
            source_tier="tier2",
            cross_verified=False,
            data_fresh_days=15
        )
        assert result["level"] == "medium"
        assert 40 <= result["score"] < 80
    
    def test_grade_low_confidence(self, grader):
        """测试低置信度分级"""
        result = grader.grade(
            has_source=True,
            source_tier=None,  # 无来源等级
            cross_verified=False,
            data_fresh_days=100
        )
        # 实际计算：有来源(20) + 无等级(0) + 未验证(0) + 旧数据(0) = 20
        # 20分对应 "low" 级别
        assert result["level"] == "low"
        assert 20 <= result["score"] < 40
    
    def test_grade_unverified(self, grader):
        """测试未验证分级"""
        result = grader.grade(
            has_source=False,
            source_tier=None,
            cross_verified=False,
            data_fresh_days=100
        )
        assert result["level"] == "unverified"
        assert result["score"] < 20
    
    def test_grade_with_explicit_score(self, grader):
        """测试使用显式分数"""
        result = grader.grade(explicit_score=85)
        assert result["level"] == "high"
        assert result["score"] == 85


class TestQualityGate:
    """测试质量闸门"""
    
    @pytest.fixture
    def gate(self):
        """创建质量闸门实例"""
        from src.core.harness.quality import QualityGate
        return QualityGate()
    
    def test_check_passes_valid_report(self, gate):
        """测试有效报告通过检查"""
        report = {
            "title": "测试报告",
            "sections": [
                {"title": "概述", "content": "内容..."}
            ],
            "facts": [
                {"id": "f1", "confidence": "high"}
            ],
            "sources": ["政府官网"]
        }
        
        result = gate.check(report)
        assert result["passed"] is True
        assert result["errors"] == []
    
    def test_check_fails_empty_title(self, gate):
        """测试空标题失败"""
        report = {"title": "", "sections": []}
        result = gate.check(report)
        assert result["passed"] is False
        assert any("标题" in e for e in result["errors"])
    
    def test_check_fails_no_sections(self, gate):
        """测试无章节失败"""
        report = {"title": "报告", "sections": []}
        result = gate.check(report)
        assert result["passed"] is False
        assert any("章节" in e for e in result["errors"])
    
    def test_check_fails_unverified_facts(self, gate):
        """测试未验证事实失败"""
        report = {
            "title": "报告",
            "sections": [{"title": "章", "content": "内容"}],
            "facts": [
                {"id": "f1", "confidence": "unverified"}
            ]
        }
        result = gate.check(report)
        assert result["passed"] is False
        assert any("未验证" in e or "unverified" in e.lower() for e in result["errors"])
    
    def test_check_fails_untrusted_source(self, gate):
        """测试不可信来源失败"""
        report = {
            "title": "报告",
            "sections": [{"title": "章", "content": "内容"}],
            "sources": ["匿名论坛"]
        }
        result = gate.check(report)
        assert result["passed"] is False
        assert any("来源" in e for e in result["errors"])
    
    def test_check_with_warnings(self, gate):
        """测试生成警告"""
        report = {
            "title": "报告",
            "sections": [{"title": "章", "content": "内容"}],
            "facts": [{"id": "f1", "confidence": "low"}],
            "sources": ["知名媒体"]
        }
        result = gate.check(report)
        assert result["passed"] is True  # 通过但有警告
        assert len(result["warnings"]) > 0
    
    def test_get_quality_score(self, gate):
        """测试获取质量分数"""
        report = {
            "title": "报告",
            "sections": [{"title": "章", "content": "内容"}],
            "facts": [
                {"id": "f1", "confidence": "high"},
                {"id": "f2", "confidence": "medium"}
            ],
            "sources": ["政府官网", "知名媒体"]
        }
        score = gate.get_quality_score(report)
        assert 0 <= score <= 100
        assert score > 70  # 高质量报告
