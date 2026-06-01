# Memory System Integration Plan

> **Version**: v1.1  
> **Status**: Implementation Complete  
> **Implementation Date**: 2026-05-05  
> **Goal**: Integrate the `src/core/memory/` module into runtime, making the memory system truly functional

---

## 1. Current Status Diagnosis

### 1.1 Actually Running System

```
User Request -> ResearchAPI -> ResearchOrchestrator -> ExecutionEngine -> StorageManager
                ↓
       PersistentSessionDict (JSON file)
```

The current system only has **one `SessionManager` doing persistence** — it's just a `dict` with auto-save, writing to `data/sessions/{id}.json`. No memory system is involved.

### 1.2 Isolated Modules

| Module | Lines | Design Purpose | Current Status |
|--------|-------|----------------|----------------|
| `UserKnowledgeBank` | 1033 | Three-layer knowledge storage (Entity/Relation/DataPoint/Insight) | CLI tool only |
| `CoreMemory` | 592 | Layer 1 core memory (<10KB, promotion + pruning) | Test only |
| `KnowledgeManager` | 423 | Unified entry point (wraps KnowledgeBank + CoreMemory) | Never instantiated |
| `DreamMode` | 535 | Background 6-phase integration (dedup/promotion/pruning/archival) | Test Mock only |
| `HistoryCompressor` | 367 | History differential compression (recent complete -> summary -> gzip) | Not imported |
| `RollingSummarizer` | 325 | Summary generation (key point extraction) | HistoryCompressor internal only |
| `ContradictionDetector` | 625 | Numeric/relation/time contradiction detection | Test only |
| `LearningManager` | 305 | Learning promotion (recurrence_count>=3 + cross-session>=2) | Test only |
| `TokenBudgetManager` | 574 | Token budget monitoring + auto-compression trigger | Test only |
| `SessionManager (memory)` | 811 | Multi-session management + step-based snapshots | Test only |

### 1.3 Key Findings

1. **Orchestrator already calls `KnowledgeCompiler.compile()`** (line 830), but the compilation results (`knowledge_pages`) are **never stored** — `store()` is never called because there's no `UserKnowledgeBank` instance
2. **`KnowledgeCompiler.store()`** method already implements entity/data point/insight storage logic, just needs a `knowledge_bank` parameter
3. **Orchestrator's constructor receives `knowledge_compiler` parameter**, but the interface doesn't accept `knowledge_bank` or `KnowledgeManager`
4. **`container.py`'s DI container** already has complete registration/resolution capability, but zero memory components are registered
5. **`KnowledgeManager.deposit()`** already wraps the complete "record research -> knowledge compilation -> contradiction detection" flow
6. **`KnowledgeManager.run_dream_mode()`** already wraps DreamMode's 6-phase integration
7. **Data paths are consistent**: All components default to using `data/` as root

---

## 2. Overall Architecture

### 2.1 Post-Integration Data Flow

```
User Request -> ResearchAPI -> ResearchOrchestrator -> ExecutionEngine
                                                      ↓
                                               ResultAggregator
                                                      ↓
                                            KnowledgeCompiler.compile()
                                                      ↓  <- NEW
                                            KnowledgeManager.deposit()
                                              ├─ research_history (SQLite)
                                              ├─ entities/relations/insights
                                              ├─ knowledge_compilation
                                              └─ contradiction_detection
                                                      ↓  <- NEW (session end hook)
                                            KnowledgeManager.run_dream_mode()
                                              ├─ Phase 1-6 integration
                                              ├─ CoreMemory promotion
                                              └─ pruning/archival
```

### 2.2 Layer Dependencies

```
┌─────────────────────────────────────────────────────────┐
│                   ResearchOrchestrator                    │
│  (receives KnowledgeManager injection, not internal creation)               │
├─────────────────────────────────────────────────────────┤
│  KnowledgeManager (unified entry, created by container)          │
├─────────────────────┬───────────────────┬───────────────┤
│  UserKnowledgeBank  │  CoreMemory       │  DreamMode    │
│  (SQLite storage)   │  (Layer 1 file)   │  (background integration)   │
├─────────┬───────────┼───────────────────┼───────────────┤
│ Entity  │ DataPoint │ HistoryCompressor │ LearningMgr   │
│ Relation│ Insight   │ RollingSummarizer │ Contradiction │
└─────────┴───────────┴───────────────────┴───────────────┘
```

[Remaining content: Integration steps Phase 1-4, Risk assessment, Acceptance criteria]
