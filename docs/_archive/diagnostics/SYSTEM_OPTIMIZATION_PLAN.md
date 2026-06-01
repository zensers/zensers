# Zensers Systematic Optimization Plan

> **Generation Date**: 2026-05-03
> **Last Updated**: 2026-05-03
> **Goal**: Complete the "Dialogue → Research → Pause → Supplement Requirements → Resume → Revise → Report" full pipeline
> **Status**: ✅ **All Complete** (Phase 0-3)

---

## 1. Current System Asset Inventory

### ✅ Available Complete Features

| Feature Module | Entry Point | Description |
|---------|------|------|
| CLI Research Execution | `Zensers research "xxx"` | Calls `Orchestrator.research()`, complete pipeline |
| API Dialogue Clarification | `POST /api/v1/research/start` + `/interact` | chat → framework flow working |
| API Research Execution | `POST /api/v1/research/start` → `_start_execution()` | **Just fixed**, now uses real orchestrator |
| Prompt Management | `prompts/agents/*.md` → `PromptManager` | All prompts externalized |
| **Report Revision** | `POST /api/v1/research/revise` | **Implemented**: `Orchestrator.revise()` supports partial revision of specified sections |
| **Preview Revision Loop** | `POST /api/v1/documents/revision-loop` | **Implemented**: `PreviewRevisionWorkflow`, up to 10 revision rounds |
| **Resume Interrupted Tasks** | CLI `session resume <task_id>` | **Implemented**: `Orchestrator.resume()` restores from checkpoint |
| **Revision History Management** | `GET /api/v1/documents/{id}/revisions` | **Implemented**: `RevisionManager`, supports rollback and comparison |
| Logging System | `logs/app.log` | Daily rotation, retains 30 days |
| Intelligent Routing | `IntelligentRoutingAdapter` | Integrated into `_start_execution()`, synchronous fallback |

### ❌ Missing/Pending Features

| Missing Feature | Impact | Priority |
|---------|------|--------|
| PAUSED State + pause/resume API | Users cannot control research flow | P0 |
| Progress Message Enhancement | Users cannot see intermediate progress | P0 |
| REST Status Query Endpoint | Frontend cannot poll status | P1 |
| Incremental Execution (skip completed) | Reworks existing work when supplementing requirements | P1 |
| Modify Requirements After Pause (modify API) | Cannot supplement new requirements after pause | P1 |
| Frontend Progress Display | Frontend needs to integrate SSE + REST | P2 |

---

## 2. Full Pipeline Flow Design

```
User Input "Research Claude Company"
  │
  ├─ Dialogue Clarification (chat mode) ── ✅ Working
  │    ├─ LLM guides user to clarify requirements
  │    ├─ Extract topic + directions
  │    └─ Confirm framework → Enter EXECUTING
  │
  ├─ Intelligent Routing Decomposition (adapter.analyze()) ── ✅ Integrated
  │    ├─ SemanticIntentAnalyzer analyzes intent
  │    ├─ TaskStructureAnalyzer decomposes sections
  │    ├─ DynamicPhaseOrchestrator orchestrates phases
  │    └─ Generate ExecutionPlan
  │
  ├─ Research Execution (orchestrator.research()) ── ✅ Just Fixed
  │    ├─ Data Collection → Agent Execution
  │    ├─ Deep Analysis → Agent Execution
  │    ├─ Synthesis Report → Agent Execution
  │    └─ Return ResearchResult
  │
  ├─ [New] Progress Push ── ❌ Pending
  │    ├─ Orchestrator calls update_progress() on each step
  │    ├─ SSE pushes detailed progress
  │    └─ REST endpoint for frontend polling
  │
  ├─ [New] Pause/Modify/Resume ── ❌ Pending
  │    ├─ PAUSED State
  │    ├─ pause/resume/modify API
  │    └─ Incremental Execution (skip completed sections)
  │
  ├─ Report Preview ── ✅ Endpoint exists but not verified
  │    └─ GET /api/v1/research/preview/{task_id}
  │
  ├─ User Feedback ── ✅ Implemented
  │    ├─ POST /api/v1/research/feedback
  │    │   ├─ action=confirm → Output final document
  │    │   └─ action=revise → Enter revision loop
  │    └─ POST /api/v1/research/revise
  │
  └─ Revision Loop ── ✅ Implemented
       ├─ PreviewRevisionWorkflow (up to 10 rounds)
       ├─ RevisionHandler (minor/section/phase/full)
       ├─ RevisionManager (history + rollback + comparison)
       └─ Output final document
```

