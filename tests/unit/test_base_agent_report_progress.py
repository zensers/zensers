"""Test: BaseAgent._report_progress pushes agent_message via SessionStreamer"""

import pytest

from src.core.agents.base import BaseAgent


class ConcreteAgent(BaseAgent):
    async def execute(self, task):
        return {"success": True}


class TestBaseAgentReportProgress:
    def test_report_progress_no_session_id(self):
        agent = ConcreteAgent("test_agent_1", "research")
        collected = []
        class MockStreamer:
            @classmethod
            def push_agent_message(cls, sid, data):
                collected.append((sid, data))
        import src.core.session_streamer as ss
        original = ss.SessionStreamer.push_agent_message
        ss.SessionStreamer.push_agent_message = MockStreamer.push_agent_message
        try:
            agent._report_progress("test message", "analyzing")
            assert len(collected) == 0
        finally:
            ss.SessionStreamer.push_agent_message = original

    def test_report_progress_with_session_id(self):
        agent = ConcreteAgent("test_agent_2", "research", {
            "context": {"aspect": "Market Size"},
        })
        agent._current_session_id = "ses_report_1"
        collected = []
        class MockStreamer:
            @classmethod
            def push_agent_message(cls, sid, data):
                collected.append((sid, data))
        import src.core.session_streamer as ss
        original = ss.SessionStreamer.push_agent_message
        ss.SessionStreamer.push_agent_message = MockStreamer.push_agent_message
        try:
            agent._report_progress("Searching for data...", "searching")
            assert len(collected) == 1
            sid, data = collected[0]
            assert sid == "ses_report_1"
            assert data["agent_id"] == "test_agent_2"
            assert data["agent_name"] == "Market Size"
            assert data["action"] == "searching"
            assert data["content"] == "Searching for data..."
        finally:
            ss.SessionStreamer.push_agent_message = original

    def test_report_progress_fallback_name_to_agent_type(self):
        agent = ConcreteAgent("test_agent_3", "deep_analysis", {})
        agent._current_session_id = "ses_report_2"
        collected = []
        class MockStreamer:
            @classmethod
            def push_agent_message(cls, sid, data):
                collected.append((sid, data))
        import src.core.session_streamer as ss
        original = ss.SessionStreamer.push_agent_message
        ss.SessionStreamer.push_agent_message = MockStreamer.push_agent_message
        try:
            agent._report_progress("Processing...", "analyzing")
            assert len(collected) == 1
            _, data = collected[0]
            assert data["agent_name"] == "deep_analysis"
        finally:
            ss.SessionStreamer.push_agent_message = original

    def test_report_progress_exception_swallowed(self):
        agent = ConcreteAgent("test_agent_4", "research")
        agent._current_session_id = "ses_report_3"
        class FailStreamer:
            @classmethod
            def push_agent_message(cls, sid, data):
                raise RuntimeError("streamer broken")
        import src.core.session_streamer as ss
        original = ss.SessionStreamer.push_agent_message
        ss.SessionStreamer.push_agent_message = FailStreamer.push_agent_message
        try:
            agent._report_progress("Should not crash", "writing")
        finally:
            ss.SessionStreamer.push_agent_message = original
