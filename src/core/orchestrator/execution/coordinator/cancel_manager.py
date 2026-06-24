"""
取消/暂停/恢复管理器

职责：
- 取消：bool 标志 + Engine 批次间检查
- 暂停：bool 标志 + asyncio.Condition
- 单一真相源：所有暂停/取消检查统一调 is_paused() / is_cancelled()
"""
import asyncio
import logging
import threading
from asyncio import Condition
from enum import Enum
from typing import Dict

from src.core.orchestrator.execution.task_utils import safe_create_task


class CancelReason(Enum):
    """取消原因（保留供 AgentCoordinator 等使用）"""
    USER_REQUEST = "user_request"
    TIMEOUT = "timeout"
    SHUTDOWN = "shutdown"

logger = logging.getLogger(__name__)


class CancelManager:
    """
    取消/暂停信号管理器。全局单例，通过 get_cancel_manager() 获取。

    设计原则：
    - 取消：bool 标志 + Engine 批次间检查。不做双通道、不做级联。
    - 暂停：bool 标志 + asyncio.Condition。
      Condition.wait() 原子性地释放锁并等待，notify() 唤醒后重新获取锁。
      不存在 Event.clear() 丢失信号的竞态问题。
    - 单一真相源：不复制状态到 session["paused"]。
      所有暂停/取消检查统一调 is_paused() / is_cancelled()。
    """

    def __init__(self):
        self._cancelled: Dict[str, bool] = {}
        self._paused: Dict[str, bool] = {}
        self._pause_conditions: Dict[str, Condition] = {}
        self._notify_tasks: Dict[str, asyncio.Task] = {}

    # ========== 取消 ==========

    def cancel(self, task_id: str) -> None:
        """
        设取消标志。唤醒暂停中的 Engine（如果有）。
        必须 notify Condition，否则 wait_for_resume_or_cancel 的
        await cond.wait() 永远不会返回，Engine 卡死在暂停循环。
        """
        self._cancelled[task_id] = True
        logger.info(f"[CTRL] CANCEL task={task_id}")

        cond = self._pause_conditions.get(task_id)
        if cond:
            async def _notify():
                async with cond:
                    cond.notify_all()
            try:
                t = safe_create_task(_notify(), name="cancel_manager.cancel_notify")
                self._notify_tasks[task_id] = t
                t.add_done_callback(lambda _: self._notify_tasks.pop(task_id, None))
            except RuntimeError:
                pass

    def is_cancelled(self, task_id: str) -> bool:
        return self._cancelled.get(task_id, False)

    # ========== 暂停/恢复 ==========

    def pause(self, task_id: str) -> None:
        """设暂停标志"""
        self._paused[task_id] = True
        logger.info(f"[CTRL] PAUSE task={task_id}")

    def resume(self, task_id: str) -> None:
        """
        清暂停标志 + 唤醒 Engine。
        create_task 结果存入 _notify_tasks，防止 3.12+ GC。
        """
        self._paused[task_id] = False
        logger.info(f"[CTRL] RESUME task={task_id}")
        cond = self._pause_conditions.get(task_id)
        if cond:
            async def _notify():
                async with cond:
                    cond.notify_all()
            try:
                t = safe_create_task(_notify(), name="cancel_manager.resume_notify")
                self._notify_tasks[task_id] = t
                t.add_done_callback(lambda _: self._notify_tasks.pop(task_id, None))
            except RuntimeError:
                pass

    def is_paused(self, task_id: str) -> bool:
        """单一真相源。所有暂停检查都调此方法，不再读 session["paused"]"""
        return self._paused.get(task_id, False)

    # ========== 等待 ==========

    async def wait_for_resume_or_cancel(self, task_id: str) -> str:
        """
        等待恢复或取消。返回 "resumed" 或 "cancelled"。

        使用 asyncio.Condition 而非 Event：
        - Condition.wait() 原子性释放锁 + 等待
        - notify() 唤醒后重新获取锁
        - 不存在 Event.clear() 吞信号的竞态

        加 asyncio.wait_for 超时兜底，防止 resume() 因 bug 未调用
        导致 Engine 永久阻塞。超时 3600 秒后自动恢复。
        """
        if task_id not in self._pause_conditions:
            self._pause_conditions[task_id] = Condition()
        cond = self._pause_conditions[task_id]
        async with cond:
            while self._paused.get(task_id, False):
                if self._cancelled.get(task_id, False):
                    logger.info(f"[CTRL] PAUSE_DONE task={task_id} result=cancelled")
                    return "cancelled"
                try:
                    await asyncio.wait_for(cond.wait(), timeout=3600)
                except asyncio.TimeoutError:
                    self._paused[task_id] = False
                    logger.warning(f"[CTRL] PAUSE_TIMEOUT task={task_id}, auto-resuming")
                    return "resumed"
        result = "cancelled" if self._cancelled.get(task_id, False) else "resumed"
        logger.info(f"[CTRL] PAUSE_DONE task={task_id} result={result}")
        return result

    # ========== 清理 ==========

    def cleanup(self, task_id: str) -> None:
        """
        任务完成后清理。
        清理前必须唤醒可能的等待者，否则 asyncio 报
        "Task was destroyed but it is pending"。
        """
        cond = self._pause_conditions.get(task_id)
        if cond:
            async def _notify():
                async with cond:
                    cond.notify_all()
            try:
                t = safe_create_task(_notify(), name="cancel_manager.cleanup_notify")
                self._notify_tasks[f"{task_id}_cleanup"] = t
                t.add_done_callback(lambda _: self._notify_tasks.pop(f"{task_id}_cleanup", None))
            except RuntimeError:
                pass
        self._cancelled.pop(task_id, None)
        self._paused.pop(task_id, None)
        self._pause_conditions.pop(task_id, None)


# ========== 全局单例 ==========

_manager: CancelManager = None
_manager_lock = threading.Lock()


def get_cancel_manager() -> CancelManager:
    """全局统一单例。AgentCoordinator 也调此方法获取。"""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = CancelManager()
    return _manager
