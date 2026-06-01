"""
Structured Logging Configuration Module
========================================

Provides structured logging functionality, supporting:
1. JSON format output - structured logs for easy parsing and analysis
2. Dynamic log level configuration - supports runtime log level adjustment
3. Log rotation strategy - rotate log files by size/time
4. Context tracing - supports trace_id, span_id propagation
5. Multiple output targets - file, console, custom handlers

Usage:
    from src.core.logging_config import StructuredLoggingConfig
    
    # Create configuration
    config = StructuredLoggingConfig(
        log_dir="logs",
        log_level="INFO",
        json_format=True
    )
    
    # Get logger
    logger = config.get_logger("my.module")
    logger.info("message", extra={"user_id": "123"})
    
    # Set trace context
    config.set_trace_id("trace-001")
    config.set_span_id("span-001")

Thread safety: All operations are thread-safe, supporting concurrent use.
"""

import json
import logging
import logging.handlers
import os
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


# Configuration system (optional integration)
try:
    from src.config import settings
    SETTINGS_AVAILABLE = True
except ImportError:
    SETTINGS_AVAILABLE = False
    settings = None


class StructuredFormatter(logging.Formatter):
    """
    Structured log formatter
    
    Converts log records to JSON format, including:
    - timestamp: Timestamp
    - level: Log level
    - message: Log message
    - logger: Logger name
    - trace_id: Trace ID (if any)
    - span_id: Span ID (if any)
    - Other custom fields
    """
    
    def __init__(
        self,
        json_format: bool = True,
        include_trace: bool = True,
        trace_context: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize formatter
        
        Args:
            json_format: Whether to use JSON format
            include_trace: Whether to include trace info
            trace_context: Trace context dict (trace_id, span_id)
        """
        super().__init__()
        self.json_format = json_format
        self.include_trace = include_trace
        self._trace_context = trace_context or {}
        self._trace_lock = threading.Lock()
    
    def set_trace_context(self, trace_id: Optional[str], span_id: Optional[str]) -> None:
        """Set trace context (thread-safe)"""
        with self._trace_lock:
            self._trace_context["trace_id"] = trace_id
            self._trace_context["span_id"] = span_id
    
    def get_trace_context(self) -> Dict[str, Optional[str]]:
        """Get trace context (thread-safe)"""
        with self._trace_lock:
            return dict(self._trace_context)
    
    def clear_trace_context(self) -> None:
        """Clear trace context"""
        with self._trace_lock:
            self._trace_context = {}
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record
        
        Args:
            record: Log record
            
        Returns:
            Formatted string
        """
        if self.json_format:
            return self._format_json(record)
        else:
            return self._format_text(record)
    
    def _format_json(self, record: logging.LogRecord) -> str:
        """JSON formatting"""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add trace info
        if self.include_trace:
            trace_ctx = self.get_trace_context()
            if trace_ctx.get("trace_id"):
                log_data["trace_id"] = trace_ctx["trace_id"]
            if trace_ctx.get("span_id"):
                log_data["span_id"] = trace_ctx["span_id"]
        
        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            log_data["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        
        # Extract extra fields from record.__dict__ (exclude standard fields)
        standard_fields = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "pathname", "process", "processName", "relativeCreated",
            "thread", "threadName", "exc_info", "exc_text", "stack_info",
            "message", "asctime", "extra"
        }
        
        for key, value in record.__dict__.items():
            if key not in standard_fields:
                try:
                    log_data[key] = value
                except Exception:
                    log_data[key] = str(value)
        
        return json.dumps(log_data, ensure_ascii=False, default=str)
    
    def _format_text(self, record: logging.LogRecord) -> str:
        """Text formatting"""
        # Standard format: time level logger message
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        
        parts = [f"{timestamp} [{record.levelname}] {record.name}: {record.getMessage()}"]
        
        # Add trace info
        if self.include_trace:
            trace_ctx = self.get_trace_context()
            if trace_ctx.get("trace_id"):
                parts.append(f"[trace_id={trace_ctx['trace_id']}]")
            if trace_ctx.get("span_id"):
                parts.append(f"[span_id={trace_ctx['span_id']}]")
        
        # Add exception info
        if record.exc_info:
            parts.append("\n" + self.formatException(record.exc_info))
        
        return " ".join(parts)


class ThreadSafeStreamHandler(logging.StreamHandler):
    """Thread-safe stream handler"""
    
    def __init__(self, stream: Optional[Any] = None):
        super().__init__(stream)
        self._lock = threading.Lock()
    
    def emit(self, record: logging.LogRecord) -> None:
        """Safely emit log"""
        with self._lock:
            super().emit(record)


class ThreadSafeFileHandler(logging.handlers.RotatingFileHandler):
    """Thread-safe file handler (supports size rotation)"""
    
    def __init__(
        self,
        filename: str,
        maxBytes: int = 10 * 1024 * 1024,  # 10MB
        backupCount: int = 5,
        encoding: Optional[str] = 'utf-8'
    ):
        """
        Initialize file handler
        
        Args:
            filename: Log file name
            maxBytes: Maximum file size
            backupCount: Number of backup files
            encoding: File encoding
        """
        # Ensure directory exists
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename, maxBytes=maxBytes, backupCount=backupCount, encoding=encoding)
        self._emit_lock = threading.Lock()
    
    def emit(self, record: logging.LogRecord) -> None:
        """Safely emit log"""
        with self._emit_lock:
            super().emit(record)


class ThreadSafeTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """Thread-safe timed rotating file handler"""
    
    def __init__(
        self,
        filename: str,
        when: str = 'D',
        interval: int = 1,
        backupCount: int = 7,
        encoding: Optional[str] = 'utf-8'
    ):
        """
        Initialize timed rotating handler
        
        Args:
            filename: Log file name
            when: Rotation period type (S seconds, M minutes, H hours, D days, W weeks)
            interval: Interval number
            backupCount: Number of backup files
            encoding: File encoding
        """
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        super().__init__(
            filename, when=when, interval=interval,
            backupCount=backupCount, encoding=encoding
        )
        self._emit_lock = threading.Lock()
    
    def emit(self, record: logging.LogRecord) -> None:
        """Safely emit log"""
        with self._emit_lock:
            super().emit(record)


class StructuredLoggingConfig:
    """
    Structured logging configuration manager
    
    Manages log configuration, handlers, formatters and trace context.
    All operations are thread-safe.
    """
    
    def __init__(
        self,
        log_dir: str = "logs",
        log_file: str = "Zensers.log",
        log_level: str = "INFO",
        json_format: bool = True,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        rotation_type: str = "size",  # size or time
        rotation_interval: str = "D",  # time rotation interval
        outputs: List[str] = ["file"],  # file, console
        custom_handlers: Optional[List[logging.Handler]] = None,
        enable_tracing: bool = True
    ):
        """
        Initialize logging configuration
        
        Args:
            log_dir: Log directory
            log_file: Log file name
            log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            json_format: Whether to use JSON format
            max_bytes: Maximum file size (bytes)
            backup_count: Number of backup files
            rotation_type: Rotation type (size or time)
            rotation_interval: Time rotation interval (S/M/H/D/W)
            outputs: Output target list
            custom_handlers: Custom handler list
            enable_tracing: Whether to enable tracing
        """
        self.log_dir = Path(log_dir)
        self.log_file = log_file
        self._log_level = self._parse_level(log_level)
        self.json_format = json_format
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.rotation_type = rotation_type
        self.rotation_interval = rotation_interval
        self.outputs = outputs
        self.enable_tracing = enable_tracing
        
        # Trace context (thread-safe)
        self._trace_id: Optional[str] = None
        self._span_id: Optional[str] = None
        self._span_stack: List[str] = []
        self._context_lock = threading.Lock()
        
        # Log level lock
        self._level_lock = threading.Lock()
        
        # Logger cache
        self._loggers: Dict[str, logging.Logger] = {}
        self._logger_lock = threading.Lock()
        
        # Handler list
        self._handlers: List[logging.Handler] = []
        self._formatter = self._create_formatter()
        
        # Create handlers
        self._setup_handlers(custom_handlers)
        
        # Create log directory
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def _parse_level(self, level: str) -> int:
        """Parse log level"""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(level.upper(), logging.INFO)
    
    def _create_formatter(self) -> StructuredFormatter:
        """Create formatter"""
        return StructuredFormatter(
            json_format=self.json_format,
            include_trace=self.enable_tracing,
            trace_context={"trace_id": self._trace_id, "span_id": self._span_id}
        )
    
    def _setup_handlers(self, custom_handlers: Optional[List[logging.Handler]]) -> None:
        """Setup handlers"""
        log_path = str(self.log_dir / self.log_file)
        
        # File handler
        if "file" in self.outputs:
            if self.rotation_type == "time":
                file_handler = ThreadSafeTimedRotatingFileHandler(
                    log_path,
                    when=self.rotation_interval,
                    backupCount=self.backup_count
                )
            else:
                file_handler = ThreadSafeFileHandler(
                    log_path,
                    maxBytes=self.max_bytes,
                    backupCount=self.backup_count
                )
            file_handler.setFormatter(self._formatter)
            self._handlers.append(file_handler)
        
        # Console handler
        if "console" in self.outputs:
            console_handler = ThreadSafeStreamHandler(sys.stdout)
            console_handler.setFormatter(self._formatter)
            self._handlers.append(console_handler)
        
        # Custom handlers
        if custom_handlers:
            for handler in custom_handlers:
                handler.setFormatter(self._formatter)
                self._handlers.append(handler)
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Get logger instance
        
        Args:
            name: Logger name
            
        Returns:
            Configured Logger instance
        """
        with self._logger_lock:
            if name in self._loggers:
                return self._loggers[name]
            
            logger = logging.getLogger(name)
            logger.setLevel(self._log_level)
            
            # Clear existing handlers, add new handlers
            logger.handlers = []
            for handler in self._handlers:
                logger.addHandler(handler)
            
            # Prevent propagation to root logger
            logger.propagate = False
            
            self._loggers[name] = logger
            return logger
    
    def configure_logger(self, logger: logging.Logger) -> None:
        """
        Configure existing logger
        
        Args:
            logger: Logger instance to configure
        """
        logger.setLevel(self._log_level)
        logger.handlers = []
        for handler in self._handlers:
            logger.addHandler(handler)
        logger.propagate = False
    
    def set_log_level(self, level: str) -> None:
        """
        Set global log level
        
        Args:
            level: Log level string
        """
        new_level = self._parse_level(level)
        
        with self._level_lock:
            self._log_level = new_level
            
            # Update all existing logger levels
            with self._logger_lock:
                for logger in self._loggers.values():
                    if logger.level != new_level:
                        logger.setLevel(new_level)
            
            # Update handler levels
            for handler in self._handlers:
                handler.setLevel(new_level)
    
    def set_logger_level(self, logger_name: str, level: str) -> None:
        """
        Set specific logger level
        
        Args:
            logger_name: Logger name
            level: Log level string
        """
        new_level = self._parse_level(level)
        
        with self._logger_lock:
            if logger_name in self._loggers:
                self._loggers[logger_name].setLevel(new_level)
            else:
                # Create and set
                logger = logging.getLogger(logger_name)
                logger.setLevel(new_level)
                self._loggers[logger_name] = logger
    
    def get_log_level(self) -> str:
        """
        Get current log level
        
        Returns:
            Log level string
        """
        level_map = {
            logging.DEBUG: "DEBUG",
            logging.INFO: "INFO",
            logging.WARNING: "WARNING",
            logging.ERROR: "ERROR",
            logging.CRITICAL: "CRITICAL",
        }
        return level_map.get(self._log_level, "INFO")
    
    def set_trace_id(self, trace_id: Optional[str]) -> None:
        """
        Set trace ID
        
        Args:
            trace_id: Trace ID, None to clear
        """
        with self._context_lock:
            self._trace_id = trace_id
            self._formatter.set_trace_context(self._trace_id, self._span_id)
    
    def get_trace_id(self) -> Optional[str]:
        """
        Get current trace ID
        
        Returns:
            Trace ID or None
        """
        with self._context_lock:
            return self._trace_id
    
    def set_span_id(self, span_id: Optional[str]) -> None:
        """
        Set Span ID
        
        Args:
            span_id: Span ID, None to clear
        """
        with self._context_lock:
            self._span_id = span_id
            self._formatter.set_trace_context(self._trace_id, self._span_id)
    
    def get_span_id(self) -> Optional[str]:
        """
        Get current Span ID
        
        Returns:
            Span ID or None
        """
        with self._context_lock:
            return self._span_id
    
    def clear_context(self) -> None:
        """Clear trace context"""
        with self._context_lock:
            self._trace_id = None
            self._span_id = None
            self._span_stack = []
            self._formatter.clear_trace_context()
    
    @contextmanager
    def child_span(self, span_id: Optional[str] = None):
        """
        Create child span context
        
        Args:
            span_id: Child span ID, None to auto-generate
            
        Yields:
            Config object (for logging in child span)
        """
        # Save parent span
        parent_span = self._span_id
        
        # Set new span
        child_id = span_id or str(uuid.uuid4())[:8]
        self.set_span_id(child_id)
        
        with self._context_lock:
            self._span_stack.append(parent_span or "")
        
        try:
            yield self
        finally:
            # Restore parent span
            with self._context_lock:
                if self._span_stack:
                    prev_span = self._span_stack.pop()
                    self._span_id = prev_span if prev_span else parent_span
                    self._formatter.set_trace_context(self._trace_id, self._span_id)
    
    def generate_trace_id(self) -> str:
        """
        Generate new trace ID
        
        Returns:
            New trace ID
        """
        return str(uuid.uuid4())
    
    def generate_span_id(self) -> str:
        """
        Generate new Span ID
        
        Returns:
            New Span ID
        """
        return str(uuid.uuid4())[:8]
    
    def shutdown(self) -> None:
        """
        Shutdown logging configuration, cleanup resources
        
        Closes all handlers and releases file handles.
        """
        with self._logger_lock:
            for logger in self._loggers.values():
                for handler in logger.handlers[:]:
                    handler.close()
                    logger.removeHandler(handler)
            self._loggers.clear()
        
        for handler in self._handlers:
            handler.close()
        self._handlers.clear()


def create_logging_config(
    log_dir: str = "logs",
    log_level: str = "INFO",
    json_format: bool = True,
    **kwargs
) -> StructuredLoggingConfig:
    """
    Create logging configuration (convenience function)
    
    Args:
        log_dir: Log directory
        log_level: Log level
        json_format: Whether to use JSON format
        **kwargs: Other parameters
        
    Returns:
        StructuredLoggingConfig instance
    """
    return StructuredLoggingConfig(
        log_dir=log_dir,
        log_level=log_level,
        json_format=json_format,
        **kwargs
    )


# Global default configuration (optional)
_default_config: Optional[StructuredLoggingConfig] = None
_config_lock = threading.Lock()


def get_default_config() -> Optional[StructuredLoggingConfig]:
    """
    Get global default logging configuration
    
    Returns:
        Default configuration or None
    """
    with _config_lock:
        return _default_config


def set_default_config(config: StructuredLoggingConfig) -> None:
    """
    Set global default logging configuration
    
    Args:
        config: Configuration instance
    """
    global _default_config
    with _config_lock:
        _default_config = config


def get_logger(name: str) -> logging.Logger:
    """
    Get logger using default configuration
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    config = get_default_config()
    if config:
        return config.get_logger(name)
    else:
        return logging.getLogger(name)


