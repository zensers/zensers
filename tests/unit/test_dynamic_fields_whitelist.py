"""Test: _parse_requirement dynamic_fields whitelist extraction (v1.3 TDD)"""

import pytest


class TestParseRequirementDynamicFields:
    """_parse_requirement must extract known dynamic fields via whitelist"""

    @pytest.fixture
    def orchestrator(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        return ResearchOrchestrator.__new__(ResearchOrchestrator)

    def test_file_ids_extracted_to_dynamic_fields(self, orchestrator):
        user_input = {
            "topic": "比亚迪年报分析",
            "aspects": ["深度财务分析"],
            "file_ids": [{"id": "file_abc123", "path": "/tmp/test.pdf"}],
        }
        req = orchestrator._parse_requirement(user_input)
        assert "file_ids" in req.dynamic_fields
        assert req.dynamic_fields["file_ids"] == [{"id": "file_abc123", "path": "/tmp/test.pdf"}]

    def test_analysis_mode_extracted_to_dynamic_fields(self, orchestrator):
        user_input = {
            "topic": "比亚迪年报分析",
            "aspects": ["深度财务分析"],
            "analysis_mode": "annual_report",
        }
        req = orchestrator._parse_requirement(user_input)
        assert req.dynamic_fields.get("analysis_mode") == "annual_report"

    def test_supplement_with_api_extracted_to_dynamic_fields(self, orchestrator):
        user_input = {
            "topic": "test",
            "aspects": ["财务分析"],
            "supplement_with_api": True,
        }
        req = orchestrator._parse_requirement(user_input)
        assert req.dynamic_fields.get("supplement_with_api") is True

    def test_preloaded_data_extracted_to_dynamic_fields(self, orchestrator):
        user_input = {
            "topic": "test",
            "aspects": ["财务分析"],
            "preloaded_data": True,
        }
        req = orchestrator._parse_requirement(user_input)
        assert req.dynamic_fields.get("preloaded_data") is True

    def test_annual_report_data_extracted_to_dynamic_fields(self, orchestrator):
        user_input = {
            "topic": "test",
            "aspects": ["财务分析"],
            "annual_report_data": {"sections": []},
        }
        req = orchestrator._parse_requirement(user_input)
        assert "annual_report_data" in req.dynamic_fields

    def test_sensitive_fields_not_in_dynamic_fields(self, orchestrator):
        user_input = {
            "topic": "test",
            "aspects": ["财务分析"],
            "llm_api_key": "sk-secret-key-12345",
            "file_ids": [{"id": "file_abc"}],
        }
        req = orchestrator._parse_requirement(user_input)
        assert "llm_api_key" not in req.dynamic_fields
        assert "file_ids" in req.dynamic_fields

    def test_standard_fields_not_in_dynamic_fields(self, orchestrator):
        user_input = {
            "topic": "test topic",
            "aspects": ["财务分析"],
            "region": "China",
            "depth": "detailed",
        }
        req = orchestrator._parse_requirement(user_input)
        assert "topic" not in req.dynamic_fields
        assert "aspects" not in req.dynamic_fields
        assert "region" not in req.dynamic_fields
        assert "depth" not in req.dynamic_fields

    def test_empty_dynamic_fields_when_no_extra_fields(self, orchestrator):
        user_input = {
            "topic": "test",
            "aspects": ["财务分析"],
        }
        req = orchestrator._parse_requirement(user_input)
        assert req.dynamic_fields == {} or all(
            v is None for v in req.dynamic_fields.values()
        )
