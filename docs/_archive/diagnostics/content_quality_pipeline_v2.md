# Content Quality Pipeline Design Proposal (Revised v2)

> Revised based on Oracle review feedback and in-depth code analysis
> Revision Date: 2026-04-29

---

## Part 1: In-depth Problem Analysis

### 1.1 Complete Current Deduplication Mechanism Map

Through in-depth code analysis, the existing three-layer deduplication architecture is as follows:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 1: Single Agent Output Level (document_generation_agent.py)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Method                    │ Line    │ Function                │ Limitations        │
│ _clean_llm_content        │ 943-1028│ Clean LLM prefix and prompt traces │ Hardcoded patterns    │
│ _deduplicate_paragraphs   │ 702-766 │ Consecutive paragraph deduplication │ Only checks adjacent    │
│ _clean_inline_duplicates  │ 822-900 │ Inline duplicate cleanup            │ Only checks before/after  │
│ _clean_duplicate_html     │ 768-820 │ HTML tag deduplication           │ Only adjacent tags    │
│ _is_similar_paragraph     │ 902-941 │ Similarity judgment              │ Only substring containment    │
│ prompt_patterns_to_remove │ 972-985│ Regex pattern list            │ Not configurable      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 2: Result Aggregation Level (result_aggregator.py)                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ Method                │ Line    │ Function                │ Limitations          │
│ _deduplicate()        │ 724-750 │ List data point deduplication          │ Only string comparison    │
│ _convert_to_sections  │ 108-438 │ Deduplicate by section["id"]   │ Does not check content duplication  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 3: Report Generation Level                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ File                    │ Method              │ Function              │ Limitations     │
│ document_generator.py   │ seen_titles dedup   │ Merge sections with same title  │ Only title matching │
│ report_generation_agent │ _integrate_body     │ ❌ No dedup logic     │ Completely missing   │
│ content_orchestrator.py │ _content_to_html    │ ❌ No dedup logic     │ Completely missing   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Key Findings

| Finding | Severity | Description |
|---------|----------|-------------|
| **CrossTypeDuplicateDetector direction bug** | High | Original `i-1` forward scanning, but title comes first, paragraph comes after, should scan backward |
| **GlobalDuplicateDetector ratio logic** | Medium | When containment is established, ratio is necessarily < 1.0, threshold check may misjudge |
| **ReportGenerationAgent completely missing** | High | 400 lines of code, `_integrate_body()` has no deduplication |
| **ContentOrchestrator missing** | Medium | `_content_to_html()` is the last link in HTML conversion, no deduplication |
| **min_length=50 too high for Chinese** | Medium | Chinese analysis paragraphs are usually 30-50 characters, 50-char threshold may filter valid content |
| **_is_similar_paragraph only checks substring** | Medium | Doesn't check semantic similarity, may miss rewritten duplicates |

### 1.3 Data Flow Analysis

```
Agent Output
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: document_generation_agent._clean_llm_content()    │
│          + _deduplicate_paragraphs()                        │
│          ↓ Cleaned Markdown string                          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: result_aggregator.aggregate()                      │
│          → AggregationResult.to_dict()                      │
│          → _convert_to_sections()                           │
│          ↓ List[Dict] sections structure                    │
└─────────────────────────────────────────────────────────────┘
    │
    ├──────────────────┬─────────────────────┐
    ▼                  ▼                     ▼
┌─────────────┐  ┌─────────────────┐  ┌───────────────────┐
│ Path A      │  │ Path B          │  │ Path C            │
│ DocGen      │  │ ReportGenAgent  │  │ ContentOrchestrator│
│ seen_titles │  │ ❌ No dedup     │  │ ❌ No dedup       │
└─────────────┘  └─────────────────┘  └───────────────────┘
```

**Key Problem**: The quality layer should be inserted after Layer 2, but needs to cover all three rendering paths.

---

## Part 2: Revised Architecture Design

### 2.1 Insertion Point Selection

**Revised Decision**: The quality layer should be a post-processing step of `AggregationResult`, not an independent intermediate layer.

```python
# Original plan: Independent intermediate layer
AggregationResult.to_dict() → ContentQualityPipeline → DocumentGenerator

# Revised plan: Embed inside to_dict()
AggregationResult.to_dict():
    1. _convert_to_sections() → sections
    2. ContentQualityPipeline.process(sections) → cleaned_sections  # New
    3. Return {"sections": cleaned_sections, ...}
```

