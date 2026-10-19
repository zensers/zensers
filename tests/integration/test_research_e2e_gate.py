"""P1-4 deterministic gate: validate evidence, lifecycle and phase manifest."""

import pytest


def _valid_case():
    phases = []
    for phase in ("collection", "analysis", "aggregation", "report_generation", "quality_check", "document_output"):
        phases.extend([
            {"event": "PHASE_START", "phase": phase},
            {"event": "PHASE_COMPLETE", "phase": phase},
        ])
    return {
        "state_sources": {
            "session": "completed",
            "progress_streamer": "completed",
            "task_persistence": "completed",
            "result_store": "completed",
        },
        "manifest": {"phases": phases},
        "report": {"sections": [{"id": "section_0", "evidence_ids": ["ev_1"]}]},
        "quality": {"l1_l5_issue_count_after": 0},
    }


def test_e2e_gate_accepts_complete_auditable_flow():
    from src.core.diagnostics.e2e_gate import validate_research_e2e

    result = validate_research_e2e(_valid_case())
    assert result["passed"] is True
    assert result["errors"] == []


def test_e2e_gate_rejects_state_divergence_and_missing_evidence():
    from src.core.diagnostics.e2e_gate import validate_research_e2e

    case = _valid_case()
    case["state_sources"]["result_store"] = "running"
    case["report"]["sections"][0]["evidence_ids"] = []
    result = validate_research_e2e(case)
    assert result["passed"] is False
    assert any("state_sources" in error for error in result["errors"])
    assert any("evidence" in error for error in result["errors"])


def test_e2e_gate_rejects_unclosed_phase():
    from src.core.diagnostics.e2e_gate import validate_research_e2e

    case = _valid_case()
    case["manifest"]["phases"] = [
        event for event in case["manifest"]["phases"]
        if not (event["phase"] == "document_output" and event["event"] == "PHASE_COMPLETE")
    ]
    result = validate_research_e2e(case)
    assert result["passed"] is False
    assert any("document_output" in error for error in result["errors"])
