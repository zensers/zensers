# -*- coding: utf-8 -*-
"""
Metrics Collection Module
=========================

Phase 4 Week 17: Observability - Metrics Collection

Features:
- Performance metrics collection - CPU, memory, IO statistics
- Business metrics tracking - task count, success rate, latency distribution
- Metrics aggregation - statistical summary (average, P50, P95, P99)
- Metrics export - support export to Prometheus format
- Metrics registry - unified management of all metrics

Core classes:
- Counter - Counter
- Gauge - Gauge
- Histogram - Histogram
- MetricsRegistry - Metrics registry
"""

import os
import time
import json
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
import logging
import math

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Metric type enumeration"""
    COUNTER = "counter"       # Counter - only increases
    GAUGE = "gauge"           # Gauge - can increase or decrease
    HISTOGRAM = "histogram"   # Histogram - distribution statistics
    SUMMARY = "summary"       # Summary - quantile statistics


@dataclass
class MetricValue:
    """Metric value"""
    value: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """
    Counter
    
    Cumulative value that only increases, like total requests, total errors.
    
    Usage example:
        counter = Counter("requests_total", "Total requests")
        counter.increment()
        counter.increment(5)
    """
    
    def __init__(
        self,
        name: str,
        description: str = "",
        labels: Optional[Dict[str, str]] = None
    ):
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value = 0.0
        self._lock = Lock()
    
    def increment(self, amount: float = 1.0) -> None:
        """Increment count"""
        if amount < 0:
            raise ValueError("Counter can only increase, not decrease")
        with self._lock:
            self._value += amount
    
    def get(self) -> float:
        """Get current value"""
        with self._lock:
            return self._value
    
    def reset(self) -> None:
        """Reset counter"""
        with self._lock:
            self._value = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "name": self.name,
            "type": MetricType.COUNTER.value,
            "description": self.description,
            "value": self._value,
            "labels": self.labels,
        }


class Gauge:
    """
    Gauge
    
    Instantaneous value that can increase or decrease, like current memory usage, active connections.
    
    Usage example:
        gauge = Gauge("memory_usage", "Memory usage")
        gauge.set(1024)
        gauge.increment(100)
        gauge.decrement(50)
    """
    
    def __init__(
        self,
        name: str,
        description: str = "",
        labels: Optional[Dict[str, str]] = None
    ):
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value = 0.0
        self._lock = Lock()
    
    def set(self, value: float) -> None:
        """Set value"""
        with self._lock:
            self._value = value
    
    def increment(self, amount: float = 1.0) -> None:
        """Increase value"""
        with self._lock:
            self._value += amount
    
    def decrement(self, amount: float = 1.0) -> None:
        """Decrease value"""
        with self._lock:
            self._value -= amount
    
    def get(self) -> float:
        """Get current value"""
        with self._lock:
            return self._value
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "name": self.name,
            "type": MetricType.GAUGE.value,
            "description": self.description,
            "value": self._value,
            "labels": self.labels,
        }


class Histogram:
    """
    Histogram
    
    Distribution statistics of observed values, like request latency, response size.
    
    Usage example:
        histogram = Histogram("request_duration", "Request latency", buckets=[0.1, 0.5, 1, 2, 5])
        histogram.observe(0.3)
        histogram.observe(1.5)
    """
    
    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
    
    def __init__(
        self,
        name: str,
        description: str = "",
        buckets: Optional[List[float]] = None,
        labels: Optional[Dict[str, str]] = None
    ):
        self.name = name
        self.description = description
        self.labels = labels or {}
        
        # Ensure buckets are sorted and include +Inf
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        if self.buckets[-1] != float('inf'):
            self.buckets.append(float('inf'))
        
        self._counts: Dict[float, int] = {b: 0 for b in self.buckets}
        self._sum = 0.0
        self._count = 0
        self._lock = Lock()
    
    def observe(self, value: float) -> None:
        """Record observation"""
        with self._lock:
            self._sum += value
            self._count += 1
            
            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[bucket] += 1
    
    def get_sum(self) -> float:
        """Get sum"""
        with self._lock:
            return self._sum
    
    def get_count(self) -> int:
        """Get count"""
        with self._lock:
            return self._count
    
    def get_buckets(self) -> Dict[float, int]:
        """Get bucket counts"""
        with self._lock:
            return self._counts.copy()
    
    def get_percentile(self, p: float) -> float:
        """
        Get percentile
        
        Args:
            p: Percentile (0-100)
        
        Returns:
            Percentile value
        """
        if not (0 <= p <= 100):
            raise ValueError("Percentile must be between 0-100")
        
        with self._lock:
            if self._count == 0:
                return 0.0
            
            target = self._count * p / 100
            cumulative = 0
            
            for bucket in self.buckets:
                cumulative += self._counts[bucket]
                if cumulative >= target:
                    return bucket
            
            return self.buckets[-1]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        with self._lock:
            return {
                "name": self.name,
                "type": MetricType.HISTOGRAM.value,
                "description": self.description,
                "sum": self._sum,
                "count": self._count,
                "buckets": {str(k): v for k, v in self._counts.items()},
                "labels": self.labels,
            }


class MetricsRegistry:
    """
    Metrics registry
    
    Unified management of all metrics.
    
    Usage example:
        registry = MetricsRegistry()
        
        counter = registry.counter("requests_total", "Total requests")
        gauge = registry.gauge("memory_usage", "Memory usage")
        histogram = registry.histogram("latency", "Latency")
        
        # Export metrics
        metrics = registry.export_all()
        prometheus = registry.export_prometheus()
    """
    
    _instance: Optional["MetricsRegistry"] = None
    _lock = Lock()
    
    def __init__(self, namespace: str = ""):
        self.namespace = namespace
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._registry_lock = Lock()
    
    @classmethod
    def get_instance(cls, namespace: str = "") -> "MetricsRegistry":
        """获取单例实例"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(namespace)
            return cls._instance
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """生成指标键"""
        key = name
        if labels:
            label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
            key = f"{name}{{{label_str}}}"
        return key
    
    def counter(
        self,
        name: str,
        description: str = "",
        labels: Optional[Dict[str, str]] = None
    ) -> Counter:
        """
        Get or create counter
        
        Args:
            name: Metric name
            description: Description
            labels: Labels
        
        Returns:
            Counter instance
        """
        key = self._make_key(name, labels)
        with self._registry_lock:
            if key not in self._counters:
                self._counters[key] = Counter(name, description, labels)
            return self._counters[key]
    
    def gauge(
        self,
        name: str,
        description: str = "",
        labels: Optional[Dict[str, str]] = None
    ) -> Gauge:
        """
        Get or create gauge
        
        Args:
            name: Metric name
            description: Description
            labels: Labels
        
        Returns:
            Gauge instance
        """
        key = self._make_key(name, labels)
        with self._registry_lock:
            if key not in self._gauges:
                self._gauges[key] = Gauge(name, description, labels)
            return self._gauges[key]
    
    def histogram(
        self,
        name: str,
        description: str = "",
        buckets: Optional[List[float]] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> Histogram:
        """
        Get or create histogram
        
        Args:
            name: Metric name
            description: Description
            buckets: Bucket boundaries
            labels: Labels
        
        Returns:
            Histogram instance
        """
        key = self._make_key(name, labels)
        with self._registry_lock:
            if key not in self._histograms:
                self._histograms[key] = Histogram(name, description, buckets, labels)
            return self._histograms[key]
    
    def export_all(self) -> Dict[str, Any]:
        """Export all metrics"""
        with self._registry_lock:
            metrics = {}
            
            for key, counter in self._counters.items():
                metrics[key] = counter.to_dict()
            
            for key, gauge in self._gauges.items():
                metrics[key] = gauge.to_dict()
            
            for key, histogram in self._histograms.items():
                metrics[key] = histogram.to_dict()
            
            return metrics
    
    def export_prometheus(self) -> str:
        """Export to Prometheus format"""
        lines = []
        
        with self._registry_lock:
            # 导出计数器
            for counter in self._counters.values():
                lines.append(f"# HELP {counter.name} {counter.description}")
                lines.append(f"# TYPE {counter.name} counter")
                label_str = ""
                if counter.labels:
                    label_str = "{" + ",".join(f'{k}="{v}"' for k, v in counter.labels.items()) + "}"
                lines.append(f"{counter.name}{label_str} {counter.get()}")
            
            # 导出仪表盘
            for gauge in self._gauges.values():
                lines.append(f"# HELP {gauge.name} {gauge.description}")
                lines.append(f"# TYPE {gauge.name} gauge")
                label_str = ""
                if gauge.labels:
                    label_str = "{" + ",".join(f'{k}="{v}"' for k, v in gauge.labels.items()) + "}"
                lines.append(f"{gauge.name}{label_str} {gauge.get()}")
            
            # 导出直方图
            for histogram in self._histograms.values():
                lines.append(f"# HELP {histogram.name} {histogram.description}")
                lines.append(f"# TYPE {histogram.name} histogram")
                
                label_str = ""
                if histogram.labels:
                    label_str = "," + ",".join(f'{k}="{v}"' for k, v in histogram.labels.items())
                
                buckets = histogram.get_buckets()
                for bucket, count in buckets.items():
                    bucket_str = "inf" if bucket == float('inf') else str(bucket)
                    lines.append(f'{histogram.name}_bucket{{le="{bucket_str}"{label_str}}} {count}')
                
                lines.append(f"{histogram.name}_sum{{{label_str[1:]}}} {histogram.get_sum()}")
                lines.append(f"{histogram.name}_count{{{label_str[1:]}}} {histogram.get_count()}")
        
        return "\n".join(lines)
    
    def clear(self) -> None:
        """Clear all metrics"""
        with self._registry_lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


# Convenience functions
def get_registry() -> MetricsRegistry:
    """Get metrics registry"""
    return MetricsRegistry.get_instance()


def counter(name: str, description: str = "") -> Counter:
    """Get counter"""
    return get_registry().counter(name, description)


def gauge(name: str, description: str = "") -> Gauge:
    """Get gauge"""
    return get_registry().gauge(name, description)


def histogram(name: str, description: str = "", buckets: Optional[List[float]] = None) -> Histogram:
    """Get histogram"""
    return get_registry().histogram(name, description, buckets)


# System metrics collector
class SystemMetricsCollector:
    """System metrics collector"""
    
    def __init__(self, registry: Optional[MetricsRegistry] = None):
        self.registry = registry or get_registry()
        
        # System metrics
        self.cpu_usage = self.registry.gauge("system_cpu_usage", "CPU usage")
        self.memory_usage = self.registry.gauge("system_memory_usage", "Memory usage")
        self.memory_percent = self.registry.gauge("system_memory_percent", "Memory usage percentage")
    
    def collect(self) -> None:
        """Collect system metrics"""
        try:
            import psutil
            
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.cpu_usage.set(cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.memory_usage.set(memory.used)
            self.memory_percent.set(memory.percent)
            
        except ImportError:
            logger.warning("psutil not installed, unable to collect system metrics")
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")