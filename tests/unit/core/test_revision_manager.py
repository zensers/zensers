# -*- coding: utf-8 -*-
"""
修订历史管理器测试
================

测试 RevisionManager 的核心功能。
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.core.adjustment.revision_manager import (
    RevisionRecord,
    RevisionDiff,
    RevisionManager,
    MAX_REVISIONS_PER_TASK,
)


class TestRevisionRecord:
    """测试 RevisionRecord 数据类"""
    
    def test_create_revision_record(self):
        """测试创建修订记录"""
        record = RevisionRecord(
            revision_id="rev_abc123",
            task_id="task_xyz",
            version_id="v1",
            revision_type="section",
            section="竞争格局",
            adjustment="补充宁德时代数据",
        )
        
        assert record.revision_id == "rev_abc123"
        assert record.task_id == "task_xyz"
        assert record.revision_type == "section"
        assert record.section == "竞争格局"
    
    def test_revision_record_to_dict(self):
        """测试序列化"""
        record = RevisionRecord(
            revision_id="rev_test",
            task_id="task_test",
            version_id="v1",
            revision_type="minor",
            adjustment="测试调整",
        )
        
        data = record.to_dict()
        
        assert data["revision_id"] == "rev_test"
        assert data["task_id"] == "task_test"
        assert data["revision_type"] == "minor"
        assert "created_at" in data
    
    def test_revision_record_from_dict(self):
        """测试反序列化"""
        data = {
            "revision_id": "rev_test",
            "task_id": "task_test",
            "version_id": "v2",
            "revision_type": "section",
            "section": "市场规模",
            "adjustment": "更新数据",
            "created_at": "2024-01-15T10:30:00",
        }
        
        record = RevisionRecord.from_dict(data)
        
        assert record.revision_id == "rev_test"
        assert record.version_id == "v2"
        assert record.section == "市场规模"


class TestRevisionDiff:
    """测试 RevisionDiff 数据类"""
    
    def test_create_revision_diff(self):
        """测试创建差异记录"""
        diff = RevisionDiff(
            revision_id="rev1_vs_rev2",
            section="竞争格局",
            changes=[
                {"type": "content_change", "original": "old", "revised": "new"}
            ],
            summary="1处差异",
        )
        
        assert diff.revision_id == "rev1_vs_rev2"
        assert len(diff.changes) == 1
    
    def test_revision_diff_to_dict(self):
        """测试差异序列化"""
        diff = RevisionDiff(
            revision_id="diff_test",
            section="测试章节",
            changes=[],
            summary="无差异",
        )
        
        data = diff.to_dict()
        
        assert data["revision_id"] == "diff_test"
        assert data["summary"] == "无差异"


class TestRevisionManager:
    """测试 RevisionManager"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def manager(self, temp_storage):
        """创建修订管理器"""
        return RevisionManager(storage_path=temp_storage)
    
    def test_manager_creation(self, manager):
        """测试管理器创建"""
        assert manager is not None
        assert len(manager._revisions) == 0
    
    def test_create_revision(self, manager):
        """测试创建修订记录"""
        record = manager.create_revision(
            task_id="task_001",
            revision_type="section",
            section="竞争格局",
            adjustment="补充宁德时代数据",
        )
        
        assert record.revision_id.startswith("rev_")
        assert record.task_id == "task_001"
        assert record.version_id == "v1"
        assert record.section == "竞争格局"
    
    def test_create_multiple_revisions(self, manager):
        """测试创建多个修订"""
        for i in range(3):
            record = manager.create_revision(
                task_id="task_002",
                revision_type="minor",
                adjustment=f"调整{i+1}",
            )
            assert record.version_id == f"v{i+1}"
    
    def test_get_revision(self, manager):
        """测试获取修订记录"""
        created = manager.create_revision(
            task_id="task_003",
            revision_type="minor",
            adjustment="测试",
        )
        
        retrieved = manager.get_revision(created.revision_id)
        
        assert retrieved is not None
        assert retrieved.revision_id == created.revision_id
    
    def test_get_nonexistent_revision(self, manager):
        """测试获取不存在的修订"""
        result = manager.get_revision("nonexistent")
        assert result is None
    
    def test_get_revision_history(self, manager):
        """测试获取修订历史"""
        # 创建多个修订
        for i in range(5):
            manager.create_revision(
                task_id="task_004",
                revision_type="minor",
                adjustment=f"调整{i+1}",
            )
        
        history = manager.get_revision_history("task_004")
        
        assert len(history) == 5
        # 验证按时间倒序
        assert history[0].version_id == "v5"
    
    def test_get_revision_history_with_limit(self, manager):
        """测试限制历史记录数量"""
        for i in range(10):
            manager.create_revision(
                task_id="task_005",
                revision_type="minor",
                adjustment=f"调整{i+1}",
            )
        
        history = manager.get_revision_history("task_005", limit=3)
        
        assert len(history) == 3
    
    def test_get_latest_revision(self, manager):
        """测试获取最新修订"""
        manager.create_revision(
            task_id="task_006",
            revision_type="minor",
            adjustment="调整1",
        )
        latest = manager.create_revision(
            task_id="task_006",
            revision_type="minor",
            adjustment="调整2",
        )
        
        result = manager.get_latest_revision("task_006")
        
        assert result is not None
        assert result.revision_id == latest.revision_id
    
    def test_compare_revisions(self, manager):
        """测试对比修订"""
        record1 = manager.create_revision(
            task_id="task_007",
            revision_type="section",
            section="市场规模",
            adjustment="原始调整",
            original_content="原始内容",
            revised_content="修订内容1",
        )
        
        record2 = manager.create_revision(
            task_id="task_007",
            revision_type="section",
            section="市场规模",
            adjustment="再次调整",
            original_content="修订内容1",
            revised_content="修订内容2",
        )
        
        diff = manager.compare_revisions(record1.revision_id, record2.revision_id)
        
        assert diff is not None
        assert len(diff.changes) > 0
    
    def test_compare_nonexistent_revisions(self, manager):
        """测试对比不存在的修订"""
        with pytest.raises(ValueError):
            manager.compare_revisions("nonexistent1", "nonexistent2")
    
    def test_rollback_to_revision(self, manager):
        """测试回滚到指定修订"""
        original = manager.create_revision(
            task_id="task_008",
            revision_type="minor",
            adjustment="原始版本",
        )
        
        manager.create_revision(
            task_id="task_008",
            revision_type="minor",
            adjustment="第二次修订",
        )
        
        rollback = manager.rollback_to_revision("task_008", original.revision_id)
        
        assert rollback.revision_type == "rollback"
        assert "回滚" in rollback.adjustment
    
    def test_rollback_wrong_task(self, manager):
        """测试回滚错误任务"""
        record = manager.create_revision(
            task_id="task_009",
            revision_type="minor",
            adjustment="测试",
        )
        
        with pytest.raises(ValueError):
            manager.rollback_to_revision("wrong_task", record.revision_id)
    
    def test_get_revision_stats(self, manager):
        """测试获取修订统计"""
        manager.create_revision(
            task_id="task_010",
            revision_type="minor",
            adjustment="微调1",
        )
        manager.create_revision(
            task_id="task_010",
            revision_type="section",
            adjustment="章节修订",
        )
        manager.create_revision(
            task_id="task_010",
            revision_type="minor",
            adjustment="微调2",
        )
        
        stats = manager.get_revision_stats("task_010")
        
        assert stats["total_revisions"] == 3
        assert stats["type_counts"]["minor"] == 2
        assert stats["type_counts"]["section"] == 1
    
    def test_clear_task_revisions(self, manager, temp_storage):
        """测试清理任务修订"""
        manager.create_revision(
            task_id="task_011",
            revision_type="minor",
            adjustment="测试1",
        )
        manager.create_revision(
            task_id="task_011",
            revision_type="minor",
            adjustment="测试2",
        )
        
        count = manager.clear_task_revisions("task_011")
        
        assert count == 2
        assert len(manager.get_revision_history("task_011")) == 0
    
    def test_invalid_task_id(self, manager):
        """测试无效的task_id"""
        with pytest.raises(ValueError):
            manager.create_revision(
                task_id="invalid task id!",
                revision_type="minor",
                adjustment="测试",
            )
    
    def test_invalid_revision_type(self, manager):
        """测试无效的修订类型"""
        with pytest.raises(ValueError):
            manager.create_revision(
                task_id="task_012",
                revision_type="invalid_type",
                adjustment="测试",
            )
    
    def test_revision_persistence(self, temp_storage):
        """测试修订持久化"""
        # 创建管理器并添加修订
        manager1 = RevisionManager(storage_path=temp_storage)
        record = manager1.create_revision(
            task_id="task_013",
            revision_type="minor",
            adjustment="持久化测试",
        )
        
        # 创建新管理器（模拟重启）
        manager2 = RevisionManager(storage_path=temp_storage)
        
        # 验证修订已加载
        retrieved = manager2.get_revision(record.revision_id)
        assert retrieved is not None
        assert retrieved.adjustment == "持久化测试"
    
    def test_max_revisions_limit(self, manager):
        """测试修订次数限制"""
        # 创建接近限制数量的修订
        for i in range(MAX_REVISIONS_PER_TASK):
            manager.create_revision(
                task_id="task_014",
                revision_type="minor",
                adjustment=f"调整{i+1}",
            )
        
        # 尝试创建超出限制的修订
        with pytest.raises(RuntimeError) as exc_info:
            manager.create_revision(
                task_id="task_014",
                revision_type="minor",
                adjustment="超出限制",
            )
        
        assert "max revisions limit" in str(exc_info.value)


