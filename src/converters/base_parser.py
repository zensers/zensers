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
            
        elif tag in ['div', 'section']:
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
                    'p', 'blockquote',
                    'li', 'ul', 'ol', 'code', 'pre']:
            if tag == 'pre':
                self._in_preformatted = False
            self._end_element(tag)
            
        elif tag in ['div', 'section']:
            # Emit structural end marker
            self._pop_tag(tag)
            elem_type = f"{tag}_end"
            self.elements.append({"type": elem_type})
            
        elif tag in ['strong', 'b', 'em', 'i', 'a']:
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
        
        # Collect any accumulated text
        text = ""
        if self.elements and self.elements[-1].get("type") == "text":
            text = self.elements.pop()["content"]
        
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
        self._slides: List[List[Dict]] = [[]]
        self._current_slide_index = 0
    
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        """Handle start tag with slide splitting."""
        attr_dict = dict(attrs)
        
        # h1 acts as a slide separator
        if tag == 'h1':
            # Start new slide
            if self._slides[self._current_slide_index]:
                self._slides.append([])
                self._current_slide_index += 1
        
        super().handle_starttag(tag, attrs)
    
    def handle_endtag(self, tag: str):
        """Handle end tag."""
        super().handle_endtag(tag)
    
    def get_slides(self) -> List[List[Dict]]:
        """Get all parsed slides."""
        return self._slides
    
    def reset_parser(self):
        """Reset parser state including slides."""
        super().reset_parser()
        self._slides = [[]]
        self._current_slide_index = 0