import pytest
from unittest.mock import patch, MagicMock


class TestFixedAgentReportProgress:
    def test_report_progress_no_session_id(self):
        from src.agents.fixed_agents.base_fixed_agent import FixedAgent
        agent = _StubFixedAgent(agent_id="test", name="Test")
        assert not hasattr(agent, '_current_session_id')
        agent._report_progress("test message")

    def test_report_progress_with_session_id(self):
        from src.agents.fixed_agents.base_fixed_agent import FixedAgent
        agent = _StubFixedAgent(agent_id="q1", name="Quality Checker")
        agent._current_session_id = "ses_123"
        with patch("src.core.session_streamer.SessionStreamer") as mock_ss:
            agent._report_progress("Checking quality...", "analyzing")
            mock_ss.push_agent_message.assert_called_once_with("ses_123", {
                "agent_id": "q1",
                "agent_name": "Quality Checker",
                "action": "analyzing",
                "content": "Checking quality...",
            })

    def test_report_progress_uses_name(self):
        from src.agents.fixed_agents.base_fixed_agent import FixedAgent
        agent = _StubFixedAgent(agent_id="q2", name="Report Generator")
        agent._current_session_id = "ses_456"
        with patch("src.core.session_streamer.SessionStreamer") as mock_ss:
            agent._report_progress("Generating...", "writing")
            call_args = mock_ss.push_agent_message.call_args[0][1]
            assert call_args["agent_name"] == "Report Generator"

    def test_report_progress_exception_swallowed(self):
        from src.agents.fixed_agents.base_fixed_agent import FixedAgent
        agent = _StubFixedAgent(agent_id="q3", name="Q")
        agent._current_session_id = "ses_789"
        with patch("src.core.session_streamer.SessionStreamer") as mock_ss:
            mock_ss.push_agent_message.side_effect = RuntimeError("boom")
            agent._report_progress("should not crash")


class _StubFixedAgent:
    from src.agents.fixed_agents.base_fixed_agent import FixedAgent

    def __init__(self, **kwargs):
        self.agent_id = kwargs.get("agent_id", "stub")
        self.name = kwargs.get("name", "Stub")
        self.agent_type = "fixed"
        self.config = kwargs.get("config", {})

    def _report_progress(self, message, action="analyzing"):
        from src.agents.fixed_agents.base_fixed_agent import FixedAgent
        FixedAgent._report_progress(self, message, action)
