"""
Skill 基类增强测试 - format_data, infer_actions, resolve_identifier, InstructionSkill

TDD RED 阶段
"""
import pytest
from unittest.mock import Mock
from pathlib import Path


class TestSkillFormatData:
    """测试 Skill.format_data 默认行为和子类覆盖"""

    def test_default_format_data_returns_empty_string(self):
        from src.skills.base import Skill, SkillConfig

        class PlainSkill(Skill):
            @property
            def name(self) -> str:
                return "plain"

            @property
            def description(self) -> str:
                return "Plain"

            async def execute(self, **kwargs):
                return {"success": True}

        skill = PlainSkill()
        result = skill.format_data({"key": "val"}, "some_action", "SYM")
        assert result == ""

    def test_subclass_can_override_format_data(self):
        from src.skills.base import Skill, SkillConfig

        class FmtSkill(Skill):
            @property
            def name(self) -> str:
                return "fmt"

            @property
            def description(self) -> str:
                return "Fmt"

            async def execute(self, **kwargs):
                return {"success": True}

            def format_data(self, data: dict, action: str, symbol: str) -> str:
                return f"{symbol}:{action}={data.get('value', 'N/A')}"

        skill = FmtSkill()
        result = skill.format_data({"value": 42}, "quote", "SH600519")
        assert result == "SH600519:quote=42"


