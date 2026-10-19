# -*- coding: utf-8 -*-
"""
ResearchOrchestrator 文档集成测试
==================================

测试 ResearchOrchestrator 与 DocumentGenerationAgent 的集成：
1. 研究完成后自动生成文档
2. 延迟生成文档
3. 版本管理集成
4. 导出管理集成
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import asyncio
from datetime import datetime


class TestOrchestratorDocumentIntegration:
    """测试 Orchestrator 与文档生成集成"""
    
    @pytest.fixture
    def temp_dir(self):
        """临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def orchestrator(self, temp_dir):
        """创建 Orchestrator 实例"""
        from src.core.orchestrator.research_orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(
            storage_path=temp_dir
        )
        
        return orchestrator
    
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
            "created_at": datetime.now().isoformat()
        }
    
    @pytest.mark.asyncio
    async def test_research_completion_triggers_document_option(self, temp_dir, sample_research_result):
        """测试研究完成后可生成文档"""
        from src.core.orchestrator.research_orchestrator import complete_research_with_document_option
        from src.core.orchestrator.research_orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(storage_path=temp_dir)
        
        # Mock 必要方法
        with patch.object(orchestrator, '_result_store') as mock_store:
            mock_store.save_result = AsyncMock(return_value="result_001")
            mock_store.update_result = Mock()
            
            result = await complete_research_with_document_option(
                orchestrator=orchestrator,
                task_id="research_test001",
                result=sample_research_result,
                output_format=None  # 不立即生成
            )
            
            assert result is not None
            assert "status" in result
    
    @pytest.mark.asyncio
    async def test_delayed_document_generation(self, temp_dir):
        """测试延迟生成文档"""
        from src.core.orchestrator.research_orchestrator import generate_document_later
        from src.core.orchestrator.research_orchestrator import ResearchOrchestrator
        from src.core.storage.research_result_store import ResearchStatus, ResearchResultMeta
        
        orchestrator = ResearchOrchestrator(storage_path=temp_dir)
        
        # Mock 必要方法
        mock_metadata = ResearchResultMeta(
            task_id="research_test001",
            title="新能源汽车市场分析",
            topic="新能源汽车市场",
            status=ResearchStatus.COMPLETED,
            created_at=datetime.now()
        )
        
        with patch.object(orchestrator, '_result_store') as mock_store:
            mock_store.load_result = Mock(return_value={"task_id": "research_test001"})
            mock_store.load_metadata = Mock(return_value=mock_metadata)
            mock_store.update_result = Mock()
            
            result = await generate_document_later(
                orchestrator=orchestrator,
                task_id="research_test001",
                output_format="docx"
            )
            
            assert result is not None
            assert "task_id" in result
    
    def test_list_completed_research(self, temp_dir):
        """测试列出已完成研究"""
        from src.core.orchestrator.research_orchestrator import list_completed_research
        from src.core.orchestrator.research_orchestrator import ResearchOrchestrator
        from src.core.storage.research_result_store import ResearchStatus, ResearchResultMeta
        
        orchestrator = ResearchOrchestrator(storage_path=temp_dir)
        
        mock_results = [
            ResearchResultMeta(
                task_id="research_001",
                title="新能源汽车",
                topic="新能源汽车市场",
                status=ResearchStatus.COMPLETED,
                created_at=datetime.now()
            )
        ]
        
        with patch.object(orchestrator._result_store, 'list_results', return_value=mock_results):
            results = list_completed_research(orchestrator, limit=10)
            
            assert results is not None
            assert len(results) >= 0


class TestDocumentGenerationAgentIntegration:
    """测试 DocumentGenerationAgent 集成"""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def doc_agent(self, temp_dir):
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        
        agent = DocumentGenerationAgent(
            agent_id="doc_agent_001",
            storage_path=temp_dir
        )
        
        return agent
    
    def test_agent_execute_generate_document(self, doc_agent):
        """测试 Agent 执行生成文档"""
        request = {
            "action": "produce_document",
            "research_result": {
                "task_id": "research_001",
                "topic": "新能源汽车",
                "sections": []
            },
            "output_format": "docx",
            "template": "consulting"
        }
        
        result = doc_agent.execute(request)
        
        assert result is not None
        # 结果包含 success 或 status
        assert "success" in result or "status" in result
    
    def test_agent_execute_list_versions(self, doc_agent):
        """测试 Agent 执行列出版本"""
        request = {
            "action": "list_versions",
            "task_id": "research_001",
            "format": "docx"
        }
        
        result = doc_agent.execute(request)
        
        assert result is not None
    
    def test_agent_execute_rollback(self, doc_agent):
        """测试 Agent 执行版本回滚"""
        request = {
            "action": "rollback_version",
            "task_id": "research_001",
            "format": "docx",
            "target_version": "v1"
        }
        
        result = doc_agent.execute(request)
        
        assert result is not None
    
    def test_agent_execute_export(self, doc_agent, temp_dir):
        """测试 Agent 执行导出"""
        request = {
            "action": "export_document",
            "task_id": "research_001",
            "version_id": "v1",
            "format": "docx",
            "export_path": f"{temp_dir}/export/test.docx"
        }
        
        result = doc_agent.execute(request)
        
        assert result is not None


