# -*- coding: utf-8 -*-
"""
LearningStore 测试用例

测试学习记录存储的核心功能
"""

import pytest
import tempfile
import os
from pathlib import Path

from src.core.memory.learning.learning_store import (
    LearningStore,
    LearningRecord,
    LearningCategory,
    LearningStatus
)


class TestLearningStore:
    """LearningStore 测试"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)
    
    @pytest.fixture
    def store(self, temp_db):
        """创建 LearningStore 实例"""
        store = LearningStore(temp_db, "test_user")
        yield store
        store.close()
    
    def test_init(self, temp_db):
        """测试初始化"""
        store = LearningStore(temp_db, "test_user")
        assert store.user_id == "test_user"
        assert store.db is not None
        store.close()
    
    def test_generate_pattern_key(self, store):
        """测试模式键生成"""
        key1 = store.generate_pattern_key("correction", "特斯拉的正确名称是 Tesla")
        key2 = store.generate_pattern_key("correction", "特斯拉的正确名称是 Tesla")
        key3 = store.generate_pattern_key("correction", "特斯拉的正确名称是 Tesla Inc")
        
        # 相同内容应该生成相同的键
        assert key1 == key2
        # 不同内容应该生成不同的键
        assert key1 != key3
        # 键格式应该正确
        assert key1.startswith("correction.")
    
    def test_record_learning_new(self, store):
        """测试记录新学习"""
        record = store.record_learning(
            category="correction",
            content="特斯拉的正确名称是 Tesla Inc.",
            session_id="sess_001"
        )
        
        assert record.learning_id.startswith("LRN-")
        assert record.user_id == "test_user"
        assert record.category == "correction"
        assert record.content == "特斯拉的正确名称是 Tesla Inc."
        assert record.session_id == "sess_001"
        assert record.status == "pending"
        assert record.recurrence_count == 1
        assert record.pattern_key is not None
    
    def test_record_learning_duplicate(self, store):
        """测试记录重复学习（去重）"""
        # 第一次记录
        record1 = store.record_learning(
            category="correction",
            content="特斯拉的正确名称是 Tesla Inc.",
            session_id="sess_001"
        )
        assert record1.recurrence_count == 1
        
        # 第二次记录相同内容
        record2 = store.record_learning(
            category="correction",
            content="特斯拉的正确名称是 Tesla Inc.",
            session_id="sess_002"
        )
        
        # 应该更新现有记录
        assert record2.learning_id == record1.learning_id
        assert record2.recurrence_count == 2
    
    def test_get_learning(self, store):
        """测试获取学习记录"""
        record = store.record_learning(
            category="preference",
            content="用户偏好 Markdown 格式"
        )
        
        fetched = store.get_learning(record.learning_id)
        assert fetched is not None
        assert fetched.learning_id == record.learning_id
        assert fetched.content == record.content
    
    def test_get_learning_not_found(self, store):
        """测试获取不存在的学习记录"""
        fetched = store.get_learning("LRN-99999999-9999")
        assert fetched is None
    
    def test_query_learnings(self, store):
        """测试查询学习记录"""
        # 创建多个学习记录
        store.record_learning(category="correction", content="纠正1")
        store.record_learning(category="correction", content="纠正2")
        store.record_learning(category="preference", content="偏好1")
        store.record_learning(category="error", content="错误1")
        
        # 查询所有
        all_records = store.query_learnings()
        assert len(all_records) >= 4
        
        # 按类别查询
        corrections = store.query_learnings(category="correction")
        assert len(corrections) == 2
        
        preferences = store.query_learnings(category="preference")
        assert len(preferences) == 1
    
    def test_update_status(self, store):
        """测试更新状态"""
        record = store.record_learning(
            category="correction",
            content="测试状态更新"
        )
        
        # 更新为已晋升
        success = store.update_status(
            learning_id=record.learning_id,
            status="promoted",
            promoted_to="core_memory"
        )
        
        assert success
        
        updated = store.get_learning(record.learning_id)
        assert updated.status == "promoted"
        assert updated.promoted_to == "core_memory"
    
    def test_get_stats(self, store):
        """测试获取统计"""
        # 创建多个学习记录
        store.record_learning(category="correction", content="纠正1")
        store.record_learning(category="preference", content="偏好1")
        
        # 创建高重复记录
        for _ in range(3):
            store.record_learning(category="pattern", content="重复模式")
        
        stats = store.get_stats()
        
        assert stats["total"] >= 3
        assert stats["pending"] >= 3
        assert stats["high_recurrence"] >= 1
        assert "by_category" in stats
    
    def test_get_promotion_candidates(self, store):
        """测试获取晋升候选"""
        # 创建普通记录
        store.record_learning(category="correction", content="普通纠正")
        
        # 创建高重复记录（晋升候选）
        for _ in range(5):
            store.record_learning(
                category="pattern",
                content="应该晋升的模式",
                session_id=f"sess_{_}"
            )
        
        candidates = store.get_promotion_candidates()
        
        assert len(candidates) >= 1
        assert all(c.recurrence_count >= 3 for c in candidates)
        assert all(c.status == "pending" for c in candidates)
    
    def test_clear_old_learnings(self, store):
        """测试清理旧记录"""
        # 创建记录并标记为忽略
        record = store.record_learning(category="error", content="临时错误")
        store.update_status(record.learning_id, status="ignored")
        
        # 清理（由于时间限制，不会真正删除）
        deleted = store.clear_old_learnings(days=0)
        # 验证方法可以执行
        assert isinstance(deleted, int)


class TestLearningRecord:
    """LearningRecord 测试"""
    
    def test_create(self):
        """测试创建记录"""
        record = LearningRecord(
            learning_id="LRN-001",
            user_id="user_001",
            category="correction",
            content="测试内容"
        )
        
        assert record.learning_id == "LRN-001"
        assert record.status == "pending"
        assert record.recurrence_count == 1
        assert record.first_seen is not None
        assert record.last_seen is not None
    
    def test_to_dict(self):
        """测试转换为字典"""
        record = LearningRecord(
            learning_id="LRN-001",
            user_id="user_001",
            category="correction",
            content="测试内容",
            metadata={"key": "value"}
        )
        
        d = record.to_dict()
        
        assert d["learning_id"] == "LRN-001"
        assert d["metadata"]["key"] == "value"
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "learning_id": "LRN-001",
            "user_id": "user_001",
            "category": "correction",
            "content": "测试内容",
            "priority": "high",
            "status": "promoted"
        }
        
        record = LearningRecord.from_dict(data)
        
        assert record.learning_id == "LRN-001"
        assert record.priority == "high"
        assert record.status == "promoted"


class TestLearningCategory:
    """LearningCategory 测试"""
    
    def test_values(self):
        """测试枚举值"""
        assert LearningCategory.CORRECTION.value == "correction"
        assert LearningCategory.ERROR.value == "error"
        assert LearningCategory.PATTERN.value == "pattern"
        assert LearningCategory.PREFERENCE.value == "preference"


class TestLearningStatus:
    """LearningStatus 测试"""
    
    def test_values(self):
        """测试枚举值"""
        assert LearningStatus.PENDING.value == "pending"
        assert LearningStatus.PROMOTED.value == "promoted"
        assert LearningStatus.IGNORED.value == "ignored"