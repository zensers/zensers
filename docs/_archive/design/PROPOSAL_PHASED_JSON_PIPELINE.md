# Layered Agent Data Persistence Plan

> **Plan Type**: Enhancement of Existing PhaseOrchestrator
> **Created**: 2026-04-21
> **Status**: Pending Approval

---

## 1. Problem Background

### 1.1 Current Architecture

The system uses a 5-phase analysis framework:

```
DATA_COLLECTION → DATA_VALIDATION → DEEP_ANALYSIS → SYNTHESIS → REPORT_GENERATION
```

**Key Components**:
- `PhaseOrchestrator` (src/core/analysis/phase_orchestrator.py) - Phase orchestrator
- `SharedMemory` (src/core/communication.py) - In-memory storage
- `ResearchResultStore` (src/core/storage/research_result_store.py) - Research result storage

### 1.2 Core Issues

| Issue | Description | Impact |
|------|------|------|
| **Memory Storage** | SharedMemory is an in-memory dict, not persisted | Data lost on crash |
| **Aspect Loss** | Aspect association lost after parallel execution merge | Analysis Agents cannot get corresponding data |
| **Storage Not Integrated** | ResearchResultStore not called during Agent execution | Phase results not saved |

### 1.3 Problem Code Location

```python
# phase_orchestrator.py:1351-1354
def _store_phase_output(self, phase: AnalysisPhase, output: Dict[str, Any]) -> None:
    if self._shared_memory:
        self._shared_memory.set(f"phase_output.{phase.value}", output)  # Memory only!

# phase_orchestrator.py:584-641
def _merge_phase_results(self, phase: AnalysisPhase, results: List[PhaseExecutionResult]):
    # Aspect information lost after merge
    all_data_points = []
    for output in successful_outputs:
        all_data_points.extend(output.get("data_points", []))  # Aspect info lost!
```

---

## 2. Solution Design

### 2.1 Architecture

```
                  PhaseOrchestrator
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   PhaseOutput      AspectOutput    SharedMemory
   Storage          Tracker         (compatible)
        │               │               │
        └───────────────┼───────────────┘
                        │
               ┌────────┴────────┐
               │                 │
        ResearchResult     TaskPersistence
        Store              Manager
```

### 2.2 Data Model

```python
@dataclass
class PhaseOutput:
    """Phase execution output data model"""
    phase: AnalysisPhase
    session_id: str
    aspect_map: Dict[str, List[DataPoint]]  # aspect → data points
    metadata: Dict[str, Any]
    created_at: float

    def to_dict(self) -> Dict:
        return {
            "phase": self.phase.value,
            "session_id": self.session_id,
            "aspect_map": {k: [dp.to_dict() for dp in v] for k, v in self.aspect_map.items()},
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "PhaseOutput":
        return cls(
            phase=AnalysisPhase(data["phase"]),
            session_id=data["session_id"],
            aspect_map={k: [DataPoint.from_dict(dp) for dp in v] for k, v in data["aspect_map"].items()},
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
        )
```

### 2.3 Storage Layer

```python
class PhaseOutputStore:
    """Phase output storage - persisted to disk"""

    def __init__(self, base_dir: str = "data/phase_outputs"):
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, output: PhaseOutput) -> str:
        path = self._base_dir / f"{output.session_id}_{output.phase.value}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output.to_dict(), f, ensure_ascii=False, indent=2)
        return str(path)

    def load(self, session_id: str, phase: AnalysisPhase) -> Optional[PhaseOutput]:
        path = self._base_dir / f"{session_id}_{phase.value}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return PhaseOutput.from_dict(json.load(f))
```

### 2.4 Aspect Tracker

```python
class AspectTracker:
    """Track data point → aspect association"""

    def __init__(self):
        self._aspect_registry: Dict[str, List[str]] = {}  # aspect → data_point_ids

    def register(self, aspect: str, data_points: List[DataPoint]) -> None:
        if aspect not in self._aspect_registry:
            self._aspect_registry[aspect] = []
        for dp in data_points:
            if dp.id not in self._aspect_registry[aspect]:
                self._aspect_registry[aspect].append(dp.id)

    def get_data_points(self, aspect: str) -> List[str]:
        return self._aspect_registry.get(aspect, [])

    def get_all_aspects(self) -> List[str]:
        return list(self._aspect_registry.keys())

    def to_dict(self) -> Dict:
        return self._aspect_registry

    @classmethod
    def from_dict(cls, data: Dict) -> "AspectTracker":
        tracker = cls()
        tracker._aspect_registry = data
        return tracker
```

