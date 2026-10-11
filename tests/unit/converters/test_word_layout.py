# -*- coding: utf-8 -*-
"""
Word 排版重构验收测试
=====================

构造最小 HTML → convert → 用 python-docx 重新打开输出文档，验证：
1. A4 页面与研报边距
2. 真 TOC 域与 updateFields 设置
3. 页脚 PAGE/NUMPAGES 域
4. H1 段前分页
5. 三线表（无 Table Grid、tblBorders、跨页重复表头 tblHeader）
6. 正文段首行缩进 w:firstLineChars="200"
7. 重复标题去重（H2 与前一 H1 去编号同文 → 跳过）
"""

import os
import tempfile

import pytest
from docx import Document
from docx.oxml.ns import qn

from src.converters.html_to_word import HTMLToWordConverter
from src.converters.word_styles import compute_image_width_cm, strip_heading_number


SAMPLE_HTML = """
<article>
    <div class="cover-page">
        <h1 class="cover-title">测试研究报告</h1>
        <p class="cover-badge">RESEARCH REPORT</p>
        <p class="cover-divider">━━━━━━━━━━</p>
        <p class="cover-meta">发布日期：2026年10月</p>
    </div>
    <div class="toc-page">
        <h2 class="toc-header">目 录</h2>
        <ul class="toc-list">
            <li class="toc-item toc-item-level1">01 产业链全景 3</li>
            <li class="toc-item toc-item-level2">01.1 核心结论 3</li>
        </ul>
    </div>
    <h1 class="chapter-title">01 产业链全景</h1>
    <h2 class="section-title">产业链全景</h2>
    <p>这是需要验证首行缩进的正文段落内容。</p>
    <table>
        <thead><tr><th>指标</th><th>数值</th></tr></thead>
        <tbody>
            <tr><td>市场规模</td><td>1.2万亿</td></tr>
            <tr><td>增长率</td><td>25%</td></tr>
        </tbody>
    </table>
</article>
"""


@pytest.fixture(scope="module")
def converted(tmp_path_factory):
    """转换一次并重新打开，供本模块所有断言复用"""
    out_dir = tmp_path_factory.mktemp("word_layout")
    output_path = os.path.join(str(out_dir), "layout.docx")
    converter = HTMLToWordConverter()
    result = converter.convert(SAMPLE_HTML, output_path)
    assert result.success is True
    return Document(output_path)


class TestWordPageSetup:
    """页面设置：A4 + 研报边距"""

    def test_a4_page_size(self, converted):
        section = converted.sections[0]
        assert abs(section.page_width.cm - 21.0) < 0.05
        assert abs(section.page_height.cm - 29.7) < 0.05

    def test_report_margins(self, converted):
        section = converted.sections[0]
        assert abs(section.top_margin.cm - 2.54) < 0.05
        assert abs(section.bottom_margin.cm - 2.54) < 0.05
        assert abs(section.left_margin.cm - 3.17) < 0.05
        assert abs(section.right_margin.cm - 3.17) < 0.05


class TestTocField:
    """目录：真 TOC 域 + updateFields"""

    def test_toc_field_exists(self, converted):
        body_xml = converted.element.xml
        assert 'TOC \\o' in body_xml

    def test_toc_placeholder_items_removed(self, converted):
        """目录区的手写目录条目不再输出为正文段落"""
        toc_texts = [p.text for p in converted.paragraphs if "核心结论" in p.text]
        assert toc_texts == []

    def test_update_fields_on_open(self, converted):
        settings_xml = converted.settings.element.xml
        assert "updateFields" in settings_xml
        assert 'w:val="true"' in settings_xml


class TestHeaderFooter:
    """页眉页脚：底边框 + PAGE/NUMPAGES 域"""

    def test_footer_contains_page_fields(self, converted):
        footer_xml = converted.sections[0].footer._element.xml
        assert "PAGE" in footer_xml
        assert "NUMPAGES" in footer_xml

    def test_footer_contains_page_number_text(self, converted):
        footer_texts = "".join(p.text for p in converted.sections[0].footer.paragraphs)
        assert "第 " in footer_texts and " 页 共 " in footer_texts

    def test_header_bottom_border(self, converted):
        header_para = converted.sections[0].header.paragraphs[0]
        p_pr = header_para._p.pPr
        assert p_pr is not None
        p_bdr = p_pr.find(qn("w:pBdr"))
        assert p_bdr is not None
        bottom = p_bdr.find(qn("w:bottom"))
        assert bottom is not None
        assert bottom.get(qn("w:sz")) == "4"
        assert bottom.get(qn("w:color")) == "1A2744"

    def test_header_contains_brand(self, converted):
        header_text = converted.sections[0].header.paragraphs[0].text
        assert "ZENSERS" in header_text


