# -*- coding: utf-8 -*-
"""生成包含表格的完整HTML并用zensers转换器转Word"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.converters.html_to_word import HTMLToWordConverter

with open(ROOT / 'output' / 'real_new_energy_vehicle_report' / 'research_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

template = (ROOT / 'templates' / 'professional_report.html').read_text(encoding='utf-8')

# 目录 - 使用简单文本格式（避免嵌套span问题）
toc_lines = []
page_num = 3  # 从第3页开始

for i, section in enumerate(data['sections'], 1):
    title = section.get('title', '')
    # 一级目录 - 简单文本格式
    toc_lines.append(
        '<p class="toc-item-level1">{:02d}  {}  ......  {}</p>'.format(
            i, title, page_num
        )
    )
    
    # 从内容中提取二级标题
    content = section.get('content', '')
    sub_items = []
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('## '):
            sub_title = line[3:].strip()
            sub_items.append(sub_title)
    
    # 添加二级目录
    for j, sub_title in enumerate(sub_items[:5]):
        toc_lines.append(
            '<p class="toc-item-level2">    {:02d}.{} {}</p>'.format(
                i, j+1, sub_title
            )
        )
    
    page_num += max(2, len(sub_items) + 1)

toc_html = '\n'.join(toc_lines)

# 内容
content_parts = []

# 关键发现
if data.get('key_findings'):
    content_parts.append('<div class="key-findings"><h2>关键发现</h2><ul>')
    for finding in data['key_findings']:
        finding = re.sub(r'\*\*', '', finding).strip()
        if finding:
            content_parts.append('<li>{}</li>'.format(finding))
    content_parts.append('</ul></div>')

# 章节
for i, section in enumerate(data['sections'], 1):
    title = section.get('title', '')
    content_parts.append('<h1 class="chapter-title">{:02d} {}</h1>'.format(i, title))

    content = section.get('content', '')
    lines = content.split('\n')

    in_table = False
    table_headers = []
    table_rows = []

    for line in lines:
        line = line.strip()
        if not line or '全球与中国市场统计口径不同' in line:
            continue

        # 表格处理 - 支持不完整行（截断的数据）
        if line.startswith('|'):
            # 处理以|开头的行（可能是截断的表格行）
            if line.endswith('|'):
                cells = [c.strip() for c in line.split('|')[1:-1]]
            else:
                # 不完整的表格行，添加到上一行
                cells = [c.strip() for c in line.split('|')[1:]]
                if in_table and table_rows:
                    # 追加到上一行
                    last_row = table_rows[-1]
                    for c in cells:
                        if last_row:
                            last_row[-1] = last_row[-1] + ' ' + c
                    continue
                else:
                    continue
            
            # 跳过分隔行
            if all(set(c.strip()) <= set('- :') for c in cells if c.strip()):
                continue
            # 清理单元格
            cleaned = [re.sub(r'\*\*', '', c).strip() for c in cells]
            if not in_table:
                in_table = True
                table_headers = cleaned
            else:
                table_rows.append(cleaned)
            continue

        # 非表格行，输出之前的表格
        if in_table and table_headers:
            content_parts.append('<table><thead><tr>')
            for h in table_headers:
                content_parts.append('<th>{}</th>'.format(h))
            content_parts.append('</tr></thead><tbody>')
            for row in table_rows:
                content_parts.append('<tr>')
                for cell in row:
                    content_parts.append('<td>{}</td>'.format(cell))
                content_parts.append('</tr>')
            content_parts.append('</tbody></table>')
            in_table = False
            table_headers = []
            table_rows = []

        # 标题
        if line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            t = line.lstrip('#').strip()
            if level == 1:
                content_parts.append('<h2 class="section-title">{}</h2>'.format(t))
            elif level == 2:
                content_parts.append('<h3 class="subsection-title">{}</h3>'.format(t))
            continue

        # 列表
        if line.startswith('- ') or line.startswith('* '):
            text = line[2:]
            text = re.sub(r'\*\*', '', text).strip()
            if text:
                content_parts.append('<li>{}</li>'.format(text))
            continue

        # 数字列表
        m = re.match(r'^(\d+)[.、]\s*(.+)$', line)
        if m:
            text = m.group(2)
            text = re.sub(r'\*\*', '', text).strip()
            if text:
                content_parts.append('<li>{}</li>'.format(text))
            continue

        # 普通段落
        text = re.sub(r'\*\*', '', line)
        text = re.sub(r'<[^>]+>', '', text).strip()
        if text:
            content_parts.append('<p>{}</p>'.format(text))

    # 处理最后一个表格
    if in_table and table_headers:
        content_parts.append('<table><thead><tr>')
        for h in table_headers:
            content_parts.append('<th>{}</th>'.format(h))
        content_parts.append('</tr></thead><tbody>')
        for row in table_rows:
            content_parts.append('<tr>')
            for cell in row:
                content_parts.append('<td>{}</td>'.format(cell))
            content_parts.append('</tr>')
        content_parts.append('</tbody></table>')

content_html = '\n'.join(content_parts)

# 替换模板
html = template.replace('{{title}}', '中国新能源汽车行业深度研究')
html = html.replace('{{subtitle}}', '中国新能源汽车行业深度研究报告')
html = html.replace('{{date}}', datetime.now().strftime('%Y年%m月'))
html = html.replace('{{report_type}}', '行业深度研究')
html = html.replace('{{toc_items}}', toc_html)
html = html.replace('{{content}}', content_html)
html = html.replace('{{page_num}}', '1')

# 保存HTML
out_dir = ROOT / 'output' / 'with_tables'
out_dir.mkdir(exist_ok=True)
(out_dir / 'report.html').write_text(html, encoding='utf-8')
print('HTML生成完成')

# 转换
converter = HTMLToWordConverter()
result = converter.convert(html=html, output_path=str(out_dir / 'report.docx'))
print('Word转换结果:', result.to_dict())
