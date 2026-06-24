"""
MCP Client Module

Handles MCP server connections and tool invocations.
Supports local mode (direct server instance) and remote mode (SSE/HTTP transport).
"""

import json
import time
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional

from .config import TransportType, ServerConfig

logger = logging.getLogger(__name__)


class ClientState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


@dataclass
class Request:
    """MCP tool request"""
    request_id: str
    tool: str
    params: Dict[str, Any] = field(default_factory=dict)
    timeout: float = 30.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "tool": self.tool,
            "params": self.params,
        }


@dataclass
class ToolMeta:
    """Metadata for an MCP tool, returned by discover_tools()"""
    name: str
    description: str
    parameters: Dict[str, Any]
    permissions: List[str] = field(default_factory=list)


@dataclass
class ClientConfig:
    """Configuration for MCP client."""
    pass


class MCPClient:
    """
    MCP client for connecting to MCP servers and invoking tools.

    Supports two modes:
    - Local mode: direct MCPServer instance (no network)
    - Remote mode: SSE or HTTP transport with auth support
    """

    def __init__(
        self,
        server_config: Optional[ServerConfig] = None,
        credential_manager: Optional[Any] = None,
        rate_limiter: Optional[Any] = None,
        server: Optional[Any] = None,
    ):
        """
        Args:
            server_config: MCP server configuration (required for remote mode)
            credential_manager: CredentialManager instance for auth
            rate_limiter: RateLimiter instance for rate control
            server: Direct MCPServer instance (local mode)
        """
        self.config = server_config
        self._credential_manager = credential_manager
        self._rate_limiter = rate_limiter
        self._server = server
        self._state = ClientState.DISCONNECTED
        self._lock = Lock()
        self._http_session: Optional[Any] = None
        self._tool_cache: Dict[str, ToolMeta] = {}

        # Latency tracking (used by health checks)
        self.last_request_latency: float = 0.0

        self._stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
        }

    @property
    def state(self) -> ClientState:
        return self._state

    async def connect(self) -> bool:
        """Establish connection to the MCP server"""
        with self._lock:
            if self._state == ClientState.CONNECTED:
                return True
            self._state = ClientState.CONNECTING

        try:
            if self._server:
                # Local mode: start the embedded server
                if hasattr(self._server, 'start'):
                    self._server.start()
                self._set_state(ClientState.CONNECTED)
                logger.info("MCP client connected (local mode)")
                return True

            if self.config and self.config.transport in (
                TransportType.SSE, TransportType.STREAMABLE_HTTP
            ):
                # Remote mode: establish HTTP session with auth
                await self._connect_remote()
                self._set_state(ClientState.CONNECTED)
                server_url = getattr(self.config, 'url', 'unknown')
                logger.info(f"MCP client connected (remote): {server_url}")
                return True

            logger.warning("MCP client: no server or server_config provided")
            self._set_state(ClientState.DISCONNECTED)
            return False

        except Exception as e:
            logger.error(f"MCP client connection failed: {e}")
            self._set_state(ClientState.DISCONNECTED)
            return False

    async def _connect_remote(self) -> None:
        """Establish remote HTTP session with auth headers"""
        import aiohttp

        headers = {}
        if self._credential_manager and self.config and self.config.name:
            auth = self._credential_manager.get_auth(self.config.name)
            if auth:
                headers.update(auth.build_headers())

        timeout = aiohttp.ClientTimeout(
            total=self.config.timeout.total if self.config and self.config.timeout else 120,
            connect=self.config.timeout.connect if self.config and self.config.timeout else 10,
        )

        server_url = getattr(self.config, 'url', '').rstrip("/") if self.config else ""
        self._http_session = aiohttp.ClientSession(
            base_url=server_url,
            headers=headers,
            timeout=timeout,
        )

    async def discover_tools(self) -> List[ToolMeta]:
        """Query the MCP server for available tools via the tools/list endpoint"""
        if self._tool_cache:
            return list(self._tool_cache.values())

        if self._server:
            tools_data = self._server.list_tools()
            for t in tools_data:
                meta = ToolMeta(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    parameters=t.get("parameters", {}),
                    permissions=t.get("permissions", []),
                )
                self._tool_cache[meta.name] = meta
            return list(self._tool_cache.values())

        session = self._http_session
        if not session:
            logger.warning("Cannot discover tools: client not connected")
            return []

        async with session.post("/tools/list", json={}) as resp:
            data = await resp.json()

        for tool_data in data.get("tools", []):
            meta = ToolMeta(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                parameters=tool_data.get("parameters", {}),
                permissions=tool_data.get("permissions", []),
            )
            self._tool_cache[meta.name] = meta

        return list(self._tool_cache.values())

    async def call_tool(self, tool_name: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Invoke an MCP tool.

        Handles auth, rate limiting, 401 refresh+retry, and latency tracking.
        """
        # Rate limiting check
        if self._rate_limiter and not self._rate_limiter.acquire():
            return {
                "success": False,
                "error": "rate_limit_exceeded",
                "retry_after": self._rate_limiter.retry_after(),
            }

        if self._state != ClientState.CONNECTED:
            return {"success": False, "error": "client_not_connected"}

        start_time = time.monotonic()
        self._stats["total_calls"] += 1

        try:
            if self._server:
                # Local mode
                req = Request(
                    request_id=str(uuid.uuid4()),
                    tool=tool_name,
                    params=params or {},
                )
                response = self._server.handle_request(req.to_dict())
                self.last_request_latency = (time.monotonic() - start_time) * 1000
                if response.success:
                    self._stats["successful_calls"] += 1
                else:
                    self._stats["failed_calls"] += 1
                return response.to_dict()

            if self._http_session:
                # Remote mode with auth handling
                result = await self._remote_call(tool_name, params or {})
                self.last_request_latency = (time.monotonic() - start_time) * 1000
                return result

            self._stats["failed_calls"] += 1
            return {"success": False, "error": "no_transport_available"}

        except Exception as e:
            self._stats["failed_calls"] += 1
            self.last_request_latency = (time.monotonic() - start_time) * 1000
            logger.error(f"Tool call failed: {tool_name}: {e}")
            return {"success": False, "error": str(e), "error_code": "call_failed"}

    async def _remote_call(self, tool_name: str, params: Dict) -> Dict[str, Any]:
        """Execute a remote tool call with auth retry logic"""
        session = self._http_session
        if not session:
            return {"success": False, "error": "no_http_session"}

        server_name = getattr(self.config, 'name', 'unknown') if self.config else 'unknown'
        payload = {"tool": tool_name, "params": params}

        async with session.post("/tools/call", json=payload) as resp:
            if resp.status == 401:
                # Token expired — attempt refresh and retry once
                if self._credential_manager:
                    refreshed = await self._credential_manager.refresh(server_name)
                    if refreshed:
                        auth = self._credential_manager.get_auth(server_name)
                        if auth:
                            headers = auth.build_headers()
                            if headers and hasattr(session, '_default_headers'):
                                session._default_headers.update(headers)
                        async with session.post("/tools/call", json=payload) as retry_resp:
                            if retry_resp.status == 200:
                                self._stats["successful_calls"] += 1
                                return await retry_resp.json()
                            return {
                                "success": False,
                                "error": "auth_refresh_failed",
                                "status_code": retry_resp.status,
                            }
                return {"success": False, "error": "auth_failed", "status_code": 401}

            if resp.status == 429:
                data = await resp.json()
                return {
                    "success": False,
                    "error": "server_rate_limit",
                    "retry_after": int(resp.headers.get("Retry-After", data.get("retry_after", 60))),
                }

            if resp.status != 200:
                self._stats["failed_calls"] += 1
                return {"success": False, "error": f"server_error_{resp.status}", "status_code": resp.status}

            self._stats["successful_calls"] += 1
            return await resp.json()

    def disconnect(self) -> None:
        """Disconnect from the MCP server"""
        with self._lock:
            if self._state == ClientState.DISCONNECTED:
                return
            self._state = ClientState.DISCONNECTED

        if self._http_session:
            try:
                try:
                    from src.core.orchestrator.execution.task_utils import safe_create_task
                    safe_create_task(self._http_session.close(), name="mcp_close_session")
                except RuntimeError:
                    asyncio.run(self._http_session.close())
            except Exception:
                pass
            self._http_session = None

        self._tool_cache.clear()
        logger.info("MCP client disconnected")

    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tool metadata (synchronous, uses cache)"""
        return [
            {
                "name": meta.name,
                "description": meta.description,
                "parameters": meta.parameters,
                "permissions": meta.permissions,
            }
            for meta in self._tool_cache.values()
        ]

    def get_stats(self) -> Dict[str, Any]:
        return {"state": self._state.value, **self._stats}

    def _set_state(self, state: ClientState) -> None:
        with self._lock:
            self._state = state

    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        self.disconnect()
