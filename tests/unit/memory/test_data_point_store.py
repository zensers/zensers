"""测试数据点存储功能"""

import pytest
import sqlite3
from pathlib import Path
from src.core.memory.stores.data_point_store import DataPointStore


class TestDataPointStoreAdd:
    """测试添加数据点"""
    
    @pytest.fixture
    def db(self, tmp_path):
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE data_points (
                data_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value TEXT NOT NULL,
                unit TEXT,
                time_period TEXT,
                source TEXT,
                source_ref TEXT,
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX idx_data_entity ON data_points(entity_id)")
        conn.execute("CREATE INDEX idx_data_metric ON data_points(metric_name)")
        yield conn
        conn.close()
    
    def test_add_data_point_basic(self, db):
        """测试添加基本数据点"""
        store = DataPointStore(db)
        data_id = store.add_data_point(
            entity_id="entity_001",
            metric_name="营收",
            metric_value="5000亿",
            unit="人民币"
        )
        
        assert data_id is not None
        assert data_id.startswith("data_")
        
        # 验证数据库中的记录
        cursor = db.execute("SELECT * FROM data_points WHERE data_id = ?", (data_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == "entity_001"
        assert row[2] == "营收"
        assert row[3] == "5000亿"
    
    def test_add_data_point_with_time_period(self, db):
        """测试添加带时间周期的数据点"""
        store = DataPointStore(db)
        data_id = store.add_data_point(
            entity_id="entity_001",
            metric_name="营收",
            metric_value="5000亿",
            time_period="2024Q1"
        )
        
        # 验证时间周期存储
        cursor = db.execute("SELECT time_period FROM data_points WHERE data_id = ?", (data_id,))
        row = cursor.fetchone()
        assert row[0] == "2024Q1"
    
    def test_add_data_point_with_source(self, db):
        """测试添加带来源的数据点"""
        store = DataPointStore(db)
        data_id = store.add_data_point(
            entity_id="entity_001",
            metric_name="营收",
            metric_value="5000亿",
            source="财务报告2024Q1"
        )
        
        # 验证来源存储
        cursor = db.execute("SELECT source FROM data_points WHERE data_id = ?", (data_id,))
        row = cursor.fetchone()
        assert row[0] == "财务报告2024Q1"
    
    def test_add_numeric_data_point(self, db):
        """测试添加数值型数据点"""
        store = DataPointStore(db)
        data_id = store.add_data_point(
            entity_id="entity_001",
            metric_name="增长率",
            metric_value="25.5%",
            unit="百分比"
        )
        
        # 验证数值存储
        cursor = db.execute("SELECT metric_value, unit FROM data_points WHERE data_id = ?", (data_id,))
        row = cursor.fetchone()
        assert row[0] == "25.5%"
        assert row[1] == "百分比"


class TestDataPointStoreGet:
    """测试获取数据点"""
    
    @pytest.fixture
    def db_with_data(self, tmp_path):
        """创建带数据的数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE data_points (
                data_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value TEXT NOT NULL,
                unit TEXT,
                time_period TEXT,
                source TEXT,
                source_ref TEXT,
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX idx_data_entity ON data_points(entity_id)")
        conn.execute("CREATE INDEX idx_data_metric ON data_points(metric_name)")
        
        store = DataPointStore(conn)
        store.add_data_point("entity_001", "营收", "5000亿", unit="人民币", time_period="2024Q1")
        store.add_data_point("entity_001", "增长率", "25%", unit="百分比", time_period="2024Q1")
        store.add_data_point("entity_002", "营收", "3000亿", unit="人民币", time_period="2024Q1")
        
        yield conn
        conn.close()
    
    def test_get_data_point_by_id(self, db_with_data):
        """测试通过ID获取数据点"""
        store = DataPointStore(db_with_data)
        
        # 先搜索获取ID
        data_points = store.get_data_for_entity("entity_001")
        data_id = data_points[0]["data_id"]
        
        # 通过ID获取
        data_point = store.get_data_point(data_id)
        assert data_point is not None
        assert data_point["metric_name"] in ["营收", "增长率"]
    
    def test_get_nonexistent_data_point(self, db_with_data):
        """测试获取不存在的数据点"""
        store = DataPointStore(db_with_data)
        
        data_point = store.get_data_point("data_nonexistent")
        assert data_point is None
    
    def test_get_data_for_entity(self, db_with_data):
        """测试获取实体的所有数据点"""
        store = DataPointStore(db_with_data)
        
        # entity_001 有2个数据点
        data_points = store.get_data_for_entity("entity_001")
        assert len(data_points) == 2
        
        metric_names = [dp["metric_name"] for dp in data_points]
        assert "营收" in metric_names
        assert "增长率" in metric_names
    
    def test_get_data_by_metric(self, db_with_data):
        """测试按指标获取数据点"""
        store = DataPointStore(db_with_data)
        
        data_points = store.get_data_by_metric("营收")
        assert len(data_points) == 2
        
        # 都是营收数据
        for dp in data_points:
            assert dp["metric_name"] == "营收"


class TestDataPointStoreSearch:
    """测试搜索数据点"""
    
    @pytest.fixture
    def db_with_data(self, tmp_path):
        """创建带数据的数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE data_points (
                data_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value TEXT NOT NULL,
                unit TEXT,
                time_period TEXT,
                source TEXT,
                source_ref TEXT,
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX idx_data_entity ON data_points(entity_id)")
        conn.execute("CREATE INDEX idx_data_metric ON data_points(metric_name)")
        
        store = DataPointStore(conn)
        store.add_data_point("entity_001", "营收", "5000亿", source="阿里巴巴财报")
        store.add_data_point("entity_001", "增长率", "25%", source="阿里巴巴财报")
        store.add_data_point("entity_002", "营收", "3000亿", source="腾讯财报")
        
        yield conn
        conn.close()
    
    def test_search_by_value(self, db_with_data):
        """测试通过值搜索"""
        store = DataPointStore(db_with_data)
        
        results = store.search_data_points("5000")
        assert len(results) >= 1
        
        # 应包含5000亿的数据点
        values = [dp["metric_value"] for dp in results]
        assert any("5000" in v for v in values)
    
    def test_search_by_source(self, db_with_data):
        """测试通过来源搜索"""
        store = DataPointStore(db_with_data)
        
        results = store.search_data_points("阿里巴巴")
        assert len(results) >= 1
        
        # 应来自阿里巴巴财报
        sources = [dp["source"] for dp in results]
        assert any("阿里巴巴" in s for s in sources)
    
    def test_search_empty_query(self, db_with_data):
        """测试空查询返回所有数据点"""
        store = DataPointStore(db_with_data)
        
        results = store.search_data_points("")
        assert len(results) == 3
    
    def test_search_with_limit(self, db_with_data):
        """测试限制结果数量"""
        store = DataPointStore(db_with_data)
        
        results = store.search_data_points("", limit=2)
        assert len(results) == 2


class TestDataPointStoreUpdate:
    """测试更新数据点"""
    
    @pytest.fixture
    def db(self, tmp_path):
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE data_points (
                data_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value TEXT NOT NULL,
                unit TEXT,
                time_period TEXT,
                source TEXT,
                source_ref TEXT,
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX idx_data_entity ON data_points(entity_id)")
        conn.execute("CREATE INDEX idx_data_metric ON data_points(metric_name)")
        yield conn
        conn.close()
    
    def test_update_confidence(self, db):
        """测试更新置信度"""
        store = DataPointStore(db)
        data_id = store.add_data_point("entity_001", "营收", "5000亿", confidence=0.5)
        
        # 更新置信度
        store.update_confidence(data_id, 0.95)
        
        # 验证更新
        cursor = db.execute("SELECT confidence FROM data_points WHERE data_id = ?", (data_id,))
        row = cursor.fetchone()
        assert row[0] == 0.95
    
    def test_update_value(self, db):
        """测试更新数值"""
        store = DataPointStore(db)
        data_id = store.add_data_point("entity_001", "营收", "5000亿")
        
        # 更新数值
        store.update_value(data_id, "5500亿")
        
        # 验证更新
        cursor = db.execute("SELECT metric_value FROM data_points WHERE data_id = ?", (data_id,))
        row = cursor.fetchone()
        assert row[0] == "5500亿"
    
    def test_delete_data_point(self, db):
        """测试删除数据点"""
        store = DataPointStore(db)
        data_id = store.add_data_point("entity_001", "营收", "5000亿")
        
        # 删除数据点
        store.delete_data_point(data_id)
        
        # 验证删除
        data_point = store.get_data_point(data_id)
        assert data_point is None
    
    def test_get_latest_data(self, db):
        """测试获取最新数据"""
        store = DataPointStore(db)
        
        # 添加多个时间点的数据
        store.add_data_point("entity_001", "营收", "5000亿", time_period="2023Q4")
        store.add_data_point("entity_001", "营收", "5500亿", time_period="2024Q1")
        
        # 获取最新数据
        latest = store.get_latest_data("entity_001", "营收")
        assert latest is not None
        assert latest["metric_value"] == "5500亿"