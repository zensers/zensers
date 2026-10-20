# -*- coding: utf-8 -*-
"""
HTML Parser Base Class
=====================

Provides generic HTML parsing functionality for converters to inherit from.

Core features:
1. HTML tag parsing
2. Heading/paragraph/list/table handling
3. Element collection

Usage example:
    class MyParser(HTMLElementParser):
        def handle_custom_tag(self, tag, attrs):
            # Custom handling
            pass
"""

import logging
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class HTMLElementParser(HTMLParser):
    """
    HTML Element Parser Base Class
    
    Converts HTML to a structured element list for format converters.
    
    Sub-classes can extend:
    - handle_starttag: Add custom tag handling
    - handle_endtag: Add custom end tag handling
    """
    
    # Maximum nesting depth (prevents malicious nesting)
    MAX_LIST_DEPTH = 10
    
    # Tag-to-semantic-type mapping for Word converter compatibility
    TAG_TYPE_MAP = {
        "h1": "heading", "h2": "heading", "h3": "heading",
        "h4": "heading", "h5": "heading", "h6": "heading",
        "p": "paragraph",
        "li": "list_item",
        "figcaption": "figure_caption",
        "figure": "figure",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements: List[Dict[str, Any]] = []
        self._tag_stack: List[str] = []  # Stack for nested element tracking
        self._attr_stack: List[Dict[str, str]] = []  # Attributes per nesting level
        self._list_stack: List[str] = []
        self._table_data: List[Dict[str, Any]] = []
        self._in_table = False
        self._current_row: List[Union[str, Dict]] = []
        self._current_cell: str = ""
        self._current_cell_attrs: Dict = {}
        self._in_preformatted = False
        self._skip_next_newline = False
        
        # Heading counter for generating table of contents
        self._heading_counters: Dict[int, int] = {}
    
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        """Handle start tag."""
        attr_dict = dict(attrs)

        if tag in ('span', 'font', 'small'):
            # Inline wrapper: track but don't create element boundary
            self._push_tag(tag, attr_dict)
            return
        
        if tag == 'table':
            self._in_table = True
            self._current_row = []
            self._table_data.append({
                "attrs": attr_dict,
                "rows": [],
                "headers": [],
            })
        
        elif tag == 'tr':
            if self._in_table:
                self._current_row = []
        
        elif tag in ('th', 'td'):
            if self._in_table:
                self._current_cell = ""
                self._current_cell_attrs = {}
                for attr_name, attr_value in attrs:
                    if attr_name in ('colspan', 'rowspan'):
                        self._current_cell_attrs[attr_name] = attr_value
        
        elif tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag[1])
            self._heading_counters[level] = self._heading_counters.get(level, 0) + 1
            for l in range(level + 1, 7):
                self._heading_counters[l] = 0
            self._start_element(tag, attr_dict)
            
        elif tag in ['div', 'section', 'figure']:
            # Emit structural start marker
            cls = attr_dict.get("class", "")
            elem_type = f"{tag}_start"
            self.elements.append({
                "type": elem_type,
                "class": cls,
                "attrs": attr_dict,
            })
            self._push_tag(tag, attr_dict)
            
        elif tag in ['p', 'blockquote']:
            self._start_element(tag, attr_dict)
            
        elif tag in ['ul', 'ol']:
            if len(self._list_stack) < self.MAX_LIST_DEPTH:
                self._list_stack.append(tag)
                self._start_element(tag, attr_dict)
            
        elif tag == 'li':
            self._start_element(tag, attr_dict)

        elif tag == 'figcaption':
            self._start_element(tag, attr_dict)
            
        elif tag in ['thead', 'tbody']:
            pass  # Just organizational
            
        elif tag == 'br':
            self._add_text_element("\n")
            
        elif tag in ['strong', 'b']:
            self._push_tag(tag, attr_dict)
            
        elif tag in ['em', 'i']:
            self._push_tag(tag, attr_dict)
            
        elif tag == 'a':
            self._push_tag(tag, attr_dict)
            
        elif tag == 'img':
            self.elements.append({
                "type": "image",
                "src": attr_dict.get("src", ""),
                "alt": attr_dict.get("alt", ""),
                "attrs": attr_dict,
            })
            
        elif tag in ['code', 'pre']:
            if tag == 'pre':
                self._in_preformatted = True
            self._start_element(tag, attr_dict)
            
        else:
            self._start_element(tag, attr_dict)
    
    def handle_endtag(self, tag: str):
        """Handle end tag."""
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                    'p', 'blockquote', 'figcaption',
                    'li', 'ul', 'ol', 'code', 'pre']:
            if tag == 'pre':
                self._in_preformatted = False
            self._end_element(tag)
            
        elif tag in ['div', 'section', 'figure']:
            # Emit structural end marker
            self._pop_tag(tag)
            elem_type = f"{tag}_end"
            self.elements.append({"type": elem_type})
            
        elif tag in ['strong', 'b', 'em', 'i', 'a']:
            self._pop_tag(tag)
            
        elif tag in ['span', 'font', 'small']:
            # Inline wrapper close: text already merged into parent text node
            self._pop_tag(tag)

        elif tag in ['table', 'thead', 'tbody']:
            self._handle_table_end(tag)
            
        elif tag == 'tr':
            if self._in_table:
                self._table_data[-1]["rows"].append(list(self._current_row))
                self._current_row = []
                
        elif tag in ['th', 'td']:
            if self._in_table and self._current_row is not None:
                cell_info = {
                    "text": self._current_cell.strip(),
                    "tag": tag,
                }
                if self._current_cell_attrs:
                    if "colspan" in self._current_cell_attrs:
                        cell_info["colspan"] = int(self._current_cell_attrs["colspan"])
                    if "rowspan" in self._current_cell_attrs:
                        cell_info["rowspan"] = int(self._current_cell_attrs["rowspan"])
                self._current_row.append(cell_info)
                self._current_cell = ""
                self._current_cell_attrs = {}
    
    def handle_data(self, data: str):
        """Handle text data."""
        if self._in_table:
            self._current_cell += data
            return

        # Get current element context
        if self.elements and self.elements[-1].get("type") == "text":
            self.elements[-1]["content"] += data
        else:
            self._add_text_element(data)
    
    def handle_entityref(self, name: str):
        """Handle HTML entity references."""
        char = self._resolve_entity(name)
        self.handle_data(char)
    
    def handle_charref(self, name: str):
        """Handle numeric character references."""
        try:
            if name.startswith('x'):
                char = chr(int(name[1:], 16))
            else:
                char = chr(int(name))
            self.handle_data(char)
        except ValueError:
            pass
    
    def _resolve_entity(self, name: str) -> str:
        """Resolve HTML entity name to character."""
        entities = {
            'nbsp': ' ', 'amp': '&', 'lt': '<', 'gt': '>',
            'quot': '"', 'apos': "'",
            'copy': '©', 'reg': '®', 'trade': '™',
            'mdash': '—', 'ndash': '–',
            'ldquo': '"', 'rdquo': '"', 'lsquo': "'", 'rsquo': "'",
        }
        return entities.get(name, f'&{name};')
    
    def _push_tag(self, tag: str, attrs: Dict[str, str]):
        """Push tag onto stack for nested tracking."""
        self._tag_stack.append(tag)
        self._attr_stack.append(attrs)

    def _pop_tag(self, tag: str) -> bool:
        """Pop tag from stack. Returns False if not found (mismatch)."""
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
            self._attr_stack.pop()
            return True
        return False

    def _start_element(self, tag: str, attrs: Dict[str, str]):
        """Start tracking an element."""
        self._push_tag(tag, attrs)
    
    def _end_element(self, tag: str):
        """End tracking and store element."""
        # Read attrs BEFORE _pop_tag — it pops the current element's attrs
        attrs = self._attr_stack[-1] if self._attr_stack else {}
        
        if not self._pop_tag(tag):
            return
        
        # Collect any accumulated text (span text lands as sibling text nodes)
        text = ""
        while self.elements and self.elements[-1].get("type") == "text":
            text = self.elements.pop()["content"] + text
        
        # Map raw tag name to semantic type
        semantic_type = self.TAG_TYPE_MAP.get(tag, tag)
        
        element = {
            "type": semantic_type,
        }
        
        # Add level for headings
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            element["level"] = int(tag[1])
            element["text"] = text.strip()
        elif tag == 'p':
            element["text"] = text.strip()
        elif tag == 'figcaption':
            element["text"] = text.strip()
        elif tag == 'li':
            element["text"] = text.strip()
            # Determine list type from parent stack
            list_type = "ul"
            for t in reversed(self._tag_stack):
                if t in ('ul', 'ol'):
                    list_type = t
                    break
            element["list_type"] = list_type
        elif tag == 'img':
            element["src"] = text.strip()
        else:
            element["content"] = text.strip()
        
        # Preserve attributes (read before _pop_tag above)
        if attrs:
            element["attrs"] = attrs
            if "class" in attrs:
                element["class"] = attrs["class"]
            if "style" in attrs:
                element["style"] = attrs["style"]
        
        # Handle list nesting
        if tag in ['ul', 'ol'] and self._list_stack:
            self._list_stack.pop()
        
        self.elements.append(element)
    
    def _add_text_element(self, text: str):
        """Add a text element."""
        if text.strip() or (self._in_preformatted and text):
            self.elements.append({
                "type": "text",
                "content": text,
            })
    
    def _handle_table_tag(self, tag: str, attrs: Dict[str, str]):
        """Handle table-related tags."""
        if tag == 'table':
            self._in_table = True
            self._table_data.append({
                "attrs": attrs,
                "rows": [],
                "headers": [],
            })
        elif tag in ['thead', 'tbody']:
            pass  # Just organizational
        elif tag == 'tr':
            pass  # Row will be handled in end tag
    
    def _handle_table_end(self, tag: str):
        """Handle table end tags."""
        if tag == 'table':
            self._in_table = False
            if self._table_data:
                table = self._table_data.pop()
                if table["rows"]:
                    table["headers"] = table["rows"].pop(0)
                self.elements.append({
                    "type": "table",
                    "attrs": table["attrs"],
                    "headers": table["headers"],
                    "rows": table["rows"],
                })
    
    def get_elements(self) -> List[Dict[str, Any]]:
        """Get parsed element list."""
        return self.elements
    
    def get_heading_counters(self) -> Dict[int, int]:
        """Get heading counters for table of contents generation."""
        return self._heading_counters.copy()
    
    def reset_parser(self):
        """Reset parser state."""
        self.elements = []
        self._tag_stack = []
        self._attr_stack = []
        self._list_stack = []
        self._table_data = []
        self._in_table = False
        self._current_row = []
        self._current_cell = ""
        self._current_cell_attrs = {}
        self._in_preformatted = False
        self._skip_next_newline = False
        self._heading_counters = {}


