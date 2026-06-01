"""
Skills package initialization

Provides all built-in Skills and hot-reload capability.

Architecture layers:
- adapters/: Third-party tool adapters (LangChain, etc.)
- builtin/: Built-in Skills (atomic capabilities + custom base Skills)
- business/: Business layer Skills reserved interface
- registry.py: Skill registry center

Usage examples:
    from src.skills import SkillRegistry, get_research_tools
    
    # Get common research tools
    tools = get_research_tools()
    
    # Execute search
    result = await tools["web_search"].execute(query="AI market")
"""
# Base types
from src.skills.base import Skill, SkillConfig, SkillOutput
from src.skills.base import SkillRegistry as _BaseSkillRegistry, get_registry

# Custom base Skills
from src.skills.file_skill import FileSkill
from src.skills.http_skill import HTTPSkill
from src.skills.llm_skill import LLMSkill
from src.skills.search_skill import SearchSkill, NewsSearchSkill
from src.skills.web_scraper_skill import WebScraperSkill
from src.skills.docx_skill import DocxSkill

# Hot reload
from src.skills.hot_reload import SkillHotReloader, SkillLoadError

# LangChain adapter
from src.skills.adapters import LangChainToolSkill, LangChainAdapter

# Built-in Tools
from src.skills.builtin import (
    get_research_tools,
    RESEARCH_TOOLS,
    create_tavily_search_skill,
    create_arxiv_search_skill,
    create_wikipedia_search_skill,
    create_python_repl_skill,
)

# Skill registry (new version)
from src.skills.registry import (
    SkillRegistry,
    get_skill_registry,
    execute_skill,
    list_skills,
)

__all__ = [
    # Base types
    "Skill",
    "SkillConfig",
    "SkillOutput",
    "SkillRegistry",
    "get_registry",
    "get_skill_registry",
    # Custom base Skills
    "FileSkill",
    "HTTPSkill",
    "LLMSkill",
    "SearchSkill",
    "NewsSearchSkill",
    "WebScraperSkill",
    "DocxSkill",
    # LangChain adapter
    "LangChainToolSkill",
    "LangChainAdapter",
    # Built-in Tools
    "get_research_tools",
    "RESEARCH_TOOLS",
    "create_tavily_search_skill",
    "create_arxiv_search_skill",
    "create_wikipedia_search_skill",
    "create_python_repl_skill",
    # Convenience functions
    "execute_skill",
    "list_skills",
    # Hot reload
    "SkillHotReloader",
    "SkillLoadError",
]
