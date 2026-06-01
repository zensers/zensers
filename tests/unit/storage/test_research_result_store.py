# -*- coding: utf-8 -*-
"""
研究结果存储测试
================

测试研究结果持久化功能：
1. 保存研究结果
2. 加载研究结果
3. 更新研究结果状态
4. 列出研究结果
5. 安全验证（Path Traversal防护）
"""

import pytest
import os
import json
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

# 导入待测试的模块
from src.core.storage.research_result_store import (
    ResearchResultStore,
    ResearchStatus,
    ResearchResultMeta,
    ResearchResultError,
    ResearchResultNotFoundError,
    InvalidTaskIdError
)


class TestResearchStatus:
    """测试 ResearchStatus 枚举"""
    
    def test_status_values(self):
        """测试状态枚举值"""
        assert ResearchStatus.ANALYZING.value == "analyzing"
        assert ResearchStatus.COLLECTING.value == "collecting"
        assert ResearchStatus.REPORTING.value == "reporting"
        assert ResearchStatus.COMPLETED.value == "completed"
        assert ResearchStatus.DOCUMENT_PENDING.value == "document_pending"
        assert ResearchStatus.DOCUMENT_GENERATED.value == "document_generated"


class TestResearchResultMeta:
    """测试 ResearchResultMeta 数据结构"""
    
    def test_create_meta(self):
        """测试创建元数据"""
        meta = ResearchResultMeta(
            task_id="research_abc123",
            title="新能源汽车市场研究",
            topic="新能源汽车",
            status=ResearchStatus.COMPLETED
        )
        
        assert meta.task_id == "research_abc123"
        assert meta.title == "新能源汽车市场研究"
        assert meta.topic == "新能源汽车"
        assert meta.status == ResearchStatus.COMPLETED
        assert meta.output_format is None
        assert meta.generated_formats == []
        assert meta.document_requests == []
        assert meta.document_paths == []
    
    def test_meta_to_dict(self):
        """测试元数据转字典"""
        meta = ResearchResultMeta(
            task_id="research_abc123",
            title="新能源汽车市场研究",
            topic="新能源汽车",
            status=ResearchStatus.COMPLETED,
            created_at=datetime(2026, 4, 11, 10, 0, 0),
            completed_at=datetime(2026, 4, 11, 11, 0, 0)
        )
        
        data = meta.to_dict()
        
        assert data["task_id"] == "research_abc123"
        assert data["title"] == "新能源汽车市场研究"
        assert data["status"] == "completed"
        assert "created_at" in data
        assert "completed_at" in data
        assert "document_paths" in data
    
    def test_meta_from_dict(self):
        """测试从字典创建元数据"""
        data = {
            "task_id": "research_abc123",
            "title": "新能源汽车市场研究",
            "topic": "新能源汽车",
            "status": "completed",
            "created_at": "2026-04-11T10:00:00",
            "completed_at": "2026-04-11T11:00:00",
            "output_format": None,
            "generated_formats": [],
            "document_requests": [],
            "document_paths": []
        }
        
        meta = ResearchResultMeta.from_dict(data)
        
        assert meta.task_id == "research_abc123"
        assert meta.title == "新能源汽车市场研究"
        assert meta.status == ResearchStatus.COMPLETED
    
    def test_meta_from_dict_missing_required_field(self):
        """测试从字典创建元数据时缺少必需字段"""
        data = {
            "task_id": "research_abc123",
            # 缺少 title
            "topic": "新能源汽车",
            "status": "completed"
        }
        
        with pytest.raises(ValueError) as excinfo:
            ResearchResultMeta.from_dict(data)
        
        assert "Missing required field" in str(excinfo.value)
    
    def test_meta_from_dict_invalid_status(self):
        """测试从字典创建元数据时无效的状态值"""
        data = {
            "task_id": "research_abc123",
            "title": "测试",
            "topic": "新能源汽车",
            "status": "invalid_status"  # 无效状态
        }
        
        with pytest.raises(ValueError) as excinfo:
            ResearchResultMeta.from_dict(data)
        
        assert "Invalid status value" in str(excinfo.value)


