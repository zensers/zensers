"""
M0→M5-b 端到端管线测试：覆盖完整 BYD 研报生成数据流。

管线顺序：
  Agent 原始产出 (DC + Analysis)
    → M5-a: fix_content_from_canonical()   (内容校准门)
    → M0:   ResultAggregator.aggregate()   (聚合 + agent_id key 映射)
    → M4:   (内嵌于 aggregate: 跨 agent 数值冲突检测)
    → M5-b: DynamicPhaseOrchestrator       (校准阶段生成)
    → M5-b: 校准结果注入 Report agent       (engine.py task building)

测试数据：BYD 2024 年报多节双阶段产出（2 个 DC + 2 个 Analysis）
"""
from copy import deepcopy

import pytest

# ============================================================
# 场景数据：BYD 2024 研报 — 2 section × 双阶段（DC + Analysis）
# ============================================================

# 金标准数据（来自年报）
# 值设计说明：分析 agent 产出包含 >5% 误差的值，验证校准门能正确修正
BYD_CANONICAL = {
    "营收_2024_CNY": {"value": 6770, "unit": "亿元", "currency": "CNY"},
    "净利润_2024_CNY": {"value": 326.5, "unit": "亿元", "currency": "CNY"},
    "销量_2024_CNY": {"value": 460, "unit": "万辆", "currency": "CNY"},
    "毛利率_2024_CNY": {"value": 22.5, "unit": "%", "currency": "CNY"},
    "研发投入_2024_CNY": {"value": 398, "unit": "亿元", "currency": "CNY"},
}

DC_RESULTS = [
    {
        "agent_id": "phase_1_agent_0",
        "success": True,
        "content": "比亚迪2024年报：营收6770亿元，净利润326.5亿元，毛利率22.5%。",
        "data_points": [
            {"metric": "营收", "value": 6770, "unit": "亿元", "year": 2024},
            {"metric": "净利润", "value": 326.5, "unit": "亿元", "year": 2024},
            {"metric": "毛利率", "value": 22.5, "unit": "%", "year": 2024},
        ],
        "sources": [{"title": "BYD 2024 Annual Report", "url": "https://byd.com/ar2024"}],
        "section_id": "section_0_核心财务指标",
        "category": "research",
    },
    {
        "agent_id": "phase_1_agent_1",
        "success": True,
        "content": "比亚迪2024年全球销量460万辆，同比增35%。",
        "data_points": [
            {"metric": "销量", "value": 460, "unit": "万辆", "year": 2024},
        ],
        "sources": [{"title": "BYD Sales Report", "url": "https://byd.com/sales2024"}],
        "section_id": "section_1_销量分析",
        "category": "research",
    },
]

ANALYSIS_RESULTS = [
    {
        "agent_id": "phase_2_agent_0",
        "success": True,
        "content": (
            "2024年核心财务分析：营收7200亿元（同比+35%），净利润360亿元（同比+28%），"
            "毛利率27.5%，研发投入350亿元。"
        ),
        "data_points": [
            {"metric": "营收", "value": 7200, "unit": "亿元", "year": 2024},
            {"metric": "净利润", "value": 360, "unit": "亿元", "year": 2024},
            {"metric": "毛利率", "value": 27.5, "unit": "%", "year": 2024},
            {"metric": "研发投入", "value": 350, "unit": "亿元", "year": 2024},
        ],
        "section_id": "section_0_核心财务指标",
        "category": "analysis",
    },
    {
        "agent_id": "phase_2_agent_1",
        "success": True,
        "content": "2024年销量分析：全球销量460万辆，同比增35%。",
        "data_points": [
            {"metric": "销量", "value": 460, "unit": "万辆", "year": 2024},
        ],
        "section_id": "section_1_销量分析",
        "category": "analysis",
    },
]

ALL_RAW = DC_RESULTS + ANALYSIS_RESULTS

SECTION_DETAILS_BYD = [
    {"id": "section_0_核心财务指标", "name": "核心财务指标"},
    {"id": "section_1_销量分析", "name": "销量分析"},
]


# ============================================================
# 辅助函数：复刻 orchestrator.py 的 M0-a key 映射
# ============================================================

def _build_agg_map(results):
    """agent_id -> result, section_id 存为 _section_id 元数据 (M0-a 修复)。"""
    m = {}
    for r in results:
        aid = r.get("agent_id", "")
        if aid:
            sid = r.get("section_id", "")
            if sid:
                r["_section_id"] = sid
            m[aid] = r
    return m


# ============================================================
# M0→M5-b 端到端测试
# ============================================================

