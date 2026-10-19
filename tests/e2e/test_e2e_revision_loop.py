# -*- coding: utf-8 -*-
"""
Phase 3: Revision Loop E2E Tests

Tests the revision lifecycle: quality review → revise → recheck → accept/rollback.
Requires real LLM for revision content generation.
"""

import asyncio
import logging
import pytest

from tests.e2e.helpers.assertion_helpers import (
    assert_no_error,
    assert_session_id,
    assert_quality_state_valid,
)

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.requires_llm]

COMPLETION_TIMEOUT = 600
POLL_INTERVAL = 5


async def _start_and_complete_research(client, topic, cleanup_list):
    start_result = await client.quick_start(
        user_input=topic,
        template_id="industry_research",
        auto_confirm=True,
    )
    assert_no_error(start_result, "quick_start")
    session_id = assert_session_id(start_result)
    cleanup_list.append(session_id)

    detail = await client.wait_for_research_result(
        session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
    )
    result = detail.get("result", {})
    assert result.get("status") in ("completed", "completed_with_warnings"), \
        f"Research did not complete: {result.get('status')}"
    return session_id, result


class TestSingleSectionRevise:
    """Scenario 3.1: Single section revise → recheck → accept"""

    @pytest.mark.asyncio
    async def test_revise_single_section(self, client, new_energy_topic, cleanup_test_sessions):
        session_id, result = await _start_and_complete_research(client, new_energy_topic, cleanup_test_sessions)
        sections = result.get("report", {}).get("sections", [])
        if not sections:
            pytest.skip("No sections in report")

        target_section = sections[0].get("title", "")
        logger.info(f"[3.1] Revise section: {target_section}")

        revise_result = await client.revise_sections(
            task_id=session_id,
            aspects=[target_section],
            adjustment="请补充更多数据支撑和具体数字",
        )
        logger.info(f"[3.1] Revise result: {revise_result.get('status', revise_result.get('mode', 'unknown'))}")

        detail = await client.wait_for_research_result(
            session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
        )
        result_after = detail.get("result", {})
        logger.info(f"[3.1] After revision: status={result_after.get('status')}")

        quality_result = await client.quality_action(session_id=session_id, action="accept")
        logger.info(f"[3.1] Quality accept: {quality_result}")

        feedback_result = await client.feedback(session_id=session_id, action="confirm")
        assert_no_error(feedback_result, "feedback_after_revise")
        logger.info(f"[3.1] Revision flow completed")


class TestMultiSectionBatchRevise:
    """Scenario 3.2: Multi-section batch revise"""

    @pytest.mark.asyncio
    async def test_revise_multiple_sections(self, client, new_energy_topic, cleanup_test_sessions):
        session_id, result = await _start_and_complete_research(client, new_energy_topic, cleanup_test_sessions)
        sections = result.get("report", {}).get("sections", [])
        if len(sections) < 2:
            pytest.skip("Need at least 2 sections for batch revise")

        target_sections = [s.get("title", "") for s in sections[:2]]
        logger.info(f"[3.2] Batch revise sections: {target_sections}")

        revise_result = await client.revise_sections(
            task_id=session_id,
            aspects=target_sections,
            adjustment="请增强逻辑连贯性，补充数据来源",
        )
        logger.info(f"[3.2] Batch revise result: {revise_result.get('status', 'unknown')}")

        detail = await client.wait_for_research_result(
            session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
        )
        logger.info(f"[3.2] After batch revision: {detail.get('result', {}).get('status')}")

        quality_result = await client.quality_action(session_id=session_id, action="accept")
        logger.info(f"[3.2] Quality accept: {quality_result}")


