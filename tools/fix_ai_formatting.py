# -*- coding: utf-8 -*-
import json
import re
import sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_FILE = Path("output/full_research/ai_revised_report_llm.json")

data = json.load(open(OUTPUT_FILE, 'r', encoding='utf-8'))

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
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('\nFormat fixes applied!')
