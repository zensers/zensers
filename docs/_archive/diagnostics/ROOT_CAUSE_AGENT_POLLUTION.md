# Agent Output Pollution Root Cause Analysis

## Pollution Root Cause

**File**: `src/core/agents/generic_agent.py`
**Method**: `_build_synthesis_prompt_with_data()` (lines 2034-2123)

### Problem Code

```python
# Lines 2082-2089
if previous_content:
    analysis_context.append("## Previous Analysis Results\n")
    for i, pc in enumerate(previous_content[:10], 1):
        agent_id = pc.get("agent_id", "Unknown Agent")
        content = pc.get("content", "")[:500]  # 500 chars per section
        
        analysis_context.append(f"### {agent_id}")
        analysis_context.append(content)  # ← Puts ALL section content into the prompt!
```

### Data Flow

```
Analysis Agent Output:
├── Market Overview Section (2500 chars)
└── Research Conclusion Section (2600 chars)
    ↓
Engine._build_synthesis_task():
├── sections = [Market Overview, Research Conclusion]
└── Passed as previous_content
    ↓
GenericAgent._build_synthesis_prompt_with_data():
├── Prompt = "Previous Analysis Results:\n" +
│   "### Market Overview\n" + Market Overview Content[:500] +
│   "### Research Conclusion\n" + Research Conclusion Content[:500]
└── Total 1000+ chars of previous content
    ↓
LLM Generates Executive Summary:
├── Sees full "Market Overview" and "Research Conclusion" content
├── Includes these contents during generation
└── Output = Executive Summary + Market Overview + Research Conclusion
    ↓
Result: Executive Summary section contains ALL section content!
```

### Problem Essence

**This is a Prompt design issue, not a code bug**:
1. Prompt gives all section content to the LLM (500 chars each, up to 10)
2. LLM cannot distinguish between "reference material" and "content to output"
3. LLM tends to output the reference content it sees

### Fix Plan

#### Plan A: Limit Previous Content Length (Recommended)

```python
# Modify line 2085
# Old code: content = pc.get("content", "")[:500]
# New code: Only pass key point summaries, not full content

# Plan A1: Only take first 100 chars as summary
content = pc.get("content", "")[:100] + "..."

# Plan A2: Extract key findings (if key_findings available)
key_findings = pc.get("key_findings", [])
if key_findings:
    content = "Key Findings:\n" + "\n".join(f"- {f}" for f in key_findings[:5])
else:
    content = pc.get("content", "")[:100] + "..."
```

#### Plan B: Explicitly Instruct LLM to Only Output Current Section

```python
# Modify line 2123 prompt ending
# Old code:
# Based on the above data and previous analysis, write comprehensive analysis for {aspect_str}. Requirements: integrate findings, original insights, professional conclusions. Output the analysis body directly using Markdown format.

# New code:
return f"""# Comprehensive Analysis Task

## Topic
{topic}

## Current Section
**You are writing the [{aspect_str}] section**

{data_str}
{analysis_str}

---

**Important Constraints**:
1. Only output content for the [{aspect_str}] section
2. Do not repeat content from other sections (such as Market Overview, Research Conclusion)
3. Synthesize based on **key points** from previous analysis, do not directly copy previous content
4. Output控制在 500-800 chars

Please write the [{aspect_str}] section content, output the body directly using Markdown format."""
```

#### Plan C: Post-processing Filter (Already Implemented)

Add section boundary filter in `ContentCleaningPipeline`:
- Detect Markdown headers (## Market Overview, ## Research Conclusion, etc.)
- Truncate before the first other section header

### Recommended Fix Order

1. **Immediate Fix**: Plan B (modify prompt, clear instruction)
2. **Follow-up Optimization**: Plan A (limit previous content length)
3. **Defensive Measure**: Plan C (post-processing filter, planned)

## Modified Files

- `src/core/agents/generic_agent.py` lines 2110-2123

## Test Verification

After modification, regenerate the report and check:
1. Whether the Executive Summary section only contains executive summary content
2. Whether section content still has duplication
