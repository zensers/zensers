import pytest
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator


class TestBuildSearchKeywords:
    def test_basic_metric_and_topic(self):
        kw = ReportOrchestrator._build_search_keywords(
            description="缺乏研发投入金额数据", topic="比亚迪财务分析",
        )
        assert any("比亚迪" in k for k in kw)
        assert any("研发" in k for k in kw)

    def test_bilingual_keywords(self):
        kw = ReportOrchestrator._build_search_keywords(
            description="缺乏净利润数据", topic="比亚迪",
        )
        assert any("净利润" in k for k in kw)
        assert any("net profit" in k.lower() or "profit" in k.lower() for k in kw)

    def test_known_metric_translations(self):
        kw = ReportOrchestrator._build_search_keywords(
            description="缺乏营收数据", topic="比亚迪",
        )
        assert any("revenue" in k.lower() for k in kw)

    def test_no_topic(self):
        kw = ReportOrchestrator._build_search_keywords(
            description="缺乏研发投入数据", topic="",
        )
        assert len(kw) >= 1

    def test_empty_description(self):
        kw = ReportOrchestrator._build_search_keywords(
            description="", topic="比亚迪",
        )
        assert isinstance(kw, list)

    def test_max_5_keywords(self):
        kw = ReportOrchestrator._build_search_keywords(
            description="缺乏营收净利润研发费用毛利率净利率数据", topic="比亚迪财务分析报告",
        )
        assert len(kw) <= 5

    def test_percentage_metric(self):
        kw = ReportOrchestrator._build_search_keywords(
            description="缺乏净利率百分比数据", topic="比亚迪",
        )
        assert any("net" in k.lower() or "净利率" in k for k in kw)
