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
