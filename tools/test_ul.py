# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.converters.base_parser import HTMLElementParser

# 测试ul和li解析
test = '<ul class="toc-list"><li class="toc-item">Item 1</li><li class="toc-item">Item 2</li></ul>'

parser = HTMLElementParser()
parser.feed(test)
for e in parser.get_elements():
    print(e)
