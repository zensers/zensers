import pytest
from unittest.mock import MagicMock
from dataclasses import asdict


class TestE4DiagnoseIssueSourceTriggerWords:
    """E4: _diagnose_issue_source 触发词扩展"""

    def test_new_trigger_words_recognized(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator, ChapterIssue, QualityIssueDiagnosis
        descs = [
            "未提供营收数据",
            "研发投入不足",
            "现金流数据欠缺",
            "缺少市场份额数据",
        ]
        for desc in descs:
            issue = ChapterIssue(category="data_support", severity="HIGH", location="p:1", description=desc, suggestion="")
            result = ReportOrchestrator._diagnose_issue_source(issue, "")
            assert result is not None
            # Should be L1_missing (search needed) if no raw_data_summary
            assert result.source_layer in ("L1_missing", "L2_omitted")


class TestD3SourceIndexResolved:
    """D3: 来源数字索引解析"""

    def test_source_49_replaced_by_href(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        dps = [{"metric": "营收", "value": "2000", "unit": "亿元", "source": "来源49"}]
        sources = [{"title": "来源1"}, {"title": "来源2"}]  # only 2 sources, 49 is OOB
        result = ReportOrchestrator._ground_data_point_sources(dps, sources)
        assert result[0]["source"] in ("来源1", "来源2")  # any fallback

    def test_source_1_maps_to_first_source(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        dps = [{"metric": "营收", "value": "2000", "unit": "亿元", "source": "来源1"}]
        sources = [{"title": "第一个来源", "href": "https://source1.com"},
                   {"title": "第二个来源"}]  
        result = ReportOrchestrator._ground_data_point_sources(dps, sources)
        assert result[0]["source"] == "第一个来源"

    def test_source_2_maps_to_second_source(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        dps = [{"metric": "营收", "value": "2000", "unit": "亿元", "source": "来源2"}]
        sources = [{"title": "第一个来源"}, {"title": "第二个来源"}]
        result = ReportOrchestrator._ground_data_point_sources(dps, sources)
        assert result[0]["source"] == "第二个来源"

    def test_vague_source_fallback_when_no_index_match(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        dps = [{"metric": "营收", "value": "2000", "unit": "亿元", "source": "行业综合数据"}]
        sources = [{"title": "可用来源", "href": "https://a.com"}]
        result = ReportOrchestrator._ground_data_point_sources(dps, sources)
        assert result[0]["source"] == "可用来源"

    def test_empty_source_replaced(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        dps = [{"metric": "营收", "value": "2000", "unit": "亿元", "source": ""}]
        sources = [{"title": "唯一来源"}]
        result = ReportOrchestrator._ground_data_point_sources(dps, sources)
        assert result[0]["source"] == "唯一来源"


class TestE2BestScoreStrictComparison:
    """E2: rewrite_review 使用严格大于比较"""

    def test_compare_uses_strict_greater(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        import inspect
        source = inspect.getsource(ReportOrchestrator._phase4_fix_and_optimize)
        # Find the rewrite comparison line
        lines = source.split('\n')
        compare_found = False
        for line in lines:
            if 'rewrite_review.score' in line and 're_review.score' in line:
                assert '>' in line and '>=' not in line, "应使用严格大于(>), 而非大于等于(>=)"
                compare_found = True
                break
        assert compare_found, "未找到rewrite_review.score比较语句"
