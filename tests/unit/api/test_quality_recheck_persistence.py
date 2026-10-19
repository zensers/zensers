import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_recheck_quality_persists_checker_result_in_quality_state():
    from src.api.research_api import ResearchAPI

    api = ResearchAPI()
    api._quality_checker = AsyncMock()
    api._quality_checker.execute.return_value = {
        "success": True,
        "quality_score": 84.0,
        "passed": True,
        "issues": [],
        "check_details": {},
    }
    state = {"phase": "revising", "overall_score": 40.0, "section_scores": {}}
    session = {
        "_session_id": "s1",
        "quality_state": state,
        "research_result": {"report": {"sections": [{"title": "市场", "content": "内容"}]}},
    }
    with patch("src.core.session_streamer.SessionStreamer"):
        result = await api._recheck_quality(session, session["research_result"]["report"]["sections"])

    assert result["quality_score"] == 84.0
    assert session["quality_state"]["overall_score"] == 84.0
    assert session["quality_state"]["overall_status"] == "passed"
    assert session["quality_state"]["phase"] == "reviewing"
    assert session["quality_state"]["last_recheck"]["passed"] is True


@pytest.mark.asyncio
async def test_failed_recheck_does_not_overwrite_quality_state():
    from src.api.research_api import ResearchAPI

    api = ResearchAPI()
    api._quality_checker = AsyncMock()
    api._quality_checker.execute.return_value = {"success": False, "error": "checker failed"}
    state = {"phase": "revising", "overall_score": 40.0}
    session = {"_session_id": "s1", "quality_state": state, "research_result": {"report": {}}}

    result = await api._recheck_quality(session, [])

    assert result is None
    assert session["quality_state"] is state
    assert session["quality_state"]["phase"] == "revising"
