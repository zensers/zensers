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
    sections: Dict[str, Any] = field(default_factory=dict)

    # Data validation
    validation: Dict[str, Any] = field(default_factory=dict)

    # Output configuration
    output: Dict[str, Any] = field(default_factory=dict)


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
        # Merge configuration
        config = _merge_config(base_template.__dict__, config)

    # Create template object
    template = ReportTemplate(
        meta=config.get('meta', {}),
        report=config.get('report', {}),
        styles=config.get('styles', {}),
        charts=config.get('charts', {}),
        tables=config.get('tables', {}),
        sections=config.get('sections', {}),
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
