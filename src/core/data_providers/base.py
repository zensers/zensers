"""数据提供者基础组件.

包含:
- DataError: 结构化错误处理
- RetryHandler: 指数退避重试
- DataCache: 内存缓存
- DataProvider: 抽象基类
"""

import time
import random
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, Optional, Set


class DataErrorType(Enum):
    """数据错误类型."""
    NETWORK_ERROR = auto()
    TIMEOUT_ERROR = auto()
    RATE_LIMIT = auto()
    AUTHENTICATION_ERROR = auto()
    AUTHORIZATION_ERROR = auto()
    VALIDATION_ERROR = auto()
    NOT_FOUND = auto()
    SERVER_ERROR = auto()
    PARSE_ERROR = auto()
    SOURCE_ERROR = auto()      # 数据源错误
    UNKNOWN_ERROR = auto()


@dataclass
class DataError(Exception):
    """结构化数据错误."""
    error_type: DataErrorType
    message: str
    source: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return {
            "error_type": self.error_type.name,
            "message": self.message,
            "source": self.source,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }
    
    def is_retryable(self) -> bool:
        """判断错误是否可重试."""
        retryable_types = {
            DataErrorType.NETWORK_ERROR,
            DataErrorType.TIMEOUT_ERROR,
            DataErrorType.RATE_LIMIT,
            DataErrorType.SERVER_ERROR,
        }
        return self.error_type in retryable_types


class RetryHandler:
    """指数退避重试处理器."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        """初始化重试处理器.
        
        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            exponential_base: 指数基数
            jitter: 是否添加随机抖动
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def calculate_delay(self, attempt: int) -> float:
        """计算重试延迟.
        
        Args:
            attempt: 当前尝试次数（从1开始）
            
        Returns:
            延迟时间（秒）
        """
        # 指数退避: base_delay * (exponential_base ^ (attempt - 1))
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            # 添加 ±20% 的随机抖动
            jitter_factor = 0.8 + random.random() * 0.4
            delay *= jitter_factor
        
        return delay
    
    def should_retry(self, error: DataError, attempt: int) -> bool:
        """判断是否应该重试.
        
        Args:
            error: 发生的错误
            attempt: 当前尝试次数（已经发生的失败次数）
            
        Returns:
            是否应该重试
        """
        # attempt 是已经失败的次数，如果 >= max_retries 则不再重试
        if attempt > self.max_retries:
            return False
        return error.is_retryable()


class DataCache:
    """内存数据缓存."""
    
    def __init__(self, default_ttl: int = 300):
        """初始化缓存.
        
        Args:
            default_ttl: 默认过期时间（秒）
        """
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0}
    
    def _make_key(self, key: str) -> str:
        """生成缓存键."""
        return key
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值.
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值或None
        """
        with self._lock:
            cache_key = self._make_key(key)
            entry = self._cache.get(cache_key)
            
            if entry is None:
                self._stats["misses"] += 1
                return None
            
            # 检查是否过期
            if time.time() > entry["expires_at"]:
                del self._cache[cache_key]
                self._stats["misses"] += 1
                return None
            
            self._stats["hits"] += 1
            return entry["value"]
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值.
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None使用默认值
        """
        with self._lock:
            cache_key = self._make_key(key)
            expires_at = time.time() + (ttl if ttl is not None else self.default_ttl)
            
            self._cache[cache_key] = {
                "value": value,
                "expires_at": expires_at,
            }
    
    def clear(self) -> None:
        """清空缓存."""
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0.0
            
            return {
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "total": total,
                "hit_rate": round(hit_rate, 2),
                "size": len(self._cache),
            }


class DataProvider(ABC):
    """数据提供者抽象基类."""
    
    def __init__(
        self,
        name: str,
        retry_handler: Optional[RetryHandler] = None,
        cache: Optional[DataCache] = None,
    ):
        """初始化数据提供者.
        
        Args:
            name: 提供者名称
            retry_handler: 重试处理器
            cache: 数据缓存
        """
        self.name = name
        self.retry_handler = retry_handler or RetryHandler()
        self.cache = cache
        self._stats = {
            "requests": 0,
            "successes": 0,
            "errors": 0,
            "retries": 0,
        }
        self._stats_lock = threading.Lock()
    
    @abstractmethod
    def _fetch(self, query: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """实际获取数据的抽象方法.
        
        Args:
            query: 查询字符串
            params: 查询参数
            
        Returns:
            获取的数据
            
        Raises:
            DataError: 获取失败时抛出
        """
        pass
    
    def fetch(self, query: str, params: Optional[Dict[str, Any]] = None, use_cache: bool = True) -> Dict[str, Any]:
        """获取数据（带重试和缓存）.
        
        Args:
            query: 查询字符串
            params: 查询参数
            use_cache: 是否使用缓存
            
        Returns:
            获取的数据
            
        Raises:
            DataError: 所有重试都失败时抛出
        """
        cache_key = f"{self.name}:{query}:{hash(str(params))}"
        
        # 尝试从缓存获取
        if use_cache and self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        
        with self._stats_lock:
            self._stats["requests"] += 1
        
        attempt = 0
        last_error = None
        
        while attempt <= self.retry_handler.max_retries:
            try:
                result = self._fetch(query, params)
                
                with self._stats_lock:
                    self._stats["successes"] += 1
                
                # 写入缓存
                if use_cache and self.cache:
                    self.cache.set(cache_key, result)
                
                return result
                
            except DataError as e:
                last_error = e
                attempt += 1
                
                with self._stats_lock:
                    self._stats["errors"] += 1
                
                if self.retry_handler.should_retry(e, attempt):
                    with self._stats_lock:
                        self._stats["retries"] += 1
                    
                    delay = self.retry_handler.calculate_delay(attempt)
                    time.sleep(delay)
                else:
                    break
        
        # 所有重试都失败
        if last_error is not None:
            raise last_error
        raise RuntimeError("All retries failed but no error was recorded")
    
    @property
    def stats(self) -> Dict[str, Any]:
        """获取统计信息（属性访问）."""
        return self.get_stats()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息."""
        with self._stats_lock:
            success_rate = (
                self._stats["successes"] / self._stats["requests"] * 100
                if self._stats["requests"] > 0
                else 0.0
            )
            
            return {
                **self._stats,
                "success_rate": round(success_rate, 2),
            }
