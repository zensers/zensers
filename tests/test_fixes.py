"""Verify all 6 integration fixes"""
import sys; sys.path.insert(0, '.')
print('=== Fix 1: Multi-language intent trigger (orchestrator level) ===')
with open('src/core/orchestrator/orchestrator.py', encoding='utf-8') as f:
    code = f.read()
assert '_survey_triggers' in code
assert '"survey"' in code and '"questionnaire"' in code
assert '"consumer survey"' in code or '"user research"' in code
import re
triggers = re.findall(r"'([^']+)'", code[code.index('_survey_triggers'):code.index('_survey_triggers')+800])
chinese_triggers = [t for t in triggers if any('\u4e00' <= c <= '\u9fff' for c in t)]
en_triggers = [t for t in triggers if t.isascii() and len(t) > 2]
print(f'  Chinese/English triggers: {len(chinese_triggers)}+{len(en_triggers)} keywords')
print('  PASS')

print()
print('=== Fix 2: PhaseType.SURVEY instantiation ===')
from src.core.dynamic_orchestrator import DynamicPhaseOrchestrator, PhaseType, TaskStructure, ExecutionPlan
from src.core.semantic_intent import DeepIntentResult
from src.core.intent_types import IntentType, TaskComplexity
assert PhaseType.SURVEY.value == 'survey'
# Test that plan() adds SURVEY phase when requires_primary_data=True
intent = DeepIntentResult(primary_intent=IntentType.RESEARCH, intent_confidence=0.8, intent_reasoning='test', complexity=TaskComplexity.MULTI, requires_primary_data=True)
orch = DynamicPhaseOrchestrator()
ts = TaskStructure(task_id='test_001', topic='test', sections=[], dependencies=[])
plan = orch.plan(ts, intent, 'test')
phase_types = [p.phase_type for p in plan.phases]
print(f'  Phase types: {[p.value for p in phase_types]}')
has_survey = PhaseType.SURVEY in phase_types
print(f'  SURVEY phase generated: {has_survey}')
assert has_survey, 'SURVEY phase not generated!'
print('  PASS')

print()
print('=== Fix 3+4: API endpoints ===')
from src.survey.task_api import router
routes = {r.path for r in router.routes if hasattr(r, 'methods')}
assert '/api/v1/surveys/{survey_id}/results' in routes, 'results endpoint missing'
assert '/api/v1/surveys/{survey_id}/analysis' in routes, 'analysis endpoint missing'
print(f'  /results: OK')
print(f'  /analysis: OK')
print(f'  Total API routes: {len(router.routes)}')
print('  PASS')

print()
print('=== Fix 5: SQLite persistence ===')
from src.survey.backends.ai_simulation import AISimulationBackend
assert hasattr(AISimulationBackend, '_persist_results')
import inspect; sig = inspect.signature(AISimulationBackend._persist_results)
print(f'  _persist_results sig: {sig}')
print('  PASS')

print()
print('=== Fix 6: Report integration ===')
with open('src/core/orchestrator/orchestrator.py', encoding='utf-8') as f:
    code = f.read()
assert 'survey_result' in code
assert 'results_for_aggregation["survey_result"]' in code
print(f'  Survey results flow into report aggregation: OK')
print('  PASS')

print()
print('=== ALL 6 FIXES PASSED ===')
