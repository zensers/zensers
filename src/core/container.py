"""
Dependency Injection Container
==============================

Provides unified dependency management mechanism, supporting:
1. Singleton registration and resolution
2. Factory function registration
3. Auto dependency injection
4. Lifecycle management

Design doc: docs/KNOWLEDGE_BASE/07_AUDIT/ENGINEERING_FIX_GUIDE.md
"""

from typing import Type, TypeVar, Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import inspect
import logging
import os

logger = logging.getLogger(__name__)

T = TypeVar('T')


class Lifecycle(Enum):
    """Lifecycle types"""
    SINGLETON = "singleton"      # Singleton: globally unique instance
    TRANSIENT = "transient"      # Transient: new instance each time
    SCOPED = "scoped"            # Scoped: unique within same scope


@dataclass
class Registration:
    """Registration info"""
    interface: Type
    implementation: Optional[Type] = None
    factory: Optional[Callable] = None
    instance: Optional[Any] = None
    lifecycle: Lifecycle = Lifecycle.SINGLETON
    dependencies: List[Type] = field(default_factory=list)


class DIContainer:
    """
    Dependency Injection Container
    
    Core features:
    - register_instance: Register created instance
    - register_singleton: Register singleton type
    - register_factory: Register factory function
    - resolve: Resolve dependency
    - inject: Inject dependencies into instance
    
    Usage example:
        container = DIContainer()
        
        # Register instance
        container.register_instance(MessageBus, MessageBus())
        
        # Register singleton type
        container.register_singleton(SkillRegistry, SkillRegistry)
        
        # Register factory
        container.register_factory(AgentFactory, lambda: AgentFactory())
        
        # Resolve dependency
        message_bus = container.resolve(MessageBus)
        
        # Inject dependencies into instance
        agent = MyAgent(agent_id="001")
        container.inject(agent)
    """
    
    def __init__(self):
        self._registrations: Dict[Type, Registration] = {}
        self._singletons: Dict[Type, Any] = {}
        self._scoped_instances: Dict[Type, Any] = {}
        self._resolving_stack: List[Type] = []  # Detect circular dependencies
    
    def register_instance(self, interface: Type[T], instance: T) -> 'DIContainer':
        """
        Register singleton instance
        
        Args:
            interface: Interface type
            instance: Instance object
            
        Returns:
            self (supports chaining)
        """
        self._registrations[interface] = Registration(
            interface=interface,
            instance=instance,
            lifecycle=Lifecycle.SINGLETON
        )
        self._singletons[interface] = instance
        logger.debug(f"Registered instance: {interface.__name__}")
        return self
    
    def register_singleton(
        self, 
        interface: Type[T], 
        implementation: Type[T],
        dependencies: Optional[List[Type]] = None
    ) -> 'DIContainer':
        """
        Register singleton type
        
        Args:
            interface: Interface type
            implementation: Implementation type
            dependencies: Dependency list (optional)
            
        Returns:
            self (supports chaining)
        """
        self._registrations[interface] = Registration(
            interface=interface,
            implementation=implementation,
            lifecycle=Lifecycle.SINGLETON,
            dependencies=dependencies or []
        )
        logger.debug(f"Registered singleton: {interface.__name__} -> {implementation.__name__}")
        return self
    
    def register_transient(
        self, 
        interface: Type[T], 
        implementation: Type[T]
    ) -> 'DIContainer':
        """
        Register transient type (new instance each time)
        
        Args:
            interface: Interface type
            implementation: Implementation type
            
        Returns:
            self (supports chaining)
        """
        self._registrations[interface] = Registration(
            interface=interface,
            implementation=implementation,
            lifecycle=Lifecycle.TRANSIENT
        )
        logger.debug(f"Registered transient: {interface.__name__} -> {implementation.__name__}")
        return self
    
    def register_factory(
        self, 
        interface: Type[T], 
        factory: Callable[[], T]
    ) -> 'DIContainer':
        """
        Register factory function
        
        Args:
            interface: Interface type
            factory: Factory function (no params, returns instance)
            
        Returns:
            self (supports chaining)
        """
        self._registrations[interface] = Registration(
            interface=interface,
            factory=factory,
            lifecycle=Lifecycle.TRANSIENT
        )
        logger.debug(f"Registered factory: {interface.__name__}")
        return self
    
    def has(self, interface: Type) -> bool:
        """
        Check if registered
        
        Args:
            interface: Interface type
            
        Returns:
            Whether registered
        """
        return interface in self._registrations
    
    def resolve(self, interface: Type[T]) -> T:
        """
        Resolve dependency
        
        Args:
            interface: Interface type
            
        Returns:
            Instance object
            
        Raises:
            KeyError: Unregistered interface
            RuntimeError: Circular dependency
        """
        # Check if registered
        if interface not in self._registrations:
            raise KeyError(f"Unregistered interface: {interface.__name__}")
        
        # Detect circular dependency
        if interface in self._resolving_stack:
            chain = " -> ".join(t.__name__ for t in self._resolving_stack)
            raise RuntimeError(f"Circular dependency detected: {chain} -> {interface.__name__}")
        
        reg = self._registrations[interface]
        
        # Singleton instance (already created)
        if reg.instance is not None:
            return reg.instance
        
        # Singleton (cached)
        if reg.lifecycle == Lifecycle.SINGLETON and interface in self._singletons:
            return self._singletons[interface]
        
        # Create instance
        self._resolving_stack.append(interface)
        try:
            instance = self._create_instance(reg)
        finally:
            self._resolving_stack.pop()
        
        # Cache singleton
        if reg.lifecycle == Lifecycle.SINGLETON:
            self._singletons[interface] = instance
        
        return instance
    
    def _create_instance(self, reg: Registration) -> Any:
        """
        Create instance
        
        Args:
            reg: Registration info
            
        Returns:
            Instance object
        """
        # Factory creation
        if reg.factory:
            return reg.factory()
        
        # Type creation
        if reg.implementation:
            return self._create_from_type(reg.implementation)
        
        raise ValueError(f"Unable to create instance: {reg.interface.__name__}")
    
    def _create_from_type(self, cls: Type[T]) -> T:
        """
        Create instance from type, auto-inject dependencies
        
        Args:
            cls: Type
            
        Returns:
            Instance object
        """
        # Get constructor signature
        sig = inspect.signature(cls.__init__)
        kwargs: Dict[str, Any] = {}
        
        for name, param in sig.parameters.items():
            if name == 'self':
                continue
            
            # Skip params without type annotation
            if param.annotation == inspect.Parameter.empty:
                continue
            
            # Skip *args and **kwargs
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            
            # Try to resolve dependency
            try:
                dependency = self.resolve(param.annotation)
                kwargs[name] = dependency
                logger.debug(f"Injected dependency: {cls.__name__}.{name} <- {param.annotation.__name__}")
            except KeyError:
                # Optional dependency, check if has default value
                if param.default == inspect.Parameter.empty:
                    logger.debug(f"Unable to resolve required dependency: {cls.__name__}.{name} ({param.annotation.__name__})")
                # Has default value, skip
        
        return cls(**kwargs)
    
    def inject(self, instance: Any) -> None:
        """
        Inject dependencies into instance
        
        Auto-detect instance attributes and inject registered dependencies.
        Mainly used for injecting communication capabilities (MessageBus, SharedMemory).
        
        Args:
            instance: Target instance
        """
        # Inject MessageBus
        if hasattr(instance, '_message_bus') and instance._message_bus is None:
            try:
                from src.core.communication import MessageBus
                if self.has(MessageBus):
                    instance._message_bus = self.resolve(MessageBus)
                    logger.debug(f"Injected MessageBus -> {instance.__class__.__name__}")
            except ImportError:
                pass
        
        # Inject SharedMemory
        if hasattr(instance, '_shared_memory') and instance._shared_memory is None:
            try:
                from src.core.communication import SharedMemory
                if self.has(SharedMemory):
                    instance._shared_memory = self.resolve(SharedMemory)
                    logger.debug(f"Injected SharedMemory -> {instance.__class__.__name__}")
            except ImportError:
                pass
        
        # Inject SkillRegistry
        if hasattr(instance, '_skill_registry') and instance._skill_registry is None:
            try:
                from src.skills.registry import SkillRegistry
                if self.has(SkillRegistry):
                    instance._skill_registry = self.resolve(SkillRegistry)
                    logger.debug(f"Injected SkillRegistry -> {instance.__class__.__name__}")
            except ImportError:
                pass
    
    def clear(self) -> None:
        """Clear all registrations"""
        self._registrations.clear()
        self._singletons.clear()
        self._scoped_instances.clear()
        logger.debug("Container cleared")
    
    def get_registrations(self) -> Dict[str, str]:
        """
        Get all registration info
        
        Returns:
            {interface_name: implementation_name/instance/factory}
        """
        result = {}
        for interface, reg in self._registrations.items():
            if reg.instance:
                result[interface.__name__] = f"instance:{reg.instance.__class__.__name__}"
            elif reg.implementation:
                result[interface.__name__] = f"type:{reg.implementation.__name__}"
            elif reg.factory:
                result[interface.__name__] = "factory"
        return result


