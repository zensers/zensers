"""Regression: chart fig-level title block + figure caption parsing."""
import sys
sys.path.insert(0, "E:/market_report_systerm")

import matplotlib
matplotlib.use("Agg")
from matplotlib.lines import Line2D

from src.services.chart_generator import ChartGenerator, ChartConfig, ChartType
from src.converters.base_parser import HTMLElementParser


def test_fig_level_title_block(tmp_path):
    """标题块在 fig 级：左对齐加粗标题 + 灰色副标题 + 金色下划线，顶部预留头部空间。"""
    g = ChartGenerator(output_dir=str(tmp_path))
    c = ChartConfig(
        chart_type=ChartType.BAR, title="T",
        subtitle="sub", unit="u",
        data={"categories": ["A", "B"], "values": [1, 2]},
    )
    fig, ax = g._create_figure(c)
    g._set_title(fig, c)

    title_texts = [t for t in fig.texts if t.get_text() == "T"]
    assert title_texts, "fig-level title text missing"
    title = title_texts[0]
    assert title.get_ha() == "left"
    assert title.get_fontweight() in ("bold", "heavy", 700)

    subtitle_texts = [t for t in fig.texts if "sub" in t.get_text()]
    assert subtitle_texts, "fig-level subtitle text missing"
    assert subtitle_texts[0].get_color() == "#666666"

    gold_lines = [a for a in fig.artists
                  if isinstance(a, Line2D) and a.get_color() == "#C9A227"]
    assert gold_lines, "gold underline artist missing"

    assert fig.subplotpars.top <= 0.85, \
        f"header space not reserved: top={fig.subplotpars.top}"


def test_figcaption_parsed():
    p = HTMLElementParser()
    p.feed('<figure class="chart-block"><img src="a.png"/><figcaption><strong>T</strong> note</figcaption></figure>')
    types = [e.get("type") for e in p.elements]
    assert "figure_caption" in types, types
    cap = next(e for e in p.elements if e.get("type") == "figure_caption")
    assert "T" in cap.get("text", "")
