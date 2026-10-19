# -*- coding: utf-8 -*-
import asyncio
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


async def poll_until(
    check_fn: Callable,
    timeout: float = 600,
    poll_interval: float = 5,
    description: str = "condition",
) -> bool:
    started = time.monotonic()
    elapsed = 0.0
    deadline = started + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            if asyncio.iscoroutinefunction(check_fn):
                result = await asyncio.wait_for(check_fn(), timeout=remaining)
            else:
                result = check_fn()
            if result:
                return True
        except asyncio.TimeoutError:
            break
        except Exception as e:
            logger.debug(f"poll_until({description}) check raised: {e}")
        await asyncio.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
        elapsed = time.monotonic() - started
    logger.warning(f"poll_until({description}) timed out after {elapsed}s")
    return False


async def poll_status_until(
    client,
    task_id: str,
    target_status: str,
    timeout: float = 600,
    poll_interval: float = 5,
) -> dict:
    started = time.monotonic()
    elapsed = 0.0
    deadline = started + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            status = await asyncio.wait_for(client.get_status(task_id), timeout=remaining)
        except asyncio.TimeoutError:
            break
        cur = status.get("status", "unknown")
        if cur == target_status:
            return status
        if cur in ("failed", "error", "cancelled") and target_status not in ("failed", "error", "cancelled"):
            return status
        await asyncio.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))
        elapsed = time.monotonic() - started
    return {"status": "timeout", "task_id": task_id}
