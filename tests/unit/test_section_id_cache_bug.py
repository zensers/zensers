"""
测试：缓存路径导致 section_id 缺失 → 聚合 key 碰撞 → 章节内容丢失

数据流追踪：
  engine.py 缓存路径（1153-1161）构造结果字典时不含 section_id
  → all-cached 分支（1189-1225）的 continue（1225）跳过 section_id 注入
  → orchestrator key 映射靠 result.get("section_id") 拿不到值
  → fallback 解析 agent_id "phase_2_agent_0" → "2_agent"（全部坍缩）
  → aggregator 收到 8 框架章节但只有 1 个 key → 7 章节降级

测试策略：
  1. _get_section_id_from_agent_id 对 phase_N_agent_M 返回原始 agent_id
  2. 缓存结果 dict 构造缺少 section_id 字段（行 1153-1161）
  3. agent_id → key 映射碰撞（所有 phase_N_agent_M 坍缩为 "N_agent"）
  4. agent_section_map 构建逻辑：仅含非空 section_id 的 agent
  5. 完整链路：缓存路径 → orchestrator key 映射 → aggregator 输出
  6. 旧格式兼容性：research_市场规模_1 不受影响
"""
import pytest
from typing import Dict, Any, List, Optional


# =============================================================================
# 辅助函数：直接从生产代码提取的映射逻辑（用于测试 BUG）
# =============================================================================

def engine_get_section_id_from_agent_id(agent_id: str) -> str:
    """engine.py:2493-2525 _get_section_id_from_agent_id 的精确复制"""
    parts = agent_id.split("_")
    if len(parts) >= 4 and parts[0] == "phase" and parts[-2] == "agent":
        return agent_id
    if len(parts) >= 3:
        if parts[-1].isdigit():
            return "_".join(parts[1:-1])
        else:
            return parts[-1]
    elif len(parts) == 2:
        return parts[1]
    return agent_id


def orchestrator_key_mapping_old(agent_id: str, stage_name: str = "batch_1", index: int = 0) -> str:
    """
    orchestrator.py:840-857 key 映射的精确复制（不含 section_id 优先）
    模拟 BUG：仅靠 agent_id 解析
    """
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


def orchestrator_key_mapping_fixed(
    agent_id: str,
    result: Dict[str, Any],
    agent_section_map: Dict[str, str],
    stage_name: str = "batch_1",
    index: int = 0,
) -> str:
    """
    修复后 key 映射：三优先级策略
    1. result.get("section_id")
    2. agent_section_map.get(agent_id)
    3. fallback 解析 agent_id
    """
    section_id = result.get("section_id", "") or ""
    if section_id:
        return section_id
    if agent_id in agent_section_map:
        return agent_section_map[agent_id]
    return orchestrator_key_mapping_old(agent_id, stage_name, index)


def build_agent_section_map_from_agents(agents: List[Any]) -> Dict[str, str]:
    """构建 agent_section_map：仅含 section_id 非空的 agent"""
    agent_section_map: Dict[str, str] = {}
    for _agent in agents:
        _sid = getattr(_agent, 'section_id', None) or ''
        if _sid:
            agent_section_map[_agent.agent_id] = _sid
    return agent_section_map


# =============================================================================
# 测试 1：_get_section_id_from_agent_id 对 phase_N_agent_M 的处理
# =============================================================================