class TestE2EM0toM5b:
    """BYD 研报管线完整端到端测试。"""

    def test_stage_m5a_calibration_gate_fixes_content(self):
        """M5-a 校准门：Analysis 中的近似值应被 canonical 修正。"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical

        gate = fix_content_from_canonical(deepcopy(ALL_RAW), BYD_CANONICAL, "CNY")
        results = gate["all_results"]
        report = gate["calibration_report"]

        assert report["total_metrics_checked"] > 0
        assert len(report["auto_fixed"]) == 4, (
            f"应修正 4 个指标（营收7200→6770, 净利润360→326.5, 毛利率27.5→22.5, 研发350→398），"
            f"实际 {len(report['auto_fixed'])}"
        )

        a0 = next(r for r in results if r["agent_id"] == "phase_2_agent_0")
        assert "6770" in a0["content"], f"营收应在 analysis content 中校准为 6770: {a0['content']}"
        assert "326.5" in a0["content"], f"净利润应在 analysis content 中校准为 326.5: {a0['content']}"

        rev_dp = next(dp for dp in a0["data_points"] if dp["metric"] == "营收")
        assert rev_dp["value"] == 6770, f"data_points 营收应校准为 6770，实际 {rev_dp['value']}"

    def test_stage_m5a_dc_values_unchanged(self):
        """M5-a 校准门：DC agent 的准确值不应被修改。"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical

        gate = fix_content_from_canonical(deepcopy(ALL_RAW), BYD_CANONICAL, "CNY")
        results = gate["all_results"]

        d0 = next(r for r in results if r["agent_id"] == "phase_1_agent_0")
        assert "6770" in d0["content"], f"DC 内容应保持不变: {d0['content']}"
        assert "326.5" in d0["content"], f"DC 内容应保持不变: {d0['content']}"

    def test_stage_m5a_data_points_preserved_after_fix(self):
        """M5-a 校准门：修复 data_points 后不丢失其他字段。"""
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical

        gate = fix_content_from_canonical(deepcopy(ALL_RAW), BYD_CANONICAL, "CNY")
        results = gate["all_results"]

        a0 = next(r for r in results if r["agent_id"] == "phase_2_agent_0")
        assert len(a0["data_points"]) == 4, "data_points 数量不应因校准而减少"

    def test_stage_m0_four_agents_four_keys(self):
        """M0 聚合：4 个 agent → 4 个独立聚合 key。"""
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        results_map = _build_agg_map(deepcopy(ALL_RAW))
        assert len(results_map) == 4

        agg = ResultAggregator()
        aggregated = agg.aggregate(results_map, section_details=SECTION_DETAILS_BYD)

        assert aggregated.stats["total_agents"] == 4
        assert aggregated.stats["total_keys"] == 4
        assert aggregated.stats["total_conflicts"] == 0

    def test_stage_m0_layered_content_by_stage(self):
        """M0 分层存储：data_collection / analysis 内容独立存在。"""
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        results_map = _build_agg_map(deepcopy(ALL_RAW))
        agg = ResultAggregator()
        aggregated = agg.aggregate(results_map, section_details=SECTION_DETAILS_BYD)

        assert "data_collection" in aggregated.layered_content
        assert "analysis" in aggregated.layered_content
        assert len(aggregated.layered_content["data_collection"]) >= 2
        assert len(aggregated.layered_content["analysis"]) >= 2

    def test_stage_m0_section_id_provenance(self):
        """M0-a: _section_id 被 ContentProvenance 消费。"""
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        results_map = _build_agg_map(deepcopy(ALL_RAW))
        agg = ResultAggregator()
        aggregated = agg.aggregate(results_map, section_details=SECTION_DETAILS_BYD)

        for key, prov in aggregated.content_provenance.items():
            if "phase_1" in key or "phase_2" in key:
                assert prov.section_target, f"{key} 应有 section_target (来自 _section_id)"

    def test_stage_m4_metric_conflicts_detected(self):
        """M4 指标冲突：DC 与 Analysis 值不同时应在 stats 中记录。"""
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator

        results_map = _build_agg_map(deepcopy(ALL_RAW))
        agg = ResultAggregator()
        aggregated = agg.aggregate(results_map, section_details=SECTION_DETAILS_BYD)

        assert aggregated.stats["metric_conflicts"] >= 2, (
            f"M4 应检测到 >=2 组指标冲突（营收7200≠6770, 净利润360≠326.5, …），"
            f"实际 {aggregated.stats['metric_conflicts']}"
        )
        assert len(aggregated.stats["metric_conflict_details"]) >= 2

        detail = aggregated.stats["metric_conflict_details"][0]
        assert "key" in detail
        assert "values" in detail
        assert "sources" in detail
        assert len(detail["values"]) >= 2

    def test_stage_m5b_calibration_phase_generated(self):
        """M5-b 校准阶段：ANALYSIS 类型 section → 生成 CALIBRATION phase。"""
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType
        from tests.helpers import make_orch_plan

        plan = make_orch_plan([SectionRole.ANALYSIS, SectionRole.ANALYSIS, SectionRole.SYNTHESIS])
        cal_phases = [p for p in plan.phases if p.phase_type == PhaseType.CALIBRATION]

        assert len(cal_phases) == 1
        cal_phase = cal_phases[0]
        calibrator = cal_phase.agent_specs[0]

        assert cal_phase.parallel == False, "校准阶段应为串行"
        assert calibrator.config.get("category") == "calibration", (
            f"校准 agent config.category 应为 calibration，实际 {calibrator.config.get('category')}"
        )
        assert calibrator.section_ids == [], "校准 agent 无 section_ids"

    def test_stage_m5b_calibrator_depends_on_all_prior(self):
        """M5-b: 校准 agent 依赖所有前置 agent。"""
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType
        from tests.helpers import make_orch_plan

        plan = make_orch_plan([SectionRole.ANALYSIS, SectionRole.ANALYSIS, SectionRole.SYNTHESIS])
        cal_phase = [p for p in plan.phases if p.phase_type == PhaseType.CALIBRATION][0]
        calibrator = cal_phase.agent_specs[0]
        deps = calibrator.config.get("resolved_dependencies", [])

        prior_ids = set()
        for p in plan.phases:
            if p.phase_type == PhaseType.CALIBRATION:
                break
            for spec in p.agent_specs:
                if spec.agent_id:
                    prior_ids.add(spec.agent_id)

        assert len(deps) >= len(prior_ids), f"deps {len(deps)} < prior agents {len(prior_ids)}"
        missing = prior_ids - set(deps)
        assert not missing, f"校准 agent 缺少依赖: {missing}"

    def test_stage_m5b_execution_order_correct(self):
        """M5-b execution_order: SYNTHESIS < CALIBRATION < REPORT。"""
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType
        from src.core.decomposition.strategies import ResearchPhase
        from tests.helpers import make_orch_plan

        plan = make_orch_plan([SectionRole.ANALYSIS, SectionRole.SYNTHESIS])
        decomp = plan.to_decomposition_plan()
        order = decomp.execution_order

        cal_idx = order.index(ResearchPhase.CALIBRATION)
        syn_idx = order.index(ResearchPhase.SYNTHESIS)
        rep_idx = order.index(ResearchPhase.REPORT_GENERATION)

        assert syn_idx < cal_idx < rep_idx, (
            f"期望 SYNTHESIS({syn_idx}) < CALIBRATION({cal_idx}) < REPORT({rep_idx})"
        )

    def test_stage_m5b_no_analysis_no_calibration(self):
        """M5-b: 无 ANALYSIS section 时不应生成校准阶段。"""
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType
        from tests.helpers import make_orch_plan

        plan = make_orch_plan([SectionRole.SYNTHESIS, SectionRole.DATA_COLLECTION])
        cal_phases = [p for p in plan.phases if p.phase_type == PhaseType.CALIBRATION]
        assert len(cal_phases) == 0

    def test_stage_m5b_calibration_injection_logic(self):
        """M5-b: 校准注入逻辑（engine.py 1871-1875 行）按契约产出正确结果。"""
        previous_results = [
            {"agent_id": "cal_1", "category": "calibration", "success": True,
             "calibration_report": {"summary": "revenue fixed", "full_text": "..."},
             "unified_data_reference": {"final_values": {"revenue": 6770}}},
            {"agent_id": "analysis_1", "category": "analysis", "success": True},
        ]

        _calib = [r for r in previous_results if r.get("category") == "calibration" and r.get("success")]
        task = {}
        if _calib:
            _calib_data = _calib[0]
            task["calibration_report"] = _calib_data.get("calibration_report", {})
            task["unified_data_reference"] = _calib_data.get("unified_data_reference", {})

        assert task["calibration_report"]["summary"] == "revenue fixed"
        assert task["unified_data_reference"]["final_values"]["revenue"] == 6770

    def test_stage_m5b_calibration_no_injection_without_results(self):
        """M5-b: 无校准结果 → 不注入 calibration_report。"""
        previous_results = [
            {"agent_id": "analysis_1", "category": "analysis", "success": True},
        ]

        _calib = [r for r in previous_results if r.get("category") == "calibration" and r.get("success")]
        task = {}
        if _calib:
            _calib_data = _calib[0]
            task["calibration_report"] = _calib_data.get("calibration_report", {})
            task["unified_data_reference"] = _calib_data.get("unified_data_reference", {})

        assert "calibration_report" not in task
        assert "unified_data_reference" not in task

    def test_stage_m5b_classify_agent_calibration(self):
        """M5-b: classify_agent 对 calibration category 返回 CALIBRATION。"""
        from src.core.orchestrator.execution.engine import ExecutionEngine, ExecutionConfig, AgentCategory
        from src.core.communication import MessageBus, SharedMemory

        class _MockAgent:
            agent_id = "calibrator_1"
            config = {"category": "calibration"}

        engine = ExecutionEngine(
            config=ExecutionConfig(),
            message_bus=MessageBus(),
            shared_memory=SharedMemory(),
        )
        result = engine.classify_agent(_MockAgent())
        assert result == AgentCategory.CALIBRATION

    def test_full_pipeline_end_to_end(self):
        """
        完整 BYD 管线一次跑通：
        Agent 原始产出 → M5-a 校准 → M0 聚合 + M4 冲突检测 → M5-b 阶段生成
        """
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType
        from src.core.decomposition.strategies import ResearchPhase
        from tests.helpers import make_orch_plan

        raw = deepcopy(ALL_RAW)

        # --- Stage 1: M5-a 校准门 ---
        gate = fix_content_from_canonical(raw, BYD_CANONICAL, "CNY")
        fixed = gate["all_results"]
        cal_report = gate["calibration_report"]

        assert cal_report["total_metrics_checked"] > 0
        assert len(cal_report["auto_fixed"]) == 4, (
            f"应修正 4 个指标，实际 {len(cal_report['auto_fixed'])}"
        )
        assert cal_report["currency_converted"] == []

        a0_content = next(r["content"] for r in fixed if r["agent_id"] == "phase_2_agent_0")
        assert "6770" in a0_content
        assert "326.5" in a0_content

        # --- Stage 2: M0 聚合 + M4 冲突检测 ---
        results_map = _build_agg_map(fixed)
        assert len(results_map) == 4

        agg = ResultAggregator()
        aggregated = agg.aggregate(results_map, section_details=SECTION_DETAILS_BYD)

        assert aggregated.stats["total_agents"] == 4
        assert aggregated.stats["total_keys"] == 4
        # 经 M5-a 校准后 DC 与 Analysis 值相同 → M4 应无冲突
        assert aggregated.stats["metric_conflicts"] == 0, (
            f"M5-a 校准后 M4 应无冲突，实际 {aggregated.stats['metric_conflicts']}"
        )
        assert "data_collection" in aggregated.layered_content
        assert "analysis" in aggregated.layered_content

        # --- Stage 3: M5-b 校准阶段生成 ---
        plan = make_orch_plan([SectionRole.ANALYSIS, SectionRole.ANALYSIS, SectionRole.SYNTHESIS])
        cal_phases = [p for p in plan.phases if p.phase_type == PhaseType.CALIBRATION]
        assert len(cal_phases) == 1

        cal_phase = cal_phases[0]
        calibrator = cal_phase.agent_specs[0]
        assert calibrator.config.get("category") == "calibration"
        assert cal_phase.parallel == False

        # 验证依赖
        deps = calibrator.config.get("resolved_dependencies", [])
        prior_ids = set()
        for p in plan.phases:
            if p.phase_type == PhaseType.CALIBRATION:
                break
            for spec in p.agent_specs:
                if spec.agent_id:
                    prior_ids.add(spec.agent_id)
        missing = prior_ids - set(deps)
        assert not missing, f"依赖缺失: {missing}"

        # 验证执行顺序
        decomp = plan.to_decomposition_plan()
        order = decomp.execution_order
        assert order.index(ResearchPhase.CALIBRATION) < order.index(ResearchPhase.REPORT_GENERATION)

    def test_full_pipeline_without_analysis_no_calibration(self):
        """
        完整管线：无 ANALYSIS 阶段时 M5-b 校准阶段不应生成。
        """
        from src.core.orchestrator.execution.calibration_gate import fix_content_from_canonical
        from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator
        from src.core.task_structure import SectionRole
        from src.core.dynamic_orchestrator import PhaseType
        from tests.helpers import make_orch_plan

        raw = deepcopy(DC_RESULTS)

        gate = fix_content_from_canonical(raw, BYD_CANONICAL, "CNY")
        fixed = gate["all_results"]
        results_map = _build_agg_map(fixed)
        agg = ResultAggregator()
        aggregated = agg.aggregate(results_map, section_details=SECTION_DETAILS_BYD)

        assert aggregated.stats["total_agents"] == 2
        assert aggregated.stats["metric_conflicts"] == 0

        plan = make_orch_plan([SectionRole.DATA_COLLECTION, SectionRole.SYNTHESIS])
        cal_phases = [p for p in plan.phases if p.phase_type == PhaseType.CALIBRATION]
        assert len(cal_phases) == 0, "无 ANALYSIS → 不应生成校准阶段"
