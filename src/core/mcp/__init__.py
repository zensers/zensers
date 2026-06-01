# -*- coding: utf-8 -*-
"""
MCP 模块初始化
==============

Phase 5: MCP 支持框架
"""

from src.core.mcp.config import MCPConfig, ToolConfig, DataSourceConfig
from src.core.mcp.server import MCPServer
from src.core.mcp.client import MCPClient, ToolMeta
from src.core.mcp.tool_registry import ToolRegistry, Tool
from src.core.mcp.credentials import CredentialManager, Credential
from src.core.mcp.rate_limiter import RateLimiter, RateLimiterRegistry
from src.core.mcp.handler import MCPProtocolHandler
from src.core.mcp.logging import MCPLogger
from src.core.mcp.health import MCPHealthChecker, ServerHealth
from src.core.mcp.security import SecureCredentialStorage, CredentialRotationManager
from src.core.mcp.stdio_adapter import StdioServerAdapter

__all__ = [
    "MCPConfig",
    "ToolConfig",
    "DataSourceConfig",
    "MCPServer",
    "MCPClient",
    "ToolMeta",
    "ToolRegistry",
    "Tool",
    "CredentialManager",
    "Credential",
    "RateLimiter",
    "RateLimiterRegistry",
    "MCPProtocolHandler",
    "MCPLogger",
    "MCPHealthChecker",
    "ServerHealth",
    "SecureCredentialStorage",
    "CredentialRotationManager",
]