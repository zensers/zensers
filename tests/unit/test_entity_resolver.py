# -*- coding: utf-8 -*-
"""Tests for EntityResolver and EntityInfo — TDD cycles 1-5."""

import asyncio
import pickle
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.entity_resolver import EntityInfo, EntityResolver, get_entity_resolver

_AHOCORASICK_AVAILABLE = False
try:
    import ahocorasick
    _AHOCORASICK_AVAILABLE = True
except ImportError:
    pass


# ============================================================
# Cycle 1: EntityInfo dataclass
# ============================================================


class TestEntityInfo:
    def test_basic_creation(self):
        e = EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)
        assert e.name == "比亚迪"
        assert e.stock_code == "002594"
        assert e.is_listed is True

    def test_non_listed(self):
        e = EntityInfo(name="华为", stock_code=None, is_listed=False)
        assert e.stock_code is None
        assert e.is_listed is False

    def test_data_source_type_listed(self):
        e = EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)
        assert e.data_source_type == "structured"

    def test_data_source_type_non_listed(self):
        e = EntityInfo(name="华为", stock_code=None, is_listed=False)
        assert e.data_source_type == "search"

    def test_resolved_code_valid(self):
        e = EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)
        assert e.resolved_code == "002594"

    def test_resolved_code_none(self):
        e = EntityInfo(name="华为", stock_code=None, is_listed=False)
        assert e.resolved_code is None

    def test_resolved_code_keyword_registry_marker(self):
        e = EntityInfo(name="比亚迪", stock_code="__keyword_registry__", is_listed=True)
        assert e.resolved_code is None

    def test_to_dict(self):
        e = EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)
        d = e.to_dict()
        assert d == {"name": "比亚迪", "stock_code": "002594", "is_listed": True}

    def test_to_dict_non_listed(self):
        e = EntityInfo(name="华为", stock_code=None, is_listed=False)
        d = e.to_dict()
        assert d == {"name": "华为", "stock_code": None, "is_listed": False}

    def test_from_dict(self):
        d = {"name": "比亚迪", "stock_code": "002594", "is_listed": True}
        e = EntityInfo.from_dict(d)
        assert e.name == "比亚迪"
        assert e.stock_code == "002594"
        assert e.is_listed is True

    def test_from_dict_missing_optional(self):
        d = {"name": "华为"}
        e = EntityInfo.from_dict(d)
        assert e.name == "华为"
        assert e.stock_code is None
        assert e.is_listed is False

    def test_roundtrip(self):
        original = EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)
        restored = EntityInfo.from_dict(original.to_dict())
        assert restored == original

    def test_roundtrip_keyword_registry_marker(self):
        original = EntityInfo(name="比亚迪", stock_code="__keyword_registry__", is_listed=True)
        restored = EntityInfo.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.stock_code == original.stock_code
        assert restored.is_listed == original.is_listed
        assert restored.resolved_code is None


# ============================================================
# Cycle 2: EntityResolver._extract_entities()
# ============================================================


