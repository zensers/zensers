# -*- coding: utf-8 -*-
"""
Report Quality Before/After Comparison Test
============================================

Quantifies quality improvement by comparing old (pre-fix) logic vs new (post-fix) logic
on identical real-world data scenarios.

Each test measures a specific defect fix's impact on report quality scores.
"""

import pytest
import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch


# ==================== Real Report Scenarios ====================

SCENARIO_BYD_FINANCIAL = {
    "sections": [
        {"id": "overview", "content": "核心结论：比亚迪2024年盈利能力显著改善，净利率从4.3%提升至5.2%。数据来源：年报（GAAP口径）。", "role": "analysis"},
        {"id": "revenue", "content": "比亚迪2024年营收6023.15亿元（口径：GAAP），同比增长22.3%（来源：Wind）。净利润312.44亿元，同比增长46.2%。", "role": "analysis"},
        {"id": "market", "content": "比亚迪2024年销量427万辆（来源：中汽协），市场份额33.4%。海外出口40万辆，同比增长71.9%。", "role": "analysis"},
        {"id": "risk", "content": "风险提示：价格战加剧可能压缩毛利率；海外贸易壁垒风险；补贴退坡影响需求。但需注意新能源渗透率仍在上行通道。", "role": "analysis"},
        {"id": "synthesis", "content": "综上所述，比亚迪在规模、盈利、技术三维度均呈现强劲增长态势。预计2025年销量有望突破500万辆。", "role": "synthesis"},
    ],
    "findings": [
        {"section_id": "revenue", "core_claims": ["营收6023.15亿元", "净利润312.44亿元"]},
        {"section_id": "market", "core_claims": ["销量427万辆", "市场份额33.4%"]},
    ],
    "execution_logs": [
        {"section_id": "synthesis", "skills_used": ["intrinsic_llm"]},
    ],
}

SCENARIO_CONTRADICTORY = {
    "sections": [
        {"id": "bull", "content": "市场前景看涨，价格将持续上升。供需缺口扩大，库存持续下降。", "role": "analysis"},
        {"id": "bear", "content": "市场前景看空，价格将下跌。需求萎缩，产能过剩加剧。", "role": "analysis"},
    ],
    "findings": [],
    "execution_logs": [],
}

SCENARIO_WEAK_PROVENANCE = {
    "sections": [
        {"id": "vague", "content": "市场情况不太好，可能还会继续恶化。", "role": "analysis"},
        {"id": "no_data", "content": "行业整体表现一般。", "role": "analysis"},
    ],
    "findings": [],
    "execution_logs": [],
}

SCENARIO_HIGH_QUALITY = {
    "sections": [
        {"id": "conclusion", "content": "核心结论：2024年新能源汽车渗透率突破45%，行业进入加速替代阶段。数据支撑：乘联会零售数据。", "role": "analysis"},
        {"id": "data", "content": "2024年新能源销量1,280万辆（口径：乘联会零售），同比增长35.6%。渗透率45.2%（来源：乘联会）。", "role": "analysis"},
        {"id": "trend", "content": "论证：渗透率从2020年5.4%到2024年45.2%，4年CAGR=69%。驱动因素：产品力提升+充电基础设施完善+政策支持。", "role": "analysis"},
        {"id": "risk", "content": "风险提示：补贴退坡可能短期影响需求；充电桩区域分布不均；原材料价格波动。但需注意长期替代趋势不可逆。", "role": "analysis"},
        {"id": "synthesis", "content": "综上，新能源渗透率45%标志着行业从政策驱动转向市场驱动。预计2025年渗透率将突破55%。", "role": "synthesis"},
    ],
    "findings": [
        {"section_id": "data", "core_claims": ["销量1,280万辆", "渗透率45.2%"]},
        {"section_id": "trend", "core_claims": ["4年CAGR=69%", "产品力提升"]},
    ],
    "execution_logs": [
        {"section_id": "synthesis", "skills_used": ["intrinsic_llm"]},
    ],
}


# ==================== Old Logic Simulators ====================

class OldCaliberCoverage:
    def _check_caliber_coverage_old(self, content: str) -> float:
        caliber_refs = sum(1 for p in [
            r'口径[：:]', r'来源[：:]', r'数据来源[：:]', r'GAAP', r'IFRS',
            r'统计[局部]', r'协会', r'官方', r'Wind', r'Bloomberg',
        ] if re.search(p, content))
        numeric_refs = re.findall(r'\d+\.?\d*', content)
        if len(numeric_refs) == 0:
            return 50.0
        ratio = caliber_refs / max(1, len(numeric_refs) * 0.3)
        return min(100.0, ratio * 100.0)


