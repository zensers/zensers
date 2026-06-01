# -*- coding: utf-8 -*-
"""
MCP 集成测试模块
================

Phase 5 Week 19: MCP 基础架构 - 集成测试

测试 MCP 系统的整体功能:
- 配置加载
- Server/Client 连接
- 工具注册和调用
- 事件处理
"""

import pytest
import tempfile
import os
from pathlib import Path

from src.core.mcp.config import (
    MCPConfig,
    ToolConfig,
    DataSourceConfig,
    ConfigLoader,
    ToolType,
    DataSourceType,
    load_config,
    get_default_config,
)
from src.core.mcp.server import MCPServer, ServerState, Response
from src.core.mcp.client import MCPClient, ClientState, ClientConfig
from src.core.mcp.tool_registry import ToolRegistry, Tool, create_default_registry


# ============================================
# Mock 工具
# ============================================

class MockTool(Tool):
    """测试 Mock 工具"""
    
    def __init__(self, name: str = "mock_tool"):
        super().__init__(
            name=name,
            description="Mock tool for testing",
            parameters={
                "input": {
                    "type": "string",
                    "description": "Input string",
                    "required": True,
                },
            },
            permissions=["test_permission"],
        )
    
    def execute(self, context, params):
        return {"output": params.get("input", "")}


# ============================================
# 配置测试
# ============================================

class TestMCPConfig:
    """MCP 配置测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = get_default_config()
        
        assert config.version == "2.0"
        assert len(config.tools) > 0
        assert len(config.servers) > 0
    
    def test_config_to_dict(self):
        """测试配置序列化"""
        config = MCPConfig(
            version="1.0",
            tools=[
                ToolConfig(name="test_tool", type=ToolType.BUILTIN),
            ],
            data_sources=[
                DataSourceConfig(name="test_db", type=DataSourceType.SQLITE),
            ],
        )
        
        data = config.to_dict()
        
        assert data["version"] == "1.0"
        assert len(data["tools"]) == 1
        assert len(data["data_sources"]) == 1
    
    def test_config_from_dict(self):
        """测试配置反序列化"""
        data = {
            "version": "2.0",
            "tools": [
                {"name": "tool1", "type": "builtin"},
                {"name": "tool2", "type": "custom", "module": "my_module"},
            ],
            "data_sources": [
                {"name": "db1", "type": "postgres", "host": "localhost"},
            ],
        }
        
        config = MCPConfig.from_dict(data)
        
        assert config.version == "2.0"
        assert len(config.tools) == 2
        assert config.tools[0].type == ToolType.BUILTIN
        assert config.tools[1].module == "my_module"
    
    def test_get_enabled_tools(self):
        """测试获取启用的工具"""
        config = MCPConfig(
            tools=[
                ToolConfig(name="enabled_tool", type=ToolType.BUILTIN, enabled=True),
                ToolConfig(name="disabled_tool", type=ToolType.BUILTIN, enabled=False),
            ],
        )
        
        enabled = config.get_enabled_tools()
        
        assert len(enabled) == 1
        assert enabled[0].name == "enabled_tool"
    
    def test_get_tool(self):
        """测试获取工具配置"""
        config = MCPConfig(
            tools=[
                ToolConfig(name="my_tool", type=ToolType.BUILTIN),
            ],
        )
        
        tool = config.get_tool("my_tool")
        assert tool is not None
        assert tool.name == "my_tool"
        
        tool = config.get_tool("nonexistent")
        assert tool is None


class TestConfigLoader:
    """配置加载器测试"""
    
    def test_load_yaml_config(self):
        """测试加载 YAML 配置"""
        yaml_content = """
version: "2.0"
tools:
  - name: web_search
    type: builtin
    enabled: true
servers:
  - name: test_server
    transport: stdio
    command: python
settings:
  max_concurrent_tools: 5
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            loader = ConfigLoader(temp_path)
            config = loader.load()
            
            assert config.version == "2.0"
            assert len(config.tools) == 1
            assert config.tools[0].name == "web_search"
            assert config.settings.max_concurrent_tools == 5
            
        finally:
            os.unlink(temp_path)
    
    def test_load_json_config(self):
        """测试加载 JSON 配置"""
        json_content = """
{
    "version": "1.0",
    "tools": [
        {"name": "test_tool", "type": "builtin"}
    ],
    "data_sources": []
}
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(json_content)
            temp_path = f.name
        
        try:
            loader = ConfigLoader(temp_path)
            config = loader.load()
            
            assert config.version == "1.0"
            assert len(config.tools) == 1
            
        finally:
            os.unlink(temp_path)
    
    def test_load_nonexistent_file(self):
        """测试加载不存在文件"""
        loader = ConfigLoader("/nonexistent/config.yaml")
        config = loader.load()
        
        # 应返回默认配置
        assert config is not None
    
    def test_reload_config(self):
        """测试重载配置"""
        yaml_content = """
