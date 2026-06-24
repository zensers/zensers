# -*- coding: utf-8 -*-
"""
Asyncio task utilities — safe task creation with exception handling

P1 Fix: 852 次 "Task exception was never retrieved"
根因: create_task 无 done callback，异常被静默吞掉

修复: safe_create_task 自动添加 done callback 记录异常
"""

import asyncio
import logging
from typing import Optional, Coroutine, Any

logger = logging.getLogger(__name__)

_global_handler_registered = False


def _task_exception_callback(task: asyncio.Task) -> None:
    try:
        exception = task.exception()
        if exception is not None:
            logger.error(
                f"Task '{task.get_name()}' exception was retrieved: {exception}",
                exc_info=exception,
            )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in task exception callback: {e}")


def safe_create_task(
    coro: Coroutine[Any, Any, Any],
    *,
    name: Optional[str] = None,
) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name or "unnamed")
    task.add_done_callback(_task_exception_callback)
    return task


def _asyncio_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    message = context.get("message", "Unknown asyncio exception")
    exception = context.get("exception")
    if exception is not None:
        logger.error(
            f"Asyncio unhandled exception: {message}",
            exc_info=exception,
        )
    else:
        logger.error(f"Asyncio unhandled exception: {message}")


def get_exception_handler():
    return _asyncio_exception_handler


def register_global_exception_handler() -> None:
    global _global_handler_registered
    if _global_handler_registered:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(_asyncio_exception_handler)
        _global_handler_registered = True
        logger.info("Global asyncio exception handler registered")
    except RuntimeError:
        pass
