"""
Task 4.4: Deprecate skill_keywords.py, discover_skills() uses manifest keywords + difflib fallback
"""
import pytest
import warnings
from src.skills.registry import SkillRegistry
from src.skills.discovery import SkillDiscovery
from pathlib import Path


@pytest.fixture
def populated_registry():
    registry = SkillRegistry()
    discovery = SkillDiscovery()
    manifests = discovery.discover_all(Path("src/skills"))
    registries = discovery.build_registries(manifests)
    registry._manifests = {m.name: m for m in manifests}
    registry._registries = registries
    registry._factories = {}
    registry._skills = {}
    return registry


class TestDiscoverSkillsUsesManifest:
    def test_discover_financial_data_finds_stock_data(self, populated_registry):
        result = populated_registry.discover_skills("financial data", auto_load=False)
        assert "stock_data" in result, f"Expected 'stock_data' in results for 'financial data', got {result}"

    def test_discover_stock_data_finds_stock_data(self, populated_registry):
        result = populated_registry.discover_skills("stock data", auto_load=False)
        assert "stock_data" in result, f"Expected 'stock_data' in results for 'stock data', got {result}"

    def test_discover_search_finds_search_skill(self, populated_registry):
        result = populated_registry.discover_skills("web search", auto_load=False)
        assert any("search" in r for r in result), f"Expected search-related skill for 'web search', got {result}"

    def test_discover_news_finds_news_search(self, populated_registry):
        result = populated_registry.discover_skills("news search", auto_load=False)
        assert any("news" in r for r in result), f"Expected news-related skill for 'news search', got {result}"

    def test_discover_xueqiu_finds_xueqiu(self, populated_registry):
        result = populated_registry.discover_skills("雪球", auto_load=False)
        assert "xueqiu" in result, f"Expected 'xueqiu' for '雪球', got {result}"


class TestDiscoverSkillsDifflibFallback:
    def test_fuzzy_match_finacial_finds_stock_data(self, populated_registry):
        result = populated_registry.discover_skills("finacial data", auto_load=False)
        assert "stock_data" in result, f"difflib fallback should match 'finacial'≈'financial', got {result}"

    def test_fuzzy_match_stok_finds_stock_data(self, populated_registry):
        result = populated_registry.discover_skills("stok data", auto_load=False)
        assert "stock_data" in result, f"difflib fallback should match 'stok'≈'stock', got {result}"


class TestSkillKeywordsDeleted:
    def test_skill_keywords_module_not_found(self):
        with pytest.raises(ModuleNotFoundError):
            from src.skills.skill_keywords import match_skills
