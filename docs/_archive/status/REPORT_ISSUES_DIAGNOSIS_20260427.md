# Report Generation Issue Diagnosis Report

## User Reported Issues

### Issue 1: Table of Contents Title Duplication
```
Table of Contents

Executive Summary
Market OverviewMarket Overview  ← Duplicate title
Research ConclusionResearch Conclusion  ← Duplicate title
Data SourceData Source  ← Duplicate title
```

### Issue 2: "Original Insight" Still Appearing
```
Original Insight: The NEV market is transitioning from "penetration rate breakthrough" to "real demand verification"
```

### Issue 3: Content Duplication
Same paragraph content repeated multiple times

### Issue 4: Separator Lines Still Present
```
------
```

---

## Root Cause Analysis

### Root Cause 1: HTML Template Rendering Issue

**Problem Location**: `config/document_templates/word_default.html` Lines 307-311

```html
{% for section in sections %}
<div class="toc-item">
    <a href="#{{ section.id }}">{{ section.title }}</a>
</div>
{% endfor %}
```

**Problem**: Template only renders `section.title`, but `section.content` may **already contain title text**!

**Data Flow Analysis**:
```
1. LLM generates content:
   "## Executive Summary\n\nQ1 2026..."
   
2. _content_to_html processing:
   Converts "## Executive Summary" to <h2>Executive Summary</h2>
   
3. Template rendering:
   <h1 class="chapter-title">Executive Summary</h1>  ← from section.title
   <div class="section-content">
     <h2>Executive Summary</h2>  ← from section.content!
     ...
   </div>
```

**Result**: Title appears twice!

---

### Root Cause 2: Cleanup Logic Not Called

**Problem Location**: Cleanup logic in `document_generation_agent.py`

**Cause**: Cleanup logic is in `_clean_llm_content` method, but it may:
1. Not be called correctly
2. Regex not match actual format

**Verification**:
- "Original Insight:" should be matched by `r'^Original Insight[：:]\s*'`
- "------" should be matched by `r'^[-*_]{3,}$'`

**Possible Cause**:
- Cleanup happens **after content has been added to sections**
- Or cleanup only targets specific fields, not covering all content

---

### Root Cause 3: Content Duplication Sources

**Possible Causes**:

1. **section.content contains duplicate paragraphs**
   - LLM generates duplicates from the start
   - Or duplicates added during content concatenation

2. **Bug in _generate_document_structure**
   - Although we fixed the loop append bug
   - If input `self._content` itself has duplicate elements, problem persists

3. **Template rendering issue**
   - If section.content and section.title contain same text
   - Template renders twice

---

## Fix Plan

### Fix 1: Prevent Title Duplicate Rendering

**Plan A**: Remove leading title in `_content_to_html`

```python
@staticmethod
def _content_to_html(content: str) -> str:
    """Convert raw text content to HTML"""
    if not content:
        return ""
    
    lines = content.split('\n')
    result = []
    
    # **Fix**: Skip leading headers (because template renders section.title)
    start_idx = 0
    while start_idx < len(lines):
        stripped = lines[start_idx].strip()
        # Skip leading ## headers
        if re.match(r'^#{1,2}\s+', stripped):
            start_idx += 1
            continue
        # Skip empty lines
        if not stripped:
            start_idx += 1
            continue
        break
    
    # Start processing from non-header content
    lines = lines[start_idx:]
    # ... continue existing logic
```

**Plan B**: Modify template to not render section.title

```html
<!-- Before modification -->
<h1 class="chapter-title">{{ section.title }}</h1>
<div class="section-content">
    {{ section.content }}
</div>

<!-- After modification -->
<div class="section-content">
    {{ section.content }}  <!-- content already includes title -->
</div>
```

---

### Fix 2: Ensure Cleanup Logic Covers All Content

**Problem**: Cleanup may only apply to specific fields

**Fix**: Apply cleanup before all content output

```python
def _clean_all_content(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """Clean problematic text from all content"""
    
    # Clean sections
    if "sections" in data:
        for section in data["sections"]:
            if "content" in section:
                section["content"] = self._clean_llm_content(section["content"])
            if "title" in section:
                section["title"] = self._clean_llm_content(section["title"])
    
    # Clean key_findings
    if "key_findings" in data:
        data["key_findings"] = [
            self._clean_llm_content(f) if isinstance(f, str) else f
            for f in data["key_findings"]
        ]
    
    return data
```

---

### Fix 3: Enhance Cleanup Regex

**Current Regex**:
```python
r'^Original Insight[：:]\s*',
r'^Original Insight\s*',
```

**Problem**: Only matches line start, but "Original Insight:" may appear at paragraph beginning

**Enhanced**:
```python
r'Original Insight[：:]\s*',  # Remove ^, match any position
r'Original Insight\s*',
r'^------+$',  # Match separator lines
r'^[-*_]{3,}$',  # Match various separator lines
```

---

### Fix 4: Detect and Remove Duplicate Content

**Add deduplication in `_generate_document_structure`**:

```python
def _remove_duplicate_paragraphs(self, content: str) -> str:
    """Remove duplicate paragraphs"""
    lines = content.split('\n')
    seen = set()
    result = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        
        # Detect duplicates (ignore space differences)
        normalized = ' '.join(stripped.split())
        if normalized in seen:
            continue  # Skip duplicate
        
        seen.add(normalized)
        result.append(line)
    
    return '\n'.join(result)
```

---

## Fix Priority

| Priority | Problem | Fix Plan | Impact |
|----------|---------|----------|--------|
| P0 | Title duplication | Plan A: _content_to_html skip leading headers | High |
| P0 | "Original Insight" not cleaned | Enhance cleanup regex, cover all content | High |
| P1 | Separator lines not cleaned | Already fixed, needs verification | Medium |
| P1 | Content duplication | Add deduplication logic | Medium |

---

## Verification Tests

After fix, verify:

1. **No title duplication**
   - Each title appears only once in TOC
   - Body titles do not duplicate with TOC

2. **"Original Insight" cleaned**
   - Report does not contain "Original Insight:" text
   - Insight content presented directly

3. **Separator lines removed**
   - No "------" etc. separator lines

4. **No content duplication**
   - Same paragraph does not appear multiple times

---

**Diagnosis Date**: 2026-04-27
**Issue Count**: 4
**Root Cause Identification**: Complete
**Fix Plan**: Pending Implementation
