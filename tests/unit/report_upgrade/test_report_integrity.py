from src.agents.fixed_agents.report_upgrade.report_integrity import ReportIntegrityChecker


def test_duplicate_claims_have_stable_id_and_l4_issue():
    result = ReportIntegrityChecker().check({
        "sections": [
            {"id": "s1", "key_conclusions": ["市场规模持续增长"], "data_points": []},
            {"id": "s2", "key_conclusions": ["市场规模持续增长"], "data_points": []},
        ]
    })
    assert result["passed"] is False
    assert result["issues"][0]["layer"] == "L4"
    assert result["issues"][0]["code"] == "duplicate_claim"
    assert result["claims"][0]["claim_id"] == result["claims"][1]["claim_id"]


def test_unique_claims_keep_evidence_ownership():
    result = ReportIntegrityChecker().check({
        "sections": [{
            "id": "s1",
            "key_conclusions": ["市场规模达到100亿元"],
            "data_points": [{"evidence_id": "ev_1"}],
        }]
    })
    assert result["passed"] is True
    assert result["claims"][0]["evidence_ids"] == ["ev_1"]
