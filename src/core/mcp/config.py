# -*- coding: utf-8 -*-
"""
MCP 配置模块
============

Phase 5 Week 19: MCP 基础架构 - 配置解析

功能特性:
- 多种传输类型 (stdio, sse, streamable_http)
- 完整的服务器配置 (命令、URL、认证、超时)
- 工具配置 (内置、自定义、外部)
- 数据源配置
- 重试和健康检查配置
- 环境变量支持
- 配置热重载

参考: Letta MCP 配置结构
"""

import os
import re
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# ============================================
# 枚举类型
# ============================================

class TransportType(Enum):
    """传输类型枚举"""
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


class ToolType(Enum):
    """工具类型枚举"""
    BUILTIN = "builtin"
    CUSTOM = "custom"
    EXTERNAL = "external"
    MCP = "mcp"  # MCP 服务器提供的工具


class DataSourceType(Enum):
    """数据源类型枚举"""
    SQLITE = "sqlite"
    POSTGRES = "postgres"
    MYSQL = "mysql"
    MONGODB = "mongodb"
    REDIS = "redis"
    API = "api"
    FILESYSTEM = "filesystem"


class AuthType(Enum):
    """认证类型枚举"""
    NONE = "none"
    BEARER = "bearer"
    API_KEY = "api_key"
    BASIC = "basic"
    OAUTH = "oauth"
    CUSTOM = "custom"


# ============================================
# 认证配置
# ============================================

