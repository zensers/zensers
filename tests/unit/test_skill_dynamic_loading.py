"""
FIX-1: Skill 动态加载修复测试

原子变更：register_factory + _validate_and_normalize_skills 修复
不可分步上线：两个修复必须同时生效，否则分析 skill 从 _skills 移到 _factories 后被验证丢弃

测试覆盖：
1. register_factory 注册的分析 skill 可通过 get() 获取
2. get() 首次调用触发 factory 实例化，第二次直接返回缓存
3. 分析 skill factory 创建的实例类型正确
4. _validate_and_normalize_skills 同时检查 _skills 和 _factories
5. factory 注册的 skill 名在 _validate_and_normalize_skills 中不被误判为 unknown
6. _get_data_collection_skills 返回的 stock_data 通过 factory 验证后不被丢弃
7. DEEP_ANALYSIS agent 的 required_skills 含 stock_analysis 时 _available_skills 正确包含
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestRegisterFactoryLazyLoading:
    """测试 register_factory 懒加载机制"""

    @pytest.fixture
    def registry(self):
        from src.skills.registry import SkillRegistry
        reg = SkillRegistry()
        return reg

    def test_factory_registered_skill_retrievable_via_get(self, registry):
        from src.skills.analysis import StockDataSkill
        registry.register_factory("stock_data", StockDataSkill)
        skill = registry.get("stock_data")
        assert skill is not None
        assert isinstance(skill, StockDataSkill)

    def test_factory_first_get_triggers_instantiation(self, registry):
        from src.skills.analysis import MarketAnalysisSkill
        call_count = {"count": 0}

        class CountingFactory(MarketAnalysisSkill):
            def __init__(self):
                call_count["count"] += 1
                super().__init__()

        registry.register_factory("market_analysis", CountingFactory)
        assert call_count["count"] == 0

        skill1 = registry.get("market_analysis")
        assert call_count["count"] == 1

        skill2 = registry.get("market_analysis")
        assert call_count["count"] == 1
        assert skill1 is skill2

    def test_all_seven_analysis_skills_factory_types(self, registry):
        from src.skills.analysis import (
            MarketAnalysisSkill, DataAnalysisSkill, StockDataSkill,
            StockAnalysisSkill, PolicyAnalysisSkill, TechTrendSkill,
            RiskAnalysisSkill,
        )
        skill_map = {
            "market_analysis": MarketAnalysisSkill,
            "data_analysis": DataAnalysisSkill,
            "stock_data": StockDataSkill,
            "stock_analysis": StockAnalysisSkill,
            "policy_analysis": PolicyAnalysisSkill,
            "tech_trend": TechTrendSkill,
            "risk_analysis": RiskAnalysisSkill,
        }
        for name, cls in skill_map.items():
            registry.register_factory(name, cls)

        for name, cls in skill_map.items():
            skill = registry.get(name)
            assert skill is not None, f"get('{name}') returned None"
            assert isinstance(skill, cls), f"get('{name}') returned {type(skill)}, expected {cls}"

    def test_factory_skill_listed_in_list_all(self, registry):
        from src.skills.analysis import StockDataSkill
        registry.register_factory("stock_data", StockDataSkill)
        names = [s.name for s in registry.list_all()]
        assert "stock_data" in names

    def test_factory_skill_not_instantiated_until_get(self, registry):
        from src.skills.analysis import StockDataSkill
        registry.register_factory("stock_data", StockDataSkill)
        assert "stock_data" not in registry._skills
        assert "stock_data" in registry._factories


class TestValidateAndNormalizeSkillsFix:
    """测试 _validate_and_normalize_skills 同时检查 _skills 和 _factories"""

    @pytest.fixture
    def factory(self):
        from src.core.agents.factory import DynamicAgentFactory
        return DynamicAgentFactory()

    def test_factory_skill_not_dropped_as_unknown(self, factory):
        from src.skills.analysis import StockDataSkill
        factory._skill_registry.register_factory("stock_data", StockDataSkill)

        norm_req, norm_opt = factory._validate_and_normalize_skills(
            agent_id="test_agent",
            required_skills=["stock_data"],
            optional_skills=[],
        )
        assert "stock_data" in norm_req, "stock_data should not be dropped as unknown"

    def test_mixed_skills_and_factories_both_recognized(self, factory):
        from src.skills.analysis import StockAnalysisSkill
        factory._skill_registry.register_factory("stock_analysis", StockAnalysisSkill)

        norm_req, norm_opt = factory._validate_and_normalize_skills(
            agent_id="test_agent",
            required_skills=["llm_skill", "stock_analysis"],
            optional_skills=[],
        )
        assert "llm_skill" in norm_req
        assert "stock_analysis" in norm_req

    def test_unknown_skill_still_dropped(self, factory):
        norm_req, norm_opt = factory._validate_and_normalize_skills(
            agent_id="test_agent",
            required_skills=["nonexistent_skill_xyz"],
            optional_skills=[],
        )
        assert "nonexistent_skill_xyz" not in norm_req

    def test_data_collection_stock_data_not_dropped(self, factory):
        from src.skills.analysis import StockDataSkill
        factory._skill_registry.register_factory("stock_data", StockDataSkill)

        norm_req, norm_opt = factory._validate_and_normalize_skills(
            agent_id="data_collection_agent",
            required_skills=["search_skill", "news_search", "llm_skill", "stock_data"],
            optional_skills=[],
        )
        assert "stock_data" in norm_req, "stock_data must survive validation for DATA_COLLECTION"

    def test_deep_analysis_skills_not_dropped(self, factory):
        from src.skills.analysis import StockAnalysisSkill, DataAnalysisSkill
        factory._skill_registry.register_factory("stock_analysis", StockAnalysisSkill)
        factory._skill_registry.register_factory("data_analysis", DataAnalysisSkill)

        norm_req, norm_opt = factory._validate_and_normalize_skills(
            agent_id="deep_analysis_agent",
            required_skills=["llm_skill", "stock_analysis", "data_analysis"],
            optional_skills=[],
        )
        assert "stock_analysis" in norm_req
        assert "data_analysis" in norm_req


class TestOrchestratorRegisterFactory:
    """测试 Orchestrator 使用 register_factory 注册分析 skill"""

    def test_orchestrator_registers_analysis_skills_via_factory(self):
        from src.skills.registry import SkillRegistry
        from src.skills.analysis import (
            MarketAnalysisSkill, DataAnalysisSkill, StockDataSkill,
            StockAnalysisSkill, PolicyAnalysisSkill, TechTrendSkill,
            RiskAnalysisSkill,
        )

        registry = SkillRegistry()
        registry.register_core_skills()

        for name, cls in [
            ("market_analysis", MarketAnalysisSkill),
            ("data_analysis", DataAnalysisSkill),
            ("stock_data", StockDataSkill),
            ("stock_analysis", StockAnalysisSkill),
            ("policy_analysis", PolicyAnalysisSkill),
            ("tech_trend", TechTrendSkill),
            ("risk_analysis", RiskAnalysisSkill),
        ]:
            registry.register_factory(name, cls)

        for name in ["market_analysis", "data_analysis", "stock_data",
                      "stock_analysis", "policy_analysis", "tech_trend", "risk_analysis"]:
            assert name in registry._factories, f"'{name}' should be in _factories"
            skill = registry.get(name)
            assert skill is not None, f"get('{name}') should return a skill instance"

    def test_orchestrator_no_longer_directly_assigns_skills_dict(self):
        from src.skills.registry import SkillRegistry
        from src.skills.analysis import StockDataSkill

        registry = SkillRegistry()
        registry.register_factory("stock_data", StockDataSkill)

        assert "stock_data" not in registry._skills, "Should NOT be in _skills before get()"
        assert "stock_data" in registry._factories

        skill = registry.get("stock_data")
        assert "stock_data" in registry._skills, "Should be in _skills after get()"


class TestEndToEndSkillAvailability:
    """端到端测试：skill 从注册到 agent._available_skills 的完整路径"""

    def test_data_collection_agent_has_stock_data(self):
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import StockDataSkill

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("stock_data", StockDataSkill)

        capability = AgentCapability(
            name="Data Collection Agent",
            description="Collects data",
            required_skills=["search_skill", "news_search", "llm_skill", "stock_data"],
        )

        agent = factory.create_agent(
            agent_id="data_col_001",
            capability=capability,
            context={"topic": "比亚迪财务分析"},
        )

        assert "stock_data" in agent._available_skills, \
            f"stock_data must be in available_skills, got: {agent._available_skills}"

    def test_deep_analysis_agent_has_analysis_skills(self):
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import StockAnalysisSkill, DataAnalysisSkill

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("stock_analysis", StockAnalysisSkill)
        factory._skill_registry.register_factory("data_analysis", DataAnalysisSkill)

        capability = AgentCapability(
            name="Deep Analysis Agent",
            description="Analyzes data",
            required_skills=["llm_skill", "stock_analysis", "data_analysis"],
        )

        agent = factory.create_agent(
            agent_id="deep_ana_001",
            capability=capability,
            context={"topic": "比亚迪财务分析"},
        )

        assert "stock_analysis" in agent._available_skills, \
            f"stock_analysis must be in available_skills, got: {agent._available_skills}"
        assert "data_analysis" in agent._available_skills, \
            f"data_analysis must be in available_skills, got: {agent._available_skills}"


class TestLoadSkillsForCategoryFix:
    """FIX-2: load_skills_for_category 支持 factory skill"""

    @pytest.fixture
    def registry(self):
        from src.skills.registry import SkillRegistry
        from src.skills.analysis import (
            MarketAnalysisSkill, DataAnalysisSkill, StockDataSkill,
            StockAnalysisSkill, PolicyAnalysisSkill, TechTrendSkill,
            RiskAnalysisSkill,
        )
        reg = SkillRegistry()
        reg.register_core_skills()
        for name, cls in [
            ("market_analysis", MarketAnalysisSkill),
            ("data_analysis", DataAnalysisSkill),
            ("stock_data", StockDataSkill),
            ("stock_analysis", StockAnalysisSkill),
            ("policy_analysis", PolicyAnalysisSkill),
            ("tech_trend", TechTrendSkill),
            ("risk_analysis", RiskAnalysisSkill),
        ]:
            reg.register_factory(name, cls)
        return reg

    def test_financial_analysis_category_returns_stock_data(self, registry):
        loaded = registry.load_skills_for_category("financial-analysis")
        assert "stock_data" in loaded, f"financial-analysis should load stock_data, got: {loaded}"

    def test_market_analysis_category_returns_market_analysis(self, registry):
        loaded = registry.load_skills_for_category("market-analysis")
        assert "market_analysis" in loaded, f"market-analysis should load market_analysis, got: {loaded}"

    def test_research_category_returns_nonempty(self, registry):
        loaded = registry.load_skills_for_category("research")
        assert len(loaded) > 0, "research category should load at least one skill"

    def test_data_analysis_category_returns_data_analysis(self, registry):
        loaded = registry.load_skills_for_category("data-analysis")
        assert "data_analysis" in loaded, f"data-analysis should load data_analysis, got: {loaded}"

    def test_synthesis_category_returns_llm(self, registry):
        loaded = registry.load_skills_for_category("synthesis")
        assert "llm_skill" in loaded, f"synthesis should load llm_skill, got: {loaded}"

    def test_calibration_category_returns_llm(self, registry):
        loaded = registry.load_skills_for_category("calibration")
        assert "llm_skill" in loaded, f"calibration should load llm_skill, got: {loaded}"

    def test_factory_skill_instantiated_on_load(self, registry):
        assert "stock_data" not in registry._skills
        loaded = registry.load_skills_for_category("financial-analysis")
        assert "stock_data" in registry._skills, "stock_data should be instantiated after load"


class TestDiscoverSkillsFactorySupport:
    """FIX-3: discover_skills 支持 factory skill + SKILL_KEYWORDS 扩展"""

    @pytest.fixture
    def registry(self):
        from src.skills.registry import SkillRegistry
        from src.skills.analysis import (
            MarketAnalysisSkill, DataAnalysisSkill, StockDataSkill,
            StockAnalysisSkill, PolicyAnalysisSkill, TechTrendSkill,
            RiskAnalysisSkill,
        )
        reg = SkillRegistry()
        reg.register_core_skills()
        for name, cls in [
            ("market_analysis", MarketAnalysisSkill),
            ("data_analysis", DataAnalysisSkill),
            ("stock_data", StockDataSkill),
            ("stock_analysis", StockAnalysisSkill),
            ("policy_analysis", PolicyAnalysisSkill),
            ("tech_trend", TechTrendSkill),
            ("risk_analysis", RiskAnalysisSkill),
        ]:
            reg.register_factory(name, cls)
        return reg

    def test_discover_stock_data_by_keyword(self, registry):
        discovered = registry.discover_skills("financial data", auto_load=True)
        assert "stock_data" in discovered, f"'financial data' should discover stock_data, got: {discovered}"

    def test_discover_stock_analysis_by_keyword(self, registry):
        discovered = registry.discover_skills("stock analysis", auto_load=True)
        assert "stock_analysis" in discovered, f"'stock analysis' should discover stock_analysis, got: {discovered}"

    def test_discover_market_analysis_by_keyword(self, registry):
        discovered = registry.discover_skills("market analysis", auto_load=True)
        assert "market_analysis" in discovered, f"'market analysis' should discover market_analysis, got: {discovered}"

    def test_discover_data_analysis_by_keyword(self, registry):
        discovered = registry.discover_skills("statistical analysis", auto_load=True)
        assert "data_analysis" in discovered, f"'statistical analysis' should discover data_analysis, got: {discovered}"

    def test_discover_risk_analysis_by_keyword(self, registry):
        discovered = registry.discover_skills("risk assessment", auto_load=True)
        assert "risk_analysis" in discovered, f"'risk assessment' should discover risk_analysis, got: {discovered}"

    def test_discover_policy_analysis_by_keyword(self, registry):
        discovered = registry.discover_skills("policy analysis", auto_load=True)
        assert "policy_analysis" in discovered, f"'policy analysis' should discover policy_analysis, got: {discovered}"

    def test_discover_tech_trend_by_keyword(self, registry):
        discovered = registry.discover_skills("technology trend", auto_load=True)
        assert "tech_trend" in discovered, f"'technology trend' should discover tech_trend, got: {discovered}"

    def test_discover_factory_skill_auto_load_instantiates(self, registry):
        assert "stock_data" not in registry._skills
        registry.discover_skills("financial data", auto_load=True)
        assert "stock_data" in registry._skills, "auto_load should instantiate factory skill"

    def test_discover_without_auto_load_no_instantiation(self, registry):
        discovered = registry.discover_skills("financial data", auto_load=False)
        assert "stock_data" in discovered
        assert "stock_data" not in registry._skills, "auto_load=False should not instantiate"


class TestAddSkillMethod:
    """FIX-4: add_skill() 运行时扩展 _available_skills"""

    @pytest.fixture
    def agent_with_registry(self):
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import StockDataSkill

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("stock_data", StockDataSkill)

        capability = AgentCapability(
            name="Test Agent",
            description="Test",
            required_skills=["llm_skill"],
        )
        agent = factory.create_agent("add_skill_test", capability, context={})
        return agent

    def test_add_skill_adds_to_available_skills(self, agent_with_registry):
        result = agent_with_registry.add_skill("stock_data")
        assert result is True
        assert "stock_data" in agent_with_registry._available_skills

    def test_add_skill_no_duplicate(self, agent_with_registry):
        agent_with_registry.add_skill("stock_data")
        result = agent_with_registry.add_skill("stock_data")
        assert result is False
        assert agent_with_registry._available_skills.count("stock_data") == 1

    def test_add_skill_nonexistent_returns_false(self, agent_with_registry):
        result = agent_with_registry.add_skill("nonexistent_skill_xyz")
        assert result is False
        assert "nonexistent_skill_xyz" not in agent_with_registry._available_skills

    def test_add_skill_syncs_session_template(self, agent_with_registry):
        mock_template = {"skill_names": ["llm_skill"]}
        mock_session = MagicMock()
        mock_session.agent_template = mock_template
        agent_with_registry._session = mock_session

        agent_with_registry.add_skill("stock_data")
        assert "stock_data" in mock_template["skill_names"]

    def test_add_skill_no_session_template_no_error(self, agent_with_registry):
        agent_with_registry._session = MagicMock()
        agent_with_registry._session.agent_template = None
        result = agent_with_registry.add_skill("stock_data")
        assert result is True
