"""数据层集成测试 - 验证DataBus V2 + 约束层的端到端集成."""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from src.core.data_providers import (
    DataBusV2,
    DataSourceConfig,
    DataSourcePriority,
    create_databus_with_defaults,
)
from src.core.harness.constraints import SourceWhitelist, FactTracer, QualityGate, QualityCheckResult


class TestDataBusWithConstraints:
    """测试 DataBus 与约束层的集成."""

    @pytest.fixture
    async def databus(self):
        """创建测试用的 DataBus 实例."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = create_databus_with_defaults(cache_dir=tmpdir)
            yield bus
            await bus.clear_all_caches()

    @pytest.fixture
    def whitelist(self):
        """创建测试用的来源白名单."""
        whitelist = SourceWhitelist()
        # 添加可信来源
        whitelist.add_trusted_source("akshare", tier="tier1")
        whitelist.add_trusted_source("tushare", tier="tier1")
        whitelist.add_trusted_source("官方统计局", tier="tier1")
        # 添加不可信来源
        whitelist.add_untrusted_source("未知博客")
        whitelist.add_untrusted_source("未经验证的论坛")
        return whitelist

    def test_whitelist_blocks_untrusted_source(self, whitelist):
        """测试白名单阻止不可信来源."""
        # 不可信来源应该返回False
        result = whitelist.is_trusted("未知博客")
        assert result is False

    def test_whitelist_allows_trusted_source(self, whitelist):
        """测试白名单允许可信来源."""
        # 可信来源应该通过验证
        result = whitelist.is_trusted("akshare")
        assert result is True

    def test_fact_tracer_records_data_origin(self):
        """测试事实追踪器记录数据来源."""
        tracer = FactTracer()
        
        # 记录一个数据点
        tracer.trace_fact(
            fact_id="gdp_2024",
            fact_statement="2024年GDP为126万亿",
            source="国家统计局",
            source_url="https://stats.gov.cn",
            confidence="high",
        )
        
        # 验证记录
        fact = tracer.get_trace("gdp_2024")
        assert fact is not None
        assert fact["fact_statement"] == "2024年GDP为126万亿"
        assert fact["source"] == "国家统计局"

    def test_quality_gate_blocks_low_confidence(self):
        """测试质量闸门阻止低置信度内容."""
        gate = QualityGate(
            min_confidence=0.7,
            require_sources=True,
        )
        
        # 低置信度内容应该被阻止
        low_confidence_data = {
            "content": "某个未经证实的消息",
            "confidence": 0.3,
            "sources": [],
        }
        
        result = gate.check(low_confidence_data)
        assert result.passed is False
        assert any("置信度" in error for error in result.errors)

    def test_quality_gate_allows_high_confidence(self):
        """测试质量闸门允许高置信度内容."""
        gate = QualityGate(
            min_confidence=0.7,
            require_sources=True,
        )
        
        # 高置信度内容应该通过
        high_confidence_data = {
            "content": "官方发布的数据",
            "confidence": 0.95,
            "sources": [{"name": "国家统计局", "url": "https://stats.gov.cn"}],
        }
        
        result = gate.check(high_confidence_data)
        assert result.passed is True
        assert len(result.errors) == 0


class TestDataBusCacheIntegration:
    """测试 DataBus 缓存集成."""

    @pytest.fixture
    async def databus_with_cache(self):
        """创建带缓存的 DataBus 实例."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = create_databus_with_defaults(cache_dir=tmpdir)
            
            # 添加一个模拟数据源
            mock_provider = Mock()
            mock_provider.fetch = AsyncMock(return_value={
                "symbol": "000001",
                "price": 10.5,
                "timestamp": datetime.now().isoformat(),
            })
            
            bus.register_provider("mock_stock", mock_provider)
            yield bus
            await bus.clear_all_caches()

    @pytest.mark.asyncio
    async def test_cache_hit_returns_fast(self, databus_with_cache):
        """测试缓存命中时快速返回."""
        bus = databus_with_cache
        
        # 第一次查询（缓存未命中）
        start = datetime.now()
        result1 = await bus.query("mock_stock", {"symbol": "000001"})
        duration1 = (datetime.now() - start).total_seconds()
        
        # 第二次查询（缓存命中）
        start = datetime.now()
        result2 = await bus.query("mock_stock", {"symbol": "000001"})
        duration2 = (datetime.now() - start).total_seconds()
        
        # 缓存命中应该快得多
        assert duration2 < duration1
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_cache_ttl_expires(self, databus_with_cache):
        """测试缓存过期后重新获取."""
        bus = databus_with_cache
        
        # 设置极短的TTL
        bus.l1_cache.default_ttl = 0.001  # 1毫秒
        
        # 第一次查询
        result1 = await bus.query("mock_stock", {"symbol": "000001"})
        
        # 等待缓存过期
        await asyncio.sleep(0.1)
        
        # 第二次查询（应该重新获取）
        result2 = await bus.query("mock_stock", {"symbol": "000001"})
        
        # 数据应该相同（虽然重新获取了）
        assert result1["symbol"] == result2["symbol"]


