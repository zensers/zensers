# Zensers Changelog

> Recording major project changes, including feature additions, architecture adjustments, code refactoring, etc.

---

## [1.0.1] - 2026-06-02

### Bug Fixes

#### BF-1: Zustand persist hydration mismatch — client-side crash on page load

**Problem**: Browser crashed with `Text content does not match server-rendered HTML` error. Server renders default "OpenAI" from `useSettingsStore`, but client reads "DeepSeek" from localStorage, causing React hydration mismatch.

**Root Cause**: `useSettingsStore` calls `getInitialState()` at module top-level, which reads `localStorage` on client but returns defaults on server. The `ChatInput` component renders `<Select value={llm.provider}>` with this mismatched value.

**Fix**: Added `mounted` state guard in `ChatInput.tsx` — provider/model `<Select>` components and bottom hint text only render after `useEffect(() => setMounted(true))` fires (client-only). SSR/first-paint shows "Loading..." placeholder.

**Files Changed**:
- `web/src/components/chat/ChatInput.tsx` — Added `mounted` state + conditional rendering for provider selector, model selector, and bottom hint

#### BF-2: Next.js 404 on static chunks after cache corruption

**Problem**: All `/_next/static/chunks/*` resources returned 404, page blank. Caused by stale `.next` build cache.

**Fix**: Deleted `.next` directory and restarted dev server.

#### BF-3: Zustand persist store schema mismatch on version upgrade

**Problem**: Old persisted session data (missing new fields like `qualityState`, `pendingInput`) caused hydration errors when merged with current store schema.

**Fix**: Added `merge` function in `useSessionStore.ts` persist config that fills missing fields from `emptyCache()` defaults, ensuring backward compatibility with old persisted data.

**Files Changed**:
- `web/src/store/useSessionStore.ts` — Added `merge` function to persist config

### Quality Feedback Revision System — Frontend Implementation

#### FE-1: QualityPanel component

**New file**: `web/src/components/quality/QualityPanel.tsx`
- Displays overall score, section scores, issue list
- Issue actions: 修订 (start revision), 忽略 (dismiss), 恢复 (reopen)
- 确认交付 (confirm delivery) with pending-issues confirmation dialog
- Version history display

#### FE-2: MainLayout integration

**File**: `web/src/components/layout/MainLayout.tsx`
- QualityPanel shown when `session.qualityState` exists and `phase !== 'confirmed'`
- Rendered as right sidebar (w-80) with border separator

#### FE-3: ChatInput pendingInput prop

**File**: `web/src/components/chat/ChatInput.tsx`
- New `pendingInput` prop for quality panel to pre-fill revision instructions
- `useEffect` watches `pendingInput` and sets input text

#### FE-4: ChatPanel pendingInput wiring

**File**: `web/src/components/chat/ChatPanel.tsx`
- Reads `pendingInput` from session store, passes to `ChatInput`
- Clears `pendingInput` via `syncActive({ pendingInput: null })` after consumption

### Quality Feedback Revision System — Backend Implementation

#### BE-1: QualityActionRequest extended

**File**: `src/api/research_api.py`
- Added `issue_id`, `version_id`, `section_name` fields
- Migrated from module-level function to ResearchAPI instance method

#### BE-2: 5 quality action handlers implemented

**File**: `src/api/research_api.py`
- `_handle_quality_dismiss` — Mark issue as dismissed
- `_handle_quality_reopen` — Restore dismissed issue to open
- `_handle_quality_rollback` — Restore snapshot version (HTML + sections + quality state)
- `_handle_quality_confirm` — Confirm delivery with force override for pending issues
- `_handle_quality_recheck` — Re-run quality check on specified or all sections

#### BE-3: Quality SSE event persistence

**File**: `src/core/session_streamer.py`
- Fixed `push_quality_confirmed()` bug (L258-264 residual code causing NameError)
- Added `_persist_event` calls to `push_preview_refresh` and `push_section_quality`
- Added timestamp to persisted events

#### BE-4: Quality check agent issue ID generation

**File**: `src/agents/fixed_agents/quality_check_agent.py`
- Issues now include stable `id` (via `generate_issue_id`), `section`, and `state` fields

#### BE-5: Quality state model updates

**File**: `src/core/quality/quality_state.py`
- `QualityIssue` gained `revision_count: int = 0` field
- Added `QUALITY_PASS_THRESHOLD = 60` constant (unified across codebase)

#### BE-6: Revision-quality integration

**File**: `src/api/research_api.py`
- `_handle_v2_revision()` now creates quality snapshot before revision
- `_post_revision_recheck()` automatically rechecks after revision + pushes SSE
- `_confirm_v2_revision()` triggers recheck after accept
- Revision count tracking and max-retry enforcement
- Preview health check after revision with warning on layout issues

#### BE-7: Concurrency protection

**File**: `src/api/research_api.py`
- Quality operations protected by `asyncio.Lock` via `_get_quality_lock()`
- Prevents concurrent quality action conflicts

### Frontend Type Extensions

**File**: `web/src/types/api.ts`
- Added `QualityIssueData`, `SectionScoreData`, `QualityStateData`, `PendingInputData`, `VersionInfoData` types
- Extended `SSEMessage` event types with `quality_result`, `section_quality`, `preview_refresh`, `quality_confirmed`

**File**: `web/src/store/useSessionStore.ts`
- `SessionCache` now includes `qualityState` and `pendingInput` fields
- `partialize` excludes these from persistence (too large / transient)

**File**: `web/src/hooks/useProgress.ts`
- Added `QualityResultEventData`, `SectionQualityEventData`, `PreviewRefreshEventData`, `QualityConfirmedEventData` interfaces
- Extended `UseSessionStreamOptions` with quality-related callbacks

---

## [1.0.0] - 2026-05-13

