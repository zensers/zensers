"""
LangChain 适配器单元测试

测试 LangChainToolSkill 和 LangChainAdapter 的核心功能。
使用 Mock 避免实际 API 调用。
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio


class TestLangChainToolSkill:
    """测试 LangChain Tool Skill 适配器"""
    
    @pytest.fixture
    def mock_langchain_tool(self):
        """创建 Mock LangChain Tool"""
        tool = Mock()
        tool.name = "test_tool"
        tool.description = "A test tool for unit testing"
        tool.ainvoke = AsyncMock(return_value="test result")
        return tool
    
    @pytest.fixture
    def mock_langchain_tool_sync(self):
        """创建 Mock 同步 LangChain Tool"""
        tool = Mock()
        tool.name = "sync_tool"
        tool.description = "A sync test tool"
        # 没有 ainvoke，只有 invoke
        tool.invoke = Mock(return_value="sync result")
        return tool
    
    @pytest.mark.asyncio
    async def test_skill_initialization(self, mock_langchain_tool):
        """测试 Skill 初始化"""
        from src.skills.adapters import LangChainToolSkill
        from src.skills.base import SkillConfig
        
        skill = LangChainToolSkill(mock_langchain_tool)
        
        assert skill.name == "lc_test_tool"
        assert skill.description == "A test tool for unit testing"
        assert skill.config.name == "lc_test_tool"
        assert skill.config.enabled is True
    
    @pytest.mark.asyncio
    async def test_skill_with_custom_config(self, mock_langchain_tool):
        """测试使用自定义配置初始化"""
        from src.skills.adapters import LangChainToolSkill
        from src.skills.base import SkillConfig
        
        config = SkillConfig(
            name="custom_name",
            version="2.0.0",
            enabled=False
        )
        skill = LangChainToolSkill(mock_langchain_tool, config)
        
        assert skill.name == "custom_name"
        assert skill.config.enabled is False
        assert skill.config.version == "2.0.0"
    
    @pytest.mark.asyncio
    async def test_execute_async_tool(self, mock_langchain_tool):
        """测试执行异步 Tool"""
        from src.skills.adapters import LangChainToolSkill
        
        skill = LangChainToolSkill(mock_langchain_tool)
        result = await skill.execute(query="test query")
        
        assert result["success"] is True
        assert result["message"] == "Tool 'test_tool' executed successfully"
        assert result["raw_result"] == "test result"
        assert result["content"] == "test result"
        
        # 验证 Tool 被正确调用
        mock_langchain_tool.ainvoke.assert_called_once_with({"query": "test query"})
    
    @pytest.mark.asyncio
    async def test_execute_sync_tool(self, mock_langchain_tool_sync):
        """测试执行同步 Tool"""
        from src.skills.adapters import LangChainToolSkill
        
        skill = LangChainToolSkill(mock_langchain_tool_sync)
        result = await skill.execute(data="test data")
        
        assert result["success"] is True
        assert result["raw_result"] == "sync result"
    
    @pytest.mark.asyncio
    async def test_execute_with_dict_result(self, mock_langchain_tool):
        """测试 Tool 返回字典结果"""
        from src.skills.adapters import LangChainToolSkill
        
        mock_langchain_tool.ainvoke = AsyncMock(
            return_value={"title": "Test", "content": "Result"}
        )
        
        skill = LangChainToolSkill(mock_langchain_tool)
        result = await skill.execute()
        
        assert result["success"] is True
        assert result["title"] == "Test"
        assert result["content"] == "Result"
    
    @pytest.mark.asyncio
    async def test_execute_with_object_result(self, mock_langchain_tool):
        """测试 Tool 返回对象结果"""
        from src.skills.adapters import LangChainToolSkill
        
        class MockResult:
            content = "object content"
            metadata = {"key": "value"}
        
        mock_langchain_tool.ainvoke = AsyncMock(return_value=MockResult())
        
        skill = LangChainToolSkill(mock_langchain_tool)
        result = await skill.execute()
        
        assert result["success"] is True
        assert result["content"] == "object content"
    
    @pytest.mark.asyncio
    async def test_execute_error_handling(self, mock_langchain_tool):
        """测试错误处理"""
        from src.skills.adapters import LangChainToolSkill
        
        mock_langchain_tool.ainvoke = AsyncMock(
            side_effect=Exception("API Error")
        )
        
        skill = LangChainToolSkill(mock_langchain_tool)
        result = await skill.execute()
        
        assert result["success"] is False
        assert result["error"] == "API Error"
        assert "failed" in result["message"]
    
    def test_get_schema(self, mock_langchain_tool):
        """测试获取参数 Schema"""
        from src.skills.adapters import LangChainToolSkill
        
        # 模拟 args_schema
        mock_schema = Mock()
        mock_schema.schema.return_value = {"type": "object", "properties": {}}
        mock_langchain_tool.args_schema = mock_schema
        
        skill = LangChainToolSkill(mock_langchain_tool)
        schema = skill.get_schema()
        
        assert schema == {"type": "object", "properties": {}}
    
    def test_langchain_tool_property(self, mock_langchain_tool):
        """测试获取底层 Tool"""
        from src.skills.adapters import LangChainToolSkill
        
        skill = LangChainToolSkill(mock_langchain_tool)
        assert skill.langchain_tool == mock_langchain_tool


class TestLangChainAdapter:
    """测试 LangChain 适配器管理器"""
    
    @pytest.fixture
    def adapter(self):
        """创建适配器实例"""
        from src.skills.adapters import LangChainAdapter
        return LangChainAdapter()
    
    @pytest.fixture
    def mock_tool(self):
        """创建 Mock Tool"""
        tool = Mock()
        tool.name = "mock_tool"
        tool.description = "Mock tool description"
        tool.ainvoke = AsyncMock(return_value="result")
        return tool
    
    def test_register_tool(self, adapter, mock_tool):
        """测试注册 Tool"""
        skill = adapter.register_tool(mock_tool)
        
        assert skill.name == "lc_mock_tool"
        assert "lc_mock_tool" in adapter.list_skills()
    
    def test_register_tool_with_custom_name(self, adapter, mock_tool):
        """测试使用自定义名称注册"""
        skill = adapter.register_tool(mock_tool, name="custom_tool")
        
        assert skill.name == "custom_tool"
        assert adapter.get_skill("custom_tool") == skill
    
    def test_get_skill_not_found(self, adapter):
        """测试获取不存在的 Skill"""
        assert adapter.get_skill("nonexistent") is None
    
    def test_list_skills(self, adapter, mock_tool):
        """测试列出所有 Skills"""
        adapter.register_tool(mock_tool, name="tool1")
        adapter.register_tool(mock_tool, name="tool2")
        
        skills = adapter.list_skills()
        assert len(skills) == 2
        assert "tool1" in skills
        assert "tool2" in skills
    
    def test_clear(self, adapter, mock_tool):
        """测试清空 Skills"""
        adapter.register_tool(mock_tool, name="tool1")
        adapter.clear()
        
        assert len(adapter.list_skills()) == 0
    
    @patch("src.skills.adapters.langchain_adapter.TavilySearchResults")
    @patch("src.skills.adapters.langchain_adapter.ArxivQueryRun")
    @patch("src.skills.adapters.langchain_adapter.WikipediaQueryRun")
    @patch("src.skills.adapters.langchain_adapter.PythonREPLTool")
    def test_register_research_tools(
        self, mock_python, mock_wiki, mock_arxiv, mock_tavily, adapter
    ):
        """测试批量注册研究 Tools"""
        # 配置 Mock
        mock_tavily.return_value = Mock(name="tavily", description="Search")
        mock_arxiv.return_value = Mock(name="arxiv", description="Papers")
        mock_wiki.return_value = Mock(name="wikipedia", description="Wiki")
        mock_python.return_value = Mock(name="python", description="REPL")
        
        count = adapter.register_research_tools()
        
        assert count == 4
        skills = adapter.list_skills()
        assert len(skills) == 4


class TestLangChainAdapterIntegration:
    """集成测试 - 验证与真实 LangChain 的集成"""
    
    @pytest.mark.skipif(
        not pytest.importorskip("langchain_core", reason="LangChain not installed"),
        reason="LangChain not installed"
    )
    def test_langchain_import(self):
        """测试 LangChain 导入"""
        from langchain_core.tools import BaseTool
        from src.skills.adapters import LangChainToolSkill
        
        assert LANGCHAIN_AVAILABLE is True


# 辅助：检查 LangChain 是否可用
try:
    from langchain_core.tools import BaseTool
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
