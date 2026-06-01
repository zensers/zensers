# -*- coding: utf-8 -*-
"""
HTML to PDF Converter
=====================

Converts HTML intermediate format to PDF documents (.pdf).

Core features:
1. HTML parsing and conversion
2. Heading level handling
3. Paragraph and list handling
4. Table handling
5. Style application

Technical approach: reportlab (recommended) or weasyprint (optional)

Usage example:
    converter = HTMLToPDFConverter()
    result = converter.convert(
        html="<article><h1>Title</h1><p>Content</p></article>",
        output_path="output.pdf"
    )
"""

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_parser import HTMLElementParser

logger = logging.getLogger(__name__)

# 常量定义
MAX_HTML_SIZE = 50 * 1024 * 1024  # 50MB


@dataclass
class ConversionResult:
    """转换结果"""
    success: bool
    output_path: Optional[str] = None
    file_size: Optional[int] = None
    pages_estimate: Optional[int] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "output_path": self.output_path,
            "file_size": self.file_size,
            "pages_estimate": self.pages_estimate,
            "error": self.error,
            "error_code": self.error_code
        }


class HTMLToPDFConverter:
    """
    HTML转PDF转换器
    
    将HTML中间格式转换为PDF文档。
    
    使用示例：
        converter = HTMLToPDFConverter()
        result = converter.convert(
            html="<article><h1>标题</h1><p>内容</p></article>",
            output_path="output.pdf"
        )
        
        if result.success:
            print(f"文件已保存: {result.output_path}")
    """
    
    # 默认样式
    DEFAULT_STYLES = {
        "title_font": "Helvetica",
        "body_font": "Helvetica",
        "chinese_font": "SimHei",
        "title_size": 24,
        "h1_size": 20,
        "h2_size": 16,
        "h3_size": 14,
        "body_size": 11,
        "line_spacing": 1.5,
        "page_width": 595,  # A4 width in points
        "page_height": 842  # A4 height in points
    }
    
    def __init__(self, styles: Optional[Dict[str, Any]] = None):
        """
        初始化转换器
        
        Args:
            styles: 自定义样式配置
        """
        self.styles = {**self.DEFAULT_STYLES, **(styles or {})}
        self._reportlab_available = self._check_reportlab_available()
        
        if not self._reportlab_available:
            logger.warning("reportlab not available, converter will have limited functionality")
    
    def _check_reportlab_available(self) -> bool:
        """检查reportlab是否可用"""
        try:
            from reportlab.lib.pagesizes import A4  # noqa: F401
            return True
        except ImportError:
            return False
    
    def get_default_styles(self) -> Dict[str, Any]:
        """获取默认样式"""
        return self.DEFAULT_STYLES.copy()
    
    def convert(
        self,
        html: str,
        output_path: str,
        styles: Optional[Dict[str, Any]] = None
    ) -> ConversionResult:
        """
        转换HTML为PDF文档
        
        Args:
            html: HTML内容
            output_path: 输出文件路径
            styles: 自定义样式（可选）
            
        Returns:
            ConversionResult 转换结果
        """
        # 输入验证
        if not isinstance(html, str):
            logger.warning("html is not a string, converting to empty string")
            html = ""
        
        if not isinstance(output_path, str):
            return ConversionResult(
                success=False,
                error="output_path must be a string",
                error_code="INVALID_PATH_TYPE"
            )
        
        # 文件大小限制检查
        if len(html) > MAX_HTML_SIZE:
            return ConversionResult(
                success=False,
                error=f"HTML content too large ({len(html)/1024/1024:.1f}MB > {MAX_HTML_SIZE/1024/1024}MB)",
                error_code="CONTENT_TOO_LARGE"
            )
        
        # 路径安全检查
        if not self._is_safe_path(output_path):
            return ConversionResult(
                success=False,
                error="Invalid or unsafe output path",
                error_code="UNSAFE_PATH"
            )
        
        # 空HTML处理
        if not html.strip():
            logger.info("Empty HTML, creating minimal document")
            html = "<article><p></p></article>"
        
        # 合并样式
        final_styles = {**self.styles, **(styles or {})}
        
        try:
            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            # 使用基类解析器
            parser = HTMLElementParser()
            parser.feed(html)
            elements = parser.get_elements()
            
            # 创建PDF文档
            if self._reportlab_available:
                return self._create_reportlab_document(elements, output_path, final_styles)
            else:
                return self._create_fallback_document(elements, output_path, final_styles)
                
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
    
    def _is_safe_path(self, path: str) -> bool:
        """检查路径是否安全"""
        if '..' in path:
            return False
        try:
            Path(path).resolve()
            return True
        except (OSError, ValueError):
            return False
    
    def _create_reportlab_document(
        self,
        elements: List[Dict[str, Any]],
        output_path: str,
        styles: Dict[str, Any]
    ) -> ConversionResult:
        """
        使用reportlab创建PDF文档
        
        Args:
            elements: 解析后的元素列表
            output_path: 输出路径
            styles: 样式配置
            
        Returns:
            ConversionResult
        """
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        
        # 创建文档（先写入临时文件，再原子替换）
        fd, temp_path = tempfile.mkstemp(suffix='.pdf', dir=os.path.dirname(output_path) or '.')
        os.close(fd)
        
        try:
            doc = SimpleDocTemplate(
                temp_path,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72
            )
            
            # 创建样式
            style_sheet = getSampleStyleSheet()
            
            h1_style = ParagraphStyle(
                'CustomH1',
                parent=style_sheet['Heading1'],
                fontSize=styles.get('h1_size', 20),
                spaceAfter=12
            )
            
            h2_style = ParagraphStyle(
                'CustomH2',
                parent=style_sheet['Heading2'],
                fontSize=styles.get('h2_size', 16),
                spaceAfter=10
            )
            
            h3_style = ParagraphStyle(
                'CustomH3',
                parent=style_sheet['Heading3'],
                fontSize=styles.get('h3_size', 14),
                spaceAfter=8
            )
            
            body_style = ParagraphStyle(
                'CustomBody',
                parent=style_sheet['Normal'],
                fontSize=styles.get('body_size', 11),
                spaceAfter=6
            )
            
            # 构建文档内容
            story = []
            
            for element in elements:
                elem_type = element.get("type", "")
                
                if elem_type == "heading":
                    level = element.get("level", 1)
                    text = element.get("text", "")
                    
                    if text:
                        if level == 1:
                            story.append(Paragraph(text, h1_style))
                        elif level == 2:
                            story.append(Paragraph(text, h2_style))
                        elif level == 3:
                            story.append(Paragraph(text, h3_style))
                        else:
                            story.append(Paragraph(text, body_style))
                
                elif elem_type == "paragraph":
                    text = element.get("text", "")
                    if text:
                        story.append(Paragraph(text, body_style))
                
                elif elem_type == "list_item":
                    text = element.get("text", "")
                    list_type = element.get("list_type", "ul")
                    
                    if text:
                        prefix = "• " if list_type == 'ul' else "1. "
                        story.append(Paragraph(prefix + text, body_style))
                
                elif elem_type == "table":
                    data = element.get("data", [])
                    
                    if data:
                        t = Table(data)
                        t.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, 0), 12),
                            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                            ('GRID', (0, 0), (-1, -1), 1, colors.black)
                        ]))
                        story.append(t)
                        story.append(Spacer(1, 12))
            
            # 构建PDF
            doc.build(story)
            
            # 原子替换
            os.replace(temp_path, output_path)
            
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
        
        # 获取文件大小
        file_size = os.path.getsize(output_path)
        
        # 估算页数
        pages_estimate = max(1, len(story) // 20)
        
        logger.info(f"PDF created: {output_path}, size={file_size}, pages~={pages_estimate}")
        
        return ConversionResult(
            success=True,
            output_path=output_path,
            file_size=file_size,
            pages_estimate=pages_estimate
        )
    
    def _create_fallback_document(
        self,
        elements: List[Dict[str, Any]],
        output_path: str,
        styles: Dict[str, Any]
    ) -> ConversionResult:
        """
        创建备用格式文档（当reportlab不可用时）
        """
        # 创建纯文本版本
        text_lines = []
        
        for element in elements:
            elem_type = element.get("type", "")
            
            if elem_type == "heading":
                level = element.get("level", 1)
                text = element.get("text", "")
                prefix = "#" * level
                text_lines.append(f"\n{prefix} {text}\n")
            
            elif elem_type == "paragraph":
                text = element.get("text", "")
                text_lines.append(text)
            
            elif elem_type == "list_item":
                text = element.get("text", "")
                list_type = element.get("list_type", "ul")
                if list_type == 'ol':
                    text_lines.append(f"1. {text}")
                else:
                    text_lines.append(f"- {text}")
            
            elif elem_type == "table":
                data = element.get("data", [])
                for row in data:
                    text_lines.append(" | ".join(row))
        
        content = "\n".join(text_lines)
        
        # 改为.txt扩展名
        txt_path = output_path.rsplit('.', 1)[0] + '.txt'
        
        # 原子写入
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
        
        logger.warning(f"reportlab not available, created text file: {txt_path}")
        
        return ConversionResult(
            success=True,
            output_path=txt_path,
            file_size=file_size,
            pages_estimate=len(text_lines) // 30,
            error="reportlab not available, created text file instead"
        )


# 导出
__all__ = ["HTMLToPDFConverter", "ConversionResult"]