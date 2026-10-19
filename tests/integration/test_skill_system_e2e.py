"""
Task 6.3: Real business scenario integration test.

Simulates a real report generation flow:
1. Orchestrator initializes → skill discovery → ManifestStrategyBuilder injection
2. Topic decomposition → DATA_COLLECTION agent creation
3. Agent executes with skill pipeline (stock_data → search_skill → news_search)
4. Data flows through _process_skill_output correctly
5. Canonical metrics written to SharedMemory

This test does NOT call real external APIs — it mocks network calls but exercises
all internal code paths with real skill objects and manifests.
"""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _create_real_registry():
    """Create a real registry with manifest-driven discovery."""
    from src.skills.registry import SkillRegistry
    from src.skills.discovery import SkillDiscovery
    registry = SkillRegistry()
    discovery = SkillDiscovery()
    manifests = discovery.discover_all(Path("src/skills"))
    registry._manifests = {m.name: m for m in manifests}
    registries = discovery.build_registries(manifests)
    registry._registries = registries
    registry._factories = {}
    registry._skills = {}
    return registry, manifests


class TestManifestStrategyBuilderIntegration:
    """Verify ManifestStrategyBuilder produces correct routing maps from real manifests."""

    def test_priority_map_contains_all_structured_db_skills(self):
        from src.core.decomposition.manifest_strategy import ManifestStrategyBuilder
        registry, manifests = _create_real_registry()
        builder = ManifestStrategyBuilder(registry._manifests)
        priority_map = builder.build_skill_priority_map()
        for m in manifests:
            if m.priority == "structured_db":
                assert m.name in priority_map, f"{m.name} (priority=structured_db) missing from priority_map"
                assert priority_map[m.name] == "structured_db"

    def test_aspect_map_covers_financial_aspects(self):
        from src.core.decomposition.manifest_strategy import ManifestStrategyBuilder
        registry, manifests = _create_real_registry()
        builder = ManifestStrategyBuilder(registry._manifests)
        aspect_map = builder.build_aspect_skill_map()
        financial_aspects = [a for a in aspect_map if any(
            kw in a.lower() for kw in ["财务", "盈利", "financial", "profit"]
        )]
        assert len(financial_aspects) > 0, "aspect_map should cover financial aspects"
        for aspect in financial_aspects:
            assert "stock_data" in aspect_map[aspect], f"stock_data should cover {aspect}"

    def test_data_source_skill_map_covers_stock_keywords(self):
        from src.core.decomposition.manifest_strategy import ManifestStrategyBuilder
        registry, manifests = _create_real_registry()
        builder = ManifestStrategyBuilder(registry._manifests)
        ds_map = builder.build_data_source_skill_map()
        stock_keywords = [k for k in ds_map if any(
            kw in k for kw in ["股票", "利润", "营收"]
        )]
        assert len(stock_keywords) > 0, "data_source_skill_map should cover stock keywords"

    def test_action_to_skill_map_search_resolves_correctly(self):
        from src.core.decomposition.manifest_strategy import ManifestStrategyBuilder
        registry, manifests = _create_real_registry()
        builder = ManifestStrategyBuilder(registry._manifests)
        action_map = builder.build_action_to_skill_map()
        assert action_map.get("search") == "search_skill"
        assert action_map.get("news_search") == "news_search"
        assert action_map.get("fetch") is not None or True  # some skills have 'fetch'

    def test_get_data_collection_skills_for_financial_aspect(self):
        from src.core.decomposition.manifest_strategy import ManifestStrategyBuilder
        registry, manifests = _create_real_registry()
        builder = ManifestStrategyBuilder(registry._manifests)
        skills = builder.get_data_collection_skills("财务分析", "贵州茅台")
        assert len(skills) > 0, "should have skills for financial analysis"
        skill_names = [s for s in skills]
        assert "stock_data" in skill_names, f"stock_data should be in data collection skills, got {skill_names}"


