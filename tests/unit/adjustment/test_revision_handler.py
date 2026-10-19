# -*- coding: utf-8 -*-
"""
RevisionHandler 单元测试
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.core.adjustment.revision_handler import (
    RevisionHandler,
    RevisionRequest,
    RevisionResult,
    RevisionStatus,
)
from src.core.adjustment.revision_manager import RevisionManager
from src.core.adjustment.section_locator import SectionLocator
from src.core.adjustment.content_applier import ContentApplier


class TestRevisionRequest:
    """RevisionRequest 测试"""
    
    def test_creation(self):
        """测试创建"""
        request = RevisionRequest(
            task_id="task_123",
            revision_type="section",
            user_feedback="需要更新数据",
        )
        
        assert request.task_id == "task_123"
        assert request.revision_type == "section"
        assert request.user_feedback == "需要更新数据"
        assert request.section_id is None
        assert request.metadata == {}
    
    def test_to_dict(self):
        """测试序列化"""
        request = RevisionRequest(
            task_id="task_123",
            revision_type="section",
            user_feedback="测试",
            section_id="section_1",
            keywords=["关键词"],
        )
        
        data = request.to_dict()
        
        assert data["task_id"] == "task_123"
        assert data["revision_type"] == "section"
        assert data["section_id"] == "section_1"
        assert data["keywords"] == ["关键词"]


class TestRevisionResult:
    """RevisionResult 测试"""
    
    def test_success_result(self):
        """测试成功结果"""
        result = RevisionResult(
            success=True,
            revision_id="rev_123",
            revision_type="section",
            document_path="/path/to/doc.md",
            section_id="section_1",
            changes=[{"type": "replace"}],
        )
        
        assert result.success is True
        assert result.revision_id == "rev_123"
        assert result.error is None
    
    def test_failure_result(self):
        """测试失败结果"""
        result = RevisionResult(
            success=False,
            error="Section not found",
            error_code="SECTION_NOT_FOUND",
        )
        
        assert result.success is False
        assert result.error == "Section not found"
        assert result.error_code == "SECTION_NOT_FOUND"
    
    def test_to_dict(self):
        """测试序列化"""
        result = RevisionResult(
            success=True,
            revision_id="rev_123",
            revision_count=3,
        )
        
        data = result.to_dict()
        
        assert data["success"] is True
        assert data["revision_id"] == "rev_123"
        assert data["revision_count"] == 3


class TestRevisionHandler:
    """RevisionHandler 测试"""
    
    @pytest.fixture
    def handler(self, tmp_path):
        """创建处理器（使用临时目录隔离）"""
        from src.core.adjustment.revision_manager import RevisionManager
        from src.core.adjustment.section_locator import SectionLocator
        from src.core.adjustment.content_applier import ContentApplier
        
        # 使用临时目录创建隔离的 RevisionManager
        storage_dir = tmp_path / "revisions"
        storage_dir.mkdir(exist_ok=True)
        revision_manager = RevisionManager(storage_path=str(storage_dir))
        
        return RevisionHandler(
            revision_manager=revision_manager,
            section_locator=SectionLocator(),
            content_applier=ContentApplier(),
        )
    
    @pytest.fixture
    def temp_dir(self, tmp_path):
        """创建临时目录"""
        return tmp_path
    
    @pytest.fixture
    def markdown_file(self, tmp_path):
        """创建测试 Markdown 文件"""
        content = """# 新能源汽车行业研究

## 市场规模

2024年全球新能源汽车销量达到1800万辆。

## 竞争格局

### 头部企业

宁德时代和比亚迪占据主导地位。

### 新进入者

小米和华为等科技企业进入市场。

## 技术趋势

