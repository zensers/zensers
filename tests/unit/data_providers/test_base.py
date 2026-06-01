"""数据提供者基础测试."""

import pytest
from datetime import datetime
from typing import Dict, Any


class TestDataError:
    """测试数据错误类型."""
    
    def test_error_creation(self):
        """测试错误创建."""
        from src.core.data_providers.base import DataError, DataErrorType
        
        error = DataError(
            error_type=DataErrorType.NETWORK_ERROR,
            message="Connection timeout",
            source="test_source"
        )
        
        assert error.error_type == DataErrorType.NETWORK_ERROR
        assert error.message == "Connection timeout"
        assert error.source == "test_source"
        assert error.timestamp is not None
    
    def test_error_to_dict(self):
        """测试错误转字典."""
        from src.core.data_providers.base import DataError, DataErrorType
        
        error = DataError(
            error_type=DataErrorType.RATE_LIMIT,
            message="Rate limited",
            source="api"
        )
        
        data = error.to_dict()
        assert data["error_type"] == "RATE_LIMIT"
        assert data["message"] == "Rate limited"
        assert data["source"] == "api"
    
    def test_error_is_retryable(self):
        """测试错误是否可重试."""
        from src.core.data_providers.base import DataError, DataErrorType
        
        network_error = DataError(DataErrorType.NETWORK_ERROR, "timeout", "api")
        assert network_error.is_retryable() == True
        
        auth_error = DataError(DataErrorType.AUTHENTICATION_ERROR, "unauthorized", "api")
        assert auth_error.is_retryable() == False
        
        rate_limit = DataError(DataErrorType.RATE_LIMIT, "too many requests", "api")
        assert rate_limit.is_retryable() == True


class TestRetryHandler:
    """测试重试处理器."""
    
    @pytest.fixture
    def retry_handler(self):
        """创建重试处理器实例."""
        from src.core.data_providers.base import RetryHandler
        return RetryHandler(max_retries=3, base_delay=0.1, max_delay=1.0)
    
    def test_calculate_delay(self, retry_handler):
        """测试延迟计算."""
        # 指数退避: 0.1, 0.2, 0.4 (有抖动)
        delay1 = retry_handler.calculate_delay(1)
        assert 0.05 <= delay1 <= 0.15  # 基础0.1，抖动±20%
        
        delay2 = retry_handler.calculate_delay(2)
        assert 0.15 <= delay2 <= 0.25  # 基础0.2，抖动±20%
        
        delay3 = retry_handler.calculate_delay(3)
        assert 0.3 <= delay3 <= 0.5  # 基础0.4，抖动±20%
    
    def test_delay_with_jitter(self, retry_handler):
        """测试抖动."""
        delays = [retry_handler.calculate_delay(1) for _ in range(10)]
        # 应该有抖动，不完全相同
        assert len(set(delays)) > 1
    
    def test_should_retry(self, retry_handler):
        """测试是否应该重试."""
        from src.core.data_providers.base import DataError, DataErrorType
        
        # 可重试错误
        error = DataError(DataErrorType.NETWORK_ERROR, "timeout", "api")
        assert retry_handler.should_retry(error, 1) == True
        assert retry_handler.should_retry(error, 3) == True
        
        # 超过最大重试次数
        assert retry_handler.should_retry(error, 4) == False
        
        # 不可重试错误
        auth_error = DataError(DataErrorType.AUTHENTICATION_ERROR, "unauthorized", "api")
        assert retry_handler.should_retry(auth_error, 1) == False


