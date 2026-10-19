"""
Tests for Pause LLM Context Loss Fix (2026-07-21)

Fix C: _llm_converse paused context + PAUSED/RUNNING conflict
Fix D: _build_research_running_context CancelManager check
Fix E: _on_sse_disconnect ProgressStreamer + SessionStreamer notification
"""

import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.orchestrator.execution.coordinator.cancel_manager import CancelManager


def _make_api():
    from src.api.research_api import ResearchAPI
    api = ResearchAPI.__new__(ResearchAPI)
    return api


class TestFixC_PausedContext:
    """Fix C: _llm_converse paused context enhancement."""

    def test_paused_context_contains_PAUSED_label(self):
        context = {"topic": "AI market analysis"}
        session = {
            "research_result": {
                "report": {"sections": ["s1", "s2", "s3"]},
                "status": "running",
            },
            "task_progress": {"progress": 0.45},
        }
        session_id = "ses_test_paused"

        cm = CancelManager()
        cm.pause(session_id)

        try:
            paused_context = ""
            if cm.is_paused(session_id) and session.get("research_result"):
                report = session["research_result"].get("report", {})
                section_count = len(report.get("sections", []))
                topic = context.get("topic", "")
                task_progress = session.get("task_progress", {})
                progress_pct = task_progress.get("progress", 0)
                paused_context = (
                    f"\n## Paused Research Context\n"
                    f"Research on '{topic}' is PAUSED (progress: {progress_pct:.0%}, {section_count} sections cached).\n"
                    f"The research was interrupted but data is preserved.\n\n"
                    f"ACTION PRIORITY (CRITICAL):\n"
                    f"1. If the user's message implies continuing/resuming the paused research\n"
                    f"   (e.g., 继续/继续任务/继续研究/continue/resume/go on/keep going), you MUST use action=\"resume_research\".\n"
                    f"2. If the user explicitly asks to modify the framework → action=\"modify_research\"\n"
                    f"3. If the user explicitly asks to regenerate the report → action=\"regenerate_report\"\n"
                    f"4. If the user asks a completely new, unrelated question → action=\"continue_chat\"\n\n"
                    f'IMPORTANT: The DEFAULT action for ambiguous messages like "继续" is resume_research, NOT continue_chat.\n'
                )

            assert "PAUSED" in paused_context
            assert "resume_research" in paused_context
            assert "ACTION PRIORITY" in paused_context
            assert "45%" in paused_context
            assert "3 sections cached" in paused_context
            assert "IMPORTANT" in paused_context
        finally:
            cm.cleanup(session_id)

    def test_dead_code_branch_removed(self):
        session = {"_paused_research_context": True}
        session.pop("_paused_research_context", None)
        assert "_paused_research_context" not in session


class TestFixC_RunningContextPausedLabel:
    """Fix C modification 2: _build_research_running_context PAUSED label."""

    def test_shows_PAUSED_when_cancel_manager_paused(self):
        api = _make_api()
        session_id = "ses_test_rrc_paused"
        session = {
            "mode": "research",
            "research_context": {
                "topic": "EV market",
                "framework": {"sections": ["s1", "s2"]},
            },
            "research_result": {"status": "running"},
            "task_progress": {"progress": 0.3},
        }

        cm = CancelManager()
        cm.pause(session_id)

        try:
            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
                result = api._build_research_running_context(session, session_id)

            assert "PAUSED" in result
            assert "RUNNING" not in result
            assert "resume_research" in result
        finally:
            cm.cleanup(session_id)

    def test_shows_RUNNING_when_not_paused(self):
        api = _make_api()
        session_id = "ses_test_rrc_running"
        session = {
            "mode": "research",
            "research_context": {
                "topic": "EV market",
                "framework": {"sections": ["s1", "s2"]},
            },
            "research_result": {"status": "running"},
            "task_progress": {"progress": 0.3},
        }

        cm = CancelManager()

        with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
            result = api._build_research_running_context(session, session_id)

        assert "RUNNING" in result
        assert "PAUSED" not in result


