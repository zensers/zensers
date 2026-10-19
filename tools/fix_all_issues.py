# -*- coding: utf-8 -*-
"""
Fix all format and content issues found in audit
"""

import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

data = json.load(open('output/full_research/semiconductor_revised_report_llm.json', 'r', encoding='utf-8'))

print('='*60)
print('FIXING FORMAT ISSUES')
print('='*60)

for i, s in enumerate(data['sections']):
    content = s['content']
    original = content
    
    # Fix 1: Remove duplicate heading markers (### # -> ###)
    content = re.sub(r'#{1,4}\s+#\s+', lambda m: '#' * (m.group().count('#') - 1) + ' ', content)
    
    # Fix 2: Remove excessive blank lines
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    # Fix 3: Ensure consistent heading spacing
    content = re.sub(r'\n(#{1,4}[^#])', r'\n\n\1', content)
    content = re.sub(r'(^#{1,4}[^#])\n\n', r'\1\n\n', content, flags=re.MULTILINE)
    
    if content != original:
        data['sections'][i]['content'] = content
        print(f'Fixed chapter {i+1}: {s["title"]}')

# Save
with open('output/full_research/semiconductor_revised_report_llm.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('\nFormat fixes applied!')
