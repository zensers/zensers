import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.fixed_agents.report_upgrade.structured_data_repair import (
    StructuredDataRepairAgent,
    RepairAttempt,
)


def _make_skill_registry(stock_data=None, knowledge_query=None):
    registry = MagicMock()
    registry.get = MagicMock(return_value=None)
    if stock_data is not None:
        def _get(name):
            if name == "stock_data":
                return stock_data
            if name == "knowledge_query":
                return knowledge_query
            return None
        registry.get = MagicMock(side_effect=_get)
    elif knowledge_query is not None:
        def _get(name):
            if name == "knowledge_query":
                return knowledge_query
            return None
        registry.get = MagicMock(side_effect=_get)
    return registry


class TestRepairAttempt:
    def test_defaults(self):
        a = RepairAttempt(gap="研发投入", source="StockDataSkill")
        assert a.gap == "研发投入"
        assert a.source == "StockDataSkill"
        assert a.found is False
        assert a.data is None

    def test_found(self):
        a = RepairAttempt(gap="净利率", source="StockDataSkill", found=True, data={"value": "5.2%"})
        assert a.found is True
        assert a.data["value"] == "5.2%"


class TestStructuredDataRepairAgentInit:
    def test_no_skill_registry(self):
        agent = StructuredDataRepairAgent(skill_registry=None)
        assert agent._registry is None

    def test_with_skill_registry(self):
        reg = _make_skill_registry()
        agent = StructuredDataRepairAgent(skill_registry=reg)
        assert agent._registry is reg


class TestTryStockData:
    @pytest.mark.asyncio
    async def test_no_registry_returns_none(self):
        agent = StructuredDataRepairAgent(skill_registry=None)
        result = await agent.try_stock_data("比亚迪", "002594")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_stock_data_skill_returns_none(self):
        reg = _make_skill_registry()
        agent = StructuredDataRepairAgent(skill_registry=reg)
        result = await agent.try_stock_data("比亚迪", "002594")
        assert result is None

    @pytest.mark.asyncio
    async def test_stock_data_returns_financials(self):
        stock_skill = AsyncMock()
        stock_skill.execute = AsyncMock(return_value={
            "success": True,
            "data": {
                "income_statement": [{"研发费用": "542亿"}],
                "balance_sheet": [],
                "cash_flow": [],
            },
            "symbol": "002594",
            "source": "akshare/East Money",
            "content": "Retrieved three financial statements for 002594",
        })
        reg = _make_skill_registry(stock_data=stock_skill)
        agent = StructuredDataRepairAgent(skill_registry=reg)
        result = await agent.try_stock_data("比亚迪", "002594")
        assert result is not None
        assert result.found is True
        assert result.source == "StockDataSkill"
        assert result.data is not None
        assert "financials" in result.data

    @pytest.mark.asyncio
    async def test_stock_data_failure_returns_none(self):
        stock_skill = AsyncMock()
        stock_skill.execute = AsyncMock(return_value={
            "success": False,
            "error": "akshare not installed",
        })
        reg = _make_skill_registry(stock_data=stock_skill)
        agent = StructuredDataRepairAgent(skill_registry=reg)
        result = await agent.try_stock_data("比亚迪", "002594")
        assert result is None

    @pytest.mark.asyncio
    async def test_stock_data_multiple_actions(self):
        call_count = 0
        results = [
            {"success": True, "data": {"营收": "6800亿"}, "symbol": "002594", "source": "akshare", "content": "key_metrics"},
            {"success": True, "data": {"income_statement": []}, "symbol": "002594", "source": "akshare", "content": "financials"},
        ]

        stock_skill = AsyncMock()

        async def _execute(**kwargs):
            nonlocal call_count
            r = results[call_count]
            call_count += 1
            return r

        stock_skill.execute = _execute
        reg = _make_skill_registry(stock_data=stock_skill)
        agent = StructuredDataRepairAgent(skill_registry=reg)
        result = await agent.try_stock_data("比亚迪", "002594")
        assert result is not None
        assert result.found is True


class TestTryKnowledgeQuery:
    @pytest.mark.asyncio
    async def test_no_registry_returns_none(self):
        agent = StructuredDataRepairAgent(skill_registry=None)
        result = await agent.try_knowledge_query("比亚迪", "新能源")
        assert result is None

    @pytest.mark.asyncio
    async def test_knowledge_query_returns_data(self):
        kq_skill = AsyncMock()
        kq_skill.execute = AsyncMock(return_value={
            "success": True,
            "message": "OK",
            "data": {"entities": [{"name": "比亚迪", "patterns": ["EV leader"]}]},
        })
        reg = _make_skill_registry(knowledge_query=kq_skill)
        agent = StructuredDataRepairAgent(skill_registry=reg)
        result = await agent.try_knowledge_query("比亚迪", "新能源")
        assert result is not None
        assert result.found is True
        assert result.source == "KnowledgeQuerySkill"

    @pytest.mark.asyncio
    async def test_knowledge_query_empty_data(self):
        kq_skill = AsyncMock()
        kq_skill.execute = AsyncMock(return_value={
            "success": True,
            "message": "no knowledge manager",
            "data": {},
        })
        reg = _make_skill_registry(knowledge_query=kq_skill)
        agent = StructuredDataRepairAgent(skill_registry=reg)
        result = await agent.try_knowledge_query("比亚迪", "新能源")
        assert result is None


class TestRepairGap:
    @pytest.mark.asyncio
    async def test_full_pipeline_stock_data_success(self):
        stock_skill = AsyncMock()
        stock_skill.execute = AsyncMock(return_value={
            "success": True,
            "data": {"income_statement": [{"研发费用": "542亿"}]},
            "symbol": "002594",
            "source": "akshare",
            "content": "financials",
        })
        reg = _make_skill_registry(stock_data=stock_skill)
        agent = StructuredDataRepairAgent(skill_registry=reg)
        attempts = await agent.repair_gap("研发投入金额", "比亚迪", "002594")
        assert len(attempts) > 0
        assert any(a.found for a in attempts)

    @pytest.mark.asyncio
    async def test_no_stock_code_falls_to_knowledge(self):
        kq_skill = AsyncMock()
        kq_skill.execute = AsyncMock(return_value={
            "success": True,
            "message": "OK",
            "data": {"entities": [{"name": "某公司"}]},
        })
        reg = _make_skill_registry(knowledge_query=kq_skill)
        agent = StructuredDataRepairAgent(skill_registry=reg)
        attempts = await agent.repair_gap("营收数据", "某公司", None)
        assert len(attempts) > 0
        assert any(a.source == "KnowledgeQuerySkill" for a in attempts)

    @pytest.mark.asyncio
    async def test_all_sources_fail(self):
        reg = _make_skill_registry()
        agent = StructuredDataRepairAgent(skill_registry=reg)
        attempts = await agent.repair_gap("某指标", "某公司", None)
        assert len(attempts) == 0
