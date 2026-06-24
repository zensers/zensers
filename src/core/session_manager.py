# -*- coding: utf-8 -*-
"""
Session Manager
===============

Replaces the global _sessions memory dict in research_api.py.
Each modification is automatically persisted to disk, and all active sessions
are automatically recovered after service restart.

Storage path: data/sessions/{session_id}.json
"""

import dataclasses
import json
import logging
import os
import threading
import traceback
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Fields that don't need persistence (runtime objects, can be recreated)
_TRANSIENT_FIELDS = {"clarifier", "_lock", "_pending_v2_revision"}


class PersistentSessionDict(dict):
    """
    Auto-persisting dictionary
    
    Inherits dict, all __setitem__ operations automatically trigger persistence.
    This allows existing session["key"] = value code to work unchanged with auto-persistence.
    """
    
    def __init__(self, manager: "SessionManager", session_id: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._manager = manager
        self._session_id = session_id
    
    def __setitem__(self, key, value):
        # Append-only guard for conversation_history (Option D)
        if key == "conversation_history":
            old = self.get("conversation_history", [])
            if isinstance(old, list) and isinstance(value, list) and len(value) < len(old):
                try:
                    self._manager._save_backup(self._session_id, "guard")
                except Exception as exc:
                    logger.error(f"Backup failed before blocking truncation: {exc}")
                raise ValueError(
                    f"conversation_history truncation blocked: "
                    f"{len(old)} -> {len(value)} items. "
                    f"History is append-only."
                )
        super().__setitem__(key, value)
        # Sync display_history with conversation_history (never compressed)
        # Use dict.__setitem__ to avoid re-triggering __setitem__ → infinite save loop
        if key == "conversation_history" and isinstance(value, list):
            dict.__setitem__(self, "display_history", list(value))
        self._manager._save_to_disk(self._session_id)
    
    def update(self, *args, **kwargs):
        merger = {}
        if args:
            merger.update(args[0])
        merger.update(kwargs)
        if "conversation_history" in merger:
            new_val = merger["conversation_history"]
            old = self.get("conversation_history", [])
            if isinstance(old, list) and isinstance(new_val, list) and len(new_val) < len(old):
                try:
                    self._manager._save_backup(self._session_id, "guard")
                except Exception as exc:
                    logger.error(f"Backup failed before blocking truncation in update(): {exc}")
                raise ValueError(
                    f"conversation_history truncation blocked in update(): "
                    f"{len(old)} -> {len(new_val)} items."
                )
        super().update(*args, **kwargs)
        # Sync display_history — use dict.__setitem__ to avoid re-triggering save
        if "conversation_history" in merger and isinstance(merger["conversation_history"], list):
            dict.__setitem__(self, "display_history", list(merger["conversation_history"]))
        self._manager._save_to_disk(self._session_id)
    
    def pop(self, key, *args):
        result = super().pop(key, *args)
        self._manager._save_to_disk(self._session_id)
        return result
    
    def clear(self):
        super().clear()
        self._manager._save_to_disk(self._session_id)


def _serialize_value(value: Any) -> Any:
    """Recursively serialize value, handling special types like datetime"""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value):
        return _serialize_value(dataclasses.asdict(value))
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, PersistentSessionDict):
        return {k: _serialize_value(v) for k, v in value.items() if k not in _TRANSIENT_FIELDS}
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items() if k not in _TRANSIENT_FIELDS}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    return value


def _deserialize_state_machine(data: dict) -> Any:
    """Restore ConversationStateMachine from dict"""
    from src.core.dialogue.state_machine import ConversationStateMachine, ConversationState

    machine = ConversationStateMachine(
        research_id=data.get("research_id"),
        context=data.get("context", {}),
    )
    # Restore state
    state_str = data.get("current_state", "understanding")
    try:
        machine.current_state = ConversationState(state_str)
    except ValueError:
        machine.current_state = ConversationState.UNDERSTANDING

    # Restore history
    history = data.get("history", [])
    machine._history = []
    for h in history:
        try:
            state = ConversationState(h.get("state", "understanding"))
        except ValueError:
            state = ConversationState.UNDERSTANDING
        machine._history.append({
            "state": state,
            "timestamp": h.get("timestamp", datetime.now().isoformat()),
        })
    return machine


