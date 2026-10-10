"""Regression: chart title/subtitle spacing + figure caption parsing."""
import sys
sys.path.insert(0, "E:/market_report_systerm")
from src.services.chart_generator import ChartGenerator, ChartConfig, ChartType
from src.converters.base_parser import HTMLElementParser


def test_title_subtitle_gap(tmp_path):
    g = ChartGenerator(output_dir=str(tmp_path))
    c = ChartConfig(
        chart_type=ChartType.BAR, title="T",
        subtitle="sub", unit="u",
        data={"categories": ["A", "B"], "values": [1, 2]},
    )
    fig, ax = g._create_figure(c)
    g._set_title(ax, c)
    fig.canvas.draw()
    gap = ax.title.get_window_extent().y0 - ax.get_window_extent().y1
    assert gap >= 20, f"title-axes gap too small: {gap}"


def test_figcaption_parsed():
    p = HTMLElementParser()
    p.feed('<figure class="chart-block"><img src="a.png"/><figcaption><strong>T</strong> note</figcaption></figure>')
    types = [e.get("type") for e in p.elements]
    assert "figure_caption" in types, types
    cap = next(e for e in p.elements if e.get("type") == "figure_caption")
    assert "T" in cap.get("text", "")
