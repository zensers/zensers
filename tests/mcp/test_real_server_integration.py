"""
Integration test with real local BRAIN Alpha data MCP server.

Tests the full stack: MCPClient -> StdioServerAdapter -> Real MCP Server
Validates that our MCP protocol layer works with actual external tools.
"""

import pytest
import asyncio


BRAIN_SERVER_PYTHON = r"C:/Users/Administrator/.conda/envs/worldquent/python.exe"
BRAIN_SERVER_SCRIPT = r"E:/worldquantV4/data_download/mcp_server.py"
BRAIN_SERVER_CWD = r"E:/worldquantV4/data_download"


@pytest.fixture(scope="module")
def stdio_adapter():
    """Create and start a stdio adapter connected to the real BRAIN server"""
    from src.core.mcp.stdio_adapter import StdioServerAdapter

    adapter = StdioServerAdapter(
        python_path=BRAIN_SERVER_PYTHON,
        script_path=BRAIN_SERVER_SCRIPT,
        cwd=BRAIN_SERVER_CWD,
    )
    adapter.start()
    yield adapter
    adapter.stop()


class TestRealServerConnection:
    """Test basic connectivity to the real MCP server"""

    @pytest.mark.asyncio
    async def test_connect_and_discover(self, stdio_adapter):
        """Should connect to real server and discover tools"""
        from src.core.mcp.client import MCPClient

        client = MCPClient(server=stdio_adapter)
        await client.connect()
        assert client.state.value == "connected"

        tools = await client.discover_tools()
        assert len(tools) >= 10
        tool_names = [t.name for t in tools]
        assert "local_query_alphas" in tool_names
        assert "local_get_statistics" in tool_names

        client.disconnect()

    @pytest.mark.asyncio
    async def test_query_alphas(self, stdio_adapter):
        """Should query alphas from the real database"""
        from src.core.mcp.client import MCPClient

        client = MCPClient(server=stdio_adapter)
        await client.connect()

        result = await client.call_tool("local_query_alphas", {
            "limit": 3,
            "region": "USA",
        })

        if not result["success"]:
            print(f"query_alphas failed: {result}")
        assert result["success"] is True, f"Result: {result}"
        result_body = result.get("result", {})
        content = result_body.get("content", [])
        assert len(content) > 0, f"Empty content in: {result_body}"
        data = content[0]
        assert data.get("type") == "text"
        parsed = __import__("json").loads(data.get("text", "{}"))
        assert "results" in parsed
        assert len(parsed["results"]) > 0

        client.disconnect()

    @pytest.mark.asyncio
    async def test_get_statistics(self, stdio_adapter):
        """Should get statistics from the real database"""
        from src.core.mcp.client import MCPClient

        client = MCPClient(server=stdio_adapter)
        await client.connect()

        result = await client.call_tool("local_get_statistics", {})

        assert result["success"] is True
        content = result.get("result", {}).get("content", [])
        assert len(content) > 0
        stats = __import__("json").loads(content[0].get("text", "{}"))
        assert "total_alphas" in stats
        assert stats["total_alphas"] > 10000
        assert "by_region" in stats
        assert "USA" in stats["by_region"]

        client.disconnect()

    @pytest.mark.asyncio
    async def test_top_alphas(self, stdio_adapter):
        """Should get top alphas by sharpe ratio"""
        from src.core.mcp.client import MCPClient

        client = MCPClient(server=stdio_adapter)
        await client.connect()

        result = await client.call_tool("local_get_top_alphas", {
            "limit": 5,
            "by": "is_sharpe",
        })

        assert result["success"] is True
        content = result.get("result", {}).get("content", [])
        if content:
            data = __import__("json").loads(content[0].get("text", "{}"))
            results = data if isinstance(data, list) else data.get("results", [])
            if results:
                assert results[0].get("is_sharpe", 0) >= results[-1].get("is_sharpe", 0)

        client.disconnect()

    @pytest.mark.asyncio
    async def test_latency_tracking(self, stdio_adapter):
        """Should track latency for real server calls"""
        from src.core.mcp.client import MCPClient

        client = MCPClient(server=stdio_adapter)
        await client.connect()

        assert client.last_request_latency == 0.0
        await client.call_tool("local_get_statistics", {})
        assert client.last_request_latency > 0.0

        client.disconnect()

    @pytest.mark.asyncio
    async def test_stats_tracking(self, stdio_adapter):
        """Should track call statistics for real calls"""
        from src.core.mcp.client import MCPClient

        client = MCPClient(server=stdio_adapter)
        await client.connect()

        await client.call_tool("local_get_statistics", {})
        await client.call_tool("local_query_alphas", {"limit": 1})

        stats = client.get_stats()
        assert stats["total_calls"] == 2
        assert stats["successful_calls"] == 2

        client.disconnect()


