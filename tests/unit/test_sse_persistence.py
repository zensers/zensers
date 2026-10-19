"""Test: SSE chat_response/agent_message persist to conversation_history"""

import pytest


class TestSSEPersistsToConversationHistory:
    """Verify SSE events write to conversation_history via _persist_event"""

    def test_chat_response_persists_to_history(self):
        from src.core.session_manager import SessionManager
        from src.core.session_streamer import SessionStreamer
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("sse-test-1", {"user_id": "u1", "conversation_history": []})
            session = mgr.get("sse-test-1")
            SessionStreamer._persist_event("sse-test-1", "chat_response", {
                "session_id": "sse-test-1",
                "message": "Hello from SSE",
                "timestamp": "2026-01-01T12:00:00",
            })
            history = session.get("conversation_history", [])
            assert len(history) >= 1
            assert any(m["content"] == "Hello from SSE" and m["role"] == "assistant" for m in history)

    def test_agent_message_persists_to_history(self):
        from src.core.session_manager import SessionManager
        from src.core.session_streamer import SessionStreamer
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("sse-test-2", {"user_id": "u1", "conversation_history": []})
            session = mgr.get("sse-test-2")
            SessionStreamer._persist_event("sse-test-2", "agent_message", {
                "session_id": "sse-test-2",
                "agent_id": "data_collector",
                "agent_name": "Data Collector",
                "action": "searching",
                "content": "Searching for data...",
                "timestamp": "2026-01-01T12:01:00",
            })
            history = session.get("conversation_history", [])
            assert len(history) >= 1
            assert any(m["role"] == "agent" and "Searching" in m["content"] for m in history)

    def test_non_chat_event_not_persisted_to_history(self):
        from src.core.session_manager import SessionManager
        from src.core.session_streamer import SessionStreamer
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("sse-test-3", {"user_id": "u1", "conversation_history": []})
            session = mgr.get("sse-test-3")
            SessionStreamer._persist_event("sse-test-3", "progress", {
                "session_id": "sse-test-3",
                "percent": 50,
            })
            history = session.get("conversation_history", [])
            assert len(history) == 0

    def test_agent_search_metadata_survives_persistence(self):
        from src.core.session_manager import SessionManager
        from src.core.session_streamer import SessionStreamer
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("sse-test-metadata", {"user_id": "u1", "conversation_history": []})
            session = mgr.get("sse-test-metadata")
            SessionStreamer.push_agent_message("sse-test-metadata", {
                "agent_id": "web_search",
                "agent_name": "Web Search Agent",
                "action": "completed",
                "content": "Completed: web_search",
                "provider": "anysearch",
                "quality_score": 82.5,
                "cache_hit": False,
                "stop_reason": "quality_reached",
            })
            history = session.get("conversation_history", [])
            message = next(m for m in history if m.get("agent_id") == "web_search")
            assert message["provider"] == "anysearch"
            assert message["quality_score"] == 82.5
            assert message["cache_hit"] is False
            assert message["stop_reason"] == "quality_reached"

    def test_sse_messages_use_conversation_history_as_display_source(self):
        """The current history model has one append-only display source."""
        from src.core.session_manager import SessionManager
        from src.core.session_streamer import SessionStreamer
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("sse-test-4", {"user_id": "u1", "conversation_history": []})
            session = mgr.get("sse-test-4")
            SessionStreamer._persist_event("sse-test-4", "chat_response", {
                "session_id": "sse-test-4",
                "message": "Test message",
                "timestamp": "2026-01-01T12:00:00",
            })
            assert "display_history" not in session
            history = session.get("conversation_history", [])
            assert len(history) >= 1
            assert any(m["content"] == "Test message" for m in history)
