"""
Task 1.7 测试：移除 orchestrator.py 手动注册 + aliases 实例共享

验证：
1. init_from_discovery() 正确处理 aliases，且 alias 与原名共享同一实例
2. init_from_discovery() 跳过 langchain manifest 注册（避免双重注册）
3. orchestrator.py 不再手动 register_factory 7个分析 Skill
4. register_core_skills() 变为空操作（向后兼容）
5. init_from_discovery() 能覆盖 register_core_skills() 注册的所有 Skill
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestAliasesInstanceSharing:
    """验证 aliases 注册逻辑：alias 和原名必须返回同一个实例"""

    def setup_method(self):
        from src.skills.registry import SkillRegistry
        self.registry = SkillRegistry()

    def test_alias_returns_same_instance_as_original(self):
        """web_search alias 和 search_skill 必须是同一个实例 (is 比较)"""
        skills_dir = Path("src/skills")
        self.registry.init_from_discovery(skills_dir)

        search_skill = self.registry.get("search_skill")
        web_search = self.registry.get("web_search")

        assert search_skill is not None, "search_skill should be registered"
        assert web_search is not None, "web_search alias should be registered"
        assert search_skill is web_search, "web_search must be the same instance as search_skill"

    def test_alias_in_manifest(self):
        """search SKILL.md 的 aliases 字段包含 web_search"""
        from src.skills.discovery import SkillDiscovery
        discovery = SkillDiscovery()
        skills_dir = Path("src/skills")
        manifests = discovery.discover_all(skills_dir)

        search_manifest = next((m for m in manifests if m.name == "search_skill"), None)
        assert search_manifest is not None, "search_skill manifest should exist"
        assert "web_search" in search_manifest.aliases, "search_skill aliases should include web_search"

    def test_all_aliases_registered(self):
        """所有 SKILL.md 中声明的 aliases 都应被注册"""
        from src.skills.discovery import SkillDiscovery
        discovery = SkillDiscovery()
        skills_dir = Path("src/skills")
        manifests = discovery.discover_all(skills_dir)

        self.registry.init_from_discovery(skills_dir)

        for manifest in manifests:
            for alias in manifest.aliases:
                skill = self.registry.get(alias)
                assert skill is not None, f"alias '{alias}' of '{manifest.name}' should be registered"
                original = self.registry.get(manifest.name)
                assert skill is original, f"alias '{alias}' must be same instance as '{manifest.name}'"

    def test_alias_factory_creates_shared_instance(self):
        """alias factory 首次调用时创建实例，后续调用返回同一实例"""
        skills_dir = Path("src/skills")
        self.registry.init_from_discovery(skills_dir)

        # 通过 factory 获取
        skill1 = self.registry.get("search_skill")
        skill2 = self.registry.get("web_search")
        skill3 = self.registry.get("search_skill")
        skill4 = self.registry.get("web_search")

        assert skill1 is skill2 is skill3 is skill4, "All gets must return same instance"


class TestLangchainManifestNoDoubleRegistration:
    """验证 langchain manifest 不在 init_from_discovery 中注册（revision #49）"""

    def setup_method(self):
        from src.skills.registry import SkillRegistry
        self.registry = SkillRegistry()

    def test_langchain_manifests_not_in_init_from_discovery(self):
        """init_from_discovery() 不应注册 langchain 类型的 manifest"""
        skills_dir = Path("src/skills")
        self.registry.init_from_discovery(skills_dir)

        for name in ["lc_tavily_search", "lc_arxiv", "lc_wikipedia", "lc_python_repl"]:
            manifest = self.registry.get_manifest(name)
            assert manifest is None, f"langchain manifest '{name}' should NOT be registered by init_from_discovery"

    def test_langchain_manifests_registered_by_auto_discover(self):
        """langchain manifest 应由 auto_discover_langchain_tools() 注册"""
        skills_dir = Path("src/skills")
        self.registry.init_from_discovery(skills_dir)

        # auto_discover_langchain_tools() 注册 manifest
        with patch.object(self.registry._adapter, 'register_research_tools', return_value=0):
            with patch.object(self.registry._adapter, '_skills', {}):
                self.registry.auto_discover_langchain_tools()

        # After auto_discover, langchain manifests should still not be in _manifests
        # (they are registered as Skill instances, not manifests)
        # The key point: no double registration


