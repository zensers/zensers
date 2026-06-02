# research_api.py Systematic Fix Plan

> **Generated**: 2026-06-01
> **Target**: `src/api/research_api.py`
> **Status**: 2533 lines, compiles without errors, 20/20 E2E tests pass
> **Scope**: Comprehensive gap analysis against 10 design documents

---

## 1. Overview

### Purpose

This document enumerates every known gap between the current `research_api.py` implementation and the requirements specified across all design documents. It serves as:

- A **single source of truth** for remaining work
- A **priority-ordered execution plan** for fixes
- A **regression prevention checklist** for future changes

### Current Status

| Metric | Value |
|--------|-------|
| File size | ~2650 lines |
| Compilation | ✅ Clean (0 errors) |
| E2E tests | ✅ 20/20 pass |
| Unit tests | ✅ All passing (13/13 helpers) |
| Design docs | 10 reviewed |
| Gaps found | 19 |
| Gaps fixed | 12 (G01/G02/G03/G04/G09/G10/G11/G13/G14/G15/G17/G18 + extras) |

---

## 2. Known Issues and Fixes (Already Completed)

### 2.1 Decompiler Artifact Cleanup

| Issue | Fix | Location |
|-------|-----|----------|
| `ConversationStateMachine` rename → `RevisionConversationContainer` | ~~NOT DONE~~ — rename was not applied; `ConversationStateMachine` still in use at L41/255/541/544/1528 | N/A |
| `DeepIntentResult` import removed | ✅ Dead import deleted | `research_api.py:41` (former) |
| `_is_greeting()` dead code | Partially done — `_is_greeting` removed but `_is_greeting_simple` still exists at L1210-1226 | Various (former: 1873-2252) |

### 2.2 Control Flow Reconstruction

| Issue | Fix | Location |
|-------|-----|----------|
| `_llm_converse` single-turn → multi-turn loop | Rewrote with `_build_initial_prompt`/`_build_followup_prompt` | `_llm_converse` (L648) |
| `_build_dialogue_context` intent_state injection removed | Simplified to phase-only guidance | L591-595 |
| `SemanticIntentAnalyzer` independent call deleted | Merged into conversation LLM output | Former L582-598 |
| `MAX_TOOL_ITERATIONS` dead code → config-driven | New `_get_max_tool_iterations()` from settings | L805-811 |
| `_do_execute_tool_background` retained for old path | DEPRECATED label added, not removed | L892 |

### 2.3 Missing Imports / Attrs

| Issue | Fix | Location |
|-------|-----|----------|
| `_loop_cancel_flags` class var added | Dict[str, int] for multi-turn loop cancellation | L207 |
| `ConversationConfig` dataclass added | `max_tool_iterations` configurable | `settings.py` |
| `ProgressNotifier` import | For v2 revision execution feedback | L2191 |
| `_session_id` set in session creation | `'_session_id': session_id` added to `session_manager.create()` at start_research | L261 |
| `SemanticIntentAnalyzer` dead import removed | Import and `self._intent_analyzer` instantiation removed | Former L51, L202 |

### 2.4 Pause Race Condition Fixes

| Fix | Documentation Source |
|-----|---------------------|
| `_start_execution` clears stale pause flag before `create_task` | `fix_plan_stale_pause_flag.md` P0 |
| `_on_sse_disconnect` checks terminal statuses (`completed/failed/cancelled/error`) | `fix_plan_stale_pause_flag.md` P2 |
| `_check_paused` adds log before blocking | `fix_plan_stale_pause_flag.md` P1 |

### 2.5 E2E Validation

| Fix | Tests |
|-----|-------|
| HTTP sync blocking → `asyncio.wait_for` timeout protection | 7 test cases |
| ~~HTML double-render → `_strip_parsed_subsections` dedup~~ | ~~NOT IMPLEMENTED~~ — method does not exist |
| Engine inject checkpoint + scheduler `merge_agents` | 14 test cases |
| LLM prompt contradiction (inject_requirement vs modify_research) | 4 test cases |
| Aggregation key extraction for inject Agent IDs | 11 test cases |
| ~~DocumentGenerator dedup → ContentOrchestrator `_dedup_sections`~~ | ~~NOT IMPLEMENTED~~ — method does not exist |
| `_inject_merge_to_section` session type error (`getattr` → `session.get`) | 3 test cases |
| `_pending_section_injects` race condition (`copy` + `clear` atomicity) | 2 test cases |
| C1: `Set.keys()` → `len()` in `cascade_update_analyzer.py` | Regression test added |
| D2: ThreadPoolExecutor shared → prevents per-call creation | `semantic_intent.py` |
| D3: BatchRevisionService integration (fallback pattern) | Sequential fallback preserved |

