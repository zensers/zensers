# -*- coding: utf-8 -*-
"""
Template Engine
===============

Responsible for applying styles and templates to HTML content.

Core Functions:
1. Template loading and caching
2. Variable rendering ({{ variable }} syntax)
3. Loop rendering ({% for item in list %} syntax)
4. Conditional rendering ({% if condition %} syntax)
5. Style application and merging

Template Syntax:
- {{ variable }}: Simple variable
- {{ object.property }}: Nested attribute
- {% for item in list %}...{% endfor %}: Loop
- {% if condition %}...{% endif %}: Conditional
- {{ loop.index }}: Loop index (1-based)
- {{ loop.index0 }}: Loop index (0-based)
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Template name validation regex: Only allows letters, numbers, underscores, hyphens
TEMPLATE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


class TemplateEngine:
    """
    Template Engine
    
    Responsible for combining HTML content with templates and styles to generate final output.
    
    Usage Example:
        engine = TemplateEngine()
        
        # Apply template
        result = engine.apply_template(
            html_content="<article>...</article>",
            template_name="consulting",
            variables={"title": "Report Title"}
        )
    """
    
    # Variable matching regex
    VARIABLE_PATTERN = re.compile(r'\{\{\s*(\w+(?:\.\w+)*)\s*\}\}')
    
    # Default templates directory
    DEFAULT_TEMPLATES_DIR = "config/document_templates"
    
    def __init__(self, templates_dir: Optional[str] = None):
        """
        Initialize template engine
        
        Args:
            templates_dir: Template directory path
        """
        if templates_dir:
            self.templates_dir = Path(templates_dir)
        else:
            self.templates_dir = Path(self.DEFAULT_TEMPLATES_DIR)
        
        # Template cache
        self._template_cache: Dict[str, str] = {}
        
        # Default styles
        self._default_styles = self._init_default_styles()
        
        # Format-specific styles
        self._format_styles = self._init_format_styles()
    
    def _init_default_styles(self) -> Dict[str, Any]:
        """Initialize default styles"""
        return {
            "colors": {
                "primary": "#1A2744",      # Deep navy blue
                "secondary": "#2C3E50",    # Classic blue-gray
                "accent": "#C9A227",       # Amber gold
                "text": "#333333",         # Text gray
                "background": "#FFFFFF",   # Background white
                "success": "#27AE60",      # Success green
                "warning": "#E67E22"       # Warning orange
            },
            "fonts": {
                "title": "Georgia, serif",
                "body": "Arial, sans-serif",
                "chinese": "'Microsoft YaHei', 'SimHei', sans-serif"
            },
            "sizes": {
                "h1": "28px",
                "h2": "24px",
                "h3": "20px",
                "body": "14px"
            }
        }
    
    def _init_format_styles(self) -> Dict[str, Dict[str, Any]]:
        """Initialize format-specific styles"""
        return {
            "docx": {
                "page": {
                    "width": "210mm",
                    "height": "297mm",
                    "margin": {"top": "2.54cm", "bottom": "2.54cm", "left": "3.18cm", "right": "3.18cm"}
                },
                "line_spacing": "1.5"
            },
            "pptx": {
                "slide": {
                    "width": "1920px",
                    "height": "1080px"
                },
                "font_scale": 1.5
            },
            "pdf": {
                "page": {
                    "width": "210mm",
                    "height": "297mm"
                }
            }
        }
    
    def apply_template(
        self,
        html_content: str,
        template_name: str,
        variables: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Apply template to HTML content
        
        Args:
            html_content: Raw HTML content
            template_name: Template name
            variables: Template variables
            
        Returns:
            Processed HTML
        """
        # Load template
        template = self.load_template(template_name)
        
        if not template:
            # Template not found, return original content
            logger.warning(f"Template not found: {template_name}, returning original content")
            return html_content
        
        # Merge variables
        if variables is None:
            variables = {}
        
        # Ensure content variable exists
        if "content" not in variables:
            variables["content"] = html_content
        
        # Full render template (loop + conditional + variable)
        result = self.render_template(template, variables)
        
        return result
    
    def load_template(self, template_name: str) -> Optional[str]:
        """
        Load template file
        
        Args:
            template_name: Template name
            
        Returns:
            Template content, returns None if not found
        """
        # Security validation: prevent path traversal
        if not TEMPLATE_NAME_PATTERN.match(template_name):
            logger.warning(f"Invalid template name: {template_name}")
            return None
        
        # Check cache
        if template_name in self._template_cache:
            return self._template_cache[template_name]
        
        # Look up template file
        template_path = self.templates_dir / f"{template_name}.html"
        
        # Verify path safety: ensure resolved path is still within template directory
        try:
            resolved_path = template_path.resolve()
            resolved_dir = self.templates_dir.resolve()
            if not str(resolved_path).startswith(str(resolved_dir)):
                logger.warning(f"Path traversal attempt in template name: {template_name}")
                return None
        except (OSError, ValueError):
            return None
        
        if not template_path.exists():
            return None
        
        # Read template
        try:
            content = template_path.read_text(encoding="utf-8")
            self._template_cache[template_name] = content
            return content
        except Exception as e:
            logger.error(f"Failed to load template {template_name}: {e}")
            return None
    
    def render_variables(
        self,
        template: str,
        variables: Dict[str, Any]
    ) -> str:
        """
        Render template variables
        
        Supports:
        - {{ variable }}: Simple variable
        - {{ object.property }}: Nested attribute
        
        Args:
            template: Template string
            variables: Variable dictionary
            
        Returns:
            Rendered string
        """
        def replace_variable(match):
            var_path = match.group(1)
            value = self._get_nested_value(variables, var_path)
            return str(value) if value is not None else match.group(0)
        
        return self.VARIABLE_PATTERN.sub(replace_variable, template)
    
    # Loop matching regex: {% for item in list %}...{% endfor %}
    LOOP_PATTERN = re.compile(
        r'\{%\s*for\s+(\w+)\s+in\s+(\w+(?:\.\w+)*)\s*%\}(.*?)\{%\s*endfor\s*%\}',
        re.DOTALL
    )
    
    # Conditional matching regex: {% if condition %}...{% endif %}
    # P0-3 fix: support nested attributes like section.tables
    IF_PATTERN = re.compile(
        r'\{%\s*if\s+([\w.]+)\s*%\}(.*?)\{%\s*endif\s*%\}',
        re.DOTALL
    )
    
    def render_loops(
        self,
        template: str,
        variables: Dict[str, Any]
    ) -> str:
        """
        Render loop statements (supports nesting)
        
        Supports:
        - {% for item in list %}...{% endfor %}
        - Proper handling of nested loops
        - Use {{ item.property }} inside loop body
        - {{ loop.index }}: Loop index (1-based)
        
        Args:
            template: Template string
            variables: Variable dictionary
            
        Returns:
            Rendered string
        """
        # Iteratively render all outermost loops
        max_iterations = 50  # Prevent infinite loop
        result = template
        
        for _ in range(max_iterations):
            # Check if there are unrendered loops
            if not re.search(r'\{%\s*for\s+\w+\s+in\s+', result):
                break
            
            # Render one outermost loop
            new_result = self._render_outermost_loop(result, variables)
            
            # If result hasn't changed, no more loops to render
            if new_result == result:
                break
            
            result = new_result
        
        return result
    
    def _render_outermost_loop(
        self,
        template: str,
        variables: Dict[str, Any]
    ) -> str:
        """Render the outermost loop (properly handles nesting)"""
        # Find first {% for
        for_match = re.search(r'\{%\s*for\s+(\w+)\s+in\s+(\w+(?:\.\w+)*)\s*%\}', template)
        if not for_match:
            return template
        
        item_name = for_match.group(1)
        list_name = for_match.group(2)
        start_pos = for_match.start()
        body_start = for_match.end()
        
        # Find matching {% endfor %} (using stack for nesting)
        depth = 1
        pos = body_start
        # P0-3 fix: support nested attributes like table.rows
        for_endfor_pattern = re.compile(r'\{%\s*(for\s+[\w.]+\s+in\s+[\w.]+|endfor)\s*%\}', re.IGNORECASE)
        
        while depth > 0 and pos < len(template):
            match = for_endfor_pattern.search(template, pos)
            if not match:
                break
            
            matched_text = match.group(1).strip()
            if matched_text.startswith('for'):
                depth += 1
            else:  # endfor
                depth -= 1
            
            pos = match.end()
        
        if depth > 0:
            logger.warning("Unmatched {% for %}...{% endfor %}")
            return template
        
        # P0-3 fix: find start position of matching {% endfor %} tag
        # When depth becomes 0, match points to the last endfor, match.start() is the endfor start
        endfor_only_pattern = re.compile(r'\{%\s*endfor\s*%\}', re.IGNORECASE)
        
        # Find the last endfor between body_start and pos
        endfor_matches = list(endfor_only_pattern.finditer(template, body_start, pos + 1))
        if not endfor_matches:
            logger.warning("Could not find matching {% endfor %}")
            return template
        
        # The last matching endfor is the one we need
        endfor_match = endfor_matches[-1]
        
        # Extract loop body (from end of {% for %} to start of {% endfor %})
        body_end = endfor_match.start()
        loop_body = template[body_start:body_end].strip()
        
        # Get list data
        items = self._get_nested_value(variables, list_name)
        if items is None or not isinstance(items, (list, tuple)):
            # For nested variables (e.g. section.tables), variable may not exist
            # Silently remove loop block, only warn when top-level variable not found
            if '.' in list_name:
                # Nested variable, silently skip
                logger.debug(f"Nested loop variable '{list_name}' not found, skipping loop")
            else:
                logger.warning(f"Loop variable '{list_name}' not found or not a list")
            # Remove entire loop block
            return template[:start_pos] + template[pos:]
        
        # Render loop
        result_parts = []
        for index, item in enumerate(items):
            loop_context = {
                item_name: item,
                'loop': {
                    'index': index + 1,
                    'index0': index,
                    'first': index == 0,
                    'last': index == len(items) - 1,
                    'length': len(items),
                }
            }
            merged_vars = {**variables, **loop_context}
            
            # P0-3 fix: recursively handle nested loops, use render_loops for all nested loops
            rendered_body = self.render_loops(loop_body, merged_vars)
            rendered_body = self.render_variables(rendered_body, merged_vars)
            result_parts.append(rendered_body)
        
        # Replace entire loop block
        return template[:start_pos] + ''.join(result_parts) + template[pos:]
    
    def render_conditions(
        self,
        template: str,
        variables: Dict[str, Any]
    ) -> str:
        """
        Render conditional statements
        
        Supports:
        - {% if variable %}...{% endif %}
        - {% if object.property %}...{% endif %}
        - Properly handle nested if statements
        
        Args:
            template: Template string
            variables: Variable dictionary
            
        Returns:
            Rendered string
        """
        # P0-3 fix: use iterative approach, support nested if
        result = template
        
        while True:
            # Find first {% if
            if_match = re.search(r'\{%\s*if\s+([\w.]+)\s*%\}', result)
            if not if_match:
                break
            
            condition_name = if_match.group(1)
            start_pos = if_match.start()
            body_start = if_match.end()
            
            # Find matching {% endif %} (using stack for nesting)
            depth = 1
            pos = body_start
            if_endif_pattern = re.compile(r'\{%\s*(if\s+[\w.]+|endif)\s*%\}', re.IGNORECASE)
            
            while depth > 0 and pos < len(result):
                match = if_endif_pattern.search(result, pos)
                if not match:
                    break
                
                matched_text = match.group(1).strip()
                if matched_text.startswith('if'):
                    depth += 1
                else:  # endif
                    depth -= 1
                
                pos = match.end()
            
            if depth > 0:
                logger.warning("Unmatched {% if %}...{% endif %}")
                break
            
            # Find matching {% endif %} tag
            endif_only_pattern = re.compile(r'\{%\s*endif\s*%\}', re.IGNORECASE)
            endif_match = endif_only_pattern.search(result, pos - 100)
            while endif_match and endif_match.end() != pos:
                endif_match = endif_only_pattern.search(result, endif_match.end())
            
            if not endif_match:
                logger.warning("Could not find matching {% endif %}")
                break
            
            # Extract conditional body
            body_end = endif_match.start()
            if_body = result[body_start:body_end]
            
            # Check for {% else %} in the conditional body
            else_match = re.search(r'\{%\s*else\s*%\}', if_body)
            if else_match:
                true_body = if_body[:else_match.start()]
                false_body = if_body[else_match.end():]
            else:
                true_body = if_body
                false_body = ''
            
            # Get condition value
            # If the condition references a loop variable (not in top-level scope yet),
            # preserve the entire if-body (including else branch) and let cleanup handle the tags.
            condition_top_var = condition_name.split('.')[0]
            if condition_top_var not in variables:
                logger.debug(f"Preserving condition '{condition_name}': top-level variable '{condition_top_var}' not in scope yet")
                result = result[:start_pos] + if_body + result[pos:]
                continue
            condition_value = self._get_nested_value(variables, condition_name)
            
            # Replace entire if block
            if condition_value:
                replacement = true_body
            else:
                replacement = false_body
            
            result = result[:start_pos] + replacement + result[pos:]
        
        return result
    
    def render_template(
        self,
        template: str,
        variables: Dict[str, Any]
    ) -> str:
        """
        Full render template (loop + conditional + variable)
        
        Render order (after P0-3 fix):
        1. Render conditions first (may contain loops)
        2. Render loops (handle loops exposed inside conditions)
        3. Repeat 1-2 until no changes
        4. Finally render variables
        
        Args:
            template: Template string
            variables: Variable dictionary
            
        Returns:
            Fully rendered string
        """
        # Iterative rendering until no changes
        max_iterations = 10
        for _ in range(max_iterations):
            # 1. Render conditions
            new_result = self.render_conditions(template, variables)
            # 2. Render loops
            new_result = self.render_loops(new_result, variables)
            # If no changes, stop
            if new_result == template:
                break
            
            template = new_result
        
        # 3. Finally render variables
        result = self.render_variables(template, variables)
        
        # 4. Final cleanup: remove any remaining template syntax
        result = self._cleanup_remaining_tags(result)
        
        return result
    
    def _cleanup_remaining_tags(self, content: str) -> str:
        """
        Clean up remaining template tags
        
        As a last resort, remove any unrendered template syntax.
        Note: Do not remove <style> and <head> as they contain critical CSS style definitions.
        """
        # Remove <script> tags and their content
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML comments (preserve comments in style/head for debugging)
        content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
        # Remove remaining {% %} tags
        content = re.sub(r'\{%.*?%\}', '', content, flags=re.DOTALL)
        # Remove remaining {{ }} tags
        content = re.sub(r'\{\{.*?\}\}', '', content, flags=re.DOTALL)
        # Clean up excess whitespace
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        return content.strip()
    
    def validate_rendered(self, content: str) -> bool:
        """
        Verify if rendered result still has template tag remnants
        
        Args:
            content: Rendered content
            
        Returns:
            True if no remnants, False if remnants exist
        """
        remaining = re.findall(r'\{%.*?%\}|\{\{.*?\}\}', content)
        if remaining:
            logger.warning(f"Unrendered template tags: {remaining[:5]}")
            return False
        return True
    
    def _get_nested_value(
        self,
        data: Dict[str, Any],
        path: str
    ) -> Optional[Any]:
        """
        Get nested attribute value
        
        Args:
            data: Data dictionary
            path: Attribute path (e.g., "colors.primary")
            
        Returns:
            Attribute value, returns None if not found
        """
        keys = path.split(".")
        value = data
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        
        return value
    
    def get_default_styles(self) -> Dict[str, Any]:
        """Get default styles"""
        return self._default_styles.copy()
    
    def apply_inline_styles(
        self,
        html_content: str,
        styles: Dict[str, Any]
    ) -> str:
        """
        Apply inline styles to HTML
        
        Args:
            html_content: HTML content
            styles: Style dictionary
            
        Returns:
            HTML with styles
        """
        # Build style tag
        style_parts = ["<style>"]
        
        # Colors
        colors = styles.get("colors", {})
        if colors:
            if "primary" in colors:
                style_parts.append(f"h1, h2 {{ color: {colors['primary']}; }}")
            if "text" in colors:
                style_parts.append(f"body {{ color: {colors['text']}; }}")
        
        # Fonts
        fonts = styles.get("fonts", {})
        if fonts:
            if "body" in fonts:
                style_parts.append(f"body {{ font-family: {fonts['body']}; }}")
        
        style_parts.append("</style>")
        
        style_tag = "\n".join(style_parts)
        
        # Insert into head or beginning
        if "</head>" in html_content:
            return html_content.replace("</head>", f"{style_tag}\n</head>")
        else:
            return f"{style_tag}\n{html_content}"
    
    def merge_styles(
        self,
        base_styles: Dict[str, Any],
        custom_styles: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge styles (custom overrides base)
        
        Args:
            base_styles: Base styles
            custom_styles: Custom styles
            
        Returns:
            Merged styles
        """
        result = base_styles.copy()
        
        for key, value in custom_styles.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                # Deep merge
                result[key] = {**result[key], **value}
            else:
                result[key] = value
        
        return result
    
    def get_format_template(self, output_format: str) -> str:
        """
        Get format-specific base template
        
        Args:
            output_format: Output format
            
        Returns:
            Base template HTML
        """
        templates = {
            "docx": '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.5; }
        article { max-width: 800px; margin: 0 auto; }
        h1 { color: #1A2744; font-size: 28px; }
        h2 { color: #2C3E50; font-size: 24px; }
        section { margin-bottom: 20px; }
    </style>
</head>
<body>
{{ content }}
</body>
</html>''',
            "pptx": '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; }
        .slide { width: 1920px; height: 1080px; padding: 60px; box-sizing: border-box; }
        h1 { color: #1A2744; font-size: 48px; }
        h2 { color: #2C3E50; font-size: 36px; }
        p { font-size: 24px; line-height: 1.6; }
    </style>
</head>
<body>
{{ content }}
</body>
</html>''',
            "pdf": '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; }
        article { max-width: 800px; margin: 0 auto; }
        h1 { color: #1A2744; }
    </style>
</head>
<body>
{{ content }}
</body>
</html>'''
        }
        
        return templates.get(output_format, templates["docx"])
    
    def get_format_styles(self, output_format: str) -> Dict[str, Any]:
        """
        Get format-specific styles
        
        Args:
            output_format: Output format
            
        Returns:
            Style dictionary
        """
        return self._format_styles.get(output_format, {})


# Export
__all__ = [
    "TemplateEngine",
    "TEMPLATE_NAME_PATTERN",
]