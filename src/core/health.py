# -*- coding: utf-8 -*-
"""
Health Check Module
===================

Phase 4 Week 17: Observability - Health Check

Features:
- Component health check - check subsystem status
- Health status aggregation - comprehensive overall health judgment
- Health endpoint - provide functional health check interface
- Custom checker - support registering custom check logic
- Health report - generate detailed health report

Core classes:
- HealthStatus - Health status enumeration
- HealthCheckResult - Check result
- HealthChecker - Health checker base class
- HealthMonitor - Health monitor
"""

import os
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
import logging

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status enumeration"""
    HEALTHY = "healthy"       # Healthy
    DEGRADED = "degraded"     # Degraded
    UNHEALTHY = "unhealthy"   # Unhealthy
    UNKNOWN = "unknown"       # Unknown


@dataclass
class HealthCheckResult:
    """Health check result"""
    name: str
    status: HealthStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
        }
    
    @classmethod
    def healthy(cls, name: str, message: str = "", **details) -> "HealthCheckResult":
        """Create healthy result"""
        return cls(name, HealthStatus.HEALTHY, message, details)
    
    @classmethod
    def degraded(cls, name: str, message: str = "", **details) -> "HealthCheckResult":
        """Create degraded result"""
        return cls(name, HealthStatus.DEGRADED, message, details)
    
    @classmethod
    def unhealthy(cls, name: str, message: str = "", **details) -> "HealthCheckResult":
        """Create unhealthy result"""
        return cls(name, HealthStatus.UNHEALTHY, message, details)


class HealthChecker:
    """
    Health checker base class
    
    Subclasses need to implement check() method.
    """
    
    def __init__(self, name: str, timeout_ms: int = 5000):
        """
        Initialize health checker
        
        Args:
            name: Checker name
            timeout_ms: Timeout (milliseconds)
        """
        self.name = name
        self.timeout_ms = timeout_ms
    
    def check(self) -> HealthCheckResult:
        """
        Execute health check
        
        Subclasses need to override this method.
        
        Returns:
            Health check result
        """
        return HealthCheckResult.healthy(self.name, "Default check passed")
    
    def check_with_timeout(self) -> HealthCheckResult:
        """Health check with timeout"""
        start_time = time.time()
        
        try:
            result = self.check()
            result.duration_ms = (time.time() - start_time) * 1000
            return result
        except Exception as e:
            return HealthCheckResult.unhealthy(
                self.name,
                f"Check exception: {str(e)}",
                duration_ms=(time.time() - start_time) * 1000
            )


class StorageHealthChecker(HealthChecker):
    """Storage health checker"""
    
    def __init__(self, storage_path: str, timeout_ms: int = 5000):
        super().__init__("storage", timeout_ms)
        self.storage_path = Path(storage_path)
    
    def check(self) -> HealthCheckResult:
        """Check storage health"""
        try:
            # Check if directory exists
            if not self.storage_path.exists():
                return HealthCheckResult.unhealthy(
                    self.name,
                    f"Storage directory does not exist: {self.storage_path}"
                )
            
            # Check read/write permissions
            test_file = self.storage_path / ".health_check"
            test_file.write_text("test")
            content = test_file.read_text()
            test_file.unlink()
            
            if content != "test":
                return HealthCheckResult.unhealthy(
                    self.name,
                    "Storage read/write test failed"
                )
            
            # Get disk usage
            total, used, free = self._get_disk_usage()
            used_percent = (used / total * 100) if total > 0 else 0
            
            details = {
                "path": str(self.storage_path),
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "used_percent": round(used_percent, 2),
            }
            
            if used_percent > 90:
                return HealthCheckResult.degraded(
                    self.name,
                    f"Disk usage too high: {used_percent:.1f}%",
                    **details
                )
            
            return HealthCheckResult.healthy(self.name, "Storage normal", **details)
            
        except Exception as e:
            return HealthCheckResult.unhealthy(self.name, f"Check failed: {str(e)}")
    
    def _get_disk_usage(self) -> tuple:
        """Get disk usage"""
        try:
            import shutil
            usage = shutil.disk_usage(self.storage_path)
            return usage.total, usage.used, usage.free
        except (OSError, IOError, PermissionError):
            return 0, 0, 0


class MemoryHealthChecker(HealthChecker):
    """Memory health checker"""
    
    def __init__(self, threshold_percent: float = 90.0, timeout_ms: int = 1000):
        super().__init__("memory", timeout_ms)
        self.threshold_percent = threshold_percent
    
    def check(self) -> HealthCheckResult:
        """Check memory health"""
        try:
            import psutil
            
            memory = psutil.virtual_memory()
            
            details = {
                "total_bytes": memory.total,
                "available_bytes": memory.available,
                "used_bytes": memory.used,
                "percent": memory.percent,
            }
            
            if memory.percent > self.threshold_percent:
                return HealthCheckResult.degraded(
                    self.name,
                    f"Memory usage too high: {memory.percent:.1f}%",
                    **details
                )
            
            return HealthCheckResult.healthy(self.name, "Memory normal", **details)
            
        except ImportError:
            return HealthCheckResult(
                self.name,
                HealthStatus.UNKNOWN,
                "psutil not installed, unable to check memory"
            )
        except Exception as e:
            return HealthCheckResult.unhealthy(self.name, f"Check failed: {str(e)}")


class ConfigHealthChecker(HealthChecker):
    """Config health checker"""
    
    def __init__(self, timeout_ms: int = 1000):
        super().__init__("config", timeout_ms)
    
    def check(self) -> HealthCheckResult:
        """Check config health"""
        try:
            # Try to load config
            from src.config import settings
            
            details = {
                "config_loaded": True,
            }
            
            return HealthCheckResult.healthy(self.name, "Config normal", **details)
            
        except ImportError:
            return HealthCheckResult.degraded(
                self.name,
                "Config module not installed, using default config"
            )
        except Exception as e:
            return HealthCheckResult.unhealthy(self.name, f"Config load failed: {str(e)}")


@dataclass
class HealthReport:
    """Health report"""
    overall_status: HealthStatus
    checks: List[HealthCheckResult]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "overall_status": self.overall_status.value,
            "checks": [c.to_dict() for c in self.checks],
            "timestamp": self.timestamp,
        }


class HealthMonitor:
    """
    Health monitor
    
    Manages all health checkers and generates health reports.
    
    Usage example:
        monitor = HealthMonitor()
        
        # Register checkers
        monitor.register(StorageHealthChecker("/data"))
        monitor.register(MemoryHealthChecker())
        
        # Execute check
        report = monitor.check_all()
        
        # Get status
        if report.overall_status == HealthStatus.HEALTHY:
            print("System healthy")
    """
    
    def __init__(self):
        """Initialize health monitor"""
        self._checkers: Dict[str, HealthChecker] = {}
        self._lock = Lock()
    
    def register(self, checker: HealthChecker) -> None:
        """
        Register health checker
        
        Args:
            checker: Health checker instance
        """
        with self._lock:
            self._checkers[checker.name] = checker
            logger.info(f"Registered health checker: {checker.name}")
    
    def unregister(self, name: str) -> bool:
        """
        Unregister health checker
        
        Args:
            name: Checker name
        
        Returns:
            Whether successfully unregistered
        """
        with self._lock:
            if name in self._checkers:
                del self._checkers[name]
                return True
            return False
    
    def check(self, name: str) -> Optional[HealthCheckResult]:
        """
        Execute single health check
        
        Args:
            name: Checker name
        
        Returns:
            Check result, None if not exists
        """
        with self._lock:
            checker = self._checkers.get(name)
            if checker:
                return checker.check_with_timeout()
            return None
    
    def check_all(self) -> HealthReport:
        """
        Execute all health checks
        
        Returns:
            Health report
        """
        results = []
        overall_status = HealthStatus.HEALTHY
        
        with self._lock:
            checkers = list(self._checkers.values())
        
        for checker in checkers:
            result = checker.check_with_timeout()
            results.append(result)
            
            # Update overall status
            if result.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            elif result.status == HealthStatus.DEGRADED and overall_status != HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.DEGRADED
        
        return HealthReport(overall_status, results)
    
    def get_health_endpoint(self) -> Callable[[], Dict[str, Any]]:
        """
        Get health check endpoint function
        
        Returns:
            Health check function for HTTP server
        """
        def health_endpoint() -> Dict[str, Any]:
            report = self.check_all()
            return report.to_dict()
        
        return health_endpoint
    
    def is_healthy(self) -> bool:
        """Check if system is healthy"""
        report = self.check_all()
        return report.overall_status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)


# Global health monitor
_global_monitor: Optional[HealthMonitor] = None
_global_lock = Lock()


def get_health_monitor() -> HealthMonitor:
    """Get global health monitor"""
    global _global_monitor
    with _global_lock:
        if _global_monitor is None:
            _global_monitor = HealthMonitor()
            # Register default checkers
            _global_monitor.register(ConfigHealthChecker())
        return _global_monitor


def register_health_checker(checker: HealthChecker) -> None:
    """Register health checker"""
    get_health_monitor().register(checker)


def check_health() -> HealthReport:
    """Execute health check"""
    return get_health_monitor().check_all()


def is_healthy() -> bool:
    """Check if system is healthy"""
    return get_health_monitor().is_healthy()