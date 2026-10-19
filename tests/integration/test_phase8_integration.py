# -*- coding: utf-8 -*-
"""
Phase 8 集成测试
===============

测试新组件与现有系统的集成。
"""

import os
import time
from pathlib import Path

import pytest

from src.core.adjustment import (
    RevisionHandler,
    RevisionRequest,
    RevisionResult,
    SectionLocator,
    ContentApplier,
    RevisionManager,
    AdjustmentHandler,
)
from src.core.workflow import (
    PreviewRevisionWorkflow,
    FeedbackRequest,
    WorkflowStatus,
)


class TestRevisionHandlerIntegration:
    """RevisionHandler 与现有组件集成"""
    
    @pytest.fixture
    def temp_storage(self, tmp_path):
        storage = tmp_path / "revisions"
        storage.mkdir(exist_ok=True)
        return str(storage)
    
    @pytest.fixture
    def sample_report(self, tmp_path):
        content = """# 集成测试报告

## 市场分析

市场分析内容。

## 竞争格局

竞争格局内容。

## 投资建议

投资建议内容。
"""
        file_path = tmp_path / "integration_report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    def test_revision_handler_with_revision_manager(self, sample_report, temp_storage):
        """测试 RevisionHandler 与 RevisionManager 集成"""
        manager = RevisionManager(storage_path=temp_storage)
        handler = RevisionHandler(revision_manager=manager)
        
        # 执行修订
        request = RevisionRequest(
            task_id="integration_task",
            revision_type="section",
            section_title="市场分析",
            user_feedback="更新市场分析",
            target_content="## 市场分析\n\n更新后的市场分析。\n",
        )
        
        result = handler.handle_revision(sample_report, request)
        assert result.success
        
        # 验证 RevisionManager 记录了修订
        history = manager.get_revision_history("integration_task")
        assert len(history) >= 1
        assert history[0].revision_type == "section"
    
    def test_revision_handler_with_section_locator(self, sample_report, temp_storage):
        """测试 RevisionHandler 与 SectionLocator 集成"""
        locator = SectionLocator()
        manager = RevisionManager(storage_path=temp_storage)
        handler = RevisionHandler(
            section_locator=locator,
            revision_manager=manager,
        )
        
        # 通过标题定位并修订
        request = RevisionRequest(
            task_id="locator_task",
            revision_type="section",
            section_title="竞争格局",
            user_feedback="更新竞争格局",
            target_content="## 竞争格局\n\n更新后的竞争格局。\n",
        )
        
        result = handler.handle_revision(sample_report, request)
        assert result.success
        assert result.section_id is not None
    
    def test_revision_handler_with_content_applier(self, sample_report, temp_storage):
        """测试 RevisionHandler 与 ContentApplier 集成"""
        applier = ContentApplier(version_suffix=False)  # 直接覆盖原文件
        manager = RevisionManager(storage_path=temp_storage)
        handler = RevisionHandler(
            content_applier=applier,
            revision_manager=manager,
        )
        
        request = RevisionRequest(
            task_id="applier_task",
            revision_type="section",
            section_title="投资建议",
            user_feedback="更新投资建议",
            target_content="## 投资建议\n\n更新后的投资建议。\n",
        )
        
        result = handler.handle_revision(sample_report, request)
        assert result.success
        assert result.backup_path is not None
        
        # 验证文件已修改
        content = Path(sample_report).read_text(encoding='utf-8')
        assert "更新后的投资建议" in content


