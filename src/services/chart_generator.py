# -*- coding: utf-8 -*-
"""
Chart Generation Service
========================

Generates professional data charts based on matplotlib, supporting multiple chart types.

Supported chart types:
1. bar - Bar chart
2. hbar - Horizontal bar chart
3. bar_line - Bar + Line combination chart
4. pie - Pie chart
5. line - Line chart
6. radar - Radar chart
7. scatter - Scatter plot
8. bubble - Bubble chart
9. waterfall - Waterfall chart
10. quadrant - Quadrant chart

Design doc: docs/KNOWLEDGE_BASE/02_ARCHITECTURE/ORCHESTRATOR_REDESIGN.md
"""

import logging
import math
import tempfile
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)

# Set Chinese fonts
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'SimSun', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class ChartType(Enum):
    """Chart type"""
    BAR = "bar"
    HBAR = "hbar"
    BAR_LINE = "bar_line"
    PIE = "pie"
    LINE = "line"
    RADAR = "radar"
    SCATTER = "scatter"
    BUBBLE = "bubble"
    WATERFALL = "waterfall"
    QUADRANT = "quadrant"


def _json_safe_chart_data(data: Any, max_points: int = 60) -> Any:
    """Return a JSON-safe copy of chart data, capped for sidecar size."""
    import json as _json

    if isinstance(data, dict):
        return {str(k): _json_safe_chart_data(v, max_points) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        capped = list(data[:max_points]) if len(data) > max_points else list(data)
        return [_json_safe_chart_data(v, max_points) for v in capped]
    if isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            raise ValueError("chart sidecar data must be finite (got NaN/inf)")
        return data
    _json.dumps(data, ensure_ascii=False, allow_nan=False)
    return data


class ChartSidecar:
    """File-backed sidecar store for auditable chart records.

    Main ``research_result.json`` keeps only light references
    (path/title/anchor); full ``ChartSpec`` records live here so review
    reads one small file and can re-render via ``from_record``.
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self._records: Dict[str, Dict[str, Any]] = {}
        if self.path.is_file():
            import json as _json

            raw = _json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw.get("charts", []):
                chart_id = str(item.get("chart_id", ""))
                if chart_id:
                    self._records[chart_id] = item

    def append(self, section: str, spec: "ChartSpec", path: str) -> Dict[str, str]:
        """Persist a spec record; returns the light reference for main JSON."""
        chart_id = f"{section}_{len(self._records) + 1}_{uuid.uuid4().hex[:8]}"
        self._records[chart_id] = {
            "chart_id": chart_id,
            "section": section,
            **spec.to_record(),
            "path": path,
        }
        self.save()
        return {"chart_id": chart_id, "path": path, "title": spec.title}

    def get(self, chart_id: str) -> Optional["ChartSpec"]:
        """Load a spec back for re-render or audit."""
        item = self._records.get(chart_id)
        if not item:
            return None
        from_record = ChartSpec.from_record
        return from_record(item)

    def save(self) -> None:
        """Write all records to disk."""
        import json as _json

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            _json.dumps({"charts": list(self._records.values())}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )


@dataclass
class ChartConfig:
    """Chart configuration"""
    chart_type: ChartType
    title: str
    data: Dict[str, Any]
    xlabel: str = ""
    ylabel: str = ""
    caption: str = ""
    source: str = "Public data compilation"
    subtitle: str = ""
    unit: str = ""
    data_ref: str = ""
    width: int = 9
    height: int = 5.5
    dpi: int = 150


@dataclass(frozen=True)
class ChartSpec:
    """Canonical, auditable chart contract used before rendering.

    ``ChartConfig`` remains the renderer-facing compatibility shape.  New
    production callers should construct ``ChartSpec`` so the analytical
    question, grain, denominator, and provenance travel with the data.
    """
    chart_type: ChartType
    title: str
    data: Dict[str, Any]
    question: str
    takeaway: str = ""
    subtitle: str = ""
    unit: str = ""
    denominator: str = ""
    data_grain: str = ""
    time_range: str = ""
    source: str = "Public data compilation"
    data_ref: str = ""
    xlabel: str = ""
    ylabel: str = ""
    caption: str = ""

    def to_config(self) -> ChartConfig:
        """Convert the audited contract to the legacy renderer config."""
        subtitle_parts = [part for part in (self.subtitle, self.takeaway) if part]
        context_parts = [part for part in (self.denominator, self.data_grain, self.time_range) if part]
        return ChartConfig(
            chart_type=self.chart_type,
            title=self.title,
            data=self.data,
            xlabel=self.xlabel,
            ylabel=self.ylabel,
            caption=self.caption,
            source=self.source,
            subtitle=" · ".join(subtitle_parts + context_parts),
            unit=self.unit,
            data_ref=self.data_ref,
        )

    def to_record(self, max_points: int = 60) -> Dict[str, Any]:
        """Serialize the audited contract to a JSON-safe sidecar record."""
        data = _json_safe_chart_data(self.data, max_points=max_points)
        return {
            "chart_type": self.chart_type.value,
            "title": self.title,
            "data": data,
            "question": self.question,
            "takeaway": self.takeaway,
            "subtitle": self.subtitle,
            "unit": self.unit,
            "denominator": self.denominator,
            "data_grain": self.data_grain,
            "time_range": self.time_range,
            "source": self.source,
            "data_ref": self.data_ref,
            "xlabel": self.xlabel,
            "ylabel": self.ylabel,
            "caption": self.caption,
        }

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "ChartSpec":
        """Rebuild the audited contract from a sidecar record."""
        try:
            chart_type = ChartType(record.get("chart_type", "bar"))
        except ValueError:
            chart_type = ChartType.BAR
        return cls(
            chart_type=chart_type,
            title=str(record.get("title", "")),
            data=dict(record.get("data", {})),
            question=str(record.get("question", "")),
            takeaway=str(record.get("takeaway", "")),
            subtitle=str(record.get("subtitle", "")),
            unit=str(record.get("unit", "")),
            denominator=str(record.get("denominator", "")),
            data_grain=str(record.get("data_grain", "")),
            time_range=str(record.get("time_range", "")),
            source=str(record.get("source", "Public data compilation")),
            data_ref=str(record.get("data_ref", "")),
            xlabel=str(record.get("xlabel", "")),
            ylabel=str(record.get("ylabel", "")),
            caption=str(record.get("caption", "")),
        )


@dataclass
class ChartResult:
    """Chart generation result"""
    success: bool
    image_path: Optional[str] = None
    error: Optional[str] = None


class ChartGenerator:
    """
    Chart Generator
    
    Generates professional format data charts, supporting multiple types.
    
    Usage example:
        generator = ChartGenerator()
        
        # Generate market share bar chart
        result = generator.generate(ChartConfig(
            chart_type=ChartType.BAR,
            title="Global Power Battery Market Share (2023)",
            data={
                "categories": ["CATL", "BYD", "LG Energy", "Panasonic", "SK On"],
                "values": [37.4, 15.7, 13.6, 7.3, 5.4]
            },
            ylabel="Market Share (%)"
        ))
    """
    
    # Professional 12-color palette
    COLORS = {
        'navy_blue': (26, 39, 68),
        'gold': (201, 162, 39),
        'charcoal': (51, 51, 51),
        'success': (39, 174, 96),
        'warning': (230, 126, 34),
        'light_gold': (255, 248, 220),
        'white': (255, 255, 255),
        'slate': (71, 95, 125),
        'teal': (38, 166, 154),
        'coral': (239, 131, 107),
        'plum': (142, 85, 142),
        'sand': (203, 174, 127),
    }
    
    # Extended color palette (12 colors, RGB tuples for matplotlib)
    PALETTE_12 = [
        (26/255, 39/255, 68/255),     # navy_blue
        (201/255, 162/255, 39/255),   # gold
        (71/255, 95/255, 125/255),    # slate
        (38/255, 166/255, 154/255),   # teal
        (239/255, 131/255, 107/255),  # coral
        (142/255, 85/255, 142/255),   # plum
        (203/255, 174/255, 127/255),  # sand
        (74/255, 144/255, 217/255),   # steel blue
        (126/255, 181/255, 166/255),  # sage
        (232/255, 168/255, 124/255),  # peach
        (212/255, 165/255, 116/255),  # tan
        (107/255, 142/255, 158/255),  # steel teal
    ]
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize chart generator
        
        Args:
            output_dir: Chart output directory, defaults to temp directory
        """
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp())
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # RGB color conversion
        self._navy = self._rgb(*self.COLORS['navy_blue'])
        self._gold = self._rgb(*self.COLORS['gold'])
        self._char = self._rgb(*self.COLORS['charcoal'])
        self._chart_counter = 0
        self._generator_id = uuid.uuid4().hex[:10]
    
    def _rgb(self, r: int, g: int, b: int) -> Tuple[float, float, float]:
        """Convert RGB to matplotlib format"""
        return (r/255, g/255, b/255)
    
    def generate(self, config: ChartConfig | ChartSpec) -> ChartResult:
        """
        Generate chart
        
        Args:
            config: Chart configuration
            
        Returns:
            ChartResult generation result
        """
        try:
            if isinstance(config, ChartSpec):
                if not config.question.strip():
                    return ChartResult(success=False, error="chart question is required")
                config = config.to_config()
            validation_error = self._validate_config(config)
            if validation_error:
                return ChartResult(success=False, error=validation_error)

            # Select generation method based on type
            handlers = {
                ChartType.BAR: self._generate_bar,
                ChartType.HBAR: self._generate_hbar,
                ChartType.BAR_LINE: self._generate_bar_line,
                ChartType.PIE: self._generate_pie,
                ChartType.LINE: self._generate_line,
                ChartType.RADAR: self._generate_radar,
                ChartType.SCATTER: self._generate_scatter,
                ChartType.BUBBLE: self._generate_bubble,
                ChartType.WATERFALL: self._generate_waterfall,
                ChartType.QUADRANT: self._generate_quadrant,
            }
            
            handler = handlers.get(config.chart_type)
            if not handler:
                return ChartResult(
                    success=False,
                    error=f"Unsupported chart type: {config.chart_type}"
                )
            
            # Generate chart
            image_path = handler(config)
            
            return ChartResult(
                success=True,
                image_path=image_path
            )
        except Exception as e:
            logger.error(f"Chart generation failed: {e}", exc_info=True)
            return ChartResult(
                success=False,
                error=str(e)
            )

    @staticmethod
    def _is_finite_number(value: Any, allow_none: bool = False) -> bool:
        """Return whether a chart value is a finite real number."""
        if value is None:
            return allow_none
        if isinstance(value, bool):
            return False
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError, OverflowError):
            return False

    @classmethod
    def _validate_numeric_sequence(
        cls, values: Any, field: str, allow_none: bool = False
    ) -> Optional[str]:
        if not isinstance(values, (list, tuple, np.ndarray)):
            return f"{field} must be a sequence"
        for index, value in enumerate(values):
            if not cls._is_finite_number(value, allow_none=allow_none):
                return f"{field}[{index}] must be a finite number"
        return None

    @classmethod
    def _validate_config(cls, config: ChartConfig) -> Optional[str]:
        """Validate chart data before any renderer is allowed to run.

        A chart file is not evidence of a valid chart.  This boundary rejects
        malformed or mixed-grain payloads instead of silently truncating them
        inside individual renderers.
        """
        if not isinstance(config, ChartConfig):
            return "config must be a ChartConfig"
        if not isinstance(config.title, str) or not config.title.strip():
            return "chart title is required"
        if not isinstance(config.data, dict):
            return "chart data must be a mapping"

        data = config.data
        chart_type = config.chart_type

        def require_equal_lengths(*named_values: Tuple[str, Any]) -> Optional[str]:
            lengths = {name: len(value) for name, value in named_values}
            if len(set(lengths.values())) != 1:
                return "chart series lengths must match: " + ", ".join(
                    f"{name}={length}" for name, length in lengths.items()
                )
            return None

        if chart_type in (ChartType.BAR, ChartType.HBAR):
            categories = data.get("labels", data.get("categories"))
            if not isinstance(categories, (list, tuple)) or not categories:
                return "bar chart requires non-empty categories"
            values = data.get("values")
            if values is not None:
                error = require_equal_lengths(("categories", categories), ("values", values))
                if error:
                    return error
                return cls._validate_numeric_sequence(values, "values")
            series = data.get("series")
            if not isinstance(series, list) or not series:
                return "bar chart requires values or a non-empty series list"
            for index, item in enumerate(series):
                if not isinstance(item, dict):
                    return f"series[{index}] must be a mapping"
                error = require_equal_lengths(
                    ("categories", categories), (f"series[{index}].values", item.get("values", []))
                )
                if error:
                    return error
                error = cls._validate_numeric_sequence(item.get("values", []), f"series[{index}].values", allow_none=True)
                if error:
                    return error
            return None

        if chart_type == ChartType.BAR_LINE:
            years = data.get("years")
            bars = data.get("bar")
            lines = data.get("line")
            if not isinstance(years, (list, tuple)) or not years:
                return "bar_line chart requires non-empty years"
            if not isinstance(bars, (list, tuple)) or not isinstance(lines, (list, tuple)):
                return "bar_line chart requires bar and line sequences"
            error = require_equal_lengths(("years", years), ("bar", bars), ("line", lines))
            if error:
                return error
            error = cls._validate_numeric_sequence(bars, "bar")
            return error or cls._validate_numeric_sequence(lines, "line", allow_none=True)

        if chart_type == ChartType.LINE:
            years = data.get("years", data.get("x"))
            scenarios = data.get("scenarios")
            if scenarios is None and "y" in data:
                scenarios = {data.get("series_name", "Series 1"): data.get("y")}
            if not isinstance(years, (list, tuple)) or not years:
                return "line chart requires non-empty x/years"
            if not isinstance(scenarios, dict) or not scenarios:
                return "line chart requires at least one named series"
            for label, values in scenarios.items():
                if not isinstance(label, str) or not label.strip():
                    return "line series names must be non-empty strings"
                error = require_equal_lengths(("years", years), (f"series[{label}].values", values))
                if error:
                    return error
                error = cls._validate_numeric_sequence(values, f"series[{label}].values", allow_none=True)
                if error:
                    return error
            return None

        if chart_type == ChartType.PIE:
            labels = data.get("labels", data.get("categories"))
            values = data.get("values")
            if not isinstance(labels, (list, tuple)) or not labels:
                return "pie chart requires non-empty labels"
            if not isinstance(values, (list, tuple)):
                return "pie chart requires values"
            error = require_equal_lengths(("labels", labels), ("values", values))
            if error:
                return error
            error = cls._validate_numeric_sequence(values, "values")
            if error:
                return error
            if any(float(value) < 0 for value in values) or sum(float(value) for value in values) <= 0:
                return "pie chart values must be non-negative and have a positive total"
            return None

        if chart_type == ChartType.SCATTER:
            x_values = data.get("x")
            y_values = data.get("y")
            if not isinstance(x_values, (list, tuple)) or not isinstance(y_values, (list, tuple)):
                return "scatter chart requires x and y sequences"
            error = require_equal_lengths(("x", x_values), ("y", y_values))
            if error:
                return error
            error = cls._validate_numeric_sequence(x_values, "x")
            if error:
                return error
            error = cls._validate_numeric_sequence(y_values, "y")
            if error:
                return error
            labels = data.get("labels", [])
            if labels and len(labels) != len(x_values):
                return "scatter labels length must match x and y"
            return None

        if chart_type == ChartType.BUBBLE:
            sectors = data.get("sectors")
            if not isinstance(sectors, list) or not sectors:
                return "bubble chart requires a non-empty sectors list"
            for index, item in enumerate(sectors):
                if not isinstance(item, dict):
                    return f"sectors[{index}] must be a mapping"
                for key in ("x", "y"):
                    if not cls._is_finite_number(item.get(key)):
                        return f"sectors[{index}].{key} must be a finite number"
                if not cls._is_finite_number(item.get("size", 10)) or float(item.get("size", 10)) < 0:
                    return f"sectors[{index}].size must be a non-negative number"
            return None

        if chart_type == ChartType.WATERFALL:
            factors = data.get("factors")
            if not isinstance(factors, list) or not factors:
                return "waterfall chart requires a non-empty factors list"
            for index, item in enumerate(factors):
                if not isinstance(item, dict) or not str(item.get("label", "")).strip():
                    return f"factors[{index}] requires a label"
                if not cls._is_finite_number(item.get("value")):
                    return f"factors[{index}].value must be a finite number"
            return None

        if chart_type == ChartType.QUADRANT:
            players = data.get("players")
            if not isinstance(players, list):
                return "quadrant chart requires a players list"
            for index, item in enumerate(players):
                if not isinstance(item, dict) or not str(item.get("name", "")).strip():
                    return f"players[{index}] requires a name"
                for key in ("x", "y"):
                    if not cls._is_finite_number(item.get(key)):
                        return f"players[{index}].{key} must be a finite number"
            return None

        if chart_type == ChartType.RADAR:
            categories = data.get("categories")
            if not isinstance(categories, (list, tuple)) or not categories:
                return "radar chart requires non-empty categories"
            scenarios = data.get("scenarios")
            if scenarios is not None:
                if not isinstance(scenarios, dict) or not scenarios:
                    return "radar scenarios must be a non-empty mapping"
                for label, values in scenarios.items():
                    error = require_equal_lengths(("categories", categories), (f"series[{label}].values", values))
                    if error:
                        return error
                    error = cls._validate_numeric_sequence(values, f"series[{label}].values")
                    if error:
                        return error
            else:
                values = data.get("values")
                error = require_equal_lengths(("categories", categories), ("values", values)) if isinstance(values, (list, tuple)) else "radar chart requires values or scenarios"
                if error:
                    return error
                return cls._validate_numeric_sequence(values, "values")
            return None

        return f"unsupported chart type: {chart_type}"

    def _create_figure(self, config: ChartConfig) -> Tuple[plt.Figure, plt.Axes]:
        """Create figure"""
        fig, ax = plt.subplots(figsize=(config.width, config.height))
        fig.patch.set_facecolor('white')
        ax.set_facecolor('#FAFAFA')
        return fig, ax

    def _set_title(self, ax: plt.Axes, config: ChartConfig, pad: int = 12) -> None:
        """Apply a consistent title and optional evidence subtitle."""
        subtitle_parts = [part for part in (config.subtitle, config.unit) if part]
        if subtitle_parts:
            pad = max(pad, 28)
        ax.set_title(config.title, fontsize=12, fontweight='bold', pad=pad, color=self._char)
        if subtitle_parts:
            ax.text(
                0.0,
                1.02,
                " · ".join(subtitle_parts),
                transform=ax.transAxes,
                ha="left",
                va="bottom",
                fontsize=8,
                color="#666666",
            )
    
    def _add_annotations(self, fig: plt.Figure, config: ChartConfig) -> None:
        """Add caption and source text below the chart"""
        if config.caption or config.source:
            text_parts = []
            if config.caption:
                text_parts.append(config.caption)
            if config.source:
                text_parts.append(f"来源：{config.source}")
            try:
                fig.subplots_adjust(bottom=max(fig.subplotpars.bottom, 0.20))
            except Exception:
                pass
            fig.text(0.5, 0.02, " | ".join(text_parts),
                    ha='center', fontsize=7, color='#888888', style='italic',
                    wrap=True)
    
    def _save_figure(self, fig: plt.Figure, name: str, config: ChartConfig = None) -> str:
        """Save figure with unique filename"""
        if config:
            self._add_annotations(fig, config)
        self._chart_counter += 1
        image_path = str(
            self.output_dir /
            f"{name}_{self._generator_id}_{self._chart_counter}.png"
        )
        dpi = config.dpi if config else 150
        fig.savefig(image_path, dpi=dpi, bbox_inches='tight', pad_inches=0.25,
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        self._validate_rendered_image(image_path)
        return image_path

    @staticmethod
    def _validate_rendered_image(image_path: str) -> None:
        """Reject corrupt or empty render artifacts at the renderer boundary."""
        path = Path(image_path)
        if not path.is_file() or path.stat().st_size < 1024:
            raise ValueError(f"rendered chart artifact is missing or empty: {image_path}")
        try:
            from PIL import Image

            with Image.open(path) as image:
                if image.width < 320 or image.height < 180:
                    raise ValueError(f"rendered chart is too small: {image.width}x{image.height}")
                image.verify()
        except ImportError:
            logger.debug("Pillow unavailable; skipped image integrity verification")

    @staticmethod
    def _scale_padding(values: List[float], minimum: float = 1.0) -> float:
        """Return a scale-relative padding instead of a fixed data-unit offset."""
        magnitude = max((abs(float(value)) for value in values), default=0.0)
        return max(magnitude * 0.08, minimum)

    @staticmethod
    def _set_numeric_limits(axis, values: List[float], horizontal: bool = False) -> None:
        """Keep absolute bar comparisons honest while supporting signed values."""
        numeric = [float(value) for value in values if value is not None]
        if not numeric:
            return
        padding = ChartGenerator._scale_padding(numeric)
        lower = min(0.0, min(numeric))
        upper = max(0.0, max(numeric))
        if horizontal:
            axis.set_xlim(lower - padding if lower < 0 else 0, upper + padding)
        else:
            axis.set_ylim(lower - padding if lower < 0 else 0, upper + padding)
    
    def _generate_bar(self, config: ChartConfig) -> str:
        """Generate bar chart (single series or grouped)"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        categories = data.get('categories', [])
        
        if 'series' in data:
            # Grouped bar chart
            series_list = data['series']
            n_series = len(series_list)
            x = np.arange(len(categories))
            width = 0.6 / n_series
            
            for i, s in enumerate(series_list):
                s_values = s.get('values', [])
                safe_values = [v if v is not None else np.nan for v in s_values]
                offset = (i - n_series / 2 + 0.5) * width
                color = self.PALETTE_12[i % len(self.PALETTE_12)]
                bars = ax.bar(x + offset, safe_values, width, color=color,
                             alpha=0.85, zorder=3, label=s.get('name', f'Series {i+1}'))
                
                unit = s.get('unit', data.get('unit', ''))
                for bar, val in zip(bars, s_values):
                    if val is None:
                        continue
                    if unit == '%':
                        label = f'{val}%'
                    elif abs(val) >= 10000:
                        label = f'{val/10000:.1f}万'
                    elif abs(val) >= 1:
                        label = f'{val:.1f}'
                    else:
                        label = f'{val:.2f}'
                    offset = self._scale_padding([v for v in s_values if v is not None], minimum=0.01)
                    label_y = bar.get_height() + (offset if val >= 0 else -offset)
                    ax.text(bar.get_x() + bar.get_width()/2, label_y,
                           label, ha='center', va='bottom' if val >= 0 else 'top', fontsize=7, color=self._char)
            
            ax.set_xticks(x)
            ax.legend(fontsize=8, loc='best')
        else:
            # Single series bar chart
            values = data.get('values', [])
            x = np.arange(len(categories))
            
            bars = ax.bar(x, values, color=self._navy, alpha=0.85, zorder=3, width=0.6)
            
            unit = data.get('unit', '')
            pct_values = data.get('show_percent', False)
            for bar, val in zip(bars, values):
                if pct_values or unit == '%':
                    label = f'{val}%'
                elif abs(val) >= 10000:
                    label = f'{val/10000:.1f}万'
                elif abs(val) >= 1:
                    label = f'{val:.1f}'
                else:
                    label = f'{val:.2f}'
                offset = self._scale_padding(values, minimum=0.01)
                ax.text(bar.get_x() + bar.get_width()/2,
                       bar.get_height() + (offset if val >= 0 else -offset),
                       label, ha='center', va='bottom' if val >= 0 else 'top', fontsize=9, color=self._char)

            self._set_numeric_limits(ax, values)
        
        ax.set_xticks(x)
        rotation = 30 if any(len(str(category)) > 8 for category in categories) else 0
        ax.set_xticklabels(categories, fontsize=9, rotation=rotation,
                           ha='right' if rotation else 'center')
        ax.set_ylabel(config.ylabel, fontsize=10)
        self._set_title(ax, config)
        ax.spines['top'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.4, zorder=0)
        
        return self._save_figure(fig, f"bar_{hash(config.title) % 10000}", config)
    
    def _generate_hbar(self, config: ChartConfig) -> str:
        """Generate horizontal bar chart"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        labels = data.get('labels', data.get('categories', []))
        values = data.get('values', [])
        
        y = np.arange(len(labels))
        colors = [self._navy] * len(labels)
        
        bars = ax.barh(y, values, color=colors, alpha=0.85, zorder=3)
        
        unit = data.get('unit', '')
        pct_values = data.get('show_percent', False)
        for bar, val in zip(bars, values):
            if pct_values or unit == '%':
                label = f'{val}%'
            elif abs(val) >= 10000:
                label = f'{val/10000:.1f}万'
            elif abs(val) >= 1:
                label = f'{val:.1f}'
            else:
                label = f'{val:.2f}'
            offset = self._scale_padding(values, minimum=0.01)
            x_pos = bar.get_width() + offset if val >= 0 else bar.get_width() - offset
            ha = 'left' if val >= 0 else 'right'
            ax.text(x_pos, bar.get_y() + bar.get_height()/2,
                   label, va='center', ha=ha, fontsize=9, color=self._char)
        
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=10)
        ax.set_xlabel(config.xlabel or config.ylabel, fontsize=10)
        self._set_title(ax, config)
        ax.spines['top'].set_visible(False)
        ax.grid(axis='x', linestyle='--', alpha=0.4, zorder=0)
        self._set_numeric_limits(ax, values, horizontal=True)
        ax.invert_yaxis()
        
        return self._save_figure(fig, f"hbar_{hash(config.title) % 10000}", config)
    
    def _generate_bar_line(self, config: ChartConfig) -> str:
        fig, ax = self._create_figure(config)

        data = config.data
        years = data.get('years', [])
        bar_values = data.get('bar', [])
        line_values = data.get('line', [])
        bar_label = data.get('bar_label', '')
        line_label = data.get('line_label', '')

        if not years or not bar_values or not line_values:
            raise ValueError("bar_line chart requires years, bar and line data")
        x = np.arange(len(years))
        w = 0.5

        bars = ax.bar(x, bar_values, w, color=self._navy, alpha=0.85, zorder=3, label=bar_label)

        bar_unit = data.get('bar_unit', '')
        for bar, val in zip(bars, bar_values):
            if bar_unit == '%':
                lbl = f'{val}%'
            elif abs(val) >= 10000:
                lbl = f'{val/10000:.1f}万'
            elif abs(val) >= 1:
                lbl = f'{val:.1f}'
            else:
                lbl = f'{val:.2f}'
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                   lbl, ha='center', va='bottom', fontsize=8, color=self._char)

        ax2 = ax.twinx()
        clean_line = [v if v is not None else np.nan for v in line_values]
        ax2.plot(x, clean_line, 'o-', color=self._gold, linewidth=2.5,
                markersize=7, label=line_label, zorder=4)

        for i, val in enumerate(line_values):
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                label = f'{val}%' if data.get('line_unit') == '%' else f'{val:.1f}'
                ax2.annotate(label, (x[i], val), textcoords="offset points",
                            xytext=(0, 10), ha='center', fontsize=8, color=self._gold)

        ax2.set_ylabel(line_label, color=self._gold, fontsize=10)
        ax2.tick_params(axis='y', labelcolor=self._gold)

        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc='upper left')

        ax.set_xticks(x)
        ax.set_xticklabels(years, fontsize=9)
        ax.set_ylabel(config.ylabel or bar_label, fontsize=10)
        self._set_title(ax, config)
        ax.spines['top'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.4, zorder=0)

        return self._save_figure(fig, f"barline_{hash(config.title) % 10000}", config)
    
    def _generate_pie(self, config: ChartConfig) -> str:
        """Generate pie chart, auto-downgrade to bar if >6 items"""
        data = config.data
        labels = data.get('labels', data.get('categories', []))
        values = data.get('values', [])
        
        # P1: Auto-downgrade to bar chart if > 6 items
        if len(values) > 6:
            bar_config = ChartConfig(
                chart_type=ChartType.BAR,
                title=config.title,
                data=config.data,
                xlabel=config.xlabel,
                ylabel=config.ylabel,
                caption=config.caption,
                source=config.source,
                width=config.width,
                height=config.height,
                dpi=config.dpi,
            )
            return self._generate_bar(bar_config)
        
        fig, ax = plt.subplots(figsize=(8, 8))
        fig.patch.set_facecolor('white')
        
        explode = data.get('explode', [0.02] * len(values))
        colors = self.PALETTE_12[:len(values)]
        
        wedges, texts, autotexts = ax.pie(
            values, labels=labels, autopct='%1.1f%%',
            colors=colors,
            explode=explode[:len(values)],
            shadow=False, startangle=90
        )
        
        for i, autotext in enumerate(autotexts):
            col = colors[i] if i < len(colors) else colors[0]
            try:
                rgb = plt.matplotlib.colors.to_rgb(col)
                luminance = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
                autotext.set_color('white' if luminance < 0.55 else '#333333')
            except Exception:
                autotext.set_color('white')
            autotext.set_fontsize(9)
            autotext.set_fontweight('bold')
        
        self._set_title(ax, config)
        
        return self._save_figure(fig, f"pie_{hash(config.title) % 10000}", config)
    
    def _generate_line(self, config: ChartConfig) -> str:
        """Generate line chart"""
        fig, ax = self._create_figure(config)

        data = config.data
        # Accept both the planner format (years/scenarios) and the generic
        # x/y format used by callers and ChartConfig examples.
        years = data.get('years', data.get('x', []))
        scenarios = data.get('scenarios')
        if scenarios is None and 'y' in data:
            scenarios = {data.get('series_name', 'Series 1'): data.get('y', [])}
        scenarios = scenarios or {}

        if not years or not scenarios:
            plt.close(fig)
            raise ValueError("line chart requires x/years and at least one series")

        x = np.arange(len(years))
        line_colors = [self._navy, self._gold, '#7EB5A6', '#E8836B', '#8E558E', '#CBAE7F', '#4A90D9', '#5B8DB8']
        line_styles = ['-', '--', '-.', ':']

        plotted = 0
        for i, (label, vals) in enumerate(scenarios.items()):
            col = line_colors[i % len(line_colors)]
            ls = line_styles[i % len(line_styles)]
            ax.plot(x, vals, marker='o', linewidth=2, color=col,
                   linestyle=ls, label=label, zorder=3)
            plotted += 1

        if not plotted:
            plt.close(fig)
            raise ValueError("line chart has no non-empty series")
        
        ax.set_xticks(x)
        ax.set_xticklabels(years, fontsize=9)
        ax.set_ylabel(config.ylabel, fontsize=10)
        self._set_title(ax, config)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(handles, labels, fontsize=9, loc='upper left')
        ax.spines['top'].set_visible(False)
        ax.grid(linestyle='--', alpha=0.4, zorder=0)
        
        return self._save_figure(fig, f"line_{hash(config.title) % 10000}", config)
    
    def _generate_radar(self, config: ChartConfig) -> str:
        data = config.data
        categories = data.get('categories', [])

        N = len(categories)
        angles = [n / float(N) * 2 * np.pi for n in range(N)]
        angles_closed = angles + angles[:1]

        fig = plt.figure(figsize=(8, 8))
        ax = plt.subplot(111, polar=True)
        fig.patch.set_facecolor('white')

        radar_colors = [self._navy, self._gold, '#7EB5A6', '#E8836B', '#8E558E']
        radar_fills = [0.25, 0.15, 0.15, 0.15, 0.15]

        if "scenarios" in data:
            scenarios = data.get("scenarios", {})
            for i, (label, vals) in enumerate(scenarios.items()):
                closed_vals = vals + vals[:1]
                color = radar_colors[i % len(radar_colors)]
                fill_alpha = radar_fills[min(i, len(radar_fills)-1)]
                ax.plot(angles_closed, closed_vals, 'o-', linewidth=2,
                       color=color, alpha=0.8, label=label)
                ax.fill(angles_closed, closed_vals, alpha=fill_alpha, color=color)
            ax.legend(fontsize=9, loc='upper right', bbox_to_anchor=(1.3, 1.1))
        else:
            values = data.get('values', [])
            closed_vals = values + values[:1]
            ax.plot(angles_closed, closed_vals, 'o-', linewidth=2, color=self._navy, alpha=0.8)
            ax.fill(angles_closed, closed_vals, alpha=0.25, color=self._navy)

        ax.set_thetagrids(np.degrees(angles), categories, fontsize=9)
        all_vals = []
        if "scenarios" in data:
            for vals in data["scenarios"].values():
                all_vals.extend([v for v in vals if isinstance(v, (int, float))])
        else:
            all_vals = data.get('values', [])
        max_val = max(all_vals) if all_vals else 100
        ax.set_ylim(0, max(max_val * 1.1, 100))
        self._set_title(ax, config, pad=20)

        plt.tight_layout()
        return self._save_figure(fig, f"radar_{hash(config.title) % 10000}", config)
    
    def _generate_scatter(self, config: ChartConfig) -> str:
        """Generate scatter plot"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        x_values = data.get('x', [])
        y_values = data.get('y', [])
        labels = data.get('labels', [])
        
        ax.scatter(x_values, y_values, color=self._navy, alpha=0.6, s=100, zorder=3)
        
        for i, label in enumerate(labels):
            ax.annotate(label, (x_values[i], y_values[i]), xytext=(5, 5),
                       textcoords='offset points', fontsize=9, color=self._char)
        
        ax.set_xlabel(config.xlabel, fontsize=10)
        ax.set_ylabel(config.ylabel, fontsize=10)
        self._set_title(ax, config)
        ax.spines['top'].set_visible(False)
        ax.grid(linestyle='--', alpha=0.4, zorder=0)
        
        return self._save_figure(fig, f"scatter_{hash(config.title) % 10000}", config)
    
    def _generate_bubble(self, config: ChartConfig) -> str:
        """Generate bubble chart"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        sectors = data.get('sectors', [])
        
        for s in sectors:
            ax.scatter(s['x'], s['y'], s=s.get('size', 10) * 50,
                      color=self._navy, alpha=0.5, zorder=3)
            ax.annotate(s['name'], (s['x'], s['y']), xytext=(5, 5),
                       textcoords='offset points', fontsize=9, color=self._char)
        
        ax.set_xlabel(config.xlabel, fontsize=10)
        ax.set_ylabel(config.ylabel, fontsize=10)
        self._set_title(ax, config)
        ax.spines['top'].set_visible(False)
        ax.grid(linestyle='--', alpha=0.4, zorder=0)
        
        return self._save_figure(fig, f"bubble_{hash(config.title) % 10000}", config)
    
    def _generate_waterfall(self, config: ChartConfig) -> str:
        """Generate waterfall chart with cumulative offset"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        factors = data.get('factors', [])
        
        labels = [f['label'] for f in factors]
        values = [f['value'] for f in factors]
        is_total = [f.get('is_total', False) for f in factors]
        
        x = np.arange(len(labels))
        
        # Calculate bottom positions for each bar
        bottoms = []
        cumulative = 0
        for i, (val, it) in enumerate(zip(values, is_total)):
            if it:
                bottoms.append(0)
                cumulative = val
            else:
                bottoms.append(cumulative)
                cumulative += val
        
        # Assign colors
        colors = []
        for v, it in zip(values, is_total):
            if it:
                colors.append(self._navy)
            elif v > 0:
                colors.append('#4CAF50')
            else:
                colors.append('#F44336')
        
        bars = ax.bar(x, values, bottom=bottoms, color=colors, alpha=0.85, zorder=3)
        
        for bar, val, bot in zip(bars, values, bottoms):
            h = bar.get_height()
            y_pos = bot + h if h >= 0 else bot
            if abs(val) >= 10000:
                label = f'{val/10000:+.1f}万'
            elif abs(val) >= 1:
                label = f'{val:+.1f}'
            else:
                label = f'{val:+.2f}'
            ax.text(bar.get_x() + bar.get_width()/2, y_pos,
                   label, ha='center', va='bottom' if h >= 0 else 'top',
                   fontsize=8, color=self._char)
        
        # Add connector lines between bars
        for i in range(len(values) - 1):
            if is_total[i + 1]:
                continue
            top = (bottoms[i] + values[i]) if not is_total[i] else values[i]
            ax.plot([x[i] + 0.4, x[i + 1] - 0.4], [top, top],
                   color='gray', linewidth=0.5, linestyle='--', zorder=2)
        
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8, rotation=20)
        ax.set_ylabel(config.ylabel, fontsize=10)
        ax.axhline(y=0, color='black', linewidth=0.5)
        self._set_title(ax, config)
        ax.spines['top'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.4, zorder=0)
        
        return self._save_figure(fig, f"waterfall_{hash(config.title) % 10000}", config)
    
    def _generate_quadrant(self, config: ChartConfig) -> str:
        """Generate quadrant chart"""
        fig, ax = self._create_figure(config)
        
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axhline(y=5, color='gray', linewidth=1, linestyle='--', alpha=0.5)
        ax.axvline(x=5, color='gray', linewidth=1, linestyle='--', alpha=0.5)
        
        # Quadrant labels
        q_labels = ['利基\n(低能力/小规模)', '领导者\n(高能力/大规模)',
                   '挑战者\n(高能力/小规模)', '跟随者\n(低能力/大规模)']
        positions = [(2.5, 2.5), (7.5, 7.5), (2.5, 7.5), (7.5, 2.5)]
        
        for pos, label in zip(positions, q_labels):
            ax.text(pos[0], pos[1], label, ha='center', va='center',
                   fontsize=8, color='gray', alpha=0.7)
        
        # Draw players
        data = config.data
        for p in data.get('players', []):
            size = p.get('size', 1) * 80
            ax.scatter(p['x'], p['y'], s=size, color=self._navy, alpha=0.6, zorder=5)
            ax.annotate(p['name'], (p['x'], p['y']), xytext=(5, 5),
                       textcoords='offset points', fontsize=9, color=self._char)
        
        ax.set_xlabel(config.xlabel, fontsize=10)
        ax.set_ylabel(config.ylabel, fontsize=10)
        ax.text(5, 5.3, config.xlabel or '规模', ha='center', fontsize=8, color='gray')
        ax.text(5.3, 5, config.ylabel or '能力', ha='center', va='center', fontsize=8,
               color='gray', rotation=90)
        self._set_title(ax, config)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        return self._save_figure(fig, f"quadrant_{hash(config.title) % 10000}", config)


# Export
__all__ = ["ChartGenerator", "ChartConfig", "ChartSpec", "ChartSidecar", "ChartType", "ChartResult"]
