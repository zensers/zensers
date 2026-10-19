# -*- coding: utf-8 -*-
"""
DocumentModels 测试
===================

测试文档生成数据结构：
1. DocumentFormat 枚举
2. DocumentGenerationRequest 输入验证
3. DocumentGenerationResult 输出结构
"""

import pytest
from datetime import datetime
from typing import Dict, Any, List, Optional

# 待测试的模块（TDD：先写测试，后实现）
# from src.agents.fixed_agents.document_models import (
#     DocumentFormat,
#     DocumentGenerationRequest,
#     DocumentGenerationResult,
#     DocumentVersion,
#     GenerationAction,
# )


class TestDocumentFormat:
    """测试 DocumentFormat 枚举"""
    
    def test_format_values(self):
        """测试格式枚举值"""
        # TDD: 导入后验证
        from src.agents.fixed_agents.document_models import DocumentFormat
        
        assert DocumentFormat.DOCX.value == "docx"
        assert DocumentFormat.PPTX.value == "pptx"
        assert DocumentFormat.PDF.value == "pdf"
        assert DocumentFormat.HTML.value == "html"
    
    def test_format_from_string(self):
        """测试从字符串创建格式"""
        from src.agents.fixed_agents.document_models import DocumentFormat
        
        assert DocumentFormat("docx") == DocumentFormat.DOCX
        assert DocumentFormat("pptx") == DocumentFormat.PPTX
        assert DocumentFormat("pdf") == DocumentFormat.PDF
    
    def test_format_invalid_value_raises(self):
        """测试无效格式值抛出异常"""
        from src.agents.fixed_agents.document_models import DocumentFormat
        
        with pytest.raises(ValueError):
            DocumentFormat("invalid_format")


class TestGenerationAction:
    """测试 GenerationAction 枚举"""
    
    def test_action_values(self):
        """测试动作枚举值"""
        from src.agents.fixed_agents.document_models import GenerationAction
        
        assert GenerationAction.PRODUCE_DOCUMENT.value == "produce_document"
        assert GenerationAction.REGENERATE_DOCUMENT.value == "regenerate_document"
        assert GenerationAction.ADJUST_CONTENT.value == "adjust_content"
        assert GenerationAction.EXPORT_DOCUMENT.value == "export_document"
        assert GenerationAction.GET_PREVIEW.value == "get_preview"
        assert GenerationAction.LIST_VERSIONS.value == "list_versions"
        assert GenerationAction.ROLLBACK_VERSION.value == "rollback_version"
        assert GenerationAction.COMPARE_VERSIONS.value == "compare_versions"