### 🚀 Features
- Version management system: VERSION file as single source of truth
- Automatic update detection on startup (30-min polling)
- Update banner UI with dismiss/remind logic
- Header badge for new version availability
- Settings panel version info card with error state display
- SemVer comparison with full prerelease support
- Multi-source remote version fetch: GitHub API → Gitee API → cache
- Desktop notifications via plyer (non-blocking)
- Changelog API (text + JSON format)

### 🐛 Bug Fixes
- **agent_coordinator.py:558** — 修复 `registries_dir` 误用为 `storage_path` 的 bug，该错误导致 `data/registries/registries/` 嵌套目录产生（904 MB 重复数据）
- **history_compressor.py:73** — 修复 `user_id=None` 时产生 `"None"` 字符串目录名的 bug
- **compress_adapter.py:57** — 同上，修复 `user_id=None` 字符串化问题

### 🧹 Cleanup
- Phase A 安全清理：删除根目录测试脚本/日志（16 文件）
- 迁移根目录大文件：CSV（182 MB）→ `_cleanup_temp/`，Logo.psd（5.4 MB）→ `_archive/`
- 清理 data/ 子目录：backups、previews、sentiment、research_*、temp、results（91.5 MB）等
- 清理 data/sessions/archives/t/ + None/（5410 文件）
- 清理测试用户 t/ + test_user/ 及关联的 knowledge_bank 数据库
- 清理旧 revision 记录（保留近 7 天）
- 归档 docs/ 历史文档（87 文件至 docs/_archive/）
- 清理 __pycache__/、.pytest_cache/、logs/ 归档日志
- 编写 registries 迁移脚本 `scripts/migrate_registries.py`

---

## [2026-05-11] Report Chart Fix + Word Export Fix + Storage Cleanup

### Overview
Fixed three critical issues: (1) missing charts in intelligent routing reports, (2) empty Word documents on export due to parser type mismatch, (3) chaotic data storage. Also optimized preview loading to avoid browser delays on re-mount.

### Changes

**Bugfix: Charts missing in reports** (`src/core/orchestrator/orchestrator.py`)
- `_research_with_routing()` was not collecting `charts` from agent results when building `research_result_data`
- Added chart collection loop (same pattern as the traditional execution path)

**Bugfix: Word export produced empty document** (`src/converters/base_parser.py`, `html_to_word.py`)
- `HTMLElementParser` output raw HTML tag names (`h1`, `p`, `div`) but `_create_docx_document` expected semantic types (`heading`, `paragraph`, `div_start`)
- Rewrote parser: replaced single `_current_tag` with `_tag_stack` for proper nested element tracking
- Added `TAG_TYPE_MAP`: `h1`→`heading`, `p`→`paragraph`, `li`→`list_item`
- `div`/`section` now emit `*_start`/`*_end` structural markers
- Added `headers`+`rows` table format support in Word converter

**Bugfix: Word download path** (`src/api/document_api.py`, `src/api/main.py`)
- Export path changed from `data/{task_id}/` to `data/reports/{task_id}/`
- Download endpoint checks `data/reports/{task_id}/` first, falls back to legacy `data/{task_id}/`
- `get_preview()` download_url check also supports both paths

**Optimization: Preview loading** (`src/api/research_api.py`)
- For preview HTML files >10KB, omit `html_content` from JSON response
- Frontend falls back to loading via `preview_url` (static file serving), avoiding 50KB+ JSON string processing

### Files Changed
- `src/core/orchestrator/orchestrator.py` (+6 lines)
- `src/converters/base_parser.py` (major rewrite, +50/-30 lines)
- `src/converters/html_to_word.py` (+5 lines)
- `src/api/document_api.py` (+1 line)
- `src/api/main.py` (+15 lines)
- `src/api/research_api.py` (+10 lines)

### Files Referenced
- `docs/REVISION_RECORD.md`

## [2026-05-02] Prompt Externalization Phase 5 + Code Cleanup + Intelligent Routing Integration

### Overview

Completed remaining hardcoded prompt externalization, cleaned up dead code, integrated intelligent routing into the main execution flow.

### Prompt Externalization (3 groups -> 5 files)

Migrated 3 remaining hardcoded prompt groups from Python code to `prompts/agents/`:

| Original Location | Original Constant | Migrated To |
|-------------------|-------------------|-------------|
| `src/api/research_api.py` | `CONVERSATION_SYSTEM_PROMPT` (50 lines) | `prompts/agents/conversation.md` |
| `src/core/semantic_intent.py` | `INTENT_ANALYSIS_*_PROMPT` (22 lines) | `prompts/agents/intent_analysis_system.md` + `intent_analysis_user.md` |
| `src/core/task_structure.py` | `SECTION_ANALYSIS_*_PROMPT` (24 lines) | `prompts/agents/section_analysis_system.md` + `section_analysis_user.md` |

All prompts now load via `PromptManager.load()` / `load_profile()`, with `FileNotFoundError` fallback.

### Dead Code Cleanup

| File | Lines | Action |
|------|-------|--------|
| `src/core/dialogue/conversation_manager.py` | 234 | **Deleted** — Zero references |
| `src/core/dialogue/__init__.py` | — | Removed `ConversationManager` export |

### Intelligent Routing Integration

`ResearchAPI._start_execution()` now prioritizes calling `IntelligentRoutingAdapter.analyze()` to generate execution plans, falling back to handwritten plans on failure.

### Shared Prompt Directory

Created `prompts/_shared/` and added:
- `output_format.md` — Shared output format definition
- `json_instruction.md` — Shared JSON instructions

### Code Quality Fixes

| Fix | File | Description |
|-----|------|-------------|
| Missing `import json` | `research_api.py` | Added module-level import, eliminating NameError risk |
| Duplicate logic extraction | `semantic_intent.py` | Extracted `_load_intent_prompts()` + `_format_intent_prompt()` |
| Format injection protection | `semantic_intent.py`, `task_structure.py` | User input curly brace escaping |

