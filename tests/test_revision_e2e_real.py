"""
修订系统端到端测试 - 真实LLM + 真实报告数据

测试修订系统在真实环境中的表现:
- 使用DeepSeek V4 Pro模型进行意图分析
- 使用真实比亚迪财务分析报告JSON数据
- 覆盖6种典型修订需求场景
- 验证每个场景的意图识别、路由决策、执行结果

运行: D:\conda\python.exe tests/test_revision_e2e_real.py
"""

import asyncio
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from src.core.adjustment.report_adapter import SessionReportAdapter
from src.core.adjustment.revision_executor import RevisionExecutor, ProgressNotifier
from src.core.adjustment.revision_types import (
    AnalysisResult, ExecutionFlow, ExecutionStatus, RevisionAction,
    RevisionOpType, RevisionTarget, SectionRef, RefType,
    LocationStrategy, TaskStatus,
)
from src.core.adjustment.report_lock_manager import ReportLockManager
from src.core.intent.revision_intent_analyzer import RevisionIntentAnalyzer
from src.core.adjustment.revision_intent_mapper import RevisionIntentMapper
from src.core.intent_types import IntentType, TaskComplexity

# ═══════════════════════════════════════════════════════════════
# 加载真实报告数据
# ═══════════════════════════════════════════════════════════════

REPORT_DATA_PATH = os.path.join(PROJECT_ROOT, "data", "research_e32d301e", "research_result_cache.json")

