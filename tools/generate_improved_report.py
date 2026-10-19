# -*- coding: utf-8 -*-
"""
改进的HTML报告生成器 - 符合专业咨询公司标准
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def clean_markdown(text):
    """清理Markdown格式，保留纯文本"""
    if not text:
        return ""
    # 移除粗体标记
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # 移除斜体标记
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # 移除代码标记
    text = re.sub(r'`(.+?)`', r'\1', text)
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', '', text)
    # 移除多余的空格
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def remove_repetitive_content(text):
    """删除重复的废话内容"""
    if not text:
        return text
    
    # 需要删除的重复语句模式
    repetitive_patterns = [
        r'全球与中国市场统计口径不同，本文不将两者直接合并比较。',
        r'全球与中国市场统计口径不同[^。]*',
        r'据中国汽车工业协会数据[，,]',
        r'据行业调研数据[（(][^)）]*[)）]',
        r'据[^。]*研究报告[，,]?',
        r'\*\*$',  # 末尾的 **
    ]
    
    for pattern in repetitive_patterns:
        text = re.sub(pattern, '', text)
    
    # 清理多余的标点和空格
    text = re.sub(r'[，,]{2,}', '，', text)
    text = re.sub(r'[。]{2,}', '。', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'^\s*[，,。]\s*', '', text)
    text = re.sub(r'\s*[，,。]\s*$', '', text)
    
    return text.strip()


def format_number(num_str):
    """格式化数字，添加千位分隔符"""
    try:
        if isinstance(num_str, (int, float)):
            return f"{num_str:,.1f}"
        num_str = str(num_str).replace(',', '').replace('，', '')
        if '.' in num_str:
            return f"{float(num_str):,.1f}"
        return f"{int(num_str):,}"
    except:
        return str(num_str)


def generate_table_html(headers, rows, caption=""):
    """生成标准的HTML表格"""
    if not headers or not rows:
        return ""
    
    html = '<table>\n'
    if caption:
        html += f'<caption>{caption}</caption>\n'
    
    # 表头
    html += '<thead><tr>\n'
    for header in headers:
        html += f'<th>{clean_markdown(header)}</th>\n'
    html += '</tr></thead>\n'
    
    # 数据行
    html += '<tbody>\n'
    for row in rows:
        html += '<tr>\n'
        for cell in row:
            html += f'<td>{clean_markdown(str(cell))}</td>\n'
        html += '</tr>\n'
    html += '</tbody>\n'
    html += '</table>\n'
    
    return html


def generate_improved_report_html(data):
    """生成改进的HTML报告，符合专业咨询公司标准"""
    
    topic = data.get('topic', '中国新能源汽车行业深度研究')
    sections = data.get('sections', [])
    key_findings = data.get('key_findings', [])
    
    # 读取模板
    template_path = ROOT / 'templates' / 'professional_report.html'
    template = template_path.read_text(encoding='utf-8')
    
    # 生成目录
    toc_items = []
    for i, section in enumerate(sections, 1):
        title = section.get('title', f'第{i}章')
        toc_items.append(f'''
            <li class="toc-item">
                <span class="chapter-num">{i:02d}</span>
                <span class="chapter-title">{title}</span>
                <span class="chapter-page">{i + 2}</span>
            </li>
        ''')
    toc_html = '\n'.join(toc_items)
    
    # 生成关键发现
    key_findings_html = ''
    if key_findings:
        key_findings_html = '<div class="key-findings"><h2>关键发现</h2><ul>\n'
        for finding in key_findings:
            key_findings_html += f'<li>{clean_markdown(finding)}</li>\n'
        key_findings_html += '</ul></div>\n'
    
    # 生成正文内容
    content_parts = []
    for i, section in enumerate(sections, 1):
        title = section.get('title', f'第{i}章')
        content = section.get('content', '')
        
        # 章节标题
        content_parts.append(f'<h1 class="chapter-title">{i:02d} {title}</h1>')
        
        # 解析内容
        lines = content.split('\n')
        in_table = False
        table_headers = []
        table_rows = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 处理Markdown表格
            if line.startswith('|') and line.endswith('|'):
                cells = [c.strip() for c in line.split('|')[1:-1]]
                # 跳过分隔行
                if all(set(c.strip()) <= set('- :') for c in cells if c.strip()):
                    continue
                # 清理单元格内容
                cleaned_cells = []
                for cell in cells:
                    cell = clean_markdown(cell)
                    cleaned_cells.append(cell)
                
                if not in_table:
                    in_table = True
                    table_headers = cleaned_cells
                else:
                    table_rows.append(cleaned_cells)
                continue
            
            # 如果不在表格中，但遇到了非表格行
            if in_table:
                # 输出表格
                if table_headers and table_rows:
                    content_parts.append(generate_table_html(table_headers, table_rows))
                in_table = False
                table_headers = []
                table_rows = []
            
            # 处理标题
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                title_text = line.lstrip('#').strip()
                if level == 1:
                    content_parts.append(f'<h2 class="section-title">{title_text}</h2>')
                elif level == 2:
                    content_parts.append(f'<h3 class="subsection-title">{title_text}</h3>')
                elif level == 3:
                    content_parts.append(f'<h4 class="sub-subsection-title">{title_text}</h4>')
                continue
            
            # 处理列表项
            if line.startswith('- ') or line.startswith('* '):
                content_parts.append(f'<li>{clean_markdown(line[2:])}</li>')
                continue
            
            # 处理数字列表
            num_match = re.match(r'^(\d+)[.、]\s*(.+)$', line)
            if num_match:
                content_parts.append(f'<li>{clean_markdown(num_match.group(2))}</li>')
                continue
            
            # 处理普通段落
            cleaned = remove_repetitive_content(clean_markdown(line))
            if cleaned:  # 只添加非空内容
                content_parts.append(f'<p>{cleaned}</p>')
        
        # 处理最后一个表格
        if in_table and table_headers and table_rows:
            content_parts.append(generate_table_html(table_headers, table_rows))
    
    content_html = '\n'.join(content_parts)
    
    # 替换模板变量
    html = template.replace('{{title}}', topic)
    if '研究' in topic:
        html = html.replace('{{subtitle}}', f'{topic}报告')
    else:
        html = html.replace('{{subtitle}}', f'{topic}研究报告')
    html = html.replace('{{date}}', datetime.now().strftime('%Y年%m月'))
    html = html.replace('{{report_type}}', '行业深度研究')
    html = html.replace('{{toc_items}}', toc_html)
    html = html.replace('{{content}}', key_findings_html + content_html)
    html = html.replace('{{page_num}}', '1')
    
    return html


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='改进的HTML报告生成器')
    parser.add_argument('--input', required=True, help='输入JSON文件路径')
    parser.add_argument('--output', help='输出目录')
    
    args = parser.parse_args()
    
    # 读取JSON数据
    json_path = Path(args.input)
    if not json_path.exists():
        print(f'文件不存在: {json_path}')
        return
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 设置输出目录
    if args.output:
        out_dir = Path(args.output)
    else:
        out_dir = json_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成HTML
    html_content = generate_improved_report_html(data)
    
    # 保存HTML
    html_file = out_dir / 'improved_report.html'
    html_file.write_text(html_content, encoding='utf-8')
    
    # 转换为Word
    from src.converters.html_to_word import HTMLToWordConverter
    converter = HTMLToWordConverter()
    word_result = converter.convert(
        html_content,
        str(out_dir / 'improved_report.docx')
    )
    
    print(f'报告生成完成!')
    print(f'  - HTML: {html_file}')
    print(f'  - Word: {out_dir / "improved_report.docx"}')
    
    return {
        'success': True,
        'html_file': str(html_file),
        'word_file': str(out_dir / 'improved_report.docx'),
    }


if __name__ == '__main__':
    main()
