# -*- coding: utf-8 -*-
"""
Zensers Configuration Module

Configuration: using .env file
    LLM_API_KEY=sk-your-api-key
    LLM_BASE_URL=https://api.openai.com/v1
    LLM_MODEL=gpt-4o

Usage:
    from src.config import settings
    api_key = settings.llm.api_key
    model = settings.llm.model
"""

from .settings import settings, Settings, get_settings
from .agents import load_agents_config, get_agent_config, AgentsConfig
from .system import load_system_config, get_system_config, SystemConfig
from .report_template import load_template, ReportTemplate

# MCP configuration imported from core.mcp
try:
    from ..core.mcp.config import load_config as load_mcp_config, MCPConfig
except ImportError:
    load_mcp_config = None
    MCPConfig = None


__all__ = [
    "settings",
    "Settings",
    "get_settings",
    "load_mcp_config",
    "MCPConfig",
    "load_agents_config",
    "get_agent_config",
    "AgentsConfig",
    "load_system_config",
    "get_system_config",
    "SystemConfig",
    "load_template",
    "ReportTemplate",
]
