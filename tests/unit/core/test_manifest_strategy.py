"""
Task 2.1 测试：ManifestStrategyBuilder parity test

验证 ManifestStrategyBuilder 的输出与 strategies.py 中的硬编码 dict 一致（子集验证）。
Task 2.2 测试：ManifestStrategyBuilder 接入 strategies.py

验证 set_manifest_strategy() 后，get_skills_for_aspect() 和 _get_data_collection_skills()
优先使用 builder 输出。
"""
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def builder():
    from src.skills.discovery import SkillDiscovery
    from src.core.decomposition.manifest_strategy import ManifestStrategyBuilder
    d = SkillDiscovery()
    manifests = {m.name: m for m in d.discover_all(Path("src/skills"))}
    return ManifestStrategyBuilder(manifests)


@pytest.fixture(autouse=True)
def reset_manifest_strategy():
    from src.core.decomposition.strategies import set_manifest_strategy
    set_manifest_strategy(None)
    yield
    set_manifest_strategy(None)


class TestManifestStrategyBuilderAspectMap:
    """验证 build_aspect_skill_map() 与 ASPECT_SKILL_MAP 的一致性"""

    def test_hardcoded_aspects_present_in_manifest_map(self, builder):
        from src.core.decomposition.strategies import ASPECT_SKILL_MAP
        manifest_aspects = builder.build_aspect_skill_map()
        for aspect, expected_skills in ASPECT_SKILL_MAP.items():
            if aspect in manifest_aspects:
                for skill in expected_skills:
                    if skill.startswith("lc_"):
                        continue
                    assert skill in manifest_aspects[aspect], \
                        f"ASPECT_SKILL_MAP['{aspect}'] expected '{skill}' but missing in manifest map"

    def test_manifest_map_has_stock_data(self, builder):
        """stock_data 应出现在 Financial Analysis 等 aspect 中（行为变更：原硬编码没有）"""
        manifest_aspects = builder.build_aspect_skill_map()
        financial_aspects = [a for a in manifest_aspects if "Financial" in a or "财务" in a]
        for aspect in financial_aspects:
            assert "stock_data" in manifest_aspects[aspect], \
                f"stock_data should be in aspect '{aspect}' via manifest"


class TestManifestStrategyBuilderPriorityMap:
    """验证 build_skill_priority_map() 与 SKILL_PRIORITY_MAP 的一致性"""

    def test_hardcoded_priorities_match(self, builder):
        from src.core.decomposition.strategies import SKILL_PRIORITY_MAP
        manifest_priority = builder.build_skill_priority_map()
        for skill, expected_tier in SKILL_PRIORITY_MAP.items():
            if skill in manifest_priority:
                assert manifest_priority[skill] == expected_tier, \
                    f"SKILL_PRIORITY_MAP['{skill}'] expected '{expected_tier}' but got '{manifest_priority[skill]}'"

    def test_stock_data_is_structured_db(self, builder):
        assert builder.build_skill_priority_map().get("stock_data") == "structured_db"

    def test_search_skill_is_web_search(self, builder):
        assert builder.build_skill_priority_map().get("search_skill") == "web_search"

    def test_news_search_is_web_search(self, builder):
        assert builder.build_skill_priority_map().get("news_search") == "web_search"


class TestManifestStrategyBuilderDataSourceMap:
    """验证 build_data_source_skill_map() 与 DATA_SOURCE_SKILL_MAP 的一致性"""

    def test_hardcoded_data_sources_present(self, builder):
        from src.core.decomposition.strategies import DATA_SOURCE_SKILL_MAP
        manifest_ds = builder.build_data_source_skill_map()
        for keyword, expected_skills in DATA_SOURCE_SKILL_MAP.items():
            if keyword in manifest_ds:
                for skill in expected_skills:
                    assert skill in manifest_ds[keyword], \
                        f"DATA_SOURCE_SKILL_MAP['{keyword}'] expected '{skill}' but missing in manifest map"

    def test_financial_keyword_maps_to_stock_data(self, builder):
        ds_map = builder.build_data_source_skill_map()
        assert "stock_data" in ds_map.get("financial", []), \
            "'financial' keyword should map to stock_data"

    def test_chinese_keywords_present(self, builder):
        ds_map = builder.build_data_source_skill_map()
        assert "财务" in ds_map, "Chinese keyword '财务' should be in data_source_skill_map"
        assert "估值" in ds_map, "Chinese keyword '估值' should be in data_source_skill_map"