class TestSkillInferActions:
    """测试 Skill.infer_actions 通用 action 推断"""

    def test_infer_actions_with_manifest_action_rules_pattern_match(self):
        from src.skills.base import Skill
        from src.skills.discovery import SkillManifest, ActionRule

        class RuleSkill(Skill):
            @property
            def name(self) -> str:
                return "rule_skill"

            @property
            def description(self) -> str:
                return "Rule"

            async def execute(self, **kwargs):
                return {"success": True}

        manifest = SkillManifest(
            name="rule_skill",
            description="Rule",
            version="1.0",
            categories=[],
            priority="web_search",
            keywords=[],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[
                ActionRule(
                    pattern=r"^(SH|SZ|BJ)?\d{6}$",
                    actions=["quote", "kline"],
                ),
                ActionRule(
                    pattern=r".*",
                    actions=["search_and_quote"],
                ),
            ],
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
        skill = RuleSkill()
        skill._manifest = manifest

        actions = skill.infer_actions("", "SH600519")
        assert actions == ["quote", "kline"]

    def test_infer_actions_fallback_to_wildcard_rule(self):
        from src.skills.base import Skill
        from src.skills.discovery import SkillManifest, ActionRule

        class RuleSkill(Skill):
            @property
            def name(self) -> str:
                return "rule_skill"

            @property
            def description(self) -> str:
                return "Rule"

            async def execute(self, **kwargs):
                return {"success": True}

        manifest = SkillManifest(
            name="rule_skill",
            description="Rule",
            version="1.0",
            categories=[],
            priority="web_search",
            keywords=[],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[
                ActionRule(
                    pattern=r"^(SH|SZ|BJ)?\d{6}$",
                    actions=["quote", "kline"],
                ),
                ActionRule(
                    pattern=r".*",
                    actions=["search_and_quote"],
                ),
            ],
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
        skill = RuleSkill()
        skill._manifest = manifest

        actions = skill.infer_actions("", "腾讯控股")
        assert actions == ["search_and_quote"]

    def test_infer_actions_with_aspect_keywords_filter(self):
        from src.skills.base import Skill
        from src.skills.discovery import SkillManifest, ActionRule

        class RuleSkill(Skill):
            @property
            def name(self) -> str:
                return "rule_skill"

            @property
            def description(self) -> str:
                return "Rule"

            async def execute(self, **kwargs):
                return {"success": True}

        manifest = SkillManifest(
            name="rule_skill",
            description="Rule",
            version="1.0",
            categories=[],
            priority="web_search",
            keywords=[],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[
                ActionRule(
                    pattern=r"^(SH|SZ|BJ)?\d{6}$",
                    aspect_keywords=["竞争", "热门", "competitive", "hot"],
                    actions=["quote", "kline", "hot_stocks"],
                ),
                ActionRule(
                    pattern=r"^(SH|SZ|BJ)?\d{6}$",
                    actions=["quote", "kline"],
                ),
            ],
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
        skill = RuleSkill()
        skill._manifest = manifest

        actions_with_aspect = skill.infer_actions("竞争格局分析", "SH600519")
        assert actions_with_aspect == ["quote", "kline", "hot_stocks"]

        actions_without_aspect = skill.infer_actions("财务分析", "SH600519")
        assert actions_without_aspect == ["quote", "kline"]

    def test_infer_actions_no_manifest_returns_default(self):
        from src.skills.base import Skill

        class NoManifestSkill(Skill):
            @property
            def name(self) -> str:
                return "no_manifest"

            @property
            def description(self) -> str:
                return "No manifest"

            async def execute(self, **kwargs):
                return {"success": True}

        skill = NoManifestSkill()
        actions = skill.infer_actions("any_aspect", "any_symbol")
        assert actions == ["default"]

    def test_infer_actions_aspect_keyword_case_insensitive(self):
        from src.skills.base import Skill
        from src.skills.discovery import SkillManifest, ActionRule

        class RuleSkill(Skill):
            @property
            def name(self) -> str:
                return "rule_skill"

            @property
            def description(self) -> str:
                return "Rule"

            async def execute(self, **kwargs):
                return {"success": True}

        manifest = SkillManifest(
            name="rule_skill",
            description="Rule",
            version="1.0",
            categories=[],
            priority="web_search",
            keywords=[],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[
                ActionRule(
                    pattern=r".*",
                    aspect_keywords=["Competitive", "Hot"],
                    actions=["special"],
                ),
                ActionRule(
                    pattern=r".*",
                    actions=["generic"],
                ),
            ],
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
        skill = RuleSkill()
        skill._manifest = manifest

        actions = skill.infer_actions("competitive analysis", "AAPL")
        assert actions == ["special"]


class TestSkillResolveIdentifier:
    """测试 Skill.resolve_identifier 从 topic 提取标识符"""

    def test_resolve_identifier_with_chinese_pattern(self):
        from src.skills.base import Skill
        from src.skills.discovery import SkillManifest

        class XueqiuSkill(Skill):
            @property
            def name(self) -> str:
                return "xueqiu"

            @property
            def description(self) -> str:
                return "Xueqiu"

            async def execute(self, **kwargs):
                return {"success": True}

        manifest = SkillManifest(
            name="xueqiu",
            description="Xueqiu",
            version="1.0",
            categories=[],
            priority="structured_db",
            keywords=[],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[],
            action_param_map={},
            supports_topic_fallback=True,
            topic_fallback_pattern=r"[\u4e00-\u9fff]+",
            is_intrinsic=False,
            aspect_coverage=[],
            skill_type="standard",
            skill_dir=Path("/fake"),
            has_code=False,
            instructions="",
        )
        skill = XueqiuSkill()
        skill._manifest = manifest

        identifier = skill.resolve_identifier("腾讯控股 投资价值分析", "估值")
        assert identifier == "腾讯控股"

    def test_resolve_identifier_all_chinese_matches_all(self):
        from src.skills.base import Skill
        from src.skills.discovery import SkillManifest

        class XueqiuSkill(Skill):
            @property
            def name(self) -> str:
                return "xueqiu"

            @property
            def description(self) -> str:
                return "Xueqiu"

            async def execute(self, **kwargs):
                return {"success": True}

        manifest = SkillManifest(
            name="xueqiu",
            description="Xueqiu",
            version="1.0",
            categories=[],
            priority="structured_db",
            keywords=[],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[],
            action_param_map={},
            supports_topic_fallback=True,
            topic_fallback_pattern=r"[\u4e00-\u9fff]+",
            is_intrinsic=False,
            aspect_coverage=[],
            skill_type="standard",
            skill_dir=Path("/fake"),
            has_code=False,
            instructions="",
        )
        skill = XueqiuSkill()
        skill._manifest = manifest

        identifier = skill.resolve_identifier("腾讯控股投资价值分析", "估值")
        assert identifier is not None
        assert "腾讯" in identifier

    def test_resolve_identifier_no_match_returns_none(self):
        from src.skills.base import Skill
        from src.skills.discovery import SkillManifest

        class XueqiuSkill(Skill):
            @property
            def name(self) -> str:
                return "xueqiu"

            @property
            def description(self) -> str:
                return "Xueqiu"

            async def execute(self, **kwargs):
                return {"success": True}

        manifest = SkillManifest(
            name="xueqiu",
            description="Xueqiu",
            version="1.0",
            categories=[],
            priority="structured_db",
            keywords=[],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[],
            action_param_map={},
            supports_topic_fallback=True,
            topic_fallback_pattern=r"[\u4e00-\u9fff]+",
            is_intrinsic=False,
            aspect_coverage=[],
            skill_type="standard",
            skill_dir=Path("/fake"),
            has_code=False,
            instructions="",
        )
        skill = XueqiuSkill()
        skill._manifest = manifest

        identifier = skill.resolve_identifier("AAPL valuation", "估值")
        assert identifier is None

    def test_resolve_identifier_no_manifest_returns_none(self):
        from src.skills.base import Skill

        class NoManifestSkill(Skill):
            @property
            def name(self) -> str:
                return "no_manifest"

            @property
            def description(self) -> str:
                return "No manifest"

            async def execute(self, **kwargs):
                return {"success": True}

        skill = NoManifestSkill()
        assert skill.resolve_identifier("anything", "anything") is None

    def test_resolve_identifier_not_supported_returns_none(self):
        from src.skills.base import Skill
        from src.skills.discovery import SkillManifest

        class NoFallbackSkill(Skill):
            @property
            def name(self) -> str:
                return "no_fallback"

            @property
            def description(self) -> str:
                return "No fallback"

            async def execute(self, **kwargs):
                return {"success": True}

        manifest = SkillManifest(
            name="no_fallback",
            description="No fallback",
            version="1.0",
            categories=[],
            priority="web_search",
            keywords=[],
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
            instructions="",
        )
        skill = NoFallbackSkill()
        skill._manifest = manifest

        assert skill.resolve_identifier("腾讯控股", "估值") is None


class TestInstructionSkill:
    """测试纯指令型 Skill"""

    def test_instruction_skill_init(self):
        from src.skills.base import InstructionSkill
        from src.skills.discovery import SkillManifest

        manifest = SkillManifest(
            name="llm",
            description="LLM instruction skill",
            version="1.0",
            categories=["synthesis", "quality-check"],
            priority="llm",
            keywords=["llm", "生成", "分析"],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[],
            action_param_map={},
            supports_topic_fallback=False,
            topic_fallback_pattern=None,
            is_intrinsic=True,
            aspect_coverage=[],
            skill_type="standard",
            skill_dir=Path("/fake/llm"),
            has_code=False,
            instructions="# LLM Skill\nYou are an expert analyst.",
        )
        skill = InstructionSkill(manifest)
        assert skill.name == "llm"
        assert skill.description == "LLM instruction skill"

    @pytest.mark.asyncio
    async def test_instruction_skill_execute(self):
        from src.skills.base import InstructionSkill
        from src.skills.discovery import SkillManifest

        manifest = SkillManifest(
            name="llm",
            description="LLM instruction skill",
            version="1.0",
            categories=[],
            priority="llm",
            keywords=[],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[],
            action_param_map={},
            supports_topic_fallback=False,
            topic_fallback_pattern=None,
            is_intrinsic=True,
            aspect_coverage=[],
            skill_type="standard",
            skill_dir=Path("/fake/llm"),
            has_code=False,
            instructions="# LLM Skill\nDetailed instructions here.",
        )
        skill = InstructionSkill(manifest)
        result = await skill.execute()
        assert result["success"] is True
        assert result["source"] == "llm"
        assert "instructions" in result["data"]
        assert "Detailed instructions here." in result["data"]["instructions"]
        assert len(result["content"]) <= 500

    def test_instruction_skill_is_skill_subclass(self):
        from src.skills.base import Skill, InstructionSkill
        from src.skills.discovery import SkillManifest

        manifest = SkillManifest(
            name="test_instr",
            description="Test",
            version="1.0",
            categories=[],
            priority="llm",
            keywords=[],
            aliases=[],
            capabilities=[],
            data_types={},
            data_source_keywords=[],
            action_rules=[],
            action_param_map={},
            supports_topic_fallback=False,
            topic_fallback_pattern=None,
            is_intrinsic=True,
            aspect_coverage=[],
            skill_type="standard",
            skill_dir=Path("/fake"),
            has_code=False,
            instructions="Test",
        )
        skill = InstructionSkill(manifest)
        assert isinstance(skill, Skill)
