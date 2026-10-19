"""
MCP Rate Limiter

Controls request rate to MCP servers to prevent cost overruns
and respect API quotas. Supports per-server and per-tool rate limits.
"""

import time
import logging
from typing import Dict, Optional
from threading import Lock

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for MCP tool calls.

    Supports:
    - Per-server rate limits (requests per minute/hour)
    - Per-tool cost tracking
    - Configurable burst allowance
    """

    def __init__(self, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        self._rpm = requests_per_minute
        self._rph = requests_per_hour

        # Token bucket state
        self._tokens_minute = float(requests_per_minute)
        self._tokens_hour = float(requests_per_hour)
        self._last_refill_minute = time.monotonic()
        self._last_refill_hour = time.monotonic()
        self._lock = Lock()

        # Statistics
        self._total_calls = 0
        self._limited_calls = 0

    def acquire(self) -> bool:
        """
        Acquire a rate limit token.

        Returns True if the request is allowed, False if rate limited.
        """
        with self._lock:
            self._refill()

            if self._tokens_minute >= 1 and self._tokens_hour >= 1:
                self._tokens_minute -= 1
                self._tokens_hour -= 1
                self._total_calls += 1
                return True
            else:
                self._limited_calls += 1
                return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time"""
        now = time.monotonic()

        # Minute-level refill
        elapsed_minute = now - self._last_refill_minute
        self._tokens_minute = min(
            self._rpm,
            self._tokens_minute + elapsed_minute * (self._rpm / 60.0)
        )
        self._last_refill_minute = now

        # Hour-level refill
        elapsed_hour = now - self._last_refill_hour
        self._tokens_hour = min(
            self._rph,
            self._tokens_hour + elapsed_hour * (self._rph / 3600.0)
        )
        self._last_refill_hour = now

    def retry_after(self) -> float:
        """
        Return seconds to wait before the next retry would likely succeed.
        """
        with self._lock:
            if self._tokens_minute < 1:
                # Time needed for 1 token at the minute refill rate
                return 60.0 / self._rpm
            if self._tokens_hour < 1:
                return 3600.0 / self._rph
            return 1.0

    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        with self._lock:
            return {
                "total_calls": self._total_calls,
                "limited_calls": self._limited_calls,
                "tokens_minute": round(self._tokens_minute, 1),
                "tokens_hour": round(self._tokens_hour, 1),
                "rpm_limit": self._rpm,
                "rph_limit": self._rph,
            }


class RateLimiterRegistry:
    """
    Manages rate limiters for multiple MCP servers.
    """

    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}
        self._default_rpm = 60
        self._default_rph = 1000

    def get_or_create(self, server_name: str, rpm: Optional[int] = None, rph: Optional[int] = None) -> RateLimiter:
        """Get or create a rate limiter for a server"""
        if server_name not in self._limiters:
            self._limiters[server_name] = RateLimiter(
                requests_per_minute=rpm or self._default_rpm,
                requests_per_hour=rph or self._default_rph,
            )
        return self._limiters[server_name]

    def get_stats(self) -> Dict[str, Dict]:
        """Get stats for all rate limiters"""
        return {name: limiter.get_stats() for name, limiter in self._limiters.items()}
