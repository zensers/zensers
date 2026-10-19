"""
Skill 基类测试 - TDD模式
"""
import pytest
from typing import Dict, Any


class TestSkillBase:
    """测试 Skill 基类"""

    def test_skill_init(self):
        """测试 Skill 初始化"""
        from src.skills.base import Skill, SkillConfig

        config = SkillConfig(name="test_skill", version="1.0.0")
        assert config.name == "test_skill"
        assert config.version == "1.0.0"
        assert config.enabled is True

    def test_skill_metadata(self):
        """测试 Skill 元数据"""
        from src.skills.base import Skill, SkillConfig

        class MySkill(Skill):
            @property
            def name(self) -> str:
                return "my_skill"

            @property
            def description(self) -> str:
                return "测试Skill"

            async def execute(self, **kwargs) -> Dict[str, Any]:
                return {"status": "ok"}

        skill = MySkill(SkillConfig(name="my_skill", version="1.0.0"))
        assert skill.name == "my_skill"
        assert skill.description == "测试Skill"

    @pytest.mark.asyncio
    async def test_skill_execute(self):
        """测试 Skill 执行"""
        from src.skills.base import Skill, SkillConfig

        class EchoSkill(Skill):
            @property
            def name(self) -> str:
                return "echo"

            @property
            def description(self) -> str:
                return "Echo Skill"

            async def execute(self, **kwargs) -> Dict[str, Any]:
                return {"echo": kwargs.get("message", "")}

        skill = EchoSkill(SkillConfig(name="echo", version="1.0.0"))
        result = await skill.execute(message="hello")
        assert result["echo"] == "hello"

    def test_skill_config_disabled(self):
        """测试禁用 Skill"""
        from src.skills.base import SkillConfig
        config = SkillConfig(name="disabled_skill", version="1.0.0", enabled=False)
        assert config.enabled is False

    def test_skill_registry(self):
        """测试 Skill 注册中心"""
        from src.skills.base import SkillRegistry, Skill, SkillConfig

        class SkillA(Skill):
            @property
            def name(self) -> str:
                return "skill_a"

            @property
            def description(self) -> str:
                return "Skill A"

            async def execute(self, **kwargs) -> Dict[str, Any]:
                return {}

        registry = SkillRegistry()
        registry.register("skill_a", SkillA)
        assert registry.get("skill_a") is SkillA

    def test_skill_registry_unknown(self):
        """测试获取未注册 Skill"""
        from src.skills.base import SkillRegistry
        registry = SkillRegistry()
        assert registry.get("nonexistent") is None

    def test_skill_output_schema(self):
        """测试 SkillOutput 结构"""
        from src.skills.base import SkillOutput
        output = SkillOutput(success=True, data={"key": "value"}, message="OK")
        assert output.success is True
        assert output.data["key"] == "value"
        assert output.message == "OK"

    def test_skill_output_failure(self):
        """测试 SkillOutput 失败结构"""
        from src.skills.base import SkillOutput
        output = SkillOutput(success=False, data={}, message="失败", error="错误详情")
        assert output.success is False
        assert output.error == "错误详情"

    def test_infer_actions_cumulative_matching(self):
        """Task 1.3a: infer_actions 应累加匹配所有 rule 的 actions，而非排他返回第一个"""
        from src.skills.base import Skill
        from src.skills.discovery import ActionRule, SkillManifest
        from pathlib import Path
        from typing import Dict, Any

        class TestSkill(Skill):
            @property
            def name(self) -> str:
                return "test_cumulative"
            @property
            def description(self) -> str:
                return "test"
            async def execute(self, **kwargs) -> Dict[str, Any]:
                return {"success": True}

        manifest = SkillManifest(
            name="test_cumulative", description="test", version="1.0",
            categories=[], priority="structured_db", keywords=[], aliases=[],
            capabilities=[], data_types={}, data_source_keywords=[],
            action_rules=[
                ActionRule(pattern=".*", aspect_keywords=["盈利", "利润"], actions=["financials"]),
                ActionRule(pattern=".*", aspect_keywords=["估值", "pe"], actions=["key_metrics", "financials"]),
                ActionRule(pattern=".*", actions=["company_info", "financials"]),
            ],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("."), has_code=False, instructions="",
        )

        skill = TestSkill()
        skill._manifest = manifest

        # aspect="盈利估值分析" 应同时匹配"盈利"和"估值"两个 rule
        # 累加模式: financials + key_metrics + financials → 去重 → ["financials", "key_metrics"]
        result = skill.infer_actions("盈利估值分析", "SH600519")
        assert "financials" in result, f"应包含 financials，实际: {result}"
        assert "key_metrics" in result, f"应包含 key_metrics（累加匹配），实际: {result}"

    def test_infer_actions_default_fallback_when_no_match(self):
        """Task 1.3a: 无 aspect_keywords 匹配时，应走兜底 rule（最后一个无 aspect_keywords 的 rule）"""
        from src.skills.base import Skill
        from src.skills.discovery import ActionRule, SkillManifest
        from pathlib import Path
        from typing import Dict, Any

        class TestSkill(Skill):
            @property
            def name(self) -> str:
                return "test_default"
            @property
            def description(self) -> str:
                return "test"
            async def execute(self, **kwargs) -> Dict[str, Any]:
                return {"success": True}

        manifest = SkillManifest(
            name="test_default", description="test", version="1.0",
            categories=[], priority="structured_db", keywords=[], aliases=[],
            capabilities=[], data_types={}, data_source_keywords=[],
            action_rules=[
                ActionRule(pattern=".*", aspect_keywords=["盈利"], actions=["financials"]),
                ActionRule(pattern=".*", actions=["company_info", "financials"]),
            ],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("."), has_code=False, instructions="",
        )

        skill = TestSkill()
        skill._manifest = manifest

        # aspect="其他分析" 不匹配任何 aspect_keywords，应走兜底 rule
        result = skill.infer_actions("其他分析", "SH600519")
        assert result == ["company_info", "financials"], f"应走兜底 rule，实际: {result}"

    def test_infer_actions_dedup_preserves_order(self):
        """Task 1.3a: 累加去重应保持首次出现顺序"""
        from src.skills.base import Skill
        from src.skills.discovery import ActionRule, SkillManifest
        from pathlib import Path
        from typing import Dict, Any

        class TestSkill(Skill):
            @property
            def name(self) -> str:
                return "test_dedup"
            @property
            def description(self) -> str:
                return "test"
            async def execute(self, **kwargs) -> Dict[str, Any]:
                return {"success": True}

        manifest = SkillManifest(
            name="test_dedup", description="test", version="1.0",
            categories=[], priority="structured_db", keywords=[], aliases=[],
            capabilities=[], data_types={}, data_source_keywords=[],
            action_rules=[
                ActionRule(pattern=".*", aspect_keywords=["增长"], actions=["financials", "key_metrics"]),
                ActionRule(pattern=".*", aspect_keywords=["估值"], actions=["key_metrics", "financials"]),
            ],
            action_param_map={}, supports_topic_fallback=False,
            topic_fallback_pattern=None, is_intrinsic=False,
            aspect_coverage=[], skill_type="standard",
            skill_dir=Path("."), has_code=False, instructions="",
        )

        skill = TestSkill()
        skill._manifest = manifest

        # "增长估值" 匹配两个 rule:
        # rule1: ["financials", "key_metrics"]
        # rule2: ["key_metrics", "financials"]
        # 累加去重: ["financials", "key_metrics"] (保持首次出现顺序)
        result = skill.infer_actions("增长估值分析", "SH600519")
        assert result == ["financials", "key_metrics"], f"去重应保持首次出现顺序，实际: {result}"
