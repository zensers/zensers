from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Optional


class ReportLockManager:
    MAX_LOCKS = 1000

    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_max_wait_seconds: int = 30

    @asynccontextmanager
    async def acquire_lock(self, report_id: str) -> None:
        if report_id not in self._locks:
            self._locks[report_id] = asyncio.Lock()
        lock = self._locks[report_id]
        acquired = False
        try:
            await asyncio.wait_for(
                lock.acquire(),
                timeout=self._lock_max_wait_seconds,
            )
            acquired = True
            yield
        finally:
            if acquired:
                lock.release()
            if report_id in self._locks and not self._locks[report_id].locked():
                del self._locks[report_id]

    def is_locked(self, report_id: str) -> bool:
        lock = self._locks.get(report_id)
        return lock is not None and lock.locked()

    def cleanup(self) -> None:
        stale = [rid for rid, lock in self._locks.items() if not lock.locked()]
        for rid in stale:
            del self._locks[rid]
