"""
Token 预算监控测试 - TDD模式

测试 TokenBudgetManager 的状态监控功能
参考: CONTEXT_COMPRESSION.md 第4节 Token 预算管理

测试覆盖：
- 预算状态监控
- 预警机制
- 历史记录追踪
- 监控回调
"""

import pytest
from typing import Dict, Any, List
from datetime import datetime
import time


class TestTokenBudgetMonitoring:
    """测试 Token 预算监控"""

    @pytest.fixture
    def budget_manager(self):
        """创建 TokenBudgetManager 实例"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        return TokenBudgetManager()

    # ========== 状态监控测试 ==========

    def test_monitor_returns_current_state(self, budget_manager):
        """测试监控返回当前状态"""
        budget_manager.set_layer_usage("layer0", 50000)
        
        state = budget_manager.get_current_state()
        
        assert "total_usage" in state
        assert "percentage" in state
        assert "status" in state
        assert "timestamp" in state

    def test_monitor_tracks_usage_history(self, budget_manager):
        """测试监控追踪使用历史"""
        # 模拟多次使用变化
        budget_manager.set_layer_usage("layer0", 10000)
        budget_manager.record_usage_snapshot()
        
        budget_manager.set_layer_usage("layer1", 20000)
        budget_manager.record_usage_snapshot()
        
        history = budget_manager.get_usage_history()
        
        assert len(history) >= 2
        assert history[0]["total_usage"] != history[1]["total_usage"]

    def test_monitor_clears_old_history(self, budget_manager):
        """测试监控清理旧历史"""
        # 添加多条历史记录
        for i in range(20):
            budget_manager.set_layer_usage("layer0", i * 1000)
            budget_manager.record_usage_snapshot()
        
        history = budget_manager.get_usage_history(max_records=10)
        
        # 应该只保留最近10条
        assert len(history) <= 10

    # ========== 预警机制测试 ==========

    def test_warning_threshold_yellow(self, budget_manager):
        """测试黄色预警阈值 (75%)"""
        budget_manager.set_layer_usage("layer0", 155000)  # 77.5%
        
        warnings = budget_manager.check_warnings()
        
        assert len(warnings) > 0
        assert any(w["level"] == "yellow" for w in warnings)

    def test_warning_threshold_orange(self, budget_manager):
        """测试橙色预警阈值 (85%)"""
        budget_manager.set_layer_usage("layer0", 175000)  # 87.5%
        
        warnings = budget_manager.check_warnings()
        
        assert len(warnings) > 0
        assert any(w["level"] == "orange" for w in warnings)

    def test_warning_threshold_red(self, budget_manager):
        """测试红色预警阈值 (95%)"""
        budget_manager.set_layer_usage("layer0", 195000)  # 97.5%
        
        warnings = budget_manager.check_warnings()
        
        assert len(warnings) > 0
        assert any(w["level"] == "red" for w in warnings)

    def test_warning_includes_message(self, budget_manager):
        """测试预警包含消息"""
        budget_manager.set_layer_usage("layer0", 155000)
        
        warnings = budget_manager.check_warnings()
        
        assert len(warnings) > 0
        assert "message" in warnings[0]
        assert "threshold" in warnings[0]

    def test_no_warning_when_ok(self, budget_manager):
        """测试状态正常时无预警"""
        budget_manager.set_layer_usage("layer0", 50000)  # 25%
        
        warnings = budget_manager.check_warnings()
        
        assert len(warnings) == 0

    # ========== 监控回调测试 ==========

    def test_register_warning_callback(self, budget_manager):
        """测试注册预警回调"""
        callback_called = []
        
        def on_warning(warning):
            callback_called.append(warning)
        
        budget_manager.register_warning_callback(on_warning)
        
        budget_manager.set_layer_usage("layer0", 155000)
        budget_manager.check_and_notify()
        
        assert len(callback_called) > 0

    def test_multiple_callbacks(self, budget_manager):
        """测试多个回调"""
        calls = []
        
        def callback1(w):
            calls.append("callback1")
        
        def callback2(w):
            calls.append("callback2")
        
        budget_manager.register_warning_callback(callback1)
        budget_manager.register_warning_callback(callback2)
        
        budget_manager.set_layer_usage("layer0", 155000)
        budget_manager.check_and_notify()
        
        assert len(calls) >= 2

    def test_callback_receives_warning_data(self, budget_manager):
        """测试回调接收预警数据"""
        received = {}
        
        def callback(warning):
            received.update(warning)
        
        budget_manager.register_warning_callback(callback)
        
        budget_manager.set_layer_usage("layer0", 155000)
        budget_manager.check_and_notify()
        
        assert "level" in received
        assert "message" in received

    # ========== 监控报告测试 ==========

    def test_generate_monitoring_report(self, budget_manager):
        """测试生成监控报告"""
        budget_manager.set_layer_usage("layer0", 50000)
        budget_manager.set_layer_usage("layer1", 8000)
        
        report = budget_manager.generate_monitoring_report()
        
        assert "current_state" in report
        assert "warnings" in report
        assert "recommendations" in report
        assert "generated_at" in report

    def test_monitoring_report_includes_layer_breakdown(self, budget_manager):
        """测试监控报告包含层分解"""
        budget_manager.set_layer_usage("layer0", 15000)
        budget_manager.set_layer_usage("layer1", 8000)
        
        report = budget_manager.generate_monitoring_report()
        
        assert "layer_breakdown" in report["current_state"]
        assert report["current_state"]["layer_breakdown"]["layer0"] == 15000
        assert report["current_state"]["layer_breakdown"]["layer1"] == 8000

    def test_monitoring_report_recommendations(self, budget_manager):
        """测试监控报告建议"""
        budget_manager.set_layer_usage("layer0", 180000)  # 90%
        
        report = budget_manager.generate_monitoring_report()
        
        assert len(report["recommendations"]) > 0
        # 应该建议压缩
        assert any("compress" in r.lower() for r in report["recommendations"])


class TestTokenBudgetThresholds:
    """测试 Token 预算阈值配置"""

    @pytest.fixture
    def budget_manager(self):
        """创建 TokenBudgetManager 实例"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        return TokenBudgetManager()

    def test_default_thresholds(self, budget_manager):
        """测试默认阈值"""
        thresholds = budget_manager.get_thresholds()
        
        assert thresholds["yellow"] == 0.75  # 75%
        assert thresholds["orange"] == 0.85  # 85%
        assert thresholds["red"] == 0.95     # 95%

    def test_custom_thresholds(self):
        """测试自定义阈值"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        
        manager = TokenBudgetManager(
            yellow_threshold=0.7,
            orange_threshold=0.8,
            red_threshold=0.9
        )
        
        thresholds = manager.get_thresholds()
        
        assert thresholds["yellow"] == 0.7
        assert thresholds["orange"] == 0.8
        assert thresholds["red"] == 0.9

    def test_threshold_validation(self):
        """测试阈值验证"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        
        # 无效阈值应该抛出异常
        with pytest.raises(ValueError):
            TokenBudgetManager(yellow_threshold=0.9, orange_threshold=0.8)  # 黄色 > 橙色

    def test_threshold_bounds(self):
        """测试阈值边界"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        
        # 阈值应该在 0-1 之间
        with pytest.raises(ValueError):
            TokenBudgetManager(yellow_threshold=1.5)  # 超过 1.0


class TestTokenBudgetNotifications:
    """测试 Token 预算通知机制"""

    @pytest.fixture
    def budget_manager(self):
        """创建 TokenBudgetManager 实例"""
        from src.core.memory.budget.budget_manager import TokenBudgetManager
        return TokenBudgetManager()

    def test_notification_on_threshold_cross(self, budget_manager):
        """测试跨阈值时发送通知"""
        notifications = []
        
        def handler(notification):
            notifications.append(notification)
        
        budget_manager.register_notification_handler(handler)
        
        # 模拟跨阈值
        budget_manager.set_layer_usage("layer0", 155000)
        budget_manager.check_and_notify()
        
        assert len(notifications) > 0

    def test_notification_level_correct(self, budget_manager):
        """测试通知级别正确"""
        notification = {}
        
        def handler(n):
            notification.update(n)
        
        budget_manager.register_notification_handler(handler)
        
        budget_manager.set_layer_usage("layer0", 180000)
        budget_manager.check_and_notify()
        
        assert notification.get("level") in ["orange", "red"]

    def test_notification_debounce(self, budget_manager):
        """测试通知防抖"""
        notifications = []
        
        def handler(n):
            notifications.append(n)
        
        budget_manager.register_notification_handler(handler)
        
        # 快速多次触发
        for _ in range(5):
            budget_manager.set_layer_usage("layer0", 180000)
            budget_manager.check_and_notify()
        
        # 应该只发送一次通知（防抖）
        assert len(notifications) <= 2  # 允许少量重复

    def test_notification_cooldown(self, budget_manager):
        """测试通知冷却时间"""
        notifications = []
        
        def handler(n):
            notifications.append(n)
        
        budget_manager.register_notification_handler(handler)
        budget_manager.set_notification_cooldown(1.0)  # 1秒冷却
        
        budget_manager.set_layer_usage("layer0", 180000)
        budget_manager.check_and_notify()
        
        # 立即再次触发
        budget_manager.check_and_notify()
        
        # 第二次应该被冷却
        assert len(notifications) == 1