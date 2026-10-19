# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.converters.base_parser import HTMLElementParser

html = open('output/with_tables/report.html', 'r', encoding='utf-8').read()
parser = HTMLElementParser()
parser.feed(html)
elements = parser.get_elements()

current_div = ''
for i, e in enumerate(elements[:60]):
    etype = e.get('type', '')
    if etype == 'div_start':
        current_div = e.get('class', '')
    elif etype == 'div_end':
        current_div = ''
    elif etype in ('heading', 'paragraph'):
        print('{:2d}: {} class="{}" div="{}" text={}'.format(
            i, etype, e.get('class', ''), current_div, e.get('text', '')[:40]
        ))
