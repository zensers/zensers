"""
Integration tests for MCP protocol layer.
Tests end-to-end flow: MCPProtocolHandler -> MCPClient -> Mock MCPServer.
"""

import pytest
from src.core.mcp.client import MCPClient, ToolMeta
from src.core.mcp.credentials import CredentialManager, AuthConfig, AuthType
from src.core.mcp.rate_limiter import RateLimiter, RateLimiterRegistry

@pytest.fixture
def credential_manager():
    cm = CredentialManager()
    cm.register_system("wind", AuthConfig(type=AuthType.API_KEY, api_key="test_wind_key"))
    cm.register_system("slack", AuthConfig(type=AuthType.BEARER, token="xoxb-test-token"))
    return cm


@pytest.fixture
def rate_limiter_registry():
    return RateLimiterRegistry()


class TestMCPProtocolHandlerIntegration:
    """Integration tests for MCPProtocolHandler with mock MCPServer"""

    @pytest.mark.asyncio
    async def test_initialize_and_discover_tools(self, mock_server):
        """Handler should discover tools from connected servers"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        client = MCPClient(server=mock_server)
        await client.connect()
        handler._clients["mock"] = client

        tools = await client.discover_tools()
        assert len(tools) == 4
        tool_names = [t.name for t in tools]
        assert "wind.get_stock_data" in tool_names
        assert "wind.get_financials" in tool_names
        assert "slack.send_message" in tool_names

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, mock_server):
        """Handler should execute known tools and return results"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        client = MCPClient(server=mock_server)
        await client.connect()
        handler._clients["mock"] = client
        handler._tool_index["wind.get_stock_data"] = "mock"
        handler._tool_meta["wind.get_stock_data"] = ToolMeta(
            name="wind.get_stock_data",
            description="Get stock data",
            parameters={},
        )

        result = await handler.execute("wind.get_stock_data", {"code": "002594"})
        assert result["success"] is True
        assert "stocks" in result["result"]
        assert result["result"]["stocks"][0]["code"] == "002594"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Handler should return error for unknown tool"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        result = await handler.execute("unknown.tool", {})
        assert result["success"] is False
        assert result["error_code"] == "unknown_tool"

    @pytest.mark.asyncio
    async def test_execute_server_disconnected(self, mock_server):
        """Handler should return error when server is not connected"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        handler._tool_index["wind.get_stock_data"] = "mock"
        handler._tool_meta["wind.get_stock_data"] = ToolMeta(
            name="wind.get_stock_data",
            description="Get stock data",
            parameters={},
        )
        # No client registered for "mock"

        result = await handler.execute("wind.get_stock_data", {"code": "002594"})
        assert result["success"] is False
        assert result["error_code"] == "server_disconnected"

    @pytest.mark.asyncio
    async def test_list_available_tools(self, mock_server):
        """Should list all indexed tools with metadata"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        handler._tool_index["tool_a"] = "server1"
        handler._tool_index["tool_b"] = "server2"
        handler._tool_meta["tool_a"] = ToolMeta(
            name="tool_a", description="Tool A", parameters={"param1": {"type": "string"}}
        )
        handler._tool_meta["tool_b"] = ToolMeta(
            name="tool_b", description="Tool B", parameters={}
        )

        tools = handler.list_available_tools()
        assert len(tools) == 2
        assert tools[0]["name"] == "tool_a"
        assert tools[1]["server"] == "server2"

    @pytest.mark.asyncio
    async def test_reconnect_server(self, mock_server):
        """Reconnect should re-discover tools"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        client = MCPClient(server=mock_server)
        handler._clients["mock"] = client

        success = await handler.reconnect("mock")
        assert success is True
        assert "wind.get_stock_data" in handler._tool_index

    @pytest.mark.asyncio
    async def test_shutdown_clears_all(self, mock_server):
        """Shutdown should disconnect all clients and clear indexes"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        client = MCPClient(server=mock_server)
        await client.connect()
        handler._clients["mock"] = client
        handler._tool_index["tool"] = "mock"
        handler._tool_meta["tool"] = ToolMeta(name="tool", description="", parameters={})

        await handler.shutdown()
        assert len(handler._clients) == 0
        assert len(handler._tool_index) == 0


