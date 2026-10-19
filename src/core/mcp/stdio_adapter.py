"""
Stdio MCP Server Adapter

Wraps a subprocess-based stdio MCP server as a local MCPServer-compatible interface.
Uses synchronous subprocess communication — safe within async test environments.
"""

import json
import logging
import subprocess
import time
from typing import Any, Dict, List, Optional

from src.core.mcp.server import Response

logger = logging.getLogger(__name__)


class StdioServerAdapter:
    """
    Adapter that wraps a stdio-based MCP subprocess as a local MCPServer.

    All communication is synchronous via subprocess stdin/stdout.
    Safe to use within async test environments (no event loop conflicts).

    Usage:
        adapter = StdioServerAdapter(python_path, script_path, cwd)
        adapter.start()
        response = adapter.handle_request({"tool": "query", "params": {...}})
        tools = adapter.list_tools()
        adapter.stop()
    """

    def __init__(
        self,
        python_path: str,
        script_path: str,
        cwd: Optional[str] = None,
    ):
        self._python_path = python_path
        self._script_path = script_path
        self._cwd = cwd
        self._proc: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._initialized = False

    def start(self) -> None:
        """Spawn the subprocess (idempotent)"""
        if self._proc is not None:
            return  # already started
        self._proc = subprocess.Popen(
            [self._python_path, self._script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self._cwd,
        )
        logger.info(f"Started stdio MCP server: {self._script_path}")

    def stop(self) -> None:
        """Terminate the subprocess"""
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            self._proc = None
            self._initialized = False

    def handle_request(self, request: Dict[str, Any]) -> Response:
        """
        Handle a tool request via stdio JSON-RPC (synchronous).

        Called by MCPClient.call_tool() in local mode.
        """
        tool_name = request.get("tool", "")
        params = request.get("params", {})
        request_id = request.get("request_id", str(self._request_id))
        start_time = time.time()

        try:
            if not self._initialized:
                self._initialize()

            self._request_id += 1
            self._write({
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": params},
            })
            r = self._read()
            duration_ms = (time.time() - start_time) * 1000

            if "error" in r:
                return Response(
                    request_id=request_id, success=False,
                    error=r["error"].get("message", str(r["error"])),
                    duration_ms=duration_ms,
                )

            result = r.get("result", {})
            if result.get("isError", False):
                return Response(
                    request_id=request_id, success=False,
                    error=str(result.get("content", "Unknown error")),
                    duration_ms=duration_ms,
                )

            return Response(
                request_id=request_id, success=True,
                result=result, duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"Stdio request failed: {e}")
            return Response(
                request_id=request_id, success=False, error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools (synchronous)"""
        try:
            if not self._initialized:
                self._initialize()
            self._request_id += 1
            self._write({
                "jsonrpc": "2.0", "id": self._request_id,
                "method": "tools/list", "params": {},
            })
            r = self._read()
            return r.get("result", {}).get("tools", [])
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            return []

    def _initialize(self) -> None:
        """Run MCP initialization sequence"""
        self._request_id += 1
        self._write({
            "jsonrpc": "2.0", "id": self._request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "Zensers-mcp", "version": "1.0"},
            },
        })
        self._read()  # consume initialize response

        # Send initialized notification (no response)
        self._write({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })
        self._initialized = True

    def _write(self, data: Dict) -> None:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("Subprocess not running")
        line = json.dumps(data) + "\n"
        self._proc.stdin.write(line.encode())
        self._proc.stdin.flush()

    def _read(self) -> Dict:
        if not self._proc or not self._proc.stdout:
            raise RuntimeError("Subprocess not running")
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError("Subprocess stdout closed")
        return json.loads(line.decode())
