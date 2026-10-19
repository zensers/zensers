# -*- coding: utf-8 -*-
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

data = json.load(open('output/full_research/semiconductor_revised_report_llm.json', 'r', encoding='utf-8'))

for i, s in enumerate(data['sections'], 1):
    content = s['content']
    table_lines = [line for line in content.split('\n') if line.strip().startswith('|')]
    print(f'Chapter {i}: {s["title"]}')
    print(f'  Table lines: {len(table_lines)}')
    if table_lines:
        print(f'  First: {table_lines[0][:80]}')
