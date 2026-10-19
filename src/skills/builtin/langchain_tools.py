"""
LangChain Tools Built-in Integration

Pre-built LangChain Tools commonly used in research, ready to use out of the box.

Supported Tools:
- web_search: Tavily real-time web search
- academic_search: Arxiv academic paper search
- wiki_search: Wikipedia knowledge search
- data_analysis: Python REPL data analysis

Usage examples:
    from src.skills.builtin import get_research_tools
    
    tools = get_research_tools()
    
    # Web search
    result = await tools["web_search"].execute(query="AI market 2026")
    
    # Academic search
    result = await tools["academic_search"].execute(query="machine learning")
"""

from typing import Dict, Optional
import os

from ..adapters import LangChainToolSkill

# Expose optional constructors at module scope so callers/tests can inject
# them without importing the optional LangChain ecosystem eagerly.
try:
    from langchain_community.tools import TavilySearchResults
except ImportError:
    TavilySearchResults = None
try:
    from langchain_community.tools.arxiv import ArxivQueryRun
    from langchain_community.utilities.arxiv import ArxivAPIWrapper
except ImportError:
    ArxivQueryRun = None
    ArxivAPIWrapper = None
try:
    from langchain_community.tools.wikipedia import WikipediaQueryRun
    from langchain_community.utilities.wikipedia import WikipediaAPIWrapper
except ImportError:
    WikipediaQueryRun = None
    WikipediaAPIWrapper = None
try:
    from langchain_experimental.tools import PythonREPLTool
except ImportError:
    PythonREPLTool = None


# Commonly used research Tools cache
_RESEARCH_TOOLS_CACHE: Optional[Dict[str, LangChainToolSkill]] = None


def create_tavily_search_skill(max_results: int = 5) -> Optional[LangChainToolSkill]:
    """
    Create Tavily search Skill
    
    Requires environment variable: TAVILY_API_KEY
    
    Args:
        max_results: Maximum number of results to return
        
    Returns:
        LangChainToolSkill or None (if dependency unavailable or missing API Key)
    """
    import os
    
    # Check API Key
    if not os.getenv("TAVILY_API_KEY") and TavilySearchResults is None:
        return None
    
    try:
        # Suppress deprecation warnings
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tool_class = TavilySearchResults
            if tool_class is None:
                from langchain_community.tools import TavilySearchResults as tool_class
            tool = tool_class(
                max_results=max_results,
                include_answer=True,
                include_raw_content=True,
            )
            return LangChainToolSkill(tool)
    except ImportError:
        return None
    except Exception:
        return None


def create_arxiv_search_skill(
    top_k_results: int = 3,
    load_max_docs: int = 3
) -> Optional[LangChainToolSkill]:
    """
    Create Arxiv academic search Skill
    
    Args:
        top_k_results: Number of results to return
        load_max_docs: Maximum number of documents to load
        
    Returns:
        LangChainToolSkill or None
    """
    try:
        tool_class = ArxivQueryRun
        wrapper_class = ArxivAPIWrapper
        if tool_class is None or wrapper_class is None:
            from langchain_community.tools.arxiv import ArxivQueryRun as tool_class
            from langchain_community.utilities.arxiv import ArxivAPIWrapper as wrapper_class
        
        api_wrapper = wrapper_class(
            top_k_results=top_k_results,
            load_max_docs=load_max_docs,
        )
        tool = tool_class(api_wrapper=api_wrapper)
        return LangChainToolSkill(tool)
    except ImportError:
        return None
    except Exception as e:
        print(f"Warning: Failed to create Arxiv search skill: {e}")
        return None


def create_wikipedia_search_skill(
    top_k_results: int = 3,
    lang: str = "zh"
) -> Optional[LangChainToolSkill]:
    """
    Create Wikipedia search Skill
    
    Args:
        top_k_results: Number of results to return
        lang: Language code (default Chinese)
        
    Returns:
        LangChainToolSkill or None
    """
    try:
        tool_class = WikipediaQueryRun
        wrapper_class = WikipediaAPIWrapper
        if tool_class is None or wrapper_class is None:
            from langchain_community.tools.wikipedia import WikipediaQueryRun as tool_class
            from langchain_community.utilities.wikipedia import WikipediaAPIWrapper as wrapper_class
        
        api_wrapper = wrapper_class(
            top_k_results=top_k_results,
            lang=lang,
        )
        tool = tool_class(api_wrapper=api_wrapper)
        return LangChainToolSkill(tool)
    except ImportError:
        return None
    except Exception as e:
        print(f"Warning: Failed to create Wikipedia search skill: {e}")
        return None


