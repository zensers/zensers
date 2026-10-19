# -*- coding: utf-8 -*-
"""
MCP API Module
==============

Provides MCP server management API endpoints:
- List all MCP servers and their status
- Start/stop specific servers
- Get server health status
"""

import logging
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.core.mcp.config import MCPConfig, ConfigLoader, ServerConfig, TransportType
from src.core.mcp.server import MCPServer, ServerState
from src.core.mcp.client import MCPClient, ClientState
from src.core.mcp.health import MCPHealthChecker, ServerHealth

logger = logging.getLogger(__name__)

# ============ Pydantic Models ============

class MCPServerInfo(BaseModel):
    """MCP Server Info"""
    name: str
    transport: str
    enabled: bool
    status: str  # running, stopped, starting, stopping, error, disabled
    description: Optional[str] = None
    tools_count: int = 0
    latency_ms: float = 0.0
    error: Optional[str] = None
    tags: List[str] = []


class MCPServerListResponse(BaseModel):
    """MCP Server List Response"""
    servers: List[MCPServerInfo]
    total: int
    healthy_count: int
    running_count: int


class MCPServerActionRequest(BaseModel):
    """MCP Server Action Request"""
    server_name: str


class MCPServerActionResponse(BaseModel):
    """MCP Server Action Response"""
    success: bool
    message: str
    server_name: str
    new_status: str


# ============ MCP Service Manager ============

class MCPServiceManager:
    """
    MCP Service Manager
    
    Singleton pattern, manages the lifecycle of all MCP servers.
    """
    
    _instance: Optional["MCPServiceManager"] = None
    
    def __init__(self):
        self._config: Optional[MCPConfig] = None
        self._servers: Dict[str, MCPServer] = {}
        self._clients: Dict[str, MCPClient] = {}
        self._health_checker = MCPHealthChecker()
        self._load_config()
    
    @classmethod
    def get_instance(cls) -> "MCPServiceManager":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _load_config(self) -> None:
        """Load MCP config"""
        try:
            loader = ConfigLoader()
            self._config = loader.load()
            logger.info(f"Loaded MCP config: {len(self._config.servers)} servers")
        except Exception as e:
            logger.warning(f"Failed to load MCP config: {e}, using default config")
            self._config = MCPConfig()
    
    def reload_config(self) -> None:
        """Reload config"""
        self._load_config()
    
    def get_config(self) -> MCPConfig:
        """Get current config"""
        return self._config
    
    def list_servers(self) -> List[MCPServerInfo]:
        """List all servers and their status"""
        result = []
        
        for server_config in self._config.servers:
            name = server_config.name
            
            # Determine status
            if not server_config.enabled:
                status = "disabled"
            elif name in self._servers:
                server = self._servers[name]
                status = server.state.value
            else:
                status = "stopped"
            
            # Get health info
            health = self._health_checker.get_server_health(name)
            tools_count = health.tools_count if health else 0
            latency_ms = health.latency_ms if health else 0.0
            error = health.error if health else None
            
            # Get transport type
            transport = server_config.transport.value if hasattr(server_config, 'transport') else 'stdio'
            
            # Get description
            description = getattr(server_config, 'description', None)
            tags = getattr(server_config, 'tags', [])
            
            result.append(MCPServerInfo(
                name=name,
                transport=transport,
                enabled=server_config.enabled,
                status=status,
                description=description,
                tools_count=tools_count,
                latency_ms=latency_ms,
                error=error,
                tags=tags,
            ))
        
        return result
    
    async def start_server(self, name: str) -> MCPServerActionResponse:
        """Start specified server"""
        # Find server config
        server_config = self._config.get_server(name)
        if not server_config:
            raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
        
        if not server_config.enabled:
            raise HTTPException(status_code=400, detail=f"Server '{name}' is disabled")
        
        # Check if already running
        if name in self._servers:
            server = self._servers[name]
            if server.state == ServerState.RUNNING:
                return MCPServerActionResponse(
                    success=True,
                    message=f"Server '{name}' is already running",
                    server_name=name,
                    new_status="running"
                )
        
        try:
            # Create and start server
            server = MCPServer(self._config)
            server.start()
            self._servers[name] = server
            
            # Create client and connect
            client = MCPClient(server=server)
            await client.connect()
            self._clients[name] = client
            
            # Perform health check
            health = await self._health_checker.check_server(client, name)
            
            logger.info(f"MCP server '{name}' started")
            
            return MCPServerActionResponse(
                success=True,
                message=f"Server '{name}' started successfully",
                server_name=name,
                new_status="running"
            )
            
        except Exception as e:
            logger.error(f"Failed to start MCP server '{name}': {e}")
            # Cleanup
            if name in self._servers:
                del self._servers[name]
            if name in self._clients:
                del self._clients[name]
            
            return MCPServerActionResponse(
                success=False,
                message=f"Start failed: {str(e)}",
                server_name=name,
                new_status="error"
            )
    
    async def stop_server(self, name: str) -> MCPServerActionResponse:
        """Stop specified server"""
        if name not in self._servers:
            return MCPServerActionResponse(
                success=True,
                message=f"Server '{name}' is not running",
                server_name=name,
                new_status="stopped"
            )
        
        try:
            # Disconnect client
            if name in self._clients:
                self._clients[name].disconnect()
                del self._clients[name]
            
            # Stop server
            server = self._servers[name]
            server.stop()
            del self._servers[name]
            
            logger.info(f"MCP server '{name}' stopped")
            
            return MCPServerActionResponse(
                success=True,
                message=f"Server '{name}' stopped",
                server_name=name,
                new_status="stopped"
            )
            
        except Exception as e:
            logger.error(f"Failed to stop MCP server '{name}': {e}")
            return MCPServerActionResponse(
                success=False,
                message=f"Stop failed: {str(e)}",
                server_name=name,
                new_status="error"
            )
    
    async def check_health(self) -> Dict[str, Any]:
        """Check health of all servers"""
        return await self._health_checker.check_all(self._clients)
    
    def get_server(self, name: str) -> Optional[MCPServer]:
        """Get server instance"""
        return self._servers.get(name)
    
    def get_client(self, name: str) -> Optional[MCPClient]:
        """Get client instance"""
        return self._clients.get(name)


