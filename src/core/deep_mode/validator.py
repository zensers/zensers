from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .models import BOMItemRecord, CompanyShareRecord, StructuredRecord, SupplierRecord


@dataclass
class ValidationResult:
    records: list[StructuredRecord]
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    partial_bom: bool = False


class RecordValidator:
    def validate(self, records: list[StructuredRecord], record_type: str) -> ValidationResult:
        if record_type not in {"company_share", "bom_item", "supplier"}:
            raise ValueError(f"unknown record_type: {record_type}")
        result = ValidationResult(records=[])
        for record in records:
            if not record.source_url or not record.source_quote:
                result.dropped.append({"record_id": record.record_id, "reason": "missing_evidence"})
                continue
            if isinstance(record, CompanyShareRecord):
                if not record.company_name or not (0 < record.share_pct <= 100):
                    result.dropped.append(
                        {"record_id": record.record_id, "reason": "invalid_share"}
                    )
                    continue
                result.records.append(record)
            elif isinstance(record, BOMItemRecord):
                if not record.component or not (0 < record.cost_share_pct <= 100):
                    result.dropped.append(
                        {"record_id": record.record_id, "reason": "invalid_bom_share"}
                    )
                    continue
                result.records.append(record)
            elif isinstance(record, SupplierRecord):
                if not record.supplier_name or not record.component:
                    result.dropped.append(
                        {"record_id": record.record_id, "reason": "invalid_supplier"}
                    )
                    continue
                result.records.append(record)

        if record_type == "company_share":
            total = sum(
                record.share_pct
                for record in result.records
                if isinstance(record, CompanyShareRecord)
            )
            if total > 100 + 1e-9:
                result.conflicts.append(
                    {"type": "share_sum_exceeds_100", "total": total}
                )
                result.records = [
                    replace(record, confidence="low")
                    if isinstance(record, CompanyShareRecord)
                    else record
                    for record in result.records
                ]

        if record_type == "bom_item":
            total = sum(
                record.cost_share_pct
                for record in result.records
                if isinstance(record, BOMItemRecord)
            )
            if result.records and not 95 <= total <= 105:
                result.partial_bom = True
            if total > 105:
                result.conflicts.append(
                    {"type": "bom_sum_exceeds_105", "total": total}
                )

        return result
