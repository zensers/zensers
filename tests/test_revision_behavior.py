"""
修订系统真实行为测试

目标：记录修订系统在真实LLM+真实报告数据下的实际行为
不做预设判断，只记录事实，基于事实再决定修什么

运行: D:\conda\python.exe tests/test_revision_behavior.py
"""

import asyncio
import json
import os
import sys
import time
import traceback

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
for p in (PROJECT_ROOT, SRC_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from src.core.adjustment.report_adapter import SessionReportAdapter
from src.core.adjustment.revision_executor import RevisionExecutor, ProgressNotifier
from src.core.adjustment.revision_types import ExecutionStatus
from src.core.adjustment.report_lock_manager import ReportLockManager
from src.core.intent.revision_intent_analyzer import RevisionIntentAnalyzer
from src.core.adjustment.revision_intent_mapper import RevisionIntentMapper
from src.core.intent_types import IntentType, TaskComplexity

REPORT_PATH = os.path.join(PROJECT_ROOT, "data", "research_e32d301e", "research_result_cache.json")


def load_report():
    with open(REPORT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def make_session(report_data):
    return {
        "session_id": "behavior_test",
        "research_result": {
            "report": {
                "sections": report_data.get("sections", []),
                "key_findings": report_data.get("key_findings", []),
            },
            "topic": report_data.get("topic", ""),
        },
        "_report_version": 0,
    }


SCENARIOS = [
    ("S1-替换文本", "将报告中'归母净利润'替换为'净利润'"),
    ("S2-补充数据", "在核心财务指标章节补充2026年Q2盈利预测"),
    ("S3-修正数据", "修正研发费用113亿元为112亿元"),
    ("S4-新增章节", "新增'投资建议'章节"),
    ("S5-多意图", "更新百分比数据并补充技术分析章节"),
    ("S6-模糊意图", "改一下报告"),
]


async def test_intent_only(user_input, adapter):
    """只测意图分析，不走执行链路"""
    analyzer = RevisionIntentAnalyzer()
    t0 = time.time()
    try:
        result = await analyzer.analyze(user_input, adapter)
        elapsed = time.time() - t0
        return {
            "ok": True,
            "elapsed": round(elapsed, 1),
            "intent_count": len(result.intents),
            "intents": [
                {
                    "action": i.action_type.value,
                    "target": i.target.raw_text[:60] if i.target else "",
                    "confidence": round(i.confidence, 2),
                }
                for i in result.intents
            ],
            "needs_clarification": result.needs_clarification,
            "is_uncertain": result.is_uncertain,
            "overall_confidence": round(result.confidence, 2),
        }
    except Exception as e:
        return {"ok": False, "elapsed": round(time.time() - t0, 1), "error": str(e)}


def test_mapper(intent_result):
    """测路由映射"""
    mapper = RevisionIntentMapper()
    intents = intent_result.get("intents", [])
    if not intents:
        return {"error": "no intents to map"}

    action = intents[0]["action"]
    action_map = {
        "replace_text": IntentType.FIX,
        "update_title": IntentType.FIX,
        "fix_punctuation": IntentType.FIX,
        "change_case": IntentType.FIX,
        "add": IntentType.RESEARCH,
        "modify": IntentType.FIX,
        "delete": IntentType.FIX,
    }
    primary = action_map.get(action, IntentType.FIX)

    lightweight_ops = {"replace_text", "update_title", "change_case", "fix_punctuation", "style", "review"}
    n = len(intents)
    if n > 2:
        complexity = TaskComplexity.COMPLEX
    elif n == 1:
        complexity = TaskComplexity.TRIVIAL if action in lightweight_ops else TaskComplexity.SINGLE
    else:
        complexity = TaskComplexity.SINGLE

    rev_intent, route = mapper.map(primary, complexity, "")
    return {
        "primary_intent": primary.value,
        "complexity": complexity.value,
        "revision_intent": rev_intent.value,
        "route": route.route,
        "route_type": route.type,
        "route_reason": route.reason,
    }


async def test_full_flow(user_input, report_data):
    """走完整修订流程，记录每一步实际行为"""
    session = make_session(report_data)
    adapter = SessionReportAdapter(session)
    lock = ReportLockManager()

    responses = []
    async def capture_prompt(q):
        responses.append({"type": "prompt", "question": q[:100]})
        return "y"

    notifier = ProgressNotifier(prompt_user_callback=capture_prompt)
    executor = RevisionExecutor(lock, notifier=notifier)

    t0 = time.time()
    try:
        flow = await executor.handle_feedback(user_input, adapter)
    except Exception as e:
        return {
            "ok": False,
            "elapsed": round(time.time() - t0, 1),
            "error": str(e),
            "traceback": traceback.format_exc()[-500:],
            "prompts_sent": responses,
        }

    elapsed = time.time() - t0
    result = {
        "ok": True,
        "elapsed": round(elapsed, 1),
        "status": flow.status.value,
        "error": flow.error,
        "task_count": len(flow.tasks),
        "op_types": [t.action.action_type.value for t in flow.tasks] if flow.tasks else [],
        "has_routing_result": hasattr(flow, '_routing_result'),
        "prompts_sent": responses,
        "has_plan": flow.plan is not None,
        "plan_actions": [a.action_type.value for a in flow.plan.actions] if flow.plan else [],
    }

    if hasattr(flow, '_routing_result') and flow._routing_result is not None:
        rr = flow._routing_result
        result["routing_info"] = {
            "phases": len(rr.execution_plan.phases),
            "agents": rr.execution_plan.total_agents,
            "intent_confidence": round(rr.intent_result.intent_confidence, 2),
        }

    return result


async def main():
    report_data = load_report()
    sections = report_data.get("sections", [])
    print("=" * 80)
    print("修订系统真实行为测试")
    print("=" * 80)
    print(f"报告: {report_data.get('topic', '?')}")
    print(f"章节数: {len(sections)}")
    for s in sections:
        print(f"  - {s.get('title', s.get('id', '?'))}")

    # ====== Phase 1: 意图识别 ======
    print("\n" + "=" * 80)
    print("Phase 1: 意图识别 (LLM直接分析, 不走执行)")
    print("=" * 80)

    intent_results = {}
    for name, user_input in SCENARIOS:
        session = make_session(report_data)
        adapter = SessionReportAdapter(session)
        print(f"\n--- {name} ---")
        print(f"  输入: {user_input}")

        ir = await test_intent_only(user_input, adapter)
        intent_results[name] = ir

        if ir["ok"]:
            print(f"  意图数: {ir['intent_count']}, 耗时: {ir['elapsed']}s")
            for i, intent in enumerate(ir["intents"]):
                print(f"    [{i+1}] {intent['action']} | target='{intent['target']}' | conf={intent['confidence']}")
            print(f"  需澄清: {ir['needs_clarification']}, 不确定: {ir['is_uncertain']}, 综合置信度: {ir['overall_confidence']}")
        else:
            print(f"  [失败] {ir.get('error', '?')}")

    # ====== Phase 2: 路由映射 ======
    print("\n" + "=" * 80)
    print("Phase 2: 路由映射 (基于Phase1意图结果)")
    print("=" * 80)

    for name, ir in intent_results.items():
        if not ir["ok"] or not ir["intents"]:
            print(f"\n--- {name}: 跳过(无意图) ---")
            continue
        print(f"\n--- {name} ---")
        mr = test_mapper(ir)
        if "error" in mr:
            print(f"  [错误] {mr['error']}")
        else:
            print(f"  primary={mr['primary_intent']}, complexity={mr['complexity']}")
            print(f"  route={mr['route']}, type={mr['route_type']}, reason={mr['route_reason']}")

    # ====== Phase 3: 完整流程 ======
    print("\n" + "=" * 80)
    print("Phase 3: 完整修订流程 (意图→路由→执行)")
    print("=" * 80)

    for name, user_input in SCENARIOS:
        print(f"\n--- {name} ---")
        print(f"  输入: {user_input}")

        fr = await test_full_flow(user_input, report_data)

        if not fr["ok"]:
            print(f"  [异常] {fr.get('error', '?')}")
            if "traceback" in fr:
                print(f"  堆栈: {fr['traceback'][:200]}")
            continue

        print(f"  状态: {fr['status']}, 耗时: {fr['elapsed']}s")
        if fr["error"]:
            print(f"  错误: {fr['error'][:100]}")
        print(f"  任务数: {fr['task_count']}, 操作类型: {fr['op_types']}")
        print(f"  有路由结果: {fr['has_routing_result']}")
        print(f"  有计划: {fr['has_plan']}, 计划操作: {fr['plan_actions']}")
        print(f"  SSE交互次数: {len(fr['prompts_sent'])}")
        if "routing_info" in fr:
            ri = fr["routing_info"]
            print(f"  路由详情: phases={ri['phases']}, agents={ri['agents']}, conf={ri['intent_confidence']}")

    # ====== Phase 4: 代码路径覆盖 ======
    print("\n" + "=" * 80)
    print("Phase 4: 代码路径检查 (静态分析)")
    print("=" * 80)

    import inspect
    from src.core.adjustment.revision_executor import RevisionExecutor as RE

    src = inspect.getsource(RE)

    checks = [
        ("_analyze_revision_route被handle_feedback调用", "_analyze_revision_route" in src and src.count("_analyze_revision_route") >= 2),
        ("_analyze_cascade_impact被handle_feedback调用", "_analyze_cascade_impact" in src and src.count("_analyze_cascade_impact") >= 2),
        ("_post_process在handle_feedback中调用", "_post_process" in src[src.find("handle_feedback"):]),
        ("_handle_unknown_intent接收user_message参数", "user_message" in inspect.getsource(RE._handle_unknown_intent)),
        ("_handle_unknown_intent路由到IntelligentRoutingAdapter", "IntelligentRoutingAdapter" in inspect.getsource(RE._handle_unknown_intent)),
        ("_intent_mapper在__init__中实例化", hasattr(RE, '__init__') and '_intent_mapper' in inspect.getsource(RE.__init__)),
    ]

    for desc, passed in checks:
        tag = "[OK]" if passed else "[!!]"
        print(f"  {tag} {desc}")

    dead_code = [desc for desc, p in checks if not p]
    if dead_code:
        print(f"\n  警告: 以下方法/逻辑已定义但未被调用(死代码):")
        for d in dead_code:
            print(f"    - {d}")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