---

## 2.6 Fixes Applied in Round 2 (2026-06-01)

| Gap ID | Fix | Location |
|--------|-----|----------|
| **G01** | `cancel_research` rewritten: saves snapshot via `_save_cancel_snapshot()`, cancels executor task via `exec_task.cancel()`, clears background tasks, calls `cm.cleanup()` | `research_api.py:cancel_research` |
| **G02** | `pause_research` enhanced: saves snapshot, adds task persistence pause | `research_api.py:pause_research` |
| **G03** | `resume_research` Path B: loads snapshot via `_load_cancel_snapshot()`, delegates to `_resume_from_snapshot()` which rebuilds plan for pending sections only | `research_api.py:resume_research`, `_resume_from_snapshot` |
| **G04** | New `_save_cancel_snapshot()` + `_load_cancel_snapshot()` methods: persist completed/pending sections to `cancel_snapshot.json` | `research_api.py:_save_cancel_snapshot`, `_load_cancel_snapshot` |
| **G09** | Already fixed in prior round: `RevisionExecutor(lock_manager=..., notifier=notifier)` | `research_api.py:_handle_v2_revision` |
| **G10** | Already fixed in prior round: `async def _confirm_v2_revision` | `research_api.py:_confirm_v2_revision` |
| **G11** | Already fixed in prior round: `await executor.continue_revision(...)` | `research_api.py:_handle_task_confirmation` |
| **G13** | Already fixed in prior round: `async def _resume_after_modify` with `await executor.execute(...)` | `research_api.py:_resume_after_modify` |
| **G14** | Keyword cancel/pause detection added in research mode: cancel keywords → `cancel_research()`, pause keywords → `pause_research()` | `research_api.py:_handle_user_message` |
| **G15** | `_handle_modify_research` reorder: `cm.pause()` → `_save_cancel_snapshot()` → `_cancel_existing_task()` | `research_api.py:_handle_modify_research` |
| **G17** | `_handle_modify_research` snapshot save added between pause and cancel | `research_api.py:_handle_modify_research` |
| **G18** | Already fixed in prior round: `async def _handle_modify_research` | `research_api.py:_handle_modify_research` |
| **G19** | `_session_id` set in session creation at `start_research` | `research_api.py:start_research` L261 |
| **NEW** | `_handle_task_confirmation` now passes `notifier=ProgressNotifier()` to `RevisionExecutor` | `research_api.py:_handle_task_confirmation` |
| **NEW** | `_resume_after_modify` task stored in `_executor_tasks` + error logging via `add_done_callback` | `research_api.py:_handle_modify_research` |
| **NEW** | `SemanticIntentAnalyzer` dead import + `_intent_analyzer` dead instance removed | Former L51, L202 |

---

## 3. Remaining Gaps (From Design Docs)

### G01 — `cancel_research()` does not match v5 CancelManager spec — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Rewritten with `_save_cancel_snapshot()`, `exec_task.cancel()`, `cm.cleanup()`. Note: `cancel_cascade()` does not exist in CancelManager; used `cm.cancel()` + explicit executor task cancel instead |
| **Source** | `TASK_CANCEL_PAUSE_REVISION_PLAN.md §3.2.2` |
| **Current Behavior** | Direct `cm.cancel(task_id)` call; no cascading, no snapshot, no backup `Task.cancel()`, no event cleanup callback |
| **Expected Behavior** | `cm.cancel_cascade()` → `_save_cancel_snapshot()` → backup `exec_task.cancel()` → `_cleanup_events` via `done_callback` → task persistence → SSE |
| **Severity** | **P0** — Critical safety gap. User cancellation does not reliably propagate to sub-tasks, no snapshot for recovery |
| **Code Location** | `research_api.py:1930-1955` — `cancel_research()` |
| **Proposed Fix** | Rewrite to match v5 spec: (1) state machine transition to CANCELLED, (2) `cm.cancel_cascade()` with appropriate reason, (3) `_save_cancel_snapshot()`, (4) backup `exec_task.cancel()`, (5) session status update, (6) task persistence, (7) SSE, (8) `_cleanup_events` via done_callback |