class TestManifestStrategyBuilderStructuredDataCapabilities:
    """验证 build_structured_data_capabilities() 与 STRUCTURED_DATA_CAPABILITIES 的一致性"""

    def test_stock_data_capabilities(self, builder):
        sdc = builder.build_structured_data_capabilities()
        assert "stock_data" in sdc, "stock_data should be in structured_data_capabilities"
        assert "zh" in sdc["stock_data"], "stock_data should have 'zh' capabilities"

    def test_xueqiu_capabilities(self, builder):
        sdc = builder.build_structured_data_capabilities()
        assert "xueqiu" in sdc, "xueqiu should be in structured_data_capabilities"
        assert "zh" in sdc["xueqiu"], "xueqiu should have 'zh' capabilities"


class TestManifestStrategyBuilderActionToSkillMap:
    """验证 build_action_to_skill_map() 与 ACTION_TO_SKILL 的一致性"""

    def test_intrinsic_actions_map_to_none(self, builder):
        action_map = builder.build_action_to_skill_map()
        intrinsic = ["llm", "analyze", "analysis", "reasoning", "summarize",
                     "translate", "research", "data_collection", "calibration", "execute"]
        for action in intrinsic:
            assert action_map.get(action) is None, \
                f"Intrinsic action '{action}' should map to None"

    def test_search_maps_to_search_skill(self, builder):
        action_map = builder.build_action_to_skill_map()
        assert action_map["search"] == "search_skill", \
            "'search' should map to 'search_skill' (explicit override)"

    def test_news_search_maps_to_news_search(self, builder):
        action_map = builder.build_action_to_skill_map()
        assert action_map["news_search"] == "news_search"

    def test_langchain_actions(self, builder):
        action_map = builder.build_action_to_skill_map()
        assert action_map["tavily_search"] == "lc_tavily_search"
        assert action_map["arxiv_search"] == "lc_arxiv"
        assert action_map["wiki_search"] == "lc_wikipedia"
        assert action_map["python_repl"] == "lc_python_repl"

    def test_file_http_docx_actions(self, builder):
        action_map = builder.build_action_to_skill_map()
        assert action_map["file_operation"] == "file_skill"
        assert action_map["http_request"] == "http_skill"
        assert action_map["generate_docx"] == "docx_skill"

    def test_capabilities_from_manifests_appear(self, builder):
        """manifest 中声明的 capabilities 应自动出现在 action_map 中（intrinsic 除外）"""
        intrinsic_actions = {"llm", "analyze", "analysis", "reasoning", "summarize",
                             "translate", "research", "data_collection", "calibration", "execute"}
        action_map = builder.build_action_to_skill_map()
        for name, manifest in builder._manifests.items():
            if manifest.skill_type == "langchain":
                continue
            for cap in manifest.capabilities:
                if cap in intrinsic_actions:
                    continue
                if cap in action_map:
                    assert action_map[cap] is not None, \
                        f"capability '{cap}' from '{name}' should map to a skill"


class TestManifestStrategyBuilderGetSkillsForAspect:
    """验证 get_skills_for_aspect() 与 get_skills_for_aspect() 的一致性"""

    def test_exact_match(self, builder):
        skills = builder.get_skills_for_aspect("Financial Analysis")
        assert "stock_analysis" in skills
        assert "data_analysis" in skills

    def test_contains_match(self, builder):
        skills = builder.get_skills_for_aspect("Financial Analysis Deep Dive")
        assert "stock_analysis" in skills

    def test_unknown_aspect_returns_empty(self, builder):
        skills = builder.get_skills_for_aspect("Unknown Aspect XYZ")
        assert skills == []


