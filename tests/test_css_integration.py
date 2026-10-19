# -*- coding: utf-8 -*-
"""
CSS样式系统集成测试
"""

import sys
sys.path.insert(0, '.')

import pytest
from pathlib import Path


class TestCSSExtractorSecurity:
    """CSS提取器安全测试"""
    
    def test_safe_path_valid(self):
        """测试有效路径"""
        from src.converters.html_to_word import HTMLToWordConverter
        
        converter = HTMLToWordConverter()
        
        # 有效路径
        assert converter._is_safe_path("output/test.docx") == True
        assert converter._is_safe_path("/tmp/test.docx") == True
        assert converter._is_safe_path("./reports/test.docx") == True
    
    def test_safe_path_traversal(self):
        """测试路径遍历攻击"""
        from src.converters.html_to_word import HTMLToWordConverter
        
        converter = HTMLToWordConverter()
        
        # 路径遍历攻击
        assert converter._is_safe_path("../../../etc/passwd") == False
        assert converter._is_safe_path("..\\..\\..\\Windows\\System32") == False
    
    def test_css_injection_blocked(self):
        """测试CSS注入被阻止"""
        from src.converters.css_extractor import CSSStyleExtractor
        
        extractor = CSSStyleExtractor()
        
        # 恶意CSS
        malicious_css = """
        .test {
            behavior: url(script.htc);
            expression(alert(1));
            color: #333;
        }
        """
        
        html = f"<style>{malicious_css}</style>"
        styles = extractor.extract_from_html(html)
        
        # 检查危险属性被过滤
        rules = extractor.rules
        if rules:
            props = rules[0].properties
            assert "behavior" not in props
            assert "expression" not in props
            assert "color" in props  # 安全属性保留
    
    def test_selector_matching_priority(self):
        """测试选择器匹配优先级"""
        from src.converters.css_extractor import CSSStyleExtractor
        
        css = """
        h1 { font-size: 24px; }
        .cover h1 { font-size: 72px; }
        .slide.cover h1 { font-size: 96px; }
        """
        
        html = f"<style>{css}</style>"
        extractor = CSSStyleExtractor()
        extractor.extract_from_html(html)
        
        # 精确匹配
        styles = extractor.get_element_styles("h1")
        assert styles.get("font-size") == "24px"
        
        # 后缀匹配
        styles = extractor.get_element_styles(".cover h1")
        assert styles.get("font-size") == "72px"


class TestDocumentGeneratorIntegration:
    """文档生成器集成测试"""
    
    def test_template_html_passed_to_converter(self):
        """测试模板HTML传递给转换器"""
        from src.core.orchestrator.output.document_generator import (
            DocumentGenerator, DocumentConfig, DocumentFormat
        )
        
        # 创建生成器
        config = DocumentConfig(format=DocumentFormat.DOCX, title="测试报告")
        generator = DocumentGenerator(config)
        
        # 添加内容
        generator.add_heading("第一章", level=1)
        generator.add_paragraph("这是测试内容")
        
        # 检查内部状态
        assert generator._content_orchestrator is not None
        assert generator._word_converter is not None
        assert generator._ppt_converter is not None
    
    def test_prepare_research_result(self):
        """测试研究结果准备"""
        from src.core.orchestrator.output.document_generator import (
            DocumentGenerator, DocumentConfig
        )
        
        generator = DocumentGenerator(DocumentConfig(title="测试"))
        generator.add_heading("标题1", level=1)
        generator.add_paragraph("段落内容")
        generator.add_heading("标题2", level=2)
        
        result = generator._prepare_research_result()
        
        assert result["title"] == "测试"
        assert len(result["sections"]) >= 1


class TestStyleMerging:
    """样式合并测试"""
    
    def test_merge_order_template_default_custom(self):
        """测试样式合并顺序：模板→默认→自定义"""
        from src.converters.html_to_word import HTMLToWordConverter
        from src.converters.css_extractor import ExtractedStyles
        
        converter = HTMLToWordConverter()
        
        # 创建模板样式
        template_styles = ExtractedStyles()
        template_styles.title_font = "SimHei"
        template_styles.title_size = 28
        
        # 自定义样式
        custom_styles = {"title_font": "Arial"}
        
        # 合并
        merged = converter._merge_styles(template_styles, custom_styles)
        
        # 自定义优先级最高
        assert merged["title_font"] == "Arial"
        # 模板样式保留
        assert merged["title_size"] == 28


if __name__ == "__main__":
    pytest.main([__file__, "-v"])