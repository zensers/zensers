# -*- coding: utf-8 -*-
"""
Word 排版设计令牌与 OOxml 工具函数
==================================

为研究报告 Word 排版规范提供统一的设计令牌与底层 OOxml 操作，
供 html_to_word 转换器调用：

- 页面：A4（21 x 29.7cm），边距上下 2.54cm、左右 3.17cm
- 字体：标题黑体（SimHei）、正文宋体（SimSun）、西文 Times New Roman
- 色彩：藏青 NAVY / 金色 GOLD / 表头底纹等灰阶令牌

python-docx 1.2.0 无原生域（field）API，fldChar/instrText 等
OOxml 结构在此手工构造。
"""

import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# ========== 色彩令牌 ==========
NAVY = "1A2744"                # 藏青：标题/三线表框线
GOLD = "C9A227"                # 金色：封面分隔线/强调
TABLE_HEADER_FILL = "E8EDF4"   # 表头浅藏青底纹
COVER_META_FILL = "F5F6F8"     # 封面元信息区浅灰底纹
GRAY_TEXT = "8C8C8C"           # 页眉页脚灰

# ========== 字体令牌 ==========
FONT_HEADING_CN = "SimHei"         # 标题黑体
FONT_BODY_CN = "SimSun"            # 正文宋体
FONT_WESTERN = "Times New Roman"   # 西文

# ========== 页面令牌 ==========
PAGE_WIDTH_CM = 21.0
PAGE_HEIGHT_CM = 29.7
MARGIN_TOP_BOTTOM_CM = 2.54
MARGIN_LEFT_RIGHT_CM = 3.17
CONTENT_WIDTH_CM = PAGE_WIDTH_CM - 2 * MARGIN_LEFT_RIGHT_CM  # ≈14.66cm

# ========== 图片规格 ==========
IMAGE_MAX_WIDTH_CM = 14.7       # 正文可用宽上限
IMAGE_SQUARE_MAX_CM = 11.0      # 饼/雷达等近方形图上限
IMAGE_ASSUME_DPI = 200          # 图表渲染 DPI 标准
IMAGE_FALLBACK_WIDTH_CM = 12.7  # PIL 读取失败时的回退宽度

# 剥离标题前导编号（"01 标题" / "第一章 标题" / "一、标题"）
_HEADING_NUMBER_PATTERN = re.compile(
    r"^\s*(第[一二三四五六七八九十百\d]+章|\d+(?:\.\d+)*|[一二三四五六七八九十]+、)\s*"
)


def strip_heading_number(text: str) -> str:
    """剥离标题前导编号，用于重复标题判断。

    "01 产业链全景" / "第一章 产业链全景" / "一、产业链全景" → "产业链全景"
    """
    return _HEADING_NUMBER_PATTERN.sub("", text or "", count=1).strip()


def _make_border_element(tag: str, val: str, sz: int, color: str) -> "OxmlElement":
    """构造单个边框元素（w:top/w:bottom/w:left/...）。"""
    el = OxmlElement(f"w:{tag}")
    el.set(qn("w:val"), val)
    el.set(qn("w:sz"), str(sz))
    el.set(qn("w:space"), "0")
    el.set(qn("w:color"), color)
    return el


def style_three_line_table(table) -> None:
    """应用三线表边框：上下 1pt 藏青粗线，左右/内线 none。

    w:sz 单位为 1/8 pt：1pt → sz=8。
    表头行内单元格的 0.5pt 下边线由调用方配合 tcBorders 处理。
    """
    tbl_pr = table._tbl.tblPr
    old = tbl_pr.find(qn("w:tblBorders"))
    if old is not None:
        tbl_pr.remove(old)

    borders = OxmlElement("w:tblBorders")
    borders.append(_make_border_element("top", "single", 8, NAVY))
    borders.append(_make_border_element("bottom", "single", 8, NAVY))
    for tag in ("left", "right", "insideH", "insideV"):
        borders.append(_make_border_element(tag, "none", 0, "auto"))

    # tblBorders 在 tblPr 子元素序列中位于 shd/tblLayout/tblCellMar/tblLook 之前
    tbl_pr.insert_element_before(
        borders, "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook"
    )


def mark_header_row_repeat(row) -> None:
    """给表头行加 w:trPr/w:tblHeader，跨页时自动重复表头。"""
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:tblHeader")) is None:
        tr_pr.append(OxmlElement("w:tblHeader"))


def add_field_run(paragraph, instr: str, placeholder: str = ""):
    """在段落内构造完整 Word 域结构，返回创建的 run 列表。

    结构：fldChar begin → instrText → fldChar separate → 占位 run → fldChar end。
    用于 TOC、PAGE、NUMPAGES 等域；占位 run 的文本在域刷新前显示。
    """
    runs = []

    r_begin = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    r_begin._r.append(fld_begin)
    runs.append(r_begin)

    r_instr = paragraph.add_run()
    instr_el = OxmlElement("w:instrText")
    instr_el.set(qn("xml:space"), "preserve")
    instr_el.text = f" {instr} "
    r_instr._r.append(instr_el)
    runs.append(r_instr)

    r_sep = paragraph.add_run()
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    r_sep._r.append(fld_sep)
    runs.append(r_sep)

    r_ph = paragraph.add_run(placeholder)
    runs.append(r_ph)

    r_end = paragraph.add_run()
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    r_end._r.append(fld_end)
    runs.append(r_end)

    return runs