class TestExtractEntities:
    def setup_method(self):
        self.resolver = EntityResolver()

    def test_suffix_company(self):
        result = self.resolver._extract_entities("比亚迪股份有限公司财务分析")
        assert "比亚迪" in result

    def test_suffix_group(self):
        result = self.resolver._extract_entities("万科集团行业分析")
        assert "万科" in result

    def test_suffix_stock(self):
        result = self.resolver._extract_entities("宁德时代股份最新动态")
        assert "宁德时代" in result

    def test_suffix_limited(self):
        result = self.resolver._extract_entities("腾讯有限公司竞争格局")
        assert "腾讯" in result

    def test_no_suffix_no_automaton(self):
        self.resolver._automaton = None
        result = self.resolver._extract_entities("新能源汽车行业竞争格局分析")
        assert result == []

    @pytest.mark.skipif(not _AHOCORASICK_AVAILABLE, reason="ahocorasick not installed")
    def test_no_suffix_with_automaton_match(self):
        import ahocorasick
        auto = ahocorasick.Automaton()
        auto.add_word("比亚迪", ("比亚迪", "002594"))
        auto.add_word("宁德时代", ("宁德时代", "300750"))
        auto.make_automaton()
        self.resolver._automaton = auto
        result = self.resolver._extract_entities("比亚迪与宁德时代对比分析")
        assert "比亚迪" in result
        assert "宁德时代" in result

    @pytest.mark.skipif(not _AHOCORASICK_AVAILABLE, reason="ahocorasick not installed")
    def test_automaton_boundary_check_rejects_substring(self):
        import ahocorasick
        auto = ahocorasick.Automaton()
        auto.add_word("新能源", ("新能源", "000001"))
        auto.make_automaton()
        self.resolver._automaton = auto
        result = self.resolver._extract_entities("新能源汽车行业分析")
        assert "新能源" not in result

    @pytest.mark.skipif(not _AHOCORASICK_AVAILABLE, reason="ahocorasick not installed")
    def test_automaton_boundary_check_allows_standalone(self):
        import ahocorasick
        auto = ahocorasick.Automaton()
        auto.add_word("比亚迪", ("比亚迪", "002594"))
        auto.make_automaton()
        self.resolver._automaton = auto
        result = self.resolver._extract_entities("比亚迪财务分析")
        assert "比亚迪" in result

    def test_dedup_preserves_order(self):
        result = self.resolver._extract_entities("比亚迪股份有限公司比亚迪集团")
        assert result.count("比亚迪") == 1


# ============================================================
# Cycle 3: EntityResolver._resolve_to_code()
# ============================================================


class TestResolveToCode:
    def setup_method(self):
        self.resolver = EntityResolver()
        self.resolver._stock_name_table = {
            "比亚迪": "002594",
            "宁德时代": "300750",
            "贵州茅台": "600519",
            "东方财富": "300059",
        }
        self.resolver._table_loaded = True
        self.resolver._resolve_cache.clear()

    @pytest.mark.asyncio
    async def test_exact_match(self):
        code = await self.resolver._resolve_to_code("比亚迪")
        assert code == "002594"

    @pytest.mark.asyncio
    async def test_fuzzy_match_substring_in_table_name(self):
        code = await self.resolver._resolve_to_code("贵州茅")
        assert code == "600519"

    @pytest.mark.asyncio
    async def test_fuzzy_match_short_name_rejected(self):
        code = await self.resolver._resolve_to_code("东方")
        assert code is None

    @pytest.mark.asyncio
    async def test_no_match(self):
        code = await self.resolver._resolve_to_code("华为")
        assert code is None

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        self.resolver._resolve_cache["比亚迪"] = "002594"
        code = await self.resolver._resolve_to_code("比亚迪")
        assert code == "002594"

    @pytest.mark.asyncio
    async def test_keyword_registry_fallback(self):
        self.resolver._table_loaded = False
        self.resolver._stock_name_table.clear()
        self.resolver._resolve_cache.clear()
        with patch.object(self.resolver, "_ensure_table_loaded", new_callable=AsyncMock):
            with patch("src.core.intent.keyword_registry.get_registry") as mock_reg:
                mock_reg.return_value.is_listed_company_topic.return_value = True
                code = await self.resolver._resolve_to_code("比亚迪")
                assert code == "__keyword_registry__"

    @pytest.mark.asyncio
    async def test_keyword_registry_fallback_not_listed(self):
        self.resolver._table_loaded = False
        self.resolver._stock_name_table.clear()
        self.resolver._resolve_cache.clear()
        with patch.object(self.resolver, "_ensure_table_loaded", new_callable=AsyncMock):
            with patch("src.core.intent.keyword_registry.get_registry") as mock_reg:
                mock_reg.return_value.is_listed_company_topic.return_value = False
                code = await self.resolver._resolve_to_code("未知公司")
                assert code is None


# ============================================================
# Cycle 4: EntityResolver.resolve() — full pipeline
# ============================================================


