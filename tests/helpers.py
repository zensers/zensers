"""Shared test utilities for M0-M5 pipeline integration tests."""
from dataclasses import dataclass, field


@dataclass
class MockSectionSpec:
    section_id: str
    section_name: str
    section_role: object
    role_reasoning: str = ""
    content_dependency: list = field(default_factory=list)
    skill_requirements: list = field(default_factory=list)
    estimated_complexity: str = "medium"
    can_parallel: bool = True
    priority: int = 0


@dataclass
class MockTaskStructure:
    task_id: str = "test"
    topic: str = "Test"
    sections: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    execution_graph: dict = field(default_factory=dict)
    parallel_groups: list = field(default_factory=list)
    critical_path: list = field(default_factory=list)
    total_estimated_agents: int = 0
    analysis_method: str = "rule_based"


class MockIntent:
    requires_primary_data: bool = False


def make_orch_plan(section_roles):
    """Create a real ExecutionPlan from DynamicPhaseOrchestrator with given section roles."""
    from src.core.task_structure import SectionRole
    from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator

    sections = [
        MockSectionSpec(f"section_{i}_{r.name}", f"Dim{i}", r)
        for i, r in enumerate(section_roles)
    ]
    section_ids = [s.section_id for s in sections]
    task = MockTaskStructure(
        sections=sections,
        parallel_groups=[section_ids],
    )
    intent = MockIntent()
    orch = DynamicPhaseOrchestrator()
    return orch.plan(task, intent, topic="Test Plan")