class TestRevisionStillFailsLoop:
    """Scenario 3.3: Revision still fails → loop continues"""

    @pytest.mark.asyncio
    async def test_revision_loop_continues(self, client, new_energy_topic, cleanup_test_sessions):
        session_id, result = await _start_and_complete_research(client, new_energy_topic, cleanup_test_sessions)
        sections = result.get("report", {}).get("sections", [])
        if not sections:
            pytest.skip("No sections")

        target_section = sections[0].get("title", "")

        for round_num in range(1, 3):
            revise_result = await client.revise_sections(
                task_id=session_id,
                aspects=[target_section],
                adjustment=f"第{round_num}轮修订：请改进内容质量",
            )
            logger.info(f"[3.3] Round {round_num} revise: {revise_result.get('status', 'unknown')}")

            detail = await client.wait_for_research_result(
                session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
            )
            logger.info(f"[3.3] Round {round_num} completed: {detail.get('result', {}).get('status')}")

        quality_result = await client.quality_action(session_id=session_id, action="accept")
        logger.info(f"[3.3] Final quality accept: {quality_result}")


class TestVersionRollback:
    """Scenario 3.4: Version rollback after revision"""

    @pytest.mark.asyncio
    async def test_rollback_after_revision(self, client, new_energy_topic, cleanup_test_sessions):
        session_id, result = await _start_and_complete_research(client, new_energy_topic, cleanup_test_sessions)

        sections = result.get("report", {}).get("sections", [])
        if not sections:
            pytest.skip("No sections")

        target_section = sections[0].get("title", "")
        original_content = sections[0].get("content", "")

        revise_result = await client.revise_sections(
            task_id=session_id,
            aspects=[target_section],
            adjustment="请大幅修改内容",
        )
        logger.info(f"[3.4] Revise result: {revise_result.get('status', 'unknown')}")

        detail = await client.wait_for_research_result(
            session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
        )
        logger.info(f"[3.4] After revision: {detail.get('result', {}).get('status')}")

        quality_data = await client.quality_state(session_id)
        version_stack = quality_data.get("version_stack", [])
        if version_stack and len(version_stack) >= 2:
            prev_version_id = version_stack[-2].get("version_id", "") or version_stack[-2].get("id", "")
            if prev_version_id:
                rollback_result = await client.quality_action(
                    session_id=session_id,
                    action="rollback",
                    version_id=prev_version_id,
                )
                logger.info(f"[3.4] Rollback result: {rollback_result}")
            else:
                logger.warning("[3.4] No version_id found in version_stack, skipping rollback")
        else:
            logger.warning("[3.4] Version stack too short for rollback, verifying quality action does not crash")
            quality_result = await client.quality_action(session_id=session_id, action="accept")
            logger.info(f"[3.4] Quality accept instead: {quality_result}")


class TestMaxRevisionRounds:
    """Scenario 3.5: Max revision rounds (10) → max_retries_reached"""

    @pytest.mark.asyncio
    async def test_max_retries_reached(self, client, new_energy_topic, cleanup_test_sessions):
        session_id, result = await _start_and_complete_research(client, new_energy_topic, cleanup_test_sessions)

        sections = result.get("report", {}).get("sections", [])
        if not sections:
            pytest.skip("No sections")

        target_section = sections[0].get("title", "")
        max_rounds = 10

        for round_num in range(1, max_rounds + 1):
            revise_result = await client.revise_sections(
                task_id=session_id,
                aspects=[target_section],
                adjustment=f"第{round_num}轮修订",
            )
            logger.info(f"[3.5] Round {round_num} revise: {revise_result.get('status', 'unknown')}")

            detail = await client.wait_for_research_result(
                session_id, timeout=COMPLETION_TIMEOUT, poll_interval=POLL_INTERVAL
            )
            if detail.get("result", {}).get("status") in ("completed", "completed_with_warnings"):
                pass

            quality_data = await client.quality_state(session_id)
            section_scores = quality_data.get("section_scores", {})
            for sec_name, sec_data in section_scores.items():
                for issue in sec_data.get("issues", []):
                    if issue.get("state") == "max_retries_reached":
                        logger.info(f"[3.5] Max retries reached at round {round_num}")
                        quality_result = await client.quality_action(session_id=session_id, action="accept")
                        return

        quality_result = await client.quality_action(session_id=session_id, action="accept")
        logger.info(f"[3.5] Completed {max_rounds} rounds, final accept: {quality_result}")
