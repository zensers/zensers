# -*- coding: utf-8 -*-
"""
Content Orchestrator
====================

Converts research results to structured HTML format.

Core features:
1. Research result → HTML structure conversion
2. Section arrangement and sorting
3. Word/PPT format adaptation
4. HTML template rendering (style integration)

HTML intermediate format:
- Word: <article><section>...</section></article>
- PPT: <section class="slide" data-type="...">...</section>
- HTML templates: config/document_templates/*.html
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import base64
import html
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from .template_engine import TemplateEngine

logger = logging.getLogger(__name__)

# Constants
MAX_SLIDE_CONTENT = 500  # Max characters per PPT slide
MAX_RECURSION_DEPTH = 10  # Max section nesting depth

# Template mapping: format → default template name
DEFAULT_TEMPLATE_MAP = {
    "docx": "word_default",
    "pdf": "word_default",
    "html": "word_default",
    "pptx": "ppt_default",
    "research_report": "word_research_report",
}


class SectionType(Enum):
    """
    Section type enumeration
    
    **Phase 3 Addition**: Used to replace agent_id string matching in engine.py
    
    Use cases:
    - Distinguish body sections, executive summary, research conclusions, etc.
    - Separate sections by type in _build_report_task
    """
    BODY = "body"                    # Body section (analysis phase)
    EXECUTIVE_SUMMARY = "exec_summary"  # Executive summary
    CONCLUSION = "conclusion"         # Research conclusion
    APPENDIX = "appendix"             # Appendix
    DATA_SOURCE = "data_source"       # Data source
    UNKNOWN = "unknown"               # Unknown type


@dataclass
class ContentSection:
    """Content section
    
    **Phase 3 Enhancement**: Added type field for section type classification
    """
    id: str
    title: str
    content: str
    order: int = 0
    type: SectionType = SectionType.BODY  # New: section type
    subsections: Optional[List["ContentSection"]] = None
    charts: Optional[List[Dict[str, Any]]] = None
    points: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.subsections is None:
            self.subsections = []
        if self.charts is None:
            self.charts = []
        if self.points is None:
            self.points = []


class ContentOrchestrator:
    """
    Content Orchestrator
    
    Responsible for converting research results to structured HTML format.
    
    Supports HTML template rendering:
    - Template directory: config/document_templates/
    - PPT template: ppt_default.html
    - Word template: word_default.html
    
    Usage example:
        orchestrator = ContentOrchestrator()
        
        # Use default template
        html = orchestrator.transform_to_html(
            research_result={"title": "...", "sections": [...]},
            output_format="pptx"
        )
        
        # Use custom template
        html = orchestrator.transform_to_html(
            research_result={"title": "...", "sections": [...]},
            output_format="docx",
            template_name="company_report"
        )
    """
    
    supported_formats = ["docx", "pptx", "pdf", "html", "research_report"]
    
    def __init__(self):
        """Initialize content orchestrator"""
        self._max_slide_content = MAX_SLIDE_CONTENT
        self._template_engine = TemplateEngine()
        self._current_template_html: Optional[str] = None  # Current template HTML
    
    def get_template_html(self, template_name: Optional[str] = None) -> Optional[str]:
        """
        Get template HTML content
        
        Used to pass template HTML to Converter for CSS style extraction.
        
        Args:
            template_name: Template name (optional)
            
        Returns:
            Template HTML content, or None if not found
        """
        if template_name:
            return self._template_engine.load_template(template_name)
        return self._current_template_html
    
    def transform_to_html(
        self,
        research_result: Dict[str, Any],
        output_format: str,
        template_name: Optional[str] = None,
        output_dir: Optional[str] = None
    ) -> str:
        """
        Convert research result to HTML
        
        Args:
            research_result: Research result data
            output_format: Output format (docx/pptx/pdf/html)
            template_name: Template name (optional, uses format default)
            
        Returns:
            Structured HTML string
        """
        # Type validation
        if not isinstance(research_result, dict):
            logger.warning("research_result is not a dict, using empty dict")
            research_result = {}
        
        # Validate format
        if output_format not in self.supported_formats:
            logger.warning(f"Unsupported format: {output_format}, defaulting to docx")
            output_format = "docx"
        
        # Parse content
        title=research_result.get("title", "Research Report")
        sections = self._parse_sections(research_result.get("sections", []))
        key_findings = research_result.get("key_findings", [])
        data_points = research_result.get("data_points", [])
        
        logger.debug(f"Transforming to HTML: format={output_format}, sections={len(sections)}")
        
        # Select template
        if not template_name:
            template_name = DEFAULT_TEMPLATE_MAP.get(output_format, "word_default")
        
        # Prepare template variables
        variables = self._prepare_template_variables(
            title=title,
            sections=sections,
            key_findings=key_findings,
            data_points=data_points,
            research_result=research_result,
            output_format=output_format,
            output_dir=output_dir
        )
        
        # Try template rendering
        template = self._template_engine.load_template(template_name)
        if template:
            logger.info(f"Using template: {template_name}")
            # Save template HTML for later style extraction
            self._current_template_html = template
            return self._template_engine.render_template(template, variables)
        else:
            # Fallback: Use built-in HTML generation
            logger.warning(f"Template '{template_name}' not found, using fallback generation")
            self._current_template_html = None
            if output_format in ["pptx"]:
                return self._generate_ppt_html(title, sections, key_findings, data_points)
            else:
                return self._generate_word_html(title, sections, key_findings, data_points)
    
    def _prepare_template_variables(
        self,
        title: str,
        sections: List[ContentSection],
        key_findings: List[str],
        data_points: List[Dict[str, Any]],
        research_result: Dict[str, Any],
        output_format: str,
        output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Prepare template variables
        
        Args:
            title: Report title
            sections: Section list
            key_findings: Key findings
            data_points: Data points
            research_result: Original research result
            output_format: Output format
            output_dir: Output directory for external chart images
            
        Returns:
            Template variable dictionary
            """
        # P0-3 fix: Convert data points to table format (process first, assign to sections later)
        table_rows = []
        for dp in data_points:
            table_rows.append([
                dp.get("metric", ""),
                dp.get("value", ""),
                dp.get("unit", ""),
            ])
        
        # Convert sections to template format
        sections_data = []
        for i, section in enumerate(sections):
            # P0-3 fix: Get tables data for this section from research_result
            section_tables = []
            raw_sections = research_result.get("sections", [])
            if i < len(raw_sections):
                raw_section = raw_sections[i] if isinstance(raw_sections[i], dict) else {}
                # Prefer section's own tables
                if raw_section.get("tables"):
                    section_tables = raw_section["tables"]
                # If section has data_points, convert to tables format
                elif raw_section.get("data_points"):
                    rows = [
                        [dp.get("metric", ""), dp.get("value", ""), dp.get("unit", "")]
                        for dp in raw_section["data_points"]
                    ]
                    non_empty_rows = [r for r in rows if any(cell.strip() for cell in r)]
                    if non_empty_rows:
                        section_tables = [{
                            "caption": raw_section.get("title", "Data Table"),
                            "headers": ["Metric", "Value", "Unit"],
                            "rows": non_empty_rows,
                        }]
            
            section_dict = {
                "id": section.id,
                "title": section.title,  # Phase 1: title guaranteed clean by _parse_sections, no regex needed
                "content": self._content_to_html(section.content) if section.content else "",  # Phase 2: removed section_title parameter
                "page": i + 3,  # Assume cover and TOC occupy first 2 pages
                "index": i + 1,
                "subsections": [],  # Always include to avoid template rendering warnings
                "tables": section_tables,  # P0-3 fix: Fill section table data
            }
            
            # Process charts: read from raw_section, distribute top-level charts
            charts_data = []
            if i < len(raw_sections):
                raw_charts = raw_sections[i].get("charts", []) if isinstance(raw_sections[i], dict) else []
                if raw_charts:
                    charts_data = raw_charts
                else:
                    # Fallback: match top-level charts by section title
                    top_charts = research_result.get("charts", [])
                    if top_charts:
                        charts_data = [c for c in top_charts if c.get("section_title", "") == section_dict["title"]]
            if charts_data and output_format == "html":
                # HTML/Preview: convert to base64 or copy as external files
                resolved = []
                for c in charts_data:
                    path = c.get("path", "")
                    if path and ContentOrchestrator._chart_path_exists(path):
                        try:
                            resolved_path = path
                            if not os.path.exists(path) and not os.path.isabs(path):
                                resolved_path = str(Path(__file__).resolve().parent.parent.parent / path)
                            
                            if output_dir:
                                # External file mode: copy PNG to charts/ subdir, use relative path
                                charts_dir = Path(output_dir) / "charts"
                                charts_dir.mkdir(parents=True, exist_ok=True)
                                dst = charts_dir / os.path.basename(resolved_path)
                                dst_str = str(dst)
                                # Only copy if source and destination are different files
                                if os.path.abspath(resolved_path) != os.path.abspath(dst_str):
                                    import shutil
                                    shutil.copy2(resolved_path, dst_str)
                                resolved.append({"path": f"charts/{dst.name}", "caption": c.get("caption", "")})
                            else:
                                # Legacy base64 mode: embed image data in HTML
                                with open(resolved_path, "rb") as f:
                                    b64 = base64.b64encode(f.read()).decode()
                                ext = os.path.splitext(resolved_path)[1].lower()
                                mime = "image/png" if ext == ".png" else "image/jpeg"
                                resolved.append({"path": f"data:{mime};base64,{b64}", "caption": c.get("caption", "")})
                        except Exception:
                            logger.exception("Chart processing failed")
                            resolved.append(c)
                    else:
                        resolved.append(c)
                section_dict["charts"] = resolved
            else:
                section_dict["charts"] = charts_data  # DOCX/PPTX: pass through (template skips)
            
            # Process subsections
            if section.subsections:
                subsections_data = []
                for j, subsec in enumerate(section.subsections):
                    subsec_dict = {
                        "id": subsec.id,
                        "title": subsec.title,
                        "content": self._content_to_html(subsec.content) if subsec.content else "",
                        "index": f"{i+1}.{j+1}",
                        "points": subsec.points or [],
                    }
                    if subsec.points:
                        subsec_dict["point_sections"] = []
                        for k, pt in enumerate(subsec.points):
                            pt_content = ContentOrchestrator._extract_point_content(subsec.content, pt)
                            subsec_dict["point_sections"].append({
                                "title": pt,
                                "content": self._content_to_html(pt_content) if pt_content else "",
                                "index": f"{i+1}.{j+1}.{k+1}",
                            })
                    subsections_data.append(subsec_dict)
                section_dict["subsections"] = subsections_data
            
            sections_data.append(section_dict)
        
        # Convert key findings to template format
        findings_data = []
        for i, finding in enumerate(key_findings):
            findings_data.append({
                "title": f"Finding {i+1}",
                "content": finding,
            })
        
        # Calculate page count
        total_pages = 2 + len(sections_data) + 1  # Cover + TOC + sections + end page
        
        # Assemble variables
        variables = {
            "title": title,
            "subtitle": research_result.get("subtitle", ""),
            "author": research_result.get("author", ""),
            "date": research_result.get("date", datetime.now().strftime("%Y-%m-%d")),
            "logo_path": research_result.get("logo_path", ""),
            "watermark": research_result.get("watermark", ""),
            
            "sections": sections_data,
            "key_findings": findings_data,
            "conclusion": research_result.get("conclusion", ""),
            
            # Table data
            "tables": [{
                "caption": "Key Data",
                "headers": ["Metric", "Value", "Unit"],
                "rows": table_rows,
            }] if table_rows else [],
            
            # Page info
            "findings_page": total_pages,
            "end_page": total_pages + 1,
            
            # Format info
            "output_format": output_format,
            "is_html_format": output_format == "html",
        }
        
        # Keep other fields from original data (for special templates like questionnaire)
        for key, value in research_result.items():
            if key not in variables:
                variables[key] = value
        
        return variables
    
    @staticmethod
    def _chart_path_exists(path: str) -> bool:
        """检查图表文件是否存在，支持相对路径 fallback"""
        if os.path.exists(path):
            return True
        if not os.path.isabs(path):
            return (Path(__file__).resolve().parent.parent.parent / path).exists()
        return False

    @staticmethod
    def _parse_markdown_title(content: str) -> Dict[str, Any]:
        """
        Parse markdown content, separate opening title from body.
        
        **Phase 1 Core Fix**: Parse title at data entry point, avoid duplicate
        title appearing in both title and content fields.
        
        Purpose: section.title already exists as a structured field,
        no need to include title again in content.
        
        Args:
            content: Original markdown content (may contain title)
            
        Returns:
            {
                "title": Optional[str],  # Parsed title (if any)
                "body": str              # Body without title
            }
        """
        if not content:
            return {"title": None, "body": ""}
        
        lines = content.split('\n')
        extracted_title = None
        body_start = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Skip empty lines
            if not stripped:
                body_start = i + 1
                continue
            
            # Markdown heading: # Title / ## Title / ### Title
            md_match = re.match(r'^#{1,6}\s+(.+)$', stripped)
            if md_match:
                extracted_title = md_match.group(1).strip()
                body_start = i + 1
                logger.debug(f"[Title Parse] Markdown title: '{extracted_title}'")
                break
            
            # Mixed numbered heading: 1. I. Title / 1, I. Title (before numeric, priority match)
            mix_match = re.match(r'^\d+[\.、，．]\s*[（(]?[一二三四五六七八九十百千]+[）).、：，．]\s*(.*)$', stripped)
            if mix_match:
                raw_title = mix_match.group(1).strip()
                extracted_title = raw_title if raw_title else stripped
                body_start = i + 1
                logger.debug(f"[Title Parse] Mixed numbered title: '{extracted_title}'")
                break
            
            # Chinese numbered heading: I. Title / (I) Title / I. Title
            cn_match = re.match(r'^[（(]?[一二三四五六七八九十百千]+[）).、：，．]\s*(.*)$', stripped)
            if cn_match:
                raw_title = cn_match.group(1).strip()
                extracted_title = raw_title if raw_title else stripped
                body_start = i + 1
                logger.debug(f"[Title Parse] Chinese numbered title: '{extracted_title}'")
                break
            
            # Numeric numbered heading: 1. Title / 1、Title / 1. Title
            num_match = re.match(r'^\d+[\.、，．]\s*(.*)$', stripped)
            if num_match:
                raw_title = num_match.group(1).strip()
                extracted_title = raw_title if raw_title else stripped
                body_start = i + 1
                logger.debug(f"[Title Parse] Numeric numbered title: '{extracted_title}'")
                break
            
            # Encountered non-title content, stop
            break
        
        # Construct body: if no title parsed, return original content
        if extracted_title:
            body = "\n".join(lines[body_start:]).strip()
            return {"title": extracted_title, "body": body}
        else:
            return {"title": None, "body": content}
    
    def _parse_sections(
        self,
        sections_data: List[Dict[str, Any]],
        depth: int = 0
    ) -> List[ContentSection]:
        """
        Parse section data
        
        **Phase 1 Fix**: Use _parse_markdown_title to parse title,
        ensure content doesn't contain duplicate title.
        
        Args:
            sections_data: Section data list
            depth: Current recursion depth
            
        Returns:
            ContentSection list (sorted)
        """
        # Recursion depth protection
        if depth > MAX_RECURSION_DEPTH:
            logger.warning(f"Max recursion depth ({MAX_RECURSION_DEPTH}) exceeded, ignoring nested sections")
            return []
        
        sections = []
        
        for data in sections_data:
            if not isinstance(data, dict):
                logger.warning(f"Invalid section data type: {type(data)}, skipping")
                continue
            
            # **Phase 1 Fix**: Parse title in content, separate title and body
            raw_content = data.get("content", "")
            parsed = ContentOrchestrator._parse_markdown_title(raw_content)
            
            # Title priority: API provided title > title parsed from content
            api_title = data.get("title", "")
            final_title = api_title if api_title else parsed["title"] or ""
            final_content = parsed["body"] if parsed["title"] else raw_content
            
            # P2 fix: Skip sections with empty titles to avoid generating blank sections
            if not final_title or not final_title.strip():
                logger.debug(f"[Section Parse] Skipping section with empty title (id={data.get('id', 'unknown')})")
                continue
            
            # Log: record parsing result
            if parsed["title"] and api_title:
                logger.debug(f"[Section Parse] Using API title '{api_title}' over parsed '{parsed['title']}'")
            elif parsed["title"] and not api_title:
                logger.debug(f"[Section Parse] Using parsed title '{parsed['title']}'")
            
            # **Phase 3**: Read type field from data
            type_value = data.get("type")
            try:
                section_type = SectionType(type_value) if type_value else SectionType.BODY
            except (ValueError, TypeError):
                section_type = SectionType.BODY
            
            section = ContentSection(
                id=data.get("id", f"section_{len(sections)}"),
                title=final_title,
                content=final_content,  # Body without title
                order=data.get("order", len(sections)),
                type=section_type,  # Pass section type
                charts=data.get("charts", []),
                subsections=self._parse_sections(data.get("subsections", []), depth + 1),
                points=data.get("points", []),
            )
            sections.append(section)
        
        # Sort by order
        sections.sort(key=lambda s: s.order)
        
        return sections
    
    def _generate_word_html(
        self,
        title: str,
        sections: List[ContentSection],
        key_findings: List[str],
        data_points: List[Dict[str, Any]]
    ) -> str:
        """
        Generate Word format HTML
        
        Uses <article> as root element, <section> as section container.
        
        Args:
            title: Report title
            sections: Section list
            key_findings: Key findings
            data_points: Data points
            
        Returns:
            Word format HTML
        """
        # 去重：相同 title 合并（避免上游 sections 重复导致的输出重复）
        sections = ContentOrchestrator._dedup_sections(sections)
        html_parts = []
        
        # Document start
        html_parts.append('<article class="document" data-format="docx">')
        
        # ===== Cover page =====
        # **Fix**: Use div.cover-page wrapper to ensure HTMLToWordConverter recognizes cover
        html_parts.append('<div class="cover-page">')
        html_parts.append(f'<h1 class="document-title">{html.escape(title)}</h1>')
        html_parts.append('</div>')
        
        # ===== Table of Contents =====
        # **Fix**: Use div.toc wrapper to ensure HTMLToWordConverter recognizes and generates TOC page
        if sections:
            html_parts.append('<div class="toc">')
            html_parts.append('<h2>Table of Contents</h2>')
            for i, section in enumerate(sections, 1):
                html_parts.append(f'<p class="toc-item">{i}. {html.escape(section.title)}</p>')
                if section.subsections:
                    for j, subsec in enumerate(section.subsections, 1):
                        html_parts.append(f'<p class="toc-item" style="margin-left: 20px;">{i}.{j} {html.escape(subsec.title)}</p>')
                        if subsec.points:
                            for k, pt in enumerate(subsec.points, 1):
                                html_parts.append(f'<p class="toc-item" style="margin-left: 40px;">{i}.{j}.{k} {html.escape(pt)}</p>')
            html_parts.append('</div>')
        
        # Section content
        for section in sections:
            html_parts.append(self._render_section_html(section))
        
        # Key findings
        if key_findings:
            html_parts.append('<section class="key-findings" id="key-findings">')
            html_parts.append('<h2>Key Findings</h2>')
            html_parts.append('<ul class="findings-list">')
            for finding in key_findings:
                html_parts.append(f'<li>{html.escape(finding)}</li>')
            html_parts.append('</ul>')
            html_parts.append('</section>')
        
        # Data points
        if data_points:
            non_empty_dps = [dp for dp in data_points if any(str(dp.get(k, "")).strip() for k in ("metric", "value", "unit"))]
            if non_empty_dps:
                html_parts.append('<section class="data-points" id="data-points">')
                html_parts.append('<h2>Key Data</h2>')
                html_parts.append('<table class="data-table">')
                html_parts.append('<thead><tr><th>Metric</th><th>Value</th><th>Unit</th></tr></thead>')
                html_parts.append('<tbody>')
                for dp in non_empty_dps:
                    metric = dp.get("metric", "")
                    value = dp.get("value", "")
                    unit = dp.get("unit", "")
                    html_parts.append(f'<tr>')
                    html_parts.append(f'<td>{html.escape(metric)}</td>')
                    html_parts.append(f'<td>{html.escape(value)}</td>')
                    html_parts.append(f'<td>{html.escape(unit)}</td>')
                    html_parts.append('</tr>')
                html_parts.append('</tbody>')
                html_parts.append('</table>')
                html_parts.append('</section>')
        
        # Document end
        html_parts.append('</article>')
        
        return '\n'.join(html_parts)

    @staticmethod
    def _dedup_sections(sections: List[ContentSection]) -> List[ContentSection]:
        """相同 title 的章节按优先级保留最佳版本

        优先级规则（从高到低）：
        1. 内容非空的版本优先于空版本
        2. 不以结构化标记（**xxx**）开头的内容优先
        3. 内容更长的版本优先
        4. 类型为SYNTHESIS的优先于BODY
        """
        seen: Dict[str, ContentSection] = {}
        result: List[ContentSection] = []

        def _priority(s: ContentSection) -> tuple:
            """计算章节优先级得分（越高越优先）"""
            content = s.content or ""
            has_content = 1 if content.strip() else 0
            # 不以"**xxx**"或"##"开头的内容更可能是有实质分析的文本
            not_structural = 1 if not re.match(r'^\s*(\*\*|#)', content) else 0
            length = min(len(content) / 1000, 10)  # 内容长度得分，上限10
            is_synthesis = 1 if s.type == SectionType.CONCLUSION else 0
            return (has_content, not_structural, length, is_synthesis)

        for s in sections:
            if s.title in seen:
                existing = seen[s.title]
                if _priority(s) > _priority(existing):
                    seen[s.title] = s
                    # Replace in result list as well
                    for idx, rs in enumerate(result):
                        if rs.title == s.title:
                            result[idx] = s
                            break
            else:
                seen[s.title] = s
                result.append(s)

        if len(result) != len(sections):
            logger.info(f"ContentOrchestrator: sections 去重 {len(sections)} → {len(result)}")
        return result

    def _generate_ppt_html(
        self,
        title: str,
        sections: List[ContentSection],
        key_findings: List[str],
        data_points: List[Dict[str, Any]]
    ) -> str:
        """
        Generate PPT format HTML
        
        Uses <section class="slide"> as slide container.
        Each section may span multiple slides.
        
        Args:
            title: Report title
            sections: Section list
            key_findings: Key findings
            data_points: Data points
            
        Returns:
            PPT format HTML
        """
        html_parts = []
        slide_number = 1
        
        # Cover slide
        html_parts.append(self._render_cover_slide(title, slide_number))
        slide_number += 1
        
        # TOC slide (if many sections)
        if len(sections) > 3:
            html_parts.append(self._render_toc_slide(sections, slide_number))
            slide_number += 1
        
        # Section slides
        for section in sections:
            slide_htmls = self._render_section_slides(section, slide_number)
            html_parts.extend(slide_htmls)
            slide_number += len(slide_htmls)
        
        # Key findings slide
        if key_findings:
            html_parts.append(self._render_findings_slide(key_findings, slide_number))
            slide_number += 1
        
        # Data points slide
        if data_points:
            html_parts.append(self._render_data_slide(data_points, slide_number))
            slide_number += 1
        
        # End slide
        html_parts.append(self._render_end_slide(title, slide_number))
        
        return '\n'.join(html_parts)
    
    def _render_section_html(self, section: ContentSection) -> str:
        """Render section to Word HTML (with simple Markdown conversion)
        
        **Phase 1 Simplification**: content already doesn't contain section title, no need to pass section_title parameter
        """
        parts = []
        parts.append(f'<section id="{section.id}" class="document-section">')
        parts.append(f'<h2 class="section-title">{html.escape(section.title)}</h2>')
        if section.content:
            parts.append(self._content_to_html(section.content))
        if section.subsections:
            for subsec in section.subsections:
                parts.append(f'<section id="{subsec.id}" class="subsection">')
                parts.append(f'<h3 class="subsection-title">{html.escape(subsec.title)}</h3>')
                if subsec.points:
                    for pt in subsec.points:
                        parts.append(f'<h4 class="sub-subsection-title">{html.escape(pt)}</h4>')
                        pt_content = ContentOrchestrator._extract_point_content(subsec.content, pt)
                        if pt_content:
                            parts.append(self._content_to_html(pt_content))
                elif subsec.content:
                    parts.append(self._content_to_html(subsec.content))
                parts.append('</section>')
        parts.append('</section>')
        return '\n'.join(parts)
    
    @staticmethod
    def _extract_point_content(full_content: str, point_title: str) -> str:
        """Extract content belonging to a specific point from subsection content.
        
        Searches for the point heading in the content and returns the text
        between this heading and the next heading or end of content.
        """
        if not full_content or not point_title:
            return ""
        import re
        escaped = re.escape(point_title)
        pattern = rf'^#{{1,4}}\s+{escaped}\s*$'
        lines = full_content.split('\n')
        capturing = False
        captured = []
        for line in lines:
            if re.match(pattern, line.strip(), re.IGNORECASE):
                capturing = True
                continue
            if capturing:
                if re.match(r'^#{1,4}\s+', line.strip()):
                    break
                captured.append(line)
        return '\n'.join(captured).strip()

    @staticmethod
    def _content_to_html(content: str, section_title: Optional[str] = None) -> str:
        """Convert raw text content to HTML (handle Markdown markers)
        
        **Phase 2 Simplification**: Remove title skip logic
        - Titles already handled in _parse_sections, content doesn't contain section titles
        - section_title parameter retained for compatibility but not used
        
        Args:
            content: Raw text content (no section title)
            section_title: Section title (deprecated, retained for compatibility)
        """
        if not content:
            return ""
        
        lines = content.split('\n')
        
        # ===== Phase 2: Remove title skip logic =====
        # Titles already handled in _parse_sections via _parse_markdown_title
        # content doesn't contain section titles, just process directly
        
        result = []
        i = 0
        
        while i < len(lines):
            stripped = lines[i].strip()
            
            if not stripped:
                i += 1
                continue
            
            # Heading
            hm = re.match(r'^(#{1,3})\s+(.+)$', stripped)
            if hm:
                level = len(hm.group(1))
                # Remove Chinese number prefix: "## I. Competitive Landscape" → "Competitive Landscape"
                raw = hm.group(2)
                cleaned = re.sub(r'^[（(]?[一二三四五六七八九十百千]+[）).、：，．]\s*', '', raw)
                text = ContentOrchestrator._inline_markdown(cleaned)
                
                tag = f'h{min(level + 1, 4)}'
                result.append(f'<{tag} class="subsection-title">{text}</{tag}>')
                i += 1
                continue
            
            # Mixed numbering: "5. I. Competitive Landscape" / "1, I. Competitive Landscape" → h3 heading
            mix_hm = re.match(r'^\d+[\.、，．]\s*[（(]?[一二三四五六七八九十百千]+[）).、：，．]\s*(.*)$', stripped)
            if mix_hm:
                text = ContentOrchestrator._inline_markdown(mix_hm.group(1))
                result.append(f'<h3 class="subsection-title">{text}</h3>')
                i += 1
                continue
            
            # Chinese numbered heading (I, II, III... / 1, 2, 3...)
            cn_hm = re.match(r'^[（(]?[一二三四五六七八九十百千]+[）).、：，．]\s*(.*)$', stripped)
            if cn_hm:
                text = ContentOrchestrator._inline_markdown(cn_hm.group(1))
                result.append(f'<h3 class="subsection-title">{text}</h3>')
                i += 1
                continue
            
            # Standalone <img> tag → <figure>
            img_match = re.match(r'^\s*(<img\s[^>]*/?>)\s*$', stripped)
            if img_match:
                result.append(f'<figure class="chart-container">{img_match.group(1)}</figure>')
                i += 1
                continue
            
            # Markdown table detection
            md_table_match = re.match(r'^\|(.+)\|$', stripped)
            if md_table_match:
                table_lines = []
                while i < len(lines):
                    line = lines[i].strip()
                    if re.match(r'^\|(.+)\|$', line):
                        table_lines.append(line)
                        i += 1
                    else:
                        break
                html_table = ContentOrchestrator._md_table_to_html(table_lines)
                if html_table:
                    result.append(html_table)
                else:
                    for tl in table_lines:
                        result.append(f'<p class="section-content">{tl}</p>')
                continue
            
            # HTML table block detection: <table>...</table>
            html_table_start = re.match(r'^\s*<table[\s>]', stripped, re.IGNORECASE)
            if html_table_start:
                table_lines = []
                while i < len(lines):
                    line = lines[i]
                    table_lines.append(line)
                    if re.search(r'</table>', line, re.IGNORECASE):
                        i += 1
                        break
                    i += 1
                html_block = '\n'.join(table_lines)
                result.append(html_block)
                continue
            
            # HTML block-level tags: preserve as raw HTML (figure, div with class, ul/ol, etc.)
            html_block_match = re.match(r'^\s*<(figure|figcaption|ul|ol|li|div\s+class|blockquote|pre|code|hr|br)\b[^>]*>', stripped, re.IGNORECASE)
            if html_block_match:
                # Single-line or multi-line HTML block
                block_lines = []
                tag_name = html_block_match.group(1).lower()
                closing_pattern = f'</{tag_name}>'
                while i < len(lines):
                    line = lines[i]
                    block_lines.append(line)
                    if re.search(closing_pattern, line, re.IGNORECASE):
                        i += 1
                        break
                    i += 1
                html_block = '\n'.join(block_lines)
                result.append(html_block)
                continue
            
            # Normal paragraph
            result.append(f'<p class="section-content">{ContentOrchestrator._inline_markdown(stripped)}</p>')
            i += 1
        
        return '\n'.join(result)

    @staticmethod
    def _md_table_to_html(table_lines: List[str]) -> str:
        if len(table_lines) < 2:
            return ""
        
        has_separator = False
        rows = []
        alignments = []
        col_count = None
        
        for line in table_lines:
            cells = [c.strip() for c in line.split('|')[1:-1]]
            
            is_separator = all(
                re.match(r'^:?-+:?$', c) for c in cells
            )
            
            if is_separator:
                has_separator = True
                alignments = []
                for c in cells:
                    if c.startswith(':') and c.endswith(':'):
                        alignments.append('center')
                    elif c.endswith(':'):
                        alignments.append('right')
                    else:
                        alignments.append('left')
                continue
            
            rows.append(cells)
        
        if not rows:
            return ""
        
        if not has_separator:
            return ""
        
        col_count = len(rows[0])
        
        for idx in range(len(rows)):
            while len(rows[idx]) < col_count:
                rows[idx].append("")
            if len(rows[idx]) > col_count:
                rows[idx] = rows[idx][:col_count]
        
        if len(alignments) != col_count:
            alignments = ['left'] * col_count
        
        parts = ['<table class="data-table">']
        
        header = rows[0]
        parts.append('<thead><tr>')
        for j, cell in enumerate(header):
            align = f' style="text-align:{alignments[j]}"' if j < len(alignments) else ''
            parts.append(f'<th{align}>{ContentOrchestrator._inline_markdown(cell)}</th>')
        parts.append('</tr></thead>')
        
        if len(rows) > 1:
            parts.append('<tbody>')
            for row in rows[1:]:
                parts.append('<tr>')
                for j, cell in enumerate(row):
                    align = f' style="text-align:{alignments[j]}"' if j < len(alignments) else ''
                    parts.append(f'<td{align}>{ContentOrchestrator._inline_markdown(cell)}</td>')
                parts.append('</tr>')
            parts.append('</tbody>')
        
        parts.append('</table>')
        return '\n'.join(parts)

    @staticmethod
    def _inline_markdown(text: str) -> str:
        """Convert inline Markdown to HTML"""
        # Protect HTML tags from html.escape (img + table/figure/block tags)
        tag_placeholders = {}
        def protect_tag(m):
            idx = len(tag_placeholders)
            placeholder = f'__HTMLTAG_{idx}__'
            tag_placeholders[placeholder] = m.group(0)
            return placeholder
        
        text = re.sub(
            r'<(?:img\s[^>]*/?>|table\b[^>]*>|/table>|thead\b[^>]*>|/thead>|tbody\b[^>]*>|/tbody>|tr\b[^>]*>|/tr>|th\b[^>]*>|/th>|td\b[^>]*>|/td>|figure\b[^>]*>|/figure>|figcaption\b[^>]*>|/figcaption>|ul\b[^>]*>|/ul>|ol\b[^>]*>|/ol>|li\b[^>]*>|/li>|blockquote\b[^>]*>|/blockquote>|pre\b[^>]*>|/pre>|code\b[^>]*>|/code>|br\s*/?>|hr\s*/?>|strong\b[^>]*>|/strong>|em\b[^>]*>|/em>|sub\b[^>]*>|/sub>|sup\b[^>]*>|/sup>|span\b[^>]*>|/span>|div\b[^>]*>|/div>|caption\b[^>]*>|/caption>|colgroup\b[^>]*>|/colgroup>|col\b[^>]*/?>)',
            protect_tag, text, flags=re.IGNORECASE
        )
        text = html.escape(text)
        for placeholder, tag in tag_placeholders.items():
            text = text.replace(placeholder, tag)
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
        return text
    
    def _render_cover_slide(self, title: str, slide_num: int) -> str:
        """Render cover slide"""
        return f'''<section class="slide" data-type="cover" data-page="{slide_num}">
    <div class="slide-content">
        <div class="slide-title">
            <h1>{html.escape(title)}</h1>
        </div>
    </div>
</section>'''
    
    def _render_toc_slide(self, sections: List[ContentSection], slide_num: int) -> str:
        """Render TOC slide"""
        items = []
        for section in sections:
            items.append(f'<li class="toc-item">{html.escape(section.title)}</li>')
        
        return f'''<section class="slide" data-type="toc" data-page="{slide_num}">
    <div class="slide-content">
        <div class="slide-title">
            <h2>Table of Contents</h2>
        </div>
        <ul class="toc-list">
            {chr(10).join(items)}
        </ul>
    </div>
</section>'''
    
    def _render_section_slides(
        self,
        section: ContentSection,
        start_slide_num: int
    ) -> List[str]:
        """Render section slides (possibly multiple pages)"""
        slides = []
        
        # Title page
        slides.append(f'''<section class="slide" data-type="section-title" data-page="{start_slide_num}">
    <div class="slide-content">
        <div class="slide-title">
            <h2>{html.escape(section.title)}</h2>
        </div>
    </div>
</section>'''
        )
        
        # Content pages (may split into multiple pages based on content length)
        if section.content:
            content_chunks = self._split_content_for_slides(section.content)
            for i, chunk in enumerate(content_chunks):
                slide_num = start_slide_num + 1 + i
                slides.append(f'''<section class="slide" data-type="content" data-page="{slide_num}" data-section="{section.id}">
    <div class="slide-content">
        <div class="slide-body">
            <p>{html.escape(chunk)}</p>
        </div>
    </div>
</section>'''
                )
        
        return slides
    
    def _split_content_for_slides(self, content: str) -> List[str]:
        """
        Split content into slide-appropriate chunks
        
        Args:
            content: Original content
            
        Returns:
            Content chunk list
        """
        # Split by paragraphs
        paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
        
        # Combine into appropriate chunks
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) < self._max_slide_content:
                current_chunk += para + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n"
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [content]
    
    def _render_findings_slide(
        self,
        key_findings: List[str],
        slide_num: int
    ) -> str:
        """Render key findings slide"""
        items = []
        for finding in key_findings:
            items.append(f'<li class="finding-item">{html.escape(finding)}</li>')
        
        return f'''<section class="slide" data-type="findings" data-page="{slide_num}">
    <div class="slide-content">
        <div class="slide-title">
            <h2>Key Findings</h2>
        </div>
        <ul class="findings-list">
            {chr(10).join(items)}
        </ul>
    </div>
</section>'''
    
    def _render_data_slide(
        self,
        data_points: List[Dict[str, Any]],
        slide_num: int
    ) -> str:
        """Render data points slide"""
        rows = []
        for dp in data_points:
            metric = dp.get("metric", "")
            value = dp.get("value", "")
            unit = dp.get("unit", "")
            rows.append(f'<tr><td>{html.escape(metric)}</td><td class="data-value">{html.escape(value)}</td><td>{html.escape(unit)}</td></tr>')
        
        return f'''<section class="slide" data-type="data" data-page="{slide_num}">
    <div class="slide-content">
        <div class="slide-title">
            <h2>Key Data</h2>
        </div>
        <table class="data-table">
            <tbody>
                {chr(10).join(rows)}
            </tbody>
        </table>
    </div>
</section>'''
    
    def _render_end_slide(self, title: str, slide_num: int) -> str:
        """Render end slide"""
        return f'''<section class="slide" data-type="end" data-page="{slide_num}">
    <div class="slide-content">
        <div class="slide-title">
            <h2>Thank You</h2>
        </div>
        <div class="slide-footer">
            <p>{html.escape(title)}</p>
        </div>
    </div>
</section>'''


# Export
__all__ = ["ContentOrchestrator", "ContentSection"]
