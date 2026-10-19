"""
Test findings_extractor - SectionFindings extraction
"""
import sys
sys.path.insert(0, "E:/market_report_systerm/src")

import pytest
from core.quality.findings import SectionFindings, extract_findings


class TestExtractFindings:
    """Test core findings extraction"""

    def test_empty_text(self):
        result = extract_findings("s1", "")
        assert result.section_id == "s1"
        assert result.core_claims == []
        assert result.key_data_points == []

    def test_extract_core_claims(self):
        text = "本章从多个维度分析了市场情况。核心判断：市场已触底反弹，2026年将进入上行周期。同时需求端也在改善。"
        result = extract_findings("s1", text)
        assert len(result.core_claims) >= 1
        assert "核心判断" in result.core_claims[0]

    def test_extract_data_points(self):
        text = "2025年全国鸡蛋产量3050万吨，同比增长15%。市场规模达到2647亿元。"
        result = extract_findings("s1", text)
        # Should find: 3050万吨, 15%, 2647亿元
        assert len(result.key_data_points) >= 2

    def test_data_point_has_value_unit_context(self):
        text = "2025年全国鸡蛋产量3050万吨。"
        result = extract_findings("s1", text)
        assert any(dp["value"] == "3050" and dp["unit"] == "万吨" for dp in result.key_data_points)

    def test_no_false_positive_year(self):
        """'年' should not be extracted as a data unit"""
        text = "2026年5月22日，市场报告发布。"
        result = extract_findings("s1", text)
        for dp in result.key_data_points:
            assert dp["unit"] != "年", f"False positive: {dp}"

    def test_to_dict_roundtrip(self):
        findings = SectionFindings(
            section_id="s1",
            core_claims=["市场增长"],
            key_data_points=[{"value": "100", "unit": "亿元", "context": "规模达到"}],
        )
        d = findings.to_dict()
        restored = SectionFindings.from_dict(d)
        assert restored.section_id == "s1"
        assert restored.core_claims == ["市场增长"]
        assert restored.key_data_points[0]["value"] == "100"
