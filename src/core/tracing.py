# -*- coding: utf-8 -*-
"""
Performance Tracing Module
=========================

Phase 4 Week 17: Observability - Performance Tracing

Features:
- Trace ID generation and propagation - distributed tracing identifier
- Span management - tracing unit creation and management
- Performance bottleneck analysis - identify slow operations
- Trace data export - support for exporting trace data
- Decorator support - convenient function call tracing

Core classes:
- TraceID - Trace identifier
- Span - Trace unit
- Tracer - Tracer
- TraceContext - Trace context
"""

import os
import time
import json
import uuid
import functools
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, Union
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
import logging

logger = logging.getLogger(__name__)


class SpanKind(Enum):
    """Span type enumeration"""
    INTERNAL = "internal"     # Internal operation
    SERVER = "server"         # Server side
    CLIENT = "client"         # Client side
    PRODUCER = "producer"     # Producer
    CONSUMER = "consumer"     # Consumer


class SpanStatus(Enum):
    """Span status enumeration"""
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class TraceID:
    """Trace identifier"""
    value: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value

    @classmethod
    def generate(cls) -> "TraceID":
        """Generate new Trace ID"""
        return cls()

    @classmethod
    def from_string(cls, value: str) -> "TraceID":
        """Create from string"""
        return cls(value)


@dataclass
class SpanID:
    """Span identifier"""
    value: str = field(default_factory=lambda: uuid.uuid4().hex[:16])

    def __str__(self) -> str:
        return self.value

    @classmethod
    def generate(cls) -> "SpanID":
        """Generate new Span ID"""
        return cls()


@dataclass
class Span:
    """
    Trace Unit

    Represents an operation or work unit.

    Usage example:
        span = Span("database_query")
        span.set_attribute("query", "SELECT * FROM users")
        span.end()
    """
    name: str
    trace_id: TraceID = field(default_factory=TraceID.generate)
    span_id: SpanID = field(default_factory=SpanID.generate)
    parent_id: Optional[SpanID] = None
    kind: SpanKind = SpanKind.INTERNAL
    status: SpanStatus = SpanStatus.UNSET
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    _lock: Lock = field(default_factory=Lock, repr=False)
    
    def set_attribute(self, key: str, value: Any) -> "Span":
        """
        Set attribute

        Args:
            key: Attribute name
            value: Attribute value

        Returns:
            Span instance (supports chaining)
        """
        with self._lock:
            self.attributes[key] = value
        return self

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> "Span":
        """
        Add event

        Args:
            name: Event name
            attributes: Event attributes

        Returns:
            Span instance (supports chaining)
        """
        with self._lock:
            self.events.append({
                "name": name,
                "timestamp": datetime.now().isoformat(),
                "attributes": attributes or {},
            })
        return self

    def set_status(self, status: SpanStatus, description: str = "") -> "Span":
        """
        Set status

        Args:
            status: Status
            description: Description

        Returns:
            Span instance (supports chaining)
        """
        with self._lock:
            self.status = status
            if description:
                self.attributes["status_description"] = description
        return self

    def record_exception(self, exception: Exception) -> "Span":
        """
        Record exception

        Args:
            exception: Exception object

        Returns:
            Span instance (supports chaining)
        """
        with self._lock:
            self.status = SpanStatus.ERROR
            self.events.append({
                "name": "exception",
                "timestamp": datetime.now().isoformat(),
                "attributes": {
                    "exception.type": type(exception).__name__,
                    "exception.message": str(exception),
                },
            })
        return self

    def end(self) -> None:
        """End Span"""
        with self._lock:
            if self.end_time is None:
                self.end_time = time.time()

    @property
    def duration_ms(self) -> float:
        """Get duration (milliseconds)"""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000

    def is_recording(self) -> bool:
        """Whether recording"""
        return self.end_time is None

    def __enter__(self) -> "Span":
        """Context manager entry"""
        return self

    def __exit__(self, *args) -> None:
        """Context manager exit"""
        self.end()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "name": self.name,
            "trace_id": str(self.trace_id),
            "span_id": str(self.span_id),
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "kind": self.kind.value,
            "status": self.status.value,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": self.events,
        }


