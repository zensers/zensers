"""
XueqiuSkill TDD 测试 — Phase 1: 核心 Skill 行为

测试覆盖：
1. name / description 属性
2. execute 路由到各 action
3. quote action（实时行情）
4. search action（股票搜索）
5. hot_posts action（热门帖子）
6. hot_stocks action（热门股票）
7. kline action（K 线数据）
8. search_and_quote 复合 action
9. 不支持的 action 返回 failure
10. 缺少必要参数时返回 failure
11. API 失败时优雅降级
12. 缓存命中
13. 异步包装（to_thread）
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock, PropertyMock


@pytest.fixture(autouse=True)
def _clear_cache():
    from src.skills.analysis.xueqiu_skill import XueqiuSkill
    XueqiuSkill._memory_cache.clear()
    yield
    XueqiuSkill._memory_cache.clear()


class TestXueqiuSkillProperties:
    """测试 Skill 基本属性"""

    @pytest.fixture
    def skill(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        return XueqiuSkill()

    def test_name_is_xueqiu(self, skill):
        assert skill.name == "xueqiu"

    def test_description_is_not_empty(self, skill):
        assert skill.description is not None
        assert len(skill.description) > 0

    def test_description_contains_keywords(self, skill):
        desc = skill.description
        assert "行情" in desc or "quote" in desc.lower() or "雪球" in desc


class TestXueqiuSkillQuote:
    """测试 quote action"""

    @pytest.fixture
    def skill(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        s = XueqiuSkill()
        s._api = MagicMock()
        return s

    @pytest.mark.asyncio
    async def test_quote_returns_stock_data(self, skill):
        skill._api.get_stock_quote.return_value = {
            "symbol": "SH600519",
            "name": "贵州茅台",
            "current": 1800.0,
            "percent": 2.5,
            "chg": 43.5,
            "high": 1820.0,
            "low": 1770.0,
            "open": 1780.0,
            "last_close": 1756.5,
            "volume": 12345,
            "amount": 2200000000,
            "market_capital": 2260000000000,
            "turnover_rate": 0.55,
            "pe_ttm": 35.2,
            "timestamp": 1700000000000,
        }
        result = await skill.execute(action="quote", symbol="SH600519")
        assert result["success"] is True
        assert result["data"]["symbol"] == "SH600519"
        assert result["data"]["current"] == 1800.0

    @pytest.mark.asyncio
    async def test_quote_missing_symbol_returns_failure(self, skill):
        result = await skill.execute(action="quote")
        assert result["success"] is False
        assert "symbol" in result.get("error", "").lower() or "代码" in result.get("error", "")


class TestXueqiuSkillSearch:
    """测试 search action"""

    @pytest.fixture
    def skill(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        s = XueqiuSkill()
        s._api = MagicMock()
        return s

    @pytest.mark.asyncio
    async def test_search_returns_stock_list(self, skill):
        skill._api.search_stock.return_value = [
            {"symbol": "SH600519", "name": "贵州茅台", "exchange": "SH"},
            {"symbol": "SZ000858", "name": "五粮液", "exchange": "SZ"},
        ]
        result = await skill.execute(action="search", query="茅台")
        assert result["success"] is True
        assert len(result["data"]) == 2
        assert result["data"][0]["symbol"] == "SH600519"

    @pytest.mark.asyncio
    async def test_search_missing_query_returns_failure(self, skill):
        result = await skill.execute(action="search")
        assert result["success"] is False


class TestXueqiuSkillHotPosts:
    """测试 hot_posts action"""

    @pytest.fixture
    def skill(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        s = XueqiuSkill()
        s._api = MagicMock()
        return s

    @pytest.mark.asyncio
    async def test_hot_posts_returns_list(self, skill):
        skill._api.get_hot_posts.return_value = [
            {"id": 1, "title": "市场分析", "text": "今日A股...", "author": "老司机", "likes": 100, "url": "https://xueqiu.com/1"},
        ]
        result = await skill.execute(action="hot_posts", limit=10)
        assert result["success"] is True
        assert len(result["data"]) >= 1


class TestXueqiuSkillHotStocks:
    """测试 hot_stocks action"""

    @pytest.fixture
    def skill(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        s = XueqiuSkill()
        s._api = MagicMock()
        return s

    @pytest.mark.asyncio
    async def test_hot_stocks_returns_ranked_list(self, skill):
        skill._api.get_hot_stocks.return_value = [
            {"symbol": "SH600519", "name": "贵州茅台", "current": 1800.0, "percent": 2.5, "rank": 1},
        ]
        result = await skill.execute(action="hot_stocks", limit=10)
        assert result["success"] is True
        assert result["data"][0]["rank"] == 1


class TestXueqiuSkillKline:
    """测试 kline action"""

    @pytest.fixture
    def skill(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        s = XueqiuSkill()
        s._api = MagicMock()
        return s

    @pytest.mark.asyncio
    async def test_kline_returns_ohlc_data(self, skill):
        skill._api.get_stock_kline.return_value = [
            {"timestamp": 1700000000000, "open": 1780, "high": 1820, "low": 1770, "close": 1800, "volume": 12345},
        ]
        result = await skill.execute(action="kline", symbol="SH600519", period="day", count=30)
        assert result["success"] is True
        assert result["data"][0]["open"] == 1780

    @pytest.mark.asyncio
    async def test_kline_missing_symbol_returns_failure(self, skill):
        result = await skill.execute(action="kline")
        assert result["success"] is False


class TestXueqiuSkillSearchAndQuote:
    """测试 search_and_quote 复合 action"""

    @pytest.fixture
    def skill(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        s = XueqiuSkill()
        s._api = MagicMock()
        return s

    @pytest.mark.asyncio
    async def test_search_and_quote_for_chinese_name(self, skill):
        skill._api.search_stock.return_value = [
            {"symbol": "00700", "name": "腾讯控股", "exchange": "HK"},
        ]
        skill._api.get_stock_quote.return_value = {
            "symbol": "00700",
            "name": "腾讯控股",
            "current": 380.0,
            "percent": 1.5,
            "chg": 5.6,
            "high": 385.0,
            "low": 375.0,
            "open": 376.0,
            "last_close": 374.4,
            "volume": 50000,
            "amount": 19000000000,
            "market_capital": 3600000000000,
            "turnover_rate": 0.3,
            "pe_ttm": 25.0,
            "timestamp": 1700000000000,
        }
        result = await skill.execute(action="search_and_quote", query="腾讯控股")
        assert result["success"] is True
        assert result["data"]["search"]["symbol"] == "00700"
        assert result["data"]["quote"]["current"] == 380.0

    @pytest.mark.asyncio
    async def test_search_and_quote_no_results_returns_failure(self, skill):
        skill._api.search_stock.return_value = []
        result = await skill.execute(action="search_and_quote", query="不存在公司")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_search_and_quote_missing_query_returns_failure(self, skill):
        result = await skill.execute(action="search_and_quote")
        assert result["success"] is False


class TestXueqiuSkillUnsupportedAction:
    """测试不支持的 action"""

    @pytest.fixture
    def skill(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        s = XueqiuSkill()
        s._api = MagicMock()
        return s

    @pytest.mark.asyncio
    async def test_unsupported_action_returns_failure(self, skill):
        result = await skill.execute(action="nonexistent_action", symbol="SH600519")
        assert result["success"] is False
        assert "unsupported" in result.get("error", "").lower() or "不支持" in result.get("error", "")


class TestXueqiuSkillCache:
    """测试缓存机制"""

    @pytest.fixture
    def skill(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        s = XueqiuSkill()
        s._api = MagicMock()
        s._memory_cache.clear()
        return s

    @pytest.mark.asyncio
    async def test_cache_hit_avoids_api_call(self, skill):
        skill._api.get_stock_quote.return_value = {
            "symbol": "SH600519", "name": "贵州茅台", "current": 1800.0,
            "percent": 2.5, "chg": 43.5, "high": 1820.0, "low": 1770.0,
            "open": 1780.0, "last_close": 1756.5, "volume": 12345,
            "amount": 2200000000, "market_capital": 2260000000000,
            "turnover_rate": 0.55, "pe_ttm": 35.2, "timestamp": 1700000000000,
        }
        result1 = await skill.execute(action="quote", symbol="SH600519")
        assert result1["success"] is True
        assert skill._api.get_stock_quote.call_count == 1

        skill._api.get_stock_quote.return_value = {"should": "not be used"}
        result2 = await skill.execute(action="quote", symbol="SH600519")
        assert result2["success"] is True
        assert result2["data"]["current"] == 1800.0
        assert skill._api.get_stock_quote.call_count == 1  # no second call


class TestXueqiuSkillApiFailure:
    """测试 API 失败时的优雅降级"""

    @pytest.fixture
    def skill(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        s = XueqiuSkill()
        s._api = MagicMock()
        return s

    @pytest.mark.asyncio
    async def test_quote_api_exception_returns_failure(self, skill):
        async def _fail(*args, **kwargs):
            raise RuntimeError("Network error")
        skill._rate_limited_call = _fail
        result = await skill.execute(action="quote", symbol="SH600519")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_search_api_exception_returns_failure(self, skill):
        skill._api.search_stock.side_effect = Exception("Timeout")
        result = await skill.execute(action="search", query="茅台")
        assert result["success"] is False


class TestXueqiuSkillAsyncWrapper:
    """测试同步 API 被异步包装"""

    @pytest.fixture
    def skill(self):
        from src.skills.analysis.xueqiu_skill import XueqiuSkill
        s = XueqiuSkill()
        s._api = MagicMock()
        return s

    @pytest.mark.asyncio
    async def test_execute_is_coroutine(self, skill):
        skill._api.get_stock_quote.return_value = {
            "symbol": "SH600519", "name": "贵州茅台", "current": 1800.0,
            "percent": 2.5, "chg": 43.5, "high": 1820.0, "low": 1770.0,
            "open": 1780.0, "last_close": 1756.5, "volume": 12345,
            "amount": 2200000000, "market_capital": 2260000000000,
            "turnover_rate": 0.55, "pe_ttm": 35.2, "timestamp": 1700000000000,
        }
        result = await skill.execute(action="quote", symbol="SH600519")
        assert asyncio.iscoroutinefunction(skill.execute)
        assert result["success"] is True
