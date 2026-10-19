# -*- coding: utf-8 -*-
"""
Startup Performance Optimization Module
========================================

Phase 4 Week 18: Performance Optimization - Startup Performance

Features:
- Module lazy loading - defer loading of non-critical modules
- Config warmup - cache commonly used configs
- Startup profiling - identify startup bottlenecks
- Optimization suggestions - auto-generate optimization recommendations

Core classes:
- StartupProfiler - startup profiler
- LazyLoader - lazy loader
- StartupOptimizer - startup optimizer
"""

import os
import time
import sys
import importlib
import threading
from typing import Dict, Any, Optional, List, Callable, Set
from datetime import datetime
from dataclasses import dataclass, field
from threading import Lock
import logging

logger = logging.getLogger(__name__)


@dataclass
class StartupPhase:
    """Startup phase"""
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    
    def complete(self) -> None:
        """Complete phase"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time


class StartupProfiler:
    """
    Startup Profiler
    
    Analyzes time spent in each startup phase.
    
    Usage example:
        profiler = StartupProfiler()
        
        with profiler.phase("config_loading"):
            load_config()
        
        with profiler.phase("database_init"):
            init_database()
        
        report = profiler.get_report()
    """
    
    def __init__(self):
        """Initialize startup profiler"""
        self._phases: List[StartupPhase] = []
        self._current_phase: Optional[StartupPhase] = None
        self._lock = Lock()
        self._start_time = time.time()
    
    def phase(self, name: str) -> "PhaseContext":
        """
        Start a phase
        
        Args:
            name: Phase name
        
        Returns:
            Context manager
        """
        return PhaseContext(self, name)
    
    def start_phase(self, name: str, **details) -> None:
        """Start phase"""
        with self._lock:
            phase = StartupPhase(
                name=name,
                start_time=time.time(),
                details=details
            )
            self._phases.append(phase)
            self._current_phase = phase
    
    def end_phase(self, name: str) -> None:
        """End phase"""
        with self._lock:
            for phase in reversed(self._phases):
                if phase.name == name and phase.end_time is None:
                    phase.complete()
                    break
    
    def get_phases(self) -> List[Dict[str, Any]]:
        """Get all phases"""
        with self._lock:
            return [
                {
                    "name": p.name,
                    "duration": p.duration,
                    "details": p.details,
                }
                for p in self._phases
            ]
    
    def get_total_duration(self) -> float:
        """Get total duration"""
        return time.time() - self._start_time
    
    def get_report(self) -> Dict[str, Any]:
        """Get startup report"""
        with self._lock:
            total = self.get_total_duration()
            
            # Sort by duration
            sorted_phases = sorted(
                self._phases,
                key=lambda p: p.duration,
                reverse=True
            )
            
            # Identify bottlenecks
            bottlenecks = [
                p.name for p in sorted_phases
                if p.duration > total * 0.1  # Exceeds 10% of total time
            ]
            
            return {
                "total_duration": round(total, 3),
                "phases": [
                    {
                        "name": p.name,
                        "duration": round(p.duration, 3),
                        "percent": round(p.duration / total * 100, 1) if total > 0 else 0,
                    }
                    for p in self._phases
                ],
                "bottlenecks": bottlenecks,
                "recommendations": self._generate_recommendations(sorted_phases),
            }
    
    def _generate_recommendations(self, phases: List[StartupPhase]) -> List[str]:
        """Generate optimization recommendations"""
        recommendations = []
        
        for phase in phases:
            if phase.duration > 1.0:
                recommendations.append(
                    f"Phase '{phase.name}' took {phase.duration:.2f}s, consider optimization or lazy loading"
                )
        
        if not recommendations:
            recommendations.append("Startup performance is good, no optimization needed")
        
        return recommendations


class PhaseContext:
    """Phase context manager"""
    
    def __init__(self, profiler: StartupProfiler, name: str):
        self.profiler = profiler
        self.name = name
    
    def __enter__(self):
        self.profiler.start_phase(self.name)
        return self
    
    def __exit__(self, *args):
        self.profiler.end_phase(self.name)


class LazyLoader:
    """
    Lazy Loader
    
    Defers module loading until first use.
    
    Usage example:
        # Instead of direct import
        # from heavy_module import HeavyClass
        
        # Use lazy loading
        HeavyClass = LazyLoader("heavy_module", "HeavyClass")
        
        # Loaded on first use
        obj = HeavyClass()  # Import happens here
    """
    
    def __init__(self, module_name: str, attr_name: Optional[str] = None):
        """
        Initialize lazy loader
        
        Args:
            module_name: Module name
            attr_name: Attribute name (optional)
        """
        self.module_name = module_name
        self.attr_name = attr_name
        self._module = None
        self._loaded = False
        self._lock = Lock()
    
    def _load(self) -> Any:
        """Load module"""
        with self._lock:
            if self._loaded:
                return self._module
            
            start_time = time.time()
            module = importlib.import_module(self.module_name)
            
            if self.attr_name:
                self._module = getattr(module, self.attr_name)
            else:
                self._module = module
            
            self._loaded = True
            duration = time.time() - start_time
            
            logger.debug(f"Lazy loaded module {self.module_name} in {duration:.3f}s")
            return self._module
    
    def __getattr__(self, name: str) -> Any:
        """Get attribute"""
        if not self._loaded:
            self._load()
        if self._module is None:
            raise ImportError(f"Module {self.module_name} failed to load")
        return getattr(self._module, name)
    
    def __call__(self, *args, **kwargs) -> Any:
        """Call"""
        if not self._loaded:
            self._load()
        if self._module is None:
            raise ImportError(f"Module {self.module_name} failed to load")
        if callable(self._module):
            return self._module(*args, **kwargs)
        raise TypeError(f"{self.module_name} is not callable")


class StartupOptimizer:
    """
    Startup Optimizer
    
    Manages startup optimization and lazy loading.
    """
    
    _instance: Optional["StartupOptimizer"] = None
    _lock = Lock()
    
    def __init__(self):
        """Initialize startup optimizer"""
        self._profiler = StartupProfiler()
        self._lazy_modules: Dict[str, LazyLoader] = {}
        self._preload_functions: List[Callable] = []
        self._optimized = False
    
    @classmethod
    def get_instance(cls) -> "StartupOptimizer":
        """Get singleton instance"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    def register_lazy(
        self,
        name: str,
        module_name: str,
        attr_name: Optional[str] = None
    ) -> LazyLoader:
        """
        Register lazy loading module
        
        Args:
            name: Registration name
            module_name: Module name
            attr_name: Attribute name
        
        Returns:
            Lazy loader
        """
        loader = LazyLoader(module_name, attr_name)
        self._lazy_modules[name] = loader
        logger.debug(f"Registered lazy module: {name} -> {module_name}")
        return loader
    
    def get_lazy(self, name: str) -> Optional[LazyLoader]:
        """Get lazy loaded module"""
        return self._lazy_modules.get(name)
    
    def register_preload(self, func: Callable) -> None:
        """Register preload function"""
        self._preload_functions.append(func)
    
    def preload(self) -> None:
        """Execute preload"""
        if self._optimized:
            return
        
        with self._profiler.phase("preload"):
            for func in self._preload_functions:
                try:
                    func()
                except Exception as e:
                    logger.warning(f"Preload failed: {e}")
        
        self._optimized = True
    
    def optimize_startup(self) -> Dict[str, Any]:
        """
        Optimize startup
        
        Returns:
            Startup report
        """
        # Preload
        self.preload()
        
        # Get report
        return self._profiler.get_report()
    
    def get_profiler(self) -> StartupProfiler:
        """Get startup profiler"""
        return self._profiler


# Global startup profiler
_global_profiler: Optional[StartupProfiler] = None


def get_startup_profiler() -> StartupProfiler:
    """Get startup profiler"""
    global _global_profiler
    if _global_profiler is None:
        _global_profiler = StartupProfiler()
    return _global_profiler


def startup_phase(name: str) -> PhaseContext:
    """Startup phase context (convenience function)"""
    return get_startup_profiler().phase(name)


def get_startup_report() -> Dict[str, Any]:
    """Get startup report"""
    return get_startup_profiler().get_report()


def lazy_import(module_name: str, attr_name: Optional[str] = None) -> LazyLoader:
    """Lazy load import (convenience function)"""
    return LazyLoader(module_name, attr_name)


# Preload common modules
def preload_common_modules() -> None:
    """Preload common modules"""
    common_modules = [
        "json",
        "os",
        "pathlib",
        "datetime",
    ]
    
    for module in common_modules:
        try:
            importlib.import_module(module)
        except ImportError:
            pass