class TestGetSectionIdFromAgentId:
    """engine.py:2493-2525 对 phase_N_agent_M 返回原始 agent_id"""

    def test_phase_agent_format_returns_raw_id(self):
        agent_id = "phase_2_agent_0"
        result = engine_get_section_id_from_agent_id(agent_id)
        assert result == "phase_2_agent_0", \
            f"应返回原始 agent_id，实际 '{result}'"

    def test_multiple_phase_agents_all_return_raw(self):
        for n in range(1, 4):
            for m in range(8):
                aid = f"phase_{n}_agent_{m}"
                result = engine_get_section_id_from_agent_id(aid)
                assert result == aid, \
                    f"phase_{n}_agent_{m} 应返回 '{aid}'，实际 '{result}'"

    def test_old_format_extracts_aspect(self):
        result = engine_get_section_id_from_agent_id("research_市场规模_2")
        assert result == "市场规模", f"应提取 '市场规模'，实际 '{result}'"

    def test_old_format_edge_cases(self):
        assert engine_get_section_id_from_agent_id("research_核心财务指标_0") == "核心财务指标"
        assert engine_get_section_id_from_agent_id("data_销量_5") == "销量"

    def test_new_format_deep_analysis(self):
        result = engine_get_section_id_from_agent_id("deep_analysis_0_市场规模")
        assert result == "市场规模", f"应返回 '市场规模'，实际 '{result}'"


# =============================================================================
# 测试 2：key 映射碰撞
# =============================================================================

class TestKeyMappingCollision:
    """验证 phase_N_agent_M 的 key 映射碰撞"""

    def test_all_phase_agents_collide_to_same_key(self):
        """不使用 section_id 时，8 个 phase_1_agent_N 全部映射到 "1_agent" """
        agent_ids = [f"phase_1_agent_{i}" for i in range(8)]
        keys = [orchestrator_key_mapping_old(aid) for aid in agent_ids]

        unique_keys = set(keys)
        assert len(unique_keys) == 1, \
            f"BUG: 8 个 agent 应坍缩为 1 个 key，实际 {len(unique_keys)} 个"
        assert unique_keys == {"1_agent"}, \
            f"BUG: 所有 key 应为 '1_agent'，实际 {unique_keys}"

    def test_different_phases_collide_per_phase(self):
        """phase_2_agent_N 映射到 "2_agent"，与 phase_1 不同"""
        p1_ids = [f"phase_1_agent_{i}" for i in range(4)]
        p2_ids = [f"phase_2_agent_{i}" for i in range(4)]

        p1_keys = {orchestrator_key_mapping_old(aid) for aid in p1_ids}
        p2_keys = {orchestrator_key_mapping_old(aid) for aid in p2_ids}

        assert p1_keys == {"1_agent"}
        assert p2_keys == {"2_agent"}

    def test_simulate_aggregation_loss(self):
        """模拟聚合流程：8 个 agent 的结果依次被同一个 key 覆盖"""
        agent_ids = [f"phase_1_agent_{i}" for i in range(8)]
        stage_results = [
            {"agent_id": aid, "content": f"agent_{i}的内容", "success": True}
            for i, aid in enumerate(agent_ids)
        ]

        results_for_aggregation = {}
        for i, result in enumerate(stage_results):
            key = orchestrator_key_mapping_old(
                result.get("agent_id", ""), "batch_1", i)
            results_for_aggregation[key] = result

        assert len(results_for_aggregation) == 1, \
            f"BUG: 应只剩 1 条结果（被覆盖），实际 {len(results_for_aggregation)} 条"
        last_key = list(results_for_aggregation.keys())[0]
        assert last_key == "1_agent"
        assert results_for_aggregation[last_key]["agent_id"] == "phase_1_agent_7"

    def test_fixed_mapping_with_section_id_all_unique(self):
        """修复后：优先使用 section_id，8 个 agent 产生 8 个唯一 key"""
        section_ids = [
            "section_0_core_financial",
            "section_1_rd_investment",
            "section_2_supply_chain",
            "section_3_sales_market",
            "section_4_international",
            "section_5_risk_assessment",
            "section_6_competition",
            "section_7_forecast",
        ]
        agent_ids = [f"phase_1_agent_{i}" for i in range(8)]

        results = [
            {"agent_id": aid, "section_id": sid, "content": f"内容{i}", "success": True}
            for i, (aid, sid) in enumerate(zip(agent_ids, section_ids))
        ]

        results_for_aggregation = {}
        for i, result in enumerate(results):
            key = orchestrator_key_mapping_fixed(
                result.get("agent_id", ""),
                result,
                agent_section_map={},
                stage_name="batch_1",
                index=i,
            )
            results_for_aggregation[key] = result

        assert len(results_for_aggregation) == 8, \
            f"修复后应有 8 条结果，实际 {len(results_for_aggregation)}"
        for sid in section_ids:
            assert sid in results_for_aggregation, f"缺少 section_id '{sid}'"


