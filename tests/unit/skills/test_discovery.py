"""
Skill 自描述架构 - SkillManifest + SkillDiscovery 测试

TDD RED 阶段：先写测试，再实现。
"""
import pytest
from pathlib import Path
from dataclasses import FrozenInstanceError


class TestActionRule:
    """测试 ActionRule 数据类"""

    def test_action_rule_creation(self):
        from src.skills.discovery import ActionRule

        rule = ActionRule(
            pattern=r"^(SH|SZ|BJ)?\d{6}$",
            actions=["quote", "kline"],
            aspect_keywords=["竞争", "热门"],
        )
        assert rule.pattern == r"^(SH|SZ|BJ)?\d{6}$"
        assert rule.actions == ["quote", "kline"]
        assert rule.aspect_keywords == ["竞争", "热门"]

    def test_action_rule_aspect_keywords_optional(self):
        from src.skills.discovery import ActionRule

        rule = ActionRule(
            pattern=r".*",
            actions=["search_and_quote"],
        )
        assert rule.aspect_keywords is None

    def test_action_rule_no_aspect_keywords_matches_any(self):
        from src.skills.discovery import ActionRule

        rule = ActionRule(pattern=r".*", actions=["search_and_quote"])
        assert rule.aspect_keywords is None


class TestSkillManifest:
    """测试 SkillManifest 数据类"""

    def test_manifest_minimal_fields(self):
        from src.skills.discovery import SkillManifest

        manifest = SkillManifest(
            name="test_skill",
            description="A test skill",
            version="1.0",
            categories=["test"],
            priority="web_search",
            keywords=["test"],
            aliases=[],
            capabilities=[],
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
            instructions="Test instructions",
        )
        assert manifest.name == "test_skill"
        assert manifest.skill_type == "standard"
        assert manifest.has_code is False

    def test_manifest_xueqiu_fields(self):
        from src.skills.discovery import SkillManifest, ActionRule

        manifest = SkillManifest(
            name="xueqiu",
            description="雪球实时行情/热门股票/热帖/K线 (A股/港股/美股)",
            version="1.0",
            categories=["financial-analysis", "research", "data-collection"],
            priority="structured_db",
            keywords=["雪球", "行情", "港股"],
            aliases=["xueqiu_stock", "stock_quote"],
            capabilities=["quote", "kline", "hot_stocks", "search_and_quote"],
            data_types={"zh": ["换手率", "实时行情"]},
            data_source_keywords=["财务", "估值", "行情"],
            action_rules=[
                ActionRule(
                    pattern=r"^(SH|SZ|BJ)?\d{6}$",
                    aspect_keywords=["竞争", "热门"],
                    actions=["quote", "kline", "hot_stocks"],
                ),
                ActionRule(
                    pattern=r"^(SH|SZ|BJ)?\d{6}$",
                    actions=["quote", "kline"],
                ),
                ActionRule(
                    pattern=r".*",
                    actions=["search_and_quote"],
                ),
            ],
            action_param_map={
                "quote": {"symbol": "symbol"},
                "kline": {"symbol": "symbol"},
                "search_and_quote": {"query": "symbol"},
            },
            supports_topic_fallback=True,
            topic_fallback_pattern=r"[\u4e00-\u9fff]+",
            is_intrinsic=False,
            aspect_coverage=["Financial Analysis", "估值分析"],
            skill_type="standard",
            skill_dir=Path("/fake/xueqiu"),
            has_code=True,
            instructions="# Xueqiu Skill\n...",
        )
        assert manifest.name == "xueqiu"
        assert manifest.priority == "structured_db"
        assert manifest.supports_topic_fallback is True
        assert len(manifest.action_rules) == 3
        assert manifest.data_source_keywords == ["财务", "估值", "行情"]


