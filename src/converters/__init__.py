# -*- coding: utf-8 -*-
"""
Format Converters
=================

Converts HTML intermediate format to target document formats.

Supported converters:
- HTMLToWordConverter: HTML → Word (.docx)
- HTMLToPPTConverter: HTML → PowerPoint (.pptx)
- HTMLToPDFConverter: HTML → PDF (.pdf)

Base Components:
- HTMLElementParser: Generic HTML parser base class
- SlideElementParser: Slide-specific parser
- CSSStyleExtractor: CSS style extractor (extracts styles from HTML templates)
"""

from .base_parser import HTMLElementParser, SlideElementParser
from .css_extractor import CSSStyleExtractor, ExtractedStyles, CSSRule
from .html_to_word import HTMLToWordConverter
from .html_to_ppt import HTMLToPPTConverter
from .html_to_pdf import HTMLToPDFConverter

__all__ = [
    "HTMLElementParser",
    "SlideElementParser",
    "CSSStyleExtractor",
    "ExtractedStyles",
    "CSSRule",
    "HTMLToWordConverter",
    "HTMLToPPTConverter",
    "HTMLToPDFConverter",
]