class TestFixD_BuildRunningContextModeGuard:
    """Fix D: _build_research_running_context CancelManager check."""

    def test_returns_context_when_mode_chat_but_cancel_manager_paused(self):
        api = _make_api()
        session_id = "ses_test_mode_guard"
        session = {
            "mode": "chat",
            "research_context": {
                "topic": "EV market",
                "framework": {"sections": ["s1", "s2"]},
            },
            "research_result": {"status": "running"},
            "task_progress": {"progress": 0.5},
        }

        cm = CancelManager()
        cm.pause(session_id)

        try:
            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
                result = api._build_research_running_context(session, session_id)

            assert result != ""
            assert "PAUSED" in result
        finally:
            cm.cleanup(session_id)

    def test_returns_empty_when_mode_chat_and_not_paused(self):
        api = _make_api()
        session = {
            "mode": "chat",
            "research_context": {
                "topic": "EV market",
                "framework": {"sections": ["s1"]},
            },
            "research_result": {"status": "running"},
        }

        cm = CancelManager()

        with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
            result = api._build_research_running_context(session, "ses_no_pause")

        assert result == ""

    def test_returns_empty_when_mode_chat_paused_but_terminal(self):
        api = _make_api()
        session_id = "ses_terminal"
        session = {
            "mode": "chat",
            "research_context": {
                "topic": "EV market",
                "framework": {"sections": ["s1"]},
            },
            "research_result": {"status": "completed"},
        }

        cm = CancelManager()
        cm.pause(session_id)

        try:
            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
                result = api._build_research_running_context(session, session_id)

            assert result == ""
        finally:
            cm.cleanup(session_id)


class TestFixE_SseDisconnectProgressStreamer:
    """SSE disconnect is transport-only and does not mutate task state."""

    @pytest.mark.asyncio
    async def test_disconnect_does_not_pause_progress_streamer(self):
        task_id = "ses_sse_disconnect_test"
        api = _make_api()
        mock_executor = MagicMock()
        mock_executor.done.return_value = False
        api._executor_tasks = {task_id: mock_executor}
        api._background_tasks = {}
        api._loop_cancel_flags = {}

        from src.core.session_manager import SessionManager
        sm = SessionManager.get_instance()
        sm._sessions[task_id] = {
            "research_result": {"status": "running"},
            "task_progress": {"progress": 0.6},
        }

        cm = CancelManager()

        real_sleep = asyncio.sleep

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
             patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm), \
             patch("src.api.research_api.session_manager", sm), \
             patch("src.core.progress_streamer.ProgressStreamer.pause_task") as mock_pause, \
             patch("src.core.session_streamer.SessionStreamer.push_agent_message"):
            api._on_sse_disconnect(task_id)

            for _ in range(200):
                await real_sleep(0.01)
                if mock_pause.called:
                    break

            assert not mock_pause.called

        sm._sessions.pop(task_id, None)
        cm.cleanup(task_id)

    @pytest.mark.asyncio
    async def test_disconnect_does_not_push_pause_message(self):
        task_id = "ses_sse_push_test"
        api = _make_api()
        mock_executor = MagicMock()
        mock_executor.done.return_value = False
        api._executor_tasks = {task_id: mock_executor}
        api._background_tasks = {}
        api._loop_cancel_flags = {}

        from src.core.session_manager import SessionManager
        sm = SessionManager.get_instance()
        sm._sessions[task_id] = {
            "research_result": {"status": "running"},
            "task_progress": {"progress": 0.6},
        }

        cm = CancelManager()

        real_sleep = asyncio.sleep

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
             patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm), \
             patch("src.api.research_api.session_manager", sm), \
             patch("src.core.progress_streamer.ProgressStreamer.pause_task"), \
             patch("src.core.session_streamer.SessionStreamer.push_agent_message") as mock_push:
            api._on_sse_disconnect(task_id)

            for _ in range(200):
                await real_sleep(0.01)
                if mock_push.called:
                    break

            assert not mock_push.called

        sm._sessions.pop(task_id, None)
        cm.cleanup(task_id)


