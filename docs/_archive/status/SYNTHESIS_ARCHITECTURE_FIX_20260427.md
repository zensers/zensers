# Synthesis Chapter Architecture Design Issue Analysis and Fix Plan

## Problem Overview

**Core Problem**: Comprehensive chapters such as "Executive Summary," "Core Insights," "Research Summary," "Research Conclusion"
- **Problem 1**: Incorrect data source - based on raw data rather than chapter content
- **Problem 2**: Correct execution order but incorrect data transmission

---

## Architecture Design Deep Analysis

### Current Architecture Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                       Current Execution Flow (Problematic)         │
└─────────────────────────────────────────────────────────────────┘

Phase 1: DATA_COLLECTION
  └─ Agent: research_MarketSize_1
  └─ Agent: research_CompetitiveLandscape_2
  └─ Agent: research_PolicyEnvironment_3
  └─ Output: raw_data (raw data points, data source descriptions, etc.)
       │
       ▼
Phase 2: DATA_VALIDATION
  └─ Dependency: All Agents from Phase 1
  └─ Output: validated_data
       │
       ▼
Phase 3: DEEP_ANALYSIS
  └─ Dependency: All Agents from Phase 2
  └─ Input: previous_results (includes raw_data + validated_data)
  └─ Output: analysis_MarketSize, analysis_CompetitiveLandscape, analysis_PolicyEnvironment
       │
       ▼
Phase 4: SYNTHESIS ❌ Problem Area
  └─ Dependency: All Agents from Phase 3
  └─ Input: previous_results (includes raw_data + validated_data + analysis)
  └─ Problem: synthesis agent receives ALL previous_results
            Including raw data points, data source descriptions, etc.
  └─ Output: synthesis_ExecutiveSummary, synthesis_ResearchConclusion
       │
       ▼
Phase 5: REPORT_GENERATION
  └─ Dependency: Phase 3 + Phase 4
  └─ Input: previous_results (results from all phases)
  └─ Output: final_report
```

### Root Cause Analysis

#### Problem 1: Data Transmission in Synthesis Phase

**Code Location**: `src/core/orchestrator/execution/engine.py` Lines 523-533

```python
# 4.5 Comprehensive Analysis (executed after all analyses complete, e.g., executive summary, conclusion)
if synthesis_agents:
    synthesis_results = await self._execute_stage(
        stage_name="synthesis",
        agents=synthesis_agents,
        task_builder=self._build_analysis_task,  # ❌ Used wrong task_builder
        requirement=requirement,
        previous_results=all_results,  # ❌ Contains all previous results (including raw data)
    )
```

**Problem Analysis**:
1. `_build_analysis_task` method (lines 692-705) passes `previous_results` directly to agent
2. `previous_results` includes:
   - Raw data from DATA_COLLECTION phase
   - Validation data from DATA_VALIDATION phase
   - Analysis results from DEEP_ANALYSIS phase
3. Synthesis agent receives **full data**, not **only chapter content**

#### Problem 2: Design Flaw in `_build_analysis_task`

**Code Location**: `src/core/orchestrator/execution/engine.py` Lines 692-705

```python
def _build_analysis_task(
    self,
    requirement: Dict[str, Any],
    previous_results: List[Dict[str, Any]],
    **kwargs
) -> Dict[str, Any]:
    """Build analysis task"""
    return {
        "action": "analysis",
        "topic": requirement.get("topic"),
        "aspects": requirement.get("aspects", []),
        "data": previous_results,  # ❌ Directly passes all previous results
        "output_format": "structured",
    }