### Modified File List

| File | Change |
|------|--------|
| `prompts/agents/conversation.md` | Added |
| `prompts/agents/intent_analysis_system.md` | Added |
| `prompts/agents/intent_analysis_user.md` | Added |
| `prompts/agents/section_analysis_system.md` | Added |
| `prompts/agents/section_analysis_user.md` | Added |
| `prompts/_shared/output_format.md` | Added |
| `prompts/_shared/json_instruction.md` | Added |
| `src/api/research_api.py` | Modified: prompt externalization + import json + intelligent routing |
| `src/core/semantic_intent.py` | Modified: prompt externalization + duplicate method extraction + injection protection |
| `src/core/task_structure.py` | Modified: prompt externalization + injection protection |
| `src/core/dialogue/__init__.py` | Modified: removed ConversationManager export |
| `src/core/dialogue/conversation_manager.py` | Deleted (234 lines of dead code) |

### Review Results

All 5 parallel reviews passed (Goal Verification / QA Execution / Code Quality / Security / Context Mining )

---

## [2026-04-29] Content Quality Pipeline Implementation

### Overview

Implemented structured content cleaning and quality check pipeline to resolve report content duplication issues.

### New Features

#### Content Quality Pipeline

**Core Components**:
- `ContentFilter`: Filter base class
- `ContentCleaningPipeline`: Cleaning pipeline
- `CrossTypeDuplicateDetector`: Cross-type deduplication (title vs paragraph)
- `GlobalDuplicateDetector`: Global cross-section deduplication
- `PromptPatternFilter`: Prompt trace cleanup
- `ContentQualityGate`: Quality gate

**Revision Points**:
1. **CrossTypeDuplicateDetector scan direction fix**: Changed from forward to backward scanning (title comes first, paragraph comes after)
2. **GlobalDuplicateDetector containment optimization**: Directly return high score when containment relationship is established
3. **Chinese adaptation**: `min_length` reduced from 50 to 30 to accommodate Chinese paragraph length

### Modified Files

| File | Change Type | Description |
|------|-------------|-------------|
| `src/core/orchestrator/aggregation/content_quality.py` | Added | Content quality pipeline core module |
| `src/core/orchestrator/aggregation/result_aggregator.py` | Modified | Integrated quality pipeline into `_convert_to_sections()` |
| `src/agents/fixed_agents/report_generation_agent.py` | Modified | Added deduplication in `_integrate_body()` |
| `config/content_quality.yaml` | Added | Configuration file |
| `tests/unit/test_content_quality.py` | Added | Unit tests (29 cases) |

### Test Results

- `test_content_quality.py`: **29/29 passed**
- `test_intelligent_routing_integration.py`: **7/7 passed**
- `test_intelligent_routing_full.py`: **14/14 passed**

### Oracle Review Conclusion

**Can be safely deployed**

Issues found have been fixed:
- `total_duplicates` count has been added
- Regex escape warnings have been fixed

---

## [2026-04-28] Intelligent Routing Runtime Issue Fixes

### Overview

This update fixes three critical runtime issues discovered after traditional routing cleanup, ensuring the intelligent routing system runs normally.

### Fix Content

#### P0-1: Agent instance missing section_id attribute

**Problem**: The `ContentLockManager` uses section_id format during initialization (e.g., `section_0_MarketSize`) different from what `ExecutionEngine` uses when looking up (e.g., `analysis_0_MarketSize`), causing "Section xxx not found" errors.

**Root Cause**: `AgentSpec.context` stores `section_id`, but `GenericAgent` and `BaseAgent` instances did not extract it as an attribute during creation, causing `_get_section_id_from_agent()` to fall back to `agent_id`.

**Fix**:
- `src/core/agents/generic_agent.py`: Extract `section_id` from `context` and set as attribute in `__init__`
- `src/core/agents/base.py`: Same
- `src/agents/fixed_agents/base_fixed_agent.py`: Same (found missing during review)

```python
# Fix code
self.section_id = self._context.get("section_id", "")
# or
context = self.config.get("context", {})
self.section_id = context.get("section_id", "")
```

#### P0-2: Skill configuration chain verification

**Problem**: Analysis found that `CATEGORY_TO_LANGCHAIN_SKILLS` mapping may not be called.

**Verification Result**: `load_skills_for_category()` method already exists in `src/skills/registry.py`, and `DynamicAgentFactory.create_agent_with_session()` correctly calls this method. No fix needed.

#### P0-3: _infer_skills() inference logic incomplete

**Problem**: `_infer_skills()` method only covers some scenarios, missing support for dimensions like "competitive landscape", "industry trends", "industry chain", etc.

**Fix**: `src/core/task_structure.py` - Extended keyword matching, supporting more research dimensions:

| Dimension | Keywords | Added Skills |
|-----------|----------|--------------|
| Market Size/Share | Market size, market share | `data_analysis`, `lc_python_repl` |
| Competitive Landscape | Competition, competitive landscape, competit | `market_analysis`, `data_analysis` |
| Industry Trends | Trends, industry trends, trend | `data_analysis` |
| Industry Chain | Industry chain, value chain, chain | `market_analysis` |
| Financial Analysis | Finance, valuation, financial, revenue | `stock_analysis`, `data_analysis` |
| Technology Analysis | Technology, technology, innovation | `lc_arxiv` |

### Files Involved

| File | Modification |
|------|--------------|
| `src/core/agents/generic_agent.py` | Added `section_id` attribute extraction |
| `src/core/agents/base.py` | Added `section_id` attribute extraction |
| `src/agents/fixed_agents/base_fixed_agent.py` | Added `section_id` attribute extraction (added after review) |
| `src/core/task_structure.py` | Enhanced `_infer_skills()` inference logic |
| `src/survey/backends/factory.py` | Added `close_all()` async cleanup method (fixed httpx event loop close error) |
| `src/core/orchestrator/orchestrator.py` | Fixed DocumentGenerationAgent.execute() parameter calling method + output path field retrieval |
| `src/core/orchestrator/execution/engine.py` | Fixed ContentLockManager section_id retrieval inconsistency |

