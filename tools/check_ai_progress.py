# -*- coding: utf-8 -*-
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

data = json.load(open('output/full_research/ai_revised_report_llm.json', 'r', encoding='utf-8'))
print('Total chars:', data['metadata']['total_chars'])
for i, s in enumerate(data['sections'], 1):
    print(f'  {i}. {s["title"]}: {len(s["content"])} chars')