```

**Problem**: This method is used by multiple phases but does not distinguish data requirements for different phases

#### Problem 3: Synthesis Agent Input Data Structure

**Should receive**:
```python
{
    "action": "synthesis",
    "topic": "New Energy Vehicle Market Analysis",
    "sections": [
        {
            "id": "section_1",
            "title": "Market Size",
            "content": "China's NEV market sales reached...",
            "key_findings": ["Sales exceeded 10 million units", "40% year-over-year growth"]
        },
        {
            "id": "section_2",
            "title": "Competitive Landscape",
            "content": "Market concentration is high, CR5 reached...",
            "key_findings": ["BYD leads market share", "New players rising rapidly"]
        }
    ],
    "output_format": "structured"
}
```

**Actually receives**:
```python
{
    "action": "analysis",
    "data": [
        # DATA_COLLECTION phase results
        {
            "agent_id": "research_MarketSize_1",
            "success": true,
            "data_points": [...],  # Raw data points
            "sources": ["China Government Website", "CAAM", ...],  # Data sources
            "raw_content": "..."  # Raw content
        },
        # DATA_VALIDATION phase results
        {...},
        # DEEP_ANALYSIS phase results
        {
            "agent_id": "deep_analysis_MarketSize_1",
            "success": true,
            "content": "China's NEV market...",  # Chapter content
            "key_findings": [...]
        },
        ...
    ]
}
```

---

## Correct Architecture Design

### Design Principles

1. **Data Layering Principle**:
   - Raw data layer: DATA_COLLECTION + DATA_VALIDATION
   - Analysis content layer: DEEP_ANALYSIS (chapter content)
   - Synthesis content layer: SYNTHESIS (based on chapter content)

2. **Dependency Transfer Principle**:
   - Synthesis agent only depends on DEEP_ANALYSIS phase results
   - Should not access raw data layer results

3. **Data Cleaning Principle**:
   - Data passed to synthesis should only contain "chapter content"
   - Should not include data source descriptions, raw data points, etc.

### Fixed Architecture Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                       Fixed Execution Flow                         │
└─────────────────────────────────────────────────────────────────┘

Phase 1: DATA_COLLECTION
  └─ Output: raw_data
       │
       ▼
Phase 2: DATA_VALIDATION
  └─ Output: validated_data
       │
       ▼
Phase 3: DEEP_ANALYSIS
  └─ Input: raw_data + validated_data
  └─ Output: sections (chapter content)
       │
       ├──────────────────────────────────────┐
       │                                      │
       ▼                                      ▼
Phase 4: SYNTHESIS ✅ After Fix         Phase 5: REPORT_GENERATION
  └─ Input: only sections (chapter content)  └─ Input: sections + synthesis
  └─ Does not access: raw_data, validated_data  └─ Output: final_report
  └─ Output: synthesis_ExecutiveSummary
```

---

## Systematic Fix Plan

### Fix 1: Add `_build_synthesis_task` Method

**File**: `src/core/orchestrator/execution/engine.py`

**Location**: Add after `_build_analysis_task` method

```python
def _build_synthesis_task(
    self,
    requirement: Dict[str, Any],
    previous_results: List[Dict[str, Any]],
    **kwargs
) -> Dict[str, Any]:
    """
    Build comprehensive analysis task
    
    **Key Fix**: Only pass chapter content, not raw data
    
    Args:
        requirement: Requirement definition
        previous_results: Previous results (only use DEEP_ANALYSIS phase results)
        
    Returns:
        Comprehensive analysis task definition
    """
    # Only extract DEEP_ANALYSIS phase results (chapter content)
    sections = []
    all_key_findings = []
    
    for r in previous_results:
        if not r.get("success"):
            continue
        
        agent_id = r.get("agent_id", "")
        
        # Only process DEEP_ANALYSIS phase results
        # Agent ID format: deep_analysis_1_MarketSize, synthesis_0_ExecutiveSummary
        if "deep_analysis" in agent_id or "analysis" in agent_id:
            content = (
                r.get("content") or 
                r.get("result") or 
                r.get("output") or
                ""
            )
            
            if content and isinstance(content, str):
                # Extract section name from agent_id
                if "_" in agent_id:
                    parts = agent_id.split("_")
                    # Extract section name (last part or middle part)
                    section_name = parts[-1] if len(parts) > 2 else parts[-1]
                else:
                    section_name = agent_id
                
                section = {
                    "id": agent_id,
                    "title": section_name,
                    "content": content,
                }
                
                # Extract key findings
                if r.get("key_findings"):
                    section["key_findings"] = r["key_findings"]
                    all_key_findings.extend(r["key_findings"])
                elif r.get("findings"):
                    section["key_findings"] = r["findings"]
                    all_key_findings.extend(r["findings"])
                
                sections.append(section)
    
    logger.info(f"[Synthesis] Extracted {len(sections)} chapters for comprehensive analysis")
    
    return {
        "action": "synthesis",
        "topic": requirement.get("topic"),
        "sections": sections,  # ✅ Only pass chapter content
        "key_findings": all_key_findings,  # ✅ Pass key findings
        "output_format": "structured",
        
        # Explicit constraints: no raw data
        "constraints": {
            "no_raw_data": True,
            "no_data_sources": True,
            "based_on_chapters_only": True,
        }
    }
```

