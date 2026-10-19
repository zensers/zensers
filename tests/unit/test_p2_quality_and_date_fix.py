# -*- coding: utf-8 -*-
"""
P2 Fix: 报告质量低/跨章节因果链 + 日期幻觉

测试验证:
- Agent prompt 包含跨章节因果链引导
- Agent prompt 包含更严格的日期约束
- 质量检查 _check_consistency 有语义检查路径

Bug: 分析深度 10-13/25, 逻辑一致性 5-7/15
根因: Agent prompt 只引导聚焦单维度，没引导跨章节因果链推理
"""

import pytest
from unittest.mock import patch, MagicMock


class TestCrossChapterCausalChainInPrompt:
    """Agent prompt 应包含跨章节因果链引导"""

    def test_prompt_contains_causal_chain_guidance(self):
        """_get_professional_role_prompt 应包含跨章节因果链引导（非评分rubric）"""
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_agent"
        agent.agent_type = "research"
        agent.topic = "比亚迪"
        agent._knowledge_enrichment = {}
        agent._quality_feedback = {}

        prompt = agent._get_professional_role_prompt("财务分析")
        has_causal_guidance = (
            "跨章节因果" in prompt
            or "章节间的关联" in prompt
            or "跨维度因果" in prompt
            or "cross-chapter causal" in prompt.lower()
            or "inter-section" in prompt.lower()
            or "其他章节的因果联系" in prompt
        )
        assert has_causal_guidance, "prompt 应包含跨章节因果链分析引导（不只是评分rubric）"


class TestDateConstraintInPrompt:
    """Agent prompt 应包含更严格的日期约束"""

    def test_prompt_contains_date_constraint(self):
        """prompt 应包含不得编造未来确定数据的约束"""
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "test_agent"
        agent.agent_type = "research"
        agent.topic = "比亚迪"
        agent._knowledge_enrichment = {}
        agent._quality_feedback = {}

        prompt = agent._get_professional_role_prompt("财务分析")
        has_date_constraint = (
            "不得编造" in prompt
            or "不要编造" in prompt
            or "不得生成" in prompt
            or "do not fabricate" in prompt.lower()
            or "do not invent" in prompt.lower()
            or "预计" in prompt
        )
        assert has_date_constraint, "prompt 应包含日期约束"


class TestQualityCheckConsistencyImprovement:
    """质量检查 _check_consistency 应有语义检查路径"""

    def test_check_consistency_has_semantic_path(self):
        """_check_consistency 应有语义一致性检查（不只是 billion 数值）"""
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        import inspect
        source = inspect.getsource(QualityCheckAgent._check_consistency)
        has_semantic = (
            "语义" in source
            or "semantic" in source.lower()
            or "跨章节" in source
            or "cross_section" in source.lower()
            or "contradiction" in source.lower()
            or "矛盾" in source
        )
        assert has_semantic, "_check_consistency 应有语义一致性检查路径"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
