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
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
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
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
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
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
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
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
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
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
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
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
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
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
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
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
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


class TestTemplateRendererOnlyPath:
    """USE_TEMPLATE_RENDERER 开关已删除，模板渲染是唯一渲染路径"""

    def test_template_renderer_is_only_path(self, monkeypatch):
        from src.converters.html_to_ppt import HTMLToPPTConverter
        converter = HTMLToPPTConverter()
        assert not hasattr(converter, "_should_use_template_renderer")

        monkeypatch.setenv("USE_TEMPLATE_RENDERER", "0")
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            html = """
            <section class="slide" data-type="content" data-page="1">
                <div class="slide-content">
                    <div class="slide-title"><h2>Overview</h2></div>
                    <ul class="slide-list"><li>Point 1</li></ul>
                </div>
            </section>
            """
            output_path = os.path.join(tmpdir, "only_path.pptx")
            result = converter.convert(html, output_path)
            assert result.success is True
            assert os.path.exists(output_path)


class TestPPTBulletContentRendering:
    """测试<li>要点内容在PPTX中正确渲染"""

    @pytest.fixture
    def converter(self):
        from src.converters.html_to_ppt import HTMLToPPTConverter
        return HTMLToPPTConverter()

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            yield tmpdir

    def test_li_items_rendered_as_bullets(self, converter, temp_dir):
        html = """
        <section class="slide" data-type="content" data-page="1">
            <h2>行业概览</h2>
            <ul>
                <li>销量950万辆 同比+37.5%</li>
                <li>市场规模1.2万亿</li>
                <li>渗透率突破40%</li>
            </ul>
        </section>
        """
        output_path = os.path.join(temp_dir, "bullets.pptx")
        result = converter.convert(html, output_path)
        assert result.success is True

        from pptx import Presentation
        prs = Presentation(output_path)
        slide = prs.slides[0]
        texts = []
        for sh in slide.shapes:
            if sh.has_text_frame:
                for para in sh.text_frame.paragraphs:
                    t = para.text.strip()
                    if t:
                        texts.append(t)
        all_text = " ".join(texts)
        assert "950" in all_text or "1.2" in all_text, "Bullet items should be rendered in PPTX"

    def test_findings_slide_with_li(self, converter, temp_dir):
        html = """
        <section class="slide" data-type="findings" data-page="1">
            <h2>核心指标</h2>
            <ul>
                <li>950万辆 同比+37.5%</li>
                <li>1.2万亿元 市场规模</li>
                <li>40.3% 渗透率</li>
            </ul>
        </section>
        """
        output_path = os.path.join(temp_dir, "findings.pptx")
        result = converter.convert(html, output_path)
        assert result.success is True


class TestRendererFontFromDesign:
    def test_renderer_uses_design_font(self):
        """SlideRenderer must read the default font from the design dict."""
        from src.converters.slide_renderer import SlideRenderer

        design = {"font_default": "SimHei"}
        renderer = SlideRenderer(design)
        assert renderer.default_font == "SimHei"

    def test_renderer_font_defaults_to_yahei(self):
        from src.converters.slide_renderer import SlideRenderer

        renderer = SlideRenderer({})
        assert renderer.default_font == "Microsoft YaHei"


class TestThemeIntegration:
    def test_design_attribute_comes_from_theme(self):
        """Converter must build its palette from the theme loader, not a hardcoded dict."""
        from src.converters.html_to_ppt import HTMLToPPTConverter
        from src.converters.ppt_theme import DEFAULT_THEME

        converter = HTMLToPPTConverter()
        assert converter.design["colors"]["navy"] == DEFAULT_THEME["colors"]["navy"]

    def test_css_overrides_theme(self):
        from src.converters.html_to_ppt import HTMLToPPTConverter

        template_html = "<html><head><style>.slide.cover h1{color:#FF0000;font-family:'SimHei'}</style></head><body></body></html>"
        converter = HTMLToPPTConverter()
        design = converter._build_design(template_html=template_html)
        assert design["colors"]["gold"] == "FF0000"
        assert design["font_default"] == "SimHei"

    def test_design_without_template_uses_theme(self):
        from src.converters.html_to_ppt import HTMLToPPTConverter

        converter = HTMLToPPTConverter()
        design = converter._build_design(template_html=None)
        assert design["colors"]["gold"] == "C9A227"

    def test_renderer_resolves_colors_from_nested_design(self):
        from src.converters.slide_renderer import SlideRenderer

        design = {"colors": {"navy": "1A2744"}, "fonts": {}, "font_default": "Microsoft YaHei"}
        renderer = SlideRenderer(design)
        assert renderer._resolve_color("navy") == "1A2744"
        assert renderer._resolve_color("#FF0000") == "#FF0000"


