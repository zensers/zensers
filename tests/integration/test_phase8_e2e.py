# -*- coding: utf-8 -*-
"""
Phase 8 端到端测试
================

测试完整的预览-修订闭环流程。
"""

import os
import tempfile
import time
from pathlib import Path

import pytest

from src.core.adjustment import (
    RevisionHandler,
    RevisionRequest,
    SectionLocator,
    ContentApplier,
    RevisionManager,
)
from src.core.workflow import (
    PreviewRevisionWorkflow,
    FeedbackRequest,
    WorkflowStatus,
)


class TestEndToEndRevision:
    """端到端修订流程测试"""
    
    @pytest.fixture
    def temp_storage(self, tmp_path):
        """创建临时存储目录"""
        storage = tmp_path / "revisions"
        storage.mkdir(exist_ok=True)
        return str(storage)
    
    @pytest.fixture
    def sample_report(self, tmp_path):
        """创建示例报告文档"""
        content = """# 新能源汽车行业研究报告

## 摘要

本报告分析了2024年全球新能源汽车市场的发展现状和未来趋势。

## 第一章 市场规模

### 1.1 全球市场

2024年全球新能源汽车销量达到1800万辆，同比增长35%。

### 1.2 中国市场

中国是全球最大的新能源汽车市场，销量达到850万辆。

## 第二章 竞争格局

### 2.1 头部企业

宁德时代、比亚迪、特斯拉位列前三，合计市场份额超过60%。

### 2.2 新进入者

小米、华为等科技企业积极布局新能源汽车领域。

## 第三章 技术趋势

### 3.1 动力电池

固态电池技术取得重大突破，预计2025年开始量产。

### 3.2 智能驾驶

L3级别自动驾驶开始规模化应用。

## 第四章 投资建议

建议关注产业链上游材料和下游应用端的投资机会。

## 结论

新能源汽车行业正处于快速发展期，前景广阔。
"""
        file_path = tmp_path / "report.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    def test_complete_revision_workflow(self, sample_report, temp_storage):
        """测试完整修订工作流"""
        # 1. 初始化组件
        revision_manager = RevisionManager(storage_path=temp_storage)
        handler = RevisionHandler(
            revision_manager=revision_manager,
        )
        
        # 2. 列出章节
        sections = handler.list_sections(sample_report)
        assert len(sections) >= 5, "应该至少有5个章节"
        
        # 3. 定位"市场规模"章节
        location = handler.locate_section(
            sample_report,
            section_title="市场规模"
        )
        assert location is not None, "应该找到市场规模章节"
        assert "市场规模" in location.section_title
        
        # 4. 执行章节修订
        new_content = """## 第一章 市场规模

### 1.1 全球市场

2025年全球新能源汽车销量预计达到2200万辆，同比增长40%。

### 1.2 中国市场

中国继续领跑全球，预计销量突破1000万辆。

### 1.3 欧洲市场

欧洲市场稳步增长，预计销量达到450万辆。
"""
        
        request = RevisionRequest(
            task_id="e2e_task_001",
            revision_type="section",
            section_title="市场规模",
            user_feedback="更新市场数据",
            target_content=new_content,
        )
        
        result = handler.handle_revision(sample_report, request)
        
        assert result.success, f"修订应该成功: {result.error}"
        assert result.revision_type == "section"
        assert result.section_id is not None
        assert result.backup_path is not None
        
        # 5. 验证修订历史
        history = handler.get_revision_history("e2e_task_001")
        assert len(history) >= 1
        
        # 6. 执行第二次修订（关键词定位）
        request2 = RevisionRequest(
            task_id="e2e_task_001",
            revision_type="section",
            keywords=["宁德时代", "比亚迪"],
            user_feedback="更新企业信息",
            target_content="""### 2.1 头部企业

宁德时代、比亚迪和特斯拉稳居前三，合计市场份额超过65%。

其中宁德时代动力电池装机量全球第一。
""",
        )
        
        result2 = handler.handle_revision(sample_report, request2)
        assert result2.success
        
        # 7. 验证修订计数
        count = handler.get_revision_count("e2e_task_001")
        assert count == 2
        
        # 8. 测试回滚
        rollback_success = handler.rollback_revision(
            sample_report,
            result.backup_path
        )
        assert rollback_success
    
    def test_workflow_orchestration(self, sample_report, temp_storage):
        """测试工作流编排"""
        # 1. 创建工作流
        revision_manager = RevisionManager(storage_path=temp_storage)
        revision_handler = RevisionHandler(revision_manager=revision_manager)
        workflow = PreviewRevisionWorkflow(
            revision_handler=revision_handler,
        )
        
        # 2. 启动工作流
        state = workflow.start(
            task_id="workflow_task_001",
            document_path=sample_report,
            max_rounds=5,
        )
        
        assert state.status == WorkflowStatus.IDLE
        assert state.current_round == 0
        
        # 3. 模拟第一轮修订
        feedback = FeedbackRequest(
            accepted=False,
            revision_type="section",
            section_title="竞争格局",
            user_feedback="更新竞争格局数据",
            target_content="""## 第二章 竞争格局

### 2.1 头部企业

行业竞争格局基本稳定，头部企业优势明显。

### 2.2 新进入者

科技企业加速布局，市场竞争加剧。
""",
        )
        
        state = workflow.submit_feedback(state.loop_id, feedback)
        
        assert state.status == WorkflowStatus.WAITING_FEEDBACK
        assert state.current_round == 1
        
        # 4. 模拟第二轮修订
        feedback2 = FeedbackRequest(
            accepted=False,
            revision_type="minor",
            user_feedback="调整格式",
        )
        
        state = workflow.submit_feedback(state.loop_id, feedback2)
        assert state.current_round == 2
        
        # 5. 确认定稿
        feedback3 = FeedbackRequest(accepted=True)
        state = workflow.submit_feedback(state.loop_id, feedback3)
        
        assert state.status == WorkflowStatus.COMPLETED
        
        # 6. 验证历史
        history = workflow.get_revision_history(state.loop_id)
        assert len(history) == 2
    
    def test_revision_limit_enforcement(self, sample_report, temp_storage):
        """测试修订次数限制"""
        revision_manager = RevisionManager(storage_path=temp_storage)
        handler = RevisionHandler(revision_manager=revision_manager)
        
        # 执行超过限制的修订
        max_rounds = 10
        for i in range(max_rounds + 2):
            request = RevisionRequest(
                task_id="limit_task",
                revision_type="minor",
                user_feedback=f"修订 {i}",
            )
            result = handler.handle_revision(sample_report, request)
            
            if i < max_rounds:
                assert result.success, f"第{i+1}次修订应该成功"
            else:
                assert not result.success, f"第{i+1}次修订应该失败"
                assert result.error_code == "LIMIT_EXCEEDED"
    
    def test_multi_format_support(self, tmp_path, temp_storage):
        """测试多格式支持"""
        revision_manager = RevisionManager(storage_path=temp_storage)
        handler = RevisionHandler(revision_manager=revision_manager)
        
        # Markdown
        md_file = tmp_path / "test.md"
        md_file.write_text("# 标题\n\n内容\n", encoding='utf-8')
        
        sections = handler.list_sections(str(md_file))
        assert len(sections) >= 1
        
        # HTML
        html_file = tmp_path / "test.html"
        html_file.write_text("<html><body><h1>标题</h1><p>内容</p></body></html>", encoding='utf-8')
        
        sections = handler.list_sections(str(html_file))
        assert len(sections) >= 1
    
    def test_backup_and_rollback(self, sample_report, temp_storage):
        """测试备份和回滚"""
        revision_manager = RevisionManager(storage_path=temp_storage)
        # 创建不使用版本后缀的 ContentApplier（直接覆盖原文件）
        applier = ContentApplier(version_suffix=False)
        handler = RevisionHandler(
            revision_manager=revision_manager,
            content_applier=applier,
        )
        
        # 读取原始内容
        original_content = Path(sample_report).read_text(encoding='utf-8')
        
        # 执行修订
        request = RevisionRequest(
            task_id="backup_task",
            revision_type="section",
            section_title="摘要",
            user_feedback="更新摘要",
            target_content="## 摘要\n\n这是更新后的摘要内容。\n",
        )
        
        result = handler.handle_revision(sample_report, request)
        assert result.success
        assert result.backup_path is not None
        
        # 验证内容已变更
        modified_content = Path(sample_report).read_text(encoding='utf-8')
        assert "更新后的摘要" in modified_content
        
        # 回滚
        handler.rollback_revision(sample_report, result.backup_path)
        
        # 验证内容已恢复
        restored_content = Path(sample_report).read_text(encoding='utf-8')
        assert "更新后的摘要" not in restored_content
        assert "本报告分析了" in restored_content


