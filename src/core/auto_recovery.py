# -*- coding: utf-8 -*-
"""
Auto Recovery Mechanism
=======================

Phase 4 Week 16 Day 1: Crash Recovery Enhancement

Features:
- Crash detection mechanism - detect sessions not closed normally
- Recovery strategy configuration - quick recovery/full recovery modes
- Task recovery executor - call TaskPersistenceManager to recover tasks
- Recovery state persistence - record recovery history

Dependencies:
- EnhancedWAL (storage_wal.py) - WAL checkpoints and auto repair
- TaskPersistenceManager (task_persistence.py) - task persistence

Configuration system integration:
- Default storage path read from settings.system.data_dir
"""

import os
import json
import uuid
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
import logging

# Configuration system
try:
    from src.config import settings
    SETTINGS_AVAILABLE = True
except ImportError:
    SETTINGS_AVAILABLE = False
    settings = None

# Import dependency modules
from src.core.storage_wal import EnhancedWAL, WALState
from src.core.task_persistence import (
    TaskPersistenceManager,
    TaskState,
    PersistentTask,
    TaskCheckpoint
)

logger = logging.getLogger(__name__)


class RecoveryMode(Enum):
    """
    Recovery mode enumeration
    
    - QUICK: Quick recovery - recover from latest checkpoint only
    - FULL: Full recovery - complete recovery from WAL
    """
    QUICK = "quick"
    FULL = "full"


@dataclass
class RecoveryConfig:
    """
    Recovery configuration
    
    Attributes:
        mode: Recovery mode
        max_retries: Maximum retry attempts
        timeout_seconds: Timeout in seconds
        enable_checksum_validation: Whether to enable checksum validation
        parallel_recovery: Whether to enable parallel recovery
    """
    mode: RecoveryMode = RecoveryMode.QUICK
    max_retries: int = 3
    timeout_seconds: int = 60
    enable_checksum_validation: bool = True
    parallel_recovery: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "mode": self.mode.value,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "enable_checksum_validation": self.enable_checksum_validation,
            "parallel_recovery": self.parallel_recovery,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryConfig":
        """Deserialize from dictionary"""
        return cls(
            mode=RecoveryMode(data.get("mode", "quick")),
            max_retries=data.get("max_retries", 3),
            timeout_seconds=data.get("timeout_seconds", 60),
            enable_checksum_validation=data.get("enable_checksum_validation", True),
            parallel_recovery=data.get("parallel_recovery", False),
        )


@dataclass
class RecoveryResult:
    """
    Recovery result
    
    Attributes:
        success: Whether successful
        tasks_recovered: Number of tasks recovered
        tasks_failed: Number of failed tasks
        duration_seconds: Recovery duration in seconds
        mode: Recovery mode
        errors: List of errors
        timestamp: Recovery timestamp
        recovered_task_ids: List of recovered task IDs
    """
    success: bool = True
    tasks_recovered: int = 0
    tasks_failed: int = 0
    duration_seconds: float = 0.0
    mode: RecoveryMode = RecoveryMode.QUICK
    errors: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    recovered_task_ids: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "success": self.success,
            "tasks_recovered": self.tasks_recovered,
            "tasks_failed": self.tasks_failed,
            "duration_seconds": self.duration_seconds,
            "mode": self.mode.value,
            "errors": self.errors,
            "timestamp": self.timestamp,
            "recovered_task_ids": self.recovered_task_ids,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryResult":
        """Deserialize from dictionary"""
        return cls(
            success=data.get("success", True),
            tasks_recovered=data.get("tasks_recovered", 0),
            tasks_failed=data.get("tasks_failed", 0),
            duration_seconds=data.get("duration_seconds", 0.0),
            mode=RecoveryMode(data.get("mode", "quick")),
            errors=data.get("errors", []),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            recovered_task_ids=data.get("recovered_task_ids", []),
        )


@dataclass
class RecoveryHistoryEntry:
    """
    Recovery history entry
    
    Attributes:
        entry_id: Entry ID
        timestamp: Recovery timestamp
        result: Recovery result
        session_info: Session information
    """
    entry_id: str
    timestamp: str
    result: Dict[str, Any]
    session_info: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "result": self.result,
            "session_info": self.session_info,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryHistoryEntry":
        """Deserialize from dictionary"""
        return cls(
            entry_id=data["entry_id"],
            timestamp=data["timestamp"],
            result=data.get("result", {}),
            session_info=data.get("session_info", {}),
        )


