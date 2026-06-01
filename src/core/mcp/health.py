"""
MCP Health Checks

Periodic health checks for connected MCP servers.
Reports connectivity, latency, and tool availability.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ServerHealth:
    """Health status for a single MCP server"""
    name: str
    status: str  # "healthy", "unhealthy", "disconnected"
    tools_count: int = 0
    latency_ms: float = 0.0
    last_checked: str = ""
    error: Optional[str] = None
    consecutive_failures: int = 0


class MCPHealthChecker:
    """
    Health checker for MCP servers.

    Provides:
    - Per-server health check via tool discovery ping
    - Batch health check for all connected servers
    - Failure tracking with consecutive failure count
    """

    def __init__(self):
        self._results: Dict[str, ServerHealth] = {}

    async def check_server(self, client: Any, server_name: str) -> ServerHealth:
        """Check health of a single MCP server by attempting tool discovery"""
        import time

        start = time.monotonic()
        health = ServerHealth(name=server_name, status="unhealthy", last_checked=datetime.now().isoformat())

        try:
            tools = await client.discover_tools()
            health.latency_ms = (time.monotonic() - start) * 1000
            if tools is not None:
                health.status = "healthy"
                health.tools_count = len(tools)
                health.consecutive_failures = 0
            else:
                health.status = "unhealthy"
                health.consecutive_failures += 1
        except Exception as e:
            health.status = "unhealthy"
            health.error = str(e)
            health.consecutive_failures = getattr(
                self._results.get(server_name), "consecutive_failures", 0
            ) + 1

        self._results[server_name] = health
        return health

    async def check_all(self, clients: Dict[str, Any]) -> Dict[str, ServerHealth]:
        """Check health of all connected MCP servers"""
        results: Dict[str, ServerHealth] = {}
        for server_name, client in clients.items():
            results[server_name] = await self.check_server(client, server_name)
        return results

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all server health statuses"""
        healthy = sum(1 for h in self._results.values() if h.status == "healthy")
        unhealthy = sum(1 for h in self._results.values() if h.status == "unhealthy")
        total = len(self._results)

        return {
            "total_servers": total,
            "healthy": healthy,
            "unhealthy": unhealthy,
            "healthy_ratio": healthy / total if total > 0 else 0,
            "last_check": max(
                (h.last_checked for h in self._results.values()),
                default="",
            ),
        }

    def get_server_health(self, server_name: str) -> Optional[ServerHealth]:
        """Get health status for a specific server"""
        return self._results.get(server_name)

    def get_unhealthy_servers(self) -> List[ServerHealth]:
        """Get list of unhealthy servers"""
        return [h for h in self._results.values() if h.status != "healthy"]
