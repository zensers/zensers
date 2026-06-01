"""错误处理框架 - Phase 2.

包含:
- CircuitBreaker: 熔断器
- TokenBucketRateLimiter: 令牌桶限流器
- RateLimiterManager: 限流管理器
- EnhancedRetryHandler: 增强版重试处理器
- execute_with_resilience: 韧性执行函数

设计参考: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/DATA_PROVIDERS.md
"""

import asyncio
import logging
import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, TypeVar, Awaitable

logger = logging.getLogger(__name__)
T = TypeVar('T')


# ============================================================================
# 熔断器 (Circuit Breaker)
# ============================================================================

class CircuitState(Enum):
    """熔断器状态."""
    CLOSED = "closed"       # 关闭（正常）
    OPEN = "open"           # 打开（熔断）
    HALF_OPEN = "half_open" # 半开（测试恢复）


class CircuitBreakerError(Exception):
    """熔断器错误."""
    
    def __init__(self, message: str, state: CircuitState, last_failure_time: Optional[datetime] = None):
        super().__init__(message)
        self.state = state
        self.last_failure_time = last_failure_time


@dataclass
class CircuitBreakerConfig:
    """熔断器配置."""
    failure_threshold: int = 5              # 触发熔断的失败次数
    recovery_timeout_seconds: float = 60.0  # 恢复超时时间（秒）
    half_open_max_calls: int = 3            # 半开状态最大测试调用次数
    success_threshold: int = 2              # 半开状态成功次数阈值（达到后关闭）