class TestSkillDiscovery:
    """测试 SkillDiscovery 自动发现引擎"""

    @pytest.fixture
    def skills_dir(self, tmp_path):
        """创建临时 skills 目录，含两个 SKILL.md"""
        skill_a = tmp_path / "skill_a"
        skill_a.mkdir()
        (skill_a / "SKILL.md").write_text(
            "---\n"
            "name: skill_a\n"
            "description: Skill A\n"
            "version: '1.0'\n"
            "categories:\n"
            "  - test\n"
            "priority: web_search\n"
            "keywords:\n"
            "  - test\n"
            "aliases: []\n"
            "capabilities: []\n"
            "data_types: {}\n"
            "data_source_keywords: []\n"
            "action_rules: []\n"
            "action_param_map: {}\n"
            "supports_topic_fallback: false\n"
            "is_intrinsic: false\n"
            "aspect_coverage: []\n"
            "skill_type: standard\n"
            "---\n"
            "# Skill A\n"
            "Test instructions.\n",
            encoding="utf-8",
        )

        skill_b = tmp_path / "skill_b"
        skill_b.mkdir()
        (skill_b / "SKILL.md").write_text(
            "---\n"
            "name: skill_b\n"
            "description: Skill B\n"
            "version: '2.0'\n"
            "categories:\n"
            "  - production\n"
            "priority: structured_db\n"
            "keywords:\n"
            "  - prod\n"
            "aliases:\n"
            "  - b_alias\n"
            "capabilities:\n"
            "  - query\n"
            "data_types:\n"
            "  zh:\n"
            "    - 数据\n"
            "data_source_keywords:\n"
            "  - 数据\n"
            "action_rules:\n"
            "  - pattern: '.*'\n"
            "    actions:\n"
            "      - query\n"
            "action_param_map:\n"
            "  query:\n"
            "    symbol: symbol\n"
            "supports_topic_fallback: false\n"
            "is_intrinsic: false\n"
            "aspect_coverage:\n"
            "  - Data Analysis\n"
            "skill_type: standard\n"
            "---\n"
            "# Skill B\n"
            "Production skill.\n",
            encoding="utf-8",
        )

        return tmp_path

    @pytest.fixture
    def skills_dir_with_code(self, tmp_path):
        """创建含 skill.py 的 skill 目录"""
        skill_dir = tmp_path / "code_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: code_skill\n"
            "description: Code Skill\n"
            "version: '1.0'\n"
            "categories:\n"
            "  - test\n"
            "priority: web_search\n"
            "keywords:\n"
            "  - code\n"
            "aliases: []\n"
            "capabilities:\n"
            "  - run\n"
            "data_types: {}\n"
            "data_source_keywords: []\n"
            "action_rules: []\n"
            "action_param_map: {}\n"
            "supports_topic_fallback: false\n"
            "is_intrinsic: false\n"
            "aspect_coverage: []\n"
            "skill_type: standard\n"
            "---\n"
            "# Code Skill\n",
            encoding="utf-8",
        )
        (skill_dir / "skill.py").write_text(
            "from src.skills.base import Skill, SkillConfig\n"
            "from typing import Dict, Any\n"
            "\n"
            "class CodeSkill(Skill):\n"
            "    @property\n"
            "    def name(self) -> str:\n"
            "        return 'code_skill'\n"
            "    @property\n"
            "    def description(self) -> str:\n"
            "        return 'Code Skill'\n"
            "    async def execute(self, **kwargs) -> Dict[str, Any]:\n"
            "        return {'success': True}\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_discover_all_finds_skill_dirs(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        assert len(manifests) == 2
        names = {m.name for m in manifests}
        assert names == {"skill_a", "skill_b"}

    def test_discover_all_skips_non_skill_dirs(self, tmp_path):
        from src.skills.discovery import SkillDiscovery

        not_a_skill = tmp_path / "random_dir"
        not_a_skill.mkdir()
        (not_a_skill / "README.md").write_text("Not a skill")

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(tmp_path)

        assert len(manifests) == 0

    def test_discover_all_parses_yaml_frontmatter(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        skill_b = next(m for m in manifests if m.name == "skill_b")
        assert skill_b.version == "2.0"
        assert skill_b.priority == "structured_db"
        assert skill_b.capabilities == ["query"]
        assert skill_b.aliases == ["b_alias"]
        assert skill_b.data_types == {"zh": ["数据"]}
        assert skill_b.data_source_keywords == ["数据"]
        assert len(skill_b.action_rules) == 1
        assert skill_b.action_rules[0].pattern == ".*"
        assert skill_b.action_rules[0].actions == ["query"]

    def test_discover_all_parses_instructions_body(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        skill_a = next(m for m in manifests if m.name == "skill_a")
        assert "# Skill A" in skill_a.instructions
        assert "Test instructions." in skill_a.instructions

    def test_discover_all_detects_has_code(self, skills_dir_with_code):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir_with_code)

        assert len(manifests) == 1
        assert manifests[0].has_code is True

    def test_discover_all_detects_no_code(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        for m in manifests:
            assert m.has_code is False

    def test_discover_all_sets_skill_dir(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        for m in manifests:
            assert m.skill_dir.parent == skills_dir

    def test_discover_all_sorted_by_name(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        names = [m.name for m in manifests]
        assert names == sorted(names)

    def test_discover_all_with_action_rules(self, skills_dir):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(skills_dir)

        skill_b = next(m for m in manifests if m.name == "skill_b")
        assert len(skill_b.action_rules) == 1
        rule = skill_b.action_rules[0]
        assert rule.pattern == ".*"
        assert rule.actions == ["query"]
        assert rule.aspect_keywords is None

    def test_discover_all_with_topic_fallback(self, tmp_path):
        from src.skills.discovery import SkillDiscovery

        skill_dir = tmp_path / "xueqiu"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: xueqiu\n"
            "description: Xueqiu\n"
            "version: '1.0'\n"
            "categories:\n"
            "  - financial-analysis\n"
            "priority: structured_db\n"
            "keywords:\n"
            "  - 雪球\n"
            "aliases: []\n"
            "capabilities:\n"
            "  - quote\n"
            "data_types: {}\n"
            "data_source_keywords: []\n"
            "action_rules: []\n"
            "action_param_map: {}\n"
            "supports_topic_fallback: true\n"
            "topic_fallback_pattern: '[\\\\u4e00-\\\\u9fff]+'\n"
            "is_intrinsic: false\n"
            "aspect_coverage: []\n"
            "skill_type: standard\n"
            "---\n"
            "# Xueqiu\n",
            encoding="utf-8",
        )

        discovery = SkillDiscovery()
        manifests = discovery.discover_all(tmp_path)

        assert len(manifests) == 1
        assert manifests[0].supports_topic_fallback is True
        assert manifests[0].topic_fallback_pattern is not None


class TestSkillDiscoveryBuildRegistries:
    """测试从 manifest 自动构建注册数据"""

    @pytest.fixture
    def manifests(self, tmp_path):
        """创建两个 skill 的 manifests"""
        from src.skills.discovery import SkillDiscovery

        skill_a = tmp_path / "stock_data"
        skill_a.mkdir()
        (skill_a / "SKILL.md").write_text(
            "---\n"
            "name: stock_data\n"
            "description: Stock Data\n"
            "version: '1.0'\n"
            "categories:\n"
            "  - financial-analysis\n"
            "  - research\n"
            "priority: structured_db\n"
            "keywords:\n"
            "  - 股票\n"
            "  - 财报\n"
            "aliases: []\n"
            "capabilities:\n"
            "  - financials\n"
            "  - company_info\n"
            "data_types:\n"
            "  zh:\n"
            "    - 营收\n"
            "data_source_keywords:\n"
            "  - 财务\n"
            "  - 估值\n"
            "action_rules: []\n"
            "action_param_map: {}\n"
            "supports_topic_fallback: false\n"
            "is_intrinsic: false\n"
            "aspect_coverage:\n"
            "  - Financial Analysis\n"
            "skill_type: standard\n"
            "---\n"
            "# Stock Data\n",
            encoding="utf-8",
        )

        skill_b = tmp_path / "xueqiu"
        skill_b.mkdir()
        (skill_b / "SKILL.md").write_text(
            "---\n"
            "name: xueqiu\n"
            "description: Xueqiu\n"
            "version: '1.0'\n"
            "categories:\n"
            "  - financial-analysis\n"
            "  - data-collection\n"
            "priority: structured_db\n"
            "keywords:\n"
            "  - 雪球\n"
            "  - 行情\n"
            "aliases:\n"
            "  - xueqiu_stock\n"
            "capabilities:\n"
            "  - quote\n"
            "  - kline\n"
            "data_types:\n"
            "  zh:\n"
            "    - 换手率\n"
            "data_source_keywords:\n"
            "  - 财务\n"
            "  - 行情\n"
            "action_rules: []\n"
            "action_param_map: {}\n"
            "supports_topic_fallback: true\n"
            "topic_fallback_pattern: '[\\\\u4e00-\\\\u9fff]+'\n"
            "is_intrinsic: false\n"
            "aspect_coverage:\n"
            "  - Financial Analysis\n"
            "  - Valuation\n"
            "skill_type: standard\n"
            "---\n"
            "# Xueqiu\n",
            encoding="utf-8",
        )

        discovery = SkillDiscovery()
        return discovery.discover_all(tmp_path)

    def test_build_category_map(self, manifests):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        registries = discovery.build_registries(manifests)

        cat_map = registries.category_to_skills
        assert "stock_data" in cat_map.get("financial-analysis", [])
        assert "xueqiu" in cat_map.get("financial-analysis", [])
        assert "stock_data" in cat_map.get("research", [])
        assert "xueqiu" in cat_map.get("data-collection", [])

    def test_build_priority_map(self, manifests):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        registries = discovery.build_registries(manifests)

        assert registries.priority_map["stock_data"] == "structured_db"
        assert registries.priority_map["xueqiu"] == "structured_db"

    def test_build_keywords_map(self, manifests):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        registries = discovery.build_registries(manifests)

        assert "股票" in registries.keywords_map["stock_data"]
        assert "雪球" in registries.keywords_map["xueqiu"]

    def test_build_alias_map(self, manifests):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        registries = discovery.build_registries(manifests)

        assert registries.alias_map.get("xueqiu_stock") == "xueqiu"

    def test_build_capabilities_map(self, manifests):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        registries = discovery.build_registries(manifests)

        assert "financials" in registries.capabilities_map
        assert registries.capabilities_map["financials"] == "stock_data"
        assert "quote" in registries.capabilities_map
        assert registries.capabilities_map["quote"] == "xueqiu"

    def test_build_data_source_map(self, manifests):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        registries = discovery.build_registries(manifests)

        ds_map = registries.data_source_skill_map
        assert "stock_data" in ds_map.get("财务", [])
        assert "xueqiu" in ds_map.get("财务", [])
        assert "xueqiu" in ds_map.get("行情", [])

    def test_build_structured_data_capabilities(self, manifests):
        from src.skills.discovery import SkillDiscovery

        discovery = SkillDiscovery()
        registries = discovery.build_registries(manifests)

        sdc = registries.structured_data_capabilities
        assert "stock_data" in sdc
        assert "xueqiu" in sdc
        assert "营收" in sdc["stock_data"]["zh"]
        assert "换手率" in sdc["xueqiu"]["zh"]


class TestSkillDiscoveryLoadClass:
    """测试动态加载 skill.py"""

    def test_load_skill_class_with_code(self, tmp_path):
        from src.skills.discovery import SkillDiscovery, SkillManifest

        skill_dir = tmp_path / "my_skill"
        skill_dir.mkdir()
        (skill_dir / "skill.py").write_text(
            "from src.skills.base import Skill, SkillConfig\n"
            "from typing import Dict, Any\n"
            "\n"
            "class MySkill(Skill):\n"
            "    @property\n"
            "    def name(self) -> str:\n"
            "        return 'my_skill'\n"
            "    @property\n"
            "    def description(self) -> str:\n"
            "        return 'My Skill'\n"
            "    async def execute(self, **kwargs) -> Dict[str, Any]:\n"
            "        return {'success': True}\n",
            encoding="utf-8",
        )

        manifest = SkillManifest(
            name="my_skill",
            description="My Skill",
            version="1.0",
            categories=["test"],
            priority="web_search",
            keywords=["my"],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[],
            action_param_map={},
            supports_topic_fallback=False,
            topic_fallback_pattern=None,
            is_intrinsic=False,
            aspect_coverage=[],
            skill_type="standard",
            skill_dir=skill_dir,
            has_code=True,
            instructions="",
        )

        discovery = SkillDiscovery()
        skill_cls = discovery.load_skill_class(manifest)

        assert skill_cls is not None
        assert skill_cls.__name__ == "MySkill"

    def test_load_skill_class_no_code(self, tmp_path):
        from src.skills.discovery import SkillDiscovery, SkillManifest

        skill_dir = tmp_path / "instr_skill"
        skill_dir.mkdir()

        manifest = SkillManifest(
            name="instr_skill",
            description="Instruction Skill",
            version="1.0",
            categories=["test"],
            priority="web_search",
            keywords=["instr"],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[],
            action_param_map={},
            supports_topic_fallback=False,
            topic_fallback_pattern=None,
            is_intrinsic=False,
            aspect_coverage=[],
            skill_type="standard",
            skill_dir=skill_dir,
            has_code=False,
            instructions="",
        )

        discovery = SkillDiscovery()
        skill_cls = discovery.load_skill_class(manifest)

        assert skill_cls is None
