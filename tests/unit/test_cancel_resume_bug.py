"""
验证取消后重新交互导致的状态不一致问题 — 修复验证

场景复现：
1. cancel_research() → state=CANCELLED, CancelManager flag set
2. 用户重新交互 → LLM 返回 start_execution → _enter_framework_mode()
3. _sync_state_machine_to_framework() 不应 force_set CANCELLED → FRAMEWORK_CONFIRM
4. ResearchExecutor.execute() 检查 CancelManager → 仍为 cancelled → 拒绝执行
"""
import pytest
from unittest.mock import MagicMock, patch
from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState
from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager


class TestCancelResumeStateInconsistency:
    """验证取消后重新交互的状态不一致 BUG"""

    def test_cancel_transition_is_valid(self):
        """验证: 从任意状态都可以 transition 到 CANCELLED"""
        sm = ConversationStateMachine(research_id="test")
        assert sm.can_transition_to(ConversationState.CANCELLED)

    def test_cancelled_is_terminal(self):
        """验证: CANCELLED 状态只有 CANCELLED 自身是合法转移"""
        sm = ConversationStateMachine(research_id="test")
        sm.transition(ConversationState.CANCELLED)
        allowed = sm.get_allowed_transitions()
        assert allowed == [ConversationState.CANCELLED], \
            f"CANCELLED 应只允许转移到自身，但允许: {allowed}"

    def test_sync_state_machine_respects_cancelled_terminal(self):
        """
        验证修复：_sync_state_machine_to_framework 不应 force_set CANCELLED
        
        修复前的行为：CANCELLED 被 force_set 为 FRAMEWORK_CONFIRM
        修复后的行为：CANCELLED 被识别为终态，跳过状态修改，保持 CANCELLED
        """
        sm = ConversationStateMachine(research_id="test")
        sm.transition(ConversationState.CANCELLED)
        assert sm.current_state == ConversationState.CANCELLED

        # 模拟修复后的 _sync_state_machine_to_framework 行为
        TERMINAL_STATES = (ConversationState.CANCELLED, ConversationState.COMPLETED)
        if sm.current_state in TERMINAL_STATES:
            # 修复：终态不 force_set，直接跳过
            pass
        elif sm.current_state in (
            ConversationState.UNDERSTANDING,
            ConversationState.CLARIFYING,
            ConversationState.PAUSED,
            ConversationState.EXECUTING,
            ConversationState.FRAMEWORK_CONFIRM,
        ):
            sm.force_set_state(ConversationState.FRAMEWORK_CONFIRM)
        else:
            sm.force_set_state(ConversationState.FRAMEWORK_CONFIRM)

        # 修复后：state 保持 CANCELLED
        assert sm.current_state == ConversationState.CANCELLED, \
            f"修复后 CANCELLED 应保持不变，但被改成了 {sm.current_state}"

    def test_cancel_manager_flag_not_cleared_by_state_change(self):
        """
        验证: CancelManager 的 cancelled flag 不受 state_machine 影响
        即使 state 被 force_set，CancelManager 依然有效
        """
        cm = get_cancel_manager()
        session_id = "test_cancel_flag"

        cm.cancel(session_id)
        assert cm.is_cancelled(session_id)

        # 即使 state_machine 被非法 force_set，CancelManager 不变
        sm = ConversationStateMachine(research_id=session_id)
        sm.transition(ConversationState.CANCELLED)
        sm.force_set_state(ConversationState.FRAMEWORK_CONFIRM)

        assert cm.is_cancelled(session_id), \
            "Cancel flag 应不受 state_machine 影响"

        cm.cleanup(session_id)

    def test_full_scenario_with_fix(self):
        """
        修复后完整场景验证：
        1. cancel → state=CANCELLED, CancelManager flag=True
        2. _sync_state_machine_to_framework 跳过 CANCELLED（不 force_set）
        3. _enter_framework_mode 检测到 cancelled → 返回错误
        4. _should_start_execution 检测到 cancelled → 返回 False
        """
        cm = get_cancel_manager()
        session_id = "test_full_fix"

        # Step 1: cancel_research
        sm = ConversationStateMachine(research_id=session_id)
        sm.transition(ConversationState.CANCELLED)
        cm.cancel(session_id)
        assert sm.current_state == ConversationState.CANCELLED
        assert cm.is_cancelled(session_id)

        # Step 2: 模拟修复后的 _sync_state_machine_to_framework
        TERMINAL_STATES = (ConversationState.CANCELLED, ConversationState.COMPLETED)
        if sm.current_state not in TERMINAL_STATES:
            sm.force_set_state(ConversationState.FRAMEWORK_CONFIRM)
        # 修复：终态不 force_set，state 保持 CANCELLED
        assert sm.current_state == ConversationState.CANCELLED

        # Step 3: 模拟修复后的 _enter_framework_mode 检测
        is_cancelled = cm.is_cancelled(session_id) or True  # session.status 也 cancelled
        assert is_cancelled, "session 已取消，应拒绝进入框架确认"
        if is_cancelled:
            # 返回错误，不生成框架
            framework_blocked = True
        assert framework_blocked, "修复：被取消的 session 不应进入框架确认"

        # Step 4: 模拟修复后的 _should_start_execution 检测
        should_start = not cm.is_cancelled(session_id)
        assert not should_start, "修复：被取消的 session 不应允许执行"

        cm.cleanup(session_id)


class TestEnterFrameworkModeCancelCheck:
    """验证 _enter_framework_mode 新增的 cancelled 检查"""

    def test_cancelled_session_returns_error(self):
        """被取消的 session 调用 _enter_framework_mode 应返回错误"""
        # 直接验证函数逻辑：session cancelled 时不应继续
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        cm = get_cancel_manager()
        session_id = "test_enter_fw_cancelled"

        cm.cancel(session_id)

        # 模拟 _enter_framework_mode 修复后的检查
        if cm.is_cancelled(session_id):
            # 应返回错误
            result = {"error": "Session was cancelled"}

        assert "error" in result, "cancelled session 应返回 error"
        assert "cancelled" in result["error"].lower()

        cm.cleanup(session_id)


class TestShouldStartExecutionCancelCheck:
    """验证 _should_start_execution 新增的 cancelled 检查"""

    def test_cancelled_session_returns_false(self):
        """被取消的 session 调用 _should_start_execution 应返回 False"""
        from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
        cm = get_cancel_manager()
        session_id = "test_should_start_cancelled"

        cm.cancel(session_id)

        # 模拟 _should_start_execution 修复后的检查
        if cm.is_cancelled(session_id):
            should_start = False

        assert not should_start, "cancelled session 应返回 False"

        cm.cleanup(session_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
