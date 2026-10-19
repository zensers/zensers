import pytest
from unittest.mock import AsyncMock, patch


def _session():
    return {
        "_session_id": "quality-dispatch",
        "quality_state": {
            "phase": "reviewing",
            "section_scores": {
                "市场规模": {
                    "score": 50,
                    "status": "warning",
                    "issues": [{
                        "id": "q-1",
                        "type": "completeness",
                        "severity": "high",
                        "message": "缺少来源",
                        "section": "市场规模",
                        "state": "open",
                    }],
                },
            },
            "version_stack": [{"id": "v0"}],
        },
        "research_result": {
            "report": {"sections": [{"section_id": "s1", "title": "市场规模", "content": "内容"}]},
        },
    }


@pytest.mark.asyncio
async def test_quality_action_dispatches_recheck_and_does_not_ignore_action():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager, \
         patch.object(api, "_recheck_quality", new_callable=AsyncMock, return_value={
             "success": True, "quality_score": 75, "passed": True,
         }):
        manager.get.return_value = session
        result = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_recheck")
        )

    assert result["success"] is True
    assert result["action"] == "quality_recheck"


@pytest.mark.asyncio
async def test_quality_action_rejects_unknown_action_without_recheck():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager, \
         patch.object(api, "_recheck_quality", new_callable=AsyncMock) as recheck:
        manager.get.return_value = session
        result = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="not-supported")
        )

    assert result["error_code"] == "UNKNOWN_ACTION"
    recheck.assert_not_awaited()


@pytest.mark.asyncio
async def test_quality_dismiss_and_reopen_update_only_requested_issue():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager, \
         patch("src.core.session_streamer.SessionStreamer") as streamer:
        manager.get.return_value = session
        dismissed = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_dismiss", issue_id="q-1")
        )
        reopened = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_reopen", issue_id="q-1")
        )

    assert dismissed["state"] == "dismissed"
    assert reopened["state"] == "open"
    assert streamer.push_quality_result.call_count == 2


@pytest.mark.asyncio
async def test_quality_dismiss_rejects_unknown_issue_and_is_idempotent():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager:
        manager.get.return_value = session
        missing = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_dismiss", issue_id="missing")
        )
        first = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_dismiss", issue_id="q-1")
        )
        second = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_dismiss", issue_id="q-1")
        )

    assert missing["error_code"] == "ISSUE_NOT_FOUND"
    assert first["state"] == second["state"] == "dismissed"


@pytest.mark.asyncio
async def test_quality_reopen_rejects_issue_that_is_not_dismissed():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager:
        manager.get.return_value = _session()
        result = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_reopen", issue_id="q-1")
        )

    assert result["error_code"] == "ISSUE_NOT_FOUND"



@pytest.mark.asyncio
async def test_quality_confirm_requires_force_for_open_issue():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager:
        manager.get.return_value = session
        result = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_confirm")
        )

    assert result["status"] == "pending_issues"
    assert result["open_issues"][0]["id"] == "q-1"
    assert session["quality_state"]["phase"] == "reviewing"


@pytest.mark.asyncio
async def test_quality_confirm_force_accepts_remaining_issues():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager, \
         patch("src.core.session_streamer.SessionStreamer"):
        manager.get.return_value = session
        result = await api.handle_quality_action(
            QualityActionRequest(
                session_id="quality-dispatch",
                action="quality_confirm",
                data={"force": True},
            )
        )

    assert result["status"] == "confirmed"
    issue = session["quality_state"]["section_scores"]["市场规模"]["issues"][0]
    assert issue["state"] == "accepted"
    assert result["formal_complete"] is False
    assert result["delivery_class"] == "available_with_warnings"
    assert session["research_result"]["formal_complete"] is False


@pytest.mark.asyncio
async def test_quality_confirm_accepts_top_level_force_and_marks_degraded_delivery():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager, \
         patch("src.core.session_streamer.SessionStreamer"):
        manager.get.return_value = session
        result = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_confirm", force=True)
        )

    assert result["status"] == "confirmed"
    assert result["quality_gate_status"] == "degraded"
    assert result["formal_complete"] is False


@pytest.mark.asyncio
async def test_quality_confirm_without_open_issues_does_not_require_force():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    session["quality_state"]["section_scores"]["市场规模"]["issues"][0]["state"] = "dismissed"
    session["quality_state"]["last_recheck"] = {"passed": True, "status": "passed"}
    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager, \
         patch("src.core.session_streamer.SessionStreamer"):
        manager.get.return_value = session
        result = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_confirm")
        )

    assert result["status"] == "confirmed"
    assert result["formal_complete"] is False


@pytest.mark.asyncio
async def test_quality_confirm_rejects_non_boolean_force():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager:
        manager.get.return_value = _session()
        result = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_confirm", force="false")
        )

    assert result["error_code"] == "INVALID_FORCE"


