# -*- coding: utf-8 -*-
"""
HTML to PPT Converter
=====================

Convert HTML intermediate format to PowerPoint document (.pptx).

Core Features:
1. HTML parsing and slide conversion
2. Slide type handling (cover, toc, content, data, end)
3. Title and content layout
4. List and table processing
5. Style application

Technology: python-pptx

Usage Example:
    converter = HTMLToPPTConverter()
    result = converter.convert(
        html="<section class='slide' data-type='cover'><h1>Title</h1></section>",
        output_path="output.pptx"
    )
"""

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base_parser import SlideElementParser
from .css_extractor import CSSStyleExtractor, ExtractedStyles

logger = logging.getLogger(__name__)

# Constants
MAX_HTML_SIZE = 50 * 1024 * 1024  # 50MB


@dataclass
class ConversionResult:
    """Conversion Result"""
    success: bool
    output_path: Optional[str] = None
    file_size: Optional[int] = None
    slides_count: Optional[int] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "output_path": self.output_path,
            "file_size": self.file_size,
            "slides_count": self.slides_count,
            "error": self.error,
            "error_code": self.error_code
        }


class HTMLToPPTConverter:
    """
    HTML to PPT Converter
    
    Convert HTML intermediate format to PowerPoint document.
    
    Usage Example:
        converter = HTMLToPPTConverter()
        result = converter.convert(
            html="<section class='slide' data-type='cover'><h1>Title</h1></section>",
            output_path="output.pptx"
        )
        
        if result.success:
            print(f"File saved: {result.output_path}")
    """
    
    # Default styles
    DEFAULT_STYLES = {
        "title_font": "Microsoft YaHei",
        "body_font": "Microsoft YaHei",
        "title_size": 44,
        "subtitle_size": 28,
        "body_size": 18,
        "slide_width": 10,  # inches
        "slide_height": 7.5  # inches
    }
    
    def __init__(self, styles: Optional[Dict[str, Any]] = None):
        """
        Initialize converter
        
        Args:
            styles: Custom style configuration
        """
        self.styles = {**self.DEFAULT_STYLES, **(styles or {})}
        self._pptx_available = self._check_pptx_available()
        
        if not self._pptx_available:
            logger.warning("python-pptx not available, converter will have limited functionality")
    
    def _check_pptx_available(self) -> bool:
        """Check if python-pptx is available"""
        try:
            from pptx import Presentation  # noqa: F401
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
        
        Merge order: template styles → default styles → custom styles
        
        Args:
            extracted_styles: Styles extracted from template
            custom_styles: User custom styles
            
        Returns:
            Merged style dictionary
        """
        # Default styles as base
        final_styles = self.DEFAULT_STYLES.copy()
        
        # Apply template-extracted styles (higher priority than defaults)
        if extracted_styles:
            template_styles = extracted_styles.to_ppt_styles()
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
        Convert HTML to PPT document
        
        Args:
            html: HTML content
            output_path: Output file path
            styles: Custom styles (optional)
            template_html: HTML template content (for extracting CSS styles)
            
        Returns:
            Conversion Result
        """
        # Input validation
        if not isinstance(html, str):
            logger.warning("html is not a string, converting to empty string")
            html = ""
        
        if not isinstance(output_path, str):
            return ConversionResult(
                success=False,
                error="output_path must be a string",
                error_code="INVALID_PATH_TYPE"
            )
        
        # File size limit check
        if len(html) > MAX_HTML_SIZE:
            return ConversionResult(
                success=False,
                error=f"HTML content too large ({len(html)/1024/1024:.1f}MB > {MAX_HTML_SIZE/1024/1024}MB)",
                error_code="CONTENT_TOO_LARGE"
            )
        
        # Path security check
        if not self._is_safe_path(output_path):
            return ConversionResult(
                success=False,
                error="Invalid or unsafe output path",
                error_code="UNSAFE_PATH"
            )
        
        # Empty HTML handling
        if not html.strip():
            logger.info("Empty HTML, creating minimal presentation")
            html = "<section class='slide' data-type='cover'><h1></h1></section>"
        
        # Preprocess HTML (cleanup + Markdown conversion)
        html = self._sanitize_html(html)
        
        # Extract CSS styles from template HTML (if any)
        extracted_styles = None
        if template_html:
            extractor = CSSStyleExtractor()
            extracted_styles = extractor.extract_from_html(template_html)
            logger.info("Extracted styles from template HTML")
        
        # Merge styles: template → default → custom
        final_styles = self._merge_styles(extracted_styles, styles)
        
        try:
            # Ensure output directory exists
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            # Use slide parser
            parser = SlideElementParser()
            parser.feed(html)
            slides = parser.get_slides()
            
            # Create PPT document
            if self._pptx_available:
                return self._create_pptx_document(slides, output_path, final_styles)
            else:
                return self._create_fallback_document(slides, output_path, final_styles)
                
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
    
    def _is_safe_path(self, path: str, base_dir: Optional[str] = None) -> bool:
        """
        Check if path is safe
        
        Args:
            path: File path
            base_dir: Allowed base directory (optional, defaults to current working directory)
            
        Returns:
            Whether safe
        """
        try:
            resolved_path = Path(path).resolve()
            
            # Check path traversal
            if '..' in path:
                return False
            
            # Determine base directory (default to current working directory if not specified)
            if base_dir is None:
                base_dir = str(Path.cwd())
            
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
            
            # Block access to sensitive system directories (exact match)
            dangerous_paths = [
                Path('/etc'), Path('/sys'), Path('/proc'), Path('/root'),
                Path('C:/Windows'), Path('C:/Windows/System32'),
                Path('D:/Windows'),
            ]
            for dangerous in dangerous_paths:
                try:
                    if resolved_path.is_relative_to(dangerous):
                        return False
                except (AttributeError, ValueError):
                    if str(resolved_path).startswith(str(dangerous)):
                        return False
            
            return True
            
        except (OSError, ValueError):
            return False
    
    def _sanitize_html(self, html: str) -> str:
        """
        Clean HTML content, remove content that should not appear in PPT
        
        1. Remove <style> tags and content
        2. Remove residual template tags {% %} and {{ }}
        3. Remove other non-content tags
        4. Convert Markdown syntax to HTML tags
        
        Args:
            html: Raw HTML content
            
        Returns:
            Cleaned HTML
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
        
        # Convert Markdown syntax to HTML tags
        html = self._convert_markdown_to_html(html)
        
        # Clean up excess whitespace
        html = re.sub(r'\n\s*\n\s*\n', '\n\n', html)
        
        return html.strip()
    
    def _convert_markdown_to_html(self, text: str) -> str:
        """
        Convert Markdown syntax to HTML tags
        
        Processed syntax:
        - **bold** → <strong>bold</strong>
        - *italic* → <em>italic</em>
        - `code` → <code>code</code>
        - [link](url) → <a href="url">link</a>
        - ~~strikethrough~~ → <del>strikethrough</del>
        
        Args:
            text: Text that may contain Markdown syntax
            
        Returns:
            Converted HTML
        """
        import re
        
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
        
        Args:
            text: Plain text content
            
        Returns:
            Converted HTML
        """
        import re
        
        # 1. Strikethrough ~~text~~
        text = re.sub(r'~~([^~]+)~~', r'<del>\1</del>', text)
        
        # 2. Bold **text**
        text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
        
        # 3. Italic *text* or _text_
        text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
        text = re.sub(r'_([^_]+)_', r'<em>\1</em>', text)
        
        # 4. Inline code `code`
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        
        # 5. Link [text](url)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        
        return text
    
    def _atomic_save(self, prs: Any, output_path: str) -> None:
        """
        Atomic save presentation
        
        Use temp file + shutil.move to ensure atomic write.
        
        Args:
            prs: Presentation object
            output_path: Final output path
        """
        import shutil
        
        # Create temp file (without file descriptor)
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        temp_path = tempfile.mktemp(suffix='.pptx', dir=output_dir or '.')
        try:
            prs.save(temp_path)
            # Use shutil.move instead of os.replace, more reliable
            shutil.move(temp_path, output_path)
        except Exception:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
    
    def _create_pptx_document(
        self,
        slides: List[Dict[str, Any]],
        output_path: str,
        styles: Dict[str, Any]
    ) -> ConversionResult:
        """
        Create PPT document using python-pptx
        
        Args:
            slides: Parsed slide list
            output_path: Output path
            styles: Style configuration
            
        Returns:
            ConversionResult
        """
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        
        # Create presentation
        prs = Presentation()
        
        # Set slide dimensions
        prs.slide_width = Inches(styles.get("slide_width", 10))
        prs.slide_height = Inches(styles.get("slide_height", 7.5))
        
        slides_count = 0
        
        for slide_data in slides:
            slide_type = slide_data.get("slide_type", "content")
            
            # Use blank layout
            slide_layout = prs.slide_layouts[6]
            slide = prs.slides.add_slide(slide_layout)
            slides_count += 1
            
            # Process by type
            if slide_type == "cover":
                self._create_cover_slide(slide, slide_data, styles)
            elif slide_type == "toc":
                self._create_toc_slide(slide, slide_data, styles)
            elif slide_type == "findings":
                self._create_findings_slide(slide, slide_data, styles)
            elif slide_type == "data":
                self._create_data_slide(slide, slide_data, styles)
            elif slide_type == "end":
                self._create_end_slide(slide, slide_data, styles)
            else:
                self._create_content_slide(slide, slide_data, styles)
        
        # Atomic save
        self._atomic_save(prs, output_path)
        
        # Get file size
        file_size = os.path.getsize(output_path)
        
        logger.info(f"PPT created: {output_path}, size={file_size}, slides={slides_count}")
        
        return ConversionResult(
            success=True,
            output_path=output_path,
            file_size=file_size,
            slides_count=slides_count
        )
    
    def _create_cover_slide(self, slide, slide_data: Dict[str, Any], styles: Dict[str, Any]):
        """Create cover slide"""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        
        title = slide_data.get("title", "")
        if title:
            title_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(2.5), Inches(9), Inches(1.5)
            )
            title_frame = title_box.text_frame
            # Support inline formatting
            self._add_formatted_text(title_frame.paragraphs[0], title, styles)
            title_frame.paragraphs[0].font.size = Pt(styles.get("title_size", 44))
            title_frame.paragraphs[0].font.bold = True
            title_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    
    def _create_toc_slide(self, slide, slide_data: Dict[str, Any], styles: Dict[str, Any]):
        """Create table of contents slide"""
        from pptx.util import Inches, Pt
        
        title = slide_data.get("title", "")
        if title:
            title_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(0.5), Inches(9), Inches(1)
            )
            title_frame = title_box.text_frame
            # Support inline formatting
            self._add_formatted_text(title_frame.paragraphs[0], title, styles)
            title_frame.paragraphs[0].font.size = Pt(styles.get("subtitle_size", 28))
            title_frame.paragraphs[0].font.bold = True
        
        items = slide_data.get("items", [])
        if items:
            content_box = slide.shapes.add_textbox(
                Inches(1), Inches(2), Inches(8), Inches(4)
            )
            tf = content_box.text_frame
            
            for i, item in enumerate(items):
                if i == 0:
                    p = tf.paragraphs[0]
                else:
                    p = tf.add_paragraph()
                # Support inline formatting
                self._add_formatted_text(p, item, styles)
                p.font.size = Pt(styles.get("body_size", 18))
    
    def _create_content_slide(self, slide, slide_data: Dict[str, Any], styles: Dict[str, Any]):
        """Create content slide"""
        from pptx.util import Inches, Pt
        
        title = slide_data.get("title", "")
        if title:
            title_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(0.5), Inches(9), Inches(1)
            )
            title_frame = title_box.text_frame
            # Support inline formatting
            self._add_formatted_text(title_frame.paragraphs[0], title, styles)
            title_frame.paragraphs[0].font.size = Pt(styles.get("subtitle_size", 28))
            title_frame.paragraphs[0].font.bold = True
        
        content = slide_data.get("content", "")
        items = slide_data.get("items", [])
        
        if content:
            content_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(1.5), Inches(9), Inches(5)
            )
            tf = content_box.text_frame
            tf.word_wrap = True
            # Support inline formatting
            self._add_formatted_text(tf.paragraphs[0], content, styles)
            tf.paragraphs[0].font.size = Pt(styles.get("body_size", 18))
        
        if items:
            content_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(1.5), Inches(9), Inches(5)
            )
            tf = content_box.text_frame
            
            for i, item in enumerate(items):
                if i == 0:
                    p = tf.paragraphs[0]
                else:
                    p = tf.add_paragraph()
                # Support inline formatting
                self._add_formatted_text(p, "• " + item, styles)
                p.font.size = Pt(styles.get("body_size", 18))
    
    def _create_findings_slide(self, slide, slide_data: Dict[str, Any], styles: Dict[str, Any]):
        """Create findings slide"""
        from pptx.util import Inches, Pt
        
        title = slide_data.get("title", "")
        if title:
            title_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(0.5), Inches(9), Inches(1)
            )
            title_frame = title_box.text_frame
            # Support inline formatting
            self._add_formatted_text(title_frame.paragraphs[0], title, styles)
            title_frame.paragraphs[0].font.size = Pt(styles.get("subtitle_size", 28))
            title_frame.paragraphs[0].font.bold = True
        
        items = slide_data.get("items", [])
        if items:
            content_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(1.5), Inches(9), Inches(5)
            )
            tf = content_box.text_frame
            
            for i, item in enumerate(items):
                if i == 0:
                    p = tf.paragraphs[0]
                else:
                    p = tf.add_paragraph()
                # Support inline formatting (using checkmark)
                self._add_formatted_text(p, "[v] " + item, styles)
                p.font.size = Pt(styles.get("body_size", 18))
    
    def _create_data_slide(self, slide, slide_data: Dict[str, Any], styles: Dict[str, Any]):
        """Create data slide"""
        from pptx.util import Inches, Pt
        
        title = slide_data.get("title", "")
        if title:
            title_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(0.5), Inches(9), Inches(1)
            )
            title_frame = title_box.text_frame
            # Support inline formatting
            self._add_formatted_text(title_frame.paragraphs[0], title, styles)
            title_frame.paragraphs[0].font.size = Pt(styles.get("subtitle_size", 28))
            title_frame.paragraphs[0].font.bold = True
        
        table_data = slide_data.get("table_data", [])
        if table_data:
            rows = len(table_data)
            cols = max(len(row) for row in table_data) if table_data else 0
            
            if rows > 0 and cols > 0:
                table = slide.shapes.add_table(
                    rows, cols, Inches(1), Inches(1.5), Inches(8), Inches(0.5 * rows)
                ).table
                
                for i, row_data in enumerate(table_data):
                    for j, cell_text in enumerate(row_data):
                        if j < cols:
                            # Clean up Markdown residuals
                            import re
                            clean_text = re.sub(r'</?(strong|em|code|del|a[^>]*)>', '', str(cell_text))
                            clean_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean_text)
                            clean_text = re.sub(r'\*([^*]+)\*', r'\1', clean_text)
                            clean_text = re.sub(r'`([^`]+)`', r'\1', clean_text)
                            table.cell(i, j).text = clean_text
    
    def _create_end_slide(self, slide, slide_data: Dict[str, Any], styles: Dict[str, Any]):
        """Create end slide"""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        
        title = slide_data.get("title", "")
        if title:
            title_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(2.5), Inches(9), Inches(1.5)
            )
            title_frame = title_box.text_frame
            # Support inline formatting
            self._add_formatted_text(title_frame.paragraphs[0], title, styles)
            title_frame.paragraphs[0].font.size = Pt(styles.get("title_size", 44))
            title_frame.paragraphs[0].font.bold = True
            title_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
        
        content = slide_data.get("content", "")
        if content:
            footer_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(5), Inches(9), Inches(1)
            )
            footer_frame = footer_box.text_frame
            # Support inline formatting
            self._add_formatted_text(footer_frame.paragraphs[0], content, styles)
            footer_frame.paragraphs[0].font.size = Pt(styles.get("body_size", 18))
            footer_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    
    def _add_formatted_text(self, paragraph, text: str, styles: Dict[str, Any]) -> None:
        """
        Add formatted text to paragraph
        
        Parse HTML inline tags in text (converted from Markdown)
        <strong>bold</strong> → bold
        <em>italic</em> → italic
        <code>code</code> → code
        
        Args:
            paragraph: Paragraph object
            text: Text that may contain HTML tags
            styles: Style configuration
        """
        import re
        from pptx.util import Pt
        
        # Clean HTML tags, extract plain text and format info
        # Simplified: directly clean HTML tags, PPT does not support complex inline formatting
        clean_text = re.sub(r'</?(strong|em|code|del|a[^>]*)>', '', text)
        
        # Check for bold markers
        has_bold = '<strong>' in text or '**' in text
        
        # Check for italic markers
        has_italic = '<em>' in text or '*' in text and '**' not in text
        
        # Check for code markers
        has_code = '<code>' in text or '`' in text
        
        paragraph.text = clean_text
        
        # Apply format (entire paragraph uses same format in PPT)
        if has_bold:
            paragraph.font.bold = True
        if has_italic:
            paragraph.font.italic = True
        if has_code:
            paragraph.font.name = 'Courier New'
            paragraph.font.size = Pt(styles.get("body_size", 18) - 2)
    
    def _create_fallback_document(
        self,
        slides: List[Dict[str, Any]],
        output_path: str,
        styles: Dict[str, Any]
    ) -> ConversionResult:
        """
        Create fallback format document (when python-pptx is unavailable)
        """
        # Create plain text version
        text_lines = []
        
        for i, slide in enumerate(slides, 1):
            slide_type = slide.get("slide_type", "content")
            text_lines.append(f"\n=== Slide {i} ({slide_type}) ===")
            
            if slide.get("title"):
                text_lines.append(f"Title: {slide['title']}")
            
            if slide.get("content"):
                text_lines.append(f"Content: {slide['content']}")
            
            items = slide.get("items", [])
            if items:
                text_lines.append("List items:")
                for item in items:
                    text_lines.append(f"  - {item}")
            
            table_data = slide.get("table_data", [])
            if table_data:
                text_lines.append("Table:")
                for row in table_data:
                    text_lines.append(f"  | {' | '.join(row)} |")
        
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
        
        logger.warning(f"python-pptx not available, created text file: {txt_path}")
        
        return ConversionResult(
            success=True,
            output_path=txt_path,
            file_size=file_size,
            slides_count=len(slides),
            error="python-pptx not available, created text file instead"
        )


# Export
__all__ = ["HTMLToPPTConverter", "ConversionResult"]