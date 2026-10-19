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

# Simulate converter loop
from collections import Counter
processed = Counter()
total_text_len = 0

for element in elements:
    elem_type = element.get("type", "")
    processed[elem_type] += 1
    
    if elem_type == "heading":
        text = element.get("text", "")
        if text:
            total_text_len += len(text)
    elif elem_type == "paragraph":
        text = element.get("text", "")
        if text:
            total_text_len += len(text)
    elif elem_type == "list_item":
        text = element.get("text", "")
        if text:
            total_text_len += len(text)
    elif elem_type == "table":
        data = element.get("data", [])
        headers = element.get("headers", [])
        rows = element.get("rows", [])
        for row in (headers + rows):
            for cell in row:
                if isinstance(cell, dict):
                    total_text_len += len(str(cell.get("text", "")))
                else:
                    total_text_len += len(str(cell))

print("Element counts:", dict(processed))
print(f"Total text length: {total_text_len}")
