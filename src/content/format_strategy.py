from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

from src.services import chart_theme


class OutputFormat(Enum):
    DOCX = "docx"
    PPTX = "pptx"
    PDF = "pdf"
    HTML = "html"


@dataclass
class ChartStyleConfig:
    figsize: tuple = (5.0, 3.5)
    dpi: int = 200
    title_fontsize: int = 12
    label_fontsize: int = 10
    tick_fontsize: int = 9
    transparent_bg: bool = False
    theme_name: str = "default"
    annotation_fontsize: int = 7


@dataclass
class WritingDirective:
    content_style: str = "detailed"
    paragraph_max_chars: int = 0
    bullet_max_chars: int = 0
    require_chart_suggestion: bool = False
    require_data_annotation: bool = False
    section_structure: str = "hierarchical"
    data_presentation: str = "embedded"


@dataclass
class QualityStandard:
    max_paragraph_chars: int = 0
    min_chart_count_per_section: int = 0
    max_slide_text_chars: int = 0
    require_visual_balance: bool = False
    check_items: List[str] = field(default_factory=list)


@dataclass
class LayoutPreference:
    slide_layouts: List[str] = field(default_factory=lambda: ["bullet_points"])
    prefer_split_layout: bool = False
    chart_position: str = "embedded"
    table_style: str = "full"


class FormatStrategy(ABC):

    @property
    @abstractmethod
    def format_name(self) -> str:
        pass

    @abstractmethod
    def get_writing_directive(self, section_type: str = "body") -> WritingDirective:
        pass

    @abstractmethod
    def get_chart_style(self) -> ChartStyleConfig:
        pass

    @abstractmethod
    def get_quality_standard(self) -> QualityStandard:
        pass

    @abstractmethod
    def get_layout_preference(self) -> LayoutPreference:
        pass


class DOCXStrategy(FormatStrategy):

    @property
    def format_name(self) -> str:
        return "docx"

    def get_writing_directive(self, section_type: str = "body") -> WritingDirective:
        return WritingDirective(
            content_style="detailed",
            paragraph_max_chars=0,
            require_chart_suggestion=False,
            require_data_annotation=True,
            section_structure="hierarchical",
            data_presentation="embedded",
        )

    def get_chart_style(self) -> ChartStyleConfig:
        # 消费 chart_theme 设计令牌，与全局图表标准（DPI=200）保持单一配置源
        return ChartStyleConfig(
            figsize=chart_theme.FIGSIZE_WIDE,
            dpi=chart_theme.DPI,
            title_fontsize=int(chart_theme.TITLE),
            label_fontsize=int(chart_theme.AXIS),
            tick_fontsize=int(chart_theme.AXIS),
            transparent_bg=False,
            theme_name="report_chart_theme",
        )

    def get_quality_standard(self) -> QualityStandard:
        return QualityStandard(
            check_items=[
                "paragraph_completeness",
                "argument_logic",
                "data_citation_accuracy",
                "heading_hierarchy",
                "cross_section_consistency",
            ],
        )

    def get_layout_preference(self) -> LayoutPreference:
        return LayoutPreference(
            slide_layouts=["bullet_points"],
            chart_position="embedded",
            table_style="full",
        )


class PPTXStrategy(FormatStrategy):

    @property
    def format_name(self) -> str:
        return "pptx"

    def get_writing_directive(self, section_type: str = "body") -> WritingDirective:
        return WritingDirective(
            content_style="bullet_points",
            paragraph_max_chars=0,
            bullet_max_chars=25,
            require_chart_suggestion=True,
            require_data_annotation=True,
            section_structure="slide_based",
            data_presentation="visual",
        )

    def get_chart_style(self) -> ChartStyleConfig:
        return ChartStyleConfig(
            figsize=(7.5, 4.5),
            dpi=200,
            title_fontsize=16,
            label_fontsize=14,
            tick_fontsize=12,
            transparent_bg=True,
            theme_name="ppt_navy_gold",
        )

    def get_quality_standard(self) -> QualityStandard:
        return QualityStandard(
            max_slide_text_chars=300,
            min_chart_count_per_section=1,
            require_visual_balance=True,
            check_items=[
                "bullet_conciseness",
                "chart_coverage",
                "visual_density",
                "slide_focus",
                "data_label_readability",
            ],
        )

    def get_layout_preference(self) -> LayoutPreference:
        return LayoutPreference(
            slide_layouts=["chart_full", "chart_split", "bullet_points", "kpi_highlight", "data_table"],
            prefer_split_layout=True,
            chart_position="right",
            table_style="compact",
        )


class PDFStrategy(FormatStrategy):

    @property
    def format_name(self) -> str:
        return "pdf"

    def get_writing_directive(self, section_type: str = "body") -> WritingDirective:
        return WritingDirective(
            content_style="detailed",
            paragraph_max_chars=0,
            require_chart_suggestion=False,
            require_data_annotation=True,
            section_structure="hierarchical",
            data_presentation="embedded",
        )

    def get_chart_style(self) -> ChartStyleConfig:
        return ChartStyleConfig(
            figsize=(5.0, 3.5),
            dpi=200,
            title_fontsize=12,
            label_fontsize=10,
            tick_fontsize=9,
            transparent_bg=False,
            theme_name="print_optimized",
        )

    def get_quality_standard(self) -> QualityStandard:
        return QualityStandard(
            check_items=[
                "paragraph_completeness",
                "argument_logic",
                "data_citation_accuracy",
                "print_readability",
                "page_break_quality",
            ],
        )

    def get_layout_preference(self) -> LayoutPreference:
        return LayoutPreference(
            chart_position="embedded",
            table_style="full",
        )


STRATEGY_REGISTRY: Dict[str, FormatStrategy] = {
    "docx": DOCXStrategy(),
    "pptx": PPTXStrategy(),
    "pdf": PDFStrategy(),
}


def get_format_strategy(output_format: str) -> FormatStrategy:
    if output_format not in STRATEGY_REGISTRY:
        output_format = "docx"
    return STRATEGY_REGISTRY[output_format]
