from src.api.research_executor import _select_section_details
from pathlib import Path


def test_selected_aspects_do_not_expand_to_full_framework_catalog():
    catalog = [
        {"id": "industry_overview", "name": "Industry Overview", "sub_sections": [{"name": "definition"}]},
        {"id": "market_size_growth", "name": "Market Size & Growth"},
        {"id": "growth_drivers", "name": "Growth Drivers"},
        {"id": "market_segmentation", "name": "Market Segmentation"},
        {"id": "competitive_landscape", "name": "Competitive Landscape"},
        {"id": "risk_analysis", "name": "Risk Analysis"},
    ]

    selected = _select_section_details(
        catalog,
        ["市场定义", "市场规模", "增长驱动", "市场细分", "竞争格局"],
    )

    assert [item["name"] for item in selected] == [
        "市场定义", "市场规模", "增长驱动", "市场细分", "竞争格局"
    ]
    assert len(selected) == 5
    assert [item["id"] for item in selected] == [
        "section_0", "section_1", "section_2", "section_3", "section_4"
    ]
    assert [item["section_id"] for item in selected] == [
        "section_0", "section_1", "section_2", "section_3", "section_4"
    ]
    assert selected[0]["template_id"] == "industry_overview"
    assert selected[0]["sub_sections"] == [{"name": "definition"}]


def test_unknown_selected_aspect_gets_minimal_detail_instead_of_all_sections():
    selected = _select_section_details(
        [{"id": "market_size", "name": "Market Size"}],
        ["锂电池回收利用"],
    )

    assert selected == [{
        "id": "section_0",
        "section_id": "section_0",
        "name": "锂电池回收利用",
        "content": "锂电池回收利用",
    }]


def test_agent_creation_does_not_overwrite_explicit_section_identity():
    source = Path("src/core/orchestrator/orchestrator.py").read_text(encoding="utf-8")
    assert 'if "section_id" not in context:' in source
    assert 'context["section_id"] = spec.output_keys[0]' in source


def test_scheduler_passes_semantic_agent_mapping_to_data_boundaries():
    source = Path("src/core/orchestrator/execution/engine.py").read_text(encoding="utf-8")
    assert "agent_aspect_map = {}" in source
    assert "self._agent_aspect_map = agent_aspect_map" in source
    assert "agent_section_map = {}" in source
    assert "self._agent_section_map = agent_section_map" in source
    assert 'agent_section_map=getattr(self, "_agent_aspect_map", {})' in source


def test_scheduler_persists_canonical_section_id_separately_from_semantic_aspect():
    source = Path("src/core/orchestrator/execution/engine.py").read_text(encoding="utf-8")
    assert 'getattr(self, "_agent_section_map", {}).get(_aid)' in source
    assert '_ar["section_id"] = _sid' in source


def test_dependent_section_does_not_shift_data_section_ids():
    selected = _select_section_details(
        [
            {"id": "executive_summary", "name": "Executive Summary"},
            {"id": "market_size", "name": "Market Size"},
            {"id": "competitive_landscape", "name": "Competitive Landscape"},
        ],
        ["执行摘要", "市场规模", "竞争格局"],
    )

    assert [item["section_id"] for item in selected] == [
        "synthesis_0", "section_0", "section_1"
    ]


def test_all_strategy_phases_carry_the_same_section_identity():
    source = Path("src/core/decomposition/strategies.py").read_text(encoding="utf-8")
    assert "normal_section_ids =" in source
    assert '"section_id": unit["section_id"]' in source
    assert '"section_id": f"synthesis_{synthesis_index}"' in source


def test_runtime_strategy_keeps_dependent_and_data_ids_aligned():
    from types import SimpleNamespace
    from src.core.decomposition.strategies import IndustryResearchStrategy, ResearchPhase

    requirement = SimpleNamespace(
        aspects=["执行摘要", "市场规模", "市场规模"],
        topic="锂电池",
        dynamic_fields={},
        section_details=[],
    )
    intent = SimpleNamespace(complexity=None, section_data_specs=[])
    plan = IndustryResearchStrategy().decompose(requirement, intent, {})

    collected = plan.phases[ResearchPhase.DATA_COLLECTION]
    assert [(item.context["aspect"], item.context["section_id"]) for item in collected] == [
        ("市场规模", "section_0"), ("市场规模", "section_1")
    ]
    synthesized = plan.phases[ResearchPhase.SYNTHESIS]
    assert [(item.context["aspect"], item.context["section_id"]) for item in synthesized] == [
        ("执行摘要", "synthesis_0")
    ]


def test_framework_subsection_points_survive_empty_llm_specs():
    from types import SimpleNamespace
    from src.core.decomposition.strategies import IndustryResearchStrategy, ResearchPhase

    requirement = SimpleNamespace(
        aspects=["市场规模"],
        topic="锂电池",
        dynamic_fields={},
        section_details=[{
            "section_id": "section_0",
            "name": "市场规模",
            "sub_sections": [{
                "id": "market_size_global",
                "name": "全球市场规模",
                "points": ["全球市场规模", "同比增速"],
            }],
        }],
    )
    intent = SimpleNamespace(complexity=None, section_data_specs=[])
    plan = IndustryResearchStrategy().decompose(requirement, intent, {})
    collection = plan.phases[ResearchPhase.DATA_COLLECTION][0]

    assert collection.context["data_needs"] == ["全球市场规模", "同比增速"]
    assert collection.context["search_data_needs"] == ["全球市场规模", "同比增速"]


