# HIGH-05: asyncio.get_event_loop() Deprecation Deep Analysis

## Part 1: Problem Background

### Python Version Evolution
- Python 3.8: First marked with `DeprecationWarning`
- Python 3.10: Upgraded to `PendingDeprecationWarning`
- Python 3.12+: Upgraded to `DeprecationWarning`, some scenarios start erroring
- Project locked at `pythonVersion = "3.10"` (`pyrightconfig.json`), **no runtime error currently**

### Alternative API
| Plan | Applicable Scenario | Description |
|------|--------------------|-------------|
| `asyncio.get_running_loop()` | Has a running event loop | Recommended, no side effects, raises `RuntimeError` if no loop running |
| `asyncio.run()` | No running loop | Auto-creates/closes new loop, recommended since Python 3.7+ |
| `time.time()` | Only need timestamp | Replaces `get_event_loop().time()` |

---

## Part 2: Full Scan Results

13 `get_event_loop()` calls, distributed across 7 files, zero test files.

| # | File | Line | Pattern | Risk | Fix Difficulty |
|---|------|------|---------|------|---------------|
| 1 | `research_api.py` | 1792 | `run_in_executor` in async method | Low | 1-line replacement |
| 2 | `knowledge_manager.py` | 376 | `await run_in_executor` in async method | Low | 1-line replacement |
| 3 | `orchestrator.py` | 703 | `await run_in_executor` in async method | Low | 1-line replacement |
| 4-8 | `task_persistence.py` | 770,799,831,866,898 | 5x `await run_in_executor` in same class | Low | 5 replacements, same file same pattern |
| 9 | `communication.py` | 88 | `run_in_executor` in async method | Low | 1-line replacement |
| 10 | `preview_revision_workflow.py` | 441 | `await run_in_executor` in async method | Low | 1-line replacement |
| 11 | `semantic_intent.py` | 158 | `get_event_loop` + `is_running()` branch | **Medium** | Needs branch logic refactoring |
| 12 | `mcp/client.py` | 299 | `get_event_loop` + `is_running()` branch | **Medium** | Needs branch logic refactoring |
| 13 | `communication.py` | 20 | `get_event_loop().time()` in `__post_init__` | Low | Replace with `time.time()` |

**Summary**: 11 low-risk + 2 medium-risk.

---

## Part 3: Per-Location Analysis

### 3.1 Low-Risk Group (11 locations — Direct Replacement)

#### Pattern A: `get_event_loop()` + `run_in_executor` inside async function

**Involved**: #1 (research_api.py), #2 (knowledge_manager.py), #3 (orchestrator.py), #4-8 (task_persistence.py 5 locations), #9 (communication.py), #10 (preview_revision_workflow.py)

**Current Code** (orchestrator.py:703 as example):
```python
loop = asyncio.get_event_loop()
relevant = await loop.run_in_executor(
    None, self._knowledge_manager.search, requirement.topic, {"limit": 10}
)
```

**Fix**:
```python
loop = asyncio.get_running_loop()
relevant = await loop.run_in_executor(
    None, self._knowledge_manager.search, requirement.topic, {"limit": 10}
)
```

**Safety Basis**:
- All 9 locations are inside `async def` method bodies
- `get_running_loop()` will always succeed in async methods (unless in a closed loop, which indicates a larger problem)
- Behaviorally equivalent: returns the same loop object

**Special Note — research_api.py:1792**:
```python
loop = asyncio.get_event_loop()
def _run_dream():
    import asyncio as _asyncio
    try:
        _asyncio.run(self._knowledge_manager.run_dream_mode(trigger="session_end"))
    finally:
        self._dream_mode_running = False
loop.run_in_executor(None, _run_dream)
```

Here `run_in_executor` result is not `await`ed (fire-and-forget), but it's still in an async method. Replacing with `get_running_loop()` does not affect this behavior.

#### Pattern B: `get_event_loop().time()` inside dataclass `__post_init__`

**Involved**: #13 (communication.py:20)

**Current Code**:
```python
def __post_init__(self):
    if self.timestamp is None:
        self.timestamp = asyncio.get_event_loop().time()
```

**Fix**:
```python
import time

def __post_init__(self):
    if self.timestamp is None:
        self.timestamp = time.time()
```

**Safety Basis**:
- `Event` might be created in both async and non-async contexts
- `time.time()` is always available, behavior equivalent to `loop.time()` (both are monotonic time)
- `loop.time()` returns the loop's internal clock (relative to loop start), not system time. But `Event.timestamp` value is only used for sorting and timestamp recording, doesn't depend on absolute time precision.
- In fact, `time.time()` is more suitable as a general-purpose timestamp

---

### 3.2 Medium-Risk Group (2 locations — needs branch logic refactoring)

#### Pattern C1: semantic_intent.py:158

**Current Code**:
```python
def analyze(self, user_request, requirement=None):
    """Synchronously analyze user intent."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                return executor.submit(asyncio.run, self.analyze_async(...)).result()
        return loop.run_until_complete(self.analyze_async(...))
    except RuntimeError:
        return asyncio.run(self.analyze_async(...))
```

