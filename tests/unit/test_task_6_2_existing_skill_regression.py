"""
Task 6.2: Existing Skill regression test

Verify stock_data, xueqiu, search_skill work correctly through the new pipeline
(_process_skill_output + format_data + manifest-driven routing).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path


def _make_registry():
    from src.skills.registry import SkillRegistry
    from src.skills.discovery import SkillDiscovery
    registry = SkillRegistry()
    discovery = SkillDiscovery()
    manifests = discovery.discover_all(Path("src/skills"))
    registries = discovery.build_registries(manifests)
    registry._manifests = {m.name: m for m in manifests}
    registry._registries = registries
    registry._factories = {}
    registry._skills = {}
    return registry, manifests


class TestStockDataThroughNewPipeline:
    @pytest.mark.asyncio
    async def test_stock_data_format_data_financials(self):
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        data = {
            "income_statement": [
                {"REPORT_DATE": "2024-03-31", "NET_PROFIT": 1500000000, "OPERATE_INCOME": 5000000000},
            ],
            "balance_sheet": [
                {"REPORT_DATE": "2024-03-31", "TOTAL_ASSETS": 200000000000},
            ],
            "cash_flow": [],
        }
        result = skill.format_data(data, "financials", "SH600519")
        assert result, "format_data should return non-empty for financials"
        assert "利润表" in result or "income_statement" in result

    @pytest.mark.asyncio
    async def test_stock_data_format_data_key_metrics(self):
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        data = {
            "periods": [
                {"report_date": "2024-03-31", "operating_income_total": 500.0, "parent_holder_net_profit": 150.0},
            ]
        }
        result = skill.format_data(data, "key_metrics", "SH600519")
        assert result, "format_data should return non-empty for key_metrics"
        assert "营业总收入" in result or "operating_income_total" in result

    @pytest.mark.asyncio
    async def test_stock_data_format_data_company_info(self):
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        data = {"股票简称": "贵州茅台", "行业": "白酒", "总股本": "12.56亿"}
        result = skill.format_data(data, "company_info", "SH600519")
        assert result, "format_data should return non-empty for company_info"
        assert "贵州茅台" in result

    @pytest.mark.asyncio
    async def test_stock_data_format_data_price_history(self):
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        data = {
            "records": [
                {"date": "2024-01-02", "close": 1800.5, "high": 1850.0, "low": 1780.0},
                {"date": "2024-01-03", "close": 1790.0, "high": 1810.0, "low": 1775.0},
            ]
        }
        result = skill.format_data(data, "price_history", "SH600519")
        assert result, "format_data should return non-empty for price_history"
        assert "1800" in result or "股价" in result

    @pytest.mark.asyncio
    async def test_stock_data_manifest_action_inference(self):
        registry, manifests = _make_registry()
        stock_manifest = next((m for m in manifests if m.name == "stock_data"), None)
        assert stock_manifest is not None
        assert stock_manifest.action_rules, "stock_data must have action_rules"

        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        skill._manifest = stock_manifest
        actions = skill.infer_actions("盈利能力分析", "SH600519")
        assert "financials" in actions

    @pytest.mark.asyncio
    async def test_stock_data_manifest_priority(self):
        registry, manifests = _make_registry()
        stock_manifest = next((m for m in manifests if m.name == "stock_data"), None)
        assert stock_manifest is not None
        assert stock_manifest.priority == "structured_db"

    @pytest.mark.asyncio
    async def test_stock_data_process_skill_output(self):
        from src.core.agents.generic_agent import GenericAgent
        from src.skills.analysis.stock_data import StockDataSkill
        registry, manifests = _make_registry()

        skill = StockDataSkill()
        registry._skills["stock_data"] = skill

        agent = GenericAgent(agent_id="test", agent_type="dynamic", config={})
        agent._skill_registry = registry

        mock_execute = AsyncMock(return_value={
            "success": True,
            "data": {"income_statement": [{"REPORT_DATE": "2024-03-31", "NET_PROFIT": 1500000000}]},
            "content": "",
        })
        skill.execute = mock_execute

        result = await agent._process_skill_output(
            skill, "stock_data", "贵州茅台", "财务分析", registry,
        )
        assert len(result.get("data_points", [])) > 0
        dp = result["data_points"][0]
        assert dp["quality_score"] == 95
        assert dp["credibility"] == "structured_source"


class TestXueqiuThroughNewPipeline:
    @pytest.mark.asyncio
    async def test_xueqiu_format_data_quote(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        skill = XueqiuSkill()
        data = {"name": "贵州茅台", "symbol": "SH600519", "current": 1800.5, "percent": 1.5, "market_capital": "2.2万亿", "pe_ttm": 30.2, "turnover_rate": "0.5%"}
        result = skill.format_data(data, "quote", "SH600519")
        assert result, "format_data should return non-empty for quote"
        assert "1800" in result or "贵州茅台" in result

    @pytest.mark.asyncio
    async def test_xueqiu_format_data_kline(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        skill = XueqiuSkill()
        data = {"records": [{"date": "2024-01-02", "close": 1800.5}]}
        result = skill.format_data(data, "kline", "SH600519")
        assert result, "format_data should return non-empty for kline"

    @pytest.mark.asyncio
    async def test_xueqiu_format_data_hot_stocks(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        skill = XueqiuSkill()
        data = {"records": [{"rank": 1, "name": "贵州茅台", "symbol": "SH600519", "current": 1800.5, "percent": 1.5}]}
        result = skill.format_data(data, "hot_stocks", "SH600519")
        assert result, "format_data should return non-empty for hot_stocks"

    @pytest.mark.asyncio
    async def test_xueqiu_manifest_priority(self):
        registry, manifests = _make_registry()
        xueqiu_manifest = next((m for m in manifests if m.name == "xueqiu"), None)
        assert xueqiu_manifest is not None
        assert xueqiu_manifest.priority == "structured_db"

    @pytest.mark.asyncio
    async def test_xueqiu_process_skill_output(self):
        from src.core.agents.generic_agent import GenericAgent
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        registry, manifests = _make_registry()

        skill = XueqiuSkill()
        registry._skills["xueqiu"] = skill

        agent = GenericAgent(agent_id="test", agent_type="dynamic", config={})
        agent._skill_registry = registry

        mock_execute = AsyncMock(return_value={
            "success": True,
            "data": {"name": "贵州茅台", "symbol": "SH600519", "current": 1800.5, "percent": 1.5},
            "content": "",
        })
        skill.execute = mock_execute

        result = await agent._process_skill_output(
            skill, "xueqiu", "贵州茅台", "行情", registry,
        )
        assert len(result.get("data_points", [])) > 0
        dp = result["data_points"][0]
        assert dp["quality_score"] == 95
        assert dp["credibility"] == "structured_source"


class TestSearchSkillThroughNewPipeline:
    @pytest.mark.asyncio
    async def test_search_skill_manifest_priority(self):
        registry, manifests = _make_registry()
        search_manifest = next((m for m in manifests if m.name == "search_skill"), None)
        assert search_manifest is not None
        assert search_manifest.priority == "web_search"

    @pytest.mark.asyncio
    async def test_search_skill_process_search_skill(self):
        from src.core.agents.generic_agent import GenericAgent
        from src.skills.registry import SkillRegistry
        from src.skills.discovery import SkillDiscovery

        registry = SkillRegistry()
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))
        registries = discovery.build_registries(manifests)
        registry._manifests = {m.name: m for m in manifests}
        registry._registries = registries
        registry._skills = {}
        registry._factories = {}

        mock_search = AsyncMock()
        mock_search.name = "search_skill"
        registry._skills["search_skill"] = mock_search

        agent = GenericAgent(agent_id="test", agent_type="dynamic", config={})
        agent._skill_registry = registry
        agent._do_deep_research = AsyncMock(return_value={
            "searches": [
                {
                    "results": [
                        {"title": "Test Result", "body": "Test content", "href": "http://test.com", "quality_score": 80},
                    ]
                }
            ]
        })

        result = await agent._process_skill_output(
            mock_search, "search_skill", "test topic", "test aspect", registry,
        )
        assert len(result.get("data_points", [])) > 0
        dp = result["data_points"][0]
        assert "content" in dp
        assert dp.get("url", "") == "http://test.com"

    @pytest.mark.asyncio
    async def test_news_search_manifest_priority(self):
        registry, manifests = _make_registry()
        news_manifest = next((m for m in manifests if m.name == "news_search"), None)
        assert news_manifest is not None
        assert news_manifest.priority == "web_search"

    @pytest.mark.asyncio
    async def test_news_search_process_news_skill(self):
        from src.core.agents.generic_agent import GenericAgent
        from src.skills.registry import SkillRegistry
        from src.skills.discovery import SkillDiscovery

        registry = SkillRegistry()
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))
        registries = discovery.build_registries(manifests)
        registry._manifests = {m.name: m for m in manifests}
        registry._registries = registries
        registry._skills = {}
        registry._factories = {}

        mock_news = AsyncMock()
        mock_news.name = "news_search"
        mock_news.execute = AsyncMock(return_value={
            "success": True,
            "results": [
                {"title": "News1", "body": "Content1", "href": "http://1", "source": "src1", "date": "2024-01"},
            ],
        })
        registry._skills["news_search"] = mock_news

        agent = GenericAgent(agent_id="test", agent_type="dynamic", config={})
        agent._skill_registry = registry

        result = await agent._process_skill_output(
            mock_news, "news_search", "test topic", "test aspect", registry,
        )
        assert len(result.get("data_points", [])) > 0
