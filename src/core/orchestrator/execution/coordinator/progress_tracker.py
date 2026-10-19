"""
进度追踪器

职责：
- 任务进度更新
- 停滞任务检测
- 进度聚合
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskProgress:
    """
    任务进度
    
    Attributes:
        task_id: 任务ID
        progress: 进度值（0.0-1.0）
        status: 状态描述
        started_at: 开始时间
        updated_at: 最后更新时间
        estimated_remaining: 预估剩余时间（秒）
        metadata: 元数据
    """
    task_id: str
    progress: float = 0.0
    status: str = "pending"
    started_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.now)
    estimated_remaining: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_stale(self, threshold_seconds: float = 30.0) -> bool:
        """检查进度是否停滞"""
        if self.updated_at is None:
            return False
        elapsed = (datetime.now() - self.updated_at).total_seconds()
        return elapsed > threshold_seconds
    
    def elapsed_seconds(self) -> float:
        """获取已用时间"""
        if self.started_at is None:
            return 0.0
        return (datetime.now() - self.started_at).total_seconds()


@dataclass
class ProgressTrackerConfig:
    """进度追踪器配置"""
    stale_threshold_seconds: float = 30.0    # 停滞阈值
    update_interval_seconds: float = 5.0     # 更新间隔
    max_history_size: int = 100              # 最大历史记录数


class ProgressTracker:
    """
    进度追踪器
    
    职责：
    - 任务进度更新
    - 停滞任务检测
    - 进度聚合
    
    使用示例:
        tracker = ProgressTracker(ProgressTrackerConfig())
        
        # 开始追踪
        tracker.start_tracking("task_001")
        
        # 更新进度
        tracker.update("task_001", 0.5, "processing")
        
        # 检查停滞
        stale = tracker.get_stale_tasks()
        
        # 完成追踪
        tracker.complete("task_001")
    """
    
    def __init__(self, config: Optional[ProgressTrackerConfig] = None):
        self.config = config or ProgressTrackerConfig()
        
        # 进度存储
        self._progress: Dict[str, TaskProgress] = {}
        
        # 进度回调
        self._callbacks: Dict[str, List[Callable[[TaskProgress], None]]] = {}
        
        # 锁
        self._lock = asyncio.Lock()
        
        # 统计
        self._total_tracked = 0
        self._total_completed = 0
        self._total_stale_detected = 0
    
    def start_tracking(
        self,
        task_id: str,
        initial_progress: float = 0.0,
        status: str = "started",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskProgress:
        """
        开始追踪任务
        
        Args:
            task_id: 任务ID
            initial_progress: 初始进度
            status: 初始状态
            metadata: 元数据
            
        Returns:
            TaskProgress: 进度对象
        """
        progress = TaskProgress(
            task_id=task_id,
            progress=initial_progress,
            status=status,
            started_at=datetime.now(),
            updated_at=datetime.now(),
            metadata=metadata or {},
        )
        
        self._progress[task_id] = progress
        self._total_tracked += 1
        
        logger.debug(f"Started tracking task {task_id}")
        
        return progress
    
    def update(
        self,
        task_id: str,
        progress: float,
        status: Optional[str] = None,
        estimated_remaining: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[TaskProgress]:
        """
        更新任务进度
        
        Args:
            task_id: 任务ID
            progress: 进度值（0.0-1.0）
            status: 状态描述
            estimated_remaining: 预估剩余时间
            metadata: 元数据
            
        Returns:
            更新后的进度对象，不存在返回None
        """
        task_progress = self._progress.get(task_id)
        if task_progress is None:
            logger.warning(f"Task {task_id} not being tracked")
            return None
        
        # 更新进度
        task_progress.progress = max(0.0, min(1.0, progress))
        task_progress.updated_at = datetime.now()
        
        if status:
            task_progress.status = status
        
        if estimated_remaining is not None:
            task_progress.estimated_remaining = estimated_remaining
        
        if metadata:
            task_progress.metadata.update(metadata)
        
        # 触发回调
        self._trigger_callbacks(task_id, task_progress)
        
        logger.debug(f"Updated task {task_id}: {progress:.1%} - {status}")
        
        return task_progress
    
    def complete(
        self,
        task_id: str,
        status: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[TaskProgress]:
        """
        标记任务完成
        
        Args:
            task_id: 任务ID
            status: 最终状态
            metadata: 元数据
            
        Returns:
            最终进度对象
        """
        result = self.update(
            task_id=task_id,
            progress=1.0,
            status=status,
            estimated_remaining=0.0,
            metadata=metadata,
        )
        
        if result:
            self._total_completed += 1
            logger.debug(f"Task {task_id} completed")
        
        return result
    
    def fail(
        self,
        task_id: str,
        error: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[TaskProgress]:
        """
        标记任务失败
        
        Args:
            task_id: 任务ID
            error: 错误信息
            metadata: 元数据
            
        Returns:
            最终进度对象
        """
        metadata = metadata or {}
        metadata["error"] = error
        
        return self.update(
            task_id=task_id,
            progress=self._progress.get(task_id, TaskProgress(task_id=task_id)).progress,
            status="failed",
            metadata=metadata,
        )
    
    def get_progress(self, task_id: str) -> Optional[TaskProgress]:
        """获取任务进度"""
        return self._progress.get(task_id)
    
    def get_all_progress(self) -> Dict[str, TaskProgress]:
        """获取所有任务进度"""
        return dict(self._progress)
    
    def get_stale_tasks(self, threshold_seconds: Optional[float] = None) -> List[str]:
        """
        获取停滞的任务
        
        Args:
            threshold_seconds: 停滞阈值，None使用配置值
            
        Returns:
            停滞任务ID列表
        """
        threshold = threshold_seconds or self.config.stale_threshold_seconds
        stale = []
        
        for task_id, progress in self._progress.items():
            if progress.is_stale(threshold):
                stale.append(task_id)
                self._total_stale_detected += 1
        
        if stale:
            logger.warning(f"Detected {len(stale)} stale tasks")
        
        return stale
    
    def get_aggregate_progress(self) -> Dict[str, Any]:
        """
        获取聚合进度
        
        Returns:
            聚合进度信息
        """
        if not self._progress:
            return {
                "total": 0,
                "average": 0.0,
                "completed": 0,
                "in_progress": 0,
            }
        
        total = len(self._progress)
        completed = sum(1 for p in self._progress.values() if p.progress >= 1.0)
        in_progress = total - completed
        average = sum(p.progress for p in self._progress.values()) / total
        
        return {
            "total": total,
            "average": average,
            "completed": completed,
            "in_progress": in_progress,
        }
    
    def register_callback(
        self,
        task_id: str,
        callback: Callable[[TaskProgress], None]
    ) -> None:
        """
        注册进度回调
        
        Args:
            task_id: 任务ID
            callback: 回调函数
        """
        if task_id not in self._callbacks:
            self._callbacks[task_id] = []
        self._callbacks[task_id].append(callback)
    
    def unregister_callback(self, task_id: str) -> bool:
        """注销进度回调"""
        if task_id in self._callbacks:
            del self._callbacks[task_id]
            return True
        return False
    
    def _trigger_callbacks(self, task_id: str, progress: TaskProgress) -> None:
        """触发回调"""
        callbacks = self._callbacks.get(task_id, [])
        for callback in callbacks:
            try:
                callback(progress)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
    
    def stop_tracking(self, task_id: str) -> Optional[TaskProgress]:
        """停止追踪任务"""
        progress = self._progress.pop(task_id, None)
        if progress:
            self._callbacks.pop(task_id, None)
            logger.debug(f"Stopped tracking task {task_id}")
        return progress
    
    def clear(self) -> None:
        """清空所有追踪"""
        self._progress.clear()
        self._callbacks.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "active_tasks": len(self._progress),
            "total_tracked": self._total_tracked,
            "total_completed": self._total_completed,
            "total_stale_detected": self._total_stale_detected,
            "aggregate_progress": self.get_aggregate_progress(),
        }
