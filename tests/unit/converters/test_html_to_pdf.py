# -*- coding: utf-8 -*-
"""
HTMLToPDFConverter 测试
========================

测试 HTML 转 PDF 文档功能：
1. 基础HTML结构转换
2. 标题和段落处理
3. 列表处理
4. 表格处理
5. 样式应用
6. 错误处理
"""

import pytest
import tempfile
import os
from pathlib import Path


class TestHTMLToPDFConverterInit:
    """测试 HTMLToPDFConverter 初始化"""
    
    def test_converter_initialization(self):
        """测试转换器初始化"""
        from src.converters.html_to_pdf import HTMLToPDFConverter
        
        converter = HTMLToPDFConverter()
        
        assert converter is not None
    
    def test_converter_default_styles(self):
        """测试默认样式"""
        from src.converters.html_to_pdf import HTMLToPDFConverter
        
        converter = HTMLToPDFConverter()
        
        assert converter.get_default_styles() is not None


class TestHTMLToPDFConverterBasic:
    """测试基础HTML转换"""
    
    @pytest.fixture
    def converter(self):
        """创建转换器实例"""
        from src.converters.html_to_pdf import HTMLToPDFConverter
        return HTMLToPDFConverter()
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_convert_simple_html(self, converter, temp_dir):
        """测试转换简单HTML"""
        html = """
        <article>
            <h1>测试报告</h1>
            <p>这是一个测试段落。</p>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "test.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        assert os.path.exists(output_path)
        assert result.file_size > 0
    
    def test_convert_with_sections(self, converter, temp_dir):
        """测试转换带章节的HTML"""
        html = """
        <article>
            <header>
                <h1>研究报告</h1>
            </header>
            <section id="s1">
                <h2>第一章</h2>
                <p>第一章内容。</p>
            </section>
            <section id="s2">
                <h2>第二章</h2>
                <p>第二章内容。</p>
            </section>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "sections.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        assert os.path.exists(output_path)
    
    def test_convert_preserves_title(self, converter, temp_dir):
        """测试标题保留"""
        html = """
        <article>
            <h1>新能源汽车市场研究报告</h1>
            <p>内容</p>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "title.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToPDFConverterHeadings:
    """测试标题处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_pdf import HTMLToPDFConverter
        return HTMLToPDFConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_h1_heading(self, converter, temp_dir):
        """测试H1标题"""
        html = "<article><h1>一级标题</h1></article>"
        
        output_path = os.path.join(temp_dir, "h1.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_h2_heading(self, converter, temp_dir):
        """测试H2标题"""
        html = "<article><h2>二级标题</h2></article>"
        
        output_path = os.path.join(temp_dir, "h2.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_h3_heading(self, converter, temp_dir):
        """测试H3标题"""
        html = "<article><h3>三级标题</h3></article>"
        
        output_path = os.path.join(temp_dir, "h3.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToPDFConverterParagraphs:
    """测试段落处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_pdf import HTMLToPDFConverter
        return HTMLToPDFConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_single_paragraph(self, converter, temp_dir):
        """测试单个段落"""
        html = "<article><p>这是一个段落。</p></article>"
        
        output_path = os.path.join(temp_dir, "para.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_multiple_paragraphs(self, converter, temp_dir):
        """测试多个段落"""
        html = """
        <article>
            <p>第一段内容。</p>
            <p>第二段内容。</p>
            <p>第三段内容。</p>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "multi_para.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_unicode_paragraph(self, converter, temp_dir):
        """测试Unicode段落"""
        html = """
        <article>
            <p>中文内容测试。</p>
            <p>日本語テスト。</p>
            <p>한국어 테스트。</p>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "unicode.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToPDFConverterLists:
    """测试列表处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_pdf import HTMLToPDFConverter
        return HTMLToPDFConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_unordered_list(self, converter, temp_dir):
        """测试无序列表"""
        html = """
        <article>
            <ul>
                <li>项目一</li>
                <li>项目二</li>
                <li>项目三</li>
            </ul>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "ul.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_ordered_list(self, converter, temp_dir):
        """测试有序列表"""
        html = """
        <article>
            <ol>
                <li>第一步</li>
                <li>第二步</li>
                <li>第三步</li>
            </ol>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "ol.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToPDFConverterTables:
    """测试表格处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_pdf import HTMLToPDFConverter
        return HTMLToPDFConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_simple_table(self, converter, temp_dir):
        """测试简单表格"""
        html = """
        <article>
            <table>
                <thead>
                    <tr><th>指标</th><th>数值</th></tr>
                </thead>
                <tbody>
                    <tr><td>市场规模</td><td>1.2万亿</td></tr>
                    <tr><td>增长率</td><td>25%</td></tr>
                </tbody>
            </table>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "table.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToPDFConverterStyles:
    """测试样式处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_pdf import HTMLToPDFConverter
        return HTMLToPDFConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_custom_styles(self, converter, temp_dir):
        """测试自定义样式"""
        html = "<article><h1>标题</h1><p>内容</p></article>"
        
        custom_styles = {
            "title_font": "Arial",
            "body_font": "Times New Roman",
            "title_size": 28
        }
        
        output_path = os.path.join(temp_dir, "custom.pdf")
        result = converter.convert(html, output_path, styles=custom_styles)
        
        assert result.success is True


class TestHTMLToPDFConverterErrorHandling:
    """测试错误处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_pdf import HTMLToPDFConverter
        return HTMLToPDFConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_empty_html(self, converter, temp_dir):
        """测试空HTML"""
        html = ""
        
        output_path = os.path.join(temp_dir, "empty.pdf")
        result = converter.convert(html, output_path)
        
        assert result is not None
    
    def test_invalid_html(self, converter, temp_dir):
        """测试无效HTML"""
        html = "<article><h1>未闭合标签"
        
        output_path = os.path.join(temp_dir, "invalid.pdf")
        result = converter.convert(html, output_path)
        
        assert result is not None
    
    def test_invalid_output_path(self, converter):
        """测试无效输出路径"""
        html = "<article><p>内容</p></article>"
        
        output_path = "/nonexistent/path/test.pdf"
        
        result = converter.convert(html, output_path)
        
        assert result.success is False or result.error is not None


class TestHTMLToPDFConverterResult:
    """测试转换结果"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_pdf import HTMLToPDFConverter
        return HTMLToPDFConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_result_has_file_size(self, converter, temp_dir):
        """测试结果包含文件大小"""
        html = "<article><h1>测试</h1><p>内容</p></article>"
        
        output_path = os.path.join(temp_dir, "size.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        assert result.file_size is not None
        assert result.file_size > 0
    
    def test_result_has_pages_estimate(self, converter, temp_dir):
        """测试结果包含页数估算"""
        html = "<article><h1>测试</h1>" + "<p>内容</p>" * 50 + "</article>"
        
        output_path = os.path.join(temp_dir, "pages.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        if result.pages_estimate is not None:
            assert result.pages_estimate > 0


class TestHTMLToPDFConverterComplex:
    """测试复杂文档转换"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_pdf import HTMLToPDFConverter
        return HTMLToPDFConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_full_document(self, converter, temp_dir):
        """测试完整文档"""
        html = """
        <article class="document" data-format="pdf">
            <header class="document-header">
                <h1 class="document-title">新能源汽车市场研究报告</h1>
            </header>
            
            <section id="section_1" class="document-section">
                <h2 class="section-title">市场规模分析</h2>
                <p class="section-content">2026年全球新能源汽车市场规模达到1.2万亿元人民币。</p>
                
                <table class="data-table">
                    <thead><tr><th>指标</th><th>数值</th><th>单位</th></tr></thead>
                    <tbody>
                        <tr><td>市场规模</td><td>1.2万亿</td><td>人民币</td></tr>
                        <tr><td>增长率</td><td>25%</td><td>同比</td></tr>
                    </tbody>
                </table>
            </section>
            
            <section id="section_2" class="document-section">
                <h2 class="section-title">竞争格局</h2>
                <p class="section-content">主要竞争者包括：</p>
                <ul>
                    <li>特斯拉</li>
                    <li>比亚迪</li>
                    <li>蔚来</li>
                </ul>
            </section>
            
            <section class="key-findings" id="key-findings">
                <h2>关键发现</h2>
                <ul class="findings-list">
                    <li>市场规模持续增长</li>
                    <li>竞争格局趋于集中</li>
                </ul>
            </section>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "full.pdf")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        assert os.path.exists(output_path)
        assert result.file_size > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
