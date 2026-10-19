"""
Unit tests for MCP core components: CredentialManager, RateLimiter.
"""

import pytest
from datetime import datetime, timedelta
from src.core.mcp.credentials import CredentialManager, AuthConfig, AuthType
from src.core.mcp.rate_limiter import RateLimiter


class TestCredentialManager:
    """Tests for CredentialManager priority stacking and dedup"""

    def setup_method(self):
        self.manager = CredentialManager()

    def test_register_and_get(self):
        """System credential should be returned when no user/session exists"""
        auth = AuthConfig(type=AuthType.API_KEY, api_key="test_key")
        self.manager.register_system("wind", auth)

        result = self.manager.get_auth("wind")
        assert result is not None
        assert result.api_key == "test_key"

    def test_user_overrides_system(self):
        """User-level credential should override system-level"""
        system_auth = AuthConfig(type=AuthType.API_KEY, api_key="system_key")
        user_auth = AuthConfig(type=AuthType.API_KEY, api_key="user_key")
        self.manager.register_system("wind", system_auth)
        self.manager.register_user("wind", user_auth)

        result = self.manager.get_auth("wind")
        assert result.api_key == "user_key"

    def test_session_overrides_user(self):
        """Session-level credential should override user-level"""
        system_auth = AuthConfig(type=AuthType.API_KEY, api_key="system_key")
        user_auth = AuthConfig(type=AuthType.API_KEY, api_key="user_key")
        session_auth = AuthConfig(type=AuthType.API_KEY, api_key="session_key")
        self.manager.register_system("wind", system_auth)
        self.manager.register_user("wind", user_auth)
        self.manager.register_session("wind", session_auth)

        result = self.manager.get_auth("wind")
        assert result.api_key == "session_key"

    def test_duplicate_source_dedup(self):
        """Registering the same source twice should replace, not append"""
        auth1 = AuthConfig(type=AuthType.API_KEY, api_key="first")
        auth2 = AuthConfig(type=AuthType.API_KEY, api_key="second")
        self.manager.register_user("wind", auth1)
        self.manager.register_user("wind", auth2)

        result = self.manager.get_auth("wind")
        assert result.api_key == "second"

    def test_expired_credential_skipped(self):
        """Expired credentials should be skipped, next priority used"""
        system_auth = AuthConfig(type=AuthType.API_KEY, api_key="system_key")
        expired_auth = AuthConfig(type=AuthType.API_KEY, api_key="expired_key")
        self.manager.register_system("wind", system_auth)

        # Manually inject an expired credential at higher priority
        from src.core.mcp.credentials import Credential
        expired = Credential(
            server_name="wind",
            auth=expired_auth,
            source="user",
            expires_at=datetime.now() - timedelta(hours=1),
        )
        self.manager._credentials.setdefault("wind", []).append(expired)

        result = self.manager.get_auth("wind")
        # Should skip expired user credential and return system instead
        assert result is not None
        assert result.api_key == "system_key"

    def test_unknown_server_returns_none(self):
        """Getting auth for an unknown server should return None"""
        result = self.manager.get_auth("nonexistent")
        assert result is None

    def test_audit_log(self):
        """Audit log should record all credential access"""
        auth = AuthConfig(type=AuthType.API_KEY, api_key="key")
        self.manager.register_system("wind", auth)
        self.manager.get_auth("wind")

        log = self.manager.get_audit_log()
        assert len(log) >= 2
        assert log[0]["action"] == "register"
        assert log[1]["action"] == "get"


class TestRateLimiter:
    """Tests for RateLimiter token bucket"""

    def test_initial_allow(self):
        """First request should be allowed"""
        limiter = RateLimiter(requests_per_minute=60, requests_per_hour=1000)
        assert limiter.acquire() is True

    def test_exhaustion_minute(self):
        """Rate limit should be hit when minute budget is exhausted"""
        limiter = RateLimiter(requests_per_minute=5, requests_per_hour=1000)
        for _ in range(5):
            limiter.acquire()
        # Sixth call should be limited
        assert limiter.acquire() is False

    def test_retry_after_positive(self):
        """retry_after should return a positive number when limited"""
        limiter = RateLimiter(requests_per_minute=1, requests_per_hour=1000)
        limiter.acquire()
        limiter.acquire()  # should be limited
        assert limiter.retry_after() > 0

    def test_stats(self):
        """Stats should track calls accurately"""
        limiter = RateLimiter(requests_per_minute=60, requests_per_hour=1000)
        limiter.acquire()
        limiter.acquire()
        stats = limiter.get_stats()
        assert stats["total_calls"] == 2
        assert stats["limited_calls"] == 0