def test_framework_tree_ids_do_not_override_canonical_strategy_ids():
    from types import SimpleNamespace
    from src.core.decomposition.strategies import IndustryResearchStrategy, ResearchPhase

    requirement = SimpleNamespace(
        aspects=["执行摘要", "市场规模"],
        topic="锂电池",
        dynamic_fields={},
        section_details=[
            {"id": "executive_summary", "name": "执行摘要", "sub_sections": []},
            {"id": "market_size", "name": "市场规模", "sub_sections": [
                {"id": "global_size", "name": "全球市场规模", "points": ["全球市场规模"]}
            ]},
        ],
    )
    intent = SimpleNamespace(complexity=None, section_data_specs=[])
    plan = IndustryResearchStrategy().decompose(requirement, intent, {})
    collection = plan.phases[ResearchPhase.DATA_COLLECTION][0]

    assert plan.section_data_specs[0].section_id == "section_0"
    assert collection.context["section_id"] == "section_0::global_size"


def test_coverage_reuses_search_synonyms_for_expanded_evidence():
    from src.core.orchestrator.execution.engine import ExecutionEngine

    engine = ExecutionEngine.__new__(ExecutionEngine)
    covered = engine._get_covered_needs(
        ["出货量", "市场份额"],
        [{"title": "动力电池交付量与市占率", "content": "行业交付量持续增长"}],
    )

    assert covered == {"出货量", "市场份额"}


def test_search_gateway_rejects_prompt_contaminated_queries_before_provider_call():
    from src.core.search.gateway import SearchGateway, SearchRequest

    assert SearchGateway._validate_query("锂电池 市场规模 2025") is None
    assert SearchGateway._validate_query("请判断以下内容是否足够支持报告结论：" + "数据" * 80)
    assert SearchGateway._validate_query("锂电池 数据缺口 请分析")


def test_scheduler_opaque_agent_ids_fallback_to_requirement_aspects():
    source = Path("src/core/orchestrator/execution/engine.py").read_text(encoding="utf-8")
    assert 'agent.agent_id.startswith("phase_")' in source
    assert '_requirement_aspects[_agent_index]' in source


def test_report_task_structure_normalizes_template_ids_to_runtime_ids():
    from src.core.orchestrator.orchestrator import ResearchOrchestrator

    structure = ResearchOrchestrator()._build_task_structure_from_section_details(
        [
            {"id": "executive_summary", "name": "执行摘要"},
            {"id": "market_size", "name": "市场规模", "sub_sections": [
                {"id": "global_size", "name": "全球市场规模", "points": ["市场规模"]},
            ]},
        ],
        "锂电池行业",
        "id-contract-test",
    )

    assert [item["section_id"] for item in structure["sections"]] == [
        "synthesis_0", "section_0"
    ]
    assert structure["sections"][0]["template_id"] == "executive_summary"
    assert structure["sections"][1]["template_id"] == "market_size"
    assert structure["sections"][1]["sub_sections"][0]["sub_section_id"] == "global_size"
    assert structure["sections"][1]["section_id"] == "section_0"


def test_legacy_routing_ids_are_normalized_before_report_join():
    from src.core.orchestrator.orchestrator import _normalize_task_structure_runtime_ids

    normalized = _normalize_task_structure_runtime_ids({
        "sections": [{"section_id": "section_0_市场规模", "content_dependency": []}],
        "dependencies": [],
        "critical_path": ["section_0_市场规模"],
        "parallel_groups": [["section_0_市场规模"]],
    })

    assert normalized["sections"][0]["section_id"] == "section_0"
    assert normalized["sections"][0]["legacy_section_id"] == "section_0_市场规模"
    assert normalized["critical_path"] == ["section_0"]
    assert normalized["parallel_groups"] == [["section_0"]]


def test_routing_normalizes_ids_before_lock_graph_creation():
    from src.core.task_structure import (
        ContentDependency,
        SectionRole,
        SectionSpec,
        TaskStructure,
        normalize_task_structure_runtime_ids,
    )

    structure = TaskStructure(
        task_id="id-contract-test",
        topic="锂电池行业",
        sections=[
            SectionSpec(
                section_id="section_0_市场规模",
                section_name="市场规模",
                section_role=SectionRole.ANALYSIS,
            ),
            SectionSpec(
                section_id="synthesis_0_摘要",
                section_name="摘要",
                section_role=SectionRole.SYNTHESIS,
            ),
        ],
        dependencies=[ContentDependency(
            from_section="section_0_市场规模",
            to_section="synthesis_0_摘要",
            dependency_type="synthesis",
        )],
        execution_graph={"synthesis_0_摘要": ["section_0_市场规模"]},
        parallel_groups=[["section_0_市场规模"], ["synthesis_0_摘要"]],
        critical_path=["section_0_市场规模", "synthesis_0_摘要"],
    )

    normalize_task_structure_runtime_ids(structure)

    assert [section.section_id for section in structure.sections] == [
        "section_0", "synthesis_0"
    ]
    assert structure.dependencies[0].from_section == "section_0"
    assert structure.dependencies[0].to_section == "synthesis_0"
    assert structure.execution_graph == {"synthesis_0": ["section_0"]}
    assert structure.critical_path == ["section_0", "synthesis_0"]
