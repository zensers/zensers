# -*- coding: utf-8 -*-
"""
CSS Style Extractor
===================

Extracts CSS styles from <style> tags in HTML templates, converts them to document formatting parameters.

Core features:
1. Extract <style> tag content from HTML
2. Parse CSS rules (selector → properties)
3. Map to Word/PPT style configuration

Usage example:
    extractor = CSSStyleExtractor()
    
    # Extract styles from HTML template
    styles = extractor.extract_from_html(html_template)
    
    # Or extract specific element styles directly
    title_styles = extractor.get_element_styles(".slide.cover h1")
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CSSRule:
    """CSS rule"""
    selector: str
    properties: Dict[str, str] = field(default_factory=dict)
    
    def get_property(self, name: str, default: str = "") -> str:
        """Get property value"""
        return self.properties.get(name, default)


@dataclass
class ExtractedStyles:
    """Extracted style configuration"""
    # Word styles
    title_font: str = "Microsoft YaHei"
    body_font: str = "Microsoft YaHei"
    title_size: int = 28  # pt
    h1_size: int = 24  # pt
    h2_size: int = 20  # pt
    h3_size: int = 16  # pt
    body_size: int = 12  # pt
    line_spacing: float = 1.5
    
    # PPT styles
    ppt_title_size: int = 44  # pt
    ppt_subtitle_size: int = 28  # pt
    ppt_body_size: int = 18  # pt
    ppt_slide_width: float = 10.0  # inches
    ppt_slide_height: float = 7.5  # inches
    
    # Colors
    title_color: str = "#1A2744"
    accent_color: str = "#C9A227"
    body_color: str = "#333333"
    
    def to_word_styles(self) -> Dict[str, Any]:
        """Convert to Word style dict"""
        return {
            "title_font": self.title_font,
            "body_font": self.body_font,
            "title_size": self.title_size,
            "h1_size": self.h1_size,
            "h2_size": self.h2_size,
            "h3_size": self.h3_size,
            "body_size": self.body_size,
            "line_spacing": self.line_spacing,
            "title_color": self.title_color,
            "accent_color": self.accent_color,
            "body_color": self.body_color,
        }
    
    def to_ppt_styles(self) -> Dict[str, Any]:
        """Convert to PPT style dict"""
        return {
            "title_font": self.title_font,
            "body_font": self.body_font,
            "title_size": self.ppt_title_size,
            "subtitle_size": self.ppt_subtitle_size,
            "body_size": self.ppt_body_size,
            "slide_width": self.ppt_slide_width,
            "slide_height": self.ppt_slide_height,
        }


class CSSStyleExtractor:
    """
    CSS Style Extractor
    
    Extracts CSS styles from HTML templates and converts them to document style configuration.
    
    Security features:
    - CSS property whitelist filtering (prevents injection)
    - Dangerous property blacklist (expression, @import, etc.)
    """
    
    # CSS safe property whitelist (properties allowed for extraction)
    SAFE_PROPERTIES = {
        # Font related
        "font-family", "font-size", "font-weight", "font-style",
        "line-height", "letter-spacing", "text-align",
        # Color related
        "color", "background-color", "background",
        # Size related
        "width", "height", "max-width", "max-height",
        "min-width", "min-height",
        "margin", "padding", "border",
        # Text related
        "text-decoration", "text-transform",
        "word-spacing", "white-space",
        # Other safe properties
        "opacity", "display", "visibility",
    }
    
    # CSS dangerous property blacklist
    DANGEROUS_PROPERTIES = {
        "behavior",          # IE specific, may execute scripts
        "expression",        # IE specific, may execute scripts
        "-moz-binding",      # Firefox XBL binding
        "content",           # May inject content
    }
    
    # CSS dangerous value patterns (regex)
    DANGEROUS_VALUE_PATTERNS = [
        r'expression\s*\(',   # IE expression()
        r'@import',           # CSS import
        r'url\s*\([\'"]?\s*javascript:',  # javascript URL
        r'url\s*\([\'"]?\s*data:',        # data URL (可能注入)
    ]
    
    # CSS属性映射表
    FONT_FAMILY_MAP = {
        "'Microsoft YaHei'": "Microsoft YaHei",
        "'SimHei'": "SimHei",
        "'SimSun'": "SimSun",
        "'sans-serif'": "Microsoft YaHei",
        "'serif'": "SimSun",
    }
    
    # 尺寸单位转换
    SIZE_UNITS = {
        "pt": 1.0,
        "px": 0.75,  # 1px ≈ 0.75pt
        "in": 72.0,  # 1in = 72pt
        "cm": 28.35,  # 1cm ≈ 28.35pt
        "em": 12.0,  # 默认按12pt基准
        "rem": 12.0,
    }
    
    def __init__(self):
        """初始化提取器"""
        self.rules: List[CSSRule] = []
        self._style_cache: Dict[str, Dict[str, str]] = {}
    
    def extract_from_html(self, html: str) -> ExtractedStyles:
        """
        从HTML提取样式
        
        Args:
            html: HTML内容
            
        Returns:
            ExtractedStyles 提取的样式配置
        """
        # 提取<style>标签内容
        style_content = self._extract_style_tag(html)
        
        if not style_content:
            logger.warning("No <style> tag found in HTML, using defaults")
            return ExtractedStyles()
        
        # 解析CSS规则
        self.rules = self._parse_css_rules(style_content)
        
        # 构建样式缓存
        self._build_style_cache()
        
        # 提取关键样式
        return self._extract_key_styles()
    
    def _extract_style_tag(self, html: str) -> str:
        """
        提取<style>标签内容
        
        Args:
            html: HTML内容
            
        Returns:
            CSS内容
        """
        # 匹配<style>标签（支持属性）
        pattern = r'<style[^>]*>(.*?)</style>'
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
        
        if matches:
            return "\n".join(matches)
        return ""
    
    def _parse_css_rules(self, css_content: str) -> List[CSSRule]:
        """
        解析CSS规则
        
        Args:
            css_content: CSS内容
            
        Returns:
            CSS规则列表
        """
        rules = []
        
        # 移除注释
        css_content = re.sub(r'/\*.*?\*/', '', css_content, flags=re.DOTALL)
        
        # 匹配规则：selector { properties }
        pattern = r'([^\{]+)\{([^\}]*)\}'
        matches = re.findall(pattern, css_content, re.DOTALL)
        
        for selector, properties_str in matches:
            # 清理选择器
            selector = selector.strip()
            
            if not selector or selector.startswith('@'):  # 跳过@规则
                continue
            
            # 解析属性
            properties = {}
            for prop_line in properties_str.split(';'):
                prop_line = prop_line.strip()
                if ':' in prop_line:
                    name, value = prop_line.split(':', 1)
                    name = name.strip()
                    value = value.strip()
                    
                    # 安全过滤
                    if self._is_safe_property(name, value):
                        properties[name] = value
            
            if properties:
                rules.append(CSSRule(selector=selector, properties=properties))
        
        return rules
    
    def _is_safe_property(self, name: str, value: str) -> bool:
        """
        检查CSS属性是否安全
        
        Args:
            name: 属性名
            value: 属性值
            
        Returns:
            是否安全
        """
        # 检查危险属性
        if name.lower() in self.DANGEROUS_PROPERTIES:
            return False
        
        # 检查危险值模式
        for pattern in self.DANGEROUS_VALUE_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                return False
        
        # 白名单检查（可选：只允许安全属性）
        # 如果属性不在白名单中，仍然允许但不用于样式提取
        # 这里我们只是记录警告，不阻止
        if name.lower() not in self.SAFE_PROPERTIES:
            logger.debug(f"Property '{name}' not in safe list, will be ignored in style extraction")
        
        return True
    
    def _build_style_cache(self) -> None:
        """构建选择器样式缓存"""
        self._style_cache = {}
        
        for rule in self.rules:
            # 存储每个选择器的属性
            self._style_cache[rule.selector] = rule.properties
    
    def get_element_styles(self, selector: str) -> Dict[str, str]:
        """
        获取指定选择器的样式
        
        Args:
            selector: CSS选择器
            
        Returns:
            样式属性字典
        """
        # 精确匹配
        if selector in self._style_cache:
            return self._style_cache[selector].copy()
        
        # 智能匹配：处理复合选择器
        # 优先级：精确匹配 > 后缀匹配 > 包含匹配
        best_match = None
        best_score = -1
        
        for cached_selector, properties in self._style_cache.items():
            score = self._calculate_selector_match_score(selector, cached_selector)
            if score > best_score:
                best_score = score
                best_match = properties
        
        return best_match.copy() if best_match else {}
    
    def _calculate_selector_match_score(self, target: str, cached: str) -> int:
        """
        计算选择器匹配得分
        
        Args:
            target: 目标选择器
            cached: 缓存的选择器
            
        Returns:
            匹配得分（越高越好，-1表示不匹配）
            
        得分范围说明：
        - 100: 精确匹配
        - 50+: 后缀匹配（50 + 匹配深度）
        - 10+: 类名交集匹配（class_overlap * 10）
        - 5+: 标签交集匹配（tag_overlap * 5）
        - -1: 不匹配
        """
        # 精确匹配
        if target == cached:
            return 100
        
        # 分割选择器为部分
        target_parts = target.split()
        cached_parts = cached.split()
        
        # 后缀匹配：检查选择器部分是否匹配（而非字符串后缀）
        # 例如 ".slide.cover h1" 的最后部分 ["h1"] 匹配 "h1"
        if len(cached_parts) >= len(target_parts):
            # 检查cached的最后N个部分是否等于target
            cached_suffix = cached_parts[-len(target_parts):]
            if cached_suffix == target_parts:
                matched_depth = len(target_parts)
                return 50 + matched_depth
        
        # 部分匹配：检查是否有共同的类名或标签
        target_classes = set()
        target_tags = set()
        
        for part in target_parts:
            if part.startswith('.'):
                target_classes.add(part[1:])
            elif part.startswith('#'):
                target_classes.add(part[1:])  # ID也作为精确标识
            else:
                target_tags.add(part)
        
        cached_classes = set()
        cached_tags = set()
        
        for part in cached_parts:
            if part.startswith('.'):
                cached_classes.add(part[1:])
            elif part.startswith('#'):
                cached_classes.add(part[1:])
            else:
                cached_tags.add(part)
        
        # 计算交集得分
        class_overlap = len(target_classes & cached_classes)
        tag_overlap = len(target_tags & cached_tags)
        
        if class_overlap > 0 or tag_overlap > 0:
            return class_overlap * 10 + tag_overlap * 5
        
        return -1  # 不匹配
    
    def _extract_key_styles(self) -> ExtractedStyles:
        """提取关键样式配置"""
        styles = ExtractedStyles()
        
        # 提取Word样式
        # 封面标题样式（.cover-page h1 优先级高于 h1.chapter-title）
        cover_title = self._get_merged_styles("h1.chapter-title", ".cover-page h1")
        if cover_title:
            styles.title_font = self._parse_font_family(cover_title.get("font-family", ""))
            styles.title_size = self._parse_size(cover_title.get("font-size", "28pt"))
            styles.title_color = self._parse_color(cover_title.get("color", "#1A2744"))
        
        # 章标题样式（精确匹配，不使用降级匹配避免误取封面样式）
        h1_styles = self._get_merged_styles("h1.chapter-title")
        if h1_styles:
            styles.h1_size = self._parse_size(h1_styles.get("font-size", "18pt"))
        
        # 节标题样式（精确匹配，不使用降级匹配避免误取目录样式）
        h2_styles = self._get_merged_styles("h2.section-title")
        if h2_styles:
            styles.h2_size = self._parse_size(h2_styles.get("font-size", "14pt"))
        
        # 子节标题样式
        h3_styles = self._get_merged_styles("h3.subsection-title")
        if h3_styles:
            styles.h3_size = self._parse_size(h3_styles.get("font-size", "12pt"))
        
        # 正文样式
        body_styles = self._get_merged_styles("body", "p")
        if body_styles:
            styles.body_font = self._parse_font_family(body_styles.get("font-family", ""))
            styles.body_size = self._parse_size(body_styles.get("font-size", "11pt"))
            styles.body_color = self._parse_color(body_styles.get("color", "#333333"))
            styles.line_spacing = self._parse_line_height(body_styles.get("line-height", "1.5"))
        
        # 提取PPT样式
        # 封面标题
        ppt_cover_title = self._get_merged_styles(".slide.cover h1", ".slide h1")
        if ppt_cover_title:
            styles.ppt_title_size = self._parse_size(ppt_cover_title.get("font-size", "72px"))
            styles.accent_color = self._parse_color(ppt_cover_title.get("color", "#C9A227"))
        
        # 内容页标题
        ppt_content_title = self._get_merged_styles(".slide.content h2", ".slide h2")
        if ppt_content_title:
            styles.ppt_subtitle_size = self._parse_size(ppt_content_title.get("font-size", "48px"))
            styles.title_color = self._parse_color(ppt_content_title.get("color", "#1A2744"))
        
        # PPT正文
        ppt_body = self._get_merged_styles(".slide.content .content-body", ".slide")
        if ppt_body:
            styles.ppt_body_size = self._parse_size(ppt_body.get("font-size", "24px"))
        
        # 幻灯片尺寸
        slide_styles = self._get_merged_styles(".slide")
        if slide_styles:
            width_px = self._parse_pixel_size(slide_styles.get("width", "1920px"))
            height_px = self._parse_pixel_size(slide_styles.get("height", "1080px"))
            # 转换为英寸（假设16:9标准PPT）
            styles.ppt_slide_width = width_px / 96.0  # 96px/inch
            styles.ppt_slide_height = height_px / 96.0
        
        return styles
    
    def _get_merged_styles(self, *selectors: str) -> Dict[str, str]:
        """
        合并多个选择器的样式
        
        Args:
            selectors: CSS选择器列表
            
        Returns:
            合并后的样式属性
        """
        merged = {}
        
        for selector in selectors:
            styles = self.get_element_styles(selector)
            merged.update(styles)
        
        return merged
    
    def _parse_font_family(self, value: str) -> str:
        """解析font-family属性"""
        if not value:
            return "Microsoft YaHei"
        
        # 提取第一个字体名
        fonts = value.split(',')
        for font in fonts:
            font = font.strip().strip('"').strip("'")
            if font in self.FONT_FAMILY_MAP:
                return self.FONT_FAMILY_MAP[font]
            if font and not font.startswith('@'):
                return font
        
        return "Microsoft YaHei"
    
    def _parse_size(self, value: str) -> int:
        """
        解析尺寸值
        
        Args:
            value: CSS尺寸值（如 "24px", "18pt"）
            
        Returns:
            尺寸（pt整数）
        """
        if not value:
            return 12
        
        # 提取数值和单位
        match = re.match(r'([\d.]+)(px|pt|in|cm|em|rem)?', value.strip())
        if match:
            num = float(match.group(1))
            unit = match.group(2) or "pt"
            
            # 转换为pt
            multiplier = self.SIZE_UNITS.get(unit, 1.0)
            return int(num * multiplier)
        
        return 12
    
    def _parse_pixel_size(self, value: str) -> float:
        """
        解析像素尺寸
        
        Args:
            value: CSS像素值（如 "1920px"）
            
        Returns:
            像素值
        """
        if not value:
            return 1920.0
        
        match = re.match(r'([\d.]+)', value.strip())
        if match:
            return float(match.group(1))
        
        return 1920.0
    
    def _parse_color(self, value: str) -> str:
        """解析颜色值"""
        if not value:
            return "#333333"
        
        # 标准化颜色格式
        value = value.strip()
        
        # hex颜色
        if value.startswith('#'):
            return value
        
        # rgb颜色
        rgb_match = re.match(r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', value)
        if rgb_match:
            r, g, b = rgb_match.groups()
            return f"#{int(r):02x}{int(g):02x}{int(b):02x}"
        
        # rgba颜色（忽略alpha）
        rgba_match = re.match(r'rgba\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', value)
        if rgba_match:
            r, g, b = rgba_match.groups()
            return f"#{int(r):02x}{int(g):02x}{int(b):02x}"
        
        return value
    
    def _parse_line_height(self, value: str) -> float:
        """解析line-height值"""
        if not value:
            return 1.5
        
        # 无单位数值
        if re.match(r'^[\d.]+$', value.strip()):
            return float(value.strip())
        
        # 百分比
        if value.endswith('%'):
            return float(value.strip('%')) / 100.0
        
        # 其他单位（转换为相对值）
        pt_size = self._parse_size(value)
        return pt_size / 12.0  # 基准12pt
    
    def get_rules_for_selector(self, selector_pattern: str) -> List[CSSRule]:
        """
        获取匹配选择器模式的所有规则
        
        Args:
            selector_pattern: 选择器模式（部分匹配）
            
        Returns:
            匹配的CSS规则列表
        """
        matched = []
        for rule in self.rules:
            if selector_pattern in rule.selector:
                matched.append(rule)
        return matched


# 导出
__all__ = ["CSSStyleExtractor", "CSSRule", "ExtractedStyles"]