def create_python_repl_skill() -> Optional[LangChainToolSkill]:
    """
    Create Python REPL data analysis Skill
    
    Allows executing Python code for data analysis.
    Note: Security risk, only use in controlled environments.
    
    Returns:
        LangChainToolSkill or None
    """
    try:
        tool_class = PythonREPLTool
        if tool_class is None:
            from langchain_experimental.tools import PythonREPLTool as tool_class
        tool = tool_class()
        return LangChainToolSkill(tool)
    except ImportError:
        return None
    except Exception as e:
        print(f"Warning: Failed to create Python REPL skill: {e}")
        return None


def get_research_tools() -> Dict[str, LangChainToolSkill]:
    """
    Get all commonly used research Tools
    
    Returns a dictionary of pre-built Tools, containing:
    - web_search: Tavily web search
    - academic_search: Arxiv academic search
    - wiki_search: Wikipedia search
    - data_analysis: Python REPL data analysis
    
    Returns:
        {tool_name: LangChainToolSkill} dictionary
    """
    global _RESEARCH_TOOLS_CACHE
    
    if _RESEARCH_TOOLS_CACHE is not None:
        return _RESEARCH_TOOLS_CACHE
    
    tools = {}
    
    # Web search
    tavily = create_tavily_search_skill()
    if tavily:
        tools["web_search"] = tavily
    
    # Academic search
    arxiv = create_arxiv_search_skill()
    if arxiv:
        tools["academic_search"] = arxiv
    
    # Encyclopedia search
    wiki = create_wikipedia_search_skill()
    if wiki:
        tools["wiki_search"] = wiki
    
    # Data analysis
    python = create_python_repl_skill()
    if python:
        tools["data_analysis"] = python
    
    _RESEARCH_TOOLS_CACHE = tools
    return tools


# Export research Tools dictionary (lazy loading)
RESEARCH_TOOLS = property(get_research_tools)


def clear_research_tools_cache() -> None:
    """Clear Tools cache (for testing or reconfiguration)"""
    global _RESEARCH_TOOLS_CACHE
    _RESEARCH_TOOLS_CACHE = None


def list_available_tools() -> Dict[str, str]:
    """
    List all available Tools and their status
    
    Returns:
        {tool_name: status} dictionary, status is "available" or "unavailable: reason"
    """
    tools_status = {}
    
    # Check Tavily
    try:
        from langchain_community.tools import TavilySearchResults
        if os.getenv("TAVILY_API_KEY"):
            tools_status["web_search (Tavily)"] = "available"
        else:
            tools_status["web_search (Tavily)"] = "unavailable: TAVILY_API_KEY not set"
    except ImportError:
        tools_status["web_search (Tavily)"] = "unavailable: langchain-community not installed"
    
    # Check Arxiv
    try:
        from langchain_community.tools.arxiv import ArxivQueryRun
        tools_status["academic_search (Arxiv)"] = "available"
    except ImportError:
        tools_status["academic_search (Arxiv)"] = "unavailable: langchain-community not installed"
    
    # Check Wikipedia
    try:
        from langchain_community.tools.wikipedia import WikipediaQueryRun
        tools_status["wiki_search (Wikipedia)"] = "available"
    except ImportError:
        tools_status["wiki_search (Wikipedia)"] = "unavailable: langchain-community not installed"
    
    # Check Python REPL
    try:
        from langchain_experimental.tools import PythonREPLTool
        tools_status["data_analysis (Python REPL)"] = "available"
    except ImportError:
        tools_status["data_analysis (Python REPL)"] = "unavailable: langchain-experimental not installed"
    
    return tools_status


# Convenience functions: quick search

async def quick_web_search(query: str, max_results: int = 5) -> Dict:
    """
    Quick web search
    
    Args:
        query: Search query
        max_results: Maximum number of results
        
    Returns:
        Skill execution result dictionary
    """
    tools = get_research_tools()
    if "web_search" not in tools:
        return {
            "success": False,
            "error": "Web search tool not available",
            "message": "Please install langchain-community and set TAVILY_API_KEY"
        }
    
    return await tools["web_search"].execute(query=query)


async def quick_academic_search(query: str, top_k: int = 3) -> Dict:
    """
    Quick academic search
    
    Args:
        query: Search query
        top_k: Number of results to return
        
    Returns:
        Skill execution result dictionary
    """
    tools = get_research_tools()
    if "academic_search" not in tools:
        return {
            "success": False,
            "error": "Academic search tool not available",
            "message": "Please install langchain-community"
        }
    
    return await tools["academic_search"].execute(query=query)
