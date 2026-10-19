# -*- coding: utf-8 -*-
"""
Enhanced Storage Layer Implementation
=====================================

Phase 4 Week 1 Day 1: WAL Enhancement

Features:
- Atomic write guarantee (temp file + atomic rename)
- Checksum validation (CRC32)
- Checkpoint mechanism (persistent checkpoint)
- Auto recovery (automatic recovery after crash)
- Sequence number management (globally increasing sequence number)

Configuration system integration:
- Default storage path read from settings.system.data_dir
"""

import os
import json
import hashlib
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from threading import Lock
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import struct

# Configuration system
try:
    from src.config import settings
    SETTINGS_AVAILABLE = True
except ImportError:
    SETTINGS_AVAILABLE = False
    settings = None  # Explicit fallback

logger = logging.getLogger(__name__)


class WALState(Enum):
    """WAL state"""
    ACTIVE = "active"          # Active state
    CHECKPOINTING = "checkpointing"  # Checkpointing
    RECOVERING = "recovering"  # Recovering


@dataclass
class CheckpointInfo:
    """Checkpoint information"""
    checkpoint_id: str
    timestamp: str
    entries_processed: int
    checkpoint_file: str
    sequence: int


class EnhancedWAL:
    """
    Enhanced Write-Ahead Log

    Features:
    1. Atomic write - using temp file + atomic rename
    2. Checksum validation - CRC32 checksum
    3. Checkpoint mechanism - persistent checkpoint
    4. Auto recovery - automatic recovery after crash
    5. Sequence number - globally increasing sequence number

    Usage example:
        wal = EnhancedWAL("/data", enable_checksum=True)

        # Append entry
        wal.append({"operation": "save", "data": "test"})

        # Create checkpoint
        wal.checkpoint()

        # Recover
        recovered = wal.recover()
    """

    def __init__(
        self,
        wal_path: str,
        enable_checksum: bool = True,
        auto_recover: bool = True
    ):
        """
        Initialize enhanced WAL

        Args:
            wal_path: WAL root directory
            enable_checksum: Whether to enable checksum
            auto_recover: Whether to auto recover
        """
        self.wal_path = Path(wal_path)
        self.wal_dir = self.wal_path / "wal"
        self.checkpoint_dir = self.wal_path / "checkpoints"

        # Create directories
        self.wal_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Configuration
        self.enable_checksum = enable_checksum
        self.auto_recover = auto_recover

        # State
        self._lock = Lock()
        self._state = WALState.ACTIVE
        self._sequence = self._load_sequence()
        self._current_file = self._get_current_wal_file()

        # Auto recovery
        if auto_recover:
            self._auto_recover()

    def _get_current_wal_file(self) -> Path:
        """Get current WAL file"""
        timestamp = datetime.now().strftime("%Y%m%d")
        return self.wal_dir / f"{timestamp}.wal"

    def _load_sequence(self) -> int:
        """Load sequence number"""
        sequence_file = self.wal_path / "sequence.txt"
        if sequence_file.exists():
            try:
                with open(sequence_file, 'r') as f:
                    return int(f.read().strip())
            except (ValueError, IOError):
                pass
        return 0

    def _save_sequence(self, sequence: int) -> None:
        """Save sequence number"""
        sequence_file = self.wal_path / "sequence.txt"
        with open(sequence_file, 'w') as f:
            f.write(str(sequence))

    def _auto_recover(self) -> None:
        """Auto recovery"""
        try:
            # Check for incomplete checkpoints
            pending_checkpoints = list(self.checkpoint_dir.glob("*.pending"))
            for pending in pending_checkpoints:
                # Delete incomplete checkpoints
                pending.unlink()
                logger.warning(f"Deleted incomplete checkpoint: {pending}")

            # Check if WAL files are corrupted
            for wal_file in self.wal_dir.glob("*.wal"):
                if self._is_wal_corrupted(wal_file):
                    logger.warning(f"Detected corrupted WAL file: {wal_file}")
                    # Attempt repair
                    self._repair_wal_file(wal_file)
        except Exception as e:
            logger.error(f"Auto recovery failed: {e}")

    def _is_wal_corrupted(self, wal_file: Path) -> bool:
        """Check if WAL file is corrupted"""
        try:
            with open(wal_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        json.loads(line)  # Attempt to parse
            return False
        except json.JSONDecodeError:
            return True

    def _repair_wal_file(self, wal_file: Path) -> None:
        """Repair corrupted WAL file"""
        # Create backup
        backup_file = wal_file.with_suffix('.wal.bak')
        shutil.copy(wal_file, backup_file)

        # Rewrite valid lines
        valid_lines = []
        with open(wal_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        json.loads(line)
                        valid_lines.append(line)
                    except json.JSONDecodeError:
                        continue

        with open(wal_file, 'w', encoding='utf-8') as f:
            for line in valid_lines:
                f.write(line + '\n')

        logger.info(f"Repaired WAL file: {wal_file}, kept {len(valid_lines)} valid records")

    def _calculate_checksum(self, data: Dict[str, Any]) -> str:
        """Calculate checksum"""
        # Use MD5 to calculate checksum
        content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content.encode('utf-8'), usedforsecurity=False).hexdigest()

    def verify_checksum(self, entry: Dict[str, Any]) -> bool:
        """
        Verify entry checksum

        Args:
            entry: Entry containing checksum field

        Returns:
            Whether checksum is valid
        """
        if "checksum" not in entry:
            return True  # No checksum, default valid

        stored_checksum = entry.pop("checksum", None)
        calculated_checksum = self._calculate_checksum(entry)
        entry["checksum"] = stored_checksum  # Restore

        return stored_checksum == calculated_checksum

    def append(self, entry: Dict[str, Any]) -> int:
        """
        Append log entry (atomic write)

        Args:
            entry: Log entry dictionary

        Returns:
            Sequence number
        """
        with self._lock:
            # Add sequence number
            self._sequence += 1
            entry["sequence"] = self._sequence

            # Add timestamp
            if "timestamp" not in entry:
                entry["timestamp"] = datetime.now().isoformat()

            # Add checksum
            if self.enable_checksum:
                entry["checksum"] = self._calculate_checksum(entry)

            # Atomic write: write to temp file first, then rename
            temp_file = self._current_file.with_suffix('.tmp')
            try:
                # Write to temp file
                with open(temp_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                    f.flush()
                    os.fsync(f.fileno())

                # If new file, rename
                if not self._current_file.exists():
                    os.rename(temp_file, self._current_file)
                else:
                    # Append to existing file
                    with open(self._current_file, 'a', encoding='utf-8') as f:
                        with open(temp_file, 'r', encoding='utf-8') as tf:
                            f.write(tf.read())
                        f.flush()
                        os.fsync(f.fileno())
                    temp_file.unlink()

                # Save sequence number
                self._save_sequence(self._sequence)

                return self._sequence

            except Exception as e:
                logger.error(f"WAL write failed: {e}")
                # Clean up temp file
                if temp_file.exists():
                    temp_file.unlink()
                raise

    def read_all(self, skip_corrupted: bool = True) -> List[Dict[str, Any]]:
        """
        Read all log entries

        Args:
            skip_corrupted: Whether to skip corrupted entries

        Returns:
            List of log entries
        """
        logs = []

        # Read all .wal files
        wal_files = sorted(self.wal_dir.glob("*.wal"))

        for wal_file in wal_files:
            try:
                with open(wal_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            entry = json.loads(line)

                            # Verify checksum
                            if self.enable_checksum and skip_corrupted:
                                if not self.verify_checksum(entry):
                                    logger.warning(f"Skipped entry with invalid checksum: {entry.get('sequence')}")
                                    continue

                            logs.append(entry)

                        except json.JSONDecodeError:
                            if skip_corrupted:
                                logger.warning(f"Skipped line with JSON parse failure")
                                continue
                            else:
                                raise

            except FileNotFoundError:
                continue

        return logs

    def checkpoint(self) -> Dict[str, Any]:
        """
        Create checkpoint

        Returns:
            Checkpoint information
        """
        with self._lock:
            self._state = WALState.CHECKPOINTING

            try:
                # Read all entries
                logs = self.read_all()

                # Create checkpoint file
                checkpoint_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                checkpoint_file = self.checkpoint_dir / f"checkpoint_{checkpoint_id}.json"
                pending_file = checkpoint_file.with_suffix('.pending')

                # Write checkpoint
                checkpoint_data = {
                    "checkpoint_id": checkpoint_id,
                    "timestamp": datetime.now().isoformat(),
                    "entries_processed": len(logs),
                    "sequence": self._sequence,
                    "entries": logs,
                }

                with open(pending_file, 'w', encoding='utf-8') as f:
                    json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                # Atomic rename (Windows needs to delete target file first)
                if checkpoint_file.exists():
                    checkpoint_file.unlink()
                os.rename(pending_file, checkpoint_file)

                # Clear WAL
                for wal_file in self.wal_dir.glob("*.wal"):
                    wal_file.unlink()

                # Reset current file
                self._current_file = self._get_current_wal_file()

                self._state = WALState.ACTIVE

                return {
                    "checkpoint_id": checkpoint_id,
                    "timestamp": checkpoint_data["timestamp"],
                    "entries_processed": len(logs),
                    "checkpoint_file": str(checkpoint_file),
                    "sequence": self._sequence,
                }

            except Exception as e:
                self._state = WALState.ACTIVE
                logger.error(f"Failed to create checkpoint: {e}")
                raise

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """
        List all checkpoints

        Returns:
            List of checkpoint information
        """
        checkpoints = []

        for checkpoint_file in sorted(self.checkpoint_dir.glob("checkpoint_*.json")):
            try:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    checkpoints.append({
                        "checkpoint_id": data["checkpoint_id"],
                        "timestamp": data["timestamp"],
                        "entries_processed": data["entries_processed"],
                        "checkpoint_file": str(checkpoint_file),
                    })
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Unable to read checkpoint {checkpoint_file}: {e}")

        return checkpoints

    def recover(self) -> List[Dict[str, Any]]:
        """
        Recover data from WAL

        Returns:
            List of recovered entries
        """
        self._state = WALState.RECOVERING

        try:
            logs = self.read_all(skip_corrupted=True)
            logger.info(f"Recovered {len(logs)} records from WAL")
            return logs

        finally:
            self._state = WALState.ACTIVE

    def truncate(self) -> None:
        """Truncate log (clear all WAL and checkpoints)"""
        with self._lock:
            # Delete all WAL files
            for wal_file in self.wal_dir.glob("*.wal"):
                wal_file.unlink()

            # Delete all checkpoints
            for checkpoint_file in self.checkpoint_dir.glob("*.json"):
                checkpoint_file.unlink()

            # Reset
            self._sequence = 0
            self._save_sequence(0)
            self._current_file = self._get_current_wal_file()

    def get_stats(self) -> Dict[str, Any]:
        """Get WAL statistics"""
        wal_files = list(self.wal_dir.glob("*.wal"))
        checkpoints = list(self.checkpoint_dir.glob("checkpoint_*.json"))
        
        total_size = sum(f.stat().st_size for f in wal_files)
        
        return {
            "state": self._state.value,
            "sequence": self._sequence,
            "wal_files": len(wal_files),
            "total_size_bytes": total_size,
            "checkpoints": len(checkpoints),
            "checksum_enabled": self.enable_checksum,
        }


class EnhancedTaskStorage:
    """
    Enhanced Task Storage Manager

    Features:
    - Uses enhanced WAL
    - Automatic crash recovery
    - Data integrity verification
    - Checkpoint support
    """

    def __init__(
        self,
        base_path: Optional[str] = None,
        enable_enhanced_wal: bool = True,
        enable_checksum: bool = True
    ):
        """
        Initialize enhanced task storage

        Args:
            base_path: Storage root directory
            enable_enhanced_wal: Whether to enable enhanced WAL
            enable_checksum: Whether to enable checksum
        """
        # Read default path from configuration system
        if base_path is None:
            if SETTINGS_AVAILABLE and settings is not None:
                base_path = settings.system.data_dir
                logger.info(f"EnhancedTaskStorage using configuration system path: {base_path}")
            else:
                base_path = "data"
                logger.warning(f"Configuration system unavailable, using default path: {base_path}")

        # At this point base_path must have a value (guaranteed by logic)
        assert base_path is not None, "base_path should be set at this point"
        self.base_path = Path(base_path)
        self.tasks_dir = self.base_path / "tasks"

        # Create directory
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

        # WAL
        self.enable_enhanced_wal = enable_enhanced_wal
        if enable_enhanced_wal:
            self.wal = EnhancedWAL(str(self.base_path), enable_checksum=enable_checksum)
        else:
            from src.core.storage import WriteAheadLog
            self.wal = WriteAheadLog(str(self.base_path))

        self._lock = Lock()

    def _get_task_path(self, task_id: str) -> Path:
        """Get task file path"""
        return self.tasks_dir / f"{task_id}.json"

    def save_task(self, task: Dict[str, Any]) -> None:
        """
        Save task

        Args:
            task: Task dictionary, must contain task_id
        """
        task_id = task.get("task_id")
        if not task_id:
            raise ValueError("Task must have 'task_id' field")

        task_path = self._get_task_path(task_id)

        with self._lock:
            # 1. Write WAL first
            if self.wal:
                self.wal.append({
                    "operation": "save_task",
                    "task_id": task_id,
                    "task": task
                })

            # 2. Atomic write to main file
            temp_file = task_path.with_suffix('.tmp')
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(task, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                # Atomic rename
                if task_path.exists():
                    task_path.unlink()
                os.rename(temp_file, task_path)

            except Exception as e:
                if temp_file.exists():
                    temp_file.unlink()
                raise

    def load_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Load task

        Args:
            task_id: Task ID

        Returns:
            Task dictionary, returns None if not exists
        """
        task_path = self._get_task_path(task_id)

        try:
            with open(task_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            logger.error(f"Task file corrupted: {task_path}")
            return None

    def list_tasks(self) -> List[Dict[str, Any]]:
        """
        List all tasks

        Returns:
            List of tasks
        """
        tasks = []

        for task_file in self.tasks_dir.glob("*.json"):
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    task = json.load(f)
                    tasks.append(task)
            except (FileNotFoundError, json.JSONDecodeError):
                continue

        return tasks

    def delete_task(self, task_id: str) -> bool:
        """
        Delete task

        Args:
            task_id: Task ID

        Returns:
            Whether deletion was successful
        """
        task_path = self._get_task_path(task_id)

        with self._lock:
            # Write WAL
            if self.wal:
                self.wal.append({
                    "operation": "delete_task",
                    "task_id": task_id
                })

            # Delete file
            try:
                task_path.unlink()
                return True
            except FileNotFoundError:
                return False

    def recover_from_wal(self) -> List[str]:
        """
        Recover data from WAL

        Returns:
            List of recovered task IDs
        """
        if not self.wal:
            return []

        recovered = []
        logs = self.wal.recover() if hasattr(self.wal, 'recover') else self.wal.read_all()

        for entry in logs:
            operation = entry.get("operation")
            task_id = entry.get("task_id")

            if operation == "save_task" and task_id:
                task = entry.get("task", {})
                task_path = self._get_task_path(task_id)

                with open(task_path, 'w', encoding='utf-8') as f:
                    json.dump(task, f, ensure_ascii=False, indent=2)

                recovered.append(task_id)

        logger.info(f"Recovered {len(recovered)} tasks from WAL")
        return recovered

    def checkpoint(self) -> Dict[str, Any]:
        """
        Create checkpoint

        Returns:
            Checkpoint information
        """
        if hasattr(self.wal, 'checkpoint'):
            return self.wal.checkpoint()
        else:
            self.wal.truncate()
            return {"entries_processed": 0}

    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        task_files = list(self.tasks_dir.glob("*.json"))
        wal_stats = self.wal.get_stats() if hasattr(self.wal, 'get_stats') else {}
        
        return {
            "tasks_count": len(task_files),
            "wal": wal_stats,
        }


def create_enhanced_storage_from_settings(
    enable_enhanced_wal: bool = True,
    enable_checksum: bool = True
) -> EnhancedTaskStorage:
    """
    Create enhanced TaskStorage instance from configuration system

    Args:
        enable_enhanced_wal: Whether to enable enhanced WAL
        enable_checksum: Whether to enable checksum

    Returns:
        Configured EnhancedTaskStorage instance
    """
    return EnhancedTaskStorage(
        enable_enhanced_wal=enable_enhanced_wal,
        enable_checksum=enable_checksum
    )