class TestRevisionTypes:
    """修订类型测试"""
    
    @pytest.fixture
    def sample_report(self, tmp_path):
        """创建示例报告"""
        content = "# 测试报告\n\n## 章节1\n\n内容1\n\n## 章节2\n\n内容2\n"
        file_path = tmp_path / "test.md"
        file_path.write_text(content, encoding='utf-8')
        return str(file_path)
    
    @pytest.fixture
    def handler(self, tmp_path):
        """创建处理器"""
        storage = tmp_path / "revisions"
        storage.mkdir(exist_ok=True)
        revision_manager = RevisionManager(storage_path=str(storage))
        return RevisionHandler(revision_manager=revision_manager)
    
    def test_minor_revision(self, handler, sample_report):
        """测试微调修订"""
        request = RevisionRequest(
            task_id="minor_task",
            revision_type="minor",
            user_feedback="格式调整",
        )
        
        result = handler.handle_revision(sample_report, request)
        assert result.success
        assert result.revision_type == "minor"
    
    def test_section_revision(self, handler, sample_report):
        """测试章节修订"""
        request = RevisionRequest(
            task_id="section_task",
            revision_type="section",
            section_title="章节1",
            user_feedback="内容更新",
            target_content="## 章节1\n\n新内容1\n",
        )
        
        result = handler.handle_revision(sample_report, request)
        assert result.success
        assert result.revision_type == "section"
    
    def test_phase_revision_with_callback(self, handler, sample_report):
        """测试阶段重做（带回调）"""
        callback_called = []
        
        def mock_callback(task_id, phase_id, user_feedback):
            callback_called.append({
                "task_id": task_id,
                "phase_id": phase_id,
            })
            return {"status": "completed"}
        
        handler.set_phase_redo_callback(mock_callback)
        
        request = RevisionRequest(
            task_id="phase_task",
            revision_type="phase",
            user_feedback="重做分析阶段",
            metadata={"phase_id": "analysis"},
        )
        
        result = handler.handle_revision(sample_report, request)
        assert result.success
        assert len(callback_called) == 1
    
    def test_full_revision_with_callback(self, handler, sample_report):
        """测试全部重做（带回调）"""
        def mock_callback(task_id, user_feedback):
            return {"status": "completed"}
        
        handler.set_full_redo_callback(mock_callback)
        
        request = RevisionRequest(
            task_id="full_task",
            revision_type="full",
            user_feedback="全部重做",
        )
        
        result = handler.handle_revision(sample_report, request)
        assert result.success
        assert result.revision_count == 0  # 全部重做后重置计数
