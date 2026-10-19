# -*- coding: utf-8 -*-
import json
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

data = json.load(open('output/full_research/semiconductor_revised_report_llm.json', 'r', encoding='utf-8'))

print('='*60)
print('COMPREHENSIVE REPORT REVIEW')
print('='*60)

issues = []

# 1. Check key findings
kf = data.get('key_findings', [])
if len(kf) < 5:
    issues.append(('Key Findings', f'Only {len(kf)} findings, need at least 5'))

# 2. Check each chapter
for i, s in enumerate(data['sections'], 1):
    title = s['title']
    content = s['content']
    
    # Length check
    if len(content) < 5000:
        issues.append((title, f'Too short: {len(content)} chars'))
    
    # Structure check
    h2_count = content.count('## ')
    h3_count = content.count('### ')
    if h2_count < 2:
        issues.append((title, f'Few H2 headers: {h2_count}'))
    
    # Table check
    table_count = content.count('|---')
    if table_count < 1:
        issues.append((title, f'No tables'))
    
    # Number check
    numbers = re.findall(r'\d+\.?\d*[%亿万美元万亿元亿美元百亿美元千亿]', content)
    if len(numbers) < 15:
        issues.append((title, f'Few numbers: {len(numbers)}'))
    
    # Source check
    if '数据来源' not in content and '来源' not in content[:500]:
        issues.append((title, 'Missing data sources'))
    
    # Chinese content check (not garbled)
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
    if chinese_chars < len(content) * 0.3:
        issues.append((title, f'Low Chinese content ratio: {chinese_chars}/{len(content)}'))

# 3. Overall structure
total_chars = sum(len(s['content']) for s in data['sections'])
if total_chars < 50000:
    issues.append(('Overall', f'Total chars too low: {total_chars}'))

print(f'\nTotal chapters: {len(data["sections"])}')
print(f'Total chars: {total_chars}')
print(f'Key findings: {len(kf)}')

print(f'\nIssues found: {len(issues)}')
for title, issue in issues:
    print(f'  [{title}] {issue}')

print('\n' + '='*60)
