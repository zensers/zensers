"""
FTS5 全文索引测试
"""
import pytest
import sqlite3
from pathlib import Path

from src.core.memory.fts import FTSIndexer, FTSSearcher, FTSManager


class TestFTSIndexer:
    """FTSIndexer 测试类"""
    
    @pytest.fixture
    def db(self, tmp_path):
        """创建测试数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        # 创建基础表
        conn.execute("""
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                aliases TEXT,
                mention_count INTEGER DEFAULT 1,
                last_mentioned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute("""
            CREATE TABLE relations (
                relation_id TEXT PRIMARY KEY,
                source_entity TEXT NOT NULL,
                target_entity TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                context TEXT,
                confidence REAL DEFAULT 1.0
            )
        """)
        
        conn.execute("""
            CREATE TABLE data_points (
                data_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value TEXT NOT NULL,
                source TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE insights (
                insight_id TEXT PRIMARY KEY,
                research_id TEXT,
                content TEXT NOT NULL,
                topic TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 插入测试数据
        conn.execute("""
            INSERT INTO entities VALUES 
                ('e1', 'company', '特斯拉', '美国电动汽车公司', 'Tesla, 特斯拉汽车', 10, datetime('now')),
                ('e2', 'company', '比亚迪', '中国新能源汽车制造商', 'BYD', 8, datetime('now')),
                ('e3', 'company', '苹果', '美国科技公司', 'Apple, 苹果公司', 15, datetime('now'))
        """)
        
        conn.execute("""
            INSERT INTO relations VALUES 
                ('r1', 'e1', 'e2', 'competitor', '新能源汽车市场竞争', 0.9),
                ('r2', 'e1', 'e3', 'partner', '供应链合作', 0.8)
        """)
        
        conn.execute("""
            INSERT INTO data_points VALUES 
                ('d1', 'e1', '营收', '500亿美元', '2024Q3财报'),
                ('d2', 'e2', '销量', '30万辆', '2024年数据')
        """)
        
        conn.execute("""
            INSERT INTO insights (insight_id, research_id, content, topic, tags, created_at) VALUES 
                ('i1', 'research_1', '特斯拉在电动车市场保持领先地位', '市场分析', '电动车, 特斯拉', datetime('now')),
                ('i2', 'research_1', '比亚迪快速增长，市场份额提升', '市场分析', '比亚迪, 新能源', datetime('now'))
        """)
        
        yield conn
        conn.close()
    
    def test_create_entities_index(self, db):
        """测试创建实体索引"""
        indexer = FTSIndexer(db)
        indexer.create_entities_index()
        
        # 检查索引是否创建
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entities_fts'"
        )
        assert cursor.fetchone() is not None
        
        # 检查索引内容
        cursor = db.execute("SELECT COUNT(*) FROM entities_fts")
        count = cursor.fetchone()[0]
        assert count == 3
    
    def test_create_all_indexes(self, db):
        """测试创建所有索引"""
        indexer = FTSIndexer(db)
        indexer.create_all_indexes()
        
        # 检查所有索引
        for table in ['entities_fts', 'relations_fts', 'data_points_fts', 'insights_fts']:
            cursor = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            assert cursor.fetchone() is not None
    
    def test_index_auto_update_on_insert(self, db):
        """测试插入时索引自动更新"""
        indexer = FTSIndexer(db)
        indexer.create_entities_index()
        
        # 插入新实体
        db.execute("""
            INSERT INTO entities VALUES 
                ('e4', 'company', '华为', '中国科技公司', 'Huawei', 5, datetime('now'))
        """)
        
        # 检查索引是否更新
        cursor = db.execute("SELECT COUNT(*) FROM entities_fts")
        count = cursor.fetchone()[0]
        assert count == 4
    
    def test_drop_all_indexes(self, db):
        """测试删除所有索引"""
        indexer = FTSIndexer(db)
        indexer.create_all_indexes()
        indexer.drop_all_indexes()
        
        # 检查索引是否删除
        for table in ['entities_fts', 'relations_fts', 'data_points_fts', 'insights_fts']:
            cursor = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            assert cursor.fetchone() is None


class TestFTSSearcher:
    """FTSSearcher 测试类"""
    
    @pytest.fixture
    def db_with_fts(self, tmp_path):
        """创建带 FTS 索引的测试数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        # 创建表和索引
        conn.execute("""
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                aliases TEXT,
                mention_count INTEGER DEFAULT 1,
                last_mentioned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute("""
            INSERT INTO entities VALUES 
                ('e1', 'company', '特斯拉', '美国电动汽车公司', 'Tesla', 10, datetime('now')),
                ('e2', 'company', '比亚迪', '中国新能源汽车制造商', 'BYD', 8, datetime('now')),
                ('e3', 'company', '苹果', '美国科技公司', 'Apple', 15, datetime('now'))
        """)
        
        indexer = FTSIndexer(conn)
        indexer.create_entities_index()
        
        yield conn
        conn.close()
    
    def test_search_entities(self, db_with_fts):
        """测试搜索实体"""
        searcher = FTSSearcher(db_with_fts)
        
        results = searcher.search_entities("特斯拉")
        
        assert len(results) >= 1
        assert any(r['name'] == '特斯拉' for r in results)
    
    def test_search_entities_with_type_filter(self, db_with_fts):
        """测试带类型过滤的搜索"""
        searcher = FTSSearcher(db_with_fts)
        
        results = searcher.search_entities("特斯拉", entity_type="company")
        
        assert len(results) >= 1
        assert all(r['entity_type'] == 'company' for r in results)
    
    def test_search_entities_limit(self, db_with_fts):
        """测试搜索结果限制"""
        searcher = FTSSearcher(db_with_fts)
        
        results = searcher.search_entities("", limit=2)
        
        assert len(results) <= 2
    
    def test_fallback_to_like_search(self, tmp_path):
        """测试回退到 LIKE 搜索"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        # 创建表但不创建 FTS 索引
        conn.execute("""
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                aliases TEXT,
                mention_count INTEGER DEFAULT 1,
                last_mentioned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute("""
            INSERT INTO entities VALUES 
                ('e1', 'company', '特斯拉', '美国电动汽车公司', 'Tesla', 10, datetime('now'))
        """)
        
        searcher = FTSSearcher(conn)
        results = searcher.search_entities("特斯拉")
        
        assert len(results) >= 1
        conn.close()


class TestFTSManager:
    """FTSManager 测试类"""
    
    @pytest.fixture
    def db(self, tmp_path):
        """创建测试数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        conn.execute("""
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                aliases TEXT,
                mention_count INTEGER DEFAULT 1,
                last_mentioned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute("""
            CREATE TABLE relations (
                relation_id TEXT PRIMARY KEY,
                source_entity TEXT NOT NULL,
                target_entity TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                context TEXT,
                confidence REAL DEFAULT 1.0
            )
        """)
        
        conn.execute("""
            CREATE TABLE data_points (
                data_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value TEXT NOT NULL,
                source TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE insights (
                insight_id TEXT PRIMARY KEY,
                research_id TEXT,
                content TEXT NOT NULL,
                topic TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute("""
            INSERT INTO entities (entity_id, entity_type, name, description, aliases, mention_count, last_mentioned) VALUES 
                ('e1', 'company', '特斯拉', '美国电动汽车公司', 'Tesla', 10, datetime('now'))
        """)
        
        yield conn
        conn.close()
    
    def test_initialize(self, db):
        """测试初始化"""
        manager = FTSManager(db)
        manager.initialize()
        
        assert manager.is_available()
    
    def test_search(self, db):
        """测试搜索"""
        manager = FTSManager(db)
        manager.initialize()
        
        results = manager.search("特斯拉")
        
        assert "entities" in results
        assert len(results["entities"]) >= 1
    
    def test_rebuild(self, db):
        """测试重建索引"""
        manager = FTSManager(db)
        manager.initialize()
        manager.rebuild()
        
        assert manager.is_available()


class TestFTSQueryBuilding:
    """FTS 查询构建测试"""
    
    def test_build_simple_query(self):
        """测试简单查询构建"""
        searcher = FTSSearcher(None)
        
        query = searcher._build_fts_query("特斯拉")
        assert query == "特斯拉*"
    
    def test_build_phrase_query(self):
        """测试短语查询构建"""
        searcher = FTSSearcher(None)
        
        query = searcher._build_fts_query("特斯拉 电动车")
        assert query == '"特斯拉 电动车"'
    
    def test_escape_special_chars(self):
        """测试特殊字符转义"""
        searcher = FTSSearcher(None)
        
        query = searcher._build_fts_query('测试"引号')
        assert '"' in query
