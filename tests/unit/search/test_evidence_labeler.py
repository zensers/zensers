# tests/unit/search/test_evidence_labeler.py
from src.core.search.evidence_labeler import EvidenceStrengthLabeler


def test_strong_evidence():
    labeler = EvidenceStrengthLabeler()
    dp = {
        "metric": "出货量",
        "value": "3.5亿",
        "period": "2025",
        "geographic_scope": "中国",
        "source": "IDC",
        "credibility": "tier1_authority",
    }
    label = labeler.label(dp)
    assert label["evidence_strength"] == "strong"


def test_weak_evidence_missing_fields():
    labeler = EvidenceStrengthLabeler()
    dp = {"metric": "出货量", "value": "3.5亿"}
    label = labeler.label(dp)
    assert label["evidence_strength"] in ("weak", "moderate")


def test_empty_datapoint():
    labeler = EvidenceStrengthLabeler()
    label = labeler.label({})
    assert label["evidence_strength"] == "weak"
