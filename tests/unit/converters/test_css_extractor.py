# -*- coding: utf-8 -*-
from src.converters.css_extractor import CSSStyleExtractor

_HTML = """
<html><head><style>
body { font-family: 'Microsoft YaHei'; color: #333333; }
.slide.cover h1 { font-size: 72px; color: #C9A227; font-family: 'SimHei'; }
.slide.content h2 { font-size: 48px; color: #1A2744; }
.slide.content .content-body { font-size: 24px; color: #555555; }
</style></head><body></body></html>
"""


class TestThemeOverrides:
    def test_extracts_palette_and_font(self):
        styles = CSSStyleExtractor().extract_from_html(_HTML)
        overrides = styles.to_theme_overrides()
        assert overrides["colors"]["gold"] == "C9A227"
        assert overrides["colors"]["navy"] == "1A2744"
        assert overrides["colors"]["text_dark"] == "555555"
        assert overrides["fonts"]["default"] == "SimHei"

    def test_empty_html_returns_empty_overrides(self):
        styles = CSSStyleExtractor().extract_from_html("<html></html>")
        overrides = styles.to_theme_overrides()
        assert overrides == {"colors": {}, "fonts": {}}
