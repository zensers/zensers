# -*- coding: utf-8 -*-
"""
Schema 注册表
=============

集中管理所有数据库表的 Schema 定义。

职责：
- 集中管理所有表定义
- 验证 Schema 完整性
- 支持版本化迁移

不负责：
- 连接管理（由 ConnectionManager 负责）
- 数据访问（由 Store 负责）

设计原则：
- 单一职责：只管 Schema
- 开闭原则：新增表通过注册，不修改核心代码
"""

__all__ = [
    "SchemaRegistry",
    "TableSchema",
    "ColumnDef",
    "IndexDef",
    "ForeignKeyDef",
]

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
import sqlite3
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class ColumnDef:
    """
    列定义
    
    定义表中的单个列。
    
    用法：
        ColumnDef("id", "TEXT", primary_key=True)
        ColumnDef("name", "TEXT", not_null=True)
        ColumnDef("count", "INTEGER", default=0)
    """
    name: str                           # 列名
    type: str                           # 数据类型：TEXT, INTEGER, REAL, BLOB
    primary_key: bool = False           # 是否主键
    not_null: bool = False              # 是否非空
    unique: bool = False                # 是否唯一
    default: Optional[Any] = None       # 默认值
    check: Optional[str] = None         # CHECK 约束
    references: Optional[str] = None    # 外键引用（如 "other_table(id)"）
    
    def to_sql(self) -> str:
        """转换为 SQL 片段"""
        parts = [self.name, self.type]
        
        if self.primary_key:
            parts.append("PRIMARY KEY")
        if self.not_null:
            parts.append("NOT NULL")
        if self.unique:
            parts.append("UNIQUE")
        if self.default is not None:
            parts.append(f"DEFAULT {self._format_default()}")
        if self.check:
            parts.append(f"CHECK({self.check})")
        if self.references:
            parts.append(f"REFERENCES {self.references}")
        
        return " ".join(parts)
    
    def _format_default(self) -> str:
        """格式化默认值（安全处理特殊字符）"""
        if self.default is None:
            return "NULL"
        if isinstance(self.default, str):
            # 特殊处理 SQL 函数
            if self.default.upper() in ("CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME"):
                return self.default
            # 转义单引号，防止 SQL 注入
            escaped = self.default.replace("'", "''")
            return f"'{escaped}'"
        if isinstance(self.default, bool):
            return "1" if self.default else "0"
        return str(self.default)


@dataclass
class IndexDef:
    """
    索引定义
    
    定义表上的索引。
    
    用法：
        IndexDef("idx_name", "users", ["name"])
        IndexDef("idx_unique_email", "users", ["email"], unique=True)
    """
    name: str                   # 索引名称
    table: str                  # 表名
    columns: List[str]          # 列名列表
    unique: bool = False        # 是否唯一索引
    where: Optional[str] = None # 部分索引条件
    
    def to_sql(self) -> str:
        """转换为 CREATE INDEX SQL"""
        unique_str = "UNIQUE " if self.unique else ""
        cols = ", ".join(self.columns)
        sql = f"CREATE {unique_str}INDEX IF NOT EXISTS {self.name} ON {self.table} ({cols})"
        if self.where:
            sql += f" WHERE {self.where}"
        return sql


@dataclass
class ForeignKeyDef:
    """
    外键定义
    
    定义表间关系。
    """
    columns: List[str]          # 本表列
    ref_table: str              # 引用表
    ref_columns: List[str]      # 引用列
    on_delete: str = "NO ACTION"  # 删除行为
    on_update: str = "NO ACTION"  # 更新行为
    
    def to_sql(self) -> str:
        """转换为 SQL 片段"""
        cols = ", ".join(self.columns)
        ref_cols = ", ".join(self.ref_columns)
        return (
            f"FOREIGN KEY ({cols}) REFERENCES {self.ref_table} ({ref_cols}) "
            f"ON DELETE {self.on_delete} ON UPDATE {self.on_update}"
        )


