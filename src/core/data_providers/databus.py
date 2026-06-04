"""DataBus V2 - 增强版数据总线.

核心功能:
- 智能数据源路由
- 自动降级/故障转移
- 多级缓存 (内存 + 磁盘 + Redis)
- 成本监控与限流
- 数据源健康检查
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

# 配置日志
logger = logging.getLogger(__name__)


class DataSourcePriority(Enum):
    """数据源优先级."""
    PRIMARY = 1      # 主数据源
    SECONDARY = 2    # 备用数据源
    FALLBACK = 3     # 降级数据源


class DataSourceHealth(Enum):
    """数据源健康状态."""
    HEALTHY = auto()      # 健康
    DEGRADED = auto()     # 降级
    UNHEALTHY = auto()    # 不健康
    UNKNOWN = auto()      # 未知


@dataclass
class DataSourceConfig:
    """数据源配置."""
    source_id: str
    provider: Any
    priority: DataSourcePriority = DataSourcePriority.PRIMARY
    data_types: List[str] = field(default_factory=list)
    cost_per_request: float = 0.0  # 每次请求成本(美元)
    rate_limit_per_minute: int = 60
    timeout_seconds: float = 30.0
    enabled: bool = True


@dataclass
class QueryCost:
    """查询成本记录."""
    source_id: str
    query_type: str
    cost_usd: float
    duration_ms: int
    timestamp: datetime = field(default_factory=datetime.now)
    cache_hit: bool = False
    fallback_used: bool = False


@dataclass
class CacheEntry:
    """缓存条目."""
    data: Any
    created_at: datetime
    ttl_seconds: int
    access_count: int = 0
    last_accessed: Optional[datetime] = None


class CacheBackend(ABC):
    """缓存后端抽象基类."""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值."""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """设置缓存值."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除缓存值."""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """清空缓存."""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息."""
        pass


class MemoryCacheBackend(CacheBackend):
    """内存缓存后端."""
    
    def __init__(self, max_size: int = 10000):
        self._cache: Dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._lock = threading.RLock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}
    
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return None
            
            # 检查过期
            if datetime.now() > entry.created_at + timedelta(seconds=entry.ttl_seconds):
                del self._cache[key]
                self._stats["misses"] += 1
                return None
            
            # 更新访问统计
            entry.access_count += 1
            entry.last_accessed = datetime.now()
            self._stats["hits"] += 1
            return entry.data
    
    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self._lock:
            # 如果缓存满了，移除最少访问的条目
            if len(self._cache) >= self._max_size:
                self._evict_lru()
            
            self._cache[key] = CacheEntry(
                data=value,
                created_at=datetime.now(),
                ttl_seconds=ttl_seconds
            )
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            return {
                **self._stats,
                "size": len(self._cache),
                "hit_rate": self._stats["hits"] / total if total > 0 else 0.0,
                "max_size": self._max_size,
            }
    
    def _evict_lru(self) -> None:
        """移除最少访问的条目 (LRU)."""
        if not self._cache:
            return
        
        # 找到最少访问的条目
        lru_key = min(
            self._cache.keys(),
            key=lambda k: (self._cache[k].access_count, self._cache[k].created_at)
        )
        del self._cache[lru_key]
        self._stats["evictions"] += 1


class DiskCacheBackend(CacheBackend):
    """磁盘缓存后端."""
    
    def __init__(self, cache_dir: str = ".cache/databus", max_size_mb: int = 100):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._lock = threading.RLock()
        self._stats = {"hits": 0, "misses": 0, "errors": 0}
    
    def _get_file_path(self, key: str) -> Path:
        """获取缓存文件路径."""
        # 使用两层目录结构避免单个目录文件过多
        hash_val = hashlib.md5(key.encode()).hexdigest()
        dir1 = hash_val[:2]
        dir2 = hash_val[2:4]
        return self._cache_dir / dir1 / dir2 / f"{hash_val}.json"
    
    def get(self, key: str) -> Optional[Any]:
        try:
            file_path = self._get_file_path(key)
            if not file_path.exists():
                self._stats["misses"] += 1
                return None
            
            # 使用JSON替代pickle，避免安全风险
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 重建CacheEntry
            entry = CacheEntry(
                data=data["data"],
                created_at=datetime.fromisoformat(data["created_at"]),
                ttl_seconds=data["ttl_seconds"],
                access_count=data.get("access_count", 0),
                last_accessed=datetime.fromisoformat(data["last_accessed"]) if data.get("last_accessed") else None
            )
            
            # 检查过期
            if datetime.now() > entry.created_at + timedelta(seconds=entry.ttl_seconds):
                file_path.unlink()
                self._stats["misses"] += 1
                return None
            
            self._stats["hits"] += 1
            return entry.data
            
        except Exception as e:
            logger.warning(f"磁盘缓存读取失败: {e}", exc_info=True)
            self._stats["errors"] += 1
            return None
    
    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        try:
            file_path = self._get_file_path(key)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            entry = CacheEntry(
                data=value,
                created_at=datetime.now(),
                ttl_seconds=ttl_seconds
            )
            
            # 使用JSON替代pickle，避免安全风险
            data = {
                "data": entry.data,
                "created_at": entry.created_at.isoformat(),
                "ttl_seconds": entry.ttl_seconds,
                "access_count": entry.access_count,
                "last_accessed": entry.last_accessed.isoformat() if entry.last_accessed else None
            }
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 检查并清理过期缓存
            self._cleanup_if_needed()
            
        except Exception as e:
            logger.warning(f"磁盘缓存写入失败: {e}", exc_info=True)
            self._stats["errors"] += 1
    
    def delete(self, key: str) -> bool:
        try:
            file_path = self._get_file_path(key)
            if file_path.exists():
                file_path.unlink()
                return True
            return False
        except Exception as e:
            logger.warning(f"删除缓存文件失败: {e}", exc_info=True)
            return False
    
    def clear(self) -> None:
        try:
            for file_path in self._cache_dir.rglob("*.json"):
                file_path.unlink()
        except Exception as e:
            logger.warning(f"清空缓存失败: {e}", exc_info=True)
    
    def get_stats(self) -> Dict[str, Any]:
        total = self._stats["hits"] + self._stats["misses"]
        return {
            **self._stats,
            "hit_rate": self._stats["hits"] / total if total > 0 else 0.0,
            "cache_dir": str(self._cache_dir),
        }
    
    def _cleanup_if_needed(self) -> None:
        """如果需要，清理过期缓存."""
        try:
            total_size = sum(
                f.stat().st_size for f in self._cache_dir.rglob("*.json")
            )
            
            if total_size > self._max_size_bytes:
                # 删除最旧的文件
                files = sorted(
                    self._cache_dir.rglob("*.json"),
                    key=lambda f: f.stat().st_mtime
                )
                
                for file_path in files:
                    if total_size <= self._max_size_bytes * 0.8:
                        break
                    size = file_path.stat().st_size
                    file_path.unlink()
                    total_size -= size
                    
        except Exception as e:
            logger.warning(f"缓存清理失败: {e}", exc_info=True)


class MultiLevelCache:
    """多级缓存."""
    
    def __init__(
        self,
        memory_cache: Optional[MemoryCacheBackend] = None,
        disk_cache: Optional[DiskCacheBackend] = None,
        redis_cache: Optional[CacheBackend] = None,
    ):
        self._memory = memory_cache or MemoryCacheBackend()
        self._disk = disk_cache
        self._redis = redis_cache
        self._stats = {"hits": 0, "misses": 0}
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值 (L1 -> L2 -> L3)."""
        # L1: 内存缓存
        value = self._memory.get(key)
        if value is not None:
            self._stats["hits"] += 1
            return value
        
        # L2: 磁盘缓存
        if self._disk:
            value = self._disk.get(key)
            if value is not None:
                # 回填到内存缓存
                self._memory.set(key, value, 60)  # 短期TTL
                self._stats["hits"] += 1
                return value
        
        # L3: Redis缓存
        if self._redis:
            value = self._redis.get(key)
            if value is not None:
                # 回填到内存和磁盘
                self._memory.set(key, value, 60)
                if self._disk:
                    self._disk.set(key, value, 300)
                self._stats["hits"] += 1
                return value
        
        self._stats["misses"] += 1
        return None
    
    def set(
        self,
        key: str,
        value: Any,
        memory_ttl: int = 300,
        disk_ttl: int = 3600,
        redis_ttl: int = 86400,
    ) -> None:
        """设置缓存值."""
        self._memory.set(key, value, memory_ttl)
        if self._disk:
            self._disk.set(key, value, disk_ttl)
        if self._redis:
            self._redis.set(key, value, redis_ttl)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息."""
        total = self._stats["hits"] + self._stats["misses"]
        return {
            **self._stats,
            "hit_rate": self._stats["hits"] / total if total > 0 else 0.0,
            "memory": self._memory.get_stats(),
            "disk": self._disk.get_stats() if self._disk else None,
            "redis": self._redis.get_stats() if self._redis else None,
        }


class DataBusV2:
    """增强版数据总线."""
    
    def __init__(
        self,
        cache: Optional[MultiLevelCache] = None,
        enable_cost_tracking: bool = True,
        enable_health_check: bool = True,
        health_check_interval: int = 60,
    ):
        """初始化数据总线.
        
        Args:
            cache: 多级缓存实例
            enable_cost_tracking: 是否启用成本追踪
            enable_health_check: 是否启用健康检查
            health_check_interval: 健康检查间隔(秒)
        """
        self._sources: Dict[str, DataSourceConfig] = {}
        self._cache = cache or MultiLevelCache()
        self._enable_cost_tracking = enable_cost_tracking
        self._cost_history: List[QueryCost] = []
        self._cost_lock = threading.Lock()
        
        # 健康检查
        self._enable_health_check = enable_health_check
        self._health_status: Dict[str, DataSourceHealth] = {}
        self._health_check_interval = health_check_interval
        self._last_health_check: Dict[str, datetime] = {}
        
        # 限流控制
        self._rate_limiters: Dict[str, "RateLimiter"] = {}
        
        # 统计信息
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "fallback_requests": 0,
            "cache_hits": 0,
        }
        self._stats_lock = threading.Lock()
    
    def register_source(self, config: DataSourceConfig) -> None:
        """注册数据源."""
        self._sources[config.source_id] = config
        self._health_status[config.source_id] = DataSourceHealth.UNKNOWN
        
        # 初始化限流器
        self._rate_limiters[config.source_id] = RateLimiter(
            max_requests=config.rate_limit_per_minute,
            window_seconds=60
        )
    
    def unregister_source(self, source_id: str) -> bool:
        """注销数据源."""
        if source_id in self._sources:
            del self._sources[source_id]
            del self._health_status[source_id]
            del self._rate_limiters[source_id]
            return True
        return False
    
    async def query(
        self,
        data_type: str,
        params: Dict[str, Any],
        preferred_source: Optional[str] = None,
        use_cache: bool = True,
        cache_ttl: int = 300,
    ) -> Dict[str, Any]:
        """查询数据.
        
        Args:
            data_type: 数据类型
            params: 查询参数
            preferred_source: 优先使用的数据源
            use_cache: 是否使用缓存
            cache_ttl: 缓存过期时间(秒)
            
        Returns:
            查询结果
        """
        with self._stats_lock:
            self._stats["total_requests"] += 1
        
        # 生成缓存键
        cache_key = self._make_cache_key(data_type, params)
        
        # 尝试从缓存获取
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                with self._stats_lock:
                    self._stats["cache_hits"] += 1
                return {
                    "success": True,
                    "data": cached,
                    "source": "cache",
                    "cached": True,
                }
        
        # 选择数据源
        sources = self._select_sources(data_type, preferred_source)
        
        if not sources:
            return {
                "success": False,
                "error": f"没有可用的数据源 for {data_type}",
            }
        
        # 尝试从数据源获取
        last_error = None
        fallback_used = False
        
        for i, source_id in enumerate(sources):
            config = self._sources.get(source_id)
            if not config or not config.enabled:
                continue
            
            # 检查健康状态
            if self._health_status.get(source_id) == DataSourceHealth.UNHEALTHY:
                if i < len(sources) - 1:
                    fallback_used = True
                    continue
            
            # 检查限流
            if not self._rate_limiters[source_id].allow():
                if i < len(sources) - 1:
                    fallback_used = True
                    continue
            
            try:
                start_time = time.time()
                
                # 调用数据提供者
                result = await config.provider.fetch(params)
                
                duration_ms = int((time.time() - start_time) * 1000)
                
                # 记录成本
                if self._enable_cost_tracking:
                    self._record_cost(
                        QueryCost(
                            source_id=source_id,
                            query_type=data_type,
                            cost_usd=config.cost_per_request,
                            duration_ms=duration_ms,
                            fallback_used=fallback_used,
                        )
                    )
                
                # 更新健康状态
                self._health_status[source_id] = DataSourceHealth.HEALTHY
                
                # 写入缓存
                if use_cache:
                    self._cache.set(cache_key, result, memory_ttl=min(cache_ttl, 300))
                
                with self._stats_lock:
                    self._stats["successful_requests"] += 1
                    if fallback_used:
                        self._stats["fallback_requests"] += 1
                
                return {
                    "success": True,
                    "data": result,
                    "source": source_id,
                    "fallback_used": fallback_used,
                    "duration_ms": duration_ms,
                }
                
            except Exception as e:
                last_error = e
                # 更新健康状态
                self._update_health_on_error(source_id)
                fallback_used = True
                continue
        
        # 所有数据源都失败
        with self._stats_lock:
            self._stats["failed_requests"] += 1
        
        return {
            "success": False,
            "error": str(last_error) if last_error else "所有数据源都不可用",
            "sources_tried": sources,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息."""
        with self._stats_lock:
            stats = dict(self._stats)
        
        total = stats["total_requests"]
        return {
            **stats,
            "success_rate": stats["successful_requests"] / total if total > 0 else 0.0,
            "cache_hit_rate": stats["cache_hits"] / total if total > 0 else 0.0,
            "cache_stats": self._cache.get_stats(),
            "health_status": {k: v.name for k, v in self._health_status.items()},
        }
    
    def get_cost_report(self, days: int = 7) -> Dict[str, Any]:
        """获取成本报告.
        
        Args:
            days: 过去多少天的数据
            
        Returns:
            成本报告
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        with self._cost_lock:
            recent_costs = [c for c in self._cost_history if c.timestamp > cutoff]
        
        if not recent_costs:
            return {"total_cost": 0.0, "request_count": 0}
        
        total_cost = sum(c.cost_usd for c in recent_costs)
        
        # 按数据源统计
        by_source = {}
        for cost in recent_costs:
            if cost.source_id not in by_source:
                by_source[cost.source_id] = {"cost": 0.0, "count": 0}
            by_source[cost.source_id]["cost"] += cost.cost_usd
            by_source[cost.source_id]["count"] += 1
        
        return {
            "period_days": days,
            "total_cost_usd": round(total_cost, 4),
            "total_requests": len(recent_costs),
            "avg_cost_per_request": round(total_cost / len(recent_costs), 6),
            "by_source": by_source,
        }
    
    def _make_cache_key(self, data_type: str, params: Dict[str, Any]) -> str:
        """生成缓存键."""
        raw = json.dumps({"type": data_type, "params": params}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()
    
    def _select_sources(
        self,
        data_type: str,
        preferred_source: Optional[str] = None,
    ) -> List[str]:
        """选择合适的数据源."""
        candidates = []
        
        # 优先使用指定的数据源
        if preferred_source and preferred_source in self._sources:
            candidates.append(preferred_source)
        
        # 按优先级排序其他数据源
        other_sources = [
            (sid, config)
            for sid, config in self._sources.items()
            if sid != preferred_source
            and config.enabled
            and (not data_type or data_type in config.data_types or not config.data_types)
        ]
        
        other_sources.sort(key=lambda x: x[1].priority.value)
        candidates.extend([sid for sid, _ in other_sources])
        
        return candidates
    
    def _record_cost(self, cost: QueryCost) -> None:
        """记录成本."""
        with self._cost_lock:
            self._cost_history.append(cost)
            # 保留最近10000条记录
            if len(self._cost_history) > 10000:
                self._cost_history = self._cost_history[-10000:]
    
    def _update_health_on_error(self, source_id: str) -> None:
        """错误时更新健康状态."""
        current = self._health_status.get(source_id, DataSourceHealth.HEALTHY)
        
        if current == DataSourceHealth.HEALTHY:
            self._health_status[source_id] = DataSourceHealth.DEGRADED
        elif current == DataSourceHealth.DEGRADED:
            self._health_status[source_id] = DataSourceHealth.UNHEALTHY


class RateLimiter:
    """滑动窗口限流器."""
    
    def __init__(self, max_requests: int, window_seconds: int):
        """初始化限流器.
        
        Args:
            max_requests: 窗口内最大请求数
            window_seconds: 窗口大小(秒)
        """
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: List[float] = []
        self._lock = threading.Lock()
    
    def allow(self) -> bool:
        """检查是否允许请求."""
        with self._lock:
            now = time.time()
            cutoff = now - self._window_seconds
            
            # 移除窗口外的请求记录
            self._requests = [t for t in self._requests if t > cutoff]
            
            # 检查是否超过限制
            if len(self._requests) >= self._max_requests:
                return False
            
            # 记录本次请求
            self._requests.append(now)
            return True
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息."""
        with self._lock:
            now = time.time()
            cutoff = now - self._window_seconds
            recent = [t for t in self._requests if t > cutoff]
            
            return {
                "current_requests": len(recent),
                "max_requests": self._max_requests,
                "window_seconds": self._window_seconds,
                "utilization": len(recent) / self._max_requests,
            }


# 便捷函数
def create_databus_with_defaults(cache_dir: Optional[str] = None) -> DataBusV2:
    """创建带有默认配置的DataBus."""
    cache = MultiLevelCache(
        memory_cache=MemoryCacheBackend(max_size=10000),
        disk_cache=DiskCacheBackend(cache_dir=cache_dir or ".cache/databus", max_size_mb=100),
    )
    
    return DataBusV2(
        cache=cache,
        enable_cost_tracking=True,
        enable_health_check=True,
    )
