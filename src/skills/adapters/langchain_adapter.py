"""
LangChain Tool adapter

Wraps LangChain Tools into the Zensers Skill interface.
Supports seamless integration of all LangChain tools.

Usage:
    from langchain_community.tools import TavilySearchResults
    from src.skills.adapters import LangChainToolSkill
    
    # Wrap a LangChain Tool
    tavily_tool = TavilySearchResults(max_results=5)
    skill = LangChainToolSkill(tavily_tool)
    
    # Execute as a Skill
    result = await skill.execute(query="AI market research")
"""

from typing import Dict, Any, Optional, Type
from abc import ABC

try:
    from langchain_core.tools import BaseTool
    LANGCHAIN_AVAILABLE = True
except ImportError:
    BaseTool = ABC  # type: ignore
    LANGCHAIN_AVAILABLE = False

from ..base import Skill, SkillConfig, SkillOutput


class LangChainToolSkill(Skill):
    """
    LangChain Tool Skill adapter
    
    Wraps any LangChain BaseTool into a Zensers Skill.
    Automatically handles input/output conversion and error handling.
    
    Attributes:
        _tool: The wrapped LangChain Tool instance
        _config: Skill configuration
    
    Example:
        >>> from langchain_community.tools import TavilySearchResults
        >>> tool = TavilySearchResults()
        >>> skill = LangChainToolSkill(tool)
        >>> result = await skill.execute(query="AI trends")
    """
    
    def __init__(self, langchain_tool: BaseTool, config: Optional[SkillConfig] = None):
        """
        Initialize a LangChain Tool Skill
        
        Args:
            langchain_tool: LangChain Tool instance
            config: Optional Skill config, automatically generated from Tool info
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "LangChain is required for LangChainToolSkill. "
                "Install with: pip install langchain langchain-community"
            )
        
        # Auto-generate config if not provided
        if config is None:
            config = SkillConfig(
                name=f"lc_{langchain_tool.name}",
                version="1.0.0",
                enabled=True,
                options={
                    "langchain_tool_name": langchain_tool.name,
                    "langchain_tool_description": langchain_tool.description,
                }
            )
        
        super().__init__(config)
        self._tool = langchain_tool
    
    @property
    def name(self) -> str:
        """Skill name, prefix lc_ indicates LangChain Tool"""
        return self.config.name
    
    @property
    def description(self) -> str:
        """Skill description, uses the LangChain Tool's description"""
        return self._tool.description or f"LangChain Tool: {self._tool.name}"
    
    @property
    def langchain_tool(self) -> BaseTool:
        """Get the underlying LangChain Tool"""
        return self._tool
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the LangChain Tool
        
        Automatically handles sync and async Tools, returns unified Skill format results.
        
        Args:
            **kwargs: Arguments to pass to the LangChain Tool
            
        Returns:
            Standard Skill result containing success, data, message
            
        Raises:
            Does not raise exceptions, all errors are wrapped in the returned result
        """
        try:
            # LangChain Tool may return a string or complex object
            if hasattr(self._tool, 'ainvoke'):
                # Async invocation
                raw_result = await self._tool.ainvoke(kwargs)
            else:
                # Sync invocation (running in async environment)
                import asyncio
                raw_result = await asyncio.to_thread(self._tool.invoke, kwargs)
            
            # Normalize output
            result_data = {
                "raw_result": raw_result,
                "tool_name": self._tool.name,
            }
            
            # Try to parse structured data
            if isinstance(raw_result, str):
                result_data["content"] = raw_result
            elif isinstance(raw_result, dict):
                result_data.update(raw_result)
            elif hasattr(raw_result, 'content'):
                result_data["content"] = raw_result.content
            
            return self._success(
                data=result_data,
                message=f"Tool '{self._tool.name}' executed successfully"
            )
            
        except Exception as e:
            return self._failure(
                error=str(e),
                message=f"Tool '{self._tool.name}' execution failed"
            )
    
    def get_schema(self) -> Dict[str, Any]:
        """
        Get the Tool's parameter schema
        
        Returns:
            Parameter definition in JSON Schema format
        """
        if hasattr(self._tool, 'args_schema'):
            return self._tool.args_schema.schema() if self._tool.args_schema else {}
        return {}


class LangChainAdapter:
    """
    LangChain adapter manager
    
    Manages and creates LangChain Tool Skills in bulk.
    Provides quick registration and discovery of commonly used Tools.
    
    Example:
        >>> adapter = LangChainAdapter()
        >>> adapter.register_research_tools()  # Register commonly used research Tools
        >>> skill = adapter.get_skill("lc_tavily_search")
    """
    
    def __init__(self):
        """Initialize the adapter"""
        self._skills: Dict[str, LangChainToolSkill] = {}
        self._tool_classes: Dict[str, Type[BaseTool]] = {}
    
    def register_tool(self, tool: BaseTool, name: Optional[str] = None) -> LangChainToolSkill:
        """
        Register a single LangChain Tool
        
        Args:
            tool: LangChain Tool instance
            name: Optional custom name
            
        Returns:
            The created LangChainToolSkill
        """
        skill = LangChainToolSkill(tool)
        skill_name = name or skill.name
        self._skills[skill_name] = skill
        return skill
    
    def get_skill(self, name: str) -> Optional[LangChainToolSkill]:
        """
        Get a registered Skill
        
        Args:
            name: Skill name
            
        Returns:
            LangChainToolSkill or None
        """
        return self._skills.get(name)
    
    def list_skills(self) -> Dict[str, str]:
        """
        List all registered Skills
        
        Returns:
            {skill_name: description} dictionary
        """
        return {name: skill.description for name, skill in self._skills.items()}
    
    def register_research_tools(self) -> int:
        """
        Batch register commonly used research Tools
        
        Auto-discovers and registers the following Tools (if dependencies are available):
        - TavilySearchResults: Real-time web search
        - ArxivQueryRun: Academic paper search
        - WikipediaQueryRun: Encyclopedia knowledge query
        - PythonREPLTool: Python code execution
        
        Returns:
            Number of successfully registered Tools
        """
        count = 0
        
        # Tavily search (requires API Key)
        try:
            import os
            if os.getenv("TAVILY_API_KEY"):
                from langchain_community.tools import TavilySearchResults
                tool = TavilySearchResults(max_results=5)
                self.register_tool(tool)
                count += 1
        except (ImportError, Exception):
            pass
        
        # Arxiv academic search
        try:
            from langchain_community.tools.arxiv import ArxivQueryRun
            tool = ArxivQueryRun()
            self.register_tool(tool)
            count += 1
        except ImportError:
            pass
        
        # Wikipedia encyclopedia
        try:
            from langchain_community.tools.wikipedia import WikipediaQueryRun
            tool = WikipediaQueryRun()
            self.register_tool(tool)
            count += 1
        except ImportError:
            pass
        
        # Python REPL
        try:
            from langchain_experimental.tools import PythonREPLTool
            tool = PythonREPLTool()
            self.register_tool(tool)
            count += 1
        except ImportError:
            pass
        
        return count
    
    def clear(self) -> None:
        """Clear all registered Skills"""
        self._skills.clear()


# Global adapter instance (singleton pattern)
_global_adapter: Optional[LangChainAdapter] = None


def get_langchain_adapter() -> LangChainAdapter:
    """
    Get the global LangChain adapter
    
    Returns:
        LangChainAdapter singleton instance
    """
    global _global_adapter
    if _global_adapter is None:
        _global_adapter = LangChainAdapter()
    return _global_adapter