固态电池和智能驾驶是主要方向。
"""
        file_path = tmp_path / "test_report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    def test_creation(self, handler):
        """测试创建"""
        assert handler.section_locator is not None
        assert handler.content_applier is not None
        assert handler.revision_manager is not None
    
    def test_revision_count(self, handler):
        """测试修订计数"""
        task_id = "task_123"
        
        assert handler.get_revision_count(task_id) == 0
        
        handler._increment_revision_count(task_id)
        assert handler.get_revision_count(task_id) == 1
        
        handler._increment_revision_count(task_id)
        assert handler.get_revision_count(task_id) == 2
        
        handler.reset_revision_count(task_id)
        assert handler.get_revision_count(task_id) == 0
    
    def test_invalid_revision_type(self, handler, markdown_file):
        """测试无效修订类型"""
        request = RevisionRequest(
            task_id="task_123",
            revision_type="invalid_type",
            user_feedback="测试",
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is False
        assert result.error_code == "INVALID_TYPE"
    
    def test_document_not_found(self, handler):
        """测试文档不存在"""
        request = RevisionRequest(
            task_id="task_123",
            revision_type="section",
            user_feedback="测试",
        )
        
        result = handler.handle_revision("/nonexistent/path.md", request)
        
        assert result.success is False
        assert result.error_code == "DOCUMENT_NOT_FOUND"
    
    def test_revision_limit(self, handler, markdown_file):
        """测试修订次数限制"""
        # 设置修订计数到上限
        from src.core.adjustment.revision_handler import MAX_REVISION_ROUNDS
        handler._revision_counts["task_123"] = MAX_REVISION_ROUNDS
        
        request = RevisionRequest(
            task_id="task_123",
            revision_type="section",
            user_feedback="测试",
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is False
        assert result.error_code == "LIMIT_EXCEEDED"
    
    def test_handle_minor_revision(self, handler, markdown_file):
        """测试微调修订"""
        request = RevisionRequest(
            task_id="task_123",
            revision_type="minor",
            user_feedback="调整格式",
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is True
        assert result.revision_type == "minor"
        assert handler.get_revision_count("task_123") == 1
    
    def test_handle_section_revision_by_title(self, handler, markdown_file):
        """测试章节修订（按标题）"""
        request = RevisionRequest(
            task_id="task_123",
            revision_type="section",
            section_title="市场规模",
            user_feedback="更新数据",
            target_content="""## 市场规模

2025年全球新能源汽车销量预计达到2200万辆，同比增长22%。
""",
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is True
        assert result.revision_type == "section"
        assert result.section_id is not None
        assert result.backup_path is not None
    
    def test_handle_section_revision_by_keywords(self, handler, markdown_file):
        """测试章节修订（按关键词）"""
        request = RevisionRequest(
            task_id="task_123",
            revision_type="section",
            keywords=["宁德时代", "比亚迪"],
            user_feedback="更新企业信息",
            target_content="""### 头部企业

