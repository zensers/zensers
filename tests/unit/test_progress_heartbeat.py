"""Test: ProgressHeartbeat pushes heartbeat agent_messages during research execution"""

import asyncio
import pytest

from src.core.progress_streamer import ProgressStreamer, TaskState


@pytest.fixture(autouse=True)
def cleanup_progress_streamer():
    yield
    for sid in list(ProgressStreamer._task_states.keys()):
        ProgressStreamer.clear_task(sid)


class TestProgressHeartbeatStart:
    @pytest.mark.asyncio
    async def test_start_creates_async_task(self):
        from src.core.progress_heartbeat import ProgressHeartbeat
        sid = "hb_test_1"
        ProgressStreamer.get_or_create_task(sid)
        ProgressHeartbeat.start(sid)
        assert sid in ProgressHeartbeat._tasks
        assert not ProgressHeartbeat._tasks[sid].done()
        ProgressHeartbeat.stop(sid)

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        from src.core.progress_heartbeat import ProgressHeartbeat
        sid = "hb_test_2"
        ProgressStreamer.get_or_create_task(sid)
        ProgressHeartbeat.start(sid)
        task1 = ProgressHeartbeat._tasks[sid]
        ProgressHeartbeat.start(sid)
        task2 = ProgressHeartbeat._tasks[sid]
        assert task1 is task2
        ProgressHeartbeat.stop(sid)


class TestProgressHeartbeatStop:
    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        from src.core.progress_heartbeat import ProgressHeartbeat
        sid = "hb_test_3"
        ProgressStreamer.get_or_create_task(sid)
        ProgressHeartbeat.start(sid)
        assert sid in ProgressHeartbeat._tasks
        ProgressHeartbeat.stop(sid)
        assert sid not in ProgressHeartbeat._tasks

    def test_stop_noop_when_not_started(self):
        from src.core.progress_heartbeat import ProgressHeartbeat
        ProgressHeartbeat.stop("nonexistent_sid")


class TestProgressHeartbeatLoop:
    @pytest.mark.asyncio
    async def test_heartbeat_pushes_agent_message_while_running(self):
        from src.core.progress_heartbeat import ProgressHeartbeat
        from src.core.session_streamer import SessionStreamer
        from src.core.session_manager import SessionManager
        import tempfile

        sid = "hb_test_4"
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = SessionManager(storage_dir=tmpdir)
            mgr.create(sid, {"user_id": "u1", "conversation_history": [], "recent_events": []})

            ProgressStreamer.get_or_create_task(sid)
            ProgressStreamer._task_states[sid].status = "running"
            ProgressStreamer._task_states[sid].progress = 0.3

            original_interval = ProgressHeartbeat._INTERVAL_SECONDS
            ProgressHeartbeat._INTERVAL_SECONDS = 0.1

            collected_messages = []

            class Collector:
                @classmethod
                def push_agent_message(cls, session_id, data):
                    if data.get("action") == "heartbeat":
                        collected_messages.append(data)
                    SessionStreamer.push_agent_message(session_id, data)

            try:
                original_push = SessionStreamer.push_agent_message
                SessionStreamer.push_agent_message = Collector.push_agent_message

                ProgressHeartbeat.start(sid)
                await asyncio.sleep(0.35)
                ProgressHeartbeat.stop(sid)

                assert len(collected_messages) >= 1
                assert any("30%" in m.get("content", "") for m in collected_messages)
            finally:
                SessionStreamer.push_agent_message = original_push
                ProgressHeartbeat._INTERVAL_SECONDS = original_interval
                ProgressStreamer.clear_task(sid)

    @pytest.mark.asyncio
    async def test_heartbeat_stops_when_task_completed(self):
        from src.core.progress_heartbeat import ProgressHeartbeat

        sid = "hb_test_5"
        ProgressStreamer.get_or_create_task(sid)
        ProgressStreamer._task_states[sid].status = "running"
        ProgressStreamer._task_states[sid].progress = 0.5

        original_interval = ProgressHeartbeat._INTERVAL_SECONDS
        ProgressHeartbeat._INTERVAL_SECONDS = 0.1

        try:
            ProgressHeartbeat.start(sid)
            await asyncio.sleep(0.15)
            ProgressStreamer._task_states[sid].status = "completed"
            await asyncio.sleep(0.25)
            assert sid not in ProgressHeartbeat._tasks or ProgressHeartbeat._tasks.get(sid) is None
        finally:
            ProgressHeartbeat._INTERVAL_SECONDS = original_interval
            ProgressHeartbeat.stop(sid)
            ProgressStreamer.clear_task(sid)

    @pytest.mark.asyncio
    async def test_heartbeat_stops_when_task_not_found(self):
        from src.core.progress_heartbeat import ProgressHeartbeat

        sid = "hb_test_6_nonexistent"
        original_interval = ProgressHeartbeat._INTERVAL_SECONDS
        ProgressHeartbeat._INTERVAL_SECONDS = 0.1

        try:
            ProgressHeartbeat.start(sid)
            await asyncio.sleep(0.25)
            assert sid not in ProgressHeartbeat._tasks or ProgressHeartbeat._tasks.get(sid) is None
        finally:
            ProgressHeartbeat._INTERVAL_SECONDS = original_interval
            ProgressHeartbeat.stop(sid)
