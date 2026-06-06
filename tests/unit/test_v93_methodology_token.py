"""
v9.3-A4: 方法论 token 150→800, 前3个框架

验证:
  1. _get_professional_role_prompt 注入前3个框架而非仅 [0]
  2. 0 方法论时跳过
  3. 截断边界 (<3 框架)
  4. 不破坏现有 entity/pattern 注入
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


class TestMethodologyMultiFramework:
    """验证方法论注入从 [0][:150] 升级为前3个"""

    def _make_agent(self):
        """创建最小 agent 实例"""
        from src.core.agents.generic_agent import GenericAgent

        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_method_001"
        agent._knowledge_enrichment = {}
        agent._quality_feedback = None
        # 模拟 _get_professional_role_prompt 所需依赖
        agent.config = {"language": "zh"}
        return agent

    def _call_prompt_method(self, agent, methodologies):
        """模拟调用 _get_professional_role_prompt 并验证方法论部分"""
        from src.core.agents.generic_agent import GenericAgent

        # 模拟 _knowledge_enrichment 中的方法论
        agent._knowledge_enrichment = {
            "entities": [{"name": "TestCo", "description": "A test company"}],
            "patterns": [{"content": "growth trend: market expanding"}],
            "methodologies": methodologies,
        }

        # 模拟 PromptManager 和其他依赖
        with patch("src.core.agents.generic_agent.PromptManager") as MockPM, \
             patch("src.core.prompt_manager.get_profile_name_for_aspect") as mock_get_profile, \
             patch("src.core.i18n.get_language_instruction") as mock_lang:

            mock_pm = MagicMock()
            mock_profile = MagicMock()
            mock_profile.system_prompt = "System prompt placeholder."
            mock_pm.load_profile.return_value = mock_profile
            mock_pm.render.return_value = "\nOutput spec placeholder.\n"
            MockPM.return_value = mock_pm
            mock_get_profile.return_value = "test_profile"
            mock_lang.return_value = ""

            # 调用被测试方法
            from src.core.agents.generic_agent import GenericAgent
            result = agent._get_professional_role_prompt("test_aspect")
            return result

    def test_three_frameworks_injected(self):
        """3 个方法论应全部注入, 带编号和名称"""
        agent = self._make_agent()
        methodologies = [
            {"name": "Porter Five Forces", "content": "Analyze competitive intensity using five forces: threat of new entrants, bargaining power of buyers, bargaining power of suppliers, threat of substitutes, and industry rivalry."},
            {"name": "SWOT Analysis", "content": "Evaluate Strengths, Weaknesses, Opportunities, and Threats relative to market position and competitive dynamics."},
            {"name": "Market Sizing", "content": "Estimate total addressable market using top-down and bottom-up approaches with cross-validation."},
        ]
        result = self._call_prompt_method(agent, methodologies)

        assert "分析框架" in result, "Should contain framework section header"
        assert "1." in result, "Should enumerate first framework"
        assert "2." in result, "Should enumerate second framework"
        assert "3." in result, "Should enumerate third framework"
        assert "Porter" in result, "Should include first framework name"
        assert "SWOT" in result, "Should include second framework name"
        assert "Market" in result, "Should include third framework name"

    def test_zero_methodologies_skipped(self):
        """无方法论时应跳过, 不产生空框架节"""
        agent = self._make_agent()
        result = self._call_prompt_method(agent, [])

        assert "分析框架" not in result, "Should not contain framework section when no methodologies"

    def test_one_methodology_injected(self):
        """仅 1 个方法论时应正确注入"""
        agent = self._make_agent()
        methodologies = [
            {"name": "Porter Five Forces", "content": "Analyze competitive intensity using five forces."},
        ]
        result = self._call_prompt_method(agent, methodologies)

        assert "1." in result
        assert "Porter" in result
        assert "2." not in result, "Should not have second framework"

    def test_two_methodologies_injected(self):
        """2 个方法论时应正确注入"""
        agent = self._make_agent()
        methodologies = [
            {"name": "SWOT", "content": "Strengths, Weaknesses, Opportunities, Threats."},
            {"name": "PESTEL", "content": "Political, Economic, Social, Technological, Environmental, Legal."},
        ]
        result = self._call_prompt_method(agent, methodologies)

        assert "1." in result
        assert "2." in result
        assert "SWOT" in result
        assert "PESTEL" in result

    def test_framework_content_truncated(self):
        """单个方法论内容超过 300 字符应截断"""
        agent = self._make_agent()
        long_content = "A " * 200  # ~400 chars
        methodologies = [
            {"name": "Long Framework", "content": long_content},
        ]
        result = self._call_prompt_method(agent, methodologies)

        # 注入内容不应超过 ~300 chars
        framework_section = result.split("分析框架")[-1] if "分析框架" in result else ""
        assert len(framework_section) < 400, f"Framework content too long: {len(framework_section)} chars"

    def test_entity_and_pattern_not_broken(self):
        """实体和模式注入不受方法论改动影响"""
        agent = self._make_agent()
        methodologies = [
            {"name": "Test", "content": "Test framework content here."},
        ]
        result = self._call_prompt_method(agent, methodologies)

        # 实体和模式应仍正常注入
        assert "TestCo" in result
        assert "market expanding" in result or "growth" in result

    def test_methodology_name_fallback_methodology_name_key(self):
        """methodology_name key 应作为 name 的回退"""
        agent = self._make_agent()
        methodologies = [
            {"methodology_name": "Alt Framework", "content": "Alternative name key content for testing fallback."},
        ]
        result = self._call_prompt_method(agent, methodologies)

        assert "Alt Framework" in result, \
            "Should use 'methodology_name' key as fallback"

    def test_methodology_name_fallback_title_key(self):
        """title key 应作为 name/methodology_name 的回退"""
        agent = self._make_agent()
        methodologies = [
            {"title": "Title Framework", "content": "Title-based name content here."},
        ]
        result = self._call_prompt_method(agent, methodologies)

        assert "Title Framework" in result, \
            "Should use 'title' key as fallback"

    def test_methodology_name_no_name_fallback(self):
        """无任何 name key 时应显示默认名称"""
        agent = self._make_agent()
        methodologies = [
            {"content": "Framework with no name key at all."},
        ]
        result = self._call_prompt_method(agent, methodologies)

        # 应默认显示"框架1"
        assert "框架1" in result, \
            "Should use default name when no name/methodology_name/title key"


if __name__ == "__main__":
    pytest.main([__file__])
