# -*- coding: utf-8 -*-
"""
HTML to Word Converter
======================

Converts HTML intermediate format to Word documents (.docx).

Core features:
1. HTML parsing and conversion
2. Heading level handling
3. Paragraph and list processing
4. Table processing
5. Style application

Technical solution: python-docx

Usage example:
    converter = HTMLToWordConverter()
    result = converter.convert(
        html="<article><h1>Title</h1><p>Content</p></article>",
        output_path="output.docx"
    )
"""

import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base_parser import HTMLElementParser
from .css_extractor import CSSStyleExtractor, ExtractedStyles

logger = logging.getLogger(__name__)

# Constants
MAX_HTML_SIZE = 50 * 1024 * 1024  # 50MB - Maximum HTML content size


@dataclass
class ConversionResult:
    """Conversion result"""
    success: bool
    output_path: Optional[str] = None
    file_size: Optional[int] = None
    pages_estimate: Optional[int] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "output_path": self.output_path,
            "file_size": self.file_size,
            "pages_estimate": self.pages_estimate,
            "error": self.error,
            "error_code": self.error_code
        }


class HTMLToWordConverter:
    """
    HTML to Word Converter
    
    Converts HTML intermediate format to Word documents.
    
    Usage example:
        converter = HTMLToWordConverter()
        result = converter.convert(
            html="<article><h1>Title</h1><p>Content</p></article>",
            output_path="output.docx"
        )
        
        if result.success:
            print(f"File saved: {result.output_path}")
    """
    
    # Default styles
    DEFAULT_STYLES = {
        "title_font": "Microsoft YaHei",
        "body_font": "Microsoft YaHei",
        "title_size": 28,
        "h1_size": 24,
        "h2_size": 20,
        "h3_size": 16,
        "h4_size": 14,
        "body_size": 12,
        "line_spacing": 1.5
    }
    
    def __init__(self, styles: Optional[Dict[str, Any]] = None):
        """
        Initialize converter
        
        Args:
            styles: Custom style configuration
        """
        self.styles = {**self.DEFAULT_STYLES, **(styles or {})}
        self._docx_available = self._check_docx_available()
        
        if not self._docx_available:
            logger.warning("python-docx not available, converter will have limited functionality")
    
    def _check_docx_available(self) -> bool:
        """Check if python-docx is available"""
        try:
            from docx import Document  # noqa: F401
            return True
        except ImportError:
            return False
    
    def get_default_styles(self) -> Dict[str, Any]:
        """Get default styles"""
        return self.DEFAULT_STYLES.copy()
    
    def _merge_styles(
        self,
        extracted_styles: Optional[ExtractedStyles],
        custom_styles: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Merge styles
        
        Merge order: Template styles → Default styles → Custom styles
        
        Args:
            extracted_styles: Styles extracted from template
            custom_styles: User custom styles
            
        Returns:
            Merged style dictionary
        """
        # Default styles as base
        final_styles = self.DEFAULT_STYLES.copy()
        
        # Apply template extracted styles (higher priority than defaults)
        if extracted_styles:
            template_styles = extracted_styles.to_word_styles()
            final_styles.update(template_styles)
            logger.debug(f"Applied template styles: {template_styles}")
        
        # Apply custom styles (highest priority)
        if custom_styles:
            final_styles.update(custom_styles)
            logger.debug(f"Applied custom styles: {custom_styles}")
        
        return final_styles
    
    def convert(
        self,
        html: str,
        output_path: str,
        styles: Optional[Dict[str, Any]] = None,
        template_html: Optional[str] = None
    ) -> ConversionResult:
        """
        Convert HTML to Word document
        
        Args:
            html: HTML content
            output_path: Output file path
            styles: Custom styles (optional)
            template_html: HTML template content (for extracting CSS styles)
            
        Returns:
            ConversionResult conversion result
        """
        # ========== CONVERSION START ==========
        logger.info("[CONVERT] ========== Starting HTML to Word conversion ==========")
        
        # Input validation
        if not isinstance(html, str):
            logger.warning("[CONVERT] html is not a string, converting to empty string")
            html = ""
        
        logger.info(f"[CONVERT] Input HTML size: {len(html)} bytes")
        
        if not isinstance(output_path, str):
            logger.error("[CONVERT] FAILED: output_path is not a string")
            return ConversionResult(
                success=False,
                error="output_path must be a string",
                error_code="INVALID_PATH_TYPE"
            )
        
        logger.info(f"[CONVERT] Output path: {output_path}")
        
        # File size limit check
        if len(html) > MAX_HTML_SIZE:
            logger.error(f"[CONVERT] FAILED: HTML too large ({len(html)/1024/1024:.1f}MB > {MAX_HTML_SIZE/1024/1024}MB)")
            return ConversionResult(
                success=False,
                error=f"HTML content too large ({len(html)/1024/1024:.1f}MB > {MAX_HTML_SIZE/1024/1024}MB)",
                error_code="CONTENT_TOO_LARGE"
            )
        
        # Path safety check
        if not self._is_safe_path(output_path):
            logger.error(f"[CONVERT] FAILED: Unsafe path detected: {output_path}")
            return ConversionResult(
                success=False,
                error="Invalid or unsafe output path",
                error_code="UNSAFE_PATH"
            )
        
        logger.info("[CONVERT] Path safety check passed")
        
        # Empty HTML handling
        if not html.strip():
            logger.warning("[CONVERT] Empty HTML, creating minimal document")
            html = "<article><p></p></article>"
        
        # Preprocessing: Remove style blocks and residual template tags
        logger.info("[CONVERT] Step 1: Sanitizing HTML")
        html = self._sanitize_html(html)
        logger.info(f"[CONVERT] Sanitized HTML size: {len(html)} bytes")
        
        # Extract CSS styles from template HTML (if provided)
        extracted_styles = None
        if template_html:
            logger.info("[CONVERT] Step 2: Extracting CSS styles from template")
            extractor = CSSStyleExtractor()
            extracted_styles = extractor.extract_from_html(template_html)
            logger.info(f"[CONVERT] CSS extraction complete: title_size={extracted_styles.title_size}, h1_size={extracted_styles.h1_size}, h2_size={extracted_styles.h2_size}")
        else:
            logger.info("[CONVERT] Step 2: No template HTML, using default styles")
        
        # Merge styles: Template styles → Default styles → Custom styles
        final_styles = self._merge_styles(extracted_styles, styles)
        logger.info(f"[CONVERT] Step 3: Final styles merged: title_font={final_styles.get('title_font')}, body_font={final_styles.get('body_font')}, title_size={final_styles.get('title_size')}")
        
        try:
            # Ensure output directory exists
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                logger.info(f"[CONVERT] Creating output directory: {output_dir}")
                os.makedirs(output_dir, exist_ok=True)
            
            # Use base class parser
            logger.info("[CONVERT] Step 4: Parsing HTML elements")
            parser = HTMLElementParser()
            parser.feed(html)
            elements = parser.get_elements()
            logger.info(f"[CONVERT] Parsed {len(elements)} elements")
            
            # Log element types for debugging
            element_types = {}
            for elem in elements:
                elem_type = elem.get("type", "unknown")
                element_types[elem_type] = element_types.get(elem_type, 0) + 1
            logger.info(f"[CONVERT] Element breakdown: {element_types}")
            
            # Create Word document
            logger.info("[CONVERT] Step 5: Creating Word document")
            if self._docx_available:
                logger.info("[CONVERT] Using python-docx for document creation")
                result = self._create_docx_document(elements, output_path, final_styles, html)
            else:
                logger.warning("[CONVERT] python-docx not available, using fallback")
                result = self._create_fallback_document(elements, output_path, final_styles)
            
            if result.success:
                logger.info(f"[CONVERT] ========== Conversion SUCCESS ==========")
                logger.info(f"[CONVERT] Output: {result.output_path}")
                logger.info(f"[CONVERT] Size: {result.file_size} bytes")
                logger.info(f"[CONVERT] Pages estimate: {result.pages_estimate}")
            else:
                logger.error(f"[CONVERT] ========== Conversion FAILED ==========")
                logger.error(f"[CONVERT] Error: {result.error}")
                logger.error(f"[CONVERT] Error code: {result.error_code}")
            
            return result
                
        except (OSError, IOError) as e:
            logger.error(f"File operation failed: {e}")
            return ConversionResult(
                success=False,
                error=f"File operation failed: {e}",
                error_code="FILE_ERROR"
            )
        except ValueError as e:
            logger.error(f"Invalid data: {e}")
            return ConversionResult(
                success=False,
                error=f"Invalid data: {e}",
                error_code="DATA_ERROR"
            )
        except RuntimeError as e:
            logger.error(f"Processing error: {e}")
            return ConversionResult(
                success=False,
                error=f"Processing error: {e}",
                error_code="PROCESSING_ERROR"
            )
    
    def _sanitize_html(self, html: str) -> str:
        """
        Sanitize HTML content, remove content that shouldn't appear in Word
        
        1. Remove <style> tags and their content
        2. Remove residual template tags {% %} and {{ }}
        3. Remove other non-content tags
        4. **New**: Convert Markdown syntax to HTML tags
        
        Args:
            html: Original HTML content
            
        Returns:
            Sanitized HTML
        """
        import re
        
        # Remove <style> tags and content
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove <script> tags and content
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove <head> tags and content
        html = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove residual template tags
        html = re.sub(r'\{%.*?%\}', '', html, flags=re.DOTALL)
        html = re.sub(r'\{\{.*?\}\}', '', html, flags=re.DOTALL)
        
        # **New**: Convert Markdown syntax to HTML tags
        html = self._convert_markdown_to_html(html)
        
        # Clean extra whitespace
        html = re.sub(r'\n\s*\n\s*\n', '\n\n', html)
        
        return html.strip()
    
    def _convert_markdown_to_html(self, text: str) -> str:
        """
        Convert Markdown syntax to HTML tags
        
        Handled syntax:
        - **bold** → <strong>bold</strong>
        - *italic* → <em>italic</em>
        - `code` → <code>code</code>
        - [link](url) → <a href="url">link</a>
        - ~~strikethrough~~ → <del>strikethrough</del>
        
        Note: Only process text content between HTML tags, avoid breaking HTML structure
        
        Args:
            text: Text that may contain Markdown syntax
            
        Returns:
            Converted HTML
        """
        import re
        
        # Protect content in HTML tag attributes (avoid accidental conversion)
        # Strategy: Process in segments, only convert text outside tags
        
        # Simplified approach: Process Markdown syntax directly, but avoid processing inside HTML tags
        # Regex to detect if inside HTML tag: <...>
        
        # Split text into HTML tags and non-tag parts
        parts = re.split(r'(<[^>]+>)', text)
        
        result_parts = []
        for part in parts:
            # If it's an HTML tag, keep unchanged
            if part.startswith('<') and part.endswith('>'):
                result_parts.append(part)
            else:
                # Non-tag part, convert Markdown syntax
                converted = self._convert_markdown_inline(part)
                result_parts.append(converted)
        
        return ''.join(result_parts)
    
    def _convert_markdown_inline(self, text: str) -> str:
        """
        Convert inline Markdown syntax to HTML
        
        Processing order matters: process longer patterns first to avoid partial matches
        
        Args:
            text: Plain text content
            
        Returns:
            Converted HTML
        """
        import re
        
        # 1. Strikethrough ~~text~~
        text = re.sub(r'~~([^~]+)~~', r'<del>\1</del>', text)
        
        # 2. Bold **text** (must process before italic to avoid * being matched)
        text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
        
        # 3. Italic *text* or _text_
        text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
        text = re.sub(r'_([^_]+)_', r'<em>\1</em>', text)
        
        # 4. Inline code `code`
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        
        # 5. Link [text](url)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        
        return text
    
    def _is_safe_path(self, path: str, base_dir: Optional[str] = None) -> bool:
        """
        Check if path is safe
        
        Args:
            path: File path
            base_dir: Allowed base directory (optional, defaults to no restriction)
            
        Returns:
            Whether safe
        """
        try:
            resolved_path = Path(path).resolve()
            
            # Check path traversal ('..' as explicit check)
            if '..' in path:
                return False
            
            # If base directory specified, check if path is within allowed directory
            if base_dir is not None:
                base_path = Path(base_dir).resolve()
                
                # Check if absolute path is within allowed directory
                try:
                    if not resolved_path.is_relative_to(base_path):
                        return False
                except AttributeError:
                    # Fallback for Python < 3.9
                    try:
                        resolved_path.relative_to(base_path)
                    except ValueError:
                        return False
            
            # Check if path is absolute or valid relative path
            # Forbid access to system sensitive directories (exact match)
            dangerous_paths = [
                Path('/etc'), Path('/sys'), Path('/proc'), Path('/root'),
                Path('C:/Windows'), Path('C:/Windows/System32'),
                Path('D:/Windows'),  # Prevent other drive letters
            ]
            for dangerous in dangerous_paths:
                try:
                    if resolved_path.is_relative_to(dangerous):
                        return False
                except (AttributeError, ValueError):
                    # Fallback: Check path prefix
                    if str(resolved_path).startswith(str(dangerous)):
                        return False
            
            return True
            
        except (OSError, ValueError):
            return False
    
    def _atomic_save(self, doc: Any, output_path: str) -> None:
        """
        Atomically save document
        
        Use temp file + shutil.move to ensure atomic write.
        
        Args:
            doc: Document object
            output_path: Final output path
        """
        import shutil
        
        logger.info(f"[CONVERT] Atomic save starting, target: {output_path}")
        
        # Create temp file (don't use file descriptor)
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        temp_path = tempfile.mktemp(suffix='.docx', dir=output_dir or '.')
        logger.info(f"[CONVERT] Temp file path: {temp_path}")
        
        try:
            logger.info(f"[CONVERT] Saving document to temp file...")
            doc.save(temp_path)
            temp_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
            logger.info(f"[CONVERT] Temp file saved, size: {temp_size} bytes")
            
            logger.info(f"[CONVERT] Moving temp file to final location...")
            shutil.move(temp_path, output_path)
            logger.info(f"[CONVERT] Atomic save complete: {output_path}")
        except Exception as e:
            logger.error(f"[CONVERT] Atomic save FAILED: {e}")
            # Clean up temp file
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    logger.info(f"[CONVERT] Cleaned up temp file: {temp_path}")
            except OSError as cleanup_err:
                logger.warning(f"[CONVERT] Failed to cleanup temp file: {cleanup_err}")
            raise
    
    def _create_docx_document(
        self,
        elements: List[Dict[str, Any]],
        output_path: str,
        styles: Dict[str, Any],
        html: str = ""
    ) -> ConversionResult:
        """
        Create Word document using python-docx
        
        Args:
            elements: Parsed element list
            output_path: Output path
            styles: Style configuration
            
        Returns:
            ConversionResult
        """
        from docx import Document
        from docx.shared import Pt, RGBColor, Cm
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING

        from .word_styles import (
            NAVY,
            GOLD,
            COVER_META_FILL,
            cn_num,
            TABLE_HEADER_FILL,
            TABLE_ZEBRA_FILL,
            STRUCTURAL_HEADINGS,
            FONT_BODY_CN,
            FONT_HEADING_CN,
            FONT_WESTERN,
            GRAY_TEXT,
            PAGE_HEIGHT_CM,
            PAGE_WIDTH_CM,
            MARGIN_TOP_BOTTOM_CM,
            MARGIN_LEFT_RIGHT_CM,
            CONTENT_WIDTH_CM,
            add_field_run,
            compute_image_width_cm,
            mark_header_row_repeat,
            mark_row_cant_split,
            set_first_line_indent_chars,
            set_paragraph_bottom_border,
            set_table_header_cell_border,
            set_update_fields_on_open,
            shade_cell_or_paragraph,
            strip_heading_number,
            style_three_line_table,
            IMAGE_FALLBACK_WIDTH_CM,
        )

        doc = Document()

        # 页面：A4 + 研报边距（上下 2.54cm、左右 3.17cm）
        word_section = doc.sections[0]
        word_section.page_width = Cm(PAGE_WIDTH_CM)
        word_section.page_height = Cm(PAGE_HEIGHT_CM)
        word_section.top_margin = Cm(MARGIN_TOP_BOTTOM_CM)
        word_section.bottom_margin = Cm(MARGIN_TOP_BOTTOM_CM)
        word_section.left_margin = Cm(MARGIN_LEFT_RIGHT_CM)
        word_section.right_margin = Cm(MARGIN_LEFT_RIGHT_CM)

        # Normal 样式：中文宋体 + 西文 Times New Roman 10.5pt，单倍行距，段后 0
        style = doc.styles['Normal']
        font = style.font
        font.name = FONT_WESTERN
        font.size = Pt(10.5)
        style._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY_CN)
        # Apply body color (from CSS body color)
        body_color = styles.get("body_color", None)
        if body_color:
            rgb = self._parse_color_to_rgb(body_color)
            if rgb:
                font.color.rgb = RGBColor(*rgb)
        # Set paragraph spacing: Normal 保持单倍行距。固定 22pt 行距下沉到正文
        # 段落显式设置（全局 EXACTLY 会裁切封面 28pt 标题/目录 18pt 标题等大字号段落）
        pf = style.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.line_spacing_rule = WD_LINE_SPACING.SINGLE

        paragraph_count = 0
        current_section_info = {}  # Current section info
        in_cover_area = True  # Whether in cover/TOC area (before first section)
        current_div_class = ""  # Current div class (cover-page/toc etc.)
        cover_title_added = False  # Whether cover title has been added
        last_h1_text = ""  # 上一个 H1 去编号文本（重复标题去重）
        h1c = h2c = h3c = 0  # 标题自动编号计数器（H1 中文数字 / H2、H3 点分）
        chart_number = 0  # 图表连续编号
        
        for elem_idx, element in enumerate(elements):
            elem_type = element.get("type", "")
            next_elem_type = elements[elem_idx + 1].get("type", "") if elem_idx + 1 < len(elements) else ""
            
            # Handle div markers: identify cover/TOC areas
            if elem_type == "div_start":
                current_div_class = element.get("class", "")
                # When cover starts, add top whitespace (centered slightly above)
                if current_div_class == "cover-page":
                    # 3 empty paragraphs ≈ 75px, make title at top 1/3 of page (centered slightly above)
                    for _ in range(3):
                        doc.add_paragraph("")
                continue
            elif elem_type == "div_end":
                # div end: add page break
                if current_div_class == "cover-page":
                    # Add page break after cover
                    doc.add_page_break()
                elif current_div_class == "toc":
                    # Add page break after TOC
                    doc.add_page_break()
                elif current_div_class == "toc-page":
                    # Template uses toc-page for the TOC container
                    doc.add_page_break()
                elif current_div_class == "disclaimer-page":
                    # End-matter: break before and after for a clean tail page
                    try:
                        doc.add_page_break()
                    except Exception:
                        pass
                current_div_class = ""
                continue
            
            # Handle section markers: add page break before entering body area
            if elem_type == "section_start":
                if in_cover_area:
                    in_cover_area = False
                current_section_info = {
                    "id": element.get("id", ""),
                    "class": element.get("class", ""),
                    "data_type": element.get("data_type", "")
                }
                continue
            elif elem_type == "section_end":
                current_section_info = {}
                continue
            
            if elem_type == "heading":
                level = element.get("level", 1)
                text = element.get("text", "")
                css_class = element.get("style", "") or element.get("class", "")
                
                if text:
                    # Cover title special handling
                    if current_div_class == "cover-page" and level == 1 and not cover_title_added:
                        # Cover main title: large, centered, dark color
                        title_para = doc.add_paragraph()
                        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        title_run = title_para.add_run(text)
                        title_run.font.size = Pt(styles.get("title_size", 28))
                        title_run.font.name = "Microsoft YaHei"
                        title_run._element.rPr.rFonts.set(qn('w:eastAsia'), "Microsoft YaHei")
                        title_run.font.bold = True
                        # Apply title color
                        title_color = styles.get("title_color", "#1C2B36")
                        rgb = self._parse_color_to_rgb(title_color)
                        if rgb:
                            title_run.font.color.rgb = RGBColor(*rgb)
                        cover_title_added = True
                        paragraph_count += 1
                    # TOC title special handling
                    elif current_div_class in ("toc", "toc-page") and level == 2:
                        # TOC title: centered, large, letter spacing
                        toc_title = doc.add_paragraph()
                        toc_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        toc_run = toc_title.add_run(text)
                        toc_run.font.size = Pt(18)
                        toc_run.font.name = FONT_WESTERN
                        toc_run._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_HEADING_CN)
                        toc_run.font.bold = True
                        toc_run.font.color.rgb = RGBColor(*self._parse_color_to_rgb(NAVY))
                        # Add empty line after TOC title
                        doc.add_paragraph("")
                        # 插入真 TOC 域（打开文档时由 updateFields 自动刷新页码）
                        toc_field_para = doc.add_paragraph()
                        add_field_run(toc_field_para, 'TOC \\o "1-3" \\h \\z \\u')
                        paragraph_count += 2
                    else:
                        # Normal heading：研究写作模板的内部结构标题
                        # （论证与分析/核心结论等）不进入正文标题流
                        if text.strip() in STRUCTURAL_HEADINGS:
                            logger.info("跳过结构性标题: %s", text.strip())
                            continue
                        # Normal heading：重复标题去重（H2 与前一 H1 去编号后同文则跳过）
                        stripped_text = strip_heading_number(text)
                        if level == 2 and last_h1_text and stripped_text == last_h1_text:
                            logger.info(f"[CONVERT] Skip duplicate heading after H1: {text}")
                        else:
                            if level == 1:
                                last_h1_text = stripped_text
                            # 自动编号（先去重判断再编号，去重命中的 H2 不消耗 h2c；
                            # 编号基于剥离旧编号后的文本，真 TOC 域自动带出编号）：
                            # H1 "一、二、…" / H2 "1.1" / H3 "1.1.1"，level>=4 不编号；
                            # 首个 H1 之前的前置区标题（h1c==0）不编号
                            if level == 1:
                                h1c += 1
                                h2c = h3c = 0
                                text = f"{cn_num(h1c)}、{stripped_text}"
                            elif level == 2 and h1c > 0:
                                h2c += 1
                                h3c = 0
                                text = f"{h1c}.{h2c} {stripped_text}"
                            elif level == 3 and h1c > 0:
                                h3c += 1
                                if h2c == 0:
                                    # 本章尚无 H2：降级为两段编号 "1.1"，
                                    # 并占用 H2 编号槽位（后续 H2 从 1.2 继续）
                                    text = f"{h1c}.{h3c} {stripped_text}"
                                    h2c = h3c
                                else:
                                    text = f"{h1c}.{h2c}.{h3c} {stripped_text}"
                            safe_level = max(1, min(level, 9))
                            heading = doc.add_heading(text, level=safe_level)
                            self._apply_heading_style(heading, safe_level, styles, css_class)
                            paragraph_count += 1
            
            elif elem_type == "paragraph":
                text = element.get("text", "")
                para_class = element.get("class", "")
                
                if text:
                    para = doc.add_paragraph()
                    
                    # Cover area special handling
                    if current_div_class == "cover-page":
                        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        
                        # Badge style (RESEARCH REPORT)
                        if para_class == "cover-badge":
                            run = para.add_run(text)
                            run.font.size = Pt(11)
                            run.font.name = "Microsoft YaHei"
                            run._element.rPr.rFonts.set(qn('w:eastAsia'), "Microsoft YaHei")
                            run.font.color.rgb = RGBColor(0xC9, 0xA2, 0x27)
                        # Subtitle style
                        elif para_class == "cover-subtitle" or para_class == "subtitle":
                            run = para.add_run(text)
                            run.font.size = Pt(14)
                            run.font.name = "Microsoft YaHei"
                            run._element.rPr.rFonts.set(qn('w:eastAsia'), "Microsoft YaHei")
                            # Subtitle color
                            rgb = self._parse_color_to_rgb("#2C4A5A")
                            if rgb:
                                run.font.color.rgb = RGBColor(*rgb)
                        # Divider style: 空文本 + 段落底边框 2.25pt 金色实线
                        elif para_class == "cover-divider":
                            set_paragraph_bottom_border(para, sz=18, color=GOLD)
                        # Metadata style (author, date): 浅灰底色块
                        elif para_class == "cover-meta" or para_class == "meta":
                            run = para.add_run(text)
                            run.font.size = Pt(11)
                            run.font.name = FONT_WESTERN
                            run._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY_CN)
                            # Metadata color (gray)
                            rgb = self._parse_color_to_rgb("#888888")
                            if rgb:
                                run.font.color.rgb = RGBColor(*rgb)
                            shade_cell_or_paragraph(para, COVER_META_FILL)
                        # Logo style
                        elif para_class == "cover-logo":
                            run = para.add_run(text)
                            run.font.size = Pt(14)
                            run.font.bold = True
                            run.font.name = "Microsoft YaHei"
                            run._element.rPr.rFonts.set(qn('w:eastAsia'), "Microsoft YaHei")
                            run.font.color.rgb = RGBColor(0xC9, 0xA2, 0x27)
                        # GitHub style
                        elif para_class == "cover-github":
                            run = para.add_run(text)
                            run.font.size = Pt(9)
                            run.font.name = "Microsoft YaHei"
                            run._element.rPr.rFonts.set(qn('w:eastAsia'), "Microsoft YaHei")
                            run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
                        else:
                            self._add_formatted_run(para, text, element.get("formats", []))
                    
                    # TOC area special handling
                    elif current_div_class in ("toc", "toc-page"):
                        # All paragraphs in TOC are TOC items (template rendering ensures this)
                        run = para.add_run(text)
                        run.font.size = Pt(12)
                        run.font.name = "Microsoft YaHei"
                        run._element.rPr.rFonts.set(qn('w:eastAsia'), "Microsoft YaHei")
                        # TOC item bottom dashed border effect (simulated with dots)
                        # python-docx doesn't support dashed borders, skip for now
                    
                    # Other areas: 正文段落（两端对齐 + 首行缩进 2 字符 + 固定 22pt 行距）
                    else:
                        self._add_formatted_run(para, text, element.get("formats", []))
                        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                        set_first_line_indent_chars(para)
                        # 券商研报正文固定行距 22pt（EXACTLY），只在正文段落显式下沉设置
                        body_pf = para.paragraph_format
                        body_pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
                        body_pf.line_spacing = Pt(22)

                    paragraph_count += 1

            elif elem_type == "list_item":
                text = element.get("text", "")
                list_type = element.get("list_type", "ul")
                li_class = element.get("class", "")

                if text:
                    if current_div_class in ("toc", "toc-page"):
                        # 目录区已插入真 TOC 域，跳过手写目录条目
                        pass
                    elif "toc-item" in li_class:
                        # 兼容：toc 目录区之外的手写目录条目（主流程不再触达）
                        self._add_toc_item(doc, text, li_class)
                        paragraph_count += 1
                    elif list_type == 'ol':
                        para = doc.add_paragraph(text, style='List Number')
                        # 列表段落显式单倍行距，防止继承残留的固定行距
                        para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                        paragraph_count += 1
                    else:
                        para = doc.add_paragraph(text, style='List Bullet')
                        para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                        paragraph_count += 1
            
            elif elem_type == "table":
                # Support both combined data and separate headers+rows formats
                data = element.get("data", [])
                if not data and element.get("headers") and element.get("rows"):
                    data = [element["headers"]] + element["rows"]
                
                if data:
                    # Calculate actual column count considering colspan
                    cols = 0
                    for row_data in data:
                        row_cols = 0
                        for cell_data in row_data:
                            if isinstance(cell_data, dict):
                                row_cols += cell_data.get("colspan", 1)
                            else:
                                row_cols += 1
                        cols = max(cols, row_cols)
                    
                    rows = len(data)

                    if rows > 0 and cols > 0:
                        table = doc.add_table(rows=rows, cols=cols)

                        try:
                            from docx.oxml.ns import qn
                            from docx.oxml import OxmlElement
                            from docx.shared import Pt, RGBColor
                            has_style_support = True
                        except ImportError:
                            has_style_support = False

                        # 三线表：上下 1pt 藏青粗线，无竖线/内线（显式不使用 Table Grid）
                        style_three_line_table(table)
                        # 跨页重复表头
                        mark_header_row_repeat(table.rows[0])

                        # 自适应布局 + 全宽 + 单元格内边距（避免列宽均分难读）
                        tbl = table._tbl
                        tbl_pr = tbl.tblPr
                        table.autofit = True
                        # 覆盖 tblW 为 100% pct（add_table 默认 type=auto/w=0）
                        tbl_w = tbl_pr.find(qn('w:tblW'))
                        if tbl_w is None:
                            tbl_w = OxmlElement('w:tblW')
                            # tblW 在 tblPr 序列中位于 jc/tblCellSpacing/tblInd/tblBorders 等之前
                            tbl_pr.insert_element_before(
                                tbl_w, 'w:jc', 'w:tblCellSpacing', 'w:tblInd',
                                'w:tblBorders', 'w:shd', 'w:tblLayout',
                                'w:tblCellMar', 'w:tblLook',
                            )
                        tbl_w.set(qn('w:w'), '5000')
                        tbl_w.set(qn('w:type'), 'pct')
                        # autofit 布局（table.autofit setter 通常已建 tblLayout，此处兜底）
                        tbl_layout = tbl_pr.find(qn('w:tblLayout'))
                        if tbl_layout is None:
                            tbl_layout = OxmlElement('w:tblLayout')
                            # tblLayout 在 tblPr 序列中位于 tblCellMar/tblLook 之前
                            tbl_pr.insert_element_before(
                                tbl_layout, 'w:tblCellMar', 'w:tblLook'
                            )
                        tbl_layout.set(qn('w:type'), 'autofit')
                        # 单元格内边距（dxa，1/20 pt）
                        if tbl_pr.find(qn('w:tblCellMar')) is None:
                            cellmar = OxmlElement('w:tblCellMar')
                            # tblCellMar 在 tblPr 序列中位于 tblLook 之前
                            tbl_pr.insert_element_before(cellmar, 'w:tblLook')
                            for side, w in (('top', 40), ('left', 80), ('bottom', 40), ('right', 80)):
                                el = OxmlElement(f'w:{side}')
                                el.set(qn('w:w'), str(w))
                                el.set(qn('w:type'), 'dxa')
                                cellmar.append(el)

                        # Track absorbed cells to avoid overwriting merged content
                        absorbed = set()

                        for i, row_data in enumerate(data):
                            actual_j = 0  # Actual column position (skip absorbed)
                            for j, cell_data in enumerate(row_data):
                                # Skip absorbed column positions
                                while actual_j < cols and (i, actual_j) in absorbed:
                                    actual_j += 1
                                if actual_j >= cols:
                                    break

                                cell = table.rows[i].cells[actual_j]

                                if isinstance(cell_data, dict):
                                    cell_text = str(cell_data.get("text", ""))
                                    colspan = cell_data.get("colspan", 1)
                                    rowspan = cell_data.get("rowspan", 1)
                                    is_header = cell_data.get("tag") == "th"

                                    # Merge cells
                                    if colspan > 1 or rowspan > 1:
                                        end_row = min(i + rowspan - 1, rows - 1)
                                        end_col = min(actual_j + colspan - 1, cols - 1)
                                        if end_row > i or end_col > actual_j:
                                            cell.merge(table.rows[end_row].cells[end_col])
                                            # Mark absorbed cell positions
                                            for ri in range(i, end_row + 1):
                                                for ci in range(actual_j, end_col + 1):
                                                    if ri != i or ci != actual_j:
                                                        absorbed.add((ri, ci))
                                            cell = table.rows[i].cells[actual_j]
                                else:
                                    cell_text = str(cell_data) if cell_data is not None else ""
                                    is_header = (i == 0)

                                # Set text
                                cell.text = cell_text

                                # 单元格段落：紧凑行距 + space 2pt
                                if has_style_support:
                                    for paragraph in cell.paragraphs:
                                        c_pf = paragraph.paragraph_format
                                        c_pf.space_before = Pt(0)
                                        c_pf.space_after = Pt(2)
                                        c_pf.line_spacing = 1.0
                                        for run in paragraph.runs:
                                            run.font.size = Pt(9.5 if (is_header or i == 0) else 9)

                                # Header style: 浅藏青底 + 藏青深字加粗 9.5pt（三线表表头）
                                if (is_header or i == 0) and has_style_support:
                                    for paragraph in cell.paragraphs:
                                        for run in paragraph.runs:
                                            run.font.bold = True
                                            run.font.color.rgb = RGBColor(*self._parse_color_to_rgb(NAVY))
                                    shade_cell_or_paragraph(cell, TABLE_HEADER_FILL)
                                    set_table_header_cell_border(cell)

                                actual_j += 1

                        # 斑马纹：数据行（i>0）奇数行隔行浅底纹（逐 cell 设置，
                        # 行级无 w:shd）；所有行加 cantSplit 防跨页断裂
                        for zebra_idx, zebra_row in enumerate(table.rows):
                            mark_row_cant_split(zebra_row)
                            if zebra_idx > 0 and zebra_idx % 2 == 1:
                                for zebra_cell in zebra_row.cells:
                                    shade_cell_or_paragraph(zebra_cell, TABLE_ZEBRA_FILL)

                        paragraph_count += 1
            
            # Image
            elif elem_type == "image":
                img_path = element.get("src", "")
                if img_path and os.path.exists(img_path):
                    try:
                        from docx.shared import Cm as _Cm
                        # 按像素宽与 200dpi 自适应宽度；饼/雷达等近方形图限宽 11cm
                        px_w = px_h = 0
                        try:
                            from PIL import Image as PILImage
                            with PILImage.open(img_path) as im:
                                px_w, px_h = im.size
                            width = _Cm(compute_image_width_cm(px_w, px_h))
                        except Exception as pil_err:
                            logger.warning(f"PIL read image size failed, fallback width: {pil_err}")
                            width = _Cm(IMAGE_FALLBACK_WIDTH_CM)

                        # 图表编号：图片上方"图表 N：{图题}"（黑体 9pt 藏青）
                        chart_number += 1
                        chart_title = element.get("title") or element.get("alt") or ""
                        num_para = doc.add_paragraph()
                        num_para.paragraph_format.keep_with_next = True
                        # 题注段落显式单倍行距（不设大纲级别，保持不进 TOC）
                        num_para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                        num_para.paragraph_format.line_spacing = 1.0
                        num_run = num_para.add_run(
                            f"图表 {chart_number}：{chart_title}" if chart_title else f"图表 {chart_number}"
                        )
                        num_run.font.size = Pt(9)
                        num_run.font.bold = False
                        num_run.font.name = FONT_WESTERN
                        num_run._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_HEADING_CN)
                        num_run.font.color.rgb = RGBColor(*self._parse_color_to_rgb(NAVY))

                        doc.add_picture(img_path, width=width)
                        # 图片段落居中，并与下方注释绑定不分页
                        last_para = doc.paragraphs[-1]
                        last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        last_para.paragraph_format.keep_with_next = True
                        # Normal 固定行距 22pt（EXACTLY）会把内联图片裁成细条，
                        # 图片段落显式重置为单倍行距
                        last_para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                        last_para.paragraph_format.line_spacing = 1.0
                        # 占位空段仅在后随图注时保持绑定，避免图与图注分页断链
                        spacer_para = doc.add_paragraph()
                        spacer_run = spacer_para.add_run("")
                        spacer_run.font.size = Pt(6)
                        # spacer 同样不继承固定行距
                        spacer_para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                        spacer_para.paragraph_format.line_spacing = 1.0
                        if next_elem_type == "figure_caption":
                            spacer_para.paragraph_format.keep_with_next = True
                        paragraph_count += 2
                    except Exception as e:
                        logger.warning(f"Failed to add image {img_path}: {e}")

            # Figure caption: centered gray caption below chart image
            elif elem_type == "figure_caption":
                text = element.get("text", "")
                if text:
                    from docx.shared import Pt as _Pt
                    cap_para = doc.add_paragraph()
                    cap_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    # 图注段落显式单倍行距，避免继承 Normal 固定 22pt 行距
                    cap_para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                    cap_para.paragraph_format.line_spacing = 1.0
                    cap_run = cap_para.add_run(text)
                    cap_run.font.size = _Pt(8.5)
                    cap_run.font.name = FONT_WESTERN
                    cap_run._element.rPr.rFonts.set(qn('w:eastAsia'), FONT_BODY_CN)
                    rgb = self._parse_color_to_rgb("#666666")
                    if rgb:
                        cap_run.font.color.rgb = RGBColor(*rgb)
                    paragraph_count += 1
        
        # 添加页眉页脚
        if len(doc.sections) > 0:
            section = doc.sections[0]

            # 从HTML中提取报告标题
            report_title = ""
            title_match = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
            if title_match:
                report_title = title_match.group(1).strip()
            if not report_title:
                cover_title_match = re.search(r'class="cover-title"[^>]*>(.*?)</h1>', html, re.DOTALL)
                if cover_title_match:
                    report_title = cover_title_match.group(1).strip()
            if not report_title:
                report_title = "zensers Research Report"

            # 页眉：左 ZENSERS + 右报告标题（右对齐制表位），段落底边框 0.5pt 藏青
            header = section.header
            header.is_linked_to_previous = False
            header_para = header.paragraphs[0]
            header_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            try:
                from docx.enum.text import WD_TAB_ALIGNMENT
                header_para.paragraph_format.tab_stops.add_tab_stop(
                    Cm(CONTENT_WIDTH_CM), WD_TAB_ALIGNMENT.RIGHT
                )
            except Exception as tab_err:
                logger.warning(f"Header tab stop setup failed: {tab_err}")

            # 左侧Logo
            run = header_para.add_run("ZENSERS")
            run.font.size = Pt(8)
            run.font.bold = True
            run.font.color.rgb = RGBColor(*self._parse_color_to_rgb(NAVY))
            run.font.name = FONT_WESTERN

            # 右侧标题（动态获取）
            run = header_para.add_run("\t" + report_title)
            run.font.size = Pt(8)
            run.font.color.rgb = RGBColor(*self._parse_color_to_rgb(GRAY_TEXT))
            run.font.name = FONT_WESTERN

            # 页眉段落底边框 0.5pt 藏青横线
            set_paragraph_bottom_border(header_para, sz=4, color=NAVY)

            # 页脚：第一行居中 "第 X 页 共 Y 页"（PAGE/NUMPAGES 域）
            footer = section.footer
            footer.is_linked_to_previous = False
            footer_para = footer.paragraphs[0]
            footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

            footer_run_specs = []

            def _footer_run(text: str):
                r = footer_para.add_run(text)
                r.font.size = Pt(8.5)
                r.font.color.rgb = RGBColor(*self._parse_color_to_rgb(GRAY_TEXT))
                r.font.name = FONT_WESTERN
                return r

            footer_run_specs.append(_footer_run("第 "))
            footer_run_specs.extend(add_field_run(footer_para, "PAGE", placeholder="1"))
            footer_run_specs.append(_footer_run(" 页 共 "))
            footer_run_specs.extend(add_field_run(footer_para, "NUMPAGES", placeholder="1"))
            footer_run_specs.append(_footer_run(" 页"))
            for r in footer_run_specs:
                r.font.size = Pt(8.5)
                r.font.color.rgb = RGBColor(*self._parse_color_to_rgb(GRAY_TEXT))
                r.font.name = FONT_WESTERN

            # 第二行版权行（7pt 灰）
            copyright_para = footer.add_paragraph()
            copyright_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            copyright_run = copyright_para.add_run(
                "© 2026 zensers Research. github.com/sunchaokun/zensers"
            )
            copyright_run.font.size = Pt(7)
            copyright_run.font.color.rgb = RGBColor(*self._parse_color_to_rgb(GRAY_TEXT))
            copyright_run.font.name = FONT_WESTERN

        # 打开文档时自动刷新域（TOC/PAGE/NUMPAGES 页码）
        set_update_fields_on_open(doc)

        # Atomic save
        logger.info(f"[CONVERT] Saving document, total paragraphs: {paragraph_count}")
        self._atomic_save(doc, output_path)
        
        # Get file size
        file_size = os.path.getsize(output_path)
        
        # Estimate page count
        pages_estimate = max(1, paragraph_count // 20)
        
        logger.info(f"[CONVERT] Word document created successfully:")
        logger.info(f"[CONVERT]   Path: {output_path}")
        logger.info(f"[CONVERT]   Size: {file_size} bytes ({file_size/1024:.1f} KB)")
        logger.info(f"[CONVERT]   Paragraphs: {paragraph_count}")
        logger.info(f"[CONVERT]   Pages estimate: {pages_estimate}")
        
        return ConversionResult(
            success=True,
            output_path=output_path,
            file_size=file_size,
            pages_estimate=pages_estimate
        )
    
    def _apply_heading_style(self, heading, level: int, styles: Dict[str, Any], css_class: str = "") -> None:
        """
        Apply research-report heading typography (overrides legacy CSS-based logic)

        规范（设计文档 §6.2）：
        - H1: 黑体 16pt 加粗 藏青，段前分页，段后 18pt，底部 1pt 藏青横线
        - H2: 黑体 14pt 加粗 藏青，段前 12pt 段后 6pt
        - H3: 黑体 12pt 藏青
        - H4: 宋体 11pt 加粗 藏青
        - 西文统一 Times New Roman

        历史 CSS class（chapter-title/section-title/subsection-title/
        sub-subsection-title）不再参与字号选择：本实现按级别统一覆盖其规格，
        css_class 仅保留入参兼容。

        Args:
            heading: Heading object
            level: Heading level
            styles: Style configuration（保留参数兼容旧调用，字号/颜色以规范令牌为准）
            css_class: CSS class name（保留参数兼容旧签名）
        """
        from docx.shared import Pt, RGBColor
        from docx.oxml.ns import qn

        from .word_styles import (
            FONT_BODY_CN,
            FONT_HEADING_CN,
            FONT_WESTERN,
            NAVY,
            set_paragraph_bottom_border,
        )

        heading_specs = {
            1: {"size": 16, "font": FONT_HEADING_CN, "bold": True, "before": 0, "after": 18},
            2: {"size": 14, "font": FONT_HEADING_CN, "bold": True, "before": 12, "after": 6},
            3: {"size": 12, "font": FONT_HEADING_CN, "bold": False, "before": 6, "after": 3},
            4: {"size": 11, "font": FONT_BODY_CN, "bold": True, "before": 6, "after": 3},
        }
        spec = heading_specs.get(level, {"size": 12, "font": FONT_BODY_CN, "bold": False, "before": 6, "after": 3})

        # H1 段前分页 + 段后 18pt + 底部 1pt 藏青横线
        if level == 1:
            heading.paragraph_format.page_break_before = True
        heading.paragraph_format.space_before = Pt(spec["before"])
        heading.paragraph_format.space_after = Pt(spec["after"])
        # 标题不继承 Normal 的固定 22pt 行距（避免大字号裁切）
        heading.paragraph_format.line_spacing = 1.2

        heading_style_rgb = RGBColor(*self._parse_color_to_rgb(NAVY))
        for run in heading.runs:
            run.font.size = Pt(spec["size"])
            run.font.bold = spec["bold"]
            run.font.name = FONT_WESTERN
            run._element.rPr.rFonts.set(qn('w:eastAsia'), spec["font"])
            run.font.color.rgb = heading_style_rgb

        if level == 1:
            set_paragraph_bottom_border(heading, sz=8, color=NAVY)
    
    def _add_formatted_run(self, paragraph, text: str, formats: List[str]) -> None:
        """
        Add formatted text to paragraph
        
        Parse HTML inline tags in text (converted from Markdown)
        <strong>bold</strong> → bold
        <em>italic</em> → italic
        <code>code</code> → code
        
        Args:
            paragraph: Paragraph object
            text: Text that may contain HTML tags
            formats: Current format stack (passed from parser)
        """
        import re
        from docx.shared import Pt
        from docx.oxml.ns import qn
        
        # If text still has HTML tags (from Markdown conversion), parse them
        # Use regex to extract tags and text
        pattern = r'<(strong|em|code|del|a[^>]*)>([^<]+)</(strong|em|code|del|a)>'
        
        last_end = 0
        for match in re.finditer(pattern, text):
            # Add plain text before tag
            if match.start() > last_end:
                plain_text = text[last_end:match.start()]
                if plain_text:
                    run = paragraph.add_run(plain_text)
            
            # Add formatted text
            tag = match.group(1)
            content = match.group(2)
            
            run = paragraph.add_run(content)
            
            # Apply format
            if tag == 'strong':
                run.bold = True
            elif tag == 'em':
                run.italic = True
            elif tag == 'code':
                run.font.name = 'Courier New'
                run.font.size = Pt(10)
            elif tag.startswith('a:'):
                # Link: extract URL
                pass  # Word doesn't support links, just display text
            
            last_end = match.end()
        
        # Add remaining text
        if last_end < len(text):
            remaining = text[last_end:]
            # Clean other HTML tags
            remaining = re.sub(r'</?(strong|em|code|del|a[^>]*)>', '', remaining)
            if remaining:
                paragraph.add_run(remaining)
        
    def _add_toc_item(self, doc, text: str, li_class: str = "") -> None:
        """Add a TOC entry with dot leader + right-aligned page number.

        Expected text shape from render script: ``01标题...3`` or
        ``01.1子标题...3`` (number + title + page concatenated by parser).
        Level-2 items indent 1cm and use smaller gray type.
        """
        import re
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
        from docx.shared import Pt, RGBColor
        from docx.oxml.ns import qn

        level2 = "level2" in li_class
        m = re.match(r"^(\d+(?:\.\d+)?)\s*(.*)$", text.strip(), re.S)
        num, rest = (m.group(1), m.group(2)) if m else ("", text.strip())
        mp = re.search(r"(\d+)\s*$", rest)
        page = mp.group(1) if mp else ""
        title = rest[: mp.start()].strip() if mp else rest

        para = doc.add_paragraph()
        pf = para.paragraph_format
        pf.space_before = Pt(2)
        pf.space_after = Pt(2)
        pf.line_spacing = 1.15
        if level2:
            para.paragraph_format.left_indent = Pt(28)
        pf.tab_stops.clear_all() if hasattr(pf.tab_stops, "clear_all") else None
        try:
            pf.tab_stops.add_tab_stop(Pt(430), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        except Exception:
            pass
        is_l1 = not level2
        run = para.add_run(f"{num}  {title}" if num else title)
        run.font.size = Pt(12 if is_l1 else 10.5)
        run.font.bold = is_l1
        run.font.name = "Microsoft YaHei"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        run.font.color.rgb = RGBColor(0x00, 0x33, 0x66) if is_l1 else RGBColor(0x55, 0x55, 0x55)
        if page:
            trun = para.add_run(f"\t{page}")
            trun.font.size = Pt(12 if is_l1 else 10.5)
            trun.font.bold = is_l1
            trun.font.name = "Microsoft YaHei"
            trun._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
            trun.font.color.rgb = RGBColor(0x00, 0x33, 0x66) if is_l1 else RGBColor(0x55, 0x55, 0x55)

    def _parse_color_to_rgb(self, color_str: str):
        """
        Convert color string to RGB tuple
        
        Args:
            color_str: Color string (e.g., "#1A2744" or "rgb(26, 39, 68)")
            
        Returns:
            (r, g, b) tuple or None
        """
        import re
        
        if not color_str:
            return None
        
        # Hex color (兼容带 # 与不带 # 的令牌，如 "1A2744" / "#1A2744")
        if color_str.startswith('#'):
            hex_color = color_str[1:]
        else:
            hex_color = color_str
        if len(hex_color) == 6:
            return (
                int(hex_color[0:2], 16),
                int(hex_color[2:4], 16),
                int(hex_color[4:6], 16)
            )
        
        # RGB color
        match = re.match(r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', color_str)
        if match:
            return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        
        return None
    
    def _create_fallback_document(
        self,
        elements: List[Dict[str, Any]],
        output_path: str,
        styles: Dict[str, Any]
    ) -> ConversionResult:
        """
        Create fallback format document (when python-docx is not available)
        
        Args:
            elements: Parsed element list
            output_path: Output path
            styles: Style configuration
            
        Returns:
            ConversionResult
        """
        # Create plain text version
        text_lines = []
        
        for element in elements:
            elem_type = element.get("type", "")
            
            if elem_type == "heading":
                level = element.get("level", 1)
                text = element.get("text") or ""
                prefix = "#" * level
                text_lines.append(f"\n{prefix} {text}\n")
            
            elif elem_type == "paragraph":
                text = element.get("text") or ""
                text_lines.append(text)
            
            elif elem_type == "list_item":
                text = element.get("text") or ""
                list_type = element.get("list_type", "ul")
                if list_type == 'ol':
                    text_lines.append(f"1. {text}")
                else:
                    text_lines.append(f"- {text}")
            
            elif elem_type == "table":
                data = element.get("data", [])
                if not data and element.get("headers") and element.get("rows"):
                    data = [element["headers"]] + element["rows"]
                for row in data:
                    safe_row = [str(cell) if cell is not None else "" for cell in row]
                    text_lines.append(" | ".join(safe_row))
        
        content = "\n".join(text_lines)
        
        # Change to .txt extension
        txt_path = output_path.rsplit('.', 1)[0] + '.txt'
        
        # Atomic write
        fd, temp_path = tempfile.mkstemp(suffix='.txt')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(temp_path, txt_path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
        
        file_size = os.path.getsize(txt_path)
        
        logger.warning(f"python-docx not available, created text file: {txt_path}")
        
        return ConversionResult(
            success=True,
            output_path=txt_path,
            file_size=file_size,
            pages_estimate=len(text_lines) // 30,
            error="python-docx not available, created text file instead"
        )


# Export
__all__ = ["HTMLToWordConverter", "ConversionResult"]