@dataclass
class AuthConfig:
    """认证配置"""
    type: AuthType = AuthType.NONE
    header: Optional[str] = None  # 认证头名称，如 "Authorization"
    token: Optional[str] = None   # 认证令牌
    username: Optional[str] = None  # Basic 认证用户名
    password: Optional[str] = None  # Basic 认证密码
    api_key: Optional[str] = None   # API Key
    api_key_header: Optional[str] = None  # API Key 头名称
    oauth_client_id: Optional[str] = None
    oauth_client_secret: Optional[str] = None
    oauth_redirect_uri: Optional[str] = None
    oauth_refresh_token: Optional[str] = None  # OAuth refresh token
    token_url: Optional[str] = None            # OAuth token endpoint
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（敏感信息已脱敏）"""
        result = {"type": self.type.value}
        if self.header:
            result["header"] = self.header
        if self.token:
            result["token"] = "***"  # 隐藏敏感信息
        if self.username:
            result["username"] = self.username
        if self.password:
            result["password"] = "***"  # 隐藏敏感信息
        if self.api_key:
            result["api_key"] = "***"  # 隐藏敏感信息
        if self.api_key_header:
            result["api_key_header"] = self.api_key_header
        if self.oauth_client_id:
            result["oauth_client_id"] = self.oauth_client_id
        if self.oauth_client_secret:
            result["oauth_client_secret"] = "***"  # 隐藏敏感信息
        if self.oauth_redirect_uri:
            result["oauth_redirect_uri"] = self.oauth_redirect_uri
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuthConfig":
        """从字典反序列化"""
        return cls(
            type=AuthType(data.get("type", "none")),
            header=data.get("header"),
            token=data.get("token"),
            username=data.get("username"),
            password=data.get("password"),
            api_key=data.get("api_key"),
            api_key_header=data.get("api_key_header"),
            oauth_client_id=data.get("oauth_client_id"),
            oauth_client_secret=data.get("oauth_client_secret"),
            oauth_redirect_uri=data.get("oauth_redirect_uri"),
        )
    
    def build_headers(self) -> Dict[str, str]:
        """构建认证头"""
        headers = {}
        if self.type == AuthType.BEARER and self.token:
            headers[self.header or "Authorization"] = f"Bearer {self.token}"
        elif self.type == AuthType.API_KEY and self.api_key:
            headers[self.api_key_header or "X-API-Key"] = self.api_key
        elif self.type == AuthType.BASIC and self.username and self.password:
            import base64
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            headers[self.header or "Authorization"] = f"Basic {credentials}"
        return headers


# ============================================
# 重试配置
# ============================================

@dataclass
class RetryConfig:
    """重试配置"""
    enabled: bool = True
    max_attempts: int = 3
    initial_delay: float = 1.0  # 秒
    max_delay: float = 30.0  # 秒
    backoff_multiplier: float = 2.0
    retry_on_errors: List[str] = field(default_factory=lambda: ["timeout", "connection_error"])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "max_attempts": self.max_attempts,
            "initial_delay": self.initial_delay,
            "max_delay": self.max_delay,
            "backoff_multiplier": self.backoff_multiplier,
            "retry_on_errors": self.retry_on_errors,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetryConfig":
        return cls(
            enabled=data.get("enabled", True),
            max_attempts=data.get("max_attempts", 3),
            initial_delay=data.get("initial_delay", 1.0),
            max_delay=data.get("max_delay", 30.0),
            backoff_multiplier=data.get("backoff_multiplier", 2.0),
            retry_on_errors=data.get("retry_on_errors", ["timeout", "connection_error"]),
        )


# ============================================
# 超时配置
# ============================================

@dataclass
class TimeoutConfig:
    """超时配置"""
    connect: float = 5.0  # 连接超时（秒）
    request: float = 30.0  # 请求超时（秒）
    read: float = 60.0  # 读取超时（秒）
    total: float = 120.0  # 总超时（秒）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "connect": self.connect,
            "request": self.request,
            "read": self.read,
            "total": self.total,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeoutConfig":
        return cls(
            connect=data.get("connect", 5.0),
            request=data.get("request", 30.0),
            read=data.get("read", 60.0),
            total=data.get("total", 120.0),
        )


# ============================================
# 健康检查配置
# ============================================

@dataclass
class HealthCheckConfig:
    """健康检查配置"""
    enabled: bool = True
    interval: int = 30  # 检查间隔（秒）
    timeout: float = 5.0  # 检查超时（秒）
    unhealthy_threshold: int = 3  # 不健康阈值
    healthy_threshold: int = 2  # 健康阈值
    endpoint: Optional[str] = None  # 健康检查端点
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "interval": self.interval,
            "timeout": self.timeout,
            "unhealthy_threshold": self.unhealthy_threshold,
            "healthy_threshold": self.healthy_threshold,
            "endpoint": self.endpoint,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HealthCheckConfig":
        return cls(
            enabled=data.get("enabled", True),
            interval=data.get("interval", 30),
            timeout=data.get("timeout", 5.0),
            unhealthy_threshold=data.get("unhealthy_threshold", 3),
            healthy_threshold=data.get("healthy_threshold", 2),
            endpoint=data.get("endpoint"),
        )


# ============================================
# MCP 服务器配置
# ============================================

@dataclass
class BaseServerConfig:
    """服务器配置基类"""
    name: str
    transport: TransportType
    enabled: bool = True
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    env: Dict[str, str] = field(default_factory=dict)  # 环境变量
    custom_headers: Dict[str, str] = field(default_factory=dict)  # 自定义请求头
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "name": self.name,
            "transport": self.transport.value,
            "enabled": self.enabled,
            "description": self.description,
            "tags": self.tags,
            "timeout": self.timeout.to_dict(),
            "retry": self.retry.to_dict(),
            "health_check": self.health_check.to_dict(),
            "env": self.env,
            "custom_headers": self.custom_headers,
        }


@dataclass
class StdioServerConfig(BaseServerConfig):
    """Stdio MCP 服务器配置"""
    transport: TransportType = TransportType.STDIO
    command: str = ""  # 要执行的命令
    args: List[str] = field(default_factory=list)  # 命令参数
    cwd: Optional[str] = None  # 工作目录
    shell: bool = False  # 是否使用 shell 执行
    
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            "command": self.command,
            "args": self.args,
            "cwd": self.cwd,
            "shell": self.shell,
        })
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StdioServerConfig":
        return cls(
            name=data["name"],
            transport=TransportType.STDIO,
            enabled=data.get("enabled", True),
            description=data.get("description"),
            tags=data.get("tags", []),
            command=data.get("command", ""),
            args=data.get("args", []),
            cwd=data.get("cwd"),
            shell=data.get("shell", False),
            timeout=TimeoutConfig.from_dict(data.get("timeout", {})),
            retry=RetryConfig.from_dict(data.get("retry", {})),
            health_check=HealthCheckConfig.from_dict(data.get("health_check", {})),
            env=data.get("env", {}),
            custom_headers=data.get("custom_headers", {}),
        )


@dataclass
class SSEServerConfig(BaseServerConfig):
    """SSE MCP 服务器配置"""
    transport: TransportType = TransportType.SSE
    url: str = ""  # 服务器 URL
    auth: Optional[AuthConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            "url": self.url,
            "auth": self.auth.to_dict() if self.auth else None,
        })
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SSEServerConfig":
        auth_data = data.get("auth")
        return cls(
            name=data["name"],
            transport=TransportType.SSE,
            enabled=data.get("enabled", True),
            description=data.get("description"),
            tags=data.get("tags", []),
            url=data.get("url", ""),
            auth=AuthConfig.from_dict(auth_data) if auth_data else None,
            timeout=TimeoutConfig.from_dict(data.get("timeout", {})),
            retry=RetryConfig.from_dict(data.get("retry", {})),
            health_check=HealthCheckConfig.from_dict(data.get("health_check", {})),
            env=data.get("env", {}),
            custom_headers=data.get("custom_headers", {}),
        )


@dataclass
class StreamableHTTPServerConfig(BaseServerConfig):
    """Streamable HTTP MCP 服务器配置"""
    transport: TransportType = TransportType.STREAMABLE_HTTP
    url: str = ""  # 服务器 URL
    auth: Optional[AuthConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            "url": self.url,
            "auth": self.auth.to_dict() if self.auth else None,
        })
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamableHTTPServerConfig":
        auth_data = data.get("auth")
        return cls(
            name=data["name"],
            transport=TransportType.STREAMABLE_HTTP,
            enabled=data.get("enabled", True),
            description=data.get("description"),
            tags=data.get("tags", []),
            url=data.get("url", ""),
            auth=AuthConfig.from_dict(auth_data) if auth_data else None,
            timeout=TimeoutConfig.from_dict(data.get("timeout", {})),
            retry=RetryConfig.from_dict(data.get("retry", {})),
            health_check=HealthCheckConfig.from_dict(data.get("health_check", {})),
            env=data.get("env", {}),
            custom_headers=data.get("custom_headers", {}),
        )


# 服务器配置联合类型
ServerConfig = Union[StdioServerConfig, SSEServerConfig, StreamableHTTPServerConfig]


def parse_server_config(data: Dict[str, Any]) -> ServerConfig:
    """解析服务器配置"""
    transport = TransportType(data.get("transport", "stdio"))
    
    if transport == TransportType.STDIO:
        return StdioServerConfig.from_dict(data)
    elif transport == TransportType.SSE:
        return SSEServerConfig.from_dict(data)
    elif transport == TransportType.STREAMABLE_HTTP:
        return StreamableHTTPServerConfig.from_dict(data)
    else:
        raise ValueError(f"不支持的传输类型: {transport}")


# ============================================
# 工具配置
# ============================================

@dataclass
class ToolConfig:
    """工具配置"""
    name: str
    type: ToolType
    enabled: bool = True
    description: Optional[str] = None
    module: Optional[str] = None  # 模块路径（自定义工具）
    server: Optional[str] = None  # MCP 服务器名称（MCP 工具）
    permissions: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)  # 参数定义
    config: Dict[str, Any] = field(default_factory=dict)  # 额外配置
    timeout: Optional[TimeoutConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "type": self.type.value,
            "enabled": self.enabled,
            "description": self.description,
            "module": self.module,
            "server": self.server,
            "permissions": self.permissions,
            "parameters": self.parameters,
            "config": self.config,
        }
        if self.timeout:
            result["timeout"] = self.timeout.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolConfig":
        timeout_data = data.get("timeout")
        return cls(
            name=data["name"],
            type=ToolType(data.get("type", "builtin")),
            enabled=data.get("enabled", True),
            description=data.get("description"),
            module=data.get("module"),
            server=data.get("server"),
            permissions=data.get("permissions", []),
            parameters=data.get("parameters", {}),
            config=data.get("config", {}),
            timeout=TimeoutConfig.from_dict(timeout_data) if timeout_data else None,
        )


# ============================================
# 数据源配置
# ============================================

@dataclass
class DataSourceConfig:
    """数据源配置"""
    name: str
    type: DataSourceType
    enabled: bool = True
    description: Optional[str] = None
    connection_string: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)
    pool_size: int = 5
    pool_timeout: float = 30.0
    timeout: Optional[TimeoutConfig] = None
    retry: Optional[RetryConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "type": self.type.value,
            "enabled": self.enabled,
            "description": self.description,
            "connection_string": self.connection_string,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "username": self.username,
            "password": "***" if self.password else None,
            "options": self.options,
            "pool_size": self.pool_size,
            "pool_timeout": self.pool_timeout,
        }
        if self.timeout:
            result["timeout"] = self.timeout.to_dict()
        if self.retry:
            result["retry"] = self.retry.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataSourceConfig":
        timeout_data = data.get("timeout")
        retry_data = data.get("retry")
        return cls(
            name=data["name"],
            type=DataSourceType(data.get("type", "sqlite")),
            enabled=data.get("enabled", True),
            description=data.get("description"),
            connection_string=data.get("connection_string"),
            host=data.get("host"),
            port=data.get("port"),
            database=data.get("database"),
            username=data.get("username"),
            password=data.get("password"),
            options=data.get("options", {}),
            pool_size=data.get("pool_size", 5),
            pool_timeout=data.get("pool_timeout", 30.0),
            timeout=TimeoutConfig.from_dict(timeout_data) if timeout_data else None,
            retry=RetryConfig.from_dict(retry_data) if retry_data else None,
        )


# ============================================
# 全局设置
# ============================================

@dataclass
class GlobalSettings:
    """全局设置"""
    # 并发设置
    max_concurrent_servers: int = 10
    max_concurrent_tools: int = 10
    max_concurrent_requests: int = 100
    
    # 默认超时
    default_timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    
    # 日志设置
    log_level: str = "INFO"
    log_requests: bool = True
    log_responses: bool = False
    
    # 缓存设置
    cache_enabled: bool = True
    cache_ttl: int = 300  # 秒
    cache_max_size: int = 1000
    
    # 安全设置
    allow_stdio: bool = True
    allow_network: bool = True
    allowed_hosts: List[str] = field(default_factory=list)
    sandbox_enabled: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_concurrent_servers": self.max_concurrent_servers,
            "max_concurrent_tools": self.max_concurrent_tools,
            "max_concurrent_requests": self.max_concurrent_requests,
            "default_timeout": self.default_timeout.to_dict(),
            "log_level": self.log_level,
            "log_requests": self.log_requests,
            "log_responses": self.log_responses,
            "cache_enabled": self.cache_enabled,
            "cache_ttl": self.cache_ttl,
            "cache_max_size": self.cache_max_size,
            "allow_stdio": self.allow_stdio,
            "allow_network": self.allow_network,
            "allowed_hosts": self.allowed_hosts,
            "sandbox_enabled": self.sandbox_enabled,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalSettings":
        timeout_data = data.get("default_timeout", {})
        return cls(
            max_concurrent_servers=data.get("max_concurrent_servers", 10),
            max_concurrent_tools=data.get("max_concurrent_tools", 10),
            max_concurrent_requests=data.get("max_concurrent_requests", 100),
            default_timeout=TimeoutConfig.from_dict(timeout_data),
            log_level=data.get("log_level", "INFO"),
            log_requests=data.get("log_requests", True),
            log_responses=data.get("log_responses", False),
            cache_enabled=data.get("cache_enabled", True),
            cache_ttl=data.get("cache_ttl", 300),
            cache_max_size=data.get("cache_max_size", 1000),
            allow_stdio=data.get("allow_stdio", True),
            allow_network=data.get("allow_network", True),
            allowed_hosts=data.get("allowed_hosts", []),
            sandbox_enabled=data.get("sandbox_enabled", False),
        )


# ============================================
# MCP 完整配置
# ============================================

@dataclass
class MCPConfig:
    """
    MCP 完整配置
    
    配置结构:
    - version: 配置版本
    - servers: MCP 服务器列表
    - tools: 工具列表
    - data_sources: 数据源列表
    - settings: 全局设置
    """
    version: str = "2.0"
    servers: List[ServerConfig] = field(default_factory=list)
    tools: List[ToolConfig] = field(default_factory=list)
    data_sources: List[DataSourceConfig] = field(default_factory=list)
    settings: GlobalSettings = field(default_factory=GlobalSettings)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "version": self.version,
            "servers": [s.to_dict() for s in self.servers],
            "tools": [t.to_dict() for t in self.tools],
            "data_sources": [d.to_dict() for d in self.data_sources],
            "settings": self.settings.to_dict(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPConfig":
        """从字典反序列化，支持两种格式：
        
        格式1 (数组格式):
            servers: [{name: "x", ...}]
            
        格式2 (字典格式，Letta/Mem0 兼容):
            servers: {"x": {...}, "y": {...}}
        """
        # 解析服务器配置
        servers = []
        servers_data = data.get("servers", [])
        
        # 检查是字典格式还是数组格式
        if isinstance(servers_data, dict):
            # 字典格式 (Letta/Mem0 风格)
            for server_name, server_config in servers_data.items():
                if isinstance(server_config, dict):
                    # 添加 name 字段（如果不存在）
                    server_config = dict(server_config)  # 复制避免修改原数据
                    if "name" not in server_config:
                        server_config["name"] = server_name
                    try:
                        servers.append(parse_server_config(server_config))
                    except Exception as e:
                        logger.warning(f"解析服务器配置失败 {server_name}: {e}")
        else:
            # 数组格式
            for server_data in servers_data:
                try:
                    servers.append(parse_server_config(server_data))
                except Exception as e:
                    logger.warning(f"解析服务器配置失败: {e}")
        
        # 解析工具配置
        tools = []
        tools_data = data.get("tools", [])
        if isinstance(tools_data, dict):
            for tool_name, tool_config in tools_data.items():
                if isinstance(tool_config, dict):
                    tool_config = dict(tool_config)
                    if "name" not in tool_config:
                        tool_config["name"] = tool_name
                    tools.append(ToolConfig.from_dict(tool_config))
        else:
            tools = [ToolConfig.from_dict(t) for t in tools_data]
        
        # 解析数据源配置
        data_sources = []
        ds_data = data.get("data_sources", [])
        if isinstance(ds_data, dict):
            for ds_name, ds_config in ds_data.items():
                if isinstance(ds_config, dict):
                    ds_config = dict(ds_config)
                    if "name" not in ds_config:
                        ds_config["name"] = ds_name
                    data_sources.append(DataSourceConfig.from_dict(ds_config))
        else:
            data_sources = [DataSourceConfig.from_dict(d) for d in ds_data]
        
        # 解析全局设置
        settings = GlobalSettings.from_dict(data.get("settings", {}))
        
        return cls(
            version=data.get("version", "2.0"),
            servers=servers,
            tools=tools,
            data_sources=data_sources,
            settings=settings,
        )
    
    def get_server(self, name: str) -> Optional[ServerConfig]:
        """获取服务器配置"""
        for server in self.servers:
            if server.name == name:
                return server
        return None
    
    def get_tool(self, name: str) -> Optional[ToolConfig]:
        """获取工具配置"""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None
    
    def get_data_source(self, name: str) -> Optional[DataSourceConfig]:
        """获取数据源配置"""
        for ds in self.data_sources:
            if ds.name == name:
                return ds
        return None
    
    def get_enabled_servers(self) -> List[ServerConfig]:
        """获取启用的服务器列表"""
        return [s for s in self.servers if s.enabled]
    
    def get_enabled_tools(self) -> List[ToolConfig]:
        """获取启用的工具列表"""
        return [t for t in self.tools if t.enabled]
    
    def get_enabled_data_sources(self) -> List[DataSourceConfig]:
        """获取启用的数据源列表"""
        return [d for d in self.data_sources if d.enabled]
    
    def get_servers_by_tag(self, tag: str) -> List[ServerConfig]:
        """按标签获取服务器"""
        return [s for s in self.servers if tag in s.tags]


# ============================================
# 配置加载器
# ============================================

class ConfigLoader:
    """配置加载器"""
    
    # 环境变量模板正则
    ENV_VAR_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')
    
    # 默认配置文件路径（按优先级）
    DEFAULT_CONFIG_PATHS = ["config/mcp.yaml", "config/mcp.yml", "config/mcp.json"]
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径，默认为按优先级查找 config/mcp.{yaml,yml,json}
        """
        if config_path is not None:
            self.config_paths = [Path(config_path)]
        else:
            self.config_paths = [Path(p) for p in self.DEFAULT_CONFIG_PATHS]
        self._config: Optional[MCPConfig] = None
        self._last_modified: Optional[float] = None
    
    def load(self, path: Optional[str] = None) -> MCPConfig:
        """
        加载配置（按优先级查找第一个存在的文件）
        
        Args:
            path: 配置文件路径（可选，默认使用初始化时指定的路径）
        
        Returns:
            MCP 配置实例
        """
        # 确定搜索路径
        search_paths = self.config_paths
        if path:
            search_paths = [Path(path)]
        
        # 按优先级查找第一个存在的文件
        config_path = None
        for p in search_paths:
            if p.exists():
                config_path = p
                break
        
        if config_path is None:
            logger.warning(f"未找到配置文件，搜索路径: {[str(p) for p in search_paths]}，使用默认配置")
            self._config = MCPConfig()
            return self._config
        
        # 读取文件
        suffix = config_path.suffix.lower()
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                if suffix in ['.yaml', '.yml']:
                    data = yaml.safe_load(f)
                elif suffix == '.json':
                    data = json.load(f)
                else:
                    raise ValueError(f"不支持的配置文件格式: {suffix}")
            
            # 解析环境变量
            data = self._resolve_env_vars(data)
            
            self._config = MCPConfig.from_dict(data)
            self._last_modified = config_path.stat().st_mtime
            
            logger.info(f"加载配置文件: {config_path}")
            return self._config
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise
    
    def _resolve_env_vars(self, data: Any) -> Any:
        """递归解析环境变量"""
        if isinstance(data, str):
            # 替换 ${VAR_NAME} 为环境变量值
            def replace_env(match) -> str:
                var_name = match.group(1)
                env_value = os.environ.get(var_name)
                if env_value is not None:
                    return env_value
                # 如果环境变量不存在，保留原始占位符
                return match.group(0)
            return self.ENV_VAR_PATTERN.sub(replace_env, data)
        elif isinstance(data, dict):
            return {k: self._resolve_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._resolve_env_vars(item) for item in data]
        else:
            return data
    
    def reload(self) -> MCPConfig:
        """重新加载配置"""
        if not self.config_paths:
            raise ValueError("未设置配置文件路径")
        # 使用第一个路径重新加载
        return self.load(str(self.config_paths[0]))
    
    def check_modified(self) -> bool:
        """检查配置文件是否被修改"""
        if not self.config_paths or not self._last_modified:
            return False
        
        try:
            # 检查第一个存在的配置文件
            for p in self.config_paths:
                if p.exists():
                    current_modified = p.stat().st_mtime
                    return current_modified > self._last_modified
            return False
        except Exception:
            return False
    
    def get_config(self) -> Optional[MCPConfig]:
        """获取当前配置"""
        return self._config


