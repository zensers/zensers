# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.converters.base_parser import HTMLElementParser

# 测试封面页HTML结构
test = '<div class="cover-page"><div class="cover-badge"><h1>Title</h1></div></div>'

parser = HTMLElementParser()
parser.feed(test)
for e in parser.get_elements():
    print(e)
