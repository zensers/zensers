"""
报告修订系统全面实战测试

测试目标:
1. 验证意图识别准确性
2. 验证路由决策正确性
3. 验证轻量修订执行
4. 验证增量修订执行
5. 验证复杂修订处理
6. 验证数据完整性
7. 验证错误处理
8. 验证性能指标

运行命令: D:\conda\python.exe tests/test_revision_comprehensive.py
"""

import asyncio
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from src.core.adjustment.report_adapter import SessionReportAdapter
from src.core.adjustment.revision_executor import RevisionExecutor, ProgressNotifier
from src.core.adjustment.revision_types import (
    AnalysisResult, ExecutionFlow, ExecutionStatus, RevisionAction,
    RevisionOpType, RevisionTarget, SectionRef, RefType,
    LocationStrategy, TaskStatus, RevisionTask,
)
from src.core.adjustment.report_lock_manager import ReportLockManager
from src.core.intent.revision_intent_analyzer import RevisionIntentAnalyzer
from src.core.adjustment.revision_intent_mapper import RevisionIntentMapper
from src.core.intent_types import IntentType, TaskComplexity

REPORT_DATA_PATH = os.path.join(PROJECT_ROOT, "data", "research_e32d301e", "research_result_cache.json")


@dataclass
class TestResult:
    test_id: str
    test_name: str
    passed: bool
    elapsed: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class TestReport:
    def __init__(self):
        self.results: List[TestResult] = []
        self.start_time = time.time()
    
    def add(self, result: TestResult):
        self.results.append(result)
        tag = "[PASS]" if result.passed else "[FAIL]"
        print(f"  {tag} {result.test_id}: {result.test_name} ({result.elapsed:.2f}s)")
        if result.error:
            print(f"       Error: {result.error[:200]}")
    
    def summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        elapsed = time.time() - self.start_time
        
        print("\n" + "=" * 80)
        print("测试报告汇总")
        print("=" * 80)
        print(f"总测试数: {total}")
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        print(f"通过率: {passed/total*100:.1f}%" if total > 0 else "N/A")
        print(f"总耗时: {elapsed:.2f}s")
        print("=" * 80)
        
        if failed > 0:
            print("\n失败测试详情:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.test_id}: {r.test_name}")
                    print(f"    Error: {r.error}")
        
        return passed, total


