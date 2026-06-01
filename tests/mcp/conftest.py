"""
Shared fixtures for MCP tests.
"""

import pytest


class MockMCPServer:
    """In-process mock MCP server for integration testing."""

    TOOLS = {
        "wind.get_stock_data": {
            "name": "wind.get_stock_data",
            "description": "Get A-share stock market data",
            "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            "mock_result": {
                "success": True,
                "result": {
                    "stocks": [
                        {"code": "002594", "name": "BYD", "pe": 25.3, "price": 250.5},
                        {"code": "300750", "name": "CATL", "pe": 30.2, "price": 180.2},
                    ]
                },
            },
        },
        "wind.get_financials": {
            "name": "wind.get_financials",
            "description": "Get financial data",
            "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            "mock_result": {"success": True, "result": {"revenue": 1000000000, "profit": 50000000}},
        },
        "slack.send_message": {
            "name": "slack.send_message",
            "description": "Send a message to Slack channel",
            "parameters": {
                "type": "object",
                "properties": {"channel": {"type": "string"}, "text": {"type": "string"}},
                "required": ["channel", "text"],
            },
            "mock_result": {"success": True, "result": {"ts": "1234567890.1234"}},
        },
        "tool.always_fails": {
            "name": "tool.always_fails",
            "description": "A tool that always returns failure",
            "parameters": {},
            "mock_result": {"success": False, "error": "Simulated failure"},
        },
    }

    def __init__(self):
        self.started = False
        self.request_count = 0

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def list_tools(self):
        return [
            {
                "name": data["name"],
                "description": data["description"],
                "parameters": data["parameters"],
                "permissions": [],
            }
            for data in self.TOOLS.values()
        ]

    def handle_request(self, request):
        self.request_count += 1
        tool_name = request.get("tool", "")
        tool_data = self.TOOLS.get(tool_name)
        if not tool_data:
            from dataclasses import dataclass
            from typing import Optional

            @dataclass
            class MockResponse:
                request_id: str
                success: bool
                result: Optional[dict] = None
                error: Optional[str] = None
                duration_ms: float = 0.0

                def to_dict(self):
                    return {
                        "request_id": self.request_id,
                        "success": self.success,
                        "result": self.result,
                        "error": self.error,
                        "duration_ms": self.duration_ms,
                    }

            return MockResponse(
                request_id=request.get("request_id", ""),
                success=False,
                error=f"Unknown tool: {tool_name}",
            )

        from dataclasses import dataclass
        from typing import Optional

        @dataclass
        class MockResponse:
            request_id: str
            success: bool
            result: Optional[dict] = None
            error: Optional[str] = None
            duration_ms: float = 0.0

            def to_dict(self):
                return {
                    "request_id": self.request_id,
                    "success": self.success,
                    "result": self.result,
                    "error": self.error,
                    "duration_ms": self.duration_ms,
                }

        result = tool_data["mock_result"]
        return MockResponse(
            request_id=request.get("request_id", ""),
            success=result.get("success", False),
            result=result.get("result"),
            error=result.get("error"),
        )


@pytest.fixture
def mock_server():
    return MockMCPServer()
