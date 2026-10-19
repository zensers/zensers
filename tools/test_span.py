# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.converters.base_parser import HTMLElementParser

# 测试带span的li
test = '<ul><li class="toc-item-level1"><span class="toc-title">01 Title</span><span class="toc-dots"></span><span class="toc-page">3</span></li></ul>'

parser = HTMLElementParser()
parser.feed(test)
for e in parser.get_elements():
    print(e)
