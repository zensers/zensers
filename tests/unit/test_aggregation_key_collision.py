"""
验证聚合 key 碰撞 BUG：所有 phase_1_agent_N 的 agent_id 被映射到同一 key

agent_id = "phase_1_agent_0"
  → parts = ["phase", "1", "agent", "0"]
  → parts[1:-1] = ["1", "agent"]
  → key = "1_agent"   ← 所有 8 个 agent 都是同一个 key！

结果：dict[key] = result 逐个覆盖，只保留最后一个，其余 7 个 agent 内容丢失
"""
import pytest


def old_aggregation_key_mapping(agent_id, stage_name="batch_1", index=0):
    """orchestrator.py 中原版的 agent_id → key 映射逻辑"""
    aspect = None
    if agent_id:
        parts = agent_id.split("_")
        if len(parts) >= 3:
            last_part = parts[-1]
            is_index = last_part.isdigit() or (
                len(last_part) >= 6
                and all(c in '0123456789abcdef' for c in last_part.lower())
            )
            if is_index:
                aspect = "_".join(parts[1:-1])
            else:
                aspect = last_part
        elif len(parts) == 2:
            aspect = parts[1]
    return aspect if aspect else f"{stage_name}_{index}"


class TestAggregationKeyCollision:
    """验证旧格式 agent_id 导致 key 碰撞"""

    def test_phase_agent_format_all_collide(self):
        """
        P0: 新格式 phase_1_agent_N 全部映射到同一个 key "1_agent"
        
        8 个 agent 执行成功，但聚合器只看到 1 个结果 → 7 章节降级占位
        """
        agent_ids = [f"phase_1_agent_{i}" for i in range(8)]
        keys = [old_aggregation_key_mapping(aid) for aid in agent_ids]

        # BUG：所有 key 都相同！
        unique_keys = set(keys)
        assert len(unique_keys) == 1, \
            f"BUG: 8 个 agent 产生 {len(unique_keys)} 个唯一 key，应有 8 个不同的 key"
        assert unique_keys == {"1_agent"}, \
            f"所有 key 都是 '1_agent'，7 个结果被覆盖丢失"

    def test_old_format_produces_unique_keys(self):
        """
        旧格式 research_市场规模_2 每个都唯一（因中间的章节名不同）
        """
        old_ids = ["research_核心财务指标_0", "research_研发投入_1",
                   "research_供应链_2", "research_销量_3"]
        keys = [old_aggregation_key_mapping(aid) for aid in old_ids]

        unique_keys = set(keys)
        assert len(unique_keys) == 4, \
            f"旧格式应有 4 个唯一 key，实际 {len(unique_keys)}"
        assert "核心财务指标" in unique_keys
        assert "研发投入" in unique_keys
        assert "供应链" in unique_keys

    def test_simulate_aggregation_result_loss(self):
        """
        模拟完整的聚合流程：8 个 agent 结果 → 聚合 dict
        
        原版逻辑：8 个结果只有 1 个存活
        期望行为：8 个结果全部存活
        """
        agent_ids = [f"phase_1_agent_{i}" for i in range(8)]
        stage_results = [
            {"agent_id": aid, "content": f"这是第{i}个agent的分析内容",
             "success": True}
            for i, aid in enumerate(agent_ids)
        ]

        # 模拟 orchestrator 的聚合 key 映射
        results_for_aggregation = {}
        for i, result in enumerate(stage_results):
            agent_id = result.get("agent_id", "")
            # 旧版 key 映射
            key = old_aggregation_key_mapping(agent_id, "batch_1", i)
            results_for_aggregation[key] = result

        # BUG：只有 1 条结果存活
        assert len(results_for_aggregation) == 1, \
            f"BUG: 应该看到 8 条结果，但只存活了 {len(results_for_aggregation)} 条"
        # 内容是被覆盖后最后一个 agent 的内容
        assert "agent_7" in list(results_for_aggregation.values())[0]["agent_id"], \
            "只剩下最后一个 agent (agent_7) 的内容"

    def test_section_id_as_key_produces_unique_keys(self):
        """
        验证修复方案：用 section_id 做 key 则每个都唯一
        
        section_id 格式: section_0_核心财务指标, section_1_研发投入, ...
        """
        section_ids = [
            "section_0_核心财务指标与盈利能力",
            "section_1_研发与创新投入",
            "section_2_供应链成本效率",
            "section_3_销量与市场份额",
            "section_4_国际化与出口",
            "section_5_财务健康_风险评估与季度业绩波动",
            "section_6_行业对标与竞争格局",
            "section_7_财务预测",
        ]

        # 修复后逻辑：直接使用 section_id 作为 key
        unique_keys = set(section_ids)
        fixed_results = {sid: f"内容_{i}" for i, sid in enumerate(section_ids)}

        assert len(unique_keys) == 8, \
            f"section_id 应有 8 个唯一 key，实际 {len(unique_keys)}"
        assert len(fixed_results) == 8, \
            f"修复后应保留全部 8 条结果，实际 {len(fixed_results)}"

    def test_fix_contract_old_ids_still_work(self):
        """
        修复不能破坏旧格式：research_市场规模_2 仍应正确映射
        """
        old_ids = ["research_核心财务指标_0", "research_研发投入_1",
                   "research_供应链_2", "research_销量_3"]
        # 模拟修复后：优先用 section_id，没有则 fallback 到旧解析
        keys = []
        for aid in old_ids:
            # 没有 section_id 时使用旧解析
            key = old_aggregation_key_mapping(aid)
            keys.append(key)

        unique_keys = set(keys)
        assert len(unique_keys) == 4, \
            f"旧格式兼容性被破坏：应有 4 个唯一 key，实际 {len(unique_keys)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
