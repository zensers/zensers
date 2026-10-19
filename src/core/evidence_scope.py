"""Chapter-scoped evidence selection for analysis agents.

This module intentionally lives outside ``src.core.orchestrator``.  Importing
the orchestrator package eagerly imports the agent factory, so placing this
small value object under the orchestrator package creates a circular import
when ``GenericAgent`` is loaded.
"""

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Dict, Iterable, List, Set, Tuple


@dataclass
class EvidenceScope:
    section_id: str
    allowed_source_agents: Set[str] = field(default_factory=set)
    required_metrics: Set[str] = field(default_factory=set)

    def _key(self, item: Dict[str, Any]) -> str:
        for field_name in ("evidence_id", "provenance_id", "data_id"):
            stable_id = str(item.get(field_name) or "").strip()
            if stable_id:
                # Once issued, the evidence identity remains stable while
                # later passes enrich value/scope/source fields.
                payload = f"{field_name}:{stable_id}"
                return "identity:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
        payload = json.dumps(
            [item.get("url"), item.get("source_url"), item.get("title"),
             item.get("metric"), item.get("content"), item.get("data"), item.get("value")],
            ensure_ascii=False, sort_keys=True, default=str,
        )
        return "hash:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _has_payload(item: Dict[str, Any]) -> bool:
        return bool(
            str(item.get("content") or "").strip()
            or item.get("data") is not None
            or item.get("value") is not None
            or str(item.get("evidence_excerpt") or "").strip()
        )

    def _is_high_value(self, item: Dict[str, Any]) -> bool:
        try:
            quality_score = float(item.get("quality_score") or 0)
        except (TypeError, ValueError):
            quality_score = 0.0
        return bool(
            item.get("is_canonical")
            or item.get("is_validated")
            or item.get("validated")
            or quality_score >= 90
            or str(item.get("caliber") or "").lower() in {"canonical", "validated", "校准", "已校准"}
        )

    def _metric_matches(self, item: Dict[str, Any]) -> bool:
        if not self.required_metrics:
            return True
        metric_text = " ".join(
            str(item.get(field_name) or "")
            for field_name in ("metric", "data_need", "title", "content")
        ).lower()
        return any(str(metric).lower() in metric_text for metric in self.required_metrics)

    def select(self, records: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        selected: List[Dict[str, Any]] = []
        seen = set()
        audit = {
            "input": 0, "excluded_invalid": 0, "excluded_by_dependency": 0,
            "excluded_by_section": 0, "excluded_duplicate": 0,
            "retained_high_value": 0,
        }
        for raw in records or []:
            audit["input"] += 1
            if not isinstance(raw, dict) or not self._has_payload(raw):
                audit["excluded_invalid"] += 1
                continue
            source_agent = str(raw.get("source_agent_id") or raw.get("agent_id") or "").strip()
            record_section = str(raw.get("section_id") or "").strip()
            high_value = self._is_high_value(raw)
            source_allowed = source_agent in self.allowed_source_agents
            section_allowed = not record_section or record_section == self.section_id
            metric_allowed = self._metric_matches(raw)
            explicit_metric = bool(str(raw.get("metric") or "").strip() or str(raw.get("data_need") or "").strip())
            is_shared_high_value = bool(
                raw.get("is_canonical") or raw.get("is_validated") or raw.get("validated")
            ) or source_agent.lower() in {"shared_memory", "databus", "data_bus"}
            shared_exception = (
                high_value and is_shared_high_value and section_allowed and metric_allowed
            )
            if not source_allowed and not shared_exception:
                audit["excluded_by_dependency"] += 1
                continue
            if not section_allowed:
                audit["excluded_by_section"] += 1
                continue
            if not metric_allowed and explicit_metric and not high_value:
                audit["excluded_by_section"] += 1
                continue
            key = self._key(raw)
            if key in seen:
                audit["excluded_duplicate"] += 1
                continue
            seen.add(key)
            item = dict(raw)
            if high_value:
                item["evidence_priority"] = "high"
                audit["retained_high_value"] += 1
            selected.append(item)

        def _quality(item: Dict[str, Any]) -> float:
            try:
                return float(item.get("quality_score") or 0)
            except (TypeError, ValueError):
                return 0.0

        selected.sort(key=lambda item: (item.get("evidence_priority") != "high", -_quality(item)))
        audit["selected"] = len(selected)
        return selected, audit

    def select_claims(self, claims: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        selected = []
        seen = set()
        for claim in claims or []:
            if not isinstance(claim, dict):
                continue
            claim_section = str(claim.get("section_id") or "").strip()
            if claim_section and claim_section != self.section_id:
                continue
            # An unconfigured scope must never turn into a global claim dump.
            # Claims without a section can only be admitted when the scope has
            # explicit metric requirements.
            if not self.required_metrics and claim_section != self.section_id:
                continue
            if not self._metric_matches(claim):
                continue
            key = str(claim.get("claim_id") or self._key(claim))
            if key not in seen:
                seen.add(key)
                selected.append(claim)
        return selected

    def select_canonical(self, canonical_data: Dict[str, Any]) -> Dict[str, Any]:
        selected: Dict[str, Any] = {}
        for key, value in (canonical_data or {}).items():
            entry = dict(value) if isinstance(value, dict) else {"value": value}
            entry.setdefault("metric", str(key))
            entry.setdefault("is_canonical", True)
            if not self.required_metrics and str(entry.get("section_id") or "").strip() != self.section_id:
                continue
            records, _ = self.select([entry])
            if records:
                selected[key] = value
        return selected