### G02 — `pause_research()` does not match v5 spec — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Added `_save_cancel_snapshot()`, task persistence pause. Note: `fresh_resume_event()` is called internally by `cm.pause()` |
| **Source** | `TASK_CANCEL_PAUSE_REVISION_PLAN.md §3.2.3` |
| **Current Behavior** | Sets pause flag + state machine transition + SSE. No snapshot, no task persistence, no `fresh_resume_event()` call |
| **Expected Behavior** | `cm.pause()` (which calls `fresh_resume_event()` internally per v5), save snapshot via `_save_cancel_snapshot()`, task persistence save, SSE PAUSED event |
| **Severity** | **P1** — Pause without snapshot means Engine crash = data loss |
| **Code Location** | `research_api.py:1852-1868` — `pause_research()` |
| **Proposed Fix** | (1) Ensure `cm.pause()` calls `fresh_resume_event()` internally (check CancelManager), (2) add `await _save_cancel_snapshot(task_id, session)`, (3) add task persistence pause, (4) ensure `ProgressStreamer.pause_task()` exists and is called |

### G03 — `resume_research()` missing SnapshotManager Path B — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Implemented Path B via `_load_cancel_snapshot()` + `_resume_from_snapshot()`. When engine is dead, loads snapshot and rebuilds plan for pending sections only |
| **Source** | `TASK_CANCEL_PAUSE_REVISION_PLAN.md §3.2.4` |
| **Current Behavior** | Only Path A (wake Engine) implemented. If Engine is dead (`executor_tasks` not found or done), returns error "Research engine has stopped, please start a new task" |
| **Expected Behavior** | Path B: Load `SnapshotManager` snapshot → identify pending sections → create `_resume_from_snapshot` task → return resumed status |
| **Severity** | **P1** — Engine death during pause = permanent task loss |
| **Code Location** | `research_api.py:1870-1894` — `resume_research()` |
| **Proposed Fix** | Implement Path B: (1) after `has_alive_executor` check, attempt `SnapshotManager.load(task_id)`, (2) if snapshot exists, compute pending sections, (3) create `_resume_from_snapshot` async task, (4) register in `_executor_tasks`, (5) return resumed response. Also implement `_resume_from_snapshot()` method |

### G04 — `_save_cancel_snapshot()` method entirely missing — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Created `_save_cancel_snapshot()` and `_load_cancel_snapshot()`. Persists completed/pending sections to `data/{task_id}/cancel_snapshot.json` |
| **Source** | `TASK_CANCEL_PAUSE_REVISION_PLAN.md §3.2.5` |
| **Current Behavior** | No snapshot saving anywhere in cancel/pause/modify flow |
| **Expected Behavior** | Method exists and is called from `cancel_research()`, `pause_research()`, and `_handle_modify_research()` before task cancellation |
| **Severity** | **P0** — Permanent data loss on cancel/pause without recovery option |
| **Code Location** | NOT FOUND — does not exist |
| **Proposed Fix** | Create `_save_cancel_snapshot(task_id, session)` that: (1) extracts completed sections from `research_result`, (2) computes pending vs completed, (3) creates `CancelSnapshot` object, (4) delegates to `SnapshotManager.save()` via thread pool |

### G05 — `QualityActionRequest` is a stub class, not Pydantic model

| Field | Detail |
|-------|--------|
| **Source** | `2026-06-01-quality-feedback-revision-design.md §5.1` |
| **Current Behavior** | Simple Python class with `__init__` taking `**kwargs`. No type validation. No Literal constraints. Uses `.get()` for field access |
| **Expected Behavior** | Pydantic `BaseModel` with `session_id: str`, `action: Literal["quality_dismiss", "quality_reopen", ...]`, `issue_id: Optional[str]`, `version_id: Optional[str]`, `section_name: Optional[str]` |
| **Severity** | **P2** — No input validation for quality actions; but stub works for current minimal implementation |
| **Code Location** | `research_api.py:2506-2511` — `QualityActionRequest` |
| **Proposed Fix** | Replace with proper Pydantic `BaseModel` with Literal action field and Optional fields |

### G06 — `handle_quality_action()` and `get_quality_state()` are stubs