@pytest.mark.asyncio
async def test_quality_confirm_blocks_after_failed_recheck():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    session["quality_state"]["section_scores"]["市场规模"]["issues"] = []
    session["quality_state"]["last_recheck"] = {
        "passed": False, "status": "failed", "error_code": "QUALITY_RECHECK_FAILED"
    }
    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager:
        manager.get.return_value = session
        result = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_confirm")
        )

    assert result["error_code"] == "QUALITY_RECHECK_FAILED"
    assert session["quality_state"]["phase"] == "reviewing"


@pytest.mark.asyncio
async def test_quality_rollback_restores_report_and_preview_from_snapshot():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    api = ResearchAPI()
    snapshot = {
        "quality_state": {"phase": "reviewing", "section_scores": {}, "version_stack": []},
        "report": {"sections": [{"section_id": "s1", "title": "旧章节", "content": "旧内容"}]},
        "html_path": "",
    }
    with patch("src.api.research_api.session_manager") as manager, \
         patch("src.core.quality.quality_snapshot_manager.QualitySnapshotManager.restore_snapshot", new_callable=AsyncMock, return_value=snapshot), \
         patch("src.core.session_streamer.SessionStreamer"):
        manager.get.return_value = session
        result = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_rollback", version_id="v0")
        )

    assert result["success"] is True
    assert session["research_result"]["report"]["sections"][0]["title"] == "旧章节"
    assert session["quality_state"]["current_version"] == "v0"


@pytest.mark.asyncio
async def test_quality_rollback_restores_artifact_pointers_with_report():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    old_doc = "data/quality-dispatch/report_v0.docx"
    session["research_result"].update({
        "document_path": "data/quality-dispatch/report_v1.docx",
        "output_path": "data/quality-dispatch/report_v1.docx",
    })
    snapshot = {
        "quality_state": {"phase": "reviewing", "section_scores": {}, "version_stack": []},
        "report": {"sections": [{"section_id": "s1", "title": "旧章节", "content": "旧内容"}]},
        "artifacts": {"document_path": old_doc, "output_path": old_doc},
        "html_path": "",
    }
    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager, \
         patch("src.core.quality.quality_snapshot_manager.QualitySnapshotManager.restore_snapshot", new_callable=AsyncMock, return_value=snapshot), \
         patch("src.core.session_streamer.SessionStreamer"):
        manager.get.return_value = session
        result = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_rollback", version_id="v0")
        )

    assert result["success"] is True
    assert session["research_result"]["document_path"] == old_doc
    assert session["research_result"]["output_path"] == old_doc


@pytest.mark.asyncio
async def test_quality_action_repairs_missing_session_identity_for_snapshot_actions():
    from src.api.research_api import QualityActionRequest, ResearchAPI

    session = _session()
    session.pop("_session_id")
    api = ResearchAPI()
    with patch("src.api.research_api.session_manager") as manager, \
         patch.object(api, "_handle_quality_confirm", new_callable=AsyncMock, return_value={"status": "confirmed"}) as confirm:
        manager.get.return_value = session
        result = await api.handle_quality_action(
            QualityActionRequest(session_id="quality-dispatch", action="quality_confirm", data={"force": True})
        )

    assert result["status"] == "confirmed"
    assert session["_session_id"] == "quality-dispatch"
    confirm.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_revision_recheck_acquires_quality_lock():
    from src.api.research_api import ResearchAPI

    api = ResearchAPI()
    session = _session()
    observed = []

    async def assert_locked(current_session):
        observed.append(api._get_quality_lock(current_session["_session_id"]).locked())

    with patch.object(api, "_post_revision_recheck_locked", new=assert_locked):
        await api._post_revision_recheck(session)

    assert observed == [True]


@pytest.mark.asyncio
async def test_recheck_preserves_dismissed_issue_state():
    from src.api.research_api import ResearchAPI
    from src.core.quality.quality_state import generate_issue_id

    api = ResearchAPI()
    session = _session()
    stable_issue_id = generate_issue_id("市场规模", "completeness", "缺少来源")
    session["quality_state"]["section_scores"]["市场规模"]["issues"][0]["id"] = stable_issue_id
    session["quality_state"]["section_scores"]["市场规模"]["issues"][0]["state"] = "dismissed"
    checker_result = {
        "success": True,
        "quality_score": 70,
        "passed": True,
        "section_results": {
            "市场规模": {
                "score": 70,
                "status": "passed",
                "issues": [{
                    "type": "completeness",
                    "severity": "high",
                    "message": "缺少来源",
                }],
            },
        },
    }
    with patch("src.api.research_api.QualityCheckAgent", create=True) as checker_cls:
        checker_cls.return_value.execute = AsyncMock(return_value=checker_result)
        api._quality_checker = checker_cls.return_value
        await api._recheck_quality(session, session["research_result"]["report"]["sections"])

    issue = session["quality_state"]["section_scores"]["市场规模"]["issues"][0]
    assert issue["state"] == "dismissed"
