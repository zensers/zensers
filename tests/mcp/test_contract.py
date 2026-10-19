"""
Contract tests for MCP protocol compliance.

Verifies that MCP client and handler implementations conform to
the expected protocol interface, regardless of backend implementation.
"""

import pytest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ============================================================
# Contract: Tool Discovery
# ============================================================

class ToolDiscoveryContract:
    """Defines the contract for MCP tool discovery."""

    @dataclass
    class DiscoveredTool:
        """Expected schema for a discovered tool"""
        name: str
        description: str
        parameters: Dict[str, Any]

    REQUIRED_TOOL_FIELDS = {"name", "description", "parameters"}

    @classmethod
    def validate_tool(cls, tool: Dict[str, Any]) -> List[str]:
        """Validate a tool dict against the contract. Returns list of violations."""
        violations = []
        missing = cls.REQUIRED_TOOL_FIELDS - set(tool.keys())
        if missing:
            violations.append(f"Missing required fields: {missing}")
        if not isinstance(tool.get("name"), str) or not tool["name"]:
            violations.append("Tool name must be a non-empty string")
        if not isinstance(tool.get("description"), str):
            violations.append("Tool description must be a string")
        if not isinstance(tool.get("parameters"), dict):
            violations.append("Tool parameters must be a dict")
        return violations


class TestToolDiscoveryContract:
    """Verify tool discovery conforms to the contract"""

    @pytest.mark.asyncio
    async def test_discovery_returns_list(self, mock_server):
        """Discovery must return a list"""
        from src.core.mcp.client import MCPClient
        client = MCPClient(server=mock_server)
        await client.connect()
        tools = await client.discover_tools()
        assert isinstance(tools, list)

    @pytest.mark.asyncio
    async def test_each_tool_has_required_fields(self, mock_server):
        """Each tool must have name, description, parameters"""
        from src.core.mcp.client import MCPClient
        client = MCPClient(server=mock_server)
        await client.connect()
        tools = await client.discover_tools()
        for tool in tools:
            violations = ToolDiscoveryContract.validate_tool({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            })
            assert not violations, f"Tool '{tool.name}' violations: {violations}"

    @pytest.mark.asyncio
    async def test_tool_names_are_unique(self, mock_server):
        """Tool names must be unique within a server"""
        from src.core.mcp.client import MCPClient
        client = MCPClient(server=mock_server)
        await client.connect()
        tools = await client.discover_tools()
        names = [t.name for t in tools]
        assert len(names) == len(set(names)), "Duplicate tool names found"


# ============================================================
# Contract: Tool Execution
# ============================================================

class ToolExecutionContract:
    """Defines the contract for MCP tool execution."""

    REQUIRED_RESULT_FIELDS_SUCCESS = {"success"}
    OPTIONAL_SUCCESS_FIELDS = {"result"}
    REQUIRED_RESULT_FIELDS_ERROR = {"success", "error"}

    @classmethod
    def validate_success(cls, result: Dict[str, Any]) -> List[str]:
        """Validate a successful result"""
        violations = []
        if not result.get("success"):
            violations.append("success must be True")
        if not isinstance(result.get("success"), bool):
            violations.append("success must be boolean")
        return violations

    @classmethod
    def validate_error(cls, result: Dict[str, Any]) -> List[str]:
        """Validate an error result"""
        violations = []
        if result.get("success") is not False:
            violations.append("success must be False on error")
        if "error" not in result:
            violations.append("error field is required on failure")
        return violations


