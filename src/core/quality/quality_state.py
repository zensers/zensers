# -*- coding: utf-8 -*-
"""
质检状态模型
============

定义质检反馈交互修订系统的核心数据模型。

设计文档: docs/2026-06-01-quality-feedback-revision-design.md
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field
import hashlib


class QualityIssue(BaseModel):
    id: str
    type: Literal["completeness", "accuracy", "consistency", "format", "hallucination"]
    severity: Literal["high", "medium", "low"]
    message: str
    section: str
    state: Literal["open", "dismissed", "revising", "resolved", "max_retries_reached", "accepted"] = "open"
    revision_count: int = 0


QUALITY_PASS_THRESHOLD = 60


class SectionScore(BaseModel):
    score: float = 0.0
    status: Literal["passed", "warning", "empty"] = "warning"
    issues: List[QualityIssue] = Field(default_factory=list)


class VersionInfo(BaseModel):
    id: str
    created_at: str = ""
    html_path: str = ""
    md_path: str = ""
    quality_state_snapshot: dict = Field(default_factory=dict)
    overall_score: float = 0.0
    label: str = ""


class QualityState(BaseModel):
    phase: Literal["reviewing", "revising", "confirmed"] = "reviewing"
    overall_score: float = 0.0
    overall_status: Literal["passed", "warning"] = "warning"
    section_scores: Dict[str, SectionScore] = Field(default_factory=dict)
    version_stack: List[VersionInfo] = Field(default_factory=list)
    current_version: str = "v0"


def generate_issue_id(section: str, issue_type: str, message: str) -> str:
    raw = f"{section}|{issue_type}|{message}"
    hash_hex = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]
    return f"q-{hash_hex}"


def merge_issues_on_recheck(
    existing_sections: Dict[str, SectionScore],
    new_section_results: Dict[str, dict],
) -> Dict[str, SectionScore]:
    merged: Dict[str, SectionScore] = {}

    for section_name, new_data in new_section_results.items():
        new_issues_raw = new_data.get("issues", [])
        new_issues_by_id: Dict[str, dict] = {}
        for raw_issue in new_issues_raw:
            iid = generate_issue_id(
                section_name,
                raw_issue.get("type", ""),
                raw_issue.get("message", ""),
            )
            raw_issue["id"] = iid
            raw_issue["section"] = section_name
            if "state" not in raw_issue:
                raw_issue["state"] = "open"
            new_issues_by_id[iid] = raw_issue

        existing_section = existing_sections.get(section_name)
        existing_issue_map: Dict[str, QualityIssue] = {}
        if existing_section:
            for iss in existing_section.issues:
                existing_issue_map[iss.id] = iss

        final_issues: List[QualityIssue] = []
        for iid, raw in new_issues_by_id.items():
            if iid in existing_issue_map:
                existing = existing_issue_map[iid]
                if existing.state == "revising":
                    existing = QualityIssue(
                        id=existing.id,
                        type=existing.type,
                        severity=existing.severity,
                        message=existing.message,
                        section=existing.section,
                        state="open",
                        revision_count=existing.revision_count,
                    )
                final_issues.append(existing)
            else:
                final_issues.append(QualityIssue(**raw))

        merged[section_name] = SectionScore(
            score=new_data.get("score", 0.0),
            status=new_data.get("status", "warning"),
            issues=final_issues,
        )

    for section_name, existing_section in existing_sections.items():
        if section_name not in merged:
            merged[section_name] = existing_section

    return merged
