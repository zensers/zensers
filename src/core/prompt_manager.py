# -*- coding: utf-8 -*-
"""
Prompt Manager - Prompt File Loader

Extracts LLM prompts hardcoded in Python code into separate .md files,
achieving separation of prompts from code.

Design principles:
1. No new dependencies - only use Python standard library + existing project dependencies (PyYAML)
2. Plain text - .md files, string.Template for variable filling
3. Don't change logic - only extract plain text, leave conditionals/loops in Python
4. Interface unchanged - existing API signatures remain the same

Usage example:
    from src.core.prompt_manager import PromptManager
    
    pm = PromptManager()
    
    # Load and render prompt
    prompt = pm.render("tasks", "research_with_data", 
        topic="New Energy Vehicles", aspect="Market Size")
    
    # Load Agent Profile
    profile = pm.load_profile("Market Size")
    print(profile.system_prompt)
    print(profile.required_skills)
"""

import re
import logging
from pathlib import Path
from string import Template
from threading import Lock
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentProfile:
    """
    Agent complete definition (prompt + metadata + skills + config) from a .md file
    
    Attributes:
        name: Agent name (from frontmatter or filename)
        description: Brief description of agent purpose
        role: Role definition (used in system prompt)
        goal: Goal definition (used in system prompt)
        backstory: Background story (enhances role depth)
        system_prompt: Body content -> LLM system prompt
        required_skills: frontmatter.skills.required
        optional_skills: frontmatter.skills.optional
        config: frontmatter.config
    """
    name: str
    description: str = ""
    role: str = ""
    goal: str = ""
    backstory: str = ""
    system_prompt: str = ""
    required_skills: List[str] = field(default_factory=list)
    optional_skills: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_md(cls, path: Path) -> "AgentProfile":
        """Parse Agent Profile from .md file"""
        content = path.read_text(encoding="utf-8")
        return cls.from_text(path.stem, content)
    
    @classmethod
    def from_text(cls, name: str, content: str) -> "AgentProfile":
        """
        Parse Agent Profile from text content (supports cached input)
        
        Supports two formats:
        1. With frontmatter: ---\\nYAML\\n---\\nbody
        2. Plain text: entire content as system_prompt
        """
        import yaml
        
        lines = content.split('\n')
        if lines and lines[0].strip() == '---':
            end = None
            for i in range(1, len(lines)):
                if lines[i].strip() == '---':
                    end = i
                    break
            if end is not None:
                fm_text = '\n'.join(lines[1:end])
                body = '\n'.join(lines[end+1:]).strip()
                try:
                    fm = yaml.safe_load(fm_text) if fm_text.strip() else {}
                except yaml.YAMLError as e:
                    logger.warning(f"YAML frontmatter parse error in {name}: {e}")
                    fm = {}
                skills = fm.get("skills", {})
                return cls(
                    name=fm.get("name", name),
                    description=fm.get("description", ""),
                    role=fm.get("role", ""),
                    goal=fm.get("goal", ""),
                    backstory=fm.get("backstory", ""),
                    system_prompt=body,
                    required_skills=skills.get("required", []),
                    optional_skills=skills.get("optional", []),
                    config=fm.get("config", {}),
                )
        # No frontmatter, entire content as system_prompt
        return cls(name=name, system_prompt=content.strip())
    
    def get_full_prompt(self) -> str:
        """Generate complete system prompt from role, goal, backstory and body"""
        parts = []
        if self.role:
            parts.append(f"# Role\n{self.role}")
        if self.goal:
            parts.append(f"# Goal\n{self.goal}")
        if self.backstory:
            parts.append(f"# Background\n{self.backstory}")
        if self.system_prompt:
            parts.append(self.system_prompt)
        return "\n\n".join(parts) if parts else ""


