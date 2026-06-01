# -*- coding: utf-8 -*-
"""
测试知识导入器

测试范围：
- KnowledgeImporter: 导入用户历史资料
- 文件解析：PDF/Word/MD/TXT/Excel/CSV
- URL 导入
- 批量导入与自动知识提取
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime

from src.core.memory.knowledge.importer import (
    KnowledgeImporter,
    ImportResult,
    FileParser,
    ImportProgress
)


class TestFileParser:
    """测试文件解析器"""
    
    def test_parse_markdown_file(self):
        """测试解析 Markdown 文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write("# 宁德时代\n\n全球领先的动力电池制造商。\n\n市场份额 37%。")
            md_path = f.name
        
        try:
            parser = FileParser()
            content = parser.parse_file(md_path)
            
            assert "宁德时代" in content
            assert "动力电池" in content
            assert "市场份额" in content
        finally:
            os.unlink(md_path)
    
    def test_parse_txt_file(self):
        """测试解析纯文本文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write("比亚迪是一家中国汽车制造商。")
            txt_path = f.name
        
        try:
            parser = FileParser()
            content = parser.parse_file(txt_path)
            
            assert "比亚迪" in content
        finally:
            os.unlink(txt_path)
    
    def test_parse_csv_file(self):
        """测试解析 CSV 文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write("公司,市场份额,年份\n宁德时代,37%,2024\n比亚迪,25%,2024")
            csv_path = f.name
        
        try:
            parser = FileParser()
            content = parser.parse_file(csv_path)
            
            # CSV 应该被解析为可读文本
            assert "宁德时代" in content or "市场份额" in content
        finally:
            os.unlink(csv_path)
    
    def test_parse_unsupported_format(self):
        """测试不支持的格式"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xyz', delete=False, encoding='utf-8') as f:
            f.write("test content")
            xyz_path = f.name
        
        try:
            parser = FileParser()
            content = parser.parse_file(xyz_path)
            
            # 不支持的格式应该返回空或抛出异常
            assert content == "" or content is None
        finally:
            os.unlink(xyz_path)


class TestImportResult:
    """测试导入结果"""
    
    def test_import_result_creation(self):
        """测试创建导入结果"""
        result = ImportResult(
            file_path="/path/to/file.md",
            status="success",
            content="文件内容...",
            pages_created=3,
            entities_extracted=5
        )
        
        assert result.file_path == "/path/to/file.md"
        assert result.status == "success"
        assert result.pages_created == 3
    
    def test_import_result_to_dict(self):
        """测试转换为字典"""
        result = ImportResult(
            file_path="/path/to/file.md",
            status="success",
            content="内容",
            pages_created=2
        )
        
        d = result.to_dict()
        
        assert d["file_path"] == "/path/to/file.md"
        assert d["status"] == "success"


class TestImportProgress:
    """测试导入进度"""
    
    def test_progress_initialization(self):
        """测试进度初始化"""
        progress = ImportProgress(total_files=10)
        
        assert progress.total_files == 10
        assert progress.processed_files == 0
        assert progress.failed_files == 0
    
    def test_progress_update(self):
        """测试进度更新"""
        progress = ImportProgress(total_files=10)
        
        progress.update(success=True)
        assert progress.processed_files == 1
        
        progress.update(success=False)
        assert progress.failed_files == 1
    
    def test_progress_percentage(self):
        """测试进度百分比"""
        progress = ImportProgress(total_files=10)
        
        progress.update(success=True)
        progress.update(success=True)
        
        assert progress.get_percentage() == 20.0


class TestKnowledgeImporter:
    """测试知识导入器"""
    
    @pytest.fixture
    def temp_knowledge_dir(self):
        """创建临时知识库目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_path = Path(tmpdir) / "knowledge"
            knowledge_path.mkdir(parents=True, exist_ok=True)
            yield knowledge_path
    
    @pytest.fixture
    def importer(self, temp_knowledge_dir):
        """创建导入器实例"""
        return KnowledgeImporter(knowledge_root=temp_knowledge_dir)
    
    def test_init(self, importer, temp_knowledge_dir):
        """测试初始化"""
        assert importer.knowledge_root == temp_knowledge_dir
        assert importer.parser is not None
    
    def test_import_single_file(self, importer):
        """测试导入单个文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write("""
            # 新能源汽车行业报告
            
            宁德时代是全球领先的动力电池制造商。
            2024年市场份额达到37%。
            
            主要竞争对手：比亚迪、国轩高科。
            """)
            file_path = f.name
        
        try:
            result = importer.import_file(file_path)
            
            assert result.status == "success"
            assert result.content is not None
        finally:
            os.unlink(file_path)
    
    def test_import_directory(self, importer):
        """测试导入目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建多个测试文件
            (Path(tmpdir) / "file1.md").write_text("宁德时代相关内容。", encoding='utf-8')
            (Path(tmpdir) / "file2.txt").write_text("比亚迪汽车介绍。", encoding='utf-8')
            (Path(tmpdir) / "file3.csv").write_text("公司,营收\n宁德时代,3000亿", encoding='utf-8')
            
            results = importer.import_directory(tmpdir)
            
            assert len(results) >= 2  # 至少处理了 md 和 txt
    
    def test_import_with_auto_extraction(self, importer):
        """测试导入时自动提取知识"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as f:
            f.write("""
            宁德时代（CATL）是全球最大的动力电池制造商。
            2024年Q3市场份额37%。
            主要客户包括特斯拉、宝马。
            """)
            file_path = f.name
        
        try:
            result = importer.import_file(
                file_path,
                auto_extract=True
            )
            
            assert result.status == "success"
            # 应该提取到实体
            assert result.entities_extracted >= 1 or result.pages_created >= 1
        finally:
            os.unlink(file_path)
    
    def test_import_url(self, importer):
        """测试导入 URL（模拟）"""
        # 由于网络依赖，这里只测试方法存在
        assert hasattr(importer, 'import_url')
    
    def test_get_supported_formats(self, importer):
        """测试获取支持的格式"""
        formats = importer.get_supported_formats()
        
        assert '.md' in formats or 'md' in formats
        assert '.txt' in formats or 'txt' in formats
        assert '.csv' in formats or 'csv' in formats
    
    def test_import_progress_callback(self, importer):
        """测试导入进度回调"""
        progress_records = []
        
        def progress_callback(progress: ImportProgress):
            progress_records.append(progress.processed_files)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "file1.md").write_text("内容1", encoding='utf-8')
            (Path(tmpdir) / "file2.md").write_text("内容2", encoding='utf-8')
            
            importer.import_directory(tmpdir, progress_callback=progress_callback)
            
            # 应该有进度记录
            assert len(progress_records) >= 1


class TestIntegration:
    """集成测试"""
    
    def test_full_import_flow(self):
        """测试完整导入流程"""
        with tempfile.TemporaryDirectory() as tmpdir:
            knowledge_path = Path(tmpdir) / "knowledge"
            knowledge_path.mkdir(parents=True, exist_ok=True)
            
            importer = KnowledgeImporter(knowledge_root=knowledge_path)
            
            # 创建测试文件
            test_file = Path(tmpdir) / "research.md"
            test_file.write_text("""
            # 新能源汽车市场分析
            
            宁德时代是全球领先的动力电池制造商，2024年市场份额37%。
            
            主要竞争对手：
            - 比亚迪：市场份额25%
            - 国轩高科：市场份额8%
            
            宁德时代向特斯拉、宝马供应电池。
            """, encoding='utf-8')
            
            # 导入文件
            result = importer.import_file(
                str(test_file),
                auto_extract=True
            )
            
            # 验证结果
            assert result.status == "success"
            assert result.content is not None
            
            # 验证知识库
            stats = importer.get_stats()
            assert stats["total_imported"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])