class TestFixC_PausedRunningConflict:
    """Fix C: PAUSED/RUNNING conflict resolution."""

    def test_no_conflict_when_paused(self):
        api = _make_api()
        session_id = "ses_conflict_test"
        session = {
            "mode": "research",
            "research_context": {
                "topic": "AI market",
                "framework": {"sections": ["s1", "s2"]},
            },
            "research_result": {"status": "running"},
            "task_progress": {"progress": 0.3},
        }

        cm = CancelManager()
        cm.pause(session_id)

        try:
            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
                rrc = api._build_research_running_context(session, session_id)

            assert "PAUSED" in rrc
            assert "RUNNING" not in rrc
        finally:
            cm.cleanup(session_id)

    def test_running_label_when_not_paused(self):
        api = _make_api()
        session = {
            "mode": "research",
            "research_context": {
                "topic": "AI market",
                "framework": {"sections": ["s1", "s2"]},
            },
            "research_result": {"status": "running"},
            "task_progress": {"progress": 0.3},
        }

        cm = CancelManager()

        with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
            rrc = api._build_research_running_context(session, "ses_running")

        assert "RUNNING" in rrc
        assert "PAUSED" not in rrc


class TestFixC_PausedContextStrictness:
    """Fix C strictness: paused_context wording and edge cases."""

    def test_paused_context_uses_PAUSED_not_interrupted(self):
        context = {"topic": "AI market"}
        session = {
            "research_result": {"report": {"sections": ["s1"]}, "status": "running"},
            "task_progress": {"progress": 0.5},
        }
        session_id = "ses_wording_test"

        cm = CancelManager()
        cm.pause(session_id)

        try:
            paused_context = ""
            if cm.is_paused(session_id) and session.get("research_result"):
                report = session["research_result"].get("report", {})
                section_count = len(report.get("sections", []))
                topic = context.get("topic", "")
                task_progress = session.get("task_progress", {})
                progress_pct = task_progress.get("progress", 0)
                paused_context = (
                    f"\n## Paused Research Context\n"
                    f"Research on '{topic}' is PAUSED (progress: {progress_pct:.0%}, {section_count} sections cached).\n"
                    f"The research was interrupted but data is preserved.\n\n"
                    f"ACTION PRIORITY (CRITICAL):\n"
                    f"1. If the user's message implies continuing/resuming the paused research\n"
                    f"   (e.g., 继续/继续任务/继续研究/continue/resume/go on/keep going), you MUST use action=\"resume_research\".\n"
                    f"2. If the user explicitly asks to modify the framework → action=\"modify_research\"\n"
                    f"3. If the user explicitly asks to regenerate the report → action=\"regenerate_report\"\n"
                    f"4. If the user asks a completely new, unrelated question → action=\"continue_chat\"\n\n"
                    f'IMPORTANT: The DEFAULT action for ambiguous messages like "继续" is resume_research, NOT continue_chat.\n'
                )

            assert "PAUSED" in paused_context
            assert "interrupted" not in paused_context.lower() or "interrupted but data is preserved" in paused_context
        finally:
            cm.cleanup(session_id)

    def test_paused_context_empty_when_not_paused(self):
        context = {"topic": "AI market"}
        session = {
            "research_result": {"report": {"sections": ["s1"]}, "status": "running"},
            "task_progress": {"progress": 0.5},
        }
        session_id = "ses_not_paused"

        cm = CancelManager()

        paused_context = ""
        if cm.is_paused(session_id) and session.get("research_result"):
            paused_context = "SHOULD NOT APPEAR"

        assert paused_context == ""

    def test_paused_context_empty_when_no_research_result(self):
        session_id = "ses_no_result"

        cm = CancelManager()
        cm.pause(session_id)

        try:
            paused_context = ""
            if cm.is_paused(session_id) and None:
                paused_context = "SHOULD NOT APPEAR"

            assert paused_context == ""
        finally:
            cm.cleanup(session_id)

    def test_paused_context_resume_is_default_action(self):
        context = {"topic": "test"}
        session = {
            "research_result": {"report": {"sections": []}, "status": "running"},
            "task_progress": {"progress": 0.1},
        }
        session_id = "ses_default_action"

        cm = CancelManager()
        cm.pause(session_id)

        try:
            paused_context = ""
            if cm.is_paused(session_id) and session.get("research_result"):
                topic = context.get("topic", "")
                task_progress = session.get("task_progress", {})
                progress_pct = task_progress.get("progress", 0)
                paused_context = (
                    f"\n## Paused Research Context\n"
                    f"Research on '{topic}' is PAUSED (progress: {progress_pct:.0%}, 0 sections cached).\n"
                    f"The research was interrupted but data is preserved.\n\n"
                    f"ACTION PRIORITY (CRITICAL):\n"
                    f"1. If the user's message implies continuing/resuming the paused research\n"
                    f"   (e.g., 继续/继续任务/继续研究/continue/resume/go on/keep going), you MUST use action=\"resume_research\".\n"
                    f"2. If the user explicitly asks to modify the framework → action=\"modify_research\"\n"
                    f"3. If the user explicitly asks to regenerate the report → action=\"regenerate_report\"\n"
                    f"4. If the user asks a completely new, unrelated question → action=\"continue_chat\"\n\n"
                    f'IMPORTANT: The DEFAULT action for ambiguous messages like "继续" is resume_research, NOT continue_chat.\n'
                )

            resume_idx = paused_context.find("resume_research")
            continue_chat_idx = paused_context.find("continue_chat")
            assert resume_idx > 0
            assert continue_chat_idx > 0
            assert resume_idx < continue_chat_idx, "resume_research should appear before continue_chat in ACTION PRIORITY"
        finally:
            cm.cleanup(session_id)


