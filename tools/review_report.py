# -*- coding: utf-8 -*-
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

data = json.load(open('output/full_research/semiconductor_revised_report_llm.json', 'r', encoding='utf-8'))

print('Topic:', data['topic'])
print('Key findings:', len(data.get('key_findings', [])))

all_issues = []
for i, s in enumerate(data['sections'], 1):
    title = s['title']
    content = s['content']
    print(f'\n=== Chapter {i}: {title} ===')
    print(f'Length: {len(content)} chars')
    
    issues = []
    
    # Check for wrong content
    if '新能源汽车' in content:
        issues.append('Contains 新能源汽车 content!')
    if '电动汽车' in content and '半导体' not in content[:500]:
        issues.append('May contain 电动汽车 content!')
    
    # Check for too short
    if len(content) < 5000:
        issues.append('Too short!')
    
    # Check for markdown headers
    if content.count('## ') < 3:
        issues.append('Too few section headers!')
    
    # Check for tables
    if '|' not in content:
        issues.append('No tables!')
    
    # Check for data/numbers
    import re
    numbers = re.findall(r'\d+\.?\d*[%亿万美元]', content)
    if len(numbers) < 10:
        issues.append(f'Few numbers ({len(numbers)})')
    
    if issues:
        print('Issues:', issues)
        all_issues.extend([(title, issue) for issue in issues])
    else:
        print('Status: OK')

print('\n' + '='*60)
print(f'Total issues: {len(all_issues)}')
for title, issue in all_issues:
    print(f'  - {title}: {issue}')
