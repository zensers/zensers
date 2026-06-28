import pytest
import json
from unittest.mock import AsyncMock, patch
from pathlib import Path

from src.agents.fixed_agents.report_upgrade.models import (
    DataGap, DataRepairResult, DataConflict, DataConflictResolution,
)
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager


@pytest.fixture
def mock_search():
    return AsyncMock()


@pytest.fixture
def mock_scraper():
    return AsyncMock()


@pytest.fixture
def mock_prompts(tmp_path):
    (tmp_path / "data_extraction.tmpl").write_text(
        "metric=${metric} context=${context} topic=${topic} results=${search_results}",
        encoding="utf-8",
    )
    (tmp_path / "conflict_resolution.tmpl").write_text(
        "metric=${metric} entries=${conflict_entries} results=${search_results}",
        encoding="utf-8",
    )
    return PromptManager(prompts_dir=tmp_path)


def make_gap(**overrides):
    defaults = dict(
        chapter_id="ch1",
        metric="\u5e02\u573a\u89c4\u6a21",
        context="\u65b0\u80fd\u6e90\u6c7d\u8f66\u5e02\u573a\u89c4\u6a21",
        search_keywords=["\u65b0\u80fd\u6e90\u6c7d\u8f66 \u5e02\u573a\u89c4\u6a21"],
    )
    defaults.update(overrides)
    return DataGap(**defaults)


def make_conflict(**overrides):
    defaults = dict(
        metric="\u5e02\u573a\u89c4\u6a21",
        entries=[
            {"value": "2000", "unit": "\u4ebf\u5143", "source": "iimedia.cn", "description": "\u7814\u7a76\u62a5\u544a"},
            {"value": "1800", "unit": "\u4ebf\u5143", "source": "36kr.com", "description": "\u65b0\u95fb\u62a5\u9053"},
        ],
    )
    defaults.update(overrides)
    return DataConflict(**defaults)