### Runtime Issue Fixes

#### P0-4: DocumentGenerationAgent.execute() parameter error

**Problem**: `TypeError: DocumentGenerationAgent.execute() got an unexpected keyword argument 'research_result'`

**Root Cause**: `DocumentGenerationAgent.execute()` accepts a single `Dict[str, Any]` parameter, but orchestrator used keyword arguments.

**Fix**: Pack all parameters into a `task_input` dictionary and add `action` field.

#### P0-5: httpx event loop close error

**Problem**: `RuntimeError: Event loop is closed` - httpx AsyncClient tries to close connection after event loop is closed.

**Root Cause**: `BackendFactory` uses singleton pattern to cache backend instances but does not provide async cleanup method.

**Fix**: Added `close_all()` async method in `BackendFactory` to close all backend instances before program exit.

#### P0-6: ContentLockManager status not correctly updated

**Problem**: `synthesis` Agent is locked by content lock, showing "Required section section_1_MarketOverview is running, not completed", even though `analysis` Agent has completed successfully.

**Root Cause**: 
- Before Agent execution, `_get_section_id_from_agent(agent)` gets section_id (returns `section_1_MarketOverview`)
- After Agent execution, `_get_section_id_from_agent_id(agent_id)` gets section_id (returns `MarketOverview`)
- The two formats are inconsistent, causing ContentLockManager to fail to find the correct section status

**Fix**: When marking completed and failed, use the same method to get section_id as before execution.

#### P0-7: Document generation output path not correctly retrieved

**Problem**: Output path is empty after research completes, report cannot be generated normally.

**Root Cause**: 
- `DocumentGenerationAgent` returns result where path field is `document_path`
- Orchestrator retrieves `output_path`
- Field name mismatch causes retrieval failure

**Fix**: Modified the field retrieval logic in orchestrator to prioritize `document_path`.

#### P0-8: sections data type error

**Problem**: `sections` is empty during document generation, unable to generate content.

**Root Cause**: 
- `aggregated_dict.get("sections", {})` returns empty dictionary `{}`
- `_populate_document_content` expects `sections` to be a list `[]`
- Empty dictionary is not a list, causing iteration failure

**Fix**: Changed default value from `{}` to `[]`.

### Review Results

After 5-Agent parallel review:
- **QA Execution Verification**: PASS - All tests pass
- **Code Quality Review**: PASS - Code meets standards
- **Security Review**: PASS - No security vulnerabilities
- **Context Mining**: Found FixedAgent omission - Fix has been added

### Verification Status

- Python syntax check passed
- All modified files have no syntax errors
- QA test verification passed

---

## [2026-04-28] Phase 4: Remove Traditional Routing (Traditional Routing Cleanup Complete)

### Overview

This update is the final phase of traditional routing cleanup, completely removing the traditional routing implementation. The system now only uses intelligent routing.

### Deleted Files

| Type | File | Description |
|------|------|-------------|
| **Source** | `src/core/intent_gate.py` | Intent gate (keyword matching) |
| | `src/core/category_router.py` | Category router |
| | `src/core/unified_intent.py` | Unified intent analyzer |
| | `src/core/composite_intent_gate.py` | Composite intent gate |
| | `src/core/workflow_orchestrator.py` | Workflow orchestrator (depends on composite intent) |
| **Test** | `tests/unit/core/test_intent_gate.py` | IntentGate tests |
| | `tests/unit/core/test_category_router.py` | CategoryRouter tests |
| | `tests/unit/core/test_composite_intent.py` | Composite intent tests |
| | `tests/unit/core/test_workflow_orchestrator.py` | Workflow orchestrator tests |
| **Config** | `config/routing/intent_keywords.yaml` | Intent keyword configuration |
| | `config/routing/capability_templates.yaml` | Capability template configuration |

### Modified Files

| File | Modification |
|------|--------------|
| `src/core/orchestrator/orchestrator.py` | Removed traditional routing imports, initialization, calls |
| `src/core/orchestrator/__init__.py` | Updated exports to intelligent routing |
| `src/core/orchestrator/analysis/__init__.py` | Updated exports to intelligent routing |
| `src/core/semantic_intent.py` | Removed IntentGate fallback dependency |
| `src/skills/registry.py` | Inlined CATEGORY_TO_LANGCHAIN_SKILLS mapping |

### Backup Location

All deleted files have been backed up to: `_archive/legacy_routing/`

### System Changes

- **Intent Analysis**: `IntentGate` -> `IntelligentRoutingAdapter.analyze_simple()`
- **Capability Templates**: `CategoryRouter` -> `IntelligentRoutingAdapter.get_template_for_intent()`
- **Composite Intent**: `UnifiedIntentAnalyzer` -> Built into intelligent routing
- **Workflow Orchestration**: `WorkflowOrchestrator` -> Removed (depends on composite intent)

### Cleanup Summary

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Type Separation | Complete | Type definitions independent of implementation |
| Phase 2: Force Intelligent Routing | Complete | Enabled by default, added deprecation warnings |
| Phase 3: Compatibility Layer | Complete | Intelligent routing provides compatible interfaces |
| Phase 4: Remove Traditional Routing | Complete | Deleted traditional routing implementation files |

**Estimated code reduction**: ~2500 lines

---

## [2026-04-28] Phase 3: Create Compatibility Layer (Traditional Routing Cleanup)

### Overview

This update is the third phase of traditional routing cleanup, adding compatible interface methods in intelligent routing.

### Changes

#### New Methods

