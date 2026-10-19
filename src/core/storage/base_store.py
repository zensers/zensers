# -*- coding: utf-8 -*-
"""
统一存储接口
============

Phase 10 选择性统一：为所有 Store 提供统一的 API 契约。

设计原则：
1. 接口统一，实现可异
2. 保留各存储介质的优点（JSON 可读性、SQLite 查询能力、内存性能）
3. 最小化改动，渐进式迁移

使用方式：
- SQLite Store: 继承 SQLiteStore 基类
- JSON Store: 实现 BaseStore 接口（保留原有实现）
- 内存 Store: 实现 BaseStore 接口（保留原有实现）
"""

__all__ = [
    # 接口
    "BaseStore",
    "ReadOnlyStore",
    "WritableStore",
    "QueryableStore",
    
    # 基类
    "SQLiteStore",
    
    # 异常
    "StoreError",
    "NotFoundError",
    "DuplicateError",
    "ValidationError",
    "ConnectionError",
    
    # 类型
    "StoreCapabilities",
    "StoreInfo",
]

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Flag, auto
from pathlib import Path
from typing import Any, Dict, Generic, Iterator, List, Optional, TypeVar, Union, TYPE_CHECKING
import sqlite3
import logging

if TYPE_CHECKING:
    from .connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

# 泛型类型
T = TypeVar('T')
ID = TypeVar('ID', str, int)


# ==================== 异常定义 ====================

class StoreError(Exception):
    """
    存储异常基类
    
    所有存储相关异常应继承此类。
    """
    
    def __init__(self, message: str, store_name: Optional[str] = None, 
                 item_id: Optional[str] = None):
        super().__init__(message)
        self.store_name = store_name
        self.item_id = item_id


class NotFoundError(StoreError):
    """项目不存在异常"""
    
    def __init__(self, item_id: str, store_name: Optional[str] = None):
        super().__init__(
            f"Item not found: {item_id}",
            store_name=store_name,
            item_id=item_id
        )


class DuplicateError(StoreError):
    """项目重复异常"""
    
    def __init__(self, item_id: str, store_name: Optional[str] = None):
        super().__init__(
            f"Item already exists: {item_id}",
            store_name=store_name,
            item_id=item_id
        )


class ValidationError(StoreError):
    """数据验证异常"""
    
    def __init__(self, message: str, field: Optional[str] = None,
                 store_name: Optional[str] = None):
        super().__init__(message, store_name=store_name)
        self.field = field


class ConnectionError(StoreError):
    """连接异常"""
    
    def __init__(self, message: str, store_name: Optional[str] = None):
        super().__init__(message, store_name=store_name)


# ==================== 能力标志 ====================

class StoreCapabilities(Flag):
    """
    存储能力标志
    
    用于描述 Store 支持的操作。
    """
    READ = auto()
    WRITE = auto()
    DELETE = auto()
    QUERY = auto()
    BATCH = auto()
    TRANSACTION = auto()
    INDEX = auto()
    
    # 常用组合
    READ_ONLY = READ
    READ_WRITE = READ | WRITE | DELETE
    FULL = READ | WRITE | DELETE | QUERY | BATCH | TRANSACTION | INDEX


# ==================== Store 信息 ====================

@dataclass
class StoreInfo:
    """存储信息"""
    name: str
    backend: str  # sqlite / json / memory / redis / etc.
    capabilities: StoreCapabilities
    item_type: str
    location: str  # 文件路径或连接信息
    size: int = 0  # 项目数量
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ==================== 基础接口 ====================

