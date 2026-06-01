# -*- coding: utf-8 -*-
"""
DialogueIntentState 单元测试
"""

import pytest
from src.core.dialogue.sub_intent import SubIntent, ReadinessLevel
from src.core.dialogue.dialogue_intent_state import DialogueIntentState


class TestDialogueIntentStateInit:
    def test_default_values(self):
        state = DialogueIntentState()
        assert state.topic_hint == ""
        assert state.confirmed_aspects == []
        assert state.readiness_level == ReadinessLevel.INSUFFICIENT
        assert state.readiness_score == 0.0
        assert state.is_composite is False
        assert state.research_turns == 0
        assert state.user_aspects == []
        assert state.framework_aspects == []


class TestDialogueIntentStateMergeFromAnalysis:
    def test_merge_topic_from_domain_context(self):
        state = DialogueIntentState()
        mock_result = type("MockResult", (), {
            "domain_context": {"topic": "新能源", "aspects": ["市场规模"]},
            "hidden_requirements": ["政策环境"],
            "clarification_questions": ["范围?"],
            "needs_clarification": False,
            "complexity": type("C", (), {"value": "single"})(),
            "is_composite": False,
        })()
        state.merge_from_analysis(mock_result)
        assert state.topic_hint == "新能源"
        assert "市场规模" in state.confirmed_aspects
        assert "市场规模" in state.user_aspects
        assert "政策环境" in state.hidden_requirements
        assert state.pending_questions == ["范围?"]

    def test_merge_needs_clarification_caps_readiness(self):
        state = DialogueIntentState(
            topic_hint="test",
            confirmed_aspects=["a", "b", "c"],
            readiness_level=ReadinessLevel.SUFFICIENT,
            readiness_score=0.8,
        )
        mock_result = type("MockResult", (), {
            "domain_context": {},
            "hidden_requirements": [],
            "clarification_questions": [],
            "needs_clarification": True,
            "complexity": type("C", (), {"value": "single"})(),
            "is_composite": False,
        })()
        state.merge_from_analysis(mock_result)
        assert state.readiness_level != ReadinessLevel.SUFFICIENT

    def test_merge_composite_via_getattr(self):
        state = DialogueIntentState()
        mock_result = type("MockResult", (), {
            "domain_context": {},
            "hidden_requirements": [],
            "clarification_questions": [],
            "needs_clarification": False,
            "complexity": type("C", (), {"value": "single"})(),
            "is_composite": True,
            "sub_intents": [SubIntent(intent_id="sub_1", description="test")],
            "orchestration_strategy": "hybrid",
        })()
        state.merge_from_analysis(mock_result)
        assert state.is_composite is True
        assert len(state.sub_intents) == 1
        assert state.orchestration_strategy == "hybrid"


class TestDialogueIntentStateUpdateFromResponse:
    def test_enter_framework_sets_sufficient(self):
        state = DialogueIntentState(topic_hint="test")
        conv_result = {"action": "enter_framework", "framework_sections": ["市场分析", "竞争格局"]}
        state.update_from_response(conv_result, "确认")
        assert "市场分析" in state.framework_aspects
        assert state.research_turns == 1
        assert state.readiness_score >= 0.7

    def test_identified_aspects_tracked(self):
        state = DialogueIntentState()
        conv_result = {"action": "continue_chat", "identified_aspects": ["技术路线", "政策"]}
        state.update_from_response(conv_result, "用户输入")
        assert "技术路线" in state.user_aspects
        assert "技术路线" in state.confirmed_aspects

    def test_clarification_questions_increment(self):
        state = DialogueIntentState()
        conv_result = {"action": "continue_chat", "clarification_questions": ["范围?"]}
        state.update_from_response(conv_result, "用户输入")
        assert state.clarification_count == 1
        assert state.pending_questions == ["范围?"]


class TestDialogueIntentStateReadiness:
    def test_readiness_sufficient_threshold(self):
        state = DialogueIntentState(topic_hint="test", confirmed_aspects=["a", "b", "c"], clarification_count=1)
        state.update_readiness()
        assert state.readiness_score >= 0.7
        assert state.readiness_level == ReadinessLevel.SUFFICIENT

    def test_readiness_partial_threshold(self):
        state = DialogueIntentState(topic_hint="test", confirmed_aspects=["a", "b"])
        state.update_readiness()
        assert state.readiness_score >= 0.4
        assert state.readiness_level == ReadinessLevel.PARTIAL

    def test_readiness_insufficient(self):
        state = DialogueIntentState()
        state.update_readiness()
        assert state.readiness_level == ReadinessLevel.INSUFFICIENT
        assert state.readiness_score == 0.0


class TestDialogueIntentStateSerialization:
    def test_round_trip(self):
        state = DialogueIntentState(
            topic_hint="储能市场",
            confirmed_aspects=["市场规模", "竞争格局"],
            user_aspects=["市场规模"],
            framework_aspects=["竞争格局"],
            readiness_level=ReadinessLevel.SUFFICIENT,
            readiness_score=0.75,
            is_composite=True,
            sub_intents=[SubIntent(intent_id="sub_1", description="储能市场研究")],
            clarification_count=2,
            research_turns=3,
        )
        d = state.to_dict()
        restored = DialogueIntentState.from_dict(d)
        assert restored.topic_hint == "储能市场"
        assert restored.confirmed_aspects == ["市场规模", "竞争格局"]
        assert restored.readiness_level == ReadinessLevel.SUFFICIENT
        assert restored.is_composite is True
        assert len(restored.sub_intents) == 1
        assert restored.clarification_count == 2
        assert restored.research_turns == 3

    def test_from_dict_default_values(self):
        restored = DialogueIntentState.from_dict({})
        assert restored.topic_hint == ""
        assert restored.readiness_level == ReadinessLevel.INSUFFICIENT


class TestClearFrameworkAspects:
    def test_clear_resets_framework(self):
        state = DialogueIntentState(
            topic_hint="test",
            confirmed_aspects=["a", "b"],
            user_aspects=["a"],
            framework_aspects=["b"],
            hidden_requirements=["req"],
            readiness_level=ReadinessLevel.SUFFICIENT,
            readiness_score=0.8,
            is_composite=True,
            sub_intents=[SubIntent(intent_id="sub_1", description="x")],
        )
        state.clear_framework_aspects()
        assert state.framework_aspects == []
        assert state.confirmed_aspects == ["a"]
        assert state.hidden_requirements == []
        assert state.readiness_level == ReadinessLevel.INSUFFICIENT
        assert state.is_composite is False
        assert state.sub_intents == []