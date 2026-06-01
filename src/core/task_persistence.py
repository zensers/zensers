# -*- coding: utf-8 -*-
"""
Task Persistence Manager
========================

Phase 4 Week 1 Day 2: Task Persistence

Features:
- Task state persistence
- Incremental saving
- Recovery mechanism
- Checkpoint support
- State history tracking

Configuration system integration:
- Default storage path read from settings.system.data_dir
"""

import os
import json
import uuid
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
    settings = None  # Explicit fallback

logger = logging.getLogger(__name__)


class TaskState(Enum):
    """Task state enumeration"""
    CREATED = "created"           # Created
    INITIALIZING = "initializing" # Initializing
    RUNNING = "running"           # Running
    PAUSED = "paused"             # Paused
    COMPLETED = "completed"       # Completed
    FAILED = "failed"             # Failed
    
    def is_terminal(self) -> bool:
        """Check if terminal state"""
        return self in (TaskState.COMPLETED, TaskState.FAILED)
    
    def is_active(self) -> bool:
        """Check if active state"""
        return self in (TaskState.CREATED, TaskState.INITIALIZING, TaskState.RUNNING, TaskState.PAUSED)


@dataclass
class TaskStatus:
    """Task status info"""
    task_id: str
    state: TaskState
    progress: float = 0.0
    message: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskStatus":
        """Deserialize from dictionary"""
        return cls(
            task_id=data["task_id"],
            state=TaskState(data["state"]),
            progress=data.get("progress", 0.0),
            message=data.get("message", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )


@dataclass
class TaskCheckpoint:
    """Task checkpoint"""
    checkpoint_id: str
    task_id: str
    step_name: str
    step_index: int
    total_steps: int
    data: Dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def progress(self) -> float:
        """Calculate progress"""
        return self.step_index / self.total_steps if self.total_steps > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "checkpoint_id": self.checkpoint_id,
            "task_id": self.task_id,
            "step_name": self.step_name,
            "step_index": self.step_index,
            "total_steps": self.total_steps,
            "data": self.data,
            "progress": self.progress,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskCheckpoint":
        """Deserialize from dictionary"""
        return cls(
            checkpoint_id=data["checkpoint_id"],
            task_id=data["task_id"],
            step_name=data["step_name"],
            step_index=data["step_index"],
            total_steps=data["total_steps"],
            data=data.get("data", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class PersistentTask:
    """Persistent task"""
    task_id: str
    task_type: str
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status: Optional[TaskStatus] = field(default=None)
    checkpoints: List[TaskCheckpoint] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Execution state tracking (for resume/revise)
    execution_state: Dict[str, Any] = field(default_factory=lambda: {
        "completed_agents": [],     # [{"agent_id": "...", "success": true, "phase": "data_collection"}, ...]
        "completed_phases": [],     # ["data_collection", "deep_analysis"]
        "current_phase": "",
        "failed_agents": [],
    })
    
    # Add type ignore annotation, since __post_init__ will ensure status is not None
    _status_initialized: bool = field(default=False, init=False, repr=False)
    
    def __post_init__(self):
        """Post-initialization processing"""
        if self.status is None:
            self.status = TaskStatus(
                task_id=self.task_id,
                state=TaskState.CREATED,
            )
        self._status_initialized = True
    
    def _ensure_status(self) -> TaskStatus:
        """Ensure status is initialized"""
        if self.status is None:
            self.status = TaskStatus(
                task_id=self.task_id,
                state=TaskState.CREATED,
            )
        return self.status
    
    def start(self) -> None:
        """Start task"""
        status = self._ensure_status()
        status.state = TaskState.RUNNING
        status.updated_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def complete(self, result: Dict[str, Any]) -> None:
        """Complete task"""
        status = self._ensure_status()
        status.state = TaskState.COMPLETED
        status.progress = 1.0
        self.result = result
        status.updated_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def fail(self, error: str) -> None:
        """Fail task"""
        status = self._ensure_status()
        status.state = TaskState.FAILED
        self.error = error
        status.updated_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def pause(self) -> None:
        """Pause task"""
        status = self._ensure_status()
        status.state = TaskState.PAUSED
        status.updated_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def resume(self) -> None:
        """Resume task"""
        status = self._ensure_status()
        status.state = TaskState.RUNNING
        status.updated_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def update_progress(self, progress: float, message: str = "") -> None:
        """Update progress"""
        status = self._ensure_status()
        status.progress = min(1.0, max(0.0, progress))
        status.message = message
        status.updated_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
    
    def add_checkpoint(self, checkpoint: TaskCheckpoint) -> None:
        """Add checkpoint"""
        self.checkpoints.append(checkpoint)
        self.updated_at = datetime.now().isoformat()
    
    def get_latest_checkpoint(self) -> Optional[TaskCheckpoint]:
        """Get latest checkpoint"""
        return self.checkpoints[-1] if self.checkpoints else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "result": self.result,
            "error": self.error,
            "status": self.status.to_dict() if self.status else None,
            "checkpoints": [cp.to_dict() for cp in self.checkpoints],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersistentTask":
        """Deserialize from dictionary"""
        return cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            input_data=data.get("input_data", {}),
            output_data=data.get("output_data"),
            result=data.get("result"),
            error=data.get("error"),
            status=TaskStatus.from_dict(data["status"]) if data.get("status") else None,
            checkpoints=[TaskCheckpoint.from_dict(cp) for cp in data.get("checkpoints", [])],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )


class TaskPersistenceManager:
    """
    Task Persistence Manager
    
    Features:
    - Task creation, saving, loading
    - State update and tracking
    - Checkpoint management
    - Crash recovery
    - State history recording
    
    Usage example:
        manager = TaskPersistenceManager("/data/tasks")
        
        # Create task
        task = manager.create_task("research", {"query": "test"})
        
        # Update state
        manager.update_task_state(task.task_id, TaskState.RUNNING)
        
        # Create checkpoint
        checkpoint = manager.create_checkpoint(task.task_id, "step_1", 1, 5, {})
        
        # Recover tasks
        recovered = manager.recover_all_tasks()
    """
    
    def __init__(
        self, 
        storage_path: Optional[str] = None,
        track_history: bool = False
    ):
        """
        Initialize task persistence manager
        
        Args:
            storage_path: Storage path (used directly as tasks_dir, no nesting)
            track_history: Whether to track state history
        """
        # Read default path from configuration system
        resolved_storage_path: str = storage_path or ""  # Explicit type
        if storage_path is None:
            if SETTINGS_AVAILABLE and settings is not None:
                # Use tasks_dir from config
                resolved_storage_path = getattr(settings.system, 'tasks_dir', 'data/tasks')
            else:
                resolved_storage_path = "data/tasks"
        
        self.storage_path = Path(resolved_storage_path)
        self.tasks_dir = self.storage_path  # Use storage_path directly as tasks_dir
        self.history_dir = self.storage_path.parent / "task_history"
        
        # Create directories
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        if track_history:
            self.history_dir.mkdir(parents=True, exist_ok=True)
        
        self.track_history = track_history
        self._lock = Lock()
    
    def _get_task_path(self, task_id: str) -> Path:
        """Get task file path"""
        return self.tasks_dir / f"{task_id}.json"
    
    def _get_history_path(self, task_id: str) -> Path:
        """Get history file path"""
        return self.history_dir / f"{task_id}_history.json"
    
    def _generate_task_id(self) -> str:
        """Generate task ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        return f"task_{timestamp}_{unique_id}"
    
    def create_task(
        self, 
        task_type: str, 
        input_data: Dict[str, Any],
        task_id: Optional[str] = None
    ) -> PersistentTask:
        """
        Create new task
        
        Args:
            task_type: Task type
            input_data: Input data
            task_id: Optional task ID
        
        Returns:
            Created task
        """
        task_id = task_id or self._generate_task_id()
        
        task = PersistentTask(
            task_id=task_id,
            task_type=task_type,
            input_data=input_data,
        )
        
        logger.info(f"Created task: {task_id} ({task_type})")
        return task
    
    def save_task(self, task: PersistentTask) -> None:
        """
        Save task
        
        Args:
            task: Task to save
        """
        task_path = self._get_task_path(task.task_id)
        
        with self._lock:
            # Atomic write
            temp_path = task_path.with_suffix('.tmp')
            try:
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(task.to_dict(), f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Atomic rename
                if task_path.exists():
                    task_path.unlink()
                os.rename(temp_path, task_path)
                
                logger.debug(f"Saved task: {task.task_id}")
            
            except Exception as e:
                if temp_path.exists():
                    temp_path.unlink()
                logger.error(f"Failed to save task: {e}")
                raise
    
    def load_task(self, task_id: str) -> Optional[PersistentTask]:
        """
        Load task
        
        Args:
            task_id: Task ID
        
        Returns:
            Task object, None if not exists
        """
        task_path = self._get_task_path(task_id)
        
        try:
            with open(task_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return PersistentTask.from_dict(data)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted task file: {task_path}: {e}")
            return None
    
    def update_task_state(
        self, 
        task_id: str, 
        state: TaskState, 
        progress: Optional[float] = None,
        message: str = ""
    ) -> bool:
        """
        Update task state
        
        Args:
            task_id: Task ID
            state: New state
            progress: Progress (optional)
            message: Message
        
        Returns:
            Whether successfully updated
        """
        task = self.load_task(task_id)
        if not task:
            logger.warning(f"Task not found: {task_id}")
            return False
        
        # Record history
        if self.track_history:
            self._record_state_change(task)
        
        # Update state
        status = task._ensure_status()
        old_state = status.state
        status.state = state
        if progress is not None:
            status.progress = progress
        status.message = message
        status.updated_at = datetime.now().isoformat()
        task.updated_at = datetime.now().isoformat()
        
        # Save
        self.save_task(task)
        
        logger.info(f"Task state updated: {task_id} {old_state.value} -> {state.value}")
        return True
    
    def _record_state_change(self, task: PersistentTask) -> None:
        """Record state change"""
        if not self.track_history:
            return
        
        status = task._ensure_status()
        history_path = self._get_history_path(task.task_id)
        
        # Read existing history
        history = []
        if history_path.exists():
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except (json.JSONDecodeError, IOError, OSError, UnicodeDecodeError):
                pass
        
        # Add new record
        history.append({
            "state": status.state.value,
            "progress": status.progress,
            "message": status.message,
            "timestamp": datetime.now().isoformat(),
        })
        
        # Save history
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    
    def get_state_history(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Get state history
        
        Args:
            task_id: Task ID
        
        Returns:
            State history list
        """
        if not self.track_history:
            return []
        
        history_path = self._get_history_path(task_id)
        
        if not history_path.exists():
            return []
        
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, OSError, UnicodeDecodeError):
            return []
    
    def create_checkpoint(
        self,
        task_id: str,
        step_name: str,
        step_index: int,
        total_steps: int,
        data: Dict[str, Any]
    ) -> Optional[TaskCheckpoint]:
        """
        Create checkpoint
        
        Args:
            task_id: Task ID
            step_name: Step name
            step_index: Step index
            total_steps: Total steps
            data: Checkpoint data
        
        Returns:
            Created checkpoint
        """
        task = self.load_task(task_id)
        if not task:
            logger.warning(f"Task not found: {task_id}")
            return None
        
        # Create checkpoint
        checkpoint = TaskCheckpoint(
            checkpoint_id=f"cp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            task_id=task_id,
            step_name=step_name,
            step_index=step_index,
            total_steps=total_steps,
            data=data,
        )
        
        # Add to task
        task.add_checkpoint(checkpoint)
        
        # Save
        self.save_task(task)
        
        logger.info(f"Created checkpoint: {task_id} - {step_name} ({step_index}/{total_steps})")
        return checkpoint
    
    def restore_from_checkpoint(
        self, 
        task_id: str, 
        checkpoint_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Restore from checkpoint
        
        Args:
            task_id: Task ID
            checkpoint_id: Checkpoint ID
        
        Returns:
            Checkpoint data
        """
        task = self.load_task(task_id)
        if not task:
            return None
        
        # Find checkpoint
        for checkpoint in task.checkpoints:
            if checkpoint.checkpoint_id == checkpoint_id:
                logger.info(f"Restored from checkpoint: {task_id} - {checkpoint_id}")
                return {
                    "step_name": checkpoint.step_name,
                    "step_index": checkpoint.step_index,
                    "total_steps": checkpoint.total_steps,
                    "data": checkpoint.data,
                    "progress": checkpoint.progress,
                }
        
        logger.warning(f"Checkpoint not found: {checkpoint_id}")
        return None
    
    def list_active_tasks(self) -> List[PersistentTask]:
        """
        List all active tasks
        
        Returns:
            Active task list
        """
        active_tasks = []
        
        for task_file in self.tasks_dir.glob("*.json"):
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    task = PersistentTask.from_dict(data)
                    status = task._ensure_status()
                    if status.state.is_active():
                        active_tasks.append(task)
            except (json.JSONDecodeError, IOError, OSError, ValueError, AttributeError):
                continue
        
        return active_tasks
    
    def list_tasks_by_state(self, state: TaskState) -> List[PersistentTask]:
        """
        List tasks by state
        
        Args:
            state: Task state
        
        Returns:
            Task list
        """
        tasks = []
        
        for task_file in self.tasks_dir.glob("*.json"):
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    task = PersistentTask.from_dict(data)
                    status = task._ensure_status()
                    if status.state == state:
                        tasks.append(task)
            except (json.JSONDecodeError, IOError, OSError, ValueError, AttributeError):
                continue
        
        return tasks
    
    def cleanup_completed_tasks(self, keep_days: int = 7) -> int:
        """
        Cleanup completed tasks
        
        Args:
            keep_days: Days to keep
        
        Returns:
            Number of cleaned tasks
        """
        cleaned = 0
        cutoff = datetime.now() - timedelta(days=keep_days)
        
        for task_file in self.tasks_dir.glob("*.json"):
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    task = PersistentTask.from_dict(data)
                
                # Check if completed/failed state
                status = task._ensure_status()
                if not status.state.is_terminal():
                    continue
                
                # Check time
                updated_at = datetime.fromisoformat(task.updated_at)
                if updated_at < cutoff:
                    task_file.unlink()
                    cleaned += 1
                    logger.debug(f"Cleaned task: {task.task_id}")
            
            except Exception as e:
                logger.warning(f"Failed to cleanup task: {task_file}: {e}")
                continue
        
        logger.info(f"Cleaned {cleaned} completed tasks")
        return cleaned
    
    def recover_all_tasks(self) -> List[PersistentTask]:
        """
        Recover all tasks
        
        Returns:
            Recovered task list
        """
        tasks = []
        
        for task_file in self.tasks_dir.glob("*.json"):
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    task = PersistentTask.from_dict(data)
                    tasks.append(task)
            except (json.JSONDecodeError, IOError, OSError, ValueError, AttributeError):
                continue
        
        logger.info(f"Recovered {len(tasks)} tasks")
        return tasks
    
    def find_interrupted_tasks(self) -> List[PersistentTask]:
        """
        Find interrupted tasks (running or paused state)
        
        Returns:
            Interrupted task list
        """
        interrupted = []
        
        for task in self.recover_all_tasks():
            status = task._ensure_status()
            if status.state in (TaskState.RUNNING, TaskState.INITIALIZING):
                interrupted.append(task)
        
        logger.info(f"Found {len(interrupted)} interrupted tasks")
        return interrupted
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get task statistics
        
        Returns:
            Statistics info
        """
        stats = {
            "total": 0,
            "by_state": {},
            "by_type": {},
        }
        
        for task in self.recover_all_tasks():
            stats["total"] += 1
            
            # By state
            status = task._ensure_status()
            state_name = status.state.value
            stats["by_state"][state_name] = stats["by_state"].get(state_name, 0) + 1
            
            # By type
            stats["by_type"][task.task_type] = stats["by_type"].get(task.task_type, 0) + 1
        
        return stats
    
    # ===== Phase 9: Survey Task Support =====
    
    async def save_survey_task(self, survey_task: Any) -> None:
        """
        Save survey task
        
        Phase 9: Survey system integration with main controller
        
        Args:
            survey_task: SurveyTask object
        """
        from src.survey.models import SurveyTask as SurveyTaskModel
        
        if not isinstance(survey_task, SurveyTaskModel):
            raise TypeError(f"Expected SurveyTask, got {type(survey_task)}")
        
        # Create dedicated survey task directory
        survey_dir = self.storage_path / "surveys"
        survey_dir.mkdir(parents=True, exist_ok=True)
        
        task_path = survey_dir / f"{survey_task.task_id}.json"
        
        # Use async file operations (simplified: execute sync IO in thread pool)
        loop = asyncio.get_running_loop()
        
        def _sync_save():
            with self._lock:
                with open(task_path, 'w', encoding='utf-8') as f:
                    json.dump(survey_task.to_dict(), f, ensure_ascii=False, indent=2)
        
        await loop.run_in_executor(None, _sync_save)
        logger.debug(f"Saved survey task: {survey_task.task_id}")
    
    async def load_survey_task(self, task_id: str) -> Optional[Any]:
        """
        Load survey task
        
        Args:
            task_id: Task ID
            
        Returns:
            SurveyTask object or None
        """
        from src.survey.models import SurveyTask as SurveyTaskModel
        
        survey_dir = self.storage_path / "surveys"
        task_path = survey_dir / f"{task_id}.json"
        
        if not task_path.exists():
            return None
        
        loop = asyncio.get_running_loop()
        
        def _sync_load():
            try:
                with open(task_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load survey task {task_id}: {e}")
                return None
        
        data = await loop.run_in_executor(None, _sync_load)
        if data:
            return SurveyTaskModel.from_dict(data)
        return None
    
    async def find_survey_tasks_by_status(self, status: Any) -> List[Any]:
        """
        Find survey tasks by status
        
        Args:
            status: SurveyStatus enum value
            
        Returns:
            Matching SurveyTask list
        """
        from src.survey.models import SurveyTask as SurveyTaskModel, SurveyStatus
        
        survey_dir = self.storage_path / "surveys"
        if not survey_dir.exists():
            return []
        
        loop = asyncio.get_running_loop()
        
        def _sync_find():
            tasks = []
            for task_file in survey_dir.glob("*.json"):
                try:
                    with open(task_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    task = SurveyTaskModel.from_dict(data)
                    if task.status == status:
                        tasks.append(task)
                except Exception as e:
                    logger.warning(f"Failed to load survey task from {task_file}: {e}")
                    continue
            return tasks
        
        return await loop.run_in_executor(None, _sync_find)
    
    async def find_child_survey_tasks(self, parent_task_id: str) -> List[Any]:
        """
        Find survey tasks associated with main controller task
        
        Args:
            parent_task_id: Main controller task ID
            
        Returns:
            Associated SurveyTask list
        """
        from src.survey.models import SurveyTask as SurveyTaskModel
        
        survey_dir = self.storage_path / "surveys"
        if not survey_dir.exists():
            return []
        
        loop = asyncio.get_running_loop()
        
        def _sync_find():
            tasks = []
            for task_file in survey_dir.glob("*.json"):
                try:
                    with open(task_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    task = SurveyTaskModel.from_dict(data)
                    if task.parent_task_id == parent_task_id:
                        tasks.append(task)
                except Exception as e:
                    logger.warning(f"Failed to load survey task from {task_file}: {e}")
                    continue
            return tasks
        
        return await loop.run_in_executor(None, _sync_find)
    
    async def list_all_survey_tasks(self) -> List[Any]:
        """
        List all survey tasks
        
        Returns:
            All SurveyTask list
        """
        from src.survey.models import SurveyTask as SurveyTaskModel
        
        survey_dir = self.storage_path / "surveys"
        if not survey_dir.exists():
            return []
        
        loop = asyncio.get_running_loop()
        
        def _sync_list():
            tasks = []
            for task_file in survey_dir.glob("*.json"):
                try:
                    with open(task_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    tasks.append(SurveyTaskModel.from_dict(data))
                except Exception as e:
                    logger.warning(f"Failed to load survey task from {task_file}: {e}")
                    continue
            return tasks
        
        return await loop.run_in_executor(None, _sync_list)


def create_task_persistence_manager(
    track_history: bool = False
) -> TaskPersistenceManager:
    """
    Create task persistence manager from configuration system
    
    Args:
        track_history: Whether to track state history
    
    Returns:
        Configured TaskPersistenceManager instance
    """
    return TaskPersistenceManager(track_history=track_history)