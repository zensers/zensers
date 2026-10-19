from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry


def test_equivalent_numeric_wording_does_not_create_false_conflict():
    registry = DataRegistry()
    registry.register("销量变化", "下滑3", "%", "ch1", "A")
    registry.register("销量变化", "-3", "%", "ch2", "B")
    registry.register("价格", "接近70", "元", "ch1", "A")
    registry.register("价格", "约70", "元", "ch2", "B")

    assert registry.get_conflicts() == []
    assert registry.is_used("销量变化", "下降3")


def test_real_numeric_conflict_is_retained():
    registry = DataRegistry()
    registry.register("销量", "100", "万辆", "ch1", "A")
    registry.register("销量", "120", "万辆", "ch2", "B")

    conflicts = registry.get_conflicts()
    assert len(conflicts) == 1
    assert {entry["value"] for entry in conflicts[0].entries} == {"100", "120"}
