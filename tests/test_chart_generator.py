"""Tests for ChartGenerator P1/P2 changes"""
import sys; sys.path.insert(0, "E:/market_report_systerm")
from src.services.chart_generator import ChartGenerator, ChartConfig, ChartType

def test_pie_auto_downgrade():
    gen = ChartGenerator()
    # > 6 items should auto-downgrade to bar
    config = ChartConfig(
        chart_type=ChartType.PIE,
        title="Test Pie",
        data={"categories": [f"Item {i}" for i in range(8)], "values": [i for i in range(8)]},
    )
    result = gen.generate(config)
    assert result.success, f"Pie downgrade failed: {result.error}"
    # Should generate a bar chart instead - check that no error occurred
    print("OK test_pie_auto_downgrade")

def test_pie_under_6():
    gen = ChartGenerator()
    config = ChartConfig(
        chart_type=ChartType.PIE,
        title="Small Pie",
        data={"categories": ["A", "B", "C"], "values": [30, 40, 30]},
    )
    result = gen.generate(config)
    assert result.success, f"Pie under 6 failed: {result.error}"
    print("OK test_pie_under_6")

def test_palette_12():
    gen = ChartGenerator()
    assert len(gen.PALETTE_12) == 12, f"Expected 12 colors, got {len(gen.PALETTE_12)}"
    bar_config = ChartConfig(
        chart_type=ChartType.BAR,
        title="Color Test",
        data={"categories": [f"Item {i}" for i in range(10)], "values": [i for i in range(10)]},
    )
    result = gen.generate(bar_config)
    assert result.success, f"Bar with 10 colors failed: {result.error}"
    print("OK test_palette_12")

if __name__ == "__main__":
    test_pie_auto_downgrade()
    test_pie_under_6()
    test_palette_12()
    print("\nAll chart generator tests passed!")