class Tracer:
    """
    Tracer

    Creates and manages Spans.

    Usage example:
        tracer = Tracer("my_service")

        # Using decorator
        @tracer.trace("operation_name")
        def my_function():
            pass

        # Manual tracing
        with tracer.start_span("database_query") as span:
            span.set_attribute("query", "SELECT * FROM ...")
    """

    def __init__(self, service_name: str, sampler: Optional[Callable[[], bool]] = None):
        """
        Initialize tracer

        Args:
            service_name: Service name
            sampler: Sampler function, returns whether to sample
        """
        self.service_name = service_name
        self.sampler = sampler
        self._spans: List[Span] = []
        self._lock = Lock()
    
    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent: Optional[Span] = None
    ) -> Union[Span, "NoopSpan"]:
        """
        Start new Span

        Args:
            name: Span name
            kind: Span type
            parent: Parent Span

        Returns:
            Span instance
        """
        # Sampling check
        if self.sampler and not self.sampler():
            return NoopSpan(name)

        span = Span(
            name=name,
            kind=kind,
            parent_id=parent.span_id if parent else None,
        )

        if parent:
            span.trace_id = parent.trace_id

        span.set_attribute("service.name", self.service_name)

        with self._lock:
            self._spans.append(span)

        return span

    def trace(self, name: Optional[str] = None) -> Callable:
        """
        Trace decorator

        Args:
            name: Span name (defaults to function name)

        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            span_name = name or func.__name__
            
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with self.start_span(span_name) as span:
                    try:
                        result = func(*args, **kwargs)
                        span.set_status(SpanStatus.OK)
                        return result
                    except Exception as e:
                        span.record_exception(e)
                        raise
            
            return wrapper
        return decorator
    
    def get_spans(self) -> List[Span]:
        """Get all Spans"""
        with self._lock:
            return list(self._spans)

    def export_traces(self) -> List[Dict[str, Any]]:
        """Export all trace data"""
        with self._lock:
            return [span.to_dict() for span in self._spans]

    def clear(self) -> None:
        """Clear all Spans"""
        with self._lock:
            self._spans.clear()


class NoopSpan:
    """No-op Span (used when sampling is disabled)"""

    def __init__(self, name: str):
        self.name = name

    def set_attribute(self, key: str, value: Any) -> "NoopSpan":
        return self

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> "NoopSpan":
        return self

    def set_status(self, status: SpanStatus, description: str = "") -> "NoopSpan":
        return self

    def record_exception(self, exception: Exception) -> "NoopSpan":
        return self

    def end(self) -> None:
        pass

    def __enter__(self) -> "NoopSpan":
        return self

    def __exit__(self, *args) -> None:
        self.end()


class TraceContext:
    """
    Trace Context Management

    Manages the currently active Span.
    """

    _current_span: Optional[Span] = None
    _lock = Lock()

    @classmethod
    def get_current_span(cls) -> Optional[Span]:
        """Get current Span"""
        with cls._lock:
            return cls._current_span

    @classmethod
    def set_current_span(cls, span: Optional[Span]) -> None:
        """Set current Span"""
        with cls._lock:
            cls._current_span = span

    @classmethod
    def get_trace_id(cls) -> Optional[str]:
        """Get current Trace ID"""
        span = cls.get_current_span()
        return str(span.trace_id) if span else None


# Global tracer
_global_tracer: Optional[Tracer] = None
_global_lock = Lock()


def get_tracer(service_name: str = "default") -> Tracer:
    """
    Get global tracer

    Args:
        service_name: Service name

    Returns:
        Tracer instance
    """
    global _global_tracer
    with _global_lock:
        if _global_tracer is None:
            _global_tracer = Tracer(service_name)
        return _global_tracer


def start_span(name: str, kind: SpanKind = SpanKind.INTERNAL) -> Union[Span, "NoopSpan"]:
    """Start new Span (convenience function)"""
    return get_tracer().start_span(name, kind, TraceContext.get_current_span())


def trace(name: Optional[str] = None) -> Callable:
    """Trace decorator (convenience function)"""
    return get_tracer().trace(name)


def get_current_span() -> Optional[Span]:
    """Get current Span"""
    return TraceContext.get_current_span()


def get_trace_id() -> Optional[str]:
    """Get current Trace ID"""
    return TraceContext.get_trace_id()


# Performance analysis tools
class PerformanceAnalyzer:
    """Performance Analyzer"""

    def __init__(self, tracer: Optional[Tracer] = None):
        self.tracer = tracer or get_tracer()
        self._slow_threshold_ms = 1000.0  # Slow operation threshold

    def set_slow_threshold(self, threshold_ms: float) -> None:
        """Set slow operation threshold"""
        self._slow_threshold_ms = threshold_ms

    def find_slow_spans(self) -> List[Dict[str, Any]]:
        """Find slow operations"""
        spans = self.tracer.get_spans()
        slow = []

        for span in spans:
            if span.duration_ms > self._slow_threshold_ms:
                slow.append({
                    "name": span.name,
                    "duration_ms": span.duration_ms,
                    "trace_id": str(span.trace_id),
                    "span_id": str(span.span_id),
                })

        return sorted(slow, key=lambda x: x["duration_ms"], reverse=True)

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics"""
        spans = self.tracer.get_spans()
        
        if not spans:
            return {"total": 0}
        
        durations = [s.duration_ms for s in spans]
        
        return {
            "total": len(spans),
            "avg_duration_ms": sum(durations) / len(durations),
            "max_duration_ms": max(durations),
            "min_duration_ms": min(durations),
            "slow_count": sum(1 for d in durations if d > self._slow_threshold_ms),
        }