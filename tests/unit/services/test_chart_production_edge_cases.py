"""Production-facing chart data boundary tests."""

from pathlib import Path

from src.services.chart_generator import ChartConfig, ChartGenerator, ChartSpec, ChartType
from src.services.smart_chart_generator import SmartChartGenerator
from src.services.stock_charting import StockChartService
from src.services.table_data_extractor import TableDataExtractor


def test_line_chart_accepts_generic_xy_payload(tmp_path: Path):
    generator = ChartGenerator(output_dir=str(tmp_path))
    result = generator.generate(ChartConfig(
        chart_type=ChartType.LINE,
        title="XY line",
        data={"x": ["2024", "2025"], "y": [10, 12]},
    ))

    assert result.success, result.error
    assert result.image_path and Path(result.image_path).exists()


def test_line_chart_rejects_mismatched_series_lengths(tmp_path: Path):
    generator = ChartGenerator(output_dir=str(tmp_path))
    result = generator.generate(ChartConfig(
        chart_type=ChartType.LINE,
        title="Aligned line",
        data={
            "years": ["2023", "2024", "2025"],
            "scenarios": {"Revenue": [1, 2]},
        },
    ))

    assert not result.success
    assert "lengths must match" in result.error


def test_bar_line_rejects_mismatched_series_lengths(tmp_path: Path):
    generator = ChartGenerator(output_dir=str(tmp_path))
    result = generator.generate(ChartConfig(
        chart_type=ChartType.BAR_LINE,
        title="Mismatched bar line",
        data={"years": ["2024", "2025"], "bar": [10], "line": [1, 2]},
    ))

    assert not result.success
    assert "lengths must match" in result.error


def test_pie_rejects_negative_values(tmp_path: Path):
    generator = ChartGenerator(output_dir=str(tmp_path))
    result = generator.generate(ChartConfig(
        chart_type=ChartType.PIE,
        title="Invalid composition",
        data={"categories": ["A", "B"], "values": [10, -1]},
    ))

    assert not result.success
    assert "non-negative" in result.error


def test_scatter_rejects_mismatched_labels(tmp_path: Path):
    generator = ChartGenerator(output_dir=str(tmp_path))
    result = generator.generate(ChartConfig(
        chart_type=ChartType.SCATTER,
        title="Invalid scatter",
        data={"x": [1, 2], "y": [3, 4], "labels": ["only one"]},
    ))

    assert not result.success
    assert "labels length" in result.error


def test_chart_generators_do_not_overwrite_same_title(tmp_path: Path):
    config = ChartConfig(
        chart_type=ChartType.BAR,
        title="Same title",
        data={"categories": ["A", "B"], "values": [1, 2]},
    )
    first = ChartGenerator(output_dir=str(tmp_path)).generate(config)
    second = ChartGenerator(output_dir=str(tmp_path)).generate(config)

    assert first.success and second.success
    assert first.image_path != second.image_path
    assert Path(first.image_path).exists()
    assert Path(second.image_path).exists()


def test_stock_chart_parser_preserves_zero_and_rejects_invalid_values():
    assert StockChartService._to_float(0) == 0.0
    assert StockChartService._to_float("0") == 0.0
    assert StockChartService._to_float("(1,234.5)") == -1234.5
    assert StockChartService._to_float("—") is None


def test_price_chart_skips_bad_rows_and_keeps_zero_price(monkeypatch):
    service = StockChartService(output_dir=".")
    captured = {}

    class FakeGenerator:
        def generate(self, config):
            captured["config"] = config
            return type("Result", (), {"success": True, "image_path": "chart.png"})()

    service.generator = FakeGenerator()
    result = __import__("asyncio").run(service.price_chart("TEST", [
        {"date": "2025-01-01", "close": "bad"},
        {"date": "2025-01-02", "close": 0},
        {"date": "2025-01-03", "close": "1,234.5"},
    ]))

    assert result["success"] is True
    assert captured["config"].data["scenarios"]["TEST"] == [0.0, 1234.5]


