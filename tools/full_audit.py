# -*- coding: utf-8 -*-
"""
Comprehensive Report Quality Audit
Checks format, content quality, and professionalism
"""

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

data = json.load(open('output/full_research/semiconductor_revised_report_llm.json', 'r', encoding='utf-8'))

print('='*70)
print('COMPREHENSIVE REPORT QUALITY AUDIT')
print('='*70)

format_issues = []
content_issues = []

for i, s in enumerate(data['sections'], 1):
    title = s['title']
    content = s['content']
    lines = content.split('\n')
    
    print(f'\n--- Chapter {i}: {title} ({len(content)} chars) ---')
    
    # ===== FORMAT CHECKS =====
    
    # 1. Check heading hierarchy
    headings = []
    for line in lines:
        if line.strip().startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            text = line.lstrip('#').strip()
            headings.append((level, text))
    
    # Check for proper hierarchy (no skipping levels)
    prev_level = 0
    for level, text in headings:
        if level > prev_level + 1 and prev_level > 0:
            format_issues.append((title, f'Heading level skip: H{prev_level} -> H{level}'))
        prev_level = level
    
    # 2. Check for duplicate heading markers
    for line in lines:
        if re.match(r'^#{1,4}\s+#{1,4}\s+', line):
            format_issues.append((title, f'Duplicate heading marker: {line[:50]}'))
    
    # 3. Check table format
    table_lines = [line for line in lines if line.strip().startswith('|')]
    if table_lines:
        # Check if tables have proper headers
        for j, line in enumerate(table_lines):
            if '|---' in line or '|:---' in line:
                # This is a separator line, check if previous line is a header
                if j > 0:
                    prev_line = table_lines[j-1]
                    if prev_line.count('|') < 2:
                        format_issues.append((title, f'Table header issue at line {j}'))
    
    # 4. Check for empty sections
    sections = content.split('\n## ')
    for sec in sections[1:]:
        sec_lines = sec.strip().split('\n')
        if len(sec_lines) < 2:
            format_issues.append((title, f'Empty section: {sec_lines[0][:30]}'))
    
    # 5. Check for consistent list format
    list_lines = [line for line in lines if line.strip().startswith(('- ', '* ', '1. ', '2. '))]
    if list_lines:
        # Check for inconsistent list markers
        dash_count = sum(1 for l in list_lines if l.strip().startswith('- '))
        star_count = sum(1 for l in list_lines if l.strip().startswith('* '))
        if dash_count > 0 and star_count > 0:
            format_issues.append((title, f'Mixed list markers: {dash_count} dashes, {star_count} stars'))
    
    # ===== CONTENT CHECKS =====
    
    # 1. Check for data sources
    source_mentions = content.count('数据来源') + content.count('来源：') + content.count('资料来源')
    if source_mentions < 2:
        content_issues.append((title, f'Few data sources mentioned: {source_mentions}'))
    
    # 2. Check for specific data points
    numbers = re.findall(r'\d+\.?\d*[%亿万美元万亿元亿美元百亿]', content)
    if len(numbers) < 20:
        content_issues.append((title, f'Few numerical data points: {len(numbers)}'))
    
    # 3. Check for professional terminology
    pro_terms = ['CAGR', 'YoY', 'Moore', 'TSMC', 'ASML', 'Samsung', 'Intel', 'NVIDIA', 
                 'SiC', 'GaN', 'HBM', 'EUV', 'DRAM', 'NAND', 'Fabless', 'IDM', 'Foundry']
    found_terms = [term for term in pro_terms if term in content]
    if len(found_terms) < 5:
        content_issues.append((title, f'Few professional terms: {len(found_terms)}'))
    
    # 4. Check for logical structure
    has_intro = '概述' in content or '背景' in content or '定义' in content
    has_conclusion = '总结' in content or '结论' in content or '展望' in content
    if not has_intro:
        content_issues.append((title, 'Missing introduction/background'))
    if not has_conclusion:
        content_issues.append((title, 'Missing conclusion/outlook'))
    
    # 5. Check for citations/references
    citation_patterns = ['据', '根据', '报告显示', '研究表明', '数据表明', '统计显示']
    citation_count = sum(content.count(p) for p in citation_patterns)
    if citation_count < 5:
        content_issues.append((title, f'Few citations: {citation_count}'))
    
    # 6. Check for analysis depth
    analysis_terms = ['分析', '研究表明', '可以发现', '值得注意', '关键因素', '主要驱动']
    analysis_count = sum(content.count(t) for t in analysis_terms)
    if analysis_count < 3:
        content_issues.append((title, f'Low analysis depth: {analysis_count}'))
    
    print(f'  Format issues: {len([f for f in format_issues if f[0] == title])}')
    print(f'  Content issues: {len([c for c in content_issues if c[0] == title])}')

print('\n' + '='*70)
print('SUMMARY')
print('='*70)
print(f'\nTotal format issues: {len(format_issues)}')
for title, issue in format_issues:
    print(f'  [{title}] {issue}')

print(f'\nTotal content issues: {len(content_issues)}')
for title, issue in content_issues:
    print(f'  [{title}] {issue}')

print('\n' + '='*70)