# ============ API Routes ============

router = APIRouter(prefix="/mcp", tags=["MCP"])

# Global service manager instance
_manager: Optional[MCPServiceManager] = None


def get_manager() -> MCPServiceManager:
    """Get service manager instance"""
    global _manager
    if _manager is None:
        _manager = MCPServiceManager.get_instance()
    return _manager


@router.get("/servers", response_model=MCPServerListResponse)
async def list_mcp_servers():
    """
    List all MCP servers and their status
    
    Returns server list including name, transport type, status, tool count and other info.
    """
    manager = get_manager()
    servers = manager.list_servers()
    
    running_count = sum(1 for s in servers if s.status == "running")
    healthy_count = sum(1 for s in servers if s.status == "running" and s.error is None)
    
    return MCPServerListResponse(
        servers=servers,
        total=len(servers),
        healthy_count=healthy_count,
        running_count=running_count,
    )


@router.post("/servers/{server_name}/start", response_model=MCPServerActionResponse)
async def start_mcp_server(server_name: str):
    """
    Start specified MCP server
    
    Args:
        server_name: Server name
    """
    manager = get_manager()
    return await manager.start_server(server_name)


@router.post("/servers/{server_name}/stop", response_model=MCPServerActionResponse)
async def stop_mcp_server(server_name: str):
    """
    Stop specified MCP server
    
    Args:
        server_name: Server name
    """
    manager = get_manager()
    return await manager.stop_server(server_name)


@router.get("/servers/{server_name}/status")
async def get_mcp_server_status(server_name: str):
    """
    Get single MCP server status
    
    Args:
        server_name: Server name
    """
    manager = get_manager()
    servers = manager.list_servers()
    
    for server in servers:
        if server.name == server_name:
            return server
    
    raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found")


@router.get("/health")
async def get_mcp_health():
    """
    Get all MCP servers health status
    
    Returns health check summary information.
    """
    manager = get_manager()
    health = await manager.check_health()
    summary = manager._health_checker.get_summary()
    
    return {
        "summary": summary,
        "details": {name: h.__dict__ for name, h in health.items()}
    }


@router.post("/reload")
async def reload_mcp_config():
    """
    Reload MCP configuration
    
    Reload MCP server configuration from config file.
    """
    manager = get_manager()
    manager.reload_config()
    
    return {
        "success": True,
        "message": "Configuration reloaded",
        "servers_count": len(manager.get_config().servers)
    }


# ============ Exports ============

__all__ = ["router", "MCPServiceManager", "get_manager"]
