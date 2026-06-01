# Report Content Pollution Diagnosis Plan

## Problem Symptoms

HTML Output:
- `section_1` contains "Executive Summary + Market Overview + Research Conclusions" all mixed together
- `section_2` repeats market overview again
- Section titles mixed into body text (e.g., "China New Energy Vehicle Market Deep Research Analysis Report", "Executive Summary", "Market Overview" as body content)

## Log Analysis

```
2026-04-29 14:01:13 [INFO] ResultAggregator: Using 3 framework sections
2026-04-29 14:01:13 [INFO] ResultAggregator: Aggregated data keys: ['Market Overview', 'Research Conclusions', 'Executive Summary']
2026-04-29 14:01:13 [INFO] ResultAggregator: Mapping 'Market Overview' -> 2427 chars
2026-04-29 14:01:13 [INFO] ResultAggregator: Mapping 'Research Conclusions' -> 2597 chars
2026-04-29 14:01:13 [INFO] ResultAggregator: Mapping 'Executive Summary' -> 2577 chars
2026-04-29 14:01:13 [INFO] ResultAggregator: Using source tracking for exact matching
2026-04-29 14:01:13 [INFO] ResultAggregator: Section 'Executive Summary' content length=2577 chars
2026-04-29 14:01:13 [INFO] ResultAggregator: Section 'Market Overview' content length=2427 chars
2026-04-29 14:01:13 [INFO] ResultAggregator: Section 'Research Conclusions' content length=2597 chars
2026-04-29 14:01:13 [INFO] ResultAggregator: Generated 3 sections using source tracking
```

**Key Findings**:
1. Aggregation phase correctly generated 3 sections
2. Each section's content length is correct (approximately 2500 chars)
3. Source tracking matching correctly executed

## Root Cause Location

### Problem Is Not at the Aggregation Layer

Logs prove `ResultAggregator` is working correctly:
- Layer storage is correct
- Source tracking is correct
- Section generation is correct

### Problem Is at the Content Source

Looking at HTML lines 33-52 (section_1 content):
- Line 33 starts with "Executive Summary" content
- Lines 53-77 again show "Executive Summary", "Market Overview", "Research Conclusions" as sub-headings
- This content is **already mixed in the raw Agent output**

### The Real Problem: Agent Output Already Contains Multiple Section Contents

Looking at HTML content structure:
```
section_1:
  - Executive Summary body (lines 33-52)
  - Sub-heading "China New Energy Vehicle Market Deep Research Analysis Report" (line 53)
  - Sub-heading "Executive Summary" (line 54)
  - Executive Summary body repeated (line 55)
  - Sub-heading "Market Overview" (line 56)
  - Market Overview body (lines 57-69)
  - Sub-heading "Research Conclusions" (line 70)
  - Research Conclusions body (lines 71-77)
```

**Conclusion**: The Agent's "Executive Summary" output already contains the complete content of "Market Overview" and "Research Conclusions"!

## Fix Plan

### Plan A: Filter at Agent Output Stage (Recommended)

In `ResultAggregator.aggregate()`, add **section boundary detection** for each Agent's content:
- Detect whether the content contains titles of other sections
- If so, truncate before the first other section title

### Plan B: Handle in Content Quality Pipeline

Add **section boundary filter** in `ContentCleaningPipeline`:
- Detect Markdown headings (## Executive Summary, ## Market Overview, etc.)
- Only retain the current section's content

### Plan C: Clearly Instruct in Prompt

Modify the Synthesis Agent's Prompt:
- Clearly require output of only the current section's content
- Do not include content from other sections

## Recommended Fix

**Priority: Plan A + Plan B**

1. Add section boundary detection in `ResultAggregator.aggregate()`
2. Add section boundary filter in `ContentCleaningPipeline`

### Implementation Code

```python
# Add in result_aggregator.py

def _detect_section_boundary(self, content: str, current_section: str) -> str:
    """
    Detect section boundary, truncate before the first other section title
    
    Args:
        content: Raw content
        current_section: Current section name
        
    Returns:
        Truncated content
    """
    # Known section title list
    section_titles = [
        "Executive Summary", "Market Overview", "Research Conclusions", "Data Sources",
        "Market Size", "Competitive Landscape", "Development Trends", "Policy Environment",
        "Technology Development", "Risk Analysis", "Investment Recommendations"
    ]
    
    lines = content.split('\n')
    result = []
    
    for line in lines:
        stripped = line.strip()
        
        # Detect Markdown heading
        match = re.match(r'^#{1,3}\s+(.+)$', stripped)
        if match:
            title = match.group(1).strip()
            
            # If heading is from another section, stop
            if title in section_titles and title != current_section:
                logger.info(f"Detected section boundary: '{title}', truncating content")
                break
        
        result.append(line)
    
    return '\n'.join(result)
```

## Next Steps

1. Implement Plan A: Add section boundary detection in `ResultAggregator.aggregate()`
2. Implement Plan B: Add section boundary filter in `ContentCleaningPipeline`
3. Test and verify