class TestTemplateHtmlForwarding:
    def test_conversion_with_template_does_not_crash(self):
        """Guard: convert(template_html=...) is the wired path used by all 3 call sites."""
        import tempfile

        from src.converters.html_to_ppt import HTMLToPPTConverter

        template_html = "<html><head><style>.slide.cover h1{color:#C9A227}</style></head><body></body></html>"
        html = "<section class='slide' data-type='cover'><h1>T</h1></section>"
        # Converter's _is_safe_path sandbox restricts output to the workspace,
        # so use a workspace-local temp dir instead of pytest tmp_path.
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            out = Path(tmpdir) / "out.pptx"
            result = HTMLToPPTConverter().convert(
                html=html, output_path=str(out), template_html=template_html
            )
            assert result.success


class TestChartMetadataPropagation:
    def _parse(self, html: str):
        from src.converters.base_parser import SlideElementParser

        parser = SlideElementParser()
        parser.feed(html)
        return parser.get_slides()

    def test_img_with_data_image_type_becomes_chart(self):
        html = (
            "<section class='slide' data-type='content'><h2>T</h2>"
            "<img src='/charts/bar_x.png' alt='c' data-image-type='chart' data-chart-type='bar'>"
            "</section>"
        )
        slides = self._parse(html)
        assert slides[0]["images"][0]["image_type"] == "chart"
        assert slides[0]["images"][0]["chart_type"] == "bar"

    def test_plain_img_has_no_image_type(self):
        html = (
            "<section class='slide' data-type='content'><h2>T</h2>"
            "<img src='/img/photo.png' alt='p'></section>"
        )
        slides = self._parse(html)
        assert "image_type" not in slides[0]["images"][0]

    def test_data_source_survives_image_attrs_shadowing(self):
        html = (
            "<section class='slide' data-type='content' data-source='IDC 2025'><h2>T</h2>"
            "<img src='/charts/bar_x.png' alt='c' data-image-type='chart'>"
            "</section>"
        )
        slides = self._parse(html)
        assert slides[0].get("source_text") == "IDC 2025"
        assert slides[0]["images"][0]["image_type"] == "chart"


class TestChartAspectFit:
    def test_chart_detection_prefers_metadata(self):
        """image_type=chart wins over filename; plain name no longer misdetects."""
        from src.converters.slide_renderer import SlideRenderer

        renderer = SlideRenderer({})
        assert renderer._is_chart_image({"image_type": "chart", "src": "/x/photo.png"})
        assert not renderer._is_chart_image({"src": "/x/photo.png"})
        # 回退：无元数据时保留文件名启发
        assert renderer._is_chart_image({"src": "/x/bar_revenue.png"})

    def test_extract_pptx_picture_sizes(self, tmp_path):
        """Charts fit inside the slot preserving aspect ratio (PIL available)."""
        import os
        import tempfile

        from PIL import Image as PILImage
        from pptx import Presentation
        from pptx.util import Inches

        from src.converters.slide_renderer import SlideRenderer

        with tempfile.TemporaryDirectory(dir=os.getcwd()) as td:
            wide = os.path.join(td, "bar_wide.png")
            PILImage.new("RGB", (400, 200)).save(wide)  # 2:1 wide chart

            prs = Presentation()
            prs.slide_width = Inches(13.333)
            prs.slide_height = Inches(7.5)
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            renderer = SlideRenderer({})
            slot = {"id": "chart", "position": {"left": 6.0, "top": 1.6, "width": 6.4, "height": 5.2}}
            slide_data = {"images": [{"src": wide, "image_type": "chart"}]}
            renderer._render_image_slot(slide, slot, slide_data, {})
            pic = [sh for sh in slide.shapes if sh.shape_type == 13][0]  # PICTURE
            # 槽位宽高比 6.4/5.2 > 2 → 受宽度约束：w=6.4, h=3.2，等比 2:1
            assert abs(pic.width / pic.height - 2.0) < 0.05
            assert pic.width <= Inches(6.4) + 1000  # EMU 容差
