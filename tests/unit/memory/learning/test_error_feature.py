# -*- coding: utf-8 -*-
"""
ErrorTracker 和 FeatureRequestStore 测试用例
"""

import pytest
import tempfile
import os

from src.core.memory.learning.error_tracker import (
    ErrorTracker,
    ErrorRecord,
    ErrorSeverity
)
from src.core.memory.learning.feature_request_store import (
    FeatureRequestStore,
    FeatureRequest,
    RequestStatus,
    RequestComplexity
)


class TestErrorTracker:
    """ErrorTracker 测试"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)
    
    @pytest.fixture
    def tracker(self, temp_db):
        """创建 ErrorTracker 实例"""
        tracker = ErrorTracker(temp_db, "test_user")
        yield tracker
        tracker.close()
    
    def test_init(self, temp_db):
        """测试初始化"""
        tracker = ErrorTracker(temp_db, "test_user")
        assert tracker.user_id == "test_user"
        tracker.close()
    
    def test_record_error(self, tracker):
        """测试记录错误"""
        record = tracker.record_error(
            error_type="ImportError",
            error_message="无法导入模块 xyz",
            session_id="sess_001",
            severity="high"
        )
        
        assert record.error_id.startswith("ERR-")
        assert record.error_type == "ImportError"
        assert record.error_message == "无法导入模块 xyz"
        assert record.severity == "high"
        assert not record.resolved
    
    def test_get_error(self, tracker):
        """测试获取错误"""
        record = tracker.record_error(
            error_type="ValueError",
            error_message="无效参数"
        )
        
        fetched = tracker.get_error(record.error_id)
        assert fetched is not None
        assert fetched.error_id == record.error_id
    
    def test_resolve_error(self, tracker):
        """测试解决错误"""
        record = tracker.record_error(
            error_type="TypeError",
            error_message="类型错误"
        )
        
        success = tracker.resolve_error(
            error_id=record.error_id,
            resolution="修复了类型检查",
            learning_id="LRN-001"
        )
        
        assert success
        
        resolved = tracker.get_error(record.error_id)
        assert resolved.resolved
        assert resolved.resolution == "修复了类型检查"
        assert resolved.learning_id == "LRN-001"
    
    def test_query_errors(self, tracker):
        """测试查询错误"""
        tracker.record_error(error_type="Error1", error_message="错误1")
        tracker.record_error(error_type="Error2", error_message="错误2", severity="high")
        
        all_errors = tracker.query_errors()
        assert len(all_errors) >= 2
        
        high_errors = tracker.query_errors(severity="high")
        assert len(high_errors) >= 1
    
    def test_get_stats(self, tracker):
        """测试获取统计"""
        tracker.record_error(error_type="Error1", error_message="错误1")
        tracker.record_error(error_type="Error2", error_message="错误2", severity="critical")
        
        stats = tracker.get_stats()
        
        assert stats["total"] >= 2
        assert stats["unresolved"] >= 2
        assert stats["critical"] >= 1


class TestFeatureRequestStore:
    """FeatureRequestStore 测试"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)
    
    @pytest.fixture
    def store(self, temp_db):
        """创建 FeatureRequestStore 实例"""
        store = FeatureRequestStore(temp_db, "test_user")
        yield store
        store.close()
    
    def test_init(self, temp_db):
        """测试初始化"""
        store = FeatureRequestStore(temp_db, "test_user")
        assert store.user_id == "test_user"
        store.close()
    
    def test_record_request_new(self, store):
        """测试记录新请求"""
        request = store.record_request(
            capability="支持 PDF 导出",
            user_context="用户需要导出研究报告为 PDF 格式",
            complexity="medium",
            priority="high"
        )
        
        assert request.request_id.startswith("REQ-")
        assert request.capability == "支持 PDF 导出"
        assert request.status == "pending"
        assert request.frequency == "first_time"
    
    def test_record_request_recurring(self, store):
        """测试记录重复请求"""
        # 第一次请求
        request1 = store.record_request(
            capability="支持 PDF 导出",
            session_id="sess_001"
        )
        assert request1.frequency == "first_time"
        
        # 第二次相同请求
        request2 = store.record_request(
            capability="支持 PDF 导出",
            session_id="sess_002"
        )
        
        # 应该标记为 recurring
        assert request2.request_id == request1.request_id
        assert request2.frequency == "recurring"
    
    def test_get_request(self, store):
        """测试获取请求"""
        request = store.record_request(
            capability="新增功能",
            user_context="测试上下文"
        )
        
        fetched = store.get_request(request.request_id)
        assert fetched is not None
        assert fetched.capability == "新增功能"
    
    def test_update_status(self, store):
        """测试更新状态"""
        request = store.record_request(
            capability="待审批功能",
            priority="high"
        )
        
        success = store.update_status(
            request_id=request.request_id,
            status="approved",
            notes="已批准开发"
        )
        
        assert success
        
        updated = store.get_request(request.request_id)
        assert updated.status == "approved"
        assert updated.notes == "已批准开发"
    
    def test_query_requests(self, store):
        """测试查询请求"""
        store.record_request(capability="功能1", priority="high")
        store.record_request(capability="功能2", priority="low")
        
        # 更新状态
        requests = store.query_requests(status="pending")
        assert len(requests) >= 2
        
        high_priority = store.query_requests(priority="high")
        assert len(high_priority) >= 1
    
    def test_get_stats(self, store):
        """测试获取统计"""
        store.record_request(capability="功能1")
        store.record_request(capability="功能2", priority="high")
        
        stats = store.get_stats()
        
        assert stats["total"] >= 2
        assert stats["pending"] >= 2
        assert "by_priority" in stats


class TestEnums:
    """枚举测试"""
    
    def test_error_severity(self):
        """测试错误严重程度枚举"""
        assert ErrorSeverity.LOW.value == "low"
        assert ErrorSeverity.MEDIUM.value == "medium"
        assert ErrorSeverity.HIGH.value == "high"
        assert ErrorSeverity.CRITICAL.value == "critical"
    
    def test_request_status(self):
        """测试请求状态枚举"""
        assert RequestStatus.PENDING.value == "pending"
        assert RequestStatus.APPROVED.value == "approved"
        assert RequestStatus.COMPLETED.value == "completed"
    
    def test_request_complexity(self):
        """测试请求复杂度枚举"""
        assert RequestComplexity.LOW.value == "low"
        assert RequestComplexity.HIGH.value == "high"