"""
Test enhanced ReportQualityChecker - 4 new dimensions
"""
import sys
sys.path.insert(0, "E:/market_report_systerm/src")

import pytest
from core.quality.checkers import ReportQualityChecker


class TestReportCheckerConsistency:
    """Test cross-chapter consistency detection"""

    def test_no_contradiction(self):
        sections = [
            {"id": "B", "content": "从供给端看，产能去化加速，市场供给偏紧。"},
            {"id": "C", "content": "从需求端看，消费稳定增长。"},
        ]
        checker = ReportQualityChecker()
        score = checker._check_cross_chapter_consistency(sections)
        assert score == 100.0

    def test_contradiction_detected(self):
        sections = [
            {"id": "B", "content": "综上所述，市场前景看涨，价格将持续上升。"},
            {"id": "C", "content": "总体来看，市场前景看空，价格将持续下跌。"},
        ]
        checker = ReportQualityChecker()
        score = checker._check_cross_chapter_consistency(sections)
        assert score < 100.0

    def test_single_section_no_contradiction(self):
        sections = [
            {"id": "A", "content": "市场看涨。"},
        ]
        checker = ReportQualityChecker()
        score = checker._check_cross_chapter_consistency(sections)
        assert score == 100.0

    def test_empty_sections(self):
        checker = ReportQualityChecker()
        score = checker._check_cross_chapter_consistency([])
        assert score == 100.0


class TestReportCheckerRedundancy:
    """Test data redundancy detection"""

    def test_no_redundancy(self):
        sections = [
            {"id": "B", "content": "产量3050万吨。", "role": "analysis"},
            {"id": "C", "content": "需求2647亿元。", "role": "analysis"},
        ]
        checker = ReportQualityChecker()
        score = checker._check_data_redundancy(sections)
        assert score == 100.0

    def test_redundancy_detected(self):
        sections = [
            {"id": "B", "content": "产量3050万吨。", "role": "analysis"},
            {"id": "C", "content": "产量3050万吨。", "role": "analysis"},
        ]
        checker = ReportQualityChecker()
        score = checker._check_data_redundancy(sections)
        assert score < 100.0

    def test_synthesis_redundancy_not_penalized(self):
        """Synthesis sections referencing same data should not count as redundancy"""
        sections = [
            {"id": "B", "content": "产量3050万吨。", "role": "analysis"},
            {"id": "A", "content": "如前所述，产量3050万吨。", "role": "synthesis"},
        ]
        checker = ReportQualityChecker()
        score = checker._check_data_redundancy(sections)
        assert score == 100.0


class TestReportCheckerProvenance:
    """Test finding provenance check"""

    def test_with_findings(self):
        data = {
            "sections": [
                {"id": "B", "content": "市场规模持续增长。"},
                {"id": "A", "content": "综上所述，市场规模持续增长，前景乐观。"},
            ],
            "findings": [
                {"section_id": "B", "core_claims": ["市场规模持续增长"]},
            ],
        }
        context = {"synthesis_section_ids": ["A"]}
        checker = ReportQualityChecker()
        score = checker._check_finding_provenance(data, context)
        assert score > 0

    def test_no_findings_graceful_degradation(self):
        """When findings_extractor not deployed, return 80 as neutral score"""
        data = {"sections": [], "findings": []}
        checker = ReportQualityChecker()
        score = checker._check_finding_provenance(data, {})
        assert score == 80.0


class TestReportCheckerSearchAudit:
    """Test external search audit"""

    def test_no_violation(self):
        data = {
            "execution_logs": [
                {"section_id": "A", "skills_used": ["llm_skill"]},
            ],
        }
        context = {"synthesis_section_ids": ["A"]}
        checker = ReportQualityChecker()
        assert checker._check_external_search_audit(data, context) == False

    def test_violation_detected(self):
        data = {
            "execution_logs": [
                {"section_id": "A", "skills_used": ["search_skill", "llm_skill"]},
            ],
        }
        context = {"synthesis_section_ids": ["A"]}
        checker = ReportQualityChecker()
        assert checker._check_external_search_audit(data, context) == True


class TestReportCheckerIntegration:
    """Test integrated calculate_score"""

    def test_good_report_passes(self):
        """A report with consistent, non-redundant, provenance-respecting content"""
        data = {
            "sections": [
                {"id": "B", "content": "产量3050万吨。供给端产能去化加速。", "role": "analysis"},
                {"id": "C", "content": "需求2647亿元。消费稳定增长。", "role": "analysis"},
                {"id": "A", "content": "综上所述，供给端产能去化加速，消费稳定增长。", "role": "synthesis"},
            ],
            "findings": [
                {"section_id": "B", "core_claims": ["供给端产能去化加速"]},
                {"section_id": "C", "core_claims": ["消费稳定增长"]},
            ],
            "execution_logs": [
                {"section_id": "A", "skills_used": ["llm_skill"]},
            ],
        }
        context = {"synthesis_section_ids": ["A"]}
        checker = ReportQualityChecker(threshold=60.0)
        result = checker.check(data, context)
        assert result.passed, f"Good report should pass, got score={result.score}"

    def test_contradictory_report_fails(self):
        data = {
            "sections": [
                {"id": "B", "content": "市场前景看涨，价格将持续上升。", "role": "analysis"},
                {"id": "C", "content": "市场前景看空，价格将下跌。", "role": "analysis"},
            ],
            "findings": [],
            "execution_logs": [],
        }
        checker = ReportQualityChecker(threshold=60.0)
        result = checker.check(data, {})
        assert not result.passed
