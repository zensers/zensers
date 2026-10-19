"""Tests for the current DataBusV2 production contract."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.core.data_providers import (
    DataBusV2,
    DataSourceConfig,
    DataSourcePriority,
    MemoryCacheBackend,
    MultiLevelCache,
)


def _bus() -> DataBusV2:
    return DataBusV2(
        cache=MultiLevelCache(memory_cache=MemoryCacheBackend(max_size=32)),
        enable_health_check=False,
    )


def _source(source_id, provider, priority=DataSourcePriority.PRIMARY, cost=0.0):
    return DataSourceConfig(
        source_id=source_id,
        provider=provider,
        priority=priority,
        data_types=["market"],
        cost_per_request=cost,
    )


@pytest.mark.asyncio
async def test_v2_cache_hit_does_not_call_provider_twice():
    bus = _bus()
    provider = type("Provider", (), {})()
    provider.fetch = AsyncMock(return_value={"value": 42})
    bus.register_source(_source("primary", provider))

    first = await bus.query("market", {"symbol": "ABC"})
    second = await bus.query("market", {"symbol": "ABC"})

    assert first["data"] == {"value": 42}
    assert second["cached"] is True
    assert second["source"] == "primary"
    assert provider.fetch.await_count == 1


@pytest.mark.asyncio
async def test_v2_failover_uses_next_priority_source():
    bus = _bus()
    primary = type("Provider", (), {})()
    primary.fetch = AsyncMock(side_effect=RuntimeError("primary down"))
    backup = type("Provider", (), {})()
    backup.fetch = AsyncMock(return_value={"value": 7})
    bus.register_source(_source("primary", primary, DataSourcePriority.PRIMARY))
    bus.register_source(_source("backup", backup, DataSourcePriority.SECONDARY))

    result = await bus.query("market", {"symbol": "ABC"}, preferred_source="primary")

    assert result["success"] is True
    assert result["source"] == "backup"
    assert result["fallback_used"] is True
    primary.fetch.assert_awaited_once()
    backup.fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_v2_cost_tracking_excludes_cache_hits():
    bus = _bus()
    provider = type("Provider", (), {})()
    provider.fetch = AsyncMock(return_value={"value": 1})
    bus.register_source(_source("paid", provider, cost=0.01))

    await bus.query("market", {"symbol": "ABC"})
    await bus.query("market", {"symbol": "ABC"})

    report = bus.get_cost_report()
    assert report["total_requests"] == 1
    assert report["total_cost_usd"] == 0.01


@pytest.mark.asyncio
async def test_v2_zero_ttl_forces_refresh():
    bus = _bus()
    provider = type("Provider", (), {})()
    provider.fetch = AsyncMock(side_effect=[{"value": 1}, {"value": 2}])
    bus.register_source(_source("primary", provider))

    first = await bus.query("market", {"symbol": "ABC"}, cache_ttl=0)
    await asyncio.sleep(0)
    second = await bus.query("market", {"symbol": "ABC"}, cache_ttl=0)

    assert first["data"] == {"value": 1}
    assert second["data"] == {"value": 2}
    assert provider.fetch.await_count == 2
