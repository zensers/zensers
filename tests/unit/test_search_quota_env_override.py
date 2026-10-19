# -*- coding: utf-8 -*-
"""ZENSERS_MAX_TOTAL_SEARCHES 环境变量覆盖运行时搜索配额上限"""
import importlib


def _make(queries=5, total=100):
    from src.core.research_framework_manager import SearchConfig
    return SearchConfig(max_queries_per_section=queries, max_total_searches=total)


def test_default_ceiling_30(monkeypatch):
    monkeypatch.delenv("ZENSERS_MAX_TOTAL_SEARCHES", raising=False)
    importlib.reload(__import__("src.core.research_framework_manager", fromlist=["SearchConfig"]))
    from src.core.research_framework_manager import SearchConfig
    assert _make(queries=5, total=100).max_total_searches == 30


def test_env_override_raises_ceiling(monkeypatch):
    monkeypatch.setenv("ZENSERS_MAX_TOTAL_SEARCHES", "60")
    importlib.reload(__import__("src.core.research_framework_manager", fromlist=["SearchConfig"]))
    from src.core.research_framework_manager import SearchConfig
    assert _make(queries=5, total=100).max_total_searches == 60


def test_env_below_floor_keeps_min(monkeypatch):
    monkeypatch.setenv("ZENSERS_MAX_TOTAL_SEARCHES", "3")
    importlib.reload(__import__("src.core.research_framework_manager", fromlist=["SearchConfig"]))
    from src.core.research_framework_manager import SearchConfig
    assert _make(queries=5, total=100).max_total_searches >= 5