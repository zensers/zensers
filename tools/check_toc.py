# -*- coding: utf-8 -*-
html = open('output/with_tables/report.html', 'r', encoding='utf-8').read()

# 找到toc-list HTML内容部分
start = html.find('<ul class="toc-list">')
if start == -1:
    print('未找到toc-list')
else:
    end = html.find('</ul>', start) + 5
    toc_section = html[start:end]
    print('TOC HTML:')
    print(toc_section[:2000])
