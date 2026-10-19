"""
Race condition test: pause flag set before executor._check_paused runs

Reproduces the exact bug from ses_724e318a logs (2026-05-27):

Timeline from logs:
  13:31:59 - executor.execute() starts, "set global language" logged
  13:31:59 - "Executing orchestrator" logged (first run works)
  13:32:34 - Research FAILED (status: failed)
  13:44:55 - SSE disconnect → _delayed_pause scheduled
  14:11:44 - User sends "Retry the research with different parameters"
  14:11:59 - LLM returns action=enter_framework → cm.pause() called (line 568)
  14:11:59 - _enter_framework_mode → "Framework already exists"
  14:12:05 - _start_execution → executor.execute() starts → "set global language"
  14:12:05 - _check_paused finds is_paused=True → blocks on wait_for_resume_or_cancel
  (no more logs until 14:16:39 cleanup — task stuck for 4+ minutes)

Root cause: When user retries after a failed research, the LLM routes to
enter_framework which calls cm.pause(). Then _start_execution is called,
which starts executor.execute(). But the pause flag is still set, so
_check_paused blocks indefinitely. Nobody calls cm.resume() because
the UI is in framework mode, not research mode.
"""

import asyncio
import pytest
from datetime import datetime

from src.core.orchestrator.execution.coordinator.cancel_manager import CancelManager


class TestPauseBeforeExecutorCheck:
    """
    Test the race condition where pause() is called BEFORE
    executor._check_paused() runs, causing the executor to block forever.
    """

    def setup_method(self):
        self.cm = CancelManager()

    @pytest.mark.asyncio
    async def test_pause_before_check_blocks_executor(self):
        """
        BUG REPRODUCTION: pause() called before _check_paused()
        → executor blocks forever on wait_for_resume_or_cancel()

        This is exactly what happens in the ses_724e318a case:
        1. LLM returns enter_framework → cm.pause(session_id)
        2. _start_execution → executor.execute() → _check_paused()
        3. _check_paused sees is_paused=True → wait_for_resume_or_cancel()
        4. Nobody resumes → executor stuck forever
        """
        task_id = "ses_test_race"

        # Step 1: LLM action=enter_framework calls cm.pause()
        self.cm.pause(task_id)
        assert self.cm.is_paused(task_id)

        # Step 2: executor._check_paused() would block forever
        # Simulate with a timeout so the test doesn't hang
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                self.cm.wait_for_resume_or_cancel(task_id),
                timeout=0.5,
            )

    @pytest.mark.asyncio
    async def test_pause_then_start_execution_race(self):
        """
        Simulate the full race: pause → start_execution → executor blocks

        In production, the sequence is:
        - _handle_user_message (mode=research) → LLM returns enter_framework
        - cm.pause(session_id) at line 568
        - _enter_framework_mode → returns framework
        - User clicks confirm → _start_execution
        - executor.execute() → _check_paused() → BLOCKS

        Nobody calls cm.resume() because:
        - The enter_framework path doesn't resume
        - _start_execution doesn't clear stale pause flags
        - The UI shows framework, not a paused research
        """
        task_id = "ses_test_full_race"

        # Phase 1: Research was running, user sends message during research
        # LLM decides enter_framework → pause + cancel executor task
        self.cm.pause(task_id)

        # Phase 2: _enter_framework_mode returns framework to user
        # (no resume happens here — pause flag stays set)

        # Phase 3: User clicks "confirm start" → _start_execution
        # executor.execute() runs → _check_paused() finds is_paused=True
        # This would block forever in production
        check_passed = False
        try:
            result = await asyncio.wait_for(
                self.cm.wait_for_resume_or_cancel(task_id),
                timeout=0.3,
            )
            # If we get here, someone resumed — but in the bug, nobody does
            check_passed = (result == "resumed")
        except asyncio.TimeoutError:
            # This is the BUG: executor blocks forever
            check_passed = False

        assert not check_passed, "Executor should be blocked (bug), but it passed"

    @pytest.mark.asyncio
    async def test_stale_pause_flag_not_cleared_on_new_execution(self):
        """
        The core issue: a stale pause flag from a PREVIOUS action
        (enter_framework) is not cleared when a NEW execution starts.

        When _start_execution is called, it should clear any stale
        pause flags because the user explicitly confirmed to start.
        """
        task_id = "ses_test_stale"

        # Previous action left a stale pause flag
        self.cm.pause(task_id)
        assert self.cm.is_paused(task_id)

        # _start_execution should clear stale pause before starting executor
        # Currently it does NOT — this is the bug
        # Expected behavior: cm.resume(task_id) or cm.cleanup(task_id)
        # before starting executor

        # Verify the flag is still set (bug)
        assert self.cm.is_paused(task_id), \
            "Bug: stale pause flag is still set when new execution starts"


