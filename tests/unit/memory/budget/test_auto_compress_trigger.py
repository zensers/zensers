"""
Token 预算自动压缩触发测试 - TDD模式

测试 TokenBudgetManager 的自动压缩触发功能
参考: CONTEXT_COMPRESSION.md 第4节 Token 预算管理

测试覆盖：
- 自动压缩触发条件
- 压缩优先级
- 压缩效果验证
- 压缩回调
"""

import pytest
from typing import Dict, Any, Optional
from unittest.mock import Mock, AsyncMock


class TestAutoCompressTrigger:
    """测试自动压缩触发"""

    @pytest.fixture
    def budget_manager(self):
        """创建 TokenBudgetManager 实例"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        return TokenBudgetManager()

    # ========== 触发条件测试 ==========

    def test_should_not_trigger_when_ok(self, budget_manager):
        """测试正常状态不触发压缩"""
        budget_manager.set_layer_usage("layer0", 50000)  # 25%
        
        should_compress = budget_manager.should_auto_compress()
        
        assert should_compress is False

    def test_should_trigger_at_critical(self, budget_manager):
        """测试紧急状态触发压缩"""
        budget_manager.set_layer_usage("layer0", 195000)  # 97.5%
        
        should_compress = budget_manager.should_auto_compress()
        
        assert should_compress is True

    def test_should_not_trigger_at_warning(self, budget_manager):
        """测试警告状态不强制触发"""
        budget_manager.set_layer_usage("layer0", 175000)  # 87.5%
        
        should_compress = budget_manager.should_auto_compress()
        
        # 警告状态建议压缩，但不强制
        assert should_compress is False

    def test_trigger_threshold_configurable(self):
        """测试触发阈值可配置"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        
        manager = TokenBudgetManager(auto_compress_threshold=0.8)
        
        manager.set_layer_usage("layer0", 170000)  # 85%
        
        assert manager.should_auto_compress() is True

    # ========== 压缩优先级测试 ==========

    def test_get_compression_priority(self, budget_manager):
        """测试获取压缩优先级"""
        budget_manager.set_layer_usage("conversation", 100000)
        budget_manager.set_layer_usage("layer2", 50000)
        
        priority = budget_manager.get_compression_priority()
        
        # conversation 和 layer2 通常是压缩优先级最高的
        assert "conversation" in priority or "layer2" in priority

    def test_prioritize_by_layer_size(self, budget_manager):
        """测试按层大小优先压缩"""
        budget_manager.set_layer_usage("layer2", 80000)
        budget_manager.set_layer_usage("conversation", 20000)
        
        priority = budget_manager.get_compression_priority()
        
        # layer2 更大，应该优先压缩
        assert priority == "layer2"

    def test_prioritize_by_layer_type(self, budget_manager):
        """测试按层类型优先压缩"""
        # 对话历史通常是第一优先级
        budget_manager.set_layer_usage("layer2", 40000)
        budget_manager.set_layer_usage("conversation", 40000)
        
        priority = budget_manager.get_compression_priority()
        
        # 对话历史可压缩性更高
        assert priority in ["conversation", "layer2"]

    # ========== 压缩执行测试 ==========

    @pytest.mark.asyncio
    async def test_execute_auto_compress(self, budget_manager):
        """测试执行自动压缩"""
        budget_manager.set_layer_usage("conversation", 100000)
        
        # 设置压缩策略
        mock_strategy = Mock()
        mock_strategy.compress = AsyncMock(return_value=50000)  # 压缩到一半
        budget_manager.set_compression_strategy("conversation", mock_strategy)
        
        result = await budget_manager.execute_auto_compress()
        
        assert result["compressed"] is True
        assert result["layer"] == "conversation"
        assert result["before"] > result["after"]

    @pytest.mark.asyncio
    async def test_compress_reduces_usage(self, budget_manager):
        """测试压缩减少使用量"""
        budget_manager.set_layer_usage("conversation", 100000)
        
        mock_strategy = Mock()
        mock_strategy.compress = AsyncMock(return_value=40000)
        budget_manager.set_compression_strategy("conversation", mock_strategy)
        
        await budget_manager.execute_auto_compress()
        
        # 验证使用量已更新
        assert budget_manager.get_layer_usage("conversation") == 40000

    @pytest.mark.asyncio
    async def test_compress_multiple_layers(self, budget_manager):
        """测试压缩多层"""
        budget_manager.set_layer_usage("conversation", 80000)
        budget_manager.set_layer_usage("layer2", 80000)
        
        # 两个层都需要压缩
        mock_strategy = Mock()
        mock_strategy.compress = AsyncMock(return_value=40000)
        budget_manager.set_compression_strategy("conversation", mock_strategy)
        budget_manager.set_compression_strategy("layer2", mock_strategy)
        
        result = await budget_manager.compress_all_critical()
        
        assert result["layers_compressed"] >= 1

    # ========== 压缩效果验证 ==========

    def test_validate_compression_effect(self, budget_manager):
        """测试验证压缩效果"""
        before = 150000
        after = 80000
        
        is_valid = budget_manager.validate_compression_result(before, after)
        
        assert is_valid is True

    def test_validate_compression_minimum_reduction(self, budget_manager):
        """测试压缩最小减少量"""
        before = 100000
        after = 95000  # 只减少了5%
        
        # 压缩效果太小可能无效
        is_valid = budget_manager.validate_compression_result(before, after, min_reduction=0.1)
        
        assert is_valid is False

    def test_compression_metrics(self, budget_manager):
        """测试压缩指标"""
        budget_manager.record_compression(
            layer="conversation",
            before=100000,
            after=40000,
            duration_ms=150
        )
        
        metrics = budget_manager.get_compression_metrics()
        
        assert metrics["total_compressions"] >= 1
        assert metrics["total_tokens_saved"] == 60000

    # ========== 压缩回调测试 ==========

    def test_compression_callback(self, budget_manager):
        """测试压缩回调"""
        callback_called = []
        
        def on_compress(result):
            callback_called.append(result)
        
        budget_manager.register_compression_callback(on_compress)
        
        budget_manager.notify_compression({
            "layer": "conversation",
            "before": 100000,
            "after": 50000
        })
        
        assert len(callback_called) == 1

    # ========== 压缩策略测试 ==========

    def test_register_compression_strategy(self, budget_manager):
        """测试注册压缩策略"""
        mock_strategy = Mock()
        
        budget_manager.set_compression_strategy("layer2", mock_strategy)
        
        assert budget_manager.get_compression_strategy("layer2") == mock_strategy

    def test_default_compression_strategy(self, budget_manager):
        """测试默认压缩策略"""
        strategy = budget_manager.get_compression_strategy("conversation")
        
        # 应该有默认策略
        assert strategy is not None


