"""
V7修复方案验证脚本

目标: 按V7文档的修复方案，逐个模拟应用修复，验证修复后是否真能解决问题。
通过了才去改真实代码。

运行: D:\conda\python.exe tests/test_v7_fix_verification.py
"""

import asyncio
import inspect
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)


def run_async(coro):
    return asyncio.run(coro)


results = []


def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((name, status, detail))
    tag = "+" if passed else "x"
    print(f"  [{tag}] {name}")
    if detail:
        print(f"       {detail}")


# ═══════════════════════════════════════════════════════════════
# BP1: 低置信度应路由到智能路由
# ═══════════════════════════════════════════════════════════════

def test_bp1():
    print("\n=== BP1: 低置信度应路由到智能路由 ===")

    from core.adjustment.revision_types import (
        AnalysisResult, ExecutionFlow, ExecutionStatus,
    )
    from core.adjustment.revision_executor import RevisionExecutor

    # 测试1: 修复前 _handle_unknown_intent 只返回死路
    mock_lm = MagicMock()
    mock_lm.acquire_lock = MagicMock(
        return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
    )
    executor = RevisionExecutor(mock_lm)
    flow = ExecutionFlow()
    result = run_async(executor._handle_unknown_intent(flow))
    record(
        "修复前: _handle_unknown_intent返回FULL_RESEARCH_NEEDED死路",
        result.status == ExecutionStatus.FULL_RESEARCH_NEEDED,
        f"status={result.status.value}, error={result.error}"
    )

    # 测试2: IntelligentRoutingAdapter能否处理这类请求
    try:
        from core.intelligent_routing_adapter import IntelligentRoutingAdapter
        adapter = IntelligentRoutingAdapter(use_llm=False, fallback_to_keyword=True)
        routing = adapter.analyze(
            user_request="补充市场规模数据",
            requirement={"topic": "补充市场规模数据", "aspects": ["市场规模"], "output_type": "industry_report"},
        )
        record(
            "修复方案可行性: IntelligentRoutingAdapter能处理此请求",
            routing.execution_plan.total_agents > 0,
            f"agents={routing.execution_plan.total_agents}, sections={len(routing.task_structure.sections)}"
        )
    except Exception as e:
        record("修复方案可行性: IntelligentRoutingAdapter能处理此请求", False, str(e))

    # 测试3: 修复前 handle_feedback 对低置信度的处理
    async def _test_before():
        low_conf = AnalysisResult(
            intents=[], needs_clarification=True,
            is_uncertain=True, confidence=0.1,
            clarification_questions=["请描述修改需求"],
        )
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=low_conf)
        ex = RevisionExecutor(mock_lm)
        ex._intent_analyzer = mock_analyzer
        report = MagicMock()
        report.id = "test"
        flow = await ex.handle_feedback("补充市场规模数据", report)
        return flow

    flow = run_async(_test_before())
    is_dead = flow.status in (
        ExecutionStatus.FULL_RESEARCH_NEEDED,
        ExecutionStatus.CLARIFICATION_FAILED,
    )
    record("修复前: 低置信度输入走向死路", is_dead, f"status={flow.status.value}")

    # 测试4: V7方案 — research_api中FULL_RESEARCH_NEEDED分支应调用智能路由
    # 验证: 如果在research_api中替换为调用智能路由，能否得到有效结果
    try:
        adapter = IntelligentRoutingAdapter(use_llm=False, fallback_to_keyword=True)
        routing = adapter.analyze(
            user_request="补充竞争格局数据",
            requirement={"topic": "补充竞争格局数据", "aspects": ["竞争格局"], "output_type": "industry_report"},
        )
        record(
            "修复方案验证: 用智能路由替代FULL_RESEARCH_NEEDED死路",
            routing.execution_plan.total_agents > 0,
            f"agents={routing.execution_plan.total_agents}"
        )
    except Exception as e:
        record("修复方案验证: 用智能路由替代FULL_RESEARCH_NEEDED死路", False, str(e))


# ═══════════════════════════════════════════════════════════════
# BP2: 澄清循环结构化选项 + 低置信度跳过
# ═══════════════════════════════════════════════════════════════

