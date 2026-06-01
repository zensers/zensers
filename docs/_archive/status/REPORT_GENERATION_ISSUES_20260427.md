# Report Generation Systemic Issue Analysis Report

## Problem Overview

User reported the following issues with report generation:

1. **Chapter numbering chaos** - No systematic design, cannot correctly divide chapters, sub-headers, content
2. **"Original Insight" should not appear** - Report should be completely original, should not contain analytical vocabulary like "Original Insight"
3. **Incorrect data source for Executive Summary** - Should be based on chapter content, not raw data
4. **Empty table of contents page** - Placeholder instead of real TOC
5. **Separator line "------" should not appear** - Affects report professionalism

---

## Root Cause Analysis

### Issue 1: Source of "Original Insight"

**Root Cause**: From LLM prompt response, not hard-coded in code

**Location**:
- `src/core/decomposition/strategies.py` Line 489: prompt asks to "extract core insights"
- LLM adds "Original Insight:" as label when generating content

**Fix Plan**:
- Add patterns to cleanup logic in `document_generation_agent.py`:
  ```python
  r'^Original Insight[：:]\s*',  # Delete "Original Insight:" prefix
  r'^Original Insight\s*',       # Delete "Original Insight" prefix
  ```

---

### Issue 2: Executive Summary Data Source

**Root Cause**: Executive summary generation logic based on `previous_results` (raw data), not chapter content

**Location**: `src/core/orchestrator/execution/engine.py` Lines 692-705

**Fix Plan**:
- Modify `_build_synthesis_prompt`, explicitly require:
  ```python
  Writing Requirements: Based on the analysis conclusions of each chapter (not raw data)
  Notes:
  - Do not mention data sources (e.g., "based on multi-source data", "China Government Website")
  - Present analysis conclusions and judgments directly
  ```

---

### Issue 3: Empty Table of Contents Page

**Root Cause**: TOC is a placeholder, not a real generated table of contents

**Location**: `src/core/orchestrator/output/document_generator.py` Lines 378-383

**Fix Plan**:
- Implement real TOC generation in `document_generator.py`
- Keep chapter numbering in `content_orchestrator.py`

---

### Issue 4: Chapter Numbering Chaos

**Root Cause**: No unified chapter numbering system

**Fix Plan**:
- Define numbering rules in template
- Unified numbering generation in `content_orchestrator.py`
- Remove regex numbering deletion logic

---

### Issue 5: Separator Line "------"

**Root Cause**: Markdown separator lines in LLM response

**Location**: `src/agents/fixed_agents/document_generation_agent.py` Line 757

**Fix Plan**:
- Expand cleanup logic to match 3+ dashes, asterisks, underscores