class TestDataProvider:
    """测试数据提供者基类."""
    
    @pytest.fixture
    def mock_provider(self):
        """创建模拟数据提供者."""
        from src.core.data_providers.base import DataProvider, DataError, DataErrorType
        
        class MockProvider(DataProvider):
            def __init__(self, should_fail=False):
                super().__init__("mock")
                self.should_fail = should_fail
                self.call_count = 0
            
            def _fetch(self, query: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
                self.call_count += 1
                if self.should_fail and self.call_count < 3:
                    raise DataError(DataErrorType.NETWORK_ERROR, f"Attempt {self.call_count}", "mock")
                return {"data": "success", "query": query}
        
        return MockProvider
    
    def test_provider_initialization(self, mock_provider):
        """测试提供者初始化."""
        provider = mock_provider()
        
        assert provider.name == "mock"
        assert provider.retry_handler is not None
        assert provider.stats["requests"] == 0
        assert provider.stats["errors"] == 0
    
    def test_successful_fetch(self, mock_provider):
        """测试成功获取数据."""
        provider = mock_provider()
        
        result = provider.fetch("test query")
        
        assert result["data"] == "success"
        assert result["query"] == "test query"
        assert provider.stats["requests"] == 1
        assert provider.stats["successes"] == 1
    
    def test_retry_on_failure(self, mock_provider):
        """测试失败时重试."""
        provider = mock_provider(should_fail=True)
        
        result = provider.fetch("test query")
        
        # 失败2次，第3次成功
        assert provider.call_count == 3
        assert result["data"] == "success"
        assert provider.stats["retries"] == 2
    
    def test_max_retries_exceeded(self, mock_provider):
        """测试超过最大重试次数."""
        from src.core.data_providers.base import DataError, DataErrorType
        
        class AlwaysFailProvider(mock_provider):
            def _fetch(self, query, params=None):
                self.call_count += 1
                raise DataError(DataErrorType.NETWORK_ERROR, "Always fails", "mock")
        
        provider = AlwaysFailProvider()
        
        with pytest.raises(DataError) as exc_info:
            provider.fetch("test query")
        
        assert provider.call_count == 4  # 初始 + 3次重试
        assert provider.stats["errors"] == 4
        assert exc_info.value.error_type == DataErrorType.NETWORK_ERROR
    
    def test_non_retryable_error(self, mock_provider):
        """测试不可重试错误."""
        from src.core.data_providers.base import DataError, DataErrorType
        
        class AuthFailProvider(mock_provider):
            def _fetch(self, query, params=None):
                self.call_count += 1
                raise DataError(DataErrorType.AUTHENTICATION_ERROR, "Unauthorized", "mock")
        
        provider = AuthFailProvider()
        
        with pytest.raises(DataError):
            provider.fetch("test query")
        
        # 只尝试1次，不重试
        assert provider.call_count == 1
    
    def test_get_stats(self, mock_provider):
        """测试获取统计信息."""
        provider = mock_provider()
        
        provider.fetch("query1")
        provider.fetch("query2")
        
        stats = provider.get_stats()
        assert stats["requests"] == 2
        assert stats["successes"] == 2
        assert stats["success_rate"] == 100.0


class TestDataCache:
    """测试数据缓存."""
    
    @pytest.fixture
    def cache(self):
        """创建缓存实例."""
        from src.core.data_providers.base import DataCache
        return DataCache(default_ttl=60)
    
    def test_cache_set_get(self, cache):
        """测试缓存设置和获取."""
        cache.set("key1", {"data": "value"})
        
        result = cache.get("key1")
        assert result == {"data": "value"}
    
    def test_cache_miss(self, cache):
        """测试缓存未命中."""
        result = cache.get("nonexistent")
        assert result is None
    
    def test_cache_expiration(self, cache):
        """测试缓存过期."""
        import time
        
        cache.set("key1", {"data": "value"}, ttl=0.1)
        
        # 立即获取应该命中
        assert cache.get("key1") is not None
        
        # 等待过期
        time.sleep(0.2)
        assert cache.get("key1") is None
    
    def test_cache_clear(self, cache):
        """测试清空缓存."""
        cache.set("key1", {"data": "1"})
        cache.set("key2", {"data": "2"})
        
        cache.clear()
        
        assert cache.get("key1") is None
        assert cache.get("key2") is None
    
    def test_cache_stats(self, cache):
        """测试缓存统计."""
        cache.set("key1", {"data": "1"})
        cache.get("key1")  # hit
        cache.get("key1")  # hit
        cache.get("key2")  # miss
        
        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 66.67
