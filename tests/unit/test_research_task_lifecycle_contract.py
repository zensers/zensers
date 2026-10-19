"""TDD contracts for recoverable research task lifecycle semantics."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.task_persistence import (
    PersistentTask,
    TaskCheckpoint,
    TaskPersistenceManager,
    TaskState,
)


def test_report_chapter_lookup_accepts_legacy_routing_section_id():
    from types import SimpleNamespace
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator

    aggregate = SimpleNamespace(
        layered_content={"analysis": {"agent_market": {"metric": "100"}}},
        content_provenance={
            "agent_market": {"section_target": "section_0_market_size"},
        },
    )
    data, _ = ReportOrchestrator._extract_chapter_data(
        aggregate, "section_0", [],
    )
    assert data == {"metric": "100"}


def test_empty_report_output_is_not_a_successful_research_result():
    from src.core.orchestrator.orchestrator import _validate_report_generation_output

    with pytest.raises(ValueError, match="sections"):
        _validate_report_generation_output({"topic": "demo", "sections": []})


def test_cancelled_task_is_recoverable_and_keeps_checkpoint(tmp_path):
    manager = TaskPersistenceManager(str(tmp_path))
    task = manager.create_task("research", {"topic": "demo"}, task_id="research_lifecycle")
    task.start()
    task.add_checkpoint(TaskCheckpoint("cp-1", task.task_id, "collection", 1, 2, {"section": "section_0"}))

    task.cancel("user requested stop")
    manager.save_task(task)
    restored = manager.load_task(task.task_id)

    assert restored.status.state is TaskState.CANCELLED
    assert restored.error is None
    assert restored.get_latest_checkpoint().checkpoint_id == "cp-1"
    assert restored.can_resume()


def test_interrupted_task_is_recoverable_without_time_based_cleanup(tmp_path):
    manager = TaskPersistenceManager(str(tmp_path))
    task = manager.create_task("research", {}, task_id="research_interrupted")
    task.start()
    manager.save_task(task)

    recovered = manager.mark_interrupted(task.task_id, "worker restarted")
    assert recovered.status.state is TaskState.INTERRUPTED
    assert recovered.can_resume()
    assert manager.load_task(task.task_id).status.state is TaskState.INTERRUPTED


def test_execution_ownership_round_trips_and_can_be_released(tmp_path):
    manager = TaskPersistenceManager(str(tmp_path))
    task = manager.create_task("research", {}, task_id="owned_task")
    task.claim_execution(run_id="run-1", owner="research-worker", process_id=123)
    manager.save_task(task)

    restored = manager.load_task(task.task_id)
    assert restored.run_id == "run-1"
    assert restored.execution_owner == "research-worker"
    assert restored.process_id == 123

    restored.release_execution()
    manager.save_task(restored)
    released = manager.load_task(task.task_id)
    assert released.run_id is None
    assert released.execution_owner is None
    assert released.process_id is None


@pytest.mark.asyncio
async def test_sse_disconnect_does_not_change_business_state():
    from src.api.research_api import ResearchAPI

    api = ResearchAPI()
    task_id = "sse_transport_only"
    session = {"research_result": {"status": "running"}}
    api._executor_tasks[task_id] = asyncio.create_task(asyncio.sleep(60))
    try:
        with patch("src.api.research_api.session_manager") as session_manager:
            session_manager.get.return_value = session
            with patch("src.api.research_api.safe_create_task") as create_task:
                api._on_sse_disconnect(task_id)
                create_task.assert_not_called()
        assert session["research_result"]["status"] == "running"
    finally:
        api._executor_tasks[task_id].cancel()
        with pytest.raises(asyncio.CancelledError):
            await api._executor_tasks[task_id]


@pytest.mark.asyncio
async def test_cancel_then_resume_uses_checkpoint_instead_of_becoming_failed(tmp_path):
    from src.api.research_api import ResearchAPI

    task_id = "cancel_resume_contract"
    task = PersistentTask(task_id, "research", {})
    task.start()
    task.add_checkpoint(TaskCheckpoint("cp-1", task_id, "collection", 1, 2, {"pending": ["section_1"]}))
    manager = TaskPersistenceManager(str(tmp_path))
    manager.save_task(task)

    session = {
        "status": "running",
        "mode": "research",
        "current_step": 1,
        "research_result": {"status": "running"},
        "research_context": {"framework": {"sections": ["section_0", "section_1"]}},
    }
    api = ResearchAPI()
    api._executor_tasks[task_id] = asyncio.create_task(asyncio.sleep(60))
    try:
        with patch("src.api.research_api.session_manager") as session_manager, \
             patch("src.core.task_persistence.TaskPersistenceManager", return_value=manager), \
             patch("src.core.progress_streamer.ProgressStreamer.cancel_task"), \
             patch("src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager") as get_cm:
            session_manager.get.return_value = session
            cm = MagicMock()
            get_cm.return_value = cm
            cancelled = await api.cancel_research(task_id)
            assert cancelled["status"] == "cancelled"
            assert manager.load_task(task_id).status.state is TaskState.CANCELLED
            assert manager.load_task(task_id).error is None
            cm.cleanup.assert_not_called()
    finally:
        current = api._executor_tasks.get(task_id)
        if current and not current.done():
            current.cancel()
            with pytest.raises(asyncio.CancelledError):
                await current


@pytest.mark.asyncio
async def test_stopped_chat_mode_routes_new_message_through_intent_router():
    """A resumably stopped task must not be implicitly resumed by the UI/API."""
    from src.api.research_api import ResearchAPI
    from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState

    task_id = "stopped_chat_intent_route"
    state_machine = ConversationStateMachine(research_id=task_id)
    state_machine.transition(ConversationState.CANCELLED)
    session = {
        "mode": "chat",
        "status": "cancelled",
        "state_machine": state_machine,
        "research_result": {"status": "cancelled"},
        "research_context": {"topic": "demo", "framework": {"sections": ["section_1"]}},
        "conversation_history": [],
    }
    api = ResearchAPI()

    with patch("src.api.research_api.session_manager") as session_manager, \
         patch.object(api, "_handle_research_msg", new_callable=AsyncMock) as route_message:
        session_manager.get.return_value = session
        route_message.return_value = {"status": "resumed", "action": "resume_research"}

        result = await api._handle_user_message(task_id, "继续刚才的研究")

        route_message.assert_awaited_once_with(task_id, "继续刚才的研究", session)
        assert result["action"] == "resume_research"


def test_history_status_is_consistent_with_recovered_progress_state():
    """List and detail must show the same paused state after a restart."""
    from types import SimpleNamespace
    from src.api.main import _resolve_history_status

    session = {
        "state_machine": {"current_state": "executing"},
        "current_step": 2,
        "research_result": {"status": "running"},
    }
    progress = SimpleNamespace(status="paused", current_phase="agent_execution")
    with patch("src.api.main.ProgressStreamer.get_task_state", return_value=progress):
        assert _resolve_history_status(session, "history-consistency") == "paused"


def test_history_status_falls_back_to_persisted_state_without_progress_snapshot():
    from src.api.main import _resolve_history_status

    session = {
        "state_machine": {"current_state": "executing"},
        "research_result": {"status": "running"},
    }
    with patch("src.api.main.ProgressStreamer.get_task_state", return_value=None):
        assert _resolve_history_status(session, "history-fallback") == "reporting"


def test_history_message_keeps_response_id_for_client_idempotency():
    from src.api.main import _build_message_entry

    message = _build_message_entry(
        {"role": "assistant", "content": "answer", "response_id": "resp-1"},
        "fallback-1",
    )
    assert message["response_id"] == "resp-1"


def test_parallel_tasks_keep_control_signals_isolated():
    from src.api.research_executor import ResearchExecutor
    from src.core.orchestrator.execution.coordinator.cancel_manager import CancelManager

    executor = ResearchExecutor()
    executor._inject_in_progress.add("task-a")
    assert "task-a" in executor._inject_in_progress
    assert "task-b" not in executor._inject_in_progress
    executor._inject_in_progress.discard("task-a")

    controls = CancelManager()
    controls.pause("task-a")
    controls.cancel("task-b")
    assert controls.is_paused("task-a") is True
    assert controls.is_paused("task-b") is False
    assert controls.is_cancelled("task-a") is False
    assert controls.is_cancelled("task-b") is True
    controls.cleanup("task-a")
    controls.cleanup("task-b")


@pytest.mark.asyncio
async def test_paused_natural_language_direction_change_routes_to_modify():
    """Direction changes are decided by the LLM, not a frontend resume call."""
    from src.api.research_api import ResearchAPI
    from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState

    task_id = "paused_direction_change"
    machine = ConversationStateMachine(research_id=task_id)
    machine.transition(ConversationState.CANCELLED)
    session = {
        "mode": "chat",
        "status": "cancelled",
        "state_machine": machine,
        "research_result": {"status": "cancelled"},
        "research_context": {"topic": "光伏行业", "framework": {"sections": ["市场规模"]}},
    }
    api = ResearchAPI()
    api._llm_converse = AsyncMock(return_value={
        "action": "modify_research",
        "modifications": {"add_aspects": ["竞争格局"]},
        "adjustment": "增加竞争格局分析",
    })
    api._handle_modify_research = AsyncMock(return_value={"status": "paused", "action": "modify_research"})

    with patch("src.api.research_api.session_manager") as session_manager:
        session_manager.get.return_value = session
        result = await api._handle_research_msg(task_id, "增加竞争格局分析", session)

    api._handle_modify_research.assert_awaited_once_with(
        session_id=task_id,
        modifications={"add_aspects": ["竞争格局"]},
        adjustment="增加竞争格局分析",
    )
    assert result["action"] == "modify_research"
