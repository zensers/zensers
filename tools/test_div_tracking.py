# -*- coding: utf-8 -*-
"""模拟HTML转换器的div class追踪"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.converters.base_parser import HTMLElementParser

html = open('output/with_tables/report.html', 'r', encoding='utf-8').read()
parser = HTMLElementParser()
parser.feed(html)
elements = parser.get_elements()

# 模拟HTML转换器的div class追踪
current_div_class = ''

for i, e in enumerate(elements[:50]):
    etype = e.get('type', '')
    
    if etype == 'div_start':
        current_div_class = e.get('class', '')
        if current_div_class in ('cover-page', 'toc-page', 'key-findings'):
            print('{:2d}: div_start -> {}'.format(i, current_div_class))
    elif etype == 'div_end':
        if current_div_class in ('cover-page', 'toc-page', 'key-findings'):
            print('{:2d}: div_end -> {} (page_break)'.format(i, current_div_class))
        current_div_class = ''
    elif etype == 'heading':
        level = e.get('level', 1)
        css_class = e.get('class', '')
        text = e.get('text', '')[:30]
        print('{:2d}: heading level={} class="{}" div="{}" text={}'.format(i, level, css_class, current_div_class, text))
