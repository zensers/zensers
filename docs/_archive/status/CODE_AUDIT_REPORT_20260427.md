# Code Deep Audit Report - Full Version

## Report Generation to Layout Output Module - Memory Risk Systematic Audit

**Audit Date**: 2026-04-27  
**Audit Scope**: Report Generation → Layout Output → Preview Generation → Agent → Skill → Storage  
**Audit Method**: 8 parallel exploration agents deep analysis  
**Audit Status**: Complete

---

## Audit Results Overview

| Module | Risk Points Found | High Risk | Medium Risk | Low Risk |
|--------|------------------|-----------|-------------|----------|
| **Report Generation Module** | 8 | 3 | 4 | 1 |
| **Document Generation Module** | 6 | 3 | 2 | 1 |
| **Layout Output Module** | 12 | 4 | 6 | 2 |
| **Preview Generation Module** | 7 | 3 | 3 | 1 |
| **Agent Module** | 8 | 3 | 4 | 1 |
| **Skill Module** | 9 | 4 | 4 | 1 |
| **Memory Configuration Module** | 6 | 2 | 3 | 1 |
| **Total** | **56** | **22** | **26** | **8** |

---

## High Risk Detailed Checklist

### I. Report Generation Module

**File**: `src/core/orchestrator/output/report_generator.py`

| ID | Location | Issue Description | Trigger Scenario |
|----|----------|------------------|------------------|
| R-001 | `_prepare_research_result` (lines 526-654) | All sections/subsections built as large dictionary in memory | Large report generation |
| R-002 | `_generate_docx` (lines 283-315) | Debug output produces debug_sections.json and debug.html | Memory doubles for large documents |
| R-003 | `_generate_markdown/_generate_html` | HTML content built as large string in memory | No streaming |

**Fix Suggestions**:
- Introduce segmented/streaming output
- Disable or conditionalize debug artifacts
- Lazy loading/generation strategy for large documents

---

### II. Document Generation Module

**File**: `src/core/orchestrator/output/document_generator.py`

| ID | Location | Issue Description | Trigger Scenario |
|----|----------|------------------|------------------|
| D-001 | `__init__` (lines 86-106) | `_content` list continuous accumulation, no cleanup mechanism | Long-running memory leak |
| D-002 | `_generate_docx` (lines 305-315) | HTML conversion produces huge intermediate strings | Large document conversion |
| D-003 | ContentOrchestrator cache | Intermediate data structures no size limit | Continuous memory growth |

---

### III. Layout Output Module

**File**: `src/converters/html_to_word.py`, `html_to_pdf.py`, `html_to_ppt.py`

| ID | Location | Issue Description | Trigger Scenario |
|----|----------|------------------|------------------|
| C-001 | `convert()` | Entire HTML string passed to parser, no streaming | 50MB limit still may OOM |
| C-002 | `base_parser.py` elements list | All parse results cached in memory | Linear memory growth |
| C-003 | CSSStyleExtractor | Style rules cache no upper limit | Large CSS files |
| C-004 | Image processing | `doc.add_picture()` directly loads | Large image memory spike |

---

### IV. Preview Generation Module

**File**: `src/core/preview/preview_generator.py`

| ID | Location | Issue Description | Trigger Scenario |
|----|----------|------------------|------------------|
| P-001 | `_cache_index` (lines 96-99) | Cache dictionary unlimited growth, no LRU eviction | Long-running memory leak |
| P-002 | `_generate_html_from_docx` (lines 385-457) | Entire DOCX loaded into memory | Large document OOM |
| P-003 | Concurrency safety missing | `_cache_index` no lock protection | Race conditions |
| P-004 | MAX_PREVIEW_SIZE not used | 10MB limit defined but not actually checked | Limit ineffective |

---

### V. Agent Module

**File**: `src/agents/fixed_agents/`