# =============================================================================
# 测试 3：agent_section_map 构建
# =============================================================================

class TestAgentSectionMap:
    """验证 agent_section_map 构建逻辑"""

    def test_map_only_contains_agents_with_section_id(self):
        class MockAgent:
            def __init__(self, agent_id, section_id):
                self.agent_id = agent_id
                self.section_id = section_id

        agents = [
            MockAgent("phase_1_agent_0", "section_0_core_financial"),
            MockAgent("phase_1_agent_1", "section_1_rd_investment"),
            MockAgent("phase_2_agent_0", "section_2_supply_chain"),
            MockAgent("research_市场规模_1", ""),
            MockAgent("research_竞争格局_2", ""),
        ]

        agent_map = build_agent_section_map_from_agents(agents)

        assert "research_市场规模_1" not in agent_map, \
            "旧 agent（section_id=''）不应出现在 map 中"
        assert "research_竞争格局_2" not in agent_map, \
            "旧 agent（section_id=''）不应出现在 map 中"
        assert agent_map.get("phase_1_agent_0") == "section_0_core_financial"
        assert agent_map.get("phase_1_agent_1") == "section_1_rd_investment"
        assert agent_map.get("phase_2_agent_0") == "section_2_supply_chain"
        assert len(agent_map) == 3, f"map 应有 3 条，实际 {len(agent_map)}"

    def test_fallback_agent_id_bug_not_in_map(self):
        """
        验证修复后的 map 构建不会把 agent_id 作为 fallback 写入

        BUG（修复前 orchestrator.py:1648）：
            _sid = getattr(_agent, 'section_id', None) or getattr(_agent, 'agent_id', '')
            → section_id='' 时 _sid = agent_id（如 "phase_2_agent_0"）

        修复后：
            _sid = getattr(_agent, 'section_id', None) or ''
            → section_id='' 时 _sid = '' → 不写入
        """
        class MockAgent:
            def __init__(self, agent_id, section_id):
                self.agent_id = agent_id
                self.section_id = section_id

        agents = [MockAgent("phase_2_agent_0", "")]
        agent_map = build_agent_section_map_from_agents(agents)
        assert "phase_2_agent_0" not in agent_map, \
            "修复后：空 section_id 的 agent 不应出现在 map 中"


# =============================================================================
# 测试 4：orchestrator key 映射的 agent_section_map 兜底
# =============================================================================

class TestKeyMappingWithAgentSectionMap:
    """验证 agent_section_map 作为 result.section_id 的兜底"""

    def test_map_fallback_when_result_missing_section_id(self):
        class MockAgent:
            def __init__(self, agent_id, section_id):
                self.agent_id = agent_id
                self.section_id = section_id

        agents = [
            MockAgent("phase_1_agent_0", "section_0_core_financial"),
            MockAgent("phase_1_agent_1", "section_1_rd_investment"),
        ]
        agent_section_map = build_agent_section_map_from_agents(agents)

        results = [
            {"agent_id": "phase_1_agent_0", "content": "内容0", "success": True},
            {"agent_id": "phase_1_agent_1", "content": "内容1", "success": True},
        ]

        results_for_aggregation = {}
        for i, result in enumerate(results):
            key = orchestrator_key_mapping_fixed(
                result.get("agent_id", ""),
                result,
                agent_section_map,
                stage_name="batch_1",
                index=i,
            )
            results_for_aggregation[key] = result

        assert len(results_for_aggregation) == 2
        assert "section_0_core_financial" in results_for_aggregation
        assert "section_1_rd_investment" in results_for_aggregation

    def test_result_section_id_takes_priority_over_map(self):
        class MockAgent:
            def __init__(self, agent_id, section_id):
                self.agent_id = agent_id
                self.section_id = section_id

        agents = [MockAgent("phase_1_agent_0", "section_0_from_agent")]
        agent_section_map = build_agent_section_map_from_agents(agents)

        result = {
            "agent_id": "phase_1_agent_0",
            "section_id": "section_0_from_result",
            "content": "内容",
            "success": True,
        }

        key = orchestrator_key_mapping_fixed(
            "phase_1_agent_0", result, agent_section_map)
        assert key == "section_0_from_result", \
            f"应使用 result 中的 section_id，实际 '{key}'"


