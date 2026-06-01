# -*- coding: utf-8 -*-
"""
洞察存储测试
============

测试 InsightStore 的核心功能。
"""

import pytest
import sqlite3
import json
from datetime import datetime
from src.core.memory.stores.insight_store import InsightStore, Insight


def _create_insights_table(conn: sqlite3.Connection) -> None:
    """创建 insights 表（与实际 schema 一致）"""
    conn.execute("""
        CREATE TABLE insights (
            insight_id TEXT PRIMARY KEY,
            research_id TEXT NOT NULL,
            topic TEXT,
            content TEXT,
            supporting_data TEXT,
            source_ref TEXT,
            confidence TEXT DEFAULT 'medium',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 添加索引
    conn.execute("CREATE INDEX idx_insights_research ON insights(research_id)")
    conn.execute("CREATE INDEX idx_insights_topic ON insights(topic)")


class TestInsightStoreCreate:
    """测试创建洞察"""

    @pytest.fixture
    def db(self, tmp_path):
        """创建临时数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        _create_insights_table(conn)
        yield conn
        conn.close()

    def test_create_basic_insight(self, db):
        """测试创建基本洞察"""
        store = InsightStore(db)
        
        insight = Insight(
            insight_id="insight_001",
            research_id="research_001",
            topic="市场趋势",
            content="AI市场正在快速增长"
        )
        
        insight_id = store.create(insight)
        assert insight_id == "insight_001"
        
        # 验证数据库记录
        cursor = db.execute("SELECT * FROM insights WHERE insight_id = ?", (insight_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row['research_id'] == "research_001"
        assert row['topic'] == "市场趋势"
        assert row['content'] == "AI市场正在快速增长"

    def test_create_insight_with_supporting_data(self, db):
        """测试创建带支撑数据的洞察"""
        store = InsightStore(db)
        
        insight = Insight(
            insight_id="insight_002",
            research_id="research_001",
            topic="竞争分析",
            content="主要竞争对手分析",
            supporting_data=["data_001", "data_002"],
            source_ref="source_001"
        )
        
        insight_id = store.create(insight)
        
        # 验证支撑数据
        cursor = db.execute("SELECT supporting_data, source_ref FROM insights WHERE insight_id = ?", (insight_id,))
        row = cursor.fetchone()
        supporting_data = json.loads(row['supporting_data'])
        assert "data_001" in supporting_data
        assert "data_002" in supporting_data
        assert row['source_ref'] == "source_001"

    def test_create_insight_with_confidence(self, db):
        """测试创建带置信度的洞察"""
        store = InsightStore(db)
        
        insight = Insight(
            insight_id="insight_003",
            research_id="research_002",
            topic="风险分析",
            content="市场风险较高",
            confidence="high"
        )
        
        store.create(insight)
        
        cursor = db.execute("SELECT confidence FROM insights WHERE insight_id = ?", ("insight_003",))
        row = cursor.fetchone()
        assert row['confidence'] == "high"


class TestInsightStoreGet:
    """测试获取洞察"""

    @pytest.fixture
    def db_with_data(self, tmp_path):
        """创建带数据的数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        _create_insights_table(conn)
        
        store = InsightStore(conn)
        
        # 创建测试数据
        store.create(Insight(
            insight_id="insight_001",
            research_id="research_001",
            topic="市场趋势",
            content="AI市场正在快速增长"
        ))
        
        store.create(Insight(
            insight_id="insight_002",
            research_id="research_001",
            topic="竞争分析",
            content="主要竞争对手包括OpenAI和Google"
        ))
        
        store.create(Insight(
            insight_id="insight_003",
            research_id="research_002",
            topic="市场趋势",
            content="云计算市场趋于饱和"
        ))
        
        yield conn
        conn.close()

    def test_get_by_id(self, db_with_data):
        """测试通过ID获取洞察"""
        store = InsightStore(db_with_data)
        
        insight = store.get("insight_001")
        assert insight is not None
        assert insight.insight_id == "insight_001"
        assert insight.research_id == "research_001"
        assert insight.topic == "市场趋势"

    def test_get_nonexistent(self, db_with_data):
        """测试获取不存在的洞察"""
        store = InsightStore(db_with_data)
        
        insight = store.get("insight_nonexistent")
        assert insight is None

    def test_get_by_research(self, db_with_data):
        """测试按研究ID获取洞察"""
        store = InsightStore(db_with_data)
        
        insights = store.get_by_research("research_001")
        assert len(insights) == 2
        
        insight_ids = [i.insight_id for i in insights]
        assert "insight_001" in insight_ids
        assert "insight_002" in insight_ids

    def test_get_by_research_empty(self, db_with_data):
        """测试获取不存在研究的洞察"""
        store = InsightStore(db_with_data)
        
        insights = store.get_by_research("research_nonexistent")
        assert len(insights) == 0


class TestInsightStoreSearch:
    """测试搜索洞察"""

    @pytest.fixture
    def db_with_data(self, tmp_path):
        """创建带数据的数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        _create_insights_table(conn)
        
        store = InsightStore(conn)
        
        store.create(Insight(
            insight_id="insight_001",
            research_id="research_001",
            topic="市场趋势",
            content="AI市场正在快速增长"
        ))
        
        store.create(Insight(
            insight_id="insight_002",
            research_id="research_001",
            topic="竞争分析",
            content="OpenAI是主要竞争对手"
        ))
        
        store.create(Insight(
            insight_id="insight_003",
            research_id="research_002",
            topic="市场趋势",
            content="云计算市场趋于饱和"
        ))
        
        yield conn
        conn.close()

    def test_search_by_query(self, db_with_data):
        """测试按关键词搜索"""
        store = InsightStore(db_with_data)
        
        results = store.search(query="AI")
        assert len(results) >= 1
        
        contents = [r.content for r in results]
        assert any("AI" in c for c in contents)

    def test_search_by_topic(self, db_with_data):
        """测试按主题搜索"""
        store = InsightStore(db_with_data)
        
        results = store.search(topic="市场趋势")
        assert len(results) == 2

    def test_search_with_limit(self, db_with_data):
        """测试限制结果数量"""
        store = InsightStore(db_with_data)
        
        results = store.search(limit=1)
        assert len(results) == 1

    def test_search_empty_query(self, db_with_data):
        """测试空查询返回所有"""
        store = InsightStore(db_with_data)
        
        results = store.search()
        assert len(results) == 3


class TestInsightStoreCount:
    """测试统计洞察"""

    @pytest.fixture
    def db_with_data(self, tmp_path):
        """创建带数据的数据库"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        _create_insights_table(conn)
        
        store = InsightStore(conn)
        
        store.create(Insight(
            insight_id="insight_001",
            research_id="research_001",
            topic="市场趋势",
            content="AI市场正在快速增长"
        ))
        
        store.create(Insight(
            insight_id="insight_002",
            research_id="research_001",
            topic="竞争分析",
            content="OpenAI是主要竞争对手"
        ))
        
        yield conn
        conn.close()

    def test_count_all(self, db_with_data):
        """测试统计所有洞察"""
        store = InsightStore(db_with_data)
        
        count = store.count()
        assert count == 2

    def test_count_with_filters(self, db_with_data):
        """测试带过滤条件的统计"""
        store = InsightStore(db_with_data)
        
        count = store.count(filters={"research_id": "research_001"})
        assert count == 2


class TestInsightModel:
    """测试 Insight 数据模型"""

    def test_insight_to_dict(self):
        """测试 Insight 转换为字典"""
        insight = Insight(
            insight_id="insight_001",
            research_id="research_001",
            topic="测试主题",
            content="测试内容",
            supporting_data=["data_001"],
            confidence="high"
        )
        
        result = insight.to_dict()
        
        assert result['insight_id'] == "insight_001"
        assert result['research_id'] == "research_001"
        assert result['topic'] == "测试主题"
        assert result['content'] == "测试内容"
        assert result['confidence'] == "high"

    def test_insight_defaults(self):
        """测试 Insight 默认值"""
        insight = Insight(
            insight_id="insight_001",
            research_id="research_001"
        )
        
        assert insight.topic == ""
        assert insight.content == ""
        assert insight.supporting_data == []
        assert insight.source_ref == ""
        assert insight.confidence == "medium"
