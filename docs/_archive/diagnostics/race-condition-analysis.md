# HIGH-03: _background_tasks Race Condition Deep Analysis and Fix Plan

## Part 1: Problem Overview

**Location**: `src/api/research_api.py:208-210`  
**Severity**: HIGH  
**Type**: Async race condition (TOCTOU)

`ResearchAPI` uses two class-level dictionaries to track background asyncio Tasks:
- `_background_tasks: Dict[str, Any]` — session_id -> asyncio.Task
- `_background_task_gen: Dict[str, int]` — session_id -> generation counter

---

## Part 2: Related Code Paths

### 2.1 Creating Background Tasks (lines 575-593)
```python
# Cancel old same-session background task
self._cancel_existing_task(session_id)

# Generation counter: ensure finally cleanup doesn't mistakenly delete new task
gen = self._background_task_gen.get(session_id, 0) + 1
self._background_task_gen[session_id] = gen

task = asyncio.create_task(
    self._do_execute_tool_background(
        session_id=session_id, generation=gen, ...
    )
)
self._background_tasks[session_id] = task
```

### 2.2 Canceling Old Task (lines 611-618)
```python
def _cancel_existing_task(self, session_id: str):
    old_task = self._background_tasks.get(session_id)
    if old_task and not old_task.done():
        old_task.cancel()
    self._background_tasks.pop(session_id, None)
    self._background_task_gen.pop(session_id, None)    # <- Problem on this line
```

### 2.3 Background Task Cleanup (lines 746-750)
```python
finally:
    if self._background_task_gen.get(session_id) == generation:
        self._background_tasks.pop(session_id, None)
        self._background_task_gen.pop(session_id, None)
```

---

## Part 3: Race Condition Scenario Analysis

### Normal Flow (Single Request)
```
R1: cancel_existing_task -> pop gen=0, tasks={}
R1: gen = 0 + 1 = 1, _background_task_gen["foo"] = 1
R1: TaskA created (generation=1), _background_tasks["foo"] = TaskA
... TaskA completes ...
TaskA finally: _background_task_gen["foo"] == 1? -> yes -> pop tasks, pop gen
```

### Race Condition (Consecutive Requests)
```
R1: TaskA created (generation=1), _background_tasks["foo"] = TaskA
[TaskA executing, awaiting LLM call]

R2 arrives (user sent second message):
R2: _cancel_existing_task("foo")
  -> _background_tasks.pop("foo") -> returns TaskA
  -> TaskA.cancel()               -> schedules CancelledError
  -> _background_task_gen.pop("foo")  -> gen removed
R2: gen = _background_task_gen.get("foo", 0) + 1 = 0 + 1 = 1
R2: _background_task_gen["foo"] = 1
R2: TaskB created (generation=1), _background_tasks["foo"] = TaskB

[TaskA's CancelledError handled at next await]
TaskA except CancelledError: logging, SSE push
TaskA finally:
  -> _background_task_gen.get("foo") == 1? -> YES! (gen=1 == TaskA.generation=1)
  -> _background_tasks.pop("foo")    -> DELETES TaskB!
  -> _background_task_gen.pop("foo") -> gen removed again

[TaskB completes next]
TaskB finally:
  -> _background_task_gen.get("foo") -> None (removed by TaskA's finally)
  -> None == 1? -> False -> no cleanup
  -> _background_tasks "foo" already gone
  -> TaskB reference leak, next cancel can't find it
```

### Consequences
1. TaskB mistakenly deleted by TaskA's finally, lost from `_background_tasks`
2. If R3 arrives, `_cancel_existing_task("foo")` can't find TaskB (already deleted)
3. TaskB continues running (not cancelled), R3 creates TaskC
4. TaskB and TaskC both run in background, producing overlapping SSE pushes

---

## Part 4: Root Cause

`_cancel_existing_task` removes the generation counter from `_background_task_gen` when canceling the old task. This causes the new task's generation to restart from 0, potentially matching the old task's generation (both being 1), breaking the anti-mistaken-deletion mechanism in the finally block.

**Core Problem**: The generation counter should strictly monotonically increase to ensure uniqueness, but it gets reset in `_cancel_existing_task`.

---

## Part 5: Fix Plan

### 5.1 Core Fix (Minimal Change)

```diff
 def _cancel_existing_task(self, session_id: str):
     old_task = self._background_tasks.get(session_id)
     if old_task and not old_task.done():
         old_task.cancel()
         logger.info(f"Cancelled existing background task for {session_id}")
     self._background_tasks.pop(session_id, None)
-    self._background_task_gen.pop(session_id, None)
```

**Principle**: 
- Keep gen counter not reset, new task inevitably gets `gen = old_gen + 1`
- TaskA (gen=1) -> cancel -> don't remove gen -> TaskB (gen=1+1=2)
- TaskA finally: `_background_task_gen["foo"] (==2) == 1?` -> **false** -> skip cleanup
- TaskB finally: `_background_task_gen["foo"] (==2) == 2?` -> **true** -> normal cleanup

### 5.2 Final Code

```python
def _cancel_existing_task(self, session_id: str):
    """Cancel old background task for the same session"""
    old_task = self._background_tasks.pop(session_id, None)
    if old_task and not old_task.done():
        old_task.cancel()
        logger.info(f"Cancelled existing background task for {session_id}")
```

### 5.3 Verification Method

```python
async def test_concurrent_cancel_does_not_orphan_new_task():
    api = ResearchAPI(orchestrator=MockOrchestrator())
    session_id = "test_session"

    # Simulate first request
    await api.execute_tool_async(session_id, {...})  # gen=1, TaskA

    # Verify TaskA registered
    assert session_id in ResearchAPI._background_tasks
    old_gen = ResearchAPI._background_task_gen.get(session_id)
    assert old_gen == 1

    # Simulate second request (triggers cancel + creates new task)
    await api.execute_tool_async(session_id, {...})  # cancel TaskA, gen should be 2

    # Verify new gen = old_gen + 1
    new_gen = ResearchAPI._background_task_gen.get(session_id)
    assert new_gen == old_gen + 1

    # Verify TaskA's finally doesn't delete TaskB
    assert ResearchAPI._background_task_gen.get(session_id) != 1  # TaskA's gen shouldn't match
    assert ResearchAPI._background_task_gen.get(session_id) == 2  # Only TaskB's gen matches
```

---

## Part 6: Summary

**One line deletion** of `self._background_task_gen.pop(session_id, None)` eliminates this race condition. The generation counter must strictly monotonically increase; any reset destroys its uniqueness guarantee. This fix does not involve locks, does not change async/sync boundaries, and does not affect existing functional flows.