| Field | Detail |
|-------|--------|
| **Source** | `2026-06-01-quality-feedback-revision-design.md §5.1, §5.2` |
| **Current Behavior** | `handle_quality_action()` handles only `action == "approve"` by setting `session['quality_status'] = 'approved'`. `get_quality_state()` returns only `quality_status` field |
| **Expected Behavior** | `handle_quality_action` handles: `quality_dismiss`, `quality_reopen`, `quality_rollback`, `quality_confirm`, `quality_recheck`. `get_quality_state` returns full `QualityState.model_dump()` |
| **Severity** | **P2** — Quality system is not yet operational. Design doc is still in design stage |
| **Code Location** | `research_api.py:2514-2533` |
| **Proposed Fix** | (1) Implement 5 quality action handlers, (2) integrate `QualityState`/`QualityIssue` Pydantic models, (3) manage `session["quality_state"]` lifecycle, (4) implement issue state machine, (5) implement version snapshots |

### G07 — No `quality_state` session field or lifecycle management

| Field | Detail |
|-------|--------|
| **Source** | `2026-06-01-quality-feedback-revision-design.md §4.1` |
| **Current Behavior** | `session["quality_state"]` is never created or managed. Only `session["quality_status"] = 'approved'` is set by the `approve` action |
| **Expected Behavior** | `QualityState` Pydantic model stored as `session["quality_state"]` dict, with phase/overall_score/section_scores/version_stack lifecycle |
| **Severity** | **P2** — Design not yet implemented |
| **Code Location** | Implicit — `research_api.py` has no quality state management |
| **Proposed Fix** | Add `QualityState`, `SectionScore`, `QualityIssue`, `VersionInfo` Pydantic models, `session["quality_state"]` lifecycle, issue state machine transitions, version stack management |

### G08 — No quality SSE event types or push methods in research_api.py

| Field | Detail |
|-------|--------|
| **Source** | `2026-06-01-quality-feedback-revision-design.md §6` |
| **Current Behavior** | No `push_preview_refresh()` or `push_quality_confirmed()` calls in research_api.py. These push methods may not exist in `session_streamer.py` |
| **Expected Behavior** | After revision execution: `SessionStreamer.push_preview_refresh(session_id, preview_url, version_id)` and `SessionStreamer.push_quality_confirmed(...)` |
| **Severity** | **P2** — Required for quality feedback loop |
| **Code Location** | NOT FOUND — push calls not integrated |
| **Proposed Fix** | (1) Verify `SessionStreamer.push_preview_refresh()` and `push_quality_confirmed()` exist, (2) integrate into `_handle_v2_revision()` completion path, (3) integrate into `_handle_quality_action()` confirm path |

### G09 — `_handle_v2_revision` creates `ProgressNotifier` but passes `_v2_lock_manager` as `notifier` to `RevisionExecutor` — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Corrected to `RevisionExecutor(lock_manager=self._v2_lock_manager, notifier=notifier)` |
| **Source** | `REVISION_V2_INTEGRATION_PLAN.md S6` |
| **Current Behavior** | Line 2197: `notifier = ProgressNotifier(session_id=session_id)` [created but never used]. Line 2198: `executor = RevisionExecutor(notifier=self._v2_lock_manager)` [lock_manager passed as notifier positional arg] |
| **Expected Behavior** | Design: `executor = RevisionExecutor(v2_container, adapter, self._v2_lock_manager)`. The `notifier` should be passed correctly, and the lock manager should be passed as keyword arg |
| **Severity** | **P1** — `RevisionExecutor` receives wrong argument. Either crashes at runtime (if type mismatch) or silently operates without proper progress notification |
| **Code Location** | `research_api.py:2197-2198` |
| **Proposed Fix** | (1) Check `RevisionExecutor.__init__` signature, (2) pass `ProgressNotifier` correctly, (3) pass `_v2_lock_manager` as correct keyword argument |

### G10 — `_confirm_v2_revision` is sync, design says async — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Changed to `async def` with `await` on async operations |
| **Source** | `REVISION_V2_INTEGRATION_PLAN.md S6` |
| **Current Behavior** | Line 2248: `def _confirm_v2_revision(self, session_id, accept):` — sync method that calls `VersionManager.commit_revision()` (sync) and `SnapshotManager.restore_snapshot()` (sync) |
| **Expected Behavior** | `async def _confirm_v2_revision(...)` with `await VersionManager().commit_revision(...)` and `await SnapshotManager().restore_snapshot(...)` |
| **Severity** | **P1** — Sync calls on potentially async operations. If `commit_revision` or `restore_snapshot` perform IO, event loop blocks |
| **Code Location** | `research_api.py:2248-2283` — `_confirm_v2_revision` |
| **Proposed Fix** | Make async: `async def`, `await` on all async operations |

