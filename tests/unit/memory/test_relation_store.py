"""测试关系存储功能"""

import pytest
import sqlite3
from pathlib import Path
from src.core.memory.stores.relation_store import RelationStore


class TestRelationStoreAdd:
    """测试添加关系"""
    
    @pytest.fixture
    def db(self, tmp_path):
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE relations (
                relation_id TEXT PRIMARY KEY,
                source_entity TEXT NOT NULL,
                target_entity TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                context TEXT,
                source_ref TEXT,
                valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_until TIMESTAMP,
                confidence REAL DEFAULT 1.0,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX idx_relations_source ON relations(source_entity)
        """)
        conn.execute("""
            CREATE INDEX idx_relations_target ON relations(target_entity)
        """)
        yield conn
        conn.close()
    
    def test_add_relation_basic(self, db):
        """测试添加基本关系"""
        store = RelationStore(db)
        relation_id = store.add_relation(
            source_entity="entity_001",
            target_entity="entity_002",
            relation_type="competitor",
            context="市场竞争关系"
        )
        
        assert relation_id is not None
        assert relation_id.startswith("relation_")
        
        # 验证数据库中的记录
        cursor = db.execute("SELECT * FROM relations WHERE relation_id = ?", (relation_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == "entity_001"  # source_entity
        assert row[2] == "entity_002"  # target_entity
        assert row[3] == "competitor"  # relation_type
    
    def test_add_relation_with_confidence(self, db):
        """测试添加带置信度的关系"""
        store = RelationStore(db)
        relation_id = store.add_relation(
            source_entity="entity_001",
            target_entity="entity_002",
            relation_type="partner",
            confidence=0.85
        )
        
        # 验证置信度存储
        cursor = db.execute("SELECT confidence FROM relations WHERE relation_id = ?", (relation_id,))
        row = cursor.fetchone()
        assert row[0] == 0.85
    
    def test_add_relation_with_source(self, db):
        """测试添加带来源的关系"""
        store = RelationStore(db)
        relation_id = store.add_relation(
            source_entity="entity_001",
            target_entity="entity_002",
            relation_type="supplier",
            source="研究报告2024Q1"
        )
        
        # 验证来源存储
        cursor = db.execute("SELECT source FROM relations WHERE relation_id = ?", (relation_id,))
        row = cursor.fetchone()
        assert row[0] == "研究报告2024Q1"


class TestRelationStoreGet:
    """测试获取关系"""
    
    @pytest.fixture
    def db_with_data(self, tmp_path):
        """创建带数据的数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE relations (
                relation_id TEXT PRIMARY KEY,
                source_entity TEXT NOT NULL,
                target_entity TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                context TEXT,
                source_ref TEXT,
                valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_until TIMESTAMP,
                confidence REAL DEFAULT 1.0,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX idx_relations_source ON relations(source_entity)")
        conn.execute("CREATE INDEX idx_relations_target ON relations(target_entity)")
        
        store = RelationStore(conn)
        store.add_relation("entity_001", "entity_002", "competitor", context="市场竞争")
        store.add_relation("entity_001", "entity_003", "partner", confidence=0.9)
        store.add_relation("entity_002", "entity_004", "supplier")
        
        yield conn
        conn.close()
    
    def test_get_relation_by_id(self, db_with_data):
        """测试通过ID获取关系"""
        store = RelationStore(db_with_data)
        
        # 先搜索获取ID
        relations = store.get_relations_for_entity("entity_001")
        relation_id = relations[0]["relation_id"]
        
        # 通过ID获取
        relation = store.get_relation(relation_id)
        assert relation is not None
        assert relation["relation_type"] == "competitor"
    
    def test_get_nonexistent_relation(self, db_with_data):
        """测试获取不存在的关系"""
        store = RelationStore(db_with_data)
        
        relation = store.get_relation("relation_nonexistent")
        assert relation is None
    
    def test_get_relations_for_entity(self, db_with_data):
        """测试获取实体的所有关系"""
        store = RelationStore(db_with_data)
        
        # entity_001 有2个关系
        relations = store.get_relations_for_entity("entity_001")
        assert len(relations) == 2
        
        relation_types = [r["relation_type"] for r in relations]
        assert "competitor" in relation_types
        assert "partner" in relation_types
    
    def test_get_relations_by_type(self, db_with_data):
        """测试按类型获取关系"""
        store = RelationStore(db_with_data)
        
        relations = store.get_relations_by_type("competitor")
        assert len(relations) == 1
        assert relations[0]["relation_type"] == "competitor"


class TestRelationStoreSearch:
    """测试搜索关系"""
    
    @pytest.fixture
    def db_with_data(self, tmp_path):
        """创建带数据的数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE relations (
                relation_id TEXT PRIMARY KEY,
                source_entity TEXT NOT NULL,
                target_entity TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                context TEXT,
                source_ref TEXT,
                valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_until TIMESTAMP,
                confidence REAL DEFAULT 1.0,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX idx_relations_source ON relations(source_entity)")
        conn.execute("CREATE INDEX idx_relations_target ON relations(target_entity)")
        
        store = RelationStore(conn)
        store.add_relation("entity_001", "entity_002", "competitor", context="电商市场竞争")
        store.add_relation("entity_001", "entity_003", "partner", context="战略合作")
        store.add_relation("entity_002", "entity_004", "supplier", context="供应链")
        
        yield conn
        conn.close()
    
    def test_search_by_context(self, db_with_data):
        """测试通过上下文搜索"""
        store = RelationStore(db_with_data)
        
        results = store.search_relations("市场")
        assert len(results) >= 1
        
        # 应包含competitor关系
        contexts = [r["context"] for r in results]
        assert any("市场" in c for c in contexts)
    
    def test_search_empty_query(self, db_with_data):
        """测试空查询返回所有关系"""
        store = RelationStore(db_with_data)
        
        results = store.search_relations("")
        assert len(results) == 3
    
    def test_search_with_limit(self, db_with_data):
        """测试限制结果数量"""
        store = RelationStore(db_with_data)
        
        results = store.search_relations("", limit=2)
        assert len(results) == 2


class TestRelationStoreUpdate:
    """测试更新关系"""
    
    @pytest.fixture
    def db(self, tmp_path):
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE relations (
                relation_id TEXT PRIMARY KEY,
                source_entity TEXT NOT NULL,
                target_entity TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                context TEXT,
                source_ref TEXT,
                valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_until TIMESTAMP,
                confidence REAL DEFAULT 1.0,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX idx_relations_source ON relations(source_entity)")
        conn.execute("CREATE INDEX idx_relations_target ON relations(target_entity)")
        yield conn
        conn.close()
    
    def test_update_confidence(self, db):
        """测试更新置信度"""
        store = RelationStore(db)
        relation_id = store.add_relation("entity_001", "entity_002", "competitor", confidence=0.5)
        
        # 更新置信度
        store.update_confidence(relation_id, 0.95)
        
        # 验证更新
        cursor = db.execute("SELECT confidence FROM relations WHERE relation_id = ?", (relation_id,))
        row = cursor.fetchone()
        assert row[0] == 0.95
    
    def test_update_context(self, db):
        """测试更新上下文"""
        store = RelationStore(db)
        relation_id = store.add_relation("entity_001", "entity_002", "competitor")
        
        # 更新上下文
        store.update_context(relation_id, "更新后的竞争关系描述")
        
        # 验证更新
        cursor = db.execute("SELECT context FROM relations WHERE relation_id = ?", (relation_id,))
        row = cursor.fetchone()
        assert row[0] == "更新后的竞争关系描述"
    
    def test_delete_relation(self, db):
        """测试删除关系"""
        store = RelationStore(db)
        relation_id = store.add_relation("entity_001", "entity_002", "competitor")
        
        # 删除关系
        store.delete_relation(relation_id)
        
        # 验证删除
        relation = store.get_relation(relation_id)
        assert relation is None