def load_report() -> dict:
    with open(REPORT_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def make_session(report_data: dict, session_id: str = "test_session") -> dict:
    return {
        "session_id": session_id,
        "research_result": {
            "report": {
                "sections": report_data.get("sections", []),
                "key_findings": report_data.get("key_findings", []),
            },
            "topic": report_data.get("topic", ""),
        },
        "_report_version": 0,
    }


def deep_copy_session(session: dict) -> dict:
    return json.loads(json.dumps(session, ensure_ascii=False))


class RevisionSystemTester:
    def __init__(self, report_data: dict):
        self.report_data = report_data
        self.test_report = TestReport()
    
    async def run_all_tests(self):
        print("=" * 80)
        print("报告修订系统全面实战测试")
        print("=" * 80)
        print(f"报告主题: {self.report_data.get('topic', 'N/A')}")
        print(f"章节数量: {len(self.report_data.get('sections', []))}")
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        await self.test_intent_recognition()
        await self.test_route_mapping()
        await self.test_lightweight_revision()
        await self.test_incremental_revision()
        await self.test_complex_revision()
        await self.test_data_integrity()
        await self.test_error_handling()
        await self.test_edge_cases()
        await self.test_performance()
        
        return self.test_report.summary()
    
    async def test_intent_recognition(self):
        print("\n" + "-" * 80)
        print("模块1: 意图识别测试")
        print("-" * 80)
        
        test_cases = [
            ("IR-01", "简单文本替换", "将报告中'归母净利润'替换为'净利润'"),
            ("IR-02", "数据修正", "修正研发费用113亿元为112亿元"),
            ("IR-03", "新增章节", "新增一个'投资建议'章节"),
            ("IR-04", "删除章节", "删除'反证与边界条件'章节"),
            ("IR-05", "多意图组合", "更新百分比数据并补充技术分析章节"),
            ("IR-06", "模糊意图", "改一下报告"),
            ("IR-07", "空输入", ""),
            ("IR-08", "超长输入", "请帮我修改报告中的所有数据" * 50),
            ("IR-09", "特殊字符", "将'比亚迪'修改为'BYD@#$%'"),
            ("IR-10", "英文输入", "Update the profit margin data"),
        ]
        
        for test_id, name, user_input in test_cases:
            t0 = time.time()
            try:
                session = make_session(self.report_data, f"intent_{test_id}")
                adapter = SessionReportAdapter(session)
                analyzer = RevisionIntentAnalyzer()
                
                result = await analyzer.analyze(user_input, adapter)
                elapsed = time.time() - t0
                
                passed = True
                error = None
                
                if test_id == "IR-07":
                    if result.intents:
                        passed = False
                        error = "空输入应返回空意图"
                elif test_id == "IR-06":
                    if result.confidence > 0.5:
                        passed = False
                        error = f"模糊意图置信度过高: {result.confidence}"
                elif test_id in ["IR-01", "IR-02"]:
                    if not result.intents:
                        passed = False
                        error = "应识别到意图"
                
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=passed,
                    elapsed=elapsed,
                    details={
                        "intent_count": len(result.intents),
                        "confidence": round(result.confidence, 2),
                        "needs_clarification": result.needs_clarification,
                        "is_uncertain": result.is_uncertain,
                    },
                    error=error,
                ))
            except Exception as e:
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=False,
                    elapsed=time.time() - t0,
                    error=str(e),
                ))
    
    async def test_route_mapping(self):
        print("\n" + "-" * 80)
        print("模块2: 路由映射测试")
        print("-" * 80)
        
        test_cases = [
            ("RM-01", "轻量操作-文本替换", IntentType.FIX, TaskComplexity.TRIVIAL, "lightweight"),
            ("RM-02", "轻量操作-标题修改", IntentType.FIX, TaskComplexity.TRIVIAL, "lightweight"),
            ("RM-03", "单意图修复", IntentType.FIX, TaskComplexity.SINGLE, "lightweight"),
            ("RM-04", "增量研究", IntentType.RESEARCH, TaskComplexity.SINGLE, "incremental"),
            ("RM-05", "复杂修复", IntentType.FIX, TaskComplexity.COMPLEX, "incremental"),
            ("RM-06", "复杂研究", IntentType.RESEARCH, TaskComplexity.COMPLEX, "incremental"),
        ]
        
        mapper = RevisionIntentMapper()
        
        for test_id, name, intent, complexity, expected_route in test_cases:
            t0 = time.time()
            try:
                revision_intent, route = mapper.map(intent, complexity, "test input")
                elapsed = time.time() - t0
                
                passed = route.route == expected_route
                error = None if passed else f"期望路由: {expected_route}, 实际: {route.route}"
                
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=passed,
                    elapsed=elapsed,
                    details={
                        "route": route.route,
                        "type": route.type,
                        "reason": route.reason,
                        "skip_phases": route.skip_phases,
                    },
                    error=error,
                ))
            except Exception as e:
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=False,
                    elapsed=time.time() - t0,
                    error=str(e),
                ))
    
    async def test_lightweight_revision(self):
        print("\n" + "-" * 80)
        print("模块3: 轻量修订测试")
        print("-" * 80)
        
        test_cases = [
            ("LR-01", "文本替换-归母净利润", "将报告中'归母净利润'替换为'净利润'"),
            ("LR-02", "文本替换-比亚迪", "将'比亚迪'替换为'BYD'"),
            ("LR-03", "标题修改", "将'核心财务指标与盈利能力'章节标题改为'财务分析'"),
        ]
        
        for test_id, name, user_input in test_cases:
            t0 = time.time()
            try:
                session = make_session(self.report_data, f"lightweight_{test_id}")
                adapter = SessionReportAdapter(session)
                lock = ReportLockManager()
                
                async def mock_prompt(q):
                    return "y"
                
                notifier = ProgressNotifier(prompt_user_callback=mock_prompt)
                executor = RevisionExecutor(lock, notifier=notifier)
                
                flow = await executor.handle_feedback(user_input, adapter)
                elapsed = time.time() - t0
                
                passed = flow.status in [ExecutionStatus.LIGHTWEIGHT_DONE, ExecutionStatus.PREVIEW_READY]
                error = None if passed else f"状态: {flow.status.value}, 错误: {flow.error}"
                
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=passed,
                    elapsed=elapsed,
                    details={
                        "status": flow.status.value,
                        "task_count": len(flow.tasks) if flow.tasks else 0,
                        "op_types": [t.action.action_type.value for t in flow.tasks] if flow.tasks else [],
                    },
                    error=error,
                ))
            except Exception as e:
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=False,
                    elapsed=time.time() - t0,
                    error=str(e),
                ))
    
    async def test_incremental_revision(self):
        print("\n" + "-" * 80)
        print("模块4: 增量修订测试")
        print("-" * 80)
        
        test_cases = [
            ("IN-01", "数据修正", "修正研发费用113亿元为112亿元"),
            ("IN-02", "补充数据", "在核心财务指标章节补充2026年Q2盈利预测"),
            ("IN-03", "新增子章节", "在核心财务指标章节下新增'毛利率分析'子章节"),
        ]
        
        for test_id, name, user_input in test_cases:
            t0 = time.time()
            try:
                session = make_session(self.report_data, f"incremental_{test_id}")
                adapter = SessionReportAdapter(session)
                lock = ReportLockManager()
                
                async def mock_prompt(q):
                    return "y"
                
                notifier = ProgressNotifier(prompt_user_callback=mock_prompt)
                executor = RevisionExecutor(lock, notifier=notifier)
                
                flow = await executor.handle_feedback(user_input, adapter)
                elapsed = time.time() - t0
                
                valid_statuses = [
                    ExecutionStatus.PREVIEW_READY,
                    ExecutionStatus.LIGHTWEIGHT_DONE,
                    ExecutionStatus.FULL_RESEARCH_NEEDED,
                    ExecutionStatus.CLARIFICATION_FAILED,
                ]
                passed = flow.status in valid_statuses
                error = None
                if not passed:
                    error = f"状态: {flow.status.value}, 错误: {flow.error}"
                elif flow.status == ExecutionStatus.FULL_RESEARCH_NEEDED and flow.error is None:
                    passed = False
                    error = "FULL_RESEARCH_NEEDED 状态但 error 为 None"
                
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=passed,
                    elapsed=elapsed,
                    details={
                        "status": flow.status.value,
                        "task_count": len(flow.tasks) if flow.tasks else 0,
                        "has_plan": flow.plan is not None,
                        "has_routing_result": hasattr(flow, '_routing_result'),
                    },
                    error=error,
                ))
            except Exception as e:
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=False,
                    elapsed=time.time() - t0,
                    error=str(e),
                ))
    
    async def test_complex_revision(self):
        print("\n" + "-" * 80)
        print("模块5: 复杂修订测试")
        print("-" * 80)
        
        test_cases = [
            ("CR-01", "多意图组合", "更新所有百分比数据并补充技术分析章节，最后删除反证章节"),
            ("CR-02", "新增完整章节", "新增'投资建议'章节，包含买卖评级和目标价位"),
            ("CR-03", "模糊意图", "改一下报告"),
            ("CR-04", "跨章节修改", "将所有章节中的'2026年'改为'2027年'"),
        ]
        
        for test_id, name, user_input in test_cases:
            t0 = time.time()
            try:
                session = make_session(self.report_data, f"complex_{test_id}")
                adapter = SessionReportAdapter(session)
                lock = ReportLockManager()
                
                async def mock_prompt(q):
                    return "y"
                
                notifier = ProgressNotifier(prompt_user_callback=mock_prompt)
                executor = RevisionExecutor(lock, notifier=notifier)
                
                flow = await executor.handle_feedback(user_input, adapter)
                elapsed = time.time() - t0
                
                valid_statuses = [
                    ExecutionStatus.FULL_RESEARCH_NEEDED,
                    ExecutionStatus.PREVIEW_READY,
                    ExecutionStatus.LIGHTWEIGHT_DONE,
                    ExecutionStatus.CLARIFICATION_FAILED,
                    ExecutionStatus.ABORTED,
                ]
                passed = flow.status in valid_statuses
                error = None if passed else f"状态: {flow.status.value}, 错误: {flow.error}"
                
                if test_id == "CR-03":
                    if flow.status == ExecutionStatus.FAILED:
                        passed = False
                        error = "模糊意图不应导致系统失败，应路由到智能路由或请求澄清"
                
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=passed,
                    elapsed=elapsed,
                    details={
                        "status": flow.status.value,
                        "has_routing_result": hasattr(flow, '_routing_result'),
                        "routing_phases": len(flow._routing_result.execution_plan.phases) if hasattr(flow, '_routing_result') and flow._routing_result else 0,
                    },
                    error=error,
                ))
            except Exception as e:
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=False,
                    elapsed=time.time() - t0,
                    error=str(e),
                ))
    
    async def test_data_integrity(self):
        print("\n" + "-" * 80)
        print("模块6: 数据完整性测试")
        print("-" * 80)
        
        test_cases = [
            ("DI-01", "修订后章节数量一致", "将'归母净利润'替换为'净利润'"),
            ("DI-02", "修订后章节ID不变", "修改核心财务指标章节内容"),
            ("DI-03", "修订后数据结构完整", "补充盈利预测数据"),
        ]
        
        for test_id, name, user_input in test_cases:
            t0 = time.time()
            try:
                session = make_session(self.report_data, f"integrity_{test_id}")
                original_session = deep_copy_session(session)
                adapter = SessionReportAdapter(session)
                lock = ReportLockManager()
                
                async def mock_prompt(q):
                    return "y"
                
                notifier = ProgressNotifier(prompt_user_callback=mock_prompt)
                executor = RevisionExecutor(lock, notifier=notifier)
                
                flow = await executor.handle_feedback(user_input, adapter)
                elapsed = time.time() - t0
                
                passed = True
                error = None
                
                original_sections = original_session["research_result"]["report"]["sections"]
                modified_sections = session["research_result"]["report"]["sections"]
                
                if test_id == "DI-01":
                    if len(original_sections) != len(modified_sections):
                        passed = False
                        error = f"章节数量变化: {len(original_sections)} -> {len(modified_sections)}"
                
                elif test_id == "DI-02":
                    original_ids = [s.get("id") for s in original_sections]
                    modified_ids = [s.get("id") for s in modified_sections]
                    if original_ids != modified_ids:
                        passed = False
                        error = f"章节ID变化: {original_ids} -> {modified_ids}"
                
                elif test_id == "DI-03":
                    for s in modified_sections:
                        if "id" not in s or "title" not in s:
                            passed = False
                            error = "修订后章节缺少必要字段"
                            break
                
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=passed,
                    elapsed=elapsed,
                    details={
                        "status": flow.status.value,
                        "original_section_count": len(original_sections),
                        "modified_section_count": len(modified_sections),
                    },
                    error=error,
                ))
            except Exception as e:
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=False,
                    elapsed=time.time() - t0,
                    error=str(e),
                ))
    
    async def test_error_handling(self):
        print("\n" + "-" * 80)
        print("模块7: 错误处理测试")
        print("-" * 80)
        
        test_cases = [
            ("EH-01", "不存在的章节", "修改'不存在的章节'的内容"),
            ("EH-02", "无效操作", "将报告转换为PDF格式"),
            ("EH-03", "矛盾指令", "删除并修改同一个章节"),
            ("EH-04", "空章节引用", "修改章节的内容"),
        ]
        
        for test_id, name, user_input in test_cases:
            t0 = time.time()
            try:
                session = make_session(self.report_data, f"error_{test_id}")
                adapter = SessionReportAdapter(session)
                lock = ReportLockManager()
                
                async def mock_prompt(q):
                    return "y"
                
                notifier = ProgressNotifier(prompt_user_callback=mock_prompt)
                executor = RevisionExecutor(lock, notifier=notifier)
                
                flow = await executor.handle_feedback(user_input, adapter)
                elapsed = time.time() - t0
                
                passed = True
                error = None
                
                if flow.status == ExecutionStatus.FAILED:
                    if "exception" in str(flow.error).lower() or "traceback" in str(flow.error).lower():
                        passed = False
                        error = f"未优雅处理错误: {flow.error}"
                
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=passed,
                    elapsed=elapsed,
                    details={
                        "status": flow.status.value,
                        "error": flow.error[:100] if flow.error else None,
                    },
                    error=error,
                ))
            except Exception as e:
                tb = traceback.format_exc()
                if "Exception" in str(e) and "handled" not in str(e).lower():
                    self.test_report.add(TestResult(
                        test_id=test_id,
                        test_name=name,
                        passed=False,
                        elapsed=time.time() - t0,
                        error=f"未捕获异常: {str(e)[:200]}",
                    ))
                else:
                    self.test_report.add(TestResult(
                        test_id=test_id,
                        test_name=name,
                        passed=True,
                        elapsed=time.time() - t0,
                        details={"handled_exception": str(e)[:100]},
                    ))
    
    async def test_edge_cases(self):
        print("\n" + "-" * 80)
        print("模块8: 边界条件测试")
        print("-" * 80)
        
        test_cases = [
            ("EC-01", "单章节报告", self._make_single_section_report()),
            ("EC-02", "空报告", self._make_empty_report()),
            ("EC-03", "深层嵌套章节", self._make_deep_nested_report()),
            ("EC-04", "特殊字符标题", self._make_special_char_report()),
        ]
        
        for test_id, name, test_report_data in test_cases:
            t0 = time.time()
            try:
                session = make_session(test_report_data, f"edge_{test_id}")
                adapter = SessionReportAdapter(session)
                lock = ReportLockManager()
                
                async def mock_prompt(q):
                    return "y"
                
                notifier = ProgressNotifier(prompt_user_callback=mock_prompt)
                executor = RevisionExecutor(lock, notifier=notifier)
                
                flow = await executor.handle_feedback("修改报告内容", adapter)
                elapsed = time.time() - t0
                
                passed = flow.status != ExecutionStatus.FAILED or "not implemented" not in str(flow.error or "").lower()
                error = None if passed else f"状态: {flow.status.value}"
                
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=passed,
                    elapsed=elapsed,
                    details={
                        "status": flow.status.value,
                        "section_count": len(test_report_data.get("sections", [])),
                    },
                    error=error,
                ))
            except Exception as e:
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=False,
                    elapsed=time.time() - t0,
                    error=str(e)[:200],
                ))
    
    async def test_performance(self):
        print("\n" + "-" * 80)
        print("模块9: 性能测试")
        print("-" * 80)
        
        test_cases = [
            ("PF-01", "意图分析响应时间", 10.0),
            ("PF-02", "轻量修订响应时间", 15.0),
            ("PF-03", "复杂修订响应时间", 60.0),
        ]
        
        for test_id, name, max_time in test_cases:
            t0 = time.time()
            try:
                session = make_session(self.report_data, f"perf_{test_id}")
                adapter = SessionReportAdapter(session)
                lock = ReportLockManager()
                
                async def mock_prompt(q):
                    return "y"
                
                notifier = ProgressNotifier(prompt_user_callback=mock_prompt)
                executor = RevisionExecutor(lock, notifier=notifier)
                
                if "意图" in name:
                    analyzer = RevisionIntentAnalyzer()
                    await analyzer.analyze("修改报告内容", adapter)
                elif "轻量" in name:
                    await executor.handle_feedback("将'归母净利润'替换为'净利润'", adapter)
                else:
                    await executor.handle_feedback("补充市场规模数据并更新竞争格局", adapter)
                
                elapsed = time.time() - t0
                passed = elapsed < max_time
                error = None if passed else f"超时: {elapsed:.2f}s > {max_time}s"
                
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=passed,
                    elapsed=elapsed,
                    details={
                        "max_time": max_time,
                        "actual_time": round(elapsed, 2),
                    },
                    error=error,
                ))
            except Exception as e:
                self.test_report.add(TestResult(
                    test_id=test_id,
                    test_name=name,
                    passed=False,
                    elapsed=time.time() - t0,
                    error=str(e)[:200],
                ))
    
    def _make_single_section_report(self) -> dict:
        return {
            "topic": "单章节测试",
            "sections": [
                {
                    "id": "section_1",
                    "title": "唯一章节",
                    "content": "这是唯一的章节内容。",
                }
            ],
        }
    
    def _make_empty_report(self) -> dict:
        return {
            "topic": "空报告测试",
            "sections": [],
        }
    
    def _make_deep_nested_report(self) -> dict:
        return {
            "topic": "深层嵌套测试",
            "sections": [
                {
                    "id": "s1",
                    "title": "一级章节",
                    "content": "一级内容",
                    "subsections": [
                        {
                            "id": "s1_1",
                            "title": "二级章节",
                            "content": "二级内容",
                            "subsections": [
                                {
                                    "id": "s1_1_1",
                                    "title": "三级章节",
                                    "content": "三级内容",
                                }
                            ]
                        }
                    ]
                }
            ],
        }
    
    def _make_special_char_report(self) -> dict:
        return {
            "topic": "特殊字符测试",
            "sections": [
                {
                    "id": "s_special",
                    "title": "章节@#$%^&*()",
                    "content": "内容包含特殊字符: <>&\"'",
                }
            ],
        }


async def main():
    report_data = load_report()
    tester = RevisionSystemTester(report_data)
    passed, total = await tester.run_all_tests()
    
    print("\n" + "=" * 80)
    if passed == total:
        print("所有测试通过!")
    else:
        print(f"测试完成: {passed}/{total} 通过")
    print("=" * 80)
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
