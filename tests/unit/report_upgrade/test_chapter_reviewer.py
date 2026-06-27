import pytest
from unittest.mock import AsyncMock

from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
from src.agents.fixed_agents.report_upgrade.models import ChapterReviewInput, ChapterReviewOutput
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def mock_prompts(tmp_path):
    (tmp_path / "chapter_review.tmpl").write_text(
        "${topic} ${section_name} ${chapter_content}", encoding="utf-8"
    )
    return PromptManager(prompts_dir=tmp_path)


@pytest.fixture
def reviewer(mock_llm, mock_prompts):
    return ChapterReviewAgent(llm_skill=mock_llm, prompt_manager=mock_prompts)


def make_review_input(**overrides):
    defaults = dict(
        framework_config={"name": "行业研究"},
        chapter_spec={"section_id": "ch1", "section_name": "市场规模", "section_role": "analysis"},
        chapter_content="市场规模达到2000亿元",
        preceding_summary="前文摘要",
        used_metrics_summary="暂无已使用的数据指标。",
        topic="新能源汽车市场分析",
    )
    defaults.update(overrides)
    return ChapterReviewInput(**defaults)


class TestChapterReviewAgentReview:
    @pytest.mark.asyncio
    async def test_review_passes(self, reviewer, mock_llm):
        mock_llm.execute.return_value = {
            "success": True,
            "content": '```json\n{"passed": true, "score": 85, "issues": []}\n```',
        }
        result = await reviewer.review(make_review_input())
        assert isinstance(result, ChapterReviewOutput)
        assert result.passed is True
        assert result.score == 85.0

    @pytest.mark.asyncio
    async def test_review_fails_with_issues(self, reviewer, mock_llm):
        mock_llm.execute.return_value = {
            "success": True,
            "content": '```json\n{"passed": false, "score": 45, "issues": [{"category": "data_support", "severity": "HIGH", "location": "data:市场规模", "description": "无数据支撑", "suggestion": "补充数据"}]}\n```',
        }
        result = await reviewer.review(make_review_input())
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].category == "data_support"

    @pytest.mark.asyncio
    async def test_review_llm_failure_raises(self, reviewer, mock_llm):
        mock_llm.execute.return_value = {"success": False}
        with pytest.raises(RuntimeError):
            await reviewer.review(make_review_input())


class TestChapterReviewAgentParseOutput:
    def test_parse_valid_json(self, reviewer):
        raw = '```json\n{"passed": true, "score": 90, "issues": []}\n```'
        result = reviewer._parse_output(raw)
        assert result.passed is True
        assert result.score == 90.0

    def test_parse_invalid_json_fallback(self, reviewer):
        raw = "不是JSON"
        result = reviewer._parse_output(raw)
        assert result.passed is False
        assert result.score == 0.0

    def test_parse_partial_json(self, reviewer):
        raw = '```json\n{"passed": false, "score": 40}\n```'
        result = reviewer._parse_output(raw)
        assert result.passed is False
        assert result.score == 40.0
        assert result.issues == []

    def test_parse_issue_with_defaults(self, reviewer):
        raw = '```json\n{"passed": false, "score": 50, "issues": [{"category": "logic", "severity": "MEDIUM", "location": "", "description": "逻辑跳跃", "suggestion": "补充过渡"}]}\n```'
        result = reviewer._parse_output(raw)
        assert len(result.issues) == 1
