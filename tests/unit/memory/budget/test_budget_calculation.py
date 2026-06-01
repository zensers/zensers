"""
Token 预算计算测试 - TDD模式

测试 TokenBudgetManager 的预算计算功能
参考: CONTEXT_COMPRESSION.md 第4节 Token 预算管理

测试覆盖：
- 预算初始化
- 各层预算计算
- 总预算计算
- 预算百分比计算
"""

import pytest
from typing import Dict, Any


class TestTokenBudgetCalculation:
    """测试 Token 预算计算"""

    @pytest.fixture
    def budget_manager(self):
        """创建 TokenBudgetManager 实例"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        return TokenBudgetManager()

    # ========== 初始化测试 ==========

    def test_budget_manager_init(self, budget_manager):
        """测试预算管理器初始化"""
        # 验证默认预算限制
        assert budget_manager.TOTAL_BUDGET == 200_000
        assert budget_manager.WARNING_YELLOW == 150_000  # 75%
        assert budget_manager.WARNING_ORANGE == 170_000  # 85%
        assert budget_manager.WARNING_RED == 190_000     # 95%

    def test_budget_manager_default_usage(self, budget_manager):
        """测试默认使用量为0"""
        assert budget_manager.current_usage == {
            "layer0": 0,
            "layer1": 0,
            "layer2": 0,
            "layer3": 0,
            "conversation": 0
        }

    def test_budget_manager_total_usage(self, budget_manager):
        """测试总使用量计算"""
        # 设置各层使用量
        budget_manager.current_usage = {
            "layer0": 15000,
            "layer1": 8000,
            "layer2": 20000,
            "layer3": 10000,
            "conversation": 40000
        }
        
        total = budget_manager.get_total_usage()
        
        assert total == 93000

    # ========== 各层预算计算测试 ==========

    def test_calculate_layer0_budget(self, budget_manager):
        """测试 Layer 0 预算计算"""
        # Layer 0 通常包含工具定义和安全规则
        # 预期大小: ~5-15KB
        budget_manager.set_layer_usage("layer0", 12000)
        
        assert budget_manager.get_layer_usage("layer0") == 12000

    def test_calculate_layer1_budget(self, budget_manager):
        """测试 Layer 1 核心记忆预算计算"""
        # Layer 1 核心记忆 < 10KB
        budget_manager.set_layer_usage("layer1", 8500)
        
        assert budget_manager.get_layer_usage("layer1") == 8500

    def test_calculate_layer2_budget(self, budget_manager):
        """测试 Layer 2 工作上下文预算计算"""
        # Layer 2 工作上下文动态，上限 ~50KB
        budget_manager.set_layer_usage("layer2", 32000)
        
        assert budget_manager.get_layer_usage("layer2") == 32000

    def test_calculate_layer3_budget(self, budget_manager):
        """测试 Layer 3 知识库检索预算计算"""
        # Layer 3 Top-K 检索结果 ~10KB
        budget_manager.set_layer_usage("layer3", 10000)
        
        assert budget_manager.get_layer_usage("layer3") == 10000

    def test_calculate_conversation_budget(self, budget_manager):
        """测试对话历史预算计算"""
        # 对话历史 ~40KB
        budget_manager.set_layer_usage("conversation", 35000)
        
        assert budget_manager.get_layer_usage("conversation") == 35000

    # ========== 预算百分比计算测试 ==========

    def test_calculate_usage_percentage(self, budget_manager):
        """测试使用百分比计算"""
        budget_manager.set_layer_usage("layer0", 15000)
        budget_manager.set_layer_usage("layer1", 10000)
        
        percentage = budget_manager.get_usage_percentage()
        
        # (15000 + 10000) / 200000 = 0.125 = 12.5%
        assert percentage == pytest.approx(0.125, rel=0.01)

    def test_calculate_remaining_budget(self, budget_manager):
        """测试剩余预算计算"""
        budget_manager.set_layer_usage("layer0", 50000)
        
        remaining = budget_manager.get_remaining_budget()
        
        assert remaining == 150000  # 200000 - 50000

    def test_calculate_remaining_percentage(self, budget_manager):
        """测试剩余百分比计算"""
        budget_manager.set_layer_usage("layer0", 50000)
        
        remaining_pct = budget_manager.get_remaining_percentage()
        
        assert remaining_pct == pytest.approx(0.75, rel=0.01)

    # ========== 预算状态检查测试 ==========

    def test_check_budget_status_ok(self, budget_manager):
        """测试预算状态 - 正常"""
        budget_manager.set_layer_usage("layer0", 100000)  # 50%
        
        status = budget_manager.check_budget()
        
        assert status["status"] == "ok"
        assert status["action"] == "continue"

    def test_check_budget_status_caution(self, budget_manager):
        """测试预算状态 - 注意（75%以上）"""
        budget_manager.set_layer_usage("layer0", 160000)  # 80%
        
        status = budget_manager.check_budget()
        
        assert status["status"] == "caution"
        assert status["action"] == "monitor"

    def test_check_budget_status_warning(self, budget_manager):
        """测试预算状态 - 警告（85%以上）"""
        budget_manager.set_layer_usage("layer0", 175000)  # 87.5%
        
        status = budget_manager.check_budget()
        
        assert status["status"] == "warning"
        assert status["action"] == "suggest_compress"

    def test_check_budget_status_critical(self, budget_manager):
        """测试预算状态 - 紧急（95%以上）"""
        budget_manager.set_layer_usage("layer0", 195000)  # 97.5%
        
        status = budget_manager.check_budget()
        
        assert status["status"] == "critical"
        assert status["action"] == "force_compress"

    # ========== 预算分配建议测试 ==========

    def test_suggest_budget_allocation(self, budget_manager):
        """测试预算分配建议"""
        allocation = budget_manager.suggest_allocation()
        
        # 验证建议的分配比例
        assert "layer0" in allocation
        assert "layer1" in allocation
        assert "layer2" in allocation
        assert "layer3" in allocation
        assert "conversation" in allocation
        
        # Layer 1 应该 < 10KB
        assert allocation["layer1"] <= 10240  # 10KB in tokens

    def test_suggest_allocation_respects_limits(self, budget_manager):
        """测试分配建议尊重限制"""
        allocation = budget_manager.suggest_allocation()
        
        # 验证总预算不超过限制
        total_suggested = sum(allocation.values())
        assert total_suggested <= budget_manager.TOTAL_BUDGET

    # ========== 预算更新测试 ==========

    def test_update_budget_from_context(self, budget_manager):
        """测试从上下文更新预算"""
        context = {
            "system_prompt": "System prompt here...",  # ~20 tokens
            "core_memory": "User preferences...",       # ~100 tokens
            "working_context": "Current session...",    # ~500 tokens
            "knowledge_results": ["fact1", "fact2"],    # ~50 tokens
            "conversation": ["user: ...", "assistant: ..."]  # ~1000 tokens
        }
        
        budget_manager.update_from_context(context)
        
        # 验证各层使用量已更新
        assert budget_manager.get_layer_usage("layer0") > 0
        assert budget_manager.get_layer_usage("layer1") > 0
        assert budget_manager.get_layer_usage("layer2") > 0

    def test_estimate_token_count(self, budget_manager):
        """测试 Token 估算"""
        text = "Hello, this is a test message."
        
        # 简单估算：约 4 字符 = 1 token
        estimated = budget_manager.estimate_tokens(text)
        
        # 验证估算结果合理
        assert estimated > 0
        assert estimated < len(text)  # Token数通常小于字符数


class TestTokenBudgetLayerAllocation:
    """测试分层预算分配"""

    @pytest.fixture
    def budget_manager(self):
        """创建 TokenBudgetManager 实例"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        return TokenBudgetManager()

    def test_layer_budget_limits(self, budget_manager):
        """测试各层预算限制"""
        limits = budget_manager.get_layer_limits()
        
        # Layer 0: 5-15KB
        assert limits["layer0"]["min"] >= 5 * 1024
        assert limits["layer0"]["max"] <= 15 * 1024
        
        # Layer 1: < 10KB
        assert limits["layer1"]["max"] <= 10 * 1024
        
        # Layer 2: 动态，上限 50KB
        assert limits["layer2"]["max"] <= 50 * 1024
        
        # Layer 3: Top-K ~10KB
        assert limits["layer3"]["max"] <= 15 * 1024

    def test_validate_layer_usage_within_limit(self, budget_manager):
        """测试层使用量在限制内"""
        # Layer 1 限制 < 10KB
        assert budget_manager.validate_layer_usage("layer1", 8000) is True
        
    def test_validate_layer_usage_exceeds_limit(self, budget_manager):
        """测试层使用量超出限制"""
        # Layer 1 限制 < 10KB
        assert budget_manager.validate_layer_usage("layer1", 15000) is False

    def test_get_layer_usage_summary(self, budget_manager):
        """测试层使用量摘要"""
        budget_manager.set_layer_usage("layer0", 10000)
        budget_manager.set_layer_usage("layer1", 8000)
        
        summary = budget_manager.get_usage_summary()
        
        assert "total" in summary
        assert "percentage" in summary
        assert "by_layer" in summary
        assert summary["by_layer"]["layer0"] == 10000
        assert summary["by_layer"]["layer1"] == 8000

    def test_budget_report_generation(self, budget_manager):
        """测试预算报告生成"""
        budget_manager.set_layer_usage("layer0", 15000)
        budget_manager.set_layer_usage("layer1", 8000)
        
        report = budget_manager.generate_report()
        
        assert "timestamp" in report
        assert "total_usage" in report
        assert "remaining" in report
        assert "status" in report
        assert "layer_breakdown" in report


