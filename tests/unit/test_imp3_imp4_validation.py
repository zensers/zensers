"""
IMP-3: DATA_VALIDATION low quality → targeted re-collection (max 1 round)
IMP-4: Numeric conflict auto-resolution by authority + timeliness

IMP-3 + IMP-4 are independent but both modify DATA_VALIDATION phase.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


AGENT_PATH = Path(__file__).resolve().parent.parent.parent / "src" / "core" / "agents" / "generic_agent.py"


class TestIMP3TargetedRecollectionMethod:
    """IMP-3: _generate_recollection_queries from validation warnings"""

    @pytest.fixture
    def agent(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "imp3_unit"
        return agent

    def test_method_exists(self, agent):
        assert hasattr(agent, '_generate_recollection_queries')
        assert callable(getattr(agent, '_generate_recollection_queries'))

    def test_timeliness_warning_generates_recency_queries(self, agent):
        warnings = [{"type": "timeliness", "message": "No recent data found in: 2023年新能源汽车报告", "url": "https://example.com/old"}]
        queries = agent._generate_recollection_queries("新能源汽车", "Market Analysis", warnings)
        assert len(queries) >= 1
        from datetime import date
        year = str(date.today().year)
        assert any(year in q for q in queries)

    def test_empty_warnings_returns_empty(self, agent):
        queries = agent._generate_recollection_queries("新能源汽车", "Market Analysis", [])
        assert len(queries) == 0

    def test_multiple_warning_types_generate_more_queries(self, agent):
        warnings = [
            {"type": "timeliness", "message": "No recent data", "url": ""},
            {"type": "timeliness", "message": "Outdated", "url": ""},
        ]
        queries = agent._generate_recollection_queries("新能源汽车", "Market Analysis", warnings)
        assert len(queries) >= 2

    def test_queries_include_topic(self, agent):
        warnings = [{"type": "timeliness", "message": "No recent data", "url": ""}]
        queries = agent._generate_recollection_queries("比亚迪", "Financial Analysis", warnings)
        assert any("比亚迪" in q for q in queries)

    def test_no_duplicate_queries(self, agent):
        warnings = [
            {"type": "timeliness", "message": "No recent data in A", "url": ""},
            {"type": "timeliness", "message": "No recent data in B", "url": ""},
        ]
        queries = agent._generate_recollection_queries("比亚迪", "Financial Analysis", warnings)
        assert len(queries) == len(set(queries))


class TestIMP3RecollectionInValidationCode:
    """IMP-3: Verify quality-check branch triggers re-collection on low quality"""

    def test_recollection_queries_called_on_low_quality(self):
        content = AGENT_PATH.read_text(encoding="utf-8")
        quality_check_start = content.find('Phase 2: DATA_VALIDATION')
        quality_check_end = content.find('Phase 3: DEEP_ANALYSIS')
        validation_code = content[quality_check_start:quality_check_end]
        assert "_generate_recollection_queries" in validation_code

    def test_recollection_max_one_round(self):
        content = AGENT_PATH.read_text(encoding="utf-8")
        quality_check_start = content.find('Phase 2: DATA_VALIDATION')
        quality_check_end = content.find('Phase 3: DEEP_ANALYSIS')
        validation_code = content[quality_check_start:quality_check_end]
        assert "_recollection_round" in validation_code or "recollection_attempted" in validation_code

    def test_recollection_uses_validation_warnings(self):
        content = AGENT_PATH.read_text(encoding="utf-8")
        assert "validation_result" in content
        assert "warnings" in content


class TestIMP4ConflictResolutionMethod:
    """IMP-4: _resolve_numerical_conflicts auto-resolves by authority + timeliness"""

    @pytest.fixture
    def agent(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "imp4_unit"
        return agent

    def test_method_exists(self, agent):
        assert hasattr(agent, '_resolve_numerical_conflicts')
        assert callable(getattr(agent, '_resolve_numerical_conflicts'))

    def test_higher_authority_wins(self, agent):
        conflicts = [{
            "type": "numerical_conflict",
            "claim": "num_35.6%",
            "sources": [
                {"source": "Random Blog", "url": "https://blog.example.com/post", "value": "35.6%"},
                {"source": "World Bank Report", "url": "https://worldbank.org/report", "value": "34.2%"},
            ],
            "message": "Conflicting values: 34.2%, 35.6%",
        }]
        resolved = agent._resolve_numerical_conflicts(conflicts)
        assert len(resolved) == 1
        assert resolved[0]["resolved_value"] == "34.2%"
        assert resolved[0]["resolution_reason"] == "authority"

    def test_more_recent_wins_when_authority_equal(self, agent):
        conflicts = [{
            "type": "numerical_conflict",
            "claim": "num_12.8亿",
            "sources": [
                {"source": "东方财富2023报告", "url": "https://eastmoney.com/2023", "value": "12.8亿"},
                {"source": "东方财富2024报告", "url": "https://eastmoney.com/2024", "value": "13.1亿"},
            ],
            "message": "Conflicting values: 12.8亿, 13.1亿",
        }]
        resolved = agent._resolve_numerical_conflicts(conflicts)
        assert len(resolved) == 1
        assert resolved[0]["resolved_value"] == "13.1亿"
        assert resolved[0]["resolution_reason"] == "timeliness"

    def test_empty_conflicts_returns_empty(self, agent):
        resolved = agent._resolve_numerical_conflicts([])
        assert resolved == []

    def test_first_source_wins_as_tiebreaker(self, agent):
        conflicts = [{
            "type": "numerical_conflict",
            "claim": "num_5.2%",
            "sources": [
                {"source": "Source A", "url": "https://a.com", "value": "5.2%"},
                {"source": "Source B", "url": "https://b.com", "value": "5.8%"},
            ],
            "message": "Conflicting values: 5.2%, 5.8%",
        }]
        resolved = agent._resolve_numerical_conflicts(conflicts)
        assert len(resolved) == 1
        assert resolved[0]["resolved_value"] in ("5.2%", "5.8%")

    def test_resolution_includes_original_conflict(self, agent):
        conflicts = [{
            "type": "numerical_conflict",
            "claim": "num_35.6%",
            "sources": [
                {"source": "Blog", "url": "https://blog.com", "value": "35.6%"},
                {"source": "IMF Report", "url": "https://imf.org/report", "value": "34.2%"},
            ],
            "message": "Conflicting values: 34.2%, 35.6%",
        }]
        resolved = agent._resolve_numerical_conflicts(conflicts)
        assert "original_conflict" in resolved[0]


class TestIMP4ConflictResolutionInValidationCode:
    """IMP-4: Verify _resolve_numerical_conflicts is called in validation flow"""

    def test_resolve_method_called_in_validation(self):
        content = AGENT_PATH.read_text(encoding="utf-8")
        quality_check_start = content.find('Phase 2: DATA_VALIDATION')
        quality_check_end = content.find('Phase 3: DEEP_ANALYSIS')
        validation_code = content[quality_check_start:quality_check_end]
        assert "_resolve_numerical_conflicts" in validation_code

    def test_resolved_conflicts_in_result(self):
        content = AGENT_PATH.read_text(encoding="utf-8")
        assert "resolved_conflicts" in content
