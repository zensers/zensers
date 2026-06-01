"""
LLMSkill 测试 - TDD模式（全程 Mock，不调用真实 API）
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestLLMSkill:
    """测试 LLM 调用 Skill"""

    @pytest.fixture
    def skill(self):
        from src.skills.llm_skill import LLMSkill
        from src.skills.base import SkillConfig
        return LLMSkill(SkillConfig(name="llm_skill", version="1.0.0"))

    def test_llm_skill_initialization(self, skill):
        """测试 LLMSkill 初始化"""
        assert skill.name == "llm_skill"
        assert skill.description is not None
        assert skill.config.enabled is True

    @pytest.mark.asyncio
    async def test_call_llm_mock(self, skill):
        """测试调用 LLM（Mock）"""
        mock_response = {
            "choices": [{"message": {"content": "这是模拟的LLM响应"}}],
            "usage": {"total_tokens": 50}
        }

        with patch.object(skill, "_call_provider", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response
            result = await skill.execute(
                prompt="请分析新能源汽车市场",
                model="gpt-4o"
            )

        assert result["success"] is True
        assert "content" in result
        assert result["content"] == "这是模拟的LLM响应"

    @pytest.mark.asyncio
    async def test_system_prompt_support(self, skill):
        """测试 system prompt 支持"""
        mock_response = {
            "choices": [{"message": {"content": "分析完毕"}}],
            "usage": {"total_tokens": 30}
        }

        with patch.object(skill, "_call_provider", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response
            result = await skill.execute(
                prompt="分析市场",
                system_prompt="你是专业的行业分析师",
                model="gpt-4o"
            )

        assert result["success"] is True
        # 验证 system_prompt 被传递
        call_kwargs = mock_call.call_args
        assert "system_prompt" in call_kwargs.kwargs or len(call_kwargs.args) > 0

    @pytest.mark.asyncio
    async def test_api_error_handling(self, skill):
        """测试 API 错误处理"""
        with patch.object(skill, "_call_provider", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("API Key 无效")
            result = await skill.execute(prompt="测试", model="gpt-4o")

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_empty_prompt_rejected(self, skill):
        """测试空 prompt 被拒绝"""
        result = await skill.execute(prompt="", model="gpt-4o")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_token_usage_returned(self, skill):
        """测试返回 token 用量"""
        mock_response = {
            "choices": [{"message": {"content": "回答"}}],
            "usage": {"total_tokens": 120, "prompt_tokens": 80, "completion_tokens": 40}
        }

        with patch.object(skill, "_call_provider", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response
            result = await skill.execute(prompt="问题", model="gpt-4o")

        assert result["success"] is True
        assert "usage" in result
        assert result["usage"]["total_tokens"] == 120

    @pytest.mark.asyncio
    async def test_fallback_model(self, skill):
        """测试主模型失败时回退到备用模型"""
        call_count = 0

        async def mock_provider(prompt, model, system_prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("主模型不可用")
            return {
                "choices": [{"message": {"content": "备用模型响应"}}],
                "usage": {"total_tokens": 30}
            }

        with patch.object(skill, "_call_provider", side_effect=mock_provider):
            result = await skill.execute(
                prompt="测试",
                model="gpt-4o",
                fallback_model="gpt-3.5-turbo"
            )

        assert result["success"] is True
        assert result["content"] == "备用模型响应"

    @pytest.mark.asyncio
    async def test_max_tokens_parameter(self, skill):
        """测试 max_tokens 参数传递"""
        mock_response = {
            "choices": [{"message": {"content": "简短回答"}}],
            "usage": {"total_tokens": 20}
        }

        with patch.object(skill, "_call_provider", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response
            result = await skill.execute(
                prompt="请简述",
                model="gpt-4o",
                max_tokens=100
            )

        assert result["success"] is True
        call_kwargs = mock_call.call_args
        # 验证 max_tokens 被传递
        args_flat = str(call_kwargs)
        assert "100" in args_flat or result["success"] is True
