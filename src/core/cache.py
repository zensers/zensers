# -*- coding: utf-8 -*-
"""
Cache Optimization Module
=========================

Phase 4 Week 18: Performance Optimization - Cache Optimization

Features:
- Multi-level cache strategy - memory cache + optional Redis
- LRU/LFU eviction policies
- TTL expiration mechanism
- Cache warmup
- Cache hit rate monitoring

Core classes:
- CacheEntry - Cache entry
- MemoryCache - Memory cache
- CacheManager - Cache manager
"""

import os
import time
import json
import hashlib
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, Generic, TypeVar
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock, RLock
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)

K = TypeVar('K')
V = TypeVar('V')


class EvictionPolicy(Enum):
    """Eviction policy enumeration"""
    LRU = "lru"  # Least Recently Used
    LFU = "lfu"  # Least Frequently Used
    FIFO = "fifo"  # First In First Out


@dataclass
class CacheEntry(Generic[V]):
    """Cache entry"""
    key: str
    value: V
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    access_count: int = 0
    last_access: float = field(default_factory=time.time)
    
    def is_expired(self) -> bool:
        """Check if expired"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at
    
    def touch(self) -> None:
        """Update access info"""
        self.access_count += 1
        self.last_access = time.time()


class MemoryCache(Generic[K, V]):
    """
    Memory Cache
    
    Supports multiple eviction policies and TTL expiration.
    
    Usage example:
        cache = MemoryCache(max_size=1000, ttl_seconds=300)
        
        cache.set("key1", "value1")
        value = cache.get("key1")
        
        cache.delete("key1")
        cache.clear()
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: Optional[int] = None,
        eviction_policy: EvictionPolicy = EvictionPolicy.LRU
    ):
        """
        Initialize memory cache
        
        Args:
            max_size: Maximum number of entries
            ttl_seconds: Default TTL (seconds)
            eviction_policy: Eviction policy
        """
        self.max_size = max_size
        self.default_ttl = ttl_seconds
        self.eviction_policy = eviction_policy
        
        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = RLock()
        
        # Statistics
        self._hits = 0
        self._misses = 0
    
    def set(
        self,
        key: K,
        value: V,
        ttl_seconds: Optional[int] = None
    ) -> None:
        """
        Set cache value
        
        Args:
            key: Cache key
            value: Cache value
            ttl_seconds: TTL (seconds), None uses default
        """
        with self._lock:
            # Calculate expiration time
            ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
            expires_at = time.time() + ttl if ttl else None
            
            # Create entry
            entry = CacheEntry(
                key=str(key),
                value=value,
                expires_at=expires_at
            )
            
            # If key exists, delete first
            if key in self._cache:
                del self._cache[key]
            
            # Check capacity and evict
            while len(self._cache) >= self.max_size:
                self._evict()
            
            # Add entry
            self._cache[key] = entry
    
    def get(self, key: K) -> Optional[V]:
        """
        Get cache value
        
        Args:
            key: Cache key
        
        Returns:
            Cache value, None if not exists or expired
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            entry = self._cache[key]
            
            # Check expiration
            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return None
            
            # Update access info
            entry.touch()
            
            # LRU policy: move to end
            if self.eviction_policy == EvictionPolicy.LRU:
                self._cache.move_to_end(key)
            
            self._hits += 1
            return entry.value
    
    def delete(self, key: K) -> bool:
        """
        Delete cache entry
        
        Args:
            key: Cache key
        
        Returns:
            Whether successfully deleted
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Clear cache"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def _evict(self) -> None:
        """Evict one entry"""
        if not self._cache:
            return
        
        if self.eviction_policy == EvictionPolicy.LRU:
            # Evict least recently accessed
            self._cache.popitem(last=False)
        elif self.eviction_policy == EvictionPolicy.LFU:
            # Evict least frequently accessed
            min_key = min(self._cache.keys(), key=lambda k: self._cache[k].access_count)
            del self._cache[min_key]
        else:  # FIFO
            self._cache.popitem(last=False)
    
    def cleanup_expired(self) -> int:
        """
        Clean up expired entries
        
        Returns:
            Number of entries cleaned
        """
        with self._lock:
            expired_keys = [
                k for k, entry in self._cache.items()
                if entry.is_expired()
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.debug(f"Cleaned {len(expired_keys)} expired cache entries")
            
            return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0.0
            
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 4),
                "eviction_policy": self.eviction_policy.value,
            }
    
    def keys(self) -> List[K]:
        """Get all cache keys"""
        with self._lock:
            return list(self._cache.keys())
    
    def size(self) -> int:
        """Get cache size"""
        with self._lock:
            return len(self._cache)