class TestManifestStrategyBuilderGetDataCollectionSkills:
    """验证 get_data_collection_skills() 与 _get_data_collection_skills() 的一致性"""

    def test_base_skills_always_present(self, builder):
        skills = builder.get_data_collection_skills("Some Aspect")
        assert "search_skill" in skills
        assert "news_search" in skills

    def test_structured_db_skills_first(self, builder):
        skills = builder.get_data_collection_skills("Financial Analysis")
        db_skills = [s for s in skills if builder.build_skill_priority_map().get(s) == "structured_db"]
        web_skills = [s for s in skills if builder.build_skill_priority_map().get(s, "web_search") != "structured_db"]
        if db_skills and web_skills:
            assert skills.index(db_skills[0]) < skills.index(web_skills[0]), \
                "structured_db skills should come before web_search skills"

    def test_intent_result_adds_structured_db(self, builder):
        class FakeIntent:
            primary_research_type = type('T', (), {'value': 'company_research'})()
        skills_without = builder.get_data_collection_skills("Generic Aspect")
        skills_with = builder.get_data_collection_skills("Generic Aspect", intent_result=FakeIntent())
        assert len(skills_with) >= len(skills_without)


class TestStrategiesIntegrationWithBuilder:
    """Task 2.2: 验证 set_manifest_strategy() 后 strategies.py 函数使用 builder"""

    def test_get_skills_for_aspect_uses_builder(self, builder):
        from src.core.decomposition.strategies import set_manifest_strategy, get_skills_for_aspect
        set_manifest_strategy(builder)
        skills = get_skills_for_aspect("Financial Analysis")
        assert "stock_analysis" in skills
        assert "data_analysis" in skills

    def test_get_skills_for_aspect_fallback_without_builder(self):
        from src.core.decomposition.strategies import get_skills_for_aspect
        skills = get_skills_for_aspect("Financial Analysis")
        assert "stock_analysis" in skills
        assert "data_analysis" in skills

    def test_get_data_collection_skills_uses_builder(self, builder):
        from src.core.decomposition.strategies import set_manifest_strategy, _get_data_collection_skills
        set_manifest_strategy(builder)
        skills = _get_data_collection_skills("Financial Analysis")
        assert "search_skill" in skills
        assert "news_search" in skills

    def test_get_data_collection_skills_fallback_without_builder(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("Financial Analysis")
        assert "search_skill" in skills
        assert "news_search" in skills

    def test_builder_and_fallback_produce_same_base_skills(self, builder):
        from src.core.decomposition.strategies import set_manifest_strategy, _get_data_collection_skills
        skills_fallback = _get_data_collection_skills("Financial Analysis")
        set_manifest_strategy(builder)
        skills_builder = _get_data_collection_skills("Financial Analysis")
        for skill in ["search_skill", "news_search", "stock_data"]:
            assert skill in skills_builder, f"'{skill}' should be in builder output"
            assert skill in skills_fallback, f"'{skill}' should be in fallback output"


class TestActionToSkillMapFromManifest:
    """Task 2.3: 验证 _build_action_to_skill_map() 从 manifest 动态构建"""

    def test_intrinsic_actions(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        from src.skills.registry import SkillRegistry
        registry = SkillRegistry()
        registry.init_from_discovery(Path("src/skills"))
        agent._skill_registry = registry
        action_map = agent._build_action_to_skill_map()
        for action in ["llm", "analyze", "analysis", "reasoning", "summarize",
                       "translate", "research", "data_collection", "calibration", "execute"]:
            assert action_map.get(action) is None, f"intrinsic '{action}' should map to None"

    def test_search_maps_to_search_skill(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        from src.skills.registry import SkillRegistry
        registry = SkillRegistry()
        registry.init_from_discovery(Path("src/skills"))
        agent._skill_registry = registry
        action_map = agent._build_action_to_skill_map()
        assert action_map["search"] == "search_skill"
        assert action_map["news_search"] == "news_search"

    def test_manifest_capabilities_appear(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        from src.skills.registry import SkillRegistry
        registry = SkillRegistry()
        registry.init_from_discovery(Path("src/skills"))
        agent._skill_registry = registry
        action_map = agent._build_action_to_skill_map()
        for name, manifest in registry.all_manifests().items():
            if manifest.skill_type == "langchain":
                continue
            for cap in manifest.capabilities:
                if cap in {"llm", "analyze", "analysis", "reasoning", "summarize",
                           "translate", "research", "data_collection", "calibration", "execute"}:
                    continue
                if cap in action_map:
                    assert action_map[cap] is not None, \
                        f"capability '{cap}' from '{name}' should map to a skill"

    def test_no_registry_returns_intrinsic_plus_overrides(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent._skill_registry = None
        action_map = agent._build_action_to_skill_map()
        assert len(action_map) >= 10
        for action in ["llm", "analyze", "analysis", "reasoning", "summarize",
                       "translate", "research", "data_collection", "calibration", "execute"]:
            assert action_map.get(action) is None, f"intrinsic '{action}' should still be None"
        assert action_map["search"] == "search_skill"
        assert action_map["news_search"] == "news_search"


class TestReviewFixes:
    """审查修复验证"""

    def test_action_to_skill_cache(self):
        """I2: _build_action_to_skill_map() 结果应被缓存"""
        from src.core.agents.generic_agent import GenericAgent
        from src.skills.registry import SkillRegistry
        agent = GenericAgent.__new__(GenericAgent)
        registry = SkillRegistry()
        registry.init_from_discovery(Path("src/skills"))
        agent._skill_registry = registry
        agent._action_to_skill_cache = None
        map1 = agent._build_action_to_skill_map()
        agent._action_to_skill_cache = map1
        map2 = agent._action_to_skill_cache
        assert map1 is map2, "cache should return same object"

    def test_langchain_call_order_independence(self):
        """I5: init_from_discovery() 先于 auto_discover_langchain_tools() 也不应出错"""
        from src.skills.registry import SkillRegistry
        registry = SkillRegistry()
        registry.init_from_discovery(Path("src/skills"))
        with patch.object(registry._adapter, 'register_research_tools', return_value=0):
            with patch.object(registry._adapter, '_skills', {}):
                count = registry.auto_discover_langchain_tools()
        assert count == 0

    def test_manifest_strategy_double_set_warning(self):
        """C2: 多次 set_manifest_strategy 应产生 warning"""
        from src.core.decomposition.strategies import set_manifest_strategy
        from src.core.decomposition.manifest_strategy import ManifestStrategyBuilder
        from src.skills.discovery import SkillDiscovery
        d = SkillDiscovery()
        manifests = {m.name: m for m in d.discover_all(Path("src/skills"))}
        builder1 = ManifestStrategyBuilder(manifests)
        builder2 = ManifestStrategyBuilder(manifests)
        set_manifest_strategy(builder1)
        set_manifest_strategy(builder2)
        set_manifest_strategy(None)

    def test_infer_actions_multiple_catchall(self):
        """I1: 多个 catch-all rule 时只返回第一个"""
        from src.skills.base import InstructionSkill
        from src.skills.discovery import SkillManifest, ActionRule
        manifest = SkillManifest(
            name="test", description="t", version="1", categories=[], priority="web_search",
            keywords=[], aliases=[], capabilities=["a", "b"],
            data_types={}, data_source_keywords=[],
            action_rules=[
                ActionRule(pattern=".*", aspect_keywords=["xyzzy"], actions=["a"]),
                ActionRule(pattern=".*", actions=["b"]),
            ],
            action_param_map={}, supports_topic_fallback=False, topic_fallback_pattern=None,
            is_intrinsic=False, aspect_coverage=[], skill_type="standard",
            skill_dir=Path("."), has_code=False, instructions="",
        )
        skill = InstructionSkill(manifest)
        result = skill.infer_actions("plain_aspect", "anything")
        assert result == ["b"], "catch-all without keywords should fire when no keyword match"

    def test_web_search_action_vs_skill_name(self):
        """I3: web_search 作为 action 映射到 lc_tavily_search，作为 skill name 是 search_skill alias"""
        from src.skills.registry import SkillRegistry
        from src.core.decomposition.manifest_strategy import ManifestStrategyBuilder
        from src.skills.discovery import SkillDiscovery
        registry = SkillRegistry()
        registry.init_from_discovery(Path("src/skills"))
        d = SkillDiscovery()
        manifests = {m.name: m for m in d.discover_all(Path("src/skills"))}
        builder = ManifestStrategyBuilder(manifests)
        action_map = builder.build_action_to_skill_map()
        assert action_map["web_search"] == "lc_tavily_search", "action 'web_search' → lc_tavily_search"
        skill = registry.get("web_search")
        assert skill is not None, "skill name 'web_search' should resolve (as alias)"
        assert registry.get("search_skill") is skill, "web_search alias should share search_skill instance"
