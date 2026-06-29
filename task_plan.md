# E2E Pipeline Test Plan

## Goal
Write a comprehensive end-to-end test that validates the full pipeline:
User Request → Dialogue → Framework → Execution → Aggregation → Report Generation → Quality Check

## Phases

### Phase 1: Test Infrastructure & Fixtures `[complete]`
- Factory helpers for session dicts, framework data, agent results, LLM responses
- Mock strategy: patch at skill/LLM boundary so orchestration logic runs real

### Phase 2: Stage 1 - User Input → Framework Confirmation `[complete]`
- _handle_chat_mode → LLM returns enter_framework → topic/directions captured
- _llm_converse → JSON parsing → context updates

### Phase 3: Stage 2 - Framework → Execution Launch `[complete]`
- _enter_framework_mode builds framework from tree/directions
- Idempotent: returns existing framework unchanged
- _start_execution builds final_plan with section_details
- Rejects empty topic/sections

### Phase 4: Stage 3 - Execution → Aggregation `[complete]`
- ResultAggregator.aggregate maps agent results to framework sections
- Provenance tracked, empty results handled gracefully

### Phase 5: Stage 4 - Aggregation → Report Output `[complete]`
- ContentOrchestrator.transform_to_html generates valid HTML
- All sections present, key findings included, empty sections handled

### Phase 6: Stage 5 - Quality Check & Completion `[complete]`
- QualityCheckAgent.execute returns score + issues
- Mocked internal checks to test scoring logic in isolation

### Phase 7: Full Pipeline Integration `[complete]`
- Aggregation → HTML → Quality pipeline validates data flows correctly
- State machine transitions validated independently

### Phase 8: Run & Validate `[complete]`
- 113 tests all passing (69 + 13 + 6 + 25)
- No regression on existing tests

## Decisions
- Mock at LLM skill level, not at method level — validates real orchestration logic
- Use AsyncMock for all LLM/search calls
- Build realistic test data from actual session structures
- Patch internal imports at source module (e.g. src.core.progress_streamer.ProgressStreamer not src.api.research_api.ProgressStreamer)
- QualityCheckAgent constructed with __init__ not __new__ to preserve mixin attributes

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| ProgressStreamer not found on research_api module | 1 | Method-level import → patch at source: src.core.progress_streamer.ProgressStreamer |
| get_cancel_manager not found on research_api module | 1 | Same: patch src.core.orchestrator.execution.coordinator.cancel_manager.get_cancel_manager |
| get_executor not found on research_api module | 1 | Patch src.api.research_executor.get_executor |
| QualityCheckAgent._message_bus missing | 1 | Use __init__(agent_id=...) instead of __new__() |
| _calculate_quality_score not found | 1 | Actual method name is _calculate_score |
| _calculate_score mock ignored (score 74.1 vs 85.0) | 2 | check_by_sections async method overrides score → mock it too |
