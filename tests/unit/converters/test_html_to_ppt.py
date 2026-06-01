# -*- coding: utf-8 -*-
"""
HTMLToPPTConverter 测试
========================

测试 HTML 转 PowerPoint 文档功能：
1. 基础HTML结构转换
2. 幻灯片结构处理
3. 标题和内容处理
4. 列表处理
5. 表格处理
6. 样式应用
7. 错误处理
"""

import pytest
import tempfile
import os
from pathlib import Path


class TestHTMLToPPTConverterInit:
    """测试 HTMLToPPTConverter 初始化"""
    
    def test_converter_initialization(self):
        """测试转换器初始化"""
        from src.converters.html_to_ppt import HTMLToPPTConverter
        
        converter = HTMLToPPTConverter()
        
        assert converter is not None
    
    def test_converter_default_styles(self):
        """测试默认样式"""
        from src.converters.html_to_ppt import HTMLToPPTConverter
        
        converter = HTMLToPPTConverter()
        
        assert converter.get_default_styles() is not None


class TestHTMLToPPTConverterBasic:
    """测试基础HTML转换"""
    
    @pytest.fixture
    def converter(self):
        """创建转换器实例"""
        from src.converters.html_to_ppt import HTMLToPPTConverter
        return HTMLToPPTConverter()
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_convert_simple_html(self, converter, temp_dir):
        """测试转换简单HTML"""
        html = """
        <section class="slide" data-type="cover" data-page="1">
            <div class="slide-title">
                <h1>测试演示文稿</h1>
            </div>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "test.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        assert os.path.exists(output_path)
        assert result.file_size > 0
    
    def test_convert_with_multiple_slides(self, converter, temp_dir):
        """测试转换多页幻灯片"""
        html = """
        <section class="slide" data-type="cover" data-page="1">
            <h1>演示标题</h1>
        </section>
        <section class="slide" data-type="content" data-page="2">
            <h2>第一页内容</h2>
            <p>这是内容</p>
        </section>
        <section class="slide" data-type="content" data-page="3">
            <h2>第二页内容</h2>
            <p>更多内容</p>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "multi.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        assert os.path.exists(output_path)


class TestHTMLToPPTConverterSlideTypes:
    """测试幻灯片类型处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_ppt import HTMLToPPTConverter
        return HTMLToPPTConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_cover_slide(self, converter, temp_dir):
        """测试封面幻灯片"""
        html = """
        <section class="slide" data-type="cover" data-page="1">
            <div class="slide-title">
                <h1>新能源汽车市场研究报告</h1>
            </div>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "cover.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_toc_slide(self, converter, temp_dir):
        """测试目录幻灯片"""
        html = """
        <section class="slide" data-type="toc" data-page="1">
            <div class="slide-title">
                <h2>目录</h2>
            </div>
            <ul class="toc-list">
                <li class="toc-item">市场规模分析</li>
                <li class="toc-item">竞争格局</li>
            </ul>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "toc.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_content_slide(self, converter, temp_dir):
        """测试内容幻灯片"""
        html = """
        <section class="slide" data-type="content" data-page="1">
            <div class="slide-title">
                <h2>市场规模分析</h2>
            </div>
            <div class="slide-body">
                <p>2026年全球新能源汽车市场规模达到1.2万亿元。</p>
            </div>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "content.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_findings_slide(self, converter, temp_dir):
        """测试关键发现幻灯片"""
        html = """
        <section class="slide" data-type="findings" data-page="1">
            <div class="slide-title">
                <h2>关键发现</h2>
            </div>
            <ul class="findings-list">
                <li class="finding-item">市场规模持续增长</li>
                <li class="finding-item">竞争格局趋于集中</li>
            </ul>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "findings.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_data_slide(self, converter, temp_dir):
        """测试数据幻灯片"""
        html = """
        <section class="slide" data-type="data" data-page="1">
            <div class="slide-title">
                <h2>关键数据</h2>
            </div>
            <table class="data-table">
                <tbody>
                    <tr><td>市场规模</td><td>1.2万亿</td><td>人民币</td></tr>
                    <tr><td>增长率</td><td>25%</td><td>同比</td></tr>
                </tbody>
            </table>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "data.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_end_slide(self, converter, temp_dir):
        """测试结束幻灯片"""
        html = """
        <section class="slide" data-type="end" data-page="1">
            <div class="slide-title">
                <h2>谢谢</h2>
            </div>
            <div class="slide-footer">
                <p>新能源汽车市场研究报告</p>
            </div>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "end.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToPPTConverterLists:
    """测试列表处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_ppt import HTMLToPPTConverter
        return HTMLToPPTConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_unordered_list(self, converter, temp_dir):
        """测试无序列表"""
        html = """
        <section class="slide" data-type="content" data-page="1">
            <h2>列表测试</h2>
            <ul>
                <li>项目一</li>
                <li>项目二</li>
                <li>项目三</li>
            </ul>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "ul.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
    
    def test_ordered_list(self, converter, temp_dir):
        """测试有序列表"""
        html = """
        <section class="slide" data-type="content" data-page="1">
            <h2>步骤</h2>
            <ol>
                <li>第一步</li>
                <li>第二步</li>
                <li>第三步</li>
            </ol>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "ol.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToPPTConverterTables:
    """测试表格处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_ppt import HTMLToPPTConverter
        return HTMLToPPTConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_simple_table(self, converter, temp_dir):
        """测试简单表格"""
        html = """
        <section class="slide" data-type="data" data-page="1">
            <h2>数据表</h2>
            <table>
                <tr><th>指标</th><th>数值</th></tr>
                <tr><td>市场规模</td><td>1.2万亿</td></tr>
            </table>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "table.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True


