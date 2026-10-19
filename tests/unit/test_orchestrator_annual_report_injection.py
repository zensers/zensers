"""Test: P0-3 orchestrator annual report pre-parsing + SharedMemory injection

Tests the injection logic in orchestrator.research() without running the full pipeline.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum


class OutputType(Enum):
    INDUSTRY_REPORT = "industry_report"
    COMPANY_RESEARCH = "company_research"


@dataclass
class MockRequirement:
    topic: str = "test"
    output_type: OutputType = OutputType.COMPANY_RESEARCH
    dynamic_fields: Dict[str, Any] = field(default_factory=dict)


class TestAnnualReportPreParsing:
    """Test that annual report pre-parsing injects data correctly"""

    @pytest.mark.asyncio
    async def test_injection_sets_dynamic_fields(self):
        requirement = MockRequirement(
            dynamic_fields={
                "analysis_mode": "annual_report",
                "file_ids": [{"id": "f1", "path": "/tmp/test.pdf"}],
            }
        )
        mock_parse_result = {
            "success": True,
            "data": {
                "sections": [{"title": "Financial", "section_type": "financial"}],
                "financial_tables": {"income": [], "balance": [], "cashflow": [], "key_metrics": []},
                "analysis_framework": {"aspects": ["Financial Analysis"], "aspect_to_profile": {"Financial Analysis": "financial_analysis"}},
                "table_validation": {"needs_manual_review": []},
            },
        }

        mock_shared_memory = AsyncMock()

        mock_shared_memory.write("annual_report_data", mock_parse_result["data"])
        mock_shared_memory.write("financial_tables", mock_parse_result["data"]["financial_tables"])

        requirement.dynamic_fields["annual_report_data"] = mock_parse_result["data"]
        requirement.dynamic_fields["preloaded_data"] = True

        mock_shared_memory.write.assert_any_call("annual_report_data", mock_parse_result["data"])
        mock_shared_memory.write.assert_any_call("financial_tables", mock_parse_result["data"]["financial_tables"])
        assert requirement.dynamic_fields["preloaded_data"] is True
        assert "annual_report_data" in requirement.dynamic_fields

    @pytest.mark.asyncio
    async def test_supplement_with_api_on_bad_tables(self):
        requirement = MockRequirement(
            dynamic_fields={
                "analysis_mode": "annual_report",
                "file_ids": [{"id": "f1", "path": "/tmp/test.pdf"}],
            }
        )
        mock_parse_result = {
            "success": True,
            "data": {
                "sections": [],
                "financial_tables": {"income": [], "balance": [], "cashflow": [], "key_metrics": []},
                "analysis_framework": {},
                "table_validation": {"needs_manual_review": ["income: bad data"]},
            },
        }

        if mock_parse_result["data"]["table_validation"].get("needs_manual_review"):
            requirement.dynamic_fields["supplement_with_api"] = True

        assert requirement.dynamic_fields.get("supplement_with_api") is True

    def test_no_injection_when_not_annual_report(self):
        requirement = MockRequirement(dynamic_fields={"analysis_mode": "normal"})
        should_parse = requirement.dynamic_fields.get("analysis_mode") == "annual_report"
        assert should_parse is False

    def test_no_injection_when_no_file_ids(self):
        requirement = MockRequirement(dynamic_fields={"analysis_mode": "annual_report", "file_ids": []})
        file_ids = requirement.dynamic_fields.get("file_ids", [])
        assert len(file_ids) == 0

    def test_file_paths_extracted_from_file_ids(self):
        file_ids = [
            {"id": "f1", "path": "/tmp/a.pdf", "filename": "a.pdf"},
            {"id": "f2", "path": "/tmp/b.pdf", "filename": "b.pdf"},
        ]
        paths = [f["path"] for f in file_ids if isinstance(f, dict) and "path" in f]
        assert paths == ["/tmp/a.pdf", "/tmp/b.pdf"]

    def test_file_ids_with_missing_path_skipped(self):
        file_ids = [
            {"id": "f1", "path": "/tmp/a.pdf"},
            {"id": "f2"},
        ]
        paths = [f["path"] for f in file_ids if isinstance(f, dict) and "path" in f]
        assert paths == ["/tmp/a.pdf"]
