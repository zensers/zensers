import inspect

from src.core.orchestrator import orchestrator
from src.core.orchestrator.execution import engine


def test_engine_has_deep_mode_service_hook():
    source = inspect.getsource(engine.ExecutionEngine._execute_batch)
    assert "deep_mode" in source
    assert "ensure_tables" in source or "enrich" in source
    assert "self._deep_mode_service.enrich(" in source
    assert "_deep_mode_done_tasks" in source
    assert "shadow" in source
    assert '_point["section_id"]' in source


def test_deep_parent_section_id():
    assert engine._deep_parent_section_id("section_7::sub_2") == "section_7"
    assert engine._deep_parent_section_id("section_3") == "section_3"


def test_orchestrator_registers_deep_mode_scope():
    source = inspect.getsource(orchestrator.ResearchOrchestrator._configure_task_search_gateway)
    assert '"deep_mode"' in source


def test_orchestrator_requirements_carry_output_type():
    orch_source = inspect.getsource(orchestrator)
    assert orch_source.count('"output_type": output_type_value') >= 4
    assert orch_source.count('"output_type": requirement_dict["output_type"]') >= 1
