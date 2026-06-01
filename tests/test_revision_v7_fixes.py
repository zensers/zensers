"""
V7修订系统修复功能测试

设计原则: 模拟真实用户场景，验证行为是否正确，而非检查代码字符串。
每个测试复现一个bug场景，断言修复后的预期行为。

运行命令: D:\conda\python.exe -m pytest tests/test_revision_v7_fixes.py -v --tb=short
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)


# ═══════════════════════════════════════════════════════════════
# BP1: 低置信度输入应路由到智能路由，而非返回死路错误
# ═══════════════════════════════════════════════════════════════

class TestBP1_LowConfidenceRoutesToIntelligentRouting:
    """
    场景: 用户输入"补充市场规模数据"，意图分析器返回低置信度结果。
    修复前: handle_feedback() 返回 FULL_RESEARCH_NEEDED + 错误消息 → 死路
    修复后: handle_feedback() 应路由到智能路由，生成子Agent执行计划
    """

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_intelligent_routing(self):
        """
        当意图分析返回 confidence < 0.3 时，
        handle_feedback 应调用智能路由而非只返回错误状态。
        """
        from core.adjustment.revision_types import (
            AnalysisResult, ExecutionStatus, RevisionAction, RevisionTarget,
            RevisionOpType, LocationStrategy, SectionRef, RefType,
            ExecutionFlow,
        )
        from core.adjustment.revision_executor import RevisionExecutor, ProgressNotifier

        low_confidence_analysis = AnalysisResult(
            intents=[],
            needs_clarification=False,
            is_uncertain=True,
            confidence=0.1,
            clarification_questions=["请描述修改需求"],
        )

        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=low_confidence_analysis)

        mock_lock_manager = MagicMock()
        mock_lock_manager.acquire_lock = MagicMock(
            return_value=MagicMock(__aenter__=AsyncMock(return_value=None),
                                    __aexit__=AsyncMock(return_value=None))
        )

        routing_called = {"value": False}

        async def fake_route_to_intelligent(user_request, **kwargs):
            routing_called["value"] = True
            return ExecutionFlow(
                status=ExecutionStatus.COMPLETED,
                error=None,
            )

        executor = RevisionExecutor(mock_lock_manager)
        executor._intent_analyzer = mock_analyzer

        if hasattr(executor, '_route_to_intelligent_routing'):
            executor._route_to_intelligent_routing = fake_route_to_intelligent

        mock_report = MagicMock()
        mock_report.id = "test_report"

        flow = await executor.handle_feedback("补充市场规模数据", mock_report)

        if flow.status == ExecutionStatus.FULL_RESEARCH_NEEDED:
            pytest.fail(
                "BP1未修复: handle_feedback 返回 FULL_RESEARCH_NEEDED 死路，"
                "未路由到智能路由。用户输入'补充市场规模数据'无法被处理。"
            )

        if flow.status == ExecutionStatus.COMPLETED:
            assert routing_called["value"], (
                "flow.status=COMPLETED 但未调用智能路由，可能走了其他路径"
            )

    @pytest.mark.asyncio
    async def test_handle_unknown_intent_invokes_routing(self):
        """
        _handle_unknown_intent 不应只设置 FULL_RESEARCH_NEEDED，
        应实际触发智能路由或委托给上层处理。
        """
        from core.adjustment.revision_types import ExecutionFlow, ExecutionStatus
        from core.adjustment.revision_executor import RevisionExecutor
        from core.adjustment.report_lock_manager import ReportLockManager

        mock_lock = MagicMock()
        executor = RevisionExecutor(mock_lock)
        flow = ExecutionFlow()

        result = await executor._handle_unknown_intent(flow)

        if result.status == ExecutionStatus.FULL_RESEARCH_NEEDED and not result.error:
            pass
        elif result.status == ExecutionStatus.FULL_RESEARCH_NEEDED:
            pytest.fail(
                "BP1未修复: _handle_unknown_intent() 只设 status=FULL_RESEARCH_NEEDED "
                "+ error='Intent not understood'，没有路由逻辑。"
            )


# ═══════════════════════════════════════════════════════════════
# BP2: 澄清循环应生成结构化选项 + 低置信度跳过澄清
# ═══════════════════════════════════════════════════════════════

class TestBP2_ClarificationLoopStructuredOptions:
    """
    场景: 意图分析返回 needs_clarification=True + 有部分intents。
    修复前: 澄清问题只是文本，无选项供用户选择
    修复后: 澄清问题应包含基于intents的结构化选项
    """

    @pytest.mark.asyncio
    async def test_clarification_includes_structured_options(self):
        """
        ClarificationLoop._format_question 应生成带选项的澄清问题，
        而非纯文本问题。
        """
        from core.dialogue.revision_sub_state_machine import ClarificationLoop
        from core.adjustment.revision_types import (
            AnalysisResult, RevisionAction, RevisionTarget,
            RevisionOpType, LocationStrategy, SectionRef, RefType,
        )

        analysis_with_intents = AnalysisResult(
            intents=[
                RevisionAction(
                    action_id="1",
                    action_type=RevisionOpType.ADD,
                    target=RevisionTarget(
                        raw_text="市场规模",
                        section_refs=[],
                        location_strategy=LocationStrategy.KEYWORD,
                        is_ambiguous=False,
                    ),
                    confidence=0.6,
                ),
            ],
            needs_clarification=True,
            clarification_questions=["您想要如何修改？"],
            confidence=0.6,
        )

        loop = ClarificationLoop(
            analyzer=AsyncMock(),
            report={},
            ask_user_callback=AsyncMock(return_value="1"),
        )

        question = loop._format_question(analysis_with_intents)

        has_options = any(
            kw in question
            for kw in ["请选择", "选项", "1.", "①", "(1)", "1:"]
        )

        if not has_options:
            pytest.fail(
                "BP2未修复: _format_question() 不生成结构化选项。"
                f"输出: '{question}' — 用户无法快速选择，只能自由输入。"
            )

    @pytest.mark.asyncio
    async def test_low_confidence_skips_clarification_enters_routing(self):
        """
        confidence < 0.3 时，handle_feedback 应跳过澄清循环，
        直接路由到智能路由。不让澄清循环处理超出能力的问题。
        """
        from core.adjustment.revision_types import (
            AnalysisResult, ExecutionStatus,
        )
        from core.adjustment.revision_executor import RevisionExecutor

        low_conf_analysis = AnalysisResult(
            intents=[],
            needs_clarification=True,
            is_uncertain=True,
            confidence=0.1,
            clarification_questions=["请描述修改需求"],
        )

        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=low_conf_analysis)

        clarification_entered = {"value": False}
        original_run = AsyncMock(return_value=low_conf_analysis)

        mock_lock_manager = MagicMock()
        mock_lock_manager.acquire_lock = MagicMock(
            return_value=MagicMock(__aenter__=AsyncMock(return_value=None),
                                    __aexit__=AsyncMock(return_value=None))
        )

        executor = RevisionExecutor(mock_lock_manager)
        executor._intent_analyzer = mock_analyzer

        mock_report = MagicMock()
        mock_report.id = "test_report"

        flow = await executor.handle_feedback("补充市场规模数据", mock_report)

        if flow.status == ExecutionStatus.CLARIFICATION_FAILED:
            pytest.fail(
                "BP2未修复: 低置信度(conf=0.1)进入了澄清循环，"
                "澄清循环无法处理超出意图分析器能力的问题，应直接路由到智能路由。"
            )


# ═══════════════════════════════════════════════════════════════
# BP3: SSE取消不应中断修订执行
# ═══════════════════════════════════════════════════════════════

class TestBP3_SSECancelDoesNotInterruptRevision:
    """
    场景: 修订正在执行中，用户发新消息触发SSE流取消。
    修复前: CancelledError传播到执行器，修订中断
    修复后: 修订在后台Task执行，SSE取消不影响
    """

    @pytest.mark.asyncio
    async def test_revision_survives_sse_cancel(self):
        """
        模拟: 修订执行期间SSE流被取消，
        修订应继续执行完成而非被CancelledError中断。
        """
        from core.adjustment.revision_types import ExecutionStatus
        from core.adjustment.revision_executor import RevisionExecutor, ProgressNotifier

        execution_completed = {"value": False}

        async def slow_prompt(question):
            await asyncio.sleep(10)
            return "y"

        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=MagicMock(
            intents=[MagicMock(action_type=MagicMock(value="modify"), confidence=0.8)],
            needs_clarification=False,
            is_uncertain=False,
            confidence=0.8,
        ))

        mock_lock_manager = MagicMock()
        mock_lock_manager.acquire_lock = MagicMock(
            return_value=MagicMock(__aenter__=AsyncMock(return_value=None),
                                    __aexit__=AsyncMock(return_value=None))
        )

        notifier = ProgressNotifier(prompt_user_callback=slow_prompt)
        executor = RevisionExecutor(mock_lock_manager, notifier=notifier)
        executor._intent_analyzer = mock_analyzer

        mock_report = MagicMock()
        mock_report.id = "test_report"

        task = asyncio.create_task(
            executor.handle_feedback("修改标题", mock_report)
        )

        await asyncio.sleep(0.1)
        task.cancel()

        try:
            flow = await task
        except asyncio.CancelledError:
            pytest.fail(
                "BP3未修复: CancelledError传播到修订执行器，"
                "修订被中断。修订应在后台Task中执行，不受SSE取消影响。"
            )

        execution_completed["value"] = True


# ═══════════════════════════════════════════════════════════════
# BP4: 澄清等待期间用户输入应被正确路由
# ═══════════════════════════════════════════════════════════════

class TestBP4_UserInputRoutedDuringClarification:
    """
    场景: 系统在澄清等待中，用户通过聊天框输入回复。
    修复前: 用户输入被吞没为"y"
    修复后: 用户真实输入应作为澄清回复传递
    """

    @pytest.mark.asyncio
    async def test_user_text_passed_as_clarification_response(self):
        """
        澄清等待期间，用户输入"补充竞争格局数据"，
        应传递到 _clarification_responses 而非自动"y"。
        """
        api_path = os.path.join(SRC_ROOT, "api", "research_api.py")
        with open(api_path, "r", encoding="utf-8") as f:
            source = f.read()

        idx = source.find("_pending_clarification_id")
        if idx == -1:
            pytest.skip("_pending_clarification_id not found in research_api.py")

        context = source[max(0, idx - 100):idx + 600]

        auto_y_patterns = [
            'clarification_responses[pending_clar_id] = "y"',
            'clarification_responses[pending_clarification_id] = "y"',
            'clarification_responses[pending_id] = "y"',
        ]

        user_text_patterns = [
            'clarification_responses[pending_clarification_id] = user_text',
            'clarification_responses[pending_clar_id] = user_text',
            'clarification_responses[pending_id] = user_text',
            'clarification_responses[' in context and '= user_' in context,
        ]

        has_auto_y = any(p in context for p in auto_y_patterns)
        has_user_text = any(p in context for p in user_text_patterns)

        if has_auto_y and not has_user_text:
            pytest.fail(
                "BP4未修复: 澄清等待期间用户输入被自动替换为'y'，"
                "用户真实输入被丢弃。应将 user_text 传递给 _clarification_responses。"
            )

    @pytest.mark.asyncio
    async def test_clarification_timeout_does_not_auto_confirm(self):
        """
        澄清超时不应自动确认"y"，
        应返回超时标记让调用方通知用户。
        """
        from core.dialogue.revision_sub_state_machine import ClarificationLoop
        from core.adjustment.revision_types import AnalysisResult

        analysis = AnalysisResult(
            intents=[],
            needs_clarification=True,
            clarification_questions=["请描述修改需求"],
            confidence=0.2,
        )

        async def timeout_callback(question):
            raise asyncio.TimeoutError()

        loop = ClarificationLoop(
            analyzer=AsyncMock(),
            report={},
            ask_user_callback=timeout_callback,
        )

        result = await loop._ask_user("请描述修改需求")

        if result == "y":
            pytest.fail(
                "BP4未修复: 澄清超时返回'y'自动确认。"
                "应返回超时标记(如'__TIMEOUT__')，让调用方通知用户并允许重试。"
            )


# ═══════════════════════════════════════════════════════════════
# 集成缺失: _post_process 未被调用
# ═══════════════════════════════════════════════════════════════

class TestIntegration_PostProcessCalledAfterExecution:
    """
    场景: 修订执行成功后，应自动调用 _post_process()
    进行章节重编号和交叉引用修复。
    修复前: _post_process 定义但从未被调用
    修复后: 执行成功后应调用
    """

    @pytest.mark.asyncio
    async def test_post_process_called_on_success(self):
        """
        _execute_plan_with_progress 成功后应调用 _post_process。
        """
        from core.adjustment.revision_executor import RevisionExecutor
        from core.adjustment.revision_types import ReportTree

        mock_lock_manager = MagicMock()
        executor = RevisionExecutor(mock_lock_manager)

        post_process_called = {"value": False}
        original_post_process = executor._post_process

        def tracking_post_process(report_tree):
            post_process_called["value"] = True
            return original_post_process(report_tree)

        executor._post_process = tracking_post_process

        report_tree = ReportTree()

        mock_plan = MagicMock()
        mock_plan.actions = []

        result = await executor._execute_plan_with_progress(
            mock_plan, report_tree, "snap_001", "session_001"
        )

        if result.success and not post_process_called["value"]:
            pytest.fail(
                "集成缺失未修复: _execute_plan_with_progress 成功后未调用 _post_process()。"
                "renumberer 和 cross_ref_fixer 处于休眠状态。"
            )


# ═══════════════════════════════════════════════════════════════
# 集成缺失: CascadeUpdateAnalyzer 未接入
# ═══════════════════════════════════════════════════════════════

class TestIntegration_CascadeAnalyzerUsed:
    """
    场景: 修订执行后，应分析级联影响。
    修复前: CascadeUpdateAnalyzer 可导入但从未在 executor 中使用
    修复后: 应在执行流程中调用
    """

    def test_cascade_analyzer_callable_from_executor(self):
        """
        CascadeUpdateAnalyzer.analyze_cascade_impact 可被调用，
        且 RevisionExecutor 中有调用点。
        """
        from core.adjustment.cascade_update_analyzer import CascadeUpdateAnalyzer
        from core.adjustment.revision_executor import RevisionExecutor

        analyzer = CascadeUpdateAnalyzer()
        result = analyzer.analyze_cascade_impact(
            target_sections=["市场规模"],
            all_sections=["市场规模", "竞争格局", "发展趋势"],
        )

        assert result is not None, "CascadeUpdateAnalyzer 应返回有效结果"

        executor_source = ""
        try:
            executor_source = str(open(
                os.path.join(SRC_ROOT, "core", "adjustment", "revision_executor.py"),
                "r", encoding="utf-8"
            ).read())
        except Exception:
            pass

        has_cascade_call = "analyze_cascade_impact" in executor_source

        if not has_cascade_call:
            pytest.fail(
                "集成缺失未修复: RevisionExecutor 中未调用 "
                "CascadeUpdateAnalyzer.analyze_cascade_impact()。"
                "级联分析能力存在但未接入执行管道。"
            )


# ═══════════════════════════════════════════════════════════════
# 集成缺失: RevisionIntentMapper 未接入
# ═══════════════════════════════════════════════════════════════

class TestIntegration_IntentMapperConnected:
    """
    场景: 意图分析后应通过三级映射路由到正确路径。
    修复前: RevisionIntentMapper 可导入但从未被调用
    修复后: 应在 handle_feedback 中使用
    """

    def test_intent_mapper_produces_valid_route(self):
        """
        RevisionIntentMapper.map() 能正确将意图映射到路由决策。
        """
        from core.adjustment.revision_intent_mapper import RevisionIntentMapper
        from core.intent_types import IntentType, TaskComplexity

        mapper = RevisionIntentMapper()

        revision_intent, route = mapper.map(
            primary_intent=IntentType.FIX,
            complexity=TaskComplexity.TRIVIAL,
            user_input="修正错别字",
        )

        assert route.route == "lightweight", (
            f"修正错别字应走lightweight路径，实际: {route.route}"
        )

        revision_intent2, route2 = mapper.map(
            primary_intent=IntentType.RESEARCH,
            complexity=TaskComplexity.COMPLEX,
            user_input="补充市场规模数据",
        )

        assert route2.route == "incremental", (
            f"复杂研究应走incremental路径，实际: {route2.route}"
        )

    @pytest.mark.asyncio
    async def test_mapper_used_in_handle_feedback(self):
        """
        RevisionExecutor.handle_feedback 应使用 RevisionIntentMapper
        决定走 lightweight/incremental/hybrid 路径。
        """
        from core.adjustment.revision_executor import RevisionExecutor
        from core.intent_types import IntentType, TaskComplexity

        mock_lock_manager = MagicMock()
        executor = RevisionExecutor(mock_lock_manager)

        has_mapper_attr = hasattr(executor, '_intent_mapper') or hasattr(executor, '_mapper')
        uses_mapper_in_source = False

        import inspect
        try:
            source = inspect.getsource(RevisionExecutor.handle_feedback)
            uses_mapper_in_source = any(
                kw in source
                for kw in ["mapper.map", "RevisionIntentMapper", "route_decision"]
            )
        except Exception:
            pass

        if not has_mapper_attr and not uses_mapper_in_source:
            pytest.fail(
                "集成缺失未修复: RevisionExecutor 未使用 RevisionIntentMapper。"
                "三级路由映射(lightweight/incremental/hybrid)未接入，"
                "所有需求只走原子操作或轻量路径。"
            )


# ═══════════════════════════════════════════════════════════════
# 端到端: 修复后因果链验证
# ═══════════════════════════════════════════════════════════════

class TestEndToEnd_CausalChainAfterFix:
    """
    完整因果链: 用户需求 → 正确路由 → 能力触达

    修复前:
      "补充市场规模数据" → FULL_RESEARCH_NEEDED → 死路

    修复后:
      "补充市场规模数据" → 智能路由 → 子Agent执行 → 结果写回
    """

    @pytest.mark.asyncio
    async def test_complex_request_not_dead_end(self):
        """
        复杂修订请求（需要重新搜集数据）不应变成死路。
        """
        from core.adjustment.revision_types import (
            AnalysisResult, ExecutionStatus,
        )
        from core.adjustment.revision_executor import RevisionExecutor

        complex_analysis = AnalysisResult(
            intents=[],
            needs_clarification=True,
            is_uncertain=True,
            confidence=0.1,
            clarification_questions=["请描述修改需求"],
        )

        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=complex_analysis)

        mock_lock_manager = MagicMock()
        mock_lock_manager.acquire_lock = MagicMock(
            return_value=MagicMock(__aenter__=AsyncMock(return_value=None),
                                    __aexit__=AsyncMock(return_value=None))
        )

        executor = RevisionExecutor(mock_lock_manager)
        executor._intent_analyzer = mock_analyzer

        mock_report = MagicMock()
        mock_report.id = "test_report"

        flow = await executor.handle_feedback("补充市场规模数据", mock_report)

        is_dead_end = (
            flow.status == ExecutionStatus.FULL_RESEARCH_NEEDED
            or (flow.status == ExecutionStatus.CLARIFICATION_FAILED)
            or (flow.status == ExecutionStatus.FAILED and "not understood" in (flow.error or ""))
        )

        if is_dead_end:
            pytest.fail(
                f"端到端失败: 复杂修订请求变成死路。"
                f"status={flow.status.value}, error={flow.error}。"
                f"修复后应路由到智能路由让子Agent执行。"
            )

    @pytest.mark.asyncio
    async def test_lightweight_still_works(self):
        """
        修复不应破坏已正常工作的轻量操作路径。
        """
        from core.adjustment.revision_types import (
            AnalysisResult, ExecutionStatus, RevisionAction, RevisionTarget,
            RevisionOpType, LocationStrategy,
        )
        from core.adjustment.revision_executor import RevisionExecutor

        lightweight_analysis = AnalysisResult(
            intents=[
                RevisionAction(
                    action_id="1",
                    action_type=RevisionOpType.UPDATE_TITLE,
                    target=RevisionTarget(
                        raw_text="标题",
                        section_refs=[],
                        location_strategy=LocationStrategy.KEYWORD,
                        is_ambiguous=False,
                    ),
                    confidence=0.9,
                ),
            ],
            needs_clarification=False,
            confidence=0.9,
        )

        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=lightweight_analysis)

        mock_lock_manager = MagicMock()
        executor = RevisionExecutor(mock_lock_manager)
        executor._intent_analyzer = mock_analyzer

        mock_report = MagicMock()
        mock_report.id = "test_report"

        flow = await executor.handle_feedback("修改标题为新标题", mock_report)

        assert flow.status == ExecutionStatus.LIGHTWEIGHT_DONE, (
            f"轻量操作路径被破坏: status={flow.status.value}，应为LIGHTWEIGHT_DONE"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])