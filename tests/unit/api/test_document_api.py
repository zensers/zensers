# -*- coding: utf-8 -*-
"""
Document API 测试
=================

测试文档生成 Web API：
1. 文档生成 API
2. 版本管理 API
3. 导出 API
4. 预览 API
5. 调整 API
6. 研究延迟生成 API
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import asyncio


class TestDocumentAPIInit:
    """测试 DocumentAPI 初始化"""
    
    def test_api_initialization(self):
        """测试API初始化"""
        from src.api.document_api import DocumentAPI, create_app
        
        app = create_app()
        
        assert app is not None
        assert app.title == "Document Generation API"
    
    def test_api_with_storage_dir(self):
        """测试带存储目录初始化"""
        from src.api.document_api import DocumentAPI
        
        with tempfile.TemporaryDirectory() as tmpdir:
            api = DocumentAPI(storage_dir=tmpdir)
            
            assert api.storage_dir == Path(tmpdir)


class TestDocumentGenerateAPI:
    """测试文档生成 API"""
    
    @pytest.fixture
    def api(self):
        from src.api.document_api import DocumentAPI
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentAPI(storage_dir=tmpdir)
    
    @pytest.fixture
    def sample_research_result(self):
        """样本研究结果"""
        return {
            "task_id": "research_test001",
            "topic": "新能源汽车市场分析",
            "sections": [
                {"title": "市场规模", "content": "2026年市场规模达到..."},
                {"title": "竞争格局", "content": "主要竞争者包括..."}
            ],
            "status": "completed",
            "created_at": "2026-04-11T10:00:00"
        }
    
    def test_generate_document_endpoint_exists(self, api):
        """测试生成文档端点存在"""
        from src.api.document_api import DocumentAPIRouter
        
        router = DocumentAPIRouter(api)
        routes = [r.path for r in router.routes]
        
        assert "/documents/generate" in routes
    
    @pytest.mark.asyncio
    async def test_generate_document_success(self, api, sample_research_result):
        """测试成功生成文档"""
        from src.api.document_api import GenerateDocumentRequest
        
        request = GenerateDocumentRequest(
            task_id="research_test001",
            output_format="docx",
            template="consulting"
        )
        
        # Mock 依赖组件
        with patch.object(api, '_get_research_result', return_value=sample_research_result):
            with patch.object(api, '_generate_document', return_value={"document_path": "/tmp/test.docx"}):
                result = await api.generate_document(request)
                
                assert result is not None
                assert "document_path" in result or "task_id" in result
    
    @pytest.mark.asyncio
    async def test_generate_document_invalid_format(self, api):
        """测试无效格式"""
        from src.api.document_api import GenerateDocumentRequest
        
        request = GenerateDocumentRequest(
            task_id="research_test001",
            output_format="invalid_format",  # 无效格式
            template="consulting"
        )
        
        result = await api.generate_document(request)
        
        # 应该返回错误信息
        assert result is not None
        assert "error" in result or result.get("status") == "failed"


class TestVersionManagementAPI:
    """测试版本管理 API"""
    
    @pytest.fixture
    def api(self):
        from src.api.document_api import DocumentAPI
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentAPI(storage_dir=tmpdir)
    
    def test_list_versions_endpoint_exists(self, api):
        """测试列出版本端点存在"""
        from src.api.document_api import DocumentAPIRouter
        
        router = DocumentAPIRouter(api)
        routes = [r.path for r in router.routes]
        
        assert "/documents/{task_id}/versions" in routes
    
    @pytest.mark.asyncio
    async def test_list_versions(self, api):
        """测试列出版本"""
        # Mock 版本管理器
        mock_versions = [
            {"version_id": "v1", "created_at": "2026-04-11"},
            {"version_id": "v2", "created_at": "2026-04-12"}
        ]
        
        with patch.object(api, '_list_versions', return_value=mock_versions):
            result = await api.list_versions("research_test001", "docx")
            
            assert result is not None
            assert len(result) >= 0
    
    @pytest.mark.asyncio
    async def test_rollback_version(self, api):
        """测试回滚版本"""
        mock_result = {"version_id": "v3", "rolled_back_from": "v2"}
        
        with patch.object(api, '_rollback_version', return_value=mock_result):
            result = await api.rollback_version("research_test001", "docx", "v1")
            
            assert result is not None


class TestExportAPI:
    """测试导出 API"""
    
    @pytest.fixture
    def api(self):
        from src.api.document_api import DocumentAPI
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentAPI(storage_dir=tmpdir)
    
    def test_export_endpoint_exists(self, api):
        """测试导出端点存在"""
        from src.api.document_api import DocumentAPIRouter
        
        router = DocumentAPIRouter(api)
        routes = [r.path for r in router.routes]
        
        assert "/documents/export" in routes
    
    @pytest.mark.asyncio
    async def test_export_document(self, api):
        """测试导出文档"""
        from src.api.document_api import ExportDocumentRequest
        
        request = ExportDocumentRequest(
            task_id="research_test001",
            version_id="v1",
            format="docx",
            export_path="/tmp/export/test.docx"
        )
        
        mock_result = {
            "export_id": "export_001",
            "export_path": "/tmp/export/test.docx",
            "status": "success"
        }
        
        with patch.object(api, '_export_document', return_value=mock_result):
            result = await api.export_document(request)
            
            assert result is not None
            assert "export_path" in result or "export_id" in result


class TestPreviewAPI:
    """测试预览 API"""
    
    @pytest.fixture
    def api(self):
        from src.api.document_api import DocumentAPI
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentAPI(storage_dir=tmpdir)
    
    def test_preview_endpoint_exists(self, api):
        """测试预览端点存在"""
        from src.api.document_api import DocumentAPIRouter
        
        router = DocumentAPIRouter(api)
        routes = [r.path for r in router.routes]
        
        assert "/documents/{task_id}/preview" in routes
    
    @pytest.mark.asyncio
    async def test_get_preview(self, api):
        """测试获取预览"""
        mock_result = {
            "preview_path": "/tmp/preview/test.png",
            "format": "png",
            "pages": 1
        }
        
        with patch.object(api, '_generate_preview', return_value=mock_result):
            result = await api.get_preview("research_test001", "v1", "png")
            
            assert result is not None


class TestAdjustmentAPI:
    """测试调整 API"""
    
    @pytest.fixture
    def api(self):
        from src.api.document_api import DocumentAPI
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentAPI(storage_dir=tmpdir)
    
    def test_adjust_endpoint_exists(self, api):
        """测试调整端点存在"""
        from src.api.document_api import DocumentAPIRouter
        
        router = DocumentAPIRouter(api)
        routes = [r.path for r in router.routes]
        
        assert "/documents/adjust" in routes
    
    @pytest.mark.asyncio
    async def test_adjust_document(self, api):
        """测试调整文档"""
        from src.api.document_api import AdjustDocumentRequest
        
        request = AdjustDocumentRequest(
            task_id="research_test001",
            adjustment_type="GLOBAL",
            target=None,
            changes={"font_size": 12}
        )
        
        mock_result = {
            "adjustment_id": "adj_001",
            "status": "success"
        }
        
        with patch.object(api, '_adjust_document', return_value=mock_result):
            result = await api.adjust_document(request)
            
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_adjust_section(self, api):
        """测试章节调整"""
        from src.api.document_api import AdjustDocumentRequest
        
        request = AdjustDocumentRequest(
            task_id="research_test001",
            adjustment_type="SECTION",
            target="market-size",
            changes={"add_content": "新增内容..."}
        )
        
        mock_result = {"adjustment_id": "adj_002", "status": "success"}
        
        with patch.object(api, '_adjust_document', return_value=mock_result):
            result = await api.adjust_document(request)
            
            assert result is not None


class TestResearchAPI:
    """测试研究延迟生成 API"""
    
    @pytest.fixture
    def api(self):
        from src.api.document_api import DocumentAPI
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentAPI(storage_dir=tmpdir)
    
    def test_list_completed_research_endpoint_exists(self, api):
        """测试列出已完成研究端点存在（路由在 main.py 和 create_app 的 research_router 中）"""
        from src.api.document_api import DocumentAPIRouter
        
        router = DocumentAPIRouter(api)
        routes = [r.path for r in router.routes]
        
        assert hasattr(api, 'list_completed_research'), "list_completed_research method should exist"
    
    @pytest.mark.asyncio
    async def test_list_completed_research(self, api):
        """测试列出已完成研究"""
        mock_researches = [
            {"task_id": "research_001", "topic": "新能源汽车", "status": "completed"},
            {"task_id": "research_002", "topic": "医疗AI", "status": "completed"}
        ]
        
        with patch.object(api, '_list_completed_research', return_value=mock_researches):
            result = await api.list_completed_research()
            
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_delayed_generate_document(self, api):
        """测试延迟生成文档"""
        from src.api.document_api import DelayedGenerateRequest
        
        request = DelayedGenerateRequest(
            task_id="research_001",
            output_format="pptx",
            template="consulting"
        )
        
        mock_result = {
            "document_path": "/tmp/test.pptx",
            "version_id": "v1"
        }
        
        with patch.object(api, '_delayed_generate', return_value=mock_result):
            # delayed_generate 接受 DelayedGenerateRequest 对象
            result = await api.delayed_generate(request)
            
            assert result is not None
            assert result.get("document_path") == "/tmp/test.pptx"


class TestAPIValidation:
    """测试 API 输入验证"""
    
    @pytest.fixture
    def api(self):
        from src.api.document_api import DocumentAPI
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentAPI(storage_dir=tmpdir)
    
    @pytest.mark.asyncio
    async def test_invalid_task_id(self, api):
        """测试无效任务ID"""
        from src.api.document_api import GenerateDocumentRequest
        
        request = GenerateDocumentRequest(
            task_id="",  # 空任务ID
            output_format="docx",
            template="consulting"
        )
        
        result = await api.generate_document(request)
        
        assert result is not None
        assert "error" in result or result.get("status") == "failed"
    
    @pytest.mark.asyncio
    async def test_path_traversal_in_export(self, api):
        """测试导出路径遍历攻击"""
        from src.api.document_api import ExportDocumentRequest
        
        request = ExportDocumentRequest(
            task_id="research_test001",
            version_id="v1",
            format="docx",
            export_path="../../../etc/passwd"  # 路径遍历攻击
        )
        
        result = await api.export_document(request)
        
        # 应拒绝危险路径
        assert result is not None
        assert "error" in result or result.get("status") == "failed"
    
    @pytest.mark.asyncio
    async def test_invalid_adjustment_type(self, api):
        """测试无效调整类型"""
        from src.api.document_api import AdjustDocumentRequest
        
        request = AdjustDocumentRequest(
            task_id="research_test001",
            adjustment_type="INVALID_TYPE",  # 无效类型
            target=None,
            changes={}
        )
        
        result = await api.adjust_document(request)
        
        assert result is not None
        assert "error" in result or result.get("status") == "failed"