class SessionManager:
    """
    Global session manager
    
    Replaces the _sessions global dict in research_api.py.
    All modifications are automatically persisted to data/sessions/ directory.
    
    Usage:
        sm = SessionManager.get_instance()
        session = sm.get(session_id)
        sm.set(session_id, "mode", "chat")
        sm.delete(session_id)
    """

    _instance: Optional["SessionManager"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs) -> "SessionManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._sessions: Dict[str, Dict[str, Any]] = {}
                    instance._lock = threading.RLock()
                    instance._base_dir = Path("data/sessions")
                    instance._base_dir.mkdir(parents=True, exist_ok=True)
                    instance._history_compressor: Optional[Any] = None
                    instance._last_write_time: Dict[str, float] = {}
                    instance._debounce_ms = 2000
                    cls._instance = instance
        return cls._instance

    @classmethod
    def get_instance(cls) -> "SessionManager":
        """Get global singleton"""
        if cls._instance is None:
            return cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)"""
        with cls._instance_lock:
            cls._instance = None

    def _get_path(self, session_id: str) -> Path:
        """Get session file path"""
        # Sanitize filename
        safe_id = session_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self._base_dir / f"{safe_id}.json"

    def _save_backup(self, session_id: str, reason: str = "guard") -> Optional[Path]:
        """Save a timestamped backup of the current session before destructive ops.

        Flushes in-memory state to disk first so the backup is never stale.
        Safe to call from within __setitem__ because _save_to_disk does not
        re-enter __setitem__ for conversation_history (compressor uses dict.__setitem__).
        """
        import shutil
        # Flush in-memory state to disk first — ensures backup is current
        self._save_to_disk(session_id)
        path = self._get_path(session_id)
        if not path.exists():
            return None
        # Dedup: skip if a backup with the same reason was created in the last hour
        existing = sorted(path.parent.glob(f"{path.stem}.*.{reason}.bak"))
        if existing:
            last_time = datetime.fromtimestamp(existing[-1].stat().st_mtime)
            if (datetime.now() - last_time).total_seconds() < 3600:
                return existing[-1]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.parent / f"{path.stem}.{timestamp}.{reason}.bak"
        shutil.copy2(str(path), str(backup_path))
        logger.warning(f"Backup saved: {backup_path}")
        return backup_path

    def _save_to_disk(self, session_id: str) -> None:
        """Persist single session to disk using atomic write (temp file + rename)."""
        import os as os_mod
        import time as _time

        session = self._sessions.get(session_id)
        if session is None:
            return

        now = _time.time()
        last = self._last_write_time.get(session_id, 0)
        if (now - last) * 1000 < self._debounce_ms:
            return
        self._last_write_time[session_id] = now
        try:
            path = self._get_path(session_id)
            # Optional: compress history before writing
            if self._history_compressor and session.get("conversation_history"):
                self._history_compressor.compress_if_needed(session_id, session)
            serialized = _serialize_value(session)

            # Atomic write: write to .tmp first, then rename
            tmp_path = path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(serialized, f, ensure_ascii=False, indent=2)
            os_mod.replace(str(tmp_path), str(path))
        except Exception as e:
            logger.error(f"Failed to persist session {session_id}: {e}")

    def _load_from_disk(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load single session from disk"""
        path = self._get_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            # Deserialize state_machine
            if "state_machine" in data and isinstance(data["state_machine"], dict):
                try:
                    data["state_machine"] = _deserialize_state_machine(data["state_machine"])
                except Exception as e:
                    logger.warning(f"Failed to deserialize state_machine for {session_id}: {e}")
                    del data["state_machine"]

            # Deserialize created_at
            if "created_at" in data and isinstance(data["created_at"], str):
                try:
                    data["created_at"] = datetime.fromisoformat(data["created_at"])
                except (ValueError, TypeError):
                    data["created_at"] = datetime.now()

            return data
        except Exception as e:
            logger.warning(f"Failed to load session {session_id}: {e} — file may be corrupted")
            return None

    def set_history_compressor(self, compressor: Any) -> None:
        """
        Attach a history compressor (called after every write).
        
        Expected interface:
            compressor.compress_if_needed(session_id, session) -> None
        """
        self._history_compressor = compressor

    # ==================== Public API ====================

    def _wrap(self, session_id: str, data: dict) -> PersistentSessionDict:
        """Wrap regular dict as auto-persisting dict"""
        if isinstance(data, PersistentSessionDict):
            return data
        wrapped = PersistentSessionDict(self, session_id, data)
        with self._lock:
            self._sessions[session_id] = wrapped
        return wrapped

    def get(self, session_id: str) -> Optional[PersistentSessionDict]:
        """
        Get session, prefer memory, load from disk on miss.
        
        Thread-safe: entire load-from-disk path is under the lock to prevent
        two threads loading and overwriting each other's data.
        
        Returns:
            Auto-persisting session dict or None
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                if isinstance(session, PersistentSessionDict):
                    return session
                return self._wrap(session_id, session)

            # Memory miss → disk load under lock (prevents TOCTOU race)
            loaded = self._load_from_disk(session_id)
            if loaded is not None:
                wrapped = PersistentSessionDict(self, session_id, loaded)
                self._sessions[session_id] = wrapped
                logger.info(f"Loaded session from disk: {session_id}")
                return wrapped
            return None

    def set(self, session_id: str, key: str, value: Any) -> None:
        """
        Set session field and persist
        
        Args:
            session_id: Session ID
            key: Field name
            value: Field value
        """
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = PersistentSessionDict(self, session_id, {})
            elif not isinstance(self._sessions[session_id], PersistentSessionDict):
                self._sessions[session_id] = PersistentSessionDict(self, session_id, self._sessions[session_id])
            self._sessions[session_id][key] = value

    def update(self, session_id: str, updates: Dict[str, Any]) -> None:
        """
        Batch update session fields and persist
        
        Args:
            session_id: Session ID
            updates: Field dict to update
        """
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = PersistentSessionDict(self, session_id, {})
            elif not isinstance(self._sessions[session_id], PersistentSessionDict):
                self._sessions[session_id] = PersistentSessionDict(self, session_id, self._sessions[session_id])
            self._sessions[session_id].update(updates)

    def create(self, session_id: str, initial_data: Dict[str, Any]) -> PersistentSessionDict:
        """
        Create new session
        
        Args:
            session_id: Session ID
            initial_data: Initial data
            
        Returns:
            Auto-persisting session dict
        """
        wrapped = self._wrap(session_id, initial_data)
        with self._lock:
            self._sessions[session_id] = wrapped
        self._save_to_disk(session_id)
        logger.info(f"Session created: {session_id}")
        return wrapped

    def delete(self, session_id: str) -> None:
        """
        Delete session (memory + disk)
        
        Args:
            session_id: Session ID
        """
        with self._lock:
            self._sessions.pop(session_id, None)

        # Delete disk file
        try:
            path = self._get_path(session_id)
            if path.exists():
                path.unlink()
                logger.info(f"Session deleted: {session_id}")
        except Exception as e:
            logger.warning(f"Failed to delete session file {session_id}: {e}")

    def exists(self, session_id: str) -> bool:
        """Check if session exists (memory or disk)"""
        with self._lock:
            if session_id in self._sessions:
                return True
        return self._get_path(session_id).exists()

    def keys(self) -> List[str]:
        """Get all session ID list (memory + disk)"""
        with self._lock:
            keys = set(self._sessions.keys())

        # Scan disk
        try:
            for f in self._base_dir.glob("*.json"):
                sid = f.stem
                keys.add(sid)
        except Exception:
            pass

        return list(keys)

    def recover_all(self, max_preload: int = 5) -> int:
        """
        Recover latest sessions on startup (prevents OOM).
        Remaining sessions load on demand via get().

        Args:
            max_preload: Max sessions to load into memory on startup

        Returns:
            Number of recovered sessions
        """
        import os as os_mod

        count = 0
        if not self._base_dir.exists():
            return 0

        # Clean up any leftover .tmp files from crashed atomic writes
        for tmp in self._base_dir.glob("*.tmp"):
            try:
                os_mod.remove(str(tmp))
                logger.info(f"Cleaned up stale temp file: {tmp.name}")
            except Exception as e:
                logger.warning(f"Failed to remove stale temp file {tmp.name}: {e}")

        files = sorted(self._base_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        deferred = len(files) - max_preload
        for f in files[:max_preload]:
            session_id = f.stem
            data = self._load_from_disk(session_id)
            if data is not None:
                with self._lock:
                    self._sessions[session_id] = PersistentSessionDict(self, session_id, data)
                count += 1

        logger.info(f"Session recovery: {count} preloaded, {max(0, deferred)} deferred")
        return count

    def cleanup_expired(self, max_age_hours: int = 72) -> int:
        """
        Cleanup expired sessions
        
        Args:
            max_age_hours: Maximum retention time (hours), default 72 hours
            
        Returns:
            Number of cleaned sessions
        """
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        cleaned = 0

        for session_id in self.keys():
            session = self.get(session_id)
            if session is None:
                continue

            created_at = session.get("created_at")
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at)
                except (ValueError, TypeError):
                    created_at = None

            if created_at and created_at < cutoff:
                # Check if terminal state (completed/cancelled)
                state_machine = session.get("state_machine")
                if state_machine and hasattr(state_machine, "current_state"):
                    from src.core.dialogue.state_machine import ConversationState
                    if state_machine.current_state in (
                        ConversationState.COMPLETED,
                        ConversationState.CANCELLED,
                    ):
                        self.delete(session_id)
                        cleaned += 1

        if cleaned:
            logger.info(f"Cleaned up {cleaned} expired sessions")
        return cleaned

    def flush_all(self) -> None:
        """No-op — PersistentSessionDict auto-persists on every mutation."""
        logger.debug("flush_all() is a no-op: PersistentSessionDict auto-persists")


# Global convenience function
def get_session_manager() -> SessionManager:
    """Get global SessionManager instance"""
    return SessionManager.get_instance()