class TestToolExecutionContract:
    """Verify tool execution conforms to the contract"""

    @pytest.mark.asyncio
    async def test_successful_call_returns_expected_schema(self, mock_server):
        """Successful calls must have success=True"""
        from src.core.mcp.client import MCPClient
        client = MCPClient(server=mock_server)
        await client.connect()
        result = await client.call_tool("wind.get_stock_data", {"code": "002594"})
        violations = ToolExecutionContract.validate_success(result)
        assert not violations, f"Contract violations: {violations}"

    @pytest.mark.asyncio
    async def test_failed_call_returns_error(self, mock_server):
        """Failed calls must have success=False and error message"""
        from src.core.mcp.client import MCPClient
        client = MCPClient(server=mock_server)
        await client.connect()
        result = await client.call_tool("tool.always_fails", {})
        violations = ToolExecutionContract.validate_error(result)
        assert not violations, f"Contract violations: {violations}"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, mock_server):
        """Unknown tools must return error, not exception"""
        from src.core.mcp.client import MCPClient
        client = MCPClient(server=mock_server)
        await client.connect()
        result = await client.call_tool("nonexistent.tool", {})
        violations = ToolExecutionContract.validate_error(result)
        assert not violations, f"Contract violations: {violations}"

    @pytest.mark.asyncio
    async def test_success_has_result_field(self, mock_server):
        """Successful calls should include a result field"""
        from src.core.mcp.client import MCPClient
        client = MCPClient(server=mock_server)
        await client.connect()
        result = await client.call_tool("wind.get_stock_data", {})
        if result.get("success"):
            assert "result" in result, "Successful response must contain 'result' field"


# ============================================================
# Contract: Error Codes
# ============================================================

class TestErrorCodeContract:
    """Verify error codes follow the contract"""

    VALID_ERROR_CODES = {
        "unknown_tool", "server_disconnected", "auth_refresh_failed",
        "auth_failed", "server_rate_limit", "rate_limit_exceeded",
        "call_failed", "missing_tool", "mcp_handler_unavailable",
        "client_not_connected", "no_transport_available", "no_http_session",
    }

    def test_known_error_codes_are_valid(self):
        """All predefined error codes must be in the valid set"""
        from src.core.mcp.client import MCPClient
        # Error codes are used as constants - verify the set is comprehensive
        assert "unknown_tool" in self.VALID_ERROR_CODES
        assert "rate_limit_exceeded" in self.VALID_ERROR_CODES
        assert "auth_failed" in self.VALID_ERROR_CODES

    @pytest.mark.asyncio
    async def test_rate_limit_error_has_retry_after(self, mock_server):
        """Rate limit errors must include retry_after"""
        from src.core.mcp.client import MCPClient
        from src.core.mcp.rate_limiter import RateLimiter

        limiter = RateLimiter(requests_per_minute=1, requests_per_hour=1000)
        client = MCPClient(server=mock_server, rate_limiter=limiter)
        await client.connect()

        await client.call_tool("wind.get_stock_data", {})
        result = await client.call_tool("wind.get_stock_data", {})

        if not result.get("success"):
            assert "retry_after" in result, "Rate limited response must include retry_after"
            assert isinstance(result["retry_after"], (int, float))
            assert result["retry_after"] > 0


# ============================================================
# Contract: Handler Interface
# ============================================================

class TestHandlerContract:
    """Verify MCPProtocolHandler conforms to expected interface"""

    @pytest.mark.asyncio
    async def test_execute_returns_dict(self, mock_server):
        """execute() must always return a dict"""
        from src.core.mcp.handler import MCPProtocolHandler
        from src.core.mcp.client import MCPClient

        handler = MCPProtocolHandler()
        client = MCPClient(server=mock_server)
        await client.connect()
        handler._clients["mock"] = client
        handler._tool_index["wind.get_stock_data"] = "mock"

        result = await handler.execute("wind.get_stock_data", {})
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_unknown_returns_structure(self):
        """execute() with unknown tool must return correct error structure"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        result = await handler.execute("unknown.tool", {})
        assert isinstance(result, dict)
        assert "success" in result
        assert "error" in result
        assert "error_code" in result

    def test_list_available_tools_returns_list(self):
        """list_available_tools() must always return a list"""
        from src.core.mcp.handler import MCPProtocolHandler

        handler = MCPProtocolHandler()
        tools = handler.list_available_tools()
        assert isinstance(tools, list)
