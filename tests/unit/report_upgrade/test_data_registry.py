import pytest

from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
from src.agents.fixed_agents.report_upgrade.models import DataConflict


class TestDataRegistryRegister:
    def test_register_new_metric(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        assert reg.get_canonical_value("市场规模") == "2000"

    def test_register_same_value_no_conflict(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        reg.register("市场规模", "2000", "亿元", "ch2", "iresearch.cn")
        conflicts = reg.get_conflicts()
        assert len(conflicts) == 0

    def test_register_different_value_creates_conflict(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        reg.register("市场规模", "1800", "亿元", "ch2", "iresearch.cn")
        conflicts = reg.get_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].metric == "市场规模"
        assert len(conflicts[0].entries) == 2

    def test_normalize_metric_case_insensitive(self):
        reg = DataRegistry()
        reg.register("GDP", "120", "万亿元", "ch1", "gov.cn")
        assert reg.get_canonical_value("gdp") == "120"

    def test_normalize_metric_whitespace(self):
        reg = DataRegistry()
        reg.register(" 市场规模 ", "2000", "亿元", "ch1", "iimedia.cn")
        assert reg.get_canonical_value("市场规模") == "2000"


class TestDataRegistryGetCanonicalValue:
    def test_unknown_metric_returns_none(self):
        reg = DataRegistry()
        assert reg.get_canonical_value("不存在") is None

    def test_after_set_canonical_value(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        reg.set_canonical_value("市场规模", "1800", "iresearch.cn")
        assert reg.get_canonical_value("市场规模") == "1800"

    def test_set_canonical_clears_conflicts(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        reg.register("市场规模", "1800", "亿元", "ch2", "iresearch.cn")
        assert len(reg.get_conflicts()) == 1
        reg.set_canonical_value("市场规模", "2000", "iimedia.cn")
        assert len(reg.get_conflicts()) == 0


class TestDataRegistryIsUsed:
    def test_not_registered(self):
        reg = DataRegistry()
        assert reg.is_used("市场规模", "2000") is False

    def test_same_value(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        assert reg.is_used("市场规模", "2000") is True

    def test_different_value(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        assert reg.is_used("市场规模", "1800") is False


class TestDataRegistrySerialize:
    def test_serialize_used_metrics_empty(self):
        reg = DataRegistry()
        assert reg.serialize_used_metrics() == "暂无已使用的数据指标。"

    def test_serialize_used_metrics_with_data(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        result = reg.serialize_used_metrics()
        assert "市场规模" in result
        assert "2000" in result
        assert "亿元" in result

    def test_serialize_used_metrics_with_conflict(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        reg.register("市场规模", "1800", "亿元", "ch2", "iresearch.cn")
        result = reg.serialize_used_metrics()
        assert "冲突" in result

    def test_serialize_conflicts_empty(self):
        reg = DataRegistry()
        assert reg.serialize_conflicts() == "无已知数据冲突。"

    def test_serialize_conflicts_with_data(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        reg.register("市场规模", "1800", "亿元", "ch2", "iresearch.cn")
        result = reg.serialize_conflicts()
        assert "市场规模" in result
        assert "2000" in result
        assert "1800" in result


class TestDataRegistrySnapshot:
    def test_to_snapshot_and_from_snapshot(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        reg.register("增速", "15", "%", "ch1", "gov.cn")
        snapshot = reg.to_snapshot()

        reg2 = DataRegistry.from_snapshot(snapshot)
        assert reg2.get_canonical_value("市场规模") == "2000"
        assert reg2.get_canonical_value("增速") == "15"

    def test_snapshot_preserves_conflicts(self):
        reg = DataRegistry()
        reg.register("市场规模", "2000", "亿元", "ch1", "iimedia.cn")
        reg.register("市场规模", "1800", "亿元", "ch2", "iresearch.cn")
        snapshot = reg.to_snapshot()

        reg2 = DataRegistry.from_snapshot(snapshot)
        conflicts = reg2.get_conflicts()
        assert len(conflicts) == 1

    def test_empty_snapshot(self):
        reg = DataRegistry.from_snapshot({})
        assert reg.get_canonical_value("anything") is None
