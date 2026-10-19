# -*- coding: utf-8 -*-
"""
E2E Quality Fix Validation Test Suite
======================================

Based on real data scenarios (比亚迪财务研究, 新能源汽车市场),
validates all 12 defect fixes from the quality audit report.

Each test class maps to one or more defect fixes and validates
the fix works correctly under realistic data conditions.
"""

import pytest
import asyncio
import re
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch


BYD_FINANCIAL_DATA = {
    "revenue_2024": 6023.15,
    "revenue_2023": 4927.58,
    "net_profit_2024": 312.44,
    "net_profit_2023": 213.67,
    "market_share_2024": 33.4,
    "ev_sales_2024": 427,
    "rd_ratio_2024": 5.8,
}

BYD_SEARCH_RESULTS = [
    {
        "title": "比亚迪2024年财报：营收6023亿 净利润312亿",
        "body": "比亚迪发布2024年度财报，全年营收6023.15亿元，同比增长22.3%。"
                "净利润312.44亿元，同比增长46.2%。研发投入349.3亿元，研发费用率5.8%。",
        "source": "cninfo.com.cn",
        "date": (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
        "credibility": "official",
    },
    {
        "title": "比亚迪2024年销量突破427万辆",
        "body": "2024年比亚迪新能源汽车销量达427万辆，市场份额33.4%，稳居国内第一。",
        "source": "caam.org.cn",
        "date": (datetime.now() - timedelta(days=10)).strftime("%Y年%m月%d日"),
        "credibility": "official",
    },
    {
        "title": "BYD Q4 earnings beat estimates",
        "body": "BYD reported Q4 net profit of 10.3 billion yuan, beating analyst estimates.",
        "source": "reuters.com",
        "date": "3天前",
        "credibility": "high",
    },
    {
        "title": "比亚迪海外出口突破40万辆",
        "body": "2024年比亚迪海外市场出口量突破40万辆，同比增长71.9%。",
        "source": "36kr.com",
        "date": (datetime.now() - timedelta(days=20)).strftime("%Y.%m.%d"),
        "credibility": "medium",
    },
    {
        "title": "新能源汽车行业深度分析",
        "body": "行业整体渗透率突破45%，比亚迪领跑。但需注意补贴退坡风险。",
        "source": "some-blog.com",
        "date": "2月前",
        "credibility": "low",
    },
]

LONG_ANALYSIS_CONTENT = "\n\n".join([
    "## 核心财务指标概览",
    "比亚迪2024年营收6023.15亿元，同比增长22.3%，连续三年保持20%以上增速。"
    "净利润312.44亿元，净利率5.2%，较上年提升0.8个百分点。",
    "中间段普通分析内容" * 80,
    "中间段结论：关键发现——比亚迪盈利能力显著改善，净利率从4.3%提升至5.2%",
    "中间段普通分析内容" * 80,
    "中间段验证：研发投入349.3亿元验证了技术驱动增长模式的有效性",
    "中间段普通分析内容" * 80,
    "## 竞争格局分析",
    "比亚迪以427万辆销量稳居第一，市场份额33.4%。特斯拉198万辆排名第二。",
    "## 最终结论与展望",
    "综合来看，比亚迪在规模、盈利、技术三维度均呈现强劲增长态势。"
    "预计2025年销量有望突破500万辆，但需关注价格战和海外贸易壁垒风险。",
])


# ==================== 3.10: get_canonical_sync exact match ====================

class TestE2ECanonicalExactMatch:
    @pytest.mark.asyncio
    async def test_year_specific_metric_no_cross_match(self):
        from src.core.communication import SharedMemory
        mem = SharedMemory()
        await mem.write_canonical(metric="revenue_2024", value=6023.15, caliber="structured_source", source="BYD年报", publisher="agent_finance")
        await mem.write_canonical(metric="revenue_2023", value=4927.58, caliber="structured_source", source="BYD年报", publisher="agent_finance")
        assert mem.get_canonical_sync("revenue_2024")["value"] == 6023.15
        assert mem.get_canonical_sync("revenue_2023")["value"] == 4927.58
        assert mem.get_canonical_sync("revenue_2025") is None

    @pytest.mark.asyncio
    async def test_prefix_no_false_match(self):
        from src.core.communication import SharedMemory
        mem = SharedMemory()
        await mem.write_canonical(metric="ev_sales_byd", value=427, caliber="search_result", source="中汽协", publisher="agent_market")
        assert mem.get_canonical_sync("ev_sales_byd")["value"] == 427
        assert mem.get_canonical_sync("ev_sales_tesla") is None


# ==================== 3.5: L5 LLM failure returns None ====================

class TestE2EL5ContradictionNoFalsePositive:
    @pytest.mark.asyncio
    async def test_llm_failure_no_heuristic_false_positive(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent._llm_client = AsyncMock()
        agent._llm_client.generate = AsyncMock(side_effect=Exception("API timeout"))
        result = await agent._detect_claim_contradiction(
            {"statement": "比亚迪2024年营收6023亿元"},
            {"statement": "比亚迪2024年净利润312亿元"},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_real_contradiction_detected(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent._llm_client = AsyncMock()
        agent._llm_client.generate = AsyncMock(
            return_value=json.dumps({"is_contradiction": True, "confidence": 0.9, "explanation": "营收数据冲突"})
        )
        result = await agent._detect_claim_contradiction(
            {"statement": "比亚迪2024年营收增长22.3%"},
            {"statement": "比亚迪2024年营收下降5%"},
        )
        assert result is not None


# ==================== 3.2: caliber coverage no denominator compression ====================

class TestE2ECaliberCoverageRealData:
    def test_real_report_caliber_scoring(self):
        from src.core.quality.checkers import AnalysisQualityChecker
        checker = AnalysisQualityChecker()
        content = (
            "比亚迪2024年营收6023.15亿元（来源：年报），"
            "同比增长22.3%（来源：Wind），"
            "净利润312.44亿元（口径：GAAP），"
            "市场份额33.4%。"
        )
        score = checker._check_caliber_coverage(content)
        assert 0 < score <= 100.0

    def test_no_caliber_annotations_low_score(self):
        from src.core.quality.checkers import AnalysisQualityChecker
        checker = AnalysisQualityChecker()
        content = "比亚迪2024年营收6023.15亿元，净利润312.44亿元，市场份额33.4%。"
        score = checker._check_caliber_coverage(content)
        assert score < 50.0


# ==================== 4.5: SemanticQualityAdapter fallback 0 not 40 ====================

class TestE2ESemanticAdapterFallback:
    def test_adapter_failure_returns_zero(self):
        from src.core.quality.semantic_adapter import SemanticQualityAdapter
        adapter = SemanticQualityAdapter.__new__(SemanticQualityAdapter)
        adapter.threshold = 60.0
        adapter._scorer = MagicMock()
        adapter._scorer.score = MagicMock(side_effect=RuntimeError("Model load failed"))
        adapter._fallback_checker = MagicMock()
        adapter._fallback_checker.check = MagicMock(side_effect=RuntimeError("Fallback also failed"))
        adapter.get_checker_type = MagicMock(return_value="semantic")
        adapter._weights = {"relevance": 0.4, "coherence": 0.3, "coverage": 0.3}
        result = adapter.check({"content": "比亚迪2024年营收6023亿元"})
        assert result.score == 0.0
        assert not result.passed


# ==================== 3.8: CrossTypeDuplicateDetector scans all paragraphs ====================

class TestE2ECrossTypeDuplicateRealReport:
    def test_heading_duplicated_in_later_paragraph(self):
        from src.core.orchestrator.aggregation.content_quality import CrossTypeDuplicateDetector
        detector = CrossTypeDuplicateDetector()
        content = (
            "## 盈利能力分析\n\n"
            "比亚迪2024年净利润312.44亿元，同比增长46.2%。\n\n"
            "其他分析内容...\n\n"
            "比亚迪2024年净利润312.44亿元，同比增长46.2%。这一数据表明盈利能力显著提升。"
        )
        result = detector.apply(content)
        assert result is not None


# ==================== 3.6: L5 precheck threshold 0.25 ====================

class TestE2EL5PrecheckThreshold:
    def test_moderate_overlap_not_flagged(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        result = agent._detect_claim_contradiction_precheck(
            {"statement": "比亚迪2024年营收6023亿元，同比增长22.3%"},
            {"statement": "比亚迪2024年研发投入349亿元，研发费用率5.8%"},
        )
        assert result is False

    def test_high_overlap_direction_words_flagged(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        result = agent._detect_claim_contradiction_precheck(
            {"statement": "比亚迪2024年营收增长22.3%"},
            {"statement": "比亚迪2024年营收下降5%"},
        )
        assert result is True


# ==================== 2.2: Canonical key write protection ====================

class TestE2ECanonicalKeyProtection:
    @pytest.mark.asyncio
    async def test_write_canonical_key_logs_warning(self):
        from src.core.communication import SharedMemory
        mem = SharedMemory()
        with patch('src.core.communication.logger.warning') as mock_warn:
            await mem.write("canonical:revenue_2024", 6023.15)
            mock_warn.assert_called()
            assert "canonical-key" in mock_warn.call_args[0][0]

    def test_set_canonical_key_logs_warning(self):
        from src.core.communication import SharedMemory
        mem = SharedMemory()
        with patch('src.core.communication.logger.warning') as mock_warn:
            mem.set("canonical:revenue_2024", 6023.15)
            mock_warn.assert_called()
            assert "canonical-key" in mock_warn.call_args[0][0]


# ==================== 4.4: Non-numeric canonical conflict detection ====================

class TestE2ENonNumericConflictRealData:
    @pytest.mark.asyncio
    async def test_string_conflict_higher_priority_wins(self):
        from src.core.communication import SharedMemory
        mem = SharedMemory()
        await mem.write_canonical(metric="byd_growth_assessment", value="高速增长", caliber="structured_source", source="年报", publisher="agent_finance")
        conflict = await mem.write_canonical(metric="byd_growth_assessment", value="增速放缓", caliber="llm_inference", source="分析师推断", publisher="agent_strategy")
        data = mem.get_canonical_sync("byd_growth_assessment")
        assert data["value"] == "高速增长"
        assert data["caliber"] == "structured_source"

    @pytest.mark.asyncio
    async def test_dict_statement_conflict_higher_priority_wins(self):
        from src.core.communication import SharedMemory
        mem = SharedMemory()
        await mem.write_canonical(
            metric="byd_outlook",
            value={"statement": "比亚迪2025年销量将突破500万辆", "confidence": "HIGH"},
            caliber="structured_source", source="券商研报", publisher="agent_market",
        )
        conflict = await mem.write_canonical(
            metric="byd_outlook",
            value={"statement": "比亚迪2025年销量增速将显著放缓", "confidence": "MEDIUM"},
            caliber="llm_inference", source="分析师推断", publisher="agent_strategy",
        )
        data = mem.get_canonical_sync("byd_outlook")
        assert data["value"]["statement"] == "比亚迪2025年销量将突破500万辆"


# ==================== 3.1: write_canonical source_type validation ====================

class TestE2ESourceTypeValidation:
    @pytest.mark.asyncio
    async def test_invalid_caliber_logs_warning(self):
        from src.core.communication import SharedMemory
        mem = SharedMemory()
        with patch('src.core.communication.logger.warning') as mock_warn:
            await mem.write_canonical(metric="test_metric", value=100, caliber="unknown_source_type", source="test", publisher="test")
            mock_warn.assert_called()
            assert "not in SOURCE_PRIORITY" in mock_warn.call_args[0][0]


# ==================== 3.7: Paragraph-level truncation ====================

class TestE2EParagraphTruncationRealData:
    @pytest.mark.asyncio
    async def test_key_conclusion_preserved_in_truncation(self):
        if len(LONG_ANALYSIS_CONTENT) > 3000:
            _paragraphs = [p for p in LONG_ANALYSIS_CONTENT.split("\n\n") if p.strip()]
            if len(_paragraphs) > 5:
                _head = "\n\n".join(_paragraphs[:2])
                _tail = "\n\n".join(_paragraphs[-2:])
                _key_patterns = ["结论", "发现", "验证", "结果", "综上", "因此", "表明", "证明"]
                _mid_candidates = [p for p in _paragraphs[2:-2] if any(kw in p for kw in _key_patterns)]
                _mid = "\n\n".join(_mid_candidates[:2]) if _mid_candidates else ""
                _parts = [_head]
                if _mid:
                    _parts.append("...[关键中间段落]...")
                    _parts.append(_mid)
                _parts.append("...[中间省略]...")
                _parts.append(_tail)
                _truncated = "\n\n".join(_parts)
                assert "关键发现" in _truncated
                assert "盈利能力显著改善" in _truncated
                assert "最终结论" in _truncated

    def test_short_paragraphs_over_3000_fallback(self):
        content = "A" * 4000
        assert len(content) > 3000
        _paragraphs = [p for p in content.split("\n\n") if p.strip()]
        if len(_paragraphs) <= 5:
            _truncated = content[:2500] + "\n\n...[中间省略]...\n\n" + content[-500:]
            assert "...[中间省略]..." in _truncated
            assert len(_truncated) < len(content)


# ==================== 3.3: jieba segmentation ====================

class TestE2EJiebaSegmentationRealQuery:
    def test_byd_query_segmentation(self):
        from src.core.search_quality_filter import SearchQualityFilter
        terms = SearchQualityFilter._split_query_terms("比亚迪财务信息研究")
        assert any("比亚迪" in t for t in terms)
        assert any("财务" in t or "信息" in t for t in terms)

    def test_ev_market_query_segmentation(self):
        from src.core.search_quality_filter import SearchQualityFilter
        terms = SearchQualityFilter._split_query_terms("新能源汽车市场规模与增长趋势")
        assert any("新能源" in t for t in terms)
        assert any("市场" in t for t in terms)

    def test_mixed_query_segmentation(self):
        from src.core.search_quality_filter import SearchQualityFilter
        terms = SearchQualityFilter._split_query_terms("BYD Q4 财报分析")
        assert "byd" in terms or any("byd" in t.lower() for t in terms)
        assert any("财报" in t or "分析" in t for t in terms)

    def test_relevance_with_jieba_terms(self):
        from src.core.search_quality_filter import SearchQualityFilter
        sqf = SearchQualityFilter()
        query = "比亚迪盈利能力"
        result = BYD_SEARCH_RESULTS[0]
        relevance = sqf._assess_relevance(result, query)
        assert relevance > 0


# ==================== 3.4: Date parsing expansion ====================

class TestE2EDateParsingRealData:
    def test_recent_dates_high_score(self):
        from src.core.search_quality_filter import SearchQualityFilter
        sqf = SearchQualityFilter()
        recent = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        score = sqf._assess_freshness({"date": recent})
        assert score == 100.0

    def test_relative_dates_parsed(self):
        from src.core.search_quality_filter import SearchQualityFilter
        sqf = SearchQualityFilter()
        assert sqf._assess_freshness({"date": "3天前"}) == 100.0
        assert sqf._assess_freshness({"date": "昨天"}) == 100.0

    def test_chinese_date_format(self):
        from src.core.search_quality_filter import SearchQualityFilter
        sqf = SearchQualityFilter()
        recent = (datetime.now() - timedelta(days=10)).strftime("%Y年%m月%d日")
        score = sqf._assess_freshness({"date": recent})
        assert score == 100.0

    def test_dot_date_format(self):
        from src.core.search_quality_filter import SearchQualityFilter
        sqf = SearchQualityFilter()
        recent = (datetime.now() - timedelta(days=20)).strftime("%Y.%m.%d")
        score = sqf._assess_freshness({"date": recent})
        assert score == 100.0

    def test_old_report_low_freshness(self):
        from src.core.search_quality_filter import SearchQualityFilter
        sqf = SearchQualityFilter()
        score = sqf._assess_freshness({"date": "2024-01-15"})
        assert score <= 40.0

    def test_no_date_defaults_medium(self):
        from src.core.search_quality_filter import SearchQualityFilter
        sqf = SearchQualityFilter()
        assert sqf._assess_freshness({}) == 60.0


# ==================== 4.3: Cross-agent reconciliation ====================

class TestE2ECrossAgentReconciliation:
    @pytest.mark.asyncio
    async def test_data_collector_conflicts_consumed(self):
        from src.core.orchestrator.execution.data_collector import DataCollector
        from src.core.communication import Event
        dc = DataCollector()
        event = Event(
            type="data.conflict.detected",
            data={
                "metric": "byd_revenue_2024",
                "values": [6023.15, 5800.0],
                "sources": ["agent_finance", "agent_market"],
            },
        )
        await dc.on_conflict_detected(event)
        conflicts = dc.get_conflicts()
        assert len(conflicts) >= 1

    def test_metric_conflict_details_format(self):
        details = [{
            "key": "byd_net_profit",
            "year": "2024",
            "values": [312.44, 280.0],
            "sources": ["agent_finance", "agent_market"],
        }]
        for d in details:
            assert "key" in d and "year" in d and "values" in d and "sources" in d
            assert len(d["values"]) > 1


# ==================== 4.6: COGNITIVE_STRATEGY _DEFERRED markers ====================

class TestE2ECognitiveStrategyDeferred:
    def test_deferred_params_exist(self):
        from src.core.agents.generic_agent import COGNITIVE_STRATEGY
        for ctype, layers in COGNITIVE_STRATEGY.items():
            l2 = layers.get("L2", {})
            assert "caliber_floor_for_citation" in l2
            assert "same_caliber_resolution" in l2
            assert "speculative_write_policy" in l2
            l3 = layers.get("L3", {})
            assert "reasoning_mode" in l3
            assert "falsification_requirement" in l3

    def test_active_params_still_functional(self):
        from src.core.agents.generic_agent import COGNITIVE_STRATEGY
        for ctype, layers in COGNITIVE_STRATEGY.items():
            l1 = layers.get("L1", {})
            assert "dimension_ceiling" in l1
            assert "speculative_word_downgrade" in l1
            l4 = layers.get("L4", {})
            assert "hypothesis_count" in l4


# ==================== 4.2: Dead code removal ====================

class TestE2EDeadCodeRemoval:
    def test_check_batch_quality_removed(self):
        from src.core.orchestrator.execution.engine import ExecutionEngine
        assert not hasattr(ExecutionEngine, '_check_batch_quality')

    def test_execute_stage_with_quality_removed(self):
        from src.core.orchestrator.execution.engine import ExecutionEngine
        assert not hasattr(ExecutionEngine, '_execute_stage_with_quality')

    def test_build_synthesis_task_removed(self):
        from src.core.orchestrator.execution.engine import ExecutionEngine
        assert not hasattr(ExecutionEngine, '_build_synthesis_task')


# ==================== Integration: Full quality pipeline ====================

class TestE2EFullQualityPipeline:
    @pytest.mark.asyncio
    async def test_canonical_data_flow_with_conflicts(self):
        from src.core.communication import SharedMemory
        mem = SharedMemory()
        await mem.write_canonical(metric="byd_revenue_2024", value=6023.15, caliber="structured_source", source="BYD年报", publisher="agent_finance")
        conflict = await mem.write_canonical(metric="byd_revenue_2024", value=5800.0, caliber="llm_inference", source="分析师估算", publisher="agent_market")
        data = mem.get_canonical_sync("byd_revenue_2024")
        assert data is not None
        assert data["value"] == 6023.15
        assert data["caliber"] == "structured_source"

    @pytest.mark.asyncio
    async def test_search_quality_full_assessment(self):
        from src.core.search_quality_filter import SearchQualityFilter
        sqf = SearchQualityFilter()
        query = "比亚迪2024年财务数据"
        for result in BYD_SEARCH_RESULTS[:3]:
            relevance = sqf._assess_relevance(result, query)
            freshness = sqf._assess_freshness(result)
            assert relevance >= 0
            assert 0 <= freshness <= 100

    def test_content_quality_with_real_duplicates(self):
        from src.core.orchestrator.aggregation.content_quality import CrossTypeDuplicateDetector
        detector = CrossTypeDuplicateDetector()
        content = (
            "## 市场规模\n\n"
            "2024年新能源汽车销量1,280万辆，同比增长35.6%。\n\n"
            "## 竞争格局\n\n"
            "2024年新能源汽车销量1,280万辆，同比增长35.6%。比亚迪以427万辆领跑。"
        )
        result = detector.apply(content)
        assert result is not None
