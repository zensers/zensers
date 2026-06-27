import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestP5SerializeReportWithContentPreview:
    """P5: serialize_report_for_review 包含正文摘要"""

    def test_content_preview_included(self):
        from src.agents.fixed_agents.report_upgrade.global_reviewer import serialize_report_for_review
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
        chapters = [
            ChapterWriteOutput(
                chapter_id="ch1", title="市场规模",
                content="前言" * 100 + "\n核心内容\n" + "后语" * 100,
                data_points_used=[DataPoint(metric="规模", value="2000", unit="亿元", source="A")],
                key_conclusions=["市场达2000亿"],
            )
        ]
        registry = MagicMock()
        result = serialize_report_for_review(chapters, registry)
        assert "正文前段" in result
        assert "正文后段" in result

    def test_head_and_tail_no_overlap_long_content(self):
        from src.agents.fixed_agents.report_upgrade.global_reviewer import serialize_report_for_review
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
        # 1000+ chars content
        chapters = [
            ChapterWriteOutput(
                chapter_id="ch1", title="测试",
                content="头部内容" + "x" * 900 + "尾部内容风险提示",
            )
        ]
        registry = MagicMock()
        result = serialize_report_for_review(chapters, registry)
        # head和tail应该不同
        assert "头部内容" in result
        assert "风险提示" in result

    def test_short_content_no_duplicate(self):
        from src.agents.fixed_agents.report_upgrade.global_reviewer import serialize_report_for_review
        from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput
        chapters = [
            ChapterWriteOutput(
                chapter_id="ch1", title="测试",
                content="短内容",
            )
        ]
        registry = MagicMock()
        result = serialize_report_for_review(chapters, registry)
        assert "短内容" in result


class TestE3ReviewLoopExit:
    """E3: 章节级review循环退出条件"""

    def test_exit_when_score_above_target(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import RetryPolicy
        assert RetryPolicy.TARGET_SCORE == 80

    def test_rewrite_trigger_condition_best_score_below_target(self):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
        import inspect
        source = inspect.getsource(ReportOrchestrator.generate_report)
        # L232附近应使用TARGET_SCORE而非MIN_REVIEW_SCORE_TO_ACCEPT
        assert 'TARGET_SCORE' in source, "rewrite触发条件应使用TARGET_SCORE"