### G11 — `_handle_task_confirmation` calls sync `continue_revision` instead of async — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Added `await` to `executor.continue_revision(...)`. Also added `notifier=ProgressNotifier()` to `RevisionExecutor` construction |
| **Source** | `REVISION_V2_INTEGRATION_PLAN.md S7` |
| **Current Behavior** | Line 2297: `flow = executor.continue_revision(flow, choice, user_input, adapter, report_tree)` — sync call |
| **Expected Behavior** | Should be `await executor.continue_revision(...)` if the method is async |
| **Severity** | **P2** — Depends on whether `continue_revision` is truly async. If it's sync, behavior is correct but pattern is inconsistent |
| **Code Location** | `research_api.py:2285-2309` — `_handle_task_confirmation` |
| **Proposed Fix** | Verify `RevisionExecutor.continue_revision()` signature; if async, add `await` |

### G12 — `_handle_inject_requirement` routes `add_sections` to `_handle_modify_research` instead of engine inject checkpoint

| Field | Detail |
|-------|--------|
| **Source** | `RESEARCH_RUNTIME_INJECT_AND_DUPLICATE_FIX_PLAN.md §P1` |
| **Current Behavior** | Line 2327-2328: When `add_sections` present, calls `self._handle_modify_research()` which pauses + cancels + re-plans entire execution |
| **Expected Behavior** | New sections should be injected via the engine inject checkpoint (callback mechanism in `orchestrator._handle_engine_inject`). Only if inject checkpoint is unavailable should it fall back to `_handle_modify_research` |
| **Severity** | **P1** — Injecting sections triggers full stop-and-replan instead of lightweight inline injection |
| **Code Location** | `research_api.py:2327-2328` |
| **Proposed Fix** | Route `add_section` ops to pending section injects queue (as design intended), not to `_handle_modify_research`. Remove the `if add_sections: return self._handle_modify_research(...)` early-return and let the inject queue mechanism handle it |

### G13 — `_resume_after_modify` is sync, should be async — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Already `async def` with `await executor.execute(...)` in prior round. Enhanced: task now stored in `_executor_tasks` with error logging via `add_done_callback` |
| **Source** | `TASK_CANCEL_PAUSE_REVISION_PLAN.md §3.2.4` |
| **Current Behavior** | Line 2485: `def _resume_after_modify(self, session_id, new_plan):` — sync method + line 2495: `executor.execute(...)` — coroutine not awaited |
| **Expected Behavior** | Should be `async def` with `await executor.execute(...)`. The coroutine is currently being fire-and-forgotten |
| **Severity** | **P0** — `executor.execute()` returns a coroutine; calling it without `await` means the coroutine is never awaited, so execution never actually starts |
| **Code Location** | `research_api.py:2485-2496` — `_resume_after_modify` |
| **Proposed Fix** | Change to `async def`, add `await` before `executor.execute(...)`, update caller `_handle_modify_research` (L2481) accordingly |

### G14 — No keyword-based cancel/pause detection in research mode — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Added keyword detection block in `_handle_user_message` for research mode: cancel keywords (`取消研究`, `cancel research`, etc.) and pause keywords (`暂停`, `pause`, etc.) |
| **Source** | `TASK_CANCEL_PAUSE_REVISION_PLAN.md §3.6.1` |
| **Current Behavior** | `_handle_user_message` has no keyword detection for cancel/pause in research mode. Only LLM action routing can trigger cancel/pause |
| **Expected Behavior** | In `mode == "research"`, detect cancel keywords (`"取消研究"`, `"cancel research"`, etc.) and pause keywords (`"暂停"`, `"pause"`, etc.) before LLM converse, and route directly to `cancel_research`/`pause_research` |
| **Severity** | **P1** — Without keyword detection, a user saying "取消研究" during a long research run must wait for LLM to process it, which can take 30+ seconds |
| **Code Location** | `research_api.py:261-324` — `_handle_user_message` |
| **Proposed Fix** | Insert keyword check block at top of `_handle_user_message` for `mode == 'research'` before the LLM converse path |