class TestResearchResultStore:
    """测试 ResearchResultStore 类"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def store(self, temp_storage):
        """创建存储实例"""
        return ResearchResultStore(temp_storage)
    
    @pytest.fixture
    def sample_result(self):
        """创建示例研究结果"""
        return {
            "title": "新能源汽车市场研究报告",
            "topic": "新能源汽车",
            "sections": [
                {
                    "id": "section_1",
                    "title": "市场规模分析",
                    "content": "2026年全球新能源汽车市场规模达到..."
                },
                {
                    "id": "section_2",
                    "title": "竞争格局分析",
                    "content": "主要竞争者包括..."
                }
            ],
            "key_findings": [
                "市场规模持续增长",
                "竞争格局趋于集中"
            ],
            "data_points": [
                {"metric": "市场规模", "value": "1.2万亿", "unit": "人民币"},
                {"metric": "增长率", "value": "25%", "unit": "同比"}
            ]
        }
    
    def test_store_initialization(self, store, temp_storage):
        """测试存储初始化"""
        assert store.storage_path == Path(temp_storage)
        assert store.results_dir == Path(temp_storage) / "results"
        assert store.results_dir.exists()
    
    def test_save_result(self, store, sample_result):
        """测试保存研究结果"""
        task_id = "research_test001"
        
        result_id = store.save_result(
            task_id=task_id,
            result=sample_result,
            status=ResearchStatus.COMPLETED
        )
        
        assert result_id == task_id
        
        # 验证文件已创建
        result_path = store.results_dir / task_id / "result.json"
        assert result_path.exists()
        
        metadata_path = store.results_dir / task_id / "metadata.json"
        assert metadata_path.exists()
    
    def test_load_result(self, store, sample_result):
        """测试加载研究结果"""
        task_id = "research_test002"
        
        # 先保存
        store.save_result(
            task_id=task_id,
            result=sample_result,
            status=ResearchStatus.COMPLETED
        )
        
        # 再加载
        loaded = store.load_result(task_id)
        
        assert loaded is not None
        assert loaded["title"] == sample_result["title"]
        assert loaded["topic"] == sample_result["topic"]
        assert len(loaded["sections"]) == 2
    
    def test_load_nonexistent_result(self, store):
        """测试加载不存在的结果"""
        loaded = store.load_result("nonexistent_task")
        assert loaded is None
    
    def test_update_result_status(self, store, sample_result):
        """测试更新研究结果状态"""
        task_id = "research_test003"
        
        # 先保存
        store.save_result(
            task_id=task_id,
            result=sample_result,
            status=ResearchStatus.COMPLETED
        )
        
        # 更新状态
        store.update_result(
            task_id=task_id,
            status=ResearchStatus.DOCUMENT_GENERATED,
            generated_format="docx",
            document_path="/output/report.docx"
        )
        
        # 验证更新
        metadata = store.load_metadata(task_id)
        assert metadata.status == ResearchStatus.DOCUMENT_GENERATED
        assert "docx" in metadata.generated_formats
        assert "/output/report.docx" in metadata.document_paths
    
    def test_update_result_not_found(self, store):
        """测试更新不存在的结果"""
        with pytest.raises(ResearchResultNotFoundError):
            store.update_result(
                task_id="nonexistent_task",
                status=ResearchStatus.DOCUMENT_GENERATED
            )
    
    def test_list_results(self, store, sample_result):
        """测试列出研究结果"""
        # 保存多个结果
        for i in range(3):
            store.save_result(
                task_id=f"research_list_{i:03d}",
                result={**sample_result, "title": f"报告{i}"},
                status=ResearchStatus.COMPLETED
            )
        
        # 列出结果
        results = store.list_results(status=ResearchStatus.COMPLETED)
        
        assert len(results) == 3
    
    def test_list_results_with_limit(self, store, sample_result):
        """测试列出研究结果（带限制）"""
        # 保存多个结果
        for i in range(5):
            store.save_result(
                task_id=f"research_limit_{i:03d}",
                result={**sample_result, "title": f"报告{i}"},
                status=ResearchStatus.COMPLETED
            )
        
        # 列出结果（限制数量）
        results = store.list_results(status=ResearchStatus.COMPLETED, limit=3)
        
        assert len(results) == 3
    
    def test_record_document_request(self, store, sample_result):
        """测试记录文档生成请求"""
        task_id = "research_doc001"
        
        # 先保存研究结果
        store.save_result(
            task_id=task_id,
            result=sample_result,
            status=ResearchStatus.COMPLETED
        )
        
        # 记录文档生成请求
        store.record_document_request(
            task_id=task_id,
            request={
                "output_format": "pptx",
                "template": "consulting",
                "generated_at": datetime.now().isoformat(),
                "document_path": "/output/report.pptx"
            }
        )
        
        # 验证记录
        metadata = store.load_metadata(task_id)
        assert len(metadata.document_requests) == 1
        assert metadata.document_requests[0]["output_format"] == "pptx"
    
    def test_record_document_request_not_found(self, store):
        """测试记录不存在的结果的文档请求"""
        with pytest.raises(ResearchResultNotFoundError):
            store.record_document_request(
                task_id="nonexistent_task",
                request={"output_format": "docx"}
            )
    
    def test_delete_result(self, store, sample_result):
        """测试删除研究结果"""
        task_id = "research_delete001"
        
        # 先保存
        store.save_result(
            task_id=task_id,
            result=sample_result,
            status=ResearchStatus.COMPLETED
        )
        
        # 验证存在
        assert store.load_result(task_id) is not None
        
        # 删除
        store.delete_result(task_id)
        
        # 验证已删除
        assert store.load_result(task_id) is None
    
    def test_result_exists(self, store, sample_result):
        """测试检查结果是否存在"""
        task_id = "research_exists001"
        
        # 保存前不存在
        assert not store.result_exists(task_id)
        
        # 保存
        store.save_result(
            task_id=task_id,
            result=sample_result,
            status=ResearchStatus.COMPLETED
        )
        
        # 保存后存在
        assert store.result_exists(task_id)


class TestSecurityValidation:
    """测试安全验证功能"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def store(self, temp_storage):
        """创建存储实例"""
        return ResearchResultStore(temp_storage)
    
    def test_path_traversal_attack_with_dots(self, store):
        """测试路径遍历攻击（使用../）"""
        malicious_task_ids = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "../../outside_dir",
            "../sibling_dir"
        ]
        
        for malicious_id in malicious_task_ids:
            with pytest.raises(InvalidTaskIdError):
                store.save_result(
                    task_id=malicious_id,
                    result={"title": "test"},
                    status=ResearchStatus.COMPLETED
                )
    
    def test_invalid_task_id_characters(self, store):
        """测试无效字符在task_id中"""
        invalid_task_ids = [
            "task/with/slashes",
            "task\\with\\backslashes",
            "task with spaces",
            "task:with:colons",
            "task*with*wildcards",
            "task\"with\"quotes",
            "task<with>brackets",
            "task|with|pipes",
            "task?with?question"
        ]
        
        for invalid_id in invalid_task_ids:
            with pytest.raises(InvalidTaskIdError):
                store.save_result(
                    task_id=invalid_id,
                    result={"title": "test"},
                    status=ResearchStatus.COMPLETED
                )
    
    def test_empty_task_id(self, store):
        """测试空task_id"""
        with pytest.raises(InvalidTaskIdError):
            store.save_result(
                task_id="",
                result={"title": "test"},
                status=ResearchStatus.COMPLETED
            )
    
    def test_valid_task_id_patterns(self, store):
        """测试有效的task_id格式"""
        valid_task_ids = [
            "research_001",
            "task-123",
            "RESEARCH_ABC",
            "task123",
            "abc_def-ghi"
        ]
        
        for valid_id in valid_task_ids:
            # 应该不抛出异常
            store.save_result(
                task_id=valid_id,
                result={"title": "test"},
                status=ResearchStatus.COMPLETED
            )
            
            # 验证保存成功
            assert store.result_exists(valid_id)
    
    def test_delete_with_path_traversal(self, store):
        """测试删除操作中的路径遍历攻击 - 应静默返回False"""
        result = store.delete_result("../../../etc/passwd")
        assert result is False
    
    def test_load_with_path_traversal(self, store):
        """测试加载操作中的路径遍历攻击 - 应静默返回None"""
        result = store.load_result("../../../etc/passwd")
        assert result is None