class TestDataBusFailover:
    """测试 DataBus 自动降级功能."""

    @pytest.mark.asyncio
    async def test_auto_failover_to_backup(self):
        """测试主数据源失败时自动切换到备用源."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = create_databus_with_defaults(cache_dir=tmpdir)
            
            # 创建主数据源（会失败）
            primary = Mock()
            primary.fetch = AsyncMock(side_effect=Exception("Primary failed"))
            
            # 创建备用数据源（正常工作）
            backup = Mock()
            backup.fetch = AsyncMock(return_value={
                "symbol": "000001",
                "price": 10.5,
                "source": "backup",
            })
            
            # 注册数据源（主+备）
            bus.register_provider("stock_data", primary)
            bus.register_provider("stock_data_backup", backup)
            
            # 配置数据源优先级
            bus.source_configs["stock_data"] = DataSourceConfig(
                name="stock_data",
                priority=DataSourcePriority.PRIMARY,
                failover_to="stock_data_backup",
            )
            
            # 查询数据（应该自动降级到备用源）
            result = await bus.query("stock_data", {"symbol": "000001"})
            
            assert result["source"] == "backup"
            assert primary.fetch.called
            assert backup.fetch.called


class TestDataBusCostTracking:
    """测试 DataBus 成本追踪功能."""

    @pytest.mark.asyncio
    async def test_cost_tracking_accumulates(self):
        """测试成本累计功能."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bus = create_databus_with_defaults(cache_dir=tmpdir)
            
            # 添加带成本的数据源
            mock_provider = Mock()
            mock_provider.fetch = AsyncMock(return_value={"data": "test"})
            mock_provider.cost_per_request = 0.01  # 每次1分钱
            
            bus.register_provider("paid_api", mock_provider)
            
            # 多次查询
            for _ in range(10):
                await bus.query("paid_api", {"param": "value"})
            
            # 验证成本累计
            stats = bus.get_cost_stats()
            assert stats["total_cost"] == 0.1  # 10 * 0.01
            assert stats["request_count"] == 10


class TestEndToEndDataFlow:
    """端到端数据流测试."""

    @pytest.mark.asyncio
    async def test_complete_data_pipeline(self):
        """测试完整的数据处理流程."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. 创建 DataBus
            bus = create_databus_with_defaults(cache_dir=tmpdir)
            
            # 2. 创建约束层组件
            whitelist = SourceWhitelist(
                trusted_sources={"akshare", "官方统计局"},
            )
            tracer = FactTracer()
            gate = QualityGate(min_confidence=0.7)
            
            # 3. 添加模拟数据源
            mock_provider = Mock()
            mock_provider.fetch = AsyncMock(return_value={
                "indicator": "gdp_growth",
                "value": 5.2,
                "unit": "%",
                "source": "akshare",
                "timestamp": datetime.now().isoformat(),
            })
            bus.register_provider("macro_data", mock_provider)
            
            # 4. 执行完整流程
            # 4.1 验证数据来源
            assert whitelist.is_trusted("akshare") is True
            
            # 4.2 获取数据
            data = await bus.query("macro_data", {"indicator": "gdp"})
            
            # 4.3 记录溯源
            tracer.trace_fact(
                fact_id="gdp_growth_2024",
                fact_statement=f"GDP增长{data['value']}%",
                source=data["source"],
                confidence="high",
            )
            
            # 4.4 质量检查
            check_result = gate.check({
                "content": f"GDP增长{data['value']}%",
                "confidence": 0.85,
                "sources": [{"name": "akshare"}],
            })
            
            # 5. 验证结果
            assert data["value"] == 5.2
            assert check_result.passed is True
            assert tracer.get_trace("gdp_growth_2024") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