class TestHeadingTypography:
    """标题排版：H1 分页 + 重复标题去重"""

    def test_h1_page_break_before(self, converted):
        h1_paras = [p for p in converted.paragraphs if p.style.name == "Heading 1"]
        assert h1_paras, "应存在 Heading 1 段落"
        assert h1_paras[0].paragraph_format.page_break_before is True

    def test_h1_bottom_border(self, converted):
        h1_paras = [p for p in converted.paragraphs if p.style.name == "Heading 1"]
        p_bdr = h1_paras[0]._p.pPr.find(qn("w:pBdr"))
        assert p_bdr is not None
        bottom = p_bdr.find(qn("w:bottom"))
        assert bottom.get(qn("w:sz")) == "8"
        assert bottom.get(qn("w:color")) == "1A2744"

    def test_duplicate_h2_after_h1_skipped(self, converted):
        """<h1>01 产业链全景</h1><h2>产业链全景</h2> 只产出 1 个正文 heading"""
        headings = [p.text for p in converted.paragraphs if p.style.name.startswith("Heading")]
        assert headings == ["01 产业链全景"]

    def test_cover_title_not_styled_as_heading(self, converted):
        """封面主标题不占用 Heading 样式，也不更新去重状态"""
        cover_paras = [p for p in converted.paragraphs if p.text == "测试研究报告"]
        assert cover_paras and cover_paras[0].style.name != "Heading 1"


class TestBodyParagraph:
    """正文段落：首行缩进 2 字符"""

    def test_first_line_indent_chars(self, converted):
        body_paras = [p for p in converted.paragraphs if "首行缩进" in p.text]
        assert body_paras, "应存在正文段落"
        ind = body_paras[0]._p.pPr.find(qn("w:ind"))
        assert ind is not None
        assert ind.get(qn("w:firstLineChars")) == "200"
        assert ind.get(qn("w:firstLine")) == "420"

    def test_normal_style_simsun_exact_22pt(self, converted):
        normal = converted.styles["Normal"]
        assert normal.font.size.pt == 10.5
        assert normal.font.name == "Times New Roman"
        east_asia = normal._element.rPr.rFonts.get(qn("w:eastAsia"))
        assert east_asia == "SimSun"


class TestThreeLineTable:
    """表格：三线表 + 跨页重复表头"""

    def test_no_table_grid_style(self, converted):
        table = converted.tables[0]
        tbl_pr = table._tbl.tblPr
        assert tbl_pr.find(qn("w:tblStyle")) is None
        assert "Table Grid" not in table._tbl.xml

    def test_tbl_borders_exist(self, converted):
        table = converted.tables[0]
        tbl_pr = table._tbl.tblPr
        borders = tbl_pr.find(qn("w:tblBorders"))
        assert borders is not None
        top = borders.find(qn("w:top"))
        assert top.get(qn("w:sz")) == "8"
        assert top.get(qn("w:color")) == "1A2744"
        assert borders.find(qn("w:insideV")).get(qn("w:val")) == "none"

    def test_header_row_repeat(self, converted):
        table = converted.tables[0]
        tr_pr = table.rows[0]._tr.trPr
        assert tr_pr is not None
        assert tr_pr.find(qn("w:tblHeader")) is not None

    def test_header_cell_shading(self, converted):
        table = converted.tables[0]
        tc_pr = table.rows[0].cells[0]._tc.tcPr
        shd = tc_pr.find(qn("w:shd"))
        assert shd is not None
        assert shd.get(qn("w:fill")) == "E8EDF4"


class TestWordStyleHelpers:
    """word_styles 工具函数单测"""

    def test_strip_heading_number_variants(self):
        assert strip_heading_number("01 产业链全景") == "产业链全景"
        assert strip_heading_number("第三章 市场规模") == "市场规模"
        assert strip_heading_number("一、供应商名录") == "供应商名录"
        assert strip_heading_number("01.2 子标题") == "子标题"
        assert strip_heading_number("无编号标题") == "无编号标题"

    def test_compute_image_width_wide(self):
        # 9×5.2in @200dpi = 1800×1040 → 宽度受 14.7cm 上限约束
        assert compute_image_width_cm(1800, 1040) == pytest.approx(14.7)

    def test_compute_image_width_small(self):
        # 800×400px @200dpi = 10.16cm（未触上限）
        assert compute_image_width_cm(800, 400) == pytest.approx(10.16, abs=0.01)

    def test_compute_image_width_square_capped(self):
        # 近方形（宽高比<1.3）上限 11cm
        assert compute_image_width_cm(1000, 900) == pytest.approx(11.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