class TestDataRepairAgentRepairGap:
    @pytest.mark.asyncio
    async def test_search_fails_returns_not_found(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {"success": False}
        agent = DataRepairAgent(mock_search, mock_scraper, prompt_manager=mock_prompts)
        gap = make_gap()
        result = await agent.repair_gap(gap, "\u65b0\u80fd\u6e90\u6c7d\u8f66")
        assert result.found is False
        assert result.gap is gap

    @pytest.mark.asyncio
    async def test_search_succeed_scrape_llm_extracts(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {
            "success": True,
            "results": [
                {"title": "\u5e02\u573a\u89c4\u6a21\u62a5\u544a", "href": "https://iimedia.cn/report1", "body": "\u5e02\u573a\u89c4\u6a21\u8fbe2000\u4ebf"},
                {"title": "\u884c\u4e1a\u5206\u6790", "href": "https://iresearch.cn/report2", "body": "\u5e02\u573a\u89c4\u6a211800\u4ebf"},
            ],
        }
        mock_scraper.execute.side_effect = [
            {"success": True, "text": "2024\u5e74\u65b0\u80fd\u6e90\u6c7d\u8f66\u5e02\u573a\u89c4\u6a21\u8fbe2000\u4ebf\u5143", "title": "\u5e02\u573a\u89c4\u6a21\u62a5\u544a"},
            {"success": True, "text": "2024\u5e74\u65b0\u80fd\u6e90\u6c7d\u8f66\u5e02\u573a\u89c4\u6a211800\u4ebf\u5143", "title": "\u884c\u4e1a\u5206\u6790"},
        ]
        with patch("src.agents.fixed_agents.report_upgrade.data_repair.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": '{"found": true, "value": "2000", "unit": "\u4ebf\u5143", "source": "iimedia.cn", "source_title": "\u5e02\u573a\u89c4\u6a21\u62a5\u544a", "confidence": 0.9}',
            }
            agent = DataRepairAgent(mock_search, mock_scraper, prompt_manager=mock_prompts)
            gap = make_gap()
            result = await agent.repair_gap(gap, "\u65b0\u80fd\u6e90\u6c7d\u8f66")
            assert result.found is True
            assert result.value == "2000"
            assert result.unit == "\u4ebf\u5143"
            assert result.source == "iimedia.cn"

    @pytest.mark.asyncio
    async def test_search_succeeds_no_scrape_results(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {
            "success": True,
            "results": [
                {"title": "\u5e02\u573a\u89c4\u6a21\u62a5\u544a", "href": "https://iimedia.cn/report1", "body": "\u5e02\u573a\u89c4\u6a21\u8fbe2000\u4ebf"},
            ],
        }
        mock_scraper.execute.return_value = {"success": False, "text": "", "title": ""}
        agent = DataRepairAgent(mock_search, mock_scraper, prompt_manager=mock_prompts)
        gap = make_gap()
        result = await agent.repair_gap(gap, "\u65b0\u80fd\u6e90\u6c7d\u8f66")
        assert result.found is False

    @pytest.mark.asyncio
    async def test_llm_extraction_found_true(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {
            "success": True,
            "results": [{"title": "\u62a5\u544a", "href": "https://gov.cn/data", "body": "\u5b98\u65b9\u6570\u636e"}],
        }
        mock_scraper.execute.return_value = {"success": True, "text": "\u5e02\u573a\u89c4\u6a212000\u4ebf\u5143", "title": "\u62a5\u544a"}
        with patch("src.agents.fixed_agents.report_upgrade.data_repair.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": '{"found": true, "value": "2000", "unit": "\u4ebf\u5143", "source": "gov.cn", "source_title": "\u62a5\u544a", "confidence": 0.95}',
            }
            agent = DataRepairAgent(mock_search, mock_scraper, prompt_manager=mock_prompts)
            result = await agent.repair_gap(make_gap(), "\u65b0\u80fd\u6e90\u6c7d\u8f66")
            assert result.found is True
            assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_llm_extraction_found_false(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {
            "success": True,
            "results": [{"title": "\u65e0\u5173\u9875\u9762", "href": "https://example.com", "body": "\u65e0\u5173\u5185\u5bb9"}],
        }
        mock_scraper.execute.return_value = {"success": True, "text": "\u65e0\u5173\u5185\u5bb9", "title": "\u65e0\u5173\u9875\u9762"}
        with patch("src.agents.fixed_agents.report_upgrade.data_repair.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"success": True, "content": '{"found": false}'}
            agent = DataRepairAgent(mock_search, mock_scraper, prompt_manager=mock_prompts)
            result = await agent.repair_gap(make_gap(), "\u65b0\u80fd\u6e90\u6c7d\u8f66")
            assert result.found is False


class TestDataRepairAgentRepairBatch:
    @pytest.mark.asyncio
    async def test_batch_runs_concurrently(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {
            "success": True,
            "results": [{"title": "\u62a5\u544a", "href": "https://iimedia.cn/r1", "body": "\u6570\u636e"}],
        }
        mock_scraper.execute.return_value = {"success": True, "text": "\u6570\u636e\u5185\u5bb9", "title": "\u62a5\u544a"}
        with patch("src.agents.fixed_agents.report_upgrade.data_repair.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": '{"found": true, "value": "100", "unit": "\u4ebf", "source": "iimedia.cn", "source_title": "\u62a5\u544a", "confidence": 0.8}',
            }
            agent = DataRepairAgent(mock_search, mock_scraper, prompt_manager=mock_prompts)
            gaps = [make_gap(metric=f"\u6307\u6807{i}") for i in range(3)]
            results = await agent.repair_batch(gaps, "\u65b0\u80fd\u6e90\u6c7d\u8f66")
            assert len(results) == 3
            assert all(r.found is True for r in results)


class TestDataRepairAgentParseExtraction:
    @pytest.fixture
    def agent(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        return DataRepairAgent(mock_search, mock_scraper, prompt_manager=mock_prompts)

    def test_valid_json_found_true(self, agent):
        gap = make_gap()
        raw = '{"found": true, "value": "2000", "unit": "\u4ebf\u5143", "source": "iimedia.cn", "source_title": "\u62a5\u544a", "confidence": 0.9}'
        result = agent._parse_extraction(raw, gap)
        assert result.found is True
        assert result.value == "2000"
        assert result.unit == "\u4ebf\u5143"

    def test_valid_json_found_false(self, agent):
        gap = make_gap()
        raw = '{"found": false}'
        result = agent._parse_extraction(raw, gap)
        assert result.found is False
        assert result.value is None

    def test_invalid_json_returns_not_found(self, agent):
        gap = make_gap()
        raw = "\u8fd9\u4e0d\u662fJSON"
        result = agent._parse_extraction(raw, gap)
        assert result.found is False
        assert result.gap is gap


class TestConflictResolverResolve:
    @pytest.mark.asyncio
    async def test_high_authority_source_wins(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict(entries=[
            {"value": "2000", "unit": "\u4ebf\u5143", "source": "gov.cn", "description": "\u5b98\u65b9\u7edf\u8ba1"},
            {"value": "1800", "unit": "\u4ebf\u5143", "source": "36kr.com", "description": "\u65b0\u95fb\u62a5\u9053"},
        ])
        resolver = ConflictResolver(search_skill=mock_search, web_scraper_skill=mock_scraper, prompt_manager=mock_prompts)
        result = await resolver.resolve(conflict, "\u65b0\u80fd\u6e90\u6c7d\u8f66")
        assert result.canonical_value == "2000"
        assert result.canonical_source == "gov.cn"

    @pytest.mark.asyncio
    async def test_no_high_score_falls_back_to_search(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict(entries=[
            {"value": "2000", "unit": "\u4ebf\u5143", "source": "sohu.com", "description": "\u5a92\u4f53\u62a5\u9053"},
            {"value": "1800", "unit": "\u4ebf\u5143", "source": "36kr.com", "description": "\u65b0\u95fb\u62a5\u9053"},
        ])
        mock_search.execute.return_value = {
            "success": True,
            "results": [{"title": "\u6743\u5a01\u6570\u636e", "href": "https://gov.cn/data", "body": "\u5e02\u573a\u89c4\u6a212000\u4ebf\u5143"}],
        }
        mock_scraper.execute.return_value = {"success": True, "text": "\u5e02\u573a\u89c4\u6a212000\u4ebf\u5143", "title": "\u6743\u5a01\u6570\u636e"}
        with patch("src.agents.fixed_agents.report_upgrade.data_repair.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": '{"canonical_value": "2000", "canonical_unit": "\u4ebf\u5143", "canonical_source": "gov.cn", "reason": "\u5b98\u65b9\u6570\u636e\u66f4\u6743\u5a01"}',
            }
            resolver = ConflictResolver(search_skill=mock_search, web_scraper_skill=mock_scraper, prompt_manager=mock_prompts)
            result = await resolver.resolve(conflict, "\u65b0\u80fd\u6e90\u6c7d\u8f66")
            assert result.canonical_value == "2000"
            assert result.canonical_source == "gov.cn"


class TestConflictResolverScoreEntry:
    @pytest.fixture
    def resolver(self, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        return ConflictResolver(prompt_manager=mock_prompts)

    def test_gov_cn_scores_10(self, resolver):
        score = resolver._score_entry({"source": "https://www.gov.cn/data", "description": "\u6570\u636e"})
        assert score == 10

    def test_unknown_source_with_official_keyword_scores_10(self, resolver):
        score = resolver._score_entry({"source": "https://unknown-site.com", "description": "\u56fd\u5bb6\u7edf\u8ba1\u5c40\u53d1\u5e03\u6570\u636e"})
        assert score == 10

    def test_unknown_source_no_match_scores_0(self, resolver):
        score = resolver._score_entry({"source": "https://random-blog.com", "description": "\u4e2a\u4eba\u89c2\u70b9"})
        assert score == 0

    def test_iimedia_scores_8(self, resolver):
        score = resolver._score_entry({"source": "https://www.iimedia.cn/report", "description": "\u7814\u7a76\u62a5\u544a"})
        assert score == 8

    def test_36kr_scores_4(self, resolver):
        score = resolver._score_entry({"source": "https://36kr.com/article", "description": "\u65b0\u95fb\u62a5\u9053"})
        assert score == 4

    def test_description_report_pattern_adds_7(self, resolver):
        score = resolver._score_entry({"source": "https://unknown.com", "description": "\u884c\u4e1a\u767d\u76ae\u4e66\u6570\u636e"})
        assert score == 7


class TestConflictResolverResolveBySearch:
    @pytest.mark.asyncio
    async def test_with_search_skill_llm_resolves(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict()
        mock_search.execute.return_value = {
            "success": True,
            "results": [{"title": "\u6570\u636e", "href": "https://gov.cn/data", "body": "\u5e02\u573a\u89c4\u6a212000\u4ebf"}],
        }
        mock_scraper.execute.return_value = {"success": True, "text": "\u5e02\u573a\u89c4\u6a212000\u4ebf\u5143", "title": "\u6570\u636e"}
        with patch("src.agents.fixed_agents.report_upgrade.data_repair.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": '{"canonical_value": "2000", "canonical_unit": "\u4ebf\u5143", "canonical_source": "gov.cn", "reason": "\u5b98\u65b9\u6570\u636e"}',
            }
            resolver = ConflictResolver(search_skill=mock_search, web_scraper_skill=mock_scraper, prompt_manager=mock_prompts)
            result = await resolver._resolve_by_search(conflict, "\u65b0\u80fd\u6e90\u6c7d\u8f66")
            assert result.canonical_value == "2000"
            assert result.canonical_source == "gov.cn"

    @pytest.mark.asyncio
    async def test_without_search_skill_uses_first_entry(self, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict(entries=[
            {"value": "2000", "unit": "\u4ebf\u5143", "source": "sohu.com", "description": "\u5a92\u4f53\u62a5\u9053", "chapter_id": "ch1"},
            {"value": "1800", "unit": "\u4ebf\u5143", "source": "36kr.com", "description": "\u65b0\u95fb\u62a5\u9053", "chapter_id": "ch2"},
        ])
        resolver = ConflictResolver(search_skill=None, web_scraper_skill=None, prompt_manager=mock_prompts)
        result = await resolver._resolve_by_search(conflict, "\u65b0\u80fd\u6e90\u6c7d\u8f66")
        assert result.canonical_value == "2000"
        assert result.canonical_source == "sohu.com"
        assert "ch2" in result.chapters_to_update

    @pytest.mark.asyncio
    async def test_llm_resolve_includes_chapters_to_update(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict(entries=[
            {"value": "2000", "unit": "\u4ebf\u5143", "source": "sohu.com", "chapter_id": "ch1"},
            {"value": "1800", "unit": "\u4ebf\u5143", "source": "36kr.com", "chapter_id": "ch2"},
        ])
        mock_search.execute.return_value = {"success": True, "results": []}
        with patch("src.agents.fixed_agents.report_upgrade.data_repair.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": '{"canonical_value": "2000", "canonical_unit": "\u4ebf\u5143", "canonical_source": "gov.cn", "reason": "\u5b98\u65b9\u6570\u636e"}',
            }
            resolver = ConflictResolver(search_skill=mock_search, web_scraper_skill=mock_scraper, prompt_manager=mock_prompts)
            result = await resolver._resolve_by_search(conflict, "\u65b0\u80fd\u6e90\u6c7d\u8f66")
            assert "ch1" in result.chapters_to_update
            assert "ch2" in result.chapters_to_update

    @pytest.mark.asyncio
    async def test_llm_fails_includes_chapters_to_update(self, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict(entries=[
            {"value": "2000", "unit": "\u4ebf\u5143", "source": "sohu.com", "chapter_id": "ch1"},
            {"value": "1800", "unit": "\u4ebf\u5143", "source": "36kr.com", "chapter_id": "ch2"},
        ])
        mock_search.execute.return_value = {"success": True, "results": []}
        with patch("src.agents.fixed_agents.report_upgrade.data_repair.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"success": False}
            resolver = ConflictResolver(search_skill=mock_search, web_scraper_skill=mock_scraper, prompt_manager=mock_prompts)
            result = await resolver._resolve_by_search(conflict, "\u65b0\u80fd\u6e90\u6c7d\u8f66")
            assert "ch2" in result.chapters_to_update
