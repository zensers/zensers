# -*- coding: utf-8 -*-
"""
ExportManager 测试
==================

测试文档导出功能：
1. 导出文档到指定位置
2. 导出历史记录
3. 导出路径验证
4. 错误处理
"""

import pytest
import tempfile
import os
import json
import shutil
from datetime import datetime
from pathlib import Path


class TestExportManagerInit:
    """测试 ExportManager 初始化"""
    
    def test_manager_initialization(self):
        """测试管理器初始化"""
        from src.core.storage.export_manager import ExportManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ExportManager(storage_dir=tmpdir)
            
            assert manager is not None
    
    def test_manager_creates_storage_dir(self):
        """测试自动创建存储目录"""
        from src.core.storage.export_manager import ExportManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = os.path.join(tmpdir, "exports")
            manager = ExportManager(storage_dir=storage_dir)
            
            assert os.path.exists(storage_dir)


class TestExportManagerExport:
    """测试导出文档"""
    
    @pytest.fixture
    def manager_and_dirs(self):
        """创建管理器和临时目录"""
        from src.core.storage.export_manager import ExportManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = os.path.join(tmpdir, "storage")
            source_dir = os.path.join(tmpdir, "source")
            export_dir = os.path.join(tmpdir, "export")
            
            os.makedirs(source_dir, exist_ok=True)
            os.makedirs(export_dir, exist_ok=True)
            
            manager = ExportManager(storage_dir=storage_dir)
            
            yield manager, source_dir, export_dir
    
    def test_export_document(self, manager_and_dirs):
        """测试导出文档"""
        manager, source_dir, export_dir = manager_and_dirs
        
        # 创建源文件
        source_file = os.path.join(source_dir, "report.docx")
        with open(source_file, 'w', encoding='utf-8') as f:
            f.write("test content")
        
        export_path = os.path.join(export_dir, "exported_report.docx")
        
        result = manager.export_document(
            task_id="research_001",
            version_id="v1",
            format="docx",
            source_path=source_file,
            export_path=export_path
        )
        
        assert result is not None
        assert result.success is True
        assert os.path.exists(export_path)
    
    def test_export_preserves_content(self, manager_and_dirs):
        """测试导出保留内容"""
        manager, source_dir, export_dir = manager_and_dirs
        
        source_file = os.path.join(source_dir, "report.docx")
        test_content = "新能源汽车市场研究报告"
        with open(source_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        export_path = os.path.join(export_dir, "exported.docx")
        
        result = manager.export_document(
            task_id="research_001",
            version_id="v1",
            format="docx",
            source_path=source_file,
            export_path=export_path
        )
        
        assert result.success is True
        with open(export_path, 'r', encoding='utf-8') as f:
            assert f.read() == test_content
    
    def test_export_creates_directory(self, manager_and_dirs):
        """测试导出自动创建目录"""
        manager, source_dir, export_dir = manager_and_dirs
        
        source_file = os.path.join(source_dir, "report.docx")
        with open(source_file, 'w', encoding='utf-8') as f:
            f.write("content")
        
        # 导出到不存在的子目录
        export_path = os.path.join(export_dir, "subdir", "report.docx")
        
        result = manager.export_document(
            task_id="research_001",
            version_id="v1",
            format="docx",
            source_path=source_file,
            export_path=export_path
        )
        
        assert result.success is True
        assert os.path.exists(export_path)
    
    def test_export_with_metadata(self, manager_and_dirs):
        """测试带元数据导出"""
        manager, source_dir, export_dir = manager_and_dirs
        
        source_file = os.path.join(source_dir, "report.docx")
        with open(source_file, 'w', encoding='utf-8') as f:
            f.write("content")
        
        export_path = os.path.join(export_dir, "report.docx")
        
        result = manager.export_document(
            task_id="research_001",
            version_id="v1",
            format="docx",
            source_path=source_file,
            export_path=export_path,
            metadata={"exported_by": "user", "purpose": "review"}
        )
        
        assert result.success is True


class TestExportManagerHistory:
    """测试导出历史"""
    
    @pytest.fixture
    def manager(self):
        from src.core.storage.export_manager import ExportManager
        with tempfile.TemporaryDirectory() as tmpdir:
            yield ExportManager(storage_dir=tmpdir)
    
    def test_list_exports_empty(self, manager):
        """测试列出空导出历史"""
        exports = manager.list_exports("research_001")
        
        assert exports == []
    
    def test_list_exports_after_export(self, manager):
        """测试导出后列出历史"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "report.docx")
            with open(source_file, 'w', encoding='utf-8') as f:
                f.write("content")
            
            export_path = os.path.join(tmpdir, "exported.docx")
            
            manager.export_document(
                task_id="research_001",
                version_id="v1",
                format="docx",
                source_path=source_file,
                export_path=export_path
            )
            
            exports = manager.list_exports("research_001")
            
            assert len(exports) == 1
            assert exports[0].task_id == "research_001"
    
    def test_list_exports_multiple(self, manager):
        """测试多次导出"""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                source_file = os.path.join(tmpdir, f"report_{i}.docx")
                with open(source_file, 'w', encoding='utf-8') as f:
                    f.write(f"content {i}")
                
                export_path = os.path.join(tmpdir, f"exported_{i}.docx")
                
                manager.export_document(
                    task_id="research_001",
                    version_id=f"v{i+1}",
                    format="docx",
                    source_path=source_file,
                    export_path=export_path
                )
            
            exports = manager.list_exports("research_001")
            
            assert len(exports) == 3
    
    def test_list_exports_format_filter(self, manager):
        """测试格式过滤"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # docx
            source_docx = os.path.join(tmpdir, "report.docx")
            with open(source_docx, 'w') as f:
                f.write("docx")
            manager.export_document(
                task_id="research_001",
                version_id="v1",
                format="docx",
                source_path=source_docx,
                export_path=os.path.join(tmpdir, "e1.docx")
            )
            
            # pptx
            source_pptx = os.path.join(tmpdir, "report.pptx")
            with open(source_pptx, 'w') as f:
                f.write("pptx")
            manager.export_document(
                task_id="research_001",
                version_id="v1",
                format="pptx",
                source_path=source_pptx,
                export_path=os.path.join(tmpdir, "e1.pptx")
            )
            
            docx_exports = manager.list_exports("research_001", format="docx")
            pptx_exports = manager.list_exports("research_001", format="pptx")
            
            assert len(docx_exports) == 1
            assert len(pptx_exports) == 1


class TestExportManagerErrorHandling:
    """测试错误处理"""
    
    @pytest.fixture
    def manager(self):
        from src.core.storage.export_manager import ExportManager
        with tempfile.TemporaryDirectory() as tmpdir:
            yield ExportManager(storage_dir=tmpdir)
    
    def test_export_nonexistent_source(self, manager):
        """测试源文件不存在"""
        result = manager.export_document(
            task_id="research_001",
            version_id="v1",
            format="docx",
            source_path="/nonexistent/file.docx",
            export_path="/tmp/output.docx"
        )
        
        assert result.success is False
    
    def test_export_invalid_task_id(self, manager):
        """测试无效task_id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "report.docx")
            with open(source_file, 'w') as f:
                f.write("content")
            
            result = manager.export_document(
                task_id="../etc/passwd",
                version_id="v1",
                format="docx",
                source_path=source_file,
                export_path=os.path.join(tmpdir, "out.docx")
            )
            
            assert result.success is False
    
    def test_export_invalid_format(self, manager):
        """测试无效格式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "report.exe")
            with open(source_file, 'w') as f:
                f.write("content")
            
            result = manager.export_document(
                task_id="research_001",
                version_id="v1",
                format="exe",
                source_path=source_file,
                export_path=os.path.join(tmpdir, "out.exe")
            )
            
            assert result.success is False
    
    def test_export_path_traversal(self, manager):
        """测试导出路径遍历"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "report.docx")
            with open(source_file, 'w') as f:
                f.write("content")
            
            result = manager.export_document(
                task_id="research_001",
                version_id="v1",
                format="docx",
                source_path=source_file,
                export_path="/etc/passwd/evil.docx"
            )
            
            assert result.success is False


class TestExportManagerResult:
    """测试导出结果"""
    
    @pytest.fixture
    def manager(self):
        from src.core.storage.export_manager import ExportManager
        with tempfile.TemporaryDirectory() as tmpdir:
            yield ExportManager(storage_dir=tmpdir)
    
    def test_result_has_file_size(self, manager):
        """测试结果包含文件大小"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "report.docx")
            with open(source_file, 'w', encoding='utf-8') as f:
                f.write("test content for size")
            
            export_path = os.path.join(tmpdir, "exported.docx")
            
            result = manager.export_document(
                task_id="research_001",
                version_id="v1",
                format="docx",
                source_path=source_file,
                export_path=export_path
            )
            
            assert result.success is True
            assert result.file_size is not None
            assert result.file_size > 0
    
    def test_result_has_export_id(self, manager):
        """测试结果包含导出ID"""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "report.docx")
            with open(source_file, 'w') as f:
                f.write("content")
            
            result = manager.export_document(
                task_id="research_001",
                version_id="v1",
                format="docx",
                source_path=source_file,
                export_path=os.path.join(tmpdir, "out.docx")
            )
            
            assert result.success is True
            assert result.export_id is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
