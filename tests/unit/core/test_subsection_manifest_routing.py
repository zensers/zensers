import pytest

from types import SimpleNamespace

from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType
from src.core.task_structure import SectionRole, SectionSpec, TaskStructure
from src.core.task_structure import normalize_task_structure_runtime_ids


def test_runtime_id_normalization_updates_section_content_dependencies():
    upstream = SectionSpec("section_1_上游", "上游", SectionRole.ANALYSIS)
    downstream = SectionSpec(
        "section_0_下游", "下游", SectionRole.ANALYSIS,
        content_dependency=["section_1_上游", "section_1_上游"],
    )
    structure = TaskStructure("t-normalize", "测试", [downstream, upstream])

    normalize_task_structure_runtime_ids(structure)

    assert downstream.content_dependency == ["section_1"]


def test_dynamic_router_expands_data_specs_into_leaf_agents_and_manifest():
    structure = TaskStructure(
        task_id="t1",
        topic="新能源汽车",
        sections=[SectionSpec("section_0_market", "市场规模", SectionRole.ANALYSIS)],
        section_data_specs=[{
            "section_id": "section_0_market",
            "name": "市场规模",
            "sub_sections": [
                {"sub_section_id": "tam", "name": "TAM", "data_needs": ["市场总规模"]},
                {"sub_section_id": "cagr", "name": "CAGR", "data_needs": ["增长率"]},
            ],
        }],
    )
    intent = SimpleNamespace(complexity=SimpleNamespace(value="multi"), requires_primary_data=False)

    plan = DynamicPhaseOrchestrator().plan(structure, intent, "新能源汽车")
    section_ids = {section.section_id for section in structure.sections}
    assert section_ids == {"section_0_market::tam", "section_0_market::cagr"}
    assert {item["section_id"] for item in structure.section_manifest} == section_ids

    analysis_phases = [phase for phase in plan.phases if phase.phase_type == PhaseType.ANALYSIS]
    assert analysis_phases
    analysis_ids = {
        section_id
        for phase in analysis_phases
        for spec in phase.agent_specs
        for section_id in spec.section_ids
    }
    assert section_ids.issubset(analysis_ids)


def test_dynamic_router_recursively_expands_multi_level_subsections():
    structure = TaskStructure(
        task_id="t1_nested",
        topic="新能源汽车",
        sections=[SectionSpec("section_0", "市场规模", SectionRole.ANALYSIS)],
        section_data_specs=[{
            "section_id": "section_0",
            "name": "市场规模",
            "sub_sections": [{
                "sub_section_id": "regional",
                "name": "区域市场",
                "sub_sections": [
                    {"sub_section_id": "china", "name": "中国市场", "data_needs": ["销量"]},
                    {"sub_section_id": "europe", "name": "欧洲市场", "data_needs": ["销量"]},
                ],
            }],
        }],
    )
    intent = SimpleNamespace(complexity=SimpleNamespace(value="multi"), requires_primary_data=False)

    plan = DynamicPhaseOrchestrator().plan(structure, intent, "新能源汽车")
    expected = {"section_0::regional::china", "section_0::regional::europe"}
    assert {section.section_id for section in structure.sections} == expected
    assert {item["section_id"] for item in structure.section_manifest} == expected
    planned_ids = {
        section_id
        for phase in plan.phases
        for spec in phase.agent_specs
        for section_id in spec.section_ids
    }
    assert expected.issubset(planned_ids)


def test_dynamic_router_keeps_parent_when_no_subsection_contract_exists():
    structure = TaskStructure(
        task_id="t2",
        topic="行业",
        sections=[SectionSpec("section_0", "行业概览", SectionRole.ANALYSIS)],
    )
    intent = SimpleNamespace(complexity=SimpleNamespace(value="single"), requires_primary_data=False)

    DynamicPhaseOrchestrator().plan(structure, intent, "行业")
    assert [section.section_id for section in structure.sections] == ["section_0"]
    assert structure.section_manifest[0]["section_id"] == "section_0"


