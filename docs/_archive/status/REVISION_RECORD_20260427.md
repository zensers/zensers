# Revision Record - April 27, 2026

## Overview

This revision addresses multiple systemic issues in the report generation system, including title duplication, table of contents generation failure, non-standard data source annotations, report structure disorder, and content deduplication. v5 implements content pipeline refactoring phase one, addressing the title duplication problem at its root cause.

**Revision Version**: v5 (Content Pipeline Refactoring - Phase One)

---

## Audit Issue Fixes

### P0: section_title Parameter Fix

**Audit Issue Found**:
- `section_title` parameter was passed but not used in the header skip logic
- Actual logic unconditionally skipped all headers at the beginning, which could cause legitimate sub-headers to be incorrectly deleted

**Fix Content**:

```python
# Before: Unconditionally skip all headers at beginning
if re.match(r'^#{1,3}\s+', stripped):
    start_idx += 1
    continue

# After: Only skip headers matching section_title
md_match = re.match(r'^#{1,3}\s+(.+)$', stripped)
if md_match:
    title_text = md_match.group(1).strip()
    if section_title and title_text.strip() == section_title.strip():
        start_idx += 1
        continue
    break  # Keep non-matching headers
```

**Test Result**: PASS - Keep legitimate sub-headers, skip duplicate headers

---

### P1: Section Name Parsing Fix

**Audit Issue Found**:
- `parts[-1]` always takes the last part, could get a number instead of section name
- `analysis_MarketSize_2` → "2" ❌

**Fix Content**:

New `_extract_section_name` method:

```python
def _extract_section_name(self, agent_id: str) -> str:
    """Extract section name from agent_id, supporting multiple formats"""
    parts = agent_id.split("_")
    
    # Filter out purely numeric parts
    non_numeric_parts = [p for p in parts if not p.isdigit()]
    
    # Filter out known prefix types
    prefix_types = {"deep", "analysis", "market", "financial", ...}
    meaningful_parts = [p for p in non_numeric_parts if p.lower() not in prefix_types]
    
    return meaningful_parts[-1] if meaningful_parts else non_numeric_parts[-1]
```

**Test Result**: PASS - All formats correctly parsed

---

### P2: Separator Line Cleanup Fix

**Audit Issue Found**:
- Separator line cleanup had line count limit `i < 10`, which could cause subsequent separator lines to not be cleaned

**Fix Content**:

```python
# Before
if re.match(r'^[-*_]{3,}$', stripped) and i < 10:
    continue

# After: Remove line count limit
if re.match(r'^[-*_]{3,}$', stripped):
    continue
```

**Test Result**: PASS - All separator lines correctly cleaned

---

## Revision Checklist

### 1. Title Duplication Fix

**Problem Description**:
- Chapter titles like "Executive Summary" appeared twice in the report: once as a level-1 heading (h1) and once as a level-3 heading (h3)
- Cause: After template rendered `section.title`, `section.content` still contained `## Executive Summary` header

**Modified File**:
- `src/content/content_orchestrator.py`

**Modification Content**:

```python
# Before
def _content_to_html(content: str) -> str:
    ...

# After
def _content_to_html(content: str, section_title: Optional[str] = None) -> str:
    ...
    # Only skip headers matching section_title, keep other legitimate sub-headers
    if section_title and title_text.strip() == section_title.strip():
        i += 1
        continue
```

**Impact Scope**:
- `_prepare_template_variables()` - Pass section_title parameter
- `_render_section_html()` - Pass section_title parameter

**Test Result**: PASS

---

### 2. Table of Contents Generation Fix

**Problem Description**:
- Table of contents page was empty or could not be generated properly
- Cause: HTML used `<nav class="document-toc">` but `HTMLToWordConverter` expected `<div class="toc">`

**Modified File**:
- `src/content/content_orchestrator.py`

**Modification Content**:

```python
# Before
html_parts.append('<nav class="document-toc">')
html_parts.append('<h2>Table of Contents</h2>')
html_parts.append('<ul class="toc-list">')
for section in sections:
    html_parts.append(f'<li><a href="#{section.id}">{html.escape(section.title)}</a></li>')
html_parts.append('</ul>')
html_parts.append('</nav>')

# After
html_parts.append('<div class="cover-page">')
html_parts.append(f'<h1 class="document-title">{html.escape(title)}</h1>')
html_parts.append('</div>')

html_parts.append('<div class="toc">')
html_parts.append('<h2>Table of Contents</h2>')
for i, section in enumerate(sections, 1):
    html_parts.append(f'<p class="toc-item">{i}. {html.escape(section.title)}</p>')
    if section.subsections:
        for j, subsec in enumerate(section.subsections, 1):
            html_parts.append(f'<p class="toc-item" style="margin-left: 20px;">{i}.{j} {html.escape(subsec.title)}</p>')
html_parts.append('</div>')
```

