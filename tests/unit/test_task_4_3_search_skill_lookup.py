"""
Task 4.3: Replace search_skill hardcoded lookup chains with registry.get("search_skill")
"""
import pytest
import inspect
from src.core.agents.generic_agent import GenericAgent


class TestNoLegacySearchFallbacks:
    def test_no_web_search_get(self):
        source = inspect.getsource(GenericAgent)
        for line_no, line in enumerate(source.split('\n'), 1):
            if 'registry.get("web_search")' in line:
                pytest.fail(f"Line {line_no}: still has registry.get('web_search'): {line.strip()}")

    def test_no_multi_search_get(self):
        source = inspect.getsource(GenericAgent)
        for line_no, line in enumerate(source.split('\n'), 1):
            if 'registry.get("multi_search")' in line:
                pytest.fail(f"Line {line_no}: still has registry.get('multi_search'): {line.strip()}")

    def test_no_baidu_search_get(self):
        source = inspect.getsource(GenericAgent)
        for line_no, line in enumerate(source.split('\n'), 1):
            if 'registry.get("baidu_search")' in line:
                pytest.fail(f"Line {line_no}: still has registry.get('baidu_search'): {line.strip()}")


class TestSearchSkillLookupWorks:
    @pytest.mark.asyncio
    async def test_search_skill_alias_resolves(self):
        from src.skills.registry import SkillRegistry
        registry = SkillRegistry()
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))
        registries = discovery.build_registries(manifests)
        registry._manifests = {m.name: m for m in manifests}
        registry._registries = registries
        registry._factories = {}
        registry._skills = {}

        from src.skills.search_skill import SearchSkill
        skill = SearchSkill()
        registry._skills["search_skill"] = skill

        if "web_search" in registries.alias_map:
            registry._skills["web_search"] = skill

        assert registry.get("search_skill") is not None, "search_skill must resolve"


class TestWebSearchAliasInFactory:
    def test_web_search_alias_resolves_to_search_skill(self):
        from src.core.agents.factory import DynamicAgentFactory
        assert "web_search" in DynamicAgentFactory._SKILL_ALIAS_MAP, \
            "web_search must be in _SKILL_ALIAS_MAP"
        assert DynamicAgentFactory._SKILL_ALIAS_MAP["web_search"] == "search_skill", \
            "web_search alias must resolve to search_skill"