class TestRevisionTypes:
    """测试不同修订类型"""
    
    @pytest.fixture
    def manager(self):
        """创建修订管理器"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield RevisionManager(storage_path=tmpdir)
    
    def test_minor_revision(self, manager):
        """测试微调类型"""
        record = manager.create_revision(
            task_id="task_minor",
            revision_type="minor",
            section="格式调整",
            adjustment="调整字体大小",
        )
        
        assert record.revision_type == "minor"
    
    def test_section_revision(self, manager):
        """测试章节修订类型"""
        record = manager.create_revision(
            task_id="task_section",
            revision_type="section",
            section="竞争格局",
            adjustment="重写竞争格局章节",
            original_content="原始内容...",
            revised_content="修订内容...",
        )
        
        assert record.revision_type == "section"
        assert record.section == "竞争格局"
    
    def test_phase_revision(self, manager):
        """测试阶段重做类型"""
        record = manager.create_revision(
            task_id="task_phase",
            revision_type="phase",
            adjustment="重新分析数据",
        )
        
        assert record.revision_type == "phase"
    
    def test_full_revision(self, manager):
        """测试全部重做类型"""
        record = manager.create_revision(
            task_id="task_full",
            revision_type="full",
            adjustment="重新生成整个报告",
        )
        
        assert record.revision_type == "full"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
