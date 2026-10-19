# -*- coding: utf-8 -*-
"""
Prompt Management API
=====================

Provides RESTful API endpoints for prompt management:
1. List available prompts
2. Get prompt content
3. Render prompt with variables
4. Manage agent profiles
5. Invalidate cache

Design Principles:
- Read-only operations for production safety
- Cache management for development
- No direct file modification via API
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

# FastAPI optional dependency
try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object
    HTTPException = Exception
    BaseModel = object

from src.core.prompt_manager import PromptManager, AgentProfile

logger = logging.getLogger(__name__)


# ==================== Data Models ====================

@dataclass
class PromptInfo:
    """Prompt file information"""
    category: str
    name: str
    path: str
    has_frontmatter: bool = False
    size_bytes: int = 0


@dataclass
class RenderPromptRequest:
    """Request to render a prompt with variables"""
    category: str
    name: str
    variables: Dict[str, Any] = field(default_factory=dict)
    strip_frontmatter: bool = True


@dataclass
class AgentProfileInfo:
    """Agent profile information"""
    name: str
    description: str
    role: str
    goal: str
    backstory: str
    required_skills: List[str] = field(default_factory=list)
    optional_skills: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


# ==================== API Implementation ====================

class PromptAPI:
    """
    Prompt Management API
    
    Provides read-only access to prompt files and agent profiles.
    """
    
    def __init__(self, base_dir: str = "prompts"):
        """
        Initialize API
        
        Args:
            base_dir: Base directory for prompt files
        """
        self._pm = PromptManager(base_dir=base_dir)
        self._base_dir = Path(base_dir)
        logger.info(f"PromptAPI initialized with base_dir={base_dir}")
    
    # ==================== List Operations ====================
    
    def list_categories(self) -> List[str]:
        """
        List all prompt categories
        
        Returns:
            List of category names
        """
        categories = []
        for item in self._base_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                categories.append(item.name)
        return sorted(categories)
    
    def list_prompts(self, category: str) -> List[PromptInfo]:
        """
        List all prompts in a category
        
        Args:
            category: Category name (_shared, agents, tasks, phases)
            
        Returns:
            List of prompt information
        """
        category_path = self._base_dir / category
        if not category_path.exists():
            return []
        
        prompts = []
        for md_file in category_path.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                has_frontmatter = content.startswith("---")
                prompts.append(PromptInfo(
                    category=category,
                    name=md_file.stem,
                    path=str(md_file.relative_to(self._base_dir)),
                    has_frontmatter=has_frontmatter,
                    size_bytes=len(content.encode("utf-8"))
                ))
            except Exception as e:
                logger.warning(f"Failed to read {md_file}: {e}")
        
        return sorted(prompts, key=lambda p: p.name)
    
    def list_all_prompts(self) -> Dict[str, List[PromptInfo]]:
        """
        List all prompts across all categories
        
        Returns:
            Dictionary mapping category to prompt list
        """
        result = {}
        for category in self.list_categories():
            result[category] = self.list_prompts(category)
        return result
    
    # ==================== Get Operations ====================
    
    def get_prompt(self, category: str, name: str) -> Optional[str]:
        """
        Get raw prompt content
        
        Args:
            category: Category name
            name: Prompt name (without .md extension)
            
        Returns:
            Raw prompt content or None if not found
        """
        try:
            return self._pm.load(category, name)
        except FileNotFoundError:
            return None
    
    def render_prompt(
        self,
        category: str,
        name: str,
        variables: Dict[str, Any],
        strip_frontmatter: bool = True
    ) -> Dict[str, Any]:
        """
        Render a prompt with variables
        
        Args:
            category: Category name
            name: Prompt name
            variables: Variables to substitute
            strip_frontmatter: Whether to remove YAML frontmatter
            
        Returns:
            Rendered prompt result
        """
        try:
            rendered = self._pm.render(
                category=category,
                name=name,
                strip_frontmatter=strip_frontmatter,
                **variables
            )
            return {
                "success": True,
                "category": category,
                "name": name,
                "rendered": rendered,
                "length": len(rendered)
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": f"Prompt not found: {category}/{name}",
                "error_code": "PROMPT_NOT_FOUND"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": "RENDER_ERROR"
            }
    
    # ==================== Agent Profile Operations ====================
    
    def list_agent_profiles(self) -> List[str]:
        """
        List all agent profile names
        
        Returns:
            List of agent profile names
        """
        agents_dir = self._base_dir / "agents"
        if not agents_dir.exists():
            return []
        return sorted([f.stem for f in agents_dir.glob("*.md")])
    
    def get_agent_profile(self, name: str) -> Optional[AgentProfileInfo]:
        """
        Get agent profile information
        
        Args:
            name: Agent profile name
            
        Returns:
            Agent profile info or None if not found
        """
        try:
            profile = self._pm.load_profile(name)
            return AgentProfileInfo(
                name=profile.name,
                description=profile.description,
                role=profile.role,
                goal=profile.goal,
                backstory=profile.backstory,
                required_skills=profile.required_skills,
                optional_skills=profile.optional_skills,
                config=profile.config
            )
        except FileNotFoundError:
            return None
    
    def get_agent_full_prompt(self, name: str) -> Optional[str]:
        """
        Get agent's full system prompt (role + goal + backstory + body)
        
        Args:
            name: Agent profile name
            
        Returns:
            Full system prompt or None if not found
        """
        try:
            return self._pm.load_profile_system_prompt(name)
        except FileNotFoundError:
            return None
    
    def get_skills_for_aspect(self, aspect: str) -> List[str]:
        """
        Get required skills for a research aspect
        
        Args:
            aspect: Research aspect name (e.g., "Market Size", "Competitive Landscape")
            
        Returns:
            List of required skills
        """
        return self._pm.get_skills_for_aspect(aspect)
    
    # ==================== Cache Operations ====================
    
    def invalidate_cache(self, key: Optional[str] = None) -> Dict[str, Any]:
        """
        Invalidate prompt cache
        
        Args:
            key: Specific cache key to invalidate (e.g., "agents/market_size")
                 If None, clears all cache
            
        Returns:
            Operation result
        """
        self._pm.invalidate(key)
        return {
            "success": True,
            "message": f"Cache invalidated: {key or 'all'}"
        }
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Cache statistics
        """
        return {
            "cache_size": len(self._pm._cache),
            "cached_keys": list(self._pm._cache.keys())
        }


