import pytest
from unittest.mock import AsyncMock, patch

from src.agents.fixed_agents.report_upgrade.global_reviewer import (
    GlobalReviewAgent, serialize_report_for_review,
)
from src.agents.fixed_agents.report_upgrade.models import (
    ReviewInput, ReviewOutput, ReviewIssue, FixSuggestion,
    ChapterWriteOutput, DataPoint,
)
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager
from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry


@pytest.fixture
def mock_prompts(tmp_path):
    (tmp_path / "global_review.tmpl").write_text(
        "${framework_name} ${report_summary}", encoding="utf-8"
    )
    (tmp_path / "global_verify_issues.tmpl").write_text(
        "${issues_context}", encoding="utf-8"
    )
    return PromptManager(prompts_dir=tmp_path)


@pytest.fixture
def reviewer(mock_prompts):
    return GlobalReviewAgent(prompt_manager=mock_prompts)


def make_chapters():
    return [
        ChapterWriteOutput(
            chapter_id="ch1", title="市场规模",
            content="市场规模达到2000亿元，增速15%。",
            data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="iimedia.cn")],
            key_conclusions=["市场规模达2000亿"],
        ),
        ChapterWriteOutput(
            chapter_id="ch2", title="竞争格局",
            content="竞争格局分析内容。",
            key_conclusions=["头部集中度高"],
        ),
    ]


_CALL_LLM_PATH = "src.agents.fixed_agents.report_upgrade.global_reviewer.call_llm"


class TestGlobalReviewAgentReview:
    @pytest.mark.asyncio
    async def test_review_with_valid_output(self, reviewer):
        with patch(_CALL_LLM_PATH, new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": '```json\n{"overall_score": 75, "dimension_scores": {"data_consistency": 70}, "issues": [{"dimension": "data_consistency", "severity": "CRITICAL", "description": "矛盾", "location": "ch1", "evidence": "ev"}], "fix_suggestions": [{"target_chapter": "ch1", "issue_id": "i1", "fix_type": "patch", "fix_instruction": "修正", "priority": "CRITICAL"}]}\n```',
            }
            inp = ReviewInput(
                framework_config={"name": "行业研究"},
                report_summary="摘要",
                conflicts_summary="冲突",
            )
            result = await reviewer.review(inp)
        assert isinstance(result, ReviewOutput)
        assert result.overall_score == 75.0
        assert len(result.issues) == 1
        assert len(result.fix_suggestions) == 1

    @pytest.mark.asyncio
    async def test_review_llm_failure_raises(self, reviewer):
        with patch(_CALL_LLM_PATH, new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"success": False, "message": "error"}
            inp = ReviewInput(framework_config={}, report_summary="", conflicts_summary="")
            with pytest.raises(RuntimeError):
                await reviewer.review(inp)


class TestGlobalReviewAgentParseOutput:
    def test_parse_valid_json(self, reviewer):
        raw = '```json\n{"overall_score": 80, "dimension_scores": {}, "issues": [], "fix_suggestions": []}\n```'
        result = reviewer._parse_output(raw)
        assert result.overall_score == 80.0

    def test_parse_invalid_json_fallback(self, reviewer):
        result = reviewer._parse_output("不是JSON")
        assert result.overall_score == 0.0

    def test_parse_raw_json_no_code_block(self, reviewer):
        raw = '{"overall_score": 78, "dimension_scores": {}, "issues": [], "fix_suggestions": []}'
        result = reviewer._parse_output(raw)
        assert result.overall_score == 78.0

    def test_parse_partial_json(self, reviewer):
        raw = '```json\n{"overall_score": 60}\n```'
        result = reviewer._parse_output(raw)
        assert result.overall_score == 60.0
        assert result.issues == []
        assert result.fix_suggestions == []


class TestGlobalReviewAgentVerifyIssues:
    @pytest.mark.asyncio
    async def test_verify_confirmed_issues(self, reviewer):
        with patch(_CALL_LLM_PATH, new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": '[{"confirmed": true, "refined_description": "确认矛盾", "refined_evidence": "证据"}]',
            }
            issues = [ReviewIssue(dimension="data_consistency", severity="CRITICAL", description="矛盾", location="ch1", evidence="ev")]
            chapters = make_chapters()
            result = await reviewer.verify_issues(issues, chapters)
        assert len(result) == 1
        assert result[0].description == "确认矛盾"

    @pytest.mark.asyncio
    async def test_verify_filters_unconfirmed(self, reviewer):
        with patch(_CALL_LLM_PATH, new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": '[{"confirmed": false, "refined_description": "", "refined_evidence": ""}]',
            }
            issues = [ReviewIssue(dimension="data_consistency", severity="CRITICAL", description="矛盾", location="ch1", evidence="ev")]
            chapters = make_chapters()
            result = await reviewer.verify_issues(issues, chapters)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_verify_empty_issues(self, reviewer):
        chapters = make_chapters()
        result = await reviewer.verify_issues([], chapters)
        assert result == []

    @pytest.mark.asyncio
    async def test_verify_llm_failure_returns_original(self, reviewer):
        with patch(_CALL_LLM_PATH, new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"success": False, "message": "error"}
            issues = [ReviewIssue(dimension="data_consistency", severity="CRITICAL", description="矛盾", location="ch1", evidence="ev")]
            chapters = make_chapters()
            result = await reviewer.verify_issues(issues, chapters)
        assert len(result) == 1
        assert result[0].description == "矛盾"


class TestExtractRelevantChapters:
    def test_finds_matching_chapter(self, reviewer):
        issues = [ReviewIssue(dimension="", severity="", description="", location="ch1", evidence="")]
        chapters = make_chapters()
        result = reviewer._extract_relevant_chapters(issues[0], chapters)
        assert "市场规模" in result

    def test_no_match(self, reviewer):
        issues = [ReviewIssue(dimension="", severity="", description="", location="ch99", evidence="")]
        chapters = make_chapters()
        result = reviewer._extract_relevant_chapters(issues[0], chapters)
        assert "未找到相关章节" in result


class TestSerializeReportForReview:
    def test_produces_summary(self):
        chapters = make_chapters()
        registry = DataRegistry()
        result = serialize_report_for_review(chapters, registry)
        assert "市场规模" in result
        assert "竞争格局" in result
        assert "2000" in result

    def test_no_data_points(self):
        chapters = [ChapterWriteOutput(chapter_id="ch1", title="概述", content="内容")]
        registry = DataRegistry()
        result = serialize_report_for_review(chapters, registry)
        assert "无数据" in result