def test_price_chart_sorts_and_deduplicates_dates(monkeypatch, tmp_path: Path):
    service = StockChartService(output_dir=str(tmp_path))
    captured = {}

    class FakeGenerator:
        def generate(self, config):
            captured["config"] = config
            return type("Result", (), {"success": True, "image_path": "chart.png"})()

    service.generator = FakeGenerator()
    result = __import__("asyncio").run(service.price_chart("TEST", [
        {"date": "2025-01-03", "close": 30},
        {"date": "2025-01-01", "close": 10},
        {"date": "2025-01-02", "close": 20},
        {"date": "2025-01-02", "close": 21},
    ]))

    assert result["success"] is True
    assert captured["config"].data["years"] == ["2025-01-01", "2025-01-02", "2025-01-03"]
    assert captured["config"].data["scenarios"]["TEST"] == [10.0, 21.0, 30.0]


def test_markdown_financial_table_parses_parenthesized_negative_value():
    tables = TableDataExtractor.extract_all(
        "| 项目 | 金额 |\n|---|---|\n| 营收 | 1,234.5 |\n| 净利润 | (23.4) |"
    )

    assert len(tables) == 1
    assert tables[0].to_chart_data()["values"] == [1234.5, -23.4]


def test_small_comparison_table_is_not_misclassified_as_pie(tmp_path: Path):
    generator = SmartChartGenerator(output_dir=str(tmp_path))
    suggestions = generator.analyze_content(
        "市场规模",
        "| 公司 | 营收 |\n|---|---:|\n| A | 100 |\n| B | 80 |",
    )

    assert suggestions
    assert suggestions[0].chart_type is ChartType.BAR


def test_table_value_column_can_be_selected_by_header():
    tables = TableDataExtractor.extract_all(
        "| 公司 | 营收 | 利润率 |\n|---|---:|---:|\n| A | 100 | 10% |\n| B | 200 | 20% |"
    )

    data = tables[0].to_chart_data(preferred_headers=["利润率"])
    assert data["value_header"] == "利润率"
    assert data["values"] == [10.0, 20.0]


def test_regex_only_suggestion_cannot_enter_production_generation(tmp_path: Path):
    generator = SmartChartGenerator(output_dir=str(tmp_path))
    suggestions = generator.analyze_content(
        "市场份额",
        "A 40% market share, B 30% market share, C 30% market share",
    )

    assert suggestions
    assert all(not suggestion.verified for suggestion in suggestions)
    assert generator.generate_chart(suggestions[0]) is None


def test_verified_table_suggestion_can_enter_production_generation(tmp_path: Path):
    generator = SmartChartGenerator(output_dir=str(tmp_path))
    suggestions = generator.analyze_content(
        "市场规模",
        "| 公司 | 营收 |\n|---|---:|\n| A | 100 |\n| B | 80 |",
    )

    assert suggestions[0].verified is True
    chart_path = generator.generate_chart(suggestions[0])
    assert chart_path and Path(chart_path).exists()


def test_chart_spec_requires_question_and_preserves_context(tmp_path: Path):
    generator = ChartGenerator(output_dir=str(tmp_path))
    invalid = generator.generate(ChartSpec(
        chart_type=ChartType.BAR,
        title="No question",
        data={"categories": ["A", "B"], "values": [1, 2]},
        question="",
    ))
    assert not invalid.success
    assert "question" in invalid.error

    valid = generator.generate(ChartSpec(
        chart_type=ChartType.BAR,
        title="Revenue",
        data={"categories": ["A", "B"], "values": [1, 2]},
        question="Which company has higher revenue?",
        unit="CNY million",
        data_grain="company-year",
        time_range="2025",
    ))
    assert valid.success, valid.error
    assert valid.image_path and Path(valid.image_path).exists()

    from PIL import Image

    with Image.open(valid.image_path) as image:
        assert image.width >= 320
        assert image.height >= 180
        assert len(image.convert("RGB").getcolors(maxcolors=1_000_000) or []) > 10