class TestMCPClientLocalMode:
    """Tests for MCPClient in local mode (direct MCPServer instance)"""

    @pytest.mark.asyncio
    async def test_connect_local(self, mock_server):
        """Should connect to local MCPServer"""
        client = MCPClient(server=mock_server)
        success = await client.connect()
        assert success is True
        assert client.state.value == "connected"
        assert mock_server.started is True

    @pytest.mark.asyncio
    async def test_discover_tools_local(self, mock_server):
        """Should discover tools via local server"""
        client = MCPClient(server=mock_server)
        await client.connect()
        tools = await client.discover_tools()
        assert len(tools) == 4
        assert any(t.name == "wind.get_stock_data" for t in tools)

    @pytest.mark.asyncio
    async def test_call_tool_local_success(self, mock_server):
        """Should call tool via local server and get result"""
        client = MCPClient(server=mock_server)
        await client.connect()
        result = await client.call_tool("wind.get_stock_data", {"code": "002594"})
        assert result["success"] is True
        assert result["result"]["stocks"][0]["name"] == "BYD"

    @pytest.mark.asyncio
    async def test_call_tool_local_failure(self, mock_server):
        """Should handle tool execution failure"""
        client = MCPClient(server=mock_server)
        await client.connect()
        result = await client.call_tool("tool.always_fails", {})
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_call_tool_unknown(self, mock_server):
        """Should handle unknown tool name"""
        client = MCPClient(server=mock_server)
        await client.connect()
        result = await client.call_tool("nonexistent.tool", {})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_latency_tracking(self, mock_server):
        """Should track request latency"""
        client = MCPClient(server=mock_server)
        await client.connect()
        assert client.last_request_latency == 0.0
        await client.call_tool("wind.get_stock_data", {"code": "002594"})
        assert client.last_request_latency > 0.0

    @pytest.mark.asyncio
    async def test_stats_tracking(self, mock_server):
        """Should track call statistics"""
        client = MCPClient(server=mock_server)
        await client.connect()
        await client.call_tool("wind.get_stock_data", {})
        await client.call_tool("tool.always_fails", {})
        stats = client.get_stats()
        assert stats["total_calls"] == 2
        assert stats["successful_calls"] == 1
        assert stats["failed_calls"] == 1

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self, mock_server):
        """Disconnect should clean up resources"""
        client = MCPClient(server=mock_server)
        await client.connect()
        await client.discover_tools()
        assert len(client._tool_cache) == 4
        client.disconnect()
        assert len(client._tool_cache) == 0

    @pytest.mark.asyncio
    async def test_rate_limiter_integration(self, mock_server):
        """Rate limiter should block calls when exhausted"""
        limiter = RateLimiter(requests_per_minute=2, requests_per_hour=1000)
        client = MCPClient(server=mock_server, rate_limiter=limiter)
        await client.connect()

        # First two calls should succeed
        r1 = await client.call_tool("wind.get_stock_data", {})
        assert r1["success"] is True
        r2 = await client.call_tool("wind.get_financials", {})
        assert r2["success"] is True

        # Third call should be rate limited
        r3 = await client.call_tool("wind.get_stock_data", {})
        assert r3["success"] is False
        assert r3["error"] == "rate_limit_exceeded"