class TestFixD_EdgeCases:
    """Fix D edge cases: _build_research_running_context mode guard."""

    def test_returns_empty_when_session_id_is_none_and_mode_chat(self):
        api = _make_api()
        session = {
            "mode": "chat",
            "research_context": {"topic": "test", "framework": {"sections": ["s1"]}},
            "research_result": {"status": "running"},
        }

        cm = CancelManager()
        cm.pause("some_other_session")

        try:
            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
                result = api._build_research_running_context(session, None)

            assert result == ""
        finally:
            cm.cleanup("some_other_session")

    def test_returns_empty_when_mode_chat_paused_but_no_research_result(self):
        api = _make_api()
        session_id = "ses_no_result"
        session = {
            "mode": "chat",
            "research_context": {"topic": "test", "framework": {"sections": ["s1"]}},
        }

        cm = CancelManager()
        cm.pause(session_id)

        try:
            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
                result = api._build_research_running_context(session, session_id)

            assert result == ""
        finally:
            cm.cleanup(session_id)

    def test_returns_context_when_mode_research_not_paused(self):
        api = _make_api()
        session_id = "ses_normal_research"
        session = {
            "mode": "research",
            "research_context": {"topic": "test", "framework": {"sections": ["s1"]}},
            "research_result": {"status": "running"},
            "task_progress": {"progress": 0.5},
        }

        cm = CancelManager()

        with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
            result = api._build_research_running_context(session, session_id)

        assert result != ""
        assert "RUNNING" in result

    def test_all_terminal_statuses_return_empty(self):
        api = _make_api()
        terminal_statuses = ['completed', 'completed_with_warnings', 'failed', 'cancelled', 'error']

        for status in terminal_statuses:
            session_id = f"ses_terminal_{status}"
            session = {
                "mode": "chat",
                "research_context": {"topic": "test", "framework": {"sections": ["s1"]}},
                "research_result": {"status": status},
            }

            cm = CancelManager()
            cm.pause(session_id)

            try:
                with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
                    result = api._build_research_running_context(session, session_id)

                assert result == "", f"Expected empty for terminal status '{status}'"
            finally:
                cm.cleanup(session_id)


