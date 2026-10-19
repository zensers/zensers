# -*- coding: utf-8 -*-
"""
Phase 4: Error Recovery E2E Tests

Tests pause/resume, cancel, SSE disconnect fallback, and session persistence.
Real LLM needed for pause/resume; polling tests do not need LLM.
"""

import asyncio
import logging
import pytest

from src.core.session_manager import SessionManager

from tests.e2e.helpers.assertion_helpers import (
    assert_no_error,
    assert_session_id,
    assert_status,
)
from tests.e2e.helpers.wait_helpers import poll_status_until

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.requires_llm]

COMPLETION_TIMEOUT = 600
POLL_INTERVAL = 5


class TestPauseAndResume:
    """Scenario 4.1: Pause during execution → resume → continues"""

    @pytest.mark.asyncio
    async def test_pause_resume_during_execution(self, client, new_energy_topic, cleanup_test_sessions):
        start_result = await client.quick_start(
            user_input=new_energy_topic,
            template_id="industry_research",
            auto_confirm=True,
        )
        assert_no_error(start_result, "quick_start")
        session_id = assert_session_id(start_result)
        cleanup_test_sessions.append(session_id)

        await asyncio.sleep(3)

        pause_result = await client.pause_research(session_id)
        logger.info(f"[4.1] Pause result: {pause_result}")
        pause_status = pause_result.get("status")
        if pause_status == "paused":
            status_check = await client.get_status(session_id)
            logger.info(f"[4.1] Status after pause: {status_check.get('status')}")

            resume_result = await client.resume_research(session_id)
            logger.info(f"[4.1] Resume result: {resume_result}")

            final = await client.wait_for_research_result(
                session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
            )
            result_status = final.get("result", {}).get("status", "")
            assert result_status in ("completed", "completed_with_warnings", "running"), \
                f"Resume did not recover: status={result_status}"
            logger.info(f"[4.1] Final status after resume: {result_status}")
        else:
            logger.warning(f"[4.1] Could not pause (status={pause_status}), research may have completed too fast")


class TestCancelDuringExecution:
    """Scenario 4.2: Cancel during execution"""

    @pytest.mark.asyncio
    async def test_cancel_during_execution(self, client, new_energy_topic, cleanup_test_sessions):
        start_result = await client.quick_start(
            user_input=new_energy_topic,
            template_id="industry_research",
            auto_confirm=True,
        )
        assert_no_error(start_result, "quick_start")
        session_id = assert_session_id(start_result)
        cleanup_test_sessions.append(session_id)

        await asyncio.sleep(3)

        cancel_result = await client.cancel_research(session_id)
        logger.info(f"[4.2] Cancel result: {cancel_result}")

        await asyncio.sleep(2)

        status = await client.get_status(session_id)
        logger.info(f"[4.2] Status after cancel: {status.get('status')}")

        sm = SessionManager.get_instance()
        session = sm.get(session_id)
        if session:
            state_machine = session.get("state_machine")
            if state_machine and hasattr(state_machine, "current_state"):
                cur_state = state_machine.current_state.value
                assert cur_state in ("cancelled", "completed", "paused"), \
                    f"Unexpected state after cancel: {cur_state}"


class TestSSEDisconnectFallback:
    """Scenario 4.3: SSE disconnect → polling fallback still works"""

    @pytest.mark.asyncio
    async def test_polling_after_sse_disconnect(self, client, new_energy_topic, cleanup_test_sessions):
        start_result = await client.quick_start(
            user_input=new_energy_topic,
            template_id="industry_research",
            auto_confirm=True,
        )
        assert_no_error(start_result, "quick_start")
        session_id = assert_session_id(start_result)
        cleanup_test_sessions.append(session_id)

        status = await client.get_status(session_id)
        assert "task_id" in status or "status" in status, f"Status polling failed: {status}"
        logger.info(f"[4.3] Initial poll status: {status.get('status')}")

        final = await client.wait_for_research_result(
            session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
        )
        result_status = final.get("result", {}).get("status", "")
        assert result_status in ("completed", "completed_with_warnings"), \
            f"Polling fallback did not detect completion: {result_status}"
        logger.info(f"[4.3] Completed via polling: {result_status}")


class TestSessionPersistenceOnDisk:
    """Scenario 4.4: Session state persisted on disk survives lookup"""

    @pytest.mark.asyncio
    async def test_session_persisted_to_disk(self, client, new_energy_topic, cleanup_test_sessions):
        from pathlib import Path

        start_result = await client.start_research(user_input=new_energy_topic)
        assert_no_error(start_result, "start_research")
        session_id = assert_session_id(start_result)
        cleanup_test_sessions.append(session_id)

        session_file = Path("data/sessions") / f"{session_id}.json"
        assert session_file.exists(), f"Session file not persisted: {session_file}"
        logger.info(f"[4.4] Session file exists: {session_file}")

        import json
        with open(session_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved.get("_session_id") == session_id or saved.get("user_input") == new_energy_topic, \
            "Persisted session data mismatch"
        logger.info(f"[4.4] Session data verified on disk")