### G15 — `_handle_modify_research` calls `_cancel_existing_task` before `cm.pause()` — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Reordered: `cm.pause()` → `_save_cancel_snapshot()` → `_cancel_existing_task()` |
| **Source** | `TASK_CANCEL_PAUSE_REVISION_PLAN.md §3.2` |
| **Current Behavior** | Line 2438-2440: `_cancel_existing_task(session_id)` → then `cm.pause(session_id)`. The `_cancel_existing_task` cancels the executor task via `Task.cancel()`, which destroys the call stack before pause is set |
| **Expected Behavior** | Should `cm.pause()` first (marks pause flag, creates fresh resume event), then cancel the executor task as backup |
| **Severity** | **P1** — Cancelling before pausing means the CancelledError propagates before pause flag is set, potentially corrupting state |
| **Code Location** | `research_api.py:2438-2440` — `_handle_modify_research` |
| **Proposed Fix** | Swap order: `cm.pause(session_id)` first, then `_cancel_existing_task(session_id)` |

### G16 — `_handle_v2_revision` missing quality state integration

| Field | Detail |
|-------|--------|
| **Source** | `2026-06-01-quality-feedback-revision-design.md §5.4` |
| **Current Behavior** | No quality state snapshot, no issue state transitions, no post-revision recheck, no SSE preview_refresh push |
| **Expected Behavior** | Before revision: create `QualitySnapshotManager` snapshot, mark related issues as `revising`. After revision: recheck modified sections via `QualityCheckAgent`, update issue states, SSE push `preview_refresh` + `section_quality` |
| **Severity** | **P2** — Quality feedback loop not yet operational |
| **Code Location** | `research_api.py:2181-2246` — `_handle_v2_revision` |
| **Proposed Fix** | Implement quality state integration as described in design doc §5.4, §8.1 |

### G17 — `_handle_modify_research` missing snapshot save — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Added `await _save_cancel_snapshot(session_id, session)` between `cm.pause()` and `_cancel_existing_task()` |
| **Source** | `TASK_CANCEL_PAUSE_REVISION_PLAN.md §3.2.5` |
| **Current Behavior** | No snapshot saving before cancel + replan |
| **Expected Behavior** | Before cancelling the executor, save a `CancelSnapshot` so completed sections can be recovered |
| **Severity** | **P1** — Modify research without snapshot loses all completed work if replan or resume fails |
| **Code Location** | `research_api.py:2416-2482` — `_handle_modify_research` |
| **Proposed Fix** | Add `await _save_cancel_snapshot(session_id, session)` call after `cm.pause()` and before `_cancel_existing_task()` |

### G18 — `_handle_modify_research` should be `async def` — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Already `async def` in prior round. All 3 callers (L358, L388, L2345) use `await` correctly |
| **Source** | `TASK_CANCEL_PAUSE_REVISION_PLAN.md §3.2` |
| **Current Behavior** | Line 2416: `def _handle_modify_research(...)` — sync, but called with `await` at lines 355, 385 |
| **Expected Behavior** | Must be `async def` since it contains `await` calls (routing result, create_task, etc.) |
| **Severity** | **P0** — Calling `await` on a sync function that returns a dict raises `TypeError: object dict can't be used in 'await' expression` at runtime |
| **Code Location** | `research_api.py:2416` — function signature |
| **Proposed Fix** | Change `def` → `async def`. Verify all callers use `await` correctly |

### G19 — `_inject_merge_to_section` uses `sid = session.get('_session_id', '')` — correct now, but the section status lookup path is wrong — ✅ FIXED

| Field | Detail |
|-------|--------|
| **Fix Applied** | Added `'_session_id': session_id` to `session_manager.create()` in `start_research` so `session.get('_session_id', '')` now returns the actual session ID |
| **Source** | `RESEARCH_RUNTIME_INJECT_AND_DUPLICATE_FIX_PLAN.md §P2` |
| **Current Behavior** | `sid = session.get('_session_id', '')` — this was fixed from `getattr(session, '_session_id', '')`. However, `_session_id` is never set in the session, so `sid` is always `''`. The `_get_section_status('', section_name)` looks up `Path("data") / "" / ...` which is invalid |
| **Expected Behavior** | Should use the actual session ID passed into the method context, not a session field that was never set |
| **Severity** | **P2** — `_get_section_status` always returns `"pending"` for all inject merges, causing all merges to go through `op_type = "revise"` (re-study) instead of `"merge_requirement"` (lightweight). No data loss, but wasted computation |
| **Code Location** | `research_api.py:2409-2410` — `_inject_merge_to_section` |
| **Proposed Fix** | Store `_session_id` in session at creation time (in `start_research` L257), or pass `session_id` through the inject chain |

---

## 4. Recommended Fix Priority

### Phase 0 — Runtime Crashes (P0) — ✅ ALL FIXED

