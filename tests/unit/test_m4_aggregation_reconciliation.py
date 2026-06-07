"""
M4 tests: 聚合阶段数值级对账 — MetricExtractor 跨 agent 冲突检测。

Scope:
1. 两个 agent 同一指标数值不一致 → 检测到冲突
2. 一致时不告警
3. 冲突记录包含 sources, values 信息
4. stats 包含 metric_conflicts 字段
5. 单一 agent 同一指标无冲突
6. 按 year 分组检测（不同年份不冲突）
7. 与 M3 交互：M3 已修复 → M4 无冲突
"""
import pytest


@pytest.fixture
def aggregator():
    """Create a ResultAggregator with minimal init for testing."""
    from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator, AggregationConfig

    agg = ResultAggregator.__new__(ResultAggregator)
    agg.config = AggregationConfig(dedup_enabled=False, conflict_resolution="keep_last")
    agg._total_aggregations = 0
    agg._total_conflicts = 0
    return agg


class TestM4MetricConflictDetection:
    """MetricExtractor 跨 agent 数值冲突检测"""

    def test_two_agents_same_metric_conflict(self, aggregator):
        """两个 agent 同一指标不一致 → 检测到冲突"""
        results = {
            "agent_a": {
                "success": True,
                "content": "2024年净利润300亿元，同比增长10%",
                "_agent_category": "analysis",
            },
            "agent_b": {
                "success": True,
                "content": "2024年净利润326亿元，同比增长12%",
                "_agent_category": "analysis",
            },
        }
        out = aggregator.aggregate(results)
        stats = out.stats
        assert stats.get("metric_conflicts", 0) >= 1

    def test_metric_conflict_record_details(self, aggregator):
        """冲突记录包含 sources, values 信息"""

        results = {
            "agent_a": {"success": True, "content": "净利润300亿元", "_agent_category": "analysis"},
            "agent_b": {"success": True, "content": "净利润326亿元", "_agent_category": "analysis"},
        }
        out = aggregator.aggregate(results)
        details = out.stats.get("metric_conflict_details", [])
        assert len(details) >= 1
        entry = details[0]
        assert "key" in entry
        assert "values" in entry
        assert "sources" in entry
        assert len(entry["values"]) >= 2

    def test_same_value_no_conflict(self, aggregator):
        """两个 agent 同一指标一致 → 无冲突"""

        results = {
            "agent_a": {"success": True, "content": "净利润326亿元", "_agent_category": "analysis"},
            "agent_b": {"success": True, "content": "净利润326亿元", "_agent_category": "analysis"},
        }
        out = aggregator.aggregate(results)
        assert out.stats.get("metric_conflicts", 0) == 0

    def test_single_agent_no_conflict(self, aggregator):
        """单一 agent 无冲突"""

        results = {
            "agent_a": {"success": True, "content": "净利润326亿元", "_agent_category": "analysis"},
        }
        out = aggregator.aggregate(results)
        assert out.stats.get("metric_conflicts", 0) == 0

    def test_different_years_no_conflict(self, aggregator):
        """不同年份不冲突"""

        results = {
            "agent_a": {"success": True, "content": "2023年净利润280亿元", "_agent_category": "analysis"},
            "agent_b": {"success": True, "content": "2024年净利润326亿元", "_agent_category": "analysis"},
        }
        out = aggregator.aggregate(results)
        assert out.stats.get("metric_conflicts", 0) == 0

    def test_m3_fixed_content_no_conflict(self, aggregator):
        """M3 已修复同一值 → 无冲突"""

        results = {
            "agent_a": {"success": True, "content": "净利润326.5亿元", "_agent_category": "analysis"},
            "agent_b": {"success": True, "content": "净利润326.5亿元", "_agent_category": "analysis"},
        }
        out = aggregator.aggregate(results)
        assert out.stats.get("metric_conflicts", 0) == 0