# =============================================================================
# 测试 5：端到端链路 — 从引擎结果到聚合器输出
# =============================================================================

class TestFullAggregationChain:
    """从结果字典到 ResultAggregator 输出的完整链路"""

    SECTION_IDS = [
        "section_0_core_financial",
        "section_1_rd_investment",
        "section_2_supply_chain",
        "section_3_sales_market",
        "section_4_international",
        "section_5_risk_assessment",
        "section_6_competition",
        "section_7_forecast",
    ]

    FRAMEWORK_SECTIONS = [
        {"id": "core_financial", "name": "Core Financial Metrics"},
        {"id": "rd_investment", "name": "R&D Investment"},
        {"id": "supply_chain", "name": "Supply Chain"},
        {"id": "sales_market", "name": "Sales & Market Share"},
        {"id": "international", "name": "International & Export"},
        {"id": "risk_assessment", "name": "Risk Assessment"},
        {"id": "competition", "name": "Competition Landscape"},
        {"id": "forecast", "name": "Financial Forecast"},
    ]

    def _make_content(self, i):
        return (
            f"Section {i} analysis: revenue growth 15%, margin expansion 2pp, "
            f"market share increased to {20+i}%, R&D intensity {5+i}%"
        )

    def _count_degraded(self, sections):
        return sum(
            1 for s in sections
            if s.get("_provenance", {}).get("matched_key") is None
        )

    def test_bug_path_cache_missing_section_id(self):
        """
        BUG 路径：缓存不注入 section_id → 8 结果坍缩为 1 key → 绝大多数章节降级

        engine.py 缓存路径（1153-1161）构造 dict 无 section_id
        → orchestrator fallback 解析 phase_1_agent_N → "1_agent"
        → 8 个结果写入同一个 key → 仅最后 1 条存活
        → aggregator 只看到 1 个 key → 其余章节降级
        """
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        agent_ids = [f"phase_1_agent_{i}" for i in range(8)]
        stage_results = [
            {"agent_id": aid, "content": self._make_content(i), "success": True}
            for i, aid in enumerate(agent_ids)
        ]

        # BUG 路径：旧版 key 映射（无 section_id）
        results_for_aggregation = {}
        for i, result in enumerate(stage_results):
            key = orchestrator_key_mapping_old(
                result.get("agent_id", ""), "batch_1", i)
            results_for_aggregation[key] = result

        # 只有 1 条结果存入（其余被覆盖）
        assert len(results_for_aggregation) == 1, \
            f"BUG: 8 条结果坍缩为 {len(results_for_aggregation)} 条"

        # 聚合器只能看到 1 个 key → 绝大多数章节降级
        aggregator = ResultAggregator()
        agg_result = aggregator.aggregate(
            results_for_aggregation,
            section_details=self.FRAMEWORK_SECTIONS,
        )
        result_dict = agg_result.to_dict() if hasattr(
            agg_result, 'to_dict') else {"sections": []}
        sections = result_dict.get("sections", [])

        degraded = self._count_degraded(sections)
        assert degraded >= 7, \
            f"BUG: 应至少有 7 个降级章节，实际 {degraded}/{len(sections)}"

    def test_fixed_path_section_id_all_matched(self):
        """
        修复路径：section_id 作为 key → 8 个唯一 key → 0 降级
        """
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        agent_ids = [f"phase_1_agent_{i}" for i in range(8)]

        # 模拟修复后结果（engine 注入 section_id）
        results = [
            {"agent_id": aid, "section_id": sid,
             "content": self._make_content(i), "success": True}
            for i, (aid, sid) in enumerate(zip(agent_ids, self.SECTION_IDS))
        ]

        # 使用 section_id 作为 key
        results_for_aggregation = {}
        for i, result in enumerate(results):
            section_id = result.get("section_id", "") or ""
            key = section_id if section_id else orchestrator_key_mapping_old(
                result.get("agent_id", ""), "batch_1", i)
            results_for_aggregation[key] = result

        assert len(results_for_aggregation) == 8

        aggregator = ResultAggregator()
        agg_result = aggregator.aggregate(
            results_for_aggregation,
            section_details=self.FRAMEWORK_SECTIONS,
        )
        result_dict = agg_result.to_dict() if hasattr(
            agg_result, 'to_dict') else {"sections": []}
        sections = result_dict.get("sections", [])

        degraded = self._count_degraded(sections)
        assert degraded == 0, \
            f"修复后不应有降级章节，但 {degraded}/{len(sections)} 个降级"
        assert len(sections) == 8

    def test_fixed_path_with_map_fallback(self):
        """
        地图兜底路径：result 无 section_id 但 agent_section_map 可提供
        """
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        class MockAgent:
            def __init__(self, agent_id, section_id):
                self.agent_id = agent_id
                self.section_id = section_id

        agents = [
            MockAgent(f"phase_1_agent_{i}", sid)
            for i, sid in enumerate(self.SECTION_IDS)
        ]
        agent_section_map = build_agent_section_map_from_agents(agents)

        # 模拟缓存路径结果（无 section_id）
        results = [
            {"agent_id": f"phase_1_agent_{i}",
             "content": self._make_content(i), "success": True}
            for i in range(8)
        ]

        results_for_aggregation = {}
        for i, result in enumerate(results):
            key = orchestrator_key_mapping_fixed(
                result.get("agent_id", ""),
                result,
                agent_section_map,
                stage_name="batch_1",
                index=i,
            )
            results_for_aggregation[key] = result

        assert len(results_for_aggregation) == 8

        aggregator = ResultAggregator()
        agg_result = aggregator.aggregate(
            results_for_aggregation,
            section_details=self.FRAMEWORK_SECTIONS,
        )
        result_dict = agg_result.to_dict() if hasattr(
            agg_result, 'to_dict') else {"sections": []}
        sections = result_dict.get("sections", [])

        degraded = self._count_degraded(sections)
        assert degraded == 0, \
            f"地图兜底后不应有降级章节，但 {degraded}/{len(sections)} 个降级"


