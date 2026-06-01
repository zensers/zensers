"""
DataBus 测试 - TDD模式
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestDataBus:
    """测试数据总线"""

    @pytest.fixture
    def databus(self):
        from src.core.data_providers.bus import DataBus
        return DataBus()

    def test_databus_initialization(self, databus):
        """测试 DataBus 初始化"""
        assert databus is not None
        assert databus.get_stats()["total_requests"] == 0

    @pytest.mark.asyncio
    async def test_register_and_query_provider(self, databus):
        """测试注册和查询 Provider"""
        mock_provider = AsyncMock()
        mock_provider.fetch.return_value = {"data": "市场数据", "source": "test"}
        mock_provider.source_id = "test_source"

        databus.register_provider("test_source", mock_provider)

        result = await databus.query(
            source="test_source",
            params={"keyword": "新能源汽车"}
        )

        assert result["success"] is True
        assert result["data"]["data"] == "市场数据"

    @pytest.mark.asyncio
    async def test_cache_hit(self, databus):
        """测试缓存命中"""
        mock_provider = AsyncMock()
        mock_provider.fetch.return_value = {"data": "缓存数据"}
        mock_provider.source_id = "cached_source"
        databus.register_provider("cached_source", mock_provider)

        # 第一次查询
        await databus.query(source="cached_source", params={"key": "val"})
        # 第二次查询（应命中缓存）
        result = await databus.query(source="cached_source", params={"key": "val"})

        assert result["success"] is True
        assert result.get("cached") is True
        # provider.fetch 只调用一次
        assert mock_provider.fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_miss_and_fetch(self, databus):
        """测试缓存未命中时重新获取"""
        mock_provider = AsyncMock()
        mock_provider.fetch.return_value = {"data": "新数据"}
        mock_provider.source_id = "fresh_source"
        databus.register_provider("fresh_source", mock_provider)

        # 两次不同参数的查询
        await databus.query(source="fresh_source", params={"page": 1})
        await databus.query(source="fresh_source", params={"page": 2})

        # 每次查询都应调用 fetch
        assert mock_provider.fetch.call_count == 2

    @pytest.mark.asyncio
    async def test_routing_strategy(self, databus):
        """测试路由策略 - 多 Provider 选择"""
        provider_a = AsyncMock()
        provider_a.fetch.return_value = {"data": "来源A", "priority": 1}
        provider_a.source_id = "source_a"

        provider_b = AsyncMock()
        provider_b.fetch.return_value = {"data": "来源B", "priority": 2}
        provider_b.source_id = "source_b"

        databus.register_provider("source_a", provider_a)
        databus.register_provider("source_b", provider_b)

        # 指定 source 的查询
        result = await databus.query(source="source_b", params={})
        assert result["data"]["data"] == "来源B"

    @pytest.mark.asyncio
    async def test_fallback_mechanism(self, databus):
        """测试 Provider 失败时回退"""
        primary = AsyncMock()
        primary.fetch.side_effect = Exception("主 Provider 不可用")
        primary.source_id = "primary"

        fallback = AsyncMock()
        fallback.fetch.return_value = {"data": "回退数据"}
        fallback.source_id = "fallback"

        databus.register_provider("primary", primary)
        databus.register_provider("fallback", fallback)

        result = await databus.query(
            source="primary",
            params={},
            fallback_source="fallback"
        )

        assert result["success"] is True
        assert result["data"]["data"] == "回退数据"
        assert result.get("fallback_used") is True

    @pytest.mark.asyncio
    async def test_unknown_source_error(self, databus):
        """测试查询未注册 source"""
        result = await databus.query(source="nonexistent", params={})
        assert result["success"] is False

    def test_get_stats(self, databus):
        """测试统计信息"""
        stats = databus.get_stats()
        assert "total_requests" in stats
        assert "cache_hits" in stats
        assert "cache_misses" in stats

    @pytest.mark.asyncio
    async def test_stats_update_after_query(self, databus):
        """测试查询后统计更新"""
        mock_provider = AsyncMock()
        mock_provider.fetch.return_value = {"data": "x"}
        mock_provider.source_id = "stats_source"
        databus.register_provider("stats_source", mock_provider)

        await databus.query(source="stats_source", params={})
        await databus.query(source="stats_source", params={})  # 缓存命中

        stats = databus.get_stats()
        assert stats["total_requests"] == 2
        assert stats["cache_hits"] >= 1