class TestEnterFrameworkPauseSequence:
    """
    Test the exact enter_framework → _start_execution sequence
    that causes the bug in research_api.py lines 566-590.
    """

    def setup_method(self):
        self.cm = CancelManager()

    @pytest.mark.asyncio
    async def test_enter_framework_sets_pause_without_resume(self):
        """
        When LLM returns action=enter_framework during research:
        - Line 568: cm.pause(session_id) is called
        - Line 569-571: executor task is cancelled
        - Line 575: log "switching to framework"
        - Line 576: session["mode"] = "chat"

        But NO resume is ever called! The pause flag persists.
        When user later clicks "confirm start", _start_execution
        launches executor.execute() which hits _check_paused() and blocks.
        """
        task_id = "ses_test_ef"

        # Simulate enter_framework action (line 566-590)
        self.cm.pause(task_id)
        # old task would be cancelled here (line 569-571)
        # session mode changes to "chat" (line 576)

        # No cm.resume() is called anywhere in the enter_framework path
        assert self.cm.is_paused(task_id)

        # Later: user clicks "confirm start" → _start_execution
        # executor.execute() → _check_paused() → BLOCKS
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                self.cm.wait_for_resume_or_cancel(task_id),
                timeout=0.3,
            )

    @pytest.mark.asyncio
    async def test_modify_research_also_sets_pause_without_resume(self):
        """
        Same bug exists in modify_research action (line 550-564):
        - Line 552: cm.pause(session_id)
        - Line 553-555: executor task cancelled
        - _handle_modify_research called

        If modify leads to _start_execution (e.g. via _resume_after_modify),
        the stale pause flag will block the new executor.
        """
        task_id = "ses_test_modify"

        # Simulate modify_research action (line 550-564)
        self.cm.pause(task_id)

        # Same stale pause problem
        assert self.cm.is_paused(task_id)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                self.cm.wait_for_resume_or_cancel(task_id),
                timeout=0.3,
            )


class TestSSEDisconnectPauseRace:
    """
    Test the SSE disconnect → delayed_pause race condition.

    This is a SECOND path that can cause the same symptom:
    - SSE disconnects → _delayed_pause scheduled (15s delay)
    - If SSE doesn't reconnect in 15s → pause_research called
    - If this fires between _start_execution and executor._check_paused,
      the executor blocks
    """

    def setup_method(self):
        self.cm = CancelManager()

    @pytest.mark.asyncio
    async def test_delayed_pause_during_execution_startup(self):
        """
        _delayed_pause fires after 15s. If execution just started
        and SSE hasn't reconnected yet, the task gets paused
        mid-execution-startup.
        """
        task_id = "ses_test_sse"

        # Execution starts (no pause yet)
        assert not self.cm.is_paused(task_id)

        # 15s later, delayed_pause fires (simulated)
        self.cm.pause(task_id)

        # executor._check_paused would now block
        assert self.cm.is_paused(task_id)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                self.cm.wait_for_resume_or_cancel(task_id),
                timeout=0.3,
            )

    @pytest.mark.asyncio
    async def test_delayed_pause_ignores_already_failed_research(self):
        """
        In the ses_724e318a case, research had ALREADY FAILED at 13:32:34.
        The SSE disconnect at 13:44:55 should NOT pause a failed task.
        But _on_sse_disconnect only checks for "completed" status,
        not "failed" status (line 3502).
        """
        task_id = "ses_test_failed"

        # Research failed — research_result.status = "failed"
        # _on_sse_disconnect only checks: research_result.get("status") == "completed"
        # It does NOT check for "failed" — so it schedules delayed_pause anyway

        # This is a secondary bug: failed research should not be paused
        # For now, just document that the check is incomplete
        session = {
            "research_result": {"status": "failed"},
        }
        # The check at line 3502 only guards against "completed"
        should_skip = session.get("research_result", {}).get("status") == "completed"
        assert not should_skip, \
            "Bug: failed research is not skipped by _on_sse_disconnect check"