# ============ Preserve original API for compatibility ============

class TraceContext:
    """
    Trace context management (compatible with old API)
    
    Use global functions to operate trace context:
    - get_trace_context(): Get current trace context
    - set_trace_context(): Set trace context
    - clear_trace_context(): Clear trace context
    """
    
    _current: Optional[Dict[str, Any]] = None
    _lock = threading.Lock()
    
    @classmethod
    def get(cls) -> Optional[Dict[str, Any]]:
        """Get current trace context"""
        with cls._lock:
            return cls._current.copy() if cls._current else None
    
    @classmethod
    def set(cls, trace_id: str, span_id: Optional[str] = None) -> None:
        """Set trace context"""
        with cls._lock:
            cls._current = {
                "trace_id": trace_id,
                "span_id": span_id or str(uuid.uuid4().hex[:16]),
                "timestamp": datetime.now().isoformat(),
            }
    
    @classmethod
    def clear(cls) -> None:
        """Clear trace context"""
        with cls._lock:
            cls._current = None


def get_trace_context() -> Optional[Dict[str, Any]]:
    """Get current trace context (compatible API)"""
    return TraceContext.get()


def set_trace_context(trace_id: str, span_id: Optional[str] = None) -> None:
    """Set trace context (compatible API)"""
    TraceContext.set(trace_id, span_id)


def clear_trace_context() -> None:
    """Clear trace context (compatible API)"""
    TraceContext.clear()


def setup_logging(log_dir: Optional[str] = None, log_level: str = "INFO") -> StructuredLoggingConfig:
    """
    Setup logging system (compatible API)
    
    Args:
        log_dir: Log directory
        log_level: Log level
    
    Returns:
        StructuredLoggingConfig instance
    """
    resolved_log_dir: str = log_dir or "logs"
    if log_dir is None:
        if SETTINGS_AVAILABLE and settings is not None:
            resolved_log_dir = getattr(settings.system, "log_dir", "logs") or "logs"
    
    config = create_logging_config(log_dir=resolved_log_dir, log_level=log_level)
    set_default_config(config)
    return config
