"""
MCP Structured Logging

Provides structured logging wrappers for MCP protocol operations.
Every tool call, discovery, and auth event is logged with consistent fields.
"""

import json
import logging
import time
from typing import Any, Dict, Optional


class MCPLogger:
    """
    Structured logger for MCP operations.

    Adds consistent fields to every log entry:
    - component: always "mcp"
    - server: MCP server name
    - tool: MCP tool name
    - latency_ms: request duration
    - success: operation success/failure
    """

    def __init__(self, name: str = "mcp"):
        self._logger = logging.getLogger(name)

    def log_tool_call(
        self,
        server_name: str,
        tool_name: str,
        params: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        latency_ms: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        """Log an MCP tool call with structured fields"""
        if error:
            self._logger.warning(
                "mcp_tool_call_failed",
                extra={
                    "component": "mcp",
                    "server": server_name,
                    "tool": tool_name,
                    "latency_ms": round(latency_ms, 1),
                    "success": False,
                    "error": error,
                    "params_size": len(json.dumps(params)),
                },
            )
        else:
            self._logger.info(
                "mcp_tool_call_completed",
                extra={
                    "component": "mcp",
                    "server": server_name,
                    "tool": tool_name,
                    "latency_ms": round(latency_ms, 1),
                    "success": True,
                    "params_size": len(json.dumps(params)),
                },
            )

    def log_discovery(
        self, server_name: str, tool_count: int, error: Optional[str] = None
    ) -> None:
        """Log tool discovery operation"""
        if error:
            self._logger.warning(
                "mcp_discovery_failed",
                extra={
                    "component": "mcp",
                    "server": server_name,
                    "success": False,
                    "error": error,
                },
            )
        else:
            self._logger.info(
                "mcp_discovery_completed",
                extra={
                    "component": "mcp",
                    "server": server_name,
                    "tool_count": tool_count,
                    "success": True,
                },
            )

    def log_auth(
        self,
        server_name: str,
        action: str,
        source: str,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Log authentication event"""
        if error:
            self._logger.warning(
                "mcp_auth_event",
                extra={
                    "component": "mcp",
                    "server": server_name,
                    "auth_action": action,
                    "auth_source": source,
                    "success": False,
                    "error": error,
                },
            )
        else:
            self._logger.info(
                "mcp_auth_event",
                extra={
                    "component": "mcp",
                    "server": server_name,
                    "auth_action": action,
                    "auth_source": source,
                    "success": True,
                },
            )

    def log_connection(
        self, server_name: str, status: str, error: Optional[str] = None
    ) -> None:
        """Log connection status change"""
        if error:
            self._logger.error(
                "mcp_connection_error",
                extra={
                    "component": "mcp",
                    "server": server_name,
                    "status": status,
                    "error": error,
                },
            )
        else:
            self._logger.info(
                "mcp_connection_change",
                extra={
                    "component": "mcp",
                    "server": server_name,
                    "status": status,
                },
            )
