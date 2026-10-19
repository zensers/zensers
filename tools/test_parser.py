# -*- coding: utf-8 -*-
"""测试HTML parser的div class追踪"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.converters.base_parser import HTMLElementParser

# 测试嵌套div
test_html = '<div class="outer"><div class="inner"><h1>Title</h1></div></div>'

parser = HTMLElementParser()
parser.feed(test_html)
elements = parser.get_elements()

print('Elements:')
for e in elements:
    print('  type={}, class={}, text={}'.format(e.get('type'), e.get('class', ''), e.get('text', '')[:20]))
