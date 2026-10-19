# -*- coding: utf-8 -*-
"""
重新生成报告脚本

从保存的JSON数据重新生成HTML和Word文档。
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def generate_toc_html(sections: List[Dict[str, Any]]) -> str:
    """生成目录 HTML"""
    toc_items = []
    for i, section in enumerate(sections, 1):
        title = section.get("title", f"第{i}章")
        toc_items.append(f'''
            <li class="toc-item">
                <span class="chapter-num">{i:02d}</span>
                <span class="chapter-title">{title}</span>
                <span class="chapter-page">{i + 2}</span>
            </li>
        ''')
    return "\n".join(toc_items)


def generate_content_html(sections: List[Dict[str, Any]]) -> str:
    """生成正文 HTML"""
    content_parts = []
    
    for i, section in enumerate(sections, 1):
        title = section.get("title", f"第{i}章")
        content = section.get("content", "")
        
        # 章节标题
        content_parts.append(f'<h1 class="chapter-title">{i:02d} {title}</h1>')
        
        # 章节内容（转换 Markdown 到 HTML）
        html_content = markdown_to_html(content)
        content_parts.append(f'<div class="section-content">{html_content}</div>')
    
    return "\n".join(content_parts)


def markdown_to_html(text: str) -> str:
    """简单的 Markdown 到 HTML 转换"""
    import re
    
    if not text:
        return ""
    
    lines = text.split('\n')
    html_lines = []
    in_table = False
    table_rows = []
    in_list = False
    list_type = None  # 'ul' or 'ol'
    
    def flush_table():
        """输出表格"""
        nonlocal in_table, table_rows
        if not table_rows:
            in_table = False
            return
        
        # 检查表格是否有效（至少有表头和分隔行）
        if len(table_rows) < 2:
            # 表格无效，作为普通文本处理
            for row in table_rows:
                html_lines.append(f'<p>{"|".join(row)}</p>')
            in_table = False
            table_rows = []
            return
        
        # 找到表头
        header_row = table_rows[0]
        num_cols = len(header_row)
        
        # 过滤掉分隔行（全是-和空格的行）
        data_rows = []
        for row in table_rows[1:]:
            # 检查是否是分隔行
            if all(set(cell.strip()) <= set('- :') for cell in row if cell.strip()):
                continue
            # 确保每行列数一致
            while len(row) < num_cols:
                row.append('')
            data_rows.append(row[:num_cols])
        
        if not data_rows:
            # 没有数据行，作为普通文本处理
            html_lines.append(f'<p>{"|".join(header_row)}</p>')
            in_table = False
            table_rows = []
            return
        
        # 输出表格
        html_lines.append('<table>')
        html_lines.append('<thead><tr>')
        for cell in header_row:
            cell_text = cell.strip()
            # 移除Markdown格式
            cell_text = re.sub(r'\*\*(.+?)\*\*', r'\1', cell_text)
            html_lines.append(f'<th>{cell_text}</th>')
        html_lines.append('</tr></thead>')
        html_lines.append('<tbody>')
        for row in data_rows:
            html_lines.append('<tr>')
            for cell in row:
                cell_text = cell.strip()
                # 移除Markdown格式
                cell_text = re.sub(r'\*\*(.+?)\*\*', r'\1', cell_text)
                html_lines.append(f'<td>{cell_text}</td>')
            html_lines.append('</tr>')
        html_lines.append('</tbody>')
        html_lines.append('</table>')
        
        in_table = False
        table_rows = []
    
    def flush_list():
        """结束列表"""
        nonlocal in_list, list_type
        if in_list:
            html_lines.append(f'</{list_type}>')
            in_list = False
            list_type = None
    
    for line in lines:
        stripped = line.strip()
        
        # 空行处理
        if not stripped:
            if in_table:
                flush_table()
            if in_list:
                flush_list()
            html_lines.append('')
            continue
        
        # 检查是否是表格行
        if stripped.startswith('|') and stripped.endswith('|'):
            if in_list:
                flush_list()
            if not in_table:
                in_table = True
            # 解析表格行
            cells = [cell.strip() for cell in stripped.split('|')[1:-1]]
            table_rows.append(cells)
            continue
        
        # 如果正在处理表格但当前行不是表格行，结束表格
        if in_table:
            flush_table()
        
        # 标题
        if stripped.startswith('#'):
            if in_list:
                flush_list()
            level = len(stripped) - len(stripped.lstrip('#'))
            title_text = stripped[level:].strip()
            if level == 1:
                html_lines.append(f'<h2 class="section-title">{title_text}</h2>')
            elif level == 2:
                html_lines.append(f'<h3 class="subsection-title">{title_text}</h3>')
            elif level == 3:
                html_lines.append(f'<h4 class="sub-subsection-title">{title_text}</h4>')
            continue
        
        # 无序列表项
        if stripped.startswith('- ') or stripped.startswith('* '):
            if in_table:
                flush_table()
            if not in_list or list_type != 'ul':
                if in_list:
                    flush_list()
                html_lines.append('<ul>')
                in_list = True
                list_type = 'ul'
            content = stripped[2:]
            # 处理粗体
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', content)
            # 确保内容不包含嵌套的HTML标签
            content = re.sub(r'<[^>]+>', '', content)
            html_lines.append(f'<li>{content}</li>')
            continue
        
        # 有序列表项 (支持 1. 或 1、格式)
        num_match = re.match(r'^(\d+)[.、]\s*(.+)$', stripped)
        if num_match:
            if in_table:
                flush_table()
            if not in_list or list_type != 'ol':
                if in_list:
                    flush_list()
                html_lines.append('<ol>')
                in_list = True
                list_type = 'ol'
            content = num_match.group(2)
            # 处理粗体
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', content)
            # 确保内容不包含嵌套的HTML标签
            content = re.sub(r'<[^>]+>', '', content)
            html_lines.append(f'<li>{content}</li>')
            continue
        
        # 如果是普通文本但正在列表中，结束列表
        if in_list:
            flush_list()
        
        # 处理粗体和斜体
        stripped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', stripped)
        stripped = re.sub(r'\*(.+?)\*', r'<em>\1</em>', stripped)
        
        # 普通段落 - 确保不包含嵌套的p标签
        stripped = re.sub(r'<p>', '', stripped)
        stripped = re.sub(r'</p>', '', stripped)
        html_lines.append(f'<p>{stripped}</p>')
    
    # 处理文件末尾的表格和列表
    if in_table:
        flush_table()
    if in_list:
        flush_list()
    
    return '\n'.join(html_lines)


def generate_report_html(
    topic: str,
    sections: List[Dict[str, Any]],
    exec_summary: str = "",
    key_findings: List[str] = None,
) -> str:
    """生成完整报告 HTML"""
    
    # 读取模板
    template_path = ROOT / "templates" / "professional_report.html"
    template = template_path.read_text(encoding="utf-8")
    
    # 生成目录
    toc_html = generate_toc_html(sections)
    
    # 生成正文
    content_html = generate_content_html(sections)
    
    # 添加关键发现
    if key_findings:
        findings_html = '<div class="key-findings"><h2>关键发现</h2><ul>'
        for finding in key_findings:
            findings_html += f'<li>{finding}</li>'
        findings_html += '</ul></div>'
        content_html = findings_html + content_html
    
    # 替换模板变量
    html = template.replace("{{title}}", topic)
    # 如果topic已经包含"研究"，则不重复添加
    if "研究" in topic:
        html = html.replace("{{subtitle}}", f"{topic}报告")
    else:
        html = html.replace("{{subtitle}}", f"{topic}研究报告")
    html = html.replace("{{date}}", datetime.now().strftime("%Y年%m月"))
    html = html.replace("{{report_type}}", "行业深度研究")
    html = html.replace("{{toc_items}}", toc_html)
    html = html.replace("{{content}}", content_html)
    html = html.replace("{{page_num}}", "1")
    
    return html


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="重新生成报告脚本")
    parser.add_argument("--input", required=True, help="输入JSON文件路径")
    parser.add_argument("--output", help="输出目录")
    
    args = parser.parse_args()
    
    # 读取JSON数据
    json_path = Path(args.input)
    if not json_path.exists():
        print(f"文件不存在: {json_path}")
        return
    
    data = json.loads(json_path.read_text(encoding="utf-8"))
    
    # 设置输出目录
    if args.output:
        out_dir = Path(args.output)
    else:
        out_dir = json_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取章节数据
    sections = data.get("sections", [])
    key_findings = data.get("key_findings", [])
    topic = data.get("topic", "中国新能源汽车行业深度研究")
    
    print(f"重新生成报告: {topic}")
    print(f"章节数量: {len(sections)}")
    
    # 生成HTML
    html_content = generate_report_html(
        topic=topic,
        sections=sections,
        key_findings=key_findings,
    )
    
    # 保存HTML
    html_file = out_dir / "report.html"
    html_file.write_text(html_content, encoding="utf-8")
    
    # 转换为Word
    from src.converters.html_to_word import HTMLToWordConverter
    converter = HTMLToWordConverter()
    word_result = converter.convert(
        html=html_content,
        output_path=str(out_dir / f"{topic}.docx"),
    )
    
    print(f"报告重新生成完成!")
    print(f"  - HTML: {html_file}")
    print(f"  - Word: {out_dir / f'{topic}.docx'}")
    
    return {
        "success": True,
        "html_file": str(html_file),
        "word_file": str(out_dir / f"{topic}.docx"),
    }


if __name__ == "__main__":
    main()
