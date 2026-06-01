# -*- coding: utf-8 -*-
"""
DocumentGenerationAgent 测试
============================

测试文档生成Agent：
1. Agent 初始化
2. 输入验证
3. execute 方法行为
4. Session context 集成
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# 待测试的模块
# from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
# from src.agents.fixed_agents.document_models import ...


class TestDocumentGenerationAgentInit:
    """测试 Agent 初始化"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    def test_agent_initialization(self, temp_storage):
        """测试Agent初始化"""
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        
        agent = DocumentGenerationAgent(
            agent_id="doc_agent_001",
            storage_path=temp_storage
        )
        
        assert agent.agent_id == "doc_agent_001"
        assert agent.agent_type == "document_generation"
        assert agent.version == "1.0.0"
        assert len(agent.capabilities) > 0
    
    def test_agent_default_capabilities(self, temp_storage):
        """测试Agent默认能力"""
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        
        agent = DocumentGenerationAgent(
            agent_id="doc_agent_002",
            storage_path=temp_storage
        )
        
        capabilities = agent.get_capabilities()
        
        assert "Word文档生成" in capabilities
        assert "PPT文档生成" in capabilities
        assert "PDF文档生成" in capabilities
        assert "版本管理" in capabilities


class TestDocumentGenerationAgentValidation:
    """测试输入验证"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def agent(self, temp_storage):
        """创建Agent实例"""
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        return DocumentGenerationAgent(
            agent_id="doc_agent_test",
            storage_path=temp_storage
        )
    
    def test_validate_valid_input(self, agent):
        """测试有效输入验证"""
        valid, error = agent.validate_input({
            "action": "produce_document",
            "output_format": "docx",
            "task_id": "test_001"
        })
        
        assert valid is True
        assert error == ""
    
    def test_validate_missing_action(self, agent):
        """测试缺少action字段"""
        valid, error = agent.validate_input({
            "output_format": "docx"
        })
        
        assert valid is False
        assert "action" in error.lower()
    
    def test_validate_invalid_action(self, agent):
        """测试无效action值"""
        valid, error = agent.validate_input({
            "action": "invalid_action"
        })
        
        assert valid is False
    
    def test_validate_missing_format_for_produce(self, agent):
        """测试produce_document缺少format"""
        valid, error = agent.validate_input({
            "action": "produce_document",
            "task_id": "test_001"
        })
        
        assert valid is False
        assert "output_format" in error.lower()
    
    def test_validate_missing_task_id_for_rollback(self, agent):
        """测试rollback_version缺少task_id"""
        valid, error = agent.validate_input({
            "action": "rollback_version",
            "version_id": "v1"
        })
        
        assert valid is False
        assert "task_id" in error.lower()


class TestDocumentGenerationAgentExecute:
    """测试 execute 方法"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def agent(self, temp_storage):
        """创建Agent实例"""
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        return DocumentGenerationAgent(
            agent_id="doc_agent_exec",
            storage_path=temp_storage
        )
    
    def test_execute_produce_document_with_research_result(self, agent):
        """测试使用研究结果生成文档"""
        result = agent.execute({
            "action": "produce_document",
            "research_result": {
                "title": "新能源汽车市场研究",
                "topic": "新能源汽车",
                "sections": [
                    {"id": "s1", "title": "市场规模", "content": "..."}
                ]
            },
            "output_format": "docx"
        })
        
        assert result["success"] is True
        assert "task_id" in result
        assert result["output_format"] == "docx"
    
    def test_execute_produce_document_with_task_id(self, agent):
        """测试使用历史task_id生成文档（延迟生成）"""
        result = agent.execute({
            "action": "produce_document",
            "task_id": "research_abc123",
            "output_format": "pptx"
        })
        
        # Week 21 骨架：返回 pending 状态
        assert result["success"] is True
        assert result["task_id"] == "research_abc123"
    
    def test_execute_list_versions(self, agent):
        """测试列出版本"""
        result = agent.execute({
            "action": "list_versions",
            "task_id": "test_001",
            "output_format": "docx"
        })
        
        assert result["success"] is True
        assert "versions" in result
    
    def test_execute_rollback_version(self, agent):
        """测试回滚版本"""
        result = agent.execute({
            "action": "rollback_version",
            "task_id": "test_001",
            "output_format": "docx",
            "version_id": "v1"
        })
        
        assert result["success"] is True
    
    def test_execute_compare_versions(self, agent):
        """测试对比版本"""
        result = agent.execute({
            "action": "compare_versions",
            "task_id": "test_001",
            "output_format": "docx",
            "version_id": "v1",
            "version_id_2": "v2"
        })
        
        assert result["success"] is True
        assert "diff_result" in result
    
    def test_execute_export_document(self, agent):
        """测试导出文档"""
        result = agent.execute({
            "action": "export_document",
            "task_id": "test_001",
            "output_format": "docx",
            "version_id": "v1",
            "export_path": "/output/exported.docx"
        })
        
        assert result["success"] is True
    
    def test_execute_get_preview(self, agent):
        """测试获取预览"""
        result = agent.execute({
            "action": "get_preview",
            "task_id": "test_001",
            "output_format": "pptx",
            "version_id": "v1"
        })
        
        assert result["success"] is True
    
    def test_execute_adjust_content(self, agent):
        """测试调整内容"""
        result = agent.execute({
            "action": "adjust_content",
            "task_id": "test_001",
            "output_format": "docx",
            "adjustments": [
                {"type": "style", "target": "title", "value": "新标题"}
            ]
        })
        
        assert result["success"] is True


