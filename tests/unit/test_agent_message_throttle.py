import pytest
import time
from unittest.mock import patch, MagicMock


class TestAgentMessageThrottle:
    def test_non_heartbeat_throttled_within_window(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._last_agent_msg_times.clear()
        with patch.object(SessionStreamer, '_notify_subscribers'), \
             patch.object(SessionStreamer, '_persist_event'):
            SessionStreamer.push_agent_message("ses_test", {
                "agent_id": "a1", "agent_name": "A", "action": "analyzing", "content": "first"
            })
            SessionStreamer.push_agent_message("ses_test", {
                "agent_id": "a2", "agent_name": "B", "action": "analyzing", "content": "second"
            })
            assert SessionStreamer._notify_subscribers.call_count == 1
        SessionStreamer._last_agent_msg_times.clear()

    def test_non_heartbeat_passes_after_window(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._last_agent_msg_times.clear()
        with patch.object(SessionStreamer, '_notify_subscribers'), \
             patch.object(SessionStreamer, '_persist_event'):
            SessionStreamer.push_agent_message("ses_test", {
                "agent_id": "a1", "agent_name": "A", "action": "analyzing", "content": "first"
            })
            SessionStreamer._last_agent_msg_times["ses_test"] = time.monotonic() - 1.0
            SessionStreamer.push_agent_message("ses_test", {
                "agent_id": "a2", "agent_name": "B", "action": "analyzing", "content": "second"
            })
            assert SessionStreamer._notify_subscribers.call_count == 2
        SessionStreamer._last_agent_msg_times.clear()

    def test_heartbeat_never_throttled(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._last_agent_msg_times.clear()
        with patch.object(SessionStreamer, '_notify_subscribers'), \
             patch.object(SessionStreamer, '_persist_event'):
            SessionStreamer.push_agent_message("ses_test", {
                "agent_id": "system", "agent_name": "System", "action": "heartbeat", "content": "1"
            })
            SessionStreamer.push_agent_message("ses_test", {
                "agent_id": "system", "agent_name": "System", "action": "heartbeat", "content": "2"
            })
            assert SessionStreamer._notify_subscribers.call_count == 2
        SessionStreamer._last_agent_msg_times.clear()