class CircuitBreaker:
    """
    熔断器实现.
    
    状态流转:
    CLOSED → (失败数 >= 阈值) → OPEN → (超时) → HALF_OPEN
        ↑                                              ↓
        └────────── (成功数 >= 阈值) ←────────────────┘
                                              ↓ (失败)
                                            OPEN
    
    使用示例:
        cb = CircuitBreaker(failure_threshold=5)
        
        # 方式1: 手动控制
        if cb.should_allow_request():
            try:
                result = operation()
                cb.record_success()
            except Exception as e:
                cb.record_failure()
                raise
        
        # 方式2: 自动包装
        result = await cb.call(async_operation)
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 60.0,
        half_open_max_calls: int = 3,
        success_threshold: int = 2
    ):
        """初始化熔断器.
        
        Args:
            failure_threshold: 触发熔断的失败次数阈值
            recovery_timeout_seconds: 打开后等待恢复的超时时间
            half_open_max_calls: 半开状态允许的最大测试调用次数
            success_threshold: 半开状态成功次数阈值，达到后关闭熔断器
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_calls = 0
        
        self._lock = threading.RLock()
    
    @property
    def state(self) -> CircuitState:
        """获取当前状态."""
        return self._state
    
    @property
    def failure_count(self) -> int:
        """获取失败计数."""
        return self._failure_count
    
    def should_allow_request(self) -> bool:
        """判断是否允许请求.
        
        Returns:
            True: 允许请求
            False: 拒绝请求
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            
            elif self._state == CircuitState.OPEN:
                # 检查是否可以进入半开状态
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                    return True
                return False
            
            elif self._state == CircuitState.HALF_OPEN:
                # 半开状态限制调用次数
                if self._half_open_calls < self.half_open_max_calls:
                    return True
                return False
        
        return False
    
    def record_success(self) -> None:
        """记录成功."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                
                # 达到成功阈值，关闭熔断器
                if self._success_count >= self.success_threshold:
                    self._transition_to_closed()
            else:
                # 关闭状态重置失败计数
                self._failure_count = 0
    
    def record_failure(self) -> None:
        """记录失败."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()
            
            if self._state == CircuitState.HALF_OPEN:
                # 半开状态失败，重新打开
                self._transition_to_open()
            
            elif self._state == CircuitState.CLOSED:
                # 达到阈值，打开熔断器
                if self._failure_count >= self.failure_threshold:
                    self._transition_to_open()
    
    async def call(
        self,
        operation: Callable[[], Awaitable[T]],
        operation_name: str = "operation"
    ) -> T:
        """执行操作（自动熔断保护）.
        
        Args:
            operation: 要执行的异步操作
            operation_name: 操作名称（用于日志）
            
        Returns:
            操作结果
            
        Raises:
            CircuitBreakerError: 熔断器打开时抛出
            Exception: 操作抛出的异常
        """
        if not self.should_allow_request():
            raise CircuitBreakerError(
                f"熔断器打开，拒绝请求: {operation_name}",
                state=self._state,
                last_failure_time=self._last_failure_time
            )
        
        try:
            # 记录半开状态调用
            with self._lock:
                if self._state == CircuitState.HALF_OPEN:
                    self._half_open_calls += 1
            
            result = await operation()
            self.record_success()
            return result
            
        except Exception as e:
            self.record_failure()
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息."""
        with self._lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "failure_threshold": self.failure_threshold,
                "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
                "half_open_calls": self._half_open_calls,
            }
    
    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试恢复."""
        if self._last_failure_time is None:
            return True
        
        elapsed = (datetime.now() - self._last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout_seconds
    
    def _transition_to_open(self) -> None:
        """转换到打开状态."""
        logger.warning(f"熔断器打开，失败次数: {self._failure_count}")
        self._state = CircuitState.OPEN
        self._success_count = 0
        self._half_open_calls = 0
    
    def _transition_to_half_open(self) -> None:
        """转换到半开状态."""
        logger.info("熔断器进入半开状态，开始测试恢复")
        self._state = CircuitState.HALF_OPEN
        self._success_count = 0
        self._half_open_calls = 0
    
    def _transition_to_closed(self) -> None:
        """转换到关闭状态."""
        logger.info("熔断器关闭，服务恢复正常")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = None
    
    def reset(self) -> None:
        """重置熔断器."""
        with self._lock:
            self._transition_to_closed()


# ============================================================================
# 限流器 (Rate Limiter)
# ============================================================================

@dataclass
class RateLimitConfig:
    """限流配置."""
    requests_per_second: float = 10.0
    burst_size: int = 10                # 突发请求数（令牌桶容量）
    max_wait_seconds: float = 5.0       # 最大等待时间


class RateLimiter(ABC):
    """限流器抽象基类."""
    
    @abstractmethod
    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """获取执行许可.
        
        Args:
            timeout: 超时时间（秒），None表示立即返回
            
        Returns:
            True: 获取成功
            False: 获取失败（超时或拒绝）
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息."""
        pass


class TokenBucketRateLimiter(RateLimiter):
    """
    令牌桶限流器.
    
    原理:
    - 桶中令牌以固定速率生成
    - 每个请求消耗一个令牌
    - 令牌不足时请求被阻塞或拒绝
    - 桶有最大容量，防止突发流量
    
    使用示例:
        limiter = TokenBucketRateLimiter(
            requests_per_second=100,
            burst_size=10
        )
        
        if await limiter.acquire(timeout=1.0):
            result = operation()
        else:
            raise RateLimitExceeded("请求被限流")
    """
    
    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst_size: int = 10
    ):
        """初始化令牌桶限流器.
        
        Args:
            requests_per_second: 每秒请求数（令牌生成速率）
            burst_size: 突发请求数（令牌桶容量）
        """
        self.requests_per_second = requests_per_second
        self.burst_size = burst_size
        
        self._tokens = float(burst_size)
        self._last_update = time.time()
        self._lock = asyncio.Lock()
        
        self._stats = {
            "total_requests": 0,
            "acquired": 0,
            "rejected": 0,
        }
    
    @property
    def tokens(self) -> float:
        """获取当前令牌数."""
        return self._tokens
    
    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """获取令牌.
        
        Args:
            timeout: 超时时间（秒），None表示无限等待
            
        Returns:
            True: 获取成功
            False: 获取失败（超时）
        """
        start_time = time.time()
        
        while True:
            async with self._lock:
                self._stats["total_requests"] += 1
                self._refill_tokens()
                
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    self._stats["acquired"] += 1
                    return True
            
            # 计算等待时间
            wait_time = 1.0 / self.requests_per_second
            
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed + wait_time > timeout:
                    async with self._lock:
                        self._stats["rejected"] += 1
                    return False
                wait_time = min(wait_time, timeout - elapsed)
            
            await asyncio.sleep(wait_time)
    
    def _refill_tokens(self) -> None:
        """补充令牌."""
        now = time.time()
        elapsed = now - self._last_update
        self._last_update = now
        
        # 计算新令牌数
        new_tokens = elapsed * self.requests_per_second
        self._tokens = min(self._tokens + new_tokens, float(self.burst_size))
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息."""
        return {
            "tokens": self._tokens,
            "burst_size": self.burst_size,
            "requests_per_second": self.requests_per_second,
            **self._stats,
        }


