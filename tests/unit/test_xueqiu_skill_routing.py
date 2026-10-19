"""
XueqiuSkill 集成路由测试 — Phase 2

测试覆盖：
1. SKILL_PRIORITY_MAP["xueqiu"] == "structured_db"
2. DATA_SOURCE_SKILL_MAP 包含 xueqiu
3. _get_data_collection_skills intent 路径包含 xueqiu
4. industry_research 触发 stock_data + xueqiu
5. STRUCTURED_DATA_CAPABILITIES 包含 xueqiu
6. skill_keywords 包含 xueqiu
7. CATEGORY_TO_SKILLS 包含 xueqiu
8. Orchestrator 工厂注册 xueqiu
9. derive_data_source_type 对 xueqiu 关键词返回 "structured"
"""
import pytest
from unittest.mock import MagicMock


class TestSkillPriorityMap:
    def test_xueqiu_is_structured_db(self):
        from src.core.decomposition.strategies import SKILL_PRIORITY_MAP
        assert SKILL_PRIORITY_MAP.get("xueqiu") == "structured_db"


class TestDataSourceSkillMap:
    def test_financial_contains_xueqiu(self):
        from src.core.decomposition.strategies import DATA_SOURCE_SKILL_MAP
        assert "xueqiu" in DATA_SOURCE_SKILL_MAP.get("financial", [])

    def test_valuation_contains_xueqiu(self):
        from src.core.decomposition.strategies import DATA_SOURCE_SKILL_MAP
        assert "xueqiu" in DATA_SOURCE_SKILL_MAP.get("valuation", [])

    def test_company_contains_xueqiu(self):
        from src.core.decomposition.strategies import DATA_SOURCE_SKILL_MAP
        assert "xueqiu" in DATA_SOURCE_SKILL_MAP.get("company", [])

    def test_market_size_contains_xueqiu(self):
        from src.core.decomposition.strategies import DATA_SOURCE_SKILL_MAP
        assert "xueqiu" in DATA_SOURCE_SKILL_MAP.get("market_size", [])

    def test_chinese_financial_contains_xueqiu(self):
        from src.core.decomposition.strategies import DATA_SOURCE_SKILL_MAP
        assert "xueqiu" in DATA_SOURCE_SKILL_MAP.get("财务", [])

    def test_hot_topic_maps_to_xueqiu(self):
        from src.core.decomposition.strategies import DATA_SOURCE_SKILL_MAP
        assert "xueqiu" in DATA_SOURCE_SKILL_MAP.get("热门", [])

    def test_hk_stock_maps_to_xueqiu(self):
        from src.core.decomposition.strategies import DATA_SOURCE_SKILL_MAP
        assert "xueqiu" in DATA_SOURCE_SKILL_MAP.get("港股", [])

    def test_us_stock_maps_to_xueqiu(self):
        from src.core.decomposition.strategies import DATA_SOURCE_SKILL_MAP
        assert "xueqiu" in DATA_SOURCE_SKILL_MAP.get("美股", [])

    def test_balance_sheet_only_stock_data(self):
        from src.core.decomposition.strategies import DATA_SOURCE_SKILL_MAP
        skills = DATA_SOURCE_SKILL_MAP.get("资产负债", [])
        assert "stock_data" in skills
        assert "xueqiu" not in skills