### Fix 2: Modify Synthesis Phase task_builder

**File**: `src/core/orchestrator/execution/engine.py`

**Location**: Lines 523-533

```python
# Before modification
if synthesis_agents:
    synthesis_results = await self._execute_stage(
        stage_name="synthesis",
        agents=synthesis_agents,
        task_builder=self._build_analysis_task,  # ❌ Wrong
        requirement=requirement,
        previous_results=all_results,
    )

# After modification
if synthesis_agents:
    synthesis_results = await self._execute_stage(
        stage_name="synthesis",
        agents=synthesis_agents,
        task_builder=self._build_synthesis_task,  # ✅ Use correct task_builder
        requirement=requirement,
        previous_results=all_results,
    )
```

### Fix 3: Update `_build_synthesis_prompt` Method

**File**: `src/core/decomposition/strategies.py`

**Location**: Lines 479-512

```python
def _build_synthesis_prompt(self, topic: str, aspect: str) -> str:
    """Build comprehensive integration prompt"""
    is_summary = aspect.lower() in {"summary", "executive_summary"}
    is_conclusion = aspect.lower() in {"conclusion", "research_conclusion"}
    is_insight = "insight" in aspect.lower()
    
    if is_summary:
        return f"""# Executive Summary

## Research Topic
{topic}

## Input Data
You will receive analysis content of each chapter (sections), please generate executive summary based on these chapter contents.

## Writing Requirements
Based on the analysis conclusions of each chapter, extract core insights in 3-5 paragraphs.

Format Requirements:
- Each paragraph starts with a **judgment sentence** (e.g.: "China's NEV market is at a critical stage of transitioning from policy-driven to market-driven")
- Each judgment should be immediately followed by data support
- Do not list data, give the meaning behind the data
- The last paragraph should provide overall judgment and outlook

**Important Constraints**:
- ✅ Must be generated based on chapter content (sections)
- ❌ Do not mention data sources (e.g., "based on multi-source data", "China Government Website")
- ❌ Do not use analysis labels like "original insights"
- ❌ Do not reference raw data points
- ✅ Present analysis conclusions directly, rather than describing the analysis process
- ✅ Content should be completely original, reflecting deep understanding of chapter content
"""
    
    elif is_conclusion:
        return f"""# Research Conclusion

## Research Topic
{topic}

## Input Data
You will receive analysis content of each chapter (sections), please generate research conclusions based on these chapter contents.

## Writing Requirements
Based on the conclusions from preceding analysis, output final judgments.

Format Requirements:
1. **Core Conclusion**: 1-2 sentences, clearly state the most core judgment about this industry/company
2. **Basis for Judgment**: List 3-5 key arguments supporting this judgment (each argument 1-2 sentences)
3. **Risk Warning**: List key risks that could invalidate the judgment
4. **Outlook**: Key observation points for the next 6-12 months

**Important Constraints**:
- ✅ Must be generated based on chapter content (sections)
- ❌ Conclusions should be **judgments** based on analysis, not a restatement of analysis content
- ❌ Do not mention data sources or raw data
- ✅ Demonstrate deep integration and refinement of chapter content
"""
    
    elif is_insight:
        return f"""# Core Insights

## Research Topic
{topic}

## Input Data
You will receive analysis content of each chapter (sections), please extract core insights based on these chapter contents.

## Writing Requirements
Extract 3-5 most valuable insights from each chapter.

Format Requirements:
- Each insight presented as a **judgment sentence**
- Explain the business value or strategic significance of the insight
- Note the chapter source of the insight

**Important Constraints**:
- ✅ Must be generated based on chapter content (sections)
- ❌ Do not use labels like "original insights"
- ❌ Do not mention data sources
- ✅ Insights should be actionable
"""
    
    else:
        # Default comprehensive prompt
        return f"""# Comprehensive Analysis

## Research Topic
{topic}

## Input Data
You will receive analysis content of each chapter (sections), please conduct comprehensive analysis based on these chapter contents.

## Writing Requirements
Based on the analysis content of each chapter, conduct comprehensive assessment.

**Important Constraints**:
- ✅ Must be generated based on chapter content (sections)
- ❌ Do not mention data sources or raw data
- ✅ Demonstrate deep understanding and integration of chapter content
"""
```

