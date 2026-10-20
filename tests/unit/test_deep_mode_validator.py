import pytest

from src.core.deep_mode.estimator import Estimator
from src.core.deep_mode.models import BOMItemRecord, CompanyShareRecord
from src.core.deep_mode.validator import RecordValidator


def _share(company: str, pct: float) -> CompanyShareRecord:
    return CompanyShareRecord(
        section_id="competitive_landscape",
        data_need="市场份额",
        source_url="https://example.com",
        source_quote=f"{company} {pct}%",
        company_name=company,
        share_pct=pct,
        metric_basis="shipments",
        period="2025",
    )


def test_validator_drops_invalid_and_flags_sum():
    result = RecordValidator().validate(
        [_share("A", 60), _share("B", 50), _share("C", 120)],
        "company_share",
    )

    assert len(result.records) == 2
    assert len(result.dropped) == 1
    assert result.conflicts


def test_validator_marks_partial_bom():
    records = [
        BOMItemRecord(
            section_id="technology_trends",
            data_need="BOM",
            source_url="https://example.com",
            source_quote="电池 60%",
            system="动力电池",
            component="电芯",
            cost_share_pct=60.0,
            period="2025",
        )
    ]

    result = RecordValidator().validate(records, "bom_item")

    assert result.partial_bom is True


def test_estimator_marks_estimate_and_method():
    record = Estimator().estimate_company_share(
        company_name="A",
        share_pct=10.0,
        metric_basis="revenue",
        period="2025",
        section_id="competitive_landscape",
        data_need="市场份额",
        anchor_url="https://example.com/industry",
        anchor_title="行业规模",
        anchor_quote="行业规模1000亿元",
        method="公司收入/行业规模",
    )

    assert record.is_estimate is True
    assert record.confidence == "low"
    assert record.estimate_method == "公司收入/行业规模"


def test_partial_bom_false_when_no_records():
    result = RecordValidator().validate([], "bom_item")

    assert result.partial_bom is False
    assert result.conflicts == []
    assert result.records == []


def test_validator_drops_missing_evidence():
    record = CompanyShareRecord(
        section_id="competitive_landscape",
        data_need="市场份额",
        source_url="",
        source_quote="A 60%",
        company_name="A",
        share_pct=60.0,
        metric_basis="shipments",
        period="2025",
    )

    result = RecordValidator().validate([record], "company_share")

    assert len(result.dropped) == 1
    assert result.dropped[0]["reason"] == "missing_evidence"
    assert result.records == []


def test_conflict_does_not_mutate_input():
    first = _share("A", 60)
    second = _share("B", 50)
    first.confidence = "high"
    second.confidence = "high"

    result = RecordValidator().validate([first, second], "company_share")

    assert [record.confidence for record in result.records] == ["low", "low"]
    assert first.confidence == "high"
    assert second.confidence == "high"
    assert result.conflicts[0]["type"] == "share_sum_exceeds_100"


def test_estimator_rejects_invalid_share_pct():
    base_kwargs = {
        "company_name": "A",
        "metric_basis": "revenue",
        "period": "2025",
        "section_id": "competitive_landscape",
        "data_need": "市场份额",
        "anchor_url": "https://example.com/industry",
        "anchor_title": "行业规模",
        "anchor_quote": "行业规模1000亿元",
        "method": "公司收入/行业规模",
    }

    with pytest.raises(ValueError):
        Estimator().estimate_company_share(**base_kwargs, share_pct=250.0)

    with pytest.raises(ValueError):
        Estimator().estimate_company_share(**base_kwargs, share_pct=float("nan"))