class TestDocumentGenerationRequest:
    """测试 DocumentGenerationRequest 输入验证"""
    
    def test_create_request_with_research_result(self):
        """测试使用研究结果创建请求"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationRequest,
            GenerationAction,
            DocumentFormat
        )
        
        request = DocumentGenerationRequest(
            action=GenerationAction.PRODUCE_DOCUMENT,
            research_result={
                "title": "新能源汽车市场研究",
                "topic": "新能源汽车",
                "sections": [{"id": "s1", "title": "市场规模", "content": "..."}]
            },
            output_format=DocumentFormat.PPTX,
            template="consulting"
        )
        
        assert request.action == GenerationAction.PRODUCE_DOCUMENT
        assert request.output_format == DocumentFormat.PPTX
        assert request.template == "consulting"
        assert request.research_result["title"] == "新能源汽车市场研究"
    
    def test_create_request_with_task_id(self):
        """测试使用历史任务ID创建请求（延迟生成）"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationRequest,
            GenerationAction,
            DocumentFormat
        )
        
        request = DocumentGenerationRequest(
            action=GenerationAction.PRODUCE_DOCUMENT,
            task_id="research_abc123",
            output_format=DocumentFormat.DOCX
        )
        
        assert request.task_id == "research_abc123"
        assert request.research_result is None
    
    def test_request_to_dict(self):
        """测试请求转字典"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationRequest,
            GenerationAction,
            DocumentFormat
        )
        
        request = DocumentGenerationRequest(
            action=GenerationAction.PRODUCE_DOCUMENT,
            task_id="test_001",
            output_format=DocumentFormat.DOCX,
            template="standard"
        )
        
        data = request.to_dict()
        
        assert data["action"] == "produce_document"
        assert data["task_id"] == "test_001"
        assert data["output_format"] == "docx"
        assert data["template"] == "standard"
    
    def test_request_from_dict(self):
        """测试从字典创建请求"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationRequest,
            GenerationAction,
            DocumentFormat
        )
        
        data = {
            "action": "produce_document",
            "task_id": "test_002",
            "output_format": "pptx",
            "template": "consulting"
        }
        
        request = DocumentGenerationRequest.from_dict(data)
        
        assert request.action == GenerationAction.PRODUCE_DOCUMENT
        assert request.output_format == DocumentFormat.PPTX
    
    def test_request_validation_missing_action(self):
        """测试缺少action字段验证"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationRequest,
            ValidationError
        )
        
        with pytest.raises(ValidationError):
            DocumentGenerationRequest.from_dict({
                "task_id": "test_001",
                "output_format": "docx"
            })
    
    def test_request_validation_missing_format(self):
        """测试缺少output_format字段验证"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationRequest,
            GenerationAction,
            ValidationError
        )
        
        with pytest.raises(ValidationError):
            DocumentGenerationRequest.from_dict({
                "action": "produce_document",
                "task_id": "test_001"
            })
    
    def test_request_validation_invalid_format(self):
        """测试无效格式验证"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationRequest,
            GenerationAction,
            ValidationError
        )
        
        with pytest.raises(ValidationError):
            DocumentGenerationRequest.from_dict({
                "action": "produce_document",
                "output_format": "invalid"
            })


class TestDocumentGenerationResult:
    """测试 DocumentGenerationResult 输出结构"""
    
    def test_create_success_result(self):
        """测试创建成功结果"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationResult,
            DocumentFormat
        )
        
        result = DocumentGenerationResult(
            success=True,
            task_id="test_001",
            output_format=DocumentFormat.DOCX,
            document_path="/output/test_001_report.docx",
            version_id="v1",
            file_size=102400,
            pages_estimate=10
        )
        
        assert result.success is True
        assert result.version_id == "v1"
        assert result.file_size == 102400
    
    def test_create_failure_result(self):
        """测试创建失败结果"""
        from src.agents.fixed_agents.document_models import DocumentGenerationResult
        
        result = DocumentGenerationResult(
            success=False,
            error="转换失败：缺少必要模板",
            error_code="TEMPLATE_MISSING"
        )
        
        assert result.success is False
        assert result.error == "转换失败：缺少必要模板"
        assert result.document_path is None
    
    def test_result_to_dict(self):
        """测试结果转字典"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationResult,
            DocumentFormat
        )
        
        result = DocumentGenerationResult(
            success=True,
            task_id="test_001",
            output_format=DocumentFormat.PPTX,
            document_path="/output/test.pptx",
            version_id="v1"
        )
        
        data = result.to_dict()
        
        assert data["success"] is True
        assert data["task_id"] == "test_001"
        assert data["output_format"] == "pptx"
        assert "version_id" in data


class TestDocumentVersion:
    """测试 DocumentVersion 版本结构"""
    
    def test_create_version(self):
        """测试创建版本"""
        from src.agents.fixed_agents.document_models import (
            DocumentVersion,
            DocumentFormat
        )
        
        version = DocumentVersion(
            version_id="v1",
            format=DocumentFormat.DOCX,
            file_path="/documents/test_001/docx/v1_report.docx",
            file_size=102400,
            created_at=datetime.now(),
            created_by="initial"
        )
        
        assert version.version_id == "v1"
        assert version.format == DocumentFormat.DOCX
        assert version.created_by == "initial"
    
    def test_version_with_parent(self):
        """测试带父版本的版本"""
        from src.agents.fixed_agents.document_models import (
            DocumentVersion,
            DocumentFormat
        )
        
        version = DocumentVersion(
            version_id="v2",
            format=DocumentFormat.DOCX,
            file_path="/documents/test_001/docx/v2_report.docx",
            file_size=108000,
            created_at=datetime.now(),
            created_by="regenerate",
            parent_version="v1",
            change_summary="增加市场趋势分析章节"
        )
        
        assert version.parent_version == "v1"
        assert version.change_summary == "增加市场趋势分析章节"
    
    def test_version_to_dict(self):
        """测试版本转字典"""
        from src.agents.fixed_agents.document_models import (
            DocumentVersion,
            DocumentFormat
        )
        
        version = DocumentVersion(
            version_id="v1",
            format=DocumentFormat.PPTX,
            file_path="/output/v1.pptx",
            file_size=50000,
            created_at=datetime.now(),
            created_by="initial"
        )
        
        data = version.to_dict()
        
        assert data["version_id"] == "v1"
        assert data["format"] == "pptx"
        assert "created_at" in data


class TestModelEdgeCases:
    """测试边界条件"""
    
    def test_empty_research_result(self):
        """测试空研究结果"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationRequest,
            GenerationAction,
            DocumentFormat
        )
        
        # 空研究结果应该被接受（后续处理时验证）
        request = DocumentGenerationRequest(
            action=GenerationAction.PRODUCE_DOCUMENT,
            research_result={},
            output_format=DocumentFormat.DOCX
        )
        
        assert request.research_result == {}
    
    def test_unicode_in_request(self):
        """测试Unicode内容"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationRequest,
            GenerationAction,
            DocumentFormat
        )
        
        request = DocumentGenerationRequest(
            action=GenerationAction.PRODUCE_DOCUMENT,
            research_result={
                "title": "日本語タイトル",
                "topic": "中文主题"
            },
            output_format=DocumentFormat.DOCX
        )
        
        assert request.research_result["title"] == "日本語タイトル"
    
    def test_large_adjustments_list(self):
        """测试大量调整项"""
        from src.agents.fixed_agents.document_models import (
            DocumentGenerationRequest,
            GenerationAction,
            DocumentFormat
        )
        
        adjustments = [{"type": "style", "value": f"change_{i}"} for i in range(50)]
        
        request = DocumentGenerationRequest(
            action=GenerationAction.ADJUST_CONTENT,
            task_id="test_001",
            output_format=DocumentFormat.DOCX,
            adjustments=adjustments
        )
        
        assert len(request.adjustments) == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])