class TestHTMLToPPTConverterStyles:
    """测试样式处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_ppt import HTMLToPPTConverter
        return HTMLToPPTConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_custom_styles(self, converter, temp_dir):
        """测试自定义样式"""
        html = """
        <section class="slide" data-type="cover" data-page="1">
            <h1>标题</h1>
        </section>
        """
        
        custom_styles = {
            "title_font": "Arial",
            "body_font": "Calibri",
            "title_size": 44
        }
        
        output_path = os.path.join(temp_dir, "custom.pptx")
        result = converter.convert(html, output_path, styles=custom_styles)
        
        assert result.success is True


class TestHTMLToPPTConverterErrorHandling:
    """测试错误处理"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_ppt import HTMLToPPTConverter
        return HTMLToPPTConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_empty_html(self, converter, temp_dir):
        """测试空HTML"""
        html = ""
        
        output_path = os.path.join(temp_dir, "empty.pptx")
        result = converter.convert(html, output_path)
        
        assert result is not None
    
    def test_invalid_html(self, converter, temp_dir):
        """测试无效HTML"""
        html = "<section><h1>未闭合标签"
        
        output_path = os.path.join(temp_dir, "invalid.pptx")
        result = converter.convert(html, output_path)
        
        assert result is not None
    
    def test_invalid_output_path(self, converter):
        """测试无效输出路径"""
        html = "<section class='slide'><h1>内容</h1></section>"
        
        output_path = "/nonexistent/path/test.pptx"
        
        result = converter.convert(html, output_path)
        
        assert result.success is False or result.error is not None


class TestHTMLToPPTConverterResult:
    """测试转换结果"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_ppt import HTMLToPPTConverter
        return HTMLToPPTConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_result_has_file_size(self, converter, temp_dir):
        """测试结果包含文件大小"""
        html = """
        <section class="slide" data-type="cover" data-page="1">
            <h1>测试</h1>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "size.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        assert result.file_size is not None
        assert result.file_size > 0
    
    def test_result_has_slide_count(self, converter, temp_dir):
        """测试结果包含幻灯片数"""
        html = """
        <section class="slide" data-type="cover" data-page="1">
            <h1>标题</h1>
        </section>
        <section class="slide" data-type="content" data-page="2">
            <h2>内容</h2>
        </section>
        <section class="slide" data-type="end" data-page="3">
            <h2>谢谢</h2>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "count.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        if result.slides_count is not None:
            assert result.slides_count >= 1


class TestHTMLToPPTConverterComplex:
    """测试复杂文档转换"""
    
    @pytest.fixture
    def converter(self):
        from src.converters.html_to_ppt import HTMLToPPTConverter
        return HTMLToPPTConverter()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_full_presentation(self, converter, temp_dir):
        """测试完整演示文稿"""
        html = """
        <section class="slide" data-type="cover" data-page="1">
            <div class="slide-content">
                <div class="slide-title">
                    <h1>新能源汽车市场研究报告</h1>
                </div>
            </div>
        </section>
        
        <section class="slide" data-type="toc" data-page="2">
            <div class="slide-content">
                <div class="slide-title">
                    <h2>目录</h2>
                </div>
                <ul class="toc-list">
                    <li class="toc-item">市场规模分析</li>
                    <li class="toc-item">竞争格局</li>
                    <li class="toc-item">关键发现</li>
                </ul>
            </div>
        </section>
        
        <section class="slide" data-type="section-title" data-page="3">
            <div class="slide-content">
                <div class="slide-title">
                    <h2>市场规模分析</h2>
                </div>
            </div>
        </section>
        
        <section class="slide" data-type="content" data-page="4" data-section="section_1">
            <div class="slide-content">
                <div class="slide-body">
                    <p>2026年全球新能源汽车市场规模达到1.2万亿元人民币，同比增长25%。</p>
                </div>
            </div>
        </section>
        
        <section class="slide" data-type="data" data-page="5">
            <div class="slide-content">
                <div class="slide-title">
                    <h2>关键数据</h2>
                </div>
                <table class="data-table">
                    <tbody>
                        <tr><td>市场规模</td><td class="data-value">1.2万亿</td><td>人民币</td></tr>
                        <tr><td>增长率</td><td class="data-value">25%</td><td>同比</td></tr>
                    </tbody>
                </table>
            </div>
        </section>
        
        <section class="slide" data-type="findings" data-page="6">
            <div class="slide-content">
                <div class="slide-title">
                    <h2>关键发现</h2>
                </div>
                <ul class="findings-list">
                    <li class="finding-item">市场规模持续增长</li>
                    <li class="finding-item">竞争格局趋于集中</li>
                </ul>
            </div>
        </section>
        
        <section class="slide" data-type="end" data-page="7">
            <div class="slide-content">
                <div class="slide-title">
                    <h2>谢谢</h2>
                </div>
                <div class="slide-footer">
                    <p>新能源汽车市场研究报告</p>
                </div>
            </div>
        </section>
        """
        
        output_path = os.path.join(temp_dir, "full.pptx")
        result = converter.convert(html, output_path)
        
        assert result.success is True
        assert os.path.exists(output_path)
        assert result.file_size > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