class AutoRecoveryManager:
    """
    Auto Recovery Manager
    
    Features:
    - Crash detection - detect sessions not closed normally
    - Recovery strategy - supports quick recovery and full recovery
    - Task recovery - call TaskPersistenceManager to recover tasks
    - Recovery history - record details of each recovery
    
    Usage example:
        manager = AutoRecoveryManager("/data")
        
        # Detect crashes
        crashed = manager.detect_crashed_sessions()
        
        # Execute recovery
        result = manager.execute_recovery()
        
        # View recovery history
        history = manager.load_recovery_history()
    """
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        config: Optional[RecoveryConfig] = None,
        task_manager: Optional[TaskPersistenceManager] = None,
        wal: Optional[EnhancedWAL] = None
    ):
        """
        Initialize auto recovery manager
        
        Args:
            storage_path: Storage path
            config: Recovery configuration
            task_manager: Task persistence manager (optional)
            wal: EnhancedWAL instance (optional)
        """
        # Read default path from configuration system
        resolved_storage_path: str = storage_path or ""
        if storage_path is None:
            if SETTINGS_AVAILABLE and settings is not None:
                resolved_storage_path = str(Path(settings.system.data_dir))
            else:
                resolved_storage_path = "data"
        
        self.storage_path = Path(resolved_storage_path)
        self.recovery_dir = self.storage_path / "recovery"
        self.history_dir = self.recovery_dir / "history"
        
        # Create directories
        self.recovery_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration
        self.config = config or RecoveryConfig()
        
        # Initialize dependency components
        self._lock = Lock()
        
        # Task manager
        if task_manager is None:
            self.task_manager = TaskPersistenceManager(
                str(self.storage_path / "tasks")
            )
        else:
            self.task_manager = task_manager
        
        # WAL
        if wal is None:
            self.wal = EnhancedWAL(
                str(self.storage_path),
                enable_checksum=self.config.enable_checksum_validation
            )
        else:
            self.wal = wal
        
        # Shutdown marker file path
        self.shutdown_marker_file = self.recovery_dir / "shutdown_marker.json"
        
        logger.info(f"Initialized AutoRecoveryManager: {self.storage_path}")
    
    # ==================== Crash Detection ====================
    
    def detect_crashed_sessions(self) -> List[PersistentTask]:
        """
        Detect crashed sessions
        
        Detects crashes through:
        1. Check if shutdown marker exists
        2. Find tasks in RUNNING or INITIALIZING state
        3. Check if WAL has incomplete checkpoints
        
        Returns:
            List of interrupted tasks
        """
        logger.info("Detecting crashed sessions...")
        
        crashed_tasks = []
        
        # 1. Check shutdown marker
        has_shutdown_marker = self.shutdown_marker_file.exists()
        
        if not has_shutdown_marker:
            logger.warning("Shutdown marker not found, crash may have occurred")
            
            # 2. Find interrupted tasks
            interrupted_tasks = self.task_manager.find_interrupted_tasks()
            
            if interrupted_tasks:
                logger.warning(f"Found {len(interrupted_tasks)} interrupted tasks")
                crashed_tasks.extend(interrupted_tasks)
        
        # 3. Check WAL incomplete checkpoints
        pending_checkpoints = self._detect_pending_checkpoints()
        if pending_checkpoints:
            logger.warning(f"Found {len(pending_checkpoints)} incomplete checkpoints")
        
        return crashed_tasks
    
    def _detect_pending_checkpoints(self) -> List[Path]:
        """
        Detect incomplete checkpoints
        
        Returns:
            List of incomplete checkpoint file paths
        """
        checkpoint_dir = self.wal.checkpoint_dir
        pending_files = list(checkpoint_dir.glob("*.pending"))
        return pending_files
    
    def detect_corrupted_wal_files(self) -> List[Path]:
        """
        Detect corrupted WAL files
        
        Returns:
            List of corrupted WAL file paths
        """
        logger.info("Detecting corrupted WAL files...")
        
        corrupted_files = []
        wal_dir = self.wal.wal_dir
        
        for wal_file in wal_dir.glob("*.wal"):
            if self.wal._is_wal_corrupted(wal_file):
                logger.warning(f"Detected corrupted WAL file: {wal_file}")
                corrupted_files.append(wal_file)
        
        return corrupted_files
    
    # ==================== Recovery Strategy ====================
    
    def execute_recovery(self) -> RecoveryResult:
        """
        Execute recovery
        
        Execute recovery based on configured mode:
        - QUICK: Quick recovery - recover from latest checkpoint only
        - FULL: Full recovery - complete recovery from WAL
        
        Returns:
            Recovery result
        """
        logger.info(f"Executing recovery, mode: {self.config.mode.value}")
        
        start_time = time.time()
        result = RecoveryResult(mode=self.config.mode)
        
        try:
            # Detect crashed sessions
            crashed_tasks = self.detect_crashed_sessions()
            
            if not crashed_tasks:
                logger.info("No tasks need recovery")
                result.success = True
                return result
            
            # Execute recovery based on mode
            if self.config.mode == RecoveryMode.QUICK:
                # Quick recovery: recover from latest checkpoint only
                for task in crashed_tasks:
                    recovery_info = self._recover_task_quick(task)
                    if recovery_info:
                        result.tasks_recovered += 1
                        result.recovered_task_ids.append(task.task_id)
                    else:
                        result.tasks_failed += 1
                        result.errors.append(f"Task {task.task_id} recovery failed")
            
            elif self.config.mode == RecoveryMode.FULL:
                # Full recovery: complete recovery from WAL
                for task in crashed_tasks:
                    recovery_info = self._recover_task_full(task)
                    if recovery_info:
                        result.tasks_recovered += 1
                        result.recovered_task_ids.append(task.task_id)
                    else:
                        result.tasks_failed += 1
                        result.errors.append(f"Task {task.task_id} recovery failed")
            
            # Repair corrupted WAL files
            corrupted_files = self.detect_corrupted_wal_files()
            for corrupted_file in corrupted_files:
                self.wal._repair_wal_file(corrupted_file)
            
            result.success = (result.tasks_failed == 0)
            
        except Exception as e:
            logger.error(f"Recovery failed: {e}")
            result.success = False
            result.errors.append(str(e))
        
        # Calculate duration
        result.duration_seconds = time.time() - start_time
        
        # Save recovery history
        self.save_recovery_history(result)
        
        logger.info(f"Recovery completed: {result.tasks_recovered} tasks recovered, {result.tasks_failed} failed")
        
        return result
    
    def _recover_task_quick(self, task: PersistentTask) -> Optional[Dict[str, Any]]:
        """
        Quick recover single task
        
        Recover from latest checkpoint only
        
        Args:
            task: Task to recover
        
        Returns:
            Recovery info, None if failed
        """
        logger.info(f"Quick recovering task: {task.task_id}")
        
        # Get latest checkpoint
        latest_checkpoint = task.get_latest_checkpoint()
        
        if latest_checkpoint:
            # Recover from checkpoint
            checkpoint_data = self.task_manager.restore_from_checkpoint(
                task.task_id,
                latest_checkpoint.checkpoint_id
            )
            
            if checkpoint_data:
                # Update task state to RUNNING
                self.task_manager.update_task_state(
                    task.task_id,
                    TaskState.RUNNING,
                    progress=checkpoint_data.get("progress", 0.0),
                    message=f"Recovered from checkpoint {latest_checkpoint.step_name}"
                )
                
                logger.info(f"Task {task.task_id} recovered from checkpoint successfully")
                return checkpoint_data
        
        # No checkpoint, restart task
        self.task_manager.update_task_state(
            task.task_id,
            TaskState.RUNNING,
            progress=0.0,
            message="No checkpoint, restarting task"
        )
        
        logger.warning(f"Task {task.task_id} has no checkpoint, restarting")
        return {"step_name": "restart", "progress": 0.0}
    
    def _recover_task_full(self, task: PersistentTask) -> Optional[Dict[str, Any]]:
        """
        Full recover single task
        
        Complete recovery of task state from WAL
        
        Args:
            task: Task to recover
        
        Returns:
            Recovery info, None if failed
        """
        logger.info(f"Full recovering task: {task.task_id}")
        
        # First try to recover from checkpoint
        recovery_info = self._recover_task_quick(task)
        
        if recovery_info:
            # Read additional data from WAL
            wal_entries = self._find_wal_entries_for_task(task.task_id)
            
            if wal_entries:
                # Integrate WAL data into recovery info
                recovery_info["wal_entries"] = len(wal_entries)
                logger.info(f"Read {len(wal_entries)} additional entries from WAL")
            
            return recovery_info
        
        return None
    
    def _find_wal_entries_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Find task-related entries from WAL
        
        Args:
            task_id: Task ID
        
        Returns:
            List of WAL entries
        """
        wal_entries = self.wal.read_all()
        
        # Filter entries related to this task
        task_entries = [
            entry for entry in wal_entries
            if entry.get("task_id") == task_id
        ]
        
        return task_entries
    
    # ==================== Task Recovery Executor ====================
    
    def recover_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Recover single task
        
        Args:
            task_id: Task ID
        
        Returns:
            Recovery info, None if failed
        """
        logger.info(f"Recovering task: {task_id}")
        
        # Load task
        task = self.task_manager.load_task(task_id)
        
        if not task:
            logger.warning(f"Task not found: {task_id}")
            return None
        
        # Recover based on configured mode
        if self.config.mode == RecoveryMode.QUICK:
            return self._recover_task_quick(task)
        else:
            return self._recover_task_full(task)
    
    def recover_all_interrupted_tasks(self) -> RecoveryResult:
        """
        Recover all interrupted tasks
        
        Returns:
            Recovery result
        """
        return self.execute_recovery()
    
    def recover_from_checkpoint(
        self,
        task_id: str,
        checkpoint_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Recover task from specified checkpoint
        
        Args:
            task_id: Task ID
            checkpoint_id: Checkpoint ID
        
        Returns:
            Recovery info, None if failed
        """
        logger.info(f"Recovering task from checkpoint: {task_id} - {checkpoint_id}")
        
        # Recover from checkpoint
        checkpoint_data = self.task_manager.restore_from_checkpoint(
            task_id,
            checkpoint_id
        )
        
        if checkpoint_data:
            # Update task state
            self.task_manager.update_task_state(
                task_id,
                TaskState.RUNNING,
                progress=checkpoint_data.get("progress", 0.0),
                message=f"Recovered from checkpoint {checkpoint_id}"
            )
            
            return checkpoint_data
        
        return None
    
    # ==================== Recovery State Persistence ====================
    
    def save_recovery_history(self, result: RecoveryResult) -> None:
        """
        Save recovery history
        
        Args:
            result: Recovery result
        """
        logger.info("Saving recovery history...")
        
        history_file = self.history_dir / "recovery_history.json"
        
        with self._lock:
            # Read existing history
            history = []
            if history_file.exists():
                try:
                    with open(history_file, 'r', encoding='utf-8') as f:
                        history = json.load(f)
                except (json.JSONDecodeError, IOError):
                    logger.warning("Unable to read existing recovery history")
            
            # Create new entry
            entry = RecoveryHistoryEntry(
                entry_id=f"recovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
                timestamp=result.timestamp,
                result=result.to_dict(),
                session_info={
                    "storage_path": str(self.storage_path),
                    "mode": self.config.mode.value,
                }
            )
            
            # Add to history
            history.append(entry.to_dict())
            
            # Save history
            temp_file = history_file.with_suffix('.tmp')
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Atomic rename
                if history_file.exists():
                    history_file.unlink()
                os.rename(temp_file, history_file)
                
                logger.debug(f"Saved recovery history: {entry.entry_id}")
            
            except Exception as e:
                if temp_file.exists():
                    temp_file.unlink()
                logger.error(f"Failed to save recovery history: {e}")
                raise
    
    def load_recovery_history(self) -> List[Dict[str, Any]]:
        """
        Load recovery history
        
        Returns:
            List of recovery history
        """
        logger.info("Loading recovery history...")
        
        history_file = self.history_dir / "recovery_history.json"
        
        if not history_file.exists():
            return []
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            logger.info(f"Loaded {len(history)} recovery history entries")
            return history
        
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load recovery history: {e}")
            return []
    
    def get_recovery_statistics(self) -> Dict[str, Any]:
        """
        Get recovery statistics
        
        Returns:
            Statistics info
        """
        logger.info("Getting recovery statistics...")
        
        history = self.load_recovery_history()
        
        stats = {
            "total_recoveries": len(history),
            "successful_recoveries": 0,
            "failed_recoveries": 0,
            "total_tasks_recovered": 0,
            "total_tasks_failed": 0,
            "average_duration_seconds": 0.0,
            "by_mode": {},
        }
        
        total_duration = 0.0
        
        for entry in history:
            result = entry.get("result", {})
            
            if result.get("success"):
                stats["successful_recoveries"] += 1
            else:
                stats["failed_recoveries"] += 1
            
            stats["total_tasks_recovered"] += result.get("tasks_recovered", 0)
            stats["total_tasks_failed"] += result.get("tasks_failed", 0)
            
            total_duration += result.get("duration_seconds", 0.0)
            
            # Statistics by mode
            mode = result.get("mode", "unknown")
            stats["by_mode"][mode] = stats["by_mode"].get(mode, 0) + 1
        
        # Calculate average duration
        if stats["total_recoveries"] > 0:
            stats["average_duration_seconds"] = total_duration / stats["total_recoveries"]
        
        logger.info(f"Recovery statistics: {stats}")
        return stats
    
    # ==================== Shutdown Marker Management ====================
    
    def create_shutdown_marker(self) -> None:
        """
        Create shutdown marker
        
        Used to mark normal shutdown
        """
        logger.info("Creating shutdown marker...")
        
        marker_data = {
            "timestamp": datetime.now().isoformat(),
            "session_id": f"session_{uuid.uuid4().hex[:8]}",
            "shutdown_type": "normal",
        }
        
        temp_file = self.shutdown_marker_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(marker_data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            
            # Atomic rename
            if self.shutdown_marker_file.exists():
                self.shutdown_marker_file.unlink()
            os.rename(temp_file, self.shutdown_marker_file)
            
            logger.debug("Shutdown marker created")
        
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            logger.error(f"Failed to create shutdown marker: {e}")
            raise
    
    def remove_shutdown_marker(self) -> None:
        """
        Remove shutdown marker
        
        Used to mark session start
        """
        logger.info("Removing shutdown marker...")
        
        if self.shutdown_marker_file.exists():
            self.shutdown_marker_file.unlink()
            logger.debug("Shutdown marker removed")
    
    def check_shutdown_marker(self) -> Optional[Dict[str, Any]]:
        """
        Check shutdown marker
        
        Returns:
            Marker data, None if not exists
        """
        if not self.shutdown_marker_file.exists():
            return None
        
        try:
            with open(self.shutdown_marker_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        except (json.JSONDecodeError, IOError):
            return None
    
    # ==================== Helper Methods ====================
    
    def get_recovery_status(self) -> Dict[str, Any]:
        """
        Get recovery status
        
        Returns:
            Recovery status info
        """
        crashed_tasks = self.detect_crashed_sessions()
        corrupted_wal = self.detect_corrupted_wal_files()
        pending_checkpoints = self._detect_pending_checkpoints()
        
        return {
            "has_shutdown_marker": self.shutdown_marker_file.exists(),
            "crashed_tasks_count": len(crashed_tasks),
            "corrupted_wal_files": len(corrupted_wal),
            "pending_checkpoints": len(pending_checkpoints),
            "config": self.config.to_dict(),
        }
    
    def cleanup_old_recovery_history(self, keep_days: int = 30) -> int:
        """
        Clean up old recovery history
        
        Args:
            keep_days: Days to keep
        
        Returns:
            Number of entries cleaned
        """
        logger.info(f"Cleaning up recovery history older than {keep_days} days...")
        
        history_file = self.history_dir / "recovery_history.json"
        
        if not history_file.exists():
            return 0
        
        cutoff_date = datetime.now() - timedelta(days=keep_days)
        
        with self._lock:
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                
                # Filter history to keep
                kept_history = []
                cleaned_count = 0
                
                for entry in history:
                    timestamp = entry.get("timestamp")
                    if timestamp:
                        try:
                            entry_date = datetime.fromisoformat(timestamp)
                            if entry_date >= cutoff_date:
                                kept_history.append(entry)
                            else:
                                cleaned_count += 1
                        except ValueError:
                            # Unable to parse time, keep entry
                            kept_history.append(entry)
                
                # Save cleaned history
                if cleaned_count > 0:
                    temp_file = history_file.with_suffix('.tmp')
                    try:
                        with open(temp_file, 'w', encoding='utf-8') as f:
                            json.dump(kept_history, f, ensure_ascii=False, indent=2)
                            f.flush()
                            os.fsync(f.fileno())
                        
                        if history_file.exists():
                            history_file.unlink()
                        os.rename(temp_file, history_file)
                    
                    except Exception as e:
                        if temp_file.exists():
                            temp_file.unlink()
                        raise
                
                logger.info(f"Cleaned {cleaned_count} recovery history entries")
                return cleaned_count
            
            except Exception as e:
                logger.error(f"Failed to clean recovery history: {e}")
                return 0


def create_auto_recovery_manager(
    config: Optional[RecoveryConfig] = None
) -> AutoRecoveryManager:
    """
    Create auto recovery manager from configuration system
    
    Args:
        config: Recovery configuration
    
    Returns:
        Configured AutoRecoveryManager instance
    """
    return AutoRecoveryManager(config=config)