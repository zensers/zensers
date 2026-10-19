"""故障注入测试：Manifest、执行结果、报告和产物必须使用同一契约。"""

import pytest

from src.core.manifest_contract import ManifestContractError, validate_manifest_contract


def _valid_inputs():
    framework_tree = [
        {
            "node_id": "section_0",
            "title": "市场规模",
            "sub_sections": [
                {"node_id": "tam", "title": "TAM"},
                {"node_id": "cagr", "title": "CAGR"},
            ],
        }
    ]
    manifest = [
        {
            "section_id": "section_0::tam",
            "parent_section_id": "section_0",
            "sub_section_id": "tam",
            "output_slot": "body",
            "producer_agent_ids": {
                "data_collection": ["collect_tam"],
                "validation": ["validate_tam"],
                "analysis": ["analyze_tam"],
            },
        },
        {
            "section_id": "section_0::cagr",
            "parent_section_id": "section_0",
            "sub_section_id": "cagr",
            "output_slot": "body",
            "producer_agent_ids": {
                "data_collection": ["collect_cagr"],
                "validation": ["validate_cagr"],
                "analysis": ["analyze_cagr"],
            },
        },
        {
            "section_id": "synthesis_0",
            "output_slot": "exec_summary",
            "producer_agent_ids": {"synthesis": ["synthesize_summary"]},
        },
        {
            "section_id": "synthesis_1",
            "output_slot": "conclusion",
            "producer_agent_ids": {"synthesis": ["synthesize_conclusion"]},
        },
    ]
    created_agents = [
        {"agent_id": agent_id}
        for agent_id in (
            "collect_tam", "validate_tam", "analyze_tam",
            "collect_cagr", "validate_cagr", "analyze_cagr",
            "synthesize_summary", "synthesize_conclusion",
        )
    ]
    execution_results = [
        {"section_id": "section_0::tam", "success": True},
        {"section_id": "section_0::cagr", "success": True},
        {"section_id": "synthesis_0", "success": True},
        {"section_id": "synthesis_1", "success": True},
    ]
    report = {
        "sections": [
            {"section_id": "section_0::tam", "content": "TAM"},
            {"section_id": "section_0::cagr", "content": "CAGR"},
        ],
        "exec_summary": "摘要",
        "conclusion": "结论",
    }
    artifacts = [
        {
            "format": "html",
            "report_version": "v1",
            "manifest_hash": "m1",
            "report_content_hash": "r1",
            "artifact_hash": "h1",
        },
        {
            "format": "docx",
            "report_version": "v1",
            "manifest_hash": "m1",
            "report_content_hash": "r1",
            "artifact_hash": "d1",
        },
    ]
    return framework_tree, manifest, created_agents, execution_results, report, artifacts


def test_valid_contract_flattens_list_producers_and_passes():
    result = validate_manifest_contract(*_valid_inputs())

    assert result.status == "passed"
    assert result.planned_body_ids == {"section_0::tam", "section_0::cagr"}
    assert result.actual_body_ids == result.planned_body_ids
    assert result.missing_producers == set()


def test_contract_accepts_a_single_root_framework_object():
    inputs = list(_valid_inputs())
    inputs[0] = inputs[0][0]
    result = validate_manifest_contract(*inputs)
    assert result.status == "passed"


def test_contract_rejects_duplicate_framework_nodes():
    inputs = list(_valid_inputs())
    inputs[0] = [inputs[0][0], dict(inputs[0][0])]
    with pytest.raises(ManifestContractError) as exc_info:
        validate_manifest_contract(*inputs)
    assert exc_info.value.code == "duplicate_section_id"


def test_contract_rejects_report_section_without_an_id():
    inputs = list(_valid_inputs())
    inputs[4]["sections"].append({"content": "unbound"})
    with pytest.raises(ManifestContractError) as exc_info:
        validate_manifest_contract(*inputs)
    assert exc_info.value.code == "unknown_section_id"


def test_contract_allows_multiple_phase_results_for_one_section_when_result_ids_differ():
    inputs = list(_valid_inputs())
    inputs[3] = [
        {"result_id": "r-tam-collect", "agent_id": "collect_tam", "section_id": "section_0::tam"},
        {"result_id": "r-tam-analyze", "agent_id": "analyze_tam", "section_id": "section_0::tam"},
        {"result_id": "r-cagr", "agent_id": "analyze_cagr", "section_id": "section_0::cagr"},
        {"result_id": "r-summary", "agent_id": "synthesize_summary", "section_id": "synthesis_0"},
        {"result_id": "r-conclusion", "agent_id": "synthesize_conclusion", "section_id": "synthesis_1"},
    ]
    result = validate_manifest_contract(*inputs)
    assert result.status == "passed"


def test_contract_rejects_duplicate_result_id_even_when_section_is_same():
    inputs = list(_valid_inputs())
    inputs[3] = [
        {"result_id": "duplicate", "agent_id": "collect_tam", "section_id": "section_0::tam"},
        {"result_id": "duplicate", "agent_id": "analyze_tam", "section_id": "section_0::tam"},
        *inputs[3][1:],
    ]
    with pytest.raises(ManifestContractError) as exc_info:
        validate_manifest_contract(*inputs)
    assert exc_info.value.code == "duplicate_section_id"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("unknown_report_id", "unknown_section_id"),
        ("duplicate_manifest_id", "duplicate_section_id"),
        ("missing_producer", "agent_contract_failed"),
        ("missing_summary", "report_coverage_failed"),
        ("artifact_hash_mismatch", "artifact_version_mismatch"),
    ],
)
def test_contract_failures_are_hard_failures(mutation, code):
    inputs = list(_valid_inputs())
    if mutation == "unknown_report_id":
        inputs[4]["sections"].append({"section_id": "unknown", "content": "x"})
    elif mutation == "duplicate_manifest_id":
        inputs[1].append(dict(inputs[1][0]))
    elif mutation == "missing_producer":
        inputs[2] = [agent for agent in inputs[2] if agent["agent_id"] != "analyze_cagr"]
    elif mutation == "missing_summary":
        inputs[4]["exec_summary"] = ""
    elif mutation == "artifact_hash_mismatch":
        inputs[5][1]["report_content_hash"] = "r2"

    with pytest.raises(ManifestContractError) as exc_info:
        validate_manifest_contract(*inputs)
    assert exc_info.value.code == code
