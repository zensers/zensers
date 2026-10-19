"""Test: push_chat_thinking() and CHAT_THINKING SSE event"""

import asyncio
import pytest


class TestChatThinkingEnum:

    def test_chat_thinking_enum_exists(self):
        from src.core.session_streamer import SessionSSEEventType
        assert hasattr(SessionSSEEventType, 'CHAT_THINKING')
        assert SessionSSEEventType.CHAT_THINKING.value == "chat_thinking"


class TestPushChatThinkingDelivery:

    @pytest.mark.asyncio
    async def test_subscriber_receives_thinking(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        streamer = SessionStreamer("ses_think_1")
        streamer.subscribe()

        SessionStreamer.push_chat_thinking("ses_think_1", "Hel")
        SessionStreamer.push_chat_thinking("ses_think_1", "lo")

        msg1 = await asyncio.wait_for(streamer._queue.get(), timeout=2)
        assert msg1.event == "chat_thinking"
        assert msg1.data["token"] == "Hel"

        msg2 = await asyncio.wait_for(streamer._queue.get(), timeout=2)
        assert msg2.event == "chat_thinking"
        assert msg2.data["token"] == "lo"

        streamer.unsubscribe()

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        s1 = SessionStreamer("ses_think_2")
        s2 = SessionStreamer("ses_think_2")
        s1.subscribe()
        s2.subscribe()

        SessionStreamer.push_chat_thinking("ses_think_2", "think")

        msg1 = await asyncio.wait_for(s1._queue.get(), timeout=2)
        msg2 = await asyncio.wait_for(s2._queue.get(), timeout=2)
        assert msg1.data["token"] == "think"
        assert msg2.data["token"] == "think"

        s1.unsubscribe()
        s2.unsubscribe()

    @pytest.mark.asyncio
    async def test_no_subscribers_no_error(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        SessionStreamer.push_chat_thinking("ses_nonexistent", "data")


class TestPushChatThinkingNoBuffer:

    def test_thinking_not_in_recent_messages(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        SessionStreamer.push_chat_thinking("ses_nobuf_t", "token1")
        recent = SessionStreamer._recent_messages.get("ses_nobuf_t", [])
        assert len(recent) == 0


class TestPushChatThinkingNoPersist:

    def test_thinking_not_in_conversation_history(self):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer._subscribers.clear()
        SessionStreamer._recent_messages.clear()

        import tempfile
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("ses_nopersist_t", {"user_id": "u1", "conversation_history": []})
            SessionStreamer.push_chat_thinking("ses_nopersist_t", "secret")
            session = mgr.get("ses_nopersist_t")
            history = session.get("conversation_history", [])
            assert len(history) == 0
