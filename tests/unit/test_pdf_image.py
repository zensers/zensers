"""Tests for HTMLToPDFConverter image element handling (P0-3)"""
import sys
sys.path.insert(0, "E:/market_report_systerm")

import os
import shutil
from pathlib import Path

from src.converters.html_to_pdf import HTMLToPDFConverter, ConversionResult


CWD = str(Path.cwd())
TEST_TMP = os.path.join(CWD, "__pdf_test_tmp__")


class TestPDFImageSupport:
    def setup_method(self):
        os.makedirs(TEST_TMP, exist_ok=True)
        self.converter = HTMLToPDFConverter()
        self.output_path = os.path.join(TEST_TMP, "test.pdf")

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.bar(["A", "B"], [1, 2])
        ax.set_title("Test Chart")
        self.chart_path = os.path.join(TEST_TMP, "chart.png")
        fig.savefig(self.chart_path, dpi=100)
        plt.close(fig)

    def teardown_method(self):
        if os.path.exists(TEST_TMP):
            shutil.rmtree(TEST_TMP, ignore_errors=True)

    def test_img_tag_in_html_produces_pdf_with_image(self):
        html = (
            "<article>"
            "<h1>Report with Chart</h1>"
            "<p>Some text content.</p>"
            f"<img src='{self.chart_path}' alt='Test Chart'>"
            "</article>"
        )
        result = self.converter.convert(html, self.output_path)
        assert result.success, f"Conversion failed: {result.error}"
        assert os.path.exists(self.output_path)
        assert result.file_size > 0

    def test_img_without_src_does_not_crash(self):
        html = (
            "<article>"
            "<h1>No Image</h1>"
            "<img alt='No Source'>"
            "</article>"
        )
        result = self.converter.convert(html, self.output_path)
        assert result.success, f"Should not crash: {result.error}"

    def test_missing_image_file_does_not_crash(self):
        html = (
            "<article>"
            "<h1>Missing Image</h1>"
            f"<img src='/nonexistent/path.png' alt='Missing'>"
            "</article>"
        )
        result = self.converter.convert(html, self.output_path)
        assert result.success, f"Should not crash on missing image: {result.error}"

    def test_multiple_images_in_html(self):
        chart2 = os.path.join(TEST_TMP, "chart2.png")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [3, 1, 2])
        fig.savefig(chart2, dpi=100)
        plt.close(fig)

        html = (
            "<article>"
            "<h1>Two Charts</h1>"
            f"<img src='{self.chart_path}' alt='Chart1'>"
            f"<img src='{chart2}' alt='Chart2'>"
            "</article>"
        )
        result = self.converter.convert(html, self.output_path)
        assert result.success, f"Conversion failed: {result.error}"

    def test_pdf_without_images_still_works(self):
        html = (
            "<article>"
            "<h1>Text Only</h1>"
            "<p>Just text, no images.</p>"
            "</article>"
        )
        result = self.converter.convert(html, self.output_path)
        assert result.success, f"Conversion failed: {result.error}"

    def test_image_with_caption(self):
        html = (
            "<article>"
            "<h1>Chart with Caption</h1>"
            "<figure>"
            f"<img src='{self.chart_path}' alt='Revenue Chart'>"
            "<figcaption>Figure 1: Revenue Growth</figcaption>"
            "</figure>"
            "</article>"
        )
        result = self.converter.convert(html, self.output_path)
        assert result.success, f"Conversion failed: {result.error}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
