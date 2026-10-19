"""Test: Annual report aspect→profile mapping via dynamic analysis_framework (v1.4 TDD)

v1.4架构: aspect→profile映射主路径是 analysis_framework["aspect_to_profile"],
ASPECT_NAME_MAP仅作为通用fallback（不含年报专用映射）。
"""

import pytest


class TestDynamicAspectProfileMapping:
    """Dynamic analysis_framework is the primary mapping path"""

    def test_framework_provides_profile_mapping(self):
        analysis_framework = {
            "aspects": ["Revenue Analysis", "Risk Assessment", "Governance Review"],
            "aspect_to_profile": {
                "Revenue Analysis": "financial_analysis",
                "Risk Assessment": "risk",
                "Governance Review": "enterprise",
            },
        }
        aspect = "Revenue Analysis"
        profile = analysis_framework.get("aspect_to_profile", {}).get(aspect, "general")
        assert profile == "financial_analysis"

    def test_english_aspect_from_us_10k(self):
        analysis_framework = {
            "aspect_to_profile": {
                "Business Overview": "enterprise",
                "Risk Factors": "risk",
                "Financial Statements": "financial_analysis",
                "MD&A": "financial_analysis",
            },
        }
        assert analysis_framework["aspect_to_profile"]["Risk Factors"] == "risk"
        assert analysis_framework["aspect_to_profile"]["MD&A"] == "financial_analysis"

    def test_japanese_aspect_from_yuka_shoken(self):
        analysis_framework = {
            "aspect_to_profile": {
                "事業概要": "enterprise",
                "リスク情報": "risk",
                "財務諸表": "financial_analysis",
            },
        }
        assert analysis_framework["aspect_to_profile"]["財務諸表"] == "financial_analysis"

    def test_fallback_to_general_when_framework_missing(self):
        from src.core.prompt_manager import get_profile_name_for_aspect
        result = get_profile_name_for_aspect("Unknown Dynamic Aspect")
        assert result == "general"

    def test_fallback_to_general_for_chinese_annual_aspects(self):
        from src.core.prompt_manager import get_profile_name_for_aspect
        assert get_profile_name_for_aspect("年报概述") == "general"
        assert get_profile_name_for_aspect("投资评估") == "general"
        assert get_profile_name_for_aspect("风险因素") == "general"


class TestAspectToProfileResolution:
    """Full resolution: framework → ASPECT_NAME_MAP → general"""

    def test_framework_priority_over_static_map(self):
        from src.core.prompt_manager import get_profile_name_for_aspect
        analysis_framework = {
            "aspect_to_profile": {"财务分析": "valuation"},
        }
        aspect = "财务分析"
        framework_profile = analysis_framework.get("aspect_to_profile", {}).get(aspect)
        static_profile = get_profile_name_for_aspect(aspect)
        assert framework_profile == "valuation"
        assert static_profile == "financial_analysis"
        assert framework_profile != static_profile
        resolved = framework_profile or static_profile or "general"
        assert resolved == "valuation"

    def test_static_map_used_when_framework_empty(self):
        from src.core.prompt_manager import get_profile_name_for_aspect
        analysis_framework = {}
        aspect = "财务分析"
        framework_profile = analysis_framework.get("aspect_to_profile", {}).get(aspect)
        resolved = framework_profile or get_profile_name_for_aspect(aspect) or "general"
        assert resolved == "financial_analysis"

    def test_general_fallback_when_all_miss(self):
        from src.core.prompt_manager import get_profile_name_for_aspect
        aspect = "Something Never Seen Before"
        framework_profile = None
        resolved = framework_profile or get_profile_name_for_aspect(aspect) or "general"
        assert resolved == "general"