| Order | Gap ID | Description | Status |
|-------|--------|-------------|--------|
| 1 | **G13** | `_resume_after_modify` async + await + error logging | ✅ Fixed |
| 2 | **G18** | `_handle_modify_research` async def | ✅ Fixed |

### Phase 1 — Data Loss / Safety (P0-P1) — ✅ ALL FIXED

| Order | Gap ID | Description | Status |
|-------|--------|-------------|--------|
| 3 | **G01** | `cancel_research` snapshot + executor cancel + cleanup | ✅ Fixed |
| 4 | **G04** | `_save_cancel_snapshot` + `_load_cancel_snapshot` | ✅ Fixed |
| 5 | **G02** | `pause_research` snapshot + persistence | ✅ Fixed |
| 6 | **G03** | `resume_research` Path B snapshot recovery | ✅ Fixed |
| 7 | **G10** | `_confirm_v2_revision` async | ✅ Fixed |
| 8 | **G15** | `_handle_modify_research` pause-before-cancel | ✅ Fixed |
| 9 | **G17** | `_handle_modify_research` snapshot save | ✅ Fixed |

### Phase 2 — Missing Features (P1-P2) — PARTIALLY FIXED

| Order | Gap ID | Description | Status |
|-------|--------|-------------|--------|
| 10 | **G12** | `_handle_inject_requirement` routing to modify_research | ⬜ Open (design decision) |
| 11 | **G14** | Keyword cancel/pause detection in research mode | ✅ Fixed |
| 12 | **G09** | `ProgressNotifier` wiring in `_handle_v2_revision` | ✅ Fixed |
| 13 | **G11** | `continue_revision` async + notifier in `_handle_task_confirmation` | ✅ Fixed |

### Phase 3 — Quality System (P2, Design Stage)

| Order | Gap ID | Description | Effort | Dependencies |
|-------|--------|-------------|--------|-------------|
| 14 | **G05** | `QualityActionRequest` → Pydantic model | 15 min | None |
| 15 | **G06** | `handle_quality_action` + `get_quality_state` stubs | 2 h | G05, G07 |
| 16 | **G07** | `quality_state` lifecycle management | 3 h | None |
| 17 | **G08** | Quality SSE event integration | 1 h | G06 |
| 18 | **G16** | `_handle_v2_revision` quality state integration | 2 h | G07, G08 |

### Phase 4 — Cosmetic / Optimization (P2-P3) — ✅ FIXED

| Order | Gap ID | Description | Status |
|-------|--------|-------------|--------|
| 19 | **G19** | `_inject_merge_to_section` `_session_id` in session | ✅ Fixed |

---

## 5. Detailed Change List

### Phase 0 — Runtime Crashes — ✅ ALL COMPLETE

#### C1: `_resume_after_modify` → `async def` — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Fixed — already `async def` with `await`. Enhanced with error logging via `add_done_callback` and task storage in `_executor_tasks` |

#### C2: `_handle_modify_research` → `async def` — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Fixed — already `async def`. All callers use `await` correctly |

### Phase 1 — Data Loss / Safety — ✅ ALL COMPLETE

#### D1: `cancel_research` rewrite — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Rewritten with snapshot save, executor task cancel, cm.cleanup() |

#### D2: New `_save_cancel_snapshot` method — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Created `_save_cancel_snapshot()` + `_load_cancel_snapshot()`. Persists to `data/{task_id}/cancel_snapshot.json` |

#### D3: `pause_research` enhanced — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Added `_save_cancel_snapshot()`, task persistence pause |

#### D4: `resume_research` Path B — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Implemented Path B via `_load_cancel_snapshot()` + `_resume_from_snapshot()`. Rebuilds plan for pending sections only |

#### D5: `_confirm_v2_revision` → async — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Already `async def` |

#### D6: Fix pause-before-cancel ordering in `_handle_modify_research` — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Reordered: `cm.pause()` → `_save_cancel_snapshot()` → `_cancel_existing_task()` |

#### D7: Add snapshot save in `_handle_modify_research` — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Added between pause and cancel |

### Phase 2 — Missing Features — PARTIALLY COMPLETE

#### F1: Fix `_handle_inject_requirement` routing — ⬜ OPEN

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ⬜ Open — design decision: current routing to `_handle_modify_research` works but is heavyweight |

#### F2: Add keyword cancel/pause detection — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Added keyword detection block in `_handle_user_message` for research mode |

