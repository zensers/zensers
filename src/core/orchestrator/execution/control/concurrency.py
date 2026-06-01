"""
并发管理器

参考: oh-my-openagent ConcurrencyManager

特性：
- 按模型/Provider限制并发
- FIFO队列
- 优先级支持
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ConcurrencyConfig:
    """并发配置"""
    max_concurrent: int = 5           # 每个key最大并发数
    default_timeout: float = 300.0    # 默认超时时间
    queue_max_size: int = 100         # 等待队列最大大小


@dataclass
class Waiter:
    """等待者"""
    priority: int
    event: asyncio.Event
    created_at: datetime = field(default_factory=datetime.now)


class ConcurrencyManager:
    """
    并发管理器
    
    参考: oh-my-openagent ConcurrencyManager
    
    特性：
    - 按模型/Provider限制并发
    - FIFO队列
    - 优先级支持
    
    使用示例:
        manager = ConcurrencyManager(ConcurrencyConfig(max_concurrent=5))
        
        # 获取槽位
        key = manager.get_key(agent)
        await manager.acquire(key)
        try:
            result = await agent.execute(task)
        finally:
            manager.release(key)
    """
    
    def __init__(self, config: ConcurrencyConfig):
        self.config = config
        
        # 每个key的活跃槽位数
        self._slots: Dict[str, int] = {}
        
        # 每个key的等待队列（优先级队列）
        self._wait_queues: Dict[str, list] = {}
        
        # 锁保护内部状态
        self._lock = asyncio.Lock()
        
        # 统计信息
        self._total_acquired = 0
        self._total_released = 0
        self._total_waited = 0
    
    async def acquire(self, key: str, priority: int = 0) -> None:
        """
        获取执行槽位
        
        Args:
            key: 并发key（如 "dynamic:anthropic/claude-opus-4"）
            priority: 优先级（数值越小优先级越高）
            
        如果当前槽位已满，会等待直到有槽位释放。
        优先级高的任务会先获得槽位。
        """
        waiter: Optional[Waiter] = None
        
        async with self._lock:
            current_slots = self._slots.get(key, 0)
            
            if current_slots < self.config.max_concurrent:
                # 有可用槽位，直接获取
                self._slots[key] = current_slots + 1
                self._total_acquired += 1
                logger.debug(f"Acquired slot for {key}, slots: {self._slots[key]}")
                return
            
            # 槽位已满，加入等待队列
            if key not in self._wait_queues:
                self._wait_queues[key] = []
            
            # 检查队列大小
            if len(self._wait_queues[key]) >= self.config.queue_max_size:
                raise RuntimeError(f"Wait queue full for key: {key}")
            
            # 创建等待者
            waiter = Waiter(
                priority=priority,
                event=asyncio.Event(),
            )
            self._wait_queues[key].append(waiter)
            self._total_waited += 1
            
            logger.debug(f"Queued for {key}, queue size: {len(self._wait_queues[key])}")
        
        # 等待被唤醒（在锁外等待，避免死锁）
        if waiter:
            await waiter.event.wait()
            
            # 被唤醒后，槽位已经在release中分配
            self._total_acquired += 1
            logger.debug(f"Acquired slot for {key} after waiting")
    
    async def release(self, key: str) -> None:
        """
        释放槽位
        
        Args:
            key: 并发key
            
        如果有等待者，会唤醒优先级最高的等待者。
        """
        async with self._lock:
            current_slots = self._slots.get(key, 0)
            
            if current_slots <= 0:
                logger.warning(f"Release called but no slots held for {key}")
                return
            
            # 减少槽位
            self._slots[key] = current_slots - 1
            self._total_released += 1
            
            # 检查是否有等待者
            wait_queue = self._wait_queues.get(key, [])
            if not wait_queue:
                logger.debug(f"Released slot for {key}, slots: {self._slots[key]}")
                return
            
            # 找到优先级最高的等待者（数值最小）
            wait_queue.sort(key=lambda w: w.priority)
            waiter = wait_queue.pop(0)
            
            # 分配槽位给等待者
            self._slots[key] = self._slots.get(key, 0) + 1
            
            # 唤醒等待者
            waiter.event.set()
            
            logger.debug(f"Released slot for {key}, woke up waiter, slots: {self._slots[key]}")
    
    def get_key(self, agent_type: str, model: Optional[str] = None) -> str:
        """
        生成并发key
        
        Args:
            agent_type: Agent类型（如 "dynamic", "fixed"）
            model: 模型标识（如 "anthropic/claude-opus-4"）
            
        Returns:
            并发key
        """
        if model:
            return f"{agent_type}:{model}"
        return agent_type
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "slots": dict(self._slots),
            "queue_sizes": {k: len(v) for k, v in self._wait_queues.items()},
            "total_acquired": self._total_acquired,
            "total_released": self._total_released,
            "total_waited": self._total_waited,
        }
    
    def get_available_slots(self, key: str) -> int:
        """获取指定key的可用槽位数"""
        current = self._slots.get(key, 0)
        return max(0, self.config.max_concurrent - current)
    
    def clear(self) -> None:
        """清空所有槽位和等待队列"""
        self._slots.clear()
        self._wait_queues.clear()
