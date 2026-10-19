"""Versioned, user-visible report context shared by agents and the web UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import copy

REPORT_PHASES = {
    "researching", "report_generating", "preview_ready",
    "awaiting_user_decision", "quality_checking", "revising",
    "completed", "failed",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _report_data(session: Dict[str, Any]) -> Dict[str, Any]:
    result = session.get("research_result") or {}
    if not isinstance(result, dict):
        return {}
    report = result.get("report")
    return report if isinstance(report, dict) else result


def _sections(session: Dict[str, Any]) -> list[dict]:
    report = _report_data(session)
    raw = report.get("sections") or []
    quality = session.get("quality_state") or {}
    scores = quality.get("section_scores", {}) if isinstance(quality, dict) else {}
    output = []
    for index, section in enumerate(raw):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or section.get("section_id") or f"section-{index + 1}")
        title = str(section.get("title") or section.get("name") or section_id)
        score = scores.get(title) or scores.get(section_id) or {}
        if not isinstance(score, dict):
            score = {}
        content = section.get("content") or section.get("body") or ""
        sources = section.get("sources") or section.get("references") or []
        output.append({
            "id": section_id,
            "title": title,
            "order": index,
            "status": section.get("status") or "ready",
            "word_count": len(str(content).split()),
            "source_count": len(sources) if isinstance(sources, list) else 0,
            "quality_status": score.get("status", "unknown"),
            "summary": section.get("summary") if isinstance(section.get("summary"), str) else None,
        })
    return output


def build_report_context(
    session_id: str,
    session: Dict[str, Any],
    *,
    phase: Optional[str] = None,
    document_version: Optional[str] = None,
    report_version_increment: bool = False,
    last_revision: Optional[dict] = None,
    pending_decision: Optional[dict] = None,
) -> dict:
    """Build a deliberately small and sanitized public snapshot."""
    previous = session.get("report_context") or {}
    previous_report_version = int(previous.get("report_version", 0) or 0)
    previous_revision = int(previous.get("context_revision", 0) or 0)
    result = session.get("research_result") or {}
    report = _report_data(session)
    quality_state = session.get("quality_state") or {}
    quality_state = quality_state if isinstance(quality_state, dict) else {}
    result_status = result.get("status") if isinstance(result, dict) else None

    inferred = phase
    if not inferred:
        session_status = str(session.get("status") or "").lower()
        status_phase = {
            "completed": "completed",
            "completed_with_warnings": "completed",
            "reporting": "report_generating",
            "document_generated": "preview_ready",
            "failed": "failed",
        }.get(session_status)
        previous_phase = previous.get("report_phase")
        # Repair stale pre-migration snapshots when a newer session state is
        # already available, while preserving an active revision/decision.
        if status_phase and (
            not previous_phase
            or previous_phase == "researching"
            or status_phase in {"completed", "failed"}
        ):
            inferred = status_phase
        else:
            inferred = previous_phase
        if not inferred:
            if result_status in ("completed", "completed_with_warnings"):
                inferred = "completed"
            elif report.get("sections"):
                inferred = "report_generating"
            else:
                inferred = "researching"
    if inferred not in REPORT_PHASES:
        inferred = "researching"

    quality_sections = quality_state.get("section_scores", {})
    open_issues = 0
    if isinstance(quality_sections, dict):
        for value in quality_sections.values():
            if isinstance(value, dict):
                open_issues += sum(
                    1 for issue in value.get("issues", [])
                    if isinstance(issue, dict) and issue.get("state", "open") == "open"
                )

    preview_url = previous.get("preview_url")
    try:
        from src.core.preview_storage import PreviewStorage
        if PreviewStorage.path(session_id).exists():
            preview_url = PreviewStorage.url(session_id)
    except Exception:
        pass

    context = {
        "schema_version": 1,
        "session_id": session_id,
        "report_id": str(session.get("report_id") or session_id),
        "report_version": previous_report_version + (1 if report_version_increment else 0),
        "report_phase": inferred,
        "document_type": session.get("output_format") or session.get("output_type"),
        "document_version": document_version or previous.get("document_version"),
        "preview_url": preview_url,
        "download_url": previous.get("download_url"),
        "topic": report.get("topic") or (session.get("research_context") or {}).get("topic") or session.get("user_input"),
        "sections": _sections(session),
        "quality": {
            "overall_score": quality_state.get("overall_score"),
            "overall_status": quality_state.get("overall_status", "unknown"),
            "open_issue_count": open_issues,
        },
        "pending_decision": pending_decision if pending_decision is not None else previous.get("pending_decision"),
        "last_revision": last_revision if last_revision is not None else previous.get("last_revision", {"status": "none", "request": None, "affected_sections": []}),
        "updated_at": _now(),
        "context_revision": previous_revision + 1,
    }
    return context


def update_report_context(
    session_id: str,
    session: Dict[str, Any],
    *,
    phase: Optional[str] = None,
    document_version: Optional[str] = None,
    report_version_increment: bool = False,
    last_revision: Optional[dict] = None,
    pending_decision: Optional[dict] = None,
    publish: bool = True,
) -> dict:
    """Persist first, then publish a report_context event."""
    from src.core.session_manager import SessionManager
    context = build_report_context(
        session_id, session, phase=phase, document_version=document_version,
        report_version_increment=report_version_increment,
        last_revision=last_revision, pending_decision=pending_decision,
    )
    session["report_context"] = copy.deepcopy(context)
    SessionManager.get_instance().force_save(session_id)
    if publish:
        from src.core.session_streamer import SessionStreamer
        SessionStreamer.push_report_context(session_id, context)
    return context
