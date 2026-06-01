# Final Fix Execution Plan

Based on the deep analysis from three parallel exploration agents, now summarizing all issues and formulating fix plans.

---

## Part 1: Issue Summary (Confirmed)

### P0 - Core Breaking Points (Must Fix Immediately)

| # | Issue | Root Cause | File | Impact |
|---|-------|------------|------|--------|
| 1 | Survey data return incomplete | `_execute_survey_integration` only returns summary, loses raw data | orchestrator.py:1794 | Survey results cannot be integrated into report |
| 2 | Chart generation not integrated | `ChartGenerator` exists but `SurveyAnalysisAgent` does not call it | survey_analysis_agent.py | Report has no charts |
| 3 | Data mapping error | `data_points` not mapped to `section.tables` | content_orchestrator.py:197 | Tables empty during template rendering |
| 4 | Loop rendering bug | Nested loops cannot be correctly matched | template_engine.py:331 | Template tags remain |
| 5 | Hardcoded paths | 6 code locations don't read configuration | Multiple files | Document storage chaos |

### P1 - Important Issues

| # | Issue | Root Cause | File | Impact |
|---|-------|------------|------|--------|
| 6 | Quality check not integrated | `QualityCheckAgent` not called in main flow | orchestrator.py:508 | Quality unguaranteed |
| 7 | AnalysisAgent missing | No dedicated analysis Agent, using GenericAgent proxy | - | Insufficient analysis capability |
| 8 | Statistical metrics missing | Missing standard deviation, confidence intervals, etc. | survey_analysis_agent.py:240 | Unprofessional data |
| 9 | Correlation analysis missing | No correlation analysis methods at all | survey_analysis_agent.py | Cannot discover variable relationships |

---

## Part 2: Fix Plans (In Execution Order)

### Phase 1: Fix Data Flow Breaks (Estimated 2 hours)

#### Fix 1.1: Survey Data Return Completeness

**File**: `src/core/orchestrator/orchestrator.py`
**Location**: Lines 1794-1802

```python
# Current code:
return {
    "status": "completed",
    "survey_id": result.get("survey_id"),
    "mode": survey_mode,
    "responses_count": len(survey_responses),
    "findings": survey_findings,
    "survey_section": survey_section,
    "survey_document": result.get("survey_document"),
}

# After fix:
return {
    "status": "completed",
    "survey_id": result.get("survey_id"),
    "mode": survey_mode,
    "responses_count": len(survey_responses),
    "findings": survey_findings,
    "survey_section": survey_section,
    "survey_document": result.get("survey_document"),
    # New: complete data
    "responses": survey_responses,
    "analysis": result.get("analysis", {}),
    "statistics": self._calculate_survey_statistics(survey_responses),
}
```

#### Fix 1.2: Data Mapping to section.tables

**File**: `src/content/content_orchestrator.py`
**Location**: Lines 197-208

```python
# In _prepare_template_variables method
# Current: each section's tables is empty list
# Fix: map data_points to corresponding section's tables

for i, section_dict in enumerate(sections):
    section_dict["subsections"] = []
    section_dict["tables"] = []
    
    # New: if there are corresponding data_points, add to tables
    if i < len(data_points):
        for dp in data_points:
            if dp.get("section_id") == section_dict.get("id"):
                section_dict["tables"].append({
                    "id": dp.get("id"),
                    "caption": dp.get("metric_name", ""),
                    "data": dp.get("value"),
                })
```

#### Fix 1.3: Loop Rendering Bug

**File**: `src/content/template_engine.py`
**Location**: Lines 331-338

```python
# Current: endfor matching logic error
# Was previously fixed once, need to confirm completeness

# Ensure endfor_pattern correctly matches complete {% endfor %}
endfor_pattern = re.compile(r'\{%\s*(for\s+[\w.]+\s+in\s+[\w.]+|endfor)\s*%\}', re.IGNORECASE)
```

---

### Phase 2: Integrate Chart Generation (Estimated 3 hours)

#### Fix 2.1: Integrate ChartGenerator in SurveyAnalysisAgent

**File**: `src/agents/fixed_agents/survey_analysis_agent.py`

