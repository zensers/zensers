import asyncio

import pytest

from src.core.orchestrator.execution.control.background import (
    BackgroundExecutor,
    BackgroundExecutorConfig,
)
from src.core.orchestrator.execution.control.timeout import TimeoutConfig, TimeoutController


@pytest.mark.asyncio
async def test_timeout_controller_does_not_cut_off_when_timeout_is_omitted():
    controller = TimeoutController(TimeoutConfig())

    async def work():
        await asyncio.sleep(0.03)
        return {"success": True, "result": "complete"}

    result = await controller.execute_with_timeout(work, task_id="long-agent")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_timeout_controller_keeps_explicit_timeout_semantics():
    controller = TimeoutController(TimeoutConfig())

    async def work():
        await asyncio.sleep(0.05)
        return {"success": True}

    result = await controller.execute_with_timeout(work, task_id="bounded", timeout=0.001)
    assert result["success"] is False
    assert result["timeout"] == 0.001


@pytest.mark.asyncio
async def test_background_executor_has_no_implicit_timeout():
    executor = BackgroundExecutor(BackgroundExecutorConfig())

    async def work():
        await asyncio.sleep(0.03)
        return {"success": True, "result": "complete"}

    task_id = await executor.launch(work, parent_session_id="test")
    result = await executor.wait_for_result(task_id)
    assert result["success"] is True
    await executor.shutdown()


@pytest.mark.asyncio
async def test_background_executor_keeps_explicit_timeout_semantics():
    executor = BackgroundExecutor(BackgroundExecutorConfig())

    async def work():
        await asyncio.sleep(0.05)
        return {"success": True}

    task_id = await executor.launch(work, parent_session_id="test", timeout=0.001)
    await asyncio.sleep(0.02)
    assert executor.get_task_status(task_id).value == "timeout"
    await executor.shutdown()
