"""
Backend Factory

Used to create and register survey backend instances.
"""

import asyncio
import importlib
import logging
import threading
from typing import Dict, List, Any, Type, Optional
from .base import SurveyBackend

logger = logging.getLogger(__name__)


class BackendFactory:
    """Backend Factory - creates and manages survey backend instances."""

    _backends: Dict[str, Type[SurveyBackend]] = {}
    _instances: Dict[str, SurveyBackend] = {}
    _lock = threading.Lock()

    @classmethod
    def register(
            cls,
            backend_type: str,
            backend_class: Type[SurveyBackend]) -> None:
        """Register a backend class."""
        with cls._lock:
            cls._backends[backend_type] = backend_class

    @classmethod
    def create(cls, backend_type: str, **kwargs) -> SurveyBackend:
        """Create a backend instance."""
        with cls._lock:
            if backend_type not in cls._backends:
                raise ValueError(f"Unknown backend type: {backend_type}")
            backend_class = cls._backends[backend_type]
        return backend_class(**kwargs)

    @classmethod
    def get_or_create(cls, backend_type: str, **kwargs) -> SurveyBackend:
        """Get or create a backend instance (singleton)."""
        cache_key = f"{backend_type}:{hash(frozenset(kwargs.items()))}"
        with cls._lock:
            if cache_key not in cls._instances:
                if backend_type not in cls._backends:
                    raise ValueError(f"Unknown backend type: {backend_type}")
                backend_class = cls._backends[backend_type]
                cls._instances[cache_key] = backend_class(**kwargs)
            return cls._instances[cache_key]

    @classmethod
    def list_available(cls) -> List[Dict[str, Any]]:
        """List all available backends."""
        backends = []
        for backend_type, backend_class in cls._backends.items():
            try:
                backends.append({
                    "type": backend_type,
                    "name": getattr(backend_class, 'backend_name', backend_type),
                    "capabilities": getattr(backend_class, 'capabilities', {}),
                })
            except Exception:
                backends.append({
                    "type": backend_type,
                    "name": backend_type,
                    "capabilities": {},
                })
        return backends

    @classmethod
    def get_backend_types(cls) -> List[str]:
        """Get all registered backend types."""
        return list(cls._backends.keys())

    @classmethod
    def is_registered(cls, backend_type: str) -> bool:
        """Check if a backend type is registered."""
        return backend_type in cls._backends

    @classmethod
    def clear_instances(cls) -> None:
        """Clear all cached instances."""
        with cls._lock:
            cls._instances.clear()

    @classmethod
    async def close_all(cls) -> None:
        """Close all backend instances."""
        with cls._lock:
            for cache_key, instance in list(cls._instances.items()):
                try:
                    if hasattr(
                            instance, 'close_client') and callable(
                            instance.close_client):
                        await instance.close_client()
                        logger.debug(f"Closed backend: {cache_key}")
                except Exception as e:
                    logger.warning(f"Failed to close {cache_key}: {e}")
            cls._instances.clear()
            logger.info("All backends closed")


def _auto_register():
    """Auto-register all built-in backends at module load time."""
    backends = [
        ("mock", "mock_backend", "MockSurveyBackend"),
        ("api_tencent", "tencent_survey", "TencentSurveyBackend"),
        ("ai_simulation", "ai_simulation", "AISimulationBackend"),
    ]
    pkg = __package__ or "src.survey.backends"
    for name, mod_name, cls_name in backends:
        try:
            full_mod = f"{pkg}.{mod_name}"
            mod = importlib.import_module(full_mod)
            BackendFactory.register(name, getattr(mod, cls_name))
        except (ImportError, AttributeError) as e:
            logger.debug(f"Backend {name} registration failed: {e}")


_auto_register()
