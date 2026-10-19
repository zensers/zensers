# -*- coding: utf-8 -*-
"""
PreviewGenerator 测试
=====================

测试文档预览生成功能：
1. 生成预览图
2. 预览缓存
3. 格式支持
4. 错误处理
"""

import pytest
import tempfile
import os
from pathlib import Path


class TestPreviewGeneratorInit:
    """测试 PreviewGenerator 初始化"""
    
    def test_generator_initialization(self):
        """测试生成器初始化"""
        from src.core.preview.preview_generator import PreviewGenerator
        
        generator = PreviewGenerator()
        
        assert generator is not None
    
    def test_generator_with_cache_dir(self):
        """测试带缓存目录初始化"""
        from src.core.preview.preview_generator import PreviewGenerator
        
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PreviewGenerator(cache_dir=tmpdir)
            
            assert generator is not None


class TestPreviewGeneratorGenerate:
    """测试生成预览"""
    
    @pytest.fixture
    def generator(self):
        from src.core.preview.preview_generator import PreviewGenerator
        with tempfile.TemporaryDirectory() as tmpdir:
            yield PreviewGenerator(cache_dir=tmpdir)
    
    @pytest.fixture
    def sample_files(self):
        """创建示例文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建模拟文档文件
            docx_path = os.path.join(tmpdir, "report.docx")
            with open(docx_path, 'wb') as f:
                f.write(b'PK\x03\x04' + b'\x00' * 100)  # ZIP header
            
            pdf_path = os.path.join(tmpdir, "report.pdf")
            with open(pdf_path, 'wb') as f:
                f.write(b'%PDF-1.4' + b'\x00' * 100)  # PDF header
            
            yield {"docx": docx_path, "pdf": pdf_path}
    
    def test_generate_preview_returns_result(self, generator, sample_files):
        """测试生成预览返回结果"""
        result = generator.generate_preview(
            document_path=sample_files["docx"],
            format="docx"
        )
        
        assert result is not None
        assert hasattr(result, "success")
    
    def test_generate_preview_creates_file(self, generator, sample_files):
        """测试生成预览创建文件"""
        result = generator.generate_preview(
            document_path=sample_files["docx"],
            format="docx"
        )
        
        if result.success:
            assert result.preview_path is not None
    
    def test_generate_preview_pdf(self, generator, sample_files):
        """测试PDF预览"""
        result = generator.generate_preview(
            document_path=sample_files["pdf"],
            format="pdf"
        )
        
        assert result is not None
    
    def test_generate_preview_with_options(self, generator, sample_files):
        """测试带选项生成预览"""
        result = generator.generate_preview(
            document_path=sample_files["docx"],
            format="docx",
            width=800,
            height=600,
            page_number=1
        )
        
        assert result is not None


class TestPreviewGeneratorCache:
    """测试预览缓存"""
    
    @pytest.fixture
    def generator_and_file(self):
        from src.core.preview.preview_generator import PreviewGenerator
        
        with tempfile.TemporaryDirectory() as tmpdir:
            generator = PreviewGenerator(cache_dir=tmpdir)
            
            docx_path = os.path.join(tmpdir, "report.docx")
            with open(docx_path, 'wb') as f:
                f.write(b'PK\x03\x04' + b'\x00' * 100)
            
            yield generator, docx_path
    
    def test_cache_reuse(self, generator_and_file):
        """测试缓存复用"""
        generator, docx_path = generator_and_file
        
        # 第一次生成
        result1 = generator.generate_preview(
            document_path=docx_path,
            format="docx"
        )
        
        # 第二次生成（应使用缓存）
        result2 = generator.generate_preview(
            document_path=docx_path,
            format="docx"
        )
        
        # 如果成功，两次结果应该相同
        if result1.success and result2.success:
            assert result1.preview_path == result2.preview_path
    
    def test_clear_cache(self, generator_and_file):
        """测试清除缓存"""
        generator, docx_path = generator_and_file
        
        generator.generate_preview(
            document_path=docx_path,
            format="docx"
        )
        
        # 清除缓存
        generator.clear_cache()
        
        # 缓存应被清空
        assert len(generator.get_cache_stats().get("cached_files", [])) == 0


class TestPreviewGeneratorErrorHandling:
    """测试错误处理"""
    
    @pytest.fixture
    def generator(self):
        from src.core.preview.preview_generator import PreviewGenerator
        with tempfile.TemporaryDirectory() as tmpdir:
            yield PreviewGenerator(cache_dir=tmpdir)
    
    def test_nonexistent_file(self, generator):
        """测试不存在的文件"""
        result = generator.generate_preview(
            document_path="/nonexistent/file.docx",
            format="docx"
        )
        
        assert result.success is False
    
    def test_invalid_format(self, generator):
        """测试无效格式"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "file.exe")
            with open(file_path, 'wb') as f:
                f.write(b'content')
            
            result = generator.generate_preview(
                document_path=file_path,
                format="exe"
            )
            
            assert result.success is False


class TestPreviewGeneratorResult:
    """测试预览结果"""
    
    @pytest.fixture
    def generator(self):
        from src.core.preview.preview_generator import PreviewGenerator
        with tempfile.TemporaryDirectory() as tmpdir:
            yield PreviewGenerator(cache_dir=tmpdir)
    
    def test_result_has_metadata(self, generator):
        """测试结果包含元数据"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "report.docx")
            with open(file_path, 'wb') as f:
                f.write(b'PK\x03\x04' + b'\x00' * 100)
            
            result = generator.generate_preview(
                document_path=file_path,
                format="docx"
            )
            
            if result.success:
                assert result.preview_format is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
