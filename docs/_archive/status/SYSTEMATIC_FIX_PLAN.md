# Systematic Issue Fix Plan

## I. Root Cause Analysis

### Why Do Problems Persist After Multiple Fixes?

**Root Cause: Fragmented fixes, lack of systematic design**

| Problem | Previous Fix | Why Not Resolved |
|---------|-------------|------------------|
| Survey data not integrated | May have modified `_build_survey_section` | But didn't fix data transmission chain, data lost during transmission |
| Quality check not running | Implemented `QualityCheckAgent` | But not integrated into execution flow, code exists but doesn't execute |
| Poor report quality | Fixed template engine | But no quality gate, problematic reports still output |

**Core Problem: Only fixed "points," not the "chain"**

---

## II. Systematic Fix Plan

### Fix Principles

1. **Complete Chain Principle**: Every link from data creation to final output must be verified
2. **Defensive Programming Principle**: Every link must handle exceptions and null values
3. **Quality Gate Principle**: Key nodes must have quality checks
4. **Backward Compatibility Principle**: Changes must not break existing functionality

### Complete Chain to Fix

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Research Task Complete Chain                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  [1] User Request                                                          │
│       │                                                                    │
│       ▼                                                                    │
│  [2] Requirement Clarification ──────────────────────────────┐            │
│       │                                                       │            │
│       ▼                                                       │            │
│  [3] Intent Analysis                                          │            │
│       │                                                       │            │
│       ├──────────► [3a] Survey Integration ──────┐            │            │
│       │                                          │            │            │
│       ▼                                          ▼            │            │
│  [4] Create Agents ──────────────► Survey Data ──┐            │            │
│       │                                           │            │            │
│       ▼                                           │            │            │
│  [5] Execute Agents                               │            │            │
│       │                                           │            │            │
│       ▼                                           ▼            │            │
│  [6] Aggregate Results ◄────────────────── Survey Result Integration ──┘  │
│       │                                           ▲                        │
│       ▼                                           │                        │
│  [7] Generate Report                              │                        │
│       │                                           │                        │
│       ▼                                           │                        │
│  [8] Quality Check ──────────────────────────────┘                        │
│       │                                                                   │
│       ├──────────► [8a] Quality Below Standard → Auto Fix → Return to [7]│
│       │                                                                   │
│       ▼                                                                   │
│  [9] Output Report                                                         │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## III. Specific Fix Checklist

### Phase 1: Survey Data Integration Fix (Priority: P0)

#### Fix Point 1: `orchestrator._execute_survey_integration()`

**File**: `src/core/orchestrator/orchestrator.py`
**Location**: Lines 1794-1802

**Current Code**:
```python
return {
    "status": "completed",
    "survey_id": result.get("survey_id"),
    "mode": survey_mode,
    "responses_count": len(survey_responses),
    "findings": survey_findings,
    "survey_section": survey_section,
    "survey_document": result.get("survey_document"),
}
```

**Problem**: Returned data is incomplete, missing `responses` and `analysis`

**After Fix**:
```python
return {
    "status": "completed",
    "survey_id": result.get("survey_id"),
    "mode": survey_mode,
    "responses_count": len(survey_responses),
    "findings": survey_findings,
    "survey_section": survey_section,
    "survey_document": result.get("survey_document"),
    # New: complete data
    "responses": survey_responses,  # Raw response data
    "analysis": result.get("analysis", {}),  # Complete analysis results
    "statistics": self._calculate_survey_statistics(survey_responses),  # Statistics
}
```

#### Fix Point 2: `orchestrator._build_survey_section()`

**File**: `src/core/orchestrator/orchestrator.py`
**Location**: Lines 1817-1847

**Current Code**: Only generates simple text description

**After Fix**: Generate structured data
```python
def _build_survey_section(
    self,
    topic: str,
    mode: str,
    target_count: int,
    collected_count: int,
    analysis: Dict[str, Any],
    responses: List[Dict] = None,  # New parameter
) -> Dict[str, Any]:
    """Build survey results section (for deep integration into report)"""
    mode_label = "AI Simulation Survey" if mode == "ai_simulation" else "Third-Party Platform Survey"
    
    key_findings = analysis.get("key_findings", [])
    findings_text = "\n".join(f"- {f}" for f in key_findings[:5]) if key_findings else "No key findings yet"
    
    # New: generate statistics
    statistics = {}
    if responses:
        statistics = self._calculate_survey_statistics(responses)
    
    # New: generate question statistics
    question_stats = analysis.get("statistics", {}).get("questions", {})
    
    return {
        "id": "survey_results",
        "title": "Survey Data Analysis",
        "content": (
            f"This study collected {collected_count}/{target_count} valid questionnaires through {mode_label} method.\n\n"
            f"**Key Findings:**\n{findings_text}\n\n"
            f"**Methodology Note:** This survey uses {mode_label} method, results are for reference only."
        ),
        "required": False,
        "data_source": "survey",
        # New: structured data
        "statistics": statistics,
        "key_findings": key_findings,
        "question_count": len(question_stats),
        "mode": mode,
    }
```