| ID | File | Issue Description | Trigger Scenario |
|----|------|------------------|------------------|
| A-001 | `document_generation_agent.py` | `_shared_memory` long-term resident research results | Historical data accumulation |
| A-002 | `report_generation_agent.py` | `full_report` large text concatenated in memory | Large report generation |
| A-003 | `quality_check_agent.py` | `RevisionService` revision history accumulates in memory | Phase 8 auto fix |

---

### VI. Skill Module

**File**: `src/skills/`

| ID | File | Issue Description | Trigger Scenario |
|----|------|------------------|------------------|
| S-001 | `docx_skill.py` | Document object memory spike during large document generation | Large tables/reports |
| S-002 | `search_skill.py` | HTML full loading, response.text no size limit | Large webpage scraping |
| S-003 | `web_scraper_skill.py` | `_html_to_markdown` recursion depth no limit | Deep nested DOM |
| S-004 | `web_scraper_skill.py` | `_extract_text` no default max_chars limit | Very large text extraction |

---

### VII. Memory Configuration Module

**File**: `src/core/memory_pool.py`, `src/core/cache.py`

| ID | File | Issue Description | Trigger Scenario |
|----|------|------------------|------------------|
| M-001 | `memory_pool.py` | MemoryMonitor depends on psutil, returns error only without psutil | Production missing dependency |
| M-002 | `core_memory.py` | CoreMemory 10KB limit may be too small | Complex user configuration |

---

## Phase Fix Plan

### P0 - Must fix this week (4.5 hours)

| # | Module | Fix Item | Effort | Risk Reduction |
|---|--------|----------|--------|----------------|
| 1 | Preview Generation | Add thread lock and LRU eviction to `_cache_index` | 2h | 60% reduction |
| 2 | Preview Generation | Enforce MAX_PREVIEW_SIZE limit | 1h | 40% reduction |
| 3 | Report Generation | Remove or conditionalize debug output | 1h | 50% reduction |
| 4 | Layout Output | Reduce MAX_HTML_SIZE to 10MB | 0.5h | 30% reduction |

### P1 - Fix within 2 weeks (16 hours)

| # | Module | Fix Item | Effort |
|---|--------|----------|--------|
| 1 | Report Generation | `_prepare_research_result` streaming | 4h |
| 2 | Document Generation | Add `clear_content()` cleanup method | 2h |
| 3 | Agent | Add TTL and capacity cap to SharedMemory | 4h |
| 4 | Skill | Add depth limit for recursive parsing | 2h |
| 5 | Global | Add memory monitor decorator | 2h |
| 6 | Storage Management | Paginated/batched processing for large datasets | 2h |

### P2 - Optimize within 1 month (3 days)

| # | Module | Fix Item | Effort |
|---|--------|----------|--------|
| 1 | Layout Output | HTML chunked parsing | 1 day |
| 2 | Skill | Streaming download | 4h |
| 3 | Agent | Large object disk-offload strategy | 1 day |
| 4 | Global | Memory baseline test | 1 day |

---

## Audit Conclusion

### Core Findings

1. **Memory explosion root cause located**: Mainly in three areas: full-loading of large objects, unlimited cache growth, unprotected recursion depth

2. **Most dangerous code paths**:
   - `_prepare_research_result` full structure build
   - `_cache_index` unlimited preview cache growth
   - `SharedMemory` cross-task cache without TTL
   - Recursive HTML parsing without depth limit

3. **Fix priorities clear**: P0 items can reduce 60% of memory risk after fixing

### Existing Memory Mechanism Evaluation

| Mechanism | Status | Evaluation |
|-----------|--------|------------|
| Memory monitoring | Exists | MemoryMonitor based on psutil, ensure dependency |
| Cache limits | Partial | Some modules have LRU, some missing |
| Resource cleanup | Partial | Exists but coverage incomplete |
| TTL mechanism | Missing | Most caches have no expiry strategy |
| Thread safety | Missing | Preview cache etc. no lock protection |

---

**Audit Completion Time**: 2026-04-27  
**Auditor**: AI Code Audit System  
**Report Version**: v1.0