**Fix**:
```python
def analyze(self, user_request, requirement=None):
    try:
        loop = asyncio.get_running_loop()
        # Has running loop -> execute in another thread using asyncio.run
        with concurrent.futures.ThreadPoolExecutor(1) as executor:
            return executor.submit(asyncio.run, self.analyze_async(user_request, requirement)).result()
    except RuntimeError:
        # No running loop -> directly asyncio.run
        return asyncio.run(self.analyze_async(user_request, requirement))
```

#### Pattern C2: mcp/client.py:299

**Current Code**:
```python
def disconnect(self) -> None:
    with self._lock:
        if self._state == ClientState.DISCONNECTED:
            return
        self._state = ClientState.DISCONNECTED

    if self._http_session:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._http_session.close())
            else:
                loop.run_until_complete(self._http_session.close())
        except Exception:
            pass
        self._http_session = None
```

**Fix**:
```python
def disconnect(self) -> None:
    with self._lock:
        if self._state == ClientState.DISCONNECTED:
            return
        self._state = ClientState.DISCONNECTED

    if self._http_session:
        import asyncio
        try:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._http_session.close())
            except RuntimeError:
                asyncio.run(self._http_session.close())
        except Exception:
            pass
        self._http_session = None
```

---

## Part 4: Regression Risk Matrix

### 4.1 Per-Location Risk Assessment

| # | File | Change | Test Coverage | Regression Risk | Description |
|---|------|--------|---------------|-----------------|-------------|
| 1 | research_api.py | `get_event_loop` -> `get_running_loop` | Low | **Low** | Inside async method, will succeed |
| 2 | knowledge_manager.py | Same | Has unit tests | **Low** | Inside async method |
| 3 | orchestrator.py | Same | Has integration tests | **Low** | Inside async method |
| 4-8 | task_persistence.py | Same x5 | Has unit tests | **Low** | Inside async method, same pattern |
| 9 | communication.py | Same | No direct tests | **Low** | Inside async method |
| 10 | preview_revision_workflow.py | Same | Has workflow tests | **Low** | Inside async method |
| 11 | semantic_intent.py | Refactor branch | Has semantic intent tests | **Medium** | Need to verify 3 scenarios |
| 12 | mcp/client.py | Refactor branch | Has MCP tests | **Medium** | Need to verify 2 scenarios |
| 13 | communication.py | `loop.time()` -> `time.time()` | No direct tests | **Low** | Only timestamp change |

---

## Part 5: Phased Fix Recommendations

### Phase 1 — Immediate Fix (Low Risk, 11 locations)
Batch replace `get_event_loop()` -> `get_running_loop()` in async contexts:

| File | Change | Estimated Time |
|------|--------|----------------|
| `src/core/task_persistence.py` | 5 replacements | 2 minutes |
| `src/core/communication.py:88` | 1 replacement | 30 seconds |
| `src/api/research_api.py:1792` | 1 replacement | 30 seconds |
| `src/core/memory/knowledge_manager.py:376` | 1 replacement | 30 seconds |
| `src/core/orchestrator/orchestrator.py:703` | 1 replacement | 30 seconds |
| `src/core/workflow/preview_revision_workflow.py:441` | 1 replacement | 30 seconds |
| `src/core/communication.py:20` | `loop.time()` -> `time.time()` | 30 seconds |

**Verification**: Run `pytest tests/unit/` to ensure no regression.

### Phase 2 — Planned Fix (Medium Risk, 2 locations)
Refactor branch logic:

| File | Change | Estimated Time |
|------|--------|----------------|
| `src/core/semantic_intent.py:158` | Refactor 3->2 branches | 10 minutes + test writing |
| `src/core/mcp/client.py:299` | Refactor 2 branches | 10 minutes + test writing |

**Verification**: 
- `semantic_intent.py`: Manually test sync/async two calling methods
- `mcp/client.py`: Write tests for the two scenarios described above

---

## Part 6: Impact of Not Changing

| Python Version | Impact |
|----------------|--------|
| 3.10 (project locked) | None, only `PendingDeprecationWarning` |
| 3.12 | Shows `DeprecationWarning`, does not affect operation |
| 3.14+ | May remove API, causing runtime errors |

**Conclusion**: Short-term (1-2 years) does not affect normal system operation, but creates technical debt.

---

## Part 7: Final Recommendation

```
Fix timing:      Current iteration
Risk level:      Overall LOW-MEDIUM
Change scope:    8 files, 13 locations
Recommended strategy: Batch fix (Phase 1 immediately, Phase 2 within this iteration)
```

11 low-risk items can be safely batch replaced (100% equivalent using `get_running_loop()` inside async methods).
2 medium-risk items require branch logic adjustments, but clear replacement patterns exist, and no errors will occur under the current Python 3.10 environment. Can prioritize the lower complexity `mcp/client.py:299` first, then handle `semantic_intent.py:158`.
