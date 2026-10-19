from pathlib import Path

from src.core.orchestrator.orchestrator import (
    _collect_report_coverage_warnings,
    _normalize_report_section_ids,
    _update_research_result_terminal_state,
)
from src.core.storage.research_result_store import ResearchResultStore, ResearchStatus


def test_terminal_report_writeback_replaces_collection_shell(tmp_path: Path):
    store = ResearchResultStore(storage_path=str(tmp_path))
    task_id = "report_writeback_contract"
    store.save_result(
        task_id,
        {
            "topic": "锂电池行业市场规模",
            "data_points": [{"metric": "market_size", "value": "100"}],
            "sources": [{"title": "source", "url": "https://example.test/source"}],
        },
        status=ResearchStatus.IN_PROGRESS,
    )

    final_report = {
        "topic": "锂电池行业市场规模",
        "title": "锂电池行业市场规模",
        "sections": [
            {
                "id": "section_0::market_size_global",
                "section_id": "section_0::market_size_global",
                "title": "全球市场规模",
            }
        ],
        "sources": [{"title": "source", "url": "https://example.test/source"}],
    }
    _update_research_result_terminal_state(
        task_id,
        tmp_path,
        ResearchStatus.COMPLETED,
        output_format="docx",
        document_path="data/report.docx",
        final_result=final_report,
    )

    result = store.load_result(task_id)
    metadata = store.load_metadata(task_id)
    assert result["status"] == ResearchStatus.COMPLETED.value
    assert result["sections"][0]["section_id"] == "section_0::market_size_global"
    assert result["data_points"]
    assert metadata.status == ResearchStatus.COMPLETED
    assert "data/report.docx" in metadata.document_paths


def test_incremental_checkpoint_merges_sections_by_canonical_id(tmp_path: Path):
    store = ResearchResultStore(storage_path=str(tmp_path))
    task_id = "incremental_section_checkpoint"
    store.save_result(
        task_id,
        {
            "sections": [
                {"section_id": "section_0", "title": "市场规模", "content": "规模正文"},
                {"section_id": "section_1", "title": "竞争格局", "content": "竞争正文"},
                {"section_id": "section_2", "title": "风险", "content": "风险正文"},
            ]
        },
        status=ResearchStatus.IN_PROGRESS,
    )
    store.save_result(
        task_id,
        {
            "sections": [
                {"section_id": "section_1", "title": "竞争格局（修订）", "content": "更新后的竞争正文"},
            ]
        },
        status=ResearchStatus.IN_PROGRESS,
    )

    result = store.load_result(task_id)
    sections = {item["section_id"]: item for item in result["sections"]}
    assert set(sections) == {"section_0", "section_1", "section_2"}
    assert sections["section_0"]["content"] == "规模正文"
    assert sections["section_1"]["content"] == "更新后的竞争正文"
    assert sections["section_2"]["content"] == "风险正文"


def test_report_fallback_exposes_legacy_section_id_alias():
    report = _normalize_report_section_ids(
        {"sections": [{"id": "section_0", "title": "市场规模"}]}
    )
    assert report["sections"][0]["section_id"] == "section_0"


def test_coverage_warning_is_non_blocking_but_detects_missing_and_placeholder():
    warnings = _collect_report_coverage_warnings(
        {
            "sections": [
                {"section_id": "section_0", "title": "全球市场规模", "content": ""},
                {"section_id": "section_1", "title": "核心结论", "content": "本章节数据不足，无法生成完整分析"},
            ]
        },
        {"sections": [
            {"section_id": "section_0", "title": "全球市场规模"},
            {"section_id": "section_1", "title": "核心结论"},
            {"section_id": "section_2", "title": "动力电池需求"},
        ]},
    )
    assert {item["type"] for item in warnings} == {
        "chapter_content_missing", "placeholder_content", "missing_chapter"
    }


def test_coverage_warning_checks_nested_sections_independently():
    warnings = _collect_report_coverage_warnings(
        {
            "sections": [{
                "section_id": "section_0",
                "title": "市场分析",
                "content": "父章节正文",
                "subsections": [{
                    "section_id": "section_0::size",
                    "title": "市场规模",
                    "content": "本章节数据不足，无法生成完整分析",
                }],
            }]
        },
        {"sections": [{
            "section_id": "section_0",
            "title": "市场分析",
            "subsections": [{"section_id": "section_0::size", "title": "市场规模"}],
        }]},
    )
    nested = [item for item in warnings if item.get("section") == "市场规模"]
    assert {item["type"] for item in nested} == {"placeholder_content"}