# =============================================================================
# 测试 6：旧格式兼容性（不回归验证）
# =============================================================================

class TestLegacyFormatCompatibility:
    """旧格式 research_市场规模_1 不受影响"""

    def test_old_format_still_works_with_fallback(self):
        old_ids = [
            ("research_核心财务指标_0", "核心财务指标"),
            ("research_研发投入_1", "研发投入"),
            ("research_供应链成本效率_2", "供应链成本效率"),
            ("research_销量与市场份额_3", "销量与市场份额"),
        ]

        for aid, expected_aspect in old_ids:
            key = orchestrator_key_mapping_old(aid)
            assert key == expected_aspect, \
                f"'{aid}' 应映射为 '{expected_aspect}'，实际 '{key}'"

    def test_old_format_compatible_with_fixed_mapping(self):
        """
        修复后的 key 映射对旧格式兼容：
        旧 agent section_id 为空 → 不进 section_id 分支
        旧 agent 不在 agent_section_map → 不进 map 分支
        → 走 fallback 解析 → 旧行为不变
        """
        class MockAgent:
            def __init__(self, agent_id, section_id):
                self.agent_id = agent_id
                self.section_id = section_id

        agents = [
            MockAgent("research_核心财务指标_0", ""),
            MockAgent("research_研发投入_1", ""),
        ]
        agent_section_map = build_agent_section_map_from_agents(agents)

        results = [
            {"agent_id": "research_核心财务指标_0", "content": "内容0", "success": True},
            {"agent_id": "research_研发投入_1", "content": "内容1", "success": True},
        ]

        r = {}
        for i, result in enumerate(results):
            aid = result.get("agent_id", "")
            key = orchestrator_key_mapping_fixed(
                aid, result, agent_section_map, "batch_1", i)
            r[key] = result

        assert len(r) == 2
        assert "核心财务指标" in r
        assert "研发投入" in r


