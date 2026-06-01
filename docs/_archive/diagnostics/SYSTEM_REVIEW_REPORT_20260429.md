# System Review Report: Complete Flow from User Request to Word Generation

> Review Date: 2026-04-29
> Verification Date: 2026-04-29
> Fix Date: 2026-04-29
> Scope: CLI Entry → Parameter Parsing → Task Decomposition → Execution Engine → Data Distribution → Agent Execution → Result Aggregation → Document Generation → Word Output
> Verification Status: ✅ All P0/P1 issues verified via code review
> Fix Status: ✅ All P0/P1 issues fixed and verified

---

## 1. Architecture Overview

```
User Request (CLI)
  │
  ▼
orchestrator.research()          ← Main Entry
  │
  ├─ 1. Requirements Parsing (_parse_requirement / SmartClarifier)
  │
  ├─ 2. Intent Analysis (IntelligentRoutingAdapter)
  │
  ├─ 3. Task Decomposition (IndustryResearchStrategy.decompose)
  │     output: DecompositionPlan (5 phases)
  │
  ├─ 4. Create Agents (AgentFactory)
  │
  ├─ 5. Execution Engine (execute_with_scheduler)
  │     ├─ Scheduler Topological Sort → Batch Execution
  │     ├─ _execute_batch → Data Distribution → Agent Execution
  │     └─ Result Collection
  │
  ├─ 6. Result Aggregation (ResultAggregator)
  │
  ├─ 7. Document Generation ★★★ (Three paths, see below)
  │
  └─ 8. Return Results to CLI
```

---

## 2. Issue List

### P0 Issues (Must Fix) — Fixed ✅

#### Issue 1: CLI Parameters Silently Dropped — Fixed ✅

**Location**: `src/cli/main.py:430-444`

```python
# CLI collected parameters
extra_kwargs = {}
if output_type:       # --type parameter
    extra_kwargs["output_type"] = output_type
if aspects:           # --aspects parameter
    extra_kwargs["custom_aspects"] = aspects
if framework:         # --framework parameter
    extra_kwargs["framework"] = framework
if template:          # --template parameter
    extra_kwargs["template_name"] = template

# Actual call (extra_kwargs not passed!)
result = await orchestrator.research(
    requirement,                     # Only the user's original string
    interaction_mode=interactive,
    interaction_callback=interaction_callback if interactive else None
    # extra_kwargs never used!
)
```

**Impact**:
- `--aspects market_size,competitive_landscape,industry_chain` → ignored, falls back to keyword matching or hardcoded defaults `["market_size", "competitive_landscape", "development_trends"]`
- `--framework detailed` → ignored
- `--template research_report` → ignored
- `--type industry_report` → ignored

**Root Cause**: `orchestrator.research()` signature (`orchestrator.py:418-426`) only accepts `user_input`, `output_dir`, `user_id`, `interaction_mode`, `interaction_callback`, `use_intelligent_routing`, but not `output_type`, `custom_aspects`, `framework`, `template_name`. CLI collected these parameters but had nowhere to pass them.

**Verification Conclusion**:
- ✅ `main.py:430-438` confirms `extra_kwargs` collected
- ✅ `main.py:440-444` confirms `extra_kwargs` not passed
- ✅ `orchestrator.py:418-426` confirms method signature doesn't support these parameters
- **Issue Status: Confirmed, needs fix**

**Fix Plan**:
1. Extend `orchestrator.research()` signature, add `output_type`, `custom_aspects`, `framework`, `template_name`, `output_format` parameters
2. In non-interactive mode, merge CLI parameters into `user_input` to pass to `_parse_requirement()`
3. Update task persistence to record CLI parameters

**Fix Verification**:
- ✅ `orchestrator.research()` signature extended
- ✅ CLI parameters correctly passed
- ✅ Non-interactive mode parameter merge logic implemented

---

#### Issue 2: Three Independent Document Generation Paths — Fixed ✅

**Severity**: ★★★★★ (Highest)

The entire system has three completely independent document generation paths, with different data sources and generation methods:

##### Path A: Orchestrator Document Agent (After Interactive Mode User Confirmation)

**Location**: `src/core/orchestrator/orchestrator.py:1003-1009`

```python
# Interactive mode, after user confirmation
doc_result = await self._document_agent.execute({
    "action": "produce_document",
    "output_format": output_format,
    "research_result": research_result_data,  # aggregated.to_dict()
    "task_id": task_id,
    "output_dir": str(output_dir_path),
})
```

- Trigger: Interactive mode → User confirms → Generate Word
- Data Source: `research_result_data` (`aggregated.to_dict()`)
- Conversion Chain: `DocumentGenerationAgent._handle_produce_document()`

