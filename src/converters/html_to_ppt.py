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
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_parser import SlideElementParser
from .css_extractor import CSSStyleExtractor, ExtractedStyles
from .ppt_theme import load_theme

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
        "slide_width": 13.333,  # inches (16:9)
        "slide_height": 7.5  # inches (16:9)
    }
    
    def __init__(self, styles: Optional[Dict[str, Any]] = None, theme: str = "default"):
        """
        Initialize converter
        
        Args:
            styles: Custom style configuration
            theme: PPT theme name (loaded from config/ppt_themes/<name>.json)
        """
        self.styles = {**self.DEFAULT_STYLES, **(styles or {})}
        self.theme_name = theme
        self.design = load_theme(theme)
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
    
    def _build_design(self, template_html: Optional[str]) -> Dict[str, Any]:
        """Merge theme file with CSS overrides extracted from the template.

        Priority: theme file base <- template CSS overrides (CSS wins where present).
        """
        design: Dict[str, Any] = {
            "colors": dict(self.design.get("colors", {})),
            "fonts": dict(self.design.get("fonts", {})),
        }
        design["font_default"] = design["fonts"].get("default", "Microsoft YaHei")
        if template_html:
            try:
                extractor = CSSStyleExtractor()
                extracted = extractor.extract_from_html(template_html)
                overrides = extracted.to_theme_overrides()
                design["colors"].update(overrides.get("colors", {}))
                if overrides.get("fonts"):
                    design["fonts"].update(overrides["fonts"])
                    design["font_default"] = overrides["fonts"].get(
                        "default", design["font_default"]
                    )
            except Exception as e:
                logger.warning(f"CSS override extraction failed, using theme defaults: {e}")
        return design
    
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
                design = self._build_design(template_html)
                return self._create_pptx_document(slides, output_path, final_styles, design=design)
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
    
    def _auto_generate_charts(self, slide_data: Dict, template_name: str, chart_gen) -> None:
        """Auto-generate chart images for slides with data but no images."""
        title = slide_data.get("title", "")
        items = slide_data.get("items", [])
        table_data = slide_data.get("table_data", [])
        text_parts = []
        if title:
            text_parts.append(title)
        for item in items:
            text_parts.append(item)
        text_for_analysis = "\n".join(text_parts)
        
        if table_data and not text_for_analysis.strip():
            table_text_parts = []
            for row in table_data:
                row_str = " | ".join(str(c) for c in row)
                table_text_parts.append(row_str)
            text_for_analysis = "\n".join(table_text_parts)
        
        if not text_for_analysis.strip():
            return
        try:
            suggestions = chart_gen.analyze_content(
                section_title=title,
                content=text_for_analysis,
                data_points=None,
            )
        except Exception:
            logger.warning(f"Chart analysis failed for slide: {title}")
            return
        if not suggestions and table_data and len(table_data) >= 2:
            try:
                chart_path = self._generate_chart_from_table(table_data, title, chart_gen)
                if chart_path and os.path.isfile(chart_path):
                    images = slide_data.get("images", [])
                    images.append({
                        "src": chart_path,
                        "alt": title,
                        "image_type": "chart",
                        "chart_type": "bar",
                        "chart_id": f"{title}:table",
                        "data_ref": "slide.table_data",
                    })
                    slide_data["images"] = images
                    logger.info(f"Auto-generated table chart for '{title}': {chart_path}")
            except Exception:
                logger.warning(f"Table chart generation failed for slide: {title}")
            return
        if not suggestions:
            return
        max_charts = 1
        if template_name == "chart_split":
            max_charts = 2
        images = slide_data.get("images", [])
        for suggestion in suggestions[:max_charts]:
            try:
                chart_path = chart_gen.generate_chart(suggestion)
                if chart_path and os.path.isfile(chart_path):
                    images.append({
                        "src": chart_path,
                        "alt": suggestion.title,
                        "image_type": "chart",
                        "chart_type": suggestion.chart_type.value,
                        "chart_id": f"{title}:{len(images)}",
                        "data_ref": "slide.content",
                        "caption": suggestion.caption,
                    })
                    logger.info(f"Auto-generated chart for '{title}': {chart_path}")
            except Exception:
                logger.warning(f"Chart generation failed for slide: {title}")
        if images:
            slide_data["images"] = images

    def _generate_chart_from_table(self, table_data, title, chart_gen) -> Optional[str]:
        """Generate a bar chart directly from table_data when SmartChartGenerator fails."""
        from src.services.chart_generator import ChartConfig, ChartType
        if len(table_data) < 2:
            return None
        headers = [str(h) for h in table_data[0]]
        categories = []
        values = []
        numeric_col_idx = None
        for col_idx in range(len(headers)):
            numeric_vals = []
            for row_idx in range(1, len(table_data)):
                cell = str(table_data[row_idx][col_idx]) if col_idx < len(table_data[row_idx]) else ""
                cleaned = re.sub(r'[^\d.\-]', '', cell)
                try:
                    numeric_vals.append(float(cleaned))
                except (ValueError, TypeError):
                    numeric_vals.append(None)
            non_none = [v for v in numeric_vals if v is not None]
            if len(non_none) >= len(table_data) * 0.5 and numeric_col_idx is None:
                numeric_col_idx = col_idx
        
        if numeric_col_idx is None:
            return None
        
        name_col = 0 if numeric_col_idx != 0 else (1 if len(headers) > 1 else None)
        if name_col is None:
            return None
        
        for row_idx in range(1, len(table_data)):
            name = str(table_data[row_idx][name_col]) if name_col < len(table_data[row_idx]) else ""
            cell = str(table_data[row_idx][numeric_col_idx]) if numeric_col_idx < len(table_data[row_idx]) else ""
            cleaned = re.sub(r'[^\d.\-]', '', cell)
            try:
                val = float(cleaned)
                categories.append(name[:12])
                values.append(val)
            except (ValueError, TypeError):
                continue
        
        if len(categories) < 2:
            return None
        
        config = ChartConfig(
            chart_type=ChartType.BAR,
            title=title,
            data={"categories": categories, "values": values},
            ylabel=headers[numeric_col_idx],
            source="",
            width=8,
            height=5,
        )
        result = chart_gen.chart_generator.generate(config)
        if result.success and result.image_path:
            dst = chart_gen.output_dir / Path(result.image_path).name
            if Path(result.image_path) != dst and Path(result.image_path).exists():
                import shutil
                shutil.move(str(result.image_path), str(dst))
                return str(dst)
            return result.image_path
        return None

    def _create_pptx_document(
        self,
        slides: List[Dict[str, Any]],
        output_path: str,
        styles: Dict[str, Any],
        design: Optional[Dict[str, Any]] = None
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
        from pptx.util import Inches
        
        if design is None:
            design = self._build_design(None)
        
        # Create presentation
        prs = Presentation()
        
        # Set slide dimensions
        prs.slide_width = Inches(styles.get("slide_width", 10))
        prs.slide_height = Inches(styles.get("slide_height", 7.5))
        
        slides_count = 0
        
        from .template_selector import TemplateRegistry, TemplateSelector
        from .slide_renderer import SlideRenderer
        from .layout_engine import LayoutEngine
        
        registry = TemplateRegistry()
        selector = TemplateSelector()
        layout_engine = LayoutEngine()
        
        try:
            from src.services.image_provider import ImageProvider
            image_provider = ImageProvider()
        except Exception:
            image_provider = None
        
        renderer = SlideRenderer(design, image_provider=image_provider)
        section_index = 0
        
        try:
            from src.services.smart_chart_generator import SmartChartGenerator
            chart_gen = SmartChartGenerator(output_dir=os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "output", "charts"
            ))
        except Exception:
            chart_gen = None
        
        for slide_data in slides:
            slide_layout = prs.slide_layouts[6]
            slide = prs.slides.add_slide(slide_layout)
            slides_count += 1
            
            slide_type = slide_data.get("slide_type", "content")
            if slide_type in ("section_title", "section-title"):
                section_index += 1
            
            if image_provider and not slide_data.get("images"):
                image_provider.enrich_images(slide_data)
            
            template_name = selector.select_and_enhance(slide_data, section_index=section_index)
            try:
                template = registry.get(template_name)
            except KeyError:
                template = registry.get("content_text_only")
            
            source = slide_data.get("source_text", "")
            if source:
                for dec in template.get("decorations", []):
                    if dec.get("type") == "source_text" and not dec.get("text"):
                        dec["text"] = source
            
            if chart_gen and layout_engine.can_accommodate_chart(slide_data, template_name):
                existing_images = slide_data.get("images", [])
                has_chart = any(
                    img.get("image_type") == "chart" or
                    (img.get("src", "").endswith((".png", ".jpg")) and "chart" in img.get("src", ""))
                    for img in existing_images
                )
                if not has_chart:
                    self._auto_generate_charts(slide_data, template_name, chart_gen)
            
            layout_overrides = None
            try:
                layout_overrides = layout_engine.compute(slide_data, template)
            except Exception:
                logger.debug("LayoutEngine compute failed, using template defaults")
            
            renderer.render(slide, slide_data, template, styles, page_num=slides_count, layout_overrides=layout_overrides)
        
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
