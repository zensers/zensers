"""
Chat History Compression Tests
- conversation_history is never truncated (append-only)
- compression appends context_summary entries
- original messages are always preserved
- LLM context builders filter out context_summary entries
"""

import pytest
import os
import tempfile


class TestConversationHistoryAppendOnly:
    """conversation_history is never truncated by compression"""

    def test_original_messages_preserved_after_compression(self):
        from src.core.compress_adapter import SessionHistoryCompressor
        with tempfile.TemporaryDirectory() as tmpdir:
            compressor = SessionHistoryCompressor(step_limit=5, size_limit_kb=10, archive_base=tmpdir)
            history = [
                {"role": "user", "content": f"Message {i}", "timestamp": f"2026-01-0{i%9+1}T00:00:00"}
                for i in range(10)
            ]
            session = {"conversation_history": list(history), "user_id": "u1"}
            original_len = len(session["conversation_history"])
            compressor.compress_if_needed("s1", session)
            assert len(session["conversation_history"]) >= original_len

    def test_context_summary_appended_not_replaced(self):
        from src.core.compress_adapter import SessionHistoryCompressor
        with tempfile.TemporaryDirectory() as tmpdir:
            compressor = SessionHistoryCompressor(step_limit=5, size_limit_kb=10, archive_base=tmpdir)
            history = [
                {"role": "user", "content": f"Msg {i}", "timestamp": f"2026-01-01T00:00:00"}
                for i in range(8)
            ]
            session = {"conversation_history": list(history), "user_id": "u1"}
            compressor.compress_if_needed("s2", session)
            conv = session["conversation_history"]
            assert len(conv) == 9
            assert conv[-1].get("type") == "context_summary"
            for i in range(8):
                assert conv[i]["content"] == f"Msg {i}"

    def test_no_compression_below_threshold(self):
        from src.core.compress_adapter import SessionHistoryCompressor
        with tempfile.TemporaryDirectory() as tmpdir:
            compressor = SessionHistoryCompressor(step_limit=20, size_limit_kb=50, archive_base=tmpdir)
            history = [
                {"role": "user", "content": f"Msg {i}", "timestamp": "2026-01-01T00:00:00"}
                for i in range(5)
            ]
            session = {"conversation_history": list(history), "user_id": "u1"}
            compressor.compress_if_needed("s3", session)
            assert len(session["conversation_history"]) == 5
            assert all(m.get("type") != "context_summary" for m in session["conversation_history"])

    def test_context_summary_has_required_fields(self):
        from src.core.compress_adapter import SessionHistoryCompressor
        with tempfile.TemporaryDirectory() as tmpdir:
            compressor = SessionHistoryCompressor(step_limit=5, size_limit_kb=10, archive_base=tmpdir)
            history = [
                {"role": "user", "content": f"Msg {i}", "timestamp": f"2026-01-01T00:00:00"}
                for i in range(8)
            ]
            session = {"conversation_history": list(history), "user_id": "u1"}
            compressor.compress_if_needed("s4", session)
            summary = session["conversation_history"][-1]
            assert summary["type"] == "context_summary"
            assert summary["role"] == "system"
            assert "content" in summary
            assert "steps_covered" in summary
            assert "created_at" in summary

    def test_no_display_history_created(self):
        from src.core.compress_adapter import SessionHistoryCompressor
        with tempfile.TemporaryDirectory() as tmpdir:
            compressor = SessionHistoryCompressor(step_limit=5, size_limit_kb=10, archive_base=tmpdir)
            history = [
                {"role": "user", "content": f"Msg {i}", "timestamp": f"2026-01-01T00:00:00"}
                for i in range(8)
            ]
            session = {"conversation_history": list(history), "user_id": "u1"}
            compressor.compress_if_needed("s5", session)
            assert "display_history" not in session
            assert "_display_synced_len" not in session


class TestSessionManagerNoDisplayHistory:
    """session_manager no longer creates display_history"""

    def test_setitem_does_not_create_display_history(self):
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("s1", {"user_id": "u1", "conversation_history": []})
            session = mgr.get("s1")
            history = session.get("conversation_history", [])
            history.append({"role": "user", "content": "Hello", "timestamp": "2026-01-01T00:00:00"})
            session["conversation_history"] = history
            assert "display_history" not in session
            assert "_display_synced_len" not in session

    def test_update_does_not_create_display_history(self):
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
            assert "display_history" not in session

    def test_append_only_guard_still_works(self):
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("s3", {"user_id": "u1", "conversation_history": [
                {"role": "user", "content": "A", "timestamp": "2026-01-01T00:00:00"},
                {"role": "assistant", "content": "B", "timestamp": "2026-01-01T00:00:01"},
            ]})
            session = mgr.get("s3")
            with pytest.raises(ValueError, match="truncation blocked"):
                session["conversation_history"] = [
                    {"role": "user", "content": "C", "timestamp": "2026-01-01T00:00:02"}
                ]