def test_dynamic_router_does_not_accept_incomplete_parent_only_manifest():
    structure = TaskStructure(
        task_id="t2b",
        topic="行业",
        sections=[SectionSpec("section_0", "行业概览", SectionRole.ANALYSIS)],
        section_data_specs=[{
            "section_id": "section_0",
            "name": "行业概览",
            "sub_sections": [{"sub_section_id": "market", "name": "市场规模"}],
        }],
        section_manifest=[{
            "section_id": "section_0",
            "parent_section_id": "section_0",
            "title": "行业概览",
        }],
    )
    intent = SimpleNamespace(complexity=SimpleNamespace(value="multi"), requires_primary_data=False)

    DynamicPhaseOrchestrator().plan(structure, intent, "行业")
    assert [section.section_id for section in structure.sections] == ["section_0::market"]
    assert [item["section_id"] for item in structure.section_manifest] == ["section_0::market"]


def test_dynamic_router_rejects_empty_expected_leaf_set_instead_of_accepting_legacy_manifest():
    """错误的 data spec ID 不能让 parent-only Manifest 直接通过。"""
    structure = TaskStructure(
        task_id="t2c",
        topic="行业",
        sections=[SectionSpec("section_0", "行业概览", SectionRole.ANALYSIS)],
        section_data_specs=[{
            "section_id": "wrong_id",
            "name": "行业概览",
            "sub_sections": [{"sub_section_id": "market", "name": "市场规模"}],
        }],
        section_manifest=[{
            "section_id": "section_0",
            "parent_section_id": "section_0",
            "title": "行业概览",
        }],
    )
    intent = SimpleNamespace(complexity=SimpleNamespace(value="multi"), requires_primary_data=False)

    with pytest.raises(ValueError, match="subsection|leaf|manifest"):
        DynamicPhaseOrchestrator().plan(structure, intent, "行业")


def test_dynamic_router_rejects_duplicate_existing_manifest_ids():
    structure = TaskStructure(
        task_id="t2d",
        topic="行业",
        sections=[SectionSpec("section_0", "行业概览", SectionRole.ANALYSIS)],
        section_data_specs=[{
            "section_id": "section_0",
            "name": "行业概览",
            "sub_sections": [{"sub_section_id": "market", "name": "市场规模"}],
        }],
        section_manifest=[
            {"section_id": "section_0::market"},
            {"section_id": "section_0::market"},
        ],
    )
    intent = SimpleNamespace(complexity=SimpleNamespace(value="multi"), requires_primary_data=False)
    with pytest.raises(ValueError, match="duplicate"):
        DynamicPhaseOrchestrator().plan(structure, intent, "行业")


def test_dynamic_router_rejects_ambiguous_name_binding():
    structure = TaskStructure(
        task_id="t2e",
        topic="行业",
        sections=[SectionSpec("section_0", "行业概览", SectionRole.ANALYSIS)],
        section_data_specs=[
            {"section_id": "spec_a", "name": "行业概览", "sub_sections": [{"id": "a", "name": "A"}]},
            {"section_id": "spec_b", "name": "行业概览", "sub_sections": [{"id": "b", "name": "B"}]},
        ],
    )
    intent = SimpleNamespace(complexity=SimpleNamespace(value="multi"), requires_primary_data=False)
    with pytest.raises(ValueError, match="ambiguous"):
        DynamicPhaseOrchestrator().plan(structure, intent, "行业")


def test_dynamic_router_rejects_unbound_subsection_contract_without_existing_manifest():
    structure = TaskStructure(
        task_id="t2f",
        topic="行业",
        sections=[SectionSpec("section_0", "行业概览", SectionRole.ANALYSIS)],
        section_data_specs=[{
            "section_id": "wrong_id",
            "name": "完全不同的章节",
            "sub_sections": [{"id": "market", "name": "市场规模"}],
        }],
    )
    intent = SimpleNamespace(complexity=SimpleNamespace(value="single"), requires_primary_data=False)
    with pytest.raises(ValueError, match="bind|subsection|Manifest"):
        DynamicPhaseOrchestrator().plan(structure, intent, "行业")


def test_dynamic_router_rejects_duplicate_generated_leaf_ids():
    structure = TaskStructure(
        task_id="t2g",
        topic="行业",
        sections=[SectionSpec("section_0", "行业概览", SectionRole.ANALYSIS)],
        section_data_specs=[{
            "section_id": "section_0",
            "name": "行业概览",
            "sub_sections": [
                {"id": "same", "name": "市场规模"},
                {"id": "same", "name": "竞争格局"},
            ],
        }],
    )
    intent = SimpleNamespace(complexity=SimpleNamespace(value="single"), requires_primary_data=False)
    with pytest.raises(ValueError, match="duplicate"):
        DynamicPhaseOrchestrator().plan(structure, intent, "行业")


