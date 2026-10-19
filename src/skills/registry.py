"""
Skill Registry

Unified management of registration, discovery, and execution of all Skills.
Supports LangChain Tools auto-discovery and custom Skill registration.

Usage:
    from src.skills.registry import SkillRegistry
    
    registry = SkillRegistry()
    
    # Auto-discover LangChain Tools
    registry.auto_discover_langchain_tools()
    
    # Get a Skill
    skill = registry.get("lc_tavily_search")
    
    # Execute a Skill
    result = await skill.execute(query="AI market")
"""

from typing import Dict, List, Optional, Type, Any, Callable
from dataclasses import dataclass
import importlib
import pkgutil
import logging

from .base import Skill, SkillConfig
from .adapters import LangChainToolSkill, LangChainAdapter

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    """Skill metadata information"""
    name: str
    description: str
    skill_type: str  # "builtin", "langchain", "custom"
    enabled: bool
    config: Optional[SkillConfig] = None


class SkillRegistry:
    """
    Skill Registry
    
    Unified management of all Skills, including:
    - Custom Skill registration
    - LangChain Tools auto-discovery and wrapping
    - Skill metadata querying
    - Batch execution and discovery
    
    Attributes:
        _skills: Dictionary of registered Skill instances
        _adapter: LangChain adapter instance
    """
    
    def __init__(self):
        """Initialize the registry"""
        self._skills: Dict[str, Skill] = {}
        self._adapter = LangChainAdapter()
        self._factories: Dict[str, Callable[[], Skill]] = {}
        self._manifests: Dict[str, Any] = {}
    
    def register(self, skill: Skill, name: Optional[str] = None) -> None:
        """
        Register a Skill
        
        Args:
            skill: Skill instance
            name: Optional custom name (defaults to skill.name)
        """
        skill_name = name or skill.name
        self._skills[skill_name] = skill
    
    def register_factory(
        self, 
        name: str, 
        factory: Callable[[], Skill],
        description: str = ""
    ) -> None:
        """
        Register a Skill factory function
        
        Used for lazy creation of Skills, only instantiated on first access.
        
        Args:
            name: Skill name
            factory: Factory function to create the Skill
            description: Skill description
        """
        self._factories[name] = factory
    
    def get(self, name: str) -> Optional[Skill]:
        """
        Get a Skill
        
        Prefers registered Skills first, falls back to factory creation.
        
        Args:
            name: Skill name
            
        Returns:
            Skill instance or None
        """
        # Directly get registered Skill
        if name in self._skills:
            return self._skills[name]
        
        # Try factory creation
        if name in self._factories:
            skill = self._factories[name]()
            self._skills[name] = skill
            return skill
        
        return None
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a Skill
        
        Args:
            name: Skill name
            
        Returns:
            Whether the unregistration succeeded
        """
        if name in self._skills:
            del self._skills[name]
            return True
        if name in self._factories:
            del self._factories[name]
            return True
        return False
    
    def list_all(self) -> List[SkillInfo]:
        """
        List all Skills
        
        Returns:
            List of SkillInfo
        """
        skills_info = []
        
        for name, skill in self._skills.items():
            skill_type = self._get_skill_type(skill)
            info = SkillInfo(
                name=name,
                description=skill.description,
                skill_type=skill_type,
                enabled=skill.is_enabled(),
                config=skill.config if hasattr(skill, 'config') else None
            )
            skills_info.append(info)
        
        # Include factory but not yet instantiated Skills
        for name in self._factories:
            if name not in self._skills:
                info = SkillInfo(
                    name=name,
                    description="Factory (not instantiated)",
                    skill_type="factory",
                    enabled=True
                )
                skills_info.append(info)
        
        return skills_info
    
    def list_by_type(self, skill_type: str) -> List[SkillInfo]:
        """
        List Skills by type
        
        Args:
            skill_type: "builtin", "langchain", "custom"
            
        Returns:
            List of matching SkillInfo
        """
        return [info for info in self.list_all() if info.skill_type == skill_type]
    
    def auto_discover_langchain_tools(self) -> int:
        """
        Auto-discover and register LangChain Tools

        Registers the following commonly used research Tools (if dependencies are available):
        - TavilySearchResults: Web search
        - ArxivQueryRun: Academic search
        - WikipediaQueryRun: Encyclopedia search
        - PythonREPLTool: Data analysis

        Note: Call order independent — skips skills already registered (e.g. by init_from_discovery).

        Returns:
            Number of successfully registered Tools
        """
        count = self._adapter.register_research_tools()

        # Sync adapter Skills to registry (skip already-registered)
        for name, skill in self._adapter._skills.items():
            if name not in self._skills:
                self._skills[name] = skill
            else:
                count -= 1
        
        return count
    
    def register_langchain_tool(self, tool: Any, name: Optional[str] = None) -> LangChainToolSkill:
        """
        Register a single LangChain Tool
        
        Args:
            tool: LangChain Tool instance
            name: Optional custom name
            
        Returns:
            The created LangChainToolSkill
        """
        skill = self._adapter.register_tool(tool, name)
        self._skills[skill.name] = skill
        return skill
    
    def auto_discover_builtin_skills(self) -> int:
        """
        Auto-discover built-in custom Skills
        
        Scans the src.skills.builtin module, automatically registers all Skill classes.
        
        Returns:
            Number of successfully registered Skills
        """
        count = 0
        
        try:
            from . import builtin
            
            # Iterate over builtin modules
            for importer, modname, ispkg in pkgutil.iter_modules(
                builtin.__path__, builtin.__name__ + "."
            ):
                try:
                    module = importlib.import_module(modname)
                    
                    # Find Skill classes in the module
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type) 
                            and issubclass(attr, Skill) 
                            and attr is not Skill
                            and attr is not LangChainToolSkill
                            and attr.__name__ != "KnowledgeQuerySkill"  # registered explicitly in register_core_skills
                        ):
                            # Instantiate and register (if config allows)
                            try:
                                skill = attr(SkillConfig(
                                    name=attr_name.lower().replace("skill", ""),
                                    version="1.0.0"
                                ))
                                self.register(skill)
                                count += 1
                            except Exception:
                                pass  # Skip uninstantiable classes
                                
                except Exception:
                    continue  # Skip unimportable modules
                    
        except ImportError:
            pass
        
        return count
    
    def register_core_skills(self) -> int:
        """
        Register core custom Skills (deprecated - now handled by init_from_discovery)

        This method is now a no-op for backward compatibility.
        All Skill registration is handled by init_from_discovery() which
        reads SKILL.md manifests and registers Skills automatically.

        Returns:
            0 (always, since no Skills are registered by this method)
        """
        logger.info("register_core_skills() is deprecated, use init_from_discovery() instead")
        return 0
    
    def load_langchain_skill(self, skill_name: str) -> bool:
        """
        Load a single LangChain Skill on demand
        
        Args:
            skill_name: Skill name (e.g. "lc_tavily_search", "lc_arxiv")
            
        Returns:
            Whether the load succeeded
        """
        # Skip if already exists
        if skill_name in self._skills:
            return True
        
        # LangChain Skill creation mapping
        skill_creators = {
            "lc_tavily_search": self._create_tavily_skill,
            "lc_arxiv": self._create_arxiv_skill,
            "lc_wikipedia": self._create_wikipedia_skill,
            "lc_python_repl": self._create_python_repl_skill,
        }
        
        creator = skill_creators.get(skill_name)
        if creator:
            skill = creator()
            if skill:
                self.register(skill)
                logger.info(f"Loaded LangChain skill: {skill_name}")
                return True
        
        return False
    
    def load_skills_for_category(self, category: str) -> List[str]:
        """
        Load Skills by category on demand (supports builtin, factory, and LangChain skills)
        
        Args:
            category: Category name (e.g. "market-analysis", "financial-analysis", "research")
            
        Returns:
            List of successfully loaded Skill names
        """
        # Phase 4: category_router removed, using built-in mapping
        CATEGORY_TO_SKILLS = {
            "market-analysis": ["market_analysis", "lc_tavily_search", "lc_wikipedia"],
            "data-collection": ["lc_tavily_search", "lc_wikipedia"],
            "academic-research": ["lc_arxiv", "lc_wikipedia"],
            "financial-analysis": ["stock_data", "stock_analysis", "lc_tavily_search", "lc_wikipedia"],
            "data-analysis": ["data_analysis", "lc_python_repl"],
            "report-generation": [],
            "quality-check": [],
            "visual-engineering": [],
            "research": ["stock_data", "lc_tavily_search", "lc_wikipedia"],
            "synthesis": [],
            "calibration": [],
            "annual-report": ["annual_report_parser", "stock_data", "stock_analysis"],
        }
        
        needed_skills = CATEGORY_TO_SKILLS.get(category, [])
        loaded = []
        
        for skill_name in needed_skills:
            if skill_name in self._skills:
                loaded.append(skill_name)
                continue
            if skill_name in self._factories:
                skill = self.get(skill_name)
                if skill:
                    loaded.append(skill_name)
                continue
            if skill_name.startswith("lc_"):
                if self.load_langchain_skill(skill_name):
                    loaded.append(skill_name)
                continue
        
        if loaded:
            logger.info(f"Loaded {len(loaded)} skills for category: {category}")
        
        return loaded
    
    def discover_skills(
        self,
        query: str,
        auto_load: bool = True,
    ) -> List[str]:
        query_lower = query.lower().strip()
        matched = []

        for name, manifest in self._manifests.items():
            for kw in manifest.keywords:
                kw_lower = kw.lower()
                if query_lower in kw_lower or kw_lower in query_lower:
                    if name not in matched:
                        matched.append(name)
                    break

        if not matched:
            import difflib
            all_keywords = {}
            keyword_to_names = {}
            for name, manifest in self._manifests.items():
                for kw in manifest.keywords:
                    kw_lower = kw.lower()
                    if kw_lower not in keyword_to_names:
                        keyword_to_names[kw_lower] = []
                    keyword_to_names[kw_lower].append(name)
                    all_keywords[kw_lower] = name
            close = difflib.get_close_matches(
                query_lower, list(all_keywords.keys()), n=5, cutoff=0.6
            )
            for kw in close:
                for name in keyword_to_names.get(kw, []):
                    if name not in matched:
                        matched.append(name)

        loaded = []
        if auto_load:
            for skill_name in matched:
                if skill_name in self._skills:
                    loaded.append(skill_name)
                elif skill_name in self._factories:
                    skill = self.get(skill_name)
                    if skill:
                        loaded.append(skill_name)
                elif skill_name.startswith("lc_"):
                    if self.load_langchain_skill(skill_name):
                        loaded.append(skill_name)
        else:
            loaded = matched

        if loaded:
            logger.info(f"Discovered skills for '{query}': {loaded}")

        return loaded
    
    def _create_tavily_skill(self):
        """Create Tavily search Skill"""
        import os
        if not os.getenv("TAVILY_API_KEY"):
            return None
        try:
            from langchain_community.tools import TavilySearchResults
            tool = TavilySearchResults(max_results=5, include_answer=True)
            return LangChainToolSkill(tool)
        except Exception:
            return None
    
    def _create_arxiv_skill(self):
        """Create Arxiv academic search Skill"""
        try:
            from langchain_community.tools.arxiv import ArxivQueryRun
            from langchain_community.utilities.arxiv import ArxivAPIWrapper
            tool = ArxivQueryRun(api_wrapper=ArxivAPIWrapper(top_k_results=3))
            return LangChainToolSkill(tool)
        except Exception:
            return None
    
    def _create_wikipedia_skill(self):
        """Create Wikipedia encyclopedia search Skill"""
        try:
            from langchain_community.tools.wikipedia import WikipediaQueryRun
            from langchain_community.utilities.wikipedia import WikipediaAPIWrapper
            tool = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper(top_k_results=3, lang="zh"))
            return LangChainToolSkill(tool)
        except Exception:
            return None
    
    def _create_python_repl_skill(self):
        """Create Python REPL data analysis Skill"""
        try:
            from langchain_experimental.tools import PythonREPLTool
            tool = PythonREPLTool()
            return LangChainToolSkill(tool)
        except Exception:
            return None
    
    def clear(self) -> None:
        """Clear all registered Skills"""
        self._skills.clear()
        self._factories.clear()
        self._manifests.clear()
        self._adapter.clear()
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get registry statistics
        
        Returns:
            Statistics dictionary
        """
        all_skills = self.list_all()
        return {
            "total": len(all_skills),
            "builtin": len([s for s in all_skills if s.skill_type == "builtin"]),
            "langchain": len([s for s in all_skills if s.skill_type == "langchain"]),
            "custom": len([s for s in all_skills if s.skill_type == "custom"]),
            "factory": len([s for s in all_skills if s.skill_type == "factory"]),
        }
    
    def _get_skill_type(self, skill: Skill) -> str:
        """Determine Skill type"""
        if isinstance(skill, LangChainToolSkill):
            return "langchain"
        elif skill.__class__.__module__.startswith("src.skills.builtin"):
            return "builtin"
        else:
            return "custom"

    def register_manifest(self, manifest: Any) -> None:
        self._manifests[manifest.name] = manifest

    def get_manifest(self, name: str) -> Optional[Any]:
        return self._manifests.get(name)

    def all_manifests(self) -> Dict[str, Any]:
        return dict(self._manifests)

    def get_by_capability(self, capability: str) -> Optional[Skill]:
        for name, manifest in self._manifests.items():
            if capability in manifest.capabilities:
                skill = self.get(name)
                if skill:
                    return skill
        return None

    def get_by_priority(self, priority: str) -> List[Skill]:
        results = []
        for name, manifest in self._manifests.items():
            if manifest.priority == priority:
                skill = self.get(name)
                if skill:
                    results.append(skill)
        return results

    def get_skills_by_category(self, category: str) -> List[str]:
        return [
            name for name, m in self._manifests.items()
            if category in m.categories
        ]

    def init_from_discovery(self, skills_dir) -> None:
        from .discovery import SkillDiscovery
        from .base import InstructionSkill
        from pathlib import Path

        skills_path = Path(skills_dir) if not isinstance(skills_dir, Path) else skills_dir
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_path)

        for manifest in manifests:
            if manifest.skill_type == "langchain":
                continue

            self.register_manifest(manifest)

            if manifest.has_code:
                skill_cls = discovery.load_skill_class(manifest)
                if skill_cls:
                    self.register_factory(manifest.name, skill_cls)
                else:
                    self.register_factory(
                        manifest.name,
                        lambda m=manifest: InstructionSkill(m),
                    )
            else:
                self.register_factory(
                    manifest.name,
                    lambda m=manifest: InstructionSkill(m),
                )

        for manifest in manifests:
            if manifest.skill_type == "langchain":
                continue
            for alias in manifest.aliases:
                if alias in self._skills or alias in self._factories:
                    continue
                if manifest.name in self._skills:
                    self._skills[alias] = self._skills[manifest.name]
                elif manifest.name in self._factories:
                    original_name = manifest.name
                    def _alias_factory(_name=original_name):
                        existing = self._skills.get(_name)
                        if existing:
                            return existing
                        original_factory = self._factories.get(_name)
                        if original_factory:
                            instance = original_factory()
                            self._skills[_name] = instance
                            return instance
                        return None
                    self._factories[alias] = _alias_factory

        self._validate_manifests()

    def _validate_manifests(self) -> None:
        for name, manifest in self._manifests.items():
            if manifest.has_code and name not in self._factories and name not in self._skills:
                logger.warning(f"Skill '{name}' has skill.py but no Skill subclass found")

            if manifest.action_param_map:
                for cap in manifest.capabilities:
                    if cap not in manifest.action_param_map:
                        logger.warning(f"Skill '{name}' capability '{cap}' not in action_param_map")

            if manifest.action_rules:
                for rule in manifest.action_rules:
                    for action in rule.actions:
                        if action not in manifest.capabilities:
                            logger.warning(f"Skill '{name}' action_rule references '{action}' not in capabilities")


# Global registry singleton
_global_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """
    Get the global Skill registry
    
    Returns:
        SkillRegistry singleton instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry


def reset_skill_registry() -> None:
    """Reset the global registry (mainly for testing)"""
    global _global_registry
    _global_registry = None


# Convenience functions

async def execute_skill(name: str, **kwargs) -> Dict[str, Any]:
    """
    Convenience function: execute a specified Skill
    
    Args:
        name: Skill name
        **kwargs: Arguments to pass to the Skill
        
    Returns:
        Skill execution result
    """
    registry = get_skill_registry()
    skill = registry.get(name)
    
    if skill is None:
        return {
            "success": False,
            "error": f"Skill '{name}' not found",
            "message": "Please register the skill first"
        }
    
    return await skill.execute(**kwargs)


def list_skills(skill_type: Optional[str] = None) -> List[SkillInfo]:
    """
    Convenience function: list all Skills
    
    Args:
        skill_type: Optional type filter
        
    Returns:
        List of SkillInfo
    """
    registry = get_skill_registry()
    if skill_type:
        return registry.list_by_type(skill_type)
    return registry.list_all()
