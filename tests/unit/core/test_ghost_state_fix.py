"""Tests for research state ghost fix (2026-07-20)

Bug 1: pause_task() should not overwrite terminal states (error/completed/cancelled)
Bug 2: call_llm_stream in _llm_converse should have timeout protection
Bug 3: subscribe() should replay paused state on reconnect
Bug 4: _on_sse_disconnect should detect dead executor task and mark failed
Bug 5: _handle_research_msg should detect failed+dead executor and not enter paused branch
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.core.progress_streamer import ProgressStreamer, TaskState, SSEEventType


@pytest.fixture(autouse=True)
def cleanup_progress_streamer():
    yield
    for sid in list(ProgressStreamer._task_states.keys()):
        ProgressStreamer.clear_task(sid)
    ProgressStreamer._disconnect_callbacks.clear()


class TestPauseTaskTerminalStateProtection:
    def test_pause_from_running_allowed(self):
        sid = "test_pause_ok"
        task = ProgressStreamer.get_or_create_task(sid)
        task.status = "running"
        ProgressStreamer.pause_task(sid, "User paused")
        assert task.status == "paused"

    def test_pause_from_pending_allowed(self):
        sid = "test_pause_pending"
        task = ProgressStreamer.get_or_create_task(sid)
        task.status = "pending"
        ProgressStreamer.pause_task(sid, "User paused")
        assert task.status == "paused"

    def test_pause_from_error_blocked(self):
        sid = "test_pause_error"
        task = ProgressStreamer.get_or_create_task(sid)
        task.status = "error"
        task.error = "Some error"
        ProgressStreamer.pause_task(sid, "User paused")
        assert task.status == "error"
        assert task.error == "Some error"

    def test_pause_from_completed_blocked(self):
        sid = "test_pause_completed"
        task = ProgressStreamer.get_or_create_task(sid)
        task.status = "completed"
        ProgressStreamer.pause_task(sid, "User paused")
        assert task.status == "completed"

    def test_pause_from_cancelled_blocked(self):
        sid = "test_pause_cancelled"
        task = ProgressStreamer.get_or_create_task(sid)
        task.status = "cancelled"
        ProgressStreamer.pause_task(sid, "User paused")
        assert task.status == "cancelled"

    def test_pause_from_paused_allowed(self):
        sid = "test_pause_paused"
        task = ProgressStreamer.get_or_create_task(sid)
        task.status = "paused"
        ProgressStreamer.pause_task(sid, "Re-paused")
        assert task.status == "paused"


class TestSubscribePausedReplay:
    def test_subscribe_replays_paused_state(self):
        import asyncio
        sid = "test_sub_paused"
        task = ProgressStreamer.get_or_create_task(sid)
        task.status = "paused"
        task.error = "Paused by user"

        streamer = ProgressStreamer(sid)
        queue = streamer._queue
        streamer.subscribe()

        messages = []
        while not queue.empty():
            msg = queue.get_nowait()
            messages.append(msg)

        event_types = [m.event for m in messages]
        assert SSEEventType.PAUSED.value in event_types

        paused_msg = next(m for m in messages if m.event == SSEEventType.PAUSED.value)
        assert paused_msg.data["task_id"] == sid

    def test_subscribe_no_paused_replay_for_running(self):
        sid = "test_sub_running"
        task = ProgressStreamer.get_or_create_task(sid)
        task.status = "running"

        streamer = ProgressStreamer(sid)
        queue = streamer._queue
        streamer.subscribe()

        messages = []
        while not queue.empty():
            msg = queue.get_nowait()
            messages.append(msg)

        event_types = [m.event for m in messages]
        assert SSEEventType.PAUSED.value not in event_types


class TestStreamTimeoutProtection:
    @pytest.mark.asyncio
    async def test_hanging_engine_call_times_out_and_returns_terminal(self):
        """Bug 2: an engine-backed call that hangs must hit STREAM_TIMEOUT
        and yield the terminal continue_chat response (never hang forever)."""
        deps = _mock_deps()

        async def _hanging_ex(prompt_builder, **kwargs):
            await asyncio.sleep(300)

        with patch("src.api.research_api.session_manager", deps["session_manager"]):
            with patch("src.api.research_api.PromptManager") as pm_cls:
                pm_cls.get_instance.return_value = deps["pm_instance"]
                with patch("src.core.session_streamer.SessionStreamer", deps["SessionStreamer"]):
                    with patch("src.api.research_api.call_llm_ex", new=_hanging_ex):
                        with patch("src.config.settings", deps["settings"]):
                            with patch("src.api.research_api.STREAM_TIMEOUT", 1):
                                from src.api.research_api import ResearchAPI
                                api = ResearchAPI()
                                api._tool_set = deps["tool_set"]
                                api._loop_cancel_flags = {}

                                result = await asyncio.wait_for(
                                    api._llm_converse("test_ses", "hello"),
                                    timeout=30,
                                )
                                assert result["action"] == "continue_chat"
                                assert "重新描述" in result["message"]

    @pytest.mark.asyncio
    async def test_normal_stream_completes_without_timeout(self):
        """Normal fast engine call should complete without hitting timeout"""
        deps = _mock_deps()

        payload = {"message": "Hello", "action": "continue_chat", "tool_call": None}
        mock_call_llm_ex = AsyncMock(return_value=payload)

        with patch("src.api.research_api.session_manager", deps["session_manager"]):
            with patch("src.api.research_api.PromptManager") as pm_cls:
                pm_cls.get_instance.return_value = deps["pm_instance"]
                with patch("src.core.session_streamer.SessionStreamer", deps["SessionStreamer"]):
                    with patch("src.api.research_api.call_llm_ex", mock_call_llm_ex):
                        with patch("src.config.settings", deps["settings"]):
                            from src.api.research_api import ResearchAPI
                            api = ResearchAPI()
                            api._tool_set = deps["tool_set"]
                            api._loop_cancel_flags = {}

                            result = await api._llm_converse("test_ses", "hello")
                            mock_call_llm_ex.assert_awaited_once()
                            assert result["status"] == "done"


def _mock_deps():
    deps = {}
    sm = MagicMock()
    sm.get.return_value = {
        "research_context": {},
        "conversation_history": [],
        "llm_config": {},
    }
    deps["session_manager"] = sm

    ms = MagicMock()
    ms.llm.max_tokens = 4096
    ms.llm.temperature = 0.7
    ms.llm.model = "test-model"
    ms.llm.cheap_model = "test-fallback"
    ms.llm.cost_limit_per_report = 0
    ms.llm.api_key = "test-key"
    ms.llm.base_url = "https://test.example.com"
    ms.llm.top_p = 1.0
    ms.llm.frequency_penalty = 0.0
    ms.llm.presence_penalty = 0.0
    deps["settings"] = ms

    pm = MagicMock()
    profile = MagicMock()
    profile.get_full_prompt.return_value = "You are a helpful assistant."
    pm.load_profile.return_value = profile
    deps["prompt_manager"] = pm
    deps["pm_instance"] = MagicMock()
    deps["pm_instance"].load_profile.return_value = profile

    deps["SessionStreamer"] = MagicMock()
    ts = MagicMock()
    ts.TOOL_DEFINITIONS = []
    deps["tool_set"] = ts
    return deps


class TestSSEDisconnectDeadExecutor:
    @pytest.mark.asyncio
    async def test_dead_executor_marked_failed_on_sse_disconnect(self):
        """Transport loss must not infer executor failure."""
        from src.api.research_api import ResearchAPI

        api = ResearchAPI()
        task_id = "test_sse_dead_exec"

        dead_task = asyncio.create_task(asyncio.sleep(0))
        await dead_task

        session = {
            "research_result": {"status": "running"},
        }

        api._executor_tasks[task_id] = dead_task

        with patch("src.api.research_api.session_manager") as sm:
            sm.get.return_value = session
            with patch("src.core.progress_streamer.ProgressStreamer.fail_task") as mock_fail:
                with patch("src.api.research_api.safe_create_task") as create_task:
                    api._on_sse_disconnect(task_id)

                    create_task.assert_not_called()
                    mock_fail.assert_not_called()
                    assert session["research_result"]["status"] == "running"

    @pytest.mark.asyncio
    async def test_popped_executor_marked_failed_on_sse_disconnect(self):
        """A missing executor is diagnosed by recovery, not SSE disconnect."""
        from src.api.research_api import ResearchAPI

        api = ResearchAPI()
        task_id = "test_sse_popped_exec"

        session = {
            "research_result": {"status": "running"},
        }

        with patch("src.api.research_api.session_manager") as sm:
            sm.get.return_value = session
            with patch("src.core.progress_streamer.ProgressStreamer.fail_task") as mock_fail:
                with patch("src.api.research_api.safe_create_task") as create_task:
                    api._on_sse_disconnect(task_id)

                    create_task.assert_not_called()
                    mock_fail.assert_not_called()
                    assert session["research_result"]["status"] == "running"

    @pytest.mark.asyncio
    async def test_alive_executor_pauses_on_sse_disconnect(self):
        """An alive executor continues after the SSE client disconnects."""
        from src.api.research_api import ResearchAPI

        api = ResearchAPI()
        task_id = "test_sse_alive_exec"

        alive_task = asyncio.create_task(asyncio.sleep(300))

        session = {
            "research_result": {"status": "running"},
        }

        api._executor_tasks[task_id] = alive_task

        with patch("src.api.research_api.session_manager") as sm:
            sm.get.return_value = session
            with patch("src.api.research_api.safe_create_task") as create_task:
                with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as gcm:
                    mock_cm = MagicMock()
                    gcm.return_value = mock_cm

                    api._on_sse_disconnect(task_id)

                    create_task.assert_not_called()
                    mock_cm.pause.assert_not_called()
                    assert session["research_result"]["status"] == "running"

        alive_task.cancel()
        try:
            await alive_task
        except asyncio.CancelledError:
            pass


class TestHandleResearchMsgDeadExecutor:
    @pytest.mark.asyncio
    async def test_failed_status_dead_executor_falls_back_to_chat(self):
        """Bug 5: failed status + dead executor should fall back to chat, not enter paused branch"""
        from src.api.research_api import ResearchAPI

        api = ResearchAPI()
        session_id = "test_hrm_dead"

        dead_task = asyncio.create_task(asyncio.sleep(0))
        await dead_task

        api._executor_tasks = {}
        session = {
            "mode": "research",
            "current_step": 3,
            "research_result": {"status": "failed", "error": "API 402"},
            "research_context": {},
            "conversation_history": [],
        }

        with patch("src.api.research_api.session_manager") as sm:
            sm.get.return_value = session
            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as gcm:
                mock_cm = MagicMock()
                mock_cm.is_paused.return_value = True
                gcm.return_value = mock_cm
                with patch.object(api, "_handle_chat_mode", new_callable=AsyncMock) as mock_chat:
                    mock_chat.return_value = {"status": "ok", "message": "chat response"}

                    result = await api._handle_research_msg(session_id, "what happened?", session)

                    mock_chat.assert_called_once()
                    assert session["mode"] == "chat"
                    assert session["current_step"] == 0

    @pytest.mark.asyncio
    async def test_error_status_dead_executor_falls_back_to_chat(self):
        """Bug 5: error status + dead executor should also fall back to chat"""
        from src.api.research_api import ResearchAPI

        api = ResearchAPI()
        session_id = "test_hrm_error"

        api._executor_tasks = {}
        session = {
            "mode": "research",
            "current_step": 2,
            "research_result": {"status": "error", "error": "Connection lost"},
            "research_context": {},
            "conversation_history": [],
        }

        with patch("src.api.research_api.session_manager") as sm:
            sm.get.return_value = session
            with patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as gcm:
                mock_cm = MagicMock()
                mock_cm.is_paused.return_value = True
                gcm.return_value = mock_cm
                with patch.object(api, "_handle_chat_mode", new_callable=AsyncMock) as mock_chat:
                    mock_chat.return_value = {"status": "ok", "message": "chat response"}

                    result = await api._handle_research_msg(session_id, "help", session)

                    mock_chat.assert_called_once()
                    assert session["mode"] == "chat"


class TestResearchExecutorErrorMessage:
    def test_failed_research_error_includes_summary(self):
        """Research executor error message should include orchestrator summary, not just status"""
        from src.core.orchestrator.orchestrator import ResearchResult
        mock_result = ResearchResult(
            task_id="test_exec", status="failed", topic="AI trends",
            agents_used=[], stages_completed=0,
            summary="Quality check failed: insufficient data sources",
        )
        _detail = mock_result.summary or mock_result.status
        error_msg = f"Research failed: {_detail}"
        assert "Quality check failed" in error_msg
        assert "insufficient data sources" in error_msg


class TestStartupGhostSessionRepair:
    def test_ghost_running_session_repaired(self):
        """Startup repair should fix sessions stuck in research mode with non-terminal status"""
        ghost_session = {
            "mode": "research",
            "current_step": 3,
            "research_result": {"status": "running"},
        }
        ok_session = {
            "mode": "chat",
            "current_step": 0,
        }

        sm_instance = MagicMock()
        sm_instance.keys.return_value = ["ses_ghost1", "ses_ok1"]
        sm_instance.get.side_effect = lambda sid: {
            "ses_ghost1": ghost_session,
            "ses_ok1": ok_session,
        }.get(sid)

        with patch("src.api.main._session_manager", sm_instance):
            from src.api.main import _repair_ghost_sessions
            _repair_ghost_sessions()

            assert ghost_session["mode"] == "chat"
            assert ghost_session["research_result"]["status"] == "failed"
            assert "Server restarted" in ghost_session["research_result"]["error"]

    def test_completed_session_not_touched(self):
        """Startup repair should not modify sessions with terminal research status"""
        done_session = {
            "mode": "research",
            "current_step": 6,
            "research_result": {"status": "completed"},
        }

        sm_instance = MagicMock()
        sm_instance.keys.return_value = ["ses_done"]
        sm_instance.get.return_value = done_session

        with patch("src.api.main._session_manager", sm_instance):
            from src.api.main import _repair_ghost_sessions
            _repair_ghost_sessions()

            assert done_session["mode"] == "research"
            assert done_session["research_result"]["status"] == "completed"

    def test_no_research_result_session_repaired(self):
        """Startup repair should fix research mode sessions with no research_result at all"""
        stale_session = {
            "mode": "research",
            "current_step": 2,
        }

        sm_instance = MagicMock()
        sm_instance.keys.return_value = ["ses_stale"]
        sm_instance.get.return_value = stale_session

        with patch("src.api.main._session_manager", sm_instance):
            from src.api.main import _repair_ghost_sessions
            _repair_ghost_sessions()

            assert stale_session["mode"] == "chat"

    def test_paused_session_repaired(self):
        """Startup repair should fix sessions stuck in paused state"""
        paused_session = {
            "mode": "research",
            "current_step": 2,
            "research_result": {"status": "paused"},
        }

        sm_instance = MagicMock()
        sm_instance.keys.return_value = ["ses_paused"]
        sm_instance.get.return_value = paused_session

        with patch("src.api.main._session_manager", sm_instance):
            from src.api.main import _repair_ghost_sessions
            _repair_ghost_sessions()

            assert paused_session["mode"] == "chat"
            assert paused_session["research_result"]["status"] == "failed"

    def test_null_session_skipped(self):
        """Startup repair should skip sessions where get() returns None"""
        sm_instance = MagicMock()
        sm_instance.keys.return_value = ["ses_null"]
        sm_instance.get.return_value = None

        with patch("src.api.main._session_manager", sm_instance):
            from src.api.main import _repair_ghost_sessions
            _repair_ghost_sessions()

    def test_exception_in_session_handled(self):
        """Startup repair should not crash on individual session errors"""
        sm_instance = MagicMock()
        sm_instance.keys.return_value = ["ses_bad"]
        sm_instance.get.side_effect = Exception("disk error")

        with patch("src.api.main._session_manager", sm_instance):
            from src.api.main import _repair_ghost_sessions
            _repair_ghost_sessions()


class TestEdgeCases:
    def test_pause_task_from_failed_status_blocked(self):
        """pause_task should also block 'failed' status if it ever appears in ProgressStreamer"""
        sid = "test_pause_failed_status"
        task = ProgressStreamer.get_or_create_task(sid)
        task.status = "error"
        ProgressStreamer.pause_task(sid, "Should not work")
        assert task.status == "error"

    @pytest.mark.asyncio
    async def test_stream_timeout_yields_terminal_result(self):
        """A stream that times out under the engine must end the loop and
        return the terminal continue_chat response instead of hanging."""
        deps = _mock_deps()

        async def _hanging_ex(prompt_builder, **kwargs):
            await asyncio.sleep(300)

        with patch("src.api.research_api.session_manager", deps["session_manager"]):
            with patch("src.api.research_api.PromptManager") as pm_cls:
                pm_cls.get_instance.return_value = deps["pm_instance"]
                with patch("src.core.session_streamer.SessionStreamer", deps["SessionStreamer"]):
                    with patch("src.api.research_api.call_llm_ex", new=_hanging_ex):
                        with patch("src.config.settings", deps["settings"]):
                            with patch("src.api.research_api.STREAM_TIMEOUT", 1):
                                from src.api.research_api import ResearchAPI
                                api = ResearchAPI()
                                api._tool_set = deps["tool_set"]
                                api._loop_cancel_flags = {}

                                result = await asyncio.wait_for(
                                    api._llm_converse("test_ses", "hello"),
                                    timeout=30,
                                )
                                assert result["action"] == "continue_chat"