| Method | Description |
|--------|-------------|
| `analyze_simple()` | Compatible with `IntentGate.analyze()` interface, returns `IntentAnalysisResult` |
| `get_template_for_intent()` | Compatible with `CategoryRouter.route_to_template()` interface |

#### Compatibility Layer Design

```python
# Traditional routing call
intent_result = intent_gate.analyze(user_request, requirement)

# Intelligent routing compatible call
intent_result = routing_adapter.analyze_simple(user_request, requirement)
# Returns same type of IntentAnalysisResult
```

### Key Features

- `analyze_simple()` returns `IntentAnalysisResult`, fully compatible with traditional routing
- `get_template_for_intent()` provides mapping from intent to capability template
- Orchestrator already has complete intelligent routing execution path `_research_with_routing()`

### Next Steps

- Phase 4: Remove traditional routing implementation files

---

## [2026-04-28] Phase 2: Force Enable Intelligent Routing (Traditional Routing Cleanup)

### Overview

This update is the second phase of traditional routing cleanup, setting intelligent routing as the default option and adding deprecation warnings.

### Changes

#### Modified Files

| File | Modification |
|------|--------------|
| `src/core/orchestrator/orchestrator.py` | `use_intelligent_routing` default value changed to `True`, added deprecation warning |

### Key Changes

**Enable Intelligent Routing by Default**:
```python
# Before
use_intelligent_routing: bool = False

# After
use_intelligent_routing: bool = True
```

**Deprecation Warnings**:
- When intelligent routing initialization fails and falls back to traditional routing, output deprecation warning
- When user explicitly disables intelligent routing, output deprecation warning
- Warning content: `[Deprecation Warning] Traditional routing will be removed in a future version`

### Next Steps

- Phase 3: Create compatibility layer
- Phase 4: Remove traditional routing implementation

---

## [2026-04-28] Phase 1: Type Definition Separation (Traditional Routing Cleanup)

### Overview

This update is the first phase of traditional routing cleanup, separating intent type definitions from implementation files in preparation for complete removal of traditional routing.

### Changes

#### New Files

- `src/core/intent_types.py` - Intent type definition file
  - `IntentType` - Intent type enum
  - `TaskComplexity` - Task complexity enum
  - `AgentCreationStrategy` - Agent creation strategy data class
  - `IntentAnalysisResult` - Intent analysis result data class

#### Modified Files

| File | Modification |
|------|--------------|
| `src/core/intent_gate.py` | Import types from `intent_types.py`, remove type definitions |
| `src/core/semantic_intent.py` | Updated import path |
| `src/core/intelligent_routing_adapter.py` | Updated import path |
| `src/core/unified_intent.py` | Updated import path |
| `src/core/orchestrator/orchestrator.py` | Updated import path |
| `src/core/orchestrator/analysis/__init__.py` | Updated export path |

### Design Principles

- Type definitions separated from implementation logic
- Traditional routing and intelligent routing share the same type set
- Maintain backward compatibility (`intent_gate.py` still exports types)
- Test files do not need modification

### Next Steps

- Phase 2: Force enable intelligent routing
- Phase 3: Create compatibility layer
- Phase 4: Remove traditional routing implementation

---

## [2026-04-28] Runtime Test Issue Fixes

### Overview

This update fixes multiple issues discovered during actual runtime testing, including intelligent routing default enablement, preview HTML link return, data source marker removal, and blank section filtering.

### Fix Content

#### P0: Intelligent Routing Default Enablement

**Problem**: Intelligent routing feature was not enabled by default, causing summary parallel generation

**Fix**: `src/api/research_api.py`
- Changed `use_intelligent_routing` default value from `False` to `True`
- Ensured all research reports use intelligent routing flow by default

#### P1: Preview HTML Link Return

**Problem**: Preview returns PNG links instead of HTML links

**Fix**: `src/api/research_api.py`
- Added `base_url` parameter for constructing accessible URLs
- Added URL mapping logic in `get_preview()` method
- Prioritize checking pre-generated `.preview.html` files

#### P2: Data Source Marker Removal

**Problem**: Data source markers in format `[Source:xxx]` appearing in the body text

**Fix**: `src/core/decomposition/strategies.py`
- Strengthened prompt wording, explicitly prohibiting adding source markers
- Added "Strictly prohibited from adding any source markers in the body text" instruction

#### P3: Blank Section Filtering

**Problem**: Two blank sections ("Key Findings", "Conclusions and Recommendations") at the end of the document

**Root Cause Analysis**:
1. `DocumentGenerator._prepare_research_result` does not filter empty heading sections
2. `ContentOrchestrator._parse_sections` does not filter sections with empty titles
3. `word_default.html` template renders fixed sections unconditionally

**Fix**:

1. **document_generator.py** (lines 566-581):
   - Check if `text.strip()` is empty when processing level-1 headings
   - Skip level-1 sections with empty titles to avoid generating blank sections

2. **content_orchestrator.py** (lines 437-447):
   - Check if `final_title.strip()` is empty before creating ContentSection
   - Skip chapters with empty titles, add debug logging

3. **word_default.html** (lines 361-372, 404-412):
   - Added `{% if key_findings and key_findings|length > 0 %}` condition for "Key Findings" section
   - Added `{% if conclusion and conclusion|trim|length > 0 %}` condition for "Conclusions and Recommendations" section

### Test Verification

- Python syntax verification passed
- All modified files have no diagnostic errors

### Files Involved

| File | Modification |
|------|--------------|
| `src/api/research_api.py` | Intelligent routing default enablement, preview URL mapping |
| `src/core/decomposition/strategies.py` | Strengthened source marker prohibition instruction |
| `src/core/orchestrator/output/document_generator.py` | Empty title section filtering |
| `src/content/content_orchestrator.py` | Empty title section filtering |
| `config/document_templates/word_default.html` | Fixed section conditional rendering |

