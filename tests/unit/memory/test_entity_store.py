"""测试实体存储功能"""

import pytest
import sqlite3
from pathlib import Path
from src.core.memory.stores.entity_store import EntityStore


def _create_entities_table(conn: sqlite3.Connection) -> None:
    """创建 entities 表（与实际 schema 一致，包含 UNIQUE 约束）"""
    conn.execute("""
        CREATE TABLE entities (
            entity_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            aliases TEXT,
            description TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_mentioned TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            mention_count INTEGER DEFAULT 1
        )
    """)
    # 添加 UNIQUE 约束（与 src/core/storage/schemas.py 一致）
    conn.execute("CREATE UNIQUE INDEX idx_entities_name_unique ON entities(name)")


class TestEntityStoreAdd:
    """测试添加实体"""
    
    @pytest.fixture
    def db(self, tmp_path):
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _create_entities_table(conn)
        yield conn
        conn.close()
    
    def test_add_entity_basic(self, db):
        """测试添加基本实体"""
        store = EntityStore(db)
        entity_id = store.add_entity(
            entity_type="company",
            name="阿里巴巴",
            description="中国电商平台"
        )
        
        assert entity_id is not None
        assert entity_id.startswith("entity_")
        
        # 验证数据库中的记录
        cursor = db.execute("SELECT * FROM entities WHERE entity_id = ?", (entity_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == "company"  # entity_type
        assert row[2] == "阿里巴巴"  # name
    
    def test_add_entity_with_aliases(self, db):
        """测试添加带别名的实体"""
        store = EntityStore(db)
        entity_id = store.add_entity(
            entity_type="company",
            name="腾讯",
            aliases=["腾讯控股", "Tencent"]
        )
        
        # 验证别名存储
        cursor = db.execute("SELECT aliases FROM entities WHERE entity_id = ?", (entity_id,))
        row = cursor.fetchone()
        import json
        aliases = json.loads(row[0])
        assert "腾讯控股" in aliases
        assert "Tencent" in aliases
    
    def test_add_duplicate_entity_increments_mention(self, db):
        """测试重复添加实体增加提及次数"""
        store = EntityStore(db)
        
        # 第一次添加
        entity_id1 = store.add_entity(
            entity_type="company",
            name="百度"
        )
        
        # 第二次添加同名实体
        entity_id2 = store.add_entity(
            entity_type="company",
            name="百度"
        )
        
        # 应该返回相同的entity_id
        assert entity_id1 == entity_id2
        
        # 提及次数应该是2
        cursor = db.execute("SELECT mention_count FROM entities WHERE entity_id = ?", (entity_id1,))
        row = cursor.fetchone()
        assert row[0] == 2


class TestEntityStoreGet:
    """测试获取实体"""
    
    @pytest.fixture
    def db_with_data(self, tmp_path):
        """创建带数据的数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _create_entities_table(conn)
        
        store = EntityStore(conn)
        store.add_entity("company", "阿里巴巴", description="中国电商平台")
        store.add_entity("company", "腾讯", aliases=["腾讯控股", "Tencent"])
        store.add_entity("industry", "电商")
        
        yield conn
        conn.close()
    
    def test_get_entity_by_id(self, db_with_data):
        """测试通过ID获取实体"""
        store = EntityStore(db_with_data)
        
        # 先搜索获取ID
        entities = store.search_entities("阿里巴巴")
        entity_id = entities[0]["entity_id"]
        
        # 通过ID获取
        entity = store.get_entity(entity_id)
        assert entity is not None
        assert entity["name"] == "阿里巴巴"
        assert entity["entity_type"] == "company"
    
    def test_get_entity_by_name(self, db_with_data):
        """测试通过名称获取实体"""
        store = EntityStore(db_with_data)
        
        entity = store.get_entity_by_name("腾讯")
        assert entity is not None
        assert entity["entity_type"] == "company"
    
    def test_get_entity_by_alias(self, db_with_data):
        """测试通过别名获取实体"""
        store = EntityStore(db_with_data)
        
        entity = store.get_entity_by_name("Tencent")
        assert entity is not None
        assert entity["name"] == "腾讯"
    
    def test_get_nonexistent_entity(self, db_with_data):
        """测试获取不存在的实体"""
        store = EntityStore(db_with_data)
        
        entity = store.get_entity("entity_nonexistent")
        assert entity is None
        
        entity = store.get_entity_by_name("不存在的公司")
        assert entity is None


class TestEntityStoreSearch:
    """测试搜索实体"""
    
    @pytest.fixture
    def db_with_data(self, tmp_path):
        """创建带数据的数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _create_entities_table(conn)
        
        store = EntityStore(conn)
        store.add_entity("company", "阿里巴巴", description="中国电商平台")
        store.add_entity("company", "腾讯", aliases=["腾讯控股"])
        store.add_entity("company", "百度", description="搜索引擎")
        store.add_entity("industry", "电商")
        store.add_entity("industry", "互联网")
        
        yield conn
        conn.close()
    
    def test_search_by_name(self, db_with_data):
        """测试通过名称搜索"""
        store = EntityStore(db_with_data)
        
        results = store.search_entities("阿里")
        assert len(results) >= 1
        
        # 找到阿里巴巴
        names = [r["name"] for r in results]
        assert "阿里巴巴" in names
    
    def test_search_by_type(self, db_with_data):
        """测试通过类型过滤"""
        store = EntityStore(db_with_data)
        
        results = store.search_entities("", entity_type="company")
        assert len(results) == 3
        
        # 都是company类型
        for entity in results:
            assert entity["entity_type"] == "company"
    
    def test_search_with_limit(self, db_with_data):
        """测试限制结果数量"""
        store = EntityStore(db_with_data)
        
        results = store.search_entities("", limit=2)
        assert len(results) == 2
    
    def test_search_empty_query(self, db_with_data):
        """测试空查询返回所有实体"""
        store = EntityStore(db_with_data)
        
        results = store.search_entities("")
        assert len(results) == 5


class TestEntityStoreUpdate:
    """测试更新实体"""
    
    @pytest.fixture
    def db(self, tmp_path):
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _create_entities_table(conn)
        yield conn
        conn.close()
    
    def test_update_mention_count(self, db):
        """测试更新提及次数"""
        store = EntityStore(db)
        entity_id = store.add_entity("company", "京东")
        
        # 更新提及次数
        store.update_mention(entity_id)
        
        # 验证提及次数
        cursor = db.execute("SELECT mention_count FROM entities WHERE entity_id = ?", (entity_id,))
        row = cursor.fetchone()
        assert row[0] == 2
    
    def test_update_last_mentioned(self, db):
        """测试更新最后提及时间"""
        import time
        store = EntityStore(db)
        entity_id = store.add_entity("company", "拼多多")
        
        time.sleep(0.1)  # 确保时间差
        
        # 更新提及
        store.update_mention(entity_id)
        
        # 验证last_mentioned更新
        cursor = db.execute("SELECT first_seen, last_mentioned FROM entities WHERE entity_id = ?", (entity_id,))
        row = cursor.fetchone()
        assert row[1] > row[0]  # last_mentioned > first_seen