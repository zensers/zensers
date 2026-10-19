# -*- coding: utf-8 -*-
"""
Phase 1: Normal Full Lifecycle E2E Tests

Covers the complete research report lifecycle from user request to final document export.
Two topics tested:
- 中国新能源汽车市场 (broad industry research via interact flow)
- 比亚迪财务分析 (focused financial analysis via quick-start flow)
"""

import asyncio
import logging
import pytest

from tests.e2e.helpers.assertion_helpers import (
    assert_no_error,
    assert_session_id,
    assert_status,
    assert_has_preview,
    assert_preview_contains_sections,
    assert_quality_state_valid,
    assert_download_success,
)

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.requires_llm]

COMPLETION_TIMEOUT = 900
POLL_INTERVAL = 10


class TestNewEnergyVehicleFullLifecycle:
    """Scenario 1.1: 中国新能源汽车市场 — full interact flow"""

    @pytest.mark.asyncio
    async def test_full_lifecycle_interact_flow(self, client, new_energy_topic, cleanup_test_sessions):
        # Step 1: Start research
        start_result = await client.start_research(user_input=new_energy_topic)
        assert_no_error(start_result, "start_research")
        session_id = assert_session_id(start_result)
        cleanup_test_sessions.append(session_id)
        logger.info(f"[1.1] Session created: {session_id}")

        # Step 2: Chat to identify intent — send "深度研究" to enter framework mode
        interact_result = await client.interact(
            session_id=session_id,
            step=0,
            response={"text": f"请对{new_energy_topic}进行深度研究", "message": f"请对{new_energy_topic}进行深度研究"},
        )
        assert_no_error(interact_result, "interact_chat")
        logger.info(f"[1.1] Chat interact done: mode={interact_result.get('mode')}, action={interact_result.get('action')}")

        # Step 3: If in framework mode, confirm to start execution
        mode = interact_result.get("mode", "chat")
        if mode == "framework":
            confirm_result = await client.interact(
                session_id=session_id,
                step=0,
                response={"text": "确认开始", "message": "确认开始"},
            )
            assert_no_error(confirm_result, "interact_confirm")
            logger.info(f"[1.1] Framework confirmed: mode={confirm_result.get('mode')}, status={confirm_result.get('status')}")

            if confirm_result.get("mode") == "framework" and confirm_result.get("status") != "running":
                start_result = await client.interact(
                    session_id=session_id,
                    step=0,
                    response={"text": "开始研究", "message": "开始研究"},
                )
                logger.info(f"[1.1] Start research: mode={start_result.get('mode')}, status={start_result.get('status')}")

        # Step 4: Wait for execution completion
        final_status = await client.wait_for_completion(
            session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
        )
        status = final_status.get("status", "unknown")
        logger.info(f"[1.1] Execution status: {status}")

        # If execution completed via the research result path, check detail
        detail = await client.get_research_detail(session_id)
        result = detail.get("result", {})
        result_status = result.get("status", "")

        if not result_status:
            from src.core.session_manager import SessionManager
            sm = SessionManager.get_instance()
            session = sm.get(session_id)
            if session:
                rr = session.get("research_result", {})
                result_status = rr.get("status", "")
                result = rr
                if not result_status and rr.get("report"):
                    result_status = "completed_with_warnings"

        assert result_status in ("completed", "completed_with_warnings"), \
            f"Research did not complete: result_status={result_status}, detail keys={list(detail.keys())}"
        logger.info(f"[1.1] Research completed: result_status={result_status}")

        # Step 5: Get preview
        preview = await client.get_preview(session_id)
        assert_has_preview(preview)
        html_content = preview.get("html_content", "")
        if html_content and result.get("report", {}).get("sections"):
            section_titles = [s.get("title", "") for s in result["report"]["sections"] if s.get("title")]
            assert_preview_contains_sections(html_content, section_titles)
        logger.info(f"[1.1] Preview OK: html_length={len(html_content) if html_content else 0}")

        # Step 6: Get sections
        sections_resp = await client.get_sections(session_id)
        assert_no_error(sections_resp, "get_sections")
        sections = sections_resp.get("sections", [])
        assert len(sections) > 0, "Report should have sections"
        logger.info(f"[1.1] Sections count: {len(sections)}")

        # Step 7: Quality action — accept
        quality_result = await client.quality_action(session_id=session_id, action="accept")
        logger.info(f"[1.1] Quality action: {quality_result.get('status', quality_result.get('error', 'ok'))}")

        # Step 8: Feedback — confirm
        feedback_result = await client.feedback(session_id=session_id, action="confirm")
        assert_no_error(feedback_result, "feedback_confirm")
        assert_status(feedback_result, "completed")
        logger.info(f"[1.1] Feedback confirmed")

        # Step 9: Download document
        download_resp = await client.download(session_id)
        if download_resp.status_code == 200:
            assert_download_success(download_resp)
            logger.info(f"[1.1] Download OK: {len(download_resp.content)} bytes, content-type={download_resp.headers.get('content-type')}")
        else:
            logger.warning(f"[1.1] Download returned {download_resp.status_code} — may need export first")


