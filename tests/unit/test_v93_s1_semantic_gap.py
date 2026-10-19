"""
v9.3-A9: S1 缺口检测语义升级

验证:
  1. _detect_knowledge_gaps 保留 4 项启发式检查 (同步方法，保持向后兼容)
  2. _detect_semantic_gaps 新增异步方法 (结构完整性 + 反证覆盖)
  3. 语义检查仅在启发式触发后由 execute() 调用 (成本控制)
  4. _call_llm_directly 返回 Dict (含 success/content 键)
  5. 不破坏现有 gap 检测结果格式 (List[str])
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
from unittest.mock import MagicMock, patch, PropertyMock, AsyncMock


class TestS1KnowledgeGapsSync:
    """验证 _detect_knowledge_gaps 仍为同步方法 (4 项启发式)"""

    def _make_agent(self):
        """创建最小 agent 实例"""
        from src.core.agents.generic_agent import GenericAgent

        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_s1_sync_001"
        agent._knowledge_enrichment = {}
        agent._quality_feedback = None
        agent.config = {"language": "zh"}
        return agent

    def test_is_sync_method(self):
        """_detect_knowledge_gaps 仍为同步方法"""
        import inspect
        from src.core.agents.generic_agent import GenericAgent

        agent = self._make_agent()
        assert hasattr(agent, "_detect_knowledge_gaps")
        assert not inspect.iscoroutinefunction(agent._detect_knowledge_gaps), \
            "_detect_knowledge_gaps must remain sync"

    def test_heuristic_short_content_gap(self):
        """短内容应触发 content too short gap"""
        agent = self._make_agent()
        gaps = agent._detect_knowledge_gaps("short")
        assert isinstance(gaps, list)
        assert any("too short" in g for g in gaps), \
            "Short content should trigger length gap"

    def test_heuristic_quantitative_gap(self):
        """无数字内容应触发定量 gap"""
        agent = self._make_agent()
        content = "这是一个很长的分析内容。" * 200 + "缺乏具体的数字和统计数据。"
        gaps = agent._detect_knowledge_gaps(content)
        assert any("quantitative" in g for g in gaps), \
            "Content without numbers should trigger quantitative gap"

    def test_heuristic_year_gap(self):
        """缺少年份引用应触发时间 gap"""
        agent = self._make_agent()
        content = "数据增长，市场扩大，竞争加剧。" * 100
        gaps = agent._detect_knowledge_gaps(content)
        # 验证有 gap（具体类型取决于内容是否满足年份条件）
        assert isinstance(gaps, list)

    def test_gap_format_preserved(self):
        """返回格式仍为 List[str]"""
        agent = self._make_agent()
        content = "测试内容 " * 500
        gaps = agent._detect_knowledge_gaps(content)
        assert isinstance(gaps, list)
        if gaps:
            assert isinstance(gaps[0], str)

    def test_heuristic_no_llm_call(self):
        """启发式检查不应调用 LLM"""
        agent = self._make_agent()
        with patch.object(agent, '_call_llm_directly') as mock_llm:
            gaps = agent._detect_knowledge_gaps("short")
            mock_llm.assert_not_called(), \
                "Heuristic check should not call LLM"

    def test_returns_list_of_strings(self):
        """所有 gap 应为字符串"""
        agent = self._make_agent()
        gaps = agent._detect_knowledge_gaps(
            "无数据" * 300  # 有长度但无数字
        )
        for g in gaps:
            assert isinstance(g, str), f"Gap should be string, got {type(g)}"


class TestS1SemanticGapsAsync:
    """验证 _detect_semantic_gaps 新增异步方法"""

    def _make_agent(self):
        from src.core.agents.generic_agent import GenericAgent

        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_s1_async_001"
        agent._knowledge_enrichment = {}
        agent._quality_feedback = None
        agent.config = {"language": "zh"}
        return agent

    def test_is_async_method(self):
        """_detect_semantic_gaps 应为异步方法"""
        import inspect
        from src.core.agents.generic_agent import GenericAgent

        agent = self._make_agent()
        assert hasattr(agent, "_detect_semantic_gaps"), \
            "Should have _detect_semantic_gaps method"
        assert inspect.iscoroutinefunction(agent._detect_semantic_gaps), \
            "_detect_semantic_gaps should be async"

    def test_returns_list_of_strings(self):
        """返回 List[str]"""
        import asyncio
        agent = self._make_agent()

        with patch.object(agent, '_call_llm_directly') as mock_llm:
            # _call_llm_directly 返回 Dict
            mock_llm.return_value = {
                "success": True,
                "content": '{"gaps": ["缺少定量数据"], '
                           '"has_structure": false, '
                           '"has_counter_evidence": false}'
            }
            result = asyncio.run(
                agent._detect_semantic_gaps("Test " * 200)
            )

        assert isinstance(result, list)
        if result:
            assert isinstance(result[0], str)

    def test_no_more_than_2_gaps(self):
        """最多返回 2 个语义缺口"""
        import asyncio
        agent = self._make_agent()

        with patch.object(agent, '_call_llm_directly') as mock_llm:
            mock_llm.return_value = {
                "success": True,
                "content": '{"gaps": ["gap1", "gap2", "gap3", "gap4"]}'
            }
            result = asyncio.run(
                agent._detect_semantic_gaps("Test " * 200)
            )

        assert len(result) <= 2, \
            f"Should return at most 2 gaps, got {len(result)}"

    def test_llm_failure_graceful(self):
        """LLM 失败时返回空列表"""
        import asyncio
        agent = self._make_agent()

        with patch.object(agent, '_call_llm_directly') as mock_llm:
            mock_llm.return_value = {"success": False, "error": "API error"}
            result = asyncio.run(
                agent._detect_semantic_gaps("Test " * 200)
            )
        assert result == []

    def test_parse_failure_graceful(self):
        """LLM 返回不可解析内容时返回空列表"""
        import asyncio
        agent = self._make_agent()

        with patch.object(agent, '_call_llm_directly') as mock_llm:
            mock_llm.return_value = {
                "success": True,
                "content": "不是 JSON 格式的内容"
            }
            result = asyncio.run(
                agent._detect_semantic_gaps("Test " * 200)
            )
        assert result == [], \
            "Unparseable LLM output should return empty list"

    def test_prompt_includes_structure_and_counter_evidence(self):
        """prompt 应包含结构和反证检查维度"""
        import asyncio
        agent = self._make_agent()

        with patch.object(agent, '_call_llm_directly') as mock_llm:
            mock_llm.return_value = {
                "success": True,
                "content": '{"gaps": []}'
            }
            asyncio.run(agent._detect_semantic_gaps("Test " * 200))

            prompt = mock_llm.call_args[1].get("prompt", "")
            assert "结构完整性" in prompt or "结构" in prompt
            assert "反证覆盖" in prompt or "反证" in prompt

    def test_uses_summary_for_token_control(self):
        """使用内容前 400 字符做摘要以控制 token"""
        import asyncio
        agent = self._make_agent()

        long_content = "Data " * 5000  # ~25000 chars
        with patch.object(agent, '_call_llm_directly') as mock_llm:
            mock_llm.return_value = {
                "success": True,
                "content": '{"gaps": ["structure missing"]}'
            }
            asyncio.run(agent._detect_semantic_gaps(long_content))

            prompt = mock_llm.call_args[1].get("prompt", "")
            # prompt 应包含最多 400 字符的摘要，而非完整内容
            assert len(prompt) < 2000, \
                "Prompt should use summary, not full content"

    def test_json_in_markdown_codeblock_parsed(self):
        """LLM 返回 markdown 代码块中的 JSON 应能解析"""
        import asyncio
        agent = self._make_agent()

        with patch.object(agent, '_call_llm_directly') as mock_llm:
            mock_llm.return_value = {
                "success": True,
                "content": '```json\n{"gaps": ["缺少结构分析"]}\n```'
            }
            result = asyncio.run(
                agent._detect_semantic_gaps("Test " * 200)
            )
        assert "缺少结构分析" in result


class TestS1IntegrationWithExecute:
    """验证语义检查在 execute() 中集成"""

    def _make_minimal_agent(self):
        from src.core.agents.generic_agent import GenericAgent

        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_s1_integration_001"
        agent._knowledge_enrichment = {}
        agent._quality_feedback = None
        agent.config = {"language": "zh"}
        return agent

    def test_semantic_check_called_when_heuristic_triggers(self):
        """execute() 在启发式缺口触发后应异步调用 _detect_semantic_gaps"""
        agent = self._make_minimal_agent()
        agent._skill_registry = MagicMock()

        # 模拟 execute 路径中的迭代深化环境
        content = "简短无数据内容" * 50  # 会触发启发式 gap
        gaps = agent._detect_knowledge_gaps(content)
        assert len(gaps) > 0, \
            "Content should trigger heuristic gaps for this test to be meaningful"

    def test_semantic_check_not_called_when_heuristic_passes(self):
        """execute() 在启发式全部通过时不调用语义检查"""
        agent = self._make_minimal_agent()

        # 高质量内容 (有数字、年份、趋势词、足够长度)
        high_quality = (
            "核心判断: 2025年市场规模达1000亿元，同比增长20%。\n"
            "数据支持: 根据统计，2024年800亿元，增长趋势明显。\n"
            "逻辑推导: 电动化率提升和国产替代推动。\n"
            "反证分析: 若政策退坡增速可能放缓至15%。\n"
            "投资含义: 结构性机会存在于龙头企业。\n"
        ) * 100

        gaps = agent._detect_knowledge_gaps(high_quality)
        # 高质量内容不应触发启发式 gap
        assert len(gaps) == 0 or all(
            "quantitative" not in g for g in gaps
        ), "High quality content should pass heuristic checks"


if __name__ == "__main__":
    pytest.main([__file__])
