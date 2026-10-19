# -*- coding: utf-8 -*-
"""
Chart Design Tokens
===================

报告图表设计令牌（视觉重构统一取值源）。
设计文档: docs/superpowers/specs/2026-10-11-report-visual-optimization-design.md §4.1

所有渲染器（ChartGenerator）与消费方（format_strategy 等）统一从这里取值，
避免多套配置源漂移。
"""

import re
from typing import Any

# ---- 色彩（麦肯锡风 + 保留品牌基因） ----
PRIMARY = "#1A2744"    # 藏青：单系列柱/线默认色
ACCENT = "#C9A227"     # 金：关键数据点强调（最大值/最新期）
SERIES = ["#1A2744", "#4A6FA5", "#A8BCD0", "#C9A227"]  # 多系列≤4
# 多系列超出 SERIES 时的灰阶扩展（补齐 PALETTE_12）
SERIES_GRAYSCALE = [
    "#333333", "#4D4D4D", "#666666", "#808080",
    "#999999", "#B3B3B3", "#C9C9C9", "#DEDEDE",
]
NEUTRAL = "#8C8C8C"    # 非重点系列/基线/脊线
GRID = "#E0E0E0"       # 仅值轴实线 0.8pt；纯白背景，废除 #FAFAFA
TEXT = "#333333"       # 一级文字
TEXT_SUB = "#666666"   # 二级文字（副标题）
TEXT_NOTE = "#999999"  # 三级文字（来源注）

# ---- 字号（微软雅黑） ----
TITLE = 13        # 加粗 左对齐
SUBTITLE = 9      # 灰
AXIS = 9
VALUE_LABEL = 8.5
NOTE = 7.5

# ---- 规格 ----
DPI = 200
FIGSIZE_WIDE = (9, 5.2)    # 宽幅图
FIGSIZE_SQUARE = (8, 4.8)  # 饼/雷达（横版）

# 时间序列类目模式：年份 / 季度 / 月份 / 半年 / YTD
_TIME_LIKE_RE = re.compile(
    r"(?:19|20)\d{2}"             # 2024 / 2024年 / 2025Q1
    r"|Q[1-4]"                    # Q1
    r"|第\s*[一二三四1-4]\s*季度"   # 第一季度
    r"|\d{1,2}\s*月"              # 3月 / 1-8月
    r"|[上下]半年"                 # 上半年 / 下半年
    r"|YTD",
    re.IGNORECASE,
)


def is_time_like(categories: Any) -> bool:
    """判定类目轴是否为时间序列。

    规则：类目数≥2 且 ≥80% 的非空类目命中时间模式（202X/Q1/N月/半年等）。
    """
    items = [str(c).strip() for c in list(categories or []) if str(c).strip()]
    if len(items) < 2:
        return False
    hits = sum(1 for item in items if _TIME_LIKE_RE.search(item))
    return hits / len(items) >= 0.8
