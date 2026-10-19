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

# Show elements with 'text' field
for i, e in enumerate(elements):
    if e.get('text'):
        text = str(e['text'])[:80]
        print(f'{i}: type={e.get("type")}, text="{text}"')
        if i > 30:
            break
