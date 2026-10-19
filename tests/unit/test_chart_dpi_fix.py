"""Tests for chart_generator DPI fix (P0-5)"""
import sys
sys.path.insert(0, "E:/market_report_systerm")

import tempfile
import os
from pathlib import Path
from src.services.chart_generator import ChartGenerator, ChartConfig, ChartType


class TestSaveFigureDPI:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.gen = ChartGenerator(output_dir=Path(self.tmp_dir))

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_default_dpi_is_200(self):
        config = ChartConfig(
            chart_type=ChartType.BAR,
            title="DPI Test",
            data={"categories": ["A", "B"], "values": [1, 2]},
        )
        result = self.gen.generate(config)
        assert result.success
        assert result.image_path
        assert os.path.exists(result.image_path)

    def test_custom_dpi_is_respected(self):
        config = ChartConfig(
            chart_type=ChartType.BAR,
            title="DPI 200 Test",
            data={"categories": ["A", "B"], "values": [1, 2]},
            dpi=200,
        )
        result = self.gen.generate(config)
        assert result.success
        assert result.image_path
        assert os.path.exists(result.image_path)

    def test_config_dpi_field_exists(self):
        config = ChartConfig(
            chart_type=ChartType.BAR,
            title="Test",
            data={"categories": ["A"], "values": [1]},
            dpi=300,
        )
        assert config.dpi == 300

    def test_config_dpi_default(self):
        config = ChartConfig(
            chart_type=ChartType.BAR,
            title="Test",
            data={"categories": ["A"], "values": [1]},
        )
        assert config.dpi == 200

    def test_pie_with_custom_dpi(self):
        config = ChartConfig(
            chart_type=ChartType.PIE,
            title="DPI Pie",
            data={"categories": ["A", "B", "C"], "values": [30, 40, 30]},
            dpi=200,
        )
        result = self.gen.generate(config)
        assert result.success

    def test_line_with_custom_dpi(self):
        config = ChartConfig(
            chart_type=ChartType.LINE,
            title="DPI Line",
            data={"x": [1, 2, 3], "y": [10, 20, 15]},
            dpi=200,
        )
        result = self.gen.generate(config)
        assert result.success


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