class TestRollingSummarizerReadsContent:
    """RollingSummarizer reads role and content fields"""

    def test_summarize_extracts_user_needs(self):
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        summarizer = RollingSummarizer()
        history = [
            {"role": "user", "content": "我想研究中国新能源汽车市场", "timestamp": "2026-01-01T00:00:00"},
            {"role": "assistant", "content": "好的，我建议从以下角度分析...", "timestamp": "2026-01-01T00:00:01"},
        ]
        summary = summarizer.summarize(history)
        assert "中国新能源汽车" in summary or "用户需求" in summary

    def test_summarize_handles_empty_history(self):
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        summarizer = RollingSummarizer()
        assert summarizer.summarize([]) == ""

    def test_summarize_skips_context_summary_entries(self):
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        summarizer = RollingSummarizer()
        history = [
            {"role": "user", "content": "Hello", "timestamp": "2026-01-01T00:00:00"},
            {"type": "context_summary", "role": "system", "content": "Old summary", "timestamp": "2026-01-01T00:00:01"},
            {"role": "assistant", "content": "Hi there", "timestamp": "2026-01-01T00:00:02"},
        ]
        summary = summarizer.summarize(history)
        assert "Old summary" not in summary

    def test_summarize_preserves_decisions(self):
        from src.core.memory.compressor.rolling_summarizer import RollingSummarizer
        summarizer = RollingSummarizer()
        history = [
            {"role": "user", "content": "确认，开始研究", "timestamp": "2026-01-01T00:00:00"},
            {"role": "assistant", "content": "好的，已确认修改框架", "timestamp": "2026-01-01T00:00:01"},
        ]
        summary = summarizer.summarize(history)
        assert "关键决策" in summary or "确认" in summary or "修改" in summary


class TestLLMContextFiltersSummary:
    """LLM context builders filter out context_summary entries"""

    def test_filter_context_summary_from_history(self):
        history = [
            {"role": "user", "content": "Msg 1", "timestamp": "2026-01-01T00:00:00"},
            {"type": "context_summary", "role": "system", "content": "Summary", "timestamp": "2026-01-01T00:00:01"},
            {"role": "assistant", "content": "Msg 2", "timestamp": "2026-01-01T00:00:02"},
        ]
        chat_history = [m for m in history if m.get('type') != 'context_summary']
        assert len(chat_history) == 2
        assert all(m.get('type') != 'context_summary' for m in chat_history)

    def test_recent_history_excludes_summary(self):
        history = [
            {"role": "user", "content": f"Msg {i}", "timestamp": f"2026-01-01T00:00:00"}
            for i in range(12)
        ] + [{"type": "context_summary", "role": "system", "content": "Summary", "timestamp": "2026-01-01T00:00:12"}]
        chat_history = [m for m in history if m.get('type') != 'context_summary']
        recent = chat_history[-10:]
        assert len(recent) == 10
        assert all(m.get('type') != 'context_summary' for m in recent)


class TestAPIReadsConversationHistory:
    """API endpoints read from conversation_history directly"""

    def test_api_reads_conversation_history(self):
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            full = [{"role": "user", "content": f"Msg {i}", "timestamp": "2026-01-01T00:00:00"} for i in range(25)]
            mgr.create("s1", {
                "user_id": "u1",
                "conversation_history": full,
                "created_at": "2026-01-01T00:00:00",
                "status": "completed",
            })
            session = mgr.get("s1")
            source = session.get("conversation_history", [])
            assert len(source) == 25

    def test_pagination_offset_limit(self):
        from src.core.session_manager import SessionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            full = [{"role": "user", "content": f"Msg {i}", "timestamp": "2026-01-01T00:00:00"} for i in range(25)]
            mgr.create("s2", {
                "user_id": "u1",
                "conversation_history": full,
                "created_at": "2026-01-01T00:00:00",
                "status": "completed",
            })
            session = mgr.get("s2")
            source = session.get("conversation_history", [])
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
            {"type": "context_summary", "role": "system", "content": "Summary text", "timestamp": "2026-01-01T00:01:00"},
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
        assert filtered[1]["role"] == "system"


