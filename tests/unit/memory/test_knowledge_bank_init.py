# -*- coding: utf-8 -*-
"""
用户知识银行初始化测试

TDD开发流程：
1. ✅ 写测试
2. 运行测试（预期失败）
3. 写实现
4. 运行测试（预期通过）

Day 1 目标：知识银行初始化
"""

import sqlite3
from pathlib import Path
from datetime import datetime

import pytest

# 注意：这些导入在实现前会失败，这是TDD的正常流程
# from src.core.memory.knowledge_bank import UserKnowledgeBank


class TestUserKnowledgeBankInit:
    """测试知识银行初始化"""
    
    def test_init_creates_database_file(self, tmp_path):
        """初始化时创建数据库文件"""
        # Arrange: 准备临时路径
        db_path = tmp_path / "knowledge.db"
        
        # Act: 创建知识银行
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # Assert: 验证数据库文件存在
        assert db_path.exists()
    
    def test_init_creates_all_tables(self, tmp_path):
        """初始化时创建所有必需的表"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        bank = UserKnowledgeBank("user_001", db_path=str(tmp_path / "test.db"))
        
        # 获取所有表名
        cursor = bank.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        
        # 验证所有表存在
        assert "entities" in tables
        assert "relations" in tables
        assert "data_points" in tables
        assert "insights" in tables
        assert "research_history" in tables
        assert "requirements" in tables
        assert "frameworks" in tables
    
    def test_init_creates_indexes(self, tmp_path):
        """初始化时创建索引"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        bank = UserKnowledgeBank("user_001", db_path=str(tmp_path / "test.db"))
        
        # 获取所有索引
        cursor = bank.db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        
        # 验证关键索引存在
        assert len(indexes) > 0  # 至少有一些索引
    
    def test_init_with_default_path(self, tmp_path):
        """使用默认路径初始化"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        
        # 不指定路径时应该使用默认路径
        bank = UserKnowledgeBank("user_001")
        
        # 验证数据库已创建
        assert bank.db is not None
    
    def test_get_user_id(self, tmp_path):
        """获取用户ID"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        bank = UserKnowledgeBank("user_001", db_path=str(tmp_path / "test.db"))
        
        assert bank.user_id == "user_001"
    
    def test_close_database(self, tmp_path):
        """关闭数据库连接"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        bank = UserKnowledgeBank("user_001", db_path=str(tmp_path / "test.db"))
        
        # 关闭数据库
        bank.close()
        
        # 验证数据库已关闭（尝试操作应该失败）
        with pytest.raises(sqlite3.ProgrammingError):
            bank.db.execute("SELECT 1")


class TestUserKnowledgeBankStores:
    """测试知识银行的子存储"""
    
    def test_entities_store_exists(self, tmp_path):
        """实体存储存在"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        bank = UserKnowledgeBank("user_001", db_path=str(tmp_path / "test.db"))
        
        assert hasattr(bank, 'entities')
        assert bank.entities is not None
    
    def test_relations_store_exists(self, tmp_path):
        """关系存储存在"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        bank = UserKnowledgeBank("user_001", db_path=str(tmp_path / "test.db"))
        
        assert hasattr(bank, 'relations')
        assert bank.relations is not None
    
    def test_data_points_store_exists(self, tmp_path):
        """数据存储存在"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        bank = UserKnowledgeBank("user_001", db_path=str(tmp_path / "test.db"))
        
        assert hasattr(bank, 'data_points')
        assert bank.data_points is not None
    
    def test_insights_store_exists(self, tmp_path):
        """洞察存储存在"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        bank = UserKnowledgeBank("user_001", db_path=str(tmp_path / "test.db"))
        
        assert hasattr(bank, 'insights')
        assert bank.insights is not None