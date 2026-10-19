from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator
from src.core.orchestrator.orchestrator import ResearchOrchestrator


def test_manifest_is_the_aggregation_join_contract_for_leaf_sections():
    manifest = [
        {"section_id": "section_0::tam", "parent_section_id": "section_0", "sub_section_id": "tam", "title": "TAM"},
        {"section_id": "section_0::cagr", "parent_section_id": "section_0", "sub_section_id": "cagr", "title": "CAGR"},
    ]
    details = ResearchOrchestrator._aggregation_section_details(
        [{"id": "section_0", "name": "市场规模", "sub_sections": [{"id": "tam", "name": "TAM"}]}],
        manifest,
    )
    assert [item["id"] for item in details] == ["section_0::tam", "section_0::cagr"]
    assert all(item["sub_sections"] == [] for item in details)

    aggregated = ResultAggregator().aggregate(
        {
            "analysis_tam": {
                "agent_id": "analysis_tam",
                "section_id": "section_0::tam",
                "content": "TAM 为 100 亿元，来源为公开统计数据。",
            },
            "analysis_cagr": {
                "agent_id": "analysis_cagr",
                "section_id": "section_0::cagr",
                "content": "CAGR 为 12%，来源为公开统计数据。",
            },
        },
        section_details=details,
    ).to_dict()

    sections = aggregated["sections"]
    assert [section["id"] for section in sections] == ["section_0::tam", "section_0::cagr"]
    assert all("本章节数据不足" not in section["content"] for section in sections)


def test_legacy_structure_freezes_each_subsection_in_manifest():
    structure = ResearchOrchestrator._build_task_structure_from_section_details(
        object.__new__(ResearchOrchestrator),
        [{
            "id": "market",
            "name": "市场规模",
            "sub_sections": [
                {"id": "tam", "name": "TAM", "points": ["规模"]},
                {"id": "cagr", "name": "CAGR", "points": ["增长率"]},
            ],
        }],
        "新能源汽车",
        "task-1",
    )
    assert [item["section_id"] for item in structure["section_manifest"]] == [
        "section_0::tam", "section_0::cagr"
    ]
    assert structure["section_manifest"][1]["required_metrics"] == ["增长率"]
