"""
Task 3.1 测试：_process_skill_output() 及辅助方法

验证通用数据管道的每个方法独立正确。
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch


def _make_agent():
    from src.core.agents.generic_agent import GenericAgent
    agent = GenericAgent.__new__(GenericAgent)
    agent.agent_id = "test_agent"
    agent._skill_registry = MagicMock()
    agent._shared_memory = MagicMock()
    agent._shared_memory.write_canonical = AsyncMock()
    agent._message_bus = MagicMock()
    agent._message_bus.publish = AsyncMock()
    agent._context = {}
    agent._available_skills = ["stock_data", "search_skill", "news_search"]
    agent._action_to_skill_cache = None
    agent._extract_stock_symbol = MagicMock(return_value="SH600519")
    agent._resolve_company_to_code = MagicMock(return_value="SH600519")
    return agent


class TestToReadableContent:
    """三层内容转换测试"""

    @pytest.mark.asyncio
    async def test_l1_skill_content(self):
        agent = _make_agent()
        skill_result = {"success": True, "content": "贵州茅台(SH600519): 当前价1800.5", "data": {}}
        content = await agent._to_readable_content(
            skill_result, None, {}, "quote", "SH600519", "xueqiu", "茅台"
        )
        assert "1800.5" in content

    @pytest.mark.asyncio
    async def test_l2_format_data(self):
        agent = _make_agent()
        skill_result = {"success": True, "content": "", "data": {"current": 1800}}
        class MockSkill:
            def format_data(self, data, action, symbol):
                return f"当前价 {data.get('current')}"
        content = await agent._to_readable_content(
            skill_result, MockSkill(), {"current": 1800}, "quote", "SH600519", "xueqiu", "茅台"
        )
        assert "1800" in content

    @pytest.mark.asyncio
    async def test_l2_overrides_l1_when_longer(self):
        agent = _make_agent()
        skill_result = {"success": True, "content": "短", "data": {"current": 1800}}
        class MockSkill:
            def format_data(self, data, action, symbol):
                return f"格式化输出: 当前价 {data.get('current')}"
        content = await agent._to_readable_content(
            skill_result, MockSkill(), {"current": 1800}, "quote", "SH600519", "xueqiu", "茅台"
        )
        assert "格式化输出" in content

    @pytest.mark.asyncio
    async def test_json_dump_fallback(self):
        agent = _make_agent()
        agent._skill_registry.get_manifest = MagicMock(return_value=None)
        skill_result = {"success": True, "content": "", "data": {}}
        data = {"key": "value", "num": 42}
        content = await agent._to_readable_content(
            skill_result, None, data, "default", "SH600519", "stock_data", "茅台"
        )
        parsed = json.loads(content)
        assert parsed["key"] == "value"
        assert parsed["num"] == 42

    @pytest.mark.asyncio
    async def test_f5_truncation_large_data(self):
        agent = _make_agent()
        agent._skill_registry.get_manifest = MagicMock(return_value=None)
        big_data = {f"key_{i}": "x" * 100 for i in range(100)}
        content = await agent._to_readable_content(
            {"success": True, "content": "", "data": big_data}, None, big_data,
            "default", "SH600519", "stock_data", "茅台"
        )
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_f3_f4_json_dump_with_default_str(self):
        agent = _make_agent()
        agent._skill_registry.get_manifest = MagicMock(return_value=None)
        from datetime import datetime
        data = {"date": datetime(2024, 1, 1), "value": 42}
        content = await agent._to_readable_content(
            {"success": True, "content": "", "data": data}, None, data,
            "default", "SH600519", "stock_data", "茅台"
        )
        assert "42" in content


class TestResolveIdentifiers:
    """identifier 解析测试"""

    def test_from_context_entities(self):
        agent = _make_agent()
        agent._context = {"entities": [{"is_listed": True, "resolved_code": "SH600519", "name": "贵州茅台"}]}
        ids = agent._resolve_identifiers("stock_data", "贵州茅台", "财务分析", agent._skill_registry)
        assert ids == ["SH600519"]

    def test_from_topic_stock_symbol(self):
        agent = _make_agent()
        agent._context = {}
        ids = agent._resolve_identifiers("stock_data", "SH600519", "财务分析", agent._skill_registry)
        assert "SH600519" in ids

    def test_empty_returns_empty_list(self):
        agent = _make_agent()
        agent._context = {}
        agent._extract_stock_symbol = MagicMock(return_value="")
        agent._resolve_company_to_code = MagicMock(return_value="")
        agent._skill_registry.get_manifest = MagicMock(return_value=None)
        ids = agent._resolve_identifiers("stock_data", "unknown", "财务分析", agent._skill_registry)
        assert ids == []


class TestInferActionsFromManifest:
    """action 推断测试"""

    def test_with_manifest_and_skill(self):
        from src.skills.discovery import SkillManifest, ActionRule
        from src.skills.base import InstructionSkill
        agent = _make_agent()
        manifest = SkillManifest(
            name="test", description="t", version="1", categories=[], priority="structured_db",
            keywords=[], aliases=[], capabilities=["financials"],
            data_types={}, data_source_keywords=[],
            action_rules=[ActionRule(pattern=".*", aspect_keywords=["盈利"], actions=["financials"])],
            action_param_map={"financials": {"symbol": "symbol"}},
            supports_topic_fallback=False, topic_fallback_pattern=None,
            is_intrinsic=False, aspect_coverage=[], skill_type="standard",
            skill_dir=MagicMock(), has_code=False, instructions="",
        )
        skill = InstructionSkill(manifest)
        actions = agent._infer_actions_from_manifest(manifest, skill, "盈利分析", "SH600519")
        assert "financials" in actions

    def test_without_manifest_returns_default(self):
        agent = _make_agent()
        actions = agent._infer_actions_from_manifest(None, None, "any", "SH600519")
        assert actions == ["default"]


class TestBuildExecuteKwargs:
    """execute 参数构建测试"""

    def test_with_manifest_action_param_map(self):
        from src.skills.discovery import SkillManifest
        agent = _make_agent()
        manifest = SkillManifest(
            name="stock_data", description="t", version="1", categories=[], priority="structured_db",
            keywords=[], aliases=[], capabilities=["financials"],
            data_types={}, data_source_keywords=[], action_rules=[],
            action_param_map={"financials": {"symbol": "symbol"}},
            supports_topic_fallback=False, topic_fallback_pattern=None,
            is_intrinsic=False, aspect_coverage=[], skill_type="standard",
            skill_dir=MagicMock(), has_code=False, instructions="",
        )
        kwargs = agent._build_execute_kwargs(manifest, "financials", "SH600519", "茅台")
        assert kwargs == {"action": "financials", "symbol": "SH600519"}

    def test_without_manifest_defaults_to_symbol(self):
        agent = _make_agent()
        kwargs = agent._build_execute_kwargs(None, "default", "SH600519", "茅台")
        assert kwargs == {"action": "default", "symbol": "SH600519"}


class TestProcessSkillOutput:
    """_process_skill_output 完整流程测试"""

    @pytest.mark.asyncio
    async def test_structured_db_skill(self):
        from src.skills.discovery import SkillManifest, ActionRule
        agent = _make_agent()
        mock_skill = MagicMock()
        mock_skill.execute = AsyncMock(return_value={
            "success": True,
            "data": {"净利润": 150.5, "营收": 500.0},
            "content": "净利润150.5亿 营收500亿",
        })
        mock_skill._manifest = None
        mock_skill.infer_actions = MagicMock(return_value=["financials"])
        manifest = SkillManifest(
            name="stock_data", description="t", version="1", categories=[], priority="structured_db",
            keywords=[], aliases=[], capabilities=["financials"],
            data_types={}, data_source_keywords=[],
            action_rules=[ActionRule(pattern=".*", actions=["financials"])],
            action_param_map={"financials": {"symbol": "symbol"}},
            supports_topic_fallback=False, topic_fallback_pattern=None,
            is_intrinsic=False, aspect_coverage=[], skill_type="standard",
            skill_dir=MagicMock(), has_code=False, instructions="",
        )
        agent._skill_registry.get_manifest = MagicMock(return_value=manifest)
        agent._skill_registry.get = MagicMock(return_value=mock_skill)
        agent._context = {"entities": [{"is_listed": True, "resolved_code": "SH600519", "name": "贵州茅台"}]}
        result = await agent._process_skill_output(
            mock_skill, "stock_data", "贵州茅台", "财务分析", agent._skill_registry
        )
        assert len(result["data_points"]) > 0
        assert result["data_points"][0]["quality_score"] == 95
        assert result["data_points"][0]["credibility"] == "structured_source"

    @pytest.mark.asyncio
    async def test_f1_skill_returns_none(self):
        agent = _make_agent()
        mock_skill = AsyncMock()
        mock_skill.execute = AsyncMock(return_value=None)
        agent._skill_registry.get_manifest = MagicMock(return_value=None)
        agent._skill_registry.get = MagicMock(return_value=mock_skill)
        agent._context = {"entities": [{"is_listed": True, "resolved_code": "SH600519", "name": "贵州茅台"}]}
        result = await agent._process_skill_output(
            mock_skill, "stock_data", "贵州茅台", "财务分析", agent._skill_registry
        )
        assert result["data_points"] == []

    @pytest.mark.asyncio
    async def test_f2_skill_returns_non_dict(self):
        """F2 fix: 非dict结果应被包装为success=True以保留content"""
        agent = _make_agent()
        mock_skill = MagicMock()
        mock_skill.execute = AsyncMock(return_value="error string")
        mock_skill._manifest = None
        mock_skill.infer_actions = MagicMock(return_value=["default"])
        mock_skill.format_data = MagicMock(return_value="")
        agent._skill_registry.get_manifest = MagicMock(return_value=None)
        agent._skill_registry.get = MagicMock(return_value=mock_skill)
        agent._context = {"entities": [{"is_listed": True, "resolved_code": "SH600519", "name": "贵州茅台"}]}
        result = await agent._process_skill_output(
            mock_skill, "stock_data", "贵州茅台", "财务分析", agent._skill_registry
        )
        assert len(result["data_points"]) > 0
        assert "error string" in result["data_points"][0]["content"]

    @pytest.mark.asyncio
    async def test_f6_data_is_none(self):
        agent = _make_agent()
        mock_skill = AsyncMock()
        mock_skill.execute = AsyncMock(return_value={
            "success": True, "data": None, "content": "some content",
        })
        agent._skill_registry.get_manifest = MagicMock(return_value=None)
        agent._skill_registry.get = MagicMock(return_value=mock_skill)
        agent._context = {"entities": [{"is_listed": True, "resolved_code": "SH600519", "name": "贵州茅台"}]}
        result = await agent._process_skill_output(
            mock_skill, "stock_data", "贵州茅台", "财务分析", agent._skill_registry
        )
        assert len(result["data_points"]) > 0


class TestProcessNewsSkill:
    """_process_news_skill 测试"""

    @pytest.mark.asyncio
    async def test_news_results_at_top_level(self):
        agent = _make_agent()
        mock_news = AsyncMock()
        mock_news.execute = AsyncMock(return_value={
            "success": True,
            "results": [
                {"title": "新闻1", "body": "内容1", "href": "http://1", "source": "源1", "date": "2024-01"},
            ],
        })
        result = await agent._process_news_skill(mock_news, "比亚迪", "财务分析", max_results=10)
        assert len(result["data_points"]) == 1
        assert result["data_points"][0]["quality_score"] == 70
        assert result["data_points"][0]["source_type"] == "news"

    @pytest.mark.asyncio
    async def test_f12_non_dict_news_item_skipped(self):
        agent = _make_agent()
        mock_news = AsyncMock()
        mock_news.execute = AsyncMock(return_value={
            "success": True,
            "results": ["string_item", {"title": "ok", "body": "b", "href": "u"}],
        })
        result = await agent._process_news_skill(mock_news, "比亚迪", "财务分析")
        assert len(result["data_points"]) == 1
        assert result["data_points"][0]["title"] == "ok"

    @pytest.mark.asyncio
    async def test_news_failure_returns_empty(self):
        agent = _make_agent()
        mock_news = AsyncMock()
        mock_news.execute = AsyncMock(side_effect=Exception("API error"))
        result = await agent._process_news_skill(mock_news, "比亚迪", "财务分析")
        assert result["data_points"] == []


class TestStockDataFormatData:
    """Task 3.3: StockDataSkill.format_data() 迁移测试"""

    def test_format_data_financials(self):
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        data = {
            "income_statement": [{"REPORT_DATE": "2024-01-01", "NET_PROFIT": 1.5e9, "BASIC_EPS": 12.5}],
        }
        result = skill.format_data(data, "financials", "SH600519")
        assert "利润表" in result
        assert "15.00亿" in result

    def test_format_data_company_info(self):
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        data = {"股票简称": "贵州茅台", "行业": "白酒", "总股本": "12.56亿"}
        result = skill.format_data(data, "company_info", "SH600519")
        assert "公司信息" in result
        assert "贵州茅台" in result

    def test_format_data_key_metrics(self):
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        data = {"operating_income_total": 500.0, "basic_eps": 12.5}
        result = skill.format_data(data, "key_metrics", "SH600519")
        assert "营业总收入" in result

    def test_format_data_price_history(self):
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        data = {"records": [
            {"日期": "2024-01-01", "收盘": 1800.5, "开盘": 1790.0, "涨跌幅": "0.5%"},
        ]}
        result = skill.format_data(data, "price_history", "SH600519")
        assert "股价数据" in result

    def test_format_data_unknown_action_returns_empty(self):
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        result = skill.format_data({"key": "val"}, "unknown_action", "SH600519")
        assert result == ""

    @pytest.mark.asyncio
    async def test_to_readable_content_uses_format_data(self):
        """验证 _to_readable_content L2 调用 skill.format_data()"""
        agent = _make_agent()
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        data = {"股票简称": "贵州茅台", "行业": "白酒"}
        content = await agent._to_readable_content(
            {"success": True, "content": "", "data": data},
            skill, data, "company_info", "SH600519", "stock_data", "茅台"
        )
        assert "贵州茅台" in content


class TestXueqiuFormatData:
    """Task 3.4: XueqiuSkill.format_data() 测试"""

    def test_format_quote(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        skill = XueqiuSkill()
        data = {"name": "贵州茅台", "current": 1800.5, "percent": 1.5, "market_capital": "22600亿"}
        result = skill.format_data(data, "quote", "SH600519")
        assert "实时行情" in result
        assert "1800.5" in result

    def test_format_kline(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        skill = XueqiuSkill()
        data = [{"time": "2024-01-01", "close": 1800, "high": 1810, "low": 1790}]
        result = skill.format_data(data, "kline", "SH600519")
        assert "K线" in result

    def test_format_hot_stocks(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        skill = XueqiuSkill()
        data = [{"name": "茅台", "percent": 2.5}, {"name": "五粮液", "percent": -1.2}]
        result = skill.format_data(data, "hot_stocks", "")
        assert "热门股票" in result

    def test_format_search_and_quote(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        skill = XueqiuSkill()
        data = {"search": {"name": "贵州茅台"}, "quote": {"current": 1800, "percent": 1.5}}
        result = skill.format_data(data, "search_and_quote", "SH600519")
        assert "搜索+行情" in result

    def test_format_empty_data(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        skill = XueqiuSkill()
        result = skill.format_data({}, "quote", "SH600519")
        assert result == ""

    def test_format_unknown_action(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        skill = XueqiuSkill()
        result = skill.format_data({"key": "val"}, "unknown", "")
        assert result == ""

    def test_format_kline_with_wrapped_dict(self):
        """I3 fix: _format_kline 应处理 {"records": [...]} wrapped dict"""
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        skill = XueqiuSkill()
        data = {"records": [{"time": "2024-01-01", "close": 1800, "high": 1810, "low": 1790}]}
        result = skill.format_data(data, "kline", "SH600519")
        assert "K线" in result
        assert "1800" in result

    def test_format_hot_stocks_with_wrapped_dict(self):
        """I3 fix: _format_hot_stocks 应处理 {"records": [...]} wrapped dict"""
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        skill = XueqiuSkill()
        data = {"records": [{"name": "茅台", "percent": 2.5}]}
        result = skill.format_data(data, "hot_stocks", "")
        assert "热门股票" in result
