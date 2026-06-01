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
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np

logger = logging.getLogger(__name__)

# Set matplotlib backend
matplotlib.use('Agg')

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
    width: int = 9
    height: int = 5.5
    dpi: int = 150


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
        (201/255, 162/255, 39/255),   # gold variant
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
    
    def _rgb(self, r: int, g: int, b: int) -> Tuple[float, float, float]:
        """Convert RGB to matplotlib format"""
        return (r/255, g/255, b/255)
    
    def generate(self, config: ChartConfig) -> ChartResult:
        """
        Generate chart
        
        Args:
            config: Chart configuration
            
        Returns:
            ChartResult generation result
        """
        try:
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
    
    def _create_figure(self, config: ChartConfig) -> Tuple[plt.Figure, plt.Axes]:
        """Create figure"""
        fig, ax = plt.subplots(figsize=(config.width, config.height))
        fig.patch.set_facecolor('white')
        ax.set_facecolor('#FAFAFA')
        return fig, ax
    
    def _save_figure(self, fig: plt.Figure, name: str) -> str:
        """Save figure with unique filename"""
        self._chart_counter += 1
        image_path = str(self.output_dir / f"{name}_{self._chart_counter}.png")
        fig.savefig(image_path, dpi=150, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        return image_path
    
    def _generate_bar(self, config: ChartConfig) -> str:
        """Generate bar chart"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        categories = data.get('categories', [])
        values = data.get('values', [])
        
        x = np.arange(len(categories))
        colors = self.PALETTE_12[:len(categories)]
        
        bars = ax.bar(x, values, color=colors, alpha=0.85, zorder=3)
        
        # Add value labels
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                   f'{val}%', ha='center', va='bottom', fontsize=9, color=self._char)
        
        ax.set_xticks(x)
        ax.set_xticklabels(categories, fontsize=9, rotation=15)
        ax.set_ylabel(config.ylabel, fontsize=10)
        ax.set_title(config.title, fontsize=12, fontweight='bold', pad=12, color=self._char)
        ax.spines['top'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.4, zorder=0)
        
        return self._save_figure(fig, f"bar_{hash(config.title) % 10000}")
    
    def _generate_hbar(self, config: ChartConfig) -> str:
        """Generate horizontal bar chart"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        labels = data.get('labels', data.get('categories', []))
        values = data.get('values', [])
        
        y = np.arange(len(labels))
        colors = self.PALETTE_12[:len(labels)]
        
        bars = ax.barh(y, values, color=colors, alpha=0.85, zorder=3)
        
        for bar, val in zip(bars, values):
            ax.text(bar.get_width() + 5, bar.get_y() + bar.get_height()/2,
                   f'{val}%', va='center', fontsize=9, color=self._char)
        
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=10)
        ax.set_xlabel(config.xlabel or config.ylabel, fontsize=10)
        ax.set_title(config.title, fontsize=12, fontweight='bold', pad=12, color=self._char)
        ax.spines['top'].set_visible(False)
        ax.grid(axis='x', linestyle='--', alpha=0.4, zorder=0)
        ax.invert_yaxis()
        
        return self._save_figure(fig, f"hbar_{hash(config.title) % 10000}")
    
    def _generate_bar_line(self, config: ChartConfig) -> str:
        """Generate bar + line combination chart"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        years = data.get('years', [])
        bar_values = data.get('bar', [])
        line_values = data.get('line', [])
        
        x = np.arange(len(years))
        w = 0.5
        
        bars = ax.bar(x, bar_values, w, color=self._navy, alpha=0.85, zorder=3)
        
        # Add line
        ax2 = ax.twinx()
        ax2.plot(x, line_values, 'o-', color=self._gold, linewidth=2.5,
                markersize=7, label=data.get('line_label', ''), zorder=4)
        ax2.set_ylabel(data.get('line_label', ''), color=self._gold, fontsize=10)
        ax2.tick_params(axis='y', labelcolor=self._gold)
        
        # Bar value labels
        for bar, val in zip(bars, bar_values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 30,
                   f'{val}', ha='center', va='bottom', fontsize=8, color=self._char)
        
        ax.set_xticks(x)
        ax.set_xticklabels(years, fontsize=9)
        ax.set_ylabel(config.ylabel, fontsize=10)
        ax.set_title(config.title, fontsize=12, fontweight='bold', pad=12, color=self._char)
        ax.spines['top'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.4, zorder=0)
        
        return self._save_figure(fig, f"barline_{hash(config.title) % 10000}")
    
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
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(9)
            autotext.set_fontweight('bold')
        
        ax.set_title(config.title, fontsize=12, fontweight='bold', pad=12, color=self._char)
        
        return self._save_figure(fig, f"pie_{hash(config.title) % 10000}")
    
    def _generate_line(self, config: ChartConfig) -> str:
        """Generate line chart"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        years = data.get('years', [])
        scenarios = data.get('scenarios', {})
        
        x = np.arange(len(years))
        line_styles = [(self._navy, '-'), (self._gold, '--'), ('#7EB5A6', '-.')]
        
        for (col, ls), (label, vals) in zip(line_styles, scenarios.items()):
            ax.plot(x, vals, marker='o', linewidth=2, color=col,
                   linestyle=ls, label=label, zorder=3)
        
        ax.set_xticks(x)
        ax.set_xticklabels(years, fontsize=9)
        ax.set_ylabel(config.ylabel, fontsize=10)
        ax.set_title(config.title, fontsize=12, fontweight='bold', pad=12, color=self._char)
        ax.legend(fontsize=9, loc='upper left')
        ax.spines['top'].set_visible(False)
        ax.grid(linestyle='--', alpha=0.4, zorder=0)
        
        return self._save_figure(fig, f"line_{hash(config.title) % 10000}")
    
    def _generate_radar(self, config: ChartConfig) -> str:
        """Generate radar chart"""
        data = config.data
        categories = data.get('categories', [])
        values = data.get('values', [])
        
        N = len(categories)
        angles = [n / float(N) * 2 * np.pi for n in range(N)]
        angles += angles[:1]
        values = values + values[:1]
        
        fig = plt.figure(figsize=(8, 8))
        ax = plt.subplot(111, polar=True)
        fig.patch.set_facecolor('white')
        
        ax.plot(angles, values, 'o-', linewidth=2, color=self._navy, alpha=0.8)
        ax.fill(angles, values, alpha=0.25, color=self._navy)
        ax.set_thetagrids(np.degrees(angles[:-1]), categories, fontsize=9)
        ax.set_ylim(0, 100)
        ax.set_title(config.title, fontsize=12, fontweight='bold', pad=20)
        
        plt.tight_layout()
        return self._save_figure(fig, f"radar_{hash(config.title) % 10000}")
    
    def _generate_scatter(self, config: ChartConfig) -> str:
        """Generate scatter plot"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        x_values = data.get('x', [])
        y_values = data.get('y', [])
        labels = data.get('labels', [])
        
        ax.scatter(x_values, y_values, c=self._navy, alpha=0.6, s=100, zorder=3)
        
        for i, label in enumerate(labels):
            ax.annotate(label, (x_values[i], y_values[i]), xytext=(5, 5),
                       textcoords='offset points', fontsize=9, color=self._char)
        
        ax.set_xlabel(config.xlabel, fontsize=10)
        ax.set_ylabel(config.ylabel, fontsize=10)
        ax.set_title(config.title, fontsize=12, fontweight='bold', pad=12, color=self._char)
        ax.spines['top'].set_visible(False)
        ax.grid(linestyle='--', alpha=0.4, zorder=0)
        
        return self._save_figure(fig, f"scatter_{hash(config.title) % 10000}")
    
    def _generate_bubble(self, config: ChartConfig) -> str:
        """Generate bubble chart"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        sectors = data.get('sectors', [])
        
        for s in sectors:
            ax.scatter(s['x'], s['y'], s=s.get('size', 10) * 50,
                      c=self._navy, alpha=0.5, zorder=3)
            ax.annotate(s['name'], (s['x'], s['y']), xytext=(5, 5),
                       textcoords='offset points', fontsize=9, color=self._char)
        
        ax.set_xlabel(config.xlabel, fontsize=10)
        ax.set_ylabel(config.ylabel, fontsize=10)
        ax.set_title(config.title, fontsize=12, fontweight='bold', pad=12, color=self._char)
        ax.spines['top'].set_visible(False)
        ax.grid(linestyle='--', alpha=0.4, zorder=0)
        
        return self._save_figure(fig, f"bubble_{hash(config.title) % 10000}")
    
    def _generate_waterfall(self, config: ChartConfig) -> str:
        """Generate waterfall chart"""
        fig, ax = self._create_figure(config)
        
        data = config.data
        factors = data.get('factors', [])
        
        labels = [f['label'] for f in factors]
        values = [f['value'] for f in factors]
        is_total = [f.get('is_total', False) for f in factors]
        
        x = np.arange(len(labels))
        colors = []
        for v, it in zip(values, is_total):
            if it:
                colors.append(self._navy)
            elif v > 0:
                colors.append('#4CAF50')
            else:
                colors.append('#F44336')
        
        bars = ax.bar(x, values, color=colors, alpha=0.85, zorder=3)
        
        cumulative = [0]
        for v in values[:-1]:
            cumulative.append(cumulative[-1] + v)
        
        for bar, val, cum in zip(bars, values, cumulative):
            h = bar.get_height()
            y_pos = cum + h if h >= 0 else cum + h
            ax.text(bar.get_x() + bar.get_width()/2, y_pos,
                   f'{val:+.0f}', ha='center', va='bottom' if h >= 0 else 'top',
                   fontsize=8, color=self._char)
        
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8, rotation=20)
        ax.set_ylabel(config.ylabel, fontsize=10)
        ax.axhline(y=0, color='black', linewidth=0.5)
        ax.set_title(config.title, fontsize=12, fontweight='bold', pad=12, color=self._char)
        ax.spines['top'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.4, zorder=0)
        
        return self._save_figure(fig, f"waterfall_{hash(config.title) % 10000}")
    
    def _generate_quadrant(self, config: ChartConfig) -> str:
        """Generate quadrant chart"""
        fig, ax = self._create_figure(config)
        
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axhline(y=5, color='gray', linewidth=1, linestyle='--', alpha=0.5)
        ax.axvline(x=5, color='gray', linewidth=1, linestyle='--', alpha=0.5)
        
        # Quadrant labels
        q_labels = ['Niche\n(Low Tech/Low Market)', 'Leader\n(High Tech/High Market)',
                   'Challenger\n(High Tech/Low Market)', 'Follower\n(Low Tech/High Market)']
        positions = [(7.5, 7.5), (2.5, 7.5), (2.5, 2.5), (7.5, 2.5)]
        
        for pos, label in zip(positions, q_labels):
            ax.text(pos[0], pos[1], label, ha='center', va='center',
                   fontsize=8, color='gray', alpha=0.7)
        
        # Draw players
        data = config.data
        for p in data.get('players', []):
            size = p.get('size', 1) * 80
            ax.scatter(p['x'], p['y'], s=size, c=self._navy, alpha=0.6, zorder=5)
            ax.annotate(p['name'], (p['x'], p['y']), xytext=(5, 5),
                       textcoords='offset points', fontsize=9, color=self._char)
        
        ax.set_xlabel(config.xlabel, fontsize=10)
        ax.set_ylabel(config.ylabel, fontsize=10)
        ax.text(5, 5.3, 'Market Capability', ha='center', fontsize=8, color='gray')
        ax.text(5.3, 5, 'Technical Capability', ha='center', va='center', fontsize=8,
               color='gray', rotation=90)
        ax.set_title(config.title, fontsize=12, fontweight='bold', pad=12, color=self._char)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        return self._save_figure(fig, f"quadrant_{hash(config.title) % 10000}")


# Export
__all__ = ["ChartGenerator", "ChartConfig", "ChartType", "ChartResult"]
