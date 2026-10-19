"""
基于真实数据形状的聚合器整合测试

测试用 REAL 数据格式喂入 ResultAggregator，验证内容不被丢失。
所有数据格式直接从生产代码中复制，不简化。
"""
import pytest
from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator


class TestAggregatorRealisticFlow:
    """真实数据流验证"""

    def test_content_found_for_all_real_sections(self):
        """
        核心验证：8 个真实章节的内容全部被聚合器找到
        
        数据格式来源：
          engine 注入 section_id: "section_0_核心财务指标与盈利能力" (从 agent.section_id)
          framework section_details: {"id": "核心财务指标与盈利能力", "name": "核心财务指标与盈利能力"}
        """
        # 模拟 engine 注入的结果（每个 agent 返回自己的内容）
        agent_results = {
            "section_0_核心财务指标与盈利能力": {
                "agent_id": "phase_1_agent_0",
                "content": "2025年比亚迪实现营业收入约7771亿元，同比增长21.04%。归母净利润402.54亿元。毛利率18.81%。",
                "section_id": "section_0_核心财务指标与盈利能力",
                "success": True,
            },
            "section_1_研发与创新投入": {
                "agent_id": "phase_1_agent_1",
                "content": "2025年研发投入约542亿元，同比增长35.16%。研发人员超过10万人。",
                "section_id": "section_1_研发与创新投入",
                "success": True,
            },
            "section_2_供应链成本效率": {
                "agent_id": "phase_1_agent_2",
                "content": "2025年垂直整合率持续提升，核心零部件自制率超过80%。单车成本同比下降约5%。",
                "section_id": "section_2_供应链成本效率",
                "success": True,
            },
            "section_3_销量与市场份额": {
                "agent_id": "phase_1_agent_3",
                "content": "2025年全年新能源汽车销量427.21万辆，同比增长40.87%。国内市占率33.2%。",
                "section_id": "section_3_销量与市场份额",
                "success": True,
            },
            "section_4_国际化与出口": {
                "agent_id": "phase_1_agent_4",
                "content": "2025年比亚迪汽车出口40.85万辆，同比增长58.44%。海外市场收入约1800亿元。",
                "section_id": "section_4_国际化与出口",
                "success": True,
            },
            "section_5_财务健康_风险评估与季度业绩波动": {
                "agent_id": "phase_1_agent_5",
                "content": "2025年末资产负债率70.94%。经营活动现金流净额1869.94亿元。货币资金储备约1200亿元。",
                "section_id": "section_5_财务健康_风险评估与季度业绩波动",
                "success": True,
            },
            "section_6_行业对标与竞争格局": {
                "agent_id": "phase_1_agent_6",
                "content": "2025年比亚迪销量427.21万辆，特斯拉178.46万辆。国内新能源市场份额33.2%。",
                "section_id": "section_6_行业对标与竞争格局",
                "success": True,
            },
            "section_7_财务预测": {
                "agent_id": "phase_1_agent_7",
                "content": "2026年预计营业收入9000-9500亿元。净利润预计550-600亿元。",
                "section_id": "section_7_财务预测",
                "success": True,
            },
        }

        # 模拟 framework 的 section_details（真实格式）
        section_details = [
            {"id": "核心财务指标与盈利能力", "name": "核心财务指标与盈利能力", "content": "核心财务指标与盈利能力"},
            {"id": "研发与创新投入", "name": "研发与创新投入", "content": "研发与创新投入"},
            {"id": "供应链成本效率", "name": "供应链成本效率", "content": "供应链成本效率"},
            {"id": "销量与市场份额", "name": "销量与市场份额", "content": "销量与市场份额"},
            {"id": "国际化与出口", "name": "国际化与出口", "content": "国际化与出口"},
            {"id": "财务健康、风险评估与季度业绩波动", "name": "财务健康、风险评估与季度业绩波动", "content": "财务健康、风险评估与季度业绩波动"},
            {"id": "行业对标与竞争格局", "name": "行业对标与竞争格局", "content": "行业对标与竞争格局"},
            {"id": "财务预测", "name": "财务预测", "content": "财务预测"},
        ]

        aggregator = ResultAggregator()
        result = aggregator.aggregate(agent_results, section_details=section_details)
        result_dict = result.to_dict() if hasattr(result, 'to_dict') else {"sections": []}
        sections = result_dict.get("sections", [])

        # 验证：每个章节都有非空内容
        empty_sections = []
        for s in sections:
            title = s.get("title", "")
            content = s.get("content", "") or ""
            if len(content.strip()) < 20:
                empty_sections.append(title)

        assert len(empty_sections) == 0, \
            f"以下章节内容为空或太短: {empty_sections}"
        assert len(sections) == 8, \
            f"应有 8 个章节，实际 {len(sections)}"

    def test_short_engine_key_long_framework_id_matches(self):
        """
        关键场景验证：engine key 短于 framework section_id 时仍能匹配
        
        真实数据：
          engine key:  "section_5_财务健康_风险评估与季度业绩波动" 
          framework:   "财务健康、风险评估与季度业绩波动"
          
        _normalize_key 移除 prefix 后：
          norm_key = "财务健康_风险评估与季度业绩波动"
          norm_id  = "财务健康_风险评估与季度业绩波动"
          它们应该相等。
        """
        from src.core.orchestrator.aggregation.result_aggregator import _normalize_key

        engine_key = "section_5_财务健康_风险评估与季度业绩波动"
        framework_id = "财务健康、风险评估与季度业绩波动"

        norm_key = _normalize_key(engine_key)
        norm_id = _normalize_key(framework_id)

        # norm_key 和 norm_id 应相等（双向匹配的边界）
        match_forward = norm_id in norm_key
        match_backward = norm_key in norm_id

        assert match_forward or match_backward or norm_key == norm_id, \
            f"归一化后应匹配: norm_key='{norm_key}' norm_id='{norm_id}'"

    def test_normalize_bidirectional_coverage(self):
        """
        验证 3 处归一化匹配逻辑的一致性
        
        真实数据中:
          engine key: "section_0_核心财务指标" (短，prefix移除后为"核心财务指标")
          framework:  "核心财务指标与盈利能力" (长)
          
          norm_key = "核心财务指标"
          norm_id  = "核心财务指标与盈利能力"
          
          norm_id in norm_key  → False (长不在短中) → 旧 BUG
          norm_key in norm_id  → True  (短在长中)  → 需要双向检查
        """
        from src.core.orchestrator.aggregation.result_aggregator import _normalize_key

        # 模拟短 engine key 场景
        engine_key = "section_0_核心财务指标"
        framework_id = "核心财务指标与盈利能力"

        norm_key = _normalize_key(engine_key)
        norm_id = _normalize_key(framework_id)

        assert norm_id not in norm_key, \
            "框架 ID（长）不应在 engine key（短）中——这正是旧 BUG"
        assert norm_key in norm_id, \
            "engine key（短）应在框架 ID（长）中——修复后必须成立"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
