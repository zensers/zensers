# -*- coding: utf-8 -*-
"""
HTMLToWordConverter 测试
========================

测试 HTML 转 Word 文档功能：
1. 基础HTML结构转换
2. 标题层级处理
3. 段落和列表处理
4. 表格处理
5. 样式应用
6. 错误处理
"""

import pytest
import tempfile
import os
from pathlib import Path


class TestHTMLToWordConverterInit:
    """测试 HTMLToWordConverter 初始化"""
    
    def test_converter_initialization(self):
        """测试转换器初始化"""
        from src.converters.html_to_word import HTMLToWordConverter
        
        converter = HTMLToWordConverter()
        
        assert converter is not None
    
    def test_converter_default_styles(self):
        """测试默认样式"""
        from src.converters.html_to_word import HTMLToWordConverter
        
        converter = HTMLToWordConverter()
        
        # 应有默认样式配置
        assert converter.get_default_styles() is not None


class TestHTMLToWordConverterBasic:
    """测试基础HTML转换"""
    
    @pytest.fixture
    def converter(self):
        """创建转换器实例"""
        from src.converters.html_to_word import HTMLToWordConverter
        return HTMLToWordConverter()
    
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
        
        output_path = os.path.join(temp_dir, "test.docx")
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
        
        output_path = os.path.join(temp_dir, "sections.docx")
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
        
        output_path = os.path.join(temp_dir, "title.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToWordConverterHeadings:
    """测试标题处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_word import HTMLToWordConverter
        return HTMLToWordConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_h1_heading(self, converter, temp_dir):
        """测试H1标题"""
        html = "<article><h1>一级标题</h1></article>"
        
        output_path = os.path.join(temp_dir, "h1.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_h2_heading(self, converter, temp_dir):
        """测试H2标题"""
        html = "<article><h2>二级标题</h2></article>"
        
        output_path = os.path.join(temp_dir, "h2.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_h3_heading(self, converter, temp_dir):
        """测试H3标题"""
        html = "<article><h3>三级标题</h3></article>"
        
        output_path = os.path.join(temp_dir, "h3.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_nested_headings(self, converter, temp_dir):
        """测试嵌套标题层级"""
        html = """
        <article>
            <h1>主标题</h1>
            <section>
                <h2>章节标题</h2>
                <section>
                    <h3>小节标题</h3>
                </section>
            </section>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "nested.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToWordConverterParagraphs:
    """测试段落处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_word import HTMLToWordConverter
        return HTMLToWordConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_single_paragraph(self, converter, temp_dir):
        """测试单个段落"""
        html = "<article><p>这是一个段落。</p></article>"
        
        output_path = os.path.join(temp_dir, "para.docx")
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
        
        output_path = os.path.join(temp_dir, "multi_para.docx")
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
        
        output_path = os.path.join(temp_dir, "unicode.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToWordConverterLists:
    """测试列表处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_word import HTMLToWordConverter
        return HTMLToWordConverter()
    
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
        
        output_path = os.path.join(temp_dir, "ul.docx")
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
        
        output_path = os.path.join(temp_dir, "ol.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_nested_list(self, converter, temp_dir):
        """测试嵌套列表"""
        html = """
        <article>
            <ul>
                <li>主项目
                    <ul>
                        <li>子项目一</li>
                        <li>子项目二</li>
                    </ul>
                </li>
            </ul>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "nested_list.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToWordConverterTables:
    """测试表格处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_word import HTMLToWordConverter
        return HTMLToWordConverter()
    
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
        
        output_path = os.path.join(temp_dir, "table.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_table_with_class(self, converter, temp_dir):
        """测试带类名的表格"""
        html = """
        <article>
            <table class="data-table">
                <tr><td>数据</td><td>值</td></tr>
            </table>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "table_class.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToWordConverterStyles:
    """测试样式处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_word import HTMLToWordConverter
        return HTMLToWordConverter()
    
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
        
        output_path = os.path.join(temp_dir, "custom.docx")
        result = converter.convert(html, output_path, styles=custom_styles)
        
        assert result.success is True
    
    def test_inline_styles(self, converter, temp_dir):
        """测试内联样式"""
        html = """
        <article>
            <p style="color: red; font-weight: bold;">红色加粗文本</p>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "inline.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToWordConverterErrorHandling:
    """测试错误处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_word import HTMLToWordConverter
        return HTMLToWordConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_empty_html(self, converter, temp_dir):
        """测试空HTML"""
        html = ""
        
        output_path = os.path.join(temp_dir, "empty.docx")
        result = converter.convert(html, output_path)
        
        # 应该返回失败或创建空文档
        assert result is not None
    
    def test_invalid_html(self, converter, temp_dir):
        """测试无效HTML"""
        html = "<article><h1>未闭合标签"
        
        output_path = os.path.join(temp_dir, "invalid.docx")
        result = converter.convert(html, output_path)
        
        # 应该尝试处理或返回错误
        assert result is not None
    
    def test_invalid_output_path(self, converter):
        """测试无效输出路径"""
        html = "<article><p>内容</p></article>"
        
        # 无效路径（不存在的目录）
        output_path = "/nonexistent/path/test.docx"
        
        result = converter.convert(html, output_path)
        
        # 应该返回失败
        assert result.success is False or result.error is not None


class TestHTMLToWordConverterResult:
    """测试转换结果"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_word import HTMLToWordConverter
        return HTMLToWordConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_result_has_file_size(self, converter, temp_dir):
        """测试结果包含文件大小"""
        html = "<article><h1>测试</h1><p>内容</p></article>"
        
        output_path = os.path.join(temp_dir, "size.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        assert result.file_size is not None
        assert result.file_size > 0
    
    def test_result_has_pages_estimate(self, converter, temp_dir):
        """测试结果包含页数估算"""
        html = "<article><h1>测试</h1>" + "<p>内容</p>" * 50 + "</article>"
        
        output_path = os.path.join(temp_dir, "pages.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        # 页数估算可能为None或正整数
        if result.pages_estimate is not None:
            assert result.pages_estimate > 0


class TestHTMLToWordConverterMarkdown:
    """测试Markdown语法转换"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_word import HTMLToWordConverter
        return HTMLToWordConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_bold_markdown(self, converter, temp_dir):
        """测试粗体Markdown **text**"""
        html = """
        <article>
            <p>这是<strong>粗体</strong>文本。</p>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "bold.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_italic_markdown(self, converter, temp_dir):
        """测试斜体Markdown *text*"""
        html = """
        <article>
            <p>这是<em>斜体</em>文本。</p>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "italic.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_code_markdown(self, converter, temp_dir):
        """测试代码Markdown `text`"""
        html = """
        <article>
            <p>使用命令<code>pip install</code>安装。</p>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "code.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_mixed_inline_formats(self, converter, temp_dir):
        """测试混合内联格式"""
        html = """
        <article>
            <p>这是<strong>粗体</strong>和<em>斜体</em>以及<code>代码</code>的混合。</p>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "mixed.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_markdown_in_heading(self, converter, temp_dir):
        """测试标题中的Markdown"""
        html = """
        <article>
            <h1><strong>重要</strong>报告标题</h1>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "md_heading.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_markdown_preprocessing(self, converter, temp_dir):
        """测试Markdown预处理（**text** → <strong>text</strong>）"""
        # 输入包含Markdown语法的HTML
        html = """
        <article>
            <p>这是**粗体**和*斜体*以及`代码`的Markdown语法。</p>
        </article>
        """
        
        output_path = os.path.join(temp_dir, "md_preprocess.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        # 验证文件生成成功（Markdown应被转换为HTML标签）


class TestHTMLToWordConverterComplex:
    """测试复杂文档转换"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_word import HTMLToWordConverter
        return HTMLToWordConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_full_document(self, converter, temp_dir):
        """测试完整文档"""
        html = """
        <article class="document" data-format="docx">
            <header class="document-header">
                <h1 class="document-title">新能源汽车市场研究报告</h1>
            </header>
            
            <nav class="document-toc">
                <h2>目录</h2>
                <ul class="toc-list">
                    <li><a href="#section_1">市场规模分析</a></li>
                    <li><a href="#section_2">竞争格局</a></li>
                </ul>
            </nav>
            
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
        
        output_path = os.path.join(temp_dir, "full.docx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        assert os.path.exists(output_path)
        assert result.file_size > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
