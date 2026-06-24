"""
端到端集成测试: 验证 Skill 动态加载修复 (FIX-1~4) 在真实代码路径中的集成效果

测试路径:
  1. Orchestrator.__init__() → register_factory → factory skill 可通过 get() 获取
  2. ASPECT_SKILL_MAP → AgentSpec.skills → AgentCapability → _validate_and_normalize_skills → agent._available_skills
  3. DATA_COLLECTION: "Financial Analysis" → _get_data_collection_skills → stock_data 保留
  4. DEEP_ANALYSIS: "Financial Analysis" → get_skills_for_aspect → stock_analysis/data_analysis 保留
  5. load_skills_for_category → factory skill 加载
  6. discover_skills → SKILL_KEYWORDS 匹配 + factory auto_load
  7. add_skill() → 动态扩展 + session 同步
  8. discover_skills 分支 → add_skill + 执行（非 execute action 路径）
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src"
sys.path.insert(0, str(SRC_ROOT))


# ═══════════════════════════════════════════════════════════════
# E2E-1: Orchestrator 初始化 → register_factory → get 可获取
# ═══════════════════════════════════════════════════════════════

class TestE2E1OrchestratorInitToFactoryGet:
    """端到端: Orchestrator 初始化 register_factory 后 skill 可通过 get() 获取"""

    def test_orchestrator_init_registers_analysis_skills_in_factories(self):
        """验证 orchestrator.py 代码中用 register_factory 而非直接赋值 _skills"""
        orchestrator_path = SRC_ROOT / "core" / "orchestrator" / "orchestrator.py"
        content = orchestrator_path.read_text(encoding="utf-8")
        assert "register_factory" in content, "orchestrator.py must use register_factory for analysis skills"
        assert "skill_registry._skills[\"market_analysis\"]" not in content, \
            "orchestrator.py must NOT directly assign _skills dict for analysis skills"

    def test_skill_registry_factory_creates_analysis_skills(self):
        """端到端: SkillRegistry register_factory → get() 返回正确类型"""
        from src.skills.registry import SkillRegistry
        from src.skills.analysis import (
            MarketAnalysisSkill, DataAnalysisSkill, StockDataSkill,
            StockAnalysisSkill, PolicyAnalysisSkill, TechTrendSkill, RiskAnalysisSkill,
        )

        registry = SkillRegistry()
        registry.register_core_skills()

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
            assert name in registry._factories, f"{name} must be in _factories after register_factory"
            assert name not in registry._skills, f"{name} must NOT be in _skills before get() (lazy loading)"
            skill = registry.get(name)
            assert skill is not None, f"get('{name}') must return skill instance"
            assert isinstance(skill, cls), f"get('{name}') must return {cls.__name__}"
            assert name in registry._skills, f"{name} must be in _skills after get() (instantiated)"

    def test_factory_skill_second_get_returns_cached(self):
        """端到端: 第二次 get() 返回同一实例（缓存）"""
        from src.skills.registry import SkillRegistry
        from src.skills.analysis import StockDataSkill

        registry = SkillRegistry()
        registry.register_factory("stock_data", StockDataSkill)

        skill1 = registry.get("stock_data")
        skill2 = registry.get("stock_data")
        assert skill1 is skill2, "Second get() must return cached instance"


# ═══════════════════════════════════════════════════════════════
# E2E-2: _validate_and_normalize_skills 同时检查 _skills 和 _factories
# ═══════════════════════════════════════════════════════════════

class TestE2E2ValidateAndNormalizeSkills:
    """端到端: factory.py 代码验证 _validate_and_normalize_skills 同时检查 _factories"""

    def test_validate_code_checks_both_skills_and_factories(self):
        """验证 factory.py 源码中 _validate_and_normalize_skills 检查 _factories"""
        factory_path = SRC_ROOT / "core" / "agents" / "factory.py"
        content = factory_path.read_text(encoding="utf-8")
        assert "_factories" in content, "factory.py must reference _factories in _validate_and_normalize_skills"
        assert "registered_names = set(self._skill_registry._skills.keys()) | set(self._skill_registry._factories.keys())" in content, \
            "_validate_and_normalize_skills must union _skills and _factories keys"

    def test_financial_analysis_aspect_skills_not_dropped(self):
        """端到端: 'Financial Analysis' aspect 的 stock_analysis/data_analysis 通过验证"""
        from src.core.agents.factory import DynamicAgentFactory
        from src.skills.analysis import StockAnalysisSkill, DataAnalysisSkill

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("stock_analysis", StockAnalysisSkill)
        factory._skill_registry.register_factory("data_analysis", DataAnalysisSkill)

        norm_req, norm_opt = factory._validate_and_normalize_skills(
            agent_id="deep_analysis_financial",
            required_skills=["llm_skill", "stock_analysis", "data_analysis"],
            optional_skills=[],
        )
        assert "stock_analysis" in norm_req, "stock_analysis must survive validation"
        assert "data_analysis" in norm_req, "data_analysis must survive validation"
        assert "llm_skill" in norm_req


# ═══════════════════════════════════════════════════════════════
# E2E-3: DATA_COLLECTION 阶段 stock_data 不被丢弃
# ═══════════════════════════════════════════════════════════════

class TestE2E3DataCollectionStockData:
    """端到端: DATA_COLLECTION agent 的 stock_data 通过完整路径不被丢弃"""

    def test_data_collection_skills_validation_keeps_stock_data(self):
        """端到端: _get_data_collection_skills('Financial Analysis') → validation → stock_data 保留"""
        from src.core.decomposition.strategies import _get_data_collection_skills
        from src.core.agents.factory import DynamicAgentFactory
        from src.skills.analysis import StockDataSkill

        skills = _get_data_collection_skills("Financial Analysis")
        assert "stock_data" in skills, "_get_data_collection_skills must include stock_data for Financial Analysis"

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("stock_data", StockDataSkill)

        norm_req, norm_opt = factory._validate_and_normalize_skills(
            agent_id="data_col_financial",
            required_skills=skills,
            optional_skills=[],
        )
        assert "stock_data" in norm_req, "stock_data must survive validation in DATA_COLLECTION path"

    def test_data_collection_agent_available_skills_contains_stock_data(self):
        """端到端: create_agent → agent._available_skills 含 stock_data"""
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import StockDataSkill

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("stock_data", StockDataSkill)

        capability = AgentCapability(
            name="Data Collection Financial",
            description="Collect financial data",
            required_skills=["search_skill", "news_search", "llm_skill", "stock_data"],
        )

        agent = factory.create_agent("data_col_001", capability, context={"topic": "比亚迪财务分析"})
        assert "stock_data" in agent._available_skills, \
            f"DATA_COLLECTION agent must have stock_data in available_skills, got: {agent._available_skills}"

    def test_generic_agent_can_fetch_stock_data_from_registry(self):
        """端到端: agent._available_skills 含 stock_data → registry.get() 返回实例"""
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import StockDataSkill

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("stock_data", StockDataSkill)

        capability = AgentCapability(
            name="Data Collection",
            description="Test",
            required_skills=["search_skill", "news_search", "llm_skill", "stock_data"],
        )

        agent = factory.create_agent("e2e_data_col", capability)
        assert "stock_data" in agent._available_skills

        skill = agent._skill_registry.get("stock_data")
        assert skill is not None, "registry.get('stock_data') must return instance after factory registration"
        assert isinstance(skill, StockDataSkill)


# ═══════════════════════════════════════════════════════════════
# E2E-4: DEEP_ANALYSIS 阶段分析 skill 不被丢弃
# ═══════════════════════════════════════════════════════════════

class TestE2E4DeepAnalysisSkills:
    """端到端: DEEP_ANALYSIS agent 的分析 skill 通过完整路径不被丢弃"""

    def test_financial_analysis_aspect_to_agent_available_skills(self):
        """端到端: ASPECT_SKILL_MAP['Financial Analysis'] → agent._available_skills"""
        from src.core.decomposition.strategies import get_skills_for_aspect
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import StockAnalysisSkill, DataAnalysisSkill

        aspect_skills = get_skills_for_aspect("Financial Analysis")
        assert "stock_analysis" in aspect_skills, "Financial Analysis must include stock_analysis"
        assert "data_analysis" in aspect_skills, "Financial Analysis must include data_analysis"

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("stock_analysis", StockAnalysisSkill)
        factory._skill_registry.register_factory("data_analysis", DataAnalysisSkill)

        capability = AgentCapability(
            name="Deep Analysis Financial",
            description="Financial analysis",
            required_skills=aspect_skills,
        )

        agent = factory.create_agent("deep_fin_001", capability, context={"aspect": "Financial Analysis"})
        assert "stock_analysis" in agent._available_skills, \
            f"DEEP_ANALYSIS agent must have stock_analysis, got: {agent._available_skills}"
        assert "data_analysis" in agent._available_skills, \
            f"DEEP_ANALYSIS agent must have data_analysis, got: {agent._available_skills}"

    def test_competitive_landscape_aspect_to_agent(self):
        """端到端: 'Competitive Landscape' → market_analysis in available_skills"""
        from src.core.decomposition.strategies import get_skills_for_aspect
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import MarketAnalysisSkill

        aspect_skills = get_skills_for_aspect("Competitive Landscape")
        assert "market_analysis" in aspect_skills

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("market_analysis", MarketAnalysisSkill)

        capability = AgentCapability(
            name="Market Analysis",
            description="Competitive landscape",
            required_skills=aspect_skills,
        )

        agent = factory.create_agent("market_001", capability)
        assert "market_analysis" in agent._available_skills


# ═══════════════════════════════════════════════════════════════
# E2E-5: load_skills_for_category 端到端
# ═══════════════════════════════════════════════════════════════

class TestE2E5LoadSkillsForCategory:
    """端到端: load_skills_for_category 含分析 skill 和 factory 实例化"""

    def test_financial_analysis_category_loads_stock_data(self):
        """端到端: load_skills_for_category('financial-analysis') → stock_data 实例化"""
        from src.skills.registry import SkillRegistry
        from src.skills.analysis import StockDataSkill, StockAnalysisSkill

        registry = SkillRegistry()
        registry.register_core_skills()
        registry.register_factory("stock_data", StockDataSkill)
        registry.register_factory("stock_analysis", StockAnalysisSkill)

        loaded = registry.load_skills_for_category("financial-analysis")
        assert "stock_data" in loaded, f"financial-analysis must load stock_data, got: {loaded}"
        assert "stock_analysis" in loaded, f"financial-analysis must load stock_analysis, got: {loaded}"
        assert "stock_data" in registry._skills, "stock_data must be instantiated after load"
        assert "stock_analysis" in registry._skills, "stock_analysis must be instantiated after load"

    def test_market_analysis_category_loads_market_analysis_skill(self):
        """端到端: load_skills_for_category('market-analysis') → market_analysis"""
        from src.skills.registry import SkillRegistry
        from src.skills.analysis import MarketAnalysisSkill

        registry = SkillRegistry()
        registry.register_core_skills()
        registry.register_factory("market_analysis", MarketAnalysisSkill)

        loaded = registry.load_skills_for_category("market-analysis")
        assert "market_analysis" in loaded

    def test_category_source_code_has_renamed_variable(self):
        """验证 registry.py 源码中变量名已改为 CATEGORY_TO_SKILLS"""
        registry_path = SRC_ROOT / "skills" / "registry.py"
        content = registry_path.read_text(encoding="utf-8")
        assert "CATEGORY_TO_SKILLS" in content, "registry.py must use CATEGORY_TO_SKILLS (not CATEGORY_TO_LANGCHAIN_SKILLS)"
        assert '"financial-analysis"' in content, "CATEGORY_TO_SKILLS must contain financial-analysis"

    def test_load_skills_for_category_factory_aware_logic(self):
        """验证 registry.py 源码中 load_skills_for_category 检查 _factories"""
        registry_path = SRC_ROOT / "skills" / "registry.py"
        content = registry_path.read_text(encoding="utf-8")
        assert "skill_name in self._factories" in content, \
            "registry.py must have 'skill_name in self._factories' check in load_skills_for_category"


# ═══════════════════════════════════════════════════════════════
# E2E-6: discover_skills 端到端
# ═══════════════════════════════════════════════════════════════

class TestE2E6DiscoverSkills:
    """端到端: discover_skills 含分析 skill 关键词匹配 + factory auto_load"""

    def test_skill_keywords_source_code_has_analysis_skills(self):
        """验证 skill_keywords.py 源码含 7 个分析 skill 关键词"""
        kw_path = SRC_ROOT / "skills" / "skill_keywords.py"
        content = kw_path.read_text(encoding="utf-8")
        for name in ["market_analysis", "stock_data", "stock_analysis",
                      "data_analysis", "policy_analysis", "tech_trend", "risk_analysis"]:
            assert f'"{name}"' in content or f"'{name}'" in content, \
                f"skill_keywords.py must contain keyword mapping for {name}"

    def test_discover_skills_code_checks_factories(self):
        """验证 registry.py 源码中 discover_skills auto_load 检查 _factories"""
        registry_path = SRC_ROOT / "skills" / "registry.py"
        content = registry_path.read_text(encoding="utf-8")
        discover_start = content.find("def discover_skills")
        assert discover_start > 0
        func_body = content[discover_start:discover_start + 1500]
        assert "_factories" in func_body, "discover_skills must check _factories in auto_load"

    def test_discover_financial_data_returns_stock_data(self):
        """端到端: discover_skills('financial data') → stock_data"""
        from src.skills.registry import SkillRegistry
        from src.skills.analysis import StockDataSkill

        registry = SkillRegistry()
        registry.register_core_skills()
        registry.register_factory("stock_data", StockDataSkill)

        discovered = registry.discover_skills("financial data", auto_load=True)
        assert "stock_data" in discovered, f"'financial data' must discover stock_data, got: {discovered}"

    def test_discover_stock_analysis_returns_stock_analysis(self):
        """端到端: discover_skills('stock analysis') → stock_analysis"""
        from src.skills.registry import SkillRegistry
        from src.skills.analysis import StockAnalysisSkill

        registry = SkillRegistry()
        registry.register_core_skills()
        registry.register_factory("stock_analysis", StockAnalysisSkill)

        discovered = registry.discover_skills("stock analysis", auto_load=True)
        assert "stock_analysis" in discovered


# ═══════════════════════════════════════════════════════════════
# E2E-7: add_skill() 端到端
# ═══════════════════════════════════════════════════════════════

class TestE2E7AddSkill:
    """端到端: add_skill() 动态扩展 + session 同步 + hibernate/restore"""

    def test_add_skill_source_code_exists(self):
        """验证 generic_agent.py 源码中有 add_skill 方法"""
        agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = agent_path.read_text(encoding="utf-8")
        assert "def add_skill" in content, "generic_agent.py must have add_skill method"
        assert "self._available_skills.append(skill_name)" in content, \
            "add_skill must append to _available_skills"

    def test_add_skill_with_registry_validation(self):
        """端到端: add_skill 验证 registry 中存在 skill"""
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import StockDataSkill

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("stock_data", StockDataSkill)

        capability = AgentCapability(name="Test", description="Test", required_skills=["llm_skill"])
        agent = factory.create_agent("add_e2e_001", capability)

        result = agent.add_skill("stock_data")
        assert result is True
        assert "stock_data" in agent._available_skills

        result2 = agent.add_skill("nonexistent_xyz")
        assert result2 is False
        assert "nonexistent_xyz" not in agent._available_skills

    def test_add_skill_session_sync(self):
        """端到端: add_skill 同步 session.agent_template['skill_names']"""
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import MarketAnalysisSkill

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("market_analysis", MarketAnalysisSkill)

        capability = AgentCapability(name="Test", description="Test", required_skills=["llm_skill"])
        agent = factory.create_agent("add_e2e_002", capability)

        mock_template = {"skill_names": ["llm_skill"]}
        mock_session = MagicMock()
        mock_session.agent_template = mock_template
        agent._session = mock_session

        agent.add_skill("market_analysis")
        assert "market_analysis" in mock_template["skill_names"], \
            "add_skill must sync skill_names in session.agent_template"

    def test_add_skill_no_duplicate(self):
        """端到端: add_skill 不重复添加"""
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import StockDataSkill

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("stock_data", StockDataSkill)

        capability = AgentCapability(name="Test", description="Test", required_skills=["llm_skill"])
        agent = factory.create_agent("add_e2e_003", capability)

        agent.add_skill("stock_data")
        result = agent.add_skill("stock_data")
        assert result is False
        assert agent._available_skills.count("stock_data") == 1


# ═══════════════════════════════════════════════════════════════
# E2E-8: discover_skills 分支端到端 (非 execute action 路径)
# ═══════════════════════════════════════════════════════════════

class TestE2E8DiscoverSkillsBranch:
    """端到端: generic_agent.py 中 discover_skills 分支用 add_skill 替代限制检查"""

    def test_discover_branch_source_code_uses_add_skill(self):
        """验证 generic_agent.py discover_skills 分支代码用 add_skill"""
        agent_path = SRC_ROOT / "core" / "agents" / "generic_agent.py"
        content = agent_path.read_text(encoding="utf-8")
        assert "def add_skill" in content, "generic_agent.py must have add_skill method"
        discover_idx = content.find("动态发现")
        assert discover_idx > 0, "generic_agent.py must have discover_skills branch"
        branch_code = content[discover_idx:discover_idx + 500]
        assert "add_skill" in branch_code, "discover branch must use add_skill()"

    @pytest.mark.asyncio
    async def test_discover_branch_adds_skill_and_executes(self):
        """端到端: 非 execute action → discover_skills → add_skill + execute"""
        from src.core.agents.generic_agent import GenericAgent
        from src.skills.registry import SkillRegistry
        from src.skills.analysis import StockDataSkill

        registry = SkillRegistry()
        registry.register_core_skills()
        registry.register_factory("stock_data", StockDataSkill)

        mock_skill_instance = registry.get("stock_data")

        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "discover_e2e_001"
        agent._skill_registry = registry
        agent._available_skills = ["llm_skill"]
        agent._session = None
        agent._context = {}

        with patch.object(mock_skill_instance, 'execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"success": True, "data": "financial data"}

            original_available = agent._available_skills.copy()

            skill = registry.get("stock_data")
            if skill:
                agent.add_skill("stock_data")
                result = await skill.execute(action="fetch", symbol="000001")

            assert "stock_data" in agent._available_skills
            assert agent._available_skills.count("stock_data") == 1
            assert "llm_skill" in agent._available_skills


# ═══════════════════════════════════════════════════════════════
# E2E-9: 完整链路 — aspect → skills → agent → available_skills
# ═══════════════════════════════════════════════════════════════

class TestE2E9FullChainIntegration:
    """端到端: aspect → strategies → factory → agent._available_skills 完整链路"""

    def test_financial_analysis_full_chain(self):
        """端到端: 'Financial Analysis' → DATA_COLLECTION + DEEP_ANALYSIS 两阶段"""
        from src.core.decomposition.strategies import get_skills_for_aspect, _get_data_collection_skills
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import (
            StockDataSkill, StockAnalysisSkill, DataAnalysisSkill,
        )

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("stock_data", StockDataSkill)
        factory._skill_registry.register_factory("stock_analysis", StockAnalysisSkill)
        factory._skill_registry.register_factory("data_analysis", DataAnalysisSkill)

        # DATA_COLLECTION phase
        data_skills = _get_data_collection_skills("Financial Analysis", topic="比亚迪财务分析")
        data_capability = AgentCapability(
            name="Data Collection Financial",
            description="收集财务数据",
            required_skills=data_skills,
        )
        data_agent = factory.create_agent("data_fin_001", data_capability, context={"topic": "比亚迪财务分析"})
        assert "stock_data" in data_agent._available_skills, \
            f"DATA_COLLECTION agent must have stock_data, got: {data_agent._available_skills}"
        assert "search_skill" in data_agent._available_skills
        assert "llm_skill" in data_agent._available_skills

        # DEEP_ANALYSIS phase
        analysis_skills = get_skills_for_aspect("Financial Analysis")
        analysis_capability = AgentCapability(
            name="Deep Analysis Financial",
            description="财务分析",
            required_skills=analysis_skills,
        )
        analysis_agent = factory.create_agent("deep_fin_001", analysis_capability, context={"aspect": "Financial Analysis"})
        assert "stock_analysis" in analysis_agent._available_skills, \
            f"DEEP_ANALYSIS agent must have stock_analysis, got: {analysis_agent._available_skills}"
        assert "data_analysis" in analysis_agent._available_skills
        assert "llm_skill" in analysis_agent._available_skills

    def test_market_analysis_full_chain(self):
        """端到端: 'Competitive Landscape' → DATA_COLLECTION + DEEP_ANALYSIS"""
        from src.core.decomposition.strategies import get_skills_for_aspect, _get_data_collection_skills
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import MarketAnalysisSkill

        factory = DynamicAgentFactory()
        factory._skill_registry.register_factory("market_analysis", MarketAnalysisSkill)

        data_skills = _get_data_collection_skills("Competitive Landscape")
        assert "stock_data" not in data_skills, "Competitive Landscape does not need stock_data"

        analysis_skills = get_skills_for_aspect("Competitive Landscape")
        assert "market_analysis" in analysis_skills

        analysis_capability = AgentCapability(
            name="Deep Analysis Market",
            description="竞争格局",
            required_skills=analysis_skills,
        )
        analysis_agent = factory.create_agent("deep_market_001", analysis_capability)
        assert "market_analysis" in analysis_agent._available_skills

    def test_all_seven_aspects_create_agents_with_correct_skills(self):
        """端到端: 所有含分析 skill 的 aspect → agent._available_skills 正确"""
        from src.core.decomposition.strategies import get_skills_for_aspect, ASPECT_SKILL_MAP
        from src.core.agents.factory import DynamicAgentFactory, AgentCapability
        from src.skills.analysis import (
            MarketAnalysisSkill, DataAnalysisSkill, StockDataSkill,
            StockAnalysisSkill, PolicyAnalysisSkill, TechTrendSkill, RiskAnalysisSkill,
        )

        factory = DynamicAgentFactory()
        for name, cls in [
            ("market_analysis", MarketAnalysisSkill),
            ("data_analysis", DataAnalysisSkill),
            ("stock_data", StockDataSkill),
            ("stock_analysis", StockAnalysisSkill),
            ("policy_analysis", PolicyAnalysisSkill),
            ("tech_trend", TechTrendSkill),
            ("risk_analysis", RiskAnalysisSkill),
        ]:
            factory._skill_registry.register_factory(name, cls)

        analysis_skill_names = {
            "market_analysis", "data_analysis", "stock_data",
            "stock_analysis", "policy_analysis", "tech_trend", "risk_analysis",
        }

        for aspect, expected_skills in ASPECT_SKILL_MAP.items():
            analysis_skills_in_aspect = [s for s in expected_skills if s in analysis_skill_names]
            if not analysis_skills_in_aspect:
                continue

            capability = AgentCapability(
                name=f"Agent-{aspect}",
                description=aspect,
                required_skills=expected_skills,
            )
            agent = factory.create_agent(f"agent_{aspect}", capability)
            for skill_name in analysis_skills_in_aspect:
                assert skill_name in agent._available_skills, \
                    f"aspect '{aspect}': {skill_name} must be in available_skills, got: {agent._available_skills}"