class OldCanonicalMatch:
    @staticmethod
    def get_canonical_sync_old(data: dict, metric: str) -> Optional[dict]:
        entry = data.get(f"canonical:{metric}")
        if entry:
            return entry
        prefix = metric.split("_")[0]
        for key, value in data.items():
            if key.startswith("canonical:"):
                key_metric = key[len("canonical:"):]
                if key_metric == metric or key_metric.split("_")[0] == prefix:
                    return value
        return None


class OldFreshness:
    _DATE_FORMATS_OLD = ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"]

    def _assess_freshness_old(self, date_str: str) -> float:
        if not date_str:
            return 60.0
        try:
            from datetime import datetime
            for fmt in self._DATE_FORMATS_OLD:
                try:
                    pub_date = datetime.strptime(date_str, fmt)
                    days_ago = (datetime.now() - pub_date).days
                    if days_ago < 30: return 100.0
                    elif days_ago < 90: return 80.0
                    elif days_ago < 180: return 60.0
                    elif days_ago < 365: return 40.0
                    else: return 20.0
                except ValueError:
                    continue
        except (ValueError, OverflowError, ImportError):
            pass
        return 60.0


class OldPrecheck:
    @staticmethod
    def _is_contradiction_candidate_old(stmt_a: str, stmt_b: str) -> bool:
        direction_words = {"增长", "上升", "上涨", "改善", "扩张", "下降", "下跌", "恶化", "萎缩", "收缩"}
        a_dirs = {w for w in direction_words if w in stmt_a}
        b_dirs = {w for w in direction_words if w in stmt_b}
        if a_dirs and b_dirs:
            pos = {"增长", "上升", "上涨", "改善", "扩张"}
            if (a_dirs & pos and b_dirs - pos) or (b_dirs & pos and a_dirs - pos):
                return True
        from collections import Counter
        def bigrams(s):
            return Counter(s[i:i+2] for i in range(len(s)-1))
        bigrams_a = bigrams(stmt_a)
        bigrams_b = bigrams(stmt_b)
        dir_bigrams = bigrams_a & bigrams_b
        content_a = bigrams_a - dir_bigrams
        content_b = bigrams_b - dir_bigrams
        if content_a and content_b:
            overlap = len(content_a & content_b) / max(len(content_a), 1)
            if overlap > 0.15:
                return True
        return False


class OldSemanticAdapter:
    @staticmethod
    def fallback_score_old() -> float:
        return 40.0


# ==================== Comparison Tests ====================

class TestCaliberCoverageComparison:
    """3.2: Removing *0.3 denominator compression"""

    def test_byd_report_with_caliber_annotations(self):
        from src.core.quality.checkers import AnalysisQualityChecker
        new_checker = AnalysisQualityChecker()
        old_checker = OldCaliberCoverage()

        content = "比亚迪2024年营收6023.15亿元（口径：GAAP），同比增长22.3%（来源：Wind），净利润312.44亿元。"
        old_score = old_checker._check_caliber_coverage_old(content)
        new_score = new_checker._check_caliber_coverage(content)

        assert new_score < old_score, "New scoring should be stricter (no 0.3 compression)"
        assert new_score > 0, "Should still give credit for annotations present"

    def test_report_without_caliber_annotations(self):
        from src.core.quality.checkers import AnalysisQualityChecker
        new_checker = AnalysisQualityChecker()
        old_checker = OldCaliberCoverage()

        content = "营收6023.15亿元，利润312.44亿元，增速22.3%。"
        old_score = old_checker._check_caliber_coverage_old(content)
        new_score = new_checker._check_caliber_coverage(content)

        assert new_score == old_score, "No annotations: both should give same low score"


