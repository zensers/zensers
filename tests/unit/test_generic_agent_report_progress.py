"""Test: GenericAgent._report_progress pushes agent_message via SessionStreamer"""

import pytest
from unittest.mock import patch


class TestGenericAgentReportProgress:
    def test_report_progress_no_session_id(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent("test_agent_1", "research", {})
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
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent("test_agent_2", "research", {
            "context": {"aspect": "市场规模"},
        })
        agent._current_session_id = "ses_gen_1"
        collected = []

        class MockStreamer:
            @classmethod
            def push_agent_message(cls, sid, data):
                collected.append((sid, data))

        import src.core.session_streamer as ss
        original = ss.SessionStreamer.push_agent_message
        ss.SessionStreamer.push_agent_message = MockStreamer.push_agent_message
        try:
            agent._report_progress("搜索中...", "searching")
            assert len(collected) == 1
            sid, data = collected[0]
            assert sid == "ses_gen_1"
            assert data["agent_id"] == "test_agent_2"
            assert data["agent_name"] == "市场规模"
            assert data["action"] == "searching"
            assert data["content"] == "搜索中..."
        finally:
            ss.SessionStreamer.push_agent_message = original

    def test_report_progress_fallback_name_to_agent_type(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent("test_agent_3", "deep_analysis", {})
        agent._current_session_id = "ses_gen_2"
        collected = []

        class MockStreamer:
            @classmethod
            def push_agent_message(cls, sid, data):
                collected.append((sid, data))

        import src.core.session_streamer as ss
        original = ss.SessionStreamer.push_agent_message
        ss.SessionStreamer.push_agent_message = MockStreamer.push_agent_message
        try:
            agent._report_progress("分析中...", "analyzing")
            assert len(collected) == 1
            _, data = collected[0]
            assert data["agent_name"] == "deep_analysis"
        finally:
            ss.SessionStreamer.push_agent_message = original

    def test_report_progress_exception_swallowed(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent("test_agent_4", "research")
        agent._current_session_id = "ses_gen_3"

        class FailStreamer:
            @classmethod
            def push_agent_message(cls, sid, data):
                raise RuntimeError("streamer broken")

        import src.core.session_streamer as ss
        original = ss.SessionStreamer.push_agent_message
        ss.SessionStreamer.push_agent_message = FailStreamer.push_agent_message
        try:
            agent._report_progress("should not crash", "writing")
        finally:
            ss.SessionStreamer.push_agent_message = original
