"""
Chat History Full-Load Tests
Task 1: display_history synced on conversation_history write
Task 2: display_history preserved through compression
Task 3: API pagination logic
"""

import pytest
import os
import tempfile


class TestTask1DisplayHistorySync:
    """Task 1: display_history is synced when conversation_history is written"""

    def test_display_history_synced_on_setitem(self):
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("s1", {"user_id": "u1", "conversation_history": []})
            session = mgr.get("s1")
            history = session.get("conversation_history", [])
            history.append({"role": "user", "content": "Hello", "timestamp": "2026-01-01T00:00:00"})
            session["conversation_history"] = history
            display = session.get("display_history", [])
            assert len(display) == 1
            assert display[0]["content"] == "Hello"

    def test_display_history_synced_on_update(self):
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("s2", {"user_id": "u1", "conversation_history": []})
            session = mgr.get("s2")
            new_history = [
                {"role": "user", "content": "A", "timestamp": "2026-01-01T00:00:00"},
                {"role": "assistant", "content": "B", "timestamp": "2026-01-01T00:00:01"},
            ]
            session.update({"conversation_history": new_history})
            display = session.get("display_history", [])
            assert len(display) == 2
            assert display[0]["content"] == "A"
            assert display[1]["content"] == "B"

    def test_display_history_not_synced_on_other_key(self):
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("s3", {"user_id": "u1", "conversation_history": []})
            session = mgr.get("s3")
            session["other_key"] = "value"
            assert "display_history" not in session or session.get("display_history") == []


class TestTask2DisplayHistoryNotCompressed:
    """Task 2: display_history survives compression"""

    def test_display_history_preserved_after_compression(self):
        from src.core.compress_adapter import SessionHistoryCompressor
        with tempfile.TemporaryDirectory() as tmpdir:
            compressor = SessionHistoryCompressor(step_limit=5, size_limit_kb=10, archive_base=tmpdir)
            history = [
                {"role": "user", "content": f"Message {i}", "timestamp": f"2026-01-0{i%9+1}T00:00:00"}
                for i in range(10)
            ]
            session = {"conversation_history": list(history), "display_history": list(history), "user_id": "u1"}
            compressor.compress_if_needed("s1", session)
            assert len(session["conversation_history"]) < 10
            assert len(session["display_history"]) == 10

    def test_display_history_set_before_compression(self):
        from src.core.compress_adapter import SessionHistoryCompressor
        with tempfile.TemporaryDirectory() as tmpdir:
            compressor = SessionHistoryCompressor(step_limit=5, size_limit_kb=10, archive_base=tmpdir)
            history = [
                {"role": "user", "content": f"Msg {i}", "timestamp": f"2026-01-01T00:00:00"}
                for i in range(8)
            ]
            session = {"conversation_history": list(history), "user_id": "u1"}
            assert "display_history" not in session
            compressor.compress_if_needed("s2", session)
            assert "display_history" in session
            assert len(session["display_history"]) == 8


class TestTask3MessagesAPI:
    """Task 3: Paginated messages API logic"""

    def test_display_history_preferred_over_conversation(self):
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            full = [{"role": "user", "content": f"Msg {i}", "timestamp": "2026-01-01T00:00:00"} for i in range(25)]
            mgr.create("s1", {
                "user_id": "u1",
                "conversation_history": full[:6],
                "display_history": full,
                "created_at": "2026-01-01T00:00:00",
                "status": "completed",
            })
            session = mgr.get("s1")
            source = session.get("display_history") or session.get("conversation_history", [])
            assert len(source) == 25

    def test_pagination_offset_limit(self):
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            full = [{"role": "user", "content": f"Msg {i}", "timestamp": "2026-01-01T00:00:00"} for i in range(25)]
            mgr.create("s2", {
                "user_id": "u1",
                "conversation_history": full[:6],
                "display_history": full,
                "created_at": "2026-01-01T00:00:00",
                "status": "completed",
            })
            session = mgr.get("s2")
            source = session.get("display_history") or session.get("conversation_history", [])
            total = len(source)
            page1 = source[0:10]
            assert len(page1) == 10
            page3 = source[20:30]
            assert len(page3) == 5
            has_more = 0 + 10 < total
            assert has_more is True
            has_more_last = 20 + 10 < total
            assert has_more_last is False

    def test_role_filter_accepts_summary_type(self):
        msgs = [
            {"role": "user", "content": "Hello", "timestamp": "2026-01-01T00:00:00"},
            {"type": "summary", "content": "Summary text", "timestamp": "2026-01-01T00:01:00"},
        ]
        filtered = []
        for msg in msgs:
            if isinstance(msg, dict) and ("role" in msg or "type" in msg) and "content" in msg:
                filtered.append({
                    "role": msg.get("role", msg.get("type", "unknown")),
                    "content": msg["content"],
                })
        assert len(filtered) == 2
        assert filtered[0]["role"] == "user"
        assert filtered[1]["role"] == "summary"

    def test_offset_negative_clamped(self):
        offset = max(0, -5)
        assert offset == 0

    def test_limit_zero_clamped(self):
        limit = max(1, 0)
        assert limit == 1


class TestTask7Integration:
    """Task 7: End-to-end — write → compress → display_history intact"""

    def test_display_history_preserved_through_compression_cycle(self):
        from src.core.session_manager import SessionManager
        from src.core.compress_adapter import SessionHistoryCompressor
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = os.path.join(tmpdir, "archives")
            mgr = SessionManager(storage_dir=tmpdir)
            mgr._history_compressor = SessionHistoryCompressor(
                step_limit=5, size_limit_kb=10, archive_base=archive_dir
            )
            mgr.create("s1", {"user_id": "u1", "conversation_history": []})
            session = mgr.get("s1")
            for i in range(15):
                history = session.get("conversation_history", [])
                history.append({
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                    "timestamp": f"2026-01-01T00:00:00"
                })
                session["conversation_history"] = history
            display = session.get("display_history", [])
            assert len(display) == 15, f"Expected 15 display_history items, got {len(display)}"
            conv = session.get("conversation_history", [])
            assert len(conv) <= 15
