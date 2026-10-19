# -*- coding: utf-8 -*-
"""
DocumentVersionManager 测试
============================

测试文档版本控制功能：
1. 创建版本
2. 列出版本
3. 获取特定版本
4. 版本对比
5. 版本回滚
6. 持久化存储
7. 错误处理
"""

import pytest
import tempfile
import os
import json
from datetime import datetime
from pathlib import Path


class TestDocumentVersionManagerInit:
    """测试 DocumentVersionManager 初始化"""
    
    def test_manager_initialization(self):
        """测试管理器初始化"""
        from src.core.storage.document_version_manager import DocumentVersionManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DocumentVersionManager(storage_dir=tmpdir)
            
            assert manager is not None
    
    def test_manager_creates_storage_dir(self):
        """测试自动创建存储目录"""
        from src.core.storage.document_version_manager import DocumentVersionManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = os.path.join(tmpdir, "versions")
            manager = DocumentVersionManager(storage_dir=storage_dir)
            
            assert os.path.exists(storage_dir)


class TestDocumentVersionManagerCreate:
    """测试创建版本"""
    
    @pytest.fixture
    def manager(self):
        """创建管理器实例"""
        from src.core.storage.document_version_manager import DocumentVersionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentVersionManager(storage_dir=tmpdir)
    
    def test_create_initial_version(self, manager):
        """测试创建初始版本"""
        version = manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/document.docx",
            file_size=10240,
            created_by="initial"
        )
        
        assert version is not None
        assert version.version_id == "v1"
        assert version.format == "docx"
        assert version.created_by == "initial"
    
    def test_create_second_version(self, manager):
        """测试创建第二个版本"""
        # 先创建v1
        manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/v1.docx",
            file_size=10240,
            created_by="initial"
        )
        
        # 再创建v2
        version = manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/v2.docx",
            file_size=11264,
            created_by="regenerate"
        )
        
        assert version.version_id == "v2"
        assert version.parent_version == "v1"
    
    def test_create_version_with_template(self, manager):
        """测试带模板创建版本"""
        version = manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/document.docx",
            file_size=10240,
            created_by="initial",
            template="consulting"
        )
        
        assert version.template == "consulting"
    
    def test_create_version_with_adjustments(self, manager):
        """测试带调整记录创建版本"""
        adjustments = [
            {"type": "section_add", "target": "section_3", "content": "新增章节"}
        ]
        
        version = manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/document.docx",
            file_size=10240,
            created_by="adjustment",
            adjustments=adjustments
        )
        
        assert len(version.adjustments) == 1
    
    def test_create_version_independent_formats(self, manager):
        """测试不同格式独立版本号"""
        # docx v1
        v1_docx = manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/doc.docx",
            file_size=10240,
            created_by="initial"
        )
        
        # pptx v1（独立计数）
        v1_pptx = manager.create_version(
            task_id="research_001",
            format="pptx",
            file_path="/path/to/ppt.pptx",
            file_size=20480,
            created_by="initial"
        )
        
        assert v1_docx.version_id == "v1"
        assert v1_pptx.version_id == "v1"


class TestDocumentVersionManagerList:
    """测试列出版本"""
    
    @pytest.fixture
    def manager(self):
        from src.core.storage.document_version_manager import DocumentVersionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentVersionManager(storage_dir=tmpdir)
    
    def test_list_versions_empty(self, manager):
        """测试列出空版本"""
        versions = manager.list_versions("research_001", "docx")
        
        assert versions == []
    
    def test_list_versions_single(self, manager):
        """测试列出单个版本"""
        manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/v1.docx",
            file_size=10240,
            created_by="initial"
        )
        
        versions = manager.list_versions("research_001", "docx")
        
        assert len(versions) == 1
        assert versions[0].version_id == "v1"
    
    def test_list_versions_multiple(self, manager):
        """测试列出多个版本"""
        for i in range(3):
            manager.create_version(
                task_id="research_001",
                format="docx",
                file_path=f"/path/to/v{i+1}.docx",
                file_size=10240 * (i + 1),
                created_by="initial" if i == 0 else "regenerate"
            )
        
        versions = manager.list_versions("research_001", "docx")
        
        assert len(versions) == 3
        # 应按版本号排序
        assert versions[0].version_id == "v1"
        assert versions[2].version_id == "v3"
    
    def test_list_versions_format_filter(self, manager):
        """测试格式过滤"""
        manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/doc.docx",
            file_size=10240,
            created_by="initial"
        )
        manager.create_version(
            task_id="research_001",
            format="pptx",
            file_path="/path/to/ppt.pptx",
            file_size=20480,
            created_by="initial"
        )
        
        docx_versions = manager.list_versions("research_001", "docx")
        pptx_versions = manager.list_versions("research_001", "pptx")
        
        assert len(docx_versions) == 1
        assert len(pptx_versions) == 1


