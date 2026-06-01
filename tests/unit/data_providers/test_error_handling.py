"""错误处理框架测试.

测试内容:
- RetryHandler: 指数退避重试
- CircuitBreaker: 熔断器
- TokenBucketRateLimiter: 令牌桶限流器
- RateLimiterManager: 限流管理器
"""

import asyncio
import time
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.data_providers.error_handling import (
    CircuitState,
    CircuitBreaker,
    CircuitBreakerError,
    TokenBucketRateLimiter,
    RateLimitConfig,
    RateLimiterManager,
    EnhancedRetryHandler,
    RetryConfig,
)


class TestCircuitBreaker:
    """熔断器测试."""
    
    def test_initial_state_is_closed(self):
        """测试初始状态为关闭."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
    
    def test_opens_after_threshold_failures(self):
        """测试达到阈值后打开熔断器."""
        cb = CircuitBreaker(failure_threshold=3)
        
        # 记录3次失败
        for _ in range(3):
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3
    
    def test_remains_closed_below_threshold(self):
        """测试未达阈值保持关闭."""
        cb = CircuitBreaker(failure_threshold=5)
        
        # 记录2次失败
        cb.record_failure()
        cb.record_failure()
        
        assert cb.state == CircuitState.CLOSED
    
    def test_success_resets_failure_count(self):
        """测试成功重置失败计数."""
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitState.CLOSED
    
    def test_half_open_after_recovery_timeout(self):
        """测试恢复超时后进入半开状态."""
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout_seconds=0.1  # 100ms for testing
        )
        
        # 触发熔断
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        # 等待恢复超时
        time.sleep(0.15)
        
        # 允许请求，进入半开状态
        assert cb.should_allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN
    
    def test_half_open_to_closed_on_success(self):
        """测试半开状态成功后关闭."""
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout_seconds=0.1,
            half_open_max_calls=2
        )
        
        # 触发熔断
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        # 等待恢复
        time.sleep(0.15)
        cb.should_allow_request()  # 进入半开
        assert cb.state == CircuitState.HALF_OPEN
        
        # 半开状态成功
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
    
    def test_half_open_to_open_on_failure(self):
        """测试半开状态失败后重新打开."""
        cb = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout_seconds=0.1
        )
        
        # 触发熔断
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        
        # 等待恢复
        time.sleep(0.15)
        cb.should_allow_request()  # 进入半开
        assert cb.state == CircuitState.HALF_OPEN
        
        # 半开状态失败
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
    
    def test_rejects_when_open(self):
        """测试打开状态拒绝请求."""
        cb = CircuitBreaker(failure_threshold=2)
        
        # 触发熔断
        cb.record_failure()
        cb.record_failure()
        
        assert cb.should_allow_request() is False
    
    @pytest.mark.asyncio
    async def test_call_success(self):
        """测试调用成功."""
        cb = CircuitBreaker(failure_threshold=3)
        
        async def success_op():
            return "success"
        
        result = await cb.call(success_op)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_call_with_retries(self):
        """测试熔断器保护下的重试."""
        cb = CircuitBreaker(failure_threshold=2)
        call_count = 0
        
        async def fail_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("temporary error")
            return "success"
        
        # 不应该触发熔断（失败次数 < 阈值）
        result = await cb.call(fail_then_success)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_call_opens_on_failures(self):
        """测试多次失败后熔断."""
        cb = CircuitBreaker(failure_threshold=2)
        
        async def always_fail():
            raise ValueError("always fails")
        
        # 连续失败
        with pytest.raises(ValueError):
            await cb.call(always_fail)
        with pytest.raises(ValueError):
            await cb.call(always_fail)
        
        # 熔断器应该打开
        assert cb.state == CircuitState.OPEN
        
        # 再次调用应该被拒绝
        with pytest.raises(CircuitBreakerError):
            await cb.call(always_fail)
    
    def test_get_stats(self):
        """测试获取统计信息."""
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_success()
        
        stats = cb.get_stats()
        assert stats["state"] == CircuitState.CLOSED.value
        assert stats["failure_count"] == 0  # 成功重置
        assert "last_failure_time" in stats


class TestTokenBucketRateLimiter:
    """令牌桶限流器测试."""
    
    def test_initial_tokens_full(self):
        """测试初始令牌数等于容量."""
        limiter = TokenBucketRateLimiter(
            requests_per_second=10,
            burst_size=5
        )
        assert limiter.tokens == 5.0
    
    @pytest.mark.asyncio
    async def test_acquire_token(self):
        """测试获取令牌."""
        limiter = TokenBucketRateLimiter(
            requests_per_second=10,
            burst_size=5
        )
        
        # 应该立即获取成功
        result = await limiter.acquire(timeout=0.1)
        assert result is True
        assert limiter.tokens < 5.0
    
    @pytest.mark.asyncio
    async def test_acquire_with_refill(self):
        """测试令牌补充."""
        limiter = TokenBucketRateLimiter(
            requests_per_second=100,  # 100/s = 0.1/ms
            burst_size=1
        )
        
        # 消耗令牌
        result1 = await limiter.acquire(timeout=0.01)
        assert result1 is True
        
        # 等待补充
        await asyncio.sleep(0.02)
        
        # 应该有新令牌
        result2 = await limiter.acquire(timeout=0.01)
        assert result2 is True
    
    @pytest.mark.asyncio
    async def test_acquire_timeout(self):
        """测试获取令牌超时."""
        limiter = TokenBucketRateLimiter(
            requests_per_second=1,
            burst_size=1
        )
        
        # 消耗唯一令牌
        result1 = await limiter.acquire(timeout=0.01)
        assert result1 is True
        
        # 短时间无法获取新令牌
        result2 = await limiter.acquire(timeout=0.01)
        assert result2 is False
    
    @pytest.mark.asyncio
    async def test_concurrent_acquire(self):
        """测试并发获取令牌."""
        limiter = TokenBucketRateLimiter(
            requests_per_second=100,
            burst_size=10
        )
        
        # 并发获取5个令牌
        results = await asyncio.gather(*[
            limiter.acquire(timeout=0.1) for _ in range(5)
        ])
        
        # 全部成功
        assert all(results)
        
        # 令牌数减少
        assert limiter.tokens < 10.0
    
    def test_get_stats(self):
        """测试获取统计信息."""
        limiter = TokenBucketRateLimiter(
            requests_per_second=10,
            burst_size=5
        )
        
        stats = limiter.get_stats()
        assert stats["tokens"] == 5.0
        assert stats["burst_size"] == 5
        assert stats["requests_per_second"] == 10


class TestRateLimiterManager:
    """限流管理器测试."""
    
    def test_register_provider(self):
        """测试注册供应商."""
        manager = RateLimiterManager()
        
        manager.register("bloomberg", RateLimitConfig(
            requests_per_second=10,
            burst_size=5
        ))
        
        assert "bloomberg" in manager._limiters
    
    @pytest.mark.asyncio
    async def test_acquire_registered_provider(self):
        """测试获取已注册供应商的令牌."""
        manager = RateLimiterManager()
        manager.register("bloomberg", RateLimitConfig(
            requests_per_second=100,
            burst_size=10
        ))
        
        result = await manager.acquire("bloomberg", timeout=0.1)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_acquire_unregistered_provider(self):
        """测试未注册供应商直接通过."""
        manager = RateLimiterManager()
        
        # 未注册的供应商应该返回True
        result = await manager.acquire("unknown", timeout=0.1)
        assert result is True
    
    def test_get_all_stats(self):
        """测试获取所有统计."""
        manager = RateLimiterManager()
        manager.register("bloomberg", RateLimitConfig(
            requests_per_second=10,
            burst_size=5
        ))
        manager.register("wind", RateLimitConfig(
            requests_per_second=5,
            burst_size=3
        ))
        
        stats = manager.get_all_stats()
        assert "bloomberg" in stats
        assert "wind" in stats


class TestEnhancedRetryHandler:
    """增强版重试处理器测试."""
    
    def test_initialization(self):
        """测试初始化."""
        config = RetryConfig(
            max_retries=5,
            base_delay_seconds=2.0,
            max_delay_seconds=120.0,
            exponential_base=3.0
        )
        handler = EnhancedRetryHandler(config)
        
        assert handler.config.max_retries == 5
        assert handler.config.base_delay_seconds == 2.0
    
    def test_calculate_delay_exponential(self):
        """测试指数退避延迟计算."""
        handler = EnhancedRetryHandler(RetryConfig(
            base_delay_seconds=1.0,
            exponential_base=2.0,
            jitter=False
        ))
        
        # 第1次: 1 * 2^0 = 1
        assert handler.calculate_delay(1) == 1.0
        # 第2次: 1 * 2^1 = 2
        assert handler.calculate_delay(2) == 2.0
        # 第3次: 1 * 2^2 = 4
        assert handler.calculate_delay(3) == 4.0
    
    def test_calculate_delay_max_cap(self):
        """测试延迟上限."""
        handler = EnhancedRetryHandler(RetryConfig(
            base_delay_seconds=1.0,
            exponential_base=10.0,
            max_delay_seconds=60.0,
            jitter=False
        ))
        
        # 第10次应该被限制在60
        delay = handler.calculate_delay(10)
        assert delay == 60.0
    
    def test_calculate_delay_with_jitter(self):
        """测试抖动延迟."""
        handler = EnhancedRetryHandler(RetryConfig(
            base_delay_seconds=1.0,
            jitter=True
        ))
        
        # 多次计算应该有差异（抖动）
        delays = [handler.calculate_delay(1) for _ in range(10)]
        assert len(set(delays)) > 1  # 不完全相同
    
    @pytest.mark.asyncio
    async def test_execute_success_first_try(self):
        """测试首次成功."""
        handler = EnhancedRetryHandler()
        
        async def success():
            return "ok"
        
        result = await handler.execute(success, "test_op")
        assert result == "ok"
    
    @pytest.mark.asyncio
    async def test_execute_success_after_retry(self):
        """测试重试后成功."""
        handler = EnhancedRetryHandler(RetryConfig(
            max_retries=3,
            base_delay_seconds=0.01,
            jitter=False
        ))
        
        call_count = 0
        
        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("temporary error")
            return "ok"
        
        result = await handler.execute(fail_twice, "test_op")
        assert result == "ok"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_execute_all_retries_failed(self):
        """测试所有重试失败."""
        handler = EnhancedRetryHandler(RetryConfig(
            max_retries=2,
            base_delay_seconds=0.01,
            jitter=False
        ))
        
        async def always_fail():
            raise ConnectionError("always fails")
        
        with pytest.raises(ConnectionError):
            await handler.execute(always_fail, "test_op")
    
    def test_get_stats(self):
        """测试获取统计."""
        handler = EnhancedRetryHandler()
        
        stats = handler.get_stats()
        assert "total_attempts" in stats
        assert "successful_attempts" in stats
        assert "failed_attempts" in stats


class TestCircuitBreakerIntegration:
    """熔断器集成测试."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_with_retry(self):
        """测试熔断器与重试处理器集成."""
        from src.core.data_providers.error_handling import (
            execute_with_resilience,
            ResilienceConfig
        )
        
        call_count = 0
        
        async def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("timeout")
            return "success"
        
        config = ResilienceConfig(
            retry_config=RetryConfig(max_retries=3, base_delay_seconds=0.01),
            circuit_breaker_config={
                "failure_threshold": 5,
                "recovery_timeout_seconds": 1
            }
        )
        
        result = await execute_with_resilience(operation, config, "test_op")
        assert result == "success"
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_protection(self):
        """测试熔断器保护."""
        from src.core.data_providers.error_handling import (
            execute_with_resilience,
            ResilienceConfig
        )
        
        # 配置：2次失败后熔断
        config = ResilienceConfig(
            retry_config=RetryConfig(max_retries=1, base_delay_seconds=0.01),
            circuit_breaker_config={
                "failure_threshold": 2,
                "recovery_timeout_seconds": 10
            }
        )
        
        call_count = 0
        
        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("error")
        
        # 第一次调用（失败）
        with pytest.raises(ValueError):
            await execute_with_resilience(always_fail, config, "test_op")
        
        # 第二次调用（失败，触发熔断）
        with pytest.raises(ValueError):
            await execute_with_resilience(always_fail, config, "test_op")
        
        # 第三次调用（被熔断器拒绝）
        with pytest.raises(CircuitBreakerError):
            await execute_with_resilience(always_fail, config, "test_op")
        
        # 熔断器拒绝后，操作不会被调用
        assert call_count == 2  # 只有2次实际调用
