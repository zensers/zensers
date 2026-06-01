"""
心跳监控

参考: oh-my-openagent polling + stability detection

职责：
- 监控任务活跃状态
- 检测无响应任务
- 支持心跳超时处理
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union, Awaitable

logger = logging.getLogger(__name__)


class HeartbeatStatus(Enum):
    """心跳状态"""
    ALIVE = "alive"
    STALE = "stale"
    DEAD = "dead"
    UNKNOWN = "unknown"


@dataclass
class HeartbeatConfig:
    """心跳配置"""
    interval_seconds: float = 5.0          # 心跳间隔
    timeout_seconds: float = 30.0          # 超时时间
    max_missed_heartbeats: int = 3         # 最大丢失心跳数
    check_interval_seconds: float = 10.0   # 检查间隔


@dataclass
class HeartbeatRecord:
    """
    心跳记录
    
    Attributes:
        task_id: 任务ID
        last_heartbeat: 最后心跳时间
        heartbeat_count: 心跳计数
        missed_count: 丢失计数
        status: 心跳状态
        started_at: 开始监控时间
    """
    task_id: str
    last_heartbeat: datetime = field(default_factory=datetime.now)
    heartbeat_count: int = 0
    missed_count: int = 0
    status: HeartbeatStatus = HeartbeatStatus.ALIVE
    started_at: datetime = field(default_factory=datetime.now)
    
    def seconds_since_last(self) -> float:
        """距离上次心跳的秒数"""
        return (datetime.now() - self.last_heartbeat).total_seconds()


class HeartbeatMonitor:
    """
    心跳监控
    
    参考: oh-my-openagent polling + stability detection
    
    职责：
    - 监控任务活跃状态
    - 检测无响应任务
    - 支持心跳超时处理
    
    使用示例:
        monitor = HeartbeatMonitor(HeartbeatConfig())
        await monitor.start()
        
        # 开始监控任务
        monitor.start_tracking("task_001")
        
        # 接收心跳
        monitor.receive_heartbeat("task_001")
        
        # 检查状态
        status = monitor.get_status("task_001")
        
        # 停止
        await monitor.stop()
    """
    
    def __init__(self, config: Optional[HeartbeatConfig] = None):
        self.config = config or HeartbeatConfig()
        
        # 心跳记录
        self._records: Dict[str, HeartbeatRecord] = {}
        
        # 超时回调（支持同步和异步）
        self._timeout_callbacks: Dict[str, Union[Callable[[str], None], Callable[[str], Awaitable[None]]]] = {}
        
        # 监控任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        
        # 锁
        self._lock = asyncio.Lock()
        
        # 统计
        self._total_tracked = 0
        self._total_timeouts = 0
        self._total_heartbeats = 0
    
    async def start(self) -> None:
        """启动监控"""
        if self._running:
            logger.warning("HeartbeatMonitor already running")
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("HeartbeatMonitor started")
    
    async def stop(self) -> None:
        """停止监控"""
        self._running = False
        
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        
        logger.info("HeartbeatMonitor stopped")
    
    async def _monitor_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                await self._check_heartbeats()
                await asyncio.sleep(self.config.check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(1.0)
    
    async def _check_heartbeats(self) -> None:
        """检查所有心跳"""
        timeout_threshold = self.config.timeout_seconds
        max_missed = self.config.max_missed_heartbeats
        
        for task_id, record in list(self._records.items()):
            seconds_since = record.seconds_since_last()
            
            # 检查是否超时
            if seconds_since > timeout_threshold:
                record.missed_count += 1
                record.status = HeartbeatStatus.STALE
                
                logger.warning(
                    f"Task {task_id} heartbeat stale: "
                    f"{seconds_since:.1f}s since last, missed={record.missed_count}"
                )
                
                # 检查是否达到最大丢失数
                if record.missed_count >= max_missed:
                    record.status = HeartbeatStatus.DEAD
                    self._total_timeouts += 1
                    
                    logger.error(f"Task {task_id} declared dead after {record.missed_count} missed heartbeats")
                    
                    # 触发超时回调（支持异步回调）
                    callback = self._timeout_callbacks.get(task_id)
                    if callback:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(task_id)
                            else:
                                callback(task_id)
                        except Exception as e:
                            logger.error(f"Heartbeat timeout callback failed: {e}")
    
    def start_tracking(
        self,
        task_id: str,
        timeout_callback: Optional[Union[Callable[[str], None], Callable[[str], Awaitable[None]]]] = None,
    ) -> HeartbeatRecord:
        """
        开始追踪任务
        
        Args:
            task_id: 任务ID
            timeout_callback: 超时回调
            
        Returns:
            HeartbeatRecord: 心跳记录
        """
        record = HeartbeatRecord(
            task_id=task_id,
            last_heartbeat=datetime.now(),
            heartbeat_count=0,
            missed_count=0,
            status=HeartbeatStatus.ALIVE,
        )
        
        self._records[task_id] = record
        self._total_tracked += 1
        
        if timeout_callback:
            self._timeout_callbacks[task_id] = timeout_callback
        
        logger.debug(f"Started heartbeat tracking for task {task_id}")
        
        return record
    
    def receive_heartbeat(self, task_id: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        接收心跳
        
        Args:
            task_id: 任务ID
            metadata: 心跳元数据（可选）
            
        Returns:
            是否成功接收
        """
        record = self._records.get(task_id)
        if record is None:
            logger.warning(f"Received heartbeat for untracked task {task_id}")
            return False
        
        # 更新记录
        record.last_heartbeat = datetime.now()
        record.heartbeat_count += 1
        record.missed_count = 0
        record.status = HeartbeatStatus.ALIVE
        
        self._total_heartbeats += 1
        
        logger.debug(f"Received heartbeat from task {task_id} (count={record.heartbeat_count})")
        
        return True
    
    def stop_tracking(self, task_id: str) -> Optional[HeartbeatRecord]:
        """
        停止追踪任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            心跳记录，不存在返回None
        """
        record = self._records.pop(task_id, None)
        
        if record:
            self._timeout_callbacks.pop(task_id, None)
            logger.debug(f"Stopped heartbeat tracking for task {task_id}")
        
        return record
    
    def get_status(self, task_id: str) -> HeartbeatStatus:
        """
        获取任务心跳状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            心跳状态
        """
        record = self._records.get(task_id)
        return record.status if record else HeartbeatStatus.UNKNOWN
    
    def get_record(self, task_id: str) -> Optional[HeartbeatRecord]:
        """获取心跳记录"""
        return self._records.get(task_id)
    
    def get_stale_tasks(self) -> List[str]:
        """获取所有停滞的任务"""
        return [
            task_id for task_id, record in self._records.items()
            if record.status == HeartbeatStatus.STALE
        ]
    
    def get_dead_tasks(self) -> List[str]:
        """获取所有死亡的任务"""
        return [
            task_id for task_id, record in self._records.items()
            if record.status == HeartbeatStatus.DEAD
        ]
    
    def get_alive_tasks(self) -> List[str]:
        """获取所有活跃的任务"""
        return [
            task_id for task_id, record in self._records.items()
            if record.status == HeartbeatStatus.ALIVE
        ]
    
    def is_alive(self, task_id: str) -> bool:
        """检查任务是否活跃"""
        return self.get_status(task_id) == HeartbeatStatus.ALIVE
    
    def get_all_records(self) -> Dict[str, HeartbeatRecord]:
        """获取所有心跳记录"""
        return dict(self._records)
    
    def clear(self) -> None:
        """清空所有追踪"""
        self._records.clear()
        self._timeout_callbacks.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "tracked_tasks": len(self._records),
            "alive": len(self.get_alive_tasks()),
            "stale": len(self.get_stale_tasks()),
            "dead": len(self.get_dead_tasks()),
            "total_tracked": self._total_tracked,
            "total_timeouts": self._total_timeouts,
            "total_heartbeats": self._total_heartbeats,
        }