class TestResearchResultStoreIntegration:
    """测试 ResearchResultStore 集成场景"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def store(self, temp_storage):
        """创建存储实例"""
        return ResearchResultStore(temp_storage)
    
    def test_full_workflow(self, store):
        """测试完整工作流程"""
        task_id = "research_workflow001"
        
        # 1. 保存研究结果（研究完成）
        result = {
            "title": "完整工作流程测试",
            "topic": "测试",
            "sections": [{"id": "s1", "title": "章节1", "content": "内容"}],
            "key_findings": ["发现1"],
            "data_points": []
        }
        
        store.save_result(
            task_id=task_id,
            result=result,
            status=ResearchStatus.COMPLETED
        )
        
        # 2. 验证状态
        metadata = store.load_metadata(task_id)
        assert metadata.status == ResearchStatus.COMPLETED
        
        # 3. 生成第一个文档（Word）
        store.record_document_request(
            task_id=task_id,
            request={
                "output_format": "docx",
                "template": "consulting",
                "generated_at": datetime.now().isoformat(),
                "document_path": "/output/report.docx"
            }
        )
        
        store.update_result(
            task_id=task_id,
            status=ResearchStatus.DOCUMENT_GENERATED,
            generated_format="docx",
            document_path="/output/report.docx"
        )
        
        # 4. 验证更新
        metadata = store.load_metadata(task_id)
        assert metadata.status == ResearchStatus.DOCUMENT_GENERATED
        assert "docx" in metadata.generated_formats
        assert "/output/report.docx" in metadata.document_paths
        
        # 5. 生成第二个文档（PPT）
        store.record_document_request(
            task_id=task_id,
            request={
                "output_format": "pptx",
                "template": "consulting",
                "generated_at": datetime.now().isoformat(),
                "document_path": "/output/report.pptx"
            }
        )
        
        store.update_result(
            task_id=task_id,
            generated_format="pptx",
            document_path="/output/report.pptx"
        )
        
        # 6. 验证多格式
        metadata = store.load_metadata(task_id)
        assert len(metadata.generated_formats) == 2
        assert "docx" in metadata.generated_formats
        assert "pptx" in metadata.generated_formats
        assert len(metadata.document_requests) == 2
        assert len(metadata.document_paths) == 2
    
    def test_unicode_content(self, store):
        """测试Unicode内容处理"""
        task_id = "unicode_test_001"
        
        result = {
            "title": "日本語タイトル",
            "topic": "中文主题",
            "sections": [
                {"id": "s1", "title": "العربية", "content": "한국어 내용"}
            ],
            "key_findings": ["Ελληνικά", "עברית"],
            "data_points": []
        }
        
        store.save_result(
            task_id=task_id,
            result=result,
            status=ResearchStatus.COMPLETED
        )
        
        loaded = store.load_result(task_id)
        
        assert loaded["title"] == "日本語タイトル"
        assert loaded["topic"] == "中文主题"
        assert loaded["sections"][0]["content"] == "한국어 내용"
    
    def test_overwrite_result(self, store):
        """测试覆盖已存在的结果"""
        task_id = "overwrite_test_001"
        
        # 第一次保存
        store.save_result(
            task_id=task_id,
            result={"title": "原标题", "topic": "test"},
            status=ResearchStatus.COMPLETED
        )
        
        # 第二次保存（覆盖）
        store.save_result(
            task_id=task_id,
            result={"title": "新标题", "topic": "test"},
            status=ResearchStatus.COMPLETED
        )
        
        loaded = store.load_result(task_id)
        assert loaded["title"] == "新标题"


class TestErrorHandling:
    """测试错误处理"""
    
    @pytest.fixture
    def temp_storage(self):
        """创建临时存储目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def store(self, temp_storage):
        """创建存储实例"""
        return ResearchResultStore(temp_storage)
    
    def test_load_result_returns_none_for_nonexistent(self, store):
        """测试加载不存在结果返回None（而非抛出异常）"""
        result = store.load_result("nonexistent")
        assert result is None
    
    def test_load_metadata_returns_none_for_nonexistent(self, store):
        """测试加载不存在元数据返回None"""
        metadata = store.load_metadata("nonexistent")
        assert metadata is None
    
    def test_delete_nonexistent_returns_false(self, store):
        """测试删除不存在结果返回False"""
        result = store.delete_result("nonexistent")
        assert result is False
    
    def test_result_exists_for_invalid_id_returns_false(self, store):
        """测试检查无效ID是否存在返回False"""
        result = store.result_exists("../../../invalid")
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
