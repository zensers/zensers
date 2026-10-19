# -*- coding: utf-8 -*-
"""
LearningManager 测试用例
"""

import pytest
import tempfile
import os

from src.core.memory.learning.learning_store import LearningStore
from src.core.memory.learning.learning_manager import LearningManager


class MockCoreMemory:
    """模拟 CoreMemory"""
    
    def __init__(self):
        self.core_learnings = []
    
    def add_core_learning(self, learning: dict):
        self.core_learnings.append(learning)


class TestLearningManager:
    """LearningManager 测试"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)
    
    @pytest.fixture
    def learning_store(self, temp_db):
        """创建 LearningStore 实例"""
        store = LearningStore(temp_db, "test_user")
        yield store
        store.close()
    
    @pytest.fixture
    def core_memory(self):
        """创建模拟 CoreMemory"""
        return MockCoreMemory()
    
    @pytest.fixture
    def manager(self, learning_store, core_memory):
        """创建 LearningManager 实例"""
        return LearningManager(learning_store, core_memory)
    
    def test_init(self, learning_store):
        """测试初始化"""
        manager = LearningManager(learning_store)
        assert manager.learning_store is not None
        assert manager.PROMOTION_THRESHOLD == 3
        assert manager.MIN_SESSIONS == 2
    
    def test_check_promotion_eligible_low_recurrence(self, manager, learning_store):
        """测试晋升条件检查 - 低重复次数"""
        record = learning_store.record_learning(
            category="correction",
            content="低重复记录",
            session_id="sess_001"
        )
        
        assert not manager.check_promotion_eligible(record)
    
    def test_check_promotion_eligible_high_recurrence(self, manager, learning_store):
        """测试晋升条件检查 - 高重复次数"""
        # 创建高重复记录
        for i in range(5):
            learning_store.record_learning(
                category="pattern",
                content="应该晋升的模式",
                session_id=f"sess_{i}"
            )
        
        # 获取记录
        records = learning_store.query_learnings(min_recurrence=3)
        record = records[0]
        
        # 应该符合晋升条件
        assert manager.check_promotion_eligible(record)
    
    def test_get_promotion_candidates(self, manager, learning_store):
        """测试获取晋升候选"""
        # 创建普通记录
        learning_store.record_learning(
            category="correction",
            content="普通纠正"
        )
        
        # 创建晋升候选
        for i in range(5):
            learning_store.record_learning(
                category="pattern",
                content="晋升候选模式",
                session_id=f"sess_{i}"
            )
        
        candidates = manager.get_promotion_candidates()
        
        assert len(candidates) >= 1
        assert all(c.recurrence_count >= 3 for c in candidates)
    
    def test_promote_learning(self, manager, learning_store, core_memory):
        """测试晋升学习"""
        # 创建高重复记录
        for i in range(5):
            learning_store.record_learning(
                category="preference",
                content="稳定偏好",
                session_id=f"sess_{i}"
            )
        
        records = learning_store.query_learnings(min_recurrence=3)
        record = records[0]
        
        # 晋升
        success = manager.promote_learning(record, promote_to_core_memory=True)
        
        assert success
        
        # 验证状态更新
        updated = learning_store.get_learning(record.learning_id)
        assert updated.status == "promoted"
        
        # 验证 CoreMemory 更新
        assert len(core_memory.core_learnings) == 1
    
    def test_auto_promote(self, manager, learning_store, core_memory):
        """测试自动晋升"""
        # 创建多个晋升候选
        for pattern_idx in range(2):
            for i in range(5):
                learning_store.record_learning(
                    category="pattern",
                    content=f"模式_{pattern_idx}",
                    session_id=f"sess_{pattern_idx}_{i}"
                )
        
        promoted = manager.auto_promote()
        
        assert len(promoted) >= 1
        assert len(core_memory.core_learnings) >= 1
    
    def test_get_learning_summary(self, manager, learning_store):
        """测试获取学习摘要"""
        # 创建一些记录
        learning_store.record_learning(category="correction", content="纠正1")
        
        for i in range(3):
            learning_store.record_learning(
                category="pattern",
                content="重复模式",
                session_id=f"sess_{i}"
            )
        
        summary = manager.get_learning_summary()
        
        assert "stats" in summary
        assert "promotion_candidates" in summary
        assert "candidates_by_category" in summary
    
    def test_process_user_feedback(self, manager, learning_store):
        """测试处理用户反馈"""
        record = manager.process_user_feedback(
            feedback_type="correction",
            content="用户纠正：特斯拉的正确名称是 Tesla Inc.",
            session_id="sess_001"
        )
        
        assert record.category == "correction"
        assert record.content == "用户纠正：特斯拉的正确名称是 Tesla Inc."
        assert record.session_id == "sess_001"
    
    def test_get_recommended_actions(self, manager, learning_store):
        """测试获取推荐行动"""
        # 创建高重复记录
        for i in range(5):
            learning_store.record_learning(
                category="error",
                content="重复错误",
                session_id=f"sess_{i}"
            )
        
        actions = manager.get_recommended_actions()
        
        assert isinstance(actions, list)
        # 应该有推荐行动
        assert len(actions) >= 1
    
    def test_manager_without_core_memory(self, learning_store):
        """测试没有 CoreMemory 的情况"""
        manager = LearningManager(learning_store, core_memory=None)
        
        # 创建高重复记录
        for i in range(5):
            learning_store.record_learning(
                category="pattern",
                content="测试模式",
                session_id=f"sess_{i}"
            )
        
        records = learning_store.query_learnings(min_recurrence=3)
        record = records[0]
        
        # 晋升应该成功（只更新状态）
        success = manager.promote_learning(record, promote_to_core_memory=False)
        assert success