class TestDocumentVersionManagerGet:
    """测试获取特定版本"""
    
    @pytest.fixture
    def manager(self):
        from src.core.storage.document_version_manager import DocumentVersionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentVersionManager(storage_dir=tmpdir)
    
    def test_get_version(self, manager):
        """测试获取特定版本"""
        manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/v1.docx",
            file_size=10240,
            created_by="initial"
        )
        
        version = manager.get_version("research_001", "docx", "v1")
        
        assert version is not None
        assert version.version_id == "v1"
    
    def test_get_version_not_found(self, manager):
        """测试获取不存在的版本"""
        version = manager.get_version("research_001", "docx", "v99")
        
        assert version is None
    
    def test_get_latest_version(self, manager):
        """测试获取最新版本"""
        for i in range(3):
            manager.create_version(
                task_id="research_001",
                format="docx",
                file_path=f"/path/to/v{i+1}.docx",
                file_size=10240 * (i + 1),
                created_by="initial" if i == 0 else "regenerate"
            )
        
        latest = manager.get_latest_version("research_001", "docx")
        
        assert latest is not None
        assert latest.version_id == "v3"


class TestDocumentVersionManagerCompare:
    """测试版本对比"""
    
    @pytest.fixture
    def manager(self):
        from src.core.storage.document_version_manager import DocumentVersionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentVersionManager(storage_dir=tmpdir)
    
    def test_compare_versions(self, manager):
        """测试版本对比"""
        manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/v1.docx",
            file_size=10240,
            created_by="initial",
            change_summary="初始版本"
        )
        
        manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/v2.docx",
            file_size=11264,
            created_by="adjustment",
            change_summary="添加了第三章"
        )
        
        diff = manager.compare_versions("research_001", "docx", "v1", "v2")
        
        assert diff is not None
        assert "v1" in diff
        assert "v2" in diff
    
    def test_compare_same_version(self, manager):
        """测试对比相同版本"""
        manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/v1.docx",
            file_size=10240,
            created_by="initial"
        )
        
        diff = manager.compare_versions("research_001", "docx", "v1", "v1")
        
        assert diff is not None
        assert diff.get("identical") is True


class TestDocumentVersionManagerRollback:
    """测试版本回滚"""
    
    @pytest.fixture
    def manager(self):
        from src.core.storage.document_version_manager import DocumentVersionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentVersionManager(storage_dir=tmpdir)
    
    def test_rollback_to_version(self, manager):
        """测试回滚到指定版本"""
        manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/v1.docx",
            file_size=10240,
            created_by="initial"
        )
        
        manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/v2.docx",
            file_size=11264,
            created_by="adjustment"
        )
        
        # 回滚到v1
        rollback_version = manager.rollback_to_version(
            task_id="research_001",
            format="docx",
            target_version_id="v1"
        )
        
        assert rollback_version is not None
        assert rollback_version.created_by == "rollback"
        assert rollback_version.parent_version == "v2"  # 从v2回滚
    
    def test_rollback_creates_new_version(self, manager):
        """测试回滚创建新版本（不删除历史）"""
        manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/v1.docx",
            file_size=10240,
            created_by="initial"
        )
        
        manager.create_version(
            task_id="research_001",
            format="docx",
            file_path="/path/to/v2.docx",
            file_size=11264,
            created_by="adjustment"
        )
        
        manager.rollback_to_version(
            task_id="research_001",
            format="docx",
            target_version_id="v1"
        )
        
        # 应有3个版本（v1, v2, v3_rollback）
        versions = manager.list_versions("research_001", "docx")
        assert len(versions) == 3


class TestDocumentVersionManagerPersistence:
    """测试持久化存储"""
    
    def test_versions_persisted(self):
        """测试版本持久化"""
        from src.core.storage.document_version_manager import DocumentVersionManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建并保存
            manager1 = DocumentVersionManager(storage_dir=tmpdir)
            manager1.create_version(
                task_id="research_001",
                format="docx",
                file_path="/path/to/v1.docx",
                file_size=10240,
                created_by="initial"
            )
            
            # 重新加载
            manager2 = DocumentVersionManager(storage_dir=tmpdir)
            versions = manager2.list_versions("research_001", "docx")
            
            assert len(versions) == 1
            assert versions[0].version_id == "v1"


class TestDocumentVersionManagerErrorHandling:
    """测试错误处理"""
    
    @pytest.fixture
    def manager(self):
        from src.core.storage.document_version_manager import DocumentVersionManager
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DocumentVersionManager(storage_dir=tmpdir)
    
    def test_invalid_task_id(self, manager):
        """测试无效task_id"""
        version = manager.create_version(
            task_id="../etc/passwd",
            format="docx",
            file_path="/path/to/doc.docx",
            file_size=10240,
            created_by="initial"
        )
        
        # 应拒绝路径遍历
        assert version is None or manager.list_versions("../etc/passwd", "docx") == []
    
    def test_invalid_format(self, manager):
        """测试无效格式"""
        version = manager.create_version(
            task_id="research_001",
            format="exe",
            file_path="/path/to/doc.exe",
            file_size=10240,
            created_by="initial"
        )
        
        # 应拒绝无效格式
        assert version is None
    
    def test_rollback_nonexistent_version(self, manager):
        """测试回滚不存在的版本"""
        result = manager.rollback_to_version(
            task_id="research_001",
            format="docx",
            target_version_id="v99"
        )
        
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