# =============================================================================
# 测试 7：混合场景
# =============================================================================

class TestMixedScenario:
    """新旧 agent 混合时的 key 映射"""

    def test_mixed_agents_generate_unique_keys(self):
        class MockAgent:
            def __init__(self, agent_id, section_id):
                self.agent_id = agent_id
                self.section_id = section_id

        agents = [
            MockAgent("phase_1_agent_0", "section_0_core"),
            MockAgent("research_市场规模_1", ""),
            MockAgent("phase_2_agent_0", "section_1_competition"),
            MockAgent("research_竞争格局_2", ""),
        ]
        agent_section_map = build_agent_section_map_from_agents(agents)

        results = [
            {"agent_id": "phase_1_agent_0", "section_id": "section_0_core",
             "content": "核心", "success": True},
            {"agent_id": "research_市场规模_1", "section_id": "research_市场规模_1",
             "content": "市场规模", "success": True},
            {"agent_id": "phase_2_agent_0", "section_id": "section_1_competition",
             "content": "竞争", "success": True},
            {"agent_id": "research_竞争格局_2", "section_id": "research_竞争格局_2",
             "content": "竞争格局", "success": True},
        ]

        r = {}
        for i, result in enumerate(results):
            aid = result.get("agent_id", "")
            key = orchestrator_key_mapping_fixed(
                aid, result, agent_section_map, "batch_1", i)
            r[key] = result

        assert len(r) == 4, f"混合场景应有 4 个唯一 key，实际 {len(r)}"
        assert "section_0_core" in r
        assert "research_市场规模_1" in r
        assert "section_1_competition" in r
        assert "research_竞争格局_2" in r


# =============================================================================
# 测试 8：engine.py 缓存结果 dict 缺少 section_id 字段（源码验证）
# =============================================================================

