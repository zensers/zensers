import inspect


def test_quality_repair_rebinds_report_used_by_next_check_and_render():
    from src.core.orchestrator.orchestrator import ResearchOrchestrator

    source = inspect.getsource(ResearchOrchestrator._research_with_routing)
    repair_pos = source.index("self._apply_quality_adjustment")
    rebind_pos = source.index("research_result_data = _preserve_report_level_fields(", repair_pos)
    render_pos = source.index('"research_result": research_result_data', rebind_pos)
    assert repair_pos < rebind_pos < render_pos