class ReadOnlyStore(ABC, Generic[T]):
    """
    只读存储接口
    
    提供基本的读取操作。
    """
    
    @abstractmethod
    def get(self, id: str) -> Optional[T]:
        """
        获取单个项目
        
        Args:
            id: 项目 ID
            
        Returns:
            项目对象，不存在返回 None
        """
        pass
    
    @abstractmethod
    def exists(self, id: str) -> bool:
        """
        检查项目是否存在
        
        Args:
            id: 项目 ID
            
        Returns:
            是否存在
        """
        pass
    
    @abstractmethod
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        计数
        
        Args:
            filters: 过滤条件
            
        Returns:
            项目数量
        """
        pass


class WritableStore(ABC, Generic[T]):
    """
    可写存储接口
    
    提供写入、更新、删除操作。
    """
    
    @abstractmethod
    def add(self, item: T) -> str:
        """
        添加项目
        
        Args:
            item: 项目对象
            
        Returns:
            新项目的 ID
            
        Raises:
            DuplicateError: 项目已存在
            ValidationError: 数据验证失败
        """
        pass
    
    @abstractmethod
    def update(self, id: str, data: Dict[str, Any]) -> bool:
        """
        更新项目
        
        Args:
            id: 项目 ID
            data: 更新数据（部分更新）
            
        Returns:
            是否更新成功
            
        Raises:
            NotFoundError: 项目不存在
        """
        pass
    
    @abstractmethod
    def delete(self, id: str) -> bool:
        """
        删除项目
        
        Args:
            id: 项目 ID
            
        Returns:
            是否删除成功
        """
        pass


class QueryableStore(ABC, Generic[T]):
    """
    可查询存储接口
    
    提供列表查询和过滤功能。
    """
    
    @abstractmethod
    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        ascending: bool = True,
    ) -> List[T]:
        """
        列表查询
        
        Args:
            filters: 过滤条件
            limit: 返回数量限制
            offset: 偏移量
            order_by: 排序字段
            ascending: 是否升序
            
        Returns:
            项目列表
        """
        pass
    
    @abstractmethod
    def find(
        self,
        field: str,
        value: Any,
        limit: int = 100,
    ) -> List[T]:
        """
        按字段查找
        
        Args:
            field: 字段名
            value: 字段值
            limit: 返回数量限制
            
        Returns:
            匹配的项目列表
        """
        pass
    
    def iterate(
        self,
        filters: Optional[Dict[str, Any]] = None,
        batch_size: int = 100,
    ) -> Iterator[T]:
        """
        迭代所有项目
        
        Args:
            filters: 过滤条件
            batch_size: 每批数量
            
        Yields:
            项目对象
        """
        offset = 0
        while True:
            items = self.list(filters=filters, limit=batch_size, offset=offset)
            if not items:
                break
            for item in items:
                yield item
            offset += batch_size


class BaseStore(ReadOnlyStore[T], WritableStore[T], QueryableStore[T]):
    """
    统一存储接口
    
    所有存储组件应实现此接口。提供完整的 CRUD + 查询能力。
    
    设计说明：
    - 接口统一：所有 Store 共享相同的 API
    - 实现可异：不同存储介质可以有不同的实现
    - 渐进迁移：现有 Store 可以逐步适配
    
    使用示例：
    ```python
    class MyStore(BaseStore[MyItem]):
        def get(self, id: str) -> Optional[MyItem]:
            # 实现获取逻辑
            pass
        
        def add(self, item: MyItem) -> str:
            # 实现添加逻辑
            pass
        
        # ... 其他方法实现
    ```
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """存储名称"""
        pass
    
    @property
    @abstractmethod
    def backend(self) -> str:
        """存储后端类型"""
        pass
    
    @property
    def capabilities(self) -> StoreCapabilities:
        """存储能力"""
        return StoreCapabilities.FULL
    
    def get_info(self) -> StoreInfo:
        """
        获取存储信息
        
        Returns:
            存储信息对象
        """
        return StoreInfo(
            name=self.name,
            backend=self.backend,
            capabilities=self.capabilities,
            item_type=self.__orig_class__.__args__[0].__name__ 
                      if hasattr(self, '__orig_class__') else 'Unknown',
            location=getattr(self, '_location', 'unknown'),
            size=self.count(),
        )
    
    # === 批量操作（默认实现） ===
    
    def batch_add(self, items: List[T]) -> List[str]:
        """
        批量添加
        
        Args:
            items: 项目列表
            
        Returns:
            新项目 ID 列表
        """
        return [self.add(item) for item in items]
    
    def batch_update(self, updates: Dict[str, Dict[str, Any]]) -> int:
        """
        批量更新
        
        Args:
            updates: {id: data} 映射
            
        Returns:
            成功更新数量
        """
        count = 0
        for id, data in updates.items():
            if self.update(id, data):
                count += 1
        return count
    
    def batch_delete(self, ids: List[str]) -> int:
        """
        批量删除
        
        Args:
            ids: 项目 ID 列表
            
        Returns:
            成功删除数量
        """
        count = 0
        for id in ids:
            if self.delete(id):
                count += 1
        return count
    
    # === 生命周期 ===
    
    def initialize(self) -> None:
        """
        初始化存储
        
        子类可重写以执行初始化逻辑（如创建表）。
        """
        pass
    
    def close(self) -> None:
        """
        关闭存储
        
        子类可重写以执行清理逻辑（如关闭连接）。
        """
        pass
    
    def clear(self) -> int:
        """
        清空存储
        
        Returns:
            删除的项目数量
        """
        all_ids = [self._get_id(item) for item in self.list(limit=10**6)]
        return self.batch_delete(all_ids)
    
    def _get_id(self, item: T) -> str:
        """
        从项目获取 ID
        
        子类应重写此方法。
        """
        if hasattr(item, 'id'):
            return item.id
        if hasattr(item, f'{self.name[:-5]}_id'):  # e.g., entity_id for EntityStore
            return getattr(item, f'{self.name[:-5]}_id')
        raise NotImplementedError("Subclass must implement _get_id")


