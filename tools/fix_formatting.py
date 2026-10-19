# -*- coding: utf-8 -*-
import json
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

data = json.load(open('output/full_research/semiconductor_revised_report_llm.json', 'r', encoding='utf-8'))

fixed_count = 0
for i, s in enumerate(data['sections']):
    content = s['content']
    original = content
    
    # Fix double headers: "## ## 1." -> "## 1."
    content = re.sub(r'##\s*##\s*', '## ', content)
    
    # Fix double headers: "### ### 1." -> "### 1."
    content = re.sub(r'###\s*###\s*', '### ', content)
    
    # Fix double headers: "#### #### 1." -> "#### 1."
    content = re.sub(r'####\s*####\s*', '#### ', content)
    
    # Remove excessive blank lines (keep max 2)
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    if content != original:
        data['sections'][i]['content'] = content
        fixed_count += 1
        print(f'Fixed chapter {i+1}: {s["title"]}')

# Save
with open('output/full_research/semiconductor_revised_report_llm.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'\nFixed {fixed_count} chapters')