version: "1.0"
tools: []
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            loader = ConfigLoader(temp_path)
            config1 = loader.load()
            
            # 修改文件
            with open(temp_path, 'w') as f:
                f.write("version: \"2.0\"\ntools: []\n")
            
            config2 = loader.reload()
            
            assert config2.version == "2.0"
            
        finally:
            os.unlink(temp_path)


# ============================================
# Server 测试
# ============================================

class TestMCPServer:
    """MCP Server 测试"""
    
    def test_server_creation(self):
        """测试服务器创建"""
        server = MCPServer()
        
        assert server.state == ServerState.STOPPED
    
    def test_server_start_stop(self):
        """测试服务器启动和停止"""
        server = MCPServer()
        
        server.start()
        assert server.state == ServerState.RUNNING
        
        server.stop()
        assert server.state == ServerState.STOPPED
    
    def test_server_register_handler(self):
        """测试注册处理器"""
        server = MCPServer()
        server.start()
        
        def my_handler(context, params):
            return {"result": "ok"}
        
        server.register_handler("test_handler", my_handler)
        
        stats = server.get_stats()
        assert stats["handlers_registered"] == 1
    
    def test_server_register_tool(self):
        """测试注册工具"""
        registry = create_default_registry()
        server = MCPServer(tool_registry=registry)
        server.start()
        
        # 内置工具应已存在
        tools = server.list_tools()
        assert len(tools) >= 2  # web_search, knowledge_query
    
    def test_server_handle_request(self):
        """测试处理请求"""
        registry = ToolRegistry()
        registry.register(MockTool())
        
        server = MCPServer(tool_registry=registry)
        server.start()
        
        request = {
            "request_id": "test-123",
            "tool": "mock_tool",
            "params": {"input": "hello"},
        }
        
        response = server.handle_request(request)
        
        assert response.success is True
        assert response.result["output"] == "hello"
    
    def test_server_handle_request_unknown_tool(self):
        """测试处理请求 - 未知工具"""
        server = MCPServer()
        server.start()
        
        request = {
            "request_id": "test-123",
            "tool": "unknown_tool",
            "params": {},
        }
        
        response = server.handle_request(request)
        
        assert response.success is False
        assert "未知工具" in response.error
    
    def test_server_handle_request_server_not_running(self):
        """测试处理请求 - 服务器未运行"""
        server = MCPServer()
        
        request = {
            "request_id": "test-123",
            "tool": "mock_tool",
            "params": {},
        }
        
        response = server.handle_request(request)
        
        assert response.success is False
        assert "未运行" in response.error
    
    def test_server_stats(self):
        """测试服务器统计"""
        registry = ToolRegistry()
        registry.register(MockTool())
        
        server = MCPServer(tool_registry=registry)
        server.start()
        
        # 执行几次请求
        server.handle_request({"tool": "mock_tool", "params": {"input": "test1"}})
        server.handle_request({"tool": "mock_tool", "params": {"input": "test2"}})
        server.handle_request({"tool": "unknown", "params": {}})  # 失败
        
        stats = server.get_stats()
        
        assert stats["total_requests"] == 3
        assert stats["successful_requests"] == 2
        assert stats["failed_requests"] == 1
    
    def test_server_event_listener(self):
        """测试事件监听"""
        server = MCPServer()
        
        events = []
        
        def listener(event):
            events.append(event)
        
        server.add_event_listener(listener)
        server.start()
        
        assert len(events) == 1
        assert events[0]["type"] == "server_started"
        
        server.stop()
        
        assert len(events) == 2
        assert events[1]["type"] == "server_stopped"


# ============================================
# Client 测试
# ============================================

