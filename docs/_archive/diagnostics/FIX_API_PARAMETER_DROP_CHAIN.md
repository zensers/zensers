# API Parameter Drop Chain Fix Plan

> Version: v1.0
> Date: 2026-05-04
> Status: Pending Review

---

## Table of Contents

1. [Problem Overview](#1-problem-overview)
2. [Fixed Items](#2-fixed-items)
3. [Pending Items](#3-pending-items)
4. [Detailed Design and Fix Plan](#4-detailed-design-and-fix-plan)
5. [File Modification List](#5-file-modification-list)
6. [Implementation Roadmap](#6-implementation-roadmap)

---

## 1. Problem Overview

### 1.1 Complete Parameter Drop Chain

After implementing the survey framework dynamic parameterization refactoring (`docs/REPORT_FRAMEWORK_INTERACTION_REFACTOR.md`), multiple breaks were found in the parameter transfer chain from frontend to backend, causing `region`, `time_range`, `company_name` and other parameters to be silently dropped during transfer.

```
Frontend -> main.py(route) -> research_api -> research_executor -> orchestrator
 ①          ②                  ③               ④                   ⑤
```

| Step | File | Problem | Status |
|------|------|--------|--------|
| ① | `web/src/lib/api.ts` | Frontend only sends `parameters` JSON, backend doesn't recognize it | Fixed |
| ② | `src/api/main.py` | quick-start route only recognizes three independent fields: `region/time_range/depth` | Fixed |
| ③ | `src/api/research_api.py` | `quick_start()` receives parameters but doesn't store them in session | Fixed |
| ④ | `src/api/research_executor.py` | `execute()` doesn't read parameters from session, doesn't pass to orchestrator | Fixed |
| ⑤ | `src/core/orchestrator/orchestrator.py` | `research()` signature has no parameter slot, but can read from dict input | No fix needed (dict path works) |

### 1.2 Pre-existing Issues Found by Audit

| # | Problem | File | Severity | Description |
|---|--------|------|----------|-------------|
| P1 | **`_handle_research_flow` only implements step 1, steps 2-5 all return `"Invalid step"`** | `research_api.py:1073-1102` | **HIGH** | Template/section selection/parameter settings/confirmation in the interactive flow are all short-circuited; this path may have been unusable all along |
| P2 | **Dialogue path executor also doesn't pass parameters** | `research_executor.py:114` | **MEDIUM** | In the `start` -> dialogue path, parameters are stored via `context.details`, but the executor only passes topic and output_type to orchestrator |
| P3 | **`interact` endpoint `step 4 response` parameter format not validated** | `research_api.py:940-958` | **LOW** | In the dialogue path, step 4 response is directly passed through to SmartClarifier, but Clarifier's `confirm_parameters` has been changed to `**kwargs`, theoretically compatible |

---

## 2. Fixed Items

The following fixes have been completed in this session:

| File | Change | Related Issue |
|------|--------|---------------|
| `web/src/lib/api.ts` | `quickStart()` sends `parameters` JSON + backward-compatible independent fields | ① |
| `src/api/main.py` | Added `parameters: Optional[str] = Form(None)` parameter, parses JSON and merges | ② |
| `src/api/research_api.py` | `quick_start()` stores dynamic parameters in session object | ③ |
| `src/api/research_executor.py` | `execute()` reads 9 parameter keys from session and constructs `user_input_dict` for orchestrator | ④ |

---

## 3. Pending Items

### P1 -- `_handle_research_flow` Only Handles Step 1

**File:** `src/api/research_api.py`

**Code Location:**

```python
async def _handle_research_flow(self, session_id, step, response):
    """Handle research flow steps"""
    session = self._sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    
    clarifier = session.get("clarifier")
    if not clarifier:
        return {"error": "Clarifier not found"}
    
    if step == 1:
        # Select output type
        output_type = response.get("output_type")
        result = clarifier.select_output_type(output_type)
        # ... only step 1 implementation ...
        return result
    
    # steps 2, 3, 4, 5 all reach here
    return {"error": "Invalid step", "error_code": "INVALID_STEP"}
```

**Impact:** The frontend `useResearch.ts`'s `selectTemplate()`, `selectSections()`, `setParameters()`, `confirmResearch()` all return `"Invalid step"`, the interactive flow cannot proceed to step 5.

**Root Cause Analysis:** 
- Possibly historical legacy; `_handle_research_flow` code was truncated or incomplete
- Or the interactive flow has already migrated to the dialogue path (`mode=chat/framework/research`), and the old step path was deprecated but not cleaned up

**Need to confirm first:** Which path does the frontend actually use?
- If it's the `useResearch.ts` `selectOutputType -> interact({step:1})` path -> This path doesn't work
- If it's the `sendMessage -> interact({step:0})` dialogue path -> This path goes through `_handle_user_message`, unaffected

**How to confirm in code:**
- Check which branch of `useResearch.ts`'s `handleOptionSelect` and `sendMessage` is actually called
- Check whether `ChatPanel.tsx`'s `currentStep` shows 1-5 or always 0 (dialogue mode)

---

### P2 -- Dialogue Path Executor Parameter Passthrough

**File:** `src/api/research_executor.py`

**Code Location:**

```python
context = session.get("research_context", {})
topic = context.get("topic", "")
framework = context.get("framework", {})
output_type = session.get("output_type", framework.get("output_type", "industry_report"))
# ↑ Here only topic, framework.sections, output_type are taken
# ↓ context.details.region/time_range/depth are not taken
orchestrator_result = await self._orchestrator.research(
    user_input=topic or user_input,
    output_type=output_type,
    custom_aspects=framework.get("sections", None),
    # ↑ region/time_range/depth not passed
)
```

Parameters for the dialogue path are stored in `context.details` (see `_generate_research_framework`, lines 987-989), but the executor does not read `context.details`.

**Impact:** Research started from the dialogue path also cannot receive `region`/`time_range`/`depth` parameters; they use default values as well.

---

## 4. Detailed Design and Fix Plan

### 4.1 Fix P1: Complete `_handle_research_flow`

**Goal:** Make steps 2-5 of the HTTP API path work correctly

```python
async def _handle_research_flow(self, session_id, step, response):
    session = self._sessions.get(session_id)
    clarifier = session.get("clarifier")
    
    if step == 1:
        output_type = response.get("output_type")
        result = clarifier.select_output_type(output_type)
        session["current_step"] = 2
        return result
    
    elif step == 2:
        # Select template/framework
        template_id = response.get("template_id")
        if template_id:
            result = clarifier.select_template(template_id)
        else:
            framework_id = response.get("framework_id")
            result = clarifier.select_framework(framework_id)
        session["current_step"] = 3
        return result
    
    elif step == 3:
        # Select/confirm sections
        selected_sections = response.get("selected_sections", [])
        confirmed = response.get("confirmed", True)
        adjustments = response.get("adjustments")
        result = clarifier.confirm_sections(
            confirmed=confirmed,
            adjustments=adjustments,
        )
        session["current_step"] = 4
        return result
    
    elif step == 4:
        # Set parameters (dynamic parameters, arbitrary key-value)
        result = clarifier.confirm_parameters(**response)
        session["current_step"] = 5
        return result
    
    elif step == 5:
        # Final confirmation
        confirmed = response.get("confirmed", False)
        result = clarifier.confirm(confirmed=confirmed)
        if confirmed and result.get("final_plan"):
            # Directly enter execution phase
            final_plan = result["final_plan"]
            user_choice = clarifier.get_final_requirement()
            if user_choice:
                session["output_type"] = user_choice.output_type.value
                session["region"] = user_choice.region
                session["time_range"] = user_choice.time_range
                # Store in context for executor use
                context = session.get("research_context", {})
                context["details"] = context.get("details", {})
                context["details"]["region"] = user_choice.region
                context["details"]["time_range"] = user_choice.time_range
                context["details"]["depth"] = user_choice.depth
                session["research_context"] = context
            
            return {
                "step": 6,
                "status": "executing",
                "final_plan": final_plan,
                **result,
            }
        return result
    
    return {"error": "Invalid step", "error_code": "INVALID_STEP"}
```

**Design Points:**
- Step 3's `confirm_sections()` now returns dynamic parameters (already completed by SmartClarifier refactoring)
- Step 4's `confirm_parameters(**response)` has been changed to `**kwargs`, accepts arbitrary parameters
- After step 5 confirmation, store parameters in `session["research_context"]["details"]`, consistent with the dialogue path storage format
- Reuses existing executor logic (executor reads `context.details`)

---

### 4.2 Fix P2: Executor Reads `context.details`

**Goal:** Make the executor correctly read parameters regardless of whether from quick-start or dialogue path

```python
# Existing session reading logic in executor
context = session.get("research_context", {})
topic = context.get("topic", "")
framework = context.get("framework", {})

# NEW: Read dialogue path parameters from context.details
details = context.get("details", {})
for key in ("region", "time_range", "depth"):
    if key in details and key not in user_input_dict:
        user_input_dict[key] = details[key]

# NEW: Read compatible fields from context top level
for key in ("region", "time_range"):
    if key in context and key not in user_input_dict:
        user_input_dict[key] = context[key]
```

Note: This part of `research_executor.py` has been consolidated in the P1 fix and does not need separate changes. If P1 is fixed first, P2 is naturally resolved.

---

## 5. File Modification List

### Already Modified (Completed in This Session)

| File | Change Description |
|------|--------------------|
| `web/src/lib/api.ts` | `quickStart()` sends parameters JSON + independent dual-format fields |
| `src/api/main.py` | quick-start route added `parameters` form field; parses JSON and merges |
| `src/api/research_api.py` | `quick_start()` stores dynamic parameters in session |
| `src/api/research_executor.py` | `execute()` extracts 9 parameter keys from session to construct `user_input_dict` |

### To Be Modified -- P1 Fix

| File | Change Description | Estimated Lines |
|------|--------------------|-----------------|
| `src/api/research_api.py` | Complete `_handle_research_flow()` step 2-5 handling logic | ~80 lines |
| `src/api/research_api.py` | After step 5 confirmation, store parameters in `session["research_context"]["details"]` | ~15 lines |

### To Be Modified -- P2 Fix

P2 is naturally resolved in the P1 fix (the executor reads `context.details` logic is already included in P1's step 5). No separate modification needed.

### Files That Do Not Need Changes

| File | Reason |
|------|--------|
| `src/core/orchestrator/orchestrator.py` | `research()`'s `user_input` supports `Dict` type, `_parse_requirement()` can extract region/time_range from it |
| `src/core/orchestrator/smart_clarifier.py` | `confirm_parameters(**kwargs)` already supports dynamic parameters |
| `web/src/components/chat/DynamicParameterForm.tsx` | Frontend component already works correctly, parameters sent to backend via `setParameters()` |

---

## 6. Implementation Roadmap

### Phase 1: Confirm Interaction Path (Estimated 0.5 day)

| Step | Description |
|------|-------------|
| 1.1 | Read frontend `ChatPanel.tsx`, confirm whether `handleOptionSelect` or `sendMessage` is the actual interaction path |
| 1.2 | Read backend `research_api.py` `handle_interact`, confirm the dispatch logic between `_handle_user_message` and `_handle_research_flow` |
| 1.3 | Write confirmation result to this document |

**Result determines subsequent plan:**
- If frontend uses `step 1-5` path -> Fix `_handle_research_flow`
- If frontend uses `step 0` dialogue path -> No need to fix `_handle_research_flow`

### Phase 2: Fix Confirmed Path (Estimated 1 day)

| Step | Description | File |
|------|-------------|------|
| 2.1 | Complete `_handle_research_flow` steps 2-5 | `src/api/research_api.py` |
| 2.2 | Store parameters to `context.details` after step 5 confirmation | Same as above |
| 2.3 | Verify `confirm_parameters(**response)` compatibility | Same as above |

### Phase 3: Verification (Estimated 0.5 day)

| Step | Description |
|------|-------------|
| 3.1 | Start backend, use curl to simulate complete step 1-5 interactive flow |
| 3.2 | Verify `region`/`time_range`/`company_name` and other parameters correctly pass to orchestrator |
| 3.3 | Verify `/template` quick-start path parameters pass correctly |
| 3.4 | Frontend `npm run build` confirms no type errors |

---

## Appendix: Complete Parameter Link Diagram

```
┌─────────────────────────┐
│   /template Quick Start  │
├─────────────────────────┤
│                         │
│  Frontend ChatPanel     │
│  └─ parseTemplateCommand│
│     -> quickStartResearch│
│        -> api.quickStart │
│           -> FormData:   │
│             parameters= │
│             JSON+indiv  │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│  main.py: quick_start()  │  <- Fixed
│  └─ Form -> custom_params │
│     <- parameters JSON   │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│  research_api:          │
│  quick_start()          │  <- Fixed
│  └─ session["region"]=  │
│     session["custom_    │
│     params"] = ...      │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│  research_executor:     │
│  execute()              │  <- Fixed
│  └─ session ->           │
│     user_input_dict     │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│  orchestrator.research()│
│  └─ _parse_requirement()│  <- Dict path works
│     -> region="China"   │
│       time_range="Last 3 years" │
└─────────────────────────┘


┌─────────────────────────┐
│   Dialogue/Interaction   │
│   Path (step 1-5)       │
├─────────────────────────┤
│                         │
│  Frontend               │
│  └─ handleOptionSelect  │
│     -> selectOutputType()│
│     -> interact(step=1)  │
│     -> selectTemplate()  │
│     -> interact(step=2)  │  <- _handle_research_flow
│     -> selectSections()  │     only handles step 1
│     -> interact(step=3)  │
│     -> setParameters()   │
│     -> interact(step=4)  │
│     -> confirmResearch() │
│     -> interact(step=5)  │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│  _handle_research_flow() │  <- Needs fix
│  step 1: Implemented    │
│  step 2: Invalid step   │
│  step 3: Invalid step   │
│  step 4: Invalid step   │
│  step 5: Invalid step   │
└─────────────────────────┘
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-05-04 | Initial draft |
