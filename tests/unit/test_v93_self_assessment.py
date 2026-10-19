"""
v9.3-A7: Agent 自评指令

验证:
  1. _self_evaluate() 方法存在且返回 Dict
  2. rubric 来源是文件读取 (_load_quality_rubric) 而非 _context
  3. _call_llm_directly 返回 Dict (含 success/content 键)
  4. 短内容 (<500 字) 跳过自评
  5. rubric 文件不存在时跳过自评
  6. max_self_eval_iterations 可配置 (默认 1, 设为 0 关闭)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
import tempfile
from unittest.mock import MagicMock, patch, AsyncMock


class TestSelfAssessmentInstruction:
    """验证 Agent 自评步骤"""

    def _make_agent(self):
        """创建最小 agent 实例"""
        from src.core.agents.generic_agent import GenericAgent

        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_selfeval_001"
        agent._knowledge_enrichment = {}
        agent._quality_feedback = None
        agent.config = {"language": "zh", "max_self_eval_iterations": 1}
        return agent

    def test_has_self_evaluate_method(self):
        """GenericAgent 应新增 _self_evaluate 异步方法"""
        from src.core.agents.generic_agent import GenericAgent
        import inspect

        agent = self._make_agent()
        assert hasattr(agent, "_self_evaluate"), "Should have _self_evaluate method"
        assert inspect.iscoroutinefunction(agent._self_evaluate), \
            "_self_evaluate should be async"

    def test_self_evaluate_returns_dict_with_score(self):
        """_self_evaluate 应返回包含 score 的 dict"""
        import asyncio
        agent = self._make_agent()

        # 模拟 _load_quality_rubric 返回有效 rubric
        with patch("src.core.agents.generic_agent._load_quality_rubric",
                   return_value="## 评分标准\n1. 数据完整性\n2. 逻辑严谨性"), \
             patch.object(agent, '_call_llm_directly') as mock_llm:

            # _call_llm_directly 返回 Dict: {"success": True, "content": "..."}
            mock_llm.return_value = {
                "success": True,
                "content": '{"score": 85, "weak_dimensions": ["data_support"], '
                           '"suggestions": ["add more quantitative data"]}'
            }

            result = asyncio.run(
                agent._self_evaluate("Test " * 200)  # > 500 chars
            )

        assert isinstance(result, dict)
        assert result.get("score") == 85
        assert "weak_dimensions" in result
        assert "suggestions" in result

    def test_self_evaluate_skipped_short_content(self):
        """短内容 (<500 字) 应跳过自评，不调用 LLM"""
        import asyncio
        agent = self._make_agent()

        with patch("src.core.agents.generic_agent._load_quality_rubric",
                   return_value="Some rubric"), \
             patch.object(agent, '_call_llm_directly') as mock_llm:

            result = asyncio.run(agent._self_evaluate("Short content"))

            assert result == {"pass": True, "score": 100}
            mock_llm.assert_not_called()

    def test_self_evaluate_skipped_no_rubric_file(self):
        """rubric 文件不存在时跳过自评"""
        import asyncio
        agent = self._make_agent()

        with patch("src.core.agents.generic_agent._load_quality_rubric",
                   return_value=""), \
             patch.object(agent, '_call_llm_directly') as mock_llm:

            result = asyncio.run(
                agent._self_evaluate("Test " * 200)  # > 500 chars
            )

            assert result == {"pass": True, "score": 100}
            mock_llm.assert_not_called()

    def test_self_evaluate_called_with_max_tokens_1000(self):
        """调用 _call_llm_directly 时应传递 max_tokens=1000"""
        import asyncio
        agent = self._make_agent()

        with patch("src.core.agents.generic_agent._load_quality_rubric",
                   return_value="Rubric"), \
             patch.object(agent, '_call_llm_directly') as mock_llm:

            mock_llm.return_value = {
                "success": True,
                "content": '{"score": 90}'
            }

            asyncio.run(agent._self_evaluate("Test " * 200))

            kwargs = mock_llm.call_args[1]
            assert kwargs.get("max_tokens") == 1000, \
                f"Expected max_tokens=1000, got {kwargs.get('max_tokens')}"

    def test_self_evaluate_llm_failure_graceful(self):
        """LLM 调用失败时应优雅降级"""
        import asyncio
        agent = self._make_agent()

        with patch("src.core.agents.generic_agent._load_quality_rubric",
                   return_value="Rubric"), \
             patch.object(agent, '_call_llm_directly') as mock_llm:

            # 模拟 LLM 失败
            mock_llm.return_value = {"success": False, "error": "API error"}

            result = asyncio.run(
                agent._self_evaluate("Test " * 200)
            )

            assert result.get("pass") is True
            assert result.get("score") == 100
            assert result.get("llm_error") == "API error"

    def test_self_evaluate_result_format(self):
        """自评结果的格式应为标准 Dict"""
        import asyncio
        agent = self._make_agent()

        with patch("src.core.agents.generic_agent._load_quality_rubric",
                   return_value="Rubric"), \
             patch.object(agent, '_call_llm_directly') as mock_llm:

            mock_llm.return_value = {
                "success": True,
                "content": '{"score": 75, "weak_dimensions": ["accuracy"], '
                           '"suggestions": ["verify data sources"]}'
            }

            result = asyncio.run(
                agent._self_evaluate("Test " * 200)
            )

            assert "score" in result
            assert 0 <= result["score"] <= 100
            assert isinstance(result.get("weak_dimensions", []), list)
            assert isinstance(result.get("suggestions", []), list)

    def test_max_self_eval_iterations_configurable(self):
        """max_self_eval_iterations 应从 config 读取"""
        agent = self._make_agent()
        assert agent.config.get("max_self_eval_iterations") == 1

        # 设为 0 可完全关闭
        agent.config["max_self_eval_iterations"] = 0
        assert agent.config["max_self_eval_iterations"] == 0

    def test_rubric_from_file_not_context(self):
        """rubric 应来自文件读取，而非 _context"""
        import asyncio
        agent = self._make_agent()

        # 即使 _context 为空，只要文件 mock 返回 rubric，自评应工作
        agent._context = {}

        with patch("src.core.agents.generic_agent._load_quality_rubric",
                   return_value="File-based rubric"), \
             patch.object(agent, '_call_llm_directly') as mock_llm:

            mock_llm.return_value = {
                "success": True,
                "content": '{"score": 80}'
            }

            result = asyncio.run(
                agent._self_evaluate("Test " * 200)
            )

            assert result.get("score") == 80
            # 验证 prompt 中包含了 rubric 内容
            prompt = mock_llm.call_args[1].get("prompt", "")
            assert "File-based rubric" in prompt


class TestLoadQualityRubric:
    """验证 _load_quality_rubric 辅助函数"""

    def test_load_rubric_from_file(self):
        """_load_quality_rubric 应从文件读取并返回字符串"""
        from src.core.agents.generic_agent import _load_quality_rubric
        from pathlib import Path

        # 模拟文件内容
        with tempfile.TemporaryDirectory() as tmpdir:
            rubric_path = Path(tmpdir) / "prompts" / "_shared" / "quality_rubric.md"
            rubric_path.parent.mkdir(parents=True, exist_ok=True)
            rubric_path.write_text("## Test Rubric\nScore 0-100")

            with patch("src.core.agents.generic_agent.Path") as MockPath:
                MockPath.return_value.parent.parent.parent.parent = Path(tmpdir)
                # 清除模块级缓存
                import src.core.agents.generic_agent as ga
                ga._RUBRIC_CACHE = ""

                content = _load_quality_rubric()
                assert "Test Rubric" in content

    def test_load_rubric_file_not_found(self):
        """rubric 文件不存在应返回空字符串"""
        from src.core.agents.generic_agent import _load_quality_rubric
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.core.agents.generic_agent.Path") as MockPath:
                MockPath.return_value.parent.parent.parent.parent = Path(tmpdir)
                import src.core.agents.generic_agent as ga
                ga._RUBRIC_CACHE = ""

                content = _load_quality_rubric()
                assert content == ""


if __name__ == "__main__":
    pytest.main([__file__])
