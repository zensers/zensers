# -*- coding: utf-8 -*-
"""
SnapshotManager - 快照管理器

管理报告的快照创建、恢复、增量快照、清理等生命周期。
支持可插拔存储后端（默认内存存储）。
"""

from __future__ import annotations

import io
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Protocol

from .revision_types import (
    ChangeRecord,
    ReportTree,
    RestoreResult,
    SnapshotId,
    SnapshotInfo,
    SnapshotType,
)

logger = logging.getLogger(__name__)


class SnapshotStorage(Protocol):
    async def save(self, snapshot_id: SnapshotId, data: bytes) -> bool: ...
    async def load(self, snapshot_id: SnapshotId) -> Optional[bytes]: ...
    async def delete(self, snapshot_id: SnapshotId) -> bool: ...
    async def list_by_report(self, report_id: str) -> List[SnapshotInfo]: ...


class VersionManager(Protocol):
    async def get_current_version(self, report_id: str) -> str: ...
    async def mark_snapshot(self, report_id: str, snapshot_id: SnapshotId) -> None: ...
    async def cleanup_before(self, report_id: str, version: str) -> None: ...


class SnapshotManager:
    _global_instance: Optional["SnapshotManager"] = None
    _instance_lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "SnapshotManager":
        if cls._global_instance is None:
            with cls._instance_lock:
                if cls._global_instance is None:
                    cls._global_instance = cls()
        return cls._global_instance

    def __init__(self, storage: Optional[SnapshotStorage] = None):
        self._storage = storage
        self._memory_store: Dict[SnapshotId, bytes] = {}

    async def create_snapshot(
        self, report: Any, snapshot_type: SnapshotType,
    ) -> SnapshotId:
        snapshot_id = f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        data = self._serialize(report)
        if self._storage is not None:
            await self._storage.save(snapshot_id, data)
        else:
            self._memory_store[snapshot_id] = data
        return snapshot_id

    async def restore_snapshot(self, snapshot_id: SnapshotId) -> Optional[Any]:
        data = None
        if self._storage is not None:
            data = await self._storage.load(snapshot_id)
        if data is None:
            data = self._memory_store.get(snapshot_id)
        if data is None:
            return None
        return self._deserialize(data)

    async def create_incremental(
        self, report: Any, base_snapshot_id: SnapshotId,
        changes: List[ChangeRecord],
    ) -> SnapshotId:
        snapshot_id = f"inc_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        inc_data = {
            "base_snapshot_id": base_snapshot_id,
            "changes": [self._change_to_dict(c) for c in changes],
            "timestamp": datetime.now().isoformat(),
        }
        data = json.dumps(inc_data, ensure_ascii=False).encode("utf-8")
        if self._storage is not None:
            await self._storage.save(snapshot_id, data)
        else:
            self._memory_store[snapshot_id] = data
        return snapshot_id

    async def list_snapshots(
        self, report_id: str,
    ) -> List[SnapshotInfo]:
        if self._storage is not None:
            return await self._storage.list_by_report(report_id)
        return []

    async def cleanup_by_policy(
        self, max_keep: int, max_age_days: int,
        version_manager: Optional[VersionManager] = None,
    ) -> None:
        cutoff = datetime.now() - timedelta(days=max_age_days)
        to_delete: List[SnapshotId] = []
        for sid in list(self._memory_store.keys()):
            age_str = sid.split("_")[1] if "_" in sid else ""
            try:
                snap_time = datetime.strptime(age_str, "%Y%m%d")
                if snap_time < cutoff:
                    to_delete.append(sid)
            except (ValueError, IndexError):
                continue
        for sid in to_delete:
            self._memory_store.pop(sid, None)
            if self._storage is not None:
                await self._storage.delete(sid)

        keep_count = len(self._memory_store)
        if keep_count > max_keep:
            sorted_keys = sorted(self._memory_store.keys(), reverse=True)
            for sid in sorted_keys[max_keep:]:
                self._memory_store.pop(sid, None)
                if self._storage is not None:
                    await self._storage.delete(sid)

    async def delete_snapshots(self, snapshot_ids: List[SnapshotId]) -> None:
        """批量删除指定快照，同步清理内存和后端存储"""
        for sid in snapshot_ids:
            self._memory_store.pop(sid, None)
            if self._storage is not None:
                await self._storage.delete(sid)

    async def restore_nodes(
        self, snapshot_id: SnapshotId, node_ids: List[str],
    ) -> RestoreResult:
        try:
            report = await self.restore_snapshot(snapshot_id)
            if report is None:
                return RestoreResult(
                    success=False, error=f"Snapshot not found: {snapshot_id}",
                )
            return RestoreResult(success=True, restored_ids=node_ids)
        except Exception as e:
            return RestoreResult(success=False, error=str(e))

    async def get_snapshot_chain(
        self, report_id: str,
    ) -> List[SnapshotInfo]:
        snapshots = await self.list_snapshots(report_id)
        snapshots.sort(key=lambda s: s.created_at)
        chain: List[SnapshotInfo] = []
        current_id: Optional[SnapshotId] = None
        snap_map = {s.snapshot_id: s for s in snapshots}

        for s in snapshots:
            if s.parent_id is None:
                current_id = s.snapshot_id
                break

        if current_id is None and snapshots:
            current_id = snapshots[0].snapshot_id

        while current_id and current_id in snap_map:
            chain.append(snap_map[current_id])
            current_id = snap_map[current_id].parent_id

        return chain

    def _serialize(self, report: Any) -> bytes:
        if hasattr(report, "to_dict"):
            report = report.to_dict()
        return json.dumps(report, default=str, ensure_ascii=False).encode("utf-8")

    def _deserialize(self, data: bytes) -> Any:
        return json.loads(data.decode("utf-8"))

    def _change_to_dict(self, change: ChangeRecord) -> Dict[str, Any]:
        return {
            "section_id": change.section_id,
            "field": change.field,
            "old_value": change.old_value,
            "new_value": change.new_value,
            "change_type": change.change_type,
        }
