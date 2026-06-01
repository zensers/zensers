"""
Skill system base classes

Provides the base framework for all Skills: configuration, registration, output structure.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Type


@dataclass
class SkillConfig:
    """
    Skill configuration

    Attributes:
        name: Skill name
        version: Skill version
        enabled: Whether enabled
        options: Extra configuration options
    """
    name: str
    version: str
    enabled: bool = True
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillOutput:
    """
    Skill output structure

    Attributes:
        success: Whether execution succeeded
        data: Output data
        message: Message
        error: Error message (on failure)
    """
    success: bool
    data: Dict[str, Any]
    message: str = ""
    error: Optional[str] = None


class Skill(ABC):
    """
    Skill abstract base class

    All Skills must inherit this class and implement the execute method.
    """

    def __init__(self, config: Optional[SkillConfig] = None):
        self.config = config or SkillConfig(name=self.name, version="1.0.0")
        self._initialized = True

    @property
    @abstractmethod
    def name(self) -> str:
        """Skill name"""

    @property
    @abstractmethod
    def description(self) -> str:
        """Skill description"""

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute Skill

        Args:
            **kwargs: Skill parameters

        Returns:
            Result dict containing success field
        """

    def is_enabled(self) -> bool:
        """Check if Skill is enabled"""
        return self.config.enabled

    def _success(self, data: Dict[str, Any], message: str = "OK") -> Dict[str, Any]:
        """Build success response"""
        return {"success": True, "message": message, **data}

    def _failure(self, error: str, message: str = "Execution failed") -> Dict[str, Any]:
        """Build failure response"""
        return {"success": False, "message": message, "error": error}


class SkillRegistry:
    """
    Skill registry center

    Manages registration and lookup of all available Skills.
    """

    def __init__(self):
        self._skills: Dict[str, Type[Skill]] = {}

    def register(self, name: str, skill_class: Type[Skill]) -> None:
        """Register Skill"""
        self._skills[name] = skill_class

    def get(self, name: str) -> Optional[Type[Skill]]:
        """Get Skill class"""
        return self._skills.get(name)

    def list_all(self) -> Dict[str, Type[Skill]]:
        """List all registered Skills"""
        return dict(self._skills)

    def unregister(self, name: str) -> bool:
        """Unregister Skill"""
        if name in self._skills:
            del self._skills[name]
            return True
        return False


# Global Skill registry singleton
_global_registry = SkillRegistry()


def get_registry() -> SkillRegistry:
    """Get global registry"""
    return _global_registry