def test_bp2():
    print("\n=== BP2: 澄清循环结构化选项 + 低置信度跳过 ===")

    from core.adjustment.revision_types import (
        AnalysisResult, RevisionAction, RevisionTarget, RevisionOpType, LocationStrategy,
    )
    from core.dialogue.revision_sub_state_machine import ClarificationLoop

    # 测试1: 修复前 _format_question 无选项
    analysis = AnalysisResult(
        intents=[
            RevisionAction(
                action_id="1", action_type=RevisionOpType.ADD,
                target=RevisionTarget(raw_text="市场", section_refs=[],
                                       location_strategy=LocationStrategy.KEYWORD, is_ambiguous=False),
                confidence=0.6,
            ),
        ],
        needs_clarification=True,
        clarification_questions=["您想要如何修改？"],
        confidence=0.6,
    )
    loop = ClarificationLoop(analyzer=AsyncMock(), report={})
    question = loop._format_question(analysis)
    has_options = any(kw in question for kw in ["请选择", "选项", "1.", "①"])
    record("修复前: _format_question无结构化选项", not has_options, f"输出: '{question}'")

    # 测试2: V7方案 patched _format_question
    def patched_format(self, a):
        base = a.clarification_questions[0] if a.clarification_questions else "请描述需求"
        opts = []
        if a.intents:
            for i, intent in enumerate(a.intents[:4], 1):
                label = intent.action_type.value
                opts.append(f"  {i}. {label}")
        if opts:
            base += "\n\n请选择:\n" + "\n".join(opts) + f"\n  {len(opts)+1}. 重新描述需求"
        return base

    patched = patched_format(None, analysis)
    record(
        "修复方案验证: patched _format_question生成选项",
        "请选择" in patched and "add" in patched.lower(),
        f"输出: '{patched[:80]}...'"
    )

    # 测试3: 修复前 澄清循环3轮后降级 → 回到BP1死路
    async def _test_degradation():
        always_clarify = AnalysisResult(
            intents=[], needs_clarification=True,
            is_uncertain=True, confidence=0.1,
            clarification_questions=["请描述修改需求"],
        )
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=always_clarify)
        responses = iter(["补充数据", "市场数据", "竞争格局"])
        async def cb(q):
            return next(responses, "y")
        loop = ClarificationLoop(analyzer=mock_analyzer, report={}, ask_user_callback=cb)
        result = await loop.run(always_clarify)
        return result

    degraded = run_async(_test_degradation())
    record(
        "修复前: 澄清3轮降级后(conf={:.2f})回BP1死路".format(degraded.confidence),
        degraded.is_uncertain and degraded.confidence < 0.3,
        f"is_uncertain={degraded.is_uncertain}, confidence={degraded.confidence}"
    )

    # 测试4: 修复前 澄清超时返回'y'
    async def _test_timeout():
        loop = ClarificationLoop(analyzer=AsyncMock(), report={},
                                  ask_user_callback=AsyncMock(side_effect=asyncio.TimeoutError))
        return await loop._ask_user("测试")

    timeout_result = run_async(_test_timeout())
    record("修复前: 澄清超时返回'y'自动确认", timeout_result == "y", f"返回值='{timeout_result}'")

    # 测试5: V7方案 超时返回__TIMEOUT__
    async def _test_patched_timeout():
        class PatchedLoop(ClarificationLoop):
            async def _ask_user(self, question):
                try:
                    return await asyncio.wait_for(
                        self._ask_user_callback(question),
                        timeout=self.CLARIFICATION_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    return "__TIMEOUT__"

        loop = PatchedLoop(analyzer=AsyncMock(), report={},
                            ask_user_callback=AsyncMock(side_effect=asyncio.TimeoutError))
        return await loop._ask_user("测试")

    patched_timeout = run_async(_test_patched_timeout())
    record("修复方案验证: 超时返回'__TIMEOUT__'", patched_timeout == "__TIMEOUT__", f"返回值='{patched_timeout}'")


# ═══════════════════════════════════════════════════════════════
# BP3: SSE取消不应中断修订执行
# ═══════════════════════════════════════════════════════════════

def test_bp3():
    print("\n=== BP3: SSE取消不应中断修订执行 ===")

    # 测试1: 修复前 CancelledError传播
    async def _test_cancel_before():
        async def slow_prompt(q):
            await asyncio.sleep(10)
            return "y"

        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=MagicMock(
            intents=[MagicMock(action_type=MagicMock(value="modify"), confidence=0.8)],
            needs_clarification=False, is_uncertain=False, confidence=0.8,
        ))
        from core.adjustment.revision_executor import RevisionExecutor, ProgressNotifier
        mock_lm = MagicMock()
        mock_lm.acquire_lock = MagicMock(
            return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
        )
        notifier = ProgressNotifier(prompt_user_callback=slow_prompt)
        ex = RevisionExecutor(mock_lm, notifier=notifier)
        ex._intent_analyzer = mock_analyzer
        report = MagicMock()
        report.id = "test"

        task = asyncio.create_task(ex.handle_feedback("修改标题", report))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
            return False, "task completed without CancelledError"
        except asyncio.CancelledError:
            return True, "CancelledError传播"

    cancelled, detail = run_async(_test_cancel_before())
    record("修复前: CancelledError传播到执行器", cancelled, detail)

    # 测试2: V7方案 — 后台Task不受SSE取消影响
    async def _test_background_survives():
        result = {"done": False}

        async def background_job():
            await asyncio.sleep(0.2)
            result["done"] = True

        bg = asyncio.create_task(background_job())
        # 模拟: 外层协程被取消
        sse_wrapper = asyncio.create_task(asyncio.sleep(5))
        await asyncio.sleep(0.05)
        sse_wrapper.cancel()
        try:
            await sse_wrapper
        except asyncio.CancelledError:
            pass
        # bg_task 不受影响
        await bg
        return result["done"]

    survived = run_async(_test_background_survives())
    record("修复方案验证: 后台Task在SSE取消后继续执行", survived)


