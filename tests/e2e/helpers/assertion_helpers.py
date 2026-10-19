# -*- coding: utf-8 -*-
import re
from typing import Any, Dict, List, Optional


def assert_no_error(result: Dict[str, Any], msg: str = ""):
    assert "error" not in result, f"{msg}: got error={result.get('error')}, code={result.get('error_code')}"


def assert_session_id(result: Dict[str, Any]) -> str:
    sid = result.get("session_id") or result.get("task_id")
    assert sid, f"No session_id/task_id in response: {list(result.keys())}"
    return sid


def assert_status(result: Dict[str, Any], expected: str, msg: str = ""):
    actual = result.get("status", "")
    assert actual == expected, f"{msg}: expected status={expected}, got={actual}"


def assert_has_preview(result: Dict[str, Any]):
    assert result.get("preview_url") or result.get("html_content"), \
        f"No preview in response: preview_url={result.get('preview_url')}, html_content present={bool(result.get('html_content'))}"


def assert_preview_contains_sections(html_content: str, sections: List[str]):
    missing = [s for s in sections if s not in html_content]
    assert not missing, f"Preview HTML missing sections: {missing}"


def assert_quality_state_valid(quality_data: Dict[str, Any]):
    assert "overall_score" in quality_data or "section_scores" in quality_data, \
        f"Quality state missing score fields: {list(quality_data.keys())}"


def assert_download_success(response):
    assert response.status_code == 200, f"Download failed: status={response.status_code}"
    content_type = response.headers.get("content-type", "")
    assert any(t in content_type for t in ("application/vnd.openxmlformats", "text/html", "application/octet-stream")), \
        f"Unexpected download content-type: {content_type}"
    assert len(response.content) > 0, "Downloaded file is empty"


def assert_state_machine_state(session: Dict[str, Any], expected_state: str):
    sm = session.get("state_machine")
    if sm and hasattr(sm, "current_state"):
        actual = sm.current_state.value
        assert actual == expected_state, f"State machine: expected={expected_state}, got={actual}"