class SlideElementParser(HTMLElementParser):
    """
    Slide-specific HTML parser.
    
    Parses HTML specifically for PPT generation, splitting content into slides.
    """
    
    def __init__(self):
        super().__init__()
        self._raw_slides: List[List[Dict]] = [[]]
        self._current_slide_index = 0
    
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        """Handle start tag with slide splitting."""
        attr_dict = dict(attrs)
        
        # h1 acts as a slide separator
        if tag == 'h1':
            if self._raw_slides[self._current_slide_index]:
                self._raw_slides.append([])
                self._current_slide_index += 1
        
        super().handle_starttag(tag, attrs)
    
    def handle_endtag(self, tag: str):
        """Handle end tag."""
        super().handle_endtag(tag)
    
    def get_slides(self) -> List[Dict[str, Any]]:
        """Get all parsed slides as structured slide dicts.
        
        Groups self.elements by section_start/section_end markers into
        slide dicts with keys: slide_type, title, content, items, table_data, images.
        Falls back to h1-based splitting if no section markers found.
        """
        return self._group_elements_into_slides()
    
    def _group_elements_into_slides(self) -> List[Dict[str, Any]]:
        """Group parsed elements into slide dicts for _create_pptx_document."""
        elements = self.elements
        if not elements:
            return []
        
        has_sections = any(e.get("type") in ("section_start", "section_end", "div_start", "div_end") for e in elements)
        
        if has_sections:
            raw_slides = self._group_by_sections(elements)
        else:
            raw_slides = self._group_by_h1(elements)
        
        return self._split_dense_slides(raw_slides)
    
    def _group_by_sections(self, elements: List[Dict]) -> List[Dict[str, Any]]:
        """Group elements by section_start/section_end markers.
        
        Only <section> elements with data-type attribute are treated as slide boundaries.
        <div> elements are treated as structural containers (not slide separators).
        """
        slides = []
        current_elements: List[Dict] = []
        current_attrs: Dict[str, str] = {}
        in_section_slide = False
        
        for elem in elements:
            etype = elem.get("type", "")
            
            if etype == "section_start":
                attrs = elem.get("attrs", {})
                if attrs.get("data-type"):
                    if current_elements and in_section_slide:
                        slide = self._build_slide_dict(current_elements, current_attrs)
                        if slide:
                            slides.append(slide)
                    current_elements = []
                    current_attrs = attrs
                    in_section_slide = True
                else:
                    pass
            elif etype == "section_end":
                attrs_snapshot = current_attrs
                if in_section_slide:
                    slide = self._build_slide_dict(current_elements, current_attrs)
                    if slide:
                        slides.append(slide)
                    current_elements = []
                    current_attrs = {}
                    in_section_slide = False
            elif etype in ("div_start", "div_end"):
                pass
            else:
                if in_section_slide:
                    current_elements.append(elem)
        
        if current_elements and in_section_slide:
            slide = self._build_slide_dict(current_elements, current_attrs)
            if slide:
                slides.append(slide)
        
        return slides
    
    def _group_by_h1(self, elements: List[Dict]) -> List[Dict[str, Any]]:
        """Group elements by h1 headings as slide separators."""
        slides = []
        current_elements: List[Dict] = []
        
        for elem in elements:
            if elem.get("type") == "heading" and elem.get("level") == 1:
                if current_elements:
                    slide = self._build_slide_dict(current_elements)
                    if slide:
                        slides.append(slide)
                current_elements = [elem]
            else:
                current_elements.append(elem)
        
        if current_elements:
            slide = self._build_slide_dict(current_elements)
            if slide:
                slides.append(slide)
        
        return slides
    
    def _build_slide_dict(self, elements: List[Dict], attrs: Dict[str, str] = None) -> Dict[str, Any]:
        """Build a slide dict from a list of elements.
        
        Output format matches _create_pptx_document expectations:
        slide_type, title, content, items, table_data, images.
        """
        attrs = attrs or {}
        slide_type = attrs.get("data-type", "content")
        
        title = ""
        content_parts: List[str] = []
        items: List[str] = []
        table_data: List[List[str]] = []
        images: List[Dict[str, str]] = []
        extra_tables: List[List[List[str]]] = []
        
        for elem in elements:
            etype = elem.get("type", "")
            
            if etype == "heading":
                level = elem.get("level", 2)
                text = elem.get("text", "")
                if level == 1 and not title:
                    title = text
                elif level == 2 and not title:
                    title = text
                else:
                    content_parts.append(text)
            
            elif etype == "paragraph":
                text = elem.get("text", "")
                if text:
                    content_parts.append(text)
            
            elif etype == "list_item":
                text = elem.get("text", "")
                if text:
                    items.append(text)
            
            elif etype == "image":
                src = elem.get("src", "")
                alt = elem.get("alt", "")
                if src:
                    img_entry = {"src": src, "alt": alt}
                    attrs = elem.get("attrs", {}) or {}
                    if attrs.get("data-image-type"):
                        img_entry["image_type"] = attrs["data-image-type"]
                    if attrs.get("data-chart-type"):
                        img_entry["chart_type"] = attrs["data-chart-type"]
                    images.append(img_entry)
            
            elif etype == "table":
                headers = elem.get("headers", [])
                rows = elem.get("rows", [])
                table_rows = []
                if headers:
                    header_texts = []
                    for h in headers:
                        if isinstance(h, dict):
                            header_texts.append(h.get("text", ""))
                        else:
                            header_texts.append(str(h))
                    table_rows.append(header_texts)
                for row in rows:
                    row_texts = []
                    for cell in row:
                        if isinstance(cell, dict):
                            row_texts.append(cell.get("text", ""))
                        else:
                            row_texts.append(str(cell))
                    table_rows.append(row_texts)
                if table_rows:
                    if table_data:
                        extra_tables.append(table_rows)
                    else:
                        table_data = table_rows
            
            elif etype == "text":
                text = elem.get("content", "").strip()
                if text:
                    content_parts.append(text)
        
        slide = {
            "slide_type": slide_type,
            "title": title,
        }
        
        if content_parts:
            slide["content"] = "\n".join(content_parts)
        if items:
            slide["items"] = items
        if table_data:
            slide["table_data"] = table_data
        if images:
            slide["images"] = images
        if extra_tables:
            slide["extra_tables"] = extra_tables
        
        source = attrs.get("data-source", "")
        if source:
            slide["source_text"] = source
        
        return slide
    
    def _split_dense_slides(self, slides: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Split slides that are too dense into multiple per-key-point slides.
        
        Strategy:
        - content/findings slides with 6+ items: split into evenly-sized chunks
        - Each chunk gets at most 1 image (images distributed across sub-slides)
        - data slides: keep as-is (tables should stay whole)
        - cover/toc/end slides: keep as-is
        """
        MAX_ITEMS_PER_SLIDE = 5
        
        result = []
        for slide in slides:
            stype = slide.get("slide_type", "content")
            if stype in ("cover", "toc", "end"):
                result.append(slide)
                continue
            
            items = slide.get("items", [])
            images = slide.get("images", [])
            content = slide.get("content", "")
            table_data = slide.get("table_data", [])
            
            if stype == "data" and table_data:
                result.append(slide)
                continue
            
            if len(items) <= MAX_ITEMS_PER_SLIDE:
                result.append(slide)
                continue
            
            num_chunks = (len(items) + MAX_ITEMS_PER_SLIDE - 1) // MAX_ITEMS_PER_SLIDE
            base_size = len(items) // num_chunks
            remainder = len(items) % num_chunks
            
            img_per_chunk = max(1, len(images) // num_chunks) if images else 0
            
            item_offset = 0
            for ci in range(num_chunks):
                chunk_size = base_size + (1 if ci < remainder else 0)
                chunk_items = items[item_offset:item_offset + chunk_size]
                item_offset += chunk_size
                
                chunk_slide = {
                    "slide_type": stype,
                    "title": slide.get("title", ""),
                }
                
                if chunk_items:
                    chunk_slide["items"] = chunk_items
                
                if ci == 0 and content:
                    chunk_slide["content"] = content
                
                if table_data:
                    chunk_slide["table_data"] = table_data
                
                if images:
                    img_start = ci * img_per_chunk
                    img_end = min(img_start + img_per_chunk, len(images)) if ci < num_chunks - 1 else len(images)
                    chunk_images = images[img_start:img_end]
                    if chunk_images:
                        chunk_slide["images"] = chunk_images
                
                if "extra_tables" in slide and ci == 0:
                    chunk_slide["extra_tables"] = slide["extra_tables"]
                
                result.append(chunk_slide)
        
        return result
    
    def reset_parser(self):
        """Reset parser state including slides."""
        super().reset_parser()
        self._raw_slides = [[]]
        self._current_slide_index = 0