from src.core.quality.checkers import ReportQualityChecker
from src.agents.fixed_agents.report_upgrade.defense_audit import ReportDefenseAudit


def test_cross_chapter_consistency_separates_geographic_scope():
    sections = [
        {"id": "china", "content": "中国市场2024年销量100万辆。"},
        {"id": "global", "content": "全球市场2024年销量300万辆。"},
    ]

    assert ReportQualityChecker()._check_cross_chapter_consistency(sections) == 100.0


def test_same_scope_numeric_difference_remains_a_conflict():
    sections = [
        {"id": "a", "content": "中国市场2024年销量100万辆。"},
        {"id": "b", "content": "中国市场2024年销量130万辆。"},
    ]

    assert ReportQualityChecker()._check_cross_chapter_consistency(sections) < 100.0


def test_explicit_global_china_comparison_is_not_scope_collision():
    report = {
        "sections": [{
            "id": "s1",
            "content": "2024年全球市场销量300万辆，相比中国市场销量100万辆。",
            "data_points": [
                {"value": 300, "unit": "万辆"},
                {"value": 100, "unit": "万辆"},
            ],
        }]
    }

    result = ReportDefenseAudit().audit(report)
    assert not any(issue["code"] == "scope_collision" for issue in result["issues"])
