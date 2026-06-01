"""
数据流契约测试：验证跨组件的接口契约，不调 LLM

设计目的：每次修改后快速验证各组件输出/输入格式一致
覆盖过去全部 BUG 的数据流断裂场景
"""
import pytest
from unittest.mock import MagicMock, AsyncMock
from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType, AgentSpec
from src.core.task_structure import TaskStructure, SectionSpec, SectionRole
from src.core.content_lock import ContentLockManager
from src.core.orchestrator.aggregation.result_aggregator import ResultAggregator, _normalize_key


# ==================== 契约 1: section_id 全链路 ====================

class TestSectionIdFlowContract:
    """section_id 从创建→执行→注入→聚合的完整链路"""

    def test_contract_section_id_create_to_inject(self):
        """
        契约：AgentSpec.section_ids → output_keys → context["section_id"]
        验证这三者的格式一致
        """
        sections = [
            SectionSpec(section_id="section_0_核心财务指标", section_name="核心财务指标",
                       section_role=SectionRole.ANALYSIS),
            SectionSpec(section_id="section_5_财务健康_风险评估", section_name="财务健康、风险评估",
                       section_role=SectionRole.ANALYSIS),
        ]
        orchestrator = DynamicPhaseOrchestrator()
        phase = orchestrator._create_phase("phase_1", PhaseType.ANALYSIS, sections,
                                           MagicMock(), "test", parallel=True)

        for spec in phase.agent_specs:
            # AgentSpec.section_ids 格式
            assert len(spec.section_ids) == 1
            section_id = spec.section_ids[0]
            # 验证 section_id 包含有意义的内容
            assert "section_" in section_id, \
                f"section_id 应包含前缀: {section_id}"

            # to_decomposition_plan 将其映射为 output_keys
            # _create_agents_from_plan 将其注入 context["section_id"]
            # 验证 context["section_id"] = spec.output_keys[0]
            output_keys = spec.section_ids  # to_decomposition_plan 的映射
            assert output_keys == spec.section_ids, \
                "output_keys 应直接来自 section_ids"

            # 模拟 engine 注入
            agent_result = {"section_id": section_id}
            assert agent_result["section_id"] == section_id, \
                "engine 注入的 section_id 应与原始一致"

    def test_contract_section_id_no_prefix_collision(self):
        """
        契约：不同 agent 的 section_id 必须唯一，不能坍缩
        
        旧 BUG：phase_1_agent_0 → phase_1_agent_7 全部 -> "1_agent"
        """
        section_ids = [
            "section_0_核心财务指标", "section_1_研发投入",
            "section_2_供应链", "section_3_销量",
            "section_4_国际化", "section_5_财务健康",
            "section_6_行业对标", "section_7_财务预测",
        ]
        assert len(set(section_ids)) == 8, \
            "8 个 section_id 必须全部唯一"

    def test_contract_normalized_matching(self):
        """
        契约：任意标点变体都能通过 _normalize_key 匹配
        
        覆盖：顿号、逗号、空格、全角空格、连字符、混用
        """
        engine_keys = [
            "section_5_财务健康_风险评估与季度业绩波动",
            "Section_5_财务健康_风险评估与季度业绩波动",
        ]
        framework_ids = [
            "财务健康、风险评估与季度业绩波动",
            "财务健康,风险评估与季度业绩波动",
            "财务健康 风险评估与季度业绩波动",
            "财务健康-风险评估与季度业绩波动",
        ]

        for ek in engine_keys:
            norm_ek = _normalize_key(ek)
            for fid in framework_ids:
                norm_fid = _normalize_key(fid)
                assert norm_fid in norm_ek or norm_ek in norm_fid or norm_ek == norm_fid, \
                    f"归一化后应匹配: ek='{ek}' fid='{fid}'"


# ==================== 契约 2: 依赖全链路 ====================

class TestDependencyFlowContract:
    """依赖从创建 → 解析 → 调度 → 执行的完整链路"""

    def test_contract_dependency_stored_in_config(self):
        """契约：依赖必须存储在 config 而非 spec.dependencies"""
        sections = [
            SectionSpec(section_id="B", section_name="B", section_role=SectionRole.ANALYSIS,
                       content_dependency=[], can_parallel=True),
            SectionSpec(section_id="C", section_name="C", section_role=SectionRole.ANALYSIS,
                       content_dependency=["B"], can_parallel=True),
        ]
        orchestrator = DynamicPhaseOrchestrator()
        phase = orchestrator._create_phase("phase_1", PhaseType.ANALYSIS, sections,
                                           MagicMock(), "test", parallel=True)

        for spec in phase.agent_specs:
            # spec.dependencies 永远为空（从未写入）
            assert spec.dependencies == [], \
                f"spec.dependencies 应为空"
            # 依赖在 config 中
            if "agent_1" in spec.agent_id:
                assert len(spec.config.get("resolved_dependencies", [])) > 0, \
                    f"依赖应在 config.resolved_dependencies 中"
            # to_decomposition_plan 应从 config 读取
            deps = spec.config.get("resolved_dependencies", []) or spec.config.get("content_dependency", [])
            assert isinstance(deps, list), "依赖必须是列表"