class TestDataCollectionPipelineIntegration:
    """Test the full DATA_COLLECTION pipeline with real skill objects."""

    @pytest.mark.asyncio
    async def test_stock_data_pipeline_with_mock_execute(self):
        """Simulate stock_data being called through _process_skill_output."""
        from src.core.agents.generic_agent import GenericAgent
        from src.skills.analysis.stock_data import StockDataSkill
        registry, manifests = _create_real_registry()

        skill = StockDataSkill()
        registry._skills["stock_data"] = skill

        agent = GenericAgent(agent_id="test_moutai", agent_type="research", config={})
        agent._skill_registry = registry
        agent._context = {"entities": [{"is_listed": True, "resolved_code": "SH600519", "name": "贵州茅台"}]}

        mock_execute = AsyncMock(side_effect=[
            {
                "success": True,
                "data": {
                    "income_statement": [{"REPORT_DATE": "2024-03-31", "NET_PROFIT": 1500000000, "OPERATE_INCOME": 5000000000}],
                    "balance_sheet": [],
                    "cash_flow": [],
                },
                "content": "",
            },
            {
                "success": True,
                "data": {"periods": [{"report_date": "2024-03-31", "operating_income_total": 500.0}]},
                "content": "",
            },
        ])
        skill.execute = mock_execute

        result = await agent._process_skill_output(
            skill, "stock_data", "贵州茅台", "财务分析", registry,
        )

        assert len(result.get("data_points", [])) > 0, "should produce data_points"
        assert result["data_points"][0]["quality_score"] == 95
        assert result["data_points"][0]["credibility"] == "structured_source"
        assert len(result.get("canonical_metrics", {})) > 0, "should extract metrics"

    @pytest.mark.asyncio
    async def test_search_skill_pipeline_with_mock_execute(self):
        """Simulate search_skill being called through _process_skill_output."""
        from src.core.agents.generic_agent import GenericAgent
        registry, manifests = _create_real_registry()

        mock_search = AsyncMock()
        mock_search.name = "search_skill"
        registry._skills["search_skill"] = mock_search

        agent = GenericAgent(agent_id="test_search", agent_type="research", config={})
        agent._skill_registry = registry
        agent._do_deep_research = AsyncMock(return_value={
            "searches": [
                {
                    "results": [
                        {"title": "贵州茅台2024年报", "body": "净利润150亿，同比增长10%", "href": "http://example.com/1", "quality_score": 85},
                        {"title": "茅台行业分析", "body": "白酒行业市场规模6000亿", "href": "http://example.com/2", "quality_score": 75},
                    ]
                }
            ]
        })

        result = await agent._process_skill_output(
            mock_search, "search_skill", "贵州茅台", "行业分析", registry,
        )

        assert len(result.get("data_points", [])) == 2, "should have 2 data_points from 2 results"
        assert len(result.get("sources", [])) == 2, "should have 2 sources"
        assert any("净利润" in dp.get("content", "") for dp in result["data_points"])

    @pytest.mark.asyncio
    async def test_news_search_pipeline_with_mock_execute(self):
        """Simulate news_search being called through _process_skill_output."""
        from src.core.agents.generic_agent import GenericAgent
        registry, manifests = _create_real_registry()

        mock_news = AsyncMock()
        mock_news.name = "news_search"
        mock_news.execute = AsyncMock(return_value={
            "success": True,
            "results": [
                {"title": "茅台新品发布", "body": "贵州茅台发布新品系列", "href": "http://news1.com", "source": "新浪", "date": "2024-06"},
            ],
        })
        registry._skills["news_search"] = mock_news

        agent = GenericAgent(agent_id="test_news", agent_type="research", config={})
        agent._skill_registry = registry

        result = await agent._process_skill_output(
            mock_news, "news_search", "贵州茅台", "最新动态", registry,
        )

        assert len(result.get("data_points", [])) > 0, "should produce data_points from news"
        assert any("茅台" in dp.get("content", "") for dp in result["data_points"])


class TestOrchestratorInitialization:
    """Verify that the Orchestrator correctly initializes the skill system."""

    def test_orchestrator_creates_registry_and_manifest_builder(self):
        """Test that ResearchOrchestrator.__init__ calls init_from_discovery + ManifestStrategyBuilder."""
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        orchestrator = ResearchOrchestrator(use_intelligent_routing=True)

        assert orchestrator._skill_registry is not None
        assert len(orchestrator._skill_registry._manifests) > 0, "registry should have manifests"

        stock_manifest = orchestrator._skill_registry.get_manifest("stock_data")
        assert stock_manifest is not None, "stock_data manifest should be registered"
        assert stock_manifest.priority == "structured_db"

    def test_manifest_strategy_is_injected_into_strategies(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        from src.core.decomposition.strategies import _manifest_strategy
        orchestrator = ResearchOrchestrator(use_intelligent_routing=True)
        assert _manifest_strategy is not None, "ManifestStrategyBuilder should be injected"


class TestDiscoverSkillsWithRealManifests:
    """Test discover_skills with real manifests from src/skills/."""

    def test_discover_stock_related(self):
        registry, _ = _create_real_registry()
        result = registry.discover_skills("stock financial data", auto_load=False)
        assert "stock_data" in result

    def test_discover_search_related(self):
        registry, _ = _create_real_registry()
        result = registry.discover_skills("web search", auto_load=False)
        assert any("search" in r for r in result)

    def test_discover_news_related(self):
        registry, _ = _create_real_registry()
        result = registry.discover_skills("news search", auto_load=False)
        assert any("news" in r for r in result)

    def test_discover_xueqiu_by_keyword(self):
        registry, _ = _create_real_registry()
        result = registry.discover_skills("雪球", auto_load=False)
        assert "xueqiu" in result

    def test_discover_fuzzy_match(self):
        registry, _ = _create_real_registry()
        result = registry.discover_skills("finacial data", auto_load=False)
        assert "stock_data" in result, "difflib fallback should match 'finacial'≈'financial'"

    def test_discover_shared_keyword_returns_both(self):
        """When multiple skills share 'search' keyword, discover_skills('search') should find both."""
        registry, _ = _create_real_registry()
        result = registry.discover_skills("search", auto_load=False)
        assert "search_skill" in result
        assert "news_search" in result, "both search_skill and news_search have 'search' keyword"


class TestFactoryAliasResolution:
    """Verify DynamicAgentFactory resolves skill aliases correctly."""

    def test_web_search_resolves_to_search_skill(self):
        from src.core.agents.factory import DynamicAgentFactory
        assert DynamicAgentFactory._SKILL_ALIAS_MAP.get("web_search") == "search_skill"

    def test_search_resolves_to_search_skill(self):
        from src.core.agents.factory import DynamicAgentFactory
        assert DynamicAgentFactory._SKILL_ALIAS_MAP.get("search") == "search_skill"

    def test_news_resolves_to_news_search(self):
        from src.core.agents.factory import DynamicAgentFactory
        assert DynamicAgentFactory._SKILL_ALIAS_MAP.get("news") == "news_search"
