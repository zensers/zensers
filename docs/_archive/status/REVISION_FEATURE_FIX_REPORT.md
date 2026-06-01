# Report Revision Feature Fix Report

> **Document Version**: 2.0  
> **Generation Date**: 2026-04-30  
> **Status**: Pending Fix  
> **Priority**: P0 (Core Functionality Missing)

---

## I. Problem Overview

### 1.1 Problem Description

User reported "Report revision feature cannot be used normally." Systematic analysis found **end-to-end integration gaps**:

- **Frontend**: Missing revision entry UI (history detail page can view preview but has no revision functionality)
- **Backend API**: `handle_feedback` method is an empty implementation (only logs requests, does not execute revision)
- **Core Component**: `RevisionService` etc. implemented but not integrated into API layer
- **Orchestrator.revise**: Complete revision logic implemented but not called by API layer

### 1.2 Usage Scenario Differences

| Scenario | CLI Mode | Frontend Mode |
|----------|----------|---------------|
| Entry Point | Choose revision after research **preview HTML** | Can initiate revision **after loading history session** |
| Interaction Method | Command-line interaction `session revise <task_id> --aspects "Market Size"` | UI chapter selection + revision description |
| Data Source | Current research task results | Historical research task results |
| Trigger Location | Preview step in `interaction_callback` | `history/[id]` detail page |

### 1.3 Impact Scope

| Impact Item | Description |
|-------------|-------------|
| User Experience | Users cannot revise and optimize generated reports |
| Feature Completeness | Phase 8 core functionality unavailable |
| System Value | Report quality cannot be iteratively improved through feedback |

---

## II. Existing Implementation Analysis

### 2.1 Implemented Core Components

```
Components fully implemented but not called by API layer:

┌─────────────────────────────────────────────────────────────┐
│ Orchestrator.revise(task_id, aspects)                      │
│ ├── Load task: TaskPersistenceManager.load_task()           │
│ ├── Rebuild requirement: ResearchRequirement               │
│ ├── Filter chapters: _filter_plan_by_aspects()             │
│ ├── Create Agent: _create_agents_from_plan()               │
│ ├── Execute research: ExecutionEngine.execute_with_scheduler()│
│ ├── Aggregate results: ResultAggregator.aggregate()        │
│ ├── Merge chapters: _merge_results()                       │
│ └── Generate document: DocumentGenerationAgent.execute()   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ RevisionService (src/core/adjustment/revision_service.py)   │
│ ├── revise_from_user_feedback() ← User feedback revision    │
│ ├── revise_from_quality_check() ← System self-check revision│
│ └── Internally uses RevisionHandler, SectionLocator, ContentApplier│
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ PreviewRevisionWorkflow (src/core/workflow/)                │
│ └── Complete preview-revision workflow (not used)           │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 CLI Mode Implementation (Available)

**File**: `src/cli/main.py` Lines 590-607

```python
async def _session_revise(task_id: str, aspects: List[str]):
    """Partially revise specified chapters"""
    from src.core.orchestrator import ResearchOrchestrator
    
    if not aspects:
        console.print("[red]Please specify chapters to revise, e.g.: --aspects \"Market Size,Competitive Landscape\"[/red]")
        return
    
    console.print(f"[yellow]Revising chapters {aspects}...[/yellow]")
    orchestrator = ResearchOrchestrator()
    try:
        result = await orchestrator.revise(task_id, aspects)
        if result.status == "completed":
            console.print(f"[green]Revision complete! Report: {result.output_path}[/green]")
        else:
            console.print(f"[red]Revision failed: {result.status}[/red]")
    except Exception as e:
        console.print(f"[red]Revision failed: {e}[/red]")
```

**CLI Usage**:
```bash
# Revise specified chapters
python -m src.cli.main session revise research_abc123 --aspects "Market Size,Competitive Landscape"
```

### 2.3 Frontend Current State

**File**: `web/src/app/history/[id]/page.tsx`

```tsx
// Current functionality:
// ✅ Load historical research metadata
// ✅ Display research info (topic, time, format, etc.)
// ✅ Preview HTML report
// ✅ Export button (exists but not fully implemented)
// ❌ Revision button - does not exist
// ❌ Chapter selection - does not exist
// ❌ Revision description input - does not exist
```

### 2.4 API Layer Problem

**File**: `src/api/research_api.py` Lines 307-330

```python
elif action == "revise":
    # User requests revision
    if not section or not adjustment:
        return {
            "error": "Missing section or adjustment for revise action",
            "error_code": "MISSING_REVISION_PARAMS",
        }
    
    # Record revision request
    revision_count = session.get("revision_count", 0) + 1
    session["revision_count"] = revision_count
    session["last_revision"] = {
        "section": section,
        "adjustment": adjustment,
        "timestamp": datetime.now().isoformat(),
    }
    
    # Trigger revision (actual revision handled by Orchestrator)  ← ⚠️ This is just a comment!
    return {
        "session_id": session_id,
        "status": "revising",
        "message": f"Revising chapter '{section}'",
        "revision_count": revision_count,
    }