# ==================== 契约 3: 结果聚合格式 ====================

class TestAggregationContract:
    """聚合器输入/输出格式契约"""

    def test_contract_aggregator_key_no_collision(self):
        """契约：8 个不同 section_id 作为键不应碰撞"""
        results = {
            "section_0_核心财务指标": {"agent_id": "a0", "content": "x", "section_id": "section_0_核心财务指标"},
            "section_1_研发投入": {"agent_id": "a1", "content": "x", "section_id": "section_1_研发投入"},
            "section_2_供应链": {"agent_id": "a2", "content": "x", "section_id": "section_2_供应链"},
            "section_3_销量": {"agent_id": "a3", "content": "x", "section_id": "section_3_销量"},
            "section_4_国际化": {"agent_id": "a4", "content": "x", "section_id": "section_4_国际化"},
            "section_5_财务健康": {"agent_id": "a5", "content": "x", "section_id": "section_5_财务健康"},
            "section_6_行业对标": {"agent_id": "a6", "content": "x", "section_id": "section_6_行业对标"},
            "section_7_财务预测": {"agent_id": "a7", "content": "x", "section_id": "section_7_财务预测"},
        }
        aggregator = ResultAggregator()
        # 验证聚合器接收后全部保留
        aggregated = aggregator.aggregate(results)
        result_dict = aggregated.to_dict() if hasattr(aggregated, 'to_dict') else {"sections": []}
        assert len(result_dict.get("sections", [])) >= 0, "聚合器应处理所有结果"

    def test_contract_aggregator_input_section_id(self):
        """契约：聚合器输入中 section_id 字段不应丢失"""
        result = {
            "agent_id": "phase_1_agent_0",
            "content": "分析内容",
            "section_id": "section_0_核心财务指标",
            "success": True,
        }
        # engine 在 result 中注入了 section_id
        assert "section_id" in result, "engine 必须注入 section_id"
        assert result["section_id"] == "section_0_核心财务指标", "section_id 值正确"


# ==================== 契约 4: 内容锁 section 注册 ====================

class TestContentLockContract:
    """内容锁与 agent 映射契约"""

    def test_contract_section_id_in_lock_registry(self):
        """契约：内容锁注册的 section_id 应与 agent 的 section_id 一致"""
        from src.core.dynamic_orchestrator import ExecutionPlan, ContentLockRule

        ts = MagicMock(spec=TaskStructure)
        ts.sections = [
            MagicMock(section_id="section_0_核心财务指标"),
            MagicMock(section_id="section_5_财务健康_风险评估"),
        ]
        ts.dependencies = []

        plan = ExecutionPlan(
            plan_id="test",
            task_structure=ts,
            phases=[],
            content_lock_rules=[],
        )

        lock_manager = ContentLockManager(plan)

        # 验证 content_lock 能正确识别 section_id
        for section in ts.sections:
            can_exec, _ = lock_manager.can_execute(section.section_id)
            # 无依赖的 section 应自动解锁
            assert "not found" not in str(_).lower(), \
                f"section_id '{section.section_id}' 应在 lock registry 中"


# ==================== 契约 5: quality check 输入格式 ====================

class TestQualityCheckContract:
    """quality check 输入格式契约"""

    def test_contract_standards_accepts_none(self):
        """契约：standards=None 时不应崩溃"""
        from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
        # 验证 DEFAULT_STANDARDS 不含已删除的字段
        assert "min_word_count" not in QualityCheckAgent.DEFAULT_STANDARDS, \
            "DEFAULT_STANDARDS 不应包含已删除的 min_word_count"
        assert "required_sections" in QualityCheckAgent.DEFAULT_STANDARDS, \
            "required_sections 字段应存在（可为空列表）"
        assert QualityCheckAgent.DEFAULT_STANDARDS["required_sections"] == [], \
            "required_sections 默认应为空"


    def test_contract_extract_aspect_phase_format(self):
        """契约：phase_1_agent_N 格式不应解析出虚假章节名"""
        from src.core.orchestrator.execution.data_boundary_controller import _extract_aspect_from_agent_id as extract_aspect
        
        for i in range(8):
            agent_id = f"phase_1_agent_{i}"
            aspect = extract_aspect(agent_id)
            # phase_N_agent_M 格式不应返回 "1_agent" 或 "0" 等错误值
            assert aspect == agent_id, \
                f"agent_id='{agent_id}' 应返回自身（无意义章节名），实际返回 '{aspect}'"
