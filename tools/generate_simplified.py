# -*- coding: utf-8 -*-
"""生成简化HTML并转换为Word"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.converters.html_to_word import HTMLToWordConverter

# 加载数据
with open(ROOT / 'output' / 'real_new_energy_vehicle_report' / 'research_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 生成简化HTML
html_parts = []
html_parts.append('<html><head><meta charset="utf-8"><title>报告</title></head><body>')

# 封面页
html_parts.append('<div class="cover-page">')
html_parts.append('<h1>中国新能源汽车行业深度研究报告</h1>')
html_parts.append('<p>研究机构：zensers Research</p>')
html_parts.append('<p>发布日期：2026年09月</p>')
html_parts.append('</div>')

# 目录页
html_parts.append('<div class="toc-page">')
html_parts.append('<h2>目 录</h2>')
for i, section in enumerate(data['sections'], 1):
    title = section.get('title', '')
    html_parts.append('<p>{:02d}  {}</p>'.format(i, title))
html_parts.append('</div>')

# 关键发现
html_parts.append('<div class="key-findings">')
html_parts.append('<h2>关键发现</h2>')
for finding in data.get('key_findings', []):
    finding = re.sub(r'\*\*', '', finding)
    finding = finding.strip()
    if finding:
        html_parts.append('<p>{}</p>'.format(finding))
html_parts.append('</div>')

# 各章节
for i, section in enumerate(data['sections'], 1):
    title = section.get('title', '')
    html_parts.append('<h1>{:02d} {}</h1>'.format(i, title))
    
    content = section.get('content', '')
    for line in content.split('\n'):
        line = line.strip()
        if not line or '全球与中国市场统计口径不同' in line:
            continue
        
        # 标题
        if line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            t = line.lstrip('#').strip()
            if level == 1:
                html_parts.append('<h2>{}</h2>'.format(t))
            elif level == 2:
                html_parts.append('<h3>{}</h3>'.format(t))
            continue
        
        # 列表
        if line.startswith('- ') or line.startswith('* '):
            text = line[2:]
            text = re.sub(r'\*\*', '', text)
            text = text.strip()
            if text:
                html_parts.append('<p>- {}</p>'.format(text))
            continue
        
        # 数字列表
        m = re.match(r'^(\d+)[.、]\s*(.+)$', line)
        if m:
            text = m.group(2)
            text = re.sub(r'\*\*', '', text)
            text = text.strip()
            if text:
                html_parts.append('<p>{}. {}</p>'.format(m.group(1), text))
            continue
        
        # 表格行跳过
        if line.startswith('|') and line.endswith('|'):
            continue
        
        # 普通段落
        text = re.sub(r'\*\*', '', line)
        text = re.sub(r'<[^>]+>', '', text)
        text = text.strip()
        if text:
            html_parts.append('<p>{}</p>'.format(text))

html_parts.append('</body></html>')

html = '\n'.join(html_parts)

# 保存HTML
out_dir = ROOT / 'output' / 'simplified_report'
out_dir.mkdir(exist_ok=True)
(out_dir / 'report.html').write_text(html, encoding='utf-8')
print('HTML生成完成')

# 用HTMLToWordConverter转换
converter = HTMLToWordConverter()
result = converter.convert(html=html, output_path=str(out_dir / 'report.docx'))
print('Word转换结果:', result.to_dict())