class TestGetDataCollectionSkills:
    def _make_intent_result(self, research_type: str):
        intent = MagicMock()
        type_mock = MagicMock()
        type_mock.value = research_type
        intent.primary_research_type = type_mock
        return intent

    def test_company_research_includes_xueqiu(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        intent = self._make_intent_result("company_research")
        skills = _get_data_collection_skills("Generic Aspect", "比亚迪", intent)
        assert "xueqiu" in skills
        assert "stock_data" in skills

    def test_industry_research_includes_xueqiu_and_stock_data(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        intent = self._make_intent_result("industry_research")
        skills = _get_data_collection_skills("市场规模", "新能源汽车", intent)
        assert "xueqiu" in skills
        assert "stock_data" in skills

    def test_investment_includes_xueqiu(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        intent = self._make_intent_result("investment")
        skills = _get_data_collection_skills("投资价值", "腾讯", intent)
        assert "xueqiu" in skills

    def test_competitive_analysis_includes_xueqiu(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        intent = self._make_intent_result("competitive_analysis")
        skills = _get_data_collection_skills("竞争格局", "比亚迪", intent)
        assert "xueqiu" in skills

    def test_xueqiu_is_structured_db_tier(self):
        from src.core.decomposition.strategies import _get_data_collection_skills, SKILL_PRIORITY_MAP
        intent = self._make_intent_result("company_research")
        skills = _get_data_collection_skills("财务分析", "比亚迪", intent)
        db_skills = [s for s in skills if SKILL_PRIORITY_MAP.get(s) == "structured_db"]
        assert "xueqiu" in db_skills

    def test_aspect_keyword_triggers_xueqiu(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("财务分析", "topic", None)
        assert "xueqiu" in skills


class TestStructuredDataCapabilities:
    def test_xueqiu_capabilities_exist(self):
        from src.core.decomposition.strategies import STRUCTURED_DATA_CAPABILITIES
        assert "xueqiu" in STRUCTURED_DATA_CAPABILITIES

    def test_xueqiu_contains_turnover_rate(self):
        from src.core.decomposition.strategies import STRUCTURED_DATA_CAPABILITIES
        zh = STRUCTURED_DATA_CAPABILITIES["xueqiu"].get("zh", [])
        assert "换手率" in zh

    def test_derive_data_source_type_turnover_rate_is_structured(self):
        from src.core.decomposition.strategies import derive_data_source_type
        result = derive_data_source_type("换手率")
        assert result == "structured"

    def test_derive_data_source_type_hot_stocks_is_structured(self):
        from src.core.decomposition.strategies import derive_data_source_type
        result = derive_data_source_type("热门股票")
        assert result == "structured"


class TestSkillKeywords:
    def test_xueqiu_keyword_exists(self):
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))
        xueqiu = next((m for m in manifests if m.name == "xueqiu"), None)
        assert xueqiu is not None
        assert "行情" in xueqiu.keywords

    def test_match_skills_xueqiu(self):
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))
        registries = discovery.build_registries(manifests)
        matched = [name for name, kws in registries.keywords_map.items() if "行情" in kws]
        assert "xueqiu" in matched

    def test_match_skills_hot_stock(self):
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))
        registries = discovery.build_registries(manifests)
        matched = [name for name, kws in registries.keywords_map.items() if "热门股票" in kws]
        assert "xueqiu" in matched

    def test_xueqiu_description_exists(self):
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))
        xueqiu = next((m for m in manifests if m.name == "xueqiu"), None)
        assert xueqiu is not None
        assert xueqiu.description
        assert len(xueqiu.description) > 0


class TestCategoryToSkills:
    def test_financial_analysis_includes_xueqiu(self):
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))
        registries = discovery.build_registries(manifests)
        assert "xueqiu" in registries.category_to_skills.get("financial-analysis", [])

    def test_research_includes_xueqiu(self):
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))
        registries = discovery.build_registries(manifests)
        assert "xueqiu" in registries.category_to_skills.get("research", [])

    def test_data_collection_includes_xueqiu(self):
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))
        registries = discovery.build_registries(manifests)
        assert "xueqiu" in registries.category_to_skills.get("data-collection", [])


class TestRegistryFactory:
    def test_xueqiu_factory_creates_instance(self):
        from src.skills.registry import SkillRegistry
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        reg = SkillRegistry()
        reg.register_factory("xueqiu", XueqiuSkill)
        skill = reg.get("xueqiu")
        assert skill is not None
        assert isinstance(skill, XueqiuSkill)
        assert skill.name == "xueqiu"
