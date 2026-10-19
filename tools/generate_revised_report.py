# -*- coding: utf-8 -*-
"""生成修订后的HTML和Word报告 - 标题层级统一版"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.converters.html_to_word import HTMLToWordConverter

with open(ROOT / 'output' / 'full_research' / 'semiconductor_revised_report_llm.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

template = (ROOT / 'templates' / 'professional_report.html').read_text(encoding='utf-8')

cn_nums = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']

toc_lines = []
page_num = 3
for i, section in enumerate(data.get('sections', []), 1):
    title = section.get('title', '')
    num = cn_nums[i-1] if i <= len(cn_nums) else str(i)
    toc_lines.append(
        '<p class="toc-item-level1">{}、{}  ......  {}</p>'.format(num, title, page_num)
    )
    page_num += 3
toc_html = '\n'.join(toc_lines)


def strip_markdown(text):
    """清理markdown格式"""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    return text.strip()


def clean_heading_numbering(text):
    """清理标题中的冗余编号：'1. xxx' -> 'xxx', '一、xxx' -> 'xxx'"""
    text = strip_markdown(text)
    text = re.sub(r'^[①②③④⑤⑥⑦⑧⑨⑩]\s*', '', text)
    text = re.sub(r'^\d+[.、]\s*', '', text)
    text = re.sub(r'^[一二三四五六七八九十]+[、.]\s*', '', text)
    text = re.sub(r'^第[一二三四五六七八九十]+部分[：:]\s*', '', text)
    return text.strip()


def content_to_html(content):
    """将markdown内容转为HTML，自动修正标题层级"""
    lines = content.split('\n')
    heading_lines = []

    for idx, line in enumerate(lines):
        m = re.match(r'^(#{1,6})\s+(.+)$', line.strip())
        if m:
            level = len(m.group(1))
            text = clean_heading_numbering(m.group(2))
            heading_lines.append((idx, level, text))

    has_h2 = any(level == 2 for _, level, _ in heading_lines)

    if not has_h2 and heading_lines:
        new_lines = list(lines)
        for idx, level, text in heading_lines:
            if level == 3:
                new_lines[idx] = '## {}'.format(text)
            elif level == 4:
                new_lines[idx] = '### {}'.format(text)
            elif level < 3:
                new_lines[idx] = '## {}'.format(text)
        lines = new_lines

    parts = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or '全球与中国市场统计口径不同' in line:
            i += 1
            continue

        if line.startswith('|'):
            headers, rows, end_idx = parse_table_block(lines, i)
            if headers:
                parts.append('<table><thead><tr>')
                for h in headers:
                    parts.append('<th>{}</th>'.format(h))
                parts.append('</tr></thead><tbody>')
                for row in rows:
                    parts.append('<tr>')
                    for cell in row:
                        parts.append('<td>{}</td>'.format(cell))
                    parts.append('</tr>')
                parts.append('</tbody></table>')
            i = end_idx
            continue

        m = re.match(r'^(#{2,4})\s+(.+)$', line)
        if m:
            level = len(m.group(1))
            t = clean_heading_numbering(m.group(2))
            if level == 2:
                parts.append('<h2 class="section-title">{}</h2>'.format(t))
            elif level == 3:
                parts.append('<h3 class="subsection-title">{}</h3>'.format(t))
            elif level == 4:
                parts.append('<h4 class="sub-subsection-title">{}</h4>'.format(t))
            i += 1
            continue

        if line.startswith('- ') or line.startswith('* '):
            text = strip_markdown(line[2:])
            if text:
                parts.append('<li>{}</li>'.format(text))
            i += 1
            continue

        m2 = re.match(r'^(\d+)[.、]\s*(.+)$', line)
        if m2:
            text = strip_markdown(m2.group(2))
            if text:
                parts.append('<li>{}</li>'.format(text))
            i += 1
            continue

        text = strip_markdown(line)
        text = re.sub(r'<[^>]+>', '', text).strip()
        if text:
            parts.append('<p>{}</p>'.format(text))
        i += 1

    return '\n'.join(parts)


def parse_table_block(lines, start_idx):
    """解析连续表格行"""
    headers = []
    rows = []
    idx = start_idx
    while idx < len(lines):
        line = lines[idx].strip()
        if not line.startswith('|'):
            break
        cells = [c.strip() for c in line.split('|')]
        if line.endswith('|'):
            cells = cells[1:-1]
        else:
            cells = cells[1:]
        if not cells:
            break
        if all(set(c) <= set('- :') for c in cells if c):
            idx += 1
            continue
        cleaned = [strip_markdown(c) for c in cells]
        if not headers:
            headers = cleaned
        else:
            rows.append(cleaned)
        idx += 1
    return headers, rows, idx


def renumber_section(section_html):
    """章节内重新编号：H2->1. H3->(1) H4->①"""
    h2_count = [0]
    def rw_h2(m):
        h2_count[0] += 1
        return '<h2 class="section-title">{}. {}</h2>'.format(h2_count[0], m.group(1))

    h3_count = [0]
    def rw_h3(m):
        h3_count[0] += 1
        return '<h3 class="subsection-title">（{}）{}</h3>'.format(h3_count[0], m.group(1))

    h4_count = [0]
    cn4 = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨']
    def rw_h4(m):
        h4_count[0] += 1
        p = cn4[h4_count[0]-1] if h4_count[0] <= len(cn4) else str(h4_count[0])
        return '<h4 class="sub-subsection-title">{}{}</h4>'.format(p, m.group(1))

    r = re.sub(r'<h2 class="section-title">(.*?)</h2>', rw_h2, section_html)
    r = re.sub(r'<h3 class="subsection-title">(.*?)</h3>', rw_h3, r)
    r = re.sub(r'<h4 class="sub-subsection-title">(.*?)</h4>', rw_h4, r)
    return r


content_parts = []
for i, section in enumerate(data.get('sections', []), 1):
    title = section.get('title', '')
    num = cn_nums[i-1] if i <= len(cn_nums) else str(i)
    content_parts.append('<h1 class="chapter-title">{}、{}</h1>'.format(num, title))

    raw_content = section.get('content', '')
    section_html = content_to_html(raw_content)
    section_html = renumber_section(section_html)
    content_parts.append(section_html)

content_html = '\n'.join(content_parts)

html = template.replace('{{title}}', data.get('topic', '中国新能源汽车行业深度研究'))
html = html.replace('{{subtitle}}', data.get('topic', '中国新能源汽车行业深度研究报告'))
html = html.replace('{{date}}', datetime.now().strftime('%Y年%m月'))
html = html.replace('{{report_type}}', '行业深度研究')
html = html.replace('{{toc_items}}', toc_html)
html = html.replace('{{content}}', content_html)
html = html.replace('{{page_num}}', '1')

html_file = ROOT / 'output' / 'full_research' / 'revised_report.html'
html_file.write_text(html, encoding='utf-8')
print('HTML saved:', html_file)

converter = HTMLToWordConverter()
result = converter.convert(html=html, output_path=str(ROOT / 'output' / 'full_research' / 'revised_report.docx'))
print('Word result:', result.to_dict())