# ==================== FastAPI Router ====================

class PromptAPIRouter:
    """
    FastAPI Router for Prompt Management
    """
    
    def __init__(self, api: PromptAPI):
        self.api = api
        self.routes = []
        
        if FASTAPI_AVAILABLE:
            self._setup_routes()
        else:
            self.routes = [
                type('Route', (), {'path': '/prompts/categories'}),
                type('Route', (), {'path': '/prompts/{category}'}),
                type('Route', (), {'path': '/prompts/{category}/{name}'}),
                type('Route', (), {'path': '/prompts/render'}),
                type('Route', (), {'path': '/agents/profiles'}),
                type('Route', (), {'path': '/agents/profiles/{name}'}),
                type('Route', (), {'path': '/agents/profiles/{name}/prompt'}),
                type('Route', (), {'path': '/agents/skills/{aspect}'}),
                type('Route', (), {'path': '/prompts/cache/invalidate'}),
                type('Route', (), {'path': '/prompts/cache/stats'}),
            ]
    
    def _setup_routes(self):
        """Setup FastAPI routes"""
        router = APIRouter(prefix="/prompts", tags=["prompts"])
        
        # List operations
        @router.get("/categories")
        async def list_categories():
            """List all prompt categories"""
            return {"categories": self.api.list_categories()}
        
        @router.get("/{category}")
        async def list_prompts(category: str):
            """List all prompts in a category"""
            prompts = self.api.list_prompts(category)
            return {
                "category": category,
                "count": len(prompts),
                "prompts": [
                    {
                        "name": p.name,
                        "path": p.path,
                        "has_frontmatter": p.has_frontmatter,
                        "size_bytes": p.size_bytes
                    }
                    for p in prompts
                ]
            }
        
        @router.get("/{category}/{name}")
        async def get_prompt(category: str, name: str):
            """Get raw prompt content"""
            content = self.api.get_prompt(category, name)
            if content is None:
                raise HTTPException(status_code=404, detail=f"Prompt not found: {category}/{name}")
            return {
                "category": category,
                "name": name,
                "content": content,
                "length": len(content)
            }
        
        @router.post("/render")
        async def render_prompt(request: RenderPromptRequest):
            """Render a prompt with variables"""
            result = self.api.render_prompt(
                category=request.category,
                name=request.name,
                variables=request.variables,
                strip_frontmatter=request.strip_frontmatter
            )
            if not result.get("success"):
                raise HTTPException(status_code=404, detail=result.get("error"))
            return result
        
        # Agent profile routes
        agents_router = APIRouter(prefix="/agents", tags=["agents"])
        
        @agents_router.get("/profiles")
        async def list_agent_profiles():
            """List all agent profiles"""
            return {
                "count": len(self.api.list_agent_profiles()),
                "profiles": self.api.list_agent_profiles()
            }
        
        @agents_router.get("/profiles/{name}")
        async def get_agent_profile(name: str):
            """Get agent profile information"""
            profile = self.api.get_agent_profile(name)
            if profile is None:
                raise HTTPException(status_code=404, detail=f"Agent profile not found: {name}")
            return {
                "name": profile.name,
                "description": profile.description,
                "role": profile.role,
                "goal": profile.goal,
                "backstory": profile.backstory,
                "required_skills": profile.required_skills,
                "optional_skills": profile.optional_skills,
                "config": profile.config
            }
        
        @agents_router.get("/profiles/{name}/prompt")
        async def get_agent_full_prompt(name: str):
            """Get agent's full system prompt"""
            prompt = self.api.get_agent_full_prompt(name)
            if prompt is None:
                raise HTTPException(status_code=404, detail=f"Agent profile not found: {name}")
            return {
                "name": name,
                "full_prompt": prompt,
                "length": len(prompt)
            }
        
        @agents_router.get("/skills/{aspect}")
        async def get_skills_for_aspect(aspect: str):
            """Get required skills for a research aspect"""
            skills = self.api.get_skills_for_aspect(aspect)
            return {
                "aspect": aspect,
                "skills": skills
            }
        
        # Cache management routes
        cache_router = APIRouter(prefix="/cache", tags=["cache"])
        
        @cache_router.post("/invalidate")
        async def invalidate_cache(key: Optional[str] = None):
            """Invalidate prompt cache"""
            return self.api.invalidate_cache(key)
        
        @cache_router.get("/stats")
        async def get_cache_stats():
            """Get cache statistics"""
            return self.api.get_cache_stats()
        
        self._router = router
        self._agents_router = agents_router
        self._cache_router = cache_router
        self.routes = router.routes + agents_router.routes + cache_router.routes
    
    def get_routers(self):
        """Get all FastAPI routers"""
        if FASTAPI_AVAILABLE and hasattr(self, '_router'):
            return {
                "prompts": self._router,
                "agents": self._agents_router,
                "cache": self._cache_router
            }
        return {}


# ==================== Factory Function ====================

def create_prompt_api(base_dir: str = "prompts") -> PromptAPI:
    """
    Create a PromptAPI instance
    
    Args:
        base_dir: Base directory for prompt files
        
    Returns:
        PromptAPI instance
    """
    return PromptAPI(base_dir=base_dir)


# Create default instance
prompt_api = PromptAPI()


# Export
__all__ = [
    "PromptAPI",
    "PromptAPIRouter",
    "prompt_api",
    "create_prompt_api",
    "PromptInfo",
    "RenderPromptRequest",
    "AgentProfileInfo",
]