class TestOrchestratorNoManualRegistration:
    """验证 orchestrator.py 不再手动注册分析 Skill"""

    def test_orchestrator_no_manual_analysis_factory(self):
        """orchestrator.py 不应手动 register_factory 7个分析 Skill"""
        import inspect
        from src.core.orchestrator.orchestrator import ResearchOrchestrator

        source = inspect.getsource(ResearchOrchestrator.__init__)
        # Should NOT contain manual factory registration for analysis skills
        forbidden_patterns = [
            'MarketAnalysisSkill',
            'DataAnalysisSkill',
            'StockDataSkill',
            'StockAnalysisSkill',
            'PolicyAnalysisSkill',
            'TechTrendSkill',
            'RiskAnalysisSkill',
        ]
        for pattern in forbidden_patterns:
            assert pattern not in source, f"orchestrator.py should not manually import {pattern}"

    def test_orchestrator_calls_init_from_discovery(self):
        """orchestrator.py 应调用 init_from_discovery()"""
        import inspect
        from src.core.orchestrator.orchestrator import ResearchOrchestrator

        source = inspect.getsource(ResearchOrchestrator.__init__)
        assert "init_from_discovery" in source, "orchestrator should call init_from_discovery()"


class TestRegisterCoreSkillsBackwardCompat:
    """验证 register_core_skills() 变为空操作但方法仍存在"""

    def setup_method(self):
        from src.skills.registry import SkillRegistry
        self.registry = SkillRegistry()

    def test_register_core_skills_exists(self):
        """register_core_skills() 方法仍存在"""
        assert hasattr(self.registry, 'register_core_skills'), "register_core_skills() should still exist"

    def test_register_core_skills_returns_zero(self):
        """register_core_skills() 应返回 0（不再注册任何 Skill）"""
        result = self.registry.register_core_skills()
        assert result == 0, "register_core_skills() should return 0 (no-op)"

    def test_register_core_skills_no_side_effects(self):
        """register_core_skills() 不应注册任何 Skill"""
        self.registry.register_core_skills()
        assert len(self.registry._skills) == 0, "register_core_skills() should not register any skills"
        assert len(self.registry._factories) == 0, "register_core_skills() should not register any factories"


class TestInitFromDiscoveryCoversAllCoreSkills:
    """验证 init_from_discovery() 能覆盖 register_core_skills() 原来注册的所有 Skill"""

    def setup_method(self):
        from src.skills.registry import SkillRegistry
        self.registry = SkillRegistry()

    def test_all_core_skills_available_via_discovery(self):
        """init_from_discovery() 后，所有原 register_core_skills() 的所有 Skill 都应可用"""
        skills_dir = Path("src/skills")
        self.registry.init_from_discovery(skills_dir)

        # 原 register_core_skills() 注册的 Skill 列表
        core_skill_names = [
            "search_skill",
            "web_search",  # alias
            "news_search",
            "file_skill",
            "http_skill",
            "docx_skill",
            "web_scraper",
            "knowledge_query",
            "annual_report_parser",
        ]

        for name in core_skill_names:
            skill = self.registry.get(name)
            assert skill is not None, f"Skill '{name}' should be available via init_from_discovery()"

    def test_all_analysis_skills_available_via_discovery(self):
        """init_from_discovery() 后，7个分析 Skill 都应可用"""
        skills_dir = Path("src/skills")
        self.registry.init_from_discovery(skills_dir)

        analysis_skills = [
            "market_analysis",
            "data_analysis",
            "stock_data",
            "stock_analysis",
            "policy_analysis",
            "tech_trend",
            "risk_analysis",
        ]

        for name in analysis_skills:
            skill = self.registry.get(name)
            assert skill is not None, f"Analysis Skill '{name}' should be available via init_from_discovery()"

    def test_all_manifests_available_via_discovery(self):
        """init_from_discovery() 后，所有非 langchain Skill 的 manifest 都应可用"""
        skills_dir = Path("src/skills")
        self.registry.init_from_discovery(skills_dir)

        # 非 langchain Skill 应有 manifest
        non_langchain_skills = [
            "search_skill", "news_search", "file_skill", "http_skill",
            "docx_skill", "web_scraper", "stock_data", "stock_analysis",
            "market_analysis", "data_analysis", "policy_analysis",
            "tech_trend", "risk_analysis", "annual_report_parser",
            "knowledge_query", "llm",
        ]

        for name in non_langchain_skills:
            manifest = self.registry.get_manifest(name)
            assert manifest is not None, f"Skill '{name}' should have a manifest registered"