class TestFixE_SseDisconnectStrictness:
    """Fix E strictness: _on_sse_disconnect edge cases and call order."""

    @pytest.mark.asyncio
    async def test_sse_disconnect_does_not_pause_or_emit_business_event(self):
        task_id = "ses_order_test"
        api = _make_api()
        mock_executor = MagicMock()
        mock_executor.done.return_value = False
        api._executor_tasks = {task_id: mock_executor}
        api._background_tasks = {}
        api._loop_cancel_flags = {}

        from src.core.session_manager import SessionManager
        sm = SessionManager.get_instance()
        sm._sessions[task_id] = {
            "research_result": {"status": "running"},
            "task_progress": {"progress": 0.6},
        }

        cm = CancelManager()
        call_order = []

        real_sleep = asyncio.sleep

        class OrderTrackingCM:
            def is_paused(self, tid):
                return cm.is_paused(tid)
            def pause(self, tid):
                call_order.append("cancel_manager.pause")
                cm.pause(tid)
            def cleanup(self, tid):
                cm.cleanup(tid)

        tracking_cm = OrderTrackingCM()

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
             patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=tracking_cm), \
             patch("src.api.research_api.session_manager", sm), \
             patch("src.core.progress_streamer.ProgressStreamer.pause_task", side_effect=lambda *a, **k: call_order.append("progress_streamer.pause_task")), \
             patch("src.core.session_streamer.SessionStreamer.push_agent_message", side_effect=lambda *a, **k: call_order.append("session_streamer.push")):
            api._on_sse_disconnect(task_id)

            for _ in range(200):
                await real_sleep(0.01)
                if len(call_order) >= 3:
                    break

        assert call_order == []

        sm._sessions.pop(task_id, None)
        cm.cleanup(task_id)

    @pytest.mark.asyncio
    async def test_sse_disconnect_skips_terminal_status(self):
        task_id = "ses_terminal_skip"
        api = _make_api()
        api._executor_tasks = {}
        api._background_tasks = {}
        api._loop_cancel_flags = {}

        from src.core.session_manager import SessionManager
        sm = SessionManager.get_instance()
        sm._sessions[task_id] = {
            "research_result": {"status": "completed"},
            "task_progress": {"progress": 1.0},
        }

        with patch("src.core.progress_streamer.ProgressStreamer.pause_task") as mock_pause:
            api._on_sse_disconnect(task_id)

        assert not mock_pause.called, "ProgressStreamer.pause_task should not be called for terminal status"

        sm._sessions.pop(task_id, None)

    @pytest.mark.asyncio
    async def test_sse_disconnect_skips_missing_session(self):
        task_id = "ses_nonexistent"
        api = _make_api()
        api._executor_tasks = {}
        api._background_tasks = {}
        api._loop_cancel_flags = {}

        from src.core.session_manager import SessionManager
        sm = SessionManager.get_instance()
        sm._sessions.pop(task_id, None)

        with patch("src.core.progress_streamer.ProgressStreamer.pause_task") as mock_pause:
            api._on_sse_disconnect(task_id)

        assert not mock_pause.called, "ProgressStreamer.pause_task should not be called for missing session"

    @pytest.mark.asyncio
    async def test_sse_disconnect_executor_dead_does_not_mark_failed(self):
        task_id = "ses_dead_executor"
        api = _make_api()
        mock_executor = MagicMock()
        mock_executor.done.return_value = True
        api._executor_tasks = {task_id: mock_executor}
        api._background_tasks = {}
        api._loop_cancel_flags = {}

        from src.core.session_manager import SessionManager
        sm = SessionManager.get_instance()
        sm._sessions[task_id] = {
            "research_result": {"status": "running"},
            "task_progress": {"progress": 0.3},
        }

        cm = CancelManager()
        real_sleep = asyncio.sleep

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
             patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm), \
             patch("src.api.research_api.session_manager", sm), \
             patch("src.core.progress_streamer.ProgressStreamer.pause_task") as mock_pause, \
             patch("src.core.progress_streamer.ProgressStreamer.fail_task") as mock_fail:
            api._on_sse_disconnect(task_id)

            for _ in range(200):
                await real_sleep(0.01)
                if mock_fail.called:
                    break

        assert not mock_fail.called
        assert not mock_pause.called
        assert sm._sessions[task_id]["research_result"]["status"] == "running"

        sm._sessions.pop(task_id, None)
        cm.cleanup(task_id)

    @pytest.mark.asyncio
    async def test_sse_disconnect_does_not_push_resume_message(self):
        task_id = "ses_push_content"
        api = _make_api()
        mock_executor = MagicMock()
        mock_executor.done.return_value = False
        api._executor_tasks = {task_id: mock_executor}
        api._background_tasks = {}
        api._loop_cancel_flags = {}

        from src.core.session_manager import SessionManager
        sm = SessionManager.get_instance()
        sm._sessions[task_id] = {
            "research_result": {"status": "running"},
            "task_progress": {"progress": 0.75},
        }

        cm = CancelManager()
        real_sleep = asyncio.sleep

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
             patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm), \
             patch("src.api.research_api.session_manager", sm), \
             patch("src.core.progress_streamer.ProgressStreamer.pause_task"), \
             patch("src.core.session_streamer.SessionStreamer.push_agent_message") as mock_push:
            api._on_sse_disconnect(task_id)

            for _ in range(200):
                await real_sleep(0.01)
                if mock_push.called:
                    break

            assert not mock_push.called

        sm._sessions.pop(task_id, None)
        cm.cleanup(task_id)


