# -*- coding: utf-8 -*-
"""
ToolRegistry 测试模块
=====================

Phase 5 Week 19: MCP 基础架构 - 工具注册表测试

TDD 测试用例:
- Tool 类测试
- ToolRegistry 注册/查找测试
- 权限验证测试
- 参数验证测试
"""

import pytest
from typing import Dict, Any, Optional
from dataclasses import dataclass

# 测试目标
from src.core.mcp.tool_registry import Tool, ToolRegistry, ToolMetadata


class MockTool(Tool):
    """测试用 Mock 工具"""
    
    def __init__(
        self,
        name: str = "mock_tool",
        description: str = "Mock tool for testing",
        permissions: Optional[list] = None
    ):
        super().__init__(
            name=name,
            description=description,
            parameters={
                "query": {
                    "type": "string",
                    "description": "Search query",
                    "required": True,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "required": False,
                    "default": 10,
                },
            },
            permissions=permissions or [],
        )
        self._call_count = 0
        self._last_params = None
    
    def execute(self, context: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具"""
        self._call_count += 1
        self._last_params = params
        
        # 模拟返回结果
        return {
            "results": [f"result_{i}" for i in range(params.get("limit", 10))],
            "query": params.get("query", ""),
        }
    
    def get_call_count(self) -> int:
        """获取调用次数"""
        return self._call_count
    
    def get_last_params(self) -> Optional[Dict[str, Any]]:
        """获取最后一次调用参数"""
        return self._last_params


class TestTool:
    """Tool 类测试"""
    
    def test_tool_creation(self):
        """测试工具创建"""
        tool = MockTool()
        
        assert tool.name == "mock_tool"
        assert tool.description == "Mock tool for testing"
        assert "query" in tool.parameters
        assert tool.permissions == []
    
    def test_tool_with_permissions(self):
        """测试带权限的工具"""
        tool = MockTool(permissions=["read", "write"])
        
        assert tool.permissions == ["read", "write"]
    
    def test_tool_validate_params_success(self):
        """测试参数验证 - 成功"""
        tool = MockTool()
        
        # 提供必需参数
        errors = tool.validate_params({"query": "test"})
        assert errors == []
    
    def test_tool_validate_params_missing_required(self):
        """测试参数验证 - 缺少必需参数"""
        tool = MockTool()
        
        # 缺少必需参数
        errors = tool.validate_params({"limit": 5})
        assert len(errors) > 0
        assert "query" in str(errors[0])
    
    def test_tool_validate_params_wrong_type(self):
        """测试参数验证 - 类型错误"""
        tool = MockTool()
        
        # 类型错误
        errors = tool.validate_params({"query": "test", "limit": "not_a_number"})
        assert len(errors) > 0
    
    def test_tool_get_metadata(self):
        """测试获取元数据"""
        tool = MockTool()
        
        metadata = tool.get_metadata()
        
        assert metadata.name == "mock_tool"
        assert metadata.description == "Mock tool for testing"
        assert metadata.parameters == tool.parameters
    
    def test_tool_to_dict(self):
        """测试序列化"""
        tool = MockTool()
        
        data = tool.to_dict()
        
        assert data["name"] == "mock_tool"
        assert data["description"] == "Mock tool for testing"
        assert "parameters" in data


class TestToolRegistry:
    """ToolRegistry 测试"""
    
    def test_registry_creation(self):
        """测试注册表创建"""
        registry = ToolRegistry()
        
        assert registry.count() == 0
        assert registry.list_all() == []
    
    def test_register_tool(self):
        """测试注册工具"""
        registry = ToolRegistry()
        tool = MockTool()
        
        registry.register(tool)
        
        assert registry.count() == 1
        assert registry.get("mock_tool") is not None
    
    def test_register_duplicate_tool(self):
        """测试注册重复工具 - 应覆盖"""
        registry = ToolRegistry()
        
        tool1 = MockTool(description="First version")
        tool2 = MockTool(description="Second version")
        
        registry.register(tool1)
        registry.register(tool2)
        
        # 应覆盖第一个
        assert registry.count() == 1
        assert registry.get("mock_tool").description == "Second version"
    
    def test_unregister_tool(self):
        """测试注销工具"""
        registry = ToolRegistry()
        tool = MockTool()
        
        registry.register(tool)
        assert registry.count() == 1
        
        registry.unregister("mock_tool")
        assert registry.count() == 0
        assert registry.get("mock_tool") is None
    
    def test_unregister_nonexistent_tool(self):
        """测试注销不存在工具 - 不报错"""
        registry = ToolRegistry()
        
        # 不应报错
        registry.unregister("nonexistent")
        assert registry.count() == 0
    
    def test_get_tool(self):
        """测试获取工具"""
        registry = ToolRegistry()
        tool = MockTool()
        
        registry.register(tool)
        
        found = registry.get("mock_tool")
        assert found is not None
        assert found.name == "mock_tool"
    
    def test_get_nonexistent_tool(self):
        """测试获取不存在工具"""
        registry = ToolRegistry()
        
        found = registry.get("nonexistent")
        assert found is None
    
    def test_list_all_tools(self):
        """测试列出所有工具"""
        registry = ToolRegistry()
        
        tool1 = MockTool(name="tool1")
        tool2 = MockTool(name="tool2")
        tool3 = MockTool(name="tool3")
        
        registry.register(tool1)
        registry.register(tool2)
        registry.register(tool3)
        
        all_tools = registry.list_all()
        
        assert len(all_tools) == 3
        names = [t.name for t in all_tools]
        assert "tool1" in names
        assert "tool2" in names
        assert "tool3" in names
    
    def test_has_tool(self):
        """测试检查工具存在"""
        registry = ToolRegistry()
        tool = MockTool()
        
        assert not registry.has("mock_tool")
        
        registry.register(tool)
        assert registry.has("mock_tool")
    
    def test_clear_registry(self):
        """测试清空注册表"""
        registry = ToolRegistry()
        
        registry.register(MockTool(name="tool1"))
        registry.register(MockTool(name="tool2"))
        registry.register(MockTool(name="tool3"))
        
        assert registry.count() == 3
        
        registry.clear()
        assert registry.count() == 0
    
    def test_find_by_permission(self):
        """测试按权限查找工具"""
        registry = ToolRegistry()
        
        tool1 = MockTool(name="tool1", permissions=["read"])
        tool2 = MockTool(name="tool2", permissions=["read", "write"])
        tool3 = MockTool(name="tool3", permissions=["admin"])
        
        registry.register(tool1)
        registry.register(tool2)
        registry.register(tool3)
        
        # 查找有 read 权限的工具
        read_tools = registry.find_by_permission("read")
        
        assert len(read_tools) == 2
        names = [t.name for t in read_tools]
        assert "tool1" in names
        assert "tool2" in names
    
    def test_find_by_multiple_permissions(self):
        """测试按多权限查找"""
        registry = ToolRegistry()
        
        tool1 = MockTool(name="tool1", permissions=["read", "write"])
        tool2 = MockTool(name="tool2", permissions=["read"])
        tool3 = MockTool(name="tool3", permissions=["write", "admin"])
        
        registry.register(tool1)
        registry.register(tool2)
        registry.register(tool3)
        
        # 查找同时有 read 和 write 的工具
        tools = registry.find_by_permissions(["read", "write"])
        
        assert len(tools) == 1
        assert tools[0].name == "tool1"


class TestToolRegistryPermissions:
    """工具权限验证测试"""
    
    def test_check_permission_allowed(self):
        """测试权限检查 - 允许"""
        registry = ToolRegistry()
        tool = MockTool(permissions=["read", "write"])
        
        registry.register(tool)
        
        assert registry.check_permission("mock_tool", "read")
        assert registry.check_permission("mock_tool", "write")
    
    def test_check_permission_denied(self):
        """测试权限检查 - 拒绝"""
        registry = ToolRegistry()
        tool = MockTool(permissions=["read"])
        
        registry.register(tool)
        
        assert registry.check_permission("mock_tool", "read")
        assert not registry.check_permission("mock_tool", "write")
    
    def test_check_permission_nonexistent_tool(self):
        """测试权限检查 - 工具不存在"""
        registry = ToolRegistry()
        
        # 不存在的工具应拒绝所有权限
        assert not registry.check_permission("nonexistent", "read")
    
    def test_check_permissions_all_required(self):
        """测试检查多个权限 - 全部需要"""
        registry = ToolRegistry()
        tool = MockTool(permissions=["read", "write", "execute"])
        
        registry.register(tool)
        
        # 全部满足
        assert registry.check_permissions("mock_tool", ["read", "write"])
        
        # 不全部满足
        assert not registry.check_permissions("mock_tool", ["read", "admin"])
    
    def test_tool_without_permissions_allows_all(self):
        """测试无权限限制的工具"""
        registry = ToolRegistry()
        tool = MockTool(permissions=[])  # 无权限限制
        
        registry.register(tool)
        
        # 无权限限制的工具应允许所有访问
        assert registry.check_permission("mock_tool", "any_permission")


class TestToolRegistryValidation:
    """工具参数验证测试"""
    
    def test_validate_params_for_tool(self):
        """测试为工具验证参数"""
        registry = ToolRegistry()
        tool = MockTool()
        
        registry.register(tool)
        
        errors = registry.validate_params("mock_tool", {"query": "test"})
        assert errors == []
    
    def test_validate_params_missing_required(self):
        """测试验证参数 - 缺少必需参数"""
        registry = ToolRegistry()
        tool = MockTool()
        
        registry.register(tool)
        
        errors = registry.validate_params("mock_tool", {})
        assert len(errors) > 0
    
    def test_validate_params_nonexistent_tool(self):
        """测试验证参数 - 工具不存在"""
        registry = ToolRegistry()
        
        errors = registry.validate_params("nonexistent", {"query": "test"})
        assert len(errors) > 0
        assert "不存在" in str(errors[0]) or "not found" in str(errors[0]).lower()


class TestToolRegistryStats:
    """注册表统计测试"""
    
    def test_get_stats(self):
        """测试获取统计信息"""
        registry = ToolRegistry()
        
        registry.register(MockTool(name="tool1", permissions=["read"]))
        registry.register(MockTool(name="tool2", permissions=["write"]))
        registry.register(MockTool(name="tool3", permissions=[]))
        
        stats = registry.get_stats()
        
        assert stats["total_tools"] == 3
        assert stats["tools_with_permissions"] == 2
    
    def test_get_permission_stats(self):
        """测试获取权限统计"""
        registry = ToolRegistry()
        
        registry.register(MockTool(name="tool1", permissions=["read", "write"]))
        registry.register(MockTool(name="tool2", permissions=["read"]))
        registry.register(MockTool(name="tool3", permissions=["admin"]))
        
        perm_stats = registry.get_permission_stats()
        
        assert perm_stats["read"] == 2
        assert perm_stats["write"] == 1
        assert perm_stats["admin"] == 1


class TestToolExecutionThroughRegistry:
    """通过注册表执行工具测试"""
    
    def test_execute_tool(self):
        """测试通过注册表执行工具"""
        registry = ToolRegistry()
        tool = MockTool()
        
        registry.register(tool)
        
        result = registry.execute("mock_tool", None, {"query": "test", "limit": 5})
        
        assert result["success"] is True
        assert len(result["result"]["results"]) == 5
        assert tool.get_call_count() == 1
    
    def test_execute_nonexistent_tool(self):
        """测试执行不存在的工具"""
        registry = ToolRegistry()
        
        result = registry.execute("nonexistent", None, {})
        
        assert result["success"] is False
        assert "error" in result
    
    def test_execute_with_validation_failure(self):
        """测试执行 - 参数验证失败"""
        registry = ToolRegistry()
        tool = MockTool()
        
        registry.register(tool)
        
        # 缺少必需参数
        result = registry.execute("mock_tool", None, {})
        
        assert result["success"] is False
        assert "error" in result


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])