```

**Problem**: Code only logs the request, returns a fake status, does not actually call any revision function.

---

## III. Fix Plan

### 3.1 Architecture Design

```
Frontend Mode Revision Flow:

┌─────────────────────────────────────────────────────────────┐
│ history/[id]/page.tsx                                      │
│ ├── Load research metadata                                 │
│ ├── Display preview                                        │
│ └── [New] Revision button → Opens RevisionPanel            │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ RevisionPanel (New Component)                               │
│ ├── GET /api/v1/research/sections/{task_id} Get chapter list│
│ ├── Chapter multi-select                                    │
│ ├── Revision description text box                           │
│ └── Submit → POST /api/v1/research/revise                   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ ResearchAPI.revise_sections() (New Method)                  │
│ └── Calls Orchestrator.revise(task_id, sections)            │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Orchestrator.revise() (Already Implemented)                 │
│ ├── Load task data                                         │
│ ├── Filter specified chapters                              │
│ ├── Re-execute Agent                                       │
│ ├── Merge old and new results                              │
│ └── Generate new document                                  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Backend Fix

#### 3.2.1 Add Get Chapter List API

**File**: `src/api/research_api.py`

```python
async def get_sections(self, task_id: str) -> Dict[str, Any]:
    """
    Get report chapter list
    
    GET /api/v1/research/sections/{task_id}
    
    Used for frontend revision feature to display chapter selection list.
    """
    from src.core.storage import ResearchResultStore
    
    store = ResearchResultStore(storage_path="data")
    result = store.load_result(task_id)
    
    if not result:
        return {
            "error": "Task not found",
            "error_code": "TASK_NOT_FOUND",
        }
    
    # Extract chapter information
    sections = result.get("sections", [])
    section_list = []
    
    for i, section in enumerate(sections):
        if isinstance(section, dict):
            section_list.append({
                "id": section.get("section_id", f"section_{i+1}"),
                "title": section.get("title", section.get("section_id", f"Chapter {i+1}")),
                "level": section.get("level", 2),
                "word_count": len(section.get("content", "")),
            })
        elif isinstance(section, str):
            # Compatibility with old format
            section_list.append({
                "id": f"section_{i+1}",
                "title": section,
                "level": 2,
                "word_count": 0,
            })
    
    return {
        "task_id": task_id,
        "topic": result.get("topic", ""),
        "sections": section_list,
        "total_sections": len(section_list),
    }
```

#### 3.2.2 Add Revise Chapters API

**File**: `src/api/research_api.py`

```python
async def revise_sections(
    self,
    task_id: str,
    sections: List[str],
    adjustment: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Revise specified chapters
    
    POST /api/v1/research/revise
    
    Args:
        task_id: Task ID
        sections: List of chapter titles to revise
        adjustment: Revision description (used for Agent prompt)
        user_id: User ID
        
    Returns:
        {
            "success": true,
            "task_id": "xxx",
            "revised_sections": ["Market Size", "Competitive Landscape"],
            "new_preview_url": "/api/v1/previews/xxx_preview.html",
            "output_path": "/path/to/new/report.docx"
        }
    """
    from src.core.orchestrator import ResearchOrchestrator
    
    logger.info(f"revise_sections: task={task_id}, sections={sections}, adjustment={adjustment}")
    
    # 1. Validate input
    if not sections:
        return {
            "success": False,
            "error": "No sections specified",
            "error_code": "MISSING_SECTIONS",
        }
    
    # 2. Call Orchestrator.revise
    try:
        orchestrator = ResearchOrchestrator()
        result = await orchestrator.revise(task_id, sections)
        
        if result.status != "completed":
            return {
                "success": False,
                "error": result.summary or "Revision failed",
                "error_code": "REVISION_FAILED",
            }
        
        # 3. Generate new preview
        preview = self._preview_generator.generate_preview(
            document_path=result.output_path,
            format="html",
        )
        
        preview_url = None
        if preview.success and preview.preview_path:
            preview_url = f"/api/v1/previews/{os.path.basename(preview.preview_path)}"
        
        return {
            "success": True,
            "task_id": task_id,
            "revised_sections": sections,
            "revision_summary": result.summary,
            "agents_used": result.agents_used,
            "new_preview_url": preview_url,
            "output_path": result.output_path,
            "document_path": result.document_path,
        }
        
    except Exception as e:
        logger.error(f"revise_sections failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "error_code": "REVISION_ERROR",
        }
```

