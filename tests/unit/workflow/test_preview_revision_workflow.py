# -*- coding: utf-8 -*-
"""
PreviewRevisionWorkflow 单元测试
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.core.workflow.preview_revision_workflow import (
    FeedbackRequest,
    PreviewRevisionWorkflow,
    WorkflowState,
    WorkflowStatus,
)
from src.core.adjustment.revision_handler import RevisionHandler
from src.core.preview.preview_generator import PreviewGenerator


class TestFeedbackRequest:
    """FeedbackRequest 测试"""
    
    def test_accepted_feedback(self):
        """测试确认反馈"""
        feedback = FeedbackRequest(accepted=True)
        
        assert feedback.accepted is True
        assert feedback.revision_type is None
        assert feedback.user_feedback is None
    
    def test_revision_feedback(self):
        """测试修订反馈"""
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="section",
            section_title="市场规模",
            user_feedback="数据需要更新",
            target_content="新内容...",
        )
        
        assert feedback.accepted is False
        assert feedback.revision_type == "section"
        assert feedback.section_title == "市场规模"
        assert feedback.target_content == "新内容..."


class TestWorkflowState:
    """WorkflowState 测试"""
    
    def test_creation(self):
        """测试创建"""
        state = WorkflowState(
            loop_id="loop_123",
            task_id="task_456",
            document_path="/path/to/doc.md",
        )
        
        assert state.loop_id == "loop_123"
        assert state.status == WorkflowStatus.IDLE
        assert state.current_round == 0
        assert len(state.revision_history) == 0
    
    def test_to_dict(self):
        """测试序列化"""
        state = WorkflowState(
            loop_id="loop_123",
            task_id="task_456",
            document_path="/path/to/doc.md",
            status=WorkflowStatus.WAITING_FEEDBACK,
            current_round=2,
        )
        
        data = state.to_dict()
        
        assert data["loop_id"] == "loop_123"
        assert data["status"] == "waiting_feedback"
        assert data["current_round"] == 2


class TestPreviewRevisionWorkflow:
    """PreviewRevisionWorkflow 测试"""
    
    @pytest.fixture
    def workflow(self):
        """创建工作流"""
        return PreviewRevisionWorkflow()
    
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

宁德时代和比亚迪占据主导地位。

## 技术趋势

固态电池和智能驾驶是主要方向。
"""
        file_path = tmp_path / "test_report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    def test_creation(self, workflow):
        """测试创建"""
        assert workflow.preview_generator is not None
        assert workflow.revision_handler is not None
    
    def test_start_workflow(self, workflow, markdown_file):
        """测试启动工作流"""
        state = workflow.start(
            task_id="task_123",
            document_path=markdown_file,
        )
        
        assert state.loop_id is not None
        assert state.task_id == "task_123"
        assert state.status == WorkflowStatus.IDLE
        assert state.current_round == 0
    
    def test_get_state(self, workflow, markdown_file):
        """测试获取状态"""
        state = workflow.start(
            task_id="task_123",
            document_path=markdown_file,
        )
        
        retrieved = workflow.get_state(state.loop_id)
        
        assert retrieved is not None
        assert retrieved.loop_id == state.loop_id
    
    def test_get_state_nonexistent(self, workflow):
        """测试获取不存在的工作流"""
        state = workflow.get_state("nonexistent_loop")
        assert state is None
    
    def test_generate_preview(self, workflow, markdown_file):
        """测试生成预览"""
        state = workflow.start(
            task_id="task_123",
            document_path=markdown_file,
        )
        
        result = workflow.generate_preview(state.loop_id)
        
        # 预览生成可能失败（如果依赖不存在），但状态应该更新
        updated_state = workflow.get_state(state.loop_id)
        assert updated_state.status in [
            WorkflowStatus.WAITING_FEEDBACK,
            WorkflowStatus.FAILED,
        ]
    
    def test_generate_preview_nonexistent_workflow(self, workflow):
        """测试不存在的工作流生成预览"""
        result = workflow.generate_preview("nonexistent_loop")
        
        assert result.success is False
        assert result.error_code == "WORKFLOW_NOT_FOUND"
    
    def test_submit_feedback_accept(self, workflow, markdown_file):
        """测试确认反馈"""
        state = workflow.start(
            task_id="task_123",
            document_path=markdown_file,
        )
        
        feedback = FeedbackRequest(accepted=True)
        updated = workflow.submit_feedback(state.loop_id, feedback)
        
        assert updated.status == WorkflowStatus.COMPLETED
    
    def test_submit_feedback_revision(self, workflow, markdown_file):
        """测试修订反馈"""
        state = workflow.start(
            task_id="task_123",
            document_path=markdown_file,
        )
        
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="minor",
            user_feedback="调整格式",
        )
        
        updated = workflow.submit_feedback(state.loop_id, feedback)
        
        assert updated.current_round == 1
        assert updated.last_revision is not None
        assert updated.status == WorkflowStatus.WAITING_FEEDBACK
    
    def test_submit_feedback_section_revision(self, workflow, markdown_file):
        """测试章节修订反馈"""
        state = workflow.start(
            task_id="task_123",
            document_path=markdown_file,
        )
        
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="section",
            section_title="市场规模",
            user_feedback="更新数据",
            target_content="## 市场规模\n\n新内容\n",
        )
        
        updated = workflow.submit_feedback(state.loop_id, feedback)
        
        assert updated.current_round == 1
        assert updated.last_revision.success is True
        assert updated.last_revision.revision_type == "section"
    
    def test_submit_feedback_max_rounds(self, workflow, markdown_file):
        """测试达到最大修订轮次"""
        state = workflow.start(
            task_id="task_123",
            document_path=markdown_file,
            max_rounds=2,
        )
        
        # 第一次修订
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="minor",
            user_feedback="测试1",
        )
        updated = workflow.submit_feedback(state.loop_id, feedback)
        assert updated.current_round == 1
        
        # 第二次修订
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="minor",
            user_feedback="测试2",
        )
        updated = workflow.submit_feedback(state.loop_id, feedback)
        assert updated.current_round == 2
        
        # 第三次应该失败
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="minor",
            user_feedback="测试3",
        )
        updated = workflow.submit_feedback(state.loop_id, feedback)
        assert updated.status == WorkflowStatus.FAILED
        assert "Maximum revision rounds" in updated.error
    
    def test_submit_feedback_nonexistent_workflow(self, workflow):
        """测试不存在的工作流提交反馈"""
        feedback = FeedbackRequest(accepted=True)
        
        with pytest.raises(ValueError):
            workflow.submit_feedback("nonexistent_loop", feedback)
    
    def test_confirm(self, workflow, markdown_file):
        """测试确认"""
        state = workflow.start(
            task_id="task_123",
            document_path=markdown_file,
        )
        
        confirmed = workflow.confirm(state.loop_id)
        
        assert confirmed.status == WorkflowStatus.COMPLETED
    
    def test_confirm_nonexistent_workflow(self, workflow):
        """测试不存在的工作流确认"""
        with pytest.raises(ValueError):
            workflow.confirm("nonexistent_loop")
    
    def test_cancel(self, workflow, markdown_file):
        """测试取消"""
        state = workflow.start(
            task_id="task_123",
            document_path=markdown_file,
        )
        
        cancelled = workflow.cancel(state.loop_id)
        
        assert cancelled.status == WorkflowStatus.CANCELLED
    
    def test_cancel_nonexistent_workflow(self, workflow):
        """测试不存在的工作流取消"""
        with pytest.raises(ValueError):
            workflow.cancel("nonexistent_loop")
    
    def test_get_revision_history(self, workflow, markdown_file):
        """测试获取修订历史"""
        state = workflow.start(
            task_id="task_123",
            document_path=markdown_file,
        )
        
        # 执行两次修订
        for i in range(2):
            feedback = FeedbackRequest(
                accepted=False,
                revision_type="minor",
                user_feedback=f"测试{i}",
            )
            workflow.submit_feedback(state.loop_id, feedback)
        
        history = workflow.get_revision_history(state.loop_id)
        
        assert len(history) == 2
    
    def test_list_active_workflows(self, workflow, markdown_file):
        """测试列出活跃工作流"""
        # 创建多个工作流
        state1 = workflow.start(task_id="task_1", document_path=markdown_file)
        state2 = workflow.start(task_id="task_2", document_path=markdown_file)
        
        # 确认一个
        workflow.confirm(state1.loop_id)
        
        active = workflow.list_active_workflows()
        
        assert len(active) == 1
        assert active[0].loop_id == state2.loop_id
    
    def test_cleanup_completed(self, workflow, markdown_file):
        """测试清理已完成工作流"""
        from datetime import datetime, timedelta
        
        # 创建并完成工作流
        state1 = workflow.start(task_id="task_1", document_path=markdown_file)
        workflow.confirm(state1.loop_id)
        
        # 设置更新时间为过去
        old_time = datetime.now() - timedelta(hours=25)
        workflow._workflows[state1.loop_id].updated_at = old_time
        
        # 创建活跃工作流
        state2 = workflow.start(task_id="task_2", document_path=markdown_file)
        
        # 清理
        cleaned = workflow.cleanup_completed(max_age_hours=24)
        
        assert cleaned == 1
        assert workflow.get_state(state1.loop_id) is None
        assert workflow.get_state(state2.loop_id) is not None