@dataclass
class TableSchema:
    """
    表 Schema 定义
    
    定义完整的表结构。
    
    用法：
        USERS_SCHEMA = TableSchema(
            table_name="users",
            columns=[
                ColumnDef("id", "TEXT", primary_key=True),
                ColumnDef("name", "TEXT", not_null=True),
                ColumnDef("email", "TEXT", unique=True),
            ],
            indexes=[
                IndexDef("idx_users_name", "users", ["name"]),
            ],
        )
        
        # 注册
        SchemaRegistry.register(USERS_SCHEMA)
        
        # 创建表
        USERS_SCHEMA.create(conn)
    """
    table_name: str
    columns: List[ColumnDef]
    indexes: List[IndexDef] = field(default_factory=list)
    foreign_keys: List[ForeignKeyDef] = field(default_factory=list)
    version: int = 1
    description: str = ""
    
    def create(self, conn: sqlite3.Connection) -> None:
        """
        创建表
        
        Args:
            conn: SQLite 连接
        """
        # 验证表名防止 SQL 注入
        if not self._validate_table_name(self.table_name):
            raise ValidationError(f"Invalid table name: {self.table_name}")
        
        # 构建 CREATE TABLE SQL
        column_sqls = [col.to_sql() for col in self.columns]
        
        # 添加外键约束
        for fk in self.foreign_keys:
            column_sqls.append(fk.to_sql())
        
        columns_sql = ", ".join(column_sqls)
        
        sql = f"CREATE TABLE IF NOT EXISTS {self.table_name} ({columns_sql})"
        
        conn.execute(sql)
        
        # 创建索引
        for index in self.indexes:
            conn.execute(index.to_sql())
        
        logger.debug(f"Table created: {self.table_name}")
    
    def drop(self, conn: sqlite3.Connection) -> None:
        """
        删除表
        
        Args:
            conn: SQLite 连接
        """
        # 验证表名防止 SQL 注入
        if not self._validate_table_name(self.table_name):
            raise ValidationError(f"Invalid table name: {self.table_name}")
        conn.execute(f"DROP TABLE IF EXISTS {self.table_name}")
        logger.debug(f"Table dropped: {self.table_name}")
    
    @staticmethod
    def _validate_table_name(name: str) -> bool:
        """
        验证表名是否安全
        
        表名只允许字母、数字、下划线，且以字母或下划线开头
        """
        import re
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name))
    
    def exists(self, conn: sqlite3.Connection) -> bool:
        """
        检查表是否存在
        
        Args:
            conn: SQLite 连接
            
        Returns:
            是否存在
        """
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (self.table_name,)
        )
        return cursor.fetchone() is not None
    
    def get_column_names(self) -> List[str]:
        """获取所有列名"""
        return [col.name for col in self.columns]
    
    def get_primary_key(self) -> Optional[str]:
        """获取主键列名"""
        for col in self.columns:
            if col.primary_key:
                return col.name
        return None
    
    def validate_row(self, row: Dict[str, Any]) -> List[str]:
        """
        验证行数据
        
        Args:
            row: 行数据字典
            
        Returns:
            错误消息列表
        """
        errors = []
        
        for col in self.columns:
            # 检查非空约束
            if col.not_null and col.name not in row:
                errors.append(f"Column '{col.name}' is required")
            
            # 检查主键
            if col.primary_key and col.name not in row:
                errors.append(f"Primary key '{col.name}' is required")
        
        return errors