class TestResolve:
    def setup_method(self):
        self.resolver = EntityResolver()
        self.resolver._stock_name_table = {
            "比亚迪": "002594",
            "宁德时代": "300750",
        }
        self.resolver._table_loaded = True
        self.resolver._automaton = None
        self.resolver._resolve_cache.clear()
        self.resolver._full_resolve_cache.clear()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _AHOCORASICK_AVAILABLE, reason="ahocorasick not installed")
    async def test_resolve_listed_company(self):
        import ahocorasick
        auto = ahocorasick.Automaton()
        auto.add_word("比亚迪", ("比亚迪", "002594"))
        auto.make_automaton()
        self.resolver._automaton = auto
        results = await self.resolver.resolve("比亚迪财务分析")
        assert len(results) == 1
        assert results[0].name == "比亚迪"
        assert results[0].stock_code == "002594"
        assert results[0].is_listed is True

    @pytest.mark.asyncio
    async def test_resolve_no_entities(self):
        results = await self.resolver.resolve("新能源汽车行业分析")
        assert results == []

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _AHOCORASICK_AVAILABLE, reason="ahocorasick not installed")
    async def test_resolve_caching(self):
        import ahocorasick
        auto = ahocorasick.Automaton()
        auto.add_word("比亚迪", ("比亚迪", "002594"))
        auto.make_automaton()
        self.resolver._automaton = auto
        r1 = await self.resolver.resolve("比亚迪财务分析")
        r2 = await self.resolver.resolve("比亚迪财务分析")
        assert r1 is r2

    @pytest.mark.asyncio
    async def test_resolve_keyword_registry_marker_stripped(self):
        self.resolver._table_loaded = False
        self.resolver._stock_name_table.clear()
        self.resolver._resolve_cache.clear()
        self.resolver._full_resolve_cache.clear()
        self.resolver._resolve_cache["比亚迪"] = "__keyword_registry__"
        results = await self.resolver.resolve("比亚迪股份有限公司")
        assert len(results) == 1
        assert results[0].stock_code == "__keyword_registry__"
        assert results[0].is_listed is True
        assert results[0].resolved_code is None


# ============================================================
# Cycle 5: EntityResolver._ensure_table_loaded() — disk cache
# ============================================================


class TestEnsureTableLoaded:
    def setup_method(self):
        self.resolver = EntityResolver()
        self.resolver._stock_name_table = {}
        self.resolver._table_loaded = False
        self.resolver._table_loading = False
        self.resolver._automaton = None

    @pytest.mark.asyncio
    async def test_load_from_disk_cache(self, tmp_path):
        cache_file = tmp_path / "stock_name_table.pkl"
        data = {
            "table": {"比亚迪": "002594", "宁德时代": "300750"},
            "timestamp": time.time(),
        }
        with open(cache_file, "wb") as f:
            pickle.dump(data, f)
        with patch("src.core.entity_resolver._CACHE_FILE", cache_file):
            with patch("src.core.entity_resolver._CACHE_DIR", tmp_path):
                await self.resolver._ensure_table_loaded()
        assert self.resolver._table_loaded is True
        assert self.resolver._stock_name_table["比亚迪"] == "002594"

    @pytest.mark.asyncio
    async def test_no_disk_cache_no_akshare(self, tmp_path):
        cache_file = tmp_path / "nonexistent.pkl"
        with patch("src.core.entity_resolver._CACHE_FILE", cache_file):
            with patch("src.core.entity_resolver._CACHE_DIR", tmp_path):
                with patch.object(
                    self.resolver, "_fetch_akshare_table", return_value=None
                ):
                    await self.resolver._ensure_table_loaded()
        assert self.resolver._table_loaded is False

    @pytest.mark.asyncio
    async def test_already_loaded_skips(self):
        self.resolver._table_loaded = True
        self.resolver._stock_name_table = {"比亚迪": "002594"}
        await self.resolver._ensure_table_loaded()
        assert self.resolver._stock_name_table == {"比亚迪": "002594"}


# ============================================================
# Cycle 6: _get_data_collection_skills() — pre_resolved_entities
# ============================================================


