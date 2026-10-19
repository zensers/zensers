# -*- coding: utf-8 -*-
"""
ConnectionManager 单元测试
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from src.core.storage.connection_manager import (
    ConnectionManager,
    ConnectionConfig,
)


class TestConnectionConfig:
    """ConnectionConfig 测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = ConnectionConfig()
        assert config.enable_wal is True
        assert config.enable_foreign_keys is True
        assert config.timeout == 5.0
        assert config.check_same_thread is False
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = ConnectionConfig(
            enable_wal=False,
            timeout=10.0,
        )
        assert config.enable_wal is False
        assert config.timeout == 10.0


class TestConnectionManager:
    """ConnectionManager 测试"""
    
    def test_init(self):
        """测试初始化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConnectionManager(tmpdir, auto_cleanup=False)
            assert manager._base_path == Path(tmpdir)
            assert len(manager._shared_connections) == 0
            manager.close_all()
    
    def test_get_connection_shared(self):
        """测试获取共享连接"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConnectionManager(tmpdir, auto_cleanup=False)
            
            conn1 = manager.get_connection("test_db", shared=True)
            conn2 = manager.get_connection("test_db", shared=True)
            
            # 共享连接应该返回同一个对象
            assert conn1 is conn2
            assert len(manager._shared_connections) == 1
            manager.close_all()
    
    def test_get_connection_independent(self):
        """测试获取独立连接"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConnectionManager(tmpdir, auto_cleanup=False)
            
            conn1 = manager.get_connection("test_db", shared=False)
            conn2 = manager.get_connection("test_db", shared=False)
            
            # 独立连接应该是不同的对象
            assert conn1 is not conn2
            manager.close_all()
    
    def test_connection_has_row_factory(self):
        """测试连接有 row_factory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConnectionManager(tmpdir, auto_cleanup=False)
            conn = manager.get_connection("test_db")
            
            assert conn.row_factory == sqlite3.Row
            manager.close_all()
    
    def test_connection_wal_mode(self):
        """测试 WAL 模式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConnectionManager(tmpdir, auto_cleanup=False)
            conn = manager.get_connection("test_db")
            
            cursor = conn.execute("PRAGMA journal_mode")
            result = cursor.fetchone()[0]
            assert result.upper() == "WAL"
            manager.close_all()
    
    def test_connection_foreign_keys(self):
        """测试外键约束"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConnectionManager(tmpdir, auto_cleanup=False)
            conn = manager.get_connection("test_db")
            
            cursor = conn.execute("PRAGMA foreign_keys")
            result = cursor.fetchone()[0]
            assert result == 1
            manager.close_all()
    
    def test_close_specific_connection(self):
        """测试关闭特定连接"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConnectionManager(tmpdir, auto_cleanup=False)
            manager.get_connection("test_db")
            
            assert len(manager._shared_connections) == 1
            manager.close("test_db")
            assert len(manager._shared_connections) == 0
    
    def test_close_all(self):
        """测试关闭所有连接"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConnectionManager(tmpdir, auto_cleanup=False)
            manager.get_connection("db1")
            manager.get_connection("db2")
            
            assert len(manager._shared_connections) == 2
            manager.close_all()
            assert len(manager._shared_connections) == 0
    
    def test_context_manager(self):
        """测试上下文管理器"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ConnectionManager(tmpdir, auto_cleanup=False) as manager:
                manager.get_connection("test_db")
                assert len(manager._shared_connections) == 1
            
            # 退出后应该关闭
            assert len(manager._shared_connections) == 0
    
    def test_from_connection(self):
        """测试从现有连接创建"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            
            manager = ConnectionManager.from_connection(conn, "test")
            
            # 应该复用现有连接
            retrieved = manager.get_connection("test")
            assert retrieved is conn
            conn.close()
    
    def test_from_path(self):
        """测试从路径创建"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            manager = ConnectionManager.from_path(db_path)
            
            # 应该预创建连接
            assert len(manager._shared_connections) == 1
            manager.close_all()
    
    def test_get_stats(self):
        """测试获取统计信息"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConnectionManager(tmpdir, auto_cleanup=False)
            manager.get_connection("db1")
            manager.get_connection("db2")
            
            stats = manager.get_stats()
            
            assert stats["shared_count"] == 2
            assert "db1" in stats["shared_connections"]
            assert "db2" in stats["shared_connections"]
            manager.close_all()


class TestConnectionManagerIntegration:
    """ConnectionManager 集成测试"""
    
    def test_create_table_and_query(self):
        """测试创建表和查询"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConnectionManager(tmpdir, auto_cleanup=False)
            conn = manager.get_connection("test_db")
            
            # 创建表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL
                )
            """)
            conn.commit()
            
            # 插入数据
            conn.execute("INSERT INTO users (id, name) VALUES (?, ?)", ("1", "Alice"))
            conn.commit()
            
            # 查询
            cursor = conn.execute("SELECT * FROM users WHERE id = ?", ("1",))
            row = cursor.fetchone()
            
            assert row["name"] == "Alice"
            manager.close_all()
    
    def test_multiple_stores_share_connection(self):
        """测试多个 Store 共享连接"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ConnectionManager(tmpdir, auto_cleanup=False)
            
            # 模拟两个 Store 获取同一个连接
            conn1 = manager.get_connection("knowledge_bank", shared=True)
            conn2 = manager.get_connection("knowledge_bank", shared=True)
            
            # 在 conn1 创建表
            conn1.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    name TEXT
                )
            """)
            conn1.commit()
            
            # 在 conn2 应该能看到表
            cursor = conn2.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='entities'"
            )
            assert cursor.fetchone() is not None
            manager.close_all()