class TestCheckPausedMissingLog:
    """
    _check_paused (research_executor.py:85-86) has no log when
    is_paused() is True — it silently enters wait_for_resume_or_cancel().
    This makes the bug invisible in logs.
    """

    def setup_method(self):
        self.cm = CancelManager()

    @pytest.mark.asyncio
    async def test_check_paused_no_log_on_pause(self):
        """
        Verify that when _check_paused encounters a paused task,
        there is no log message before blocking. This is why
        the bug is invisible — logs show "set global language"
        then nothing.
        """
        task_id = "ses_test_nolog"
        self.cm.pause(task_id)

        # _check_paused code (line 85-86):
        #   if cm.is_paused(session_id):
        #       r = await cm.wait_for_resume_or_cancel(session_id)
        # No logger.info() between the if and the await!

        # This test documents the missing log.
        # The fix should add: logger.info(f"Task paused, waiting: {session_id}")
        # before the wait_for_resume_or_cancel call.
        assert self.cm.is_paused(task_id)


class TestAllPauseCallSites:
    """
    Audit all cm.pause() call sites and verify which ones
    have a corresponding cm.resume() before _start_execution.
    """

    def setup_method(self):
        self.cm = CancelManager()

    @pytest.mark.asyncio
    async def test_pause_site_1_enter_framework_line568(self):
        """
        research_api.py:568 — action=enter_framework during research
        Pause: YES (cm.pause)
        Resume before _start_execution: NO
        Bug: YES — stale pause blocks new execution
        """
        task_id = "site1"
        self.cm.pause(task_id)
        # No resume path before _start_execution
        assert self.cm.is_paused(task_id)

    @pytest.mark.asyncio
    async def test_pause_site_2_modify_research_line552(self):
        """
        research_api.py:552 — action=modify_research during research
        Pause: YES (cm.pause)
        Resume before _start_execution: MAYBE — _resume_after_modify calls cm.resume
        Bug: DEPENDS — if modify leads to _resume_after_modify, resume is called.
              But if modify fails or user takes a different path, stale pause remains.
        """
        task_id = "site2"
        self.cm.pause(task_id)
        # _resume_after_modify does call cm.resume, but only on success path
        assert self.cm.is_paused(task_id)

    @pytest.mark.asyncio
    async def test_pause_site_3_pause_research_line3310(self):
        """
        research_api.py:3310 — explicit pause_research API call
        Pause: YES (cm.pause)
        Resume before _start_execution: NO — user must explicitly call resume_research
        Bug: YES — if user clicks "confirm start" while paused, stale pause blocks
        """
        task_id = "site3"
        self.cm.pause(task_id)
        assert self.cm.is_paused(task_id)

    @pytest.mark.asyncio
    async def test_pause_site_4_modify_research_line4112(self):
        """
        research_api.py:4112 — _handle_modify_research step 1
        Pause: YES (cm.pause)
        Resume before _start_execution: Same as site 2
        Bug: SAME — depends on _resume_after_modify success
        """
        task_id = "site4"
        self.cm.pause(task_id)
        assert self.cm.is_paused(task_id)

    @pytest.mark.asyncio
    async def test_pause_site_5_sse_disconnect_delayed(self):
        """
        research_api.py:3528 — _delayed_pause → pause_research
        Pause: YES (via pause_research → cm.pause)
        Resume before _start_execution: NO
        Bug: YES — SSE reconnect doesn't clear pause flag
        """
        task_id = "site5"
        self.cm.pause(task_id)
        assert self.cm.is_paused(task_id)
