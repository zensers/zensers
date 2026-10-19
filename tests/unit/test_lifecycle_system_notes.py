# -*- coding: utf-8 -*-
"""Regression: lifecycle system notes persist into conversation_history.

Root cause this guards against:
- ProgressHeartbeat pushed action=heartbeat agent_messages every 15s and
  _persist_event wrote them into conversation_history AND recent_events.
  The 200-slot recent_events buffer evicted every REAL agent message, and
  the paginated history endpoint returned walls of identical heartbeats —
  the user could no longer see what was happening.
- Task lifecycle changes (paused/cancelled/resumed) were only shown in a
  top status bar, not in the conversation timeline.
"""
import asyncio
import uuid

import pytest


@pytest.fixture
def sm():
    from src.core.session_manager import SessionManager
    return SessionManager.get_instance()


@pytest.fixture
def session_id(sm):
    sid = f"zz-test-system-note-{uuid.uuid4().hex[:8]}"
    sm.create(sid, {"user_id": "u1", "conversation_history": [], "recent_events": []})
    yield sid
    try:
        sm.delete(sid)
    except Exception:
        pass


class TestHeartbeatNotPersisted:
    def test_heartbeat_not_in_conversation_history(self, sm, session_id):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer.push_agent_message(session_id, {
            "agent_id": "system", "agent_name": "System",
            "action": "heartbeat",
            "content": "Research in progress... (80% complete)",
        })
        history = sm.get(session_id).get("conversation_history", [])
        assert not any(
            m.get("role") == "agent" and m.get("action") == "heartbeat" for m in history
        ), "heartbeats must never enter conversation_history"

    def test_heartbeat_not_in_recent_events(self, sm, session_id):
        from src.core.session_streamer import SessionStreamer

        received = []

        async def _drain():
            streamer = SessionStreamer(session_id)
            streamer.subscribe()
            SessionStreamer.push_agent_message(session_id, {
                "agent_id": "system", "agent_name": "System",
                "action": "heartbeat", "content": "hb",
            })
            received.append(await asyncio.wait_for(streamer._queue.get(), timeout=2))
            streamer.unsubscribe()

        asyncio.run(_drain())

        # Live SSE delivery still works (keep-alive contract preserved).
        assert received and received[0].data.get("action") == "heartbeat"

        events = sm.get(session_id).get("recent_events", [])
        assert not any(
            e.get("event") == "agent_message" and isinstance(e.get("data"), dict)
            and e["data"].get("action") == "heartbeat" for e in events
        ), "heartbeats must not occupy recent_events slots"

    def test_real_agent_message_still_persists(self, sm, session_id):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer.push_agent_message(session_id, {
            "agent_id": "web_search", "agent_name": "Web Search",
            "action": "completed", "content": "Completed: web_search",
        })
        history = sm.get(session_id).get("conversation_history", [])
        assert any(m.get("agent_id") == "web_search" for m in history)


class TestSystemNotePersistence:
    def test_system_note_persists_with_system_role(self, sm, session_id):
        from src.core.session_streamer import SessionStreamer
        content = "⏸️ 研究已暂停。已采集的数据与检查点已保留。"
        SessionStreamer.push_system_note(session_id, content)
        history = sm.get(session_id).get("conversation_history", [])
        note = next(m for m in history if m.get("_type") == "system_note")
        assert note["role"] == "system"
        assert note["content"] == content

    def test_system_note_dedupes_consecutive_identical(self, sm, session_id):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer.push_system_note(session_id, "same note")
        SessionStreamer.push_system_note(session_id, "same note")
        history = sm.get(session_id).get("conversation_history", [])
        notes = [m for m in history if m.get("_type") == "system_note" and m["content"] == "same note"]
        assert len(notes) == 1

    def test_system_note_live_delivery(self, sm, session_id):
        from src.core.session_streamer import SessionStreamer
        received = []

        async def _drain():
            streamer = SessionStreamer(session_id)
            streamer.subscribe()
            SessionStreamer.push_system_note(session_id, "▶️ 研究已恢复。")
            received.append(await asyncio.wait_for(streamer._queue.get(), timeout=2))
            streamer.unsubscribe()

        asyncio.run(_drain())
        assert received and received[0].data.get("action") == "system_status"

    def test_system_note_not_in_recent_events(self, sm, session_id):
        from src.core.session_streamer import SessionStreamer
        SessionStreamer.push_system_note(session_id, "note X")
        events = sm.get(session_id).get("recent_events", [])
        assert not any(e.get("event") == "chat_response" or e.get("event") == "agent_message"
                       for e in events)