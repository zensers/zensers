from src.agents.fixed_agents.report_upgrade.defense_audit import ReportDefenseAudit


def _report(*, content="中国市场2025年销量为100万辆。", **dp_overrides):
    dp = {
        "metric": "销量",
        "value": "100",
        "unit": "万辆",
        "source": "国家统计局",
        "source_url": "https://www.stats.gov.cn/example",
        "evidence_id": "ev-1",
        "provenance_id": "prov-1",
        "chapter_id": "ch1",
        "geographic_scope": "中国",
        "period": "2025年",
        "population": "乘用车",
        "epistemic_level": "factual",
        "evidence_status": "verified",
        **dp_overrides,
    }
    return {"sections": [{"id": "ch1", "content": content, "data_points": [dp]}]}


def test_clean_report_passes_all_layers():
    result = ReportDefenseAudit().audit(_report(), "无已知数据冲突。")
    assert result["passed"] is True
    assert result["layers"] == {"L1": False, "L2": False, "L3": False, "L4": False, "L5": False}


def test_global_number_used_in_domestic_paragraph_is_l4_failure():
    result = ReportDefenseAudit().audit(
        _report(content="全球市场销量增长10%，因此中国国内市场增长10%。"),
        "无已知数据冲突。",
    )
    assert result["passed"] is False
    assert any(item["layer"] == "L4" and item["code"] == "scope_collision" for item in result["issues"])


def test_explicit_scope_disclaimer_is_not_l4_collision():
    result = ReportDefenseAudit().audit(
        _report(content="全球与中国市场统计口径不同，本文不将两者直接合并比较。"),
        "无已知数据冲突。",
    )
    assert not any(item["code"] == "scope_collision" for item in result["issues"])


def test_verified_point_requires_evidence_identity():
    result = ReportDefenseAudit().audit(
        _report(evidence_id="", provenance_id=""),
        "无已知数据冲突。",
    )
    assert any(item["code"] == "incomplete_evidence_identity" for item in result["issues"])


def test_missing_provenance_and_registry_conflict_are_not_silent():
    result = ReportDefenseAudit().audit(
        _report(source_url="", evidence_status="unverified"),
        "销量：100万辆 vs 120万辆",
    )
    assert result["passed"] is False
    codes = {item["code"] for item in result["issues"]}
    assert "missing_source_url" in codes
    assert "unverified_evidence" in codes
    assert "unresolved_registry_conflict" in codes


def test_unbound_numeric_claim_in_body_is_not_allowed():
    report = {"sections": [{"id": "ch1", "content": "市场规模达到100亿元。", "data_points": []}]}
    result = ReportDefenseAudit().audit(report, "无已知数据冲突。")
    assert result["passed"] is False
    assert any(item["code"] == "unbound_numeric_claim" for item in result["issues"])


def test_population_is_required_for_quantitative_data_points():
    result = ReportDefenseAudit().audit(_report(population=""), "无已知数据冲突。")
    assert result["passed"] is False
    assert any(item["code"] == "missing_population" for item in result["issues"])


def test_future_year_boundary_is_dynamic_and_forecast_label_is_required():
    from datetime import datetime

    future_year = datetime.now().year + 1
    result = ReportDefenseAudit().audit(
        _report(content=f"市场将在{future_year}年完成扩张。"),
        "无已知数据冲突。",
    )
    assert any(item["code"] == "unlabeled_future_value" for item in result["issues"])

    labeled = ReportDefenseAudit().audit(
        _report(content=f"预计{future_year}年市场规模将达到100亿元。"),
        "无已知数据冲突。",
    )
    assert not any(item["code"] == "unlabeled_future_value" for item in labeled["issues"])
