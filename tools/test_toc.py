# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.converters.base_parser import HTMLElementParser

# 测试完整的toc结构
test = '<div class="toc-page"><h2 class="toc-header">目录</h2><ul class="toc-list"><li class="toc-item">Item 1</li><li class="toc-item">Item 2</li></ul></div>'

parser = HTMLElementParser()
parser.feed(test)
for e in parser.get_elements():
    print(e)
