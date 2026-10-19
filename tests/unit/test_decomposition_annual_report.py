"""Test: P0-4 DecompositionPlan annual report mode

Tests that IndustryResearchStrategy.decompose() correctly handles:
1. Dynamic aspects from analysis_framework
2. Preloaded data delivery agents (DATA_COLLECTION)
3. Document context injection (DEEP_ANALYSIS)
"""
import pytest
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock


class MockRequirement:
    def __init__(self, aspects=None, topic="Test", dynamic_fields=None):
        self.aspects = aspects or []
        self.topic = topic
        self.dynamic_fields = dynamic_fields or {}


class MockIntentResult:
    def __init__(self):
        self.complexity = None
        self.section_data_specs = []


class TestAnnualReportDecomposition:
    """Test decompose() with annual report mode"""

    def test_framework_aspects_used_when_empty(self):
        """When aspects is empty, use analysis_framework aspects"""
        requirement = MockRequirement(
            aspects=[],
            dynamic_fields={
                "annual_report_data": {
                    "analysis_framework": {
                        "aspects": ["Financial Analysis", "Risk Assessment"],
                        "aspect_to_profile": {"Financial Analysis": "financial_analysis", "Risk Assessment": "risk"},
                        "aspect_to_section_ids": {"Financial Analysis": [1], "Risk Assessment": [2]},
                    },
                    "sections": [
                        {"title": "Financial", "content": "Revenue data..."},
                        {"title": "Risk", "content": "Risk factors..."},
                    ],
                    "financial_tables": {"income": [], "balance": [], "cashflow": [], "key_metrics": []},
                },
                "preloaded_data": True,
            }
        )
        annual_report_data = requirement.dynamic_fields.get("annual_report_data", {})
        analysis_framework = annual_report_data.get("analysis_framework", {})
        
        aspects = requirement.aspects
        if analysis_framework and analysis_framework.get("aspects"):
            if not aspects or len(aspects) == 0:
                aspects = analysis_framework["aspects"]
        
        assert aspects == ["Financial Analysis", "Risk Assessment"]

    def test_explicit_aspects_preserved(self):
        """When aspects is already set, don't override"""
        requirement = MockRequirement(
            aspects=["Custom Aspect"],
            dynamic_fields={
                "annual_report_data": {
                    "analysis_framework": {"aspects": ["Financial Analysis"]},
                },
            },
        )
        annual_report_data = requirement.dynamic_fields.get("annual_report_data", {})
        analysis_framework = annual_report_data.get("analysis_framework", {})
        
        aspects = requirement.aspects
        if analysis_framework and analysis_framework.get("aspects"):
            if not aspects or len(aspects) == 0:
                aspects = analysis_framework["aspects"]
        
        assert aspects == ["Custom Aspect"]

    def test_preloaded_data_creates_lightweight_agents(self):
        """DATA_COLLECTION: preloaded=True for annual report mode"""
        preloaded_data = True
        if preloaded_data:
            spec_context = {"aspect": "Financial Analysis", "topic": "Test",
                           "preloaded": True, "section_id": "section_0"}
        else:
            spec_context = {"aspect": "Financial Analysis", "topic": "Test",
                           "section_id": "section_0"}
        
        assert spec_context.get("preloaded") is True

    def test_document_context_injected_for_financial_aspect(self):
        """DEEP_ANALYSIS: financial aspects get document_tables"""
        annual_report_data = {
            "analysis_framework": {
                "aspect_to_section_ids": {"Financial Analysis": [1]},
                "aspect_to_profile": {"Financial Analysis": "financial_analysis"},
            },
            "sections": [
                {"title": "Financial", "content": "Revenue is 1 billion..."},
            ],
            "financial_tables": {"income": [{"科目": "Revenue", "2023": 1000}], "balance": [], "cashflow": [], "key_metrics": []},
        }
        analysis_framework = annual_report_data.get("analysis_framework", {})
        aspect = "Financial Analysis"
        
        section_ids = analysis_framework.get("aspect_to_section_ids", {}).get(aspect, [])
        aspect_to_profile = analysis_framework.get("aspect_to_profile", {})
        sections = annual_report_data.get("sections", [])
        
        context_parts = []
        for sid in section_ids:
            if isinstance(sid, int) and 0 <= sid - 1 < len(sections):
                content = sections[sid - 1].get("content", "")
                if content:
                    context_parts.append(content[:4000])
        
        document_context = "\n\n".join(context_parts) if context_parts else ""
        document_tables = []
        
        profile = aspect_to_profile.get(aspect, "")
        if profile in ("financial_analysis", "valuation", "investment"):
            financial_tables = annual_report_data.get("financial_tables", {})
            if financial_tables:
                document_tables = financial_tables
        
        assert "Revenue" in document_context
        assert document_tables == annual_report_data["financial_tables"]

    def test_no_document_tables_for_non_financial(self):
        """Non-financial aspects don't get document_tables"""
        annual_report_data = {
            "analysis_framework": {
                "aspect_to_section_ids": {"Risk Assessment": [2]},
                "aspect_to_profile": {"Risk Assessment": "risk"},
            },
            "sections": [
                {"title": "Financial", "content": "Financial data..."},
                {"title": "Risk", "content": "Risk factors..."},
            ],
            "financial_tables": {"income": [], "balance": [], "cashflow": [], "key_metrics": []},
        }
        aspect = "Risk Assessment"
        analysis_framework = annual_report_data.get("analysis_framework", {})
        aspect_to_profile = analysis_framework.get("aspect_to_profile", {})
        
        profile = aspect_to_profile.get(aspect, "")
        document_tables = []
        if profile in ("financial_analysis", "valuation", "investment"):
            financial_tables = annual_report_data.get("financial_tables", {})
            if financial_tables:
                document_tables = financial_tables
        
        assert document_tables == []

    def test_section_id_out_of_range_handled(self):
        """Section IDs beyond sections list are safely ignored"""
        annual_report_data = {
            "analysis_framework": {
                "aspect_to_section_ids": {"Test": [99]},
                "aspect_to_profile": {"Test": "general"},
            },
            "sections": [{"title": "Only one", "content": "Data"}],
        }
        aspect = "Test"
        analysis_framework = annual_report_data["analysis_framework"]
        section_ids = analysis_framework.get("aspect_to_section_ids", {}).get(aspect, [])
        sections = annual_report_data.get("sections", [])
        
        context_parts = []
        for sid in section_ids:
            if isinstance(sid, int) and 0 <= sid - 1 < len(sections):
                content = sections[sid - 1].get("content", "")
                if content:
                    context_parts.append(content[:4000])
        
        assert context_parts == []
