"""Test: DATA_SOURCE_PRIORITY — structured_db > web_search > llm"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.decomposition.strategies import (
    DATA_SOURCE_PRIORITY,
    SKILL_PRIORITY_MAP,
    _get_data_collection_skills,
)


class TestPriorityConstants:
    def test_structured_db_highest(self):
        assert DATA_SOURCE_PRIORITY["structured_db"] > DATA_SOURCE_PRIORITY["web_search"]

    def test_web_search_above_llm(self):
        assert DATA_SOURCE_PRIORITY["web_search"] > DATA_SOURCE_PRIORITY["llm"]

    def test_stock_data_is_structured_db(self):
        assert SKILL_PRIORITY_MAP["stock_data"] == "structured_db"

    def test_wind_data_is_structured_db(self):
        assert SKILL_PRIORITY_MAP["wind_data"] == "structured_db"

    def test_bloomberg_data_is_structured_db(self):
        assert SKILL_PRIORITY_MAP["bloomberg_data"] == "structured_db"

    def test_search_skill_is_web_search(self):
        assert SKILL_PRIORITY_MAP["search_skill"] == "web_search"

    def test_news_search_is_web_search(self):
        assert SKILL_PRIORITY_MAP["news_search"] == "web_search"

    def test_llm_skill_is_llm(self):
        assert SKILL_PRIORITY_MAP["llm_skill"] == "llm"


class TestSkillOrdering:
    def test_financial_aspect_stock_data_first(self):
        skills = _get_data_collection_skills("财务分析", "比亚迪")
        assert skills.index("stock_data") < skills.index("search_skill")
        assert skills.index("stock_data") < skills.index("llm_skill")

    def test_valuation_aspect_stock_data_first(self):
        skills = _get_data_collection_skills("估值分析", "比亚迪")
        assert skills.index("stock_data") < skills.index("search_skill")

    def test_non_financial_aspect_no_stock_data(self):
        skills = _get_data_collection_skills("政策环境", "新能源汽车")
        assert "stock_data" not in skills
        assert "search_skill" in skills
        assert "llm_skill" in skills

    def test_llm_skill_always_last(self):
        for aspect in ["财务分析", "政策环境", "技术趋势", "市场分析"]:
            skills = _get_data_collection_skills(aspect, "比亚迪")
            if "llm_skill" in skills and len(skills) > 1:
                assert skills.index("llm_skill") == len(skills) - 1

    def test_structured_db_before_web_before_llm(self):
        skills = _get_data_collection_skills("财务分析", "比亚迪")
        tiers = [SKILL_PRIORITY_MAP.get(s, "web_search") for s in skills]
        for i in range(len(tiers) - 1):
            assert DATA_SOURCE_PRIORITY[tiers[i]] >= DATA_SOURCE_PRIORITY[tiers[i + 1]]

    def test_intent_result_stock_data_still_first(self):
        from enum import Enum

        class FakeResearchType(Enum):
            company_research = "company_research"

        class FakeIntent:
            primary_research_type = FakeResearchType.company_research

        skills = _get_data_collection_skills("竞争格局", "比亚迪", FakeIntent())
        assert "stock_data" in skills
        assert skills.index("stock_data") < skills.index("search_skill")


class TestAgentExecutionPriority:
    """Test that generic_agent executes structured_db skills before web_search"""

    def _make_agent(self, skills=None):
        from src.core.agents.generic_agent import GenericAgent
        mock_registry = MagicMock()
        mock_registry.get = MagicMock(return_value=MagicMock())
        config = {
            "name": "test",
            "category": "research",
            "skills": skills or ["stock_data", "search_skill", "news_search", "llm_skill"],
            "required_skills": ["stock_data"],
            "optional_skills": ["search_skill", "news_search", "llm_skill"],
            "skill_registry": mock_registry,
            "context": {},
        }
        return GenericAgent(agent_id="test_agent", agent_type="dynamic", config=config)

    @pytest.mark.asyncio
    async def test_structured_db_executed_before_search(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = self._make_agent()
        call_order = []

        async def mock_fetch(self_inner, skill, topic, aspect, skill_name="stock_data"):
            call_order.append("structured_db")
            return {"data_points": [{"title": "test", "content": "data", "url": "akshare://test", "quality_score": 95, "credibility": "structured_source"}], "sources": [], "canonical_metrics": {}}

        async def mock_research(self_inner, topic, aspect, aspects, skill_registry, preloaded_search_results=None, depth="deep"):
            call_order.append("web_search")
            return {"searches": [], "total_sources": 0, "quality_stats": {}}

        with patch.object(GenericAgent, '_fetch_structured_data', mock_fetch), \
             patch.object(GenericAgent, '_do_deep_research', mock_research):
            result = await agent.execute({
                "action": "research",
                "topic": "比亚迪财务分析",
                "aspect": "财务分析",
            })
            assert call_order[0] == "structured_db"
            assert "web_search" in call_order

    @pytest.mark.asyncio
    async def test_sufficient_structured_data_uses_basic_depth(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = self._make_agent()
        depth_used = {"value": None}

        async def mock_fetch(self_inner, skill, topic, aspect, skill_name="stock_data"):
            dps = [{"title": f"dp{i}", "content": f"data{i}", "url": f"akshare://test/{i}", "quality_score": 95, "credibility": "structured_source"} for i in range(5)]
            return {"data_points": dps, "sources": [], "canonical_metrics": {}}

        async def mock_research(self_inner, topic, aspect, aspects, skill_registry, preloaded_search_results=None, depth="deep"):
            depth_used["value"] = depth
            return {"searches": [], "total_sources": 0, "quality_stats": {}}

        with patch.object(GenericAgent, '_fetch_structured_data', mock_fetch), \
             patch.object(GenericAgent, '_do_deep_research', mock_research):
            result = await agent.execute({
                "action": "research",
                "topic": "比亚迪财务分析",
                "aspect": "财务分析",
            })
            assert depth_used["value"] == "basic"

    @pytest.mark.asyncio
    async def test_insufficient_structured_data_uses_deep_depth(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = self._make_agent()
        depth_used = {"value": None}

        async def mock_fetch(self_inner, skill, topic, aspect, skill_name="stock_data"):
            return {"data_points": [], "sources": [], "canonical_metrics": {}}

        async def mock_research(self_inner, topic, aspect, aspects, skill_registry, preloaded_search_results=None, depth="deep"):
            depth_used["value"] = depth
            return {"searches": [], "total_sources": 0, "quality_stats": {}}

        with patch.object(GenericAgent, '_fetch_structured_data', mock_fetch), \
             patch.object(GenericAgent, '_do_deep_research', mock_research):
            result = await agent.execute({
                "action": "research",
                "topic": "比亚迪财务分析",
                "aspect": "财务分析",
            })
            assert depth_used["value"] == "deep"

    @pytest.mark.asyncio
    async def test_news_search_reduced_when_structured_sufficient(self):
        from src.core.agents.generic_agent import GenericAgent

        news_max_results = {"value": None}

        async def mock_fetch(self_inner, skill, topic, aspect, skill_name="stock_data"):
            dps = [{"title": f"dp{i}", "content": f"data{i}", "url": f"akshare://test/{i}", "quality_score": 95, "credibility": "structured_source"} for i in range(5)]
            return {"data_points": dps, "sources": [], "canonical_metrics": {}}

        async def mock_research(self_inner, topic, aspect, aspects, skill_registry, preloaded_search_results=None, depth="deep"):
            return {"searches": [], "total_sources": 0, "quality_stats": {}}

        mock_news_skill = MagicMock()
        async def mock_news_execute(**kwargs):
            news_max_results["value"] = kwargs.get("max_results", 0)
            return {"success": True, "results": []}
        mock_news_skill.execute = mock_news_execute

        mock_registry = MagicMock()
        def registry_get(name):
            if name == "news_search":
                return mock_news_skill
            return MagicMock()
        mock_registry.get = registry_get

        config = {
            "name": "test",
            "category": "research",
            "skills": ["stock_data", "search_skill", "news_search", "llm_skill"],
            "required_skills": ["stock_data"],
            "optional_skills": ["search_skill", "news_search", "llm_skill"],
            "skill_registry": mock_registry,
            "context": {},
        }
        agent = GenericAgent(agent_id="test_agent4", agent_type="dynamic", config=config)

        with patch.object(GenericAgent, '_fetch_structured_data', mock_fetch), \
             patch.object(GenericAgent, '_do_deep_research', mock_research):
            result = await agent.execute({
                "action": "research",
                "topic": "比亚迪财务分析",
                "aspect": "财务分析",
            })
            assert news_max_results["value"] == 5

    @pytest.mark.asyncio
    async def test_structured_only_no_web_search_returns_success(self):
        from src.core.agents.generic_agent import GenericAgent

        async def mock_fetch(self_inner, skill, topic, aspect, skill_name="stock_data"):
            dps = [{"title": f"dp{i}", "content": f"data{i}", "url": f"akshare://test/{i}", "quality_score": 95, "credibility": "structured_source"} for i in range(3)]
            return {"data_points": dps, "sources": [{"title": "akshare", "url": "akshare://test", "type": "structured", "quality_score": 95}], "canonical_metrics": {}}

        mock_registry = MagicMock()
        mock_registry.get = MagicMock(return_value=MagicMock())

        config = {
            "name": "test",
            "category": "research",
            "skills": ["stock_data", "llm_skill"],
            "required_skills": ["stock_data"],
            "optional_skills": ["llm_skill"],
            "skill_registry": mock_registry,
            "context": {},
        }
        agent = GenericAgent(agent_id="test_db_only", agent_type="dynamic", config=config)

        with patch.object(GenericAgent, '_fetch_structured_data', mock_fetch):
            result = await agent.execute({
                "action": "research",
                "topic": "比亚迪财务分析",
                "aspect": "财务分析",
            })
            assert result["success"] is True
            assert len(result["data_points"]) == 3
            assert len(result["sources"]) == 1

    @pytest.mark.asyncio
    async def test_no_data_sources_returns_failure(self):
        from src.core.agents.generic_agent import GenericAgent

        mock_registry = MagicMock()
        mock_registry.get = MagicMock(return_value=None)

        config = {
            "name": "test",
            "category": "research",
            "skills": ["llm_skill"],
            "required_skills": [],
            "optional_skills": ["llm_skill"],
            "skill_registry": mock_registry,
            "context": {},
        }
        agent = GenericAgent(agent_id="test_no_data", agent_type="dynamic", config=config)

        result = await agent.execute({
            "action": "research",
            "topic": "比亚迪财务分析",
            "aspect": "财务分析",
        })
        assert result["success"] is False