---

## [2026-04-20] Quality Control System + HTML Converter Fixes

### Overview

This update implements a complete quality control and intelligent routing system, and fixes Markdown residual issues in HTML to Word/PPT converters.

### Core Features

#### 1. Quality Control Module

**New Files**:
- `src/core/quality/__init__.py` - Module exports
- `src/core/quality/metadata_extractor.py` - QualityMetadataExtractor (380 lines)
- `src/core/quality/checkers.py` - Three checkers (450 lines)
- `src/core/quality/feedback_executor.py` - Feedback executor (280 lines)

**Configuration Update**: `config/system.yaml` added quality configuration node

```yaml
quality:
  thresholds:
    data_collection: 70    # Data collection threshold
    analysis: 70           # Analysis threshold
    report: 80             # Overall report threshold
  max_retries: 3           # Maximum retry count
```

**Core Features**:
- Three-stage quality check: Data collection -> Analysis -> Report
- Feedback loop: Not pass -> Retry 3 times -> Best score output
- Degradation handling: Only degrade when no data

#### 2. HTML to Word Converter Fix

**File**: `src/converters/html_to_word.py`

**Fix Content**:
- Added `_convert_markdown_to_html()` - Markdown preprocessing
- Added `_convert_markdown_inline()` - Inline Markdown conversion
- Added `_apply_heading_style()` - CSS style application
- Added `_add_formatted_run()` - Inline format handling
- Support for `**bold**`, `*italic*`, `` `code` `` conversion
- Support for section/div structural tags
- Apply CSS styles to Word elements

**File**: `src/converters/base_parser.py`

**Fix Content**:
- Added `inline_format_stack` - Track inline formats
- Added `section_stack` - Track section structure
- Extended `handle_starttag()` - Support strong/em/code tags

#### 3. HTML to PPT Converter Fix

**File**: `src/converters/html_to_ppt.py`

**Fix Content**:
- Added `_sanitize_html()` - Clean HTML + Markdown preprocessing
- Added `_convert_markdown_to_html()` - Markdown to HTML
- Added `_add_formatted_text()` - Add formatted text
- Fixed `_atomic_save()` - Use shutil.move instead of os.replace
- All slide creation methods support inline formatting

### Bug Fixes

#### 1. MetadataExtractor Type Compatibility Fix

**Problem**: `[MetadataExtractor] Extraction failed: 'str' object has no attribute 'get'`

**Cause**: `QualityMetadataExtractor.extract()` expects dictionary input, but Skill output may be a string

**Fix**:
- `src/core/quality/metadata_extractor.py:129-155` - Added type checking and automatic conversion
- `src/core/orchestrator/execution/engine.py:924-961` - `_extract_raw_output()` ensures dict return

#### 2. Formatted String Syntax Error

**Problem**: `Invalid format specifier '.1f if best_result else 0' for object of type 'float'`

**Cause**: Conditional expression syntax error in f-string

**Fix**:
- `src/core/quality/feedback_executor.py:193-197` - Separated conditional judgment

```python
# Before fix
f"Best score: {best_result.score:.1f if best_result else 0}"

# After fix
best_score = best_result.score if best_result else 0
f"Best score: {best_score:.1f}"
```

#### 3. Section ID and Aggregated Data Key Mismatch

**Problem**: Report word count insufficient (191 words vs required 1000), section content shows "[To be added]"

**Cause**: Framework section IDs (e.g., `market_size`) do not match aggregated data keys (e.g., `MarketSize`)

**Fix**:
- `src/core/orchestrator/aggregation/result_aggregator.py:232-296` - Enhanced matching logic

**Added Matching Strategies**:
1. Exact ID match
2. Fuzzy match (key contains section_id or section_name)
3. Alias name match (bidirectional inclusion)
4. ID alias mapping (common English names to Chinese names)

```python
# Alias mapping example
id_aliases = {
    "market_size": ["market_size", "scale", "market"],
    "competition": ["competition", "competitive_landscape", "competition"],
    "industry_chain": ["industry_chain", "value_chain", "chain"],
    ...
}
```

### Deprecated Code Cleanup

| Deleted Item | Description |
|--------------|-------------|
| `skill_output_standardizer.py` | Skill output standardization module (543 lines) |
| `standardized_output.py` | Standardized output module (787 lines) |
| `LayoutDesignAgent` initialization | Removed redundant calls, functionality integrated into DocumentGenerationAgent |

### Test Results

```
# Markdown conversion tests
[PASS] '**bold**' -> '<strong>bold</strong>'
[PASS] '*italic*' -> '<em>italic</em>'
[PASS] '`code`' -> '<code>code</code>'

# Word conversion tests
[PASS] Document generation successful - 36812 bytes, estimated pages: 1

# PPT conversion tests
[PASS] PPT generation successful - 30236 bytes, slide count: 3
```

### Data Flow Verification

```
User requirements -> ResearchOrchestrator -> Data Collection Agent
    ↓
Quality check (threshold 70) -> Pass/Retry
    ↓
Analysis Agent -> Quality check (threshold 70) -> Pass/Retry
    ↓
Report Generation Agent -> Quality check (threshold 80) -> Pass/Retry
    ↓
ContentOrchestrator -> HTML intermediate format
    ↓
HTMLToWordConverter/HTMLToPPTConverter -> Final document
```

---

## [2026-04-19] Systematic Integration Fix - Communication Method Compatibility Fix

### Overview

Fixed the issue of `CommunicationMixin` missing `set_message_bus()` and `set_shared_memory()` methods, and CLI calling wrong method names.

### Key Fixes

#### 1. CommunicationMixin Missing Methods

**File**: `src/core/agents/mixins.py`

**Problem**: `orchestrator.py` calls `set_message_bus()` and `set_shared_memory()`, but `CommunicationMixin` only has `inject_communication()` method

