"""
LangChain Tools 内置集成测试

测试研究常用 Tools 的创建和执行。
使用 Mock 避免实际 API 调用。
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import os


class TestLangChainToolsCreation:
    """测试 Tools 创建函数"""
    
    @patch("src.skills.builtin.langchain_tools.TavilySearchResults")
    def test_create_tavily_search_skill(self, mock_tavily_class):
        """测试创建 Tavily 搜索 Skill"""
        from src.skills.builtin.langchain_tools import create_tavily_search_skill
        
        mock_tool = Mock()
        mock_tool.name = "tavily_search"
        mock_tavily_class.return_value = mock_tool
        
        skill = create_tavily_search_skill(max_results=10)
        
        assert skill is not None
        assert skill.name == "lc_tavily_search"
        mock_tavily_class.assert_called_once_with(
            max_results=10,
            include_answer=True,
            include_raw_content=True,
        )
    
    @patch("src.skills.builtin.langchain_tools.TavilySearchResults")
    def test_create_tavily_search_skill_import_error(self, mock_tavily_class):
        """测试 Tavily 导入错误处理"""
        from src.skills.builtin.langchain_tools import create_tavily_search_skill
        
        mock_tavily_class.side_effect = ImportError("No module named 'tavily'")
        
        skill = create_tavily_search_skill()
        
        assert skill is None
    
    @patch("src.skills.builtin.langchain_tools.ArxivQueryRun")
    @patch("src.skills.builtin.langchain_tools.ArxivAPIWrapper")
    def test_create_arxiv_search_skill(self, mock_api_wrapper_class, mock_arxiv_class):
        """测试创建 Arxiv 搜索 Skill"""
        from src.skills.builtin.langchain_tools import create_arxiv_search_skill
        
        mock_wrapper = Mock()
        mock_api_wrapper_class.return_value = mock_wrapper
        
        mock_tool = Mock()
        mock_tool.name = "arxiv"
        mock_arxiv_class.return_value = mock_tool
        
        skill = create_arxiv_search_skill(top_k_results=5)
        
        assert skill is not None
        assert skill.name == "lc_arxiv"
        mock_api_wrapper_class.assert_called_once_with(
            top_k_results=5,
            load_max_docs=3,
        )
    
    @patch("src.skills.builtin.langchain_tools.WikipediaQueryRun")
    @patch("src.skills.builtin.langchain_tools.WikipediaAPIWrapper")
    def test_create_wikipedia_search_skill(self, mock_api_wrapper_class, mock_wiki_class):
        """测试创建 Wikipedia 搜索 Skill"""
        from src.skills.builtin.langchain_tools import create_wikipedia_search_skill
        
        mock_wrapper = Mock()
        mock_api_wrapper_class.return_value = mock_wrapper
        
        mock_tool = Mock()
        mock_tool.name = "wikipedia"
        mock_wiki_class.return_value = mock_tool
        
        skill = create_wikipedia_search_skill(top_k_results=5, lang="en")
        
        assert skill is not None
        mock_api_wrapper_class.assert_called_once_with(
            top_k_results=5,
            lang="en",
        )
    
    @patch("src.skills.builtin.langchain_tools.PythonREPLTool")
    def test_create_python_repl_skill(self, mock_python_class):
        """测试创建 Python REPL Skill"""
        from src.skills.builtin.langchain_tools import create_python_repl_skill
        
        mock_tool = Mock()
        mock_tool.name = "python_repl"
        mock_python_class.return_value = mock_tool
        
        skill = create_python_repl_skill()
        
        assert skill is not None
        assert skill.name == "lc_python_repl"


class TestGetResearchTools:
    """测试获取研究 Tools"""
    
    @patch("src.skills.builtin.langchain_tools.create_tavily_search_skill")
    @patch("src.skills.builtin.langchain_tools.create_arxiv_search_skill")
    @patch("src.skills.builtin.langchain_tools.create_wikipedia_search_skill")
    @patch("src.skills.builtin.langchain_tools.create_python_repl_skill")
    def test_get_research_tools_all_available(
        self, mock_python, mock_wiki, mock_arxiv, mock_tavily
    ):
        """测试获取所有可用 Tools"""
        from src.skills.builtin.langchain_tools import (
            get_research_tools,
            clear_research_tools_cache,
        )
        
        # 清除缓存
        clear_research_tools_cache()
        
        # 设置 Mock 返回值
        mock_tavily.return_value = Mock(name="tavily_skill")
        mock_arxiv.return_value = Mock(name="arxiv_skill")
        mock_wiki.return_value = Mock(name="wiki_skill")
        mock_python.return_value = Mock(name="python_skill")
        
        tools = get_research_tools()
        
        assert len(tools) == 4
        assert "web_search" in tools
        assert "academic_search" in tools
        assert "wiki_search" in tools
        assert "data_analysis" in tools
    
    @patch("src.skills.builtin.langchain_tools.create_tavily_search_skill")
    @patch("src.skills.builtin.langchain_tools.create_arxiv_search_skill")
    def test_get_research_tools_partial_available(
        self, mock_arxiv, mock_tavily
    ):
        """测试部分 Tools 可用"""
        from src.skills.builtin.langchain_tools import (
            get_research_tools,
            clear_research_tools_cache,
        )
        
        clear_research_tools_cache()
        
        mock_tavily.return_value = Mock(name="tavily_skill")
        mock_arxiv.return_value = None  # 不可用
        
        tools = get_research_tools()
        
        assert "web_search" in tools
        assert "academic_search" not in tools
    
    @patch("src.skills.builtin.langchain_tools.create_tavily_search_skill")
    def test_get_research_tools_caching(self, mock_tavily):
        """测试 Tools 缓存"""
        from src.skills.builtin.langchain_tools import (
            get_research_tools,
            clear_research_tools_cache,
        )
        
        clear_research_tools_cache()
        
        mock_skill = Mock(name="tavily_skill")
        mock_tavily.return_value = mock_skill
        
        # 第一次调用
        tools1 = get_research_tools()
        # 第二次调用（应该使用缓存）
        tools2 = get_research_tools()
        
        # 验证只创建了一次
        mock_tavily.assert_called_once()
        assert tools1 is tools2


class TestListAvailableTools:
    """测试列出可用 Tools"""
    
    def test_list_available_tools(self):
        """测试列出 Tools 状态"""
        from src.skills.builtin.langchain_tools import list_available_tools
        
        status = list_available_tools()
        
        assert isinstance(status, dict)
        assert len(status) >= 4
        
        # 检查是否包含预期的 Tools
        tool_names = ["web_search", "academic_search", "wiki_search", "data_analysis"]
        for name in tool_names:
            matching = [k for k in status.keys() if name in k.lower()]
            assert len(matching) > 0, f"Expected tool {name} not found"


class TestQuickSearchFunctions:
    """测试快速搜索函数"""
    
    @pytest.mark.asyncio
    @patch("src.skills.builtin.langchain_tools.get_research_tools")
    async def test_quick_web_search_success(self, mock_get_tools):
        """测试快速网页搜索成功"""
        from src.skills.builtin.langchain_tools import quick_web_search
        
        mock_skill = Mock()
        mock_skill.execute = AsyncMock(return_value={
            "success": True,
            "content": "search results"
        })
        
        mock_get_tools.return_value = {"web_search": mock_skill}
        
        result = await quick_web_search("AI market", max_results=5)
        
        assert result["success"] is True
        mock_skill.execute.assert_called_once_with(query="AI market")
    
    @pytest.mark.asyncio
    @patch("src.skills.builtin.langchain_tools.get_research_tools")
    async def test_quick_web_search_not_available(self, mock_get_tools):
        """测试快速网页搜索 Tool 不可用"""
        from src.skills.builtin.langchain_tools import quick_web_search
        
        mock_get_tools.return_value = {}  # 没有 web_search
        
        result = await quick_web_search("AI market")
        
        assert result["success"] is False
        assert "not available" in result["error"]
    
    @pytest.mark.asyncio
    @patch("src.skills.builtin.langchain_tools.get_research_tools")
    async def test_quick_academic_search_success(self, mock_get_tools):
        """测试快速学术搜索成功"""
        from src.skills.builtin.langchain_tools import quick_academic_search
        
        mock_skill = Mock()
        mock_skill.execute = AsyncMock(return_value={
            "success": True,
            "content": "paper results"
        })
        
        mock_get_tools.return_value = {"academic_search": mock_skill}
        
        result = await quick_academic_search("machine learning", top_k=5)
        
        assert result["success"] is True
        mock_skill.execute.assert_called_once_with(query="machine learning")


class TestClearCache:
    """测试缓存清除"""
    
    @patch("src.skills.builtin.langchain_tools._RESEARCH_TOOLS_CACHE", {"test": "data"})
    def test_clear_research_tools_cache(self):
        """测试清除缓存"""
        from src.skills.builtin.langchain_tools import (
            clear_research_tools_cache,
            _RESEARCH_TOOLS_CACHE,
        )
        
        clear_research_tools_cache()
        
        assert _RESEARCH_TOOLS_CACHE is None