**Test Result**: PASS

---

### 3. Data Source Annotation Optimization

**Problem Description**:
- Data in the body was annotated as [Source 15] format, affecting reading experience
- User requirement: Only chart data needs source annotations, body data does not
- But academic papers and other scenarios need to retain body citations

**Modified Files**:
- `src/core/decomposition/strategies.py`
- `src/core/research_framework_manager.py`
- `config/research_frameworks.yaml`

**Modification Content**:

#### 3.1 New Configuration Item

```yaml
# config/research_frameworks.yaml
academic_paper:
  name: Academic Research Report
  agent_config:
    content:
      require_inline_citations: true  # Academic reports need inline source annotations

default:
  content:
    require_inline_citations: false  # Default no inline source annotations in body
```

#### 3.2 Configuration Parsing Support

```python
# src/core/research_framework_manager.py
@dataclass
class ContentConfig:
    require_inline_citations: bool = False  # New field

def requires_inline_citations(self) -> bool:
    """Whether inline citation annotations are required"""
    return self.agent_config.content.require_inline_citations
```

#### 3.3 Analysis Prompt Dynamic Adjustment

```python
# src/core/decomposition/strategies.py
def _build_analysis_prompt(self, topic, aspect, framework_config):
    require_inline_citations = framework_config.requires_inline_citations() if framework_config else False
    
    if require_inline_citations:
        citation_instruction = "Data must annotate sources (using [Source X] format)"
    else:
        citation_instruction = "Body data does not need source annotations, present data directly"
```

**Test Result**: PASS

---

### 4. Cleanup Logic Enhancement

**Problem Description**:
- Analysis labels like "Original Insight:" were not cleaned
- Cause: Regex only matched line start, but actual content might be at paragraph beginning

**Modified File**:
- `src/agents/fixed_agents/document_generation_agent.py`

**Modification Content**:

```python
# New cleanup patterns
prompt_patterns_to_remove = [
    # ... existing patterns ...
    r'Original Insight[：:]\s*',          # Delete "Original Insight:" from paragraphs
    r'Original Insight\s*[：:]',          # Delete "Original Insight:" (with space variants)
]

# New inline replacement logic
cleaned_line = line
for pattern in [r'Original Insight[：:]\s*', r'Original Insight\s*[：:]']:
    cleaned_line = re.sub(pattern, '', cleaned_line)

# Separator line cleanup: Remove line count limit
if re.match(r'^[-*_]{3,}$', stripped):
    continue
```

**Test Result**: PASS

---

### 5. Synthesis Task Filtering Fix

**Problem Description**:
- Synthesis chapters (Executive Summary, Research Conclusion, etc.) were incorrectly receiving raw data
- Should only generate based on analysis chapter content

**Modified File**:
- `src/core/orchestrator/execution/engine.py`

**Modification Content**:

```python
def _build_synthesis_task(self, requirement, previous_results, **kwargs):
    sections = []
    for r in previous_results:
        if not r.get("success"):
            continue
        agent_id = r.get("agent_id", "")
        
        # Only process DEEP_ANALYSIS phase results
        is_analysis = (
            "deep_analysis" in agent_id or 
            ("analysis" in agent_id and "data_collection" not in agent_id and "research" not in agent_id)
        )
        
        if is_analysis:
            section_name = self._extract_section_name(agent_id)  # New: use improved parsing method
            sections.append({"id": agent_id, "title": section_name, "content": content})
    
    return {"sections": sections, ...}  # Only return chapter content, not raw data
```

**Test Result**: PASS

---

### 6. Content Duplication Fix (New)

**Problem Description**:
- Paragraph-level duplication appeared in chapters like Executive Summary
- Same paragraph output twice by LLM

**Modified File**:
- `src/agents/fixed_agents/document_generation_agent.py`

**Modification Content**:

New two methods:

```python
def _deduplicate_paragraphs(self, content: str) -> str:
    """Remove duplicate paragraphs from content"""
    # Detect consecutive similar paragraphs and skip
    ...

def _is_similar_paragraph(self, text1: str, text2: str, threshold: float = 0.9) -> bool:
    """Determine if two paragraphs are similar"""
    # Supports exact match, normalized match, substring inclusion, etc.
    ...
```

