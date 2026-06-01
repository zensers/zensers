# -*- coding: utf-8 -*-
"""
对话状态机测试

测试对话状态转换和持久化
"""

import pytest
from pathlib import Path
from src.core.dialogue.state_machine import (
    ConversationState,
    ConversationStateMachine,
    InvalidTransitionError
)
from src.core.dialogue.sub_intent import ReadinessLevel
from src.core.dialogue.dialogue_intent_state import DialogueIntentState


class TestConversationState:
    """测试对话状态枚举"""
    
    def test_state_values(self):
        """测试状态值"""
        assert ConversationState.UNDERSTANDING.value == "understanding"
        assert ConversationState.CLARIFYING.value == "clarifying"
        assert ConversationState.FRAMEWORK_CONFIRM.value == "framework_confirm"
        assert ConversationState.EXECUTING.value == "executing"
        assert ConversationState.COMPLETED.value == "completed"
    
    def test_all_states_defined(self):
        """测试所有状态都已定义"""
        states = list(ConversationState)
        assert len(states) == 8


class TestConversationStateMachineInit:
    """测试状态机初始化"""
    
    def test_initial_state_is_understanding(self):
        """初始状态为理解中"""
        machine = ConversationStateMachine()
        assert machine.current_state == ConversationState.UNDERSTANDING
    
    def test_init_with_research_id(self):
        """使用研究ID初始化"""
        machine = ConversationStateMachine(research_id="research_001")
        assert machine.research_id == "research_001"
    
    def test_init_with_context(self):
        """使用上下文初始化"""
        context = {"user_input": "研究储能行业"}
        machine = ConversationStateMachine(context=context)
        assert machine.context == context


class TestConversationStateMachineTransitions:
    """测试状态转换"""
    
    def test_valid_transition_understanding_to_clarifying(self):
        """有效转换: 理解中 -> 澄清中"""
        machine = ConversationStateMachine()
        machine.transition(ConversationState.CLARIFYING)
        assert machine.current_state == ConversationState.CLARIFYING
    
    def test_valid_transition_clarifying_to_framework_confirm(self):
        """有效转换: 澄清中 -> 框架确认"""
        machine = ConversationStateMachine()
        machine.transition(ConversationState.CLARIFYING)
        machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        assert machine.current_state == ConversationState.FRAMEWORK_CONFIRM
    
    def test_valid_transition_framework_confirm_to_executing(self):
        """有效转换: 框架确认 -> 执行中"""
        machine = ConversationStateMachine()
        machine.transition(ConversationState.CLARIFYING)
        machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        machine.transition(ConversationState.EXECUTING)
        assert machine.current_state == ConversationState.EXECUTING
    
    def test_valid_transition_executing_to_completed(self):
        """有效转换: 执行中 -> 完成"""
        machine = ConversationStateMachine()
        machine.transition(ConversationState.CLARIFYING)
        machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        machine.transition(ConversationState.EXECUTING)
        machine.transition(ConversationState.COMPLETED)
        assert machine.current_state == ConversationState.COMPLETED
    
    def test_invalid_transition_understanding_to_completed(self):
        """无效转换: 理解中 -> 完成（跳过中间状态）"""
        machine = ConversationStateMachine()
        with pytest.raises(InvalidTransitionError) as exc_info:
            machine.transition(ConversationState.COMPLETED)
        assert "Invalid transition" in str(exc_info.value)
    
    def test_valid_transition_understanding_to_executing(self):
        """有效转换: 理解中 -> 执行中（P2 fix: 允许模板快速启动直接跳到执行）"""
        machine = ConversationStateMachine()
        machine.transition(ConversationState.EXECUTING)
        assert machine.current_state == ConversationState.EXECUTING
    
    def test_valid_transition_understanding_to_framework_confirm(self):
        """有效转换: 理解中 -> 框架确认（readiness=SUFFICIENT 时直接跳转）"""
        machine = ConversationStateMachine()
        machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        assert machine.current_state == ConversationState.FRAMEWORK_CONFIRM
    
    def test_transition_to_same_state_allowed(self):
        """允许转换到当前状态（幂等）"""
        machine = ConversationStateMachine()
        machine.transition(ConversationState.UNDERSTANDING)  # 同状态转换
        assert machine.current_state == ConversationState.UNDERSTANDING


