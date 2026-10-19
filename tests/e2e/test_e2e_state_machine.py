# -*- coding: utf-8 -*-
"""
Phase 2: State Machine Boundary E2E Tests

Tests invalid and edge-case state transitions.
No real LLM needed — state machine transitions are deterministic.
"""

import asyncio
import logging
import pytest

from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState
from src.core.session_manager import SessionManager

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e]


class TestStateMachineInvalidTransitions:
    """Scenario 2.1: Invalid transition from UNDERSTANDING to COMPLETED"""

    def test_understanding_to_completed_raises(self):
        sm = ConversationStateMachine(research_id="test_2_1")
        assert sm.current_state == ConversationState.UNDERSTANDING
        with pytest.raises(Exception):
            sm.transition(ConversationState.COMPLETED)

    def test_understanding_to_paused_raises(self):
        sm = ConversationStateMachine(research_id="test_2_1c")
        with pytest.raises(Exception):
            sm.transition(ConversationState.PAUSED)

    def test_understanding_to_previewing_raises(self):
        sm = ConversationStateMachine(research_id="test_2_1d")
        with pytest.raises(Exception):
            sm.transition(ConversationState.PREVIEWING)

    def test_cancelled_to_executing_is_allowed_for_checkpoint_resume(self):
        sm = ConversationStateMachine(research_id="test_2_1e")
        sm.transition(ConversationState.CANCELLED)
        sm.transition(ConversationState.EXECUTING)
        assert sm.current_state == ConversationState.EXECUTING

    def test_completed_to_executing_raises(self):
        sm = ConversationStateMachine(research_id="test_2_1f")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        sm.transition(ConversationState.COMPLETED)
        with pytest.raises(Exception):
            sm.transition(ConversationState.EXECUTING)


class TestHeavyActionInExecuting:
    """Scenario 2.2: Heavy action downgraded in EXECUTING state"""

    def test_validate_action_downgrades_in_executing(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        sm = ConversationStateMachine(research_id="test_2_2")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        result = api._validate_action_for_state("modify_research", sm, "casual chat")
        assert result != "modify_research", "Heavy action should be downgraded in EXECUTING"

    def test_continue_chat_allowed_in_executing(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        sm = ConversationStateMachine(research_id="test_2_2b")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        result = api._validate_action_for_state("continue_chat", sm, "hello")
        assert result == "continue_chat"


class TestFrameworkConfirmWhilePaused:
    """Scenario 2.3: PAUSED can transition to FRAMEWORK_CONFIRM (design allows modifying requirements)"""

    def test_paused_can_transition_to_framework_confirm(self):
        sm = ConversationStateMachine(research_id="test_2_3")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        sm.transition(ConversationState.PAUSED)
        assert sm.current_state == ConversationState.PAUSED
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        assert sm.current_state == ConversationState.FRAMEWORK_CONFIRM

    def test_paused_cannot_transition_to_completed(self):
        sm = ConversationStateMachine(research_id="test_2_3b")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        sm.transition(ConversationState.PAUSED)
        with pytest.raises(Exception):
            sm.transition(ConversationState.COMPLETED)

    def test_paused_can_resume_to_executing(self):
        sm = ConversationStateMachine(research_id="test_2_3c")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        sm.transition(ConversationState.PAUSED)
        sm.transition(ConversationState.EXECUTING)
        assert sm.current_state == ConversationState.EXECUTING


class TestResumeFromCancelled:
    """Scenario 2.4: CANCELLED is resumable only through an explicit checkpoint."""

    def test_cancelled_state_allows_only_explicit_resume_paths(self):
        sm = ConversationStateMachine(research_id="test_2_4")
        sm.transition(ConversationState.CANCELLED)
        assert sm.can_transition_to(ConversationState.EXECUTING)
        assert sm.can_transition_to(ConversationState.PAUSED)
        with pytest.raises(Exception):
            sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        with pytest.raises(Exception):
            sm.transition(ConversationState.COMPLETED)

    @pytest.mark.asyncio
    async def test_cancelled_session_resume_starts_new_generation(self, client, cleanup_test_sessions):
        start_result = await client.quick_start(
            user_input="test cancel resume",
            template_id="industry_research",
            auto_confirm=True,
        )
        session_id = start_result.get("session_id") or start_result.get("task_id")
        if not session_id:
            pytest.skip("Could not create session")
        cleanup_test_sessions.append(session_id)

        await asyncio.sleep(3)

        cancel_result = await client.cancel_research(session_id)
        logger.info(f"Cancel result: {cancel_result}")

        resume_result = await client.resume_research(session_id)
        resume_status = resume_result.get("status", "")
        assert resume_status == "resumed", \
            f"A cancelled session with a saved checkpoint should resume: got {resume_status}"


class TestDoubleConfirmIdempotent:
    """Scenario 2.5: Double confirm is idempotent"""

    def test_double_framework_confirm(self):
        sm = ConversationStateMachine(research_id="test_2_5")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        assert sm.current_state == ConversationState.FRAMEWORK_CONFIRM
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        assert sm.current_state == ConversationState.FRAMEWORK_CONFIRM

    @pytest.mark.asyncio
    async def test_double_feedback_confirm(self, client, cleanup_test_sessions):
        start_result = await client.start_research(user_input="test double confirm")
        session_id = start_result.get("session_id") or start_result.get("task_id")
        if not session_id:
            pytest.skip("Could not create session")
        cleanup_test_sessions.append(session_id)

        fb1 = await client.feedback(session_id=session_id, action="confirm")
        fb2 = await client.feedback(session_id=session_id, action="confirm")
        assert fb1.get("status") == fb2.get("status"), "Double confirm should be idempotent"


class TestValidStateTransitions:
    """Cover all valid state machine transitions"""

    def test_understanding_to_framework_confirm(self):
        sm = ConversationStateMachine(research_id="test_valid_1")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        assert sm.current_state == ConversationState.FRAMEWORK_CONFIRM

    def test_framework_confirm_to_executing(self):
        sm = ConversationStateMachine(research_id="test_valid_2")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        assert sm.current_state == ConversationState.EXECUTING

    def test_executing_to_paused(self):
        sm = ConversationStateMachine(research_id="test_valid_3")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        sm.transition(ConversationState.PAUSED)
        assert sm.current_state == ConversationState.PAUSED

    def test_executing_to_completed(self):
        sm = ConversationStateMachine(research_id="test_valid_4")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        sm.transition(ConversationState.COMPLETED)
        assert sm.current_state == ConversationState.COMPLETED

    def test_paused_to_executing(self):
        sm = ConversationStateMachine(research_id="test_valid_5")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        sm.transition(ConversationState.PAUSED)
        sm.transition(ConversationState.EXECUTING)
        assert sm.current_state == ConversationState.EXECUTING

    def test_executing_to_cancelled(self):
        sm = ConversationStateMachine(research_id="test_valid_6")
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        sm.transition(ConversationState.EXECUTING)
        sm.transition(ConversationState.CANCELLED)
        assert sm.current_state == ConversationState.CANCELLED
