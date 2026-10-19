# -*- coding: utf-8 -*-
"""用HTML模板 + HTMLToWordConverter生成Word报告"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 加载数据
with open(ROOT / 'output' / 'real_new_energy_vehicle_report' / 'research_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 读取HTML模板
template = (ROOT / 'templates' / 'professional_report.html').read_text(encoding='utf-8')

# 生成目录HTML
toc_lines = []
for i, section in enumerate(data['sections'], 1):
    title = section.get('title', '')
    toc_lines.append(
        '<li class="toc-item">'
        '<span class="chapter-num">{:02d}</span>'
        '<span class="chapter-title">{}</span>'
        '<span class="chapter-page">{}</span>'
        '</li>'.format(i, title, i + 2)
    )
toc_html = '\n'.join(toc_lines)

# 生成内容HTML
content_parts = []

# 关键发现
if data.get('key_findings'):
    content_parts.append('<div class="key-findings"><h2>关键发现</h2><ul>')
    for finding in data['key_findings']:
        finding = re.sub(r'\*\*(.+?)\*\*', r'\1', finding)
        finding = re.sub(r'<[^>]+>', '', finding)
        content_parts.append('<li>{}</li>'.format(finding.strip()))
    content_parts.append('</ul></div>')

# 各章节
for i, section in enumerate(data['sections'], 1):
    title = section.get('title', '')
    content_parts.append('<h1 class="chapter-title">{:02d} {}</h1>'.format(i, title))

    content = section.get('content', '')
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        if '全球与中国市场统计口径不同' in line:
            continue

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
            # 清理所有**标记
            text = re.sub(r'\*\*', '', text)
            text = re.sub(r'\*(.+?)\*', r'\1', text)
            text = re.sub(r'<[^>]+>', '', text)
            text = text.strip()
            if text:
                content_parts.append('<li>{}</li>'.format(text))
            continue

        # 数字列表
        m = re.match(r'^(\d+)[.、]\s*(.+)$', line)
        if m:
            text = m.group(2)
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            text = re.sub(r'\*(.+?)\*', r'\1', text)
            text = re.sub(r'<[^>]+>', '', text)
            if text.strip():
                content_parts.append('<li>{}</li>'.format(text))
            continue

        # 表格行跳过
        if line.startswith('|') and line.endswith('|'):
            continue

        # 普通段落
        text = line
        # 清理所有**标记
        text = re.sub(r'\*\*', '', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = text.strip()
        if text:
            content_parts.append('<p>{}</p>'.format(text))

content_html = '\n'.join(content_parts)

# 替换模板变量
html = template.replace('{{title}}', '中国新能源汽车行业深度研究')
html = html.replace('{{subtitle}}', '中国新能源汽车行业深度研究报告')
html = html.replace('{{date}}', datetime.now().strftime('%Y年%m月'))
html = html.replace('{{report_type}}', '行业深度研究')
html = html.replace('{{toc_items}}', toc_html)
html = html.replace('{{content}}', content_html)
html = html.replace('{{page_num}}', '1')

# 保存HTML
out_dir = ROOT / 'output' / 'final_with_converter'
out_dir.mkdir(exist_ok=True)
(out_dir / 'report.html').write_text(html, encoding='utf-8')
print('HTML生成完成')

# 用HTMLToWordConverter转换
from src.converters.html_to_word import HTMLToWordConverter
converter = HTMLToWordConverter()
result = converter.convert(html=html, output_path=str(out_dir / 'report.docx'))
print('Word转换结果:', result.to_dict())