def set_update_fields_on_open(doc) -> None:
    """settings.xml 写入 w:updateFields val=true，Word/WPS 打开时自动刷新域。"""
    settings = doc.settings.element
    if settings.find(qn("w:updateFields")) is not None:
        return
    el = OxmlElement("w:updateFields")
    el.set(qn("w:val"), "true")
    # updateFields 在 settings 子元素序列中位于 compat/rsids/mathPr 等之前
    settings.insert_element_before(
        el,
        "w:hdrShapeDefaults", "w:footnotePr", "w:endnotePr", "w:compat",
        "w:rsids", "m:mathPr", "w:themeFontLang", "w:clrSchemeMapping",
        "w:doNotAutoCompressPictures", "w:shapeDefaults",
        "w:decimalSymbol", "w:listSeparator",
    )


def set_paragraph_bottom_border(paragraph, sz: int, color: str) -> None:
    """给段落加底边框（w:pPr/w:pBdr/w:bottom）。

    Args:
        sz: 边框粗细，单位 1/8 pt（如 1pt → 8，0.5pt → 4，2.25pt → 18）
        color: 十六进制颜色（不带 #）
    """
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        # pBdr 在 pPr 序列中位于 shd/tabs/spacing/ind/jc 等之前
        p_pr.insert_element_before(
            p_bdr,
            "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku",
            "w:wordWrap", "w:overflowPunct", "w:topLinePunct",
            "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd",
            "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing",
            "w:mirrorIndents", "w:suppressOverlap", "w:jc",
            "w:textDirection", "w:textAlignment", "w:textboxTightWrap",
            "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr",
            "w:pPrChange",
        )
    bottom = p_bdr.find(qn("w:bottom"))
    if bottom is None:
        bottom = OxmlElement("w:bottom")
        p_bdr.append(bottom)
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(sz))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)


def set_first_line_indent_chars(paragraph, chars: int = 200) -> None:
    """正文段落首行缩进（字符单位 + twips 兜底）。

    w:ind 同时写入 w:firstLineChars="200"（随字号缩放）与
    w:firstLine="420" twips（按 10.5pt 正文两字符兜底）。
    """
    from docx.shared import Pt

    # python-docx API 负责创建位置正确的 w:ind
    paragraph.paragraph_format.first_line_indent = Pt(21)  # 420 twips
    p_pr = paragraph._p.pPr
    if p_pr is None:
        return
    ind = p_pr.find(qn("w:ind"))
    if ind is not None:
        ind.set(qn("w:firstLineChars"), str(chars))


def shade_cell_or_paragraph(obj, fill: str) -> None:
    """给表格单元格（_Cell）或段落（Paragraph）加底纹 w:shd。"""
    if hasattr(obj, "_tc"):
        pr = obj._tc.get_or_add_tcPr()
    elif hasattr(obj, "_p"):
        pr = obj._p.get_or_add_pPr()
    else:
        raise TypeError(f"unsupported object: {type(obj)!r}")

    shd = pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        if hasattr(obj, "_tc"):
            # tcPr 序列：shd 位于 noWrap/tcMar/textDirection/vAlign/hideMark 之前
            pr.insert_element_before(
                shd, "w:noWrap", "w:tcMar", "w:textDirection",
                "w:tcFitText", "w:vAlign", "w:hideMark",
            )
        else:
            # pPr 序列：shd 位于 tabs/spacing/ind/jc 等之前
            pr.insert_element_before(
                shd,
                "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
                "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE",
                "w:autoSpaceDN", "w:bidi", "w:adjustRightInd", "w:snapToGrid",
                "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents",
                "w:suppressOverlap", "w:jc", "w:textDirection",
                "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl",
                "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
            )
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)


def set_table_header_cell_border(cell, sz: int = 4, color: str = NAVY) -> None:
    """表头单元格加 0.5pt 底边线（w:tcPr/w:tcBorders/w:bottom）。"""
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        # tcBorders 在 tcPr 序列中位于 shd/noWrap/tcMar/vAlign 等之前
        tc_pr.insert_element_before(
            borders, "w:shd", "w:noWrap", "w:tcMar", "w:textDirection",
            "w:tcFitText", "w:vAlign", "w:hideMark",
        )
    bottom = borders.find(qn("w:bottom"))
    if bottom is None:
        bottom = OxmlElement("w:bottom")
        borders.append(bottom)
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(sz))
    bottom.set(qn("w:space"), "0")
    bottom.set(qn("w:color"), color)


def compute_image_width_cm(px_w: int, px_h: int) -> float:
    """按像素宽与 200dpi 计算图片插入宽度（cm），含上限规则。

    - 宽度 = min(14.7cm, 像素宽 / 200dpi)
    - 宽高比 < 1.3（饼/雷达等近方形图）上限 11cm
    """
    if px_w <= 0:
        return IMAGE_FALLBACK_WIDTH_CM
    width_cm = min(IMAGE_MAX_WIDTH_CM, px_w / float(IMAGE_ASSUME_DPI) * 2.54)
    if px_h > 0 and (px_w / float(px_h)) < 1.3:
        width_cm = min(width_cm, IMAGE_SQUARE_MAX_CM)
    return width_cm
