# Report Content Pollution Fix Plan

## Four Breaking Points Root Cause Analysis

### Breaking Point 1: result_aggregator flat merging
**Problem**: `content_map` flattens all Agent outputs into a single Dict, causing source confusion.

```
Agent A (synthesis) outputs "Executive Summary" -> content_map["Executive Summary"] = "..."
Agent B (analysis)  outputs "Market Overview"  -> content_map["Market Overview"] = "..."
Agent C (synthesis) outputs "Research Conclusions" -> content_map["Research Conclusions"] = "..."
```

Then the section matching logic fishes for content from this flat Dict using string matching, guessing wrong causes contamination.

### Breaking Point 2: Incorrect HTML structure
**Evidence**: HTML only has 2 sections, should have at least 4:
- `section_1` contains "Executive Summary + Market Overview + Research Conclusions" all mixed together
- `section_2` repeats Market Overview again

### Breaking Point 3: Quality check not executed
**Problem**: QualityCheckAgent was initialized but didn't check:
- Prompt contamination (e.g., "OK, according to the task requirements you provided...")
- Content duplication
- Section titles mixed into body text

### Breaking Point 4: HTML -> Word has no confirmation step
**Problem**: DocumentGenerator saves HTML and immediately converts to Word, with no confirmation step.

## Fix Implementation (Completed)

### Fix 1: Layered Storage (Breaking Point 1)
**File**: `src/core/orchestrator/aggregation/result_aggregator.py`

**Changes**:
1. Added `ContentProvenance` data class, recording content source information
2. Added `layered_content` and `content_provenance` fields in `AggregationResult`
3. In `aggregate()` method, extract stage information by agent_id, store content in layers

**Key Code**:
```python
@dataclass
class ContentProvenance:
    source_key: str
    stage: str = "unknown"  # synthesis, analysis, data_collection
    agent_type: str = ""
    section_target: str = ""

def _extract_stage_from_agent_id(self, agent_id: str) -> str:
    """Extract stage information from agent_id"""
    agent_id_lower = agent_id.lower()
    if "synthesis" in agent_id_lower or "summary" in agent_id_lower:
        return "synthesis"
    elif "analysis" in agent_id_lower or "market" in agent_id_lower:
        return "analysis"
    ...
```

### Fix 2: Source Tracking Matching (Breaking Point 2)
**File**: `src/core/orchestrator/aggregation/result_aggregator.py`

**Changes**:
1. In `_convert_to_sections()`, prioritize using source tracking for matching
2. Determine which stage content should come from based on section type
3. Synthesis stage content can only be assigned to summary/conclusion sections
4. Analysis stage content can only be assigned to market_*/competition etc. sections

**Key Code**:
```python
# Determine which stage content should come from based on section type
target_stages = []
if section_id in ["summary", "executive_summary"]:
    target_stages = ["synthesis"]
elif section_id in ["conclusion", "recommendations"]:
    target_stages = ["synthesis"]
elif section_id in ["market_size", "competition", ...]:
    target_stages = ["analysis", "data_collection"]
```

### Fix 3: Contamination Detection (Breaking Point 3)
**File**: `src/core/quality/checkers.py`

**Changes**:
1. Added `_check_content_pollution()` method
2. Detect LLM prompt contamination (e.g., "OK, according to what you provided...")
3. Detect section titles mixed into body text
4. Detect cross-section content duplication
5. Added contamination detection weight in `calculate_score()`

**Key Code**:
```python
def _check_content_pollution(self, report_data: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Check content pollution"""
    llm_pollution_patterns = [
        r'^OK,\s*according to (your|the)',
        r'^OK,\s*following your instructions',
        r'^Based on (your|the).*requirements',
        ...
    ]
    # Detect LLM prompt contamination
    # Detect section titles mixed into body text
    # Detect cross-section content duplication
```

### Fix 4: Preview Confirmation Flow (Breaking Point 4)
**File**: `src/core/orchestrator/orchestrator.py`

**Changes**:
1. Removed the logic of directly generating Word in non-interactive mode
2. Added `generate_final_document()` method, called after user confirmation
3. After HTML preview is generated, wait for user confirmation

**Key Code**:
```python
# Breaking Point 4 fix: no longer directly generate Word, return preview path, wait for user confirmation
if not final_document_generated and output_format in ("docx", "pptx", "pdf"):
    logger.info(f"[{task_id}] HTML preview generated: {preview_path}")
    logger.info(f"[{task_id}] User can generate final {output_format} document after confirmation")

async def generate_final_document(self, task_id: str, output_format: str = "docx", ...):
    """Generate final document after user confirmation"""
    ...
```

### Previously Completed Fixes

1. **Enhanced `PromptPatternFilter`** - Added LLM reply prefix patterns
   - File: `src/core/orchestrator/aggregation/content_quality.py`
   - Added patterns like "OK, according to what you provided..."

## Test Verification

### Test 1: Layered Storage
```
Test 1 - ContentProvenance: test_agent -> summary
Test 2 - Layered content stages: ['synthesis', 'analysis', 'data_collection', 'unknown']
Test 2 - Provenance count: 2
All tests passed!
```

### Test 2: Contamination Detection
```
Test 1 - Clean content: score=100.0, issues=[]
Test 2 - LLM pollution: score=80.0, issues=["Section 'summary' contains LLM prompt contamination"]
Pollution detection tests passed!
```

## Modified File List

| File | Change | Line Change |
|------|--------|-------------|
| `result_aggregator.py` | Layered storage + source tracking | +136 lines |
| `checkers.py` | Contamination detection | +85 lines |
| `orchestrator.py` | Preview confirmation flow | +55 lines |
| `content_quality.py` | Prompt filter enhancement | Completed |

## Next Steps

1. Run complete test suite to verify
2. Generate test report to verify fix effectiveness
3. Update user documentation explaining the new confirmation flow