class TestAutoCompressIntegration:
    """测试自动压缩集成"""

    @pytest.fixture
    def budget_manager(self):
        """创建 TokenBudgetManager 实例"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        return TokenBudgetManager()

    @pytest.mark.asyncio
    async def test_full_compress_cycle(self, budget_manager):
        """测试完整压缩周期"""
        # 模拟高使用量
        budget_manager.set_layer_usage("conversation", 120000)
        budget_manager.set_layer_usage("layer2", 60000)
        
        # 设置策略
        mock_strategy = Mock()
        mock_strategy.compress = AsyncMock(side_effect=lambda x: x // 2)
        budget_manager.set_compression_strategy("conversation", mock_strategy)
        budget_manager.set_compression_strategy("layer2", mock_strategy)
        
        # 执行自动压缩
        result = await budget_manager.auto_compress_if_needed()
        
        assert result["compressed"] is True
        assert budget_manager.get_total_usage() < 180000

    @pytest.mark.asyncio
    async def test_compress_until_safe(self, budget_manager):
        """测试压缩直到安全"""
        budget_manager.set_layer_usage("conversation", 180000)
        
        mock_strategy = Mock()
        call_count = [0]
        
        async def compress(x):
            call_count[0] += 1
            return max(x // 2, 20000)  # 每次减半，最小20k
        
        mock_strategy.compress = compress
        budget_manager.set_compression_strategy("conversation", mock_strategy)
        
        await budget_manager.compress_until_safe()
        
        # 应该多次压缩直到安全
        assert budget_manager.get_usage_percentage() < 0.85

    @pytest.mark.asyncio
    async def test_compress_preserves_critical_data(self, budget_manager):
        """测试压缩保留关键数据"""
        budget_manager.set_layer_usage("layer1", 8000)  # 核心记忆
        budget_manager.set_layer_usage("conversation", 100000)
        
        mock_strategy = Mock()
        mock_strategy.compress = AsyncMock(return_value=50000)
        budget_manager.set_compression_strategy("conversation", mock_strategy)
        
        await budget_manager.execute_auto_compress()
        
        # 核心记忆不应该被压缩
        assert budget_manager.get_layer_usage("layer1") == 8000