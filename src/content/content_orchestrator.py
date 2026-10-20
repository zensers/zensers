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
from .format_strategy import get_format_strategy

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
        self._current_template_html: Optional[str] = None
        self._last_render_diagnostics: List[Dict[str, Any]] = []
        self._last_render_validation: Dict[str, Any] = {"passed": True, "issues": []}
        from .content_condenser import ContentCondenser
        # PPT 编辑契约的单一来源是 PPTXStrategy（format_strategy.py）。
        # condenser 只在 _render_section_slides（pptx 分支）中使用。
        directive = get_format_strategy("pptx").get_writing_directive()
        self._condenser = ContentCondenser(
            max_bullet_chars=directive.bullet_max_chars or 25
        )
    
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

    def get_render_diagnostics(self) -> Dict[str, Any]:
        """Expose render diagnostics without changing the core task state model."""
        return {
            "status": "warning" if self._last_render_diagnostics else "ok",
            "issues": [dict(issue) for issue in self._last_render_diagnostics],
            "post_render_validation": dict(self._last_render_validation),
        }
    
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
        self._last_render_diagnostics = []
        self._last_render_validation = {"passed": True, "issues": []}
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

        # PPT needs an explicit page plan.  The generic document template is
        # intentionally bypassed here because it represents one section as
        # one page, which is a Word/report layout assumption.  Keep the
        # template available for CSS extraction and browser preview.
        if output_format == "pptx":
            self._current_template_html = self._template_engine.load_template(
                template_name or DEFAULT_TEMPLATE_MAP["pptx"]
            )
            return self._generate_ppt_html(
                title,
                sections,
                key_findings,
                data_points,
            )
        
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
            rendered = self._template_engine.render_template(template, variables)
            self._last_render_validation = self._template_engine.get_last_render_validation()
            return rendered
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
            # Skip if content already contains a table (avoid double rendering)
            section_tables = []
            raw_sections = research_result.get("sections", [])
            if i < len(raw_sections):
                raw_section = raw_sections[i] if isinstance(raw_sections[i], dict) else {}
                # Check if the converted content already has a <table>
                content_html_preview = self._content_to_html(section.content, diagnostics=self._last_render_diagnostics) if section.content else ""
                content_has_table = "<table" in content_html_preview
                if not content_has_table:
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
                "title": section.title,
                "page": i + 3,
                "index": i + 1,
                "subsections": [],
                "tables": section_tables,
            }
            
            if output_format == "pptx" and section.content:
                table_data_for_condenser = None
                if section_tables and len(section_tables) > 0:
                    first_table = section_tables[0]
                    if isinstance(first_table, dict):
                        rows = first_table.get("rows", [])
                        headers = first_table.get("headers", [])
                        if headers:
                            table_data_for_condenser = [headers] + rows
                        elif rows:
                            table_data_for_condenser = rows
                    elif isinstance(first_table, list):
                        table_data_for_condenser = first_table

                condensed = self._condenser.condense(
                    section.content,
                    title=section.title,
                    table_data=table_data_for_condenser,
                )
                # Use the full set here; pagination is the renderer's job.  The
                # capped ``items`` field is retained for single-slide consumers.
                items = condensed.get("all_items", condensed.get("items", []))
                kpi_data = condensed.get("kpi_data", [])
                chart_suggestions = condensed.get("chart_suggestions", [])
                
                bullet_html_parts = []
                if items:
                    li_items = [f'<li>{ContentOrchestrator._inline_markdown(item)}</li>' for item in items]
                    bullet_html_parts.append(f'<ul>{chr(10).join(li_items)}</ul>')
                else:
                    bullet_html_parts.append(self._content_to_html(section.content, diagnostics=self._last_render_diagnostics))
                
                section_dict["content"] = chr(10).join(bullet_html_parts)
                section_dict["items"] = items
                section_dict["kpi_data"] = kpi_data
                section_dict["chart_suggestions"] = chart_suggestions
            else:
                section_dict["content"] = self._content_to_html(section.content, diagnostics=self._last_render_diagnostics) if section.content else ""
            
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
            if charts_data and output_format in ("html", "pptx", "pdf", "docx"):
                resolved = []
                for c in charts_data:
                    path = c.get("path", "")
                    if path and ContentOrchestrator._chart_path_exists(path):
                        try:
                            resolved_path = path
                            if not os.path.exists(path) and not os.path.isabs(path):
                                resolved_path = str(Path(__file__).resolve().parent.parent.parent / path)
                            
                            if output_format == "pptx":
                                resolved.append({
                                    "path": resolved_path,
                                    "caption": c.get("caption", ""),
                                    "insertion_anchor": c.get("insertion_anchor", ""),
                                    "anchor_type": c.get("anchor_type", "section_end"),
                                    "title": c.get("title", ""),
                                    "chart_type": c.get("chart_type", "bar"),
                                    "chart_id": c.get("chart_id", ""),
                                })
                            elif output_format in ("pdf", "docx"):
                                resolved.append({
                                    "path": resolved_path,
                                    "caption": c.get("caption", ""),
                                    "insertion_anchor": c.get("insertion_anchor", ""),
                                    "anchor_type": c.get("anchor_type", "section_end"),
                                    "title": c.get("title", ""),
                                    "chart_type": c.get("chart_type", "bar"),
                                    "chart_id": c.get("chart_id", ""),
                                })
                            elif output_dir:
                                charts_dir = Path(output_dir) / "charts"
                                charts_dir.mkdir(parents=True, exist_ok=True)
                                dst = charts_dir / os.path.basename(resolved_path)
                                dst_str = str(dst)
                                if os.path.abspath(resolved_path) != os.path.abspath(dst_str):
                                    import shutil
                                    shutil.copy2(resolved_path, dst_str)
                                resolved.append({
                                    "path": f"charts/{dst.name}",
                                    "caption": c.get("caption", ""),
                                    "insertion_anchor": c.get("insertion_anchor", ""),
                                    "anchor_type": c.get("anchor_type", "section_end"),
                                    "title": c.get("title", ""),
                                    "chart_type": c.get("chart_type", "bar"),
                                    "chart_id": c.get("chart_id", ""),
                                })
                            else:
                                with open(resolved_path, "rb") as f:
                                    b64 = base64.b64encode(f.read()).decode()
                                ext = os.path.splitext(resolved_path)[1].lower()
                                mime = "image/png" if ext == ".png" else "image/jpeg"
                                resolved.append({
                                    "path": f"data:{mime};base64,{b64}",
                                    "caption": c.get("caption", ""),
                                    "insertion_anchor": c.get("insertion_anchor", ""),
                                    "anchor_type": c.get("anchor_type", "section_end"),
                                    "title": c.get("title", ""),
                                    "chart_type": c.get("chart_type", "bar"),
                                    "chart_id": c.get("chart_id", ""),
                                })
                        except Exception:
                            logger.exception("Chart processing failed")
                            resolved.append(c)
                    else:
                        resolved.append(c)
                
                if output_format == "html":
                    section_dict["content"] = self._insert_charts_into_html(
                        section_dict["content"],
                        resolved,
                        section.content or "",
                    )
                    section_dict["charts"] = []
                else:
                    section_dict["charts"] = resolved
            
            # Process subsections
            if section.subsections:
                subsections_data = []
                for j, subsec in enumerate(section.subsections):
                    subsec_dict = {
                        "id": subsec.id,
                        "title": subsec.title,
                        "content": self._content_to_html(subsec.content, diagnostics=self._last_render_diagnostics) if subsec.content else "",
                        "index": f"{i+1}.{j+1}",
                        "points": subsec.points or [],
                    }
                    if subsec.points:
                        subsec_dict["point_sections"] = []
                        for k, pt in enumerate(subsec.points):
                            pt_content = ContentOrchestrator._extract_point_content(subsec.content, pt)
                            subsec_dict["point_sections"].append({
                                "title": pt,
                                "content": self._content_to_html(pt_content, diagnostics=self._last_render_diagnostics) if pt_content else "",
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
            "labels": {"toc": "目 录", "findings": "关键发现", "data": "核心数据"},
            
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
    def _resolve_ppt_chart_path(path: str) -> str:
        """Resolve chart paths for the direct multi-slide PPT path."""
        if not path:
            return ""
        if os.path.exists(path):
            return path
        if not os.path.isabs(path):
            candidate = Path(__file__).resolve().parent.parent.parent / path
            if candidate.exists():
                return str(candidate)
        return path

    def _insert_charts_into_html(
        self,
        html: str,
        charts: List[Dict[str, Any]],
        original_content: str,
    ) -> str:
        """
        在 HTML 中插入图表（锚点定位）

        Args:
            html: 已转换的 HTML 内容
            charts: 图表信息列表（含 insertion_anchor, anchor_type, path, caption）
            original_content: 原始 Markdown 内容（用于锚点定位）
        """
        if not charts:
            return html

        md_lines = original_content.split("\n")
        html_lines = html.split("\n")

        # Step 1: Build mapping from MD line number -> HTML line range
        # Strategy: parse top-level HTML blocks and map them sequentially
        # to non-empty MD lines (table blocks span multiple MD lines)
        md_nonempty_indices = []
        for md_line_no, md_line in enumerate(md_lines):
            if md_line.strip():
                md_nonempty_indices.append(md_line_no)

        # Parse top-level HTML blocks: each starts with a top-level tag
        html_blocks = []
        i = 0
        while i < len(html_lines):
            line = html_lines[i].strip()
            if not line:
                i += 1
                continue

            start = i
            # Detect multi-line blocks by opening tag
            if "<table" in line:
                while i < len(html_lines) and "</table>" not in html_lines[i]:
                    i += 1
                i += 1  # include the </table> line
            elif "<figure" in line:
                while i < len(html_lines) and "</figure>" not in html_lines[i]:
                    i += 1
                i += 1
            elif line.startswith("<"):
                i += 1  # single-line HTML element
            else:
                i += 1  # fallback

            html_blocks.append((start, i - 1))

        # Map MD non-empty lines to HTML blocks sequentially
        # A table in MD spans multiple non-empty lines but maps to one HTML block
        md_to_html_range: Dict[int, Tuple[int, int]] = {}
        md_idx = 0
        blk_idx = 0

        while md_idx < len(md_nonempty_indices) and blk_idx < len(html_blocks):
            md_line_no = md_nonempty_indices[md_idx]
            md_line = md_lines[md_line_no].strip()
            blk_start, blk_end = html_blocks[blk_idx]

            # Check if this MD line starts a table block
            is_table_start = bool(re.match(r"^\|(.+)\|$", md_line))
            if is_table_start:
                # Collect all consecutive pipe lines
                table_md_lines = [md_line_no]
                j = md_idx + 1
                while j < len(md_nonempty_indices):
                    next_line = md_lines[md_nonempty_indices[j]].strip()
                    if re.match(r"^\|(.+)\|$", next_line):
                        table_md_lines.append(md_nonempty_indices[j])
                        j += 1
                    else:
                        break
                # All these MD lines map to this single HTML block
                for tmd in table_md_lines:
                    md_to_html_range[tmd] = (blk_start, blk_end)
                md_idx = j
                blk_idx += 1
            else:
                # Single MD line -> single HTML block
                md_to_html_range[md_line_no] = (blk_start, blk_end)
                md_idx += 1
                blk_idx += 1

        # Step 2: Find anchor positions in MD
        anchor_line_map: Dict[int, Optional[int]] = {}

        for idx, chart in enumerate(charts):
            anchor = chart.get("insertion_anchor", "")
            anchor_type = chart.get("anchor_type", "section_end")

            if anchor_type == "section_start":
                anchor_line_map[idx] = 0
                continue

            if anchor_type == "section_end" or not anchor:
                anchor_line_map[idx] = None
                continue

            best_line = None
            if anchor_type == "after_table":
                anchor_md_line = None
                for line_no, line in enumerate(md_lines):
                    if anchor in line:
                        anchor_md_line = line_no
                        break
                if anchor_md_line is None:
                    core_words = self._extract_core_words(anchor)
                    for word in core_words[:3]:
                        for line_no, line in enumerate(md_lines):
                            if word in line:
                                anchor_md_line = line_no
                                break
                        if anchor_md_line is not None:
                            break
                if anchor_md_line is not None:
                    for line_no in range(anchor_md_line, len(md_lines)):
                        if re.match(r"^\|(.+)\|$", md_lines[line_no].strip()):
                            best_line = line_no
                            break
            else:
                for line_no, line in enumerate(md_lines):
                    if anchor in line:
                        best_line = line_no
                        break

                if best_line is None:
                    core_words = self._extract_core_words(anchor)
                    for word in core_words[:3]:
                        for line_no, line in enumerate(md_lines):
                            if word in line:
                                best_line = line_no
                                break
                        if best_line is not None:
                            break

            anchor_line_map[idx] = best_line

        # Step 3: Determine insert positions
        insertions: List[Tuple[int, str]] = []

        for idx, chart in enumerate(charts):
            chart_html = self._render_chart_figure(chart)
            md_line = anchor_line_map.get(idx)
            chart_anchor_type = chart.get("anchor_type", "section_end")

            if md_line is None:
                insertions.append((len(html_lines), chart_html))
            elif md_line == 0 and chart_anchor_type == "section_start":
                insertions.append((0, chart_html))
            else:
                html_range = md_to_html_range.get(md_line)
                if html_range is not None:
                    insert_after = html_range[1] + 1
                    insertions.append((insert_after, chart_html))
                else:
                    insertions.append((len(html_lines), chart_html))

        # Insert from back to front to avoid index shifting
        # Use enumerated index to break ties (preserve original chart order at same position)
        indexed_insertions = list(enumerate(insertions))
        for enum_idx, (pos, chart_html) in sorted(
            indexed_insertions, key=lambda x: (x[1][0], x[0]), reverse=True
        ):
            if 0 <= pos <= len(html_lines):
                html_lines.insert(pos, chart_html)

        return "\n".join(html_lines)

    def _extract_core_words(self, anchor: str) -> List[str]:
        chinese_words = re.findall(r"[\u4e00-\u9fff]{2,4}", anchor)
        if chinese_words:
            return chinese_words
        english_words = re.findall(r"[a-zA-Z]{3,}", anchor)
        return english_words

    def _render_chart_figure(self, chart: Dict[str, Any]) -> str:
        """渲染单个图表为HTML figure元素"""
        path = chart.get("path", "")
        caption = chart.get("caption", "")
        title = chart.get("title", "")
        alt_text = html.escape(caption or title or "Chart")
        safe_path = html.escape(path, quote=True)
        return (
            f'<figure class="chart-container">'
            f'<img src="{safe_path}" alt="{alt_text}" style="max-width:100%">'
            f'<figcaption class="figure-caption">{html.escape(caption)}</figcaption>'
            f'</figure>'
        )

    @staticmethod
    def _ppt_chart_img(chart_path: str, chart_alt: str, chart: Dict[str, Any]) -> str:
        chart_type = html.escape(str(chart.get("chart_type", "") or ""), quote=True)
        return (
            f'<img src="{html.escape(chart_path, quote=True)}" alt="{chart_alt}" '
            f'data-image-type="chart" data-chart-type="{chart_type}">'
        )

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
                # Lines like "1. **bold text**" are ordered list items, not titles
                if raw_title.startswith('**') or raw_title.startswith('*'):
                    break
                extracted_title = raw_title if raw_title else stripped
                body_start = i + 1
                logger.debug(f"[Title Parse] Numeric numbered title: '{extracted_title}'")
                break
            
            # Encountered non-title content, stop
            break
        
        # Construct body: if no title parsed, return original content
        if extracted_title:
            extracted_title = re.sub(r'^\*{1,2}(.+?)\*{1,2}$', r'\1', extracted_title)
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
            
            # Content cleaner: fix blacklist titles and extract JSON content
            try:
                from src.content.content_cleaner import clean_section
                data = clean_section(data)
                raw_content = data.get("content", raw_content)
            except ImportError:
                pass
            
            # Skip sections where refinement was refused (empty draft, no data)
            if data.get("_refusal"):
                logger.info(f"[Section Parse] Skipping refusal/empty-draft section: '{data.get('title', '')}' (id={data.get('id', 'unknown')})")
                continue
            
            parsed = ContentOrchestrator._parse_markdown_title(raw_content)
            
            # Title priority: API provided title > title parsed from content > section_id fallback
            api_title = data.get("title", "")
            section_id = data.get("section_id", "")
            final_title = api_title if api_title else parsed["title"] or ""
            final_content = parsed["body"] if parsed["title"] else raw_content
            
            # If still no title, try to extract from content or use section_id
            if not final_title or not final_title.strip():
                # Try to extract title from content (e.g., **核心结论：** or 第一章 市场概况)
                # Look for bold text at the start
                bold_match = re.match(r'^\*\*(.+?)[:：]\*\*', raw_content)
                if bold_match:
                    final_title = bold_match.group(1).strip()
                # Look for numbered heading
                elif re.match(r'^第[一二三四五六七八九十]+章', raw_content):
                    title_match = re.match(r'^(第[一二三四五六七八九十]+章\s*.+?)(?:\n|$)', raw_content)
                    if title_match:
                        final_title = title_match.group(1).strip()
                # Use section_id as last resort
                elif section_id:
                    final_title = section_id.replace("_", " ")
                else:
                    final_title = f"Section {len(sections) + 1}"
            
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

    _STOP_CHARS = frozenset("的与和及及其在中从对等了着过被把让向往以")

    @staticmethod
    def _char_jaccard(a: str, b: str) -> float:
        """标题相似度：提取核心词后计算字符级Jaccard

        去掉停用字后，"行业现存问题与风险" → "行业现存问题风险"
        "行业问题与痛点" → "行业问题痛点"，Jaccard更高
        """
        if not a or not b:
            return 0.0
        stop = ContentOrchestrator._STOP_CHARS
        sa = set(c for c in a if c not in stop)
        sb = set(c for c in b if c not in stop)
        if not sa or not sb:
            return 0.0
        inter = len(sa & sb)
        union = len(sa | sb)
        return inter / union if union else 0.0

    @staticmethod
    def _dedup_sections(sections: List[ContentSection], threshold: float = 0.35) -> List[ContentSection]:
        """相同或语义相近 title 的章节按优先级保留最佳版本

        去重策略：
        1. 精确标题匹配 → 直接去重
        2. 字符级Jaccard相似度 > threshold → 语义去重

        优先级规则（从高到低）：
        1. 内容非空的版本优先于空版本
        2. 不以结构化标记（**xxx**）开头的内容优先
        3. 内容更长的版本优先
        4. 类型为SYNTHESIS的优先于BODY
        """
        seen: Dict[str, ContentSection] = {}
        result: List[ContentSection] = []

        def _priority(s: ContentSection) -> tuple:
            content = s.content or ""
            has_content = 1 if content.strip() else 0
            not_structural = 1 if not re.match(r'^\s*(\*\*|#)', content) else 0
            length = min(len(content) / 1000, 10)
            is_synthesis = 1 if s.type == SectionType.CONCLUSION else 0
            return (has_content, not_structural, length, is_synthesis)

        def _find_similar(title: str) -> Optional[str]:
            for existing_title in seen:
                if ContentOrchestrator._char_jaccard(title, existing_title) > threshold:
                    return existing_title
            return None

        for s in sections:
            matched_key = None
            if s.title in seen:
                matched_key = s.title
            else:
                matched_key = _find_similar(s.title)

            if matched_key is not None:
                existing = seen[matched_key]
                if _priority(s) > _priority(existing):
                    seen[s.title] = s
                    if matched_key != s.title:
                        del seen[matched_key]
                    for idx, rs in enumerate(result):
                        if rs.title == matched_key:
                            result[idx] = s
                            break
                    else:
                        result.append(s)
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
        # Keep the rendering seam usable for lightweight instances created by
        # callers/tests without running the full orchestrator constructor.
        diagnostics = getattr(self, "_last_render_diagnostics", [])
        parts.append(f'<section id="{section.id}" class="document-section">')
        parts.append(f'<h2 class="section-title">{html.escape(section.title)}</h2>')
        if section.content:
            parts.append(self._content_to_html(section.content, diagnostics=diagnostics))
        if section.subsections:
            for subsec in section.subsections:
                parts.append(f'<section id="{subsec.id}" class="subsection">')
                parts.append(f'<h3 class="subsection-title">{html.escape(subsec.title)}</h3>')
                if subsec.points:
                    for pt in subsec.points:
                        parts.append(f'<h4 class="sub-subsection-title">{html.escape(pt)}</h4>')
                        pt_content = ContentOrchestrator._extract_point_content(subsec.content, pt)
                        if pt_content:
                            parts.append(self._content_to_html(pt_content, diagnostics=diagnostics))
                elif subsec.content:
                    parts.append(self._content_to_html(subsec.content, diagnostics=diagnostics))
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
    def _content_to_html(
        content: str,
        section_title: Optional[str] = None,
        diagnostics: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
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
            
            # Fenced code block: ``` ... ```
            if stripped.startswith('```'):
                lang = stripped[3:].strip()
                code_lines = []
                i += 1
                while i < len(lines):
                    if lines[i].strip().startswith('```'):
                        i += 1
                        break
                    code_lines.append(lines[i])
                    i += 1
                if lang == 'json':
                    try:
                        import json as _json
                        data = _json.loads('\n'.join(code_lines))
                        if isinstance(data, dict) and 'content' in data:
                            result.append(ContentOrchestrator._content_to_html(data['content']))
                            continue
                    except Exception:
                        pass
                result.append(f'<pre class="code-block"><code>{html.escape(chr(10).join(code_lines))}</code></pre>')
                continue
            
            # Unordered list: - item / * item
            if stripped.startswith('- ') or stripped.startswith('* '):
                list_items = []
                while i < len(lines):
                    line = lines[i].strip()
                    if line.startswith('- ') or line.startswith('* '):
                        item_text = line[2:].strip()
                        list_items.append(f'<li>{ContentOrchestrator._inline_markdown(item_text)}</li>')
                        i += 1
                    else:
                        break
                result.append(f'<ul>{chr(10).join(list_items)}</ul>')
                continue
            
            # Blockquote: > text
            if stripped.startswith('> '):
                quote_lines = []
                while i < len(lines):
                    line = lines[i].strip()
                    if line.startswith('> '):
                        quote_lines.append(line[2:])
                        i += 1
                    else:
                        break
                quote_text = ContentOrchestrator._inline_markdown(' '.join(quote_lines))
                result.append(f'<blockquote class="quote-block">{quote_text}</blockquote>')
                continue
            
            # Heading: # / ## / ### / #### / ##### / ######
            hm = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if hm:
                level = len(hm.group(1))
                raw = hm.group(2)
                cleaned = re.sub(r'^[（(]?[一二三四五六七八九十百千]+[）).、：，．]\s*', '', raw)
                text = ContentOrchestrator._inline_markdown(cleaned)
                
                tag = f'h{min(level + 1, 6)}'
                class_map = {
                    2: 'section-title',
                    3: 'subsection-title',
                    4: 'sub-subsection-title',
                }
                css_class = class_map.get(min(level + 1, 4), '')
                class_attr = f' class="{css_class}"' if css_class else ''
                result.append(f'<{tag}{class_attr}>{text}</{tag}>')
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
            
            # Ordered list: 1. item / 1、item (but NOT mixed/chinese headings above)
            ol_match = re.match(r'^(\d+)[\.、]\s+(.+)$', stripped)
            if ol_match:
                list_items = []
                while i < len(lines):
                    line = lines[i].strip()
                    ol_m = re.match(r'^(\d+)[\.、]\s+(.+)$', line)
                    if ol_m and not re.match(r'^\d+[\.、，．]\s*[（(]?[一二三四五六七八九十百千]+', line):
                        list_items.append(f'<li>{ContentOrchestrator._inline_markdown(ol_m.group(2))}</li>')
                        i += 1
                    else:
                        break
                if list_items:
                    result.append(f'<ol>{chr(10).join(list_items)}</ol>')
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
                    issue = {
                        "code": "MARKDOWN_TABLE_RENDER_FAILED",
                        "severity": "warning",
                        "message": "Markdown table could not be rendered; source was not downgraded to paragraphs.",
                        "lines": list(table_lines),
                    }
                    if diagnostics is not None:
                        diagnostics.append(issue)
                    logger.warning("Markdown table render failed (%d lines)", len(table_lines))
                    result.append(
                        '<div class="render-diagnostic render-diagnostic-warning" '
                        'data-diagnostic-code="MARKDOWN_TABLE_RENDER_FAILED">'
                        '<strong>表格渲染诊断：</strong>Markdown 表格无法转换，请检查表头、分隔行和列数。'
                        '</div>'
                    )
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
            result.append(f'<p class="para">{ContentOrchestrator._inline_markdown(stripped)}</p>')
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
        if not col_count or any(len(row) != col_count for row in rows):
            # 宽容规整（B 端评估实证）：LLM 产出的表格常有长短行，过去
            # 直接放弃渲染导致整段原始 markdown（含未转链接）泄漏进正文。
            # 现按首行列数补齐/截断，保证表格始终以 <table> 呈现。
            col_count = len(rows[0])
            norm = []
            for row in rows:
                row = list(row)
                if len(row) < col_count:
                    row += [""] * (col_count - len(row))
                elif len(row) > col_count:
                    row = row[:col_count]
                norm.append(row)
            rows = norm
        if not col_count:
            return ""
        if len(alignments) != col_count:
            alignments = (list(alignments) + [""] * col_count)[:col_count]
        
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
        # Protect existing HTML entities from double-escaping
        entity_placeholders = {}
        def protect_entity(m):
            idx = len(entity_placeholders)
            placeholder = f'__HTMLENTITY_{idx}__'
            entity_placeholders[placeholder] = m.group(0)
            return placeholder
        text = re.sub(r'&[a-zA-Z]+;|&#\d+;', protect_entity, text)
        text = html.escape(text)
        for placeholder, entity in entity_placeholders.items():
            text = text.replace(placeholder, entity)
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
            <h2>目录</h2>
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
        """Render section slides (possibly multiple pages)
        
        For PPT output, content is condensed into bullet items (<li>)
        rather than long paragraphs (<p>).
        """
        slides = []
        # Build a short chapter thesis for the divider without putting the
        # full report paragraph on the page.
        section_summary = ""
        if section.content:
            summary_items = self._condenser.extract_all_bullets(section.content)
            section_summary = summary_items[0] if summary_items else ""
        
        slides.append(f'''<section class="slide" data-type="section-title" data-page="{start_slide_num}">
    <div class="slide-content">
        <div class="slide-title">
            <h2>{html.escape(section.title)}</h2>
        </div>
        <p class="section-summary">{ContentOrchestrator._inline_markdown(section_summary)}</p>
    </div>
</section>'''
        )
        
        charts = getattr(section, 'charts', []) or []
        chart_idx = 0
        
        if section.content:
            condensed = self._condenser.condense(
                section.content,
                title=section.title,
            )
            items = condensed.get("all_items", condensed.get("items", []))
            kpi_data = condensed.get("kpi_data", [])
            chart_suggestions = condensed.get("chart_suggestions", [])
            display_items = items
            
            if kpi_data and len(kpi_data) >= 2:
                kpi_slide_num = start_slide_num + 1
                kpi_items = []
                for kpi in kpi_data[:4]:
                    num = kpi.get("number", "")
                    label = kpi.get("label", "")
                    trend = kpi.get("trend", "")
                    parts = [num]
                    if label:
                        parts.insert(0, label)
                    if trend:
                        parts.append(trend)
                    kpi_items.append(html.escape(" ".join(p for p in parts if p)))
                
                kpi_li = "\n            ".join(f'<li>{item}</li>' for item in kpi_items)
                # Keep this as a content slide so the PPT renderer can detect
                # the numeric items and choose the editable KPI-card layout.
                slides.append(f'''<section class="slide" data-type="content" data-page="{kpi_slide_num}" data-section="{section.id}">
    <div class="slide-content">
        <div class="slide-title">
            <h2>{html.escape(section.title)} - 核心指标</h2>
        </div>
        <ul class="findings-list">
            {kpi_li}
        </ul>
    </div>
</section>'''
                )
                start_offset = 1
                # Do not show the same numeric evidence once as KPI cards and
                # again as ordinary bullets.  Keep anything beyond the
                # editable four-card capacity for the following content page.
                removed = 0
                display_items = []
                for item in items:
                    # A KPI card may replace a short, number-only bullet, but
                    # it must not replace a descriptive fact that contains
                    # several named entities or a category list.  Doing so
                    # used to delete revisions such as
                    # "Key verticals: semiconductor manufacturing ...".
                    descriptive_fact = ":" in item or "：" in item
                    if (
                        removed < 4
                        and self._condenser.extract_kpis(item)
                        and not descriptive_fact
                    ):
                        removed += 1
                        continue
                    display_items.append(item)
            else:
                start_offset = 0
            
            if display_items:
                chunk_size = self._condenser.max_bullets_per_slide
                item_chunks = [display_items[i:i+chunk_size] for i in range(0, len(display_items), chunk_size)]
                
                for ci, item_chunk in enumerate(item_chunks):
                    slide_num = start_slide_num + len(slides)
                    
                    chart_imgs = ""
                    while chart_idx < len(charts):
                        chart = charts[chart_idx]
                        anchor_type = chart.get("anchor_type", "section_end")
                        if anchor_type == "section_end" and ci < len(item_chunks) - 1:
                            break
                        chart_path = self._resolve_ppt_chart_path(chart.get("path", ""))
                        chart_alt = html.escape(chart.get("caption", "") or chart.get("title", "") or "Chart")
                        if chart_path:
                            chart_imgs += ContentOrchestrator._ppt_chart_img(chart_path, chart_alt, chart)
                        chart_idx += 1
                        if anchor_type != "section_end":
                            break
                    
                    li_items = []
                    for item in item_chunk:
                        li_items.append(f'<li>{ContentOrchestrator._inline_markdown(item)}</li>')
                    li_html = "\n            ".join(li_items)
                    
                    slides.append(f'''<section class="slide" data-type="content" data-page="{slide_num}" data-section="{section.id}">
    <div class="slide-content">
        <div class="slide-title">
            <h2>{html.escape(section.title)}</h2>
        </div>
        <div class="slide-body">
            <ul>
            {li_html}
            </ul>
            {chart_imgs}
        </div>
    </div>
</section>'''
                    )
            else:
                content_chunks = self._split_content_for_slides(section.content)
                for i, chunk in enumerate(content_chunks):
                    slide_num = start_slide_num + len(slides)
                    chart_imgs = ""
                    while chart_idx < len(charts):
                        chart = charts[chart_idx]
                        anchor = chart.get("insertion_anchor", "")
                        anchor_type = chart.get("anchor_type", "section_end")
                        if anchor_type == "section_end" and i < len(content_chunks) - 1:
                            break
                        if anchor and chunk.find(anchor) < 0 and anchor_type != "section_end":
                            break
                        chart_path = self._resolve_ppt_chart_path(chart.get("path", ""))
                        chart_alt = html.escape(chart.get("caption", "") or chart.get("title", "") or "Chart")
                        if chart_path:
                            chart_imgs += ContentOrchestrator._ppt_chart_img(chart_path, chart_alt, chart)
                        chart_idx += 1
                        if anchor_type != "section_end":
                            break
                    
                    slides.append(f'''<section class="slide" data-type="content" data-page="{slide_num}" data-section="{section.id}">
    <div class="slide-content">
        <div class="slide-title">
            <h2>{html.escape(section.title)}</h2>
        </div>
        <div class="slide-body">
            <p>{ContentOrchestrator._inline_markdown(chunk)}</p>
            {chart_imgs}
        </div>
    </div>
</section>'''
                    )
        
        while chart_idx < len(charts):
            chart = charts[chart_idx]
            chart_path = self._resolve_ppt_chart_path(chart.get("path", ""))
            chart_alt = html.escape(chart.get("caption", "") or chart.get("title", "") or "Chart")
            slide_num = start_slide_num + len(slides)
            if chart_path:
                slides.append(f'''<section class="slide" data-type="data" data-page="{slide_num}" data-section="{section.id}">
    <div class="slide-content">
        <div class="slide-title">
            <h2>{chart_alt}</h2>
        </div>
        <div class="slide-body">
            {ContentOrchestrator._ppt_chart_img(chart_path, chart_alt, chart)}
        </div>
    </div>
</section>'''
                )
            chart_idx += 1
        
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
            <h2>核心发现</h2>
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
            <h2>核心数据</h2>
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
            <h2>报告结论</h2>
        </div>
        <div class="slide-footer">
            <p>{html.escape(title)} · 谢谢观看</p>
        </div>
    </div>
</section>'''


# Export
__all__ = ["ContentOrchestrator", "ContentSection"]
