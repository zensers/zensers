import asyncio
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from src.core.adjustment.report_adapter import SessionReportAdapter
from src.core.adjustment.revision_executor import RevisionExecutor, ProgressNotifier
from src.core.adjustment.revision_types import ExecutionStatus
from src.core.adjustment.report_lock_manager import ReportLockManager

REPORT_DATA_PATH = os.path.join(PROJECT_ROOT, "data", "research_e32d301e", "research_result_cache.json")

def load_report():
    with open(REPORT_DATA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    wrapped = {"research_result": {"report": raw}}
    return wrapped

def make_executor(mock_prompt):
    lock_mgr = ReportLockManager()
    notifier = ProgressNotifier(prompt_user_callback=mock_prompt)
    return RevisionExecutor(lock_manager=lock_mgr, notifier=notifier)

async def test_IN02():
    print("\n=== IN-02: user confirm ===")
    report_data = load_report()
    adapter = SessionReportAdapter(report_data)
    
    user_inputs = ["y", "y", "y", "y", "y"]  # multiple prompts possible
    input_idx = [0]
    async def mock_prompt(msg):
        if input_idx[0] >= len(user_inputs):
            return "y"  # default to yes
        resp = user_inputs[input_idx[0]]
        input_idx[0] += 1
        print(f"  [prompt] -> {resp}")
        return resp
    
    executor = make_executor(mock_prompt)
    result = await executor.handle_feedback("请修改第三部分的标题", adapter)
    
    passed = result.status in (ExecutionStatus.COMPLETED, ExecutionStatus.LIGHTWEIGHT_DONE, ExecutionStatus.PREVIEW_READY)
    print(f"  status={result.status.value} -> {'PASS' if passed else 'FAIL'}")
    if not passed:
        print(f"  error={result.error}")
    return passed

async def test_IN03():
    print("\n=== IN-03: user reject ===")
    report_data = load_report()
    adapter = SessionReportAdapter(report_data)
    
    user_inputs = ["n", "n", "n", "n", "n"]
    input_idx = [0]
    async def mock_prompt(msg):
        if input_idx[0] >= len(user_inputs):
            return "n"
        resp = user_inputs[input_idx[0]]
        input_idx[0] += 1
        print(f"  [prompt] -> {resp}")
        return resp
    
    executor = make_executor(mock_prompt)
    result = await executor.handle_feedback("请修改第三部分的标题", adapter)
    
    passed = result.status == ExecutionStatus.ABORTED
    print(f"  status={result.status.value} -> {'PASS' if passed else 'FAIL'}")
    if not passed:
        print(f"  error={result.error}")
    return passed

async def test_CR02():
    print("\n=== CR-02: ADD operation ===")
    report_data = load_report()
    adapter = SessionReportAdapter(report_data)
    
    user_inputs = ["y", "y", "y", "y", "y"]  # multiple prompts possible
    input_idx = [0]
    async def mock_prompt(msg):
        if input_idx[0] >= len(user_inputs):
            return "y"  # default to yes
        resp = user_inputs[input_idx[0]]
        input_idx[0] += 1
        print(f"  [prompt] -> {resp}")
        return resp
    
    executor = make_executor(mock_prompt)
    result = await executor.handle_feedback("请添加一个新章节：风险提示", adapter)
    
    passed = result.status in (ExecutionStatus.COMPLETED, ExecutionStatus.LIGHTWEIGHT_DONE, ExecutionStatus.PREVIEW_READY)
    print(f"  status={result.status.value} -> {'PASS' if passed else 'FAIL'}")
    if not passed:
        print(f"  error={result.error}")
    return passed

async def main():
    print("=" * 50)
    print("Quick verify - previously failing tests")
    print("=" * 50)
    
    results = {}
    for name, fn in [("IN-02", test_IN02), ("IN-03", test_IN03), ("CR-02", test_CR02)]:
        try:
            results[name] = await fn()
        except Exception as e:
            print(f"  {name} ERROR: {e}")
            import traceback; traceback.print_exc()
            results[name] = False
    
    print("\n" + "=" * 50)
    for name, passed in results.items():
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    total = len(results)
    passed_count = sum(1 for v in results.values() if v)
    print(f"  => {passed_count}/{total}")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
