"""
Skill system base classes

Provides the base framework for all Skills: configuration, registration, output structure.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Type
import re


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

    def format_data(self, data: dict, action: str, symbol: str) -> str:
        return ""

    def infer_actions(self, aspect: str, symbol: str) -> List[str]:
        manifest = getattr(self, '_manifest', None)
        if manifest and manifest.action_rules:
            all_actions = []
            matched = False
            for rule in manifest.action_rules:
                if not re.match(rule.pattern, symbol):
                    continue
                if rule.aspect_keywords:
                    aspect_lower = (aspect or "").lower()
                    if any(kw.lower() in aspect_lower for kw in rule.aspect_keywords):
                        all_actions.extend(rule.actions)
                        matched = True
                    continue
                if not matched:
                    return rule.actions
            if matched:
                return list(dict.fromkeys(all_actions))
        return ["default"]

    def resolve_identifier(self, topic: str, aspect: str) -> Optional[str]:
        manifest = getattr(self, '_manifest', None)
        if manifest and manifest.supports_topic_fallback and manifest.topic_fallback_pattern:
            m = re.search(manifest.topic_fallback_pattern, topic)
            if m:
                return m.group(0)
        return None


class InstructionSkill(Skill):
    """Pure instruction Skill — no Python execution, provides SKILL.md instructions for AI."""

    def __init__(self, manifest):
        self._manifest = manifest
        self._name = manifest.name
        self._description = manifest.description
        self.config = SkillConfig(name=manifest.name, version=manifest.version)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    async def execute(self, **kwargs) -> Dict[str, Any]:
        return {
            "success": True,
            "data": {"instructions": self._manifest.instructions},
            "content": self._manifest.instructions[:500],
            "source": self.name,
        }


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
