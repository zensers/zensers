# -*- coding: utf-8 -*-
"""
P1 Fix: asyncio 任务异常未回收 + CR-FIX-2 磁盘恢复类型错误

测试验证:
- asyncio.create_task 的 done callback 捕获异常
- AgentSessionRegistry.load 接收 Path 而非 str
- 全局未处理异常处理器已注册

Bug 1: 852 次 "Task exception was never retrieved"
根因: create_task 无 done callback，异常被静默吞掉

Bug 2: CR-FIX-2 disk recovery failed: 'str' object has no attribute 'exists'
根因: AgentSessionRegistry.load 期望 Path 参数，但传入 str(_reg_path)
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path


class TestTaskExceptionCallback:
    """create_task 应有 done callback 捕获异常"""

    @pytest.mark.asyncio
    async def test_task_exception_is_logged(self):
        """异常任务应有 done callback 记录错误"""
        from src.core.orchestrator.execution.task_utils import safe_create_task

        async def failing_task():
            raise ValueError("test exception")

        with patch("src.core.orchestrator.execution.task_utils.logger") as mock_logger:
            task = safe_create_task(failing_task(), name="test_failing")
            await asyncio.sleep(0.1)
            logged_error = any(
                "test exception" in str(call)
                for call in mock_logger.error.call_args_list
            )
            assert logged_error, "任务异常应被 done callback 记录"

    @pytest.mark.asyncio
    async def test_safe_create_task_returns_task(self):
        """safe_create_task 应返回正常的 asyncio.Task"""
        from src.core.orchestrator.execution.task_utils import safe_create_task

        async def normal_task():
            return 42

        task = safe_create_task(normal_task(), name="test_normal")
        result = await task
        assert result == 42


class TestAgentSessionRegistryLoadType:
    """AgentSessionRegistry.load 应接收 Path 而非 str"""

    def test_load_expects_path_type(self):
        """load 方法签名应期望 Path 类型"""
        from src.core.agents.agent_session import AgentSessionRegistry
        import inspect
        sig = inspect.signature(AgentSessionRegistry.load)
        path_param = sig.parameters.get("path")
        if path_param and path_param.annotation != inspect.Parameter.empty:
            assert path_param.annotation is Path or "Path" in str(path_param.annotation), \
                f"load 的 path 参数应标注为 Path，实际: {path_param.annotation}"

    def test_engine_passes_path_not_str(self):
        """engine.py 中 CR-FIX-2 调用应传 Path 而非 str(Path)"""
        import re
        with open("src/core/orchestrator/execution/engine.py", "r", encoding="utf-8") as f:
            content = f.read()
        cr_fix2_block = content[content.find("CR-FIX-2"):content.find("CR-FIX-2") + 500]
        has_str_wrap = "str(_reg_path)" in cr_fix2_block or "str(reg_path)" in cr_fix2_block
        assert not has_str_wrap, "CR-FIX-2 应直接传 Path 对象，而非 str(Path)"


class TestGlobalAsyncioExceptionHandler:
    """应有全局 asyncio 未处理异常处理器"""

    def test_exception_handler_registered(self):
        """应注册 asyncio 未处理异常处理器"""
        from src.core.orchestrator.execution.task_utils import get_exception_handler
        handler = get_exception_handler()
        assert handler is not None, "应注册全局 asyncio 异常处理器"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