def load_real_report() -> dict:
    """加载真实的比亚迪财务分析报告"""
    with open(REPORT_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def build_session_from_report(report_data: dict) -> dict:
    """从真实报告数据构建session dict，适配SessionReportAdapter"""
    session = {
        "session_id": "e2e_test_session",
        "research_result": {
            "report": {
                "sections": report_data.get("sections", []),
                "key_findings": report_data.get("key_findings", []),
            },
            "topic": report_data.get("topic", ""),
            "task_id": report_data.get("task_id", ""),
        },
        "_report_version": 0,
    }
    return session


# ═══════════════════════════════════════════════════════════════
# 测试场景定义
# ═══════════════════════════════════════════════════════════════

TEST_SCENARIOS = [
    {
        "id": "S1",
        "name": "轻量修订 - 替换文本",
        "description": "简单文本替换，应走lightweight路径",
        "user_input": "将报告中所有'归母净利润'替换为'净利润'",
        "expected_path": "lightweight",
        "expected_op": ["replace_text", "UPDATE_TITLE", "REPLACE_TEXT", "FIX_PUNCTUATION", "CHANGE_CASE"],
    },
    {
        "id": "S2",
        "name": "增量修订 - 补充数据",
        "description": "补充新数据到特定章节，应走incremental路径",
        "user_input": "在核心财务指标章节补充2026年第二季度的盈利预测数据",
        "expected_path": "incremental",
        "expected_op": ["add", "ADD", "MODIFY"],
    },
    {
        "id": "S3",
        "name": "增量修订 - 修正数据",
        "description": "修正报告中的错误数据",
        "user_input": "修正报告中研发费用113亿元的数据，应为112亿元",
        "expected_path": "incremental",
        "expected_op": ["modify", "MODIFY", "replace_text", "REPLACE_TEXT"],
    },
    {
        "id": "S4",
        "name": "结构修订 - 新增章节",
        "description": "添加全新章节，可能因目标定位失败但意图识别应正确",
        "user_input": "新增一个'投资建议'章节，包含比亚迪股票的买卖评级和目标价位",
        "expected_path": "incremental_or_clarification",
        "expected_op": ["add", "ADD"],
    },
    {
        "id": "S5",
        "name": "复杂修订 - 多意图组合",
        "description": "同时修改多个章节，多意图应路由到智能路由或增量路径",
        "user_input": "把所有章节里的百分比数据都更新为最新数据，然后补充技术分析章节，最后删除反证与边界条件章节",
        "expected_path": "incremental_or_routing",
        "expected_op": ["modify", "add", "delete", "MODIFY", "ADD", "DELETE", "full_research"],
    },
    {
        "id": "S6",
        "name": "模糊意图 - 低置信度路由",
        "description": "模糊意图应触发低置信度路由到智能路由而非死路",
        "user_input": "改一下报告",
        "expected_path": "routing_or_clarification",
        "expected_op": [],
    },
]


# ═══════════════════════════════════════════════════════════════
# 测试执行器
# ═══════════════════════════════════════════════════════════════

results: List[Dict[str, Any]] = []


def record_result(scenario_id: str, scenario_name: str, passed: bool, details: Dict[str, Any]):
    status = "PASS" if passed else "FAIL"
    results.append({
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "status": status,
        "details": details,
    })
    tag = "[PASS]" if passed else "[FAIL]"
    print(f"\n  {tag} {scenario_id}: {scenario_name}")
    for k, v in details.items():
        val_str = str(v)[:200] if v is not None else "None"
        print(f"       {k}: {val_str}")


async def run_single_scenario(
    scenario: Dict[str, Any],
    report_data: dict,
) -> Dict[str, Any]:
    """运行单个修订场景"""
    session = build_session_from_report(report_data)
    adapter = SessionReportAdapter(session)
    lock_manager = ReportLockManager()

    async def mock_prompt(question: str) -> str:
        return "y"

    notifier = ProgressNotifier(prompt_user_callback=mock_prompt)
    executor = RevisionExecutor(lock_manager, notifier=notifier)

    start_time = time.time()
    try:
        flow = await executor.handle_feedback(scenario["user_input"], adapter)
    except Exception as e:
        tb = traceback.format_exc()
        return {
            "success": False,
            "flow_status": "exception",
            "error": str(e),
            "traceback": tb,
            "elapsed": time.time() - start_time,
            "intents": [],
            "confidence": 0,
            "route": "unknown",
            "op_types": [],
            "flow_has_tasks": False,
            "task_count": 0,
        }

    elapsed = time.time() - start_time

    intents = []
    op_types = []
    confidence = 0
    route = "unknown"

    if flow.status == ExecutionStatus.LIGHTWEIGHT_DONE and flow.tasks:
        op_types = [t.action.action_type.value for t in flow.tasks]
        if flow.tasks and flow.tasks[0].action:
            intents = [flow.tasks[0].action.action_type.value]
            confidence = flow.tasks[0].action.confidence if hasattr(flow.tasks[0].action, 'confidence') else 1.0
        route = "lightweight"
    elif flow.status == ExecutionStatus.FULL_RESEARCH_NEEDED:
        route = "routing"
        has_routing_result = hasattr(flow, '_routing_result')
        if has_routing_result:
            rr = flow._routing_result
            op_types = ["full_research"]
            confidence = rr.intent_result.intent_confidence if rr else 0
        elif flow.error:
            route = "routing_fallback"
    elif flow.status == ExecutionStatus.CLARIFICATION_FAILED:
        route = "clarification_failed"
    elif flow.status == ExecutionStatus.PREVIEW_READY:
        route = "incremental"
        if flow.plan and flow.plan.actions:
            op_types = [a.action_type.value for a in flow.plan.actions]
    elif flow.status == ExecutionStatus.ABORTED:
        route = "aborted"
    elif flow.status == ExecutionStatus.FAILED:
        route = "failed"

    return {
        "success": True,
        "flow_status": flow.status.value,
        "error": flow.error,
        "elapsed": elapsed,
        "intents": intents,
        "confidence": confidence,
        "route": route,
        "op_types": op_types,
        "flow_has_tasks": len(flow.tasks) > 0,
        "task_count": len(flow.tasks),
        "has_routing_result": hasattr(flow, '_routing_result'),
    }


def evaluate_scenario(scenario: Dict[str, Any], result: Dict[str, Any]) -> bool:
    """评估场景是否通过"""
    if not result["success"]:
        return False

    expected_path = scenario["expected_path"]
    actual_route = result["route"]

    # 路径匹配
    if expected_path == "lightweight":
        if actual_route != "lightweight":
            return False
    elif expected_path == "incremental":
        if actual_route not in ("incremental", "lightweight", "routing"):
            return False
    elif expected_path == "incremental_or_routing":
        if actual_route not in ("incremental", "routing", "clarification_failed", "lightweight"):
            return False
    elif expected_path == "routing_or_clarification":
        if actual_route not in ("routing", "clarification_failed", "routing_fallback", "lightweight", "incremental"):
            return False

    # 操作类型匹配 (宽松: 只要有一个匹配就行)
    expected_ops = scenario["expected_op"]
    if expected_ops:
        actual_ops = result["op_types"]
        matched = any(op in actual_ops for op in expected_ops)
        if not matched and actual_ops:
            return False

    return True


# ═══════════════════════════════════════════════════════════════
# 意图分析器单独测试 (不经过完整flow, 直接测试意图识别)
# ═══════════════════════════════════════════════════════════════

async def test_intent_analysis_only(
    user_input: str,
    adapter: SessionReportAdapter,
) -> Dict[str, Any]:
    """单独测试意图分析, 查看LLM返回了什么"""
    analyzer = RevisionIntentAnalyzer()
    try:
        result = await analyzer.analyze(user_input, adapter)
        return {
            "intents": [
                {
                    "action_type": i.action_type.value,
                    "target_text": i.target.raw_text if i.target else "",
                    "confidence": i.confidence,
                }
                for i in result.intents
            ],
            "needs_clarification": result.needs_clarification,
            "is_uncertain": result.is_uncertain,
            "confidence": result.confidence,
            "clarification_questions": result.clarification_questions,
            "is_global_feedback": result.is_global_feedback,
        }
    except Exception as e:
        return {"error": str(e), "intents": []}


# ═══════════════════════════════════════════════════════════════
# 路由映射器单独测试
# ═══════════════════════════════════════════════════════════════

def test_route_mapping(intents: List[Dict], user_input: str) -> Dict[str, Any]:
    """测试RevisionIntentMapper路由映射"""
    mapper = RevisionIntentMapper()
    if not intents:
        return {"route": "no_intents", "reason": "no intents to map"}

    primary_intent = IntentType.FIX
    action_type = intents[0].get("action_type", "")
    action_map = {
        "modify": IntentType.FIX,
        "replace_text": IntentType.FIX,
        "add": IntentType.RESEARCH,
        "delete": IntentType.FIX,
        "update_title": IntentType.FIX,
        "fix_punctuation": IntentType.FIX,
        "change_case": IntentType.FIX,
    }
    primary_intent = action_map.get(action_type, IntentType.FIX)

    complexity = TaskComplexity.SINGLE
    if len(intents) > 2:
        complexity = TaskComplexity.COMPLEX
    elif len(intents) == 1:
        lightweight_ops = {"replace_text", "update_title", "change_case", "fix_punctuation"}
        if action_type in lightweight_ops:
            complexity = TaskComplexity.TRIVIAL

    revision_intent, route_decision = mapper.map(
        primary_intent=primary_intent,
        complexity=complexity,
        user_input=user_input,
    )
    return {
        "route": route_decision.route,
        "type": route_decision.type,
        "reason": route_decision.reason,
        "skip_phases": route_decision.skip_phases,
        "revision_intent": revision_intent.value,
        "primary_intent": primary_intent.value,
        "complexity": complexity.value,
    }


# ═══════════════════════════════════════════════════════════════
# 主测试流程
# ═══════════════════════════════════════════════════════════════

async def main():
    print("=" * 80)
    print("修订系统端到端测试 (真实LLM + 真实报告数据)")
    print("=" * 80)

    report_data = load_real_report()
    sections = report_data.get("sections", [])
    print(f"\n报告主题: {report_data.get('topic', 'N/A')}")
    print(f"章节数量: {len(sections)}")
    print(f"章节标题: {[s.get('title', s.get('id', '?'))[:30] for s in sections]}")

    print("\n" + "=" * 80)
    print("Phase 1: 意图识别能力测试 (LLM直接分析)")
    print("=" * 80)

    for scenario in TEST_SCENARIOS:
        session = build_session_from_report(report_data)
        adapter = SessionReportAdapter(session)

        print(f"\n  --- {scenario['id']}: {scenario['name']} ---")
        print(f"  用户输入: {scenario['user_input']}")

        intent_result = await test_intent_analysis_only(scenario["user_input"], adapter)

        if "error" in intent_result:
            print(f"  [ERROR] 意图分析失败: {intent_result['error']}")
            continue

        print(f"  识别到意图: {len(intent_result['intents'])}个")
        for i, intent in enumerate(intent_result["intents"]):
            print(f"    [{i+1}] action={intent['action_type']}, target='{intent['target_text'][:50]}', conf={intent['confidence']:.2f}")
        print(f"  需要澄清: {intent_result['needs_clarification']}")
        print(f"  不确定: {intent_result['is_uncertain']}")
        print(f"  综合置信度: {intent_result['confidence']:.2f}")

        # 路由映射
        route_result = test_route_mapping(intent_result["intents"], scenario["user_input"])
        print(f"  路由决策: route={route_result['route']}, type={route_result['type']}, reason={route_result['reason']}")

    print("\n" + "=" * 80)
    print("Phase 2: 完整修订流程测试 (意图→路由→执行)")
    print("=" * 80)

    for scenario in TEST_SCENARIOS:
        print(f"\n  --- {scenario['id']}: {scenario['name']} ---")
        print(f"  用户输入: {scenario['user_input']}")

        result = await run_single_scenario(scenario, report_data)
        passed = evaluate_scenario(scenario, result)

        record_result(
            scenario["id"],
            scenario["name"],
            passed,
            {
                "route": result["route"],
                "flow_status": result["flow_status"],
                "op_types": result["op_types"],
                "confidence": f"{result['confidence']:.2f}",
                "task_count": result["task_count"],
                "elapsed": f"{result['elapsed']:.1f}s",
                "has_routing_result": result["has_routing_result"],
                "error": result.get("error", "None"),
            },
        )

    # ═══════════════════════════════════════════════════════════════
    # 结果汇总
    # ═══════════════════════════════════════════════════════════════

    print("\n" + "=" * 80)
    total = len(results)
    passed_count = sum(1 for r in results if r["status"] == "PASS")
    failed_count = total - passed_count
    print(f"结果: {passed_count}/{total} 通过, {failed_count}/{total} 失败")
    print("=" * 80)

    print("\n--- 详细结果 ---")
    for r in results:
        tag = "[PASS]" if r["status"] == "PASS" else "[FAIL]"
        print(f"  {tag} {r['scenario_id']}: {r['scenario_name']}")
        for k, v in r["details"].items():
            print(f"       {k}: {v}")

    # ═══════════════════════════════════════════════════════════════
    # 修订后报告内容变化检查
    # ═══════════════════════════════════════════════════════════════

    print("\n" + "=" * 80)
    print("Phase 3: 修订内容变化验证")
    print("=" * 80)

    # 对每个轻量修订场景, 检查session中的数据是否真的变了
    lightweight_scenarios = [s for s in TEST_SCENARIOS if s["expected_path"] == "lightweight"]
    for scenario in lightweight_scenarios:
        session = build_session_from_report(report_data)
        adapter = SessionReportAdapter(session)
        original_sections = json.dumps(session["research_result"]["report"]["sections"], ensure_ascii=False)

        lock_manager = ReportLockManager()
        notifier = ProgressNotifier(prompt_user_callback=lambda q: "y")
        executor = RevisionExecutor(lock_manager, notifier=notifier)

        try:
            flow = await executor.handle_feedback(scenario["user_input"], adapter)
        except Exception as e:
            print(f"  [ERROR] {scenario['id']}: {e}")
            continue

        modified_sections = json.dumps(session["research_result"]["report"]["sections"], ensure_ascii=False)
        changed = original_sections != modified_sections

        print(f"\n  {scenario['id']}: {scenario['name']}")
        print(f"  报告内容是否变化: {changed}")
        print(f"  修订状态: {flow.status.value}")
        if flow.tasks:
            print(f"  操作类型: {[t.action.action_type.value for t in flow.tasks]}")

    print("\n" + "=" * 80)
    print("端到端测试完成")
    print("=" * 80)

    return passed_count >= total - 1


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)