#### F3: Fix `ProgressNotifier` wiring — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Already fixed: `RevisionExecutor(lock_manager=..., notifier=notifier)` |

#### F4: Verify `continue_revision` sync/async — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Already `await executor.continue_revision(...)`. Also added `notifier` to `RevisionExecutor` construction |

### Phase 3 — Quality System

#### Q1: `QualityActionRequest` Pydantic model

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Method** | `QualityActionRequest` class (L2506-2511) |
| **Change** | Replace with Pydantic BaseModel: `session_id: str`, `action: Literal[...]`, optional fields |
| **Risk** | Low — standalone class, no callers outside this file |
| **Verification** | Pydantic validation works on inputs |

#### Q2: `handle_quality_action` full implementation

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Method** | `handle_quality_action` (L2514-2522) |
| **Change** | Implement 5 action handlers, `QualityState` lifecycle, issue state machine |
| **Risk** | Medium — new complex logic |
| **Verification** | Run quality action tests (design doc §15) |

#### Q3: Quality state session management

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py`, `src/core/quality/quality_state.py` |
| **Change** | Create `QualityState`, `SectionScore`, `QualityIssue`, `VersionInfo` Pydantic models; manage `session["quality_state"]` lifecycle |
| **Risk** | Medium — new module + session integration |
| **Verification** | Verify session persistence of quality state |

#### Q4: Quality SSE integration

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py`, `src/core/session_streamer.py` |
| **Change** | Integrate `push_preview_refresh` + `push_quality_confirmed` into revision/quality flows |
| **Risk** | Low — additive SSE events |
| **Verification** | Subscribe to SSE events; verify correct payload |

#### Q5: `_handle_v2_revision` quality integration

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Method** | `_handle_v2_revision` (L2181-2246) |
| **Change** | Add pre-revision snapshot, issue state transitions, post-revision recheck, SSE preview refresh |
| **Risk** | Medium — modifies critical revision path |
| **Verification** | Run quality feedback loop E2E test |

### Phase 4 — Cosmetic — ✅ ALL COMPLETE

#### N1: Fix `_session_id` in inject_merge_to_section — ✅ DONE

| Field | Value |
|-------|-------|
| **File** | `src/api/research_api.py` |
| **Status** | ✅ Added `'_session_id': session_id` to `session_manager.create()` in `start_research` |

---

## Appendix A: Design Document Cross-Reference

| Doc | Status | Key Gaps |
|-----|--------|----------|
| `REVISION_V2_INTEGRATION_PLAN.md` | ✅ Fully implemented | None remaining — G09, G10, G11 all fixed |
| `tool-call-chain-fix-plan.md` | ✅ Fully implemented | None — Phase 1+2 complete, dead code removed |
| `TASK_CANCEL_PAUSE_REVISION_PLAN.md` v5 | ✅ Fully implemented | None remaining — G01, G02, G03, G04, G13, G14, G15, G17, G18 all fixed |
| `RESEARCH_RUNTIME_INJECT_AND_DUPLICATE_FIX_PLAN.md` | Mostly implemented | G12 (inject routing still routes to modify_research — design decision), G19 ✅ fixed |
| `2026-06-01-quality-feedback-revision-design.md` | Design stage only | G05, G06, G07, G08, G16 — quality system not yet built |
| `REVISION_BEFORE_AFTER.md` | Informational only | No gaps — comparison summary document |
| `API.md` | Informational only | No gaps — general API overview |
| `fix_plan_stale_pause_flag.md` | ✅ Fully implemented | All 3 fixes applied (P0 clears flag, P1 log, P2 terminal check) |
| `revision_system_v3_p1p2_design.md` | Not implemented | P1 (table/chart ops) and P2 (paragraph/sentence/translate) operations not implemented |
| `REVISION_SYSTEM_FIX_PLAN.md` | ✅ Mostly implemented | C1, D2, D3 done; I1 assessed; I2/I3 methods not found in current codebase |

## Appendix B: Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| G13 fix reveals latent bug in executor | Medium | P0 | Test with full E2E suite |
| G01 rewrite introduces new cancel bugs | Medium | P0 | Add cancel_cascade unit tests before writing |
| G09 ProgressNotifier breakage | Medium | P1 | Check RevisionExecutor.__init__ signature first |
| G18 fix: sync→async breaks sync caller pattern | Low | P0 | Grep all callers before change |
| Quality system (Phase 3) scope creep | High | P2 | Treat as separate implementation phase |