---

## 3. PhaseOrchestrator Changes

### 3.1 Store Phase Output

```python
# In phase_orchestrator.py, modify _store_phase_output:
def _store_phase_output(self, phase: AnalysisPhase, output: Dict[str, Any]) -> None:
    phase_output = PhaseOutput(
        phase=phase,
        session_id=self._session_id,
        aspect_map=output.get("aspect_map", {}),
        metadata={"agent_count": len(output.get("agents", [])), "timestamp": time.time()},
        created_at=time.time(),
    )
    # Persist to disk
    self._phase_store.save(phase_output)
    # Keep backward compatibility with SharedMemory
    if self._shared_memory:
        self._shared_memory.set(f"phase_output.{phase.value}", phase_output.to_dict())
```

### 3.2 Track Aspect in Merge

```python
# In _merge_phase_results, add aspect tracking:
def _merge_phase_results(self, phase: AnalysisPhase, results: List[PhaseExecutionResult]):
    aspect_tracker = AspectTracker()

    for output in successful_outputs:
        aspect = output.get("aspect", "general")
        data_points = output.get("data_points", [])
        aspect_tracker.register(aspect, data_points)

    # Store aspect tracking
    self._aspect_tracker = aspect_tracker

    # Log aspect coverage
    logger.info(f"Phase {phase.value}: tracked {len(aspect_tracker.get_all_aspects())} aspects")
```

---

## 4. Data Flow

```
PhaseOrchestrator.execute_phase(phase)
  │
  ├─ Create phase agents (by aspect)
  │
  ├─ Execute each agent
  │    └─ agent.execute() → Dict with data_points + aspect
  │
  ├─ _merge_phase_results()
  │    ├─ AspectTracker: track aspect → data_point mapping
  │    └─ Merge data points
  │
  ├─ _store_phase_output()
  │    ├─ PhaseOutputStore: persist to disk
  │    └─ SharedMemory: backward compatibility
  │
  └─ Return PhaseExecutionResult

Next phase:
  └─ Load previous phase output from PhaseOutputStore
       └─ Reconstruct aspect → data_points mapping
            └─ Distribute to appropriate Agents
```

---

## 5. Compatibility Notes

### 5.1 Backward Compatibility

| Original Method | New Method | Period |
|-----------------|------------|--------|
| `SharedMemory.get("phase_output.X")` | `PhaseOutputStore.load(session_id, phase_X)` | Keep both |
| `SharedMemory.set("phase_output.X")` | `PhaseOutputStore.save(phase_output)` | Keep both |

During transition, both SharedMemory and PhaseOutputStore coexist. The orchestrator writes to both and reads from SharedMemory first (with PhaseOutputStore as fallback).

### 5.2 PhaseOutput to_dict() Field Mapping

| PhaseOutput Field | SharedMemory Key | Notes |
|-------------------|-----------------|-------|
| phase | phase_output.phase.value | Auto-set by orchestrator |
| session_id | N/A | New field for persistence |
| aspect_map | implicit in data_points | New field, explicit tracking |
| metadata | N/A | New field for debugging |

---

## 6. Implementation Plan

| Step | Content | File | Effort |
|------|---------|------|--------|
| 1 | Add PhaseOutput dataclass | src/core/analysis/phase_output.py | 1h |
| 2 | Add AspectTracker | src/core/analysis/aspect_tracker.py | 1h |
| 3 | Implement PhaseOutputStore | src/core/storage/phase_output_store.py | 2h |
| 4 | Modify PhaseOrchestrator._store_phase_output | src/core/analysis/phase_orchestrator.py | 1h |
| 5 | Modify PhaseOrchestrator._merge_phase_results | src/core/analysis/phase_orchestrator.py | 1h |
| 6 | Update read logic in downstream Agents | src/core/agents/generic_agent.py | 2h |
| 7 | Unit tests | tests/ | 2h |

Total: ~10 hours
