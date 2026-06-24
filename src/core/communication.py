"""
Core Communication Module - MessageBus and SharedMemory
"""
import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


class DataEventType:
    """Data bus event type constants (B-FIX-2)"""
    CANONICAL_UPDATED = "data.canonical.updated"
    CONFLICT_DETECTED = "data.conflict.detected"
    SEARCH_COMPLETED = "data.search.completed"
    ANALYSIS_READY = "data.analysis.ready"


@dataclass
class Event:
    """Event data class"""
    type: str
    data: Any
    source: Optional[str] = None
    timestamp: Optional[float] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class MessageBus:
    """
    Async Message Bus - For inter-Agent event notification
    
    Features:
    - Multiple subscribers support
    - Topic isolation
    - Async processing
    """
    
    def __init__(self):
        # Topic -> handlers list mapping
        self._subscribers: Dict[str, List[Callable[[Event], Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def subscribe(self, topic: str, handler: Callable[[Event], Any]) -> None:
        """
        Subscribe to topic
        
        Args:
            topic: Topic name
            handler: Event handler
        """
        async with self._lock:
            self._subscribers[topic].append(handler)
    
    async def unsubscribe(self, topic: str, handler: Callable[[Event], Any]) -> bool:
        """
        Unsubscribe from topic
        
        Args:
            topic: Topic name
            handler: Event handler
            
        Returns:
            Whether successfully unsubscribed
        """
        async with self._lock:
            if topic in self._subscribers and handler in self._subscribers[topic]:
                self._subscribers[topic].remove(handler)
                return True
            return False
    
    async def publish(self, topic: str, event: Event) -> int:
        """
        Publish event to topic
        
        Args:
            topic: Topic name
            event: Event object
            
        Returns:
            Number of subscribers successfully notified
        """
        handlers = []
        async with self._lock:
            handlers = self._subscribers[topic].copy()
        
        # Async call all handlers
        tasks = []
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                from src.core.orchestrator.execution.task_utils import safe_create_task
                tasks.append(safe_create_task(handler(event), name="messagebus.publish_handler"))
            else:
                from src.core.orchestrator.execution.task_utils import safe_create_task
                loop = asyncio.get_running_loop()
                tasks.append(safe_create_task(
                    loop.run_in_executor(None, handler, event),
                    name="messagebus.publish_sync_handler",
                ))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        return len(handlers)
    
    def get_subscriber_count(self, topic: str) -> int:
        """Get subscriber count for topic"""
        return len(self._subscribers.get(topic, []))


SOURCE_PRIORITY = {
    "structured_source": 100,
    "search_result": 50,
    "llm_inference": 10,
}


class SharedMemory:
    """
    Shared Memory - For Agent state synchronization
    
    Features:
    - Async read/write
    - Thread-safe
    - Concurrent access support
    """
    
    def __init__(self, message_bus: Optional['MessageBus'] = None):
        self._data: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._version: Dict[str, int] = {}
        self._message_bus = message_bus
    
    async def read(self, key: str) -> Optional[Any]:
        """
        Read data
        
        Args:
            key: Data key
            
        Returns:
            Data value, None if not exists
        """
        async with self._lock:
            return self._data.get(key)
    
    async def write(self, key: str, value: Any) -> None:
        """
        Write data
        
        Args:
            key: Data key
            value: Data value
        """
        async with self._lock:
            self._data[key] = value
    
    async def delete(self, key: str) -> bool:
        """
        Delete data
        
        Args:
            key: Data key
            
        Returns:
            Whether successfully deleted
        """
        async with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        async with self._lock:
            return key in self._data
    
    async def keys(self) -> List[str]:
        """Get all keys"""
        async with self._lock:
            return list(self._data.keys())
    
    async def clear(self) -> None:
        """Clear all data"""
        async with self._lock:
            self._data.clear()
    
    # ==================== Canonical Data Methods (B-FIX-1) ====================
    
    async def write_canonical(
        self,
        metric: str,
        value: Any,
        caliber: str = "",
        source: str = "",
        publisher: str = "",
    ) -> Optional[Any]:
        """
        Write canonical data with conflict detection, versioning, and source priority.
        
        Source priority (ISSUE-G): structured_source > search_result > llm_inference.
        Lower-priority sources do not overwrite higher-priority values.
        
        Returns ConflictRecord if conflict detected, None otherwise.
        """
        from src.core.orchestrator.aggregation.result_aggregator import ConflictRecord, ConflictResolution
        key = f"canonical:{metric}"
        async with self._lock:
            existing = self._data.get(key)
            conflict = None
            if existing and isinstance(value, (int, float)) and isinstance(existing["value"], (int, float)):
                if abs(existing["value"] - value) / max(abs(value), 0.01) > 0.05:
                    conflict = ConflictRecord(
                        key=metric,
                        values=[existing["value"], value],
                        sources=[existing.get("source", ""), source],
                        resolution=ConflictResolution.MANUAL,
                        resolved_value=None,
                    )
            if existing:
                existing_priority = SOURCE_PRIORITY.get(existing.get("caliber", ""), 0)
                new_priority = SOURCE_PRIORITY.get(caliber, 0)
                if new_priority <= existing_priority and new_priority != existing_priority:
                    if conflict:
                        logger.info(f"SharedMemory: canonical '{metric}' conflict - keeping higher-priority source "
                                    f"({existing.get('caliber', '?')}={existing['value']} vs {caliber}={value})")
                        conflict = None
                    return conflict
            self._data[key] = {
                "value": value, "caliber": caliber, "source": source,
                "publisher": publisher,
                "version": self._version.get(key, 0) + 1,
                "timestamp": time.time(),
            }
            self._version[key] = self._version.get(key, 0) + 1
        
        if self._message_bus:
            from src.core.communication import Event
            event_type = "data.canonical.updated" if not conflict else "data.conflict.detected"
            await self._message_bus.publish(
                event_type,
                Event(type=event_type, data={
                    "metric": metric, "value": value, "conflict": conflict is not None,
                    "caliber": caliber, "source": source, "publisher": publisher,
                })
            )
        return conflict
    
    async def get_canonical(self, metric: str) -> Optional[Dict]:
        """Read canonical data entry"""
        async with self._lock:
            return self._data.get(f"canonical:{metric}")
    
    def get_canonical_sync(self, metric: str) -> Optional[Dict]:
        """Synchronous read for prompt building context"""
        entry = self._data.get(f"canonical:{metric}")
        if entry:
            return entry
        prefix = metric.split("_")[0]
        for key, value in self._data.items():
            if key.startswith("canonical:"):
                key_metric = key[len("canonical:"):]
                if key_metric == metric or key_metric.split("_")[0] == prefix:
                    return value
        return None
    
    def get_all_canonical(self) -> Dict[str, Dict]:
        """Get all canonical data entries"""
        result = {}
        for key, value in self._data.items():
            if key.startswith("canonical:"):
                metric_name = key[len("canonical:"):]
                result[metric_name] = value
        return result
    
    # ==================== Synchronous Access Methods (for non-async contexts) ====================
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Synchronously read data (non-thread-safe, for performance-critical paths)
        
        Note: This method does not use locks, suitable for:
        - When sync access is needed in async context
        - Performance-critical scenarios where strict thread safety is not required
        
        Args:
            key: Data key
            default: Default value
            
        Returns:
            Data value, returns default if not exists
        """
        return self._data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        Synchronously write data (non-thread-safe, for performance-critical paths)
        
        Note: This method does not use locks, suitable for:
        - When sync access is needed in async context
        - Performance-critical scenarios where strict thread safety is not required
        
        Args:
            key: Data key
            value: Data value
        """
        self._data[key] = value
    
    def get_all(self) -> Dict[str, Any]:
        """
        Synchronously get all data snapshot
        
        Returns:
            Copy of data dictionary
        """
        return dict(self._data)
    
    def set_all(self, data: Dict[str, Any]) -> None:
        """
        Synchronously batch set data
        
        Args:
            data: Data dictionary
        """
        self._data = dict(data)
