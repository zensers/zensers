"""Regression tests for manifest-driven stock-data action routing."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestManifestStockActions:
    """English and Chinese aspects use the stock_data manifest rules."""

    @pytest.fixture
    def agent(self):
        from pathlib import Path
        from src.skills.analysis.stock_data import StockDataSkill
        from src.skills.discovery import SkillDiscovery

        manifest = next(
            item for item in SkillDiscovery().discover_all(Path("src/skills"))
            if item.name == "stock_data"
        )
        skill = StockDataSkill()
        skill._manifest = manifest
        return skill

    def test_financial_aspect(self, agent):
        actions = agent.infer_actions("Financial Analysis", "600519")
        assert "financials" in actions

    def test_valuation_aspect(self, agent):
        actions = agent.infer_actions("Valuation Analysis", "600519")
        assert "key_metrics" in actions

    def test_growth_aspect(self, agent):
        actions = agent.infer_actions("Growth Analysis", "600519")
        assert "financials" in actions
        assert "key_metrics" in actions

    def test_risk_aspect(self, agent):
        actions = agent.infer_actions("Risk Analysis", "600519")
        assert "financials" in actions

    def test_sales_aspect(self, agent):
        actions = agent.infer_actions("Sales Analysis", "600519")
        assert "financials" in actions

    def test_market_share_aspect(self, agent):
        actions = agent.infer_actions("Market Share", "600519")
        assert "industry_comparison" in actions

    def test_company_analysis_aspect(self, agent):
        actions = agent.infer_actions("Company Analysis", "600519")
        assert "company_info" in actions

    def test_industry_trends_aspect(self, agent):
        actions = agent.infer_actions("Industry Trends", "600519")
        assert "industry_comparison" in actions

    def test_comprehensive_aspect(self, agent):
        actions = agent.infer_actions("Comprehensive Analysis", "600519")
        assert len(actions) >= 1

    def test_chinese_financial_aspect(self, agent):
        actions = agent.infer_actions("财务分析", "600519")
        assert "financials" in actions

    def test_chinese_valuation_aspect(self, agent):
        actions = agent.infer_actions("估值分析", "600519")
        assert "key_metrics" in actions

    def test_no_duplicate_actions(self, agent):
        actions = agent.infer_actions("Financial Risk Analysis", "600519")
        assert len(actions) == len(set(actions))


class TestStockDataCanonicalization:
    """Company-name resolution stays at the StockDataSkill boundary."""

    @pytest.mark.asyncio
    async def test_company_name_is_canonicalized_before_execution(self):
        from src.skills.analysis.stock_data import StockDataSkill

        skill = StockDataSkill()
        with patch.object(skill, "_canonicalize_symbol", new=AsyncMock(return_value="002594")), \
             patch.object(skill, "_company_info", new=AsyncMock(return_value={"success": True, "symbol": "002594"})), \
             patch.dict("sys.modules", {"akshare": MagicMock()}):
            result = await skill.execute(action="company_info", symbol="比亚迪")

        assert result["success"] is True
        assert result["symbol"] == "002594"
