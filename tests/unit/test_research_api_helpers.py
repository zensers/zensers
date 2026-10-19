# -*- coding: utf-8 -*-
"""
ResearchAPI 辅助方法单元测试
"""

import pytest
from unittest.mock import MagicMock, patch
from src.core.dialogue.state_machine import ConversationState, ConversationStateMachine
from src.core.dialogue.sub_intent import ReadinessLevel
from src.core.dialogue.dialogue_intent_state import DialogueIntentState


class TestMergeSectionsDedup:
    def _make_api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    def test_exact_duplicate_removed(self):
        api = self._make_api()
        result = api._merge_sections_dedup(["市场规模", "竞争格局"], ["市场规模"])
        assert result == ["市场规模", "竞争格局"]

    def test_substring_keeps_longer(self):
        api = self._make_api()
        result = api._merge_sections_dedup(["市场规模分析"], ["市场规模"])
        assert result == ["市场规模分析"]

    def test_semantic_overlap_065(self):
        api = self._make_api()
        result = api._merge_sections_dedup(
            ["市场规模、竞争格局与发展趋势分析"],
            ["市场规模、竞争格局与发展趋势研究"]
        )
        assert len(result) == 1

    def test_no_overlap_appends(self):
        api = self._make_api()
        result = api._merge_sections_dedup(["市场规模"], ["竞争格局"])
        assert result == ["市场规模", "竞争格局"]

    def test_different_semantics_not_merged(self):
        api = self._make_api()
        result = api._merge_sections_dedup(["市场分析"], ["竞争分析"])
        assert len(result) == 2


class TestActionAlignsWithState:
    def _make_api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    def test_continue_chat_aligns_with_understanding(self):
        api = self._make_api()
        assert api._action_aligns_with_state("continue_chat", ConversationState.UNDERSTANDING) is True

    def test_enter_framework_aligns_with_framework_confirm(self):
        api = self._make_api()
        assert api._action_aligns_with_state("enter_framework", ConversationState.FRAMEWORK_CONFIRM) is True

    def test_continue_chat_not_aligned_with_framework_confirm(self):
        api = self._make_api()
        assert api._action_aligns_with_state("continue_chat", ConversationState.FRAMEWORK_CONFIRM) is False

    def test_unknown_state_returns_false(self):
        api = self._make_api()
        assert api._action_aligns_with_state("continue_chat", ConversationState.COMPLETED) is False


class TestSyncModeWithState:
    def _make_api(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        return api

    def test_understanding_sets_chat(self):
        api = self._make_api()
        session = {"mode": "research"}
        api._sync_mode_with_state(session, ConversationStateMachine())
        assert session["mode"] == "chat"

    def test_framework_confirm_sets_framework(self):
        api = self._make_api()
        m = ConversationStateMachine()
        m.transition(ConversationState.FRAMEWORK_CONFIRM)
        session = {"mode": "chat"}
        api._sync_mode_with_state(session, m)
        assert session["mode"] == "framework"

    def test_executing_sets_research(self):
        api = self._make_api()
        m = ConversationStateMachine()
        m.transition(ConversationState.EXECUTING)
        session = {"mode": "chat"}
        api._sync_mode_with_state(session, m)
        assert session["mode"] == "research"

    def test_completed_sets_chat(self):
        api = self._make_api()
        m = ConversationStateMachine()
        m.force_set_state(ConversationState.COMPLETED)
        session = {"mode": "research"}
        api._sync_mode_with_state(session, m)
        assert session["mode"] == "chat"