---

## 3. Implementation Roadmap

### Phase 0: Progress Push Enhancement (P0, 1 day) ⏺️ Completed

Insert progress calls at key steps in `ResearchOrchestrator.research()`:

```python
# Insert into orchestrator.py research() method
self._push_progress(task_id, 0.05, "Analyzing research requirements...")
# ... intent analysis ...
self._push_progress(task_id, 0.15, "Decomposing research task...")
# ... task decomposition ...
for i, agent in enumerate(agents):
    p = 0.3 + (i / len(agents)) * 0.6
    self._push_progress(task_id, p, f"Agent {agent.name}: executing...")
    await agent.run()
self._push_progress(task_id, 0.95, "Integrating report...")
```

Also add REST status query endpoint:
```python
@router.get("/api/v1/research/{task_id}/status")
async def get_task_status(task_id: str):
    """REST Status Query"""
```

**Files Changed**: `orchestrator.py`, `main.py`

---

### Phase 1: Pause/Resume/Modify (P0, 2 days) ⏺️ Completed

#### 1.1 StateMachine Add PAUSED

```python
class ConversationState(Enum):
    PAUSED = "paused"
    CANCELLED = "cancelled"

VALID_TRANSITIONS = {
    ConversationState.EXECUTING: [
        ConversationState.EXECUTING,
        ConversationState.PAUSED,     # New
        ConversationState.PREVIEWING,
        ConversationState.COMPLETED,
    ],
    ConversationState.PAUSED: [
        ConversationState.PAUSED,
        ConversationState.EXECUTING,   # resume → back to executing
        ConversationState.CANCELLED,   # cancel → terminate
    ],
}
```

#### 1.2 API Endpoints

| Endpoint | Function |
|------|------|
| `POST /api/v1/research/{id}/pause` | Set paused flag, executor stops at next checkpoint |
| `POST /api/v1/research/{id}/resume` | Clear paused, restart executor |
| `POST /api/v1/research/{id}/modify` | Update requirements → intelligent routing re-plans |
| `POST /api/v1/research/{id}/cancel` | Terminate research, clean up resources |

#### 1.3 Executor Pause Check

```python
async def execute(self, session_id, plan, sessions):
    for phase in phases:
        await self._check_paused(session_id)
        # ... execute phase ...
    
    async def _check_paused(self, session_id):
        session = sessions.get(session_id, {})
        while session.get("paused"):
            await asyncio.sleep(1)
            if session.get("status") == "cancelled":
                raise CancelledError()
```

#### 1.4 Integrate TaskPersistenceManager

```python
# Save checkpoint on pause
task = TaskPersistenceManager.load_task(session_id)
task.pause()
task.execution_state["current_phase"] = current_phase
task.execution_state["completed_phases"] = completed_phases
TaskPersistenceManager.save_task(task)
```

**Files Changed**: `state_machine.py`, `main.py`, `research_api.py`, `research_executor.py`, `task_persistence.py`

---

### Phase 2: Incremental Execution (P1, 2 days) ⏺️ Completed

When users supplement requirements, intelligent routing does incremental judgment:

