# Progress Push and Execution Chain Systematic Fix Report

> **Generated**: 2026-05-02
> **Last Updated**: 2026-05-03
> **Review Scope**: Progress push system, research executor, Orchestrator integration
> **Status**: Partially Complete (Phase 3 implemented, Phase 1-2 pending follow-up)

---

## 1. Current System Status Overview

| Component | Status | Description |
|-----------|--------|-------------|
| ResearchExecutor real execution | **Completed** | Changed to call `ResearchOrchestrator.research()`, same path as CLI |
| Prompt externalization | **Completed** | conversation / intent_analysis / section_analysis all extracted to `prompts/agents/` |
| ConversationManager cleanup | **Completed** | Dead code deleted, CLI references fixed |
| Logging configuration | **Completed** | `force=True` + `TimedRotatingFileHandler` (daily rotation, keep 30 days) |
| StateMachine bug fix | **Completed** | quick_start state transition path fix |
| **Progress message enhancement** | **Pending** | Still only pushes start/end, no intermediate process |
| **REST status query endpoint** | **Pending** | Only SSE stream, no polling query |
| **Pause/Resume/Cancel** | **Pending** | StateMachine missing states, API missing endpoints, Executor missing checkpoints |

---

## 2. Fixed Issues

### 2.1 ResearchExecutor Real Execution Chain

**Fixed**: `ResearchExecutor.execute()` changed to call `self._orchestrator.research()`:

```python
orchestrator_result = await self._orchestrator.research(
    user_input=topic or user_input,
    interaction_mode=False,       # Skip interaction steps (API layer already completed)
    output_type=output_type,
    custom_aspects=framework.get("sections", None),
    output_format="html",
)
```

**Key Points**:
- Uses the same `ResearchOrchestrator.research()` path as CLI's `Zensers research "xxx"`
- Passes `interaction_mode=False` to skip dialogue phase
- Result converted to unified dict format and stored in session

### 2.2 Prompt Externalization

| Original Location | Migrated To | Status |
|-------------------|-------------|--------|
| `research_api.py` -> `CONVERSATION_SYSTEM_PROMPT` | `prompts/agents/conversation.md` | Done |
| `semantic_intent.py` -> `INTENT_ANALYSIS_*` | `prompts/agents/intent_analysis_*.md` | Done |
| `task_structure.py` -> `SECTION_ANALYSIS_*` | `prompts/agents/section_analysis_*.md` | Done |

### 2.3 Dead Code Cleanup

| File | Action | Description |
|------|--------|-------------|
| `src/core/dialogue/conversation_manager.py` | **Deleted** | 234 lines of zero-reference code |
| `src/core/dialogue/__init__.py` | Modified | Removed ConversationManager export |
| `src/cli/main.py` (chat command) | Modified | Changed to use ConversationStateMachine |

### 2.4 Logging Fix

```python
logging.basicConfig(level=logging.INFO, force=True)  # Override uvicorn configuration
TimedRotatingFileHandler("logs/app.log", when="midnight", backupCount=30)  # Daily rotation
```

---

## 3. Issues Pending Fix

### 3.1 Progress Messages Too Coarse

**Current State**: `ResearchOrchestrator.research()` only reports progress **twice** during the entire process:

```
# Only 3 progress calls in orchestrator.py
Line 90:  TaskState.RUNNING,  progress=0.0    # Start
Line 833: TaskState.COMPLETED, progress=1.0   # Complete
Line 855: TaskState.FAILED,   progress=0.0    # Failed
```

After the user confirms research via `POST /api/v1/research/interact`, they see progress stuck at 0% until everything finishes and jumps to 100%.

**Cause**: `ResearchOrchestrator.research()` manages serial/parallel execution of multiple Agents internally, but does not push intermediate progress to `ProgressStreamer`.

**Fix Plan**:

Insert progress calls at key steps in `ResearchOrchestrator.research()`:

```python
# In orchestrator.py research() method (pseudocode)
async def research(self, ...):
    self._update_progress(task_id, 0.05, "Analyzing research requirements...")
    # intent analysis...
    
    self._update_progress(task_id, 0.15, "Decomposing research tasks...")
    # task decomposition...
    
    self._update_progress(task_id, 0.25, "Generating research plan...")
    # planning...
    
    for i, agent in enumerate(agents):
        progress = 0.3 + (i / len(agents)) * 0.6
        self._update_progress(task_id, progress, f"Agent {agent.name}: executing...")
        await agent.run()
    
    self._update_progress(task_id, 0.9, "Integrating report...")
    # report generation...
    
    self._update_progress(task_id, 1.0, "Research complete")
```

### 3.2 Missing REST Status Query Endpoint

**Current State**: Only `GET /api/v1/stream/{task_id}` (SSE stream), frontend cannot recover after disconnection.

**Needs to add**:

```python
@router.get("/api/v1/research/{task_id}/status")
async def get_task_status(task_id: str):
    """REST status query for frontend polling"""
    state = ProgressStreamer.get_task_state(task_id)
    if not state:
        return {"task_id": task_id, "status": "unknown"}
    return {
        "task_id": task_id,
        "status": state.status,
        "progress": state.progress,
        "current_phase": state.current_phase,
        "phases": [{"id": p.id, "name": p.name, "status": p.status, "progress": p.progress}
                   for p in state.phases],
    }
```

### 3.3 Missing Pause/Resume/Cancel

**Needs changes in 3 places**:

| Level | Change | Description |
|-------|--------|-------------|
| StateMachine | Add `PAUSED` / `CANCELLED` states | conversation_state enum + transition rules |
| API Endpoints | `POST /research/{id}/pause/resume/cancel` | Modify session status, control executor |
| Executor | Add pause checkpoints | Check `session.paused` flag, wait/terminate |

---

[Remaining sections: Complete change list, System health status...]