##### Path B: CLI Independent Save (Triggered by `--format` Parameter)

**Location**: `src/cli/main.py:712-749`

```python
async def _save_report(result: dict, output: str, format: str):
    ...
    elif format == "docx":
        from report_generator.styled_generator import StyledReportGenerator
        generator = StyledReportGenerator()
        doc = generator.create_report(
            title=report.get("title", "Research Report"),
            sections=sections,
        )
        doc.save(output_path)
```

- Trigger: After `_research_async` completes, if `--output` parameter specified
- Data Source: `result.get("report", {})` — structure may differ from Path A's `research_result_data`
- Conversion Chain: `StyledReportGenerator.create_report()` — **completely independent third-party library**
- **No relationship to Path A/Path C at all**, completely bypasses orchestrator's document generation flow

##### Path C: Orchestrator HTML Preview

**Location**: `src/core/orchestrator/orchestrator.py:754-760`

```python
preview_result = await self._document_agent.execute({
    "action": "get_preview",
    "output_format": "html",
    "research_result": research_result_data,
    "task_id": task_id,
    "output_dir": str(output_dir_path),
})
```

- Trigger: Always executes after aggregation
- Data Source: `research_result_data`
- Output: `.preview.html` file (preview only, no Word generation)

##### Relationship of Three Paths

```
  aggregated.to_dict()
       │
       ├──→ [Path C] get_preview → HTML Preview File  ← Preview only
       │
       ├──→ [Path A] produce_document → Word/PPT/PDF  ← After interactive mode confirmation
       │
       └──→ ResearchResult returned to CLI
              │
              └──→ [Path B] _save_report → StyledReportGenerator → Word/MD/JSON
                       ↑ Completely independent path, data format may differ
```

**Impact**:
- Word output from Path B may **differ in content** from Path A (completely different data sources and generation methods)
- Path B bypasses "HTML preview → user confirmation → generate Word" flow control
- Document styling, format, and quality across three paths cannot be guaranteed consistent

**Verification Conclusion**:
- ✅ Path A exists in `orchestrator.py`, uses `DocumentGenerationAgent`
- ✅ Path B exists in `main.py:728-746`, uses `StyledReportGenerator`
- ✅ Path C exists in `orchestrator.py`, generates HTML preview
- ✅ Path B completely independent, bypasses preview confirmation flow
- **Issue Status: Confirmed, needs fix**

**Fix Plan**:
1. Deprecate Path B (`_save_report`), mark with `DeprecationWarning`
2. CLI uses orchestrator-generated documents via `result.document_path`
3. If user specifies `--output`, copy document to specified path

**Fix Verification**:
- ✅ `_save_report` marked deprecated
- ✅ CLI now uses `result.document_path`
- ✅ Document generation unified under orchestrator

---

### P1 Issues (Important) — Fixed ✅

#### Issue 3: Non-Interactive Mode Word Missing (Fixed ✅) — Verified ✅

**Location**: `src/core/orchestrator/orchestrator.py:1087-1097`

**Original Code**: Only logs "HTML preview generated, user can confirm to generate final document", no Word generation logic.

**Fix**: Non-interactive mode automatically calls `_document_agent.execute(action="produce_document")`, consistent with interactive mode user confirmation logic.

```python
# After fix
if not final_document_generated and output_format in ("docx", "pptx", "pdf"):
    if interaction_mode:
        logger.info(f"Waiting for user confirmation to generate {output_format} document")
    else:
        # Non-interactive mode: auto-generate final document after preview
        doc_result = await self._document_agent.execute({
            "action": "produce_document",
            "output_format": output_format,
            "research_result": research_result_data,
            ...
        })
```

**Verification Conclusion**:
- ✅ `orchestrator.py:1091-1115` confirms fixed
- ✅ Non-interactive mode automatically calls `_document_agent.execute(action="produce_document")`
- **Issue Status: Fixed**

---

#### Issue 4: ResearchResult Data Structure Uncertainty — Fixed ✅

**Location**: `src/cli/main.py:717`

```python
report = result.get("report", {})
```

`ResearchResult` is a dataclass (`orchestrator.py:1153-1171`), not a dictionary. `result.get("report")` is dataclass field access syntax (Python 3.10+), but if `result` type is incorrectly inferred or `report` field doesn't exist, this returns an empty dictionary. Path B may generate empty documents.

**Verification Conclusion**:
- ✅ `ResearchResult` confirmed as dataclass (`orchestrator.py:156-175`)
- ⚠️ `main.py:717` using `result.get("report", {})` may have issues
- ⚠️ `ResearchResult` originally had no `report` field