class TestWorkflowStatus:
    """WorkflowStatus 测试"""
    
    def test_status_values(self):
        """测试状态值"""
        assert WorkflowStatus.IDLE == "idle"
        assert WorkflowStatus.PREVIEWING == "previewing"
        assert WorkflowStatus.WAITING_FEEDBACK == "waiting_feedback"
        assert WorkflowStatus.REVISING == "revising"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.CANCELLED == "cancelled"
        assert WorkflowStatus.FAILED == "failed"


class TestWorkflowIntegration:
    """工作流集成测试"""
    
    @pytest.fixture
    def workflow(self):
        """创建工作流"""
        return PreviewRevisionWorkflow()
    
    @pytest.fixture
    def markdown_file(self, tmp_path):
        """创建测试 Markdown 文件"""
        content = """# 测试报告

## 第一章

内容1

## 第二章

内容2
"""
        file_path = tmp_path / "report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    def test_full_revision_loop(self, workflow, markdown_file):
        """测试完整修订循环"""
        # 1. 启动
        state = workflow.start(
            task_id="task_integration",
            document_path=markdown_file,
        )
        assert state.status == WorkflowStatus.IDLE
        
        # 2. 生成预览
        preview = workflow.generate_preview(state.loop_id)
        state = workflow.get_state(state.loop_id)
        assert state.status in [WorkflowStatus.WAITING_FEEDBACK, WorkflowStatus.FAILED]
        
        # 3. 第一次修订
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="section",
            section_title="第一章",
            user_feedback="更新内容",
            target_content="## 第一章\n\n新内容1\n",
        )
        state = workflow.submit_feedback(state.loop_id, feedback)
        assert state.current_round == 1
        assert state.last_revision.success is True
        
        # 4. 第二次修订
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="section",
            section_title="第二章",
            user_feedback="更新内容",
            target_content="## 第二章\n\n新内容2\n",
        )
        state = workflow.submit_feedback(state.loop_id, feedback)
        assert state.current_round == 2
        
        # 5. 确认定稿
        feedback = FeedbackRequest(accepted=True)
        state = workflow.submit_feedback(state.loop_id, feedback)
        assert state.status == WorkflowStatus.COMPLETED
        
        # 6. 检查历史
        history = workflow.get_revision_history(state.loop_id)
        assert len(history) == 2
