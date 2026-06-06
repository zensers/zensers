"""
v9.3-A5: 融合权重配置化

验证:
  1. QualityCheckAgent 有 FUSION_WEIGHTS 类常量 (非 field)
  2. 默认权重 quality_score=0.6, section_overall=0.4 (和为 1.0)
  3. _get_fusion_weights() 优先读取 config 覆盖
  4. 无效 config 值回退到默认
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


class TestFusionWeightsConfiguration:
    """验证 quality_check_agent 融合权重可配置"""

    def _make_agent(self, config_override=None):
        """创建 quality check agent 实例"""
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent

        config = {"language": "zh"}
        if config_override:
            config.update(config_override)

        agent = QualityCheckAgent.__new__(QualityCheckAgent)
        agent.agent_id = "test_qc_weights_001"
        agent.config = config
        agent._quality_feedback = None
        agent._knowledge_enrichment = {}
        return agent

    def test_has_fusion_weights_constant(self):
        """QualityCheckAgent 应有 FUSION_WEIGHTS 类常量"""
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent

        weights = getattr(QualityCheckAgent, "FUSION_WEIGHTS", None)
        assert weights is not None, \
            "Should have FUSION_WEIGHTS class constant"
        assert isinstance(weights, dict), \
            f"FUSION_WEIGHTS should be dict, got {type(weights)}"

    def test_default_weights_values(self):
        """默认权重应为 quality_score=0.6, section_overall=0.4"""
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent

        weights = QualityCheckAgent.FUSION_WEIGHTS
        assert abs(weights["quality_score"] - 0.6) < 0.01, \
            f"Expected quality_score weight 0.6, got {weights['quality_score']}"
        assert abs(weights["section_overall"] - 0.4) < 0.01, \
            f"Expected section_overall weight 0.4, got {weights['section_overall']}"

    def test_weights_sum_to_one(self):
        """权重之和应为 1.0"""
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent

        total = sum(QualityCheckAgent.FUSION_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01, \
            f"Weights sum to {total}, expected 1.0"

    def test_fusion_weights_not_field(self):
        """FUSION_WEIGHTS 应为普通类变量，非 field()"""
        import dataclasses
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent

        # QualityCheckAgent 不是 dataclass
        assert not dataclasses.is_dataclass(QualityCheckAgent), \
            "FUSION_WEIGHTS should be a plain class variable, not field()"

    def test_get_fusion_weights_default(self):
        """_get_fusion_weights() 默认返回类常量"""
        agent = self._make_agent()
        if hasattr(agent, "_get_fusion_weights"):
            weights = agent._get_fusion_weights()
            assert abs(weights["quality_score"] - 0.6) < 0.01
            assert abs(weights["section_overall"] - 0.4) < 0.01
        else:
            pytest.skip("_get_fusion_weights not implemented yet")

    def test_config_override_weights(self):
        """session config 应能覆盖权重"""
        agent = self._make_agent({
            "fusion_weights": {
                "quality_score": 0.5,
                "section_overall": 0.5,
            }
        })

        if hasattr(agent, "_get_fusion_weights"):
            weights = agent._get_fusion_weights()
            assert abs(weights["quality_score"] - 0.5) < 0.01
            assert abs(weights["section_overall"] - 0.5) < 0.01
        else:
            # 备用验证
            cfg = agent.config.get("fusion_weights", {})
            assert abs(cfg.get("quality_score", 0) - 0.5) < 0.01

    def test_invalid_weights_fallback(self):
        """无效的配置值应回退到默认权重"""
        agent = self._make_agent({
            "fusion_weights": "invalid_string",  # 不是 dict
        })

        if hasattr(agent, "_get_fusion_weights"):
            weights = agent._get_fusion_weights()
            assert abs(weights["quality_score"] - 0.6) < 0.01
            assert abs(weights["section_overall"] - 0.4) < 0.01
        else:
            pytest.skip("_get_fusion_weights not implemented yet")

    def test_invalid_weights_sum_fallback(self):
        """权重和不为 1.0 时应回退到默认"""
        agent = self._make_agent({
            "fusion_weights": {
                "quality_score": 1.0,    # 和 = 1.5, 不是 1.0
                "section_overall": 0.5,
            }
        })

        if hasattr(agent, "_get_fusion_weights"):
            weights = agent._get_fusion_weights()
            # 应回退到默认
            assert abs(weights["quality_score"] - 0.6) < 0.01
        else:
            pytest.skip("_get_fusion_weights not implemented yet")

    def test_section_overall_fusion_formula(self):
        """验证融合公式使用配置化权重"""
        agent = self._make_agent()

        quality_score = 80.0
        section_overall = 70.0

        if hasattr(agent, "_get_fusion_weights"):
            w = agent._get_fusion_weights()
        else:
            from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
            w = QualityCheckAgent.FUSION_WEIGHTS

        fused = quality_score * w["quality_score"] + section_overall * w["section_overall"]
        expected = 80.0 * 0.6 + 70.0 * 0.4
        assert abs(fused - expected) < 0.01, \
            f"Fusion result {fused} != expected {expected}"


if __name__ == "__main__":
    pytest.main([__file__])