```python
# IntelligentRoutingAdapter new method
def analyze_incremental(
    self,
    user_request: str,
    requirement: Dict[str, Any],
    completed_aspects: List[str],
    topic: Optional[str] = None,
) -> IntelligentRoutingResult:
    # 1. Full analysis of new requirements
    full_result = self.analyze(user_request, requirement, topic)
    
    # 2. Compare with completed sections, mark overlaps
    for section in full_result.task_structure.sections:
        if section.section_name in completed_aspects:
            section.status = "SKIP"  # Complete overlap → skip
    
    # 3. Semantic detection of partial overlap (LLM judgment)
    #    "Competitive Landscape" vs "Company Research" → partial overlap
    overlaps = await self._detect_semantic_overlap(
        new_aspects=[s.section_name for s in full_result.task_structure.sections],
        completed_aspects=completed_aspects,
    )
    
    return full_result  # With SKIP/PARTIAL/NEW markers
```

**Orchestrator.research() support skip_phases**:

```python
async def research(
    self,
    user_input,
    skip_phases: Optional[List[str]] = None,  # New
    ...
):
    for phase in execution_plan.phases:
        if skip_phases and phase.id in skip_phases:
            logger.info(f"Skipping completed phase: {phase.id}")
            continue
        await self._execute_phase(phase)
```

**Files Changed**: `intelligent_routing_adapter.py`, `orchestrator.py`, `research_executor.py`

---

### Phase 3: Revision Module Integration Verification (0.5 day) ⏺️ Completed

Revision module (`RevisionService` + `PreviewRevisionWorkflow`) is implemented, needs end-to-end path verification:

```
Research Complete
  → preview (GET /api/v1/research/preview/{task_id})
  → User Feedback (POST /api/v1/research/feedback)
      → confirm → Output final document ✅
      → revise → POST /api/v1/research/revise
          → orchestrator.revise() partial revision ✅
          → PreviewRevisionWorkflow loop revision ✅
          → Update document → Preview again ✅
  → Confirm → Final document
```

Verify actual response of each API endpoint.

---

## 4. File Change Summary

| Phase | File | Change | Effort |
|-------|------|------|------|
| 0 | `src/core/orchestrator/orchestrator.py` | research() add progress push | 0.5 day |
| 0 | `src/api/main.py` | Add `GET /research/{id}/status` endpoint | 0.5 day |
| 1 | `src/core/dialogue/state_machine.py` | Add PAUSED/CANCELLED states | 0.25 day |
| 1 | `src/api/main.py` | Add pause/resume/modify/cancel endpoints | 0.5 day |
| 1 | `src/api/research_api.py` | Add pause/resume/modify methods | 0.5 day |
| 1 | `src/api/research_executor.py` | Add pause checkpoints | 0.25 day |
| 1 | `src/core/task_persistence.py` | Persist on pause/resume | 0.25 day |
| 2 | `src/core/intelligent_routing_adapter.py` | Add `analyze_incremental()` | 1 day |
| 2 | `src/core/orchestrator/orchestrator.py` | research() add skip_phases | 0.5 day |
| 3 | Various API Endpoints | Revision module integration verification | 0.5 day |
| | **Total** | | **~5 days** |

---

## 5. Completed Fixes Review

| Fix | Status | Time |
|------|------|------|
| Prompts externalized (conversation / intent_analysis / section_analysis) | ✅ | Phase 5 |
| ConversationManager dead code removed | ✅ | |
| ResearchExecutor real execution path | ✅ | Just Fixed |
| StateMachine quick_start state transition bug | ✅ | Just Fixed |
| Logging fix (force=True + rotation) | ✅ | Just Fixed |
| CLI conversation_manager reference fix | ✅ | Just Fixed |
| System status report FIX_REPORT_PROGRESS_AND_EXECUTION.md | ✅ | Updated |

---

*This plan covers all known issues. Recommended implementation order: Phase 0 → 1 → 2 → 3. Revision module (Phase 3) can be integration-verified first to confirm end-to-end path is working.*
