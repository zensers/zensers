# -*- coding: utf-8 -*-
import sys, re
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')
from src.converters.base_parser import HTMLElementParser

html = open('output/full_research/revised_report.html', 'r', encoding='utf-8').read()
html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
html = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)

parser = HTMLElementParser()
parser.feed(html)
elements = parser.get_elements()

# Count elements with text
with_text = [e for e in elements if e.get('text')]
without_text = [e for e in elements if not e.get('text') and e.get('type') in ('paragraph', 'heading', 'list_item')]
print(f'Total elements: {len(elements)}')
print(f'With text: {len(with_text)}')
print(f'Paragraph/heading/list_item without text: {len(without_text)}')

# Show first 5 without text
for i, e in enumerate(without_text[:5]):
    print(f'  {i}: type={e.get("type")}, keys={list(e.keys())}')