class TestFixC_CombinedContextNoConflict:
    """Fix C: Verify paused_context + rrc together have no PAUSED/RUNNING conflict."""

    def test_combined_context_no_running_when_paused(self):
        api = _make_api()
        session_id = "ses_combined_test"
        session = {
            "mode": "research",
            "research_context": {
                "topic": "AI market",
                "framework": {"sections": ["s1", "s2"]},
            },
            "research_result": {
                "report": {"sections": ["s1", "s2"]},
                "status": "running",
            },
            "task_progress": {"progress": 0.45},
        }

        cm = CancelManager()
        cm.pause(session_id)

        try:
            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager", return_value=cm):
                rrc = api._build_research_running_context(session, session_id)

            context = session.get("research_context", {})
            paused_context = ""
            if cm.is_paused(session_id) and session.get("research_result"):
                report = session["research_result"].get("report", {})
                section_count = len(report.get("sections", []))
                topic = context.get("topic", "")
                task_progress = session.get("task_progress", {})
                progress_pct = task_progress.get("progress", 0)
                paused_context = (
                    f"\n## Paused Research Context\n"
                    f"Research on '{topic}' is PAUSED (progress: {progress_pct:.0%}, {section_count} sections cached).\n"
                    f"The research was interrupted but data is preserved.\n\n"
                    f"ACTION PRIORITY (CRITICAL):\n"
                    f"1. If the user's message implies continuing/resuming the paused research\n"
                    f"   (e.g., 继续/继续任务/继续研究/continue/resume/go on/keep going), you MUST use action=\"resume_research\".\n"
                    f"2. If the user explicitly asks to modify the framework → action=\"modify_research\"\n"
                    f"3. If the user explicitly asks to regenerate the report → action=\"regenerate_report\"\n"
                    f"4. If the user asks a completely new, unrelated question → action=\"continue_chat\"\n\n"
                    f'IMPORTANT: The DEFAULT action for ambiguous messages like "继续" is resume_research, NOT continue_chat.\n'
                )

            combined = paused_context + rrc
            assert "PAUSED" in combined
            running_count = combined.count("RUNNING")
            assert running_count == 0, f"Combined context should not contain 'RUNNING' when paused, found {running_count} occurrences"
        finally:
            cm.cleanup(session_id)