class TestWorkflowIntegration:
    """PreviewRevisionWorkflow 与组件集成"""
    
    @pytest.fixture
    def sample_report(self, tmp_path):
        content = "# 工作流集成测试\n\n## 章节1\n\n内容1\n\n## 章节2\n\n内容2\n"
        file_path = tmp_path / "workflow_report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    @pytest.fixture
    def workflow(self, tmp_path):
        storage = tmp_path / "revisions"
        storage.mkdir(exist_ok=True)
        revision_manager = RevisionManager(storage_path=str(storage))
        revision_handler = RevisionHandler(revision_manager=revision_manager)
        return PreviewRevisionWorkflow(revision_handler=revision_handler)
    
    def test_workflow_with_revision_handler(self, workflow, sample_report):
        """测试工作流与 RevisionHandler 集成"""
        state = workflow.start(
            task_id="wf_integration",
            document_path=sample_report,
        )
        
        # 修订
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="section",
            section_title="章节1",
            user_feedback="更新",
            target_content="## 章节1\n\n新内容1\n",
        )
        
        state = workflow.submit_feedback(state.loop_id, feedback)
        assert state.status == WorkflowStatus.WAITING_FEEDBACK
        assert state.last_revision.success is True
        
        # 确认
        feedback = FeedbackRequest(accepted=True)
        state = workflow.submit_feedback(state.loop_id, feedback)
        assert state.status == WorkflowStatus.COMPLETED
    
    def test_workflow_multiple_loops(self, workflow, sample_report):
        """测试多个并行工作流"""
        states = []
        
        # 启动3个工作流
        for i in range(3):
            state = workflow.start(
                task_id=f"parallel_task_{i}",
                document_path=sample_report,
            )
            states.append(state)
        
        # 验证所有工作流独立
        loop_ids = [s.loop_id for s in states]
        assert len(set(loop_ids)) == 3, "工作流ID应该唯一"
        
        # 每个工作流独立修订
        for state in states:
            feedback = FeedbackRequest(
                accepted=False,
                revision_type="minor",
                user_feedback="测试",
            )
            workflow.submit_feedback(state.loop_id, feedback)
        
        # 验证状态独立
        for state in states:
            current = workflow.get_state(state.loop_id)
            assert current.current_round == 1


class TestAdjustmentHandlerIntegration:
    """与现有 AdjustmentHandler 集成"""
    
    @pytest.fixture
    def sample_report(self, tmp_path):
        content = "# 调整集成测试\n\n## 章节1\n\n内容1\n"
        file_path = tmp_path / "adjust_report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    def test_adjustment_handler_coexists(self, sample_report):
        """测试 AdjustmentHandler 与 RevisionHandler 共存"""
        # AdjustmentHandler 使用不同的修订类型
        adjustment_handler = AdjustmentHandler()
        
        # RevisionHandler 使用新的修订类型
        revision_handler = RevisionHandler()
        
        # 两者可以独立工作
        assert adjustment_handler is not None
        assert revision_handler is not None
    
    def test_revision_types_distinct(self):
        """测试修订类型区分"""
        # AdjustmentHandler 类型
        adjustment_types = ['global', 'section', 'element']
        
        # RevisionHandler 类型
        revision_types = ['minor', 'section', 'phase', 'full']
        
        # section 类型重叠，但语义不同
        # AdjustmentHandler.section = 章节级调整
        # RevisionHandler.section = 章节修订
        assert 'section' in adjustment_types
        assert 'section' in revision_types


class TestDocumentAPIIntegration:
    """DocumentAPI 集成测试"""
    
    @pytest.fixture
    def sample_report(self, tmp_path):
        content = "# API集成测试\n\n## 章节1\n\n内容1\n"
        file_path = tmp_path / "api_report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    def test_api_request_models(self):
        """测试 API 请求模型"""
        from src.api.document_api import RevisionRequest as APIRevisionRequest
        
        # 创建请求
        request = APIRevisionRequest(
            task_id="api_task",
            revision_type="section",
            user_feedback="API测试",
            section_title="章节1",
            target_content="新内容",
        )
        
        # 验证
        error = request.validate()
        assert error is None, f"验证应该通过: {error}"
    
    def test_api_revision_loop_request(self):
        """测试 API 修订循环请求"""
        from src.api.document_api import RevisionLoopRequest
        
        request = RevisionLoopRequest(
            task_id="loop_task",
            max_rounds=5,
        )
        
        error = request.validate()
        assert error is None
    
    def test_api_feedback_request(self):
        """测试 API 反馈请求"""
        from src.api.document_api import FeedbackRequest as APIFeedbackRequest
        
        # 确认反馈
        feedback = APIFeedbackRequest(
            loop_id="loop_123",
            accepted=True,
        )
        assert feedback.validate() is None
        
        # 修订反馈
        feedback = APIFeedbackRequest(
            loop_id="loop_123",
            accepted=False,
            revision_type="section",
            section_title="章节1",
            user_feedback="更新",
            target_content="新内容",
        )
        assert feedback.validate() is None