class TestGenericAgentMCPIntegration:
    """Tests for GenericAgent MCP integration (via handler, avoids broken import chain)"""

    @pytest.mark.asyncio
    async def test_mcp_route_via_handler(self, mock_server):
        """MCP tool execution through handler — equivalent to GenericAgent action='mcp'"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        client = MCPClient(server=mock_server)
        await client.connect()
        handler._clients["mock"] = client
        handler._tool_index["wind.get_stock_data"] = "mock"
        handler._tool_meta["wind.get_stock_data"] = ToolMeta(
            name="wind.get_stock_data", description="", parameters={}
        )

        # This is what GenericAgent._execute_mcp() does internally
        result = await handler.execute("wind.get_stock_data", {"industry": "EV"})

        assert result["success"] is True
        assert "stocks" in result["result"]

    @pytest.mark.asyncio
    async def test_mcp_route_no_handler(self):
        """Should return error when MCP handler is not configured — equivalent to GenericAgent without handler"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        result = await handler.execute("wind.get_stock_data", {})

        assert result["success"] is False
        assert result["error_code"] == "unknown_tool"


class TestCredentialManagerIntegration:
    """Tests for CredentialManager + MCPClient integration"""

    @pytest.mark.asyncio
    async def test_credential_passed_to_client(self, mock_server, credential_manager):
        """Credentials should be available for MCPClient"""
        client = MCPClient(
            server=mock_server,
            credential_manager=credential_manager,
        )
        # In local mode, credential_manager is stored but not used for transport
        # This test verifies the injection path works
        assert client._credential_manager is not None
        auth = client._credential_manager.get_auth("wind")
        assert auth is not None
        assert auth.api_key == "test_wind_key"

    @pytest.mark.asyncio
    async def test_multi_server_credentials(self, credential_manager):
        """CredentialManager should handle multiple servers"""
        auth_wind = credential_manager.get_auth("wind")
        auth_slack = credential_manager.get_auth("slack")
        assert auth_wind.type == AuthType.API_KEY
        assert auth_slack.type == AuthType.BEARER

    @pytest.mark.asyncio
    async def test_user_credential_overrides(self, credential_manager):
        """User-level credential should override system-level"""
        credential_manager.register_user(
            "wind",
            AuthConfig(type=AuthType.API_KEY, api_key="user_wind_key"),
        )
        auth = credential_manager.get_auth("wind")
        assert auth.api_key == "user_wind_key"


class TestRateLimiterIntegration:
    """Tests for RateLimiterRegistry + MCPClient integration"""

    @pytest.mark.asyncio
    async def test_registry_creates_limiters(self):
        """RateLimiterRegistry should create per-server limiters"""
        registry = RateLimiterRegistry()
        limiter = registry.get_or_create("wind", rpm=30, rph=500)
        assert limiter is not None
        stats = limiter.get_stats()
        assert stats["rpm_limit"] == 30
        assert stats["rph_limit"] == 500

    @pytest.mark.asyncio
    async def test_registry_reuses_limiters(self):
        """RateLimiterRegistry should reuse existing limiters"""
        registry = RateLimiterRegistry()
        limiter1 = registry.get_or_create("wind")
        limiter2 = registry.get_or_create("wind")
        assert limiter1 is limiter2

    @pytest.mark.asyncio
    async def test_registry_stats(self):
        """RateLimiterRegistry stats should reflect all limiters"""
        registry = RateLimiterRegistry()
        registry.get_or_create("wind", rpm=30)
        registry.get_or_create("slack", rpm=10)
        stats = registry.get_stats()
        assert "wind" in stats
        assert "slack" in stats

    @pytest.mark.asyncio
    async def test_rate_limiter_with_client(self, mock_server):
        """Full integration: RateLimiter + MCPClient + mock server"""
        limiter = RateLimiter(requests_per_minute=3, requests_per_hour=1000)
        client = MCPClient(server=mock_server, rate_limiter=limiter)
        await client.connect()

        for _ in range(3):
            r = await client.call_tool("wind.get_stock_data", {})
            assert r["success"] is True

        # Fourth call hits the 3/min limit
        r = await client.call_tool("wind.get_stock_data", {})
        assert r["success"] is False
        assert r["retry_after"] > 0