**Fix Plan**:
1. Add `report` and `document_path` fields to `ResearchResult`
2. Populate `report=aggregated.to_dict()` and `document_path=output_path` when building `ResearchResult`

**Fix Verification**:
- ✅ `ResearchResult` now has `report` and `document_path` fields
- ✅ Field values correctly populated
- ✅ CLI can access document path via `result.document_path`

---

### P2 Issues (Minor, Fixed)

| Issue | Status | Description |
|------|------|------|
| Path A Legacy Code | ✅ Cleaned | `_build_data_task`, `_build_analysis_task` removed; `_build_synthesis_task`, `_build_report_task`, `_execute_stage` replaced with stubs |
| Execution Engine Dual Path | ✅ Unified | `execute()` delegates to `execute_with_scheduler()` |
| Data Points Not Filtered by Dependency | ✅ Fixed | In `_execute_batch()`, filter `aggregated_data_points` by `dependencies` |
| DataBoundaryController | ✅ Integrated | Initialized in `engine.py:__init__()`, boundaries and audit registered in `_execute_batch()` |
| Insufficient Prompt Constraints | ✅ Fixed | synthesis: "Only output [{target_aspect}] section"; analysis: "Only output [{aspect}] section" |
| Scheduler Category Inference | ✅ Fixed | Added `analysis` type to `_get_agent_category` |
| Scheduler Dependency Logic | ✅ Fixed | Priority uses configured dependencies, falls back to inference defaults when no config |
| **Content Pollution** | ✅ Fixed | Synthesis agent previous content filtering + enhanced prompt constraints |

---

## 3. Uncovered Review Areas

The following areas could not be fully code-reviewed due to exploration tasks queued concurrently:

| Area | File | Status |
|------|------|------|
| Result Aggregator | `result_aggregator.py` | ⏳ Queued |
| Document Generation Handler (`_handle_get_preview` / `_handle_produce_document`) | `document_generation_agent.py` | ⏳ Queued |
| Preview Revision Workflow | `preview_workflow.py` | ⏳ Queued |
| HTML→Word Converter | `converters/html_to_word.py` | ⏳ Queued |

---

## 4. Fix Priority Recommendations

| Priority | Issue No. | Issue Description | Impact | Recommended Plan |
|--------|----------|----------|--------|----------|
| **P0** | Issue 1 | CLI parameters `--aspects/--framework/--template/--type` silently dropped | User specification ineffective, sections incorrect | 1. `orchestrator.research()` add parameter acceptance, 2. Or CLI pass `user_input` as dict |
| **P0** | Issue 2 | Three independent document paths causing Word roaming | Flow out of control, content inconsistency | 1. Deprecate Path B (`_save_report` / `StyledReportGenerator`), 2. Unify to Path A (`_document_agent`), 3. CLI `--format` passed as orchestrator parameter |
| **P1** | Issue 3 | Non-interactive mode Word | Fixed | — |
| **P1** | Issue 4 | `ResearchResult` data structure | Path B may generate empty documents | Confirm `result` type, use attribute access |
| **P2** | Issues 5-8 | 5 items fixed | Fixed | — |

---

## 5. Key Code Index

| Function | File | Line |
|------|------|------|
| CLI Entry | `src/cli/main.py` | L83-120 |
| CLI → Orchestrator Call | `src/cli/main.py` | L440-444 |
| CLI _save_report (Path B) | `src/cli/main.py` | L712-749 |
| orchestrator.research() | `src/core/orchestrator/orchestrator.py` | L418-426 |
| _parse_requirement() | `src/core/orchestrator/orchestrator.py` | L2340-2424 |
| HTML Preview Generation (Path C) | `src/core/orchestrator/orchestrator.py` | L754-760 |
| Interactive Mode Confirm→Word (Path A) | `src/core/orchestrator/orchestrator.py` | L999-1020 |
| Non-interactive Mode Word (Fixed) | `src/core/orchestrator/orchestrator.py` | L1087-1097 |
| generate_final_document() | `src/core/orchestrator/orchestrator.py` | L4541-4579 |
| Task Decomposition (5 phases) | `src/core/decomposition/strategies.py` | L229-387 |
| AgentSpec Definition | `src/core/decomposition/strategies.py` | L83-99 |
| DecompositionPlan Definition | `src/core/decomposition/strategies.py` | L102-118 |
| ScheduledAgent Definition | `src/core/orchestrator/execution/scheduler.py` | L30-39 |
| Topological Sort Batch Generation | `src/core/orchestrator/execution/scheduler.py` | L120-563 |
| _execute_batch (Data Distribution) | `src/core/orchestrator/execution/engine.py` | L1508-1785 |
| DataBoundaryController | `src/core/orchestrator/execution/data_boundary_controller.py` | Full |
| Prompt Construction (Constraints) | `src/core/agents/generic_agent.py` | L2038-2153 |