class TestConversationStateMachineContext:
    """测试上下文管理"""
    
    def test_update_context(self):
        """更新上下文"""
        machine = ConversationStateMachine()
        machine.update_context("user_input", "研究储能行业")
        assert machine.context["user_input"] == "研究储能行业"
    
    def test_update_context_multiple_times(self):
        """多次更新上下文"""
        machine = ConversationStateMachine()
        machine.update_context("user_input", "研究储能行业")
        machine.update_context("time_range", "未来3年")
        
        assert machine.context["user_input"] == "研究储能行业"
        assert machine.context["time_range"] == "未来3年"
    
    def test_get_context(self):
        """获取上下文"""
        machine = ConversationStateMachine()
        machine.update_context("key", "value")
        assert machine.get_context("key") == "value"
    
    def test_get_context_default(self):
        """获取不存在的上下文返回默认值"""
        machine = ConversationStateMachine()
        assert machine.get_context("nonexistent", default=None) is None


class TestConversationStateMachinePersistence:
    """测试状态持久化"""
    
    def test_save_state(self, tmp_path):
        """保存状态"""
        machine = ConversationStateMachine(research_id="research_001")
        machine.transition(ConversationState.CLARIFYING)
        machine.update_context("user_input", "研究储能行业")
        
        save_path = tmp_path / "state.json"
        machine.save(str(save_path))
        
        assert save_path.exists()
    
    def test_load_state(self, tmp_path):
        """加载状态"""
        # 创建并保存状态
        machine1 = ConversationStateMachine(research_id="research_001")
        machine1.transition(ConversationState.CLARIFYING)
        machine1.update_context("user_input", "研究储能行业")
        
        save_path = tmp_path / "state.json"
        machine1.save(str(save_path))
        
        # 加载状态
        machine2 = ConversationStateMachine.load(str(save_path))
        
        assert machine2.research_id == "research_001"
        assert machine2.current_state == ConversationState.CLARIFYING
        assert machine2.context["user_input"] == "研究储能行业"
    
    def test_load_nonexistent_file_raises_error(self, tmp_path):
        """加载不存在的文件抛出错误"""
        with pytest.raises(FileNotFoundError):
            ConversationStateMachine.load(str(tmp_path / "nonexistent.json"))
    
    def test_save_and_load_preserves_all_data(self, tmp_path):
        """保存和加载保留所有数据"""
        machine1 = ConversationStateMachine(research_id="test_123")
        machine1.transition(ConversationState.CLARIFYING)
        machine1.transition(ConversationState.FRAMEWORK_CONFIRM)
        machine1.update_context("key1", "value1")
        machine1.update_context("key2", "value2")
        
        save_path = tmp_path / "full_state.json"
        machine1.save(str(save_path))
        
        machine2 = ConversationStateMachine.load(str(save_path))
        
        assert machine2.research_id == "test_123"
        assert machine2.current_state == ConversationState.FRAMEWORK_CONFIRM
        assert machine2.context["key1"] == "value1"
        assert machine2.context["key2"] == "value2"


class TestConversationStateMachineHistory:
    """测试状态历史"""
    
    def test_state_history_tracking(self):
        """状态历史追踪"""
        machine = ConversationStateMachine()
        machine.transition(ConversationState.CLARIFYING)
        machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        
        history = machine.get_history()
        
        assert len(history) == 3  # UNDERSTANDING, CLARIFYING, FRAMEWORK_CONFIRM
        assert history[0]["state"] == ConversationState.UNDERSTANDING
        assert history[1]["state"] == ConversationState.CLARIFYING
        assert history[2]["state"] == ConversationState.FRAMEWORK_CONFIRM
    
    def test_history_includes_timestamps(self):
        """历史包含时间戳"""
        machine = ConversationStateMachine()
        machine.transition(ConversationState.CLARIFYING)
        
        history = machine.get_history()
        
        assert "timestamp" in history[0]
        assert "timestamp" in history[1]
    
    def test_clear_history(self):
        """清除历史"""
        machine = ConversationStateMachine()
        machine.transition(ConversationState.CLARIFYING)
        machine.clear_history()
        
        assert len(machine.get_history()) == 0