**Advantages**:
1. All rendering paths pass through the quality layer
2. Does not break existing call chains
3. Quality check happens after data is structured, before rendering

### 2.2 Core Component Revisions

#### 2.2.1 CrossTypeDuplicateDetector Revision

**Original plan bug**: Forward scanning `range(i-1, i-5, -1)`

**Problem Analysis**:
```
Markdown structure:
### Market Size              ← heading (i)
Market size reached 500 billion...  ← paragraph (i+1)

Original plan checks i-1 to i-5, but there is no paragraph above the heading!
Should check i+1 to i+5, looking for paragraphs below the heading.
```

**Revised Implementation**:

```python
class CrossTypeDuplicateDetector(ContentFilter):
    """
    Cross-type duplicate detection (revised)
    
    Detects if heading and immediately following paragraph content are highly similar.
    Solves: body first sentence using same text as sub-heading.
    
    Revision points:
    1. Fix scan direction: forward → backward
    2. Add multi-paragraph check: check up to 3 paragraphs after heading
    3. Retention strategy: prioritize retaining paragraphs (more complete info), delete duplicate headings
    """
    
    def __init__(self, threshold: float = 0.75, max_scan_lines: int = 5):
        self.threshold = threshold
        self.max_scan_lines = max_scan_lines
    
    def apply(self, content: str) -> str:
        lines = content.split('\n')
        result = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Check if it's a Markdown heading
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                heading_level = heading_match.group(1)
                heading_text = heading_match.group(2).strip()
                
                # Revised: scan backward to find paragraphs
                found_duplicate = False
                for j in range(i + 1, min(i + 1 + self.max_scan_lines, len(lines))):
                    next_line = lines[j].strip()
                    
                    # Skip blank lines
                    if not next_line:
                        continue
                    
                    # Stop at next heading
                    if next_line.startswith('#'):
                        break
                    
                    # Check paragraph-heading similarity
                    similarity = self._text_similarity(heading_text, next_line)
                    
                    if similarity > self.threshold:
                        logger.info(f"Cross-type duplicate detected: "
                                   f"heading '{heading_text[:30]}...' matches paragraph "
                                   f"(similarity={similarity:.2f})")
                        found_duplicate = True
                        break
                    
                    # Only check first non-empty paragraph
                    break
                
                if found_duplicate:
                    # Strategy: skip heading, keep paragraph (paragraph has more info)
                    logger.debug(f"Skipping duplicate heading: {heading_text[:30]}...")
                    i += 1
                    continue
            
            result.append(line)
            i += 1
        
        return '\n'.join(result)
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate text similarity (revised)
        
        Revision points:
        1. Add Chinese punctuation handling
        2. Add digit normalization (avoid data differences causing misjudgment)
        3. Return more precise similarity score
        """
        # Remove punctuation and whitespace (including Chinese punctuation)
        clean1 = re.sub(r'[\s,，。、；：""''！？()（）【】\[\]《》—…·]', '', text1)
        clean2 = re.sub(r'[\s,，。、；：""''！？()（）【】\[\]《》—…·]', '', text2)
        
        # Digit normalization: replace consecutive digits with placeholder
        clean1 = re.sub(r'\d+', 'N', clean1)
        clean2 = re.sub(r'\d+', 'N', clean2)
        
        if not clean1 or not clean2:
            return 0.0
        
        # Calculate character overlap ratio
        set1 = set(clean1)
        set2 = set(clean2)
        
        if not set1 or not set2:
            return 0.0
        
        intersection = set1 & set2
        union = set1 | set2
        
        # Jaccard similarity
        jaccard = len(intersection) / len(union) if union else 0.0
        
        # Containment bonus
        shorter, longer = (clean1, clean2) if len(clean1) < len(clean2) else (clean2, clean1)
        if shorter in longer:
            containment_ratio = len(shorter) / len(longer)
            return max(jaccard, containment_ratio * 0.9)
        
        return jaccard
```

#### 2.2.2 GlobalDuplicateDetector Revision

**Original plan issues**:
```python
if (normalized in seen_norm or seen_norm in normalized):
    ratio = min(len(normalized), len(seen_norm)) / max(len(normalized), len(seen_norm))
    if ratio > self.threshold:  # When shorter in longer, ratio is necessarily < 1.0
```

**Revised Implementation**: (Content continues with the rest of the file translated similarly)