class TestMCPClient:
    """MCP Client 测试"""
    
    def test_client_creation(self):
        """测试客户端创建"""
        client = MCPClient()
        
        assert client.state == ClientState.DISCONNECTED
    
    def test_client_connect_disconnect(self):
        """测试客户端连接和断开"""
        client = MCPClient()
        
        client.connect()
        assert client.state == ClientState.CONNECTED
        
        client.disconnect()
        assert client.state == ClientState.DISCONNECTED
    
    def test_client_context_manager(self):
        """测试客户端上下文管理器"""
        with MCPClient() as client:
            assert client.state == ClientState.CONNECTED
        
        assert client.state == ClientState.DISCONNECTED
    
    def test_client_connect_to_server(self):
        """测试连接到服务器"""
        registry = ToolRegistry()
        registry.register(MockTool())
        
        server = MCPServer(tool_registry=registry)
        client = MCPClient(server=server)
        
        client.connect()
        
        assert client.state == ClientState.CONNECTED
        assert server.state == ServerState.RUNNING
    
    def test_client_call_tool(self):
        """测试调用工具"""
        registry = ToolRegistry()
        registry.register(MockTool())
        
        server = MCPServer(tool_registry=registry)
        client = MCPClient(server=server)
        
        client.connect()
        
        response = client.call_tool("mock_tool", {"input": "test"})
        
        assert response["success"] is True
        assert response["result"]["output"] == "test"
    
    def test_client_call_tool_not_connected(self):
        """测试调用工具 - 未连接"""
        client = MCPClient()
        
        response = client.call_tool("mock_tool", {"input": "test"})
        
        assert response["success"] is False
        assert "未连接" in response["error"]
    
    def test_client_list_tools(self):
        """测试列出工具"""
        registry = create_default_registry()
        server = MCPServer(tool_registry=registry)
        client = MCPClient(server=server)
        
        client.connect()
        
        tools = client.list_tools()
        
        assert len(tools) >= 2
    
    def test_client_stats(self):
        """测试客户端统计"""
        registry = ToolRegistry()
        registry.register(MockTool())
        
        server = MCPServer(tool_registry=registry)
        client = MCPClient(server=server)
        client.connect()
        
        # 执行几次调用
        client.call_tool("mock_tool", {"input": "test1"})
        client.call_tool("mock_tool", {"input": "test2"})
        client.call_tool("unknown", {})  # 失败
        
        stats = client.get_stats()
        
        assert stats["total_calls"] == 3
        assert stats["successful_calls"] == 2
        assert stats["failed_calls"] == 1


# ============================================
# 集成测试
# ============================================

class TestMCPIntegration:
    """MCP 集成测试"""
    
    def test_full_flow(self):
        """测试完整流程"""
        # 1. 创建配置
        config = MCPConfig(
            tools=[
                ToolConfig(name="mock_tool", type=ToolType.BUILTIN, enabled=True),
            ],
        )
        
        # 2. 创建工具注册表
        registry = ToolRegistry()
        registry.register(MockTool())
        
        # 3. 创建服务器
        server = MCPServer(config=config, tool_registry=registry)
        
        # 4. 创建客户端
        client = MCPClient(server=server)
        
        # 5. 连接
        client.connect()
        
        # 6. 调用工具
        response = client.call_tool("mock_tool", {"input": "integration test"})
        
        assert response["success"] is True
        assert response["result"]["output"] == "integration test"
        
        # 7. 清理
        client.disconnect()
        server.stop()
    
    def test_config_driven_tools(self):
        """测试配置驱动工具加载"""
        # 创建配置
        yaml_content = """
version: "1.0"
tools:
  - name: mock_tool
    type: builtin
    enabled: true
settings:
  tool_timeout_seconds: 30
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name
        
        try:
            # 加载配置
            config = load_config(temp_path)
            
            # 创建注册表和服务器
            registry = ToolRegistry()
            registry.register(MockTool())
            
            server = MCPServer(config=config, tool_registry=registry)
            server.start()
            
            # 配置中的工具应可用
            tool_config = config.get_tool("mock_tool")
            assert tool_config is not None
            assert tool_config.enabled
            
        finally:
            os.unlink(temp_path)
    
    def test_multiple_clients(self):
        """测试多个客户端"""
        registry = ToolRegistry()
        registry.register(MockTool())
        
        server = MCPServer(tool_registry=registry)
        server.start()
        
        # 创建多个客户端
        client1 = MCPClient(server=server)
        client2 = MCPClient(server=server)
        
        client1.connect()
        client2.connect()
        
        # 两个客户端都应能调用工具
        response1 = client1.call_tool("mock_tool", {"input": "client1"})
        response2 = client2.call_tool("mock_tool", {"input": "client2"})
        
        assert response1["result"]["output"] == "client1"
        assert response2["result"]["output"] == "client2"
        
        # 服务器统计应反映所有调用
        stats = server.get_stats()
        assert stats["total_requests"] == 2
    
    def test_error_handling(self):
        """测试错误处理"""
        registry = ToolRegistry()
        
        # 创建会抛出异常的工具
        class ErrorTool(Tool):
            def __init__(self):
                super().__init__(
                    name="error_tool",
                    description="Tool that throws error",
                    parameters={},
                )
            
            def execute(self, context, params):
                raise ValueError("Test error")
        
        registry.register(ErrorTool())
        
        server = MCPServer(tool_registry=registry)
        client = MCPClient(server=server)
        
        client.connect()
        
        response = client.call_tool("error_tool", {})
        
        assert response["success"] is False
        assert "Test error" in response["error"]


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])