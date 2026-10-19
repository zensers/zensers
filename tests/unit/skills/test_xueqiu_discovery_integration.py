"""
Xueqiu 自描述架构集成测试

验证 xueqiu 的 SKILL.md 能被 SkillDiscovery 发现，
通过 SkillRegistry.init_from_discovery 注册，
并生成正确的注册数据。
"""
import pytest
from pathlib import Path


class TestXueqiuSkillDiscovery:
    """测试 xueqiu SKILL.md 能被发现并解析"""

    @pytest.fixture
    def skills_dir(self):
        return Path("src/skills")

    def test_discover_xueqiu_skill(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        xueqiu = next((m for m in manifests if m.name == "xueqiu"), None)
        assert xueqiu is not None, "xueqiu SKILL.md not discovered"

    def test_xueqiu_manifest_fields(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        xueqiu = next(m for m in manifests if m.name == "xueqiu")
        assert xueqiu.description == "雪球实时行情/热门股票/热帖/K线 (A股/港股/美股)"
        assert "financial-analysis" in xueqiu.categories
        assert "research" in xueqiu.categories
        assert "data-collection" in xueqiu.categories
        assert xueqiu.priority == "structured_db"
        assert "雪球" in xueqiu.keywords
        assert "xueqiu_stock" in xueqiu.aliases
        assert "stock_quote" in xueqiu.aliases
        assert "quote" in xueqiu.capabilities
        assert "search_and_quote" in xueqiu.capabilities
        assert xueqiu.supports_topic_fallback is True
        assert xueqiu.topic_fallback_pattern is not None
        assert xueqiu.has_code is True
        assert xueqiu.skill_type == "standard"

    def test_xueqiu_action_rules(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        xueqiu = next(m for m in manifests if m.name == "xueqiu")
        assert len(xueqiu.action_rules) == 3

        rule1 = xueqiu.action_rules[0]
        assert "quote" in rule1.actions
        assert "hot_stocks" in rule1.actions
        assert rule1.aspect_keywords is not None

        rule2 = xueqiu.action_rules[1]
        assert rule2.actions == ["quote", "kline"]
        assert rule2.aspect_keywords is None

        rule3 = xueqiu.action_rules[2]
        assert rule3.actions == ["search_and_quote"]

    def test_xueqiu_data_source_keywords(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        xueqiu = next(m for m in manifests if m.name == "xueqiu")
        assert "财务" in xueqiu.data_source_keywords
        assert "行情" in xueqiu.data_source_keywords
        assert "港股" in xueqiu.data_source_keywords

    def test_xueqiu_aspect_coverage(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        xueqiu = next(m for m in manifests if m.name == "xueqiu")
        assert "Financial Analysis" in xueqiu.aspect_coverage
        assert "竞争格局" in xueqiu.aspect_coverage

    def test_xueqiu_instructions_body(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        xueqiu = next(m for m in manifests if m.name == "xueqiu")
        assert "Xueqiu Skill" in xueqiu.instructions
        assert "search_and_quote" in xueqiu.instructions


class TestXueqiuRegistryIntegration:
    """测试 xueqiu 通过 discovery 注册到 registry"""

    @pytest.fixture
    def registry(self):
        from src.skills.registry import SkillRegistry
        return SkillRegistry()

    def test_xueqiu_registered_via_discovery(self, registry):
        registry.init_from_discovery(Path("src/skills"))

        manifest = registry.get_manifest("xueqiu")
        assert manifest is not None

    def test_xueqiu_skill_instance_via_discovery(self, registry):
        registry.init_from_discovery(Path("src/skills"))

        skill = registry.get("xueqiu")
        assert skill is not None
        assert skill.name == "xueqiu"

    def test_xueqiu_get_by_capability(self, registry):
        registry.init_from_discovery(Path("src/skills"))

        skill = registry.get_by_capability("quote")
        assert skill is not None
        assert skill.name == "xueqiu"

    def test_xueqiu_get_by_priority(self, registry):
        registry.init_from_discovery(Path("src/skills"))

        skills = registry.get_by_priority("structured_db")
        names = {s.name for s in skills}
        assert "xueqiu" in names

    def test_xueqiu_build_registries(self):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))

        xueqiu = next((m for m in manifests if m.name == "xueqiu"), None)
        if xueqiu is None:
            pytest.skip("xueqiu SKILL.md not found")

        registries = discovery.build_registries(manifests)

        assert "xueqiu" in registries.priority_map
        assert registries.priority_map["xueqiu"] == "structured_db"
        assert "xueqiu_stock" in registries.alias_map
        assert registries.alias_map["xueqiu_stock"] == "xueqiu"
        assert "xueqiu" in registries.structured_data_capabilities
        assert "行情" in registries.data_source_skill_map
        assert "xueqiu" in registries.data_source_skill_map["行情"]

    def test_xueqiu_infer_actions_from_manifest(self):
        from src.skills.discovery import SkillDiscovery
        from src.skills.registry import SkillRegistry

        registry = SkillRegistry()
        registry.init_from_discovery(Path("src/skills"))

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(Path("src/skills"))

        xueqiu = next((m for m in manifests if m.name == "xueqiu"), None)
        if xueqiu is None:
            pytest.skip("xueqiu SKILL.md not found")

        skill = registry.get("xueqiu")
        skill._manifest = xueqiu

        actions_a_stock = skill.infer_actions("财务分析", "SH600519")
        assert "quote" in actions_a_stock
        assert "kline" in actions_a_stock

        actions_non_a = skill.infer_actions("", "腾讯控股")
        assert actions_non_a == ["search_and_quote"]

        actions_competitive = skill.infer_actions("竞争格局分析", "SH600519")
        assert "hot_stocks" in actions_competitive
