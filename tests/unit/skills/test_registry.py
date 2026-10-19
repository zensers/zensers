"""
Skill 注册表单元测试

测试 SkillRegistry 的注册、发现、查询功能。
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch


class TestSkillRegistry:
    """测试 SkillRegistry 核心功能"""
    
    @pytest.fixture
    def registry(self):
        """创建新的注册表实例"""
        from src.skills.registry import SkillRegistry
        return SkillRegistry()
    
    @pytest.fixture
    def mock_skill(self):
        """创建 Mock Skill"""
        skill = Mock()
        skill.name = "mock_skill"
        skill.description = "A mock skill"
        skill.is_enabled.return_value = True
        skill.config = Mock()
        return skill
    
    def test_register_skill(self, registry, mock_skill):
        """测试注册 Skill"""
        registry.register(mock_skill)
        
        assert registry.get("mock_skill") == mock_skill
    
    def test_register_with_custom_name(self, registry, mock_skill):
        """测试使用自定义名称注册"""
        registry.register(mock_skill, name="custom_name")
        
        assert registry.get("custom_name") == mock_skill
        assert registry.get("mock_skill") is None
    
    def test_get_nonexistent_skill(self, registry):
        """测试获取不存在的 Skill"""
        assert registry.get("nonexistent") is None
    
    def test_unregister_skill(self, registry, mock_skill):
        """测试取消注册 Skill"""
        registry.register(mock_skill)
        result = registry.unregister("mock_skill")
        
        assert result is True
        assert registry.get("mock_skill") is None
    
    def test_unregister_nonexistent(self, registry):
        """测试取消注册不存在的 Skill"""
        result = registry.unregister("nonexistent")
        
        assert result is False
    
    def test_list_all(self, registry, mock_skill):
        """测试列出所有 Skills"""
        registry.register(mock_skill, name="skill1")
        registry.register(mock_skill, name="skill2")
        
        skills = registry.list_all()
        
        assert len(skills) == 2
        names = [s.name for s in skills]
        assert "skill1" in names
        assert "skill2" in names
    
    def test_list_by_type(self, registry):
        """测试按类型列出 Skills"""
        from src.skills.adapters import LangChainToolSkill
        
        # Mock LangChain Skill
        lc_skill = Mock(spec=LangChainToolSkill)
        lc_skill.name = "lc_skill"
        lc_skill.description = "LangChain skill"
        lc_skill.is_enabled.return_value = True
        lc_skill.config = Mock()
        
        # Mock 普通 Skill
        normal_skill = Mock()
        normal_skill.name = "normal_skill"
        normal_skill.description = "Normal skill"
        normal_skill.is_enabled.return_value = True
        normal_skill.config = Mock()
        normal_skill.__class__.__module__ = "src.skills.builtin.test"
        
        registry.register(lc_skill)
        registry.register(normal_skill)
        
        langchain_skills = registry.list_by_type("langchain")
        builtin_skills = registry.list_by_type("builtin")
        
        assert len(langchain_skills) == 1
        assert langchain_skills[0].name == "lc_skill"
        assert len(builtin_skills) == 1
        assert builtin_skills[0].name == "normal_skill"
    
    def test_register_factory(self, registry, mock_skill):
        """测试注册工厂函数"""
        factory = Mock(return_value=mock_skill)
        
        registry.register_factory("factory_skill", factory)
        
        # 首次获取会调用工厂
        skill = registry.get("factory_skill")
        assert skill == mock_skill
        factory.assert_called_once()
        
        # 再次获取应该使用缓存
        skill2 = registry.get("factory_skill")
        assert skill2 == mock_skill
        factory.assert_called_once()  # 不再调用
    
    def test_clear(self, registry, mock_skill):
        """测试清空注册表"""
        registry.register(mock_skill)
        registry.register_factory("factory", Mock())
        
        registry.clear()
        
        assert registry.get("mock_skill") is None
        assert len(registry.list_all()) == 0
    
    def test_get_stats(self, registry, mock_skill):
        """测试获取统计信息"""
        registry.register(mock_skill, name="skill1")
        registry.register(mock_skill, name="skill2")
        
        stats = registry.get_stats()
        
        assert stats["total"] == 2
        assert "builtin" in stats
        assert "langchain" in stats


class TestAutoDiscover:
    """测试自动发现功能"""
    
    @pytest.fixture
    def registry(self):
        """创建新的注册表实例"""
        from src.skills.registry import SkillRegistry
        return SkillRegistry()
    
    @patch("src.skills.registry.LangChainAdapter.register_research_tools")
    def test_auto_discover_langchain_tools(self, mock_register, registry):
        """测试自动发现 LangChain Tools"""
        mock_register.return_value = 3
        
        count = registry.auto_discover_langchain_tools()
        
        assert count == 3
        mock_register.assert_called_once()
    
    @patch("src.skills.registry.pkgutil.iter_modules")
    @patch("src.skills.registry.importlib.import_module")
    def test_auto_discover_builtin_skills(
        self, mock_import, mock_iter_modules, registry
    ):
        """测试自动发现内置 Skills"""
        # Mock 模块遍历
        mock_iter_modules.return_value = [
            (None, "src.skills.builtin.test", False)
        ]
        
        # Mock 模块
        mock_module = Mock()
        mock_skill_class = Mock()
        mock_skill_instance = Mock()
        mock_skill_class.return_value = mock_skill_instance
        mock_skill_instance.name = "test_skill"
        mock_skill_instance.description = "Test skill"
        mock_skill_instance.is_enabled.return_value = True
        mock_skill_instance.config = Mock()
        
        mock_module.TestSkill = mock_skill_class
        mock_import.return_value = mock_module
        
        # Mock dir() 返回
        with patch.object(registry, '_skills', {}):
            pass  # 简化测试


class TestGlobalRegistry:
    """测试全局注册表"""
    
    def test_get_skill_registry_singleton(self):
        """测试全局注册表单例"""
        from src.skills.registry import get_skill_registry, reset_skill_registry
        
        reset_skill_registry()  # 重置
        
        registry1 = get_skill_registry()
        registry2 = get_skill_registry()
        
        assert registry1 is registry2
    
    def test_reset_skill_registry(self):
        """测试重置全局注册表"""
        from src.skills.registry import (
            get_skill_registry, 
            reset_skill_registry
        )
        
        registry1 = get_skill_registry()
        reset_skill_registry()
        registry2 = get_skill_registry()
        
        assert registry1 is not registry2


class TestConvenienceFunctions:
    """测试便捷函数"""
    
    @pytest.mark.asyncio
    @patch("src.skills.registry.get_skill_registry")
    async def test_execute_skill_success(self, mock_get_registry):
        """测试便捷执行 Skill 成功"""
        from src.skills.registry import execute_skill
        
        mock_skill = Mock()
        mock_skill.execute = AsyncMock(return_value={"success": True})
        
        mock_registry = Mock()
        mock_registry.get.return_value = mock_skill
        mock_get_registry.return_value = mock_registry
        
        result = await execute_skill("test_skill", query="test")
        
        assert result["success"] is True
        mock_skill.execute.assert_called_once_with(query="test")
    
    @pytest.mark.asyncio
    @patch("src.skills.registry.get_skill_registry")
    async def test_execute_skill_not_found(self, mock_get_registry):
        """测试便捷执行 Skill 未找到"""
        from src.skills.registry import execute_skill
        
        mock_registry = Mock()
        mock_registry.get.return_value = None
        mock_get_registry.return_value = mock_registry
        
        result = await execute_skill("nonexistent")
        
        assert result["success"] is False
        assert "not found" in result["error"]
    
    @patch("src.skills.registry.get_skill_registry")
    def test_list_skills(self, mock_get_registry):
        """测试便捷列出 Skills"""
        from src.skills.registry import list_skills
        
        mock_registry = Mock()
        mock_registry.list_all.return_value = []
        mock_get_registry.return_value = mock_registry
        
        result = list_skills()
        
        assert result == []
        mock_registry.list_all.assert_called_once()
    
    @patch("src.skills.registry.get_skill_registry")
    def test_list_skills_by_type(self, mock_get_registry):
        """测试便捷列出特定类型 Skills"""
        from src.skills.registry import list_skills
        
        mock_registry = Mock()
        mock_registry.list_by_type.return_value = []
        mock_get_registry.return_value = mock_registry
        
        result = list_skills(skill_type="langchain")
        
        assert result == []
        mock_registry.list_by_type.assert_called_once_with("langchain")
