from typing import List, Dict, Any
from dataclasses import asdict
from datetime import datetime

from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint
from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry


def sections_to_chapters(sections: List[Dict]) -> List[ChapterWriteOutput]:
    key_conclusions_extractor = ChapterWriter._extract_conclusions
    chapters = []
    for sec in sections:
        chapter_id = str(sec.get("id", "") or sec.get("section_id", ""))
        raw_data_points = sec.get("data_points")
        if raw_data_points is None:
            raw_data_points = sec.get("data_points_used", [])
        data_points = []
        for raw_point in raw_data_points or []:
            if isinstance(raw_point, DataPoint):
                point = raw_point
            elif isinstance(raw_point, dict):
                # Rehydrate the complete evidence contract.  Older persisted
                # reports may omit newer fields, so let DataPoint defaults
                # fill those fields without discarding known provenance.
                allowed = set(DataPoint.__dataclass_fields__)
                point = DataPoint(**{
                    key: value for key, value in raw_point.items()
                    if key in allowed
                })
            else:
                continue
            point.chapter_id = point.chapter_id or chapter_id
            point.sub_section_id = point.sub_section_id or str(
                sec.get("sub_section_id", "") or ""
            )
            data_points.append(point)
        key_conclusions = sec.get("key_conclusions", [])
        if not key_conclusions and sec.get("content"):
            key_conclusions = key_conclusions_extractor(sec.get("content", ""))
        chapters.append(ChapterWriteOutput(
            chapter_id=chapter_id,
            title=sec.get("title", sec.get("name", "")),
            content=sec.get("content", ""),
            data_points_used=data_points,
            key_conclusions=key_conclusions,
            status=sec.get("status", "ready") or "ready",
            error=sec.get("error", "") or "",
        ))
    return chapters


def restore_data_registry(session) -> DataRegistry:
    snapshot = session.get("_data_registry_snapshot")
    if snapshot:
        return DataRegistry.from_snapshot(snapshot)
    return DataRegistry()


def get_framework_config(session) -> Dict:
    cached = session.get("_framework_config")
    if cached:
        return cached
    try:
        from src.core.research_framework_manager import get_framework_config as _get_fc
        output_type = session.get("output_type") or session.get("research_context", {}).get("framework", {}).get("output_type", "industry_report")
        fc_obj = _get_fc(output_type)
        return {
            "name": fc_obj.name,
            "description": fc_obj.description,
            "section_weights": fc_obj.section_weights,
            "interaction_parameters": fc_obj.interaction_parameters,
        }
    except Exception:
        return {"name": "通用研究报告", "description": "通用研究"}


def get_task_structure(session) -> Dict:
    cached = session.get("_task_structure")
    if cached:
        return cached
    research_context = session.get("research_context", {})
    return {
        "topic": research_context.get("topic", ""),
        "directions": research_context.get("directions", []),
        "framework": research_context.get("framework"),
    }


def apply_revision_to_session(session, result, chapters, data_registry):
    report = session.setdefault("research_result", {}).setdefault("report", {})
    updated_sections = []
    for ch in chapters:
        updated_sections.append({
            "id": ch.chapter_id,
            "name": ch.title,
            "title": ch.title,
            "content": ch.content,
            "data_points": [asdict(dp) for dp in ch.data_points_used],
            "key_conclusions": ch.key_conclusions,
        })
    report["sections"] = updated_sections
    # Keep both projections synchronized. Older consumers and result.json use
    # top-level sections, while revision/report APIs use report.sections.
    session["research_result"]["sections"] = list(updated_sections)
    session["_data_registry_snapshot"] = data_registry.to_snapshot()
    revision_record = {
        "timestamp": datetime.now().isoformat(),
        "chapters_revised": len(result.get("chapter_results", [])),
        "global_review_score": result.get("global_review_score", 0),
        "global_review_passed": result.get("global_review_passed", False),
    }
    session.setdefault("_revision_history", []).append(revision_record)