宁德时代、比亚迪和特斯拉位列前三，合计市场份额超过60%。
""",
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is True
        assert result.section_id is not None
    
    def test_handle_section_revision_not_found(self, handler, markdown_file):
        """测试章节修订（章节未找到）"""
        request = RevisionRequest(
            task_id="task_123",
            revision_type="section",
            section_title="不存在的章节",
            user_feedback="测试",
            target_content="新内容",
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is False
        assert result.error_code == "SECTION_NOT_FOUND"
    
    def test_handle_section_revision_missing_content(self, handler, markdown_file):
        """测试章节修订（缺少内容）"""
        request = RevisionRequest(
            task_id="task_123",
            revision_type="section",
            section_title="市场规模",
            user_feedback="测试",
            # 没有 target_content
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is False
        assert result.error_code == "MISSING_CONTENT"
    
    def test_handle_phase_revision_no_callback(self, handler, markdown_file):
        """测试阶段重做（无回调）"""
        request = RevisionRequest(
            task_id="task_123",
            revision_type="phase",
            user_feedback="重做分析阶段",
            metadata={"phase_id": "analysis"},
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is False
        assert result.error_code == "CALLBACK_NOT_SET"
    
    def test_handle_phase_revision_with_callback(self, handler, markdown_file):
        """测试阶段重做（有回调）"""
        # 设置回调
        def mock_callback(task_id, phase_id, user_feedback):
            return {"status": "completed", "phase_id": phase_id}
        
        handler.set_phase_redo_callback(mock_callback)
        
        request = RevisionRequest(
            task_id="task_123",
            revision_type="phase",
            user_feedback="重做分析阶段",
            metadata={"phase_id": "analysis"},
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is True
        assert result.revision_type == "phase"
    
    def test_handle_phase_revision_missing_phase_id(self, handler, markdown_file):
        """测试阶段重做（缺少 phase_id）"""
        def mock_callback(task_id, phase_id, user_feedback):
            return {"status": "completed"}
        
        handler.set_phase_redo_callback(mock_callback)
        
        request = RevisionRequest(
            task_id="task_123",
            revision_type="phase",
            user_feedback="重做",
            # 没有 phase_id
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is False
        assert result.error_code == "MISSING_PHASE_ID"
    
    def test_handle_full_revision_no_callback(self, handler, markdown_file):
        """测试全部重做（无回调）"""
        request = RevisionRequest(
            task_id="task_123",
            revision_type="full",
            user_feedback="全部重做",
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is False
        assert result.error_code == "CALLBACK_NOT_SET"
    
    def test_handle_full_revision_with_callback(self, handler, markdown_file):
        """测试全部重做（有回调）"""
        def mock_callback(task_id, user_feedback):
            return {"status": "completed"}
        
        handler.set_full_redo_callback(mock_callback)
        
        # 先设置一些修订计数
        handler._revision_counts["task_123"] = 5
        
        request = RevisionRequest(
            task_id="task_123",
            revision_type="full",
            user_feedback="全部重做",
        )
        
        result = handler.handle_revision(markdown_file, request)
        
        assert result.success is True
        assert result.revision_type == "full"
        assert result.revision_count == 0  # 应该被重置
        assert handler.get_revision_count("task_123") == 0
    
    def test_list_sections(self, handler, markdown_file):
        """测试列出章节"""
        sections = handler.list_sections(markdown_file)
        
        assert len(sections) >= 4  # 至少4个章节
        titles = [s.section_title for s in sections]
        assert "市场规模" in titles
        assert "竞争格局" in titles
    
    def test_locate_section(self, handler, markdown_file):
        """测试定位章节"""
        section = handler.locate_section(
            markdown_file,
            section_title="市场规模",
        )
        
        assert section is not None
        assert "市场规模" in section.section_title
    
    def test_get_revision_history(self, handler, markdown_file):
        """测试获取修订历史"""
        # 执行一次修订
        request = RevisionRequest(
            task_id="task_123",
            revision_type="minor",
            user_feedback="测试",
        )
        handler.handle_revision(markdown_file, request)
        
        # 获取历史
        history = handler.get_revision_history("task_123")
        
        assert len(history) >= 1
        assert history[0].revision_type == "minor"
    
    def test_rollback_revision(self, handler, markdown_file):
        """测试回滚修订"""
        # 先执行一次修订
        request = RevisionRequest(
            task_id="task_123",
            revision_type="section",
            section_title="市场规模",
            user_feedback="测试",
            target_content="## 市场规模\n\n新内容\n",
        )
        
        result = handler.handle_revision(markdown_file, request)
        assert result.success is True
        assert result.backup_path is not None
        
        # 回滚
        rollback_success = handler.rollback_revision(
            markdown_file,
            result.backup_path,
        )
        
        assert rollback_success is True
    
    def test_rollback_nonexistent_backup(self, handler, markdown_file):
        """测试回滚不存在的备份"""
        success = handler.rollback_revision(
            markdown_file,
            "/nonexistent/backup.md",
        )
        
        assert success is False


class TestRevisionStatus:
    """RevisionStatus 测试"""
    
    def test_status_values(self):
        """测试状态值"""
        assert RevisionStatus.PENDING == "pending"
        assert RevisionStatus.IN_PROGRESS == "in_progress"
        assert RevisionStatus.COMPLETED == "completed"
        assert RevisionStatus.FAILED == "failed"
        assert RevisionStatus.CANCELLED == "cancelled"