class TestGetDataCollectionSkills:
    def test_no_entities_no_topic(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("竞争格局")
        assert "stock_data" not in skills

    def test_with_listed_entity(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        entities = [EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)]
        skills = _get_data_collection_skills("竞争格局", topic="比亚迪", pre_resolved_entities=entities)
        assert "stock_data" in skills

    def test_with_non_listed_entity(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        entities = [EntityInfo(name="华为", stock_code=None, is_listed=False)]
        skills = _get_data_collection_skills("竞争格局", topic="华为", pre_resolved_entities=entities)
        assert "stock_data" not in skills

    def test_mixed_entities(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        entities = [
            EntityInfo(name="比亚迪", stock_code="002594", is_listed=True),
            EntityInfo(name="华为", stock_code=None, is_listed=False),
        ]
        skills = _get_data_collection_skills("竞争格局", topic="比亚迪与华为", pre_resolved_entities=entities)
        assert "stock_data" in skills

    def test_aspect_keyword_still_works(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("财务分析")
        assert "stock_data" in skills

    def test_no_duplicate_stock_data(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        entities = [EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)]
        skills = _get_data_collection_skills("财务分析", topic="比亚迪", pre_resolved_entities=entities)
        assert skills.count("stock_data") == 1


# ============================================================
# Cycle 7: Integration — decompose, _fetch_structured_data,
#           _generate_structured_fallback_queries, _infer_skills
# ============================================================

class TestDecomposeEntityResolution:
    """EntityResolver integration in IndustryResearchStrategy.decompose()"""

    @pytest.mark.asyncio
    async def test_decompose_resolves_entities_and_injects_context(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy, ResearchPhase
        from dataclasses import dataclass, field as f

        @dataclass
        class FakeReq:
            topic: str = "比亚迪股份有限公司竞争格局"
            aspects: list = f(default_factory=lambda: ["竞争格局"])

        strategy = IndustryResearchStrategy()
        resolver = EntityResolver()
        resolver._stock_name_table = {"比亚迪": "002594"}
        resolver._table_loaded = True
        resolver._automaton = None
        resolver._resolve_cache.clear()
        resolver._full_resolve_cache.clear()

        with patch.object(strategy, '_build_data_collection_prompt', return_value=""), \
             patch.object(strategy, '_build_validation_prompt', return_value=""), \
             patch.object(strategy, '_build_analysis_prompt', return_value=""), \
             patch.object(strategy, '_build_synthesis_prompt', return_value=""), \
             patch.object(strategy, '_build_report_prompt', return_value=""), \
             patch("src.core.entity_resolver.get_entity_resolver", return_value=resolver):
            plan = await strategy.decompose(FakeReq(), None, {})

        dc_agents = plan.phases.get(ResearchPhase.DATA_COLLECTION, [])
        assert len(dc_agents) >= 1
        agent_0 = dc_agents[0]
        assert "entities" in agent_0.context
        entities_dicts = agent_0.context["entities"]
        assert len(entities_dicts) == 1
        assert entities_dicts[0]["name"] == "比亚迪"
        assert entities_dicts[0]["is_listed"] is True

    @pytest.mark.asyncio
    async def test_decompose_no_topic_no_crash(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy, ResearchPhase
        from dataclasses import dataclass, field as f

        @dataclass
        class FakeReq:
            topic: str = ""
            aspects: list = f(default_factory=lambda: ["竞争格局"])

        strategy = IndustryResearchStrategy()
        with patch.object(strategy, '_build_data_collection_prompt', return_value=""), \
             patch.object(strategy, '_build_validation_prompt', return_value=""), \
             patch.object(strategy, '_build_analysis_prompt', return_value=""), \
             patch.object(strategy, '_build_synthesis_prompt', return_value=""), \
             patch.object(strategy, '_build_report_prompt', return_value=""):
            plan = await strategy.decompose(FakeReq(), None, {})

        dc_agents = plan.phases.get(ResearchPhase.DATA_COLLECTION, [])
        assert len(dc_agents) >= 1
        assert dc_agents[0].context.get("entities", []) == []

    @pytest.mark.asyncio
    async def test_decompose_entities_in_deep_analysis_context(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy, ResearchPhase
        from dataclasses import dataclass, field as f

        @dataclass
        class FakeReq:
            topic: str = "比亚迪股份有限公司财务分析"
            aspects: list = f(default_factory=lambda: ["财务分析"])

        strategy = IndustryResearchStrategy()
        resolver = EntityResolver()
        resolver._stock_name_table = {"比亚迪": "002594"}
        resolver._table_loaded = True
        resolver._automaton = None
        resolver._resolve_cache.clear()
        resolver._full_resolve_cache.clear()

        with patch.object(strategy, '_build_data_collection_prompt', return_value=""), \
             patch.object(strategy, '_build_validation_prompt', return_value=""), \
             patch.object(strategy, '_build_analysis_prompt', return_value=""), \
             patch.object(strategy, '_build_synthesis_prompt', return_value=""), \
             patch.object(strategy, '_build_report_prompt', return_value=""), \
             patch("src.core.entity_resolver.get_entity_resolver", return_value=resolver):
            plan = await strategy.decompose(FakeReq(), None, {})

        da_agents = plan.phases.get(ResearchPhase.DEEP_ANALYSIS, [])
        assert len(da_agents) >= 1
        assert "entities" in da_agents[0].context
        assert da_agents[0].context["entities"][0]["name"] == "比亚迪"


class TestFetchStructuredDataEntities:
    """_fetch_structured_data reads entities from context"""

    @pytest.mark.asyncio
    async def test_fetch_uses_context_entities(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test"
        agent.agent_type = "research"
        agent._context = {
            "entities": [
                {"name": "比亚迪", "stock_code": "002594", "is_listed": True},
            ]
        }

        mock_skill = AsyncMock()
        mock_skill.execute.return_value = {"success": False, "error": "test"}

        with patch.object(agent, '_extract_stock_symbol', return_value="") as mock_extract:
            result = await agent._fetch_structured_data(mock_skill, "比亚迪", "财务")

        mock_skill.execute.assert_called()
        call_args = mock_skill.execute.call_args
        assert call_args.kwargs.get("symbol") == "002594" or (call_args[1] if len(call_args) > 1 else {}).get("symbol") == "002594"

    @pytest.mark.asyncio
    async def test_fetch_multi_symbol(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test"
        agent.agent_type = "research"
        agent._context = {
            "entities": [
                {"name": "比亚迪", "stock_code": "002594", "is_listed": True},
                {"name": "宁德时代", "stock_code": "300750", "is_listed": True},
            ]
        }

        mock_skill = AsyncMock()
        mock_skill.execute.return_value = {"success": False, "error": "test"}

        with patch.object(agent, '_extract_stock_symbol', return_value=""):
            result = await agent._fetch_structured_data(mock_skill, "比亚迪 宁德时代", "财务")

        symbols_called = [
            call.kwargs.get("symbol", call[1].get("symbol", "") if len(call) > 1 else "")
            for call in mock_skill.execute.call_args_list
        ]
        assert "002594" in symbols_called
        assert "300750" in symbols_called

    @pytest.mark.asyncio
    async def test_fetch_falls_back_to_extract_stock_symbol(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test"
        agent.agent_type = "research"
        agent._context = {}

        mock_skill = AsyncMock()
        mock_skill.execute.return_value = {"success": False, "error": "test"}

        with patch.object(agent, '_extract_stock_symbol', return_value="002594"), \
             patch.object(agent, '_resolve_company_to_code', return_value=""):
            result = await agent._fetch_structured_data(mock_skill, "比亚迪", "财务")

        assert mock_skill.execute.called

    @pytest.mark.asyncio
    async def test_fetch_no_context_no_crash(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test"
        agent.agent_type = "research"

        mock_skill = AsyncMock()
        mock_skill.execute.return_value = {"success": False, "error": "test"}

        with patch.object(agent, '_extract_stock_symbol', return_value="002594"), \
             patch.object(agent, '_resolve_company_to_code', return_value=""):
            result = await agent._fetch_structured_data(mock_skill, "比亚迪", "财务")

        assert result is not None

    @pytest.mark.asyncio
    async def test_fetch_skips_non_listed_entities(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test"
        agent.agent_type = "research"
        agent._context = {
            "entities": [
                {"name": "华为", "stock_code": None, "is_listed": False},
            ]
        }

        mock_skill = AsyncMock()
        mock_skill.execute.return_value = {"success": False, "error": "test"}

        with patch.object(agent, '_extract_stock_symbol', return_value=""), \
             patch.object(agent, '_resolve_company_to_code', return_value=""):
            result = await agent._fetch_structured_data(mock_skill, "华为", "技术")

        mock_skill.execute.assert_not_called()


class TestGenerateStructuredFallbackQueriesEntities:
    """_generate_structured_fallback_queries uses entities for search"""

    def test_listed_entity_gets_annual_report_queries(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test"
        agent._context = {
            "entities": [
                {"name": "比亚迪", "stock_code": "002594", "is_listed": True},
            ]
        }
        queries = agent._generate_structured_fallback_queries("比亚迪", "财务分析")
        assert any("年报" in q for q in queries)
        assert any("比亚迪" in q for q in queries)

    def test_non_listed_entity_gets_industry_queries(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test"
        agent._context = {
            "entities": [
                {"name": "华为", "stock_code": None, "is_listed": False},
            ]
        }
        queries = agent._generate_structured_fallback_queries("华为", "技术")
        assert any("华为" in q for q in queries)
        assert any("行业分析" in q or "深度分析" in q for q in queries)

    def test_no_entities_falls_back_to_topic(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test"
        agent._context = {}
        queries = agent._generate_structured_fallback_queries("比亚迪", "财务分析")
        assert any("比亚迪" in q for q in queries)

    def test_no_context_no_crash(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test"
        queries = agent._generate_structured_fallback_queries("比亚迪", "财务分析")
        assert len(queries) >= 1


class TestInferSkillsPreResolvedEntities:
    """_infer_skills in task_structure uses pre_resolved_entities"""

    def test_listed_entity_adds_stock_analysis(self):
        from src.core.task_structure import TaskStructureAnalyzer, SectionRole
        from src.core.semantic_intent import DeepIntentResult
        from src.core.intent_types import IntentType, TaskComplexity
        analyzer = TaskStructureAnalyzer(use_llm=False)
        intent = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test",
            complexity=TaskComplexity.MULTI,
        )
        skills = analyzer._infer_skills(
            "竞争格局",
            SectionRole.ANALYSIS,
            intent,
            pre_resolved_entities=[
                {"name": "比亚迪", "stock_code": "002594", "is_listed": True},
            ],
        )
        assert "stock_analysis" in skills
        assert "data_analysis" in skills

    def test_no_entities_no_extra_skill(self):
        from src.core.task_structure import TaskStructureAnalyzer, SectionRole
        from src.core.semantic_intent import DeepIntentResult
        from src.core.intent_types import IntentType, TaskComplexity
        analyzer = TaskStructureAnalyzer(use_llm=False)
        intent = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test",
            complexity=TaskComplexity.MULTI,
        )
        skills = analyzer._infer_skills(
            "竞争格局",
            SectionRole.ANALYSIS,
            intent,
            pre_resolved_entities=[],
        )
        assert "stock_analysis" not in skills

    def test_aspect_skill_map_covers_no_duplicate(self):
        from src.core.task_structure import TaskStructureAnalyzer, SectionRole
        from src.core.semantic_intent import DeepIntentResult
        from src.core.intent_types import IntentType, TaskComplexity
        analyzer = TaskStructureAnalyzer(use_llm=False)
        intent = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test",
            complexity=TaskComplexity.MULTI,
        )
        skills = analyzer._infer_skills(
            "Financial Analysis",
            SectionRole.ANALYSIS,
            intent,
            pre_resolved_entities=[
                {"name": "比亚迪", "stock_code": "002594", "is_listed": True},
            ],
        )
        assert skills.count("stock_analysis") == 1

    def test_non_listed_entity_no_stock_analysis(self):
        from src.core.task_structure import TaskStructureAnalyzer, SectionRole
        from src.core.semantic_intent import DeepIntentResult
        from src.core.intent_types import IntentType, TaskComplexity
        analyzer = TaskStructureAnalyzer(use_llm=False)
        intent = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test",
            complexity=TaskComplexity.MULTI,
        )
        skills = analyzer._infer_skills(
            "竞争格局",
            SectionRole.ANALYSIS,
            intent,
            pre_resolved_entities=[
                {"name": "华为", "stock_code": None, "is_listed": False},
            ],
        )
        assert "stock_analysis" not in skills


# ============================================================
# Cycle 8: Integration — dynamic_orchestrator + intelligent_routing
# ============================================================

class TestDynamicOrchestratorEntityIntegration:
    """dynamic_orchestrator.to_decomposition_plan() passes entities"""

    def _make_plan(self, agent_core_question="Financial Analysis", topic="比亚迪财务分析"):
        from src.core.dynamic_orchestrator import ExecutionPlan, ExecutionPhase, AgentSpec as DynAgentSpec, PhaseType, ContentLockRule
        from src.core.task_structure import TaskStructure, SectionSpec, SectionRole

        ts = TaskStructure(
            task_id="test",
            topic=topic,
            sections=[
                SectionSpec(
                    section_id="section_0",
                    section_name=agent_core_question,
                    section_role=SectionRole.DATA_COLLECTION,
                )
            ],
            dependencies=[],
        )

        phase = ExecutionPhase(
            phase_id="phase_0",
            phase_type=PhaseType.DATA_COLLECTION,
            agent_specs=[
                DynAgentSpec(
                    agent_id="dc_0",
                    agent_type="research",
                    core_question=agent_core_question,
                    section_ids=["section_0"],
                    priority=10,
                    parallel_group=0,
                    quality_threshold=0.7,
                    max_retries=3,
                    config={},
                )
            ],
            section_ids=["section_0"],
        )
        plan = ExecutionPlan(
            plan_id="test_plan",
            task_structure=ts,
            phases=[phase],
            content_lock_rules=[],
            total_agents=1,
        )
        return plan

    def test_to_decomposition_plan_with_entities(self):
        entities = [EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)]
        plan = self._make_plan()

        from src.core.decomposition.strategies import ResearchPhase
        decomp = plan.to_decomposition_plan(pre_resolved_entities=entities)

        dc_agents = decomp.phases.get(ResearchPhase.DATA_COLLECTION, [])
        assert len(dc_agents) >= 1
        assert "entities" in dc_agents[0].context
        entity_dicts = dc_agents[0].context["entities"]
        assert len(entity_dicts) == 1
        assert entity_dicts[0]["name"] == "比亚迪"
        assert entity_dicts[0]["is_listed"] is True

    def test_to_decomposition_plan_no_entities_no_crash(self):
        plan = self._make_plan(topic="新能源汽车行业分析")

        from src.core.decomposition.strategies import ResearchPhase
        decomp = plan.to_decomposition_plan()

        dc_agents = decomp.phases.get(ResearchPhase.DATA_COLLECTION, [])
        assert len(dc_agents) >= 1
        assert "entities" not in dc_agents[0].context or dc_agents[0].context.get("entities") == []

    def test_to_decomposition_plan_listed_entity_injects_stock_data(self):
        entities = [EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)]
        plan = self._make_plan(agent_core_question="竞争格局", topic="比亚迪竞争格局")

        from src.core.decomposition.strategies import ResearchPhase
        decomp = plan.to_decomposition_plan(pre_resolved_entities=entities)

        dc_agents = decomp.phases.get(ResearchPhase.DATA_COLLECTION, [])
        assert "stock_data" in dc_agents[0].skills


class TestIntelligentRoutingAdapterEntityIntegration:
    """intelligent_routing_adapter passes entities through"""

    def test_analyze_structure_receives_entities(self):
        from src.core.task_structure import TaskStructureAnalyzer, SectionRole
        from src.core.semantic_intent import DeepIntentResult
        from src.core.intent_types import IntentType, TaskComplexity

        analyzer = TaskStructureAnalyzer(use_llm=False)
        intent = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test",
            complexity=TaskComplexity.MULTI,
        )
        entities = [EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)]

        structure = analyzer.analyze(
            intent=intent,
            aspects=["竞争格局"],
            topic="比亚迪竞争格局",
            pre_resolved_entities=entities,
        )
        assert structure is not None
        assert len(structure.sections) == 1
        assert "stock_analysis" in structure.sections[0].skill_requirements


class TestEndToEndEntityToStockData:
    """End-to-end: topic → entity resolution → stock_data injection → _fetch_structured_data"""

    @pytest.mark.asyncio
    async def test_full_flow_decompose_path(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy, ResearchPhase
        from dataclasses import dataclass, field as f

        @dataclass
        class FakeReq:
            topic: str = "比亚迪股份有限公司财务分析"
            aspects: list = f(default_factory=lambda: ["财务分析"])

        strategy = IndustryResearchStrategy()
        resolver = EntityResolver()
        resolver._stock_name_table = {"比亚迪": "002594"}
        resolver._table_loaded = True
        resolver._automaton = None
        resolver._resolve_cache.clear()
        resolver._full_resolve_cache.clear()

        with patch.object(strategy, '_build_data_collection_prompt', return_value=""), \
             patch.object(strategy, '_build_validation_prompt', return_value=""), \
             patch.object(strategy, '_build_analysis_prompt', return_value=""), \
             patch.object(strategy, '_build_synthesis_prompt', return_value=""), \
             patch.object(strategy, '_build_report_prompt', return_value=""), \
             patch("src.core.entity_resolver.get_entity_resolver", return_value=resolver):
            plan = await strategy.decompose(FakeReq(), None, {})

        dc_agents = plan.phases.get(ResearchPhase.DATA_COLLECTION, [])
        assert len(dc_agents) >= 1
        assert "stock_data" in dc_agents[0].skills
        assert "entities" in dc_agents[0].context
        entity_dicts = dc_agents[0].context["entities"]
        assert entity_dicts[0]["name"] == "比亚迪"
        assert entity_dicts[0]["stock_code"] == "002594"
        assert entity_dicts[0]["is_listed"] is True

    @pytest.mark.asyncio
    async def test_full_flow_fetch_structured_data(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test"
        agent.agent_type = "research"
        agent._context = {
            "entities": [
                {"name": "比亚迪", "stock_code": "002594", "is_listed": True},
            ]
        }

        mock_skill = AsyncMock()
        mock_skill.execute.return_value = {
            "success": True,
            "data": {"revenue": 100, "profit": 10},
            "content": "",
        }

        result = await agent._fetch_structured_data(mock_skill, "比亚迪财务分析", "财务分析")
        assert len(result["data_points"]) > 0
        assert result["data_points"][0]["quality_score"] == 95
        assert result["data_points"][0]["credibility"] == "structured_source"

    @pytest.mark.asyncio
    async def test_full_flow_non_listed_no_stock_data(self):
        from src.core.decomposition.strategies import IndustryResearchStrategy, ResearchPhase
        from dataclasses import dataclass, field as f

        @dataclass
        class FakeReq:
            topic: str = "华为技术路线"
            aspects: list = f(default_factory=lambda: ["技术路线"])

        strategy = IndustryResearchStrategy()
        resolver = EntityResolver()
        resolver._stock_name_table = {}
        resolver._table_loaded = True
        resolver._automaton = None
        resolver._resolve_cache.clear()
        resolver._full_resolve_cache.clear()

        with patch.object(strategy, '_build_data_collection_prompt', return_value=""), \
             patch.object(strategy, '_build_validation_prompt', return_value=""), \
             patch.object(strategy, '_build_analysis_prompt', return_value=""), \
             patch.object(strategy, '_build_synthesis_prompt', return_value=""), \
             patch.object(strategy, '_build_report_prompt', return_value=""), \
             patch("src.core.entity_resolver.get_entity_resolver", return_value=resolver):
            plan = await strategy.decompose(FakeReq(), None, {})

        dc_agents = plan.phases.get(ResearchPhase.DATA_COLLECTION, [])
        assert len(dc_agents) >= 1
        assert "stock_data" not in dc_agents[0].skills