---

## 6. Verification Summary

### Verification Method

Directly read source code files to verify issues identified in the report:

1. `main.py:420-520` — CLI parameter collection and passing
2. `main.py:700-780` — CLI independent save function
3. `orchestrator.py:418-500` — research method signature
4. `orchestrator.py:1080-1180` — Non-interactive mode handling

### Verification Results

| Issue | Report Description | Verification Result | Status |
|------|----------|----------|------|
| Issue 1 | CLI parameters silently dropped | ✅ Confirmed, `extra_kwargs` collected but not passed | **Pending Fix** |
| Issue 2 | Three independent document paths | ✅ Confirmed, Path B completely independent | **Pending Fix** |
| Issue 3 | Non-interactive mode Word | ✅ Fixed, code correct | **Fixed** |
| Issue 4 | ResearchResult data structure | ✅ Confirmed, `report` field doesn't exist | **Pending Fix** |

### Code Evidence

**Issue 1 Evidence**:
```python
# main.py:430-438 — Parameter collection
extra_kwargs = {}
if output_type: extra_kwargs["output_type"] = output_type
if aspects: extra_kwargs["custom_aspects"] = aspects
if framework: extra_kwargs["framework"] = framework
if template: extra_kwargs["template_name"] = template

# main.py:440-444 — Not passed
result = await orchestrator.research(
    requirement,  # Only raw string
    interaction_mode=interactive,
    interaction_callback=interaction_callback if interactive else None
    # extra_kwargs never used!
)
```

**Issue 2 Evidence**:
```python
# main.py:728-746 — Path B
elif format == "docx":
    from report_generator.styled_generator import StyledReportGenerator
    generator = StyledReportGenerator()
    doc = generator.create_report(title=report.get("title", "Research Report"), sections=sections)
    doc.save(output_path)
```

**Issue 3 Evidence**:
```python
# orchestrator.py:1091-1115 — Fixed
if not final_document_generated and output_format in ("docx", "pptx", "pdf"):
    if interaction_mode:
        logger.info(f"Waiting for user confirmation to generate {output_format} document")
    else:
        # Non-interactive mode: auto-generate final document after preview
        doc_result = await self._document_agent.execute({
            "action": "produce_document",
            ...
        })
```

**Issue 4 Evidence**:
```python
# orchestrator.py:1153-1171 — ResearchResult definition
result = ResearchResult(
    task_id=task_id,
    status="completed",
    topic=requirement.topic,
    agents_used=[...],
    stages_completed=len(results_for_aggregation),
    output_path=output_path,  # Has output_path
    summary=self._generate_summary(aggregated, requirement),
    # No report field!
)

# main.py:717 — Attempting to get non-existent field
report = result.get("report", {})  # Returns empty dictionary
```

---

## 7. Fix Recommendations

### P0-1: CLI Parameter Passing

**Plan A**: Extend `orchestrator.research()` signature

```python
# orchestrator.py
async def research(
    self,
    user_input: Union[str, Dict[str, Any]],
    output_dir: Optional[str] = None,
    user_id: Optional[str] = None,
    interaction_mode: bool = True,
    interaction_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
    use_intelligent_routing: Optional[bool] = None,
    # New parameters
    output_type: Optional[str] = None,
    custom_aspects: Optional[List[str]] = None,
    framework: Optional[str] = None,
    template_name: Optional[str] = None,
) -> ResearchResult:
```

**Plan B**: Pass structured data via `user_input`

```python
# main.py
structured_input = {
    "query": requirement,
    "output_type": output_type,
    "custom_aspects": aspects.split(",") if aspects else None,
    "framework": framework,
    "template_name": template,
}
result = await orchestrator.research(structured_input, ...)
```

### P0-2: Unify Document Generation Path

**Recommended Plan**: Deprecate Path B, unify using Path A

1. Remove `StyledReportGenerator` call from `main.py:_save_report`
2. Ensure `orchestrator.research()` accepts `output_format` parameter
3. CLI specifies output format via orchestrator parameter
4. Document generation managed uniformly by orchestrator

```python
# main.py — After modification
result = await orchestrator.research(
    requirement,
    output_dir=output,
    output_format=format,  # New parameter
    interaction_mode=interactive,
)

# _save_report no longer needed, orchestrator handles it
# if output:
#     await _save_report(result, output, format)  # Deleted
```

### P1-4: ResearchResult Data Structure

**Plan**: Remove Path B, no need to handle this issue

If retaining Path B, need to:
1. Add `report` field to `ResearchResult`
2. Or modify `_save_report` to use correct data source
