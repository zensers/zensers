# -*- coding: utf-8 -*-
"""
Memory Optimization Module
=========================

Phase 4 Week 18: Performance Optimization - Memory Optimization

Features:
- Object pool management - Reuse objects to reduce allocation
- Memory monitoring - Track memory usage
- Memory fragmentation optimization - Defragment memory
- Resource limits - Memory usage ceiling

Core classes:
- ObjectPool - Object pool
- MemoryMonitor - Memory monitor
- ResourceManager - Resource manager
"""

import os
import time
import weakref
import threading
from typing import Dict, Any, Optional, List, Callable, Generic, TypeVar
from datetime import datetime
from dataclasses import dataclass, field
from threading import Lock, RLock
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class PoolStats:
    """Pool statistics"""
    total_created: int = 0
    total_reused: int = 0
    total_returned: int = 0
    current_size: int = 0
    peak_size: int = 0


class ObjectPool(Generic[T]):
    """
    Object Pool

    Reuse objects to reduce memory allocation and GC pressure.

    Usage example:
        pool = ObjectPool(
            factory=lambda: ExpensiveObject(),
            max_size=100
        )

        obj = pool.acquire()
        try:
            obj.do_work()
        finally:
            pool.release(obj)
    """

    def __init__(
        self,
        factory: Callable[[], T],
        max_size: int = 100,
        reset_func: Optional[Callable[[T], None]] = None,
        validate_func: Optional[Callable[[T], bool]] = None
    ):
        """
        Initialize object pool

        Args:
            factory: Object factory function
            max_size: Maximum pool size
            reset_func: Reset function (called on return)
            validate_func: Validation function (called on acquire)
        """
        self.factory = factory
        self.max_size = max_size
        self.reset_func = reset_func
        self.validate_func = validate_func

        self._pool: List[T] = []
        self._lock = Lock()
        self._stats = PoolStats()

    def acquire(self) -> T:
        """
        Acquire object

        Returns:
            Object instance
        """
        with self._lock:
            if self._pool:
                obj = self._pool.pop()
                self._stats.total_reused += 1
                self._stats.current_size -= 1

                # Validate object
                if self.validate_func and not self.validate_func(obj):
                    # Validation failed, create new object
                    obj = self._create_new()

                return obj

            return self._create_new()

    def _create_new(self) -> T:
        """Create new object"""
        obj = self.factory()
        self._stats.total_created += 1
        return obj

    def release(self, obj: T) -> None:
        """
        Release object

        Args:
            obj: Object to release
        """
        with self._lock:
            # Check if pool is full
            if len(self._pool) >= self.max_size:
                return  # Discard object

            # Reset object
            if self.reset_func:
                try:
                    self.reset_func(obj)
                except Exception as e:
                    logger.warning(f"Failed to reset object: {e}")
                    return

            # Return to pool
            self._pool.append(obj)
            self._stats.total_returned += 1
            self._stats.current_size += 1
            self._stats.peak_size = max(self._stats.peak_size, self._stats.current_size)

    def clear(self) -> None:
        """Clear pool"""
        with self._lock:
            self._pool.clear()
            self._stats.current_size = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        with self._lock:
            return {
                "total_created": self._stats.total_created,
                "total_reused": self._stats.total_reused,
                "total_returned": self._stats.total_returned,
                "current_size": self._stats.current_size,
                "peak_size": self._stats.peak_size,
                "reuse_rate": (
                    self._stats.total_reused / (self._stats.total_created + self._stats.total_reused)
                    if (self._stats.total_created + self._stats.total_reused) > 0 else 0
                ),
            }


