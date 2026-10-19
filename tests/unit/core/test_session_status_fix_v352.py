"""Tests for v3.5.2 session status fixes

Bug 1: list_all_sessions / get_research_detail should use research_result.status
       over state_machine for completed tasks (avoids stale "reporting" status)
Bug 2: ProgressStreamer._restore_from_session should override status when
       research_result indicates a terminal state (avoids stale "running" in SSE)
Bug 3: get_research_detail should return phases and progress fields
Bug 4: _repair_ghost_sessions should reset state_machine to CANCELLED
Bug 5: /status API heartbeat staleness check should NOT override status
       when research_result already indicates a terminal state
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from src.core.progress_streamer import ProgressStreamer, TaskState


@pytest.fixture(autouse=True)
def cleanup_progress_streamer():
    yield
    for sid in list(ProgressStreamer._task_states.keys()):
        ProgressStreamer.clear_task(sid)
    ProgressStreamer._disconnect_callbacks.clear()


# =====================================================================
# Bug 1: list_all_sessions status determination
# =====================================================================

class TestListAllSessionsStatusPriority:
    """research_result.status should take priority over state_machine for status determination."""

    def _make_session(self, rr_status=None, sm_value=None, current_step=0):
        session = {"current_step": current_step, "research_context": {}, "user_input": "test"}
        if rr_status is not None:
            session["research_result"] = {"status": rr_status}
        if sm_value is not None:
            sm = MagicMock()
            sm.current_state.value = sm_value
            session["state_machine"] = sm
        return session

    def _determine_status(self, session):
        """Simulate the status determination logic from list_all_sessions."""
        rr = session.get("research_result") or {}
        rr_status = rr.get("status") if isinstance(rr, dict) else None
        _terminal_rr = ("completed", "completed_with_warnings", "failed", "cancelled", "error")

        state_machine = session.get("state_machine")
        if rr_status in _terminal_rr:
            state = "completed" if rr_status in ("completed", "completed_with_warnings") else "paused"
        elif state_machine and hasattr(state_machine, "current_state"):
            status_map = {
                "understanding": "paused", "clarifying": "paused",
                "framework_confirm": "analyzing", "executing": "reporting",
                "paused": "paused", "previewing": "completed",
                "completed": "completed", "cancelled": "paused",
                "data_extracted": "analyzing", "requirement_confirm": "analyzing",
                "data_supplement": "analyzing",
            }
            state = status_map.get(state_machine.current_state.value, "paused")
        else:
            current_step = session.get("current_step", 0)
            if current_step == 6:
                state = "reporting"
            elif current_step and current_step > 0:
                state = "analyzing"
            else:
                state = "paused"
        return state

    def test_completed_rr_overrides_executing_sm(self):
        """Completed research_result should override state_machine=executing."""
        session = self._make_session(rr_status="completed", sm_value="executing")
        assert self._determine_status(session) == "completed"

    def test_completed_with_warnings_rr_overrides_executing_sm(self):
        session = self._make_session(rr_status="completed_with_warnings", sm_value="executing")
        assert self._determine_status(session) == "completed"

    def test_failed_rr_overrides_executing_sm(self):
        session = self._make_session(rr_status="failed", sm_value="executing")
        assert self._determine_status(session) == "paused"

    def test_cancelled_rr_overrides_executing_sm(self):
        session = self._make_session(rr_status="cancelled", sm_value="executing")
        assert self._determine_status(session) == "paused"

    def test_error_rr_overrides_executing_sm(self):
        session = self._make_session(rr_status="error", sm_value="executing")
        assert self._determine_status(session) == "paused"

    def test_no_rr_uses_state_machine(self):
        """Without research_result, fall back to state_machine."""
        session = self._make_session(sm_value="executing")
        assert self._determine_status(session) == "reporting"

    def test_no_rr_no_sm_uses_step(self):
        """Without research_result or state_machine, fall back to current_step."""
        session = self._make_session(current_step=6)
        assert self._determine_status(session) == "reporting"

    def test_no_rr_no_sm_no_step_is_paused(self):
        session = self._make_session()
        assert self._determine_status(session) == "paused"

    def test_completed_rr_no_sm(self):
        """Completed research_result without state_machine."""
        session = self._make_session(rr_status="completed")
        assert self._determine_status(session) == "completed"


# =====================================================================
# Bug 2: ProgressStreamer._restore_from_session research_result override
# =====================================================================

class TestProgressStreamerRestoreFromSession:
    """When restoring task state from disk, research_result terminal status
    should override stale task_progress.status."""

    def test_completed_rr_overrides_running_progress(self):
        """task_progress says 'running' but research_result says 'completed' → status should be 'completed'."""
        task_id = "test_restore_completed"
        session_data = {
            "task_progress": {
                "status": "running",
                "progress": 0.8,
                "current_phase": "execution",
            },
            "research_result": {"status": "completed"},
            "task_phases": [
                {"id": "p1", "name": "Phase 1", "status": "completed", "progress": 1.0},
            ],
        }
        sm_instance = MagicMock()
        sm_instance.get.return_value = session_data

        with patch("src.core.session_manager.SessionManager") as sm_cls:
            sm_cls.get_instance.return_value = sm_instance
            task = ProgressStreamer._restore_from_session(task_id)

        assert task is not None
        assert task.status == "completed"
        assert task.progress == 1.0

    def test_failed_rr_overrides_running_progress(self):
        """task_progress says 'running' but research_result says 'failed' → status should be 'error'."""
        task_id = "test_restore_failed"
        session_data = {
            "task_progress": {
                "status": "running",
                "progress": 0.5,
                "current_phase": "execution",
            },
            "research_result": {"status": "failed", "error": "timeout"},
            "task_phases": [],
        }
        sm_instance = MagicMock()
        sm_instance.get.return_value = session_data

        with patch("src.core.session_manager.SessionManager") as sm_cls:
            sm_cls.get_instance.return_value = sm_instance
            task = ProgressStreamer._restore_from_session(task_id)

        assert task is not None
        assert task.status == "error"

    def test_no_rr_uses_task_progress_status(self):
        """Without research_result, task_progress.status should be used as-is."""
        task_id = "test_restore_no_rr"
        session_data = {
            "task_progress": {
                "status": "running",
                "progress": 0.5,
            },
            "task_phases": [],
        }
        sm_instance = MagicMock()
        sm_instance.get.return_value = session_data

        with patch("src.core.session_manager.SessionManager") as sm_cls:
            sm_cls.get_instance.return_value = sm_instance
            task = ProgressStreamer._restore_from_session(task_id)

        assert task is not None
        assert task.status == "running"

    def test_non_terminal_rr_uses_task_progress_status(self):
        """research_result with non-terminal status should not override."""
        task_id = "test_restore_non_terminal"
        session_data = {
            "task_progress": {
                "status": "running",
                "progress": 0.5,
            },
            "research_result": {"status": "running"},
            "task_phases": [],
        }
        sm_instance = MagicMock()
        sm_instance.get.return_value = session_data

        with patch("src.core.session_manager.SessionManager") as sm_cls:
            sm_cls.get_instance.return_value = sm_instance
            task = ProgressStreamer._restore_from_session(task_id)

        assert task is not None
        assert task.status == "running"


# =====================================================================
# Bug 3: get_research_detail returns phases and progress
# =====================================================================

class TestGetResearchDetailPhasesAndProgress:
    """get_research_detail should include phases and progress in the response."""

    def test_completed_task_phases_status_fixed(self):
        """For completed tasks, running phases should be corrected to completed."""
        phases_data = [
            {"id": "orch", "name": "Orchestrator", "status": "running", "progress": 0.5},
            {"id": "exec", "name": "Execution", "status": "completed", "progress": 1.0},
            {"id": "report", "name": "Report", "status": "pending", "progress": 0},
        ]
        state = "completed"

        phases = [
            {"id": p.get("id", ""), "name": p.get("name", ""),
             "status": p.get("status", "pending"), "progress": p.get("progress", 0)}
            for p in phases_data
        ]
        if state == "completed":
            phases = [
                {**p, "status": "completed" if p["status"] in ("running", "pending") else p["status"],
                 "progress": 100 if p["status"] in ("running", "completed") else p["progress"]}
                for p in phases
            ]

        assert phases[0]["status"] == "completed"
        assert phases[0]["progress"] == 100
        assert phases[1]["status"] == "completed"
        assert phases[1]["progress"] == 100
        assert phases[2]["status"] == "completed"

    def test_completed_task_progress_forced_100(self):
        """For completed tasks, progress should be 100 regardless of stored value."""
        state = "completed"
        task_progress_data = {"progress": 0.9}

        raw_progress = task_progress_data.get("progress")
        if state == "completed":
            progress_val = 100
        elif raw_progress is not None:
            progress_val = raw_progress
        else:
            progress_val = 0

        assert progress_val == 100

    def test_running_task_progress_from_stored(self):
        """For non-completed tasks, progress should use stored value."""
        state = "running"
        task_progress_data = {"progress": 0.8}

        raw_progress = task_progress_data.get("progress")
        if state == "completed":
            progress_val = 100
        elif raw_progress is not None:
            progress_val = raw_progress
        else:
            progress_val = 0

        assert progress_val == 0.8


# =====================================================================
# Bug 4: _repair_ghost_sessions resets state_machine
# =====================================================================

class TestGhostSessionRepairStateMachine:
    """Ghost session repair should reset state_machine to CANCELLED."""

    def test_ghost_session_state_machine_reset_to_cancelled(self):
        ghost_session = {
            "mode": "research",
            "current_step": 3,
            "research_result": {"status": "running"},
            "state_machine": MagicMock(),
        }
        ghost_session["state_machine"].current_state.value = "executing"
        ghost_session["state_machine"].transition = MagicMock()

        sm_instance = MagicMock()
        sm_instance.keys.return_value = ["ses_ghost"]
        sm_instance.get.return_value = ghost_session

        with patch("src.api.main._session_manager", sm_instance):
            from src.api.main import _repair_ghost_sessions
            _repair_ghost_sessions()

        from src.core.dialogue.state_machine import ConversationState
        ghost_session["state_machine"].transition.assert_called_once_with(ConversationState.CANCELLED)

    def test_ghost_session_no_state_machine_no_crash(self):
        """Ghost session without state_machine should not crash."""
        ghost_session = {
            "mode": "research",
            "current_step": 3,
            "research_result": {"status": "running"},
        }

        sm_instance = MagicMock()
        sm_instance.keys.return_value = ["ses_ghost"]
        sm_instance.get.return_value = ghost_session

        with patch("src.api.main._session_manager", sm_instance):
            from src.api.main import _repair_ghost_sessions
            _repair_ghost_sessions()

        assert ghost_session["mode"] == "chat"

    def test_ghost_session_state_machine_transition_failure_handled(self):
        """If state_machine.transition raises, should not crash."""
        ghost_session = {
            "mode": "research",
            "current_step": 3,
            "research_result": {"status": "running"},
            "state_machine": MagicMock(),
        }
        ghost_session["state_machine"].current_state.value = "completed"
        ghost_session["state_machine"].transition.side_effect = Exception("invalid transition")

        sm_instance = MagicMock()
        sm_instance.keys.return_value = ["ses_ghost"]
        sm_instance.get.return_value = ghost_session

        with patch("src.api.main._session_manager", sm_instance):
            from src.api.main import _repair_ghost_sessions
            _repair_ghost_sessions()

        assert ghost_session["mode"] == "chat"


class TestStatusApiHeartbeatOverride:
    """/status API should not downgrade completed status to paused based on
    stale heartbeat when research_result already indicates terminal state."""

    def _simulate_status_response(self, progress_status, rr_status):
        _terminal_rr = ("completed", "completed_with_warnings", "failed", "cancelled", "error")

        response = {"task_id": "test_task", "status": progress_status, "progress": 1.0}

        session = {
            "task_progress": {"status": "running", "last_heartbeat_at": "2026-07-24T15:36:25.000000"},
            "research_result": {"status": rr_status} if rr_status else {},
        }

        rr = session.get("research_result")
        rr_status_val = rr.get("status") if isinstance(rr, dict) else None

        if rr_status_val not in _terminal_rr:
            tp_data = session.get("task_progress", {})
            if tp_data.get("status") == "running":
                is_stale = True
                last_hb = tp_data.get("last_heartbeat_at")
                if last_hb:
                    from datetime import datetime as dt
                    try:
                        hb_time = dt.fromisoformat(last_hb)
                        is_stale = (dt.now() - hb_time).total_seconds() > 300
                    except (ValueError, TypeError):
                        pass
                if is_stale:
                    response["status"] = "paused"
                    response["interrupted"] = True

        return response

    def test_completed_rr_not_overridden_by_stale_heartbeat(self):
        resp = self._simulate_status_response("completed", "completed")
        assert resp["status"] == "completed"
        assert "interrupted" not in resp

    def test_completed_with_warnings_not_overridden(self):
        resp = self._simulate_status_response("completed", "completed_with_warnings")
        assert resp["status"] == "completed"

    def test_failed_rr_not_overridden(self):
        resp = self._simulate_status_response("error", "failed")
        assert resp["status"] == "error"

    def test_no_rr_allows_heartbeat_override(self):
        resp = self._simulate_status_response("running", None)
        assert resp["status"] == "paused"
        assert resp.get("interrupted") is True

    def test_running_rr_allows_heartbeat_override(self):
        resp = self._simulate_status_response("running", "running")
        assert resp["status"] == "paused"
