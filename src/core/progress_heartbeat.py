# -*- coding: utf-8 -*-
"""
Progress Heartbeat
==================

Periodically pushes heartbeat agent_messages during research execution
to prevent the frontend from thinking the system is frozen.
"""

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ProgressHeartbeat:
    _tasks: dict = {}
    _INTERVAL_SECONDS = 15

    @classmethod
    def start(cls, session_id: str):
        if session_id in cls._tasks:
            return
        cls._tasks[session_id] = asyncio.create_task(cls._loop(session_id))

    @classmethod
    def stop(cls, session_id: str):
        task = cls._tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    @classmethod
    async def _loop(cls, session_id: str):
        try:
            while True:
                await asyncio.sleep(cls._INTERVAL_SECONDS)
                from src.core.progress_streamer import ProgressStreamer
                task = ProgressStreamer.get_task_state(session_id)
                if not task or task.status not in ("running", "paused"):
                    break
                cls._update_heartbeat(session_id)
                from src.core.session_streamer import SessionStreamer
                SessionStreamer.push_agent_message(session_id, {
                    "agent_id": "system",
                    "agent_name": "System",
                    "action": "heartbeat",
                    "content": f"Research in progress... ({task.progress:.0%} complete)",
                })
        except asyncio.CancelledError:
            pass
        finally:
            cls._tasks.pop(session_id, None)

    @classmethod
    def _update_heartbeat(cls, session_id: str):
        try:
            from src.core.session_manager import SessionManager
            sm = SessionManager.get_instance()
            session = sm.get(session_id)
            if session is None:
                return
            tp = session.get("task_progress", {})
            tp["last_heartbeat_at"] = datetime.now().isoformat()
            session.update({"task_progress": tp})
        except Exception as e:
            logger.debug(f"Heartbeat persist failed for {session_id}: {e}")
