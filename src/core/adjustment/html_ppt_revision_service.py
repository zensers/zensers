"""HTML-first PPT revision loop."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.core.adjustment.html_ppt_artifact_store import HtmlPptArtifactStore
from src.core.adjustment.ppt_auditor import PptAuditor, PptAuditReport


@dataclass
class HtmlPptRevisionRequest:
    task_id: str
    level: str = "L1"
    revision_type: str = "replace_text"
    slide_index: Optional[int] = None
    target_field: Optional[str] = None
    new_value: Optional[str] = None
    description: str = ""
    new_html: Optional[str] = None
    content_model: Optional[Dict[str, Any]] = None


@dataclass
class HtmlPptRevisionResult:
    success: bool
    level: str
    message: str = ""
    error: Optional[str] = None
    version: Optional[int] = None
    audit_report: Optional[Dict[str, Any]] = None
    recovery_action: Optional[str] = None


class HtmlPptRevisionService:
    def __init__(self, store: HtmlPptArtifactStore, auditor: Optional[PptAuditor] = None):
        self.store = store
        self.auditor = auditor or PptAuditor()

    def revise(self, request: HtmlPptRevisionRequest) -> HtmlPptRevisionResult:
        original = self.store.state()
        original_html = self.store.load_html()
        level = request.level or "L1"
        if level == "L0":
            report = self._audit(original_html)
            self.store.set_audit(report.to_dict())
            return HtmlPptRevisionResult(True, "L0", "HTML audit completed", audit_report=report.to_dict())
        if level.startswith("L5"):
            return HtmlPptRevisionResult(
                False, "L5", "HTML revision requires framework/data regeneration",
                error="requires_framework_regeneration", recovery_action="framework_regeneration",
            )
        try:
            revised = self._apply(original_html, request)
            report = self._audit(revised)
            report_dict = report.to_dict()
            if not report.passed:
                self.store.set_audit(report_dict)
                return HtmlPptRevisionResult(
                    False, level, "HTML audit failed; draft was not committed",
                    error="html_audit_failed", audit_report=report_dict,
                    recovery_action="rollback",
                )
            state = self.store.commit(
                revised, audit=report_dict, content_model=request.content_model,
            )
            return HtmlPptRevisionResult(
                True, level, "HTML revision committed and audited",
                version=state["version"], audit_report=report_dict,
            )
        except Exception as exc:
            self.store.restore(int(original["version"]))
            return HtmlPptRevisionResult(
                False, level, "HTML revision failed; draft restored", error=str(exc),
                recovery_action="rollback",
            )

    def confirm(self) -> Dict[str, Any]:
        report = self._audit(self.store.load_html())
        self.store.set_audit(report.to_dict())
        if not report.passed:
            raise ValueError("HTML audit failed; confirmation blocked")
        return self.store.confirm()

    def _audit(self, html: str) -> PptAuditReport:
        findings = self.auditor.audit_html(html)
        return PptAuditReport(
            passed=not any(item.severity == "error" for item in findings),
            findings=findings,
            checked=["html_render"],
        )

    def _apply(self, html: str, request: HtmlPptRevisionRequest) -> str:
        if request.level == "L1":
            if not request.new_value:
                raise ValueError("L1 HTML revision requires new_value")
            if request.target_field in ("title", "heading") and request.slide_index is not None:
                return self._replace_heading(html, request.slide_index, request.new_value)
            if request.description and request.new_value:
                return html.replace(request.description, request.new_value, 1)
            raise ValueError("L1 HTML revision requires target_field or description")
        if request.level == "L2":
            if request.new_html and request.slide_index is not None:
                return self._replace_slide(html, request.slide_index, request.new_html)
            raise ValueError("L2 HTML revision requires target slide HTML")
        if request.level == "L3":
            if not request.new_html or request.slide_index is None:
                raise ValueError("L3 HTML revision requires target slide HTML")
            return self._replace_slide(html, request.slide_index, request.new_html)
        if request.level == "L4":
            if not request.new_html:
                raise ValueError("L4 HTML revision requires complete HTML")
            return request.new_html
        raise ValueError(f"Unsupported HTML revision level: {request.level}")

    @staticmethod
    def _slide_pattern(index: int) -> re.Pattern:
        return re.compile(
            r"<section\b(?=[^>]*class=[\"'][^\"']*\bslide\b[^\"']*[\"'])[^>]*>.*?</section>",
            re.IGNORECASE | re.DOTALL,
        )

    def _replace_slide(self, html: str, index: int, replacement: str) -> str:
        matches = list(self._slide_pattern(index).finditer(html))
        if index < 0 or index >= len(matches):
            raise IndexError("HTML slide index out of range")
        match = matches[index]
        return html[:match.start()] + replacement + html[match.end():]

    def _replace_heading(self, html: str, index: int, new_value: str) -> str:
        matches = list(self._slide_pattern(index).finditer(html))
        if index < 0 or index >= len(matches):
            raise IndexError("HTML slide index out of range")
        section = matches[index].group(0)
        updated, count = re.subn(
            r"(<h[1-6]\b[^>]*>)(.*?)(</h[1-6]>)",
            lambda m: m.group(1) + new_value + m.group(3),
            section, count=1, flags=re.IGNORECASE | re.DOTALL,
        )
        if not count:
            raise ValueError("Target HTML slide has no heading")
        return html[:matches[index].start()] + updated + html[matches[index].end():]
