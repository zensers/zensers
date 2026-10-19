import pytest

from src.core.orchestrator.execution.engine import ExecutionEngine
from src.core.orchestrator.orchestrator import _collect_report_coverage_warnings
from src.core.orchestrator.orchestrator import _normalize_task_structure_runtime_ids
from src.core.manifest_contract import ManifestContractError
from src.core.orchestrator.orchestrator import _audit_report_manifest_contract


def test_report_task_uses_manifest_order_and_keeps_missing_leaf_visible():
    manifest = [
        {"section_id": "section_0::tam", "title": "TAM", "role": "analysis", "required_metrics": ["市场规模"]},
        {"section_id": "section_0::cagr", "title": "CAGR", "role": "analysis", "required_metrics": ["增长率"]},
    ]
    task = ExecutionEngine._build_report_task(
        object(),
        {"task_id": "t1", "topic": "行业", "section_manifest": manifest},
        [{
            "success": True,
            "section_id": "section_0::tam",
            "content": "TAM evidence",
            "data_points": [],
            "sources": [],
        }],
    )

    assert [section["section_id"] for section in task["sections"]] == ["section_0::tam", "section_0::cagr"]
    assert task["sections"][1]["status"] == "failed"
    assert task["missing_section_ids"] == ["section_0::cagr"]
    assert task["research_result"]["section_manifest"] == manifest


def test_report_task_manifest_join_does_not_match_by_title_or_agent_id():
    manifest = [{"section_id": "section_0::tam", "title": "TAM", "role": "analysis"}]
    task = ExecutionEngine._build_report_task(
        object(),
        {"task_id": "t2", "topic": "行业", "section_manifest": manifest},
        [{"success": True, "agent_id": "phase_2_agent_0", "title": "TAM", "content": "wrong join"}],
    )
    assert task["sections"][0]["status"] == "failed"
    assert task["sections"][0]["content"] == ""


def test_report_task_rejects_unknown_exact_result_id():
    manifest = [{"section_id": "section_0::tam", "title": "TAM", "role": "analysis"}]
    with pytest.raises(ManifestContractError) as exc_info:
        ExecutionEngine._build_report_task(
            object(),
            {"task_id": "t2c", "topic": "行业", "section_manifest": manifest},
            [{"success": True, "section_id": "unknown", "content": "wrong join"}],
        )
    assert exc_info.value.code == "unknown_section_id"


def test_report_task_rejects_duplicate_manifest_ids_before_assembly():
    manifest = [
        {"section_id": "section_0::tam", "title": "TAM", "role": "analysis"},
        {"section_id": "section_0::tam", "title": "TAM duplicate", "role": "analysis"},
    ]
    with pytest.raises(ManifestContractError) as exc_info:
        ExecutionEngine._build_report_task(
            object(),
            {"task_id": "t2d", "topic": "行业", "section_manifest": manifest},
            [],
        )
    assert exc_info.value.code == "duplicate_section_id"


def test_final_report_boundary_runs_hard_manifest_audit_against_original_specs():
    requirement = type("Requirement", (), {"section_details": []})()
    task_structure = {
        "section_data_specs": [{
            "section_id": "section_0",
            "name": "市场规模",
            "sub_sections": [{"id": "tam", "name": "TAM"}],
        }],
        "section_manifest": [{
            "section_id": "section_0::tam",
            "output_slot": "body",
            "producer_agent_ids": {"analysis": ["analysis_0"]},
        }],
    }
    report = {"sections": [{"section_id": "section_0::tam", "content": "TAM"}]}
    audit = _audit_report_manifest_contract(
        requirement,
        task_structure,
        [{"agent_id": "analysis_0"}],
        {"analysis_0": {"agent_id": "analysis_0", "section_id": "section_0::tam"}},
        report,
    )
    assert audit["status"] == "passed"
    assert audit["planned_body_ids"] == ["section_0::tam"]


def test_final_report_boundary_does_not_downgrade_unknown_report_id():
    requirement = type("Requirement", (), {"section_details": []})()
    task_structure = {
        "section_data_specs": [{
            "section_id": "section_0",
            "name": "市场规模",
            "sub_sections": [{"id": "tam", "name": "TAM"}],
        }],
        "section_manifest": [{
            "section_id": "section_0::tam",
            "output_slot": "body",
            "producer_agent_ids": {"analysis": ["analysis_0"]},
        }],
    }
    with pytest.raises(ManifestContractError) as exc_info:
        _audit_report_manifest_contract(
            requirement,
            task_structure,
            [{"agent_id": "analysis_0"}],
            {"analysis_0": {"agent_id": "analysis_0", "section_id": "section_0::tam"}},
            {"sections": [
                {"section_id": "section_0::tam", "content": "TAM"},
                {"section_id": "unknown", "content": "bad"},
            ]},
        )
    assert exc_info.value.code == "unknown_section_id"


