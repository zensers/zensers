# -*- coding: utf-8 -*-
"""
Progress Streamer
================

Responsibilities:
- Convert ProgressTracker updates to SSE event stream
- Support multiple clients subscribing to the same task
- Auto cleanup completed task subscriptions

Usage example:
    # In FastAPI endpoint
    @app.get("/api/v1/stream/{task_id}")
    async def stream_progress(task_id: str):
        streamer = ProgressStreamer(task_id)
        return StreamingResponse(
            streamer.generate(),
            media_type="text/event-stream",
        )
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, AsyncGenerator
from enum import Enum

logger = logging.getLogger(__name__)


class SSEEventType(str, Enum):
    """SSE event type"""
    PROGRESS = "progress"
    PHASE_START = "phase_start"
    PHASE_COMPLETE = "phase_complete"
    ERROR = "error"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    RESUMED = "resumed"
    CHAT_RESPONSE = "chat_response"


@dataclass
class SSEMessage:
    """SSE message"""
    event: str
    data: Dict[str, Any]
    id: Optional[str] = None
    retry: Optional[int] = None

    def to_sse(self) -> str:
        """Convert to SSE format string"""
        lines = []
        if self.id:
            lines.append(f"id: {self.id}")
        if self.event:
            lines.append(f"event: {self.event}")
        if self.retry:
            lines.append(f"retry: {self.retry}")
        lines.append(f"data: {json.dumps(self.data, ensure_ascii=False)}")
        return "\n".join(lines) + "\n\n"


@dataclass
class TaskPhase:
    """Task phase"""
    id: str
    name: str
    description: str = ""
    status: str = "pending"  # pending, running, completed, error
    progress: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class TaskState:
    """Task state"""
    task_id: str
    status: str = "pending"  # pending, running, paused, completed, error, cancelled
    progress: float = 0.0
    phases: List[TaskPhase] = field(default_factory=list)
    current_phase: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_chat_response: Optional[Dict[str, Any]] = None  # for replay on reconnect


class ProgressStreamer:
    """
    Progress Streamer

    Converts task progress to SSE event stream for frontend real-time subscription.
    """

    # Class-level task state storage (supports multiple clients subscribing to same task)
    _task_states: Dict[str, TaskState] = {}
    _subscribers: Dict[str, Set[asyncio.Queue]] = {}
    _STATE_TTL_SECONDS: float = 300.0  # keep terminal states alive for reconnecting clients
    # Disconnect callbacks: {task_id: callable} — called when last SSE subscriber disconnects
    _disconnect_callbacks: Dict[str, Any] = {}

    @classmethod
    def set_disconnect_callback(cls, task_id: str, callback: Any) -> None:
        """Register a callback to fire when the last SSE subscriber for this task disconnects."""
        cls._disconnect_callbacks[task_id] = callback

    @classmethod
    def clear_disconnect_callback(cls, task_id: str) -> None:
        """Remove a previously registered disconnect callback."""
        cls._disconnect_callbacks.pop(task_id, None)

    @classmethod
    def has_active_subscribers(cls, task_id: str) -> bool:
        """Check if a task has any active SSE subscribers."""
        return bool(cls._subscribers.get(task_id))

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._queue: asyncio.Queue = asyncio.Queue()

    @classmethod
    def _persist_to_session(cls, task_id: str) -> None:
        """将 ProgressStreamer 的状态持久化到 SessionManager (自动写磁盘)"""
        task = cls._task_states.get(task_id)
        if task is None:
            return
        try:
            from src.core.session_manager import SessionManager
            sm = SessionManager.get_instance()
            session = sm.get(task_id)
            if session is None:
                return

            # 使用 update() 批量写入，减少磁盘 IO
            update_payload = {
                "task_progress": {
                    "status": task.status,
                    "progress": task.progress,
                    "current_phase": task.current_phase,
                    "error": task.error,
                    "started_at": task.started_at.isoformat() if task.started_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                    "last_heartbeat_at": datetime.now().isoformat(),
                },
                "task_phases": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "status": p.status,
                        "progress": p.progress,
                        "started_at": p.started_at.isoformat() if p.started_at else None,
                        "completed_at": p.completed_at.isoformat() if p.completed_at else None,
                    }
                    for p in task.phases
                ],
            }

            if task.last_chat_response:
                update_payload["last_chat_response"] = task.last_chat_response

            session.update(update_payload)
        except Exception as e:
            logger.warning(f"Failed to persist task state for {task_id}: {e}")

    @classmethod
    def _restore_from_session(cls, task_id: str) -> Optional[TaskState]:
        """从 SessionManager 恢复 ProgressStreamer 状态"""
        try:
            from src.core.session_manager import SessionManager
            sm = SessionManager.get_instance()
            session = sm.get(task_id)
            if session is None:
                return None

            tp = session.get("task_progress")
            if tp is None:
                return None

            task = TaskState(task_id=task_id)
            task.status = tp.get("status", "pending")
            task.progress = tp.get("progress", 0.0)
            task.current_phase = tp.get("current_phase")
            task.error = tp.get("error")
            task.last_chat_response = session.get("last_chat_response")

            if tp.get("started_at"):
                try:
                    task.started_at = datetime.fromisoformat(tp["started_at"])
                except (ValueError, TypeError):
                    pass
            if tp.get("completed_at"):
                try:
                    task.completed_at = datetime.fromisoformat(tp["completed_at"])
                except (ValueError, TypeError):
                    pass

            task.result = session.get("task_result")

            phases_data = session.get("task_phases", [])
            for pd in phases_data:
                phase = TaskPhase(
                    id=pd["id"],
                    name=pd["name"],
                    description=pd.get("description", ""),
                    status=pd.get("status", "pending"),
                    progress=pd.get("progress", 0.0),
                )
                if pd.get("started_at"):
                    try:
                        phase.started_at = datetime.fromisoformat(pd["started_at"])
                    except (ValueError, TypeError):
                        pass
                if pd.get("completed_at"):
                    try:
                        phase.completed_at = datetime.fromisoformat(pd["completed_at"])
                    except (ValueError, TypeError):
                        pass
                task.phases.append(phase)

            return task
        except Exception as e:
            logger.warning(f"Failed to restore task state for {task_id}: {e}")
            return None

    @classmethod
    def get_or_create_task(cls, task_id: str) -> TaskState:
        """Get or create task state (prefer memory, restore from disk on miss)"""
        if task_id not in cls._task_states:
            # Try to restore from SessionManager (persisted state)
            restored = cls._restore_from_session(task_id)
            if restored is not None:
                cls._task_states[task_id] = restored
            else:
                cls._task_states[task_id] = TaskState(task_id=task_id)
            cls._subscribers[task_id] = set()
        return cls._task_states[task_id]

    @classmethod
    def update_progress(
        cls,
        task_id: str,
        progress: float,
        phase_id: Optional[str] = None,
        message: Optional[str] = None,
    ):
        """
        Update task progress

        Args:
            task_id: Task ID
            progress: Progress value (0.0-1.0)
            phase_id: Current phase ID
            message: Progress message
        """
        task = cls.get_or_create_task(task_id)
        task.progress = progress
        task.status = "running"

        if phase_id:
            task.current_phase = phase_id
            for phase in task.phases:
                if phase.id == phase_id:
                    phase.progress = progress
                    phase.status = "running"

        # Notify all subscribers
        cls._notify_subscribers(task_id, SSEEventType.PROGRESS, {
            "task_id": task_id,
            "progress": progress,
            "phase_id": phase_id,
            "message": message or "",
            "timestamp": datetime.now().isoformat(),
        })

        logger.debug(f"Progress update: {task_id} -> {progress:.1%}")
        cls._persist_to_session(task_id)

    @classmethod
    def start_phase(
        cls,
        task_id: str,
        phase_id: str,
        phase_name: str,
        description: str = "",
    ):
        """Start a phase"""
        task = cls.get_or_create_task(task_id)

        # Check if phase already exists
        phase = next((p for p in task.phases if p.id == phase_id), None)
        if not phase:
            phase = TaskPhase(
                id=phase_id,
                name=phase_name,
                description=description,
            )
            task.phases.append(phase)

        phase.status = "running"
        phase.started_at = datetime.now()
        task.current_phase = phase_id
        task.status = "running"

        # Notify subscribers
        cls._notify_subscribers(task_id, SSEEventType.PHASE_START, {
            "task_id": task_id,
            "phase_id": phase_id,
            "phase_name": phase_name,
            "description": description,
            "timestamp": datetime.now().isoformat(),
        })

        # Push agent_message for inline chat display
        try:
            from src.core.session_streamer import SessionStreamer
            SessionStreamer.push_agent_message(task_id, {
                "agent_id": phase_id,
                "agent_name": phase_name,
                "action": "analyzing",
                "content": f"Starting {phase_name}...",
            })
        except ImportError:
            pass

        logger.info(f"Phase started: {task_id}/{phase_id} - {phase_name}")
        cls._persist_to_session(task_id)

    @classmethod
    def complete_phase(
        cls,
        task_id: str,
        phase_id: str,
        success: bool = True,
    ):
        """Complete a phase"""
        task = cls.get_or_create_task(task_id)

        for phase in task.phases:
            if phase.id == phase_id:
                phase.status = "completed" if success else "error"
                phase.progress = 1.0 if success else phase.progress
                phase.completed_at = datetime.now()
                break

        # Notify subscribers
        cls._notify_subscribers(task_id, SSEEventType.PHASE_COMPLETE, {
            "task_id": task_id,
            "phase_id": phase_id,
            "status": "completed" if success else "error",
            "timestamp": datetime.now().isoformat(),
        })

        # Push agent_message for inline chat display
        try:
            _phase_name = phase_id
            for _p in task.phases:
                if _p.id == phase_id:
                    _phase_name = _p.name
                    break
            from src.core.session_streamer import SessionStreamer
            SessionStreamer.push_agent_message(task_id, {
                "agent_id": phase_id,
                "agent_name": _phase_name,
                "action": "completed",
                "content": f"{_phase_name} completed." if success else f"{_phase_name} failed.",
            })
        except ImportError:
            pass

        logger.info(f"Phase completed: {task_id}/{phase_id} - {'success' if success else 'error'}")
        cls._persist_to_session(task_id)

    @classmethod
    def complete_task(
        cls,
        task_id: str,
        result: Optional[Dict[str, Any]] = None,
    ):
        """Complete task"""
        task = cls.get_or_create_task(task_id)
        task.status = "completed"
        task.progress = 1.0
        task.completed_at = datetime.now()
        task.result = result

        # Notify subscribers
        cls._notify_subscribers(task_id, SSEEventType.COMPLETE, {
            "task_id": task_id,
            "output_path": result.get("output_path") if result else None,
            "sections": result.get("sections") if result else [],
            "statistics": result.get("statistics") if result else {},
            "timestamp": datetime.now().isoformat(),
        })

        logger.info(f"Task completed: {task_id}")
        cls._persist_to_session(task_id)

    @classmethod
    def fail_task(cls, task_id: str, error: str, details: Optional[Dict] = None):
        """Task failed"""
        task = cls.get_or_create_task(task_id)
        task.status = "error"
        task.error = error

        # Notify subscribers
        cls._notify_subscribers(task_id, SSEEventType.ERROR, {
            "task_id": task_id,
            "code": "TASK_FAILED",
            "message": error,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
        })

        logger.error(f"Task failed: {task_id} - {error}")
        cls._persist_to_session(task_id)

    @classmethod
    def cancel_task(cls, task_id: str, reason: str = "Cancelled by user"):
        """Task cancelled by user (not an error)"""
        task = cls.get_or_create_task(task_id)
        task.status = "cancelled"
        task.progress = 0.0
        task.completed_at = datetime.now()

        cls._notify_subscribers(task_id, SSEEventType.CANCELLED, {
            "task_id": task_id,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })

        logger.info(f"Task cancelled: {task_id} - {reason}")
        cls._persist_to_session(task_id)

    @classmethod
    def pause_task(cls, task_id: str, message: str = "Task paused") -> None:
        """Send PAUSED event. Frontend shows paused state + resume button."""
        task = cls.get_or_create_task(task_id)
        task.status = "paused"
        cls._notify_subscribers(task_id, SSEEventType.PAUSED, {
            "task_id": task_id,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        })
        cls._persist_to_session(task_id)

    @classmethod
    def resume_task(cls, task_id: str, message: str = "Task resumed") -> None:
        """Send RESUMED event. Frontend shows running state."""
        task = cls.get_or_create_task(task_id)
        task.status = "running"
        cls._notify_subscribers(task_id, SSEEventType.RESUMED, {
            "task_id": task_id,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        })
        cls._persist_to_session(task_id)

    @classmethod
    def _notify_subscribers(
        cls,
        task_id: str,
        event_type: SSEEventType,
        data: Dict[str, Any],
    ):
        """Notify all subscribers"""
        if task_id not in cls._subscribers:
            return

        message = SSEMessage(event=event_type.value, data=data)

        for queue in list(cls._subscribers[task_id]):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(f"Queue full for subscriber of {task_id}")

    def subscribe(self):
        """Subscribe to task updates, pushing current state immediately for any non-pending status."""
        if self.task_id not in self._subscribers:
            self._subscribers[self.task_id] = set()
        self._subscribers[self.task_id].add(self._queue)

        if self.task_id in self._task_states:
            task = self._task_states[self.task_id]
            if task.status == "running":
                self._queue.put_nowait(SSEMessage(
                    event=SSEEventType.PROGRESS.value,
                    data={
                        "task_id": self.task_id,
                        "progress": task.progress,
                        "phase_id": task.current_phase,
                        "message": "Connected to existing task",
                        "timestamp": datetime.now().isoformat(),
                    }
                ))
                # Replay the last chat_response so late-connecting clients don't miss it
                if task.last_chat_response:
                    cr = task.last_chat_response
                    self._queue.put_nowait(SSEMessage(
                        event=SSEEventType.CHAT_RESPONSE.value,
                        data={
                            "session_id": self.task_id,
                            "message": cr.get("message", ""),
                            "action": cr.get("action", "continue_chat"),
                            "topic": cr.get("topic"),
                            "directions": cr.get("directions", []),
                            "suggestions": cr.get("suggestions", []),
                            "timestamp": datetime.now().isoformat(),
                        }
                    ))
            elif task.status == "completed":
                self._queue.put_nowait(SSEMessage(
                    event=SSEEventType.COMPLETE.value,
                    data={
                        "task_id": self.task_id,
                        "output_path": task.result.get("output_path") if task.result else None,
                        "sections": task.result.get("sections") if task.result else [],
                        "statistics": task.result.get("statistics") if task.result else {},
                        "timestamp": datetime.now().isoformat(),
                    }
                ))
            elif task.status == "error":
                self._queue.put_nowait(SSEMessage(
                    event=SSEEventType.ERROR.value,
                    data={
                        "task_id": self.task_id,
                        "code": "TASK_FAILED",
                        "message": task.error or "Unknown error",
                        "details": {},
                        "timestamp": datetime.now().isoformat(),
                    }
                ))

        logger.debug(f"Subscriber added for task {self.task_id}")

    @classmethod
    def _schedule_state_cleanup(cls, task_id: str):
        """Schedule delayed cleanup of terminal task state (avoids race with reconnecting clients)."""
        if task_id not in cls._task_states:
            return
        task = cls._task_states[task_id]
        if task.status not in ("completed", "error"):
            return

        async def _cleanup():
            await asyncio.sleep(cls._STATE_TTL_SECONDS)
            if task_id in cls._task_states and task_id not in cls._subscribers:
                logger.info(f"Cleaning up terminal task state: {task_id}")
                cls._task_states.pop(task_id, None)

        asyncio.ensure_future(_cleanup())

    def unsubscribe(self):
        """Unsubscribe — delay cleanup of terminal states to support reconnecting clients."""
        if self.task_id in self._subscribers:
            self._subscribers[self.task_id].discard(self._queue)
            if not self._subscribers[self.task_id]:
                del self._subscribers[self.task_id]
                self._schedule_state_cleanup(self.task_id)

        logger.debug(f"Subscriber removed for task {self.task_id}")

    async def generate(self) -> AsyncGenerator[str, None]:
        """
        Generate SSE event stream

        Yields:
            SSE format string
        """
        self.subscribe()

        try:
            # Send connection success event
            yield SSEMessage(
                event="connected",
                data={"task_id": self.task_id, "timestamp": datetime.now().isoformat()}
            ).to_sse()

            # Listen to queue continuously
            while True:
                try:
                    # Wait for message, send heartbeat on timeout
                    message = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=30.0
                    )

                    yield message.to_sse()

                    # End stream when task completes, fails, or is cancelled
                    if message.event in (
                        SSEEventType.COMPLETE.value,
                        SSEEventType.ERROR.value,
                        SSEEventType.CANCELLED.value,
                    ):
                        break

                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection
                    yield SSEMessage(
                        event="heartbeat",
                        data={"timestamp": datetime.now().isoformat()}
                    ).to_sse()

        except asyncio.CancelledError:
            logger.debug(f"SSE stream cancelled for {self.task_id}")

        finally:
            self.unsubscribe()
            # Fire disconnect callback when last subscriber leaves
            remaining = len(self._subscribers.get(self.task_id, set()))
            if remaining == 0:
                cb = self._disconnect_callbacks.pop(self.task_id, None)
                if cb:
                    try:
                        cb(self.task_id)
                    except Exception as e:
                        logger.warning(f"Disconnect callback failed for {self.task_id}: {e}")

    @classmethod
    def get_task_state(cls, task_id: str) -> Optional[TaskState]:
        """Get task state"""
        return cls._task_states.get(task_id)

    @classmethod
    def push_chat_response(cls, session_id: str, response_data: Dict[str, Any]):
        """推送对话工具执行结果（双写：ProgressStreamer + SessionStreamer）"""
        task = cls.get_or_create_task(session_id)
        task.last_chat_response = response_data  # store for replay on reconnect
        cls._notify_subscribers(session_id, SSEEventType.CHAT_RESPONSE, {
            "session_id": session_id,
            "message": response_data.get("message", ""),
            "action": response_data.get("action", "continue_chat"),
            "topic": response_data.get("topic"),
            "directions": response_data.get("directions", []),
            "suggestions": response_data.get("suggestions", []),
            "timestamp": datetime.now().isoformat(),
        })
        # Dual-write to persistent SessionStreamer (Issue 2 fix)
        try:
            from src.core.session_streamer import SessionStreamer
            SessionStreamer.push_chat_response(session_id, response_data)
        except ImportError:
            pass
        logger.info(f"Chat response pushed: {session_id}")
        cls._persist_to_session(session_id)

    @classmethod
    def clear_task(cls, task_id: str):
        """Clear task state"""
        cls._task_states.pop(task_id, None)
        cls._subscribers.pop(task_id, None)


# ============ Convenience functions ============

def update_progress(task_id: str, progress: float, **kwargs):
    """Convenience function to update progress"""
    ProgressStreamer.update_progress(task_id, progress, **kwargs)


def start_phase(task_id: str, phase_id: str, phase_name: str, **kwargs):
    """Convenience function to start phase"""
    ProgressStreamer.start_phase(task_id, phase_id, phase_name, **kwargs)


def complete_phase(task_id: str, phase_id: str, **kwargs):
    """Convenience function to complete phase"""
    ProgressStreamer.complete_phase(task_id, phase_id, **kwargs)


def complete_task(task_id: str, **kwargs):
    """Convenience function to complete task"""
    ProgressStreamer.complete_task(task_id, **kwargs)


def fail_task(task_id: str, error: str, **kwargs):
    """Convenience function for task failure"""
    ProgressStreamer.fail_task(task_id, error, **kwargs)


def cancel_task(task_id: str, reason: str = "Cancelled by user"):
    """Convenience function for task cancellation"""
    ProgressStreamer.cancel_task(task_id, reason)


def pause_task(task_id: str, message: str = "Task paused"):
    """Convenience function for task pause"""
    ProgressStreamer.pause_task(task_id, message)


def resume_task(task_id: str, message: str = "Task resumed"):
    """Convenience function for task resume"""
    ProgressStreamer.resume_task(task_id, message)


def push_chat_response(session_id: str, response_data: Dict[str, Any]):
    """Convenience function to push chat response"""
    ProgressStreamer.push_chat_response(session_id, response_data)


__all__ = [
    "ProgressStreamer",
    "SSEEventType",
    "SSEMessage",
    "TaskState",
    "TaskPhase",
    "update_progress",
    "start_phase",
    "complete_phase",
    "complete_task",
    "fail_task",
    "cancel_task",
    "pause_task",
    "resume_task",
    "push_chat_response",
]
