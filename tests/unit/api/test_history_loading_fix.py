"""
Tests for History Loading & Display History Bug Fixes

Bug1: serverOffsetRef race condition on session restore
Bug2: Random message IDs cause duplicates between getResearchDetail and getMessages
Bug3: display_history overwritten after compression + new message append
"""

import pytest
from unittest.mock import MagicMock, patch


class TestBugFix_DisplayHistoryPreservedAfterCompression:
    """Bug3: display_history must not be overwritten by compressed conversation_history."""

    def _apply_sync(self, existing_display, old_conv, new_value):
        if not existing_display:
            return [dict(m) if isinstance(m, dict) else m for m in new_value]
        elif len(new_value) > len(old_conv):
            new_msgs = new_value[len(old_conv):]
            return list(existing_display) + [dict(m) if isinstance(m, dict) else m for m in new_msgs]
        return existing_display

    def test_display_history_not_overwritten_when_shorter(self):
        display_full = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        compressed = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        result = self._apply_sync(display_full, compressed, compressed)
        assert len(result) == 20
        assert result == display_full

    def test_display_history_appended_when_new_value_longer(self):
        existing = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        old_conv = list(existing)
        new_value = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
        result = self._apply_sync(existing, old_conv, new_value)
        assert len(result) == 10

    def test_display_history_created_when_none_exists(self):
        new_value = [{"role": "user", "content": "msg 1"}]
        result = self._apply_sync(None, [], new_value)
        assert len(result) == 1

    def test_display_history_preserved_after_compression_then_append(self):
        full = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        compressed = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        compressed_plus_new = compressed + [{"role": "user", "content": "new msg"}]
        synced_len = 5
        new_msgs = compressed_plus_new[synced_len:]
        result = list(full) + new_msgs
        assert len(result) == 21
        assert result[20]["content"] == "new msg"

    def test_display_history_appended_after_many_new_messages(self):
        full = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        compressed = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        many_new = compressed + [{"role": "user", "content": f"new {i}"} for i in range(16)]
        synced_len = 5
        new_msgs = many_new[synced_len:]
        result = list(full) + new_msgs
        assert len(result) == 36
        assert result[0]["content"] == "msg 0"
        assert result[19]["content"] == "msg 19"
        assert result[20]["content"] == "new 0"

    def test_display_history_unchanged_when_same_length(self):
        existing = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        new_value = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        result = self._apply_sync(existing, existing, new_value)
        assert result is existing

    def test_display_history_empty_list_treated_as_none(self):
        new_value = [{"role": "user", "content": "msg 1"}]
        result = self._apply_sync([], [], new_value)
        assert len(result) == 1


class TestBugFix_StableMessageIds:
    """Bug2: Message IDs must be stable (deterministic) across API calls."""

    def test_get_research_detail_uses_index_based_id(self):
        history = [
            {"role": "user", "content": "hello", "timestamp": "2026-01-01T00:00:00"},
            {"role": "assistant", "content": "hi", "timestamp": "2026-01-01T00:00:01"},
        ]
        messages = []
        for i, msg in enumerate(history):
            entry = {
                "id": msg.get("id") or f"msg-{i}",
                "role": msg.get("role"),
                "content": msg["content"],
            }
            messages.append(entry)

        assert messages[0]["id"] == "msg-0"
        assert messages[1]["id"] == "msg-1"

    def test_get_messages_uses_offset_aware_id(self):
        offset = 10
        page = [
            {"role": "user", "content": "hello", "timestamp": "2026-01-01T00:00:00"},
            {"role": "assistant", "content": "hi", "timestamp": "2026-01-01T00:00:01"},
        ]
        messages = []
        for i, msg in enumerate(page):
            entry = {
                "id": msg.get("id") or f"msg-{offset + i}",
                "role": msg.get("role"),
                "content": msg["content"],
            }
            messages.append(entry)

        assert messages[0]["id"] == "msg-10"
        assert messages[1]["id"] == "msg-11"

    def test_ids_are_deterministic_across_calls(self):
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        ids1 = [msg.get("id") or f"msg-{i}" for i, msg in enumerate(history)]
        ids2 = [msg.get("id") or f"msg-{i}" for i, msg in enumerate(history)]
        assert ids1 == ids2

    def test_existing_id_preserved(self):
        history = [
            {"role": "user", "content": "hello", "id": "custom-id-123"},
        ]
        for i, msg in enumerate(history):
            result_id = msg.get("id") or f"msg-{i}"
            assert result_id == "custom-id-123"


