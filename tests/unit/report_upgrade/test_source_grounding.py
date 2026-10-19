from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator


def test_grounding_does_not_invent_fallback_source():
    sources = [{"title": "国家统计局", "url": "https://www.stats.gov.cn/example", "evidence_excerpt": "销量数据"}]
    points = [{"metric": "销量", "value": "100", "unit": "万辆", "source": ""}]

    result = ReportOrchestrator._ground_data_point_sources(points, sources, chapter_id="ch1")

    assert result[0]["source"] == ""
    assert result[0]["source_url"] == ""
    assert result[0]["evidence_status"] == "unverified"
    assert result[0]["chapter_id"] == "ch1"


def test_grounding_does_not_mark_url_and_excerpt_verified_without_identity():
    sources = [{
        "title": "国家统计局",
        "url": "https://www.stats.gov.cn/example",
        "evidence_excerpt": "销量数据",
    }]
    points = [{"metric": "销量", "value": "100", "unit": "万辆", "source": "国家统计局"}]

    result = ReportOrchestrator._ground_data_point_sources(points, sources, chapter_id="ch1")

    assert result[0]["source_url"] == "https://www.stats.gov.cn/example"
    assert result[0]["evidence_status"] == "unverified"
    assert result[0].get("evidence_id", "") == ""
    assert result[0].get("provenance_id", "") == ""


def test_grounding_resolves_index_and_rejects_out_of_range_index():
    sources = [{
        "title": "国家统计局",
        "url": "https://www.stats.gov.cn/example",
        "evidence_excerpt": "销量数据",
        "evidence_id": "ev_stats_1",
        "provenance_id": "prov_stats_1",
    }]
    points = [
        {"metric": "销量", "value": "100", "unit": "万辆", "source": "来源1"},
        {"metric": "渗透率", "value": "30", "unit": "%", "source": "来源9"},
    ]

    result = ReportOrchestrator._ground_data_point_sources(points, sources, chapter_id="ch1")

    assert result[0]["source"] == "国家统计局"
    assert result[0]["source_url"] == "https://www.stats.gov.cn/example"
    assert result[0]["evidence_status"] == "verified"
    assert result[1]["source"] == ""
    assert result[1]["evidence_status"] == "unverified"


def test_grounding_rejects_url_not_in_source_catalog():
    sources = [{
        "title": "国家统计局",
        "url": "https://www.stats.gov.cn/example",
        "evidence_excerpt": "销量数据",
        "evidence_id": "ev_stats_1",
        "provenance_id": "prov_stats_1",
    }]
    points = [{
        "metric": "销量", "value": "100", "unit": "万辆",
        "source": "国家统计局", "source_url": "https://attacker.invalid/fake",
    }]

    result = ReportOrchestrator._ground_data_point_sources(points, sources, chapter_id="ch1")

    assert result[0]["source_url"] == "https://www.stats.gov.cn/example"
    assert result[0]["evidence_status"] == "verified"


def test_grounding_rejects_mismatched_evidence_identity():
    sources = [{
        "title": "国家统计局",
        "url": "https://www.stats.gov.cn/example",
        "evidence_excerpt": "销量数据",
        "evidence_id": "ev-catalog",
        "provenance_id": "prov-catalog",
    }]
    points = [{
        "metric": "销量", "value": "100", "unit": "万辆",
        "source_url": "https://www.stats.gov.cn/example",
        "evidence_id": "ev-other", "provenance_id": "prov-other",
    }]

    result = ReportOrchestrator._ground_data_point_sources(points, sources, chapter_id="ch1")

    assert result[0]["evidence_status"] == "unverified"
    assert result[0]["evidence_id"] == ""
    assert result[0]["provenance_id"] == ""
    assert result[0]["evidence_binding_error"] == "provided_evidence_identity_mismatch"


def test_grounding_does_not_choose_between_ambiguous_source_titles():
    sources = [
        {
            "title": "行业市场报告",
            "url": "https://example.com/market-a",
            "evidence_excerpt": "A",
            "evidence_id": "ev_a",
            "provenance_id": "prov_a",
        },
        {
            "title": "行业市场报告（亚洲）",
            "url": "https://example.com/market-b",
            "evidence_excerpt": "B",
            "evidence_id": "ev_b",
            "provenance_id": "prov_b",
        },
    ]
    points = [{"metric": "规模", "value": "100", "unit": "亿元", "source": "市场报告"}]

    result = ReportOrchestrator._ground_data_point_sources(points, sources, chapter_id="ch1")

    assert result[0]["source_url"] == ""
    assert result[0]["evidence_status"] == "unverified"