class TestConversationStateMachineHelpers:
    """测试辅助方法"""
    
    def test_is_in_state(self):
        """检查当前状态"""
        machine = ConversationStateMachine()
        assert machine.is_in_state(ConversationState.UNDERSTANDING)
        assert not machine.is_in_state(ConversationState.COMPLETED)
    
    def test_can_transition_to(self):
        """检查是否可以转换到目标状态"""
        machine = ConversationStateMachine()
        
        # 可以转换到 CLARIFYING
        assert machine.can_transition_to(ConversationState.CLARIFYING)
        
        # 不能直接转换到 COMPLETED
        assert not machine.can_transition_to(ConversationState.COMPLETED)
    
    def test_get_allowed_transitions(self):
        """获取允许的转换"""
        machine = ConversationStateMachine()
        allowed = machine.get_allowed_transitions()
        
        # UNDERSTANDING 状态可以转换到 UNDERSTANDING 和 CLARIFYING
        assert ConversationState.UNDERSTANDING in allowed
        assert ConversationState.CLARIFYING in allowed
        assert ConversationState.COMPLETED not in allowed
    
    def test_reset(self):
        """重置状态机"""
        machine = ConversationStateMachine()
        machine.transition(ConversationState.CLARIFYING)
        machine.update_context("key", "value")
        
        machine.reset()
        
        assert machine.current_state == ConversationState.UNDERSTANDING
        assert len(machine.context) == 0
        # reset后会记录初始状态，所以历史长度为1
        assert len(machine.get_history()) == 1
        assert machine.get_history()[0]["state"] == ConversationState.UNDERSTANDING


class TestForceSetState:
    """测试强制设置状态"""

    def test_force_set_state_to_valid_state(self):
        machine = ConversationStateMachine()
        machine.force_set_state(ConversationState.EXECUTING)
        assert machine.current_state == ConversationState.EXECUTING

    def test_force_set_state_invalid_value_raises(self):
        machine = ConversationStateMachine()
        with pytest.raises(ValueError):
            machine.force_set_state("invalid_state")

    def test_force_set_state_records_history(self):
        machine = ConversationStateMachine()
        machine.force_set_state(ConversationState.COMPLETED)
        history = machine.get_history()
        assert history[-1]["state"] == ConversationState.COMPLETED


class TestSuggestNext:
    """测试基于 ReadinessLevel 的状态建议"""

    def test_understanding_insufficient_returns_none(self):
        machine = ConversationStateMachine()
        state = DialogueIntentState()
        assert state.readiness_level == ReadinessLevel.INSUFFICIENT
        assert machine.suggest_next(state) is None

    def test_understanding_partial_suggests_clarifying(self):
        machine = ConversationStateMachine()
        state = DialogueIntentState(topic_hint="test", readiness_level=ReadinessLevel.PARTIAL)
        assert machine.suggest_next(state) == ConversationState.CLARIFYING

    def test_understanding_sufficient_suggests_framework_confirm(self):
        machine = ConversationStateMachine()
        state = DialogueIntentState(topic_hint="test", readiness_level=ReadinessLevel.SUFFICIENT)
        assert machine.suggest_next(state) == ConversationState.FRAMEWORK_CONFIRM

    def test_clarifying_sufficient_suggests_framework_confirm(self):
        machine = ConversationStateMachine()
        machine.transition(ConversationState.CLARIFYING)
        state = DialogueIntentState(topic_hint="test", readiness_level=ReadinessLevel.SUFFICIENT)
        assert machine.suggest_next(state) == ConversationState.FRAMEWORK_CONFIRM

    def test_clarifying_partial_returns_none(self):
        machine = ConversationStateMachine()
        machine.transition(ConversationState.CLARIFYING)
        state = DialogueIntentState(topic_hint="test", readiness_level=ReadinessLevel.PARTIAL)
        assert machine.suggest_next(state) is None

    def test_framework_confirm_insufficient_suggests_clarifying(self):
        machine = ConversationStateMachine()
        machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        state = DialogueIntentState(readiness_level=ReadinessLevel.INSUFFICIENT)
        assert machine.suggest_next(state) == ConversationState.CLARIFYING

    def test_framework_confirm_sufficient_returns_none(self):
        machine = ConversationStateMachine()
        machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        state = DialogueIntentState(topic_hint="test", readiness_level=ReadinessLevel.SUFFICIENT)
        assert machine.suggest_next(state) is None

    def test_executing_returns_none(self):
        machine = ConversationStateMachine()
        machine.transition(ConversationState.EXECUTING)
        state = DialogueIntentState(readiness_level=ReadinessLevel.SUFFICIENT)
        assert machine.suggest_next(state) is None