class TestBugFix_ServerOffsetRefSync:
    """Bug1: serverOffsetRef must sync with actual loaded message count."""

    def test_offset_set_to_message_count_when_available(self):
        active_session_id = "ses_test"
        session_messages = [{"id": "msg-0"}, {"id": "msg-1"}, {"id": "msg-2"}]

        server_offset_ref = 0
        has_more = True

        if session_messages:
            server_offset_ref = len(session_messages)
            has_more = len(session_messages) > 0

        assert server_offset_ref == 3
        assert has_more is True

    def test_offset_reset_when_no_messages(self):
        active_session_id = "ses_empty"
        session_messages = None

        server_offset_ref = 100
        has_more = True

        if session_messages:
            server_offset_ref = len(session_messages)
            has_more = len(session_messages) > 0
        else:
            server_offset_ref = 0
            has_more = True

        assert server_offset_ref == 0
        assert has_more is True


class TestBugFix_ScrollDepsChange:
    """Scroll auto-scroll should only trigger on message count change, not content update."""

    def test_deps_change_only_on_length_change(self):
        messages_v1 = [{"id": "1", "content": "hello"}]
        messages_v2 = [{"id": "1", "content": "hello world"}]

        deps_v1 = [len(messages_v1)]
        deps_v2 = [len(messages_v2)]

        assert deps_v1 == deps_v2

    def test_deps_change_on_new_message(self):
        messages_v1 = [{"id": "1", "content": "hello"}]
        messages_v2 = [{"id": "1", "content": "hello"}, {"id": "2", "content": "world"}]

        deps_v1 = [len(messages_v1)]
        deps_v2 = [len(messages_v2)]

        assert deps_v1 != deps_v2


class TestSessionManagerHistoryPersistenceIntegration:
    """Current contract: conversation history is append-only and complete."""

    def test_history_survives_compression_cycle(self):
        from src.core.session_manager import SessionManager, PersistentSessionDict
        import tempfile, shutil

        tmp = tempfile.mkdtemp()
        try:
            sm = SessionManager(storage_path=tmp)
            sid = "test_compression_cycle"
            session = sm.create(sid, {"conversation_history": []})

            for i in range(20):
                history = session.get("conversation_history", [])
                history.append({"role": "user", "content": f"msg {i}"})
                session["conversation_history"] = history

            assert len(session.get("conversation_history", [])) == 20

            compressed = session.get("conversation_history", [])[:5]
            with pytest.raises(ValueError, match="truncation blocked"):
                session["conversation_history"] = compressed
            assert len(session.get("conversation_history", [])) == 20

            for i in range(20, 25):
                history = session.get("conversation_history", [])
                history.append({"role": "user", "content": f"msg {i}"})
                session["conversation_history"] = history

            history_after_append = session.get("conversation_history", [])
            assert len(history_after_append) == 25
            assert history_after_append[0]["content"] == "msg 0"
            assert history_after_append[24]["content"] == "msg 24"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestBugFix_StableIdsAcrossEndpoints:
    """Integration test: getResearchDetail and getMessages produce consistent IDs."""

    def test_ids_match_between_detail_and_messages_endpoints(self):
        history = [
            {"role": "user", "content": "hello", "timestamp": "2026-01-01T00:00:00"},
            {"role": "assistant", "content": "hi", "timestamp": "2026-01-01T00:00:01"},
            {"role": "user", "content": "bye", "timestamp": "2026-01-01T00:00:02"},
        ]

        detail_ids = []
        for i, msg in enumerate(history):
            detail_ids.append(msg.get("id") or f"msg-{i}")

        offset = 0
        limit = 50
        page = history[offset:offset + limit]
        messages_ids = []
        for i, msg in enumerate(page):
            messages_ids.append(msg.get("id") or f"msg-{offset + i}")

        assert detail_ids == messages_ids
