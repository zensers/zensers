# -*- coding: utf-8 -*-
"""
zensers 行业研究报告 Word 模板生成器

生成带有 zensers 品牌标识的专业研究报告模板。
"""

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os


def set_cell_border(cell, **kwargs):
    """设置单元格边框"""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for edge in ('start', 'top', 'end', 'bottom', 'insideH', 'insideV'):
        edge_data = kwargs.get(edge)
        if edge_data:
            element = OxmlElement(f'w:{edge}')
            for key in ["sz", "val", "color", "space"]:
                if key in edge_data:
                    element.set(qn(f'w:{key}'), str(edge_data[key]))
            tcBorders.append(element)
    tcPr.append(tcBorders)


def add_watermark(doc, text="github.com/zensers/zensers"):
    """添加水印"""
    for section in doc.sections:
        header = section.header
        footer = section.footer
        
        # 添加页眉中的水印文字（简化版本，实际水印需要更复杂的XML操作）
        # 这里我们先用页脚来展示 GitHub URL
        pass


def create_template(output_path):
    """创建 zensers 行业研究报告模板"""
    doc = Document()
    
    # 设置默认字体
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial'
    font.size = Pt(11)
    font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    
    # 设置中文字体
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '思源黑体')
    
    # 设置页面边距
    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.18)
        section.right_margin = Cm(3.18)
    
    # ==================== 封面页 ====================
    
    # 添加空行
    for _ in range(4):
        doc.add_paragraph('')
    
    # Logo 占位符（实际使用时替换为真实 Logo）
    logo_para = doc.add_paragraph()
    logo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    logo_run = logo_para.add_run('[zensers Logo]')
    logo_run.font.size = Pt(14)
    logo_run.font.color.rgb = RGBColor(0x1a, 0x36, 0x5d)
    
    doc.add_paragraph('')
    
    # 副标题
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_run = subtitle.add_run('AI 驱动的行业研究平台')
    subtitle_run.font.size = Pt(14)
    subtitle_run.font.color.rgb = RGBColor(0x1a, 0x36, 0x5d)
    
    # 分隔线
    doc.add_paragraph('')
    separator = doc.add_paragraph()
    separator.alignment = WD_ALIGN_PARAGRAPH.CENTER
    separator_run = separator.add_run('═' * 50)
    separator_run.font.color.rgb = RGBColor(0xd6, 0x9e, 0x2e)
    
    doc.add_paragraph('')
    
    # 报告标题
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.add_run('报告标题')
    title_run.font.size = Pt(28)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(0x1a, 0x36, 0x5d)
    
    # 副标题
    subtitle2 = doc.add_paragraph()
    subtitle2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle2_run = subtitle2.add_run('副标题（可选）')
    subtitle2_run.font.size = Pt(16)
    subtitle2_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    
    doc.add_paragraph('')
    
    # 分隔线
    separator2 = doc.add_paragraph()
    separator2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    separator2_run = separator2.add_run('═' * 50)
    separator2_run.font.color.rgb = RGBColor(0xd6, 0x9e, 0x2e)
    
    doc.add_paragraph('')
    doc.add_paragraph('')
    
    # 发布信息
    info_para = doc.add_paragraph()
    info_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info_run = info_para.add_run('发布日期：2026年9月')
    info_run.font.size = Pt(12)
    info_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    
    version_para = doc.add_paragraph()
    version_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    version_run = version_para.add_run('版本：v1.0')
    version_run.font.size = Pt(12)
    version_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    
    doc.add_paragraph('')
    
    # GitHub 标识
    github_para = doc.add_paragraph()
    github_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    github_run = github_para.add_run('⭐ GitHub: zensers/zensers ⭐')
    github_run.font.size = Pt(12)
    github_run.font.bold = True
    github_run.font.color.rgb = RGBColor(0x1a, 0x36, 0x5d)
    
    # 分页
    doc.add_page_break()
    
    # ==================== 目录页 ====================
    
    toc_title = doc.add_heading('目录', level=1)
    
    toc_items = [
        ('执行摘要', '1'),
        ('研究背景与方法论', '2'),
        ('第一章 市场概况', '3'),
        ('第二章 竞争格局', '5'),
        ('第三章 技术趋势', '7'),
        ('第四章 风险分析', '9'),
        ('第五章 投资建议', '11'),
        ('数据来源与附录', '13'),
        ('免责声明', '14'),
        ('关于 zensers', '15'),
    ]
    
    for item, page in toc_items:
        toc_para = doc.add_paragraph()
        toc_run = toc_para.add_run(f'{item} {"." * (50 - len(item))} {page}')
        toc_run.font.size = Pt(11)
    
    doc.add_page_break()
    
    # ==================== 正文页面（带页眉页脚） ====================
    
    # 设置页眉
    section = doc.sections[0]
    header = section.header
    header_para = header.paragraphs[0]
    header_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    
    # Logo 占位符
    header_run1 = header_para.add_run('[zensers]  ')
    header_run1.font.size = Pt(9)
    header_run1.font.color.rgb = RGBColor(0x1a, 0x36, 0x5d)
    header_run1.font.bold = True
    
    # 报告标题（占位符）
    header_run2 = header_para.add_run('XX行业研究报告  ')
    header_run2.font.size = Pt(9)
    header_run2.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    
    # 页码
    header_run3 = header_para.add_run('第X页')
    header_run3.font.size = Pt(9)
    header_run3.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    
    # 设置页脚
    footer = section.footer
    footer_para = footer.paragraphs[0]
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # 分隔线
    footer_run1 = footer_para.add_run('─' * 60 + '\n')
    footer_run1.font.size = Pt(8)
    footer_run1.font.color.rgb = RGBColor(0xcc, 0xcc, 0xcc)
    
    # GitHub URL
    footer_run2 = footer_para.add_run('github.com/zensers/zensers')
    footer_run2.font.size = Pt(8)
    footer_run2.font.color.rgb = RGBColor(0x1a, 0x36, 0x5d)
    footer_run2.font.bold = True
    
    footer_run3 = footer_para.add_run('  |  ')
    footer_run3.font.size = Pt(8)
    footer_run3.font.color.rgb = RGBColor(0xcc, 0xcc, 0xcc)
    
    # 版权信息
    footer_run4 = footer_para.add_run('© 2026 zensers. 保留所有权利。')
    footer_run4.font.size = Pt(8)
    footer_run4.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    
    # ==================== 执行摘要 ====================
    
    doc.add_heading('执行摘要', level=1)
    
    summary_text = doc.add_paragraph()
    summary_text.add_run('核心发现：').font.bold = True
    
    findings = [
        '市场规模：XX行业2025年市场规模达到XX亿元，同比增长XX%。',
        '竞争格局：前五大企业市场份额合计XX%，行业集中度较高。',
        '技术趋势：AI技术正在重塑行业格局，预计2026年渗透率将达到XX%。',
        '投资建议：建议重点关注XX细分领域，预计未来3年复合增长率达XX%。',
    ]
    
    for finding in findings:
        bullet = doc.add_paragraph(finding, style='List Bullet')
    
    doc.add_paragraph('')
    
    # 风险提示
    risk_para = doc.add_paragraph()
    risk_run = risk_para.add_run('风险提示：')
    risk_run.font.bold = True
    risk_run.font.color.rgb = RGBColor(0xcc, 0x00, 0x00)
    
    risk_text = doc.add_paragraph('本报告基于公开数据和AI分析模型生成，预测结果仅供参考，不构成投资建议。')
    
    doc.add_page_break()
    
    # ==================== 研究背景与方法论 ====================
    
    doc.add_heading('研究背景与方法论', level=1)
    
    doc.add_heading('研究背景', level=2)
    doc.add_paragraph('本报告旨在全面分析XX行业的发展现状、竞争格局和未来趋势，为投资者和从业者提供决策参考。')
    
    doc.add_heading('研究方法', level=2)
    
    methods = [
        '数据采集：通过公开渠道获取行业数据，包括企业财报、行业报告、新闻资讯等。',
        '数据分析：采用多维度量化分析方法，结合统计学和机器学习技术。',
        '专家验证：关键结论经过行业专家审核验证。',
        'AI辅助：本报告由 zensers AI 系统辅助生成，经人工审核。',
    ]
    
    for method in methods:
        bullet = doc.add_paragraph(method, style='List Bullet')
    
    doc.add_heading('数据来源', level=2)
    doc.add_paragraph('详见附录《数据来源与方法论》。')
    
    doc.add_page_break()
    
    # ==================== 章节模板 ====================
    
    # 第一章
    doc.add_heading('第一章 市场概况', level=1)
    
    doc.add_heading('1.1 市场规模', level=2)
    doc.add_paragraph('[在此插入市场规模分析内容]')
    
    doc.add_heading('1.2 增长趋势', level=2)
    doc.add_paragraph('[在此插入增长趋势分析内容]')
    
    doc.add_heading('1.3 区域分布', level=2)
    doc.add_paragraph('[在此插入区域分布分析内容]')
    
    doc.add_page_break()
    
    # 第二章
    doc.add_heading('第二章 竞争格局', level=1)
    
    doc.add_heading('2.1 主要玩家', level=2)
    doc.add_paragraph('[在此插入主要玩家分析内容]')
    
    doc.add_heading('2.2 市场份额', level=2)
    doc.add_paragraph('[在此插入市场份额分析内容]')
    
    doc.add_heading('2.3 竞争策略', level=2)
    doc.add_paragraph('[在此插入竞争策略分析内容]')
    
    doc.add_page_break()
    
    # 第三章
    doc.add_heading('第三章 技术趋势', level=1)
    
    doc.add_heading('3.1 技术发展', level=2)
    doc.add_paragraph('[在此插入技术发展分析内容]')
    
    doc.add_heading('3.2 应用场景', level=2)
    doc.add_paragraph('[在此插入应用场景分析内容]')
    
    doc.add_heading('3.3 未来展望', level=2)
    doc.add_paragraph('[在此插入未来展望分析内容]')
    
    doc.add_page_break()
    
    # 第四章
    doc.add_heading('第四章 风险分析', level=1)
    
    doc.add_heading('4.1 市场风险', level=2)
    doc.add_paragraph('[在此插入市场风险分析内容]')
    
    doc.add_heading('4.2 政策风险', level=2)
    doc.add_paragraph('[在此插入政策风险分析内容]')
    
    doc.add_heading('4.3 技术风险', level=2)
    doc.add_paragraph('[在此插入技术风险分析内容]')
    
    doc.add_page_break()
    
    # 第五章
    doc.add_heading('第五章 投资建议', level=1)
    
    doc.add_heading('5.1 投资机会', level=2)
    doc.add_paragraph('[在此插入投资机会分析内容]')
    
    doc.add_heading('5.2 投资策略', level=2)
    doc.add_paragraph('[在此插入投资策略分析内容]')
    
    doc.add_heading('5.3 风险提示', level=2)
    doc.add_paragraph('[在此插入风险提示内容]')
    
    doc.add_page_break()
    
    # ==================== 附录 ====================
    
    doc.add_heading('数据来源与附录', level=1)
    
    doc.add_heading('数据来源', level=2)
    sources = [
        '国家统计局',
        '中国信息通信研究院',
        'IDC中国',
        'Gartner',
        '企业年报',
        '行业白皮书',
    ]
    
    for source in sources:
        bullet = doc.add_paragraph(source, style='List Bullet')
    
    doc.add_heading('方法论说明', level=2)
    doc.add_paragraph('[在此插入方法论详细说明]')
    
    doc.add_page_break()
    
    # ==================== 免责声明 ====================
    
    doc.add_heading('免责声明', level=1)
    
    disclaimers = [
        '本报告由 zensers AI 系统自动生成，经人工审核。',
        '本报告中的数据和分析基于公开信息，不保证数据的完整性和准确性。',
        '本报告中的预测和建议仅供参考，不构成投资建议。',
        '投资者应根据自身情况独立做出投资决策，本报告作者不承担任何责任。',
        '本报告版权归 zensers 所有，未经授权不得转载或引用。',
    ]
    
    for disclaimer in disclaimers:
        bullet = doc.add_paragraph(disclaimer, style='List Bullet')
    
    doc.add_page_break()
    
    # ==================== 关于 zensers ====================
    
    doc.add_heading('关于 zensers', level=1)
    
    doc.add_paragraph(
        'zensers 是一个开源的 AI 驱动行业研究平台，支持自动化数据采集与清洗、'
        '多维度质量评估、结构化报告生成和可定制的研究框架。'
    )
    
    doc.add_paragraph('')
    
    # GitHub 信息
    github_para = doc.add_paragraph()
    github_run = github_para.add_run('开源地址：')
    github_run.font.bold = True
    github_para.add_run('https://github.com/zensers/zensers')
    
    doc.add_paragraph('')
    
    doc.add_paragraph(
        '欢迎贡献代码、提交 Issue 或 Star 支持项目发展。'
    )
    
    doc.add_paragraph('')
    
    # 联系方式
    contact_para = doc.add_paragraph()
    contact_run = contact_para.add_run('联系我们：')
    contact_run.font.bold = True
    contact_para.add_run('GitHub Issues')
    
    # 保存文档
    doc.save(output_path)
    print(f'模板已生成：{output_path}')


if __name__ == '__main__':
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, 'zensers_report_template.docx')
    create_template(output_path)