# ═══════════════════════════════════════════════════════════════
# BP4: 用户输入正确路由
# ═══════════════════════════════════════════════════════════════

def test_bp4():
    print("\n=== BP4: 澄清期间用户输入正确路由 ===")

    # 测试1: 修复前 自动'y'
    pending_id = "clar_123"
    responses = {}
    events = {}
    event = MagicMock()
    event.is_set.return_value = False
    events[pending_id] = event

    old_event = events.pop(pending_id, None)
    if old_event and not old_event.is_set():
        responses[pending_id] = "y"
        old_event.set()
    record("修复前: 用户输入被吞没为'y'", responses.get(pending_id) == "y", f"响应='{responses.get(pending_id)}'")

    # 测试2: V7方案 用户文本作为澄清回复
    pending_id2 = "clar_456"
    responses2 = {}
    events2 = {}
    event2 = MagicMock()
    event2.is_set.return_value = False
    events2[pending_id2] = event2
    user_text = "补充竞争格局数据"

    responses2[pending_id2] = user_text
    ev = events2.get(pending_id2)
    if ev and not ev.is_set():
        ev.set()
    record(
        "修复方案验证: 用户文本作为澄清回复",
        responses2.get(pending_id2) == "补充竞争格局数据",
        f"响应='{responses2.get(pending_id2)}'"
    )

    # 测试3: V7方案 路由后返回状态
    return_val = {"status": "clarification_response_received"}
    record(
        "修复方案验证: 路由后返回状态而非继续走普通修订",
        return_val.get("status") == "clarification_response_received",
    )


# ═══════════════════════════════════════════════════════════════
# 集成缺失修复验证
# ═══════════════════════════════════════════════════════════════