**Fix**: Added backward compatibility methods
```python
def set_message_bus(self, message_bus):
    self._message_bus = message_bus

def set_shared_memory(self, shared_memory):
    self._shared_memory = shared_memory
```

#### 2. CLI Method Name Error

**File**: `src/cli/main.py:77`

**Problem**: CLI calls `orchestrator.process_request()` but the method does not exist

**Fix**: Changed to call the correct `research()` method
```python
# Before fix
result = await orchestrator.process_request(requirement)
# After fix
result = await orchestrator.research(requirement)
```

### Verification Status

- ResearchOrchestrator initialization successful
- CLI research command started successfully
- Windows console encoding issue (not a code issue)

---

## [2026-04-19] Systematic Integration Fix - Survey Analysis Complete Data Flow

### Overview

This update systematically fixed all integration issues in the market research report generation system, ensuring complete data flow from survey data collection to report generation.

### P0 Key Fixes

#### 1. Survey Data Return Completeness Fix

**File**: `src/core/orchestrator/orchestrator.py:1794-1802`

**Problem**: Survey data returned by `_execute_survey_phase` was missing key fields

**Fix**: Added complete return fields
```python
return {
    "status": "completed",
    "survey_id": result.get("survey_id"),
    "mode": survey_mode,
    "responses_count": len(survey_responses),
    "findings": survey_findings,
    "survey_section": survey_section,
    "survey_document": result.get("survey_document"),
    # Added complete data
    "responses": survey_responses,
    "analysis": survey_findings,
    "statistics": survey_findings.get("statistics", {}),
    "insights": survey_findings.get("insights", []),
    "cross_analysis": survey_findings.get("cross_analysis", {}),
    "survey": result.get("survey", {}),
}
```

#### 2. Chart Generation Integration

**File**: `src/agents/fixed_agents/survey_analysis_agent.py`

**New Features**:
- Integrated `ChartGenerator` service
- Added `_generate_charts()` method
- Supports automatic bar chart and statistical chart generation
- Returns chart path list

#### 3. Data Mapping Fix

**File**: `src/content/content_orchestrator.py:197-250`

**Problem**: `data_points` not correctly mapped to `section.tables`

**Fix**:
- Get section tables from `research_result.sections[i].tables`
- Support automatic conversion of `section.data_points` to table format
- Added global `tables` variable rendering

#### 4. Template Engine Loop Rendering Fix

**File**: `src/content/template_engine.py`

**Fix Content**:
- Fixed nested loop `{% for %}...{% endfor %}` matching logic
- Fixed nested condition `{% if %}...{% endif %}` handling
- Support for complex nested structures (e.g., `{% if %} -> {% for %} -> {% for %}`)
- Fixed `render_loops` recursive call logic

#### 5. Unified Storage Path

**Fixed Files**:
- `src/core/orchestrator/orchestrator.py:209`
- `src/core/orchestrator/output/storage_manager.py:51`
- `src/agents/fixed_agents/survey_integration_agent.py:814`

**Unified Path**: `output/reports/{task_id}/`

### P1 Feature Enhancements

#### 1. Quality Check Agent Integration

**File**: `src/core/orchestrator/orchestrator.py:264, 517-540`

**New**:
- Initialize `QualityCheckAgent`
- Automatic quality check after document generation
- Record quality issues in non-interactive mode

#### 2. Advanced Statistical Indicators

**File**: `src/agents/fixed_agents/survey_analysis_agent.py:274-298`

**New Indicators**:
- Standard deviation (std_dev)
- Variance (variance)
- 95% confidence interval (confidence_interval_95)
- Quartiles (q1, q3, iqr)

#### 3. Correlation Analysis

**File**: `src/agents/fixed_agents/survey_analysis_agent.py:345-470`

**New Features**:
- Pearson correlation coefficient calculation
- Chi-square test (categorical variables)
- Correlation strength interpretation

### Template Updates

**Files**: `config/document_templates/word_default.html`, `config/document_templates/ppt_default.html`

**Word Template New**:
- Global data table area `{% if tables %}`
- Section `tables` data rendering support

**PPT Template New**:
- Section `tables` data rendering support
- Global data table slide `{% if tables %}`
- Unified table style

**New**: Global data table area
```html
{% if tables %}
<section id="data-tables">
    <h1 class="chapter-title">Key Data</h1>
    {% for table in tables %}
    <table>...</table>
    {% endfor %}
</section>
{% endif %}
```

### Test Results

| Test Module | Result |
|-------------|--------|
| content module | 29/29 passed |
| orchestrator import | 6/6 passed |
| Feature verification | 5/5 passed |

### Unified Storage Structure

```
output/reports/{task_id}/
├── report.docx              # Research report
├── survey/                  # Survey related
│   ├── questionnaire.docx
│   └── analysis.json
├── charts/                  # Chart files
└── preview/                 # Preview files
```

---

## [2026-04-17] Document Generation System Completion + Project Organization

### New Features

#### 1. McKinsey Style Report Generator

Implemented professional report generation in international publication style:

- **Color Scheme**: Deep navy blue primary + Amber gold accent (three-color principle)
- **Chart Types**: Bar chart, horizontal bar chart, donut chart, combination chart, etc. (10 types)
- **Layout**: Generous white space, clear hierarchy, McKinsey standard format
- **Markdown Fix**: `**bold**` correctly converted to Word native bold

**New Files**:
- `src/services/chart_generator.py` - Chart generation service

#### 2. DocumentGenerationAgent Completion

Completed core functionality of the document generation Agent:

- `_handle_produce_document()` - Full document generation flow implementation
- `_load_research_result()` - Load research results from history
- `_populate_document_content()` - Populate document content
- `_fallback_generate_document()` - Fallback generation method

### Code Cleanup

#### Deleted Files

