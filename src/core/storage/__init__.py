# -*- coding: utf-8 -*-
"""
存储模块
========

提供各种数据的持久化存储功能。

Phase 10 新增：
- BaseStore: 统一存储接口
- SQLiteStore: SQLite 存储基类
- ConnectionManager: 连接管理器
- SchemaRegistry: Schema 注册表
- schemas: 集中定义所有表 Schema
- 通用异常类型

遗留模块（从 storage_legacy.py 导入）：
- TaskStorage: 任务存储管理器
- WriteAheadLog: 预写日志
"""

# Phase 10 统一存储接口
from .base_store import (
    # 接口
    BaseStore,
    ReadOnlyStore,
    WritableStore,
    QueryableStore,
    
    # 基类
    SQLiteStore,
    
    # 异常
    StoreError,
    NotFoundError,
    DuplicateError,
    ValidationError,
    ConnectionError,
    
    # 类型
    StoreCapabilities,
    StoreInfo,
)

# Phase 10 基础设施
from .connection_manager import (
    ConnectionManager,
    ConnectionConfig,
)

from .schema_registry import (
    SchemaRegistry,
    TableSchema,
    ColumnDef,
    IndexDef,
    ForeignKeyDef,
)

# 现有存储实现
from .research_result_store import (
    ResearchResultStore,
    ResearchStatus,
    ResearchResultMeta,
    ResearchResultError,
    ResearchResultNotFoundError,
    InvalidTaskIdError
)

from .document_version_manager import (
    DocumentVersionManager,
    VersionInfo,
    VersionError
)

from .export_manager import (
    ExportManager,
    ExportRecord,
    ExportResult,
    ExportError
)

# 遗留模块：延迟导入避免循环依赖
def __getattr__(name: str):
    """延迟导入 TaskStorage 和 WriteAheadLog"""
    if name in ("TaskStorage", "WriteAheadLog", "create_task_storage_from_settings", "get_storage_paths"):
        from src.core.storage_legacy import (
            TaskStorage,
            WriteAheadLog,
            create_task_storage_from_settings,
            get_storage_paths,
        )
        if name == "TaskStorage":
            return TaskStorage
        elif name == "WriteAheadLog":
            return WriteAheadLog
        elif name == "create_task_storage_from_settings":
            return create_task_storage_from_settings
        elif name == "get_storage_paths":
            return get_storage_paths
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Phase 10 统一接口
    "BaseStore",
    "ReadOnlyStore",
    "WritableStore",
    "QueryableStore",
    "SQLiteStore",
    "StoreError",
    "NotFoundError",
    "DuplicateError",
    "ValidationError",
    "ConnectionError",
    "StoreCapabilities",
    "StoreInfo",
    
    # Phase 10 基础设施
    "ConnectionManager",
    "ConnectionConfig",
    "SchemaRegistry",
    "TableSchema",
    "ColumnDef",
    "IndexDef",
    "ForeignKeyDef",
    
    # 现有存储
    "ResearchResultStore",
    "ResearchStatus",
    "ResearchResultMeta",
    "ResearchResultError",
    "ResearchResultNotFoundError",
    "InvalidTaskIdError",
    "DocumentVersionManager",
    "VersionInfo",
    "VersionError",
    "ExportManager",
    "ExportRecord",
    "ExportResult",
    "ExportError",
    
    # 遗留模块（延迟导入）
    "TaskStorage",
    "WriteAheadLog",
    "create_task_storage_from_settings",
    "get_storage_paths",
]