import pytest
from src.core.dialogue.state_machine import (
    ConversationState, ConversationStateMachine, InvalidTransitionError,
)
from src.core.dialogue.sub_intent import ReadinessLevel


class _MockIntentState:
    def __init__(self, readiness_level):
        self.readiness_level = readiness_level


def _mock_intent_state(level):
    return _MockIntentState(level)


class TestNewConversationStates:
    def test_data_extracted_state_exists(self):
        assert hasattr(ConversationState, "DATA_EXTRACTED")
        assert ConversationState.DATA_EXTRACTED.value == "data_extracted"

    def test_requirement_confirm_state_exists(self):
        assert hasattr(ConversationState, "REQUIREMENT_CONFIRM")
        assert ConversationState.REQUIREMENT_CONFIRM.value == "requirement_confirm"

    def test_data_supplement_state_exists(self):
        assert hasattr(ConversationState, "DATA_SUPPLEMENT")
        assert ConversationState.DATA_SUPPLEMENT.value == "data_supplement"


class TestNewStateTransitions:
    def test_understanding_to_data_extracted(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        assert sm.current_state == ConversationState.DATA_EXTRACTED

    def test_data_extracted_to_requirement_confirm(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.REQUIREMENT_CONFIRM)
        assert sm.current_state == ConversationState.REQUIREMENT_CONFIRM

    def test_data_extracted_to_clarifying(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.CLARIFYING)
        assert sm.current_state == ConversationState.CLARIFYING

    def test_data_extracted_to_cancelled(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.CANCELLED)
        assert sm.current_state == ConversationState.CANCELLED

    def test_requirement_confirm_to_data_supplement(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.REQUIREMENT_CONFIRM)
        sm.transition(ConversationState.DATA_SUPPLEMENT)
        assert sm.current_state == ConversationState.DATA_SUPPLEMENT

    def test_requirement_confirm_to_framework_confirm(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.REQUIREMENT_CONFIRM)
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        assert sm.current_state == ConversationState.FRAMEWORK_CONFIRM

    def test_requirement_confirm_to_clarifying(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.REQUIREMENT_CONFIRM)
        sm.transition(ConversationState.CLARIFYING)
        assert sm.current_state == ConversationState.CLARIFYING

    def test_data_supplement_to_framework_confirm(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.REQUIREMENT_CONFIRM)
        sm.transition(ConversationState.DATA_SUPPLEMENT)
        sm.transition(ConversationState.FRAMEWORK_CONFIRM)
        assert sm.current_state == ConversationState.FRAMEWORK_CONFIRM

    def test_data_supplement_to_clarifying(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.REQUIREMENT_CONFIRM)
        sm.transition(ConversationState.DATA_SUPPLEMENT)
        sm.transition(ConversationState.CLARIFYING)
        assert sm.current_state == ConversationState.CLARIFYING

    def test_data_extracted_to_executing_is_valid(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.EXECUTING)
        assert sm.current_state == ConversationState.EXECUTING

    def test_invalid_transition_data_extracted_to_previewing(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        with pytest.raises(InvalidTransitionError):
            sm.transition(ConversationState.PREVIEWING)

    def test_data_extracted_self_loop(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.DATA_EXTRACTED)
        assert sm.current_state == ConversationState.DATA_EXTRACTED

    def test_requirement_confirm_self_loop(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.REQUIREMENT_CONFIRM)
        sm.transition(ConversationState.REQUIREMENT_CONFIRM)
        assert sm.current_state == ConversationState.REQUIREMENT_CONFIRM

    def test_data_supplement_self_loop(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.REQUIREMENT_CONFIRM)
        sm.transition(ConversationState.DATA_SUPPLEMENT)
        sm.transition(ConversationState.DATA_SUPPLEMENT)
        assert sm.current_state == ConversationState.DATA_SUPPLEMENT


class TestNewStateSuggestNext:
    def test_suggest_next_from_data_extracted_returns_none(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        result = sm.suggest_next(_mock_intent_state(ReadinessLevel.SUFFICIENT))
        assert result is None

    def test_suggest_next_from_requirement_confirm_sufficient(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.REQUIREMENT_CONFIRM)
        result = sm.suggest_next(_mock_intent_state(ReadinessLevel.SUFFICIENT))
        assert result == ConversationState.DATA_SUPPLEMENT

    def test_suggest_next_from_data_supplement_sufficient(self):
        sm = ConversationStateMachine()
        sm.transition(ConversationState.DATA_EXTRACTED)
        sm.transition(ConversationState.REQUIREMENT_CONFIRM)
        sm.transition(ConversationState.DATA_SUPPLEMENT)
        result = sm.suggest_next(_mock_intent_state(ReadinessLevel.SUFFICIENT))
        assert result == ConversationState.FRAMEWORK_CONFIRM