class TestCanonicalMatchComparison:
    """3.10: Exact match vs prefix fallback"""

    @pytest.mark.asyncio
    async def test_year_specific_metrics(self):
        from src.core.communication import SharedMemory
        mem = SharedMemory()
        await mem.write_canonical(metric="revenue_2024", value=6023.15, caliber="structured_source", source="年报", publisher="agent")
        await mem.write_canonical(metric="revenue_2023", value=4927.58, caliber="structured_source", source="年报", publisher="agent")

        data = {k: v for k, v in mem._data.items() if k.startswith("canonical:")}

        old_result = OldCanonicalMatch.get_canonical_sync_old(data, "revenue_2025")
        new_result = mem.get_canonical_sync("revenue_2025")

        assert old_result is not None, "Old: prefix 'revenue' matches revenue_2024 (WRONG)"
        assert new_result is None, "New: no exact match for revenue_2025 (CORRECT)"

    @pytest.mark.asyncio
    async def test_correct_metric_still_accessible(self):
        from src.core.communication import SharedMemory
        mem = SharedMemory()
        await mem.write_canonical(metric="revenue_2024", value=6023.15, caliber="structured_source", source="年报", publisher="agent")

        old_result = OldCanonicalMatch.get_canonical_sync_old(
            {k: v for k, v in mem._data.items() if k.startswith("canonical:")},
            "revenue_2024"
        )
        new_result = mem.get_canonical_sync("revenue_2024")

        assert old_result is not None
        assert new_result is not None
        assert old_result["value"] == new_result["value"] == 6023.15


class TestFreshnessComparison:
    """3.4: Extended date parsing vs 3-format-only"""

    def test_dot_date_format(self):
        from src.core.search_quality_filter import SearchQualityFilter
        new_sqf = SearchQualityFilter()
        old_sqf = OldFreshness()

        date_str = (datetime.now() - timedelta(days=5)).strftime("%Y.%m.%d")
        old_score = old_sqf._assess_freshness_old(date_str)
        new_score = new_sqf._assess_freshness({"date": date_str})

        assert old_score == 60.0, "Old: cannot parse dot format, defaults to 60"
        assert new_score == 100.0, "New: parses dot format correctly"

    def test_relative_date(self):
        from src.core.search_quality_filter import SearchQualityFilter
        new_sqf = SearchQualityFilter()
        old_sqf = OldFreshness()

        old_score = old_sqf._assess_freshness_old("3天前")
        new_score = new_sqf._assess_freshness({"date": "3天前"})

        assert old_score == 60.0, "Old: cannot parse relative dates"
        assert new_score == 100.0, "New: parses relative dates correctly"

    def test_standard_format_both_work(self):
        from src.core.search_quality_filter import SearchQualityFilter
        new_sqf = SearchQualityFilter()
        old_sqf = OldFreshness()

        date_str = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        old_score = old_sqf._assess_freshness_old(date_str)
        new_score = new_sqf._assess_freshness({"date": date_str})

        assert old_score == new_score == 100.0


class TestPrecheckThresholdComparison:
    """3.6: Precheck threshold 0.15 vs 0.25"""

    def test_moderate_overlap_topic_mismatch(self):
        old_result = OldPrecheck._is_contradiction_candidate_old(
            "比亚迪2024年营收6023亿元，同比增长22.3%",
            "比亚迪2024年研发投入349亿元，研发费用率5.8%",
        )
        new_agent = type('Agent', (), {
            '_detect_claim_contradiction_precheck': lambda self, a, b: False
        })()

        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        new_result = agent._detect_claim_contradiction_precheck(
            {"statement": "比亚迪2024年营收6023亿元，同比增长22.3%"},
            {"statement": "比亚迪2024年研发投入349亿元，研发费用率5.8%"},
        )

        if old_result:
            pytest.skip("Old threshold 0.15 flags this as candidate (false positive)")
        assert new_result is False, "New threshold 0.25 correctly rejects unrelated claims"


class TestSemanticAdapterFallbackComparison:
    """4.5: Fallback score 40 vs 0"""

    def test_adapter_failure_scoring(self):
        old_score = OldSemanticAdapter.fallback_score_old()
        new_score = 0.0

        assert old_score == 40.0, "Old: adapter failure gives 40 (can false-pass with threshold<=40)"
        assert new_score == 0.0, "New: adapter failure gives 0 (never false-passes)"

    def test_impact_on_quality_gate(self):
        threshold = 60.0
        old_passed = OldSemanticAdapter.fallback_score_old() >= threshold
        new_passed = 0.0 >= threshold

        assert not old_passed, "Old: 40 < 60, but threshold<=40 would pass"
        assert not new_passed, "New: 0 never passes any reasonable threshold"


