from types import SimpleNamespace

from src.agents.fixed_agents.report_upgrade.coverage_checker import ChapterCoverageChecker
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterRequirement, ReportEvidenceContext,
)
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator


def test_coverage_distinguishes_raw_search_from_external_gap():
    checker = ChapterCoverageChecker()
    requirement = ChapterRequirement(
        section_id="market", required_metrics=["forecast_growth_rate"],
    )
    context = ReportEvidenceContext(raw_search_results=[{
        "title": "Industry outlook",
        "snippet": "forecast_growth_rate reached 12% in 2025",
        "url": "https://example.test/outlook",
    }])
    coverage = checker.check(requirement, {}, context)
    assert coverage.available_in_raw_search == ["forecast_growth_rate"]
    assert coverage.external_search_required is False
    assert coverage.missing_metrics == []


def test_context_reads_legacy_sources_and_assigns_evidence_identity():
    aggregate = SimpleNamespace(
        data={"market": {"content": "初稿"}},
        sources=[{
            "title": "Legacy source",
            "url": "https://example.test/legacy",
            "snippet": "market size 100",
        }],
        raw_search_results=[],
        evidence_registry={},
    )
    context = ReportOrchestrator._build_evidence_context(
        aggregate, {"sections": [{"section_id": "market"}]},
    )
    assert len(context.raw_search_results) == 1
    assert context.raw_search_results[0]["evidence_id"].startswith("ev_")
    assert context.raw_search_results[0]["provenance_id"].startswith("prov_")


def test_context_provenance_is_task_scoped():
    aggregate = SimpleNamespace(
        data={}, sources=[{"title": "S", "url": "https://example.test/s", "snippet": "x"}],
        raw_search_results=[], evidence_registry={},
    )
    context = ReportOrchestrator._build_evidence_context(
        aggregate, {"sections": []}, task_id="task-42",
    )
    assert context.raw_search_results[0]["provenance_id"] == \
        ReportOrchestrator._ensure_source_evidence_identity(
            aggregate.sources, task_id="task-42",
        )[0]["provenance_id"]


def test_context_reads_legacy_dict_aggregate_without_dropping_evidence():
    aggregate = {
        "data": {"market": {"content": "初稿"}},
        "raw_search_results": [{
            "title": "Raw result",
            "url": "https://example.test/raw",
            "snippet": "market size 100",
        }],
        "evidence_registry": {"ev_existing": {"url": "https://example.test/raw"}},
    }
    context = ReportOrchestrator._build_evidence_context(
        aggregate, {"sections": []}, task_id="legacy-task",
    )
    assert context.structured_data == aggregate["data"]
    assert len(context.raw_search_results) == 1
    assert context.raw_search_results[0]["evidence_id"].startswith("ev_")
    assert "ev_existing" in context.evidence_registry


def test_subsections_expand_into_independent_chapter_specs():
    specs = ReportOrchestrator._iter_report_chapter_specs([{
        "section_id": "market",
        "section_name": "市场分析",
        "sub_sections": [
            {"sub_section_id": "size", "name": "市场规模", "required_metrics": ["TAM"]},
            {"sub_section_id": "growth", "name": "市场增长", "required_metrics": ["CAGR"]},
        ],
    }])
    assert [spec["section_id"] for spec in specs] == ["market::size", "market::growth"]
    assert [spec["sub_section_id"] for spec in specs] == ["size", "growth"]
    assert all(spec["parent_section_id"] == "market" for spec in specs)
    assert specs[0]["sub_section_requirements"][0]["required_metrics"] == ["TAM"]
