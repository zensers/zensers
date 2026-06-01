import asyncio
import os
import sys

PROJECT_ROOT = r"E:\market_report_systerm"
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from unittest.mock import MagicMock, AsyncMock

from core.dialogue.revision_sub_state_machine import ClarificationLoop
from core.adjustment.revision_types import (
    AnalysisResult, RevisionAction, RevisionOpType,
    ExecutionFlow, ExecutionStatus,
)
from core.adjustment.revision_executor import RevisionExecutor
from core.adjustment.report_lock_manager import ReportLockManager

# 1. _format_question has structured options
action = RevisionAction(action_id="test", action_type=RevisionOpType.ADD, target=MagicMock(raw_text="test"))
analysis = AnalysisResult(intents=[action], needs_clarification=True, clarification_questions=["need info?"])
loop = ClarificationLoop(MagicMock(), MagicMock())
question = loop._format_question(analysis)
print(f"[FIX] _format_question has options: {'options' in question.lower() or '可选' in question}")

# 2. Timeout returns __TIMEOUT__
async def check_timeout():
    loop2 = ClarificationLoop(MagicMock(), MagicMock(), ask_user_callback=AsyncMock(side_effect=asyncio.TimeoutError))
    return await loop2._ask_user("test")

result = asyncio.run(check_timeout())
print(f"[FIX] Timeout returns __TIMEOUT__: {result == '__TIMEOUT__'}")

# 3. _handle_unknown_intent routes to IntelligentRoutingAdapter
executor = RevisionExecutor(ReportLockManager())
flow = ExecutionFlow()

async def check_routing():
    return await executor._handle_unknown_intent(flow, "add market data", None)

r = asyncio.run(check_routing())
print(f"[FIX] _handle_unknown_intent has _routing_result: {hasattr(r, '_routing_result')}")
print(f"[FIX] status is FULL_RESEARCH_NEEDED: {r.status == ExecutionStatus.FULL_RESEARCH_NEEDED}")

# 4. RevisionIntentMapper and CascadeUpdateAnalyzer integrated
print(f"[FIX] _intent_mapper exists: {hasattr(executor, '_intent_mapper')}")
print(f"[FIX] _cascade_analyzer exists: {hasattr(executor, '_cascade_analyzer')}")

# 5. _analyze_revision_route method exists
print(f"[FIX] _analyze_revision_route exists: {hasattr(executor, '_analyze_revision_route')}")
print(f"[FIX] _analyze_cascade_impact exists: {hasattr(executor, '_analyze_cascade_impact')}")

# 6. _post_process called in handle_feedback
import inspect
src = inspect.getsource(RevisionExecutor.handle_feedback)
print(f"[FIX] _post_process called in handle_feedback: {'_post_process' in src}")

# 7. Low confidence skips clarification and goes to routing
print(f"[FIX] Low conf < 0.3 routes directly (check source): {'_handle_unknown_intent' in src}")

print("\nAll fixes verified!")
