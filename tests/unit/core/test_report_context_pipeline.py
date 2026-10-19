from unittest.mock import patch


def _context():
    return {
        "schema_version": 1,
        "session_id": "ctx-pipeline",
        "report_id": "ctx-pipeline",
        "report_version": 2,
        "report_phase": "completed",
        "document_type": "docx",
        "document_version": "final",
        "preview_url": "/api/v1/preview/ctx-pipeline",
        "download_url": None,
        "topic": "测试报告",
        "sections": [],
        "quality": {"overall_score": 90, "overall_status": "passed", "open_issue_count": 0},
        "pending_decision": None,
        "last_revision": {"status": "none", "request": None, "affected_sections": []},
        "updated_at": "2026-01-01T00:00:00+00:00",
        "context_revision": 4,
    }


def test_update_context_persists_before_publishing():
    from src.core.report_context import update_report_context

    order = []

    class FakeManager:
        def force_save(self, session_id):
            order.append(("save", session_id))

    session = {
        "research_context": {"topic": "测试报告"},
        "research_result": {"status": "completed", "sections": []},
    }

    with patch("src.core.session_manager.SessionManager.get_instance", return_value=FakeManager()), \
         patch("src.core.session_streamer.SessionStreamer.push_report_context", side_effect=lambda sid, data: order.append(("publish", sid, data["context_revision"]))):
        result = update_report_context("ctx-pipeline", session, phase="completed")

    assert session["report_context"]["session_id"] == "ctx-pipeline"
    assert result["context_revision"] == 1
    assert order[0] == ("save", "ctx-pipeline")
    assert order[1] == ("publish", "ctx-pipeline", 1)


def test_report_context_sse_payload_is_versioned_and_separate_from_agent_message():
    from src.core.session_streamer import SessionMessage, SessionStreamer

    messages = []
    session_id = "ctx-event"
    queue = __import__("asyncio").Queue()
    SessionStreamer._subscribers[session_id] = {queue}
    try:
        with patch.object(SessionStreamer, "_persist_event"):
            SessionStreamer.push_report_context(session_id, _context())
        message = queue.get_nowait()
        assert isinstance(message, SessionMessage)
        assert message.event == "report_context"
        assert message.data["session_id"] == session_id
        assert message.data["report_version"] == 2
        assert message.data["context_revision"] == 4
        assert message.data["snapshot"]["schema_version"] == 1
        messages.append(message)
    finally:
        SessionStreamer._subscribers.pop(session_id, None)
        SessionStreamer._recent_messages.pop(session_id, None)
    assert messages
