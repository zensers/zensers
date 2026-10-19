"""Contracts for isolation between concurrently active research tasks."""

import asyncio

import pytest


def test_progress_states_are_keyed_by_task_id():
    from src.core.progress_streamer import ProgressStreamer

    task_a = "parallel-progress-a"
    task_b = "parallel-progress-b"
    for task_id in (task_a, task_b):
        ProgressStreamer._task_states.pop(task_id, None)
        ProgressStreamer._subscribers.pop(task_id, None)

    ProgressStreamer.update_progress(task_a, 0.25, phase_id="phase-a")
    ProgressStreamer.update_progress(task_b, 0.75, phase_id="phase-b")

    assert ProgressStreamer.get_task_state(task_a).progress == 0.25
    assert ProgressStreamer.get_task_state(task_a).current_phase == "phase-a"
    assert ProgressStreamer.get_task_state(task_b).progress == 0.75
    assert ProgressStreamer.get_task_state(task_b).current_phase == "phase-b"

    for task_id in (task_a, task_b):
        ProgressStreamer._task_states.pop(task_id, None)
        ProgressStreamer._subscribers.pop(task_id, None)


def test_session_events_are_keyed_by_session_id():
    from src.core.session_streamer import SessionStreamer

    session_a = "parallel-session-a"
    session_b = "parallel-session-b"
    for session_id in (session_a, session_b):
        SessionStreamer._recent_messages.pop(session_id, None)

    SessionStreamer.push_chat_response(session_a, {"message": "A", "response_id": "r-a"})
    SessionStreamer.push_chat_response(session_b, {"message": "B", "response_id": "r-b"})

    events_a = SessionStreamer._recent_messages[session_a]
    events_b = SessionStreamer._recent_messages[session_b]
    assert [event.data["message"] for event in events_a] == ["A"]
    assert [event.data["message"] for event in events_b] == ["B"]
    assert events_a[0].data["session_id"] == session_a
    assert events_b[0].data["session_id"] == session_b

    for session_id in (session_a, session_b):
        SessionStreamer._recent_messages.pop(session_id, None)


@pytest.mark.asyncio
async def test_pause_and_resume_signals_do_not_cross_tasks():
    from src.core.orchestrator.execution.coordinator.cancel_manager import CancelManager

    manager = CancelManager()
    manager.pause("parallel-control-a")
    manager.pause("parallel-control-b")

    wait_a = asyncio.create_task(manager.wait_for_resume_or_cancel("parallel-control-a"))
    wait_b = asyncio.create_task(manager.wait_for_resume_or_cancel("parallel-control-b"))
    await asyncio.sleep(0)

    manager.resume("parallel-control-a")
    assert await asyncio.wait_for(wait_a, timeout=1) == "resumed"
    assert not wait_b.done()

    manager.resume("parallel-control-b")
    assert await asyncio.wait_for(wait_b, timeout=1) == "resumed"
    manager.cleanup("parallel-control-a")
    manager.cleanup("parallel-control-b")