class TestTokenBudgetEdgeCases:
    """测试 Token 预算边界情况"""

    @pytest.fixture
    def budget_manager(self):
        """创建 TokenBudgetManager 实例"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        return TokenBudgetManager()

    def test_zero_usage(self, budget_manager):
        """测试零使用量"""
        assert budget_manager.get_total_usage() == 0
        assert budget_manager.get_usage_percentage() == 0.0
        assert budget_manager.get_remaining_budget() == 200000

    def test_full_usage(self, budget_manager):
        """测试满使用量"""
        budget_manager.set_layer_usage("layer0", 200000)
        
        assert budget_manager.get_usage_percentage() == 1.0
        assert budget_manager.get_remaining_budget() == 0

    def test_over_budget(self, budget_manager):
        """测试超出预算"""
        budget_manager.set_layer_usage("layer0", 250000)  # 超出
        
        status = budget_manager.check_budget()
        
        # 应该返回 critical 状态
        assert status["status"] == "critical"

    def test_negative_usage_not_allowed(self, budget_manager):
        """测试负使用量不被允许"""
        with pytest.raises(ValueError):
            budget_manager.set_layer_usage("layer0", -1000)

    def test_invalid_layer_name(self, budget_manager):
        """测试无效的层名称"""
        with pytest.raises(KeyError):
            budget_manager.set_layer_usage("invalid_layer", 1000)

    def test_unicode_text_token_estimation(self, budget_manager):
        """测试 Unicode 文本 Token 估算"""
        text = "这是中文测试文本，用于测试 Unicode 字符的 Token 估算"
        
        estimated = budget_manager.estimate_tokens(text)
        
        # 中文字符通常 1-2 tokens
        assert estimated > 0
        assert estimated <= len(text) * 2  # 最多每个字符2个token

    def test_empty_text_token_estimation(self, budget_manager):
        """测试空文本 Token 估算"""
        assert budget_manager.estimate_tokens("") == 0

    def test_very_long_text_token_estimation(self, budget_manager):
        """测试超长文本 Token 估算"""
        text = "a" * 100000  # 100,000 个字符
        
        estimated = budget_manager.estimate_tokens(text)
        
        # 应该估算合理（约 25,000 tokens for 100k chars）
        assert estimated > 0
        assert estimated <= 100000