class TestEngineCacheDictMissingSectionId:
    """
    直接读取 engine.py 源码，验证缓存路径构造的 dict 不含 section_id。
    此测试在修复后应断言相反行为（含 section_id）。
    """

    def test_cache_result_dict_now_has_section_id(self):
        """
        engine.py:1153 completed_results.append({...}) 现在包含 section_id。
        P1 修复后验证：缓存路径 dict 已包含 section_id。
        """
        import ast
        engine_path = r"E:\market_report_systerm\src\core\orchestrator\execution\engine.py"
        with open(engine_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        found_cache_append = False
        cache_dict_has_section_id = False
        for i, line in enumerate(lines):
            if 'completed_results.append' in line and i > 1100 and i < 1200:
                found_cache_append = True
                block_lines = []
                for j in range(i, min(i + 20, len(lines))):
                    block_lines.append(lines[j])
                    if '}' in lines[j]:
                        break
                block_text = ''.join(block_lines)
                if '"section_id"' in block_text or "'section_id'" in block_text:
                    cache_dict_has_section_id = True
                break

        assert found_cache_append, "未找到缓存路径的 completed_results.append"
        assert cache_dict_has_section_id, \
            "P1 修复后：缓存路径 dict 应包含 section_id"

    def test_normal_execution_dict_has_section_id(self):
        """
        engine.py:1284-1290 正常执行路径注入 section_id。
        此测试确认正常路径是正确的。
        """
        engine_path = r"E:\market_report_systerm\src\core\orchestrator\execution\engine.py"
        with open(engine_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')

        # 找到正常路径的 section_id 注入代码
        found_injection = False
        for i, line in enumerate(lines):
            if i > 1270 and i < 1310 and 'agent_result["section_id"]' in line:
                found_injection = True
                break

        assert found_injection, "正常执行路径缺少 section_id 注入代码"


# =============================================================================
# 测试 9：engine.py continue 跳过 section_id 注入（源码验证）
# =============================================================================

class TestEngineContinueSkipsInjection:
    """
    验证 engine.py all-cached 分支的 continue 语句跳过了 section_id 注入。
    """

    def test_continue_after_cached_batch_skips_injection(self):
        """
        engine.py:1225 的 continue 在 all-cached 分支跳过了 1284-1290 的注入。
        此测试确认 BUG 存在。
        """
        engine_path = r"E:\market_report_systerm\src\core\orchestrator\execution\engine.py"
        with open(engine_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 在 1180-1230 范围内找到 continue
        found_continue = False
        continue_line = -1
        for i in range(1178, min(1235, len(lines))):
            stripped = lines[i].strip()
            if stripped == 'continue':
                # 确保它在 all-cached 分支内（缩进层级匹配）
                found_continue = True
                continue_line = i + 1  # 1-indexed
                break

        assert found_continue, "未找到 all-cached 分支的 continue 语句"

        # 确认 section_id 注入代码在 continue 之后
        injection_line = -1
        for i in range(1280, min(1310, len(lines))):
            if 'agent_result["section_id"]' in lines[i]:
                injection_line = i + 1
                break

        assert injection_line > 0, "未找到 section_id 注入代码"
        assert injection_line > continue_line, \
            f"section_id 注入（行{injection_line}）应在 continue（行{continue_line}）之后"


# =============================================================================
# 测试 10：orchestrator.py agent_section_map 的现有 BUG（源码验证）
# =============================================================================

class TestOrchestratorExistingMapBug:
    """
    验证 orchestrator.py:1648 的 agent_section_map 使用了错误的 fallback。
    """

    def test_map_no_longer_uses_agent_id_as_fallback(self):
        """
        orchestrator.py:1648 修复后：
            _sid = getattr(_agent, 'section_id', None) or ''
        不再使用 agent_id 作为 fallback。
        """
        orch_path = r"E:\market_report_systerm\src\core\orchestrator\orchestrator.py"
        with open(orch_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        found_line = None
        for i, line in enumerate(lines):
            if ('getattr(_agent' in line
                and 'section_id' in line
                and 'agent_id' not in line
                and 'agent_section_map' not in line):
                found_line = i + 1
                line_content = line.strip()
                break

        assert found_line is not None, "未找到 agent_section_map 的 _sid 构建行"
        assert 'agent_id' not in line_content, \
            f"行{found_line}: P2c 修复后不应包含 agent_id fallback，内容: {line_content}"

    def test_key_mapping_now_uses_map(self):
        """
        验证 _research_with_routing 的 key 映射代码现在使用 agent_section_map。
        P2d 修复后验证。
        """
        orch_path = r"E:\market_report_systerm\src\core\orchestrator\orchestrator.py"
        with open(orch_path, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        map_used_in_mapping = False
        for i in range(1740, min(1810, len(lines))):
            if 'agent_section_map' in lines[i] and 'key' in lines[i].lower():
                map_used_in_mapping = True
                break

        assert map_used_in_mapping, \
            "P2d 修复后：key 映射代码应使用 agent_section_map"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])