#### 3.2.3 Add API Routes

**File**: `src/api/main.py`

```python
from typing import List, Optional
from fastapi import Body

@app.get("/api/v1/research/sections/{task_id}")
async def get_sections(task_id: str):
    """Get report chapter list (for revision feature)"""
    return await research_api.get_sections(task_id)


@app.post("/api/v1/research/revise")
async def revise_sections(
    task_id: str = Body(...),
    sections: List[str] = Body(...),
    adjustment: str = Body(""),
    user_id: Optional[str] = Body(None),
):
    """Revise specified chapters"""
    return await research_api.revise_sections(
        task_id=task_id,
        sections=sections,
        adjustment=adjustment,
        user_id=user_id,
    )
```

### 3.3 Frontend Fix

#### 3.3.1 Update API Client

**File**: `web/src/lib/api.ts`

```typescript
// Add revision related interface types
interface Section {
  id: string;
  title: string;
  level: number;
  word_count: number;
}

interface SectionsResponse {
  task_id: string;
  topic: string;
  sections: Section[];
  total_sections: number;
}

interface ReviseResponse {
  success: boolean;
  task_id: string;
  revised_sections: string[];
  revision_summary?: string;
  new_preview_url?: string;
  output_path?: string;
  error?: string;
  error_code?: string;
}

class ApiClient {
  // ... existing methods ...

  /**
   * Get report chapter list
   */
  async getSections(taskId: string): Promise<SectionsResponse> {
    const { data } = await this.client.get(`/api/v1/research/sections/${taskId}`);
    return data;
  }

  /**
   * Revise specified chapters
   */
  async reviseSections(params: {
    task_id: string;
    sections: string[];
    adjustment?: string;
    user_id?: string;
  }): Promise<ReviseResponse> {
    const { data } = await this.client.post('/api/v1/research/revise', params);
    return data;
  }
}
```

#### 3.3.2 Create Revision Panel Component (Preview)

The RevisionPanel component is a new frontend dialog component that provides:
- Chapter multi-select list loaded from API
- Revision description text area
- Submit button that calls the revise API

---

## IV. Fix Verification Checklist

### 4.1 Backend Verification

| Verification Item | Verification Method | Expected Result |
|------------------|-------------------|-----------------|
| GET /sections endpoint | `curl http://localhost:8000/api/v1/research/sections/{task_id}` | Returns chapter list JSON |
| POST /revise endpoint | `curl -X POST -d '{"task_id":"xxx","sections":["Market Size"]}'` | Executes revision and returns result |
| Orchestrator.revise call | Unit test | Correctly calls and returns result |
| New preview generation | Check preview_url after revision | Returns new preview URL |

### 4.2 Frontend Verification

| Verification Item | Verification Method | Expected Result |
|------------------|-------------------|-----------------|
| Revision button display | Visit history detail page | Shows "Revise Chapter" button |
| Click opens panel | Click revision button | Displays RevisionPanel dialog |
| Chapter list loads | After opening panel | Shows chapter checkbox list |
| Multi-select chapters | Select multiple chapters | Shows selected count |
| Submit revision | Select chapters + submit | Shows revising status |
| Preview refresh | After successful revision | Preview shows new content |

---

## V. Implementation Plan

### 5.1 Effort Estimation

| Task | Estimated Time | Priority |
|------|---------------|----------|
| Backend API Integration (get_sections) | 0.5 hour | P0 |
| Backend API Integration (revise_sections) | 1 hour | P0 |
| Add API Routes | 0.5 hour | P0 |
| Frontend API Client Update | 0.5 hour | P0 |
| Create RevisionPanel Component | 1.5 hours | P0 |
| Modify History Detail Page | 0.5 hour | P0 |
| Integration Testing | 1 hour | P0 |
| **Total** | **5.5 hours** | - |

---

## VI. Conclusion

The core logic of the report revision feature (`Orchestrator.revise`) is fully implemented and available in CLI mode. Frontend mode requires the following integration work:

1. **Backend API Layer**: Add `get_sections` and `revise_sections` endpoints, connect to Orchestrator
2. **Frontend UI Layer**: Create RevisionPanel component, add revision entry button

Fix effort approximately **5.5 hours**. After fix, the following flow will be possible:

```
History Detail Page → Click "Revise Chapter" → Select Chapters → Enter Description → Start Revision → Refresh Preview
```

Enabling complete dual-end revision capability alongside CLI mode.

---

*Report Generation Time: 2026-04-30*
*Version: 2.0*
