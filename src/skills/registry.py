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
        
        Returns:
            Number of successfully registered Tools
        """
        count = self._adapter.register_research_tools()
        
        # Sync adapter Skills to registry
        # Note: _adapter._skills contains actual Skill objects
        for name, skill in self._adapter._skills.items():
            if name not in self._skills:
                self._skills[name] = skill
        
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
        Register core custom Skills (direct registration, no scanning)
        
        Registers the following core Skills:
        - search_skill: Multi-search engine integration (Baidu/Bing/Google/Sogou etc., 17 engines)
        - news_search: News search
        - file_skill: File operations
        - http_skill: HTTP requests
        - docx_skill: Word document generation
        
        Returns:
            Number of successfully registered Skills
        """
        count = 0
        
        # Import core Skills
        try:
            from .search_skill import SearchSkill, NewsSearchSkill
            from .file_skill import FileSkill
            from .http_skill import HTTPSkill
            from .docx_skill import DocxSkill
            
            # Register search Skill (multi-search engine integration)
            # search_skill is the generic search interface, uses the most feature-complete SearchSkill
            if "search_skill" not in self._skills:
                self.register(SearchSkill(), name="search_skill")
                count += 1
            
            # Also register web_search as alias (backward compatibility)
            if "web_search" not in self._skills:
                self.register(SearchSkill(), name="web_search")
                count += 1
            
            # Register news search Skill
            if "news_search" not in self._skills:
                self.register(NewsSearchSkill())
                count += 1
            
            # Register file Skill
            if "file_skill" not in self._skills:
                self.register(FileSkill())
                count += 1
            
            # Register HTTP Skill
            if "http_skill" not in self._skills:
                self.register(HTTPSkill())
                count += 1
            
            # Register Docx Skill
            if "docx_skill" not in self._skills:
                self.register(DocxSkill())
                count += 1
            
            # Register LLM Skill (core reasoning capability)
            if "llm_skill" not in self._skills:
                from .llm_skill import LLMSkill
                self.register(LLMSkill())
                count += 1
            
            # Register Web Scraper Skill (key component of two-phase search strategy)
            if "web_scraper" not in self._skills:
                from .web_scraper_skill import WebScraperSkill
                self.register(WebScraperSkill(), name="web_scraper")
                count += 1
            
            # Register KnowledgeQuerySkill (global singleton, lazy KM injection)
            if "knowledge_query" not in self._skills:
                from .builtin.knowledge_query_skill import KnowledgeQuerySkill, _LazyKM
                self.register(KnowledgeQuerySkill(knowledge_manager=_LazyKM()))
                count += 1
                logger.info("KnowledgeQuerySkill registered (lazy KM)")
            
        except Exception as e:
            logger.warning(f"Failed to register core skills: {e}")
        
        return count
    
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
            "market-analysis": ["market_analysis", "lc_tavily_search", "lc_wikipedia", "llm_skill"],
            "data-collection": ["lc_tavily_search", "lc_wikipedia"],
            "academic-research": ["lc_arxiv", "lc_wikipedia", "llm_skill"],
            "financial-analysis": ["stock_data", "stock_analysis", "lc_tavily_search", "lc_wikipedia", "llm_skill"],
            "data-analysis": ["data_analysis", "lc_python_repl", "llm_skill"],
            "report-generation": ["llm_skill"],
            "quality-check": ["llm_skill"],
            "visual-engineering": [],
            "research": ["stock_data", "lc_tavily_search", "lc_wikipedia", "llm_skill"],
            "synthesis": ["llm_skill"],
            "calibration": ["llm_skill"],
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
            if skill_name == "llm_skill":
                if skill_name not in self._skills:
                    self.register_core_skills()
                if skill_name in self._skills:
                    loaded.append(skill_name)
        
        if loaded:
            logger.info(f"Loaded {len(loaded)} skills for category: {category}")
        
        return loaded
    
    def discover_skills(
        self,
        query: str,
        auto_load: bool = True,
    ) -> List[str]:
        """
        Intelligently discover Skills (fuzzy matching + LLM fallback)
        
        Intelligently matches the most suitable Skills based on user query keywords.
        If no match is found, automatically falls back to llm_skill.
        
        Args:
            query: User query keywords (e.g. "patent analysis", "data analysis")
            auto_load: Whether to auto-load matched Skills, default True
            
        Returns:
            List of matched and loaded Skill names
            
        Example:
            >>> registry.discover_skills("patent analysis")
            ["lc_arxiv", "llm_skill"]
            
            >>> registry.discover_skills("quantum computing")
            ["llm_skill"]  # No match, falls back to LLM
        """
        from .skill_keywords import match_skills
        
        # Intelligently match Skills
        matched = match_skills(query)
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
                elif skill_name == "llm_skill":
                    if skill_name not in self._skills:
                        self.register_core_skills()
                    if skill_name in self._skills:
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