def load_config(path: Optional[str] = None) -> MCPConfig:
    """
    加载配置（便捷函数）
    
    Args:
        path: 配置文件路径，默认为按优先级查找 config/mcp.{yaml,yml,json}
    
    Returns:
        MCPConfig 实例
    """
    if path is not None:
        loader = ConfigLoader(path)
    else:
        loader = ConfigLoader()  # 使用多路径默认配置
    return loader.load()


def get_default_config() -> MCPConfig:
    """
    获取默认配置
    
    按优先级查找 config/mcp.{yaml,yml,json} 加载配置，
    如果所有配置文件都不存在则返回内置默认配置。
    
    Returns:
        MCPConfig 实例
    """
    loader = ConfigLoader()
    config = loader.load()
    # 如果没有任何配置加载成功（servers/tools 都为空），回退到内置默认配置
    if not config.servers and not config.tools and not config.data_sources:
        return _get_builtin_default_config()
    return config


def _get_builtin_default_config() -> MCPConfig:
    """
    获取内置默认配置（当配置文件不存在时使用）
    
    Returns:
        MCPConfig 实例
    """
    return MCPConfig(
        servers=[
            StdioServerConfig(
                name="local_tools",
                command="python",
                args=["-m", "mcp_tools"],
                description="本地 MCP 工具服务器",
                tags=["local", "tools"],
            ),
            SSEServerConfig(
                name="remote_api",
                url="https://api.example.com/mcp",
                description="远程 API 服务器",
                auth=AuthConfig(
                    type=AuthType.BEARER,
                    token="${API_TOKEN}",
                ),
                tags=["remote", "api"],
            ),
        ],
        tools=[
            ToolConfig(
                name="web_search",
                type=ToolType.BUILTIN,
                description="网络搜索工具",
                enabled=True,
            ),
            ToolConfig(
                name="knowledge_query",
                type=ToolType.MCP,
                server="local_tools",
                description="知识库查询工具",
                enabled=True,
            ),
        ],
        data_sources=[
            DataSourceConfig(
                name="knowledge_base",
                type=DataSourceType.SQLITE,
                database="data/knowledge.db",
                description="知识库数据库",
                enabled=True,
            ),
        ],
    )