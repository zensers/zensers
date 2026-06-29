"""Test: push_chat_token() and CHAT_TOKEN SSE event"""

import asyncio
import pytest


class TestChatTokenEnum:
    """CHAT_TOKEN enum value must exist on SessionSSEEventType."""

    def test_chat_token_enum_exists(self):
        from src.core.session_streamer import SessionSSEEventType
        assert hasattr(SessionSSEEventType, 'CHAT_TOKEN')
        assert SessionSSEEventType.CHAT_TOKEN.value == "chat_token"


class TestPushChatTokenDelivery:
    """push_chat_token must deliver tokens to active subscribers."""

    @pytest.mark.asyncio
    async def test_subscriber_receives_token(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        streamer = SessionStreamer("ses_token_1")
        streamer.subscribe()

        SessionStreamer.push_chat_token("ses_token_1", "Hel")
        SessionStreamer.push_chat_token("ses_token_1", "lo")

        msg1 = await asyncio.wait_for(streamer._queue.get(), timeout=2)
        assert msg1.event == "chat_token"
        assert msg1.data["token"] == "Hel"

        msg2 = await asyncio.wait_for(streamer._queue.get(), timeout=2)
        assert msg2.event == "chat_token"
        assert msg2.data["token"] == "lo"

        streamer.unsubscribe()

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        s1 = SessionStreamer("ses_token_2")
        s2 = SessionStreamer("ses_token_2")
        s1.subscribe()
        s2.subscribe()

        SessionStreamer.push_chat_token("ses_token_2", "test")

        msg1 = await asyncio.wait_for(s1._queue.get(), timeout=2)
        msg2 = await asyncio.wait_for(s2._queue.get(), timeout=2)
        assert msg1.data["token"] == "test"
        assert msg2.data["token"] == "test"

        s1.unsubscribe()
        s2.unsubscribe()

    @pytest.mark.asyncio
    async def test_no_subscribers_no_error(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        SessionStreamer.push_chat_token("ses_nonexistent", "data")
        # Should not raise


class TestPushChatTokenNoBuffer:
    """push_chat_token must NOT add to _recent_messages."""

    def test_token_not_in_recent_messages(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        SessionStreamer.push_chat_token("ses_nobuf", "token1")
        recent = SessionStreamer._recent_messages.get("ses_nobuf", [])
        assert len(recent) == 0

    def test_chat_response_still_buffered(self):
        """Sanity check: push_chat_response still uses _notify_subscribers."""
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        import tempfile
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("ses_buf_check", {"user_id": "u1"})

            SessionStreamer.push_chat_response("ses_buf_check", {
                "message": "hello", "action": "continue_chat",
            })
            recent = SessionStreamer._recent_messages.get("ses_buf_check", [])
            assert len(recent) >= 1
            assert recent[-1].event == "chat_response"

    def test_tokens_dont_push_out_chat_responses(self):
        """Verifying that push_chat_token bypasses _recent_messages (not _notify_subscribers)."""
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        import tempfile
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("ses_mix", {"user_id": "u1"})
            SessionStreamer.push_chat_response("ses_mix", {
                "message": "resp1", "action": "continue_chat",
            })
            for ch in "abcde":
                SessionStreamer.push_chat_token("ses_mix", ch)
            recent = SessionStreamer._recent_messages.get("ses_mix", [])
            assert all(m.event != "chat_token" for m in recent)
            assert any(m.event == "chat_response" for m in recent)


class TestPushChatTokenNoPersist:
    """push_chat_token must NOT persist to conversation_history."""

    def test_token_not_in_conversation_history(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        import tempfile
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("ses_nopersist", {"user_id": "u1", "conversation_history": []})
            SessionStreamer.push_chat_token("ses_nopersist", "secret")
            session = mgr.get("ses_nopersist")
            history = session.get("conversation_history", [])
            assert len(history) == 0