class RateLimiterManager:
    """
    限流管理器.
    
    管理多个数据供应商的限流器。
    
    使用示例:
        manager = RateLimiterManager()
        manager.register("bloomberg", RateLimitConfig(
            requests_per_second=10,
            burst_size=5
        ))
        
        if await manager.acquire("bloomberg", timeout=1.0):
            result = fetch_data()
    """
    
    def __init__(self):
        self._limiters: Dict[str, TokenBucketRateLimiter] = {}
        self._lock = threading.Lock()
    
    def register(self, provider_name: str, config: RateLimitConfig) -> None:
        """注册供应商限流器.
        
        Args:
            provider_name: 供应商名称
            config: 限流配置
        """
        with self._lock:
            self._limiters[provider_name] = TokenBucketRateLimiter(
                requests_per_second=config.requests_per_second,
                burst_size=config.burst_size
            )
    
    async def acquire(self, provider_name: str, timeout: Optional[float] = None) -> bool:
        """获取供应商的执行许可.
        
        Args:
            provider_name: 供应商名称
            timeout: 超时时间
            
        Returns:
            True: 获取成功
            False: 获取失败（未注册的供应商返回True）
        """
        limiter = self._limiters.get(provider_name)
        if limiter is None:
            # 未注册的供应商直接通过
            return True
        
        return await limiter.acquire(timeout=timeout)
    
    def get_stats(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """获取供应商限流统计."""
        limiter = self._limiters.get(provider_name)
        if limiter is None:
            return None
        return limiter.get_stats()
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有供应商限流统计."""
        with self._lock:
            return {
                name: limiter.get_stats()
                for name, limiter in self._limiters.items()
            }


# ============================================================================
# 重试处理器 (Retry Handler)
# ============================================================================

@dataclass
class RetryConfig:
    """重试配置."""
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = (ConnectionError, TimeoutError, asyncio.TimeoutError)


class EnhancedRetryHandler:
    """
    增强版重试处理器.
    
    特性:
    - 指数退避
    - 随机抖动
    - 可配置异常类型
    - 统计信息
    
    使用示例:
        handler = EnhancedRetryHandler(RetryConfig(
            max_retries=3,
            base_delay_seconds=1.0
        ))
        
        result = await handler.execute(
            fetch_data,
            operation_name="fetch_data"
        )
    """
    
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self._stats = {
            "total_attempts": 0,
            "successful_attempts": 0,
            "failed_attempts": 0,
            "total_retries": 0,
        }
        self._lock = threading.Lock()
    
    def calculate_delay(self, attempt: int) -> float:
        """计算重试延迟.
        
        Args:
            attempt: 尝试次数（从1开始）
            
        Returns:
            延迟时间（秒）
        """
        # 指数退避
        delay = self.config.base_delay_seconds * (
            self.config.exponential_base ** (attempt - 1)
        )
        delay = min(delay, self.config.max_delay_seconds)
        
        # 随机抖动
        if self.config.jitter:
            jitter_factor = 0.8 + random.random() * 0.4  # 80%-120%
            delay *= jitter_factor
        
        return delay
    
    async def execute(
        self,
        operation: Callable[[], Awaitable[T]],
        operation_name: str = "operation"
    ) -> T:
        """执行操作（带重试）.
        
        Args:
            operation: 要执行的异步操作
            operation_name: 操作名称
            
        Returns:
            操作结果
            
        Raises:
            Exception: 所有重试失败后抛出最后一次异常
        """
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            with self._lock:
                self._stats["total_attempts"] += 1
                if attempt > 0:
                    self._stats["total_retries"] += 1
            
            try:
                result = await operation()
                with self._lock:
                    self._stats["successful_attempts"] += 1
                return result
                
            except self.config.retryable_exceptions as e:
                last_error = e
                
                if attempt < self.config.max_retries:
                    delay = self.calculate_delay(attempt + 1)
                    logger.warning(
                        f"{operation_name} 失败 (尝试 {attempt + 1}/{self.config.max_retries + 1}), "
                        f"{delay:.2f}秒后重试: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    with self._lock:
                        self._stats["failed_attempts"] += 1
                    logger.error(
                        f"{operation_name} 在 {self.config.max_retries + 1} 次尝试后失败: {e}"
                    )
            
            except Exception as e:
                # 不可重试的异常直接抛出
                with self._lock:
                    self._stats["failed_attempts"] += 1
                raise
        
        # 所有重试耗尽，抛出最后一次错误
        # 此时 last_error 一定不为 None（因为至少有一次异常才会到达这里）
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"{operation_name}: Unexpected state - no error recorded")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息."""
        with self._lock:
            return {
                **self._stats,
                "config": {
                    "max_retries": self.config.max_retries,
                    "base_delay_seconds": self.config.base_delay_seconds,
                }
            }


# ============================================================================
# 韧性执行 (Resilience Execution)
# ============================================================================

@dataclass
class ResilienceConfig:
    """韧性执行配置."""
    retry_config: Optional[RetryConfig] = None
    circuit_breaker_config: Optional[Dict[str, Any]] = None
    rate_limit_config: Optional[RateLimitConfig] = None


async def execute_with_resilience(
    operation: Callable[[], Awaitable[T]],
    config: ResilienceConfig,
    operation_name: str = "operation",
    circuit_breaker: Optional[CircuitBreaker] = None,
    rate_limiter: Optional[TokenBucketRateLimiter] = None
) -> T:
    """韧性执行操作.
    
    集成重试、熔断、限流三种保护机制。
    
    Args:
        operation: 要执行的异步操作
        config: 韧性配置
        operation_name: 操作名称
        circuit_breaker: 熔断器实例（可选）
        rate_limiter: 限流器实例（可选）
        
    Returns:
        操作结果
        
    Raises:
        CircuitBreakerError: 熔断器打开
        Exception: 操作异常
    """
    # 初始化组件
    retry_handler = EnhancedRetryHandler(config.retry_config)
    
    cb = circuit_breaker
    if cb is None and config.circuit_breaker_config:
        cb = CircuitBreaker(**config.circuit_breaker_config)
    
    limiter = rate_limiter
    
    async def protected_operation():
        # 限流检查
        if limiter:
            acquired = await limiter.acquire(timeout=config.rate_limit_config.max_wait_seconds if config.rate_limit_config else 5.0)
            if not acquired:
                raise asyncio.TimeoutError(f"限流等待超时: {operation_name}")
        
        # 熔断检查
        if cb and not cb.should_allow_request():
            raise CircuitBreakerError(
                f"熔断器打开: {operation_name}",
                state=cb.state,
                last_failure_time=cb._last_failure_time
            )
        
        # 执行操作
        try:
            result = await operation()
            if cb:
                cb.record_success()
            return result
        except Exception as e:
            if cb:
                cb.record_failure()
            raise
    
    # 带重试执行
    return await retry_handler.execute(protected_operation, operation_name)