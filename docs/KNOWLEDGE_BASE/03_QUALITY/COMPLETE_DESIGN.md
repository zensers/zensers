# Research Report System Quality Control and Intelligent Routing Complete Design

> Version: v5.0 | Date: 2026-04-23 | Status: Verified Design (with Code Analysis)

---

## I. Core Problem Diagnosis

### 1.1 Issue Checklist

| Problem | Description | Existing Code Location | Solution |
|---------|-------------|----------------------|----------|
| Missing Intelligent Routing | Keyword matching cannot understand semantics | `src/core/intent_gate.py` | LLM intent analysis |
| Quality Module Not Integrated | QualityCheckAgent exists but not called by ExecutionEngine | `quality_check_agent.py:89-171` | Integrate into execution flow |
| No Quality Control in Analysis Phase | ExecutionEngine only has data/analysis/report three phases | `engine.py:89-94` | Add analysis quality check |
| Skill Output Not Standardizable | Diverse formats uncontrollable | N/A | Extract rather than convert |
| Quality Gate Not Integrated | Execution phase missing threshold judgment | `engine.py:346-499` | Three-phase gating + feedback loop |

### 1.2 Existing Implementation Analysis

**Implemented Quality Components:**

| Component | File Path | Lines | Function |
|-----------|----------|-------|----------|
| QualityCheckAgent | `src/agents/fixed_agents/quality_check_agent.py` | 618 | 4-dimension check + scoring + Phase 8 auto fix |
| ConfidenceGrader | `src/core/harness/quality.py` | 270 | Confidence grading |
| QualityGate | `src/core/harness/quality.py` | Same | Quality gate |
| SearchQualityFilter | `src/core/search_quality_filter.py` | - | Search result quality filter |
| RevisionService | `src/core/adjustment/revision_service.py` | 603 | Revision service (Phase 8) |
| RevisionHandler | `src/core/adjustment/revision_handler.py` | 593 | 4 revision types handling |
| LayoutDesignAgent | `src/agents/fixed_agents/layout_design_agent.py` | 383 | Word/PPT/HTML layout |

**Key Finding: Quality Check Not Called!**

```
ExecutionEngine.execute() flow:
├── classify_agents() → classify as data/analysis/synthesis/report
├── _execute_stage(DATA_COLLECTION) → data collection
├── _execute_stage(ANALYSIS) → analysis
├── _execute_stage("synthesis") → synthesis
├── _execute_stage(REPORT_GENERATION) → report generation
└── validator.validate_batch() → validate results
    ❌ Missing: quality check phase
    ❌ Missing: threshold judgment
    ❌ Missing: feedback loop
```