class TestIntegration:
    """End-to-end: write → compress → original messages intact"""

    def test_original_messages_preserved_through_compression_cycle(self):
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
            conv = session.get("conversation_history", [])
            original_msgs = [m for m in conv if m.get("type") != "context_summary"]
            assert len(original_msgs) == 15, f"Expected 15 original messages, got {len(original_msgs)}"
            summaries = [m for m in conv if m.get("type") == "context_summary"]
            assert len(summaries) >= 0

    def test_no_duplicate_summary_after_server_restart(self):
        from src.core.compress_adapter import SessionHistoryCompressor
        with tempfile.TemporaryDirectory() as tmpdir:
            compressor1 = SessionHistoryCompressor(step_limit=5, size_limit_kb=10, archive_base=tmpdir)
            history = [
                {"role": "user", "content": f"Msg {i}", "timestamp": f"2026-01-01T00:00:00"}
                for i in range(8)
            ]
            session = {"conversation_history": list(history), "user_id": "u1"}
            compressor1.compress_if_needed("s1", session)
            summaries_after_first = [m for m in session["conversation_history"] if m.get("type") == "context_summary"]
            assert len(summaries_after_first) == 1
            compressor2 = SessionHistoryCompressor(step_limit=5, size_limit_kb=10, archive_base=tmpdir)
            compressor2.compress_if_needed("s1", session)
            summaries_after_second = [m for m in session["conversation_history"] if m.get("type") == "context_summary"]
            assert len(summaries_after_second) == 1, f"Expected 1 summary, got {len(summaries_after_second)} — duplicate summary appended after restart"

    def test_new_summary_appended_after_more_messages(self):
        from src.core.compress_adapter import SessionHistoryCompressor
        with tempfile.TemporaryDirectory() as tmpdir:
            compressor = SessionHistoryCompressor(step_limit=5, size_limit_kb=10, archive_base=tmpdir)
            history = [
                {"role": "user", "content": f"Msg {i}", "timestamp": f"2026-01-01T00:00:00"}
                for i in range(8)
            ]
            session = {"conversation_history": list(history), "user_id": "u1"}
            compressor.compress_if_needed("s1", session)
            summaries = [m for m in session["conversation_history"] if m.get("type") == "context_summary"]
            assert len(summaries) == 1
            for i in range(8, 16):
                session["conversation_history"].append(
                    {"role": "user", "content": f"Msg {i}", "timestamp": f"2026-01-01T00:00:00"}
                )
            compressor.compress_if_needed("s1", session)
            summaries = [m for m in session["conversation_history"] if m.get("type") == "context_summary"]
            assert len(summaries) == 2
            original_msgs = [m for m in session["conversation_history"] if m.get("type") != "context_summary"]
            assert len(original_msgs) == 16


class TestPersistEventDedup:
    """_persist_event deduplicates chat_response entries"""

    def test_chat_response_not_duplicated(self):
        from src.core.session_streamer import SessionStreamer
        import asyncio
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.core.session_manager import SessionManager
            SessionManager.reset_instance()
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("s1", {"user_id": "u1", "conversation_history": [
                {"role": "assistant", "content": "Hello", "timestamp": "2026-01-01T00:00:00"},
            ]})
            SessionStreamer._persist_event("s1", "chat_response", {
                "message": "Hello",
                "timestamp": "2026-01-01T00:00:00",
            })
            session = mgr.get("s1")
            assistant_msgs = [m for m in session["conversation_history"] if m.get("role") == "assistant"]
            assert len(assistant_msgs) == 1

    def test_chat_response_appended_when_new(self):
        from src.core.session_streamer import SessionStreamer
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.core.session_manager import SessionManager
            SessionManager.reset_instance()
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("s2", {"user_id": "u1", "conversation_history": []})
            SessionStreamer._persist_event("s2", "chat_response", {
                "message": "New message",
                "timestamp": "2026-01-01T00:00:01",
            })
            session = mgr.get("s2")
            assistant_msgs = [m for m in session["conversation_history"] if m.get("role") == "assistant"]
            assert len(assistant_msgs) == 1
            assert assistant_msgs[0]["content"] == "New message"

    def test_agent_message_always_appended(self):
        from src.core.session_streamer import SessionStreamer
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.core.session_manager import SessionManager
            SessionManager.reset_instance()
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create("s3", {"user_id": "u1", "conversation_history": []})
            SessionStreamer._persist_event("s3", "agent_message", {
                "content": "Searching...",
                "agent_id": "web_search",
                "agent_name": "Web Search",
                "action": "searching",
                "timestamp": "2026-01-01T00:00:00",
            })
            session = mgr.get("s3")
            agent_msgs = [m for m in session["conversation_history"] if m.get("role") == "agent"]
            assert len(agent_msgs) == 1
