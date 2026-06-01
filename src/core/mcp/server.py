# -*- coding: utf-8 -*-
"""
MCP Server 模块
===============

Phase 5 Week 19: MCP 基础架构 - MCP Server

功能特性:
- MCP Server 初始化
- 工具注册和管理
- 请求处理
- 事件通知
"""

import os
import json
import time
import threading
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
import logging
import uuid

from src.core.mcp.config import MCPConfig, ToolConfig
from src.core.mcp.tool_registry import ToolRegistry, Tool

logger = logging.getLogger(__name__)


class ServerState(Enum):
    """服务器状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


@dataclass
class RequestContext:
    """请求上下文"""
    request_id: str
    tool_name: str
    params: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    user: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class Response:
    """响应"""
    request_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "request_id": self.request_id,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class MCPServer:
    """
    MCP 服务器
    
    提供工具调用和数据访问服务。
    
    使用示例:
        server = MCPServer(config)
        server.register_tool("my_tool", my_handler)
        server.start()
        
        # 处理请求
        response = server.handle_request(request)
        
        server.stop()
    """
    
    def __init__(
        self,
        config: Optional[MCPConfig] = None,
        tool_registry: Optional[ToolRegistry] = None
    ):
        """
        初始化 MCP 服务器
        
        Args:
            config: MCP 配置
            tool_registry: 工具注册表
        """
        self.config = config or MCPConfig()
        self.tool_registry = tool_registry or ToolRegistry()
        self._state = ServerState.STOPPED
        self._lock = Lock()
        self._request_handlers: Dict[str, Callable] = {}
        self._event_listeners: List[Callable] = []
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
        }
    
    @property
    def state(self) -> ServerState:
        """获取服务器状态"""
        return self._state
    
    def start(self) -> None:
        """启动服务器"""
        with self._lock:
            if self._state == ServerState.RUNNING:
                logger.warning("服务器已在运行")
                return
            
            self._state = ServerState.STARTING
            logger.info("启动 MCP 服务器...")
            
            # 注册配置中的工具
            self._register_config_tools()
            
            self._state = ServerState.RUNNING
            logger.info("MCP 服务器已启动")
            
            # 触发启动事件
            self._emit_event("server_started", {})
    
    def stop(self) -> None:
        """停止服务器"""
        with self._lock:
            if self._state == ServerState.STOPPED:
                return
            
            self._state = ServerState.STOPPING
            logger.info("停止 MCP 服务器...")
            
            # 清理资源
            self._request_handlers.clear()
            
            self._state = ServerState.STOPPED
            logger.info("MCP 服务器已停止")
            
            # 触发停止事件
            self._emit_event("server_stopped", {})
    
    def _register_config_tools(self) -> None:
        """注册配置中的工具"""
        for tool_config in self.config.get_enabled_tools():
            # 内置工具已预注册
            if tool_config.type.value == "builtin":
                logger.debug(f"内置工具已就绪: {tool_config.name}")
                continue
            
            # 自定义工具需要动态加载
            if tool_config.type.value == "custom" and tool_config.module:
                try:
                    self._load_custom_tool(tool_config)
                except Exception as e:
                    logger.error(f"加载自定义工具失败 {tool_config.name}: {e}")
    
    def _load_custom_tool(self, config: ToolConfig) -> None:
        """加载自定义工具"""
        import importlib
        
        module = importlib.import_module(config.module)
        
        # 查找工具类或函数
        if hasattr(module, 'Tool'):
            tool_class = getattr(module, 'Tool')
            tool = tool_class(config.name, config.config)
            self.tool_registry.register(tool)
        elif hasattr(module, 'handler'):
            handler = getattr(module, 'handler')
            self.register_handler(config.name, handler)
        else:
            raise ValueError(f"模块 {config.module} 未定义 Tool 类或 handler 函数")
        
        logger.info(f"加载自定义工具: {config.name}")
    
    def register_handler(self, tool_name: str, handler: Callable) -> None:
        """
        注册请求处理器
        
        Args:
            tool_name: 工具名称
            handler: 处理函数
        """
        self._request_handlers[tool_name] = handler
        logger.debug(f"注册处理器: {tool_name}")
    
    def register_tool(self, tool: Tool) -> None:
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        self.tool_registry.register(tool)
    
    def handle_request(self, request: Dict[str, Any]) -> Response:
        """
        处理请求
        
        Args:
            request: 请求字典
        
        Returns:
            响应对象
        """
        if self._state != ServerState.RUNNING:
            return Response(
                request_id=request.get("request_id", ""),
                success=False,
                error="服务器未运行"
            )
        
        request_id = request.get("request_id", str(uuid.uuid4()))
        tool_name = request.get("tool", "")
        params = request.get("params", {})
        
        start_time = time.time()
        self._stats["total_requests"] += 1
        
        # 创建请求上下文
        context = RequestContext(
            request_id=request_id,
            tool_name=tool_name,
            params=params,
            user=request.get("user"),
            session_id=request.get("session_id"),
        )
        
        try:
            # 查找处理器
            handler = self._request_handlers.get(tool_name)
            
            if not handler:
                # 尝试从工具注册表查找
                tool = self.tool_registry.get(tool_name)
                if tool:
                    handler = tool.execute
            
            if not handler:
                self._stats["failed_requests"] += 1
                return Response(
                    request_id=request_id,
                    success=False,
                    error=f"未知工具: {tool_name}"
                )
            
            # 执行处理器
            result = handler(context, params)
            
            self._stats["successful_requests"] += 1
            
            return Response(
                request_id=request_id,
                success=True,
                result=result,
                duration_ms=(time.time() - start_time) * 1000
            )
            
        except Exception as e:
            self._stats["failed_requests"] += 1
            logger.error(f"处理请求失败: {e}")
            
            return Response(
                request_id=request_id,
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
    
    def add_event_listener(self, listener: Callable) -> None:
        """
        添加事件监听器
        
        Args:
            listener: 监听函数
        """
        self._event_listeners.append(listener)
    
    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """触发事件"""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }
        
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception as e:
                logger.warning(f"事件监听器错误: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "state": self._state.value,
            "tools_registered": self.tool_registry.count(),
            "handlers_registered": len(self._request_handlers),
            **self._stats,
        }
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有可用工具"""
        tools = self.tool_registry.list_all()
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in tools
        ]