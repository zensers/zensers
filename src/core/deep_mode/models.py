from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar
from uuid import uuid4


@dataclass
class StructuredRecord:
    section_id: str
    data_need: str
    source_url: str
    source_title: str = ""
    source_quote: str = ""
    evidence_id: str = ""
    period: str = ""
    region: str = ""
    confidence: str = "medium"
    quality_score: float = 0.0
    is_estimate: bool = False
    estimate_method: str = ""
    record_id: str = field(default_factory=lambda: uuid4().hex)
    record_type: ClassVar[str] = "structured"

    @property
    def title(self) -> str:
        return self.record_type

    def payload(self) -> dict[str, Any]:
        raise NotImplementedError

    def summary(self) -> str:
        return f"{self.record_type}: {self.payload()}"

    def to_data_point(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "content": self.summary(),
            "url": self.source_url,
            "source": self.source_title,
            "source_quote": self.source_quote,
            "evidence_id": self.evidence_id,
            "record_id": self.record_id,
            "record_type": self.record_type,
            "structured_data": self.payload(),
            "data_need": self.data_need,
            "section_id": self.section_id,
            "period": self.period,
            "region": self.region,
            "confidence": self.confidence,
            "is_estimate": self.is_estimate,
            "estimate_method": self.estimate_method,
            "quality_score": self.quality_score,
            "credibility": "estimated" if self.is_estimate else "search_result",
        }


@dataclass
class CompanyShareRecord(StructuredRecord):
    company_name: str = ""
    share_pct: float = 0.0
    metric_basis: str = ""
    ticker: str = ""
    rank: int | None = None
    record_type: ClassVar[str] = "company_share"

    @property
    def title(self) -> str:
        return f"{self.company_name} 市场份额"

    def payload(self) -> dict[str, Any]:
        return {
            "company_name": self.company_name,
            "ticker": self.ticker,
            "share_pct": self.share_pct,
            "metric_basis": self.metric_basis,
            "rank": self.rank,
        }

    def summary(self) -> str:
        return (
            f"{self.company_name} 市场份额 {self.share_pct:.1f}%"
            f"（口径：{self.metric_basis or '未注明'}，期间：{self.period or '未注明'}）"
        )


@dataclass
class BOMItemRecord(StructuredRecord):
    system: str = ""
    component: str = ""
    cost_share_pct: float = 0.0
    unit_cost: float | None = None
    currency: str = ""
    supplier_names: list[str] = field(default_factory=list)
    model: str = ""
    record_type: ClassVar[str] = "bom_item"

    @property
    def title(self) -> str:
        return f"{self.system} / {self.component} BOM成本"

    def payload(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "component": self.component,
            "cost_share_pct": self.cost_share_pct,
            "unit_cost": self.unit_cost,
            "currency": self.currency,
            "supplier_names": list(self.supplier_names),
            "model": self.model,
        }

    def summary(self) -> str:
        return (
            f"{self.system}/{self.component} 成本占比 {self.cost_share_pct:.1f}%"
            f"（期间：{self.period or '未注明'}）"
        )


@dataclass
class SupplierRecord(StructuredRecord):
    supplier_name: str = ""
    component: str = ""
    customers: list[str] = field(default_factory=list)
    relationship_type: str = "supplier"
    record_type: ClassVar[str] = "supplier"

    @property
    def title(self) -> str:
        return f"{self.supplier_name} 供应商关系"

    def payload(self) -> dict[str, Any]:
        return {
            "supplier_name": self.supplier_name,
            "component": self.component,
            "customers": list(self.customers),
            "relationship_type": self.relationship_type,
        }

    def summary(self) -> str:
        customers = "、".join(self.customers) or "未披露"
        return (
            f"{self.supplier_name} 供应 {self.component}"
            f"（客户：{customers}，关系：{self.relationship_type}）"
        )


@dataclass(frozen=True)
class DeepQuery:
    query: str
    record_type: str
    section_id: str
    company: str = ""
    system: str = ""
    component: str = ""


@dataclass
class DeepModePlan:
    topic: str
    sections: dict[str, str]
    section_needs: dict[str, list[str]]
    companies: list[str] = field(default_factory=list)
    bom_systems: list[str] = field(default_factory=list)