def test_final_report_boundary_rejects_manifest_title_mismatch():
    requirement = type("Requirement", (), {"section_details": []})()
    task_structure = {
        "section_data_specs": [{"section_id": "section_0", "name": "市场规模", "sub_sections": []}],
        "section_manifest": [{
            "section_id": "section_0",
            "title": "市场规模",
            "output_slot": "body",
            "producer_agent_ids": {"analysis": "analysis_0"},
        }],
    }
    with pytest.raises(ManifestContractError) as exc_info:
        _audit_report_manifest_contract(
            requirement,
            task_structure,
            [{"agent_id": "analysis_0"}],
            [{"section_id": "section_0"}],
            {"sections": [{"section_id": "section_0", "title": "数据精准修补", "content": "body"}]},
        )
    assert exc_info.value.code == "report_title_mismatch"


def test_final_audit_uses_expanded_runtime_sections_when_specs_keep_display_ids():
    """Raw framework specs must not split the final runtime identity space."""
    requirement = type("Requirement", (), {
        "section_details": [
            {"id": "市场规模与出货量", "name": "市场规模与出货量"},
            {"id": "品牌竞争格局", "name": "品牌竞争格局"},
        ]
    })()
    task_structure = {
        "sections": [
            {"section_id": "section_0", "section_name": "市场规模与出货量"},
            {"section_id": "section_1", "section_name": "品牌竞争格局"},
        ],
        "section_data_specs": [
            {"section_id": "市场规模与出货量", "name": "市场规模与出货量", "sub_sections": []},
            {"section_id": "品牌竞争格局", "name": "品牌竞争格局", "sub_sections": []},
        ],
        "section_manifest": [
            {"section_id": "section_0", "output_slot": "body", "producer_agent_ids": {"analysis": "a0"}},
            {"section_id": "section_1", "output_slot": "body", "producer_agent_ids": {"analysis": "a1"}},
        ],
    }
    report = {
        "sections": [
            {"section_id": "section_0", "content": "市场规模"},
            {"section_id": "section_1", "content": "品牌竞争"},
        ]
    }

    audit = _audit_report_manifest_contract(
        requirement,
        task_structure,
        [{"agent_id": "a0"}, {"agent_id": "a1"}],
        [{"section_id": "section_0"}, {"section_id": "section_1"}],
        report,
    )

    assert audit["status"] == "passed"
    assert audit["framework_leaf_ids"] == ["section_0", "section_1"]


def test_manifest_synthesis_uses_exact_id_and_dedicated_output_slots():
    manifest = [
        {"section_id": "a", "title": "市场规模", "role": "analysis", "output_slot": "body"},
        {"section_id": "s", "title": "任意标题", "role": "synthesis", "output_slot": "exec_summary"},
        {"section_id": "c", "title": "任意标题", "role": "synthesis", "output_slot": "conclusion"},
    ]
    task = ExecutionEngine._build_report_task(
        object(), {"task_id": "t3", "topic": "行业", "section_manifest": manifest},
        [
            {"success": True, "section_id": "a", "content": "body"},
            {"success": True, "section_id": "s", "content": "summary"},
            {"success": True, "section_id": "c", "content": "conclusion"},
        ],
    )
    assert task["exec_summary"] == "summary"
    assert task["conclusion"] == "conclusion"
    assert [item["section_id"] for item in task["sections"]] == ["a"]


def test_l0_manifest_requires_summary_and_conclusion_slots_even_when_body_exists():
    manifest = [
        {"section_id": "a", "title": "市场规模", "output_slot": "body"},
        {"section_id": "s", "title": "执行摘要", "output_slot": "exec_summary"},
        {"section_id": "c", "title": "研究结论", "output_slot": "conclusion"},
    ]
    report = {"sections": [{"section_id": "a", "content": "body"}], "exec_summary": "", "conclusion": ""}
    warnings = _collect_report_coverage_warnings(report, {"section_manifest": manifest})
    assert {item["section_id"] for item in warnings} == {"s", "c"}


def test_task_structure_id_normalization_keeps_manifest_in_same_identity_space():
    normalized = _normalize_task_structure_runtime_ids({
        "sections": [{"section_id": "section_0_market_size"}],
        "dependencies": [],
        "section_manifest": [{
            "section_id": "section_0_market_size",
            "parent_section_id": "section_0_market_size",
            "producer_agent_ids": {"analysis": "analysis_0"},
        }],
    })
    assert normalized["sections"][0]["section_id"] == "section_0"
    assert normalized["section_manifest"][0]["section_id"] == "section_0"
    assert normalized["section_manifest"][0]["parent_section_id"] == "section_0"
