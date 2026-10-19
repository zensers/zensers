"""Test: Chinese aspects trigger stock_data via DATA_SOURCE_SKILL_MAP"""

import pytest


class TestChineseAspectTriggersStockData:
    """Chinese-named aspects must resolve stock_data via DATA_SOURCE_SKILL_MAP"""

    def test_financial_chinese(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("财务分析", "比亚迪")
        assert "stock_data" in skills

    def test_valuation_chinese(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("估值分析", "比亚迪")
        assert "stock_data" in skills

    def test_company_chinese(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("公司分析", "比亚迪")
        assert "stock_data" in skills

    def test_profit_chinese(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("盈利能力分析", "比亚迪")
        assert "stock_data" in skills

    def test_revenue_chinese(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("营收增长", "比亚迪")
        assert "stock_data" in skills

    def test_market_cap_chinese(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("市值对比", "比亚迪")
        assert "stock_data" in skills

    def test_investment_chinese(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("投资价值", "比亚迪")
        assert "stock_data" in skills

    def test_policy_aspect_no_stock_data(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("政策环境", "新能源汽车")
        assert "stock_data" not in skills

    def test_technology_aspect_no_stock_data(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        skills = _get_data_collection_skills("技术趋势", "新能源汽车")
        assert "stock_data" not in skills

    def test_intent_result_fallback(self):
        from src.core.decomposition.strategies import _get_data_collection_skills
        from enum import Enum
        
        class FakeResearchType(Enum):
            company_research = "company_research"
            investment = "investment"
            competitive_analysis = "competitive_analysis"
        
        class FakeIntent:
            primary_research_type = FakeResearchType.company_research
        
        skills = _get_data_collection_skills("竞争格局", "比亚迪", FakeIntent())
        assert "stock_data" in skills

    def test_research_category_includes_stock_data(self):
        from src.skills.registry import SkillRegistry
        reg = SkillRegistry()
        reg._skills["stock_data"] = type("FakeSkill", (), {"name": "stock_data"})()
        skills = reg.load_skills_for_category("research")
        assert "stock_data" in skills
