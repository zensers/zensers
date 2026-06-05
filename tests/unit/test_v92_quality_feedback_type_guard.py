import pytest
from unittest.mock import patch, MagicMock


class TestQualityFeedbackTypeGuard:
    """_quality_feedback issues 字段类型守卫测试。

    当前代码在 generic_agent.py:2922 假设 fb_issues 是 List[str]，
    type guard 需兼容 List[str] 和 List[Dict] 两种格式。
    """

    @pytest.fixture
    def agent(self):
        from src.core.agents.generic_agent import GenericAgent
        import gc
        # Create minimal instance without full __init__
        a = GenericAgent.__new__(GenericAgent)
        a.agent_id = "test_guard_001"
        a._knowledge_enrichment = {}
        a._quality_feedback = None
        return a

    def _call_prompt_method(self, agent, aspect="test_aspect"):
        """Call _get_professional_role_prompt with mocked dependencies."""
        with patch("src.core.agents.generic_agent.PromptManager") as MockPM, \
             patch("src.core.prompt_manager.get_profile_name_for_aspect") as mock_get_profile, \
             patch("src.core.i18n.get_language_instruction") as mock_lang:

            mock_get_profile.return_value = "general"
            mock_lang.return_value = ""

            mock_pm = MagicMock()
            mock_profile = MagicMock()
            mock_profile.system_prompt = "System prompt placeholder."
            mock_pm.load_profile.return_value = mock_profile
            mock_pm.render.return_value = "\nOutput spec placeholder.\n"
            MockPM.return_value = mock_pm

            return agent._get_professional_role_prompt(aspect)

    def test_string_issues_render_correctly(self, agent):
        agent._quality_feedback = {
            "score": 42.0,
            "issues": ["数据覆盖不足", "缺少竞争对比", "因果分析缺失"],
            "previous_attempt": 1,
        }
        result = self._call_prompt_method(agent)
        assert "需改进的问题:" in result
        assert "- 数据覆盖不足" in result
        assert "- 缺少竞争对比" in result
        assert "- 因果分析缺失" in result
        assert "上次得分: 42" in result
        assert "重试第2次" in result

    def test_dict_issues_render_by_message_key(self, agent):
        agent._quality_feedback = {
            "score": 35.0,
            "issues": [
                {"message": "数据覆盖不足", "type": "coverage", "severity": "high"},
                {"message": "缺少竞争对比", "type": "analysis", "severity": "medium"},
            ],
            "previous_attempt": 0,
        }
        result = self._call_prompt_method(agent)
        assert "需改进的问题:" in result
        assert "- 数据覆盖不足" in result
        assert "- 缺少竞争对比" in result
        assert "重试第1次" in result

    def test_mixed_issues_handles_both_types(self, agent):
        agent._quality_feedback = {
            "score": 50.0,
            "issues": [
                "简单文本问题",
                {"message": "结构化问题", "type": "structure"},
            ],
            "previous_attempt": 2,
        }
        result = self._call_prompt_method(agent)
        assert "- 简单文本问题" in result
        assert "- 结构化问题" in result
        assert "重试第3次" in result

    def test_empty_issues_produces_clean_output(self, agent):
        agent._quality_feedback = {
            "score": 80.0,
            "issues": [],
            "previous_attempt": 0,
        }
        result = self._call_prompt_method(agent)
        assert "需改进的问题:" in result
        assert "重试第1次" in result

    def test_max_three_issues_shown(self, agent):
        agent._quality_feedback = {
            "score": 30.0,
            "issues": ["问题A", "问题B", "问题C", "问题D", "问题E"],
            "previous_attempt": 0,
        }
        result = self._call_prompt_method(agent)
        assert "- 问题A" in result
        assert "- 问题C" in result
        assert "- 问题D" not in result
        assert "- 问题E" not in result

    def test_missing_issues_key_does_not_crash(self, agent):
        agent._quality_feedback = {"score": 60.0, "previous_attempt": 0}
        result = self._call_prompt_method(agent)
        assert "需改进的问题:" in result

    def test_quality_feedback_none_skips_section(self, agent):
        agent._quality_feedback = None
        result = self._call_prompt_method(agent)
        assert "质量反馈" not in result

    def test_quality_feedback_empty_dict_skips_section(self, agent):
        agent._quality_feedback = {}
        result = self._call_prompt_method(agent)
        assert "质量反馈" not in result

    def test_dict_issues_without_message_key_falls_back_to_str(self, agent):
        agent._quality_feedback = {
            "score": 45.0,
            "issues": [
                {"type": "unknown", "severity": "low"},
            ],
            "previous_attempt": 0,
        }
        result = self._call_prompt_method(agent)
        assert "需改进的问题:" in result

    def test_issues_truncated_to_first_three_dicts(self, agent):
        agent._quality_feedback = {
            "score": 20.0,
            "issues": [
                {"message": "问题1"},
                {"message": "问题2"},
                {"message": "问题3"},
                {"message": "问题4"},
            ],
            "previous_attempt": 0,
        }
        result = self._call_prompt_method(agent)
        assert "- 问题1" in result
        assert "- 问题3" in result
        assert "问题4" not in result