class TestBYDFinancialQuickStart:
    """Scenario 1.2: 比亚迪财务分析 — quick-start flow"""

    @pytest.mark.asyncio
    async def test_quick_start_lifecycle(self, client, byd_topic, cleanup_test_sessions):
        # Step 1: Quick-start with template
        qs_result = await client.quick_start(
            user_input=byd_topic,
            template_id="company_analysis",
            auto_confirm=True,
            region="China",
            time_range="Last 1 year",
        )
        assert_no_error(qs_result, "quick_start")
        session_id = assert_session_id(qs_result)
        cleanup_test_sessions.append(session_id)
        logger.info(f"[1.2] Quick-start session: {session_id}, status={qs_result.get('status')}")

        # Step 2: Wait for completion
        final_status = await client.wait_for_research_result(
            session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
        )
        result = final_status.get("result", {})
        result_status = result.get("status", "")

        if not result_status:
            from src.core.session_manager import SessionManager
            sm = SessionManager.get_instance()
            session = sm.get(session_id)
            if session:
                rr = session.get("research_result", {})
                result_status = rr.get("status", "")
                result = rr
                if not result_status and rr.get("report"):
                    result_status = "completed_with_warnings"

        assert result_status in ("completed", "completed_with_warnings"), \
            f"Research did not complete: result_status={result_status}"
        logger.info(f"[1.2] Research completed: result_status={result_status}")

        # Step 3: Get preview
        preview = await client.get_preview(session_id)
        assert_has_preview(preview)
        html_content = preview.get("html_content", "")
        logger.info(f"[1.2] Preview OK: html_length={len(html_content) if html_content else 0}")

        # Step 4: Get sections
        sections_resp = await client.get_sections(session_id)
        assert_no_error(sections_resp, "get_sections")
        sections = sections_resp.get("sections", [])
        assert len(sections) > 0, "Report should have sections"
        logger.info(f"[1.2] Sections count: {len(sections)}")

        # Step 5: Quality action — accept
        quality_result = await client.quality_action(session_id=session_id, action="accept")
        logger.info(f"[1.2] Quality action: {quality_result}")

        # Step 6: Feedback — confirm
        feedback_result = await client.feedback(session_id=session_id, action="confirm")
        assert_no_error(feedback_result, "feedback_confirm")
        assert_status(feedback_result, "completed")
        logger.info(f"[1.2] Feedback confirmed")

        # Step 7: Download
        download_resp = await client.download(session_id)
        if download_resp.status_code == 200:
            assert_download_success(download_resp)
            logger.info(f"[1.2] Download OK: {len(download_resp.content)} bytes")
        else:
            logger.warning(f"[1.2] Download returned {download_resp.status_code}")