```python
# Add import at file beginning
from src.services.chart_generator import ChartGenerator

# Add chart generation in _generate_markdown_report method
def _generate_markdown_report(self, statistics, cross_analysis, insights):
    """Generate Markdown report"""
    chart_generator = ChartGenerator()
    
    report_lines = ["# Survey Analysis Report\n"]
    
    # Generate statistic charts
    for q_id, q_stats in statistics.items():
        if q_stats.get("type") in ["single", "multiple"]:
            # Generate pie chart
            chart_path = chart_generator.generate_pie_chart(
                data=q_stats.get("distribution", {}),
                title=q_stats.get("question_text", ""),
                output_dir="output/charts"
            )
            if chart_path:
                report_lines.append(f"\n![{q_id}](../{chart_path})\n")
    
    # ... other content
```

#### Fix 2.2: Add Statistical Indicators

**File**: `src/agents/fixed_agents/survey_analysis_agent.py`
**Location**: Lines 240-246

```python
# Add in _calculate_statistics method
import statistics

elif q_type in ["scale", "likert"]:
    numeric_answers = [a for a in answers if isinstance(a, (int, float))]
    if numeric_answers:
        q_stats["mean"] = sum(numeric_answers) / len(numeric_answers)
        q_stats["min"] = min(numeric_answers)
        q_stats["max"] = max(numeric_answers)
        q_stats["median"] = sorted(numeric_answers)[len(numeric_answers) // 2]
        # New
        q_stats["std"] = statistics.stdev(numeric_answers) if len(numeric_answers) > 1 else 0
        q_stats["variance"] = statistics.variance(numeric_answers) if len(numeric_answers) > 1 else 0
        # 95% confidence interval
        import math
        n = len(numeric_answers)
        se = q_stats["std"] / math.sqrt(n) if n > 0 else 0
        q_stats["confidence_interval_95"] = (
            q_stats["mean"] - 1.96 * se,
            q_stats["mean"] + 1.96 * se
        )
```

---

### Phase 3: Integrate Quality Check (Estimated 2 hours)

#### Fix 3.1: Add Quality Check in Main Flow

**File**: `src/core/orchestrator/orchestrator.py`
**Location**: After line 508

```python
# After report generation completes
output_path = doc_result.get("document_path")

# === New: Quality Check ===
logger.info(f"[{task_id}] Executing quality check")

from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent

qc_agent = QualityCheckAgent(agent_id=f"{task_id}_qc")
report_data = aggregated.to_dict()

qc_result = await qc_agent.execute({
    "report": {
        "title": requirement.topic,
        "content": str(report_data.get("data", {})),
        "sections": report_data.get("sections", []),
        "word_count": sum(len(s.get("content", "")) for s in report_data.get("sections", [])),
    },
})

quality_score = qc_result.get("quality_score", 0)
passed = qc_result.get("passed", False)
issues = qc_result.get("issues", [])

logger.info(f"[{task_id}] Quality check: score={quality_score}, passed={passed}")

if not passed and output_path:
    logger.warning(f"[{task_id}] Quality not up to standard, attempting auto-fix")
    fix_result = await qc_agent.execute_and_fix(
        task_input={"report": report_data},
        document_path=output_path,
        max_fix_rounds=3,
        quality_threshold=70.0,
    )
    if fix_result.get("success"):
        output_path = fix_result.get("document_path", output_path)
```

---

### Phase 4: Unify Storage Paths (Estimated 1 hour)

#### Fix 4.1: Read Configuration Paths

**Modified Files**:
- `orchestrator.py:209`
- `storage_manager.py:51`
- `document_generation_agent.py:185`
- `survey_integration_agent.py:814`

```python
# Unified use of configuration
from src.config import settings

# Replace all hardcoded paths
output_dir = Path(settings.system.report_output_dir)  # output/reports
```

---

## Part 3: Execution Checklist

Must verify after fixes are complete:

### Data Flow Verification
- [ ] Survey return includes `responses`, `analysis`, `statistics`
- [ ] `section.tables` contains data
- [ ] Template rendering has no residual tags

### Feature Verification
- [ ] Report contains charts
- [ ] Statistical indicators complete (mean, standard deviation, confidence interval)
- [ ] Quality check log output

### Quality Verification
- [ ] Report layout correct
- [ ] Data professionalism up to standard
- [ ] No CSS/template residuals

### Integration Verification
- [ ] All Agents correctly integrated
- [ ] Data flow without breaks
- [ ] Configuration correctly loaded

---

## Part 4: Execute Now

Now begin executing fixes by phase:

1. **Phase 1**: Fix data flow breaks -> 2 hours
2. **Phase 2**: Integrate chart generation -> 3 hours
3. **Phase 3**: Integrate quality check -> 2 hours
4. **Phase 4**: Unify storage paths -> 1 hour

**Total estimated time**: 8 hours

Shall we start executing immediately?
