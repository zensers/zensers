"""Deterministic integration checks for the report evidence pipeline."""

from src.agents.fixed_agents.report_upgrade.coverage_checker import ChapterCoverageChecker
from src.agents.fixed_agents.report_upgrade.models import ChapterRequirement
from src.agents.fixed_agents.report_upgrade.report_integrity import ReportIntegrityChecker
from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator


def test_aggregator_to_coverage_preserves_raw_search_envelope():
    aggregated = ResultAggregator().aggregate({
        "market_agent": {
            "content": "分析初稿",
            "sources": [],
            "search_results": {
                "searches": [{
                    "query": "market growth",
                    "results": [{
                        "title": "Official outlook",
                        "url": "https://example.test/outlook",
                        "snippet": "forecast_growth_rate is 12%",
                        "evidence_id": "ev_1",
                        "provenance_id": "prov_1",
                    }],
                }],
            },
        }
    })
    assert aggregated.raw_search_results[0]["evidence_id"] == "ev_1"
    assert aggregated.raw_search_results[0]["evidence_excerpt"]

    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
    context = ReportOrchestrator._build_evidence_context(
        aggregated, {"sections": [{"section_id": "market"}]}, task_id="task-1",
    )
    coverage = ChapterCoverageChecker().check(
        ChapterRequirement("market", required_metrics=["forecast_growth_rate"]),
        {}, context,
    )
    assert coverage.available_in_raw_search == ["forecast_growth_rate"]
    assert coverage.external_search_required is False


def test_integrity_gate_exposes_claim_ownership():
    result = ReportIntegrityChecker().check({
        "sections": [
            {"id": "market", "key_conclusions": ["市场规模持续增长"], "data_points": []},
            {"id": "trend", "key_conclusions": ["市场规模持续增长"], "data_points": []},
        ]
    })
    assert result["passed"] is False
    assert result["issues"][0]["primary_section_id"] == "market"
