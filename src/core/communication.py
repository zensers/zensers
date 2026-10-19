"""
Core Communication Module - MessageBus and SharedMemory
"""
import asyncio
from contextvars import ContextVar
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


# Each orchestrator execution inherits its own scope into child Agent tasks.
# This prevents canonical metrics from concurrent research sessions sharing
# the same storage key while leaving ordinary shared configuration keys global.
_MEMORY_SCOPE: ContextVar[Optional[str]] = ContextVar("shared_memory_scope", default=None)


def set_memory_scope(scope: Optional[str]):
    """Bind canonical-memory operations in the current async task context."""
    return _MEMORY_SCOPE.set(scope or None)


def reset_memory_scope(token) -> None:
    """Restore the memory scope that was active before an execution."""
    if token is not None:
        _MEMORY_SCOPE.reset(token)


def get_memory_scope() -> Optional[str]:
    """Return the current task-local canonical-memory scope."""
    return _MEMORY_SCOPE.get()


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
    "llm_inference_factual": 15,
    "llm_inference": 10,
    "llm_inference_speculative": 5,
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

    @staticmethod
    def _is_scoped_key(key: str) -> bool:
        return key.startswith("canonical:") or key == "_canonical_registry"

    @staticmethod
    def _storage_key(key: str) -> str:
        scope = get_memory_scope()
        if scope and SharedMemory._is_scoped_key(key):
            return f"scope:{scope}:{key}"
        return key
    
    async def read(self, key: str) -> Optional[Any]:
        """
        Read data
        
        Args:
            key: Data key
            
        Returns:
            Data value, None if not exists
        """
        async with self._lock:
            return self._data.get(self._storage_key(key))
    
    async def write(self, key: str, value: Any) -> None:
        if key.startswith("canonical:") or key.startswith("_canonical"):
            logger.warning(
                f"SharedMemory.write(): writing canonical-key '{key}' via non-quality-controlled path. "
                f"Use write_canonical() instead."
            )
        async with self._lock:
            self._data[self._storage_key(key)] = value
    
    async def delete(self, key: str) -> bool:
        """
        Delete data
        
        Args:
            key: Data key
            
        Returns:
            Whether successfully deleted
        """
        async with self._lock:
            storage_key = self._storage_key(key)
            if storage_key in self._data:
                del self._data[storage_key]
                return True
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        async with self._lock:
            return self._storage_key(key) in self._data
    
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
        # TODO: L2 strategy integration — accept same_caliber_resolution and speculative_write_policy
        # from COGNITIVE_STRATEGY. Currently uses default behavior for all types.
        # See docs/superpowers/specs/2026-07-01-aspect-cognitive-strategy-design.md Section 4.3
        source: str = "",
        publisher: str = "",
    ) -> Optional[Any]:
        """
        Write canonical data with conflict detection, versioning, and source priority.
        
        Source priority (ISSUE-G): structured_source > search_result > llm_inference.
        Lower-priority sources do not overwrite higher-priority values.
        
        Returns ConflictRecord if conflict detected, None otherwise.
        """
        if caliber and caliber not in SOURCE_PRIORITY:
            logger.warning(
                f"SharedMemory.write_canonical(): source_type '{caliber}' not in SOURCE_PRIORITY, "
                f"will be treated as priority=0"
            )
        from src.core.orchestrator.aggregation.result_aggregator import ConflictRecord, ConflictResolution
        key = self._storage_key(f"canonical:{metric}")
        should_write = True
        async with self._lock:
            existing = self._data.get(key)
            conflict = None
            if existing and isinstance(existing, dict) and "value" in existing:
                if isinstance(value, (int, float)) and isinstance(existing["value"], (int, float)):
                    if abs(existing["value"] - value) / max(abs(value), 0.01) > 0.05:
                        conflict = ConflictRecord(
                            key=metric,
                            values=[existing["value"], value],
                            sources=[existing.get("source", ""), source],
                            resolution=ConflictResolution.MANUAL,
                            resolved_value=None,
                        )
                elif isinstance(value, str) and isinstance(existing["value"], str):
                    if value != existing["value"] and len(value) > 2 and len(existing["value"]) > 2:
                        conflict = ConflictRecord(
                            key=metric,
                            values=[existing["value"], value],
                            sources=[existing.get("source", ""), source],
                            resolution=ConflictResolution.MANUAL,
                            resolved_value=None,
                        )
                elif isinstance(value, dict) and isinstance(existing["value"], dict):
                    _old_stmt = existing["value"].get("statement", "")
                    _new_stmt = value.get("statement", "")
                    if _old_stmt and _new_stmt and _old_stmt != _new_stmt:
                        conflict = ConflictRecord(
                            key=metric,
                            values=[existing["value"], value],
                            sources=[existing.get("source", ""), source],
                            resolution=ConflictResolution.MANUAL,
                            resolved_value=None,
                        )
            if existing and isinstance(existing, dict) and "value" in existing:
                existing_priority = SOURCE_PRIORITY.get(existing.get("caliber", ""), 0) if isinstance(existing, dict) else 0
                new_priority = SOURCE_PRIORITY.get(caliber, 0)
                if new_priority <= existing_priority:
                    if new_priority != existing_priority:
                        # Keep the higher-priority value, but do not discard
                        # the conflict.  It must be published after the lock
                        # so DataCollector/L5 can audit the rejected claim.
                        should_write = False
                        logger.info(f"SharedMemory: canonical '{metric}' conflict - keeping higher-priority source "
                                    f"({existing.get('caliber', '?')}={existing.get('value')} vs {caliber}={value})")
                    else:
                        if source == existing.get("source", ""):
                            # Same publisher/source is an intentional update.
                            conflict = None
                        elif caliber == existing.get("caliber", ""):
                            logger.info(
                                f"SharedMemory: canonical '{metric}' same-caliber write blocked "
                                f"({caliber}, keeping existing from {existing.get('source','')})"
                            )
                            if not conflict:
                                conflict = ConflictRecord(
                                    key=metric,
                                    values=[existing["value"], value],
                                    sources=[existing.get("source", ""), source],
                                    resolution=ConflictResolution.MANUAL,
                                    resolved_value=None,
                                )
                            should_write = False
                        else:
                            if not conflict:
                                conflict = ConflictRecord(
                                    key=metric,
                                    values=[existing["value"], value],
                                    sources=[existing.get("source", ""), source],
                                    resolution=ConflictResolution.MANUAL,
                                    resolved_value=None,
                                )
                            should_write = False
            if should_write:
                self._data[key] = {
                    "value": value, "caliber": caliber, "source": source,
                    "publisher": publisher,
                    "version": self._version.get(key, 0) + 1,
                    "timestamp": time.time(),
                }
                self._version[key] = self._version.get(key, 0) + 1
        
        if self._message_bus:
            from src.core.communication import Event
            # A rejected same-value lower-priority write is neither an update
            # nor a conflict.  Do not emit a false canonical.updated event.
            event_type = "data.conflict.detected" if conflict else (
                "data.canonical.updated" if should_write else None
            )
            if event_type:
                await self._message_bus.publish(
                    event_type,
                    Event(type=event_type, data={
                        "metric": metric, "value": value, "conflict": conflict is not None,
                        "caliber": caliber, "source": source, "publisher": publisher,
                        "scope": get_memory_scope(),
                    })
                )
        return conflict
    
    async def get_canonical(self, metric: str) -> Optional[Dict]:
        """Read canonical data entry"""
        async with self._lock:
            return self._data.get(self._storage_key(f"canonical:{metric}"))
    
    def get_canonical_sync(self, metric: str) -> Optional[Dict]:
        """Synchronous read for prompt building context"""
        entry = self._data.get(self._storage_key(f"canonical:{metric}"))
        if entry:
            return entry
        return None
    
    def get_all_canonical(self) -> Dict[str, Dict]:
        """Get all canonical data entries"""
        result = {}
        scope_prefix = self._storage_key("canonical:")
        scoped = get_memory_scope()
        for key, value in self._data.items():
            if scoped:
                if not key.startswith(scope_prefix):
                    continue
                metric_name = key[len(scope_prefix):]
            elif key.startswith("canonical:"):
                metric_name = key[len("canonical:"):]
            else:
                continue
            if metric_name:
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
        return self._data.get(self._storage_key(key), default)
    
    def set(self, key: str, value: Any) -> None:
        if key.startswith("canonical:") or key.startswith("_canonical"):
            logger.warning(
                f"SharedMemory.set(): writing canonical-key '{key}' via non-quality-controlled path. "
                f"Use write_canonical() instead."
            )
        self._data[self._storage_key(key)] = value
    
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


def resolve_shared_memory(explicit: Optional[SharedMemory] = None) -> SharedMemory:
    """Resolve the process communication memory through the DI container.

    Production entry points configure one SharedMemory singleton in the
    container.  Components created outside that bootstrap path retain the
    previous behavior and receive a private instance, which is important for
    isolated tests and explicitly scoped integrations.
    """
    if explicit is not None:
        return explicit
    try:
        from src.core.container import get_container
        container = get_container()
        if container.has(SharedMemory):
            return container.resolve(SharedMemory)
    except Exception as exc:
        logger.debug("SharedMemory DI resolution unavailable: %s", exc)
    return SharedMemory()
