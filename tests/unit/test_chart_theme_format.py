# -*- coding: utf-8 -*-
"""chart_theme 设计令牌 + 图表公共格式化工具（_format_value/_auto_margins/来源过滤）单测。"""
import sys
sys.path.insert(0, "E:/market_report_systerm")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.services import chart_theme
from src.services.chart_generator import ChartGenerator, normalize_source
from src.services.chart_theme import is_time_like


class TestFormatValue:
    def test_zero(self):
        assert ChartGenerator._format_value(0) == "0.00"

    def test_half(self):
        assert ChartGenerator._format_value(0.5) == "0.50"

    def test_under_thousand_one_decimal(self):
        assert ChartGenerator._format_value(999) == "999.0"

    def test_thousand_separator(self):
        assert ChartGenerator._format_value(1500) == "1,500"

    def test_upper_boundary_before_wan(self):
        assert ChartGenerator._format_value(9999) == "9,999"

    def test_wan(self):
        assert ChartGenerator._format_value(12345) == "1.2万"

    def test_percent_unit(self):
        assert ChartGenerator._format_value(12.34, "%") == "12.3%"

    def test_negative_thousand(self):
        assert ChartGenerator._format_value(-2345) == "-2,345"

    def test_negative_wan(self):
        assert ChartGenerator._format_value(-20000) == "-2.0万"


class TestNormalizeSource:
    def test_leaked_content(self):
        assert normalize_source("content") == "公开资料整理"

    def test_leaked_fetched_case_insensitive(self):
        assert normalize_source("Fetched") == "公开资料整理"
        assert normalize_source("CONTENT") == "公开资料整理"

    def test_leaked_default_english(self):
        assert normalize_source("Public data compilation") == "公开资料整理"

    def test_blank_falls_back(self):
        assert normalize_source("") == "公开资料整理"
        assert normalize_source("   ") == "公开资料整理"
        assert normalize_source(None) == "公开资料整理"

    def test_real_source_passes_through(self):
        assert normalize_source("高工机器人产业研究所（GGII）") == "高工机器人产业研究所（GGII）"


class TestAutoMargins:
    def test_vertical_upper_headroom(self):
        fig, ax = plt.subplots()
        try:
            ChartGenerator._auto_margins(ax, [10, 364.4, 200])
            ymin, ymax = ax.get_ylim()
            assert ymax >= 364.4 * 1.15 - 1e-9
            assert ymin == 0
        finally:
            plt.close(fig)

    def test_horizontal_right_headroom(self):
        fig, ax = plt.subplots()
        try:
            ChartGenerator._auto_margins(ax, [5000, 18000, 40000], horizontal=True)
            xmin, xmax = ax.get_xlim()
            assert xmax >= 40000 * 1.12 - 1e-9
            assert xmin == 0
        finally:
            plt.close(fig)

    def test_negative_values_keep_zero_base(self):
        fig, ax = plt.subplots()
        try:
            ChartGenerator._auto_margins(ax, [-5, 10, 3])
            ymin, ymax = ax.get_ylim()
            assert ymax >= 10 * 1.15 - 1e-9
            assert ymin <= -5
            assert ymin < 0 < ymax
        finally:
            plt.close(fig)

    def test_all_negative(self):
        fig, ax = plt.subplots()
        try:
            ChartGenerator._auto_margins(ax, [-5, -10])
            ymin, ymax = ax.get_ylim()
            assert ymax == 0
            assert ymin <= -5
        finally:
            plt.close(fig)

    def test_empty_values_noop(self):
        fig, ax = plt.subplots()
        try:
            before = ax.get_ylim()
            ChartGenerator._auto_margins(ax, [])
            assert ax.get_ylim() == before
        finally:
            plt.close(fig)


class TestIsTimeLike:
    def test_quarters(self):
        assert is_time_like(["2025Q1", "2025Q2", "2025Q3"]) is True

    def test_mixed_quarter_and_cumulative(self):
        assert is_time_like(["2025Q1", "2025年1-8月", "2026Q1"]) is True

    def test_years(self):
        assert is_time_like(["2023年", "2024年", "2025年"]) is True

    def test_plain_years(self):
        assert is_time_like(["2023", "2024", "2025"]) is True

    def test_chinese_quarters(self):
        assert is_time_like(["第一季度", "第二季度", "第三季度"]) is True

    def test_half_year(self):
        assert is_time_like(["2025上半年", "2025下半年"]) is True

    def test_companies_not_time(self):
        assert is_time_like(["CATL", "BYD", "LG能源"]) is False

    def test_too_few_categories(self):
        assert is_time_like(["2024"]) is False
        assert is_time_like([]) is False
        assert is_time_like(None) is False


def test_theme_tokens():
    assert chart_theme.PRIMARY == "#1A2744"
    assert chart_theme.ACCENT == "#C9A227"
    assert len(chart_theme.SERIES) == 4
    assert chart_theme.SERIES[0] == chart_theme.PRIMARY
    assert chart_theme.NEUTRAL == "#8C8C8C"
    assert chart_theme.GRID == "#E0E0E0"
    assert chart_theme.DPI == 200
    assert chart_theme.FIGSIZE_WIDE == (9, 5.2)
    assert chart_theme.FIGSIZE_SQUARE == (8, 4.8)
    assert chart_theme.TITLE == 13
    assert chart_theme.SUBTITLE == 9
    assert chart_theme.AXIS == 9
    assert chart_theme.VALUE_LABEL == 8.5
    assert chart_theme.NOTE == 7.5


def test_palette_12_still_has_twelve_colors():
    assert len(ChartGenerator.PALETTE_12) == 12
    # 前四色对齐 theme.SERIES，其后为灰阶扩展
    assert ChartGenerator.PALETTE_12[:4] == chart_theme.SERIES
