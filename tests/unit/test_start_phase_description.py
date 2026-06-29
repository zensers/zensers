"""Test: start_phase SSE event includes description field"""

import asyncio
import pytest

from src.core.progress_streamer import ProgressStreamer


@pytest.fixture(autouse=True)
def cleanup_progress_streamer():
    yield
    for sid in list(ProgressStreamer._task_states.keys()):
        ProgressStreamer.clear_task(sid)


class TestStartPhaseDescription:
    def test_start_phase_includes_description_in_sse_event(self):
        sid = "desc_test_1"
        ProgressStreamer.get_or_create_task(sid)

        queue = asyncio.Queue()
        if sid not in ProgressStreamer._subscribers:
            ProgressStreamer._subscribers[sid] = set()
        ProgressStreamer._subscribers[sid].add(queue)

        ProgressStreamer.start_phase(
            sid, "execution", "Agent Execution",
            description="Running research agents...",
        )

        messages = []
        while not queue.empty():
            messages.append(queue.get_nowait())

        phase_start_msgs = [m for m in messages if m.event == "phase_start"]
        assert len(phase_start_msgs) == 1

        data = phase_start_msgs[0].data
        assert "description" in data
        assert data["description"] == "Running research agents..."
        assert data["phase_name"] == "Agent Execution"
        assert data["phase_id"] == "execution"

        ProgressStreamer.clear_task(sid)

    def test_start_phase_description_defaults_to_empty(self):
        sid = "desc_test_2"
        ProgressStreamer.get_or_create_task(sid)

        queue = asyncio.Queue()
        if sid not in ProgressStreamer._subscribers:
            ProgressStreamer._subscribers[sid] = set()
        ProgressStreamer._subscribers[sid].add(queue)

        ProgressStreamer.start_phase(sid, "quality_check", "Quality Check")

        messages = []
        while not queue.empty():
            messages.append(queue.get_nowait())

        phase_start_msgs = [m for m in messages if m.event == "phase_start"]
        assert len(phase_start_msgs) == 1

        data = phase_start_msgs[0].data
        assert data.get("description") == ""

        ProgressStreamer.clear_task(sid)

    def test_phase_name_present_in_sse_event(self):
        sid = "desc_test_3"
        ProgressStreamer.get_or_create_task(sid)

        queue = asyncio.Queue()
        if sid not in ProgressStreamer._subscribers:
            ProgressStreamer._subscribers[sid] = set()
        ProgressStreamer._subscribers[sid].add(queue)

        ProgressStreamer.start_phase(
            sid, "report_gen", "Report Generation",
            description="Generating research report...",
        )

        messages = []
        while not queue.empty():
            messages.append(queue.get_nowait())

        phase_start_msgs = [m for m in messages if m.event == "phase_start"]
        assert len(phase_start_msgs) == 1
        data = phase_start_msgs[0].data
        assert data["phase_name"] == "Report Generation"

        ProgressStreamer.clear_task(sid)
