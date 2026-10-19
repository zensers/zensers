"""Deterministic acceptance checks for the research E2E pipeline."""

from typing import Any, Dict, Iterable, List


_DEFAULT_PHASES = (
    "collection", "analysis", "aggregation", "report_generation",
    "quality_check", "document_output",
)


def _status_family(value: Any) -> str:
    value = str(value or "").lower()
    if value in {"completed", "completed_with_warnings", "success"}:
        return "completed"
    if value in {"paused", "interrupted"}:
        return "paused"
    return value


def validate_research_e2e(
    case: Dict[str, Any], expected_phases: Iterable[str] = _DEFAULT_PHASES,
) -> Dict[str, Any]:
    """Return explainable gate errors instead of silently skipping prerequisites."""
    errors: List[str] = []
    states = case.get("state_sources") or {}
    required_states = ("session", "progress_streamer", "task_persistence", "result_store")
    missing_states = [name for name in required_states if name not in states]
    if missing_states:
        errors.append(f"state_sources missing: {', '.join(missing_states)}")
    else:
        families = {_status_family(states[name]) for name in required_states}
        if len(families) != 1:
            errors.append(f"state_sources diverged: {states}")

    report = case.get("report") or {}
    sections = report.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("report sections are empty")
    else:
        seen = set()
        for index, section in enumerate(sections):
            if not isinstance(section, dict) or not section.get("id"):
                errors.append(f"section {index} has no stable id")
                continue
            section_id = str(section["id"])
            if section_id in seen:
                errors.append(f"duplicate section id: {section_id}")
            seen.add(section_id)
            if not section.get("evidence_ids"):
                errors.append(f"section {section_id} has no evidence ids")

    events = case.get("manifest", {}).get("phases", [])
    by_phase: Dict[str, set] = {}
    for event in events if isinstance(events, list) else []:
        if isinstance(event, dict) and event.get("phase"):
            by_phase.setdefault(event["phase"], set()).add(event.get("event"))
    for phase in expected_phases:
        event_set = by_phase.get(phase, set())
        if "PHASE_START" not in event_set:
            errors.append(f"phase {phase} missing PHASE_START")
        if not ({"PHASE_COMPLETE", "PHASE_FAILED"} & event_set):
            errors.append(f"phase {phase} has no terminal boundary event")

    quality = case.get("quality") or {}
    if quality.get("l1_l5_issue_count_after") not in (None, 0):
        errors.append("L1-L5 issues remain after repair")

    return {"passed": not errors, "errors": errors}
