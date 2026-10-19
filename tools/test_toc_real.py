# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.converters.base_parser import HTMLElementParser

html = open('output/with_tables/report.html', 'r', encoding='utf-8').read()

# 提取toc-page部分
start = html.find('<div class="toc-page">')
end = html.find('</div>', start) + 6
toc_html = html[start:end]

print('TOC HTML:')
print(toc_html[:500])
print()

# 解析
parser = HTMLElementParser()
parser.feed(toc_html)
print('解析结果:')
for e in parser.get_elements():
    print('  type={}, text={}'.format(e.get('type'), e.get('text', '')[:30]))
