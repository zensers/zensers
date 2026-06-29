"""
Tests for _recover_results_from_sessions in orchestrator.py
"""
import pytest
from unittest.mock import MagicMock
from src.core.agents.agent_session import AgentSessionStatus


def _make_session(sid, agent_id, status, result=None, context=None):
    session = MagicMock()
    session.session_id = sid
    session.agent_id = agent_id
    session.status = status
    session.result = result
    session.context = context or {}
    return session


class TestRecoverResultsFromSessions:
    def _get_method(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        return ResearchOrchestrator._recover_results_from_sessions

    def test_no_registry(self):
        method = self._get_method()
        orchestrator = MagicMock()
        result = method(orchestrator, "task_1", None)
        assert result == []

    def test_registry_no_child_sessions_attr(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock(spec=[])
        result = method(orchestrator, "task_1", registry)
        assert result == []

    def test_recover_cancelled_with_result(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = _make_session(
            "s1", "phase_1_agent_0",
            AgentSessionStatus.CANCELLED,
            result={"content": "营收数据", "data_points": []},
            context={"section_id": "section_0_营收构成分析"},
        )
        registry.child_sessions = {"s1": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 1
        assert results[0]["agent_id"] == "phase_1_agent_0"
        assert results[0]["_recovered"] is True
        assert results[0]["section_id"] == "section_0_营收构成分析"

    def test_recover_failed_with_result(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = _make_session(
            "s2", "phase_1_agent_1",
            AgentSessionStatus.FAILED,
            result={"content": "利润数据"},
            context={},
        )
        registry.child_sessions = {"s2": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 1
        assert results[0]["_recovered"] is True

    def test_skip_completed(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = _make_session(
            "s3", "phase_1_agent_2",
            AgentSessionStatus.COMPLETED,
            result={"content": "completed data"},
        )
        registry.child_sessions = {"s3": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 0

    def test_skip_cancelled_no_result(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = _make_session(
            "s4", "phase_1_agent_3",
            AgentSessionStatus.CANCELLED,
            result=None,
        )
        registry.child_sessions = {"s4": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 0

    def test_string_result_converted(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        session = _make_session(
            "s5", "phase_1_agent_4",
            AgentSessionStatus.CANCELLED,
            result="plain text result",
        )
        registry.child_sessions = {"s5": session}
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 1
        assert results[0]["content"] == "plain text result"
        assert results[0]["_recovered"] is True

    def test_mixed_sessions(self):
        method = self._get_method()
        orchestrator = MagicMock()
        registry = MagicMock()
        sessions = {
            "s1": _make_session("s1", "a0", AgentSessionStatus.CANCELLED, result={"content": "data1"}),
            "s2": _make_session("s2", "a1", AgentSessionStatus.COMPLETED, result={"content": "data2"}),
            "s3": _make_session("s3", "a2", AgentSessionStatus.FAILED, result={"content": "data3"}),
            "s4": _make_session("s4", "a3", AgentSessionStatus.CANCELLED, result=None),
        }
        registry.child_sessions = sessions
        results = method(orchestrator, "task_1", registry)
        assert len(results) == 2
        agent_ids = {r["agent_id"] for r in results}
        assert agent_ids == {"a0", "a2"}