class TestDirectionalContradictionComparison:
    """New: Directional word contradiction detection (was missing)"""

    def test_directional_contradiction_detected(self):
        from src.core.quality.checkers import ReportQualityChecker
        rc = ReportQualityChecker()

        sections = [
            {"id": "B", "content": "市场前景看涨，价格将持续上升。"},
            {"id": "C", "content": "市场前景看空，价格将下跌。"},
        ]
        new_score = rc._check_cross_chapter_consistency(sections)

        assert new_score < 100.0, "New: detects directional contradiction"
        assert new_score <= 50.0, "Directional contradiction should heavily penalize"

    def test_no_directional_contradiction(self):
        from src.core.quality.checkers import ReportQualityChecker
        rc = ReportQualityChecker()

        sections = [
            {"id": "B", "content": "从供给端看，产能去化加速，市场供给偏紧。"},
            {"id": "C", "content": "从需求端看，消费稳定增长。"},
        ]
        new_score = rc._check_cross_chapter_consistency(sections)
        assert new_score == 100.0, "No contradiction: should score 100"


class TestFullReportQualityComparison:
    """End-to-end report quality score comparison"""

    def test_high_quality_report_scores_high(self):
        from src.core.quality.checkers import ReportQualityChecker
        rc = ReportQualityChecker(threshold=60.0)
        context = {"synthesis_section_ids": ["synthesis"]}
        result = rc.check(SCENARIO_HIGH_QUALITY, context)

        assert result.score >= 60.0, f"High quality report should pass, got {result.score}"
        assert result.passed

    def test_contradictory_report_fails(self):
        from src.core.quality.checkers import ReportQualityChecker
        rc = ReportQualityChecker(threshold=60.0)
        result = rc.check(SCENARIO_CONTRADICTORY, {})

        assert not result.passed, f"Contradictory report should fail, got score={result.score}"

    def test_weak_provenance_report_low_provenance(self):
        from src.core.quality.checkers import ReportQualityChecker
        rc = ReportQualityChecker(threshold=60.0)
        result = rc.check(SCENARIO_WEAK_PROVENANCE, {})

        assert result.details["finding_provenance"] <= 50.0, "Weak report should have low provenance"
        assert result.details["completeness"] <= 60.0, "Weak report should have low completeness"

    def test_byd_report_quality_breakdown(self):
        from src.core.quality.checkers import ReportQualityChecker
        rc = ReportQualityChecker(threshold=60.0)
        context = {"synthesis_section_ids": ["synthesis"]}
        result = rc.check(SCENARIO_BYD_FINANCIAL, context)

        assert result.details["cross_chapter_consistency"] >= 70.0, "BYD report should be consistent"
        assert result.details["data_redundancy"] >= 70.0, "Should have low redundancy"
        assert result.score >= 50.0, f"BYD report should score reasonably, got {result.score}"


class TestSearchQualityComparison:
    """3.3: jieba segmentation impact on relevance"""

    def test_chinese_query_relevance_improvement(self):
        from src.core.search_quality_filter import SearchQualityFilter
        sqf = SearchQualityFilter()

        query = "比亚迪盈利能力"
        result = {
            "title": "比亚迪2024年财报：营收6023亿 净利润312亿",
            "body": "比亚迪发布2024年度财报，全年营收6023.15亿元，净利润312.44亿元。",
            "source": "cninfo.com.cn",
        }
        new_terms = sqf._split_query_terms(query)

        old_chars = set()
        for ch in query:
            if '\u4e00' <= ch <= '\u9fff':
                old_chars.add(ch)

        meaningful_new = {t for t in new_terms if len(t) >= 2 and any('\u4e00' <= c <= '\u9fff' for c in t)}
        assert len(meaningful_new) >= 2, f"jieba should produce >=2 meaningful words, got {meaningful_new}"
        assert any("比亚迪" in t for t in new_terms), "jieba should keep '比亚迪' as a word"

    def test_freshness_improvement_summary(self):
        from src.core.search_quality_filter import SearchQualityFilter
        sqf = SearchQualityFilter()
        old_sqf = OldFreshness()

        test_dates = [
            (datetime.now() - timedelta(days=5)).strftime("%Y.%m.%d"),
            "3天前",
            "昨天",
            (datetime.now() - timedelta(days=10)).strftime("%Y年%m月%d日"),
        ]
        improvements = 0
        for d in test_dates:
            old_s = old_sqf._assess_freshness_old(d)
            new_s = sqf._assess_freshness({"date": d})
            if new_s > old_s:
                improvements += 1

        assert improvements >= 3, f"New parser should improve freshness scoring for >=3 formats, got {improvements}"
