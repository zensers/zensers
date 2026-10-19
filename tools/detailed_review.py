# -*- coding: utf-8 -*-
import json
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

data = json.load(open('output/full_research/semiconductor_revised_report_llm.json', 'r', encoding='utf-8'))

print('='*60)
print('DETAILED CONTENT REVIEW')
print('='*60)

for i, s in enumerate(data['sections'], 1):
    title = s['title']
    content = s['content']
    
    print(f'\n--- Chapter {i}: {title} ---')
    print(f'Length: {len(content)} chars')
    
    # Check for garbled text
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
    total_chars = len(content)
    chinese_ratio = chinese_chars / total_chars if total_chars > 0 else 0
    
    # Check for common issues
    issues = []
    
    # Check for repeated patterns
    if content.count('例如') > 5:
        issues.append('Too many "例如"')
    if content.count('比如') > 5:
        issues.append('Too many "比如"')
    
    # Check for empty sections
    sections = content.split('## ')
    empty_sections = [s for s in sections[1:] if len(s.strip()) < 100]
    if empty_sections:
        issues.append(f'{len(empty_sections)} short sections')
    
    # Check for table quality
    table_lines = [line for line in content.split('\n') if line.strip().startswith('|')]
    if table_lines:
        # Check if tables have headers
        tables_with_headers = sum(1 for line in table_lines if '---' in line)
        print(f'  Tables: {len(table_lines)//3} (with {tables_with_headers} separators)')
    
    # Check for data sources
    if '数据来源' in content:
        source_count = content.count('数据来源')
        print(f'  Data sources mentioned: {source_count}')
    
    print(f'  Chinese ratio: {chinese_ratio:.1%}')
    
    if issues:
        print(f'  Issues: {issues}')
    else:
        print(f'  Status: OK')

print('\n' + '='*60)
