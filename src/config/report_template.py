# -*- coding: utf-8 -*-
"""
Report Template Configuration Loading Module
==================

Load and manage report template configurations.

Usage:
    from src.config.report_template import load_template, ReportTemplate

    # Load template
    template = load_template("default_report")

    # Access configuration
    print(template.meta['name'])
    for chart in template.charts:
        print(chart['title'])
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import logging

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


@dataclass
class PointConfig:
    zh: str = ""
    en: str = ""

    @property
    def text(self) -> str:
        return self.zh or self.en


@dataclass
class SubSectionConfig:
    id: str = ""
    name: Any = field(default_factory=dict)
    description: Any = field(default_factory=dict)
    points: List[PointConfig] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        if isinstance(self.name, dict):
            return self.name.get("zh", self.name.get("en", self.id))
        return str(self.name) or self.id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "points": [{"zh": pt.zh, "en": pt.en} for pt in self.points],
        }


@dataclass
class SectionConfig:
    id: str = ""
    name: Any = field(default_factory=dict)
    required: bool = False
    description: Any = field(default_factory=dict)
    sub_sections: List[SubSectionConfig] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        if isinstance(self.name, dict):
            return self.name.get("zh", self.name.get("en", self.id))
        return str(self.name) or self.id

    def to_subsections_list(self) -> List[Dict]:
        return [
            {
                "id": sub.id,
                "title": sub.display_name,
                "name": sub.name,
                "points": [pt.text for pt in sub.points],
            }
            for sub in self.sub_sections
        ]

    def get(self, key: str, default: Any = None) -> Any:
        mapping = {
            "id": self.id,
            "name": self.name,
            "required": self.required,
            "description": self.description,
            "sub_sections": [sub.to_dict() for sub in self.sub_sections],
        }
        return mapping.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "required": self.required,
            "description": self.description,
            "sub_sections": [sub.to_dict() for sub in self.sub_sections],
        }


@dataclass
class ReportTemplate:
    """Report template configuration"""
    # Meta information
    meta: Dict[str, Any] = field(default_factory=dict)

    # Report configuration
    report: Dict[str, Any] = field(default_factory=dict)

    # Style configuration
    styles: Dict[str, Any] = field(default_factory=dict)

    # Chart configuration
    charts: Dict[str, Any] = field(default_factory=dict)

    # Table configuration
    tables: Dict[str, Any] = field(default_factory=dict)

    # Section configuration
    sections: List[SectionConfig] = field(default_factory=list)

    # Data validation
    validation: Dict[str, Any] = field(default_factory=dict)

    # Output configuration
    output: Dict[str, Any] = field(default_factory=dict)


def _parse_sections(raw_sections: list) -> List[SectionConfig]:
    result = []
    for s in raw_sections:
        sub_sections = []
        for sub in s.get("sub_sections", []):
            points = []
            for pt in sub.get("points", []):
                if isinstance(pt, dict):
                    points.append(PointConfig(zh=pt.get("zh", ""), en=pt.get("en", "")))
                elif isinstance(pt, str):
                    points.append(PointConfig(zh=pt, en=pt))
            sub_sections.append(SubSectionConfig(
                id=sub.get("id", ""),
                name=sub.get("name", {}),
                description=sub.get("description", {}),
                points=points,
            ))
        result.append(SectionConfig(
            id=s.get("id", ""),
            name=s.get("name", {}),
            required=s.get("required", False),
            description=s.get("description", {}),
            sub_sections=sub_sections,
        ))
    return result


def load_template(template_name: str, template_dir: Optional[str] = None) -> ReportTemplate:
    """
    Load report template configuration

    Args:
        template_name: Template name (without .yaml extension)
        template_dir: Template directory, defaults to config/templates

    Returns:
        ReportTemplate instance
    """
    if yaml is None:
        raise ImportError("Please install PyYAML: pip install pyyaml")

    # Find template file
    if template_dir is None:
        template_dir = "config/templates"

    template_path = os.path.join(template_dir, f"{template_name}.yaml")

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file not found: {template_path}")

    # Load YAML
    with open(template_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}

    # Handle inheritance
    if 'extends' in config:
        base_template = load_template(config['extends'], template_dir)
        base_dict = {
            'meta': base_template.meta,
            'report': base_template.report,
            'styles': base_template.styles,
            'charts': base_template.charts,
            'tables': base_template.tables,
            'sections': [s.to_dict() for s in base_template.sections],
            'validation': base_template.validation,
            'output': base_template.output,
        }
        config = _merge_config(base_dict, config)

    # Create template object
    template = ReportTemplate(
        meta=config.get('meta', {}),
        report=config.get('report', {}),
        styles=config.get('styles', {}),
        charts=config.get('charts', {}),
        tables=config.get('tables', {}),
        sections=_parse_sections(config.get('sections', [])),
        validation=config.get('validation', {}),
        output=config.get('output', {}),
    )

    return template


def _merge_config(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge configuration (deep merge)"""
    result = base.copy()

    for key, value in override.items():
        if key == 'extends':
            continue

        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_config(result[key], value)
        else:
            result[key] = value

    return result


def list_templates(template_dir: Optional[str] = None) -> List[str]:
    """
    List all available templates

    Args:
        template_dir: Template directory

    Returns:
        List of template names
    """
    if template_dir is None:
        template_dir = "config/templates"

    if not os.path.exists(template_dir):
        return []

    templates = []
    for file in os.listdir(template_dir):
        if file.endswith('.yaml') or file.endswith('.yml'):
            templates.append(file.rsplit('.', 1)[0])

    return sorted(templates)


def get_chart_config(template: ReportTemplate, chart_id: str) -> Optional[Dict[str, Any]]:
    """
    Get chart configuration by ID

    Args:
        template: Report template
        chart_id: Chart ID

    Returns:
        Chart configuration dict
    """
    definitions = template.charts.get('definitions', [])
    for chart in definitions:
        if chart.get('id') == chart_id:
            return chart
    return None


def get_table_config(template: ReportTemplate, table_id: str) -> Optional[Dict[str, Any]]:
    """
    Get table configuration by ID

    Args:
        template: Report template
        table_id: Table ID

    Returns:
        Table configuration dict
    """
    definitions = template.tables.get('definitions', [])
    for table in definitions:
        if table.get('id') == table_id:
            return table
    return None


def get_charts_by_chapter(template: ReportTemplate, chapter: int) -> List[Dict[str, Any]]:
    """
    Get all charts for a specific chapter

    Args:
        template: Report template
        chapter: Chapter number

    Returns:
        List of chart configurations
    """
    definitions = template.charts.get('definitions', [])
    return [c for c in definitions if c.get('chapter') == chapter]


def get_tables_by_chapter(template: ReportTemplate, chapter: int) -> List[Dict[str, Any]]:
    """
    Get all tables for a specific chapter

    Args:
        template: Report template
        chapter: Chapter number

    Returns:
        List of table configurations
    """
    definitions = template.tables.get('definitions', [])
    return [t for t in definitions if t.get('chapter') == chapter]