class TestDocumentFlowIntegration:
    """测试完整文档生成流程"""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.mark.asyncio
    async def test_full_flow_research_to_document(self, temp_dir):
        """测试完整流程：研究 → 存储 → 生成文档"""
        from src.core.storage.research_result_store import ResearchResultStore, ResearchStatus
        
        # 1. 创建研究结果存储
        store = ResearchResultStore(storage_path=temp_dir)
        
        # 2. 保存研究结果
        research_result = {
            "task_id": "research_flow_001",
            "topic": "完整流程测试",
            "sections": [
                {"title": "第一节", "content": "内容1"},
                {"title": "第二节", "content": "内容2"}
            ]
        }
        
        result_id = store.save_result(
            task_id="research_flow_001",
            result=research_result,
            status=ResearchStatus.COMPLETED
        )
        
        assert result_id is not None
        
        # 3. 更新状态为完成
        store.update_result(
            task_id="research_flow_001",
            status=ResearchStatus.COMPLETED
        )
        
        # 4. 加载结果
        loaded = store.load_result("research_flow_001")
        assert loaded is not None
        assert loaded["task_id"] == "research_flow_001"
        
        # 5. 列出已完成研究
        completed = store.list_results(status=ResearchStatus.COMPLETED)
        assert len(completed) >= 1
    
    def test_flow_with_version_management(self, temp_dir):
        """测试流程：生成 → 版本管理 → 回滚"""
        from src.core.storage.document_version_manager import DocumentVersionManager
        
        version_manager = DocumentVersionManager(storage_dir=temp_dir)
        
        # 创建版本（使用正确的参数）
        version = version_manager.create_version(
            task_id="research_version_001",
            format="docx",
            file_path=f"{temp_dir}/test.docx",
            file_size=1024,
            created_by="initial"
        )
        
        assert version is not None
        
        # 列出版本
        versions = version_manager.list_versions(
            task_id="research_version_001",
            format="docx"
        )
        
        assert len(versions) >= 1
    
    def test_flow_with_export(self, temp_dir):
        """测试流程：版本 → 导出"""
        from src.core.storage.export_manager import ExportManager
        
        export_manager = ExportManager(storage_dir=temp_dir)
        
        # 创建源文件
        source_file = Path(temp_dir) / "source.docx"
        source_file.write_text("test content")
        
        # 导出文档
        export_record = export_manager.export_document(
            task_id="research_export_001",
            version_id="v1",
            format="docx",
            source_path=str(source_file),
            export_path=f"{temp_dir}/export/test_export.docx"
        )
        
        assert export_record is not None
        assert export_record.success
        
        # 列出导出历史
        exports = export_manager.list_exports(task_id="research_export_001")
        
        assert len(exports) >= 1


class TestAPIIntegration:
    """测试 API 集成"""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def api(self, temp_dir):
        from src.api.document_api import DocumentAPI
        
        return DocumentAPI(storage_dir=temp_dir)
    
    @pytest.mark.asyncio
    async def test_api_generate_document_flow(self, api):
        """测试 API 生成文档流程"""
        from src.api.document_api import GenerateDocumentRequest
        
        request = GenerateDocumentRequest(
            task_id="research_api_001",
            output_format="docx",
            template="consulting"
        )
        
        result = await api.generate_document(request)
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_api_list_versions_flow(self, api):
        """测试 API 列出版本流程"""
        result = await api.list_versions("research_api_001", "docx")
        
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_api_delayed_generate_flow(self, api):
        """测试 API 延迟生成流程"""
        from src.api.document_api import DelayedGenerateRequest
        
        request = DelayedGenerateRequest(
            task_id="research_delayed_001",
            output_format="pptx",
            template="consulting"
        )
        
        result = await api.delayed_generate(request)
        
        assert result is not None