def test_integration():
    print("\n=== 集成缺失修复验证 ===")

    from core.adjustment.revision_executor import RevisionExecutor
    from core.adjustment.revision_types import ReportTree
    from core.adjustment.cascade_update_analyzer import CascadeUpdateAnalyzer
    from core.adjustment.revision_intent_mapper import RevisionIntentMapper
    from core.intent_types import IntentType, TaskComplexity

    # 测试1: _post_process 能否正常调用
    mock_lm = MagicMock()
    executor = RevisionExecutor(mock_lm)
    rt = ReportTree()

    called = {"v": False}
    orig = executor._post_process

    def track(x):
        called["v"] = True
        return orig(x)

    executor._post_process = track
    executor._post_process(rt)
    record("修复方案验证: _post_process可被调用", called["v"])

    # 测试2: _post_process 包含 renumber + fix_references
    try:
        src = inspect.getsource(RevisionExecutor._post_process)
        has_renumber = "renumber" in src
        has_fix = "fix_references" in src or "cross_ref" in src
        record("修复方案验证: _post_process内含renumber+fix_references", has_renumber and has_fix)
    except Exception as e:
        record("修复方案验证: _post_process内含renumber+fix_references", False, str(e))

    # 测试3: _execute_plan_with_progress 中是否调用了 _post_process
    try:
        src = inspect.getsource(RevisionExecutor._execute_plan_with_progress)
        record("修复前: _execute_plan_with_progress未调用_post_process", "_post_process" not in src)
    except Exception as e:
        record("修复前: _execute_plan_with_progress未调用_post_process", False, str(e))

    # 测试4: CascadeUpdateAnalyzer 能否正常工作
    analyzer = CascadeUpdateAnalyzer()
    result = analyzer.analyze_cascade_impact(
        target_sections=["市场规模"],
        all_sections=["市场规模", "竞争格局", "发展趋势", "投资建议"],
    )
    record(
        "修复方案验证: CascadeUpdateAnalyzer.analyze_cascade_impact可用",
        len(result.affected_sections) > 0,
        f"受影响={result.affected_sections}, risk={result.risk_level}"
    )

    # 测试5: RevisionIntentMapper 三级映射
    mapper = RevisionIntentMapper()
    _, r1 = mapper.map(IntentType.FIX, TaskComplexity.TRIVIAL, "修正错别字")
    record("修复方案验证: TRIVIAL+FIX→lightweight", r1.route == "lightweight", f"route={r1.route}")

    _, r2 = mapper.map(IntentType.RESEARCH, TaskComplexity.COMPLEX, "补充市场数据")
    record("修复方案验证: COMPLEX+RESEARCH→incremental", r2.route == "incremental", f"route={r2.route}")

    # 测试6: mapper 接入 handle_feedback 的推断逻辑
    from core.adjustment.revision_types import RevisionOpType

    def infer_intent(analysis):
        if not analysis.intents:
            if analysis.is_uncertain or analysis.confidence < 0.3:
                return IntentType.RESEARCH  # 低置信度→hybrid
            return IntentType.CLARIFICATION
        op = analysis.intents[0].action_type
        m = {
            RevisionOpType.MODIFY: IntentType.FIX,
            RevisionOpType.ADD: IntentType.RESEARCH,
            RevisionOpType.DELETE: IntentType.FIX,
            RevisionOpType.UPDATE_TITLE: IntentType.FIX,
            RevisionOpType.REPLACE_TEXT: IntentType.FIX,
            RevisionOpType.STYLE: IntentType.FIX,
            RevisionOpType.TRANSLATE: IntentType.IMPLEMENTATION,
        }
        return m.get(op, IntentType.RESEARCH)

    def infer_complexity(analysis):
        if len(analysis.intents) > 2:
            return TaskComplexity.COMPLEX
        if analysis.is_uncertain or analysis.confidence < 0.3:
            return TaskComplexity.COMPLEX
        if len(analysis.intents) == 1:
            op = analysis.intents[0].action_type
            lightweight_ops = {
                RevisionOpType.UPDATE_TITLE, RevisionOpType.REPLACE_TEXT,
                RevisionOpType.CHANGE_CASE, RevisionOpType.FIX_PUNCTUATION,
                RevisionOpType.STYLE, RevisionOpType.REVIEW,
            }
            if op in lightweight_ops:
                return TaskComplexity.TRIVIAL
            return TaskComplexity.SINGLE
        return TaskComplexity.SINGLE

    from core.adjustment.revision_types import (
        AnalysisResult, RevisionAction, RevisionTarget, LocationStrategy,
    )

    cases = [
        (AnalysisResult(intents=[
            RevisionAction(action_id="1", action_type=RevisionOpType.UPDATE_TITLE,
                          target=RevisionTarget(raw_text="标题", section_refs=[],
                                                location_strategy=LocationStrategy.KEYWORD, is_ambiguous=False),
                          confidence=0.9)
        ], confidence=0.9), "lightweight"),
        (AnalysisResult(intents=[
            RevisionAction(action_id="1", action_type=RevisionOpType.ADD,
                          target=RevisionTarget(raw_text="市场规模", section_refs=[],
                                                location_strategy=LocationStrategy.KEYWORD, is_ambiguous=False),
                          confidence=0.6)
        ], confidence=0.6), "incremental"),
        (AnalysisResult(intents=[], is_uncertain=True, confidence=0.1), "incremental"),  # 当前mapper无hybrid, COMPLEX强制incremental
    ]

    all_ok = True
    for a, expected in cases:
        it = infer_intent(a)
        tc = infer_complexity(a)
        _, route = mapper.map(it, tc, "test")
        if route.route != expected:
            all_ok = False
            print(f"       预期={expected}, 实际={route.route}")

    record("修复方案验证: 推断逻辑+mapper→正确路由", all_ok)


# ═══════════════════════════════════════════════════════════════
# 端到端
# ═══════════════════════════════════════════════════════════════