| Category | Count | Description |
|----------|-------|-------------|
| Cache directories | 295+ | `__pycache__/`, `.cache/`, `.pytest_cache/`, etc. |
| Deprecated documents | 39 | `docs/_archive/` directory |
| Temporary files | 20+ | `memory_modules.txt`, `qa_*.txt`, etc. |
| Test data | 300+ | `data/backups/`, `data/revisions/`, etc. |
| Test research | 11 | Test data in `docs/research_results/` |

#### Deleted Root Temporary Files

- `task_plan.md`, `findings.md`, `progress.md`
- `memory_modules.txt`, `memory_tests.txt`
- `echo_test.txt`, `simple_test.txt`, `qa_output.txt`
- `test_result.log`, `.coverage`, `test.bat`

### Documentation Updates

| File | Description |
|------|-------------|
| `docs/API.md` | Added API documentation, including core Agent, Skill, Service API |
| `README.md` | Updated project structure description |
| `CHANGELOG.md` | This changelog |

### Project Structure Optimization

```
market_report_systerm/
├── config/                 # Configuration files
├── data/                   # Runtime data (cleaned)
├── docs/                   # Documentation directory
│   ├── API.md              # API documentation (new)
│   ├── CHANGELOG.md
│   ├── ROADMAP.md
│   └── KNOWLEDGE_BASE/
├── examples/               # Example code
├── output/                 # Output directory
├── scripts/                # Utility scripts
├── src/                    # Source code
└── tests/                  # Test code
```

### Output Example

Generated McKinsey-style research report:
- `output/ChinaLithiumBatteryIndustryCompetitionAnalysis_McKinseyStyle.docx` (322 KB)
- Contains 4 professional data charts

---

## [2026-04-10] Dual-Track Learning System Integration + Multi-Version Cleanup

### New Features

#### 1. Dual-Track Learning System

Integrated oh-my-openagent (OMO) multi-Agent collaboration mechanism to form two independent learning tracks:

**Track 1 (Wisdom)**: Tool-layer evolution, enhancing Agent factory capabilities
- `src/core/intent_gate.py` - Intent analysis module (7 intent types, 4 complexity levels)
- `src/core/category_router.py` - Agent capability template routing (6 predefined templates)
- `src/core/wisdom.py` - Experience storage and Skills recommendation

**Track 2 (Knowledge)**: Knowledge-layer accumulation (optional injection)
- Inject KnowledgeBank and CoreMemory via `inject_knowledge_components()`

#### 2. ResearchOrchestrator Unified Version

`src/core/orchestrator/research_orchestrator.py` becomes the only Orchestrator implementation:
- Integrates dual-track learning system
- Supports Chinese and English keyword analysis
- Provides unified research flow entry

### Code Cleanup

#### Deleted Multi-Version Files (8)

| File | Reason |
|------|--------|
| `src/agents/orchestrator.py` | Merged into research_orchestrator.py |
| `src/agents/orchestrator_v2.py` | Merged into research_orchestrator.py |
| `src/core/enhanced_orchestrator.py` | Merged into research_orchestrator.py |
| `src/core/enhanced_orchestrator_flow.py` | Functionality integrated |
| `src/core/agents/factory.py` (EnhancedAgentFactory) | Merged into factory.py |
| `src/agents/factory/` directory | Not used |
| `src/core/data_providers/databus_v3.py` | Not used |
| `src/core/memory/extraction/entity_extractor_v2.py` | Not used |

#### Renamed Files (3)

| Original File | New File | Description |
|---------------|----------|-------------|
| `src/core/agents/factory_v2.py` | `src/core/agents/factory.py` | DynamicAgentFactory becomes main version |
| `src/core/data_providers/databus_v2.py` | `src/core/data_providers/databus.py` | DataBusV2 becomes main version |
| `src/core/storage_enhanced.py` | `src/core/storage_wal.py` | Clear function distinction |

### Import Path Updates

| File | Old Import | New Import |
|------|------------|------------|
| `src/core/agents/__init__.py` | `factory_v2` | `factory` |
| `src/core/data_providers/__init__.py` | `databus_v2` | `databus` |
| `src/core/recovery_validator.py` | `storage_enhanced` | `storage_wal` |
| `src/core/auto_recovery.py` | `storage_enhanced` | `storage_wal` |
| `examples/agent_architecture_demo.py` | Rewritten | Uses new module paths |

### New Documentation and Tools

| File | Description |
|------|-------------|
| `docs/CODE_VERSION_GUIDELINES.md` | Version management specification document |
| `scripts/check_version_variants.py` | Multi-version file check script |
| `scripts/verify_orchestrator.py` | Integration verification script |
| `docs/CHANGELOG.md` | This changelog |

### Test Verification

**Quick Test**: 3/3 passed
- IntentGate test
- CategoryRouter test
- WisdomStore test

**Integration Verification**: 8/8 passed
- Import test
- Initialization test
- IntentGate test
- CategoryRouter test
- WisdomStore test
- Requirement parsing test
- English keyword test
- Dual-track status test

### Preventive Measures

1. **Specification Document**: `docs/CODE_VERSION_GUIDELINES.md`
2. **Check Script**: `scripts/check_version_variants.py`
3. **Core Principles**:
    - Prohibited from creating `_v2`, `_enhanced`, `_new` suffix files
    - Directly upgrade original files

---

## Change Statistics

| Category | Count |
|----------|-------|
| New modules | 4 |
| Deleted files | 8 |
| Renamed files | 3 |
| Updated imports | 5 |
| New tests | 3 |
| New documents | 4 |

---

## Next Steps

### Phase 3 Pending
- [ ] Deep integration with DynamicAgentFactory
- [ ] Hook system support

### Phase 4 Production Ready
- [ ] Integration testing with existing Orchestrator
- [ ] End-to-end verification

---

*Last updated: 2026-04-10*
