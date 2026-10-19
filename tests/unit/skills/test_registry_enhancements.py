"""
SkillRegistry 增强测试 - manifest 注册、capability 查询、init_from_discovery

TDD RED 阶段
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch


class TestSkillRegistryManifest:
    """测试 SkillRegistry manifest 相关方法"""

    @pytest.fixture
    def registry(self):
        from src.skills.registry import SkillRegistry
        return SkillRegistry()

    def test_register_manifest(self, registry):
        from src.skills.discovery import SkillManifest

        manifest = SkillManifest(
            name="test_skill",
            description="Test",
            version="1.0",
            categories=["test"],
            priority="web_search",
            keywords=["test"],
            aliases=[],
            capabilities=["query"],
            data_types={},
            data_source_keywords=[],
            action_rules=[],
            action_param_map={},
            supports_topic_fallback=False,
            topic_fallback_pattern=None,
            is_intrinsic=False,
            aspect_coverage=[],
            skill_type="standard",
            skill_dir=Path("/fake"),
            has_code=False,
            instructions="",
        )
        registry.register_manifest(manifest)

        assert registry.get_manifest("test_skill") is manifest

    def test_get_manifest_nonexistent(self, registry):
        assert registry.get_manifest("nonexistent") is None

    def test_register_multiple_manifests(self, registry):
        from src.skills.discovery import SkillManifest

        m1 = SkillManifest(
            name="a", description="A", version="1.0", categories=[],
            priority="web_search", keywords=[], aliases=[], capabilities=[],
            data_types={}, data_source_keywords=[], action_rules=[],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("/fake"), has_code=False, instructions="",
        )
        m2 = SkillManifest(
            name="b", description="B", version="1.0", categories=[],
            priority="structured_db", keywords=[], aliases=[], capabilities=[],
            data_types={}, data_source_keywords=[], action_rules=[],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("/fake"), has_code=False, instructions="",
        )
        registry.register_manifest(m1)
        registry.register_manifest(m2)

        assert registry.get_manifest("a").name == "a"
        assert registry.get_manifest("b").name == "b"


class TestSkillRegistryGetByCapability:
    """测试 SkillRegistry.get_by_capability"""

    @pytest.fixture
    def registry(self):
        from src.skills.registry import SkillRegistry
        from src.skills.discovery import SkillManifest
        from unittest.mock import Mock

        reg = SkillRegistry()

        m1 = SkillManifest(
            name="xueqiu", description="Xueqiu", version="1.0",
            categories=["financial-analysis"], priority="structured_db",
            keywords=["雪球"], aliases=[], capabilities=["quote", "kline", "search"],
            data_types={}, data_source_keywords=[], action_rules=[],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("/fake"), has_code=True, instructions="",
        )
        m2 = SkillManifest(
            name="search_skill", description="Search", version="1.0",
            categories=["data-collection"], priority="web_search",
            keywords=["搜索"], aliases=[], capabilities=["search", "web_search"],
            data_types={}, data_source_keywords=[], action_rules=[],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("/fake"), has_code=True, instructions="",
        )
        reg.register_manifest(m1)
        reg.register_manifest(m2)

        mock_xueqiu = Mock()
        mock_xueqiu.name = "xueqiu"
        reg.register(mock_xueqiu, name="xueqiu")

        mock_search = Mock()
        mock_search.name = "search_skill"
        reg.register(mock_search, name="search_skill")

        return reg

    def test_get_by_capability_found(self, registry):
        skill = registry.get_by_capability("quote")
        assert skill is not None
        assert skill.name == "xueqiu"

    def test_get_by_capability_shared_capability(self, registry):
        skill = registry.get_by_capability("search")
        assert skill is not None
        assert skill.name in ("xueqiu", "search_skill")

    def test_get_by_capability_not_found(self, registry):
        skill = registry.get_by_capability("nonexistent_capability")
        assert skill is None


class TestSkillRegistryGetByPriority:
    """测试 SkillRegistry.get_by_priority"""

    @pytest.fixture
    def registry(self):
        from src.skills.registry import SkillRegistry
        from src.skills.discovery import SkillManifest
        from unittest.mock import Mock

        reg = SkillRegistry()

        m1 = SkillManifest(
            name="xueqiu", description="Xueqiu", version="1.0",
            categories=[], priority="structured_db",
            keywords=[], aliases=[], capabilities=[],
            data_types={}, data_source_keywords=[], action_rules=[],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("/fake"), has_code=True, instructions="",
        )
        m2 = SkillManifest(
            name="search_skill", description="Search", version="1.0",
            categories=[], priority="web_search",
            keywords=[], aliases=[], capabilities=[],
            data_types={}, data_source_keywords=[], action_rules=[],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("/fake"), has_code=True, instructions="",
        )
        m3 = SkillManifest(
            name="stock_data", description="Stock Data", version="1.0",
            categories=[], priority="structured_db",
            keywords=[], aliases=[], capabilities=[],
            data_types={}, data_source_keywords=[], action_rules=[],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("/fake"), has_code=True, instructions="",
        )
        reg.register_manifest(m1)
        reg.register_manifest(m2)
        reg.register_manifest(m3)

        for name in ("xueqiu", "search_skill", "stock_data"):
            mock_skill = Mock()
            mock_skill.name = name
            reg.register(mock_skill, name=name)

        return reg

    def test_get_by_priority_structured_db(self, registry):
        skills = registry.get_by_priority("structured_db")
        names = {s.name for s in skills}
        assert names == {"xueqiu", "stock_data"}

    def test_get_by_priority_web_search(self, registry):
        skills = registry.get_by_priority("web_search")
        names = {s.name for s in skills}
        assert names == {"search_skill"}

    def test_get_by_priority_empty(self, registry):
        skills = registry.get_by_priority("llm")
        assert len(skills) == 0


class TestSkillRegistryGetSkillsByCategory:
    """测试 SkillRegistry.get_skills_by_category"""

    @pytest.fixture
    def registry(self):
        from src.skills.registry import SkillRegistry
        from src.skills.discovery import SkillManifest

        reg = SkillRegistry()

        m1 = SkillManifest(
            name="xueqiu", description="Xueqiu", version="1.0",
            categories=["financial-analysis", "data-collection"],
            priority="structured_db", keywords=[], aliases=[], capabilities=[],
            data_types={}, data_source_keywords=[], action_rules=[],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("/fake"), has_code=False, instructions="",
        )
        m2 = SkillManifest(
            name="stock_data", description="Stock Data", version="1.0",
            categories=["financial-analysis", "research"],
            priority="structured_db", keywords=[], aliases=[], capabilities=[],
            data_types={}, data_source_keywords=[], action_rules=[],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("/fake"), has_code=False, instructions="",
        )
        reg.register_manifest(m1)
        reg.register_manifest(m2)

        return reg

    def test_get_skills_by_category_financial(self, registry):
        skills = registry.get_skills_by_category("financial-analysis")
        assert "xueqiu" in skills
        assert "stock_data" in skills

    def test_get_skills_by_category_data_collection(self, registry):
        skills = registry.get_skills_by_category("data-collection")
        assert "xueqiu" in skills
        assert "stock_data" not in skills

    def test_get_skills_by_category_empty(self, registry):
        skills = registry.get_skills_by_category("nonexistent")
        assert len(skills) == 0


class TestSkillRegistryAllManifests:
    """测试 SkillRegistry.all_manifests"""

    def test_all_manifests(self):
        from src.skills.registry import SkillRegistry
        from src.skills.discovery import SkillManifest

        reg = SkillRegistry()

        m1 = SkillManifest(
            name="a", description="A", version="1.0", categories=[],
            priority="web_search", keywords=[], aliases=[], capabilities=[],
            data_types={}, data_source_keywords=[], action_rules=[],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("/fake"), has_code=False, instructions="",
        )
        reg.register_manifest(m1)

        result = reg.all_manifests()
        assert "a" in result
        assert result["a"] is m1

    def test_all_manifests_empty(self):
        from src.skills.registry import SkillRegistry

        reg = SkillRegistry()
        assert reg.all_manifests() == {}


class TestSkillRegistryInitFromDiscovery:
    """测试 SkillRegistry.init_from_discovery"""

    @pytest.fixture
    def skills_dir(self, tmp_path):
        skill_a = tmp_path / "instr_skill"
        skill_a.mkdir()
        (skill_a / "SKILL.md").write_text(
            "---\n"
            "name: instr_skill\n"
            "description: Instruction Skill\n"
            "version: '1.0'\n"
            "categories:\n"
            "  - test\n"
            "priority: llm\n"
            "keywords:\n"
            "  - instr\n"
            "aliases: []\n"
            "capabilities: []\n"
            "data_types: {}\n"
            "data_source_keywords: []\n"
            "action_rules: []\n"
            "action_param_map: {}\n"
            "supports_topic_fallback: false\n"
            "is_intrinsic: true\n"
            "aspect_coverage: []\n"
            "skill_type: standard\n"
            "---\n"
            "# Instruction Skill\n"
            "This is an instruction-only skill.\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_init_from_discovery_registers_instruction_skill(self, skills_dir):
        from src.skills.registry import SkillRegistry

        registry = SkillRegistry()
        registry.init_from_discovery(skills_dir)

        skill = registry.get("instr_skill")
        assert skill is not None
        assert skill.name == "instr_skill"

    def test_init_from_discovery_registers_manifest(self, skills_dir):
        from src.skills.registry import SkillRegistry

        registry = SkillRegistry()
        registry.init_from_discovery(skills_dir)

        manifest = registry.get_manifest("instr_skill")
        assert manifest is not None
        assert manifest.is_intrinsic is True

    def test_init_from_discovery_empty_dir(self, tmp_path):
        from src.skills.registry import SkillRegistry

        registry = SkillRegistry()
        registry.init_from_discovery(tmp_path)

        assert len(registry.all_manifests()) == 0

    def test_init_from_discovery_nonexistent_dir(self, tmp_path):
        from src.skills.registry import SkillRegistry

        registry = SkillRegistry()
        nonexistent = tmp_path / "no_such_dir"
        registry.init_from_discovery(nonexistent)

        assert len(registry.all_manifests()) == 0
