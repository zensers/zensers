from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class PhaseOutputSchema:
    REQUIRED_FIELDS = {
        "data_collection": ["topic", "data_points"],
        "data_validation": ["valid", "quality_score"],
        "deep_analysis": ["framework_used", "insights"],
        "synthesis": ["executive_summary"],
        "report_generation": ["sections", "format"],
    }


class SchemaValidator:
    def validate_phase_output(self, phase: str, output: Dict[str, Any]) -> Tuple[bool, List[str]]:
        required = PhaseOutputSchema.REQUIRED_FIELDS.get(phase, [])
        errors = [f"Missing required field: {f}" for f in required if f not in output]
        return (len(errors) == 0, errors)


PHASE_OUTPUT_SCHEMAS = {
    "data_collection": PhaseOutputSchema(),
    "data_validation": PhaseOutputSchema(),
    "deep_analysis": PhaseOutputSchema(),
    "synthesis": PhaseOutputSchema(),
    "report_generation": PhaseOutputSchema(),
}


@dataclass
class DataPoint:
    metric: str
    value: Any
    unit: str = ""
    source: str = ""
    confidence: float = 1.0
    source_url: str = ""
    evidence_id: str = ""
    provenance_id: str = ""
    evidence_excerpt: str = ""
    locator: str = ""
    task_id: str = ""
    request_id: str = ""
    retrieved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "confidence": self.confidence,
            "source_url": self.source_url,
            "evidence_id": self.evidence_id,
            "provenance_id": self.provenance_id,
            "evidence_excerpt": self.evidence_excerpt,
            "locator": self.locator,
            "task_id": self.task_id,
            "request_id": self.request_id,
            "retrieved_at": self.retrieved_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataPoint":
        return cls(
            metric=data["metric"],
            value=data["value"],
            unit=data.get("unit", ""),
            source=data.get("source", ""),
            confidence=data.get("confidence", 1.0),
            source_url=data.get("source_url", ""),
            evidence_id=data.get("evidence_id", ""),
            provenance_id=data.get("provenance_id", ""),
            evidence_excerpt=data.get("evidence_excerpt", ""),
            locator=data.get("locator", ""),
            task_id=data.get("task_id", ""),
            request_id=data.get("request_id", ""),
            retrieved_at=data.get("retrieved_at"),
        )


@dataclass
class Insight:
    insight: str
    evidence: List[str] = field(default_factory=list)
    implication: str = ""
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "insight": self.insight,
            "evidence": self.evidence,
            "implication": self.implication,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Insight":
        return cls(
            insight=data["insight"],
            evidence=data.get("evidence", []),
            implication=data.get("implication", ""),
            confidence=data.get("confidence", 1.0),
        )