class TestDocumentGenerationAgentSession:
    """测试 Session context 集成"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def agent(self, temp_storage):
        """创建Agent实例"""
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        return DocumentGenerationAgent(
            agent_id="doc_agent_session",
            storage_path=temp_storage
        )
    
    def test_session_context_in_request(self, agent):
        """测试请求中包含Session上下文"""
        result = agent.execute({
            "action": "produce_document",
            "output_format": "docx",
            "task_id": "test_session_001",
            "session_context": {
                "parent_session_id": "research_xxx",
                "user_id": "user_123"
            }
        })
        
        assert result["success"] is True
    
    def test_agent_supports_shared_memory(self, agent):
        """测试Agent支持SharedMemory"""
        from unittest.mock import MagicMock
        
        # 模拟 SharedMemory
        shared_memory = MagicMock()
        shared_memory.read = MagicMock(return_value={
            "title": "测试报告",
            "sections": []
        })
        
        agent.set_shared_memory(shared_memory)
        
        assert agent._shared_memory is not None


class TestDocumentGenerationAgentErrorHandling:
    """测试错误处理"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def agent(self, temp_storage):
        """创建Agent实例"""
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        return DocumentGenerationAgent(
            agent_id="doc_agent_error",
            storage_path=temp_storage
        )
    
    def test_execute_with_invalid_input(self, agent):
        """测试无效输入执行"""
        result = agent.run({
            # 缺少 action
            "output_format": "docx"
        })
        
        assert result["success"] is False
        assert "error" in result
    
    def test_execute_with_unsupported_format(self, agent):
        """测试不支持的格式"""
        result = agent.execute({
            "action": "produce_document",
            "output_format": "unsupported_format"
        })
        
        assert result["success"] is False
    
    def test_run_method_catches_exception(self, agent):
        """测试run方法捕获异常"""
        # 模拟execute抛出异常
        original_execute = agent.execute
        
        def mock_execute(task_input):
            raise RuntimeError("测试异常")
        
        agent.execute = mock_execute
        
        result = agent.run({
            "action": "produce_document",
            "output_format": "docx"
        })
        
        assert result["success"] is False
        assert "测试异常" in result["error"]
        
        # 恢复原方法
        agent.execute = original_execute


class TestDocumentGenerationAgentIntegration:
    """测试集成场景"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def agent(self, temp_storage):
        """创建Agent实例"""
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        return DocumentGenerationAgent(
            agent_id="doc_agent_integration",
            storage_path=temp_storage
        )
    
    def test_full_produce_workflow(self, agent):
        """测试完整生成流程"""
        # 1. 生成文档
        result = agent.execute({
            "action": "produce_document",
            "research_result": {
                "title": "完整流程测试报告",
                "topic": "测试",
                "sections": [
                    {"id": "s1", "title": "第一章", "content": "内容..."}
                ]
            },
            "output_format": "docx",
            "template": "standard"
        })
        
        assert result["success"] is True
        task_id = result["task_id"]
        
        # 2. 列出版本
        versions_result = agent.execute({
            "action": "list_versions",
            "task_id": task_id,
            "output_format": "docx"
        })
        
        assert versions_result["success"] is True
    
    def test_multiple_format_generation(self, agent):
        """测试多格式生成"""
        research_result = {
            "title": "多格式测试",
            "topic": "测试",
            "sections": []
        }
        
        formats = ["docx", "pptx", "pdf"]
        results = []
        
        for fmt in formats:
            result = agent.execute({
                "action": "produce_document",
                "research_result": research_result,
                "output_format": fmt
            })
            results.append(result)
        
        assert all(r["success"] for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])