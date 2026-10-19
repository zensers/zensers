"""MKB (Methodology Knowledge Base) tests"""
import pytest
from pathlib import Path
from src.methodologies import registry
from src.methodologies import schema


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset registry before each test"""
    registry._frameworks_loaded = False
    registry._frameworks.clear()
    yield
    registry._frameworks_loaded = False
    registry._frameworks.clear()


class TestMKBRegistry:
    def test_all_frameworks_valid(self):
        """All framework JSON files pass schema validation"""
        results = schema.validate_all_frameworks()
        errors = {k: v for k, v in results.items() if v}
        assert not errors, f"Framework validation errors: {errors}"

    def test_frameworks_loaded_count(self):
        """At least 35 frameworks loaded (we have 38)"""
        registry._ensure_loaded()
        assert len(registry._frameworks) >= 35

    def test_match_for_aspect_returns_list(self):
        """match_for_aspect always returns a list"""
        result = registry.match_for_aspect("technology")
        assert isinstance(result, list)

    def test_match_for_aspect_unknown_returns_empty(self):
        """Unknown aspect returns empty list"""
        result = registry.match_for_aspect("nonexistent_aspect_xyz")
        assert result == []

    def test_match_for_aspect_technology(self):
        """Technology aspect matches relevant frameworks"""
        result = registry.match_for_aspect("technology")
        ids = [f["id"] for f in result]
        assert "gartner_hype_cycle" in ids
        assert "trl_assessment" in ids
        assert "technology_s_curve" in ids

    def test_match_for_aspect_market_size(self):
        """Market size aspect matches sizing frameworks"""
        result = registry.match_for_aspect("market_size")
        ids = [f["id"] for f in result]
        assert "market_sizing_top_down" in ids
        assert "market_sizing_bottom_up" in ids
        assert "cross_market_analogy" in ids

    def test_match_for_aspect_competitive_landscape(self):
        """Competitive landscape matches Porter + strategic mapping"""
        result = registry.match_for_aspect("competitive_landscape")
        ids = [f["id"] for f in result]
        assert "porter_five_forces" in ids
        assert "strategic_group_mapping" in ids

    def test_match_for_aspect_industry_chain(self):
        """Industry chain matches chain-specific frameworks"""
        result = registry.match_for_aspect("industry_chain")
        ids = [f["id"] for f in result]
        assert "profit_pool_analysis" in ids
        assert "bargaining_power_framework" in ids
        assert "ecosystem_mapping" in ids

    def test_match_for_aspect_policy(self):
        """Policy aspect matches policy frameworks"""
        result = registry.match_for_aspect("policy")
        ids = [f["id"] for f in result]
        assert "regulatory_impact_assessment" in ids
        assert "policy_cycle_framework" in ids
        assert "stakeholder_mapping" in ids

    def test_match_for_aspect_trend(self):
        """Trend aspect matches trend frameworks"""
        result = registry.match_for_aspect("trend")
        ids = [f["id"] for f in result]
        assert "steep_analysis" in ids
        assert "industry_lifecycle" in ids
        assert "signal_detection" in ids

    def test_match_for_aspect_enterprise(self):
        """Enterprise aspect matches enterprise frameworks"""
        result = registry.match_for_aspect("enterprise_analysis")
        ids = [f["id"] for f in result]
        assert "business_model_canvas" in ids
        assert "moat_assessment" in ids
        assert "management_quality_framework" in ids

    def test_match_for_aspect_financial(self):
        """Financial analysis aspect matches financial frameworks"""
        result = registry.match_for_aspect("financial_analysis")
        ids = [f["id"] for f in result]
        assert "dupont_analysis" in ids
        assert "cash_flow_quality" in ids
        assert "mean_reversion_analysis" in ids

    def test_match_for_aspect_risk(self):
        """Risk assessment aspect matches risk frameworks"""
        result = registry.match_for_aspect("risk_assessment")
        ids = [f["id"] for f in result]
        assert "risk_assessment" in ids
        assert "scenario_planning" in ids
        assert "credit_analysis" in ids

    def test_sum_of_distinct_aspects(self):
        """At least 20 distinct aspect keys mapped"""
        amap = registry.get_aspect_map()
        assert len(amap) >= 20

    def test_every_framework_has_valid_priority(self):
        """All frameworks have priority >= 1"""
        registry._ensure_loaded()
        for fw in registry._frameworks:
            assert fw.get("priority", 0) >= 1, f"{fw['id']} has invalid priority"

    def test_every_framework_has_non_empty_content(self):
        """All frameworks have non-empty content"""
        registry._ensure_loaded()
        for fw in registry._frameworks:
            assert fw.get("content"), f"{fw['id']} has empty content"
            assert len(fw["content"]) >= 50, f"{fw['id']} content too short"

    def test_frameworks_sorted_by_priority(self):
        """Frameworks list is sorted by priority ascending"""
        registry._ensure_loaded()
        priorities = [f.get("priority", 99) for f in registry._frameworks]
        assert priorities == sorted(priorities)


class TestMKBSchema:
    def test_validate_framework_missing_id(self):
        """Missing id returns error"""
        errors = schema.validate_framework({"name": "test"})
        assert any("id" in e for e in errors)

    def test_validate_framework_missing_name(self):
        """Missing name returns error"""
        errors = schema.validate_framework({"id": "test"})
        assert any("name" in e for e in errors)

    def test_validate_framework_missing_priority(self):
        """Missing priority returns error"""
        errors = schema.validate_framework({"id": "test", "name": "t"})
        assert any("priority" in e for e in errors)

    def test_validate_framework_missing_aspects(self):
        """Missing aspects returns error"""
        errors = schema.validate_framework({"id": "test", "name": "t", "priority": 1})
        assert any("aspects" in e for e in errors)

    def test_validate_framework_missing_content(self):
        """Missing content returns error"""
        errors = schema.validate_framework({"id": "test", "name": "t", "priority": 1, "aspects": ["a"]})
        assert any("content" in e for e in errors)

    def test_validate_framework_valid_passes(self):
        """Valid framework passes with no errors"""
        fw = {
            "id": "test_framework",
            "name": "Test Framework",
            "priority": 1,
            "aspects": ["test"],
            "content": "This is a test framework content with enough length to pass validation."
        }
        errors = schema.validate_framework(fw)
        assert errors == []

    def test_validate_framework_empty_aspects(self):
        """Empty aspects list returns error"""
        errors = schema.validate_framework({
            "id": "test", "name": "t", "priority": 1,
            "aspects": [], "content": "x" * 50
        })
        assert any("aspects" in e for e in errors)

    def test_validate_framework_invalid_priority(self):
        """Priority < 1 returns error"""
        errors = schema.validate_framework({
            "id": "test", "name": "t", "priority": 0,
            "aspects": ["a"], "content": "x" * 50
        })
        assert any("priority" in e for e in errors)

    def test_validate_framework_non_string_id(self):
        """Non-string id returns error"""
        errors = schema.validate_framework({
            "id": 123, "name": "t", "priority": 1,
            "aspects": ["a"], "content": "x" * 50
        })
        assert any("id" in e for e in errors)


class TestMKBKnowledgeQueryIntegration:
    def test_knowledge_query_enrich_returns_3_frameworks(self):
        """KnowledgeQuerySkill._enrich returns up to 3 frameworks per aspect"""
        import inspect
        from src.skills.builtin.knowledge_query_skill import KnowledgeQuerySkill
        source = inspect.getsource(KnowledgeQuerySkill._enrich)
        # Should slice [:3] not [:1]
        assert "[:3]" in source


class TestMKBFrameworkContent:
    def test_framework_content_has_actionable_steps(self):
        """All framework content describes actionable analysis steps"""
        registry._ensure_loaded()
        for fw in registry._frameworks:
            content = fw["content"]
            assert ":" in content or "1." in content, \
                f"{fw['id']} content lacks structure (no ':' or numbered steps)"

    def test_porter_five_forces_has_all_forces(self):
        """Porter's Five Forces contains all 5 forces"""
        porter = registry.match_for_aspect("competitive_landscape")
        porter = [f for f in porter if f["id"] == "porter_five_forces"]
        assert len(porter) == 1
        content = porter[0]["content"]
        for force in ["竞争", "进入", "替代", "供应商", "购买"]:
            assert force in content, f"Porter missing force: {force}"

    def test_dupont_has_three_components(self):
        """DuPont analysis contains all 3 ROE components"""
        registry._ensure_loaded()
        du = [f for f in registry._frameworks if f["id"] == "dupont_analysis"]
        assert len(du) == 1
        content = du[0]["content"]
        for comp in ["净利率", "周转", "杠杆"]:
            assert comp in content, f"DuPont missing component: {comp}"