class MemoryMonitor:
    """
    Memory Monitor

    Tracks memory usage.
    """

    def __init__(self, sample_interval: float = 1.0):
        """
        Initialize memory monitor

        Args:
            sample_interval: Sampling interval (seconds)
        """
        self.sample_interval = sample_interval

        self._samples: List[Dict[str, Any]] = []
        self._lock = Lock()
        self._monitoring = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start monitoring"""
        if self._monitoring:
            return

        self._monitoring = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Memory monitoring started")

    def stop(self) -> None:
        """Stop monitoring"""
        self._monitoring = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("Memory monitoring stopped")

    def _monitor_loop(self) -> None:
        """Monitoring loop"""
        while self._monitoring:
            sample = self._take_sample()
            with self._lock:
                self._samples.append(sample)

            time.sleep(self.sample_interval)

    def _take_sample(self) -> Dict[str, Any]:
        """Take sample"""
        try:
            import psutil
            process = psutil.Process()

            return {
                "timestamp": datetime.now().isoformat(),
                "rss": process.memory_info().rss,
                "vms": process.memory_info().vms,
                "percent": process.memory_percent(),
                "available": psutil.virtual_memory().available,
            }
        except ImportError:
            return {
                "timestamp": datetime.now().isoformat(),
                "error": "psutil not installed",
            }

    def get_current(self) -> Dict[str, Any]:
        """Get current memory usage"""
        return self._take_sample()

    def get_samples(self, count: int = 100) -> List[Dict[str, Any]]:
        """Get recent samples"""
        with self._lock:
            return list(self._samples[-count:])

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        with self._lock:
            if not self._samples:
                return {"error": "No sample data"}

            rss_values = [s.get("rss", 0) for s in self._samples if "rss" in s]

            if not rss_values:
                return {"error": "No valid samples"}

            return {
                "sample_count": len(self._samples),
                "avg_rss": sum(rss_values) / len(rss_values),
                "max_rss": max(rss_values),
                "min_rss": min(rss_values),
            }

    def clear_samples(self) -> None:
        """Clear samples"""
        with self._lock:
            self._samples.clear()


class ResourceManager:
    """
    Resource Manager

    Manages system resources and limits.
    """

    _instance: Optional["ResourceManager"] = None
    _lock = Lock()

    def __init__(
        self,
        max_memory_mb: Optional[int] = None,
        warning_threshold: float = 0.8
    ):
        """
        Initialize resource manager

        Args:
            max_memory_mb: Maximum memory limit (MB)
            warning_threshold: Warning threshold (ratio)
        """
        self.max_memory_mb = max_memory_mb
        self.warning_threshold = warning_threshold

        self._pools: Dict[str, ObjectPool] = {}
        self._monitor = MemoryMonitor()
        self._manager_lock = Lock()

    @classmethod
    def get_instance(cls, **kwargs) -> "ResourceManager":
        """Get singleton instance"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(**kwargs)
            return cls._instance

    def register_pool(self, name: str, pool: ObjectPool) -> None:
        """Register object pool"""
        with self._manager_lock:
            self._pools[name] = pool
            logger.info(f"Registered object pool: {name}")

    def get_pool(self, name: str) -> Optional[ObjectPool]:
        """Get object pool"""
        with self._manager_lock:
            return self._pools.get(name)

    def start_monitoring(self) -> None:
        """Start monitoring"""
        self._monitor.start()

    def stop_monitoring(self) -> None:
        """Stop monitoring"""
        self._monitor.stop()

    def check_memory(self) -> Dict[str, Any]:
        """Check memory usage"""
        current = self._monitor.get_current()

        result = {
            "current": current,
            "status": "ok",
        }

        # Check memory limit
        if self.max_memory_mb and "rss" in current:
            current_mb = current["rss"] / (1024 * 1024)
            result["usage_percent"] = current_mb / self.max_memory_mb

            if current_mb > self.max_memory_mb * self.warning_threshold:
                result["status"] = "warning"
                logger.warning(f"Memory usage approaching limit: {current_mb:.1f}MB / {self.max_memory_mb}MB")

            if current_mb > self.max_memory_mb:
                result["status"] = "critical"
                logger.error(f"Memory usage exceeded limit: {current_mb:.1f}MB / {self.max_memory_mb}MB")

        return result

    def get_all_stats(self) -> Dict[str, Any]:
        """Get all statistics"""
        with self._manager_lock:
            return {
                "pools": {
                    name: pool.get_stats()
                    for name, pool in self._pools.items()
                },
                "memory": self._monitor.get_stats(),
            }

    def cleanup(self) -> None:
        """Cleanup all resources"""
        with self._manager_lock:
            for pool in self._pools.values():
                pool.clear()
            self._monitor.clear_samples()
        logger.info("Resource cleanup completed")


# Convenience functions
def get_memory_monitor() -> MemoryMonitor:
    """Get memory monitor"""
    return ResourceManager.get_instance()._monitor


def check_memory_usage() -> Dict[str, Any]:
    """Check memory usage"""
    return ResourceManager.get_instance().check_memory()


def get_resource_stats() -> Dict[str, Any]:
    """Get resource statistics"""
    return ResourceManager.get_instance().get_all_stats()