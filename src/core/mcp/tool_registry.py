# -*- coding: utf-8 -*-
"""
ToolRegistry 模块
=================

Phase 5 Week 19: MCP 基础架构 - 工具注册表

功能特性:
- Tool 抽象基类
- ToolRegistry 工具注册表
- 权限验证
- 参数验证
- 工具执行管理
"""

import os
import json
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from threading import Lock
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str
    description: str
    parameters: Dict[str, Any]
    permissions: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: Optional[str] = None
    created_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "permissions": self.permissions,
            "version": self.version,
            "author": self.author,
            "created_at": self.created_at,
        }


class Tool(ABC):
    """
    工具抽象基类
    
    所有 MCP 工具必须继承此类并实现 execute 方法。
    
    使用示例:
        class WebSearchTool(Tool):
            def __init__(self):
                super().__init__(
                    name="web_search",
                    description="Search the web",
                    parameters={
                        "query": {
                            "type": "string",
                            "description": "Search query",
                            "required": True,
                        },
                    },
                )
            
            def execute(self, context, params):
                # 实现搜索逻辑
                return {"results": [...]}
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Optional[Dict[str, Any]] = None,
        permissions: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        初始化工具
        
        Args:
            name: 工具名称（唯一标识）
            description: 工具描述
            parameters: 参数定义（JSON Schema 格式）
            permissions: 所需权限列表
            metadata: 其他元数据
        """
        self.name = name
        self.description = description
        self.parameters = parameters or {}
        self.permissions = permissions or []
        self._metadata = metadata or {}
        self._created_at = datetime.now().isoformat()
    
    @abstractmethod
    def execute(self, context: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具
        
        Args:
            context: 执行上下文（请求信息）
            params: 工具参数
        
        Returns:
            执行结果
        """
        pass
    
    def validate_params(self, params: Dict[str, Any]) -> List[str]:
        """
        验证参数
        
        Args:
            params: 待验证参数
        
        Returns:
            错误列表（空列表表示验证通过）
        """
        errors = []
        
        for param_name, param_def in self.parameters.items():
            # 检查必需参数
            if param_def.get("required", False):
                if param_name not in params:
                    errors.append(f"缺少必需参数: {param_name}")
                    continue
            
            # 检查类型（如果参数存在）
            if param_name in params:
                expected_type = param_def.get("type")
                value = params[param_name]
                
                type_error = self._validate_type(param_name, value, expected_type)
                if type_error:
                    errors.append(type_error)
        
        return errors
    
    def _validate_type(
        self,
        param_name: str,
        value: Any,
        expected_type: Optional[str]
    ) -> Optional[str]:
        """验证参数类型"""
        if not expected_type:
            return None
        
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        
        expected_python_type = type_map.get(expected_type)
        if not expected_python_type:
            return None
        
        # 特殊处理：integer 可以接受 float（但会警告）
        if expected_type == "integer" and isinstance(value, float):
            if value != int(value):
                return f"参数 {param_name} 应为整数，但得到浮点数: {value}"
        
        if not isinstance(value, expected_python_type):
            return f"参数 {param_name} 类型错误: 期望 {expected_type}, 实际 {type(value).__name__}"
        
        return None
    
    def get_metadata(self) -> ToolMetadata:
        """获取元数据"""
        return ToolMetadata(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            permissions=self.permissions,
            version=self._metadata.get("version", "1.0.0"),
            author=self._metadata.get("author"),
            created_at=self._created_at,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "permissions": self.permissions,
        }
    
    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"


class ToolRegistry:
    """
    工具注册表
    
    管理所有注册的工具，提供查找、验证和执行功能。
    
    使用示例:
        registry = ToolRegistry()
        registry.register(my_tool)
        
        # 查找工具
        tool = registry.get("my_tool")
        
        # 执行工具
        result = registry.execute("my_tool", context, params)
    """
    
    def __init__(self):
        """初始化注册表"""
        self._tools: Dict[str, Tool] = {}
        self._lock = Lock()
        self._stats = {
            "total_registrations": 0,
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
        }
    
    def register(self, tool: Tool) -> None:
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        with self._lock:
            if tool.name in self._tools:
                logger.warning(f"工具 {tool.name} 已存在，将被覆盖")
            
            self._tools[tool.name] = tool
            self._stats["total_registrations"] += 1
            logger.info(f"注册工具: {tool.name}")
    
    def unregister(self, name: str) -> None:
        """
        注销工具
        
        Args:
            name: 工具名称
        """
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                logger.info(f"注销工具: {name}")
    
    def get(self, name: str) -> Optional[Tool]:
        """
        获取工具
        
        Args:
            name: 工具名称
        
        Returns:
            工具实例（不存在则返回 None）
        """
        return self._tools.get(name)
    
    def has(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools
    
    def list_all(self) -> List[Tool]:
        """列出所有工具"""
        return list(self._tools.values())
    
    def count(self) -> int:
        """获取工具数量"""
        return len(self._tools)
    
    def clear(self) -> None:
        """清空注册表"""
        with self._lock:
            self._tools.clear()
            logger.info("清空工具注册表")
    
    def check_permission(self, name: str, permission: str) -> bool:
        """
        检查工具权限
        
        Args:
            name: 工具名称
            permission: 待检查权限
        
        Returns:
            是否有权限
        """
        tool = self._tools.get(name)
        if not tool:
            return False
        
        # 无权限限制的工具允许所有访问
        if not tool.permissions:
            return True
        
        return permission in tool.permissions
    
    def check_permissions(self, name: str, permissions: List[str]) -> bool:
        """
        检查多个权限（需要全部满足）
        
        Args:
            name: 工具名称
            permissions: 待检查权限列表
        
        Returns:
            是否满足所有权限
        """
        tool = self._tools.get(name)
        if not tool:
            return False
        
        # 无权限限制的工具允许所有访问
        if not tool.permissions:
            return True
        
        return all(p in tool.permissions for p in permissions)
    
    def find_by_permission(self, permission: str) -> List[Tool]:
        """
        按权限查找工具
        
        Args:
            permission: 权限名称
        
        Returns:
            有该权限的工具列表
        """
        tools = []
        for tool in self._tools.values():
            if permission in tool.permissions or not tool.permissions:
                tools.append(tool)
        return tools
    
    def find_by_permissions(self, permissions: List[str]) -> List[Tool]:
        """
        按多权限查找工具（需要全部满足）
        
        Args:
            permissions: 权限列表
        
        Returns:
            满足所有权限的工具列表
        """
        tools = []
        for tool in self._tools.values():
            if not tool.permissions:
                tools.append(tool)
            elif all(p in tool.permissions for p in permissions):
                tools.append(tool)
        return tools
    
    def validate_params(self, name: str, params: Dict[str, Any]) -> List[str]:
        """
        验证工具参数
        
        Args:
            name: 工具名称
            params: 参数
        
        Returns:
            错误列表
        """
        tool = self._tools.get(name)
        if not tool:
            return [f"工具不存在: {name}"]
        
        return tool.validate_params(params)
    
    def execute(
        self,
        name: str,
        context: Any,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行工具
        
        Args:
            name: 工具名称
            context: 执行上下文
            params: 参数
        
        Returns:
            执行结果（包含 success 字段）
        """
        self._stats["total_executions"] += 1
        
        tool = self._tools.get(name)
        if not tool:
            self._stats["failed_executions"] += 1
            return {
                "success": False,
                "error": f"工具不存在: {name}",
            }
        
        # 验证参数
        errors = tool.validate_params(params)
        if errors:
            self._stats["failed_executions"] += 1
            return {
                "success": False,
                "error": f"参数验证失败: {', '.join(errors)}",
            }
        
        try:
            result = tool.execute(context, params)
            self._stats["successful_executions"] += 1
            
            return {
                "success": True,
                "result": result,
            }
            
        except Exception as e:
            self._stats["failed_executions"] += 1
            logger.error(f"执行工具 {name} 失败: {e}")
            
            return {
                "success": False,
                "error": str(e),
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        tools_with_permissions = len([
            t for t in self._tools.values() if t.permissions
        ])
        
        return {
            "total_tools": len(self._tools),
            "tools_with_permissions": tools_with_permissions,
            **self._stats,
        }
    
    def get_permission_stats(self) -> Dict[str, int]:
        """获取权限统计"""
        perm_counts: Dict[str, int] = {}
        
        for tool in self._tools.values():
            for perm in tool.permissions:
                perm_counts[perm] = perm_counts.get(perm, 0) + 1
        
        return perm_counts
    
    def export_tools(self) -> List[Dict[str, Any]]:
        """导出所有工具信息"""
        return [tool.to_dict() for tool in self._tools.values()]
    
    def import_tools(self, tools_data: List[Dict[str, Any]]) -> None:
        """
        导入工具信息（仅元数据，不包含实现）
        
        注意：此方法仅用于元数据导入，实际工具需要通过 register 注册
        """
        for tool_data in tools_data:
            # 创建占位符工具（用于元数据查询）
            placeholder = PlaceholderTool(
                name=tool_data["name"],
                description=tool_data["description"],
                parameters=tool_data.get("parameters", {}),
                permissions=tool_data.get("permissions", []),
            )
            self.register(placeholder)
            logger.warning(f"导入占位符工具: {tool_data['name']}（无实际实现）")


class PlaceholderTool(Tool):
    """
    占位符工具
    
    用于导入元数据时的占位，不提供实际功能。
    """
    
    def execute(self, context: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行（总是失败）"""
        return {
            "error": "此工具为占位符，无实际实现",
        }


# ============================================
# 内置工具示例
# ============================================

class WebSearchTool(Tool):
    """Web 搜索工具示例"""
    
    def __init__(self):
        super().__init__(
            name="web_search",
            description="搜索网络内容",
            parameters={
                "query": {
                    "type": "string",
                    "description": "搜索查询",
                    "required": True,
                },
                "limit": {
                    "type": "integer",
                    "description": "最大结果数",
                    "required": False,
                    "default": 10,
                },
            },
            permissions=["web_access"],
        )
    
    def execute(self, context: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行搜索（示例实现）"""
        # 实际实现需要调用搜索 API
        query = params.get("query", "")
        limit = params.get("limit", 10)
        
        logger.info(f"Web 搜索: query={query}, limit={limit}")
        
        # 返回示例结果
        return {
            "results": [
                {"title": f"Result {i}", "url": f"https://example.com/{i}"}
                for i in range(min(limit, 5))
            ],
            "query": query,
        }


class KnowledgeQueryTool(Tool):
    """知识库查询工具示例"""
    
    def __init__(self):
        super().__init__(
            name="knowledge_query",
            description="查询知识库",
            parameters={
                "query": {
                    "type": "string",
                    "description": "查询内容",
                    "required": True,
                },
                "knowledge_root": {
                    "type": "string",
                    "description": "知识库根路径",
                    "required": False,
                },
            },
            permissions=["knowledge_read"],
        )
    
    def execute(self, context: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行查询（示例实现）"""
        query = params.get("query", "")
        
        logger.info(f"知识库查询: query={query}")
        
        # 返回示例结果
        return {
            "answers": ["示例答案 1", "示例答案 2"],
            "query": query,
        }


def create_default_registry() -> ToolRegistry:
    """创建默认工具注册表"""
    registry = ToolRegistry()
    
    # 注册内置工具
    registry.register(WebSearchTool())
    registry.register(KnowledgeQueryTool())
    
    return registry