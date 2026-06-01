# -*- coding: utf-8 -*-
"""
SchemaRegistry 单元测试
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from src.core.storage.schema_registry import (
    SchemaRegistry,
    TableSchema,
    ColumnDef,
    IndexDef,
    ForeignKeyDef,
)


class TestColumnDef:
    """ColumnDef 测试"""
    
    def test_simple_column(self):
        """测试简单列"""
        col = ColumnDef("name", "TEXT")
        assert col.to_sql() == "name TEXT"
    
    def test_primary_key(self):
        """测试主键"""
        col = ColumnDef("id", "TEXT", primary_key=True)
        assert "PRIMARY KEY" in col.to_sql()
    
    def test_not_null(self):
        """测试非空约束"""
        col = ColumnDef("name", "TEXT", not_null=True)
        assert "NOT NULL" in col.to_sql()
    
    def test_default_value(self):
        """测试默认值"""
        col = ColumnDef("count", "INTEGER", default=0)
        sql = col.to_sql()
        assert "DEFAULT" in sql
        assert "0" in sql
    
    def test_default_string(self):
        """测试字符串默认值"""
        col = ColumnDef("status", "TEXT", default="pending")
        sql = col.to_sql()
        assert "DEFAULT" in sql
        assert "'pending'" in sql
    
    def test_default_current_timestamp(self):
        """测试 CURRENT_TIMESTAMP 默认值"""
        col = ColumnDef("created_at", "TEXT", default="CURRENT_TIMESTAMP")
        sql = col.to_sql()
        assert "DEFAULT CURRENT_TIMESTAMP" in sql


class TestIndexDef:
    """IndexDef 测试"""
    
    def test_simple_index(self):
        """测试简单索引"""
        idx = IndexDef("idx_name", "users", ["name"])
        sql = idx.to_sql()
        assert "CREATE INDEX IF NOT EXISTS idx_name" in sql
        assert "ON users (name)" in sql
    
    def test_unique_index(self):
        """测试唯一索引"""
        idx = IndexDef("idx_email", "users", ["email"], unique=True)
        sql = idx.to_sql()
        assert "UNIQUE INDEX" in sql
    
    def test_composite_index(self):
        """测试复合索引"""
        idx = IndexDef("idx_comp", "users", ["name", "email"])
        sql = idx.to_sql()
        assert "(name, email)" in sql
    
    def test_partial_index(self):
        """测试部分索引"""
        idx = IndexDef("idx_active", "users", ["name"], where="active = 1")
        sql = idx.to_sql()
        assert "WHERE active = 1" in sql


class TestTableSchema:
    """TableSchema 测试"""
    
    def test_simple_schema(self):
        """测试简单 Schema"""
        schema = TableSchema(
            table_name="users",
            columns=[
                ColumnDef("id", "TEXT", primary_key=True),
                ColumnDef("name", "TEXT", not_null=True),
            ],
        )
        
        assert schema.table_name == "users"
        assert len(schema.columns) == 2
    
    def test_create_table(self):
        """测试创建表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            
            schema = TableSchema(
                table_name="users",
                columns=[
                    ColumnDef("id", "TEXT", primary_key=True),
                    ColumnDef("name", "TEXT", not_null=True),
                ],
            )
            
            schema.create(conn)
            
            # 验证表存在
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            )
            assert cursor.fetchone() is not None
            conn.close()
    
    def test_create_table_with_indexes(self):
        """测试创建带索引的表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            
            schema = TableSchema(
                table_name="users",
                columns=[
                    ColumnDef("id", "TEXT", primary_key=True),
                    ColumnDef("name", "TEXT", not_null=True),
                ],
                indexes=[
                    IndexDef("idx_users_name", "users", ["name"]),
                ],
            )
            
            schema.create(conn)
            
            # 验证索引存在
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_users_name'"
            )
            assert cursor.fetchone() is not None
            conn.close()
    
    def test_exists(self):
        """测试检查表是否存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            
            schema = TableSchema(
                table_name="users",
                columns=[ColumnDef("id", "TEXT", primary_key=True)],
            )
            
            assert not schema.exists(conn)
            schema.create(conn)
            assert schema.exists(conn)
            conn.close()
    
    def test_get_column_names(self):
        """测试获取列名"""
        schema = TableSchema(
            table_name="users",
            columns=[
                ColumnDef("id", "TEXT", primary_key=True),
                ColumnDef("name", "TEXT"),
                ColumnDef("email", "TEXT"),
            ],
        )
        
        names = schema.get_column_names()
        assert names == ["id", "name", "email"]
    
    def test_get_primary_key(self):
        """测试获取主键"""
        schema = TableSchema(
            table_name="users",
            columns=[
                ColumnDef("id", "TEXT", primary_key=True),
                ColumnDef("name", "TEXT"),
            ],
        )
        
        assert schema.get_primary_key() == "id"
    
    def test_validate_row(self):
        """测试行验证"""
        schema = TableSchema(
            table_name="users",
            columns=[
                ColumnDef("id", "TEXT", primary_key=True),
                ColumnDef("name", "TEXT", not_null=True),
            ],
        )
        
        # 缺少必填字段
        errors = schema.validate_row({})
        assert len(errors) == 2
        
        # 完整数据
        errors = schema.validate_row({"id": "1", "name": "Alice"})
        assert len(errors) == 0


class TestSchemaRegistry:
    """SchemaRegistry 测试"""
    
    def setup_method(self):
        """每个测试前清空注册表"""
        SchemaRegistry.clear()
    
    def test_register(self):
        """测试注册 Schema"""
        schema = TableSchema(
            table_name="users",
            columns=[ColumnDef("id", "TEXT", primary_key=True)],
        )
        
        SchemaRegistry.register(schema)
        
        assert SchemaRegistry.get("users") is schema
    
    def test_unregister(self):
        """测试注销 Schema"""
        schema = TableSchema(
            table_name="users",
            columns=[ColumnDef("id", "TEXT", primary_key=True)],
        )
        
        SchemaRegistry.register(schema)
        assert SchemaRegistry.unregister("users") is True
        assert SchemaRegistry.get("users") is None
    
    def test_get_all(self):
        """测试获取所有 Schema"""
        schema1 = TableSchema(
            table_name="users",
            columns=[ColumnDef("id", "TEXT", primary_key=True)],
        )
        schema2 = TableSchema(
            table_name="posts",
            columns=[ColumnDef("id", "TEXT", primary_key=True)],
        )
        
        SchemaRegistry.register(schema1)
        SchemaRegistry.register(schema2)
        
        all_schemas = SchemaRegistry.get_all()
        assert len(all_schemas) == 2
        assert "users" in all_schemas
        assert "posts" in all_schemas
    
    def test_create_all(self):
        """测试创建所有表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            
            schema1 = TableSchema(
                table_name="users",
                columns=[ColumnDef("id", "TEXT", primary_key=True)],
            )
            schema2 = TableSchema(
                table_name="posts",
                columns=[ColumnDef("id", "TEXT", primary_key=True)],
            )
            
            SchemaRegistry.register(schema1)
            SchemaRegistry.register(schema2)
            
            SchemaRegistry.create_all(conn)
            
            # 验证两个表都存在
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cursor.fetchall()]
            assert "users" in tables
            assert "posts" in tables
            conn.close()
    
    def test_validate(self):
        """测试验证 Schema 完整性"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            
            schema = TableSchema(
                table_name="users",
                columns=[ColumnDef("id", "TEXT", primary_key=True)],
            )
            
            SchemaRegistry.register(schema)
            
            # 表不存在时应该有错误
            errors = SchemaRegistry.validate(conn)
            assert len(errors) == 1
            assert "users" in errors[0]
            
            # 创建表后应该无错误
            SchemaRegistry.create_all(conn)
            errors = SchemaRegistry.validate(conn)
            assert len(errors) == 0
            conn.close()
    
    def test_is_valid(self):
        """测试检查 Schema 是否完整"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            
            schema = TableSchema(
                table_name="users",
                columns=[ColumnDef("id", "TEXT", primary_key=True)],
            )
            
            SchemaRegistry.register(schema)
            
            assert not SchemaRegistry.is_valid(conn)
            SchemaRegistry.create_all(conn)
            assert SchemaRegistry.is_valid(conn)
            conn.close()
    
    def test_get_stats(self):
        """测试获取统计信息"""
        schema = TableSchema(
            table_name="users",
            columns=[
                ColumnDef("id", "TEXT", primary_key=True),
                ColumnDef("name", "TEXT"),
            ],
            indexes=[IndexDef("idx_name", "users", ["name"])],
        )
        
        SchemaRegistry.register(schema)
        
        stats = SchemaRegistry.get_stats()
        
        assert stats["table_count"] == 1
        assert len(stats["tables"]) == 1
        assert stats["tables"][0]["columns"] == 2
        assert stats["tables"][0]["indexes"] == 1
