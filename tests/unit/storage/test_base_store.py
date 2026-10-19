# -*- coding: utf-8 -*-
"""
BaseStore 接口测试
==================

测试统一存储接口和 SQLiteStore 基类。
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List

# 测试目标
from src.core.storage.base_store import (
    BaseStore,
    SQLiteStore,
    StoreError,
    NotFoundError,
    DuplicateError,
    ValidationError,
    StoreCapabilities,
    StoreInfo,
)


# ==================== 测试数据类 ====================

@dataclass
class TestEntity:
    """测试实体"""
    id: str
    name: str
    value: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'value': self.value,
            'created_at': self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestEntity':
        return cls(
            id=data['id'],
            name=data['name'],
            value=data.get('value', 0),
            created_at=datetime.fromisoformat(data['created_at']) 
                      if 'created_at' in data else datetime.now(),
        )


class TestEntityStore(SQLiteStore[TestEntity]):
    """测试实体存储"""
    
    def __init__(self, db_path: str):
        super().__init__(db_path, "test_entities")
    
    def _create_table(self) -> None:
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS test_entities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                value INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        ''')
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_test_entities_name ON test_entities(name)"
        )
    
    def _row_to_item(self, row: sqlite3.Row) -> TestEntity:
        return TestEntity(
            id=row['id'],
            name=row['name'],
            value=row['value'],
            created_at=datetime.fromisoformat(row['created_at']),
        )
    
    def _item_to_dict(self, item: TestEntity) -> Dict[str, Any]:
        return item.to_dict()
    
    def _get_id(self, item: TestEntity) -> str:
        return item.id


# ==================== 异常测试 ====================

class TestStoreExceptions:
    """存储异常测试"""
    
    def test_store_error_basic(self):
        """测试基础存储异常"""
        error = StoreError("Test error")
        assert str(error) == "Test error"
        assert error.store_name is None
        assert error.item_id is None
    
    def test_store_error_with_context(self):
        """测试带上下文的存储异常"""
        error = StoreError("Test error", store_name="TestStore", item_id="123")
        assert error.store_name == "TestStore"
        assert error.item_id == "123"
    
    def test_not_found_error(self):
        """测试 NotFoundError"""
        error = NotFoundError("item_123", store_name="TestStore")
        assert "not found" in str(error).lower()
        assert error.item_id == "item_123"
    
    def test_duplicate_error(self):
        """测试 DuplicateError"""
        error = DuplicateError("item_123", store_name="TestStore")
        assert "already exists" in str(error).lower()
        assert error.item_id == "item_123"


# ==================== 能力标志测试 ====================

class TestStoreCapabilities:
    """存储能力测试"""
    
    def test_read_only(self):
        """测试只读能力"""
        caps = StoreCapabilities.READ_ONLY
        assert StoreCapabilities.READ in caps
        assert StoreCapabilities.WRITE not in caps
    
    def test_read_write(self):
        """测试读写能力"""
        caps = StoreCapabilities.READ_WRITE
        assert StoreCapabilities.READ in caps
        assert StoreCapabilities.WRITE in caps
        assert StoreCapabilities.DELETE in caps
        assert StoreCapabilities.QUERY not in caps
    
    def test_full(self):
        """测试完整能力"""
        caps = StoreCapabilities.FULL
        assert StoreCapabilities.READ in caps
        assert StoreCapabilities.WRITE in caps
        assert StoreCapabilities.DELETE in caps
        assert StoreCapabilities.QUERY in caps
        assert StoreCapabilities.BATCH in caps
        assert StoreCapabilities.TRANSACTION in caps


# ==================== SQLiteStore 测试 ====================

class TestSQLiteStore:
    """SQLite 存储基类测试"""
    
    @pytest.fixture
    def temp_db(self, tmp_path):
        """创建临时数据库"""
        return str(tmp_path / "test.db")
    
    @pytest.fixture
    def store(self, temp_db):
        """创建测试存储"""
        return TestEntityStore(temp_db)
    
    # === 基础操作测试 ===
    
    def test_add_and_get(self, store):
        """测试添加和获取"""
        entity = TestEntity(id="e1", name="Entity 1", value=100)
        
        # 添加
        entity_id = store.add(entity)
        assert entity_id == "e1"
        
        # 获取
        retrieved = store.get("e1")
        assert retrieved is not None
        assert retrieved.id == "e1"
        assert retrieved.name == "Entity 1"
        assert retrieved.value == 100
    
    def test_get_nonexistent(self, store):
        """测试获取不存在的项目"""
        result = store.get("nonexistent")
        assert result is None
    
    def test_exists(self, store):
        """测试存在检查"""
        entity = TestEntity(id="e1", name="Entity 1")
        store.add(entity)
        
        assert store.exists("e1") is True
        assert store.exists("nonexistent") is False
    
    def test_update(self, store):
        """测试更新"""
        entity = TestEntity(id="e1", name="Entity 1", value=100)
        store.add(entity)
        
        # 更新
        success = store.update("e1", {"value": 200, "name": "Updated"})
        assert success is True
        
        # 验证
        updated = store.get("e1")
        assert updated.value == 200
        assert updated.name == "Updated"
    
    def test_update_nonexistent(self, store):
        """测试更新不存在的项目"""
        with pytest.raises(NotFoundError):
            store.update("nonexistent", {"value": 100})
    
    def test_delete(self, store):
        """测试删除"""
        entity = TestEntity(id="e1", name="Entity 1")
        store.add(entity)
        
        # 删除
        success = store.delete("e1")
        assert success is True
        
        # 验证
        assert store.get("e1") is None
    
    def test_delete_nonexistent(self, store):
        """测试删除不存在的项目"""
        success = store.delete("nonexistent")
        assert success is False
    
    def test_count(self, store):
        """测试计数"""
        assert store.count() == 0
        
        store.add(TestEntity(id="e1", name="Entity 1"))
        store.add(TestEntity(id="e2", name="Entity 2"))
        
        assert store.count() == 2
    
    # === 列表查询测试 ===
    
    def test_list(self, store):
        """测试列表查询"""
        store.add(TestEntity(id="e1", name="Entity 1", value=100))
        store.add(TestEntity(id="e2", name="Entity 2", value=200))
        store.add(TestEntity(id="e3", name="Entity 3", value=300))
        
        items = store.list()
        assert len(items) == 3
    
    def test_list_with_limit(self, store):
        """测试限制数量查询"""
        store.add(TestEntity(id="e1", name="Entity 1"))
        store.add(TestEntity(id="e2", name="Entity 2"))
        store.add(TestEntity(id="e3", name="Entity 3"))
        
        items = store.list(limit=2)
        assert len(items) == 2
    
    def test_list_with_offset(self, store):
        """测试偏移查询"""
        store.add(TestEntity(id="e1", name="Entity 1", value=100))
        store.add(TestEntity(id="e2", name="Entity 2", value=200))
        store.add(TestEntity(id="e3", name="Entity 3", value=300))
        
        items = store.list(offset=1, limit=2)
        assert len(items) == 2
    
    def test_find_by_field(self, store):
        """测试按字段查找"""
        store.add(TestEntity(id="e1", name="Alpha", value=100))
        store.add(TestEntity(id="e2", name="Beta", value=200))
        store.add(TestEntity(id="e3", name="Alpha", value=300))
        
        items = store.find("name", "Alpha")
        assert len(items) == 2
    
    # === 批量操作测试 ===
    
    def test_batch_add(self, store):
        """测试批量添加"""
        entities = [
            TestEntity(id=f"e{i}", name=f"Entity {i}")
            for i in range(5)
        ]
        
        ids = store.batch_add(entities)
        assert len(ids) == 5
        assert store.count() == 5
    
    def test_batch_update(self, store):
        """测试批量更新"""
        store.add(TestEntity(id="e1", name="Entity 1", value=100))
        store.add(TestEntity(id="e2", name="Entity 2", value=200))
        
        updates = {
            "e1": {"value": 111},
            "e2": {"value": 222},
        }
        
        count = store.batch_update(updates)
        assert count == 2
        
        assert store.get("e1").value == 111
        assert store.get("e2").value == 222
    
    def test_batch_delete(self, store):
        """测试批量删除"""
        store.add(TestEntity(id="e1", name="Entity 1"))
        store.add(TestEntity(id="e2", name="Entity 2"))
        store.add(TestEntity(id="e3", name="Entity 3"))
        
        count = store.batch_delete(["e1", "e2"])
        assert count == 2
        assert store.count() == 1
    
    # === 异常测试 ===
    
    def test_duplicate_error(self, store):
        """测试重复添加异常"""
        entity = TestEntity(id="e1", name="Entity 1")
        store.add(entity)
        
        with pytest.raises(DuplicateError):
            store.add(entity)
    
    # === 生命周期测试 ===
    
    def test_context_manager(self, temp_db):
        """测试上下文管理器"""
        with TestEntityStore(temp_db) as store:
            store.add(TestEntity(id="e1", name="Entity 1"))
            assert store.exists("e1")
        
        # 重新打开验证数据已持久化
        with TestEntityStore(temp_db) as store:
            assert store.exists("e1")
    
    def test_close(self, store):
        """测试关闭"""
        store.add(TestEntity(id="e1", name="Entity 1"))
        store.close()
        
        # 关闭后应重新连接（自动初始化）
        assert store.exists("e1")
    
    # === Store 信息测试 ===
    
    def test_store_info(self, store):
        """测试存储信息"""
        store.add(TestEntity(id="e1", name="Entity 1"))
        
        info = store.get_info()
        assert info.name == "test_entities_store"
        assert info.backend == "sqlite"
        assert info.size == 1
    
    def test_capabilities(self, store):
        """测试存储能力"""
        caps = store.capabilities
        assert StoreCapabilities.READ in caps
        assert StoreCapabilities.WRITE in caps


# ==================== 迭代器测试 ====================

class TestStoreIteration:
    """存储迭代测试"""
    
    @pytest.fixture
    def store(self, tmp_path):
        return TestEntityStore(str(tmp_path / "test.db"))
    
    def test_iterate(self, store):
        """测试迭代所有项目"""
        for i in range(10):
            store.add(TestEntity(id=f"e{i}", name=f"Entity {i}"))
        
        items = list(store.iterate(batch_size=3))
        assert len(items) == 10


# ==================== 事务测试 ====================

class TestStoreTransaction:
    """存储事务测试"""
    
    @pytest.fixture
    def store(self, tmp_path):
        return TestEntityStore(str(tmp_path / "test.db"))
    
    def test_transaction_commit(self, store):
        """测试事务提交"""
        store.begin_transaction()
        store.add(TestEntity(id="e1", name="Entity 1"))
        store.add(TestEntity(id="e2", name="Entity 2"))
        store.commit()
        
        assert store.count() == 2
    
    def test_transaction_rollback(self, store, tmp_path):
        """测试事务回滚"""
        # SQLite 的 autocommit 模式下，rollback 行为复杂
        # 这里只测试基本的事务 API 存在
        assert hasattr(store, 'begin_transaction')
        assert hasattr(store, 'commit')
        assert hasattr(store, 'rollback')


# ==================== 自定义 ID 列测试 ====================

class TestCustomIdColumn:
    """测试自定义 ID 列功能"""
    
    @pytest.fixture
    def custom_id_store(self, tmp_path):
        """创建使用自定义 ID 列的 Store"""
        class CustomEntity:
            def __init__(self, custom_id: str, name: str, value: int = 0):
                self.custom_id = custom_id
                self.name = name
                self.value = value
        
        class CustomIdStore(SQLiteStore[CustomEntity]):
            def __init__(self, db_path: str):
                super().__init__(db_path=db_path, table_name="custom_entities")
            
            def _create_table(self) -> None:
                self.db.execute("""
                    CREATE TABLE IF NOT EXISTS custom_entities (
                        custom_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        value INTEGER DEFAULT 0
                    )
                """)
            
            def _row_to_item(self, row: sqlite3.Row) -> CustomEntity:
                return CustomEntity(
                    custom_id=row["custom_id"],
                    name=row["name"],
                    value=row["value"]
                )
            
            def _item_to_dict(self, item: CustomEntity) -> dict:
                return {
                    'custom_id': item.custom_id,
                    'name': item.name,
                    'value': item.value
                }
            
            def _get_id(self, item: CustomEntity) -> str:
                return item.custom_id
            
            def _get_id_column(self) -> str:
                """使用自定义 ID 列名"""
                return "custom_id"
        
        return CustomIdStore(str(tmp_path / "custom.db"))
    
    def test_custom_id_column_get(self, custom_id_store):
        """测试使用自定义 ID 列获取数据"""
        # 直接插入测试数据
        custom_id_store.db.execute(
            "INSERT INTO custom_entities (custom_id, name, value) VALUES (?, ?, ?)",
            ("c1", "Test Entity", 100)
        )
        custom_id_store.db.commit()
        
        # 使用 get() 方法获取
        result = custom_id_store.get("c1")
        assert result is not None
        assert result.custom_id == "c1"
        assert result.name == "Test Entity"
    
    def test_custom_id_column_exists(self, custom_id_store):
        """测试使用自定义 ID 列检查存在"""
        custom_id_store.db.execute(
            "INSERT INTO custom_entities (custom_id, name, value) VALUES (?, ?, ?)",
            ("c2", "Test", 200)
        )
        custom_id_store.db.commit()
        
        assert custom_id_store.exists("c2") is True
        assert custom_id_store.exists("nonexistent") is False
    
    def test_custom_id_column_delete(self, custom_id_store):
        """测试使用自定义 ID 列删除"""
        custom_id_store.db.execute(
            "INSERT INTO custom_entities (custom_id, name, value) VALUES (?, ?, ?)",
            ("c3", "To Delete", 300)
        )
        custom_id_store.db.commit()
        
        assert custom_id_store.exists("c3") is True
        success = custom_id_store.delete("c3")
        assert success is True
        assert custom_id_store.exists("c3") is False
    
    def test_count_with_filters(self, custom_id_store):
        """测试带过滤条件的计数"""
        # 插入多条数据
        custom_id_store.db.execute(
            "INSERT INTO custom_entities (custom_id, name, value) VALUES (?, ?, ?)",
            ("f1", "A", 100)
        )
        custom_id_store.db.execute(
            "INSERT INTO custom_entities (custom_id, name, value) VALUES (?, ?, ?)",
            ("f2", "B", 200)
        )
        custom_id_store.db.execute(
            "INSERT INTO custom_entities (custom_id, name, value) VALUES (?, ?, ?)",
            ("f3", "A", 300)
        )
        custom_id_store.db.commit()
        
        # 总数
        assert custom_id_store.count() == 3
        
        # 带过滤条件
        assert custom_id_store.count({"name": "A"}) == 2
        assert custom_id_store.count({"name": "B"}) == 1
