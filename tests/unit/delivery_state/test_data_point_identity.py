from src.core.storage.research_result_store import ResearchResultStore, ResearchStatus
from src.core.evidence_scope import EvidenceScope
from src.core.orchestrator.execution.engine import _evidence_record_key


def test_data_points_from_same_url_keep_distinct_metric_scope_identity(tmp_path):
    store = ResearchResultStore(str(tmp_path))
    common = {
        "source_url": "https://example.test/report",
        "source": "example",
        "unit": "万台",
        "evidence_status": "verified",
    }
    store.save_result(
        "identity-test",
        {
            "title": "t",
            "sections": [],
            "data_points": [
                {**common, "metric": "出货量", "value": "100", "period": "2026Q1", "geographic_scope": "中国"},
                {**common, "metric": "出货量", "value": "200", "period": "2026Q1", "geographic_scope": "全球"},
            ],
        },
        status=ResearchStatus.COMPLETED_WITH_WARNINGS,
    )

    result = store.load_result("identity-test")
    assert len(result["data_points"]) == 2


def test_stable_evidence_identity_survives_late_enrichment():
    base = {
        "evidence_id": "ev-1",
        "metric": "出货量",
        "value": "100",
        "unit": "万台",
        "source_url": "https://example.test/report",
        "is_canonical": True,
    }
    q1_cn = {**base, "period": "2026Q1", "geographic_scope": "中国"}
    q2_global = {**base, "value": "120", "period": "2026Q2", "geographic_scope": "全球",
                 "source_url": "https://example.test/enriched"}

    assert _evidence_record_key(q1_cn, "data_point") == _evidence_record_key(q2_global, "data_point")
    scope = EvidenceScope(section_id="section_0")
    selected, audit = scope.select([q1_cn, q2_global])
    assert len(selected) == 1
    assert audit["excluded_duplicate"] == 1
