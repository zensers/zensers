# Plan A Final Implementation: Independent Task + Full Body + Prompt Constraints

## Core Principle

**Pass full body, but constrain LLM to only output target section**

```
Analysis Agent 1 (Market Overview) ──┐
Analysis Agent 2 (Competitive Landscape) ──┼──► Full Body Content
Analysis Agent 3 (Development Trends) ──┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     Executive Summary Agent             Research Conclusions Agent
     task.target_aspect="Executive Summary"      task.target_aspect="Research Conclusions"
     Receives full body                       Receives full body
     Prompt constraint: only output summary    Prompt constraint: only output conclusions
              │                               │
              ▼                               ▼
         Executive Summary Content       Research Conclusions Content
```

## Modified Files

### 1. engine.py - `_execute_stage()`

**Change**: Each agent in the synthesis phase receives an independent task

```python
is_synthesis_stage = stage_name == "synthesis"

if is_synthesis_stage and len(agents) > 1:
    for agent in agents:
        agent_aspect = self._extract_aspect_from_agent_id(agent.agent_id)
        agent_task = task_builder(
            requirement=...,
            previous_results=...,
            target_aspect=agent_aspect,  # Pass target section
        )
        # Distribute independent task
```

### 2. engine.py - `_build_synthesis_task()`

**Changes**:
1. Support `target_aspect` parameter
2. Pass full content (no truncation)
3. Exclude synthesis phase results

```python
def _build_synthesis_task(
    self,
    requirement: Dict[str, Any],
    previous_results: List[Dict[str, Any]],
    target_aspect: Optional[str] = None,  # New
    **kwargs
) -> Dict[str, Any]:
    # ...
    
    # Exclude synthesis phase results
    is_analysis = (
        "deep_analysis" in agent_id or 
        ("analysis" in agent_id and "synthesis" not in agent_id)  # New
    )
    
    # Pass full content
    section = {
        "id": agent_id,
        "title": section_name,
        "content": content,  # Full content
    }
    
    # Add target section to task
    if target_aspect:
        task["target_aspect"] = target_aspect
```

### 3. engine.py - `_extract_aspect_from_agent_id()`

**New**: Extract target section name from agent_id

```python
def _extract_aspect_from_agent_id(self, agent_id: str) -> str:
    # synthesis_executive_summary_1 -> "Executive Summary"
    # synthesis_research_conclusions_2 -> "Research Conclusions"
    # synthesis_summary_1 -> "Executive Summary"
    # synthesis_conclusion_2 -> "Research Conclusions"
```

### 4. generic_agent.py - `execute()`

**Change**: Get `target_aspect` from task and pass it

```python
target_aspect = task.get("target_aspect", "")

prompt = self._build_synthesis_prompt_with_data(
    topic=topic,
    aspect=aspect,
    aspects=aspects,
    data_points=aggregated_data_points,
    sources=aggregated_sources,
    previous_content=aggregated_content,
    target_aspect=target_aspect,  # New
)
```

### 5. generic_agent.py - `_build_synthesis_prompt_with_data()`

**Change**: Add `target_aspect` parameter, constrain prompt

```python
def _build_synthesis_prompt_with_data(
    self,
    topic: str,
    aspect: str,
    aspects: List[str],
    data_points: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
    previous_content: List[Dict[str, Any]],
    target_aspect: str = "",  # New
) -> str:
    # ...
    
    if target_aspect:
        constraint_text = f"""
**Important Constraint**:
1. You are writing the [{target_aspect}] section, only output the content for this section
2. The "previous analysis results" above are reference materials for you to understand the research content
3. Do not directly copy reference material content into your output
4. Do not output content from other sections (such as Market Overview, Research Conclusions)
5. Output word count should be controlled at 500-800 words

Please write the [{target_aspect}] section content, directly output the body text, using Markdown format."""
```

## Key Improvements

1. **Independent Task**: Each synthesis agent receives an independent task without interference
2. **Full Body**: Pass full content, giving the LLM enough information to generate high-quality summaries/conclusions
3. **Prompt Constraints**: Clearly tell the LLM to only output the target section, not to copy reference material
4. **Phase Isolation**: Exclude synthesis phase results to avoid circular dependencies

## Test Verification

```
✓ _extract_aspect_from_agent_id test passed
✓ Import test passed
```

## Expected Effects

- Executive Summary Agent receives full body but only outputs executive summary
- Research Conclusions Agent receives full body but only outputs research conclusions
- No cross-section content contamination