Called in content processing flow:

```python
# New: Remove duplicate paragraphs (LLM may generate duplicate content)
cleaned_content = self._deduplicate_paragraphs(cleaned_content)
```

**Test Result**: PASS - Duplicate paragraphs correctly removed

---

### 7. Writing Style Standardization (New)

**Problem Description**:
- Content overly colloquial: "It is worth noting that", "Coincidentally" etc.
- Unnecessary source explanations: "(Multiple agencies predict)"
- Does not meet professional research report standards

**Modified File**:
- `src/core/decomposition/strategies.py`

**Modification Content**:

Add writing style constraints to all analysis prompts:

```python
### Writing Style Requirements (Professional Research Report Standards)
- ❌ No colloquial expressions: e.g., "It is worth noting that", "Coincidentally", "Interestingly", "It must be said"
- ❌ No speech-style: e.g., "Let's look at", "Imagine", "Did you know"
- ❌ No short video commentary style: e.g., "This means", "In other words", "Simply put"
- ❌ No parenthetical source explanations: e.g., "(Multiple agencies predict)", "(Data shows)", "(According to research)"
- ✅ Use professional written language: Directly state facts and judgments, no transitional colloquialisms
- ✅ Data presentation: Give data directly, no need to explain data source or origin
- ✅ Judgment presentation: Give conclusions directly, no need for "We believe", "Analysis shows" prefixes

**Example Comparison**:
- ❌ Incorrect: "It is worth noting that, although the 15.2% year-over-year growth rate has significantly slowed from 28.2% in 2025..."
- ✅ Correct: "The 15.2% year-over-year growth rate has significantly slowed from 28.2% in 2025, but the absolute increment still reaches approximately 3 million units."

- ❌ Incorrect: "China's total automobile sales in 2026 are expected to exceed 34.75 million units (multiple agencies predict)..."
- ✅ Correct: "China's total automobile sales in 2026 are expected to exceed 34.75 million units, with NEV increment covering almost all of the overall market growth."
```

**Impact Scope**:
- `_build_analysis_prompt()` - Deep analysis prompt
- `_build_synthesis_prompt()` - Executive Summary, Research Conclusion, Core Insights prompts

**Test Result**: PASS - Prompts updated

---

## Test Results Summary

| Test Item | Status | Description |
|-----------|--------|-------------|
| Title Duplication Fix | PASS | Only skip matching title, keep legitimate sub-headers |
| Table of Contents Fix | PASS | HTML output includes correct div wrapper |
| Data Source Annotation | PASS | Default no inline annotations, academic config requires |
| Cleanup Logic | PASS | "Original Insight" etc. tags correctly cleaned |
| Synthesis Filtering | PASS | Correctly filtered to analysis chapters |
| Section Name Parsing | PASS | All formats correctly parsed |
| Separator Line Cleanup | PASS | All separator lines correctly cleaned |
| Content Duplication Fix | PASS | Duplicate paragraphs correctly removed |
| Writing Style Standardization | PASS | Prompts updated with professional writing constraints |

---

## Modified File List

| File Path | Modification Type | Description |
|-----------|-------------------|-------------|
| `src/content/content_orchestrator.py` | Modified | Title skip logic (only skip matching titles) |
| `src/core/decomposition/strategies.py` | Modified | Analysis prompt dynamic adjustment |
| `src/core/research_framework_manager.py` | Modified | New require_inline_citations config |
| `src/core/orchestrator/execution/engine.py` | Modified | New _extract_section_name method |
| `src/agents/fixed_agents/document_generation_agent.py` | Modified | Cleanup logic enhancement, separator fix |
| `config/research_frameworks.yaml` | Modified | New academic_paper config |

---

## Usage Guide

### General Research Report (Default)

```python
# Use default config, body data no inline annotations
# Chart data annotated below charts
# All data sources listed at end of report
```

### Academic Research Report

```python
# Use academic_paper config
# Body data needs inline annotations (e.g., "2024 sales 12.80 million units [Source 15]")
# Chart data annotated with sources
# References listed at end of report
```

---

## Review Points

1. **Title Duplication**: Verify that `_content_to_html` only skips titles matching `section_title`
2. **Table of Contents**: Verify `<div class="toc">` wrapper is correctly recognized by `HTMLToWordConverter`
3. **Data Source**: Verify `require_inline_citations` config is correct for different report types
4. **Cleanup Logic**: Verify separator line cleanup has removed line count limit
5. **Section Name Parsing**: Verify `_extract_section_name` method correctly handles various formats