def test_warning_terminal_state_is_persisted_as_warning_not_completed(tmp_path: Path):
    store = ResearchResultStore(storage_path=str(tmp_path))
    task_id = "warning_terminal_state"
    store.save_result(task_id, {"topic": "t", "sections": []}, status=ResearchStatus.IN_PROGRESS)
    _update_research_result_terminal_state(
        task_id, tmp_path, ResearchStatus.COMPLETED_WITH_WARNINGS,
        final_result={"topic": "t", "sections": [], "coverage_warnings": [{"type": "missing_chapter"}]},
    )
    assert store.load_metadata(task_id).status == ResearchStatus.COMPLETED_WITH_WARNINGS


def test_quality_gate_metadata_survives_result_persistence(tmp_path: Path):
    store = ResearchResultStore(storage_path=str(tmp_path))
    task_id = "quality_gate_metadata"
    store.save_result(task_id, {"topic": "t", "sections": []}, status=ResearchStatus.IN_PROGRESS)

    store.save_result(
        task_id,
        {
            "topic": "t",
            "sections": [],
            "quality_gate_status": "blocked",
            "formal_complete": False,
        },
        status=ResearchStatus.COMPLETED_WITH_WARNINGS,
    )

    result = store.load_result(task_id)
    assert result["quality_gate_status"] == "blocked"
    assert result["formal_complete"] is False


def test_terminal_writeback_persists_latest_artifact_manifest(tmp_path: Path):
    store = ResearchResultStore(storage_path=str(tmp_path))
    task_id = "artifact_manifest_contract"
    store.save_result(task_id, {"topic": "t", "sections": []}, status=ResearchStatus.IN_PROGRESS)
    artifact_path = tmp_path / "report_v2.html"
    artifact_path.write_text("<html>v2</html>", encoding="utf-8")

    _update_research_result_terminal_state(
        task_id,
        tmp_path,
        ResearchStatus.COMPLETED_WITH_WARNINGS,
        output_format="html",
        document_path=str(artifact_path),
        final_result={"topic": "t", "sections": [], "report_version": 2},
    )

    result = store.load_result(task_id)
    assert result["output_path"] == str(artifact_path)
    assert result["document_path"] == str(artifact_path)
    assert result["artifact_manifest"][0]["path"] == str(artifact_path)
    assert result["artifact_manifest"][0]["status"] == "ready"
    assert result["artifact_manifest"][0]["content_hash"]
    assert result["artifact_manifest"][0]["artifact_hash"] == result["artifact_manifest"][0]["content_hash"]
    assert result["artifact_manifest"][0]["manifest_hash"]
    assert result["artifact_manifest"][0]["report_content_hash"]


def test_terminal_writeback_enriches_existing_html_and_docx_artifacts(tmp_path: Path):
    store = ResearchResultStore(storage_path=str(tmp_path))
    task_id = "dual_artifact_manifest_contract"
    store.save_result(task_id, {"topic": "t", "sections": []}, status=ResearchStatus.IN_PROGRESS)
    html_path = tmp_path / "report.html"
    docx_path = tmp_path / "report.docx"
    html_path.write_text("<html>same report</html>", encoding="utf-8")
    docx_path.write_bytes(b"same report")
    final_result = {
        "topic": "t",
        "sections": [{"section_id": "section_0", "content": "正文"}],
        "report_version": "v2",
        "manifest_hash": "manifest-v2",
        "report_content_hash": "content-v2",
        "artifact_manifest": [
            {"path": str(html_path), "format": "html", "report_version": "v2"},
            {"path": str(docx_path), "format": "docx", "report_version": "v2"},
        ],
    }
    _update_research_result_terminal_state(
        task_id,
        tmp_path,
        ResearchStatus.COMPLETED,
        output_format="docx",
        document_path=str(docx_path),
        final_result=final_result,
    )
    artifacts = store.load_result(task_id)["artifact_manifest"]
    by_path = {item["path"]: item for item in artifacts}
    assert set(by_path) == {str(html_path), str(docx_path)}
    assert all(item["artifact_hash"] for item in by_path.values())
    assert {item["manifest_hash"] for item in by_path.values()} == {"manifest-v2"}
    assert {item["report_content_hash"] for item in by_path.values()} == {"content-v2"}