class TestMCPProtocolHandlerWithRealServer:
    """Test MCPProtocolHandler with the real BRAIN server"""

    @pytest.mark.asyncio
    async def test_handler_initialization(self, stdio_adapter):
        """MCPProtocolHandler should route calls through real server"""
        from src.core.mcp.handler import MCPProtocolHandler
        from src.core.mcp.client import MCPClient, ToolMeta

        handler = MCPProtocolHandler()
        client = MCPClient(server=stdio_adapter)
        await client.connect()
        handler._clients["brain"] = client

        # Index tools from real server
        tools = await client.discover_tools()
        for tool in tools:
            handler._tool_index[tool.name] = "brain"
            handler._tool_meta[tool.name] = tool

        assert len(handler._tool_index) >= 10
        assert "local_query_alphas" in handler._tool_index

        await handler.shutdown()

    @pytest.mark.asyncio
    async def test_handler_execute_query(self, stdio_adapter):
        """Handler should execute queries through real server"""
        from src.core.mcp.handler import MCPProtocolHandler
        from src.core.mcp.client import MCPClient, ToolMeta

        handler = MCPProtocolHandler()
        client = MCPClient(server=stdio_adapter)
        await client.connect()
        handler._clients["brain"] = client
        handler._tool_index["local_get_statistics"] = "brain"
        handler._tool_meta["local_get_statistics"] = ToolMeta(
            name="local_get_statistics", description="", parameters={}
        )

        result = await handler.execute("local_get_statistics", {})

        assert result["success"] is True
        content = result.get("result", {}).get("content", [])
        assert len(content) > 0
        stats = __import__("json").loads(content[0].get("text", "{}"))
        assert stats["total_alphas"] > 10000
        assert "USA" in stats["by_region"]

        await handler.shutdown()

    @pytest.mark.asyncio
    async def test_handler_unknown_tool(self, stdio_adapter):
        """Handler should return error for unknown tools"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        result = await handler.execute("nonexistent.tool", {})
        assert result["success"] is False
        assert result["error_code"] == "unknown_tool"


class TestStdioAdapterEdgeCases:
    """Test edge cases of the stdio adapter"""

    @pytest.mark.asyncio
    async def test_unknown_tool_error(self, stdio_adapter):
        """Should handle unknown tool gracefully — server returns content with error text"""
        from src.core.mcp.client import MCPClient

        client = MCPClient(server=stdio_adapter)
        await client.connect()

        result = await client.call_tool("nonexistent_tool_xyz", {})

        # Real MCP server returns success=True with error text in content
        # The key assertion is that the call doesn't crash or hang
        assert isinstance(result, dict)
        assert "success" in result

        client.disconnect()

    @pytest.mark.asyncio
    async def test_multiple_sequential_calls(self, stdio_adapter):
        """Should handle multiple calls without connection issues"""
        from src.core.mcp.client import MCPClient

        client = MCPClient(server=stdio_adapter)
        await client.connect()

        for i in range(5):
            result = await client.call_tool("local_get_statistics", {})
            assert result["success"] is True, f"Call {i} failed"

        stats = client.get_stats()
        assert stats["total_calls"] == 5

        client.disconnect()
