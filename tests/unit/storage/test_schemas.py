# -*- coding: utf-8 -*-
"""
Schema 定义测试
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from src.core.storage.schemas import (
    register_all_schemas,
    ENTITIES_SCHEMA,
    RELATIONS_SCHEMA,
    DATA_POINTS_SCHEMA,
    INSIGHTS_SCHEMA,
    RESEARCH_HISTORY_SCHEMA,
    REQUIREMENTS_SCHEMA,
    FRAMEWORKS_SCHEMA,
    LEARNINGS_SCHEMA,
    ERRORS_SCHEMA,
    FEATURE_REQUESTS_SCHEMA,
    KNOWLEDGE_VERSIONS_SCHEMA,
    PROVENANCE_SCHEMA,
    CONTRADICTIONS_SCHEMA,
    KNOWLEDGE_PAGES_SCHEMA,
    SESSION_SNAPSHOTS_SCHEMA,
    RAW_RESEARCH_DATA_SCHEMA,
)
from src.core.storage.schema_registry import SchemaRegistry


class TestSchemaDefinitions:
    """Schema 定义测试"""
    
    def test_entities_schema(self):
        """测试实体 Schema"""
        assert ENTITIES_SCHEMA.table_name == "entities"
        assert len(ENTITIES_SCHEMA.columns) == 10
        assert len(ENTITIES_SCHEMA.indexes) == 2
        assert ENTITIES_SCHEMA.get_primary_key() == "entity_id"
    
    def test_relations_schema(self):
        """测试关系 Schema"""
        assert RELATIONS_SCHEMA.table_name == "relations"
        assert len(RELATIONS_SCHEMA.columns) == 10
        assert len(RELATIONS_SCHEMA.indexes) == 3
    
    def test_data_points_schema(self):
        """测试数据点 Schema"""
        assert DATA_POINTS_SCHEMA.table_name == "data_points"
        assert len(DATA_POINTS_SCHEMA.columns) == 9
        assert len(DATA_POINTS_SCHEMA.indexes) == 2
    
    def test_insights_schema(self):
        """测试洞察 Schema"""
        assert INSIGHTS_SCHEMA.table_name == "insights"
        assert len(INSIGHTS_SCHEMA.columns) == 8
        assert len(INSIGHTS_SCHEMA.indexes) == 2
    
    def test_research_history_schema(self):
        """测试研究历史 Schema"""
        assert RESEARCH_HISTORY_SCHEMA.table_name == "research_history"
        assert len(RESEARCH_HISTORY_SCHEMA.columns) == 8
    
    def test_learnings_schema(self):
        """测试学习记录 Schema"""
        assert LEARNINGS_SCHEMA.table_name == "learnings"
        assert len(LEARNINGS_SCHEMA.columns) == 15
        assert len(LEARNINGS_SCHEMA.indexes) == 5  # 添加了 recurrence_count 索引
    
    def test_errors_schema(self):
        """测试错误记录 Schema"""
        assert ERRORS_SCHEMA.table_name == "errors"
        assert len(ERRORS_SCHEMA.columns) == 12
    
    def test_feature_requests_schema(self):
        """测试功能请求 Schema"""
        assert FEATURE_REQUESTS_SCHEMA.table_name == "feature_requests"
        assert len(FEATURE_REQUESTS_SCHEMA.columns) == 9
    
    def test_contradictions_schema(self):
        """测试矛盾记录 Schema"""
        assert CONTRADICTIONS_SCHEMA.table_name == "contradictions"
        assert len(CONTRADICTIONS_SCHEMA.columns) == 13
    
    def test_provenance_schema(self):
        """测试来源追溯 Schema"""
        assert PROVENANCE_SCHEMA.table_name == "provenance"
        assert len(PROVENANCE_SCHEMA.columns) == 9


class TestRegisterAllSchemas:
    """注册所有 Schema 测试"""
    
    def setup_method(self):
        SchemaRegistry.clear()
    
    def test_register_all(self):
        """测试注册所有 Schema"""
        register_all_schemas()
        
        # 应该至少注册了 16 个基础表（survey 等后续扩展可能增加）
        names = SchemaRegistry.get_table_names()
        assert len(names) >= 16, f"Expected at least 16 schemas, got {len(names)}: {names}"
    
    def test_all_core_tables_registered(self):
        """测试核心表都已注册"""
        register_all_schemas()
        
        expected_tables = [
            "entities", "relations", "data_points", "insights",
            "research_history", "requirements", "frameworks",
            "learnings", "errors", "feature_requests",
            "knowledge_versions", "provenance", "contradictions",
            "knowledge_pages", "session_snapshots", "raw_research_data",
        ]
        
        for table in expected_tables:
            assert SchemaRegistry.get(table) is not None, f"Table {table} not registered"
    
    def test_create_all_tables(self):
        """测试创建所有表"""
        import gc
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            
            register_all_schemas()
            SchemaRegistry.create_all(conn)
            
            # 验证所有表都存在
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]
            
            expected = sorted([
                "entities", "relations", "data_points", "insights",
                "research_history", "requirements", "frameworks",
                "learnings", "errors", "feature_requests",
                "knowledge_versions", "provenance", "contradictions",
                "knowledge_pages", "session_snapshots", "raw_research_data",
                "survey_tasks", "survey_responses", "survey_personas",
                "survey_checkpoints",
            ])
            
            assert sorted(tables) == sorted(expected), f"Tables mismatch. Got: {tables}, Expected: {expected}"
            conn.close()
            # Windows 文件锁：关闭连接后强制清理
    
    def test_create_all_with_indexes(self):
        """测试创建所有表和索引"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            
            register_all_schemas()
            SchemaRegistry.create_all(conn)
            
            # 验证索引存在
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            indexes = [row[0] for row in cursor.fetchall()]
            
            # 应该有多个索引
            assert len(indexes) > 0
            
            # 验证关键索引
            assert "idx_entities_type" in indexes
            assert "idx_entities_name_unique" in indexes  # 改为 UNIQUE 索引
            assert "idx_relations_source" in indexes
            assert "idx_learnings_pattern" in indexes
            
            conn.close()
    
    def test_schema_validation(self):
        """测试 Schema 验证"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = sqlite3.connect(str(db_path))
            
            register_all_schemas()
            
            # 未创建表时应该有错误
            errors = SchemaRegistry.validate(conn)
            assert len(errors) >= 16, f"Expected at least 16 validation errors, got {len(errors)}"
            
            # 创建表后应该无错误
            SchemaRegistry.create_all(conn)
            errors = SchemaRegistry.validate(conn)
            assert len(errors) == 0
            
            conn.close()
