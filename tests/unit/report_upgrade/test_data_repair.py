import pytest
import json
from unittest.mock import AsyncMock, MagicMock
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
def mock_llm():
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
        metric="市场规模",
        context="新能源汽车市场规模",
        search_keywords=["新能源汽车 市场规模"],
    )
    defaults.update(overrides)
    return DataGap(**defaults)


def make_conflict(**overrides):
    defaults = dict(
        metric="市场规模",
        entries=[
            {"value": "2000", "unit": "亿元", "source": "iimedia.cn", "description": "研究报告"},
            {"value": "1800", "unit": "亿元", "source": "36kr.com", "description": "新闻报道"},
        ],
    )
    defaults.update(overrides)
    return DataConflict(**defaults)


class TestDataRepairAgentRepairGap:
    @pytest.mark.asyncio
    async def test_search_fails_returns_not_found(self, mock_search, mock_scraper, mock_llm, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {"success": False}
        agent = DataRepairAgent(mock_search, mock_scraper, mock_llm, mock_prompts)
        gap = make_gap()
        result = await agent.repair_gap(gap, "新能源汽车")
        assert result.found is False
        assert result.gap is gap

    @pytest.mark.asyncio
    async def test_search_succeed_scrape_llm_extracts(self, mock_search, mock_scraper, mock_llm, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {
            "success": True,
            "results": [
                {"title": "市场规模报告", "href": "https://iimedia.cn/report1", "body": "市场规模达2000亿"},
                {"title": "行业分析", "href": "https://iresearch.cn/report2", "body": "市场规模1800亿"},
            ],
        }
        mock_scraper.execute.side_effect = [
            {"success": True, "text": "2024年新能源汽车市场规模达2000亿元", "title": "市场规模报告"},
            {"success": True, "text": "2024年新能源汽车市场规模1800亿元", "title": "行业分析"},
        ]
        mock_llm.execute.return_value = {
            "success": True,
            "content": '{"found": true, "value": "2000", "unit": "亿元", "source": "iimedia.cn", "source_title": "市场规模报告", "confidence": 0.9}',
        }
        agent = DataRepairAgent(mock_search, mock_scraper, mock_llm, mock_prompts)
        gap = make_gap()
        result = await agent.repair_gap(gap, "新能源汽车")
        assert result.found is True
        assert result.value == "2000"
        assert result.unit == "亿元"
        assert result.source == "iimedia.cn"

    @pytest.mark.asyncio
    async def test_search_succeeds_no_scrape_results(self, mock_search, mock_scraper, mock_llm, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {
            "success": True,
            "results": [
                {"title": "市场规模报告", "href": "https://iimedia.cn/report1", "body": "市场规模达2000亿"},
            ],
        }
        mock_scraper.execute.return_value = {"success": False, "text": "", "title": ""}
        agent = DataRepairAgent(mock_search, mock_scraper, mock_llm, mock_prompts)
        gap = make_gap()
        result = await agent.repair_gap(gap, "新能源汽车")
        assert result.found is False

    @pytest.mark.asyncio
    async def test_llm_extraction_found_true(self, mock_search, mock_scraper, mock_llm, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {
            "success": True,
            "results": [{"title": "报告", "href": "https://gov.cn/data", "body": "官方数据"}],
        }
        mock_scraper.execute.return_value = {"success": True, "text": "市场规模2000亿元", "title": "报告"}
        mock_llm.execute.return_value = {
            "success": True,
            "content": '{"found": true, "value": "2000", "unit": "亿元", "source": "gov.cn", "source_title": "报告", "confidence": 0.95}',
        }
        agent = DataRepairAgent(mock_search, mock_scraper, mock_llm, mock_prompts)
        result = await agent.repair_gap(make_gap(), "新能源汽车")
        assert result.found is True
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_llm_extraction_found_false(self, mock_search, mock_scraper, mock_llm, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {
            "success": True,
            "results": [{"title": "无关页面", "href": "https://example.com", "body": "无关内容"}],
        }
        mock_scraper.execute.return_value = {"success": True, "text": "无关内容", "title": "无关页面"}
        mock_llm.execute.return_value = {
            "success": True,
            "content": '{"found": false}',
        }
        agent = DataRepairAgent(mock_search, mock_scraper, mock_llm, mock_prompts)
        result = await agent.repair_gap(make_gap(), "新能源汽车")
        assert result.found is False


class TestDataRepairAgentRepairBatch:
    @pytest.mark.asyncio
    async def test_batch_runs_concurrently(self, mock_search, mock_scraper, mock_llm, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search.execute.return_value = {
            "success": True,
            "results": [{"title": "报告", "href": "https://iimedia.cn/r1", "body": "数据"}],
        }
        mock_scraper.execute.return_value = {"success": True, "text": "数据内容", "title": "报告"}
        mock_llm.execute.return_value = {
            "success": True,
            "content": '{"found": true, "value": "100", "unit": "亿", "source": "iimedia.cn", "source_title": "报告", "confidence": 0.8}',
        }
        agent = DataRepairAgent(mock_search, mock_scraper, mock_llm, mock_prompts)
        gaps = [make_gap(metric=f"指标{i}") for i in range(3)]
        results = await agent.repair_batch(gaps, "新能源汽车")
        assert len(results) == 3
        assert all(r.found is True for r in results)


class TestDataRepairAgentParseExtraction:
    @pytest.fixture
    def agent(self, mock_search, mock_scraper, mock_llm, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        return DataRepairAgent(mock_search, mock_scraper, mock_llm, mock_prompts)

    def test_valid_json_found_true(self, agent):
        gap = make_gap()
        raw = '{"found": true, "value": "2000", "unit": "亿元", "source": "iimedia.cn", "source_title": "报告", "confidence": 0.9}'
        result = agent._parse_extraction(raw, gap)
        assert result.found is True
        assert result.value == "2000"
        assert result.unit == "亿元"
        assert result.source == "iimedia.cn"
        assert result.confidence == 0.9

    def test_valid_json_found_false(self, agent):
        gap = make_gap()
        raw = '{"found": false}'
        result = agent._parse_extraction(raw, gap)
        assert result.found is False
        assert result.value is None

    def test_invalid_json_returns_not_found(self, agent):
        gap = make_gap()
        raw = "这不是JSON"
        result = agent._parse_extraction(raw, gap)
        assert result.found is False
        assert result.gap is gap


class TestConflictResolverResolve:
    @pytest.mark.asyncio
    async def test_high_authority_source_wins(self, mock_llm, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict(entries=[
            {"value": "2000", "unit": "亿元", "source": "gov.cn", "description": "官方统计"},
            {"value": "1800", "unit": "亿元", "source": "36kr.com", "description": "新闻报道"},
        ])
        resolver = ConflictResolver(mock_llm, mock_search, mock_scraper, mock_prompts)
        result = await resolver.resolve(conflict, "新能源汽车")
        assert result.canonical_value == "2000"
        assert result.canonical_source == "gov.cn"

    @pytest.mark.asyncio
    async def test_no_high_score_falls_back_to_search(self, mock_llm, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict(entries=[
            {"value": "2000", "unit": "亿元", "source": "sohu.com", "description": "媒体报道"},
            {"value": "1800", "unit": "亿元", "source": "36kr.com", "description": "新闻报道"},
        ])
        mock_search.execute.return_value = {
            "success": True,
            "results": [{"title": "权威数据", "href": "https://gov.cn/data", "body": "市场规模2000亿元"}],
        }
        mock_scraper.execute.return_value = {"success": True, "text": "市场规模2000亿元", "title": "权威数据"}
        mock_llm.execute.return_value = {
            "success": True,
            "content": '{"canonical_value": "2000", "canonical_unit": "亿元", "canonical_source": "gov.cn", "reason": "官方数据更权威"}',
        }
        resolver = ConflictResolver(mock_llm, mock_search, mock_scraper, mock_prompts)
        result = await resolver.resolve(conflict, "新能源汽车")
        assert result.canonical_value == "2000"
        assert result.canonical_source == "gov.cn"


class TestConflictResolverScoreEntry:
    @pytest.fixture
    def resolver(self, mock_llm, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        return ConflictResolver(mock_llm, prompt_manager=mock_prompts)

    def test_gov_cn_scores_10(self, resolver):
        score = resolver._score_entry({"source": "https://www.gov.cn/data", "description": "数据"})
        assert score == 10

    def test_unknown_source_with_official_keyword_scores_10(self, resolver):
        score = resolver._score_entry({"source": "https://unknown-site.com", "description": "国家统计局发布数据"})
        assert score == 10

    def test_unknown_source_no_match_scores_0(self, resolver):
        score = resolver._score_entry({"source": "https://random-blog.com", "description": "个人观点"})
        assert score == 0

    def test_iimedia_scores_8(self, resolver):
        score = resolver._score_entry({"source": "https://www.iimedia.cn/report", "description": "研究报告"})
        assert score == 8

    def test_36kr_scores_4(self, resolver):
        score = resolver._score_entry({"source": "https://36kr.com/article", "description": "新闻报道"})
        assert score == 4

    def test_description_report_pattern_adds_7(self, resolver):
        score = resolver._score_entry({"source": "https://unknown.com", "description": "行业白皮书数据"})
        assert score == 7


class TestConflictResolverResolveBySearch:
    @pytest.mark.asyncio
    async def test_with_search_skill_llm_resolves(self, mock_llm, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict()
        mock_search.execute.return_value = {
            "success": True,
            "results": [{"title": "数据", "href": "https://gov.cn/data", "body": "市场规模2000亿"}],
        }
        mock_scraper.execute.return_value = {"success": True, "text": "市场规模2000亿元", "title": "数据"}
        mock_llm.execute.return_value = {
            "success": True,
            "content": '{"canonical_value": "2000", "canonical_unit": "亿元", "canonical_source": "gov.cn", "reason": "官方数据"}',
        }
        resolver = ConflictResolver(mock_llm, mock_search, mock_scraper, mock_prompts)
        result = await resolver._resolve_by_search(conflict, "新能源汽车")
        assert result.canonical_value == "2000"
        assert result.canonical_source == "gov.cn"

    @pytest.mark.asyncio
    async def test_without_search_skill_uses_first_entry(self, mock_llm, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict(entries=[
            {"value": "2000", "unit": "亿元", "source": "sohu.com", "description": "媒体报道", "chapter_id": "ch1"},
            {"value": "1800", "unit": "亿元", "source": "36kr.com", "description": "新闻报道", "chapter_id": "ch2"},
        ])
        resolver = ConflictResolver(mock_llm, search_skill=None, web_scraper_skill=None, prompt_manager=mock_prompts)
        result = await resolver._resolve_by_search(conflict, "新能源汽车")
        assert result.canonical_value == "2000"
        assert result.canonical_source == "sohu.com"
        assert "ch2" in result.chapters_to_update

    @pytest.mark.asyncio
    async def test_llm_resolve_includes_chapters_to_update(self, mock_llm, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict(entries=[
            {"value": "2000", "unit": "亿元", "source": "sohu.com", "chapter_id": "ch1"},
            {"value": "1800", "unit": "亿元", "source": "36kr.com", "chapter_id": "ch2"},
        ])
        mock_search.execute.return_value = {"success": True, "results": []}
        mock_llm.execute.return_value = {
            "success": True,
            "content": '{"canonical_value": "2000", "canonical_unit": "亿元", "canonical_source": "gov.cn", "reason": "官方数据"}',
        }
        resolver = ConflictResolver(mock_llm, mock_search, mock_scraper, mock_prompts)
        result = await resolver._resolve_by_search(conflict, "新能源汽车")
        assert "ch1" in result.chapters_to_update
        assert "ch2" in result.chapters_to_update

    @pytest.mark.asyncio
    async def test_llm_fails_includes_chapters_to_update(self, mock_llm, mock_search, mock_scraper, mock_prompts):
        from src.agents.fixed_agents.report_upgrade.data_repair import ConflictResolver
        conflict = make_conflict(entries=[
            {"value": "2000", "unit": "亿元", "source": "sohu.com", "chapter_id": "ch1"},
            {"value": "1800", "unit": "亿元", "source": "36kr.com", "chapter_id": "ch2"},
        ])
        mock_search.execute.return_value = {"success": True, "results": []}
        mock_llm.execute.return_value = {"success": False}
        resolver = ConflictResolver(mock_llm, mock_search, mock_scraper, mock_prompts)
        result = await resolver._resolve_by_search(conflict, "新能源汽车")
        assert "ch2" in result.chapters_to_update
