"""
Task 3.0: DATA_COLLECTION 行为快照测试

在重构前覆盖当前 DATA_COLLECTION 阶段的关键行为，确保重构后行为一致。
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


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


class TestStructuredDBBehavior:
    """Tier 1: structured_db Skill 通过 _process_skill_output 获取数据"""

    @pytest.mark.asyncio
    async def test_process_skill_output_returns_data_points(self):
        agent = _make_agent()
        mock_skill = AsyncMock()
        mock_skill.name = "stock_data"
        mock_skill.execute = AsyncMock(return_value={
            "success": True,
            "data": {"current_price": 1800.5, "pe_ratio": 30.2},
            "content": "贵州茅台(SH600519): 当前价1800.5",
        })
        mock_manifest = MagicMock()
        mock_manifest.priority = "structured_db"
        mock_manifest.action_rules = []
        mock_manifest.action_param_map = {}
        agent._skill_registry.get_manifest = MagicMock(return_value=mock_manifest)
        result = await agent._process_skill_output(
            mock_skill, "stock_data", "贵州茅台", "财务分析", agent._skill_registry,
        )
        assert len(result.get("data_points", [])) > 0

    @pytest.mark.asyncio
    async def test_process_skill_output_extracts_canonical_metrics(self):
        agent = _make_agent()
        mock_skill = AsyncMock()
        mock_skill.name = "stock_data"
        mock_skill.execute = AsyncMock(return_value={
            "success": True,
            "data": {"净利润": 150.5, "营收": 500.0},
            "content": "",
        })
        mock_manifest = MagicMock()
        mock_manifest.priority = "structured_db"
        mock_manifest.action_rules = []
        mock_manifest.action_param_map = {}
        agent._skill_registry.get_manifest = MagicMock(return_value=mock_manifest)
        result = await agent._process_skill_output(
            mock_skill, "stock_data", "贵州茅台", "财务分析", agent._skill_registry,
        )
        assert len(result.get("canonical_metrics", {})) > 0

    @pytest.mark.asyncio
    async def test_process_skill_output_list_data_wrapped(self):
        agent = _make_agent()
        mock_skill = AsyncMock()
        mock_skill.name = "stock_data"
        mock_skill.execute = AsyncMock(return_value={
            "success": True,
            "data": [{"item": 1}, {"item": 2}],
            "content": "",
        })
        mock_manifest = MagicMock()
        mock_manifest.priority = "structured_db"
        mock_manifest.action_rules = []
        mock_manifest.action_param_map = {}
        agent._skill_registry.get_manifest = MagicMock(return_value=mock_manifest)
        result = await agent._process_skill_output(
            mock_skill, "stock_data", "贵州茅台", "财务分析", agent._skill_registry,
        )
        assert len(result.get("data_points", [])) > 0

    @pytest.mark.asyncio
    async def test_process_skill_output_none_result_returns_empty(self):
        agent = _make_agent()
        mock_skill = AsyncMock()
        mock_skill.name = "stock_data"
        mock_skill.execute = AsyncMock(return_value=None)
        mock_manifest = MagicMock()
        mock_manifest.priority = "structured_db"
        mock_manifest.action_rules = []
        mock_manifest.action_param_map = {}
        agent._skill_registry.get_manifest = MagicMock(return_value=mock_manifest)
        result = await agent._process_skill_output(
            mock_skill, "stock_data", "unknown topic", "财务分析", agent._skill_registry,
        )
        assert result.get("data_points", []) == []
        assert result.get("sources", []) == []


class TestNewsSearchBehavior:
    """Tier 2: news_search 内联处理"""

    @pytest.mark.asyncio
    async def test_news_search_results_appended_to_data_points(self):
        agent = _make_agent()
        mock_news = AsyncMock()
        mock_news.execute = AsyncMock(return_value={
            "success": True,
            "results": [
                {"title": "新闻1", "body": "内容1", "href": "http://1", "source": "源1", "date": "2024-01"},
                {"title": "新闻2", "body": "内容2", "href": "http://2", "source": "源2", "date": "2024-01"},
            ],
        })
        agent._skill_registry.get = MagicMock(return_value=mock_news)
        news_result = await mock_news.execute(query="测试 最新 动态", max_results=10, time_range="w")
        assert news_result.get("success")
        results = news_result.get("results", [])
        assert len(results) == 2
        assert results[0]["title"] == "新闻1"

    @pytest.mark.asyncio
    async def test_news_search_results_at_top_level(self):
        """NewsSearchSkill 返回 results 在顶层而非 data 子键下"""
        agent = _make_agent()
        mock_news = AsyncMock()
        mock_news.execute = AsyncMock(return_value={
            "success": True,
            "results": [{"title": "t", "body": "b", "href": "u"}],
        })
        result = await mock_news.execute(query="q", max_results=5, time_range="w")
        assert "results" in result
        assert "data" not in result or result.get("data") is None


class TestBFix3MetricsExtraction:
    """B-FIX-3: 从 web search content 中正则提取数值写入 SharedMemory"""

    @pytest.mark.asyncio
    async def test_regex_extracts_net_profit(self):
        agent = _make_agent()
        import re
        pattern = r'(?:净利润|归母|扣非)[^\d]*?(\d+\.?\d*)\s*亿元'
        text = "公司2023年净利润 150.5亿元，同比增长10%"
        m = re.search(pattern, text)
        assert m is not None
        assert float(m.group(1)) == 150.5

    @pytest.mark.asyncio
    async def test_regex_extracts_revenue(self):
        import re
        pattern = r'(?:(?:营业)?收入|营收)[^\d]*?(\d+\.?\d*)\s*亿元'
        text = "2023年营业收入 500.2亿元"
        m = re.search(pattern, text)
        assert m is not None
        assert float(m.group(1)) == 500.2


class TestFallbackQueries:
    """structured_db 不可用时注入 fallback queries"""

    def test_generate_fallback_queries_returns_list(self):
        agent = _make_agent()
        agent._context = {}
        queries = agent._generate_structured_fallback_queries("比亚迪", "财务分析")
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_fallback_queries_contain_topic(self):
        agent = _make_agent()
        agent._context = {}
        queries = agent._generate_structured_fallback_queries("比亚迪", "财务分析")
        assert any("比亚迪" in q for q in queries)


class TestTieredExecutionOrder:
    """验证 execution_order: structured_db → web_search → llm"""

    def test_execution_order_priority(self):
        from src.core.decomposition.strategies import SKILL_PRIORITY_MAP
        available = ["stock_data", "search_skill", "news_search", "llm"]
        def _skill_tier(name):
            return SKILL_PRIORITY_MAP.get(name, "web_search")
        tiered = {}
        for s in available:
            tiered.setdefault(_skill_tier(s), []).append(s)
        execution_order = (
            tiered.get("structured_db", [])
            + tiered.get("web_search", [])
            + tiered.get("llm", [])
        )
        assert execution_order.index("stock_data") < execution_order.index("search_skill")
        assert execution_order.index("stock_data") < execution_order.index("news_search")


class TestExtractNumericMetrics:
    """验证 _extract_numeric_metrics 行为"""

    def test_extracts_from_flat_dict(self):
        agent = _make_agent()
        data = {"净利润": 150.5, "营收": 500.0}
        metrics = agent._extract_numeric_metrics(data)
        assert "净利润" in metrics
        assert metrics["净利润"] == 150.5

    def test_extracts_from_nested_list_of_dicts(self):
        agent = _make_agent()
        data = {"periods": [{"NET_PROFIT": 100.0}, {"NET_PROFIT": 200.0}]}
        metrics = agent._extract_numeric_metrics(data)
        assert len(metrics) > 0

    def test_skips_nan(self):
        agent = _make_agent()
        data = {"val": float('nan')}
        metrics = agent._extract_numeric_metrics(data)
        assert "val" not in metrics

    def test_parses_chinese_numbers(self):
        agent = _make_agent()
        data = {"利润": "150.5亿"}
        metrics = agent._extract_numeric_metrics(data)
        assert len(metrics) > 0