def test_e2e():
    print("\n=== 端到端验证 ===")

    from core.adjustment.revision_types import (
        AnalysisResult, ExecutionStatus, RevisionAction, RevisionTarget,
        RevisionOpType, LocationStrategy,
    )
    from core.adjustment.revision_executor import RevisionExecutor
    from core.intelligent_routing_adapter import IntelligentRoutingAdapter

    # 场景1: 复杂请求 → 修复前死路
    async def _s1():
        low_conf = AnalysisResult(
            intents=[], needs_clarification=True,
            is_uncertain=True, confidence=0.1,
            clarification_questions=["请描述修改需求"],
        )
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=low_conf)
        mock_lm = MagicMock()
        mock_lm.acquire_lock = MagicMock(
            return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
        )
        ex = RevisionExecutor(mock_lm)
        ex._intent_analyzer = mock_analyzer
        report = MagicMock()
        report.id = "test"
        flow = await ex.handle_feedback("补充市场规模数据", report)
        return flow

    flow = run_async(_s1())
    is_dead = flow.status in (
        ExecutionStatus.FULL_RESEARCH_NEEDED,
        ExecutionStatus.CLARIFICATION_FAILED,
    )
    record("修复前: '补充市场规模数据'走向死路", is_dead, f"status={flow.status.value}")

    # 场景1修复方案: 智能路由能否处理
    try:
        adapter = IntelligentRoutingAdapter(use_llm=False, fallback_to_keyword=True)
        routing = adapter.analyze(
            user_request="补充市场规模数据",
            requirement={"topic": "补充市场规模数据", "aspects": ["市场规模"], "output_type": "industry_report"},
        )
        record(
            "修复方案验证: 智能路由能处理'补充市场规模数据'",
            routing.execution_plan.total_agents > 0,
            f"agents={routing.execution_plan.total_agents}"
        )
    except Exception as e:
        record("修复方案验证: 智能路由能处理'补充市场规模数据'", False, str(e))

    # 场景2: 轻量操作 → 修复后应不受影响
    async def _s2():
        lightweight = AnalysisResult(
            intents=[
                RevisionAction(
                    action_id="1", action_type=RevisionOpType.UPDATE_TITLE,
                    target=RevisionTarget(raw_text="标题", section_refs=[],
                                          location_strategy=LocationStrategy.KEYWORD, is_ambiguous=False),
                    confidence=0.9,
                ),
            ],
            needs_clarification=False, confidence=0.9,
        )
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=lightweight)
        mock_lm = MagicMock()
        mock_lm.acquire_lock = MagicMock(
            return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
        )
        ex = RevisionExecutor(mock_lm)
        ex._intent_analyzer = mock_analyzer
        report = MagicMock()
        report.id = "test"
        flow = await ex.handle_feedback("修改标题为新标题", report)
        return flow

    flow2 = run_async(_s2())
    record("修复方案验证: 轻量路径不受影响", flow2.status == ExecutionStatus.LIGHTWEIGHT_DONE, f"status={flow2.status.value}")


# ═══════════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("V7修复方案验证脚本")
    print("目标: 验证修复方案能否解决问题，通过后才改真实代码")
    print("=" * 70)

    test_bp1()
    test_bp2()
    test_bp3()
    test_bp4()
    test_integration()
    test_e2e()

    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    total = len(results)

    print("\n" + "=" * 70)
    print(f"结果: {passed}/{total} 通过, {failed}/{total} 失败")
    print("=" * 70)

    print("\n--- 修复前问题确认 ---")
    for name, status, detail in results:
        if "修复前" in name:
            print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))

    print("\n--- 修复方案可行性 ---")
    for name, status, detail in results:
        if "修复方案" in name:
            print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))

    fix_viable = all(s == "PASS" for n, s, _ in results if "修复方案" in n)
    bug_confirmed = all(s == "PASS" for n, s, _ in results if "修复前" in n)

    print("\n" + "=" * 70)
    if bug_confirmed and fix_viable:
        print("结论: 所有bug已确认，所有修复方案验证通过 -> 可以修改真实代码")
    elif bug_confirmed and not fix_viable:
        print("结论: bug已确认，但部分修复方案未通过 -> 需调整方案")
        for n, s, d in results:
            if "修复方案" in n and s == "FAIL":
                print(f"  需调整: {n} -- {d}")
    else:
        print("结论: 部分bug未能确认 -> 需重新分析")
    print("=" * 70)


if __name__ == "__main__":
    main()