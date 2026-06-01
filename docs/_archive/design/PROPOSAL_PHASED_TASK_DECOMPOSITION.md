# Report Analysis System Phased Task Decomposition Plan

**Version**: v2.0  
**Date**: 2025-01-XX  
**Status**: Pending Review  
**Author**: Sisyphus AI Agent

---

## Table of Contents

1. [Background and Problem Analysis](#1-background-and-problem-analysis)
2. [Current Status Assessment](#2-current-status-assessment)
3. [Design Plan](#3-design-plan)
4. [Core Component Design](#4-core-component-design)
5. [Data Flow Design](#5-data-flow-design)
6. [Error Handling Design](#6-error-handling-design)
7. [Implementation Plan](#7-implementation-plan)
8. [Risk Assessment](#8-risk-assessment)
9. [Acceptance Criteria](#9-acceptance-criteria)

---

## 1. Background and Problem Analysis

### 1.1 Business Background

The report analysis system needs to generate professional-grade market research reports. Current core challenges:

- **Insufficient Executive Summary Depth**: Only extracts first two sentences, lacks SCR framework
- **Missing Analysis Frameworks**: No TAM/SAM/SOM, Porter's Five Forces, etc.
- **Coarse Task Decomposition**: All Agents execute at the same level, no phase orchestration
- **Messy Data Flow**: No Schema constraints for inter-phase data transfer

### 1.2 Problem Diagnosis

| Issue | Root Cause | Impact |
|------|------|------|
| Insufficient Analysis Depth | Agent prompts lack professional methodology guidance | Low report professionalism |
| Coarse Task Decomposition | ExecutionEngine phase orchestration incomplete | Low execution efficiency |
| Messy Data Flow | SharedMemory Schema undefined | Uncontrollable data quality |
| Missing Error Recovery | No phase rollback mechanism | Failure leads to termination |

---

## 2. Current Status Assessment

### 2.1 Current Architecture

```
User Input
  │
  ▼
Orchestrator.research()
  │
  ├─ 1. Parse Requirements
  │   └─ SmartClarifier (w/o type awareness)
  │
  ├─ 2. Intent Analysis
  │   └─ IntelligentRoutingAdapter
  │
  ├─ 3. Task Decomposition
  │   └─ IndustryResearchStrategy.decompose() → 5 phases
  │
  ├─ 4. Create Agents
  │   └─ AgentFactory
  │
  ├─ 5. Execute
  │   └─ ExecutionEngine.execute_with_scheduler()
  │       └─ Topological Sort → Batch Execution
  │
  ├─ 6. Aggregate
  │   └─ ResultAggregator
  │
  └─ 7. Generate Document
      └─ DocumentGenerationAgent
```

### 2.2 Issues Found

| No. | Issue | Severity | Location |
|-----|-------|----------|----------|
| 1 | Phase number mismatch: 5 designed vs 3 actual | High | execution/engine.py |
| 2 | Role×Phase orthogonality not utilized | High | decomposition/strategies.py |
| 3 | Prompt phase awareness lacking | High | agents/generic_agent.py |
| 4 | Inter-phase data not validated | Medium | execution/engine.py |
| 5 | No error recovery mechanism | Medium | execution/engine.py |
| 6 | Quality checker not activated | Low | quality/checker.py |

---

## 3. Design Plan

### 3.1 Design Goals

1. **Phased Specialization**: Each phase executes dedicated tasks
2. **Data Validation Phase**: Independent data quality check
3. **Phase Awareness**: Each phase has its own prompt template
4. **Error Recovery**: Each phase can retry on failure
5. **Quality Gates**: Quality check between phases

### 3.2 Five Phases

| Phase | Code | Description | Agent Type |
|-------|------|-------------|------------|
| 1 | DATA_COLLECTION | Collect raw data (search) | Research Agent |
| 2 | DATA_VALIDATION | Cross-validate data quality | Quality Agent |
| 3 | DEEP_ANALYSIS | Professional framework analysis | Analysis Agent |
| 4 | SYNTHESIS | Cross-section integration | Synthesis Agent |
| 5 | REPORT_GENERATION | Output final report | Report Agent |

### 3.3 Core Changes

```python
# 1. Add phases to ExecutionStage
class ExecutionStage(Enum):
    DATA_COLLECTION = "data_collection"
    DATA_VALIDATION = "data_validation"
    DEEP_ANALYSIS = "deep_analysis"
    SYNTHESIS = "synthesis"
    REPORT_GENERATION = "report_generation"

# 2. Phase-aware Agent classification
def classify_agent(self, spec: AgentSpec) -> ExecutionStage:
    category = spec.category or ""
    if category in ("data_collection", "research"):
        return ExecutionStage.DATA_COLLECTION
    if category in ("quality-check", "validation"):
        return ExecutionStage.DATA_VALIDATION
    if category in ("analysis", "market-analysis", "financial"):
        return ExecutionStage.DEEP_ANALYSIS
    if category in ("synthesis", "summary"):
        return ExecutionStage.SYNTHESIS
    return ExecutionStage.REPORT_GENERATION

# 3. Phase-specific prompt selection
def select_phase_prompt(agent_category: str) -> str:
    prompts = {
        "data_collection": "tasks/data_collection.md",
        "quality-check": "tasks/data_validation.md",
        "analysis": "tasks/deep_analysis.md",
        "synthesis": "tasks/synthesis.md",
        "report_generation": "tasks/report_generation.md",
    }
    return prompts.get(agent_category, "tasks/basic_research.md")
```

---

## 4. Core Component Design

### 4.1 Phase-Controlled Agent

```python
class PhaseControlledAgent(GenericAgent):
    """Agent with phase awareness"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.phase = config.get("phase", ExecutionStage.DATA_COLLECTION)

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("action", "")

        if action == "execute":
            if self.phase == ExecutionStage.DATA_COLLECTION:
                return await self._execute_collection(task)
            elif self.phase == ExecutionStage.DATA_VALIDATION:
                return await self._execute_validation(task)
            elif self.phase == ExecutionStage.DEEP_ANALYSIS:
                return await self._execute_analysis(task)
            elif self.phase == ExecutionStage.SYNTHESIS:
                return await self._execute_synthesis(task)
            else:
                return await self._execute_report(task)

        return await super().execute(task)

    async def _execute_collection(self, task: Dict[str, Any]) -> Dict:
        """Data collection phase: search only, no analysis"""
        search_results = await self._do_deep_research(
            topic=task.get("topic", ""),
            aspect=task.get("aspect", ""),
            aspects=task.get("aspects", []),
            skill_registry=self._skill_registry,
        )
        return {"success": True, "data_points": search_results.get("data_points", [])}

    async def _execute_analysis(self, task: Dict[str, Any]) -> Dict:
        """Analysis phase: use validated data for analysis, no search"""
        validated_data = task.get("validated_data", [])
        prompt = self._build_analysis_prompt(
            topic=task.get("topic", ""),
            aspect=task.get("aspect", ""),
            data=validated_data,
        )
        result = await self._call_llm(prompt)
        return {"success": True, "content": result}
```

### 4.2 Quality Gate

```python
class PhaseQualityGate:
    """Quality check between phases"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.checkers = {
            ExecutionStage.DATA_COLLECTION: self._check_data_collection,
            ExecutionStage.DATA_VALIDATION: self._check_data_validation,
            ExecutionStage.DEEP_ANALYSIS: self._check_analysis,
            ExecutionStage.SYNTHESIS: self._check_synthesis,
        }

    async def check(self, stage: ExecutionStage, result: Dict) -> bool:
        checker = self.checkers.get(stage)
        if not checker:
            return True
        return await checker(result)

    async def _check_data_collection(self, result: Dict) -> bool:
        data_points = result.get("data_points", [])
        return len(data_points) >= self.config.get("min_data_points", 5)

    async def _check_data_validation(self, result: Dict) -> bool:
        validation = result.get("validation", {})
        pass_rate = validation.get("pass_rate", 0)
        return pass_rate >= self.config.get("min_validation_rate", 0.7)

    async def _check_analysis(self, result: Dict) -> bool:
        content = result.get("content", "")
        return len(content) >= self.config.get("min_analysis_length", 500)
```

---

## 5. Data Flow Design

### 5.1 Phase Data Transfer

```
Phase 1: DATA_COLLECTION
  Output: {"data_points": [...], "sources": [...]}
    │
    ▼ Quality Gate
    │
Phase 2: DATA_VALIDATION
  Input:  {"data_points": [...], "sources": [...]}
  Output: {"validated_data": [...], "quality_report": {...}}
    │
    ▼ Quality Gate
    │
Phase 3: DEEP_ANALYSIS
  Input:  {"validated_data": [...], "quality_report": {...}}
  Output: {"analysis_content": "...", "key_findings": [...]}
    │
    ▼ Quality Gate
    │
Phase 4: SYNTHESIS
  Input:  {"analyses": [...], "key_findings": [...]}
  Output: {"synthesis_content": "...", "conclusions": [...]}
    │
    ▼ Quality Gate
    │
Phase 5: REPORT_GENERATION
  Input:  {"synthesis": {...}, "conclusions": [...]}
  Output: {"report": "...", "format": "docx"}
```

---

## 6. Error Handling Design

### 6.1 Phase Retry Logic

```python
async def execute_phase_with_retry(
    self,
    phase: ExecutionStage,
    agents: List[Agent],
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Execute phase with retry logic"""
    for attempt in range(max_retries):
        try:
            result = await self._execute_phase_batch(phase, agents)
            quality_ok = await self._quality_gate.check(phase, result)

            if quality_ok:
                return result

            logger.warning(
                f"Phase {phase.value} quality check failed "
                f"(attempt {attempt + 1}/{max_retries})"
            )

            if attempt < max_retries - 1:
                await self._supplement_data(phase, result)

        except Exception as e:
            logger.error(f"Phase {phase.value} execution failed: {e}")
            if attempt == max_retries - 1:
                raise

    return result
```

### 6.2 Phase Fallback

```python
async def _execute_phase_with_fallback(
    self,
    phase: ExecutionStage,
    primary_result: Dict,
) -> Dict[str, Any]:
    """Execute phase with fallback to previous phase data"""
    quality_ok = await self._quality_gate.check(phase, primary_result)

    if quality_ok:
        return primary_result

    logger.warning(f"Phase {phase.value} quality not met, trying fallback")
    fallback_data = await self._load_previous_phase_output(phase)

    if fallback_data:
        result = await self._retry_with_fallback_data(phase, fallback_data)
        return result

    return primary_result
```

---

## 7. Implementation Plan

### Phase 1: Core Infrastructure

| Task | File | Effort |
|------|------|--------|
| Add ExecutionStage enum values | execution/engine.py | 0.5h |
| Implement PhaseControlledAgent | agents/generic_agent.py | 3h |
| Create PhaseQualityGate | quality/phase_quality.py | 2h |

### Phase 2: Phase Prompt Separation

| Task | File | Effort |
|------|------|--------|
| Create data_collection.md prompts | prompts/tasks/ | 1h |
| Create data_validation.md prompts | prompts/tasks/ | 1h |
| Create deep_analysis.md prompts | prompts/tasks/ | 1h |
| Modify GenericAgent.execute() | agents/generic_agent.py | 2h |

### Phase 3: Error Recovery

| Task | File | Effort |
|------|------|--------|
| Add phase retry logic | execution/engine.py | 1h |
| Add fallback mechanism | execution/engine.py | 1h |
| Unit and integration tests | tests/ | 3h |

---

## 8. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-----------|--------|------------|
| Phase overhead reduces throughput | High | Medium | Configurable phase switch |
| Quality gate too strict | Medium | Medium | Configurable thresholds |
| Agent refactoring introduces bugs | Medium | High | Keep backward-compatible interface |
| Phase prompts inconsistent with code | Low | Medium | Automated comparison tests |

---

## 9. Acceptance Criteria

- [ ] 5-phase execution pipeline working
- [ ] Phase-specific prompts loaded correctly
- [ ] Quality gates functional between phases
- [ ] Phase retry mechanism operational
- [ ] Data validation phase independently identifiable
- [ ] All existing tests pass
- [ ] No performance regression
