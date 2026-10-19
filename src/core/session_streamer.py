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
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, AsyncGenerator
from enum import Enum

logger = logging.getLogger(__name__)


class SessionSSEEventType(str, Enum):
    """Session SSE event types"""
    CHAT_RESPONSE = "chat_response"
    CHAT_TOKEN = "chat_token"
    CHAT_THINKING = "chat_thinking"
    AGENT_MESSAGE = "agent_message"
    HEARTBEAT = "heartbeat"
    CONNECTED = "connected"
    QUALITY_RESULT = "quality_result"
    SECTION_QUALITY = "section_quality"
    PREVIEW_REFRESH = "preview_refresh"
    QUALITY_CONFIRMED = "quality_confirmed"
    REPORT_CONTEXT = "report_context"


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
    _last_agent_msg_times: Dict[str, float] = {}
    _AGENT_MSG_THROTTLE_SECONDS = 0.05
    _pending_agent_msgs: Dict[str, Dict[str, Any]] = {}
    _persist_lock = __import__('threading').Lock()

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
        """持久化 SSE 事件到 SessionManager (最多 200 条, 分类保留)
        
        chat_response: 追加到 conversation_history（防御性去重：检查末尾5条是否有相同内容）。
            注意：当前 _chat_response()/_framework_response()/_start_execution() 与
            ProgressStreamer.push_chat_response() 路径互斥（Chat模式走前者，Research模式走后者），
            所以去重实际上不会触发，但保留作为防御性编程。
        agent_message: 始终追加（agent消息没有其他写入路径）。
        """
        with cls._persist_lock:
            try:
                from src.core.session_manager import SessionManager
                sm = SessionManager.get_instance()
                session = sm.get(session_id)
                if session is None:
                    return

                if event_type in ("chat_response", "agent_message"):
                    history = session.get("conversation_history", [])
                    if event_type == "chat_response":
                        msg_content = data.get("message", "")
                        response_id = data.get("response_id")
                        already_exists = any(
                            isinstance(m, dict)
                            and m.get("role") == "assistant"
                            and response_id
                            and m.get("response_id") == response_id
                            for m in history
                        ) if response_id else any(
                            isinstance(m, dict)
                            and m.get("role") == "assistant"
                            and m.get("content") == msg_content
                            and msg_content != ""
                            for m in history[-5:]
                        )
                        if not already_exists:
                            history.append({
                                "role": "assistant",
                                "content": msg_content,
                                **({"response_id": response_id} if response_id else {}),
                                "timestamp": data.get("timestamp") or datetime.now().isoformat(),
                            })
                            session["conversation_history"] = history
                    elif event_type == "agent_message":
                        history.append({
                            "role": "agent",
                            "content": data.get("content", ""),
                            "agent_id": data.get("agent_id", ""),
                            "agent_name": data.get("agent_name", ""),
                            "action": data.get("action", ""),
                            "timestamp": data.get("timestamp", datetime.now().isoformat()),
                            **{
                                key: data[key]
                                for key in ("provider", "quality_score", "cache_hit", "stop_reason")
                                if key in data and data[key] is not None
                            },
                        })
                        session["conversation_history"] = history

                events = session.get("recent_events", [])
                events.append({
                    "event": event_type,
                    "data": data,
                    "created_at": datetime.now().isoformat(),
                })

                _MAX_EVENTS_TOTAL = 200
                _MIN_AGENT_EVENTS = 30
                if len(events) > _MAX_EVENTS_TOTAL:
                    chat_msgs = [e for e in events if e.get("event") == "chat_response"]
                    agent_msgs = [e for e in events if e.get("event") == "agent_message"]
                    other_msgs = [e for e in events if e.get("event") not in ("chat_response", "agent_message")]

                    keep_agent = max(_MIN_AGENT_EVENTS, _MAX_EVENTS_TOTAL - len(chat_msgs) - len(other_msgs))
                    if keep_agent < len(agent_msgs):
                        agent_msgs = agent_msgs[-keep_agent:]

                    max_chat = _MAX_EVENTS_TOTAL - len(agent_msgs) - len(other_msgs)
                    if len(chat_msgs) > max_chat:
                        chat_msgs = chat_msgs[-max_chat:]

                    events = chat_msgs + agent_msgs + other_msgs
                    events.sort(key=lambda e: e.get("created_at", ""))

                session["recent_events"] = events
            except Exception as e:
                logger.debug(f"Failed to persist event for {session_id}: {e}")

    @classmethod
    def push_chat_response(cls, session_id: str, response_data: Dict[str, Any]):
        """Push a chat_response event to all session subscribers"""
        response_data.setdefault("response_id", f"chat_{uuid.uuid4().hex}")
        event_data = {
            "session_id": session_id,
            "response_id": response_data.get("response_id"),
            "message": response_data.get("message", ""),
            "action": response_data.get("action", "continue_chat"),
            "topic": response_data.get("topic"),
            "directions": response_data.get("directions", []),
            "suggestions": response_data.get("suggestions", []),
            "thinking_content": response_data.get("thinking_content"),
            "mode": response_data.get("mode", "chat"),
            "step": response_data.get("step", 0),
            "timestamp": datetime.now().isoformat(),
        }
        cls._notify_subscribers(session_id, SessionSSEEventType.CHAT_RESPONSE, event_data)
        _ts = datetime.now().isoformat()
        cls._persist_event(session_id, SessionSSEEventType.CHAT_RESPONSE.value, {
            "session_id": session_id,
            "response_id": response_data.get("response_id"),
            "message": response_data.get("message", ""),
            "action": response_data.get("action", "continue_chat"),
            "topic": response_data.get("topic"),
            "directions": response_data.get("directions", []),
            "suggestions": response_data.get("suggestions", []),
            "thinking_content": response_data.get("thinking_content"),
            "mode": response_data.get("mode", "chat"),
            "step": response_data.get("step", 0),
            "timestamp": _ts,
        })
        logger.info(f"Session stream chat_response pushed: {session_id}")

    @classmethod
    def push_chat_token(cls, session_id: str, token: str):
        """Push a single chat token for streaming display.

        Bypasses _notify_subscribers() to avoid buffering individual tokens
        in _recent_messages (which would flood the replay buffer).
        Does NOT persist to conversation_history.
        """
        message = SessionMessage(event=SessionSSEEventType.CHAT_TOKEN.value, data={
            "session_id": session_id,
            "token": token,
        })
        subscribers = cls._subscribers.get(session_id)
        if not subscribers:
            return
        for queue in list(subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass

    @classmethod
    def push_chat_thinking(cls, session_id: str, token: str):
        """Push a single thinking token for streaming display.

        Same delivery semantics as push_chat_token:
        - Bypasses _notify_subscribers() to avoid buffering in _recent_messages
        - Does NOT persist to conversation_history
        """
        message = SessionMessage(event=SessionSSEEventType.CHAT_THINKING.value, data={
            "session_id": session_id,
            "token": token,
        })
        subscribers = cls._subscribers.get(session_id)
        if not subscribers:
            return
        for queue in list(subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass

    @classmethod
    def push_agent_message(cls, session_id: str, agent_data: Dict[str, Any]):
        """Push an agent_message event to all session subscribers"""
        import time
        # Preserve search observability fields on live and persisted events.
        _metadata = {
            key: agent_data[key]
            for key in ("provider", "quality_score", "cache_hit", "stop_reason")
            if key in agent_data and agent_data[key] is not None
        }
        _action = agent_data.get("action", "")
        if _action != "heartbeat":
            _now = time.monotonic()
            _last = cls._last_agent_msg_times.get(session_id, 0.0)
            if _now - _last < cls._AGENT_MSG_THROTTLE_SECONDS:
                cls._pending_agent_msgs[session_id] = agent_data
                return
            cls._last_agent_msg_times[session_id] = _now
        _ts = datetime.now().isoformat()
        _event_payload = {
            "session_id": session_id,
            "agent_id": agent_data.get("agent_id", ""),
            "agent_name": agent_data.get("agent_name", ""),
            "action": agent_data.get("action", ""),
            "content": agent_data.get("content", ""),
            "timestamp": _ts,
            **_metadata,
        }
        cls._notify_subscribers(session_id, SessionSSEEventType.AGENT_MESSAGE, _event_payload)
        if _action == "heartbeat":
            # Heartbeats are transport keep-alives, not research history.
            # Persisting them flooded conversation_history and evicted real
            # agent messages from the 200-slot recent_events buffer.
            return
        cls._persist_event(session_id, SessionSSEEventType.AGENT_MESSAGE.value, _event_payload)
        logger.debug(f"Session stream agent_message pushed: {session_id}/{agent_data.get('agent_id', '')}")
        pending = cls._pending_agent_msgs.pop(session_id, None)
        if pending:
            try:
                loop = asyncio.get_running_loop()
                loop.call_later(
                    cls._AGENT_MSG_THROTTLE_SECONDS,
                    lambda: cls.push_agent_message(session_id, pending)
                )
            except RuntimeError:
                import threading
                try:
                    loop = asyncio.get_event_loop()
                    loop.call_soon_threadsafe(
                        lambda: loop.call_later(
                            cls._AGENT_MSG_THROTTLE_SECONDS,
                            lambda: cls.push_agent_message(session_id, pending)
                        )
                    )
                except Exception:
                    pass

    @classmethod
    def push_system_note(cls, session_id: str, content: str, note_type: str = "status"):
        """Push a durable system status note and persist it into conversation_history.

        Task lifecycle changes (paused/cancelled/resumed) must live inside the
        conversation timeline so the user can scroll through history and still
        see what happened — a top bar cannot carry that context after a reload.
        """
        _ts = datetime.now().isoformat()
        cls._notify_subscribers(session_id, SessionSSEEventType.AGENT_MESSAGE, {
            "session_id": session_id,
            "agent_id": "system",
            "agent_name": "System",
            "action": f"system_{note_type}",
            "content": content,
            "timestamp": _ts,
        })
        # Direct append: role=system rows must reach the paginated history but
        # must NOT occupy recent_events slots needed by real agent messages.
        cls._persist_system_note(session_id, content, _ts)
        logger.info(f"System note pushed: {session_id} ({note_type})")

    @classmethod
    def _persist_system_note(cls, session_id: str, content: str, timestamp: str):
        with cls._persist_lock:
            try:
                from src.core.session_manager import SessionManager
                sm = SessionManager.get_instance()
                session = sm.get(session_id)
                if session is None:
                    return
                history = session.get("conversation_history", [])
                _already = any(
                    isinstance(m, dict) and m.get("role") == "system" and m.get("content") == content
                    for m in history[-10:]
                )
                if not _already:
                    history.append({
                        "role": "system",
                        "content": content,
                        "_type": f"system_note",
                        "timestamp": timestamp,
                    })
                    session["conversation_history"] = history
            except Exception as e:
                logger.warning(f"Failed to persist system note for {session_id}: {e}")

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

    @classmethod
    def push_report_context(cls, session_id: str, context: Dict[str, Any]):
        """Push the versioned, public report context snapshot.

        The snapshot is persisted by ``update_report_context`` before this
        method is called.  This event is intentionally separate from
        ``agent_message`` because that event has a fixed status-only schema.
        """
        event_data = {
            "event_id": f"ctx_{uuid.uuid4().hex}",
            "session_id": session_id,
            "context_revision": context.get("context_revision", 0),
            "report_version": context.get("report_version", 0),
            "snapshot": context,
            "timestamp": datetime.now().isoformat(),
        }
        cls._notify_subscribers(session_id, SessionSSEEventType.REPORT_CONTEXT, event_data)
        cls._persist_event(session_id, SessionSSEEventType.REPORT_CONTEXT.value, event_data)
        logger.info(
            "Session stream report_context pushed: %s revision=%s version=%s",
            session_id, event_data["context_revision"], event_data["report_version"],
        )

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
            except Exception:
                pass

        # Put all messages into queue (single pass — fixes double-put bug where
        # persisted events were put inside the load loop AND again here)
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