# ============================================================================
# Global Container Instance
# ============================================================================

_container: Optional[DIContainer] = None


def get_container() -> DIContainer:
    """
    Get global container instance
    
    Returns:
        DIContainer instance
    """
    global _container
    if _container is None:
        _container = DIContainer()
    return _container


def reset_container() -> None:
    """Reset global container"""
    global _container
    _container = None


def configure_container(
    message_bus: Optional[Any] = None,
    shared_memory: Optional[Any] = None,
    skill_registry: Optional[Any] = None,
) -> DIContainer:
    """
    Configure default container
    
    Register core components:
    - MessageBus
    - SharedMemory
    - SkillRegistry
    
    Args:
        message_bus: MessageBus instance (optional, default creates new instance)
        shared_memory: SharedMemory instance (optional, default creates new instance)
        skill_registry: SkillRegistry instance (optional, default creates new instance)
        
    Returns:
        Configured DIContainer
    """
    container = DIContainer()
    
    # Register communication components
    try:
        from src.core.communication import MessageBus, SharedMemory
        
        if message_bus:
            container.register_instance(MessageBus, message_bus)
        else:
            container.register_singleton(MessageBus, MessageBus)
        
        if shared_memory:
            container.register_instance(SharedMemory, shared_memory)
        else:
            container.register_singleton(SharedMemory, SharedMemory)
            
    except ImportError as e:
        logger.warning(f"Unable to import communication components: {e}")
    
    # Register SkillRegistry
    try:
        from src.skills.registry import SkillRegistry
        
        if skill_registry:
            container.register_instance(SkillRegistry, skill_registry)
        else:
            container.register_singleton(SkillRegistry, SkillRegistry)
            
    except ImportError as e:
        logger.warning(f"Unable to import SkillRegistry: {e}")
    
    # Register KnowledgeManager (memory system)
    try:
        from src.core.memory import KnowledgeManager
        from src.core.memory.config import KnowledgeConfig
        config = KnowledgeConfig.from_env()
        user_id = os.getenv("DEFAULT_USER_ID", "default")
        container.register_instance(KnowledgeManager, KnowledgeManager(
            user_id=user_id,
            config=config
        ))
    except Exception as e:
        logger.warning(f"KnowledgeManager not available: {e}")

    # Update global container
    global _container
    _container = container
    
    logger.info(f"Container configured: {len(container._registrations)} registrations")
    return container


# ============================================================================
# Decorators
# ============================================================================

def injectable(cls: Type[T]) -> Type[T]:
    """
    Injectable decorator
    
    Mark class as injectable, auto-add inject method.
    
    Usage example:
        @injectable
        class MyAgent:
            _message_bus: Optional[MessageBus] = None
            _shared_memory: Optional[SharedMemory] = None
        
        agent = MyAgent()
        get_container().inject(agent)
    """
    original_init = cls.__init__
    
    def new_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        # Auto inject
        try:
            container = get_container()
            if container._registrations:  # Only inject when container has registrations
                container.inject(self)
        except Exception as e:
            logger.debug(f"Auto injection failed: {e}")
    
    cls.__init__ = new_init
    return cls
