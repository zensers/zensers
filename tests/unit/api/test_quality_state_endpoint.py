import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_quality_state_endpoint_returns_persisted_state():
    from src.api.research_api import ResearchAPI

    quality_state = {"phase": "reviewing", "section_scores": {"市场规模": {"score": 72}}}
    session = {"quality_state": quality_state}
    with patch("src.api.research_api.session_manager") as manager:
        manager.get.return_value = session
        result = await ResearchAPI().get_quality_state("session-1")

    assert result is quality_state


@pytest.mark.asyncio
async def test_quality_state_endpoint_does_not_autocreate_unknown_session():
    from src.api.research_api import ResearchAPI

    with patch("src.api.research_api.session_manager") as manager:
        manager.get.return_value = None
        result = await ResearchAPI().get_quality_state("missing")

    assert result["error_code"] == "SESSION_NOT_FOUND"
    manager.get.assert_called_once_with("missing")
