"""
Task 4.1+4.2: Delete dead code — _fetch_structured_data, _infer_stock_actions,
_format_structured_data, _format_financials, _format_price_history,
_format_key_metrics, _format_company_info, _FINANCIALS_KEY_COLUMNS, _THS_METRIC_CN
"""
import pytest
import inspect
from src.core.agents.generic_agent import GenericAgent


@pytest.fixture
def agent():
    return GenericAgent(agent_id="test_42", agent_type="dynamic", config={})


class TestDeadCodeRemoved:
    def test_fetch_structured_data_removed(self, agent):
        assert not hasattr(agent, "_fetch_structured_data"), \
            "_fetch_structured_data should be removed (dead code)"

    def test_infer_stock_actions_removed(self, agent):
        assert not hasattr(agent, "_infer_stock_actions"), \
            "_infer_stock_actions should be removed (dead code)"

    def test_format_structured_data_removed(self, agent):
        assert not hasattr(agent, "_format_structured_data"), \
            "_format_structured_data should be removed (dead code)"

    def test_format_financials_removed(self, agent):
        assert not hasattr(agent, "_format_financials"), \
            "_format_financials should be removed (dead code)"

    def test_format_price_history_removed(self, agent):
        assert not hasattr(agent, "_format_price_history"), \
            "_format_price_history should be removed (dead code)"

    def test_format_key_metrics_removed(self, agent):
        assert not hasattr(agent, "_format_key_metrics"), \
            "_format_key_metrics should be removed (dead code)"

    def test_format_company_info_removed(self, agent):
        assert not hasattr(agent, "_format_company_info"), \
            "_format_company_info should be removed (dead code)"

    def test_financials_key_columns_removed(self, agent):
        assert not hasattr(GenericAgent, "_FINANCIALS_KEY_COLUMNS"), \
            "_FINANCIALS_KEY_COLUMNS should be removed from GenericAgent"

    def test_ths_metric_cn_removed(self, agent):
        assert not hasattr(GenericAgent, "_THS_METRIC_CN"), \
            "_THS_METRIC_CN should be removed from GenericAgent"


class TestStockDataActionInferenceViaManifest:
    """Verify stock_data action inference still works via manifest (not _infer_stock_actions)."""

    @pytest.mark.asyncio
    async def test_financial_aspect_returns_financials_action(self):
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path
        skills_dir = Path("src/skills")
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)
        stock_manifest = next((m for m in manifests if m.name == "stock_data"), None)
        assert stock_manifest is not None, "stock_data SKILL.md must exist"
        assert stock_manifest.action_rules, "stock_data must have action_rules"

        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        skill._manifest = stock_manifest
        actions = skill.infer_actions("盈利能力分析", "600519")
        assert "financials" in actions, f"Expected 'financials' in actions for 盈利, got {actions}"

    @pytest.mark.asyncio
    async def test_company_aspect_returns_company_info(self):
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path
        skills_dir = Path("src/skills")
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)
        stock_manifest = next((m for m in manifests if m.name == "stock_data"), None)
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        skill._manifest = stock_manifest
        actions = skill.infer_actions("公司概况", "600519")
        assert "company_info" in actions, f"Expected 'company_info' in actions for 公司, got {actions}"

    @pytest.mark.asyncio
    async def test_valuation_aspect_returns_key_metrics(self):
        from src.skills.discovery import SkillDiscovery
        from pathlib import Path
        skills_dir = Path("src/skills")
        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)
        stock_manifest = next((m for m in manifests if m.name == "stock_data"), None)
        from src.skills.analysis.stock_data import StockDataSkill
        skill = StockDataSkill()
        skill._manifest = stock_manifest
        actions = skill.infer_actions("估值分析", "600519")
        assert "key_metrics" in actions, f"Expected 'key_metrics' in actions for 估值, got {actions}"


class TestNoReferencesToDeletedMethods:
    """Verify no remaining references to deleted methods in generic_agent.py."""

    def test_no_fetch_structured_data_references(self):
        import src.core.agents.generic_agent as mod
        source = inspect.getsource(mod.GenericAgent)
        assert "_fetch_structured_data" not in source, \
            "generic_agent.py still references _fetch_structured_data"

    def test_no_infer_stock_actions_references(self):
        import src.core.agents.generic_agent as mod
        source = inspect.getsource(mod.GenericAgent)
        assert "_infer_stock_actions" not in source, \
            "generic_agent.py still references _infer_stock_actions"

    def test_no_format_structured_data_references(self):
        import src.core.agents.generic_agent as mod
        source = inspect.getsource(mod.GenericAgent)
        assert "_format_structured_data" not in source, \
            "generic_agent.py still references _format_structured_data"
