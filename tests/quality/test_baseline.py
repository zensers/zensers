"""
Quality baseline test suite (G5-FIX-1).
Run: pytest tests/quality/test_baseline.py -v
"""
import pytest
from src.core.quality.checkers import AnalysisQualityChecker, ReportQualityChecker

SAMPLE_5_SEGMENT = """**核心判断**: 净利润326亿元，同比增长22.5%。
**逻辑推导**: 销量增长贡献+120亿，规模效应+2亿，价格战拖累-45亿。
**数据支撑**: 326亿元（来源：比亚迪2025年报，A股口径）。
**反证条件**: 如果补贴退坡超30%，利润增速可能降至10%以下。
**含义**: 需关注政策风险。"""

SAMPLE_CONFLICT_CHAPTERS = [
    {"id": "ch1", "content": "净利润326亿元（A股口径）"},
    {"id": "ch2", "content": "净利润520亿元（港股口径）"},
]

SAMPLE_NO_CONFLICT = [
    {"id": "ch1", "content": "净利润326亿元（A股口径）"},
    {"id": "ch2", "content": "净利润增长率22.5%（比亚迪2025年报）"},
]


class TestAnalysisQualityChecker:
    def test_5_segment_scores_high(self):
        c = AnalysisQualityChecker(threshold=75)
        assert c.check({"content": SAMPLE_5_SEGMENT}).score >= 75

    def test_empty_scores_0(self):
        assert AnalysisQualityChecker(threshold=75).check({"content": ""}).score < 10


class TestCrossChapterConsistency:
    def test_conflict_detected(self):
        c = ReportQualityChecker(threshold=80)
        assert not c.check({"sections": SAMPLE_CONFLICT_CHAPTERS}).passed

    def test_no_conflict_passes(self):
        c = ReportQualityChecker(threshold=80)
        assert c.check({"sections": SAMPLE_NO_CONFLICT}).passed

    def test_single_chapter_passes(self):
        c = ReportQualityChecker(threshold=80)
        assert c.check({"sections": [SAMPLE_CONFLICT_CHAPTERS[0]]}).passed


class TestMetricRegex:
    def test_net_profit(self):
        from src.core.data.metric_extractor import MetricExtractor
        r = MetricExtractor().extract([{"content": "净利润326亿元", "url": ""}])
        assert any(x["metric"] == "净利润" and x["value"] == 326.0 for x in r)

    def test_revenue(self):
        from src.core.data.metric_extractor import MetricExtractor
        r = MetricExtractor().extract([{"content": "营收8040亿元", "url": ""}])
        assert any(x["metric"] == "营收" for x in r)


class TestCaliberDecision:
    def test_annual_report_wins(self):
        from src.core.data.caliber_decision import CaliberDecisionEngine
        r = CaliberDecisionEngine().decide("净利润_2025", [
            {"value": 326, "source": "比亚迪2025年报", "caliber": "A股口径", "confidence": 0.8},
            {"value": 321, "source": "新闻报道", "caliber": "", "confidence": 0.4}])
        assert r["value"] == 326

    def test_rejected_count(self):
        from src.core.data.caliber_decision import CaliberDecisionEngine
        r = CaliberDecisionEngine().decide("净利润_2025", [
            {"value": 326, "source": "年报", "caliber": "A股口径", "confidence": 0.8},
            {"value": 321, "source": "新闻", "caliber": "", "confidence": 0.4}])
        assert len(r["rejected"]) == 1