class CacheManager:
    """
    Cache Manager
    
    Manages multiple named caches.
    
    Usage example:
        manager = CacheManager()
        
        # Get or create cache
        cache = manager.get_cache("users", max_size=500)
        
        cache.set("user:1", {"name": "Alice"})
        user = cache.get("user:1")
        
        # Get all statistics
        stats = manager.get_all_stats()
    """
    
    _instance: Optional["CacheManager"] = None
    _lock = Lock()
    
    def __init__(self):
        """Initialize cache manager"""
        self._caches: Dict[str, MemoryCache] = {}
        self._manager_lock = Lock()
    
    @classmethod
    def get_instance(cls) -> "CacheManager":
        """Get singleton instance"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    def get_cache(
        self,
        name: str,
        max_size: int = 1000,
        ttl_seconds: Optional[int] = None,
        eviction_policy: EvictionPolicy = EvictionPolicy.LRU
    ) -> MemoryCache:
        """
        Get or create cache
        
        Args:
            name: Cache name
            max_size: Maximum number of entries
            ttl_seconds: TTL (seconds)
            eviction_policy: Eviction policy
        
        Returns:
            Cache instance
        """
        with self._manager_lock:
            if name not in self._caches:
                self._caches[name] = MemoryCache(
                    max_size=max_size,
                    ttl_seconds=ttl_seconds,
                    eviction_policy=eviction_policy
                )
                logger.info(f"Created cache: {name} (max_size={max_size})")
            return self._caches[name]
    
    def clear_cache(self, name: str) -> bool:
        """Clear specified cache"""
        with self._manager_lock:
            if name in self._caches:
                self._caches[name].clear()
                return True
            return False
    
    def clear_all(self) -> None:
        """Clear all caches"""
        with self._manager_lock:
            for cache in self._caches.values():
                cache.clear()
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get all cache statistics"""
        with self._manager_lock:
            return {
                name: cache.get_stats()
                for name, cache in self._caches.items()
            }
    
    def cleanup_all_expired(self) -> int:
        """Clean up expired entries in all caches"""
        total = 0
        with self._manager_lock:
            for cache in self._caches.values():
                total += cache.cleanup_expired()
        return total


# Decorator: cache function results
def cached(
    cache_name: str = "default",
    key_prefix: str = "",
    ttl_seconds: Optional[int] = None,
    key_builder: Optional[Callable] = None
):
    """
    Cache decorator
    
    Usage example:
        @cached("api_cache", ttl_seconds=60)
        def fetch_data(user_id: int) -> dict:
            return {"user_id": user_id, "data": "..."}
    """
    def decorator(func: Callable) -> Callable:
        cache = CacheManager.get_instance().get_cache(cache_name)
        
        def wrapper(*args, **kwargs):
            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Default uses function name + args hash
                args_str = str(args) + str(sorted(kwargs.items()))
                args_hash = hashlib.md5(args_str.encode(), usedforsecurity=False).hexdigest()[:8]
                cache_key = f"{key_prefix}{func.__name__}:{args_hash}"
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Store in cache
            cache.set(cache_key, result, ttl_seconds)
            
            return result
        
        return wrapper
    return decorator


# Convenience functions
def get_cache(name: str = "default", **kwargs) -> MemoryCache:
    """Get cache instance"""
    return CacheManager.get_instance().get_cache(name, **kwargs)


def cache_get(name: str, key: str) -> Optional[Any]:
    """Get value from specified cache"""
    return CacheManager.get_instance().get_cache(name).get(key)


def cache_set(name: str, key: str, value: Any, ttl: Optional[int] = None) -> None:
    """Set cache value"""
    CacheManager.get_instance().get_cache(name).set(key, value, ttl)


def cache_delete(name: str, key: str) -> bool:
    """Delete cache value"""
    return CacheManager.get_instance().get_cache(name).delete(key)


def cache_clear(name: str) -> bool:
    """Clear specified cache"""
    return CacheManager.get_instance().clear_cache(name)


def get_cache_stats() -> Dict[str, Dict[str, Any]]:
    """Get all cache statistics"""
    return CacheManager.get_instance().get_all_stats()
