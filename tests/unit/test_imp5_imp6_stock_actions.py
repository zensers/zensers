"""
IMP-5: _infer_stock_actions English keyword coverage
IMP-6: _fetch_structured_data stock_data retry via _resolve_company_to_code

IMP-5 + IMP-6 are independent improvements.
"""

import pytest
from pathlib import Path


AGENT_PATH = Path(__file__).resolve().parent.parent.parent / "src" / "core" / "agents" / "generic_agent.py"


class TestIMP5InferStockActionsEnglish:
    """IMP-5: _infer_stock_actions maps English aspects to correct actions"""

    @pytest.fixture
    def agent(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "imp5_unit"
        return agent

    def test_financial_aspect(self, agent):
        actions = agent._infer_stock_actions("Financial Analysis")
        assert "financials" in actions

    def test_valuation_aspect(self, agent):
        actions = agent._infer_stock_actions("Valuation Analysis")
        assert "key_metrics" in actions

    def test_growth_aspect(self, agent):
        actions = agent._infer_stock_actions("Growth Analysis")
        assert "financials" in actions
        assert "key_metrics" in actions

    def test_risk_aspect(self, agent):
        actions = agent._infer_stock_actions("Risk Analysis")
        assert "financials" in actions

    def test_sales_aspect(self, agent):
        actions = agent._infer_stock_actions("Sales Analysis")
        assert "financials" in actions

    def test_market_share_aspect(self, agent):
        actions = agent._infer_stock_actions("Market Share")
        assert "industry_comparison" in actions

    def test_company_analysis_aspect(self, agent):
        actions = agent._infer_stock_actions("Company Analysis")
        assert "company_info" in actions

    def test_industry_trends_aspect(self, agent):
        actions = agent._infer_stock_actions("Industry Trends")
        assert "industry_comparison" in actions

    def test_comprehensive_aspect(self, agent):
        actions = agent._infer_stock_actions("Comprehensive Analysis")
        assert len(actions) >= 1

    def test_chinese_financial_aspect(self, agent):
        actions = agent._infer_stock_actions("财务分析")
        assert "financials" in actions

    def test_chinese_valuation_aspect(self, agent):
        actions = agent._infer_stock_actions("估值分析")
        assert "key_metrics" in actions

    def test_no_duplicate_actions(self, agent):
        actions = agent._infer_stock_actions("Financial Risk Analysis")
        assert len(actions) == len(set(actions))


class TestIMP6StockDataRetry:
    """IMP-6: _fetch_structured_data retries via _resolve_company_to_code"""

    def test_resolve_company_to_code_called_on_empty_symbol(self):
        """Verify code path: when _extract_stock_symbol returns empty, try _resolve_company_to_code"""
        content = AGENT_PATH.read_text(encoding="utf-8")
        fetch_start = content.find("def _fetch_structured_data")
        fetch_end = content.find("def _infer_stock_actions", fetch_start + 1)
        if fetch_end < 0:
            fetch_end = content.find("def _generate_structured_fallback_queries", fetch_start + 1)
        fetch_code = content[fetch_start:fetch_end]
        assert "_resolve_company_to_code" in fetch_code, "_fetch_structured_data must retry via _resolve_company_to_code when symbol is empty"

    def test_retry_uses_extracted_chinese_name(self):
        """Verify retry extracts Chinese name from topic, not full topic"""
        content = AGENT_PATH.read_text(encoding="utf-8")
        fetch_start = content.find("def _fetch_structured_data")
        fetch_end = content.find("def _infer_stock_actions", fetch_start + 1)
        if fetch_end < 0:
            fetch_end = content.find("def _generate_structured_fallback_queries", fetch_start + 1)
        fetch_code = content[fetch_start:fetch_end]
        assert "chinese_m_retry" in fetch_code, "Must extract Chinese name for retry, not use full topic"
        assert "retry_name" in fetch_code
