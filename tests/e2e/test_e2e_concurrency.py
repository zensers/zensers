# -*- coding: utf-8 -*-
"""
Phase 5: Concurrency & Race Condition E2E Tests

Tests concurrent quality actions, concurrent section revisions, and
interact-during-execution scenarios.
"""

import asyncio
import logging
import os
import pytest

from tests.e2e.helpers.assertion_helpers import (
    assert_no_error,
    assert_session_id,
)

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.requires_llm]

# Keep production-like defaults, but allow diagnostic runs to impose a bounded
# wait without editing the test. This is intentionally test-only configuration.
COMPLETION_TIMEOUT = float(os.environ.get("E2E_COMPLETION_TIMEOUT", "600"))
POLL_INTERVAL = float(os.environ.get("E2E_POLL_INTERVAL", "5"))


class TestConcurrentQualityActions:
    """Scenario 5.1: Concurrent quality actions should be serialized by lock"""

    @pytest.mark.asyncio
    async def test_concurrent_accept_and_revise(self, client, new_energy_topic, cleanup_test_sessions):
        start_result = await client.quick_start(
            user_input=new_energy_topic,
            template_id="industry_research",
            auto_confirm=True,
        )
        assert_no_error(start_result, "quick_start")
        session_id = assert_session_id(start_result)
        cleanup_test_sessions.append(session_id)

        detail = await client.wait_for_research_result(
            session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
        )
        result = detail.get("result", {})
        assert result.get("status") in ("completed", "completed_with_warnings")

        accept_task = asyncio.create_task(
            client.quality_action(session_id=session_id, action="accept")
        )
        revise_task = asyncio.create_task(
            client.quality_action(session_id=session_id, action="revise", section_name="市场规模")
        )

        results = await asyncio.gather(accept_task, revise_task, return_exceptions=True)
        logger.info(f"[5.1] Concurrent quality results: accept={results[0]}, revise={results[1]}")

        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"[5.1] One concurrent action raised: {r}")
            elif isinstance(r, dict):
                assert "error" not in r or r.get("error_code") in ("NO_QUALITY_STATE", "NO_SECTIONS"), \
                    f"Unexpected error in concurrent quality action: {r}"

        sm = __import__("src.core.session_manager", fromlist=["SessionManager"]).SessionManager.get_instance()
        session = sm.get(session_id)
        if session:
            quality_data = session.get("quality_state", {})
            if quality_data:
                assert isinstance(quality_data.get("section_scores"), dict), \
                    "Quality state corrupted by concurrent access"


class TestConcurrentSectionRevisions:
    """Scenario 5.2: Concurrent revisions of different sections"""

    @pytest.mark.asyncio
    async def test_concurrent_different_section_revisions(self, client, new_energy_topic, cleanup_test_sessions):
        start_result = await client.quick_start(
            user_input=new_energy_topic,
            template_id="industry_research",
            auto_confirm=True,
        )
        assert_no_error(start_result, "quick_start")
        session_id = assert_session_id(start_result)
        cleanup_test_sessions.append(session_id)

        detail = await client.wait_for_research_result(
            session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
        )
        result = detail.get("result", {})
        assert result.get("status") in ("completed", "completed_with_warnings")

        sections = result.get("report", {}).get("sections", [])
        if len(sections) < 2:
            pytest.skip("Need at least 2 sections for concurrent revision test")

        section_a = sections[0].get("title", "")
        section_b = sections[1].get("title", "")

        task_a = asyncio.create_task(
            client.revise_sections(task_id=session_id, aspects=[section_a], adjustment="补充数据")
        )
        task_b = asyncio.create_task(
            client.revise_sections(task_id=session_id, aspects=[section_b], adjustment="增强分析")
        )

        results = await asyncio.gather(task_a, task_b, return_exceptions=True)
        logger.info(f"[5.2] Concurrent revision results: a={results[0]}, b={results[1]}")

        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"[5.2] One revision raised: {r}")
            elif isinstance(r, dict):
                assert "error" not in r or r.get("error_code") != "SESSION_CORRUPTED", \
                    "Session should not be corrupted by concurrent revisions"


class TestInteractDuringExecution:
    """Scenario 5.3: Send chat while research is executing"""

    @pytest.mark.asyncio
    async def test_chat_during_execution(self, client, new_energy_topic, cleanup_test_sessions):
        start_result = await client.quick_start(
            user_input=new_energy_topic,
            template_id="industry_research",
            auto_confirm=True,
        )
        assert_no_error(start_result, "quick_start")
        session_id = assert_session_id(start_result)
        cleanup_test_sessions.append(session_id)

        await asyncio.sleep(5)

        interact_result = await client.interact(
            session_id=session_id,
            step=0,
            response={"text": "研究进展如何？", "message": "研究进展如何？"},
        )
        logger.info(f"[5.3] Interact during execution: {interact_result.get('mode', 'unknown')}, action={interact_result.get('action')}")

        assert "error" not in interact_result or interact_result.get("error_code") not in ("CRASH", "FATAL"), \
            "Interact during execution should not crash"

        final = await client.wait_for_research_result(
            session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
        )
        result_status = final.get("result", {}).get("status", "")
        assert result_status in ("completed", "completed_with_warnings"), \
            f"Research should still complete after interact: {result_status}"
        logger.info(f"[5.3] Research completed after interact: {result_status}")