# ==================== SQLite 基类 ====================

class SQLiteStore(BaseStore[T]):
    """
    SQLite 存储基类
    
    提供基于 SQLite 的通用存储实现。
    
    支持三种连接模式：
    1. ConnectionManager 注入（推荐）：Store 从 ConnectionManager 获取连接
    2. 外部连接注入：Store 接收外部管理的连接
    3. 自管理连接：Store 自己创建和管理连接（遗留模式，不推荐）
    
    子类必须实现：
    - _create_table(): 创建表
    - _row_to_item(): 行转对象
    - _item_to_dict(): 对象转字典
    - _get_id(): 获取项目 ID
    
    用法：
    ```python
    from src.core.storage.connection_manager import ConnectionManager
    from src.core.storage.schema_registry import SchemaRegistry, TableSchema, ColumnDef
    
    # 定义 Schema
    ENTITIES_SCHEMA = TableSchema(
        table_name="entities",
        columns=[
            ColumnDef("id", "TEXT", primary_key=True),
            ColumnDef("name", "TEXT", not_null=True),
        ],
    )
    SchemaRegistry.register(ENTITIES_SCHEMA)
    
    # 实现 Store
    class EntityStore(SQLiteStore[Entity]):
        def __init__(self, connection_manager: ConnectionManager):
            super().__init__(
                connection_manager=connection_manager,
                connection_name="knowledge_bank",
                table_name="entities",
            )
        
        def _create_table(self) -> None:
            schema = SchemaRegistry.get("entities")
            if schema:
                schema.create(self.db)
        
        def _row_to_item(self, row: sqlite3.Row) -> Entity:
            ...
        
        def _item_to_dict(self, item: Entity) -> Dict[str, Any]:
            ...
        
        def _get_id(self, item: Entity) -> str:
            return item.id
    ```
    """
    
    def __init__(
        self,
        db_path: Union[str, Path, None] = None,
        table_name: str = "",
        auto_init: bool = True,
        *,
        connection_manager: Optional['ConnectionManager'] = None,
        connection_name: Optional[str] = None,
        external_db: Optional[sqlite3.Connection] = None,
        db: Optional[sqlite3.Connection] = None,  # external_db 别名，向后兼容
        shared_connection: bool = True,
    ):
        """
        初始化 SQLite 存储
        
        Args:
            db_path: 数据库文件路径（自管理连接模式，不推荐）
            table_name: 表名
            auto_init: 是否自动初始化（创建表）
            connection_manager: 连接管理器（推荐）
            connection_name: 连接名称（配合 ConnectionManager 使用）
            external_db: 外部连接（兼容模式）
            db: external_db 别名（向后兼容）
            shared_connection: 是否使用共享连接
            
        Raises:
            ValidationError: 表名格式无效
            ValueError: 未提供任何连接方式
        """
        # 验证表名格式（防止 SQL 注入）
        if not self._validate_table_name(table_name):
            raise ValidationError(
                f"Invalid table name: {table_name}. Only alphanumeric and underscore allowed.",
                store_name=f"{table_name}_store"
            )
        
        self._table_name = table_name
        self._auto_init = auto_init
        self._initialized = False
        
        # 兼容处理：db 作为 external_db 的别名
        effective_external_db = external_db or db
        
        # 确定连接模式
        if connection_manager is not None:
            # 模式 1：ConnectionManager 注入（推荐）
            self._connection_manager = connection_manager
            self._connection_name = connection_name or table_name
            self._db = connection_manager.get_connection(
                self._connection_name, 
                shared=shared_connection
            )
            self._owns_connection = False
            self._connection_mode = "manager"
            
        elif effective_external_db is not None:
            # 模式 2：外部连接注入（兼容模式）
            self._connection_manager = None
            self._connection_name = None
            self._db = effective_external_db
            self._owns_connection = False
            self._connection_mode = "external"
            
        elif db_path is not None:
            # 模式 3：自管理连接（遗留模式）
            self._db_path = Path(db_path)
            self._connection_manager = None
            self._connection_name = None
            self._db: Optional[sqlite3.Connection] = None
            self._owns_connection = True
            self._connection_mode = "self"
            
        else:
            raise ValueError(
                "Must provide one of: connection_manager, external_db (or db), or db_path"
            )
        
        # 自动初始化
        if auto_init:
            self._ensure_initialized()
    
    @staticmethod
    def _validate_table_name(name: str) -> bool:
        """
        验证表名是否安全
        
        Args:
            name: 表名
            
        Returns:
            是否有效
        """
        if not name:
            return False
        import re
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name))
    
    @property
    def name(self) -> str:
        return f"{self._table_name}_store"
    
    @property
    def backend(self) -> str:
        return "sqlite"
    
    @property
    def db(self) -> sqlite3.Connection:
        """获取数据库连接（自动健康检查）"""
        if self._db is None and self._connection_mode == "self":
            self._init_db()
        if self._db is None:
            raise ConnectionError("Database connection not initialized")
        # ConnectionManager 模式下进行健康检查
        if self._connection_mode == "manager" and self._connection_manager is not None:
            if not self._connection_manager._is_connection_healthy(self._db):
                # 重新获取连接
                self._db = self._connection_manager.get_connection(
                    self._connection_name, shared=True
                )
        return self._db
    
    def _ensure_initialized(self) -> None:
        """确保已初始化（创建表）"""
        if self._initialized:
            return
        
        if self._connection_mode == "self" and self._db is None:
            self._init_db()
        else:
            # ConnectionManager 或外部连接模式，只需创建表
            self._create_table()
        
        self._initialized = True
    
    def _init_db(self) -> None:
        """初始化数据库连接（仅自管理模式）"""
        if self._connection_mode != "self":
            return
        
        if not hasattr(self, '_db_path'):
            raise ConnectionError("db_path not set for self-managed connection")
        
        # 确保目录存在
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 创建连接
        self._db = sqlite3.connect(str(self._db_path))
        self._db.row_factory = sqlite3.Row
        
        # 启用外键约束
        self._db.execute("PRAGMA foreign_keys = ON")
        
        # 创建表
        self._create_table()
        
        logger.info(f"SQLiteStore initialized: {self._db_path} / {self._table_name}")
    
    @abstractmethod
    def _create_table(self) -> None:
        """
        创建表
        
        子类必须实现此方法。
        """
        pass
    
    @abstractmethod
    def _row_to_item(self, row: sqlite3.Row) -> T:
        """
        行转对象
        
        Args:
            row: SQLite 行对象
            
        Returns:
            项目对象
        """
        pass
    
    @abstractmethod
    def _item_to_dict(self, item: T) -> Dict[str, Any]:
        """
        对象转字典
        
        Args:
            item: 项目对象
            
        Returns:
            字典（用于 INSERT/UPDATE）
        """
        pass
    
    def _get_id_column(self) -> str:
        """
        获取 ID 列名
        
        子类可以覆盖此方法以支持自定义 ID 列名。
        默认返回 'id'。
        
        Returns:
            ID 列名
        """
        return "id"
    
    # === BaseStore 实现 ===
    
    def get(self, id: str) -> Optional[T]:
        """获取单个项目"""
        id_column = self._get_id_column()
        cursor = self.db.execute(
            f"SELECT * FROM {self._table_name} WHERE {id_column} = ?",
            (id,)
        )
        row = cursor.fetchone()
        return self._row_to_item(row) if row else None
    
    def exists(self, id: str) -> bool:
        """检查项目是否存在"""
        id_column = self._get_id_column()
        cursor = self.db.execute(
            f"SELECT 1 FROM {self._table_name} WHERE {id_column} = ? LIMIT 1",
            (id,)
        )
        return cursor.fetchone() is not None
    
    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """计数"""
        if filters:
            where, params = self._build_where(filters)
            cursor = self.db.execute(
                f"SELECT COUNT(*) FROM {self._table_name} WHERE {where}",
                params
            )
        else:
            cursor = self.db.execute(
                f"SELECT COUNT(*) FROM {self._table_name}"
            )
        return cursor.fetchone()[0]
    
    def add(self, item: T) -> str:
        """添加项目"""
        data = self._item_to_dict(item)
        id = self._get_id(item)
        
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        
        try:
            self.db.execute(
                f"INSERT INTO {self._table_name} ({columns}) VALUES ({placeholders})",
                tuple(data.values())
            )
            self.db.commit()
            return id
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint" in str(e):
                raise DuplicateError(id, self.name)
            # 不暴露原始错误消息，防止信息泄露
            raise ValidationError("Data integrity violation", store_name=self.name)
    
    def update(self, id: str, data: Dict[str, Any]) -> bool:
        """更新项目"""
        if not self.exists(id):
            raise NotFoundError(id, self.name)
        
        id_column = self._get_id_column()
        set_clause = ", ".join(f"{k} = ?" for k in data.keys())
        values = list(data.values()) + [id]
        
        self.db.execute(
            f"UPDATE {self._table_name} SET {set_clause} WHERE {id_column} = ?",
            tuple(values)
        )
        self.db.commit()
        return True
    
    def delete(self, id: str) -> bool:
        """删除项目"""
        id_column = self._get_id_column()
        cursor = self.db.execute(
            f"DELETE FROM {self._table_name} WHERE {id_column} = ?",
            (id,)
        )
        self.db.commit()
        return cursor.rowcount > 0
    
    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        ascending: bool = True,
    ) -> List[T]:
        """列表查询"""
        sql = f"SELECT * FROM {self._table_name}"
        params = []
        
        if filters:
            where, params = self._build_where(filters)
            sql += f" WHERE {where}"
        
        if order_by:
            # 安全验证：检查 order_by 列名
            if not self._validate_column_name(order_by):
                raise ValidationError(
                    "Invalid column specification",
                    store_name=self.name
                )
            
            # 白名单验证（如果子类提供了白名单）
            allowed_columns = self._get_allowed_columns()
            if allowed_columns and order_by not in allowed_columns:
                raise ValidationError(
                    "Column not allowed for ordering",
                    store_name=self.name
                )
            
            direction = "ASC" if ascending else "DESC"
            sql += f" ORDER BY {order_by} {direction}"
        
        sql += f" LIMIT {limit} OFFSET {offset}"
        
        cursor = self.db.execute(sql, tuple(params))
        return [self._row_to_item(row) for row in cursor.fetchall()]
    
    def find(self, field: str, value: Any, limit: int = 100) -> List[T]:
        """按字段查找"""
        return self.list(filters={field: value}, limit=limit)
    
    def iterate(
        self,
        filters: Optional[Dict[str, Any]] = None,
        batch_size: int = 100,
    ) -> Iterator[T]:
        """
        迭代所有项目（使用 keyset 分页，性能更优）
        
        相比 offset 分页，keyset 分页在大数据量时性能更好：
        - offset 分页：O(n) 每次都要跳过前 n 条记录
        - keyset 分页：O(1) 直接从上次位置继续
        
        Args:
            filters: 过滤条件
            batch_size: 每批数量
            
        Yields:
            项目对象
        """
        id_column = self._get_id_column()
        last_id = None
        
        while True:
            # 构建查询
            sql = f"SELECT * FROM {self._table_name}"
            params: List[Any] = []
            
            if filters:
                where, params = self._build_where(filters)
                sql += f" WHERE {where}"
                if last_id:
                    sql += f" AND {id_column} > ?"
                    params.append(last_id)
            elif last_id:
                sql += f" WHERE {id_column} > ?"
                params.append(last_id)
            
            sql += f" ORDER BY {id_column} ASC LIMIT ?"
            params.append(batch_size)
            
            cursor = self.db.execute(sql, tuple(params))
            rows = cursor.fetchall()
            
            if not rows:
                break
            
            for row in rows:
                item = self._row_to_item(row)
                yield item
                last_id = self._get_id(item)
    
    def close(self) -> None:
        """关闭连接"""
        if self._db:
            self._db.close()
            self._db = None
    
    # === 辅助方法 ===
    
    def _validate_column_name(self, name: str) -> bool:
        """
        验证列名是否安全
        
        防止 SQL 注入：只允许字母、数字、下划线
        
        Args:
            name: 列名
            
        Returns:
            是否有效
        """
        if not name:
            return False
        # 只允许字母、数字、下划线
        import re
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name))
    
    def _get_allowed_columns(self) -> List[str]:
        """
        获取允许的列名列表
        
        子类可重写此方法提供具体的列名白名单。
        默认返回空列表，表示不做白名单检查（仅做格式验证）。
        
        Returns:
            允许的列名列表
        """
        return []
    
    def _build_where(self, filters: Dict[str, Any]) -> tuple[str, List[Any]]:
        """
        构建 WHERE 子句
        
        Args:
            filters: 过滤条件
            
        Returns:
            (where_clause, params)
            
        Raises:
            ValidationError: 列名无效或不在白名单中
        """
        conditions = []
        params = []
        allowed_columns = self._get_allowed_columns()
        
        for key, value in filters.items():
            # 安全验证：检查列名格式
            if not self._validate_column_name(key):
                raise ValidationError(
                    "Invalid column specification",
                    store_name=self.name
                )
            
            # 白名单验证（如果子类提供了白名单）
            if allowed_columns and key not in allowed_columns:
                raise ValidationError(
                    "Column not allowed in filter",
                    store_name=self.name
                )
            
            if value is None:
                conditions.append(f"{key} IS NULL")
            elif isinstance(value, (list, tuple)):
                if len(value) == 0:
                    raise ValidationError(
                        f"Empty list not allowed in filter for column '{key}'",
                        store_name=self.name
                    )
                placeholders = ", ".join("?" * len(value))
                conditions.append(f"{key} IN ({placeholders})")
                params.extend(value)
            else:
                conditions.append(f"{key} = ?")
                params.append(value)
        
        return " AND ".join(conditions), params
    
    # === 事务支持 ===
    
    def begin_transaction(self) -> None:
        """开始事务"""
        self.db.execute("BEGIN TRANSACTION")
    
    def commit(self) -> None:
        """提交事务"""
        self.db.commit()
    
    def rollback(self) -> None:
        """回滚事务"""
        self.db.rollback()
    
    def __enter__(self) -> "SQLiteStore[T]":
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