#### Fix Point 3: Add Statistics Calculation Method

**File**: `src/core/orchestrator/orchestrator.py`
**Location**: Add after `_build_survey_section`

```python
def _calculate_survey_statistics(self, responses: List[Dict]) -> Dict[str, Any]:
    """Calculate survey statistics"""
    if not responses:
        return {}
    
    stats = {
        "total_responses": len(responses),
        "valid_responses": sum(1 for r in responses if r.get("is_valid", 1)),
        "average_quality": sum(r.get("quality_score", 1.0) for r in responses) / len(responses),
    }
    
    return stats
```

#### Fix Point 4: `orchestrator.research()` Survey Data Integration

**File**: `src/core/orchestrator/orchestrator.py`
**Location**: Lines 446-455

**Current Code**:
```python
if survey_result and survey_result.get("status") == "completed":
    results_for_aggregation["survey_result"] = {
        "success": True,
        "title": "Survey Data Analysis",
        "result": survey_result.get("survey_section", {}),
        "responses_count": survey_result.get("responses_count", 0),
        "findings": survey_result.get("findings", {}),
    }
```

**After Fix**:
```python
if survey_result and survey_result.get("status") == "completed":
    survey_section = survey_result.get("survey_section", {})
    
    results_for_aggregation["survey_result"] = {
        "success": True,
        "title": "Survey Data Analysis",
        "result": survey_section,
        "content": survey_section.get("content", ""),
        "responses_count": survey_result.get("responses_count", 0),
        "findings": survey_result.get("findings", {}),
        # New: ensure complete data transfer
        "statistics": survey_section.get("statistics", {}),
        "key_findings": survey_section.get("key_findings", []),
    }
    logger.info(f"[{task_id}] Survey results added to aggregation data: {survey_result.get('responses_count')} responses")
```

#### Fix Point 5: `ResultAggregator._convert_to_sections()`

**File**: `src/core/orchestrator/aggregation/result_aggregator.py`
**Location**: Lines 103-141

**New Special Handling**:
```python
def _convert_to_sections(self) -> List[Dict[str, Any]]:
    """Convert aggregated data to section structure"""
    sections = []
    
    # Special handling: survey results
    if "survey_result" in self.data:
        survey = self.data["survey_result"]
        if isinstance(survey, dict):
            survey_section = survey.get("result", survey.get("content", {}))
            if isinstance(survey_section, dict):
                sections.append({
                    "id": survey_section.get("id", "survey_results"),
                    "title": survey.get("title", "Survey Data Analysis"),
                    "content": survey_section.get("content", ""),
                })
    
    # Handle other Agent results
    if isinstance(self.data, dict):
        for key, value in self.data.items():
            if key == "survey_result":
                continue  # Already handled
            # ... existing code ...
    
    return sections
```

---

## IV. Verification Checklist

### Must Verify After Fix Completion:

- [ ] Whether survey data returns complete (`responses`, `analysis`, `statistics`)
- [ ] Whether survey section appears in report
- [ ] Whether quality check executes after report generation
- [ ] Whether quality check logs are output
- [ ] Whether auto fix triggers when quality is below standard
- [ ] Whether non-interactive mode also has quality check
- [ ] Whether existing functionality is not broken

---

## V. File Modification Summary

| File | Fix Point | Line | Description |
|------|-----------|------|-------------|
| `orchestrator.py` | Fix Point 1 | 1794-1802 | Return complete survey data |
| `orchestrator.py` | Fix Point 2 | 1817-1847 | Generate structured sections |
| `orchestrator.py` | Fix Point 3 | New | Statistics calculation method |
| `orchestrator.py` | Fix Point 4 | 446-455 | Data integration fix |
| `orchestrator.py` | Fix Point 6 | After 508 | Quality check integration |
| `result_aggregator.py` | Fix Point 5 | 103-141 | Survey special handling |
