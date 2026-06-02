# -*- coding: utf-8 -*-
"""
Session Streamer
================

Persistent SSE stream for session-level events.

Unlike ProgressStreamer:
- Does NOT terminate on task complete/error
- Stays alive for the entire session lifetime
- Used for chat_response and agent_message events
- Frontend keeps a persistent EventSource connection

Usage:
    # Push a chat response
    SessionStreamer.push_chat_response(session_id, response_data)
    
    # Push an agent message
    SessionStreamer.push_agent_message(session_id, agent_data)
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, AsyncGenerator
from enum import Enum

logger = logging.getLogger(__name__)


class SessionSSEEventType(str, Enum):
    """Session SSE event types"""
    CHAT_RESPONSE = "chat_response"
    AGENT_MESSAGE = "agent_message"
    HEARTBEAT = "heartbeat"
    CONNECTED = "connected"
    QUALITY_RESULT = "quality_result"
    SECTION_QUALITY = "section_quality"
    PREVIEW_REFRESH = "preview_refresh"
    QUALITY_CONFIRMED = "quality_confirmed"


@dataclass
class SessionMessage:
    """SSE message for session stream"""
    event: str
    data: Dict[str, Any]
    id: Optional[str] = None

    def to_sse(self) -> str:
        """Convert to SSE format string"""
        lines = []
        if self.id:
            lines.append(f"id: {self.id}")
        if self.event:
            lines.append(f"event: {self.event}")
        lines.append(f"data: {json.dumps(self.data, ensure_ascii=False)}")
        return "\n".join(lines) + "\n\n"


class SessionStreamer:
    """
    Persistent session SSE stream.
    
    Never terminates on its own — stays alive for the session lifetime.
    The frontend should keep this connection open and reconnect on drop.
    """

    # Class-level subscriber registry
    _subscribers: Dict[str, Set[asyncio.Queue]] = {}
    # Recent messages buffer for replay on late connections (Issue 2 fix)
    _recent_messages: Dict[str, List[SessionMessage]] = {}
    _MAX_REPLAY = 20

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._queue: asyncio.Queue = asyncio.Queue()

    # ---- Class methods for pushing events ----

    @classmethod
    def _ensure_subscribers(cls, session_id: str) -> Set[asyncio.Queue]:
        """Get or create subscriber set for a session"""
        if session_id not in cls._subscribers:
            cls._subscribers[session_id] = set()
        return cls._subscribers[session_id]

    @classmethod
    def _notify_subscribers(cls, session_id: str, event_type: SessionSSEEventType, data: Dict[str, Any]):
        """Notify all subscribers of a session event"""
        message = SessionMessage(event=event_type.value, data=data)

        # Buffer recent messages for late subscribers (replay on connect)
        if session_id not in cls._recent_messages:
            cls._recent_messages[session_id] = []
        cls._recent_messages[session_id].append(message)
        if len(cls._recent_messages[session_id]) > cls._MAX_REPLAY:
            cls._recent_messages[session_id].pop(0)

        subscribers = cls._subscribers.get(session_id)
        if not subscribers:
            logger.debug(f"No session subscribers for {session_id}, event {event_type.value} dropped")
            return

        dead_queues = []
        for queue in list(subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(f"Session stream queue full for {session_id}")
            except Exception:
                dead_queues.append(queue)

        for q in dead_queues:
            subscribers.discard(q)

    @classmethod
    def _persist_event(cls, session_id: str, event_type: str, data: Dict[str, Any]):
        """持久化 SSE 事件到 SessionManager (最多 100 条, 分类保留)"""
        try:
            from src.core.session_manager import SessionManager
            sm = SessionManager.get_instance()
            session = sm.get(session_id)
            if session is None:
                return

            events = session.get("recent_events", [])
            events.append({
                "event": event_type,
                "data": data,
                "created_at": datetime.now().isoformat(),
            })

            # 最多保留 100 条，优先保留 chat_response
            _MAX_EVENTS_TOTAL = 100
            if len(events) > _MAX_EVENTS_TOTAL:
                chat_msgs = [e for e in events if e.get("event") == "chat_response"]
                agent_msgs = [e for e in events if e.get("event") == "agent_message"]
                keep_chat = len(chat_msgs)
                keep_agent = _MAX_EVENTS_TOTAL - keep_chat
                if keep_agent < len(agent_msgs):
                    agent_msgs = agent_msgs[-keep_agent:]
                events = chat_msgs + agent_msgs
                events.sort(key=lambda e: e.get("created_at", ""))

            session["recent_events"] = events
        except Exception as e:
            logger.debug(f"Failed to persist event for {session_id}: {e}")

    @classmethod
    def push_chat_response(cls, session_id: str, response_data: Dict[str, Any]):
        """Push a chat_response event to all session subscribers"""
        cls._notify_subscribers(session_id, SessionSSEEventType.CHAT_RESPONSE, {
            "session_id": session_id,
            "message": response_data.get("message", ""),
            "action": response_data.get("action", "continue_chat"),
            "topic": response_data.get("topic"),
            "directions": response_data.get("directions", []),
            "suggestions": response_data.get("suggestions", []),
            "timestamp": datetime.now().isoformat(),
        })
        cls._persist_event(session_id, SessionSSEEventType.CHAT_RESPONSE.value, {
            "session_id": session_id,
            "message": response_data.get("message", ""),
            "action": response_data.get("action", "continue_chat"),
            "topic": response_data.get("topic"),
            "directions": response_data.get("directions", []),
            "suggestions": response_data.get("suggestions", []),
        })
        logger.info(f"Session stream chat_response pushed: {session_id}")

    @classmethod
    def push_agent_message(cls, session_id: str, agent_data: Dict[str, Any]):
        """Push an agent_message event to all session subscribers"""
        cls._notify_subscribers(session_id, SessionSSEEventType.AGENT_MESSAGE, {
            "session_id": session_id,
            "agent_id": agent_data.get("agent_id", ""),
            "agent_name": agent_data.get("agent_name", ""),
            "action": agent_data.get("action", ""),
            "content": agent_data.get("content", ""),
            "timestamp": datetime.now().isoformat(),
        })
        cls._persist_event(session_id, SessionSSEEventType.AGENT_MESSAGE.value, {
            "session_id": session_id,
            "agent_id": agent_data.get("agent_id", ""),
            "agent_name": agent_data.get("agent_name", ""),
            "action": agent_data.get("action", ""),
            "content": agent_data.get("content", ""),
        })
        logger.debug(f"Session stream agent_message pushed: {session_id}/{agent_data.get('agent_id', '')}")

    @classmethod
    def push_clarification(cls, session_id: str, question: str, clarification_id: str):
        """Push a clarification question event to all session subscribers"""
        cls._notify_subscribers(session_id, SessionSSEEventType.AGENT_MESSAGE, {
            "session_id": session_id,
            "agent_id": "clarifier",
            "action": "asking",
            "content": question,
            "clarification_id": clarification_id,
            "timestamp": datetime.now().isoformat(),
        })
        cls._persist_event(session_id, "clarification", {
            "session_id": session_id,
            "agent_id": "clarifier",
            "question": question,
            "clarification_id": clarification_id,
        })
        logger.info(f"Clarification pushed: {session_id} id={clarification_id}")

    @classmethod
    def push_quality_result(cls, session_id: str, quality_data: Dict[str, Any]):
        """Push a quality_result event to all session subscribers"""
        cls._notify_subscribers(session_id, SessionSSEEventType.QUALITY_RESULT, {
            "session_id": session_id,
            "overall_score": quality_data.get("overall_score", 0),
            "overall_status": quality_data.get("overall_status", "unknown"),
            "section_results": quality_data.get("section_results", {}),
            "issues": quality_data.get("issues", [])[:20],
            "timestamp": datetime.now().isoformat(),
        })
        cls._persist_event(session_id, SessionSSEEventType.QUALITY_RESULT.value, {
            "session_id": session_id,
            "overall_score": quality_data.get("overall_score", 0),
            "overall_status": quality_data.get("overall_status", "unknown"),
        })
        logger.info(f"Session stream quality_result pushed: {session_id}")

    @classmethod
    def push_section_quality(cls, session_id: str, section_name: str, quality_data: dict):
        """Push a section quality check result to session subscribers"""
        event_data = {
            "session_id": session_id,
            "section_name": section_name,
            "data": quality_data,
        }
        cls._notify_subscribers(session_id, SessionSSEEventType.SECTION_QUALITY, event_data)
        cls._persist_event(session_id, SessionSSEEventType.SECTION_QUALITY.value, event_data)
        logger.debug(f"Session stream section_quality pushed: {session_id}/{section_name}")

    @classmethod
    def push_preview_refresh(cls, session_id: str, preview_url: str, version_id: str):
        """Push a preview refresh event to session subscribers"""
        event_data = {
            "session_id": session_id,
            "preview_url": preview_url,
            "version_id": version_id,
            "timestamp": datetime.now().isoformat(),
        }
        cls._notify_subscribers(session_id, SessionSSEEventType.PREVIEW_REFRESH, event_data)
        cls._persist_event(session_id, SessionSSEEventType.PREVIEW_REFRESH.value, event_data)
        logger.info(f"Session stream preview_refresh pushed: {session_id}")

    @classmethod
    def push_quality_confirmed(cls, session_id: str, final_document_path: str):
        """Push a quality confirmed event to session subscribers"""
        event_data = {
            "session_id": session_id,
            "final_document_path": final_document_path,
            "timestamp": datetime.now().isoformat(),
        }
        cls._notify_subscribers(session_id, SessionSSEEventType.QUALITY_CONFIRMED, event_data)
        cls._persist_event(session_id, SessionSSEEventType.QUALITY_CONFIRMED.value, event_data)
        logger.info(f"Session stream quality_confirmed pushed: {session_id}")

    # ---- Instance methods for SSE generator ----

    def subscribe(self):
        """Subscribe this instance to session events and replay recent messages"""
        subscribers = self._ensure_subscribers(self.session_id)
        self._queue = asyncio.Queue()  # fresh queue for this subscriber
        subscribers.add(self._queue)

        # Replay recent messages for late subscribers (Issue 2 fix)
        recent = self._recent_messages.get(self.session_id, [])

        # If memory buffer is empty, try to load from SessionManager
        if not recent:
            try:
                from src.core.session_manager import SessionManager
                sm = SessionManager.get_instance()
                session = sm.get(self.session_id)
                if session:
                    persisted_events = session.get("recent_events", [])
                    for ev in persisted_events[-self._MAX_REPLAY:]:
                        msg = SessionMessage(
                            event=ev.get("event", "unknown"),
                            data=ev.get("data", {}),
                            id=ev.get("created_at"),
                        )
                        recent.append(msg)
                        try:
                            self._queue.put_nowait(msg)
                        except asyncio.QueueFull:
                            break
            except Exception:
                pass

        for msg in recent:
            try:
                self._queue.put_nowait(msg)
            except asyncio.QueueFull:
                break

        logger.debug(f"Session stream subscriber added: {self.session_id} (replayed {len(recent)} messages)")

    def unsubscribe(self):
        """Remove this instance's subscription"""
        subscribers = self._subscribers.get(self.session_id)
        if subscribers:
            subscribers.discard(self._queue)
            if not subscribers:
                del self._subscribers[self.session_id]
                self._recent_messages.pop(self.session_id, None)  # cleanup buffer
                logger.debug(f"Session stream subscribers cleaned up: {self.session_id}")

    async def generate(self) -> AsyncGenerator[str, None]:
        """
        Generate SSE event stream.
        
        Unlike ProgressStreamer.generate(), this NEVER terminates
        on complete/error — it stays alive with heartbeats.
        The frontend keeps this open for the entire session.
        """
        self.subscribe()

        try:
            # Send connection event
            yield SessionMessage(
                event=SessionSSEEventType.CONNECTED.value,
                data={
                    "session_id": self.session_id,
                    "timestamp": datetime.now().isoformat(),
                }
            ).to_sse()

            # Event loop — runs until cancelled
            while True:
                try:
                    message = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=30.0
                    )
                    yield message.to_sse()
                except asyncio.TimeoutError:
                    # Heartbeat to keep connection alive
                    yield SessionMessage(
                        event=SessionSSEEventType.HEARTBEAT.value,
                        data={
                            "session_id": self.session_id,
                            "timestamp": datetime.now().isoformat(),
                        }
                    ).to_sse()

        except asyncio.CancelledError:
            logger.debug(f"Session stream cancelled: {self.session_id}")
        except Exception as e:
            logger.error(f"Session stream error: {self.session_id} - {e}", exc_info=True)
        finally:
            self.unsubscribe()


__all__ = ["SessionStreamer", "SessionSSEEventType", "SessionMessage"]
