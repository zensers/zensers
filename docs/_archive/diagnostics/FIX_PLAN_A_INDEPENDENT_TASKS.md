# Plan A Implementation: Independent Task Distribution

## Problem

```
Current flow (problematic):

Analysis Agent 1 ──┐
Analysis Agent 2 ──┼──► _build_synthesis_task() ──► Same task
Analysis Agent 3 ──┘           │
                               ▼
                    ┌──────────────────────────┐
                    │ Executive Summary Agent  │
                    │ Research Conclusions Agent│  ← Both receive the same task
                    └──────────────────────────┘
                               │
                               ▼
                     Output: Executive Summary + Market Overview + Research Conclusions (contamination)
```

## Fix Plan

### Modification 1: `_execute_stage` (engine.py lines 618-725)

**Core Change**: Each agent in the synthesis phase receives an independent task

```python
# Contamination fix: synthesis phase each agent receives independent task
is_synthesis_stage = stage_name == "synthesis"

if is_synthesis_stage and len(agents) > 1:
    # Each synthesis agent receives an independent task
    for agent in agents:
        agent_aspect = self._extract_aspect_from_agent_id(agent.agent_id)
        agent_task = task_builder(
            requirement=kwargs.get("requirement"),
            previous_results=kwargs.get("previous_results"),
            target_aspect=agent_aspect,  # Pass target section
        )
        # Distribute independent task
        task_id = await self._coordinator.dispatch_task(agent=agent, task=agent_task, ...)
```

### Modification 2: `_build_synthesis_task` (engine.py lines 726-810)

**Core Change**:
1. Support `target_aspect` parameter
2. Only pass section summaries (200 chars), not full content
3. Exclude synthesis phase results

```python
def _build_synthesis_task(
    self,
    requirement: Dict[str, Any],
    previous_results: List[Dict[str, Any]],
    target_aspect: Optional[str] = None,  # New parameter
    **kwargs
) -> Dict[str, Any]:
    # ...
    
    # Contamination fix: exclude SYNTHESIS phase results
    is_analysis = (
        "deep_analysis" in agent_id or 
        ("analysis" in agent_id and "data_collection" not in agent_id 
         and "research" not in agent_id and "synthesis" not in agent_id)  # New
    )
    
    # Contamination fix: only pass section summary, not full content
    content_summary = content[:200] + "..." if len(content) > 200 else content
    
    # Contamination fix: if target_aspect specified, add to task
    if target_aspect:
        task["target_aspect"] = target_aspect
```

### Modification 3: New `_extract_aspect_from_agent_id` (engine.py lines 727-770)

Extract target section name from agent_id:
- `synthesis_executive_summary_1` -> "Executive Summary"
- `synthesis_research_conclusions_2` -> "Research Conclusions"
- `synthesis_summary_1` -> "Executive Summary"
- `synthesis_conclusion_2` -> "Research Conclusions"

## Fixed Flow

```
Fixed flow:

Analysis Agent 1 (Market Overview) ──┐
Analysis Agent 2 (Competitive Landscape) ──┼──► Body Summary (200 chars each)
Analysis Agent 3 (Development Trends) ──┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     Executive Summary Agent             Research Conclusions Agent
     task.target_aspect="Executive Summary"      task.target_aspect="Research Conclusions"
     Only sees body summary                    Only sees body summary
              │                               │
              ▼                               ▼
         Executive Summary Content       Research Conclusions Content
         (Independent)                   (Independent)
```

## Key Improvements

1. **Independent Task**: Each synthesis agent receives an independent task without interference
2. **Content Limit**: Only pass body summaries (200 chars per chapter), not full content
3. **Clear Goal**: Task contains `target_aspect`, clearly indicating what the agent should generate
4. **Phase Isolation**: Exclude synthesis phase results to avoid circular dependencies

## Modified Files

- `src/core/orchestrator/execution/engine.py`
  - `_execute_stage()` method: lines 618-725
  - `_build_synthesis_task()` method: lines 726-810
  - `_extract_aspect_from_agent_id()` method: new

## Test Verification

```
✓ _extract_aspect_from_agent_id test passed
✓ Import test passed
```

## Expected Effects

- Executive Summary section only contains executive summary content
- Research Conclusions section only contains research conclusion content
- No cross-section content contamination