class TestEndToEndIntegration:
    """完整集成流程测试"""
    
    @pytest.fixture
    def full_report(self, tmp_path):
        """创建完整报告"""
        content = """# 完整集成测试报告

## 摘要

本报告用于测试完整的修订闭环流程。

## 市场分析

### 市场规模

2024年市场规模达到1000亿元。

### 增长趋势

年复合增长率25%。

## 竞争分析

### 主要竞争者

公司A、公司B、公司C。

### 市场份额

公司A占40%，公司B占30%，公司C占20%。

## 投资建议

建议关注行业龙头。
"""
        file_path = tmp_path / "full_report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    @pytest.fixture
    def handler(self, tmp_path):
        storage = tmp_path / "revisions"
        storage.mkdir(exist_ok=True)
        return RevisionHandler(
            revision_manager=RevisionManager(storage_path=str(storage))
        )
    
    def test_full_revision_loop(self, handler, full_report):
        """测试完整修订闭环"""
        workflow = PreviewRevisionWorkflow(revision_handler=handler)
        
        # 1. 启动
        state = workflow.start(
            task_id="full_loop_task",
            document_path=full_report,
        )
        
        # 2. 第一轮：章节修订
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="section",
            section_title="市场规模",
            user_feedback="数据过时",
            target_content="### 市场规模\n\n2025年市场规模预计达到1200亿元。\n",
        )
        state = workflow.submit_feedback(state.loop_id, feedback)
        assert state.current_round == 1
        assert state.last_revision.success
        
        # 3. 第二轮：关键词修订
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="section",
            keywords=["公司A", "公司B"],
            user_feedback="更新竞争者信息",
            target_content="### 主要竞争者\n\n公司A、公司B、公司D（公司C已退出）。\n",
        )
        state = workflow.submit_feedback(state.loop_id, feedback)
        assert state.current_round == 2
        
        # 4. 第三轮：微调
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="minor",
            user_feedback="调整格式",
        )
        state = workflow.submit_feedback(state.loop_id, feedback)
        assert state.current_round == 3
        
        # 5. 确认定稿
        feedback = FeedbackRequest(accepted=True)
        state = workflow.submit_feedback(state.loop_id, feedback)
        assert state.status == WorkflowStatus.COMPLETED
        
        # 6. 验证历史
        history = workflow.get_revision_history(state.loop_id)
        assert len(history) == 3
        
        # 7. 验证修订类型分布
        types = [h.revision_type for h in history]
        assert "section" in types
        assert "minor" in types
    
    def test_revision_then_rollback(self, handler, full_report):
        """测试修订后回滚"""
        # 使用直接覆盖原文件的 applier
        applier = ContentApplier(version_suffix=False)
        storage = Path(full_report).parent / "revisions"
        storage.mkdir(exist_ok=True)
        handler = RevisionHandler(
            content_applier=applier,
            revision_manager=RevisionManager(storage_path=str(storage)),
        )
        
        original = Path(full_report).read_text(encoding='utf-8')
        
        # 修订
        request = RevisionRequest(
            task_id="rollback_task",
            revision_type="section",
            section_title="投资建议",
            user_feedback="更新建议",
            target_content="## 投资建议\n\n建议关注新兴企业。\n",
        )
        
        result = handler.handle_revision(full_report, request)
        assert result.success
        
        # 验证修改
        modified = Path(full_report).read_text(encoding='utf-8')
        assert "新兴企业" in modified
        
        # 回滚
        handler.rollback_revision(full_report, result.backup_path)
        
        # 验证恢复
        restored = Path(full_report).read_text(encoding='utf-8')
        assert "行业龙头" in restored