class PromptManager:
    """
    Prompt file loader. Zero dependencies, pure text.
    
    Features:
    - Load prompt from .md files
    - Support YAML frontmatter (for Agent Profile)
    - Support {include:xxx} shared content references
    - Use string.Template for variable substitution
    - Thread-safe caching
    - Singleton pattern for global cache sharing
    """
    
    _instance: Optional["PromptManager"] = None
    _instance_lock = Lock()
    
    def __new__(cls, base_dir: str = "prompts") -> "PromptManager":
        """
        Singleton pattern: ensure only one instance exists globally.
        This allows cache sharing across all callers.
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._base_dir = Path(base_dir)
                    instance._cache: Dict[str, str] = {}
                    instance._lock = Lock()
                    instance._strict_mode = False  # PR-FIX-1: 未解析变量时是否抛异常
                    cls._instance = instance
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "PromptManager":
        """Get the singleton instance"""
        if cls._instance is None:
            return cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for testing)"""
        with cls._instance_lock:
            cls._instance = None
    
    def load(self, category: str, name: str) -> str:
        """
        Load .md file with caching. Double-checked locking to prevent races.
        
        Args:
            category: Category directory name (_shared, agents, tasks, phases)
            name: File name (without .md extension)
            
        Returns:
            File content (may contain frontmatter)
            
        Raises:
            FileNotFoundError: File not found
        """
        key = f"{category}/{name}"
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        
        path = self._base_dir / category / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")
        content = path.read_text(encoding="utf-8")
        
        # Lock again to write, prevent double-write
        with self._lock:
            if key not in self._cache:
                self._cache[key] = content
        return content
    
    def render(self, category: str, name: str, strip_frontmatter: bool = False, **variables) -> str:
        """
        Load and render prompt
        
        Args:
            category: Category directory name
            name: File name
            strip_frontmatter: Whether to remove YAML frontmatter
            **variables: Template variables
            
        Returns:
            Rendered prompt string
        """
        return self._render_with_includes(category, name, _depth=0, strip_frontmatter=strip_frontmatter, **variables)
    
    def _render_with_includes(self, category: str, name: str, _depth: int, 
                               strip_frontmatter: bool = False, **variables) -> str:
        """
        Recursively render prompt, handling {include:xxx} references
        
        Args:
            category: Category directory name
            name: File name
            _depth: Current recursion depth (internal param, avoid conflict with template variables)
            strip_frontmatter: Whether to remove frontmatter
            **variables: Template variables
            
        Returns:
            Rendered prompt
            
        Raises:
            RuntimeError: Recursion depth exceeds 5 levels
        """
        if _depth > 5:
            raise RuntimeError(f"Prompt include recursion too deep: {name}")
        
        template = self.load(category, name)
        
        # Remove frontmatter
        if strip_frontmatter:
            template = re.sub(r'^---\n.*?\n---\n', '', template, flags=re.DOTALL)
        
        # Handle {include:xxx} references
        template = re.sub(
            r'\{include:(\w+)\}',
            lambda m: self._render_with_includes("_shared", m.group(1), _depth + 1),
            template
        )
        
        # Variable substitution
        result = Template(template).safe_substitute(**variables)
        
        # Check for unfilled variables (PR-FIX-1: only match ${xxx} to avoid $M/$B false positives)
        if '$' in result:
            unresolved = re.findall(r'\$\{[a-zA-Z_]\w*\}', result)
            if unresolved:
                logger.error(f"Unresolved prompt variables in {category}/{name}: {unresolved}")
                if self._strict_mode:
                    raise ValueError(f"Unresolved prompt variables: {unresolved}")
        
        return result
    
    def invalidate(self, key: Optional[str] = None) -> None:
        """
        Clear cache
        
        Args:
            key: Specific cache key to clear (e.g. "agents/Market Size"), None means clear all
        """
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()
    
    # ─── Agent Profile Loading (prompt + skills + config unified management) ───
    
    def load_profile(self, name: str) -> AgentProfile:
        """
        Load Agent Profile = system_prompt + skills + config (with caching)
        
        Args:
            name: Agent name (filename without extension)
            
        Returns:
            AgentProfile object
        """
        raw = self.load("agents", name)  # With caching
        return AgentProfile.from_text(name, raw)
    
    def load_profile_system_prompt(self, name: str) -> str:
        """
        Load Agent's full system prompt (combining role, goal, backstory and body)
        
        Args:
            name: Agent name
            
        Returns:
            Complete system prompt string
        """
        return self.load_profile(name).get_full_prompt()
    
    def get_skills_for_aspect(self, aspect: str) -> List[str]:
        """
        Return required Skills list based on research aspect
        
        Reads skills from agents/*.md file frontmatter.
        Supports exact match and fuzzy match (key in aspect).
        
        Args:
            aspect: Research aspect name
            
        Returns:
            Applicable Skills list
        """
        # Exact match
        try:
            profile = self.load_profile(aspect)
            return profile.required_skills
        except FileNotFoundError:
            pass
        
        # Fuzzy match: iterate all agents/*.md files
        agents_dir = self._base_dir / "agents"
        if agents_dir.exists():
            for md_file in agents_dir.glob("*.md"):
                file_stem = md_file.stem
                # Check if filename is contained in aspect, or aspect contains filename
                if file_stem in aspect or aspect in file_stem:
                    try:
                        profile = self.load_profile(file_stem)
                        return profile.required_skills
                    except Exception:
                        continue
        
        # Default
        return ["llm_skill", "search_skill"]


# Aspect Chinese to English mapping
ASPECT_NAME_MAP = {
    "市场规模": "market_size",
    "竞争格局": "competition",
    "发展趋势": "trend",
    "产业链": "industry_chain",
    "财务分析": "financial_analysis",
    "估值分析": "valuation",
    "政策法规": "policy",
    "技术趋势": "technology",
    "企业分析": "enterprise",
    "风险分析": "risk",
    "投资价值": "investment",
    "执行摘要": "executive_summary_role",
    "研究结论": "conclusion_role",
    "数据验证": "validation",
    "综合分析": "general",
}


def get_profile_name_for_aspect(aspect: str) -> str:
    """Map Chinese aspect to English filename"""
    # Exact match
    if aspect in ASPECT_NAME_MAP:
        return ASPECT_NAME_MAP[aspect]
    
    # Fuzzy match: check if aspect contains keyword
    for key, value in ASPECT_NAME_MAP.items():
        if key in aspect:
            return value
    
    # Default
    return "general"


# Global singleton (optional use)
_prompt_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """Get global PromptManager singleton"""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptManager()
    return _prompt_manager
