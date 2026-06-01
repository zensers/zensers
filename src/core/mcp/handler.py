"""
MCP Protocol Handler

Protocol adapter for MCP tool invocation within GenericAgent.
This is NOT a Skill wrapper — it routes tool calls to the correct MCP server
via the MCP protocol and returns raw data for LLM consumption.

Key principles:
1. No format conversion — MCP returns raw data, LLM handles interpretation
2. Tool discovery via MCP protocol (tools/list)
3. Credential injection via CredentialManager
4. Rate limiting at the transport level
"""

import logging
from typing import Any, Dict, List, Optional

from src.core.mcp.client import MCPClient, ToolMeta
from src.core.mcp.config import MCPConfig
from src.core.mcp.credentials import CredentialManager
from src.core.mcp.rate_limiter import RateLimiterRegistry

logger = logging.getLogger(__name__)


class MCPProtocolHandler:
    """
    Routes MCP tool calls to the correct server, handling discovery,
    credential injection, and raw data relay (no format conversion).

    Usage:
        handler = await MCPProtocolHandler.create(config, credential_manager)
        result = await handler.execute("wind.get_stock_data", {"code": "002594"})
    """

    def __init__(
        self,
        credential_manager: Optional[CredentialManager] = None,
        rate_limiter_registry: Optional[RateLimiterRegistry] = None,
    ):
        self._credential_manager = credential_manager
        self._rate_limiter_registry = rate_limiter_registry
        self._clients: Dict[str, MCPClient] = {}
        self._tool_index: Dict[str, str] = {}       # tool_name → server_name
        self._tool_meta: Dict[str, ToolMeta] = {}    # tool_name → metadata

    @classmethod
    async def create(
        cls,
        config: MCPConfig,
        credential_manager: Optional[CredentialManager] = None,
        rate_limiter_registry: Optional[RateLimiterRegistry] = None,
    ) -> "MCPProtocolHandler":
        """Factory method: creates and initializes the handler"""
        handler = cls(credential_manager, rate_limiter_registry)
        await handler.initialize(config)
        return handler

    async def initialize(self, config: MCPConfig) -> None:
        """
        Connect to all enabled MCP servers and discover their tools.

        Failed servers are logged but do not block initialization.
        """
        for server_config in config.get_enabled_servers():
            try:
                rate_limiter = None
                if self._rate_limiter_registry and server_config.name:
                    rl_config = server_config.rate_limit if hasattr(server_config, 'rate_limit') else None
                    rate_limiter = self._rate_limiter_registry.get_or_create(
                        server_config.name,
                        rpm=getattr(rl_config, 'requests_per_minute', None),
                        rph=getattr(rl_config, 'requests_per_hour', None),
                    )

                client = MCPClient(
                    server_config=server_config,
                    credential_manager=self._credential_manager,
                    rate_limiter=rate_limiter,
                )
                await client.connect()
                self._clients[server_config.name] = client

                # Discover and index tools
                tools = await client.discover_tools()
                for tool in tools:
                    self._tool_index[tool.name] = server_config.name
                    self._tool_meta[tool.name] = tool

                logger.info(
                    f"MCP server '{server_config.name}' initialized: {len(tools)} tools"
                )

            except Exception as e:
                logger.error(f"Failed to initialize MCP server '{server_config.name}': {e}")

    async def execute(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an MCP tool.

        Args:
            tool: Fully qualified tool name (e.g., "wind.get_stock_data")
            params: Tool parameters

        Returns:
            Dict with keys:
            - success: bool
            - result: raw tool response (if success)
            - error: error message (if failure)
            - error_code: error type (if failure)
            - retry_after: seconds to wait (if rate limited)
        """
        server_name = self._tool_index.get(tool)
        if not server_name:
            return {
                "success": False,
                "error": f"Unknown MCP tool: {tool}",
                "error_code": "unknown_tool",
            }

        client = self._clients.get(server_name)
        if not client:
            return {
                "success": False,
                "error": f"MCP server not connected: {server_name}",
                "error_code": "server_disconnected",
            }

        return await client.call_tool(tool, params)

    def list_available_tools(self) -> List[Dict[str, Any]]:
        """List all discovered MCP tools with metadata"""
        return [
            {
                "name": name,
                "server": server,
                "description": self._tool_meta[name].description,
                "parameters": self._tool_meta[name].parameters,
            }
            for name, server in self._tool_index.items()
        ]

    def get_tool_meta(self, tool_name: str) -> Optional[ToolMeta]:
        """Get metadata for a specific tool"""
        return self._tool_meta.get(tool_name)

    async def reconnect(self, server_name: str) -> bool:
        """Reconnect a disconnected MCP server"""
        client = self._clients.get(server_name)
        if not client:
            return False
        success = await client.connect()
        if success:
            # Re-discover tools
            tools = await client.discover_tools()
            for tool in tools:
                self._tool_index[tool.name] = server_name
                self._tool_meta[tool.name] = tool
        return success

    async def shutdown(self) -> None:
        """Disconnect all MCP clients"""
        for name, client in self._clients.items():
            try:
                client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting {name}: {e}")
        self._clients.clear()
        self._tool_index.clear()
        self._tool_meta.clear()
