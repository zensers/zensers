"""Atomic, append-only phase boundary manifest for research tasks."""

import json
import logging
import os
import threading
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_EVENTS = {
    "PHASE_START", "PHASE_INPUT", "PHASE_OUTPUT",
    "CHECKPOINT_SAVED", "PHASE_COMPLETE", "PHASE_FAILED",
}


class PhaseManifestStore:
    """Persist auditable phase events without coupling to execution control."""

    _locks: Dict[str, threading.Lock] = {}
    _locks_guard = threading.Lock()

    def __init__(
        self, task_id: str, session_id: str, root: Path = Path("data"),
        run_id: Optional[str] = None,
    ) -> None:
        self.task_id = str(task_id)
        if not self.task_id or Path(self.task_id).name != self.task_id or self.task_id in {".", ".."}:
            raise ValueError(f"Invalid task_id: {task_id!r}")
        self.session_id = str(session_id)
        self.run_id = str(run_id or "")
        self.path = (Path(root) / self.task_id / "diagnostic_manifest.json").resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self._locks_guard:
            self._locks.setdefault(str(self.path), threading.Lock())
        with self._locks_guard:
            lock = self._locks[str(self.path)]
        with lock:
            with self._interprocess_lock():
                if not self.path.exists():
                    self._write({
                        "session_id": self.session_id,
                        "task_id": self.task_id,
                        "run_id": self.run_id,
                        "phases": [],
                    })

    def record(self, event: str, *, phase: str = "", batch_id: str = "",
               agent_id: str = "", section_id: str = "",
               checkpoint_id: str = "", **details: Any) -> Dict[str, Any]:
        if event not in _EVENTS:
            raise ValueError(f"Unsupported phase event: {event}")
        if not phase:
            raise ValueError("phase is required for a boundary event")

        item = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "phase": phase,
            "batch_id": batch_id,
            "agent_id": agent_id,
            "section_id": section_id,
            "checkpoint_id": checkpoint_id,
            **details,
        }
        with self._locks_guard:
            lock = self._locks[str(self.path)]
        with lock:
            with self._interprocess_lock():
                manifest = self._read()
                manifest.setdefault("phases", []).append(item)
                self._write(manifest)
        logger.info(
            "%s session_id=%s task_id=%s run_id=%s phase=%s batch_id=%s agent_id=%s section_id=%s checkpoint_id=%s",
            event, self.session_id, self.task_id, self.run_id, phase,
            batch_id, agent_id, section_id, checkpoint_id,
        )
        return item

    def _read(self) -> Dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"session_id": self.session_id, "task_id": self.task_id,
                    "run_id": self.run_id, "phases": []}

    def _write(self, data: Dict[str, Any]) -> None:
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=f".{self.path.stem}.", suffix=".tmp", delete=False
            ) as handle:
                temp_name = handle.name
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)

    @contextmanager
    def _interprocess_lock(self):
        """Serialize read-modify-write across processes on the same host."""
        lock_path = self.path.with_suffix(".lock")
        with open(lock_path, "a+b") as lock_file:
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                if os.name == "nt":
                    import msvcrt
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
