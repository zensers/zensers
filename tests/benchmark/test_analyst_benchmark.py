# -*- coding: utf-8 -*-
"""
专业分析师基准测试
================

将 AI 生成报告与专业一线分析师标准对比，
确保 AI 报告质量达到或超过分析师水平。

测试维度:
1. 数据准确性 (权重 30%)
2. 内容完整性 (权重 25%)
3. 逻辑连贯性 (权重 20%)
4. 格式规范性 (权重 15%)
5. 语言专业性 (权重 10%)
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

# 项目组件
from src.core.harness.quality import QualityGate, ConfidenceGrader
from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent


# ==================== 基准定义 ====================

@dataclass
class AnalystBenchmark:
    """专业分析师基准"""
    accuracy_rate: float = 0.99       # 数据准确率 ≥ 99%
    completeness_rate: float = 0.95   # 内容完整率 ≥ 95%
    consistency_rate: float = 0.90    # 逻辑一致率 ≥ 90%
    format_score: float = 0.95        # 格式规范分 ≥ 95%
    language_score: float = 0.90      # 语言专业分 ≥ 90%
    
    # AI 目标（允许略低于分析师，但需达到 85% 以上）
    ai_accuracy_target: float = 0.98
    ai_completeness_target: float = 0.95
    ai_consistency_target: float = 0.90
    ai_format_target: float = 0.95
    ai_language_target: float = 0.85
    
    # 综合质量目标
    overall_quality_target: float = 85.0  # AI 报告综合评分 ≥ 85


@dataclass
class QualityDimension:
    """质量维度评分"""
    name: str
    score: float
    weight: float
    target: float
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)


# ==================== 测试样本 ====================

PROFESSIONAL_REPORT = {
    "title": "2025年中国新能源汽车市场深度研究报告",
    "content": """
# 执行摘要

2025年中国新能源汽车市场继续保持高速增长态势。全年销量达到1,280万辆，
同比增长35.6%，市场渗透率突破45%。比亚迪以427万辆的销量稳居第一，
市场份额达33.4%。

## 市场规模

2025年新能源汽车销量1,280万辆，同比增长35.6%。
其中纯电动汽车896万辆，占比70%；插电混动384万辆，占比30%。

## 竞争格局

| 排名 | 企业 | 销量(万辆) | 份额 |
|------|------|-----------|------|
| 1 | 比亚迪 | 427 | 33.4% |
| 2 | 特斯拉 | 198 | 15.5% |
| 3 | 蔚来 | 89 | 7.0% |

## 发展趋势

1. 电池技术持续突破，固态电池进入量产阶段
2. 智能驾驶渗透率快速提升，L3级以上占比超30%
3. 充电基础设施加速建设，公共充电桩达350万个
""",
    "sections": [
        {"title": "执行摘要", "content": "2025年中国新能源汽车市场..."},
        {"title": "市场规模", "content": "2025年新能源汽车销量1,280万辆..."},
        {"title": "竞争格局", "content": "比亚迪427万辆，份额33.4%..."},
        {"title": "发展趋势", "content": "电池技术持续突破..."},
    ],
    "word_count": 5000,
    "facts": [
        {"id": "f1", "confidence": "high", "source": "中国汽车工业协会"},
        {"id": "f2", "confidence": "high", "source": "国家统计局"},
        {"id": "f3", "confidence": "medium", "source": "行业预测"},
    ],
    "sources": ["中国汽车工业协会", "国家统计局", "知名媒体"],
}

LOW_QUALITY_REPORT = {
    "title": "新能源报告",
    "content": "新能源汽车销量增长了好多。比亚迪卖得最好。",
    "sections": [
        {"title": "概述", "content": "新能源汽车销量增长了好多。"},
    ],
    "word_count": 50,
    "facts": [
        {"id": "f1", "confidence": "unverified"},
    ],
    "sources": ["匿名论坛"],
}

MODERATE_QUALITY_REPORT = {
    "title": "2025年新能源汽车市场分析",
    "content": """
# 市场分析

2025年新能源汽车销量约1,200万辆，同比增长约30%。
比亚迪销量约400万辆，市场份额约33%。

## 主要发现