def test_dynamic_router_preserves_nested_object_subsections():
    nested = SimpleNamespace(
        sub_section_id="regional",
        name="区域市场",
        sub_sections=[SimpleNamespace(sub_section_id="china", name="中国市场", data_needs=["销量"])],
    )
    spec = SimpleNamespace(section_id="section_0", name="市场规模", sub_sections=[nested])
    structure = TaskStructure(
        task_id="t2h",
        topic="行业",
        sections=[SectionSpec("section_0", "市场规模", SectionRole.ANALYSIS)],
        section_data_specs=[spec],
    )
    intent = SimpleNamespace(complexity=SimpleNamespace(value="single"), requires_primary_data=False)
    DynamicPhaseOrchestrator().plan(structure, intent, "行业")
    assert [section.section_id for section in structure.sections] == ["section_0::regional::china"]


def test_task_structure_serialization_preserves_data_specs_for_contract_audit():
    structure = TaskStructure(
        task_id="t2i",
        topic="行业",
        sections=[SectionSpec("section_0", "市场规模", SectionRole.ANALYSIS)],
        section_data_specs=[{"section_id": "section_0", "name": "市场规模", "sub_sections": []}],
    )
    assert structure.to_dict()["section_data_specs"] == structure.section_data_specs


def test_synthesis_agents_depend_on_every_upstream_leaf_and_report_gets_manifest():
    structure = TaskStructure(
        task_id="t3",
        topic="行业",
        sections=[
            SectionSpec("a", "市场规模", SectionRole.ANALYSIS),
            SectionSpec("b", "竞争格局", SectionRole.ANALYSIS),
            SectionSpec("s", "执行摘要", SectionRole.SYNTHESIS,
                        config={"output_slot": "exec_summary"}),
            SectionSpec("c", "研究结论", SectionRole.SYNTHESIS,
                        config={"output_slot": "conclusion"}),
        ],
        parallel_groups=[["a", "b", "s", "c"]],
    )
    intent = SimpleNamespace(complexity=SimpleNamespace(value="single"), requires_primary_data=False)

    plan = DynamicPhaseOrchestrator().plan(structure, intent, "行业")
    synthesis = next(p for p in plan.phases if p.phase_type == PhaseType.SYNTHESIS)
    analysis_agent_ids = {
        spec.agent_id for phase in plan.phases
        if phase.phase_type == PhaseType.ANALYSIS
        for spec in phase.agent_specs
    }
    assert analysis_agent_ids
    for spec in synthesis.agent_specs:
        assert analysis_agent_ids.issubset(set(spec.config["resolved_dependencies"]))

    report_phase = next(p for p in plan.phases if p.phase_type == PhaseType.REPORT)
    assert report_phase.agent_specs[0].config["section_manifest"] == structure.section_manifest
    slots = {item["section_id"]: item["output_slot"] for item in structure.section_manifest}
    assert slots["s"] == "exec_summary"
    assert slots["c"] == "conclusion"
    assert all(item.get("producer_agent_ids") for item in structure.section_manifest)
    planned_agent_ids = {spec.agent_id for phase in plan.phases for spec in phase.agent_specs}
    assert all(
        producer_id in planned_agent_ids
        for item in structure.section_manifest
        for producer_ids in item["producer_agent_ids"].values()
        for producer_id in producer_ids
    )


def test_routing_adapter_preserves_user_confirmed_tree_when_llm_specs_empty():
    from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter

    adapter = IntelligentRoutingAdapter(use_llm=False, fallback_to_keyword=True)
    intent = SimpleNamespace(
        section_data_specs=[], requires_primary_data=False,
        recommended_skills=[], complexity=SimpleNamespace(value="single"),
    )
    structure = adapter._analyze_structure(
        {
            "aspects": ["市场规模"],
            "dynamic_fields": {
                "sections_tree": [{
                    "id": "market_size",
                    "name": "市场规模",
                    "sub_sections": [{"id": "tam", "name": "TAM", "points": ["市场总规模"]}],
                }],
            },
        },
        intent,
        "新能源汽车",
    )
    assert structure.section_data_specs[0]["sub_sections"][0]["name"] == "TAM"