### Fix 4: Update DEPENDENT_SECTIONS Definition

**File**: `src/core/decomposition/strategies.py`

**Location**: Line 218

```python
# Before modification
DEPENDENT_SECTIONS = {"summary", "conclusion", "executive_summary", "research_conclusion"}

# After modification (extended definition)
DEPENDENT_SECTIONS = {
    # English
    "summary", "conclusion", "executive_summary", "key_insights", 
    "research_summary", "research_conclusion", "synthesis",
    # Chinese equivalents
    "insights", "key_findings"
}
```

---

## Data Flow Comparison

### Before Fix

```
Data received by synthesis agent:
├─ DATA_COLLECTION results
│  ├─ raw_data (raw data)
│  ├─ data_points (data points)
│  └─ sources (data source descriptions) ← ❌ Should not access
├─ DATA_VALIDATION results
│  └─ validated_data
└─ DEEP_ANALYSIS results
   ├─ content (chapter content) ← ✅ Should access
   └─ key_findings
```

### After Fix

```
Data received by synthesis agent:
└─ DEEP_ANALYSIS results (only this part)
   ├─ sections (chapter content)
   │  ├─ {id, title, content}
   │  └─ key_findings
   └─ all_key_findings (key findings from all chapters)
```

---

## Test Verification

### Test Case 1: Executive Summary Data Source

**Input**:
```python
previous_results = [
    {"agent_id": "research_MarketSize_1", "data_points": [...], "sources": ["China Government Website"]},
    {"agent_id": "deep_analysis_MarketSize_1", "content": "China's NEV market..."},
]
```

**Expected Output**:
```python
synthesis_task = {
    "action": "synthesis",
    "sections": [
        {"id": "deep_analysis_MarketSize_1", "title": "MarketSize", "content": "China's NEV market..."}
    ],
    # Does not include data_points, sources
}
```

### Test Case 2: Executive Summary Content Verification

**Input**: Content generated by synthesis agent

**Expectation**:
- ✅ Contains analysis conclusions from chapter content
- ❌ Does not contain "based on multi-source data"
- ❌ Does not contain "original insights"
- ❌ Does not contain data source names

---

## Fix Checklist

| # | Fix Item | File | Priority | Status |
|---|----------|------|----------|--------|
| 1 | Add `_build_synthesis_task` method | `engine.py` | P0 | Pending |
| 2 | Modify synthesis phase task_builder | `engine.py` | P0 | Pending |
| 3 | Update `_build_synthesis_prompt` method | `strategies.py` | P0 | Pending |
| 4 | Extend DEPENDENT_SECTIONS definition | `strategies.py` | P1 | Pending |
| 5 | Add unit tests | `test_engine.py` | P1 | Pending |
| 6 | Add integration tests | `test_integration.py` | P2 | Pending |

---

## Expected Results

After fix, comprehensive chapters will:

1. **Correct data source**: Based only on chapter content, does not access raw data
2. **Original content**: No phrases like "based on multi-source data", "original insights"
3. **Correct execution order**: Executed after all analysis chapters complete
4. **Correct data transmission**: Only receives necessary chapter content

---

**Document Generation Date**: 2026-04-27
**Analysis Scope**: Comprehensive chapter architecture design
**Problems Found**: 2 core issues
**Fix Plan**: 4 fix items