1. 市场持续增长
2. 比亚迪领先
3. 充电设施增加
""",
    "sections": [
        {"title": "市场分析", "content": "2025年新能源汽车销量..."},
        {"title": "主要发现", "content": "市场持续增长..."},
    ],
    "word_count": 2000,
    "facts": [
        {"id": "f1", "confidence": "medium", "source": "知名媒体"},
        {"id": "f2", "confidence": "medium", "source": "行业协会"},
    ],
    "sources": ["知名媒体", "行业协会"],
}


# ==================== 测试类 ====================

class TestAnalystBenchmark:
    """专业分析师基准测试"""
    
    @pytest.fixture
    def benchmark(self):
        """创建基准定义"""
        return AnalystBenchmark()
    
    @pytest.fixture
    def quality_gate(self):
        """创建质量闸门"""
        return QualityGate()
    
    @pytest.fixture
    def quality_agent(self):
        """创建质量检查Agent"""
        return QualityCheckAgent(agent_id="test_qc")
    
    # === 准确性基准测试 ===
    
    def test_accuracy_high_quality_report(self, quality_gate):
        """测试高质量报告的数据准确性"""
        result = quality_gate.check(PROFESSIONAL_REPORT)
        # 专业级报告应通过准确性检查
        assert result["quality_score"] >= 70, \
            f"专业级报告质量分数应≥70，实际: {result['quality_score']}"
        # 不应有数据准确性相关错误
        accuracy_errors = [e for e in result.get("errors", []) if "准确" in e or "数据" in e]
        assert len(accuracy_errors) == 0, f"发现准确性错误: {accuracy_errors}"
    
    def test_accuracy_low_quality_report(self, quality_gate):
        """测试低质量报告的准确性检测"""
        result = quality_gate.check(LOW_QUALITY_REPORT)
        # 低质量报告不应通过
        assert result["passed"] is False
    
    # === 完整性基准测试 ===
    
    @pytest.mark.asyncio
    async def test_completeness_professional_report(self, quality_agent):
        """测试专业级报告的完整性"""
        result = await quality_agent.execute({"report": PROFESSIONAL_REPORT})
        # 专业级报告应通过完整性检查
        completeness = result.get("check_details", {}).get("completeness", {})
        assert completeness.get("passed", False), \
            f"专业级报告完整性未通过: {completeness.get('issues', [])}"
    
    @pytest.mark.asyncio
    async def test_completeness_low_quality_report(self, quality_agent):
        """测试低质量报告的完整性检测"""
        result = await quality_agent.execute({"report": LOW_QUALITY_REPORT})
        completeness = result.get("check_details", {}).get("completeness", {})
        # 应检测到完整性问题
        assert not completeness.get("passed", True), \
            "低质量报告应检测到完整性问题"
    
    # === 综合质量基准测试 ===
    
    @pytest.mark.asyncio
    async def test_overall_quality_professional(self, quality_agent, benchmark):
        """测试专业级报告的综合质量"""
        result = await quality_agent.execute({"report": PROFESSIONAL_REPORT})
        quality_score = result.get("quality_score", 0)
        # 专业级报告质量应达到 AI 目标
        assert quality_score >= benchmark.overall_quality_target, \
            f"专业级报告质量{quality_score}未达到目标{benchmark.overall_quality_target}"
    
    @pytest.mark.asyncio
    async def test_overall_quality_moderate(self, quality_agent):
        """测试中等质量报告"""
        result = await quality_agent.execute({"report": MODERATE_QUALITY_REPORT})
        quality_score = result.get("quality_score", 0)
        # 中等报告应有合理的质量分数
        assert 40 <= quality_score <= 90, \
            f"中等报告质量分数异常: {quality_score}"
    
    @pytest.mark.asyncio
    async def test_overall_quality_low(self, quality_agent):
        """测试低质量报告"""
        result = await quality_agent.execute({"report": LOW_QUALITY_REPORT})
        quality_score = result.get("quality_score", 0)
        # 低质量报告分数应低于通过阈值
        assert quality_score < 70, \
            f"低质量报告不应通过: {quality_score}"


class TestQualityDimensions:
    """质量维度测试"""
    
    @pytest.fixture
    def quality_agent(self):
        return QualityCheckAgent(agent_id="test_qc")
    
    @pytest.mark.asyncio
    async def test_all_dimensions_checked(self, quality_agent):
        """测试所有质量维度都被检查"""
        result = await quality_agent.execute({"report": PROFESSIONAL_REPORT})
        check_details = result.get("check_details", {})
        # 验证4个维度都被检查
        expected_dimensions = {"completeness", "accuracy", "consistency", "format"}
        actual_dimensions = set(check_details.keys())
        assert expected_dimensions.issubset(actual_dimensions), \
            f"缺少质量维度: {expected_dimensions - actual_dimensions}"
    
    @pytest.mark.asyncio
    async def test_quality_score_range(self, quality_agent):
        """测试质量分数范围"""
        for report in [PROFESSIONAL_REPORT, MODERATE_QUALITY_REPORT, LOW_QUALITY_REPORT]:
            result = await quality_agent.execute({"report": report})
            score = result.get("quality_score", -1)
            assert 0 <= score <= 100, \
                f"质量分数超出范围: {score}"
    
    @pytest.mark.asyncio
    async def test_issues_structure(self, quality_agent):
        """测试问题结构完整性"""
        result = await quality_agent.execute({"report": LOW_QUALITY_REPORT})
        issues = result.get("issues", [])
        for issue in issues:
            assert "type" in issue, "问题缺少 type 字段"
            assert "severity" in issue, "问题缺少 severity 字段"
            assert "message" in issue, "问题缺少 message 字段"
            assert issue["severity"] in ("high", "medium", "low"), \
                f"无效严重度: {issue['severity']}"


class TestConfidenceGrading:
    """置信度分级测试"""
    
    @pytest.fixture
    def grader(self):
        return ConfidenceGrader()
    
    def test_tier1_source_high_confidence(self, grader):
        """测试 Tier1 来源（政府/财报）应获得高置信度"""
        result = grader.grade(
            has_source=True,
            source_tier="tier1",
            cross_verified=True,
            data_fresh_days=3
        )
        assert result["level"] == "high"
        assert result["score"] >= 80
    
    def test_tier2_source_medium_confidence(self, grader):
        """测试 Tier2 来源（知名媒体）应获得中等置信度"""
        result = grader.grade(
            has_source=True,
            source_tier="tier2",
            cross_verified=False,
            data_fresh_days=15
        )
        assert result["level"] in ("medium", "high")
    
    def test_no_source_unverified(self, grader):
        """测试无来源应为未验证"""
        result = grader.grade(
            has_source=False,
            source_tier=None,
            cross_verified=False,
            data_fresh_days=365
        )
        assert result["level"] == "unverified"
    
    def test_cross_verification_improves_confidence(self, grader):
        """测试交叉验证提升置信度"""
        without = grader.grade(has_source=True, source_tier="tier2", cross_verified=False)
        with_cv = grader.grade(has_source=True, source_tier="tier2", cross_verified=True)
        assert with_cv["score"] > without["score"]
    
    def test_data_freshness_affects_confidence(self, grader):
        """测试数据新鲜度影响置信度"""
        fresh = grader.grade(has_source=True, source_tier="tier2", data_fresh_days=3)
        stale = grader.grade(has_source=True, source_tier="tier2", data_fresh_days=180)
        assert fresh["score"] > stale["score"]


class TestQualityGateBenchmark:
    """质量闸门基准测试"""
    
    @pytest.fixture
    def gate(self):
        return QualityGate()
    
    def test_professional_report_passes_gate(self, gate):
        """测试专业级报告通过质量闸门"""
        result = gate.check(PROFESSIONAL_REPORT)
        assert result["passed"] is True
        assert result["quality_score"] >= 70
    
    def test_low_quality_report_fails_gate(self, gate):
        """测试低质量报告不通过质量闸门"""
        result = gate.check(LOW_QUALITY_REPORT)
        assert result["passed"] is False
    
    def test_untrusted_source_fails_gate(self, gate):
        """测试不可信来源不通过质量闸门"""
        report = {
            "title": "报告",
            "sections": [{"title": "章", "content": "内容"}],
            "sources": ["匿名论坛"]
        }
        result = gate.check(report)
        assert result["passed"] is False
    
    def test_trusted_source_passes_gate(self, gate):
        """测试可信来源通过质量闸门"""
        report = {
            "title": "专业市场研究报告",
            "sections": [{"title": "概述", "content": "详细内容..."}],
            "facts": [{"id": "f1", "confidence": "high"}],
            "sources": ["政府官网", "国家统计局"]
        }
        result = gate.check(report)
        assert result["passed"] is True
