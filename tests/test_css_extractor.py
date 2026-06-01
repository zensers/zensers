# -*- coding: utf-8 -*-
"""CSS样式提取器测试"""

import sys
sys.path.insert(0, 'E:/market_report_systerm')

from src.converters.css_extractor import CSSStyleExtractor, ExtractedStyles

def test_word_template():
    """测试Word模板样式提取"""
    word_template = open('E:/market_report_systerm/config/document_templates/word_default.html', 'r', encoding='utf-8').read()
    extractor = CSSStyleExtractor()
    styles = extractor.extract_from_html(word_template)
    
    print('=== Word模板样式提取 ===')
    print(f'title_font: {styles.title_font}')
    print(f'body_font: {styles.body_font}')
    print(f'title_size: {styles.title_size}pt')
    print(f'h1_size: {styles.h1_size}pt')
    print(f'h2_size: {styles.h2_size}pt')
    print(f'body_size: {styles.body_size}pt')
    print(f'line_spacing: {styles.line_spacing}')
    print(f'title_color: {styles.title_color}')
    print()
    
    # 验证提取结果
    assert styles.title_font == "SimHei", f"Expected SimHei, got {styles.title_font}"
    assert styles.body_font == "SimSun", f"Expected SimSun, got {styles.body_font}"
    assert styles.title_size == 28, f"Expected 28pt, got {styles.title_size}"
    assert styles.h1_size == 18, f"Expected 18pt, got {styles.h1_size}"
    assert styles.body_size == 11, f"Expected 11pt, got {styles.body_size}"
    
    print("Word模板测试通过!")
    return styles

def test_ppt_template():
    """测试PPT模板样式提取"""
    ppt_template = open('E:/market_report_systerm/config/document_templates/ppt_default.html', 'r', encoding='utf-8').read()
    extractor = CSSStyleExtractor()
    styles = extractor.extract_from_html(ppt_template)
    
    print('=== PPT模板样式提取 ===')
    print(f'ppt_title_size: {styles.ppt_title_size}pt')
    print(f'ppt_subtitle_size: {styles.ppt_subtitle_size}pt')
    print(f'ppt_body_size: {styles.ppt_body_size}pt')
    print(f'slide_width: {styles.ppt_slide_width}in')
    print(f'slide_height: {styles.ppt_slide_height}in')
    print(f'title_color: {styles.title_color}')
    print(f'accent_color: {styles.accent_color}')
    print()
    
    # 验证提取结果
    assert styles.ppt_title_size == 54, f"Expected 54pt (72px*0.75), got {styles.ppt_title_size}"
    assert styles.ppt_subtitle_size == 36, f"Expected 36pt (48px*0.75), got {styles.ppt_subtitle_size}"
    assert styles.ppt_body_size == 18, f"Expected 18pt (24px*0.75), got {styles.ppt_body_size}"
    assert styles.accent_color == "#c9a227", f"Expected #c9a227, got {styles.accent_color}"
    
    print("PPT模板测试通过!")
    return styles

def test_style_conversion():
    """测试样式字典转换"""
    styles = ExtractedStyles()
    styles.title_font = "SimHei"
    styles.title_size = 28
    styles.ppt_title_size = 54
    
    word_dict = styles.to_word_styles()
    ppt_dict = styles.to_ppt_styles()
    
    print('=== Word样式字典 ===')
    for k, v in word_dict.items():
        print(f'{k}: {v}')
    print()
    
    print('=== PPT样式字典 ===')
    for k, v in ppt_dict.items():
        print(f'{k}: {v}')
    print()
    
    assert word_dict['title_font'] == "SimHei"
    assert word_dict['title_size'] == 28
    assert ppt_dict['title_size'] == 54
    
    print("样式转换测试通过!")

if __name__ == "__main__":
    test_word_template()
    test_ppt_template()
    test_style_conversion()
    print("\n所有测试通过!")
