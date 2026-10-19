from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def report_context_client(tmp_path):
    from src.core.session_manager import SessionManager
    from src.api.main import app

    SessionManager.reset_instance()
    manager = SessionManager()
    manager._base_dir = Path(tmp_path)
    manager.create("api-context-1", {
        "user_input": "测试报告",
        "research_context": {"topic": "测试报告"},
        "output_format": "docx",
        "research_result": {
            "status": "completed",
            "report": {"sections": [{"id": "s1", "title": "结论", "content": "测试内容"}]},
        },
    })
    try:
        yield TestClient(app)
    finally:
        SessionManager.reset_instance()


def test_report_context_api_returns_snapshot(report_context_client):
    response = report_context_client.get("/api/v1/research/api-context-1/report-context")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "api-context-1"
    assert payload["report_phase"] == "completed"
    assert payload["sections"][0]["title"] == "结论"
    assert payload["sections"][0]["word_count"] == 1

    from src.core.session_manager import SessionManager
    persisted = SessionManager.get_instance().get("api-context-1")
    assert persisted["report_context"]["context_revision"] == payload["context_revision"]


def test_report_context_api_returns_404_for_unknown_session(report_context_client):
    response = report_context_client.get("/api/v1/research/not-found/report-context")

    assert response.status_code == 404