class SchemaRegistry:
    """
    Schema 注册表
    
    集中管理所有表的 Schema 定义。
    
    线程安全：
        所有操作都通过锁保护，支持多线程并发访问。
    
    用法：
        # 注册 Schema
        SchemaRegistry.register(ENTITIES_SCHEMA)
        SchemaRegistry.register(RELATIONS_SCHEMA)
        
        # 获取 Schema
        schema = SchemaRegistry.get("entities")
        
        # 创建所有表
        SchemaRegistry.create_all(conn)
        
        # 验证
        errors = SchemaRegistry.validate(conn)
    """
    
    _schemas: Dict[str, TableSchema] = {}
    _initialized: bool = False
    _lock = threading.RLock()  # 线程安全锁
    
    @classmethod
    def register(cls, schema: TableSchema) -> None:
        """
        注册表 Schema
        
        Args:
            schema: 表 Schema 定义
        """
        with cls._lock:
            cls._schemas[schema.table_name] = schema
        logger.debug(f"Schema registered: {schema.table_name}")
    
    @classmethod
    def unregister(cls, table_name: str) -> bool:
        """
        注销表 Schema
        
        Args:
            table_name: 表名
            
        Returns:
            是否成功注销
        """
        with cls._lock:
            if table_name in cls._schemas:
                del cls._schemas[table_name]
                logger.debug(f"Schema unregistered: {table_name}")
                return True
        return False
    
    @classmethod
    def get(cls, table_name: str) -> Optional[TableSchema]:
        """
        获取表 Schema
        
        Args:
            table_name: 表名
            
        Returns:
            表 Schema，不存在则返回 None
        """
        with cls._lock:
            return cls._schemas.get(table_name)
    
    @classmethod
    def get_all(cls) -> Dict[str, TableSchema]:
        """获取所有 Schema"""
        with cls._lock:
            return cls._schemas.copy()
    
    @classmethod
    def get_table_names(cls) -> List[str]:
        """获取所有表名"""
        with cls._lock:
            return list(cls._schemas.keys())
    
    @classmethod
    def create_all(cls, conn: sqlite3.Connection) -> None:
        """
        创建所有表
        
        Args:
            conn: SQLite 连接
        """
        with cls._lock:
            schemas = list(cls._schemas.values())
        for schema in schemas:
            schema.create(conn)
        conn.commit()
        logger.info(f"All tables created: {len(schemas)} tables")
    
    @classmethod
    def create_tables(
        cls,
        conn: sqlite3.Connection,
        table_names: List[str],
    ) -> None:
        """
        创建指定表
        
        Args:
            conn: SQLite 连接
            table_names: 表名列表
        """
        with cls._lock:
            schemas = [(name, cls._schemas.get(name)) for name in table_names]
        for name, schema in schemas:
            if schema:
                schema.create(conn)
        conn.commit()
    
    @classmethod
    def drop_all(cls, conn: sqlite3.Connection) -> None:
        """
        删除所有表
        
        Args:
            conn: SQLite 连接
        """
        with cls._lock:
            schemas = list(cls._schemas.values())
        for schema in schemas:
            schema.drop(conn)
        conn.commit()
        logger.info(f"All tables dropped: {len(schemas)} tables")
    
    @classmethod
    def validate(cls, conn: sqlite3.Connection) -> List[str]:
        """
        验证 Schema 完整性
        
        检查所有注册的表是否存在于数据库中。
        
        Args:
            conn: SQLite 连接
            
        Returns:
            错误消息列表
        """
        with cls._lock:
            schemas = dict(cls._schemas)
        errors = []
        for name, schema in schemas.items():
            if not schema.exists(conn):
                errors.append(f"Table missing: {name}")
        return errors
    
    @classmethod
    def is_valid(cls, conn: sqlite3.Connection) -> bool:
        """
        检查 Schema 是否完整
        
        Args:
            conn: SQLite 连接
            
        Returns:
            是否所有表都存在
        """
        return len(cls.validate(conn)) == 0
    
    @classmethod
    def clear(cls) -> None:
        """清空所有注册的 Schema"""
        with cls._lock:
            cls._schemas.clear()
            cls._initialized = False
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """获取统计信息"""
        with cls._lock:
            schemas = dict(cls._schemas)
        return {
            "table_count": len(schemas),
            "tables": [
                {
                    "name": schema.table_name,
                    "columns": len(schema.columns),
                    "indexes": len(schema.indexes),
                    "version": schema.version,
                }
                for schema in schemas.values()
            ],
        }
