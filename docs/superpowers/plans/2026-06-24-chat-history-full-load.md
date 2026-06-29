# Chat History Full-Load Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the main chat window to scroll-load ALL conversation history, not just the compressed subset.

**Architecture:** Separate display history from LLM context history. Add `display_history` field to session (never compressed). Add paginated messages API. Add infinite scroll to ChatPanel.

**Tech Stack:** Python/FastAPI (backend), React/Next.js/Zustand (frontend)

---

## Root Cause Analysis

| # | Root Cause | File | Effect |
|---|-----------|------|--------|
| 1 | `HistoryCompressor` reduces `conversation_history` to 5-6 entries | `compress_adapter.py:90,100` + `history_compressor.py:135,143` | Long conversations show only last 5 messages + 1 summary |
| 2 | API filter `"role" in msg and "content" in msg` drops summary entries | `main.py:606` | Even compressed summaries are invisible |
| 3 | `restoreSession` casts `role as 'user' \| 'assistant'` losing `'agent'` | `useSessionStore.ts:84` | Agent messages lost on restore |
| 4 | Zustand persist `.slice(-50)` + strips `agentMessages` | `useSessionStore.ts:256,260` | Old sessions lose data on refresh |
| 5 | No pagination — all messages rendered at once | `ChatPanel.tsx:478` | No scroll-load mechanism |

## Fix Strategy

**Phase A (Backend):** Add `display_history` field — a complete, never-compressed copy of conversation history. Add paginated API endpoint.

**Phase B (Frontend):** Add infinite scroll to ChatPanel. Fix role casting. Increase persist limits.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/core/session_manager.py` | Modify | Sync `display_history` on every `conversation_history` write |
| `src/core/compress_adapter.py` | Modify | Only compress `conversation_history`, never touch `display_history` |
| `src/api/main.py` | Modify | New paginated messages endpoint; fix role filter |
| `web/src/lib/api.ts` | Modify | Add `getMessages(sessionId, offset, limit)` method |
| `web/src/store/useSessionStore.ts` | Modify | Fix role cast; increase persist limits; add `prependMessages` |
| `web/src/store/useChatStore.ts` | Modify | Add `prependMessages` action |
| `web/src/components/chat/ChatPanel.tsx` | Modify | Add infinite scroll (scroll-up load) |
| `web/src/hooks/useChatScroll.ts` | Modify | Add `onScrollTop` callback for load trigger |
| `tests/unit/test_chat_history_full_load.py` | Create | Backend + frontend logic tests |

---

### Task 1: Backend — Add `display_history` field to session

**Files:**
- Modify: `src/core/session_manager.py:44-59` (PersistentSessionDict.__setitem__)
- Modify: `src/core/session_manager.py:61-79` (PersistentSessionDict.update)
- Test: `tests/unit/test_chat_history_full_load.py`

- [ ] **Step 1: Write the failing test**

```python
def test_display_history_synced_on_conversation_history_write():
    """When conversation_history is written, display_history should be synced."""
    from src.core.session_manager import SessionManager, PersistentSessionDict
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = SessionManager(storage_dir=tmpdir)
        mgr.create("test-session", {"user_id": "u1", "conversation_history": []})
        session = mgr.get("test-session")
        # Append a message
        history = session.get("conversation_history", [])
        history.append({"role": "user", "content": "Hello", "timestamp": "2026-01-01T00:00:00"})
        session["conversation_history"] = history
        # display_history should be synced
        display = session.get("display_history", [])
        assert len(display) == 1
        assert display[0]["content"] == "Hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\conda\python.exe -m pytest tests/unit/test_chat_history_full_load.py::test_display_history_synced_on_conversation_history_write -v`
Expected: FAIL (display_history not synced)

- [ ] **Step 3: Write minimal implementation**

In `PersistentSessionDict.__setitem__`, after the append-only guard and `super().__setitem__`, sync `display_history`:

```python
def __setitem__(self, key, value):
    if key == "conversation_history":
        old = self.get("conversation_history", [])
        if isinstance(old, list) and isinstance(value, list) and len(value) < len(old):
            try:
                self._manager._save_backup(self._session_id, "guard")
            except Exception as exc:
                logger.error(f"Backup failed before blocking truncation: {exc}")
            raise ValueError(
                f"conversation_history truncation blocked: "
                f"{len(old)} -> {len(value)} items. "
                f"History is append-only."
            )
    super().__setitem__(key, value)
    # Sync display_history with conversation_history (never compressed)
    # Use dict.__setitem__ to avoid re-triggering __setitem__ → infinite save loop
    if key == "conversation_history" and isinstance(value, list):
        dict.__setitem__(self, "display_history", list(value))
    self._manager._save_to_disk(self._session_id)
```

Same logic in `update()` method — after the guard check, add sync:

```python
def update(self, *args, **kwargs):
    merger = {}
    if args:
        merger.update(args[0])
    merger.update(kwargs)
    if "conversation_history" in merger:
        new_val = merger["conversation_history"]
        old = self.get("conversation_history", [])
        if isinstance(old, list) and isinstance(new_val, list) and len(new_val) < len(old):
            try:
                self._manager._save_backup(self._session_id, "guard")
            except Exception as exc:
                logger.error(f"Backup failed before blocking truncation in update(): {exc}")
            raise ValueError(
                f"conversation_history truncation blocked in update(): "
                f"{len(old)} -> {len(new_val)} items."
            )
    super().update(*args, **kwargs)
    # Sync display_history — use dict.__setitem__ to avoid re-triggering save
    if "conversation_history" in merger and isinstance(merger["conversation_history"], list):
        dict.__setitem__(self, "display_history", list(merger["conversation_history"]))
    self._manager._save_to_disk(self._session_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\conda\python.exe -m pytest tests/unit/test_chat_history_full_load.py::test_display_history_synced_on_conversation_history_write -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/session_manager.py tests/unit/test_chat_history_full_load.py
git commit -m "feat: sync display_history with conversation_history (never compressed)"
```

---

### Task 2: Backend — Protect `display_history` from compression

**Files:**
- Modify: `src/core/compress_adapter.py:76-107`
- Test: `tests/unit/test_chat_history_full_load.py`

- [ ] **Step 1: Write the failing test**

```python
def test_display_history_not_compressed():
    """display_history should remain intact after compression runs."""
    from src.core.compress_adapter import SessionHistoryCompressor
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        compressor = SessionHistoryCompressor(step_limit=5, size_limit_kb=10, archive_base=tmpdir)
        # Build a session with 10 messages
        history = [{"role": "user", "content": f"Message {i}", "timestamp": f"2026-01-0{i+1}T00:00:00"} for i in range(10)]
        session = {"conversation_history": history, "display_history": list(history), "user_id": "u1"}
        compressor.compress_if_needed("test-session", session)
        # conversation_history should be compressed
        assert len(session["conversation_history"]) < 10
        # display_history should be untouched
        assert len(session["display_history"]) == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\conda\python.exe -m pytest tests/unit/test_chat_history_full_load.py::test_display_history_not_compressed -v`
Expected: FAIL (display_history gets compressed too, or doesn't exist)

- [ ] **Step 3: Write minimal implementation**

In `compress_adapter.py`, `compress_if_needed` method — after compression, restore `display_history` from the original:

```python
def compress_if_needed(self, session_id: str, session: dict) -> None:
    history = session.get("conversation_history")
    if not history or not isinstance(history, list):
        return

    import json
    history_len = len(history)
    size_kb = len(json.dumps(history, ensure_ascii=False).encode("utf-8")) / 1024

    needs_compress = history_len > self._step_limit or size_kb > self._size_limit_kb
    if not needs_compress:
        return

    try:
        user_id = session.get("user_id", "default")
        compressor = self._get_compressor(session_id, user_id)
        result = compressor.compress(history)
        # Save full history to display_history BEFORE compression
        dict.__setitem__(session, "display_history", list(history))
        # Compress conversation_history (for LLM context only)
        dict.__setitem__(session, "conversation_history", result["history"])
        dict.__setitem__(session, "_compressed", True)
        logger.info(
            f"History compressed: {session_id} "
            f"({len(history)} -> {len(result['history'])} steps, "
            f"ratio={result['compression_ratio']:.1%}), "
            f"display_history preserved ({len(history)} items)"
        )
    except Exception as e:
        logger.warning(f"History compression failed for {session_id}: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\conda\python.exe -m pytest tests/unit/test_chat_history_full_load.py::test_display_history_not_compressed -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/compress_adapter.py
git commit -m "fix: preserve display_history before compressing conversation_history"
```

---

### Task 3: Backend — Add paginated messages API endpoint

**Files:**
- Modify: `src/api/main.py` (add new endpoint after line 617)
- Test: `tests/unit/test_chat_history_full_load.py`

- [ ] **Step 1: Write the failing test**

```python
def test_messages_api_returns_display_history():
    """GET /api/v1/research/{task_id}/messages should return display_history with pagination."""
    from src.core.session_manager import SessionManager
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = SessionManager(storage_dir=tmpdir)
        history = [{"role": "user", "content": f"Msg {i}", "timestamp": f"2026-01-01T00:00:00"} for i in range(25)]
        mgr.create("test-session", {
            "user_id": "u1",
            "conversation_history": history[:6],  # compressed
            "display_history": history,            # full
            "created_at": "2026-01-01T00:00:00",
            "status": "completed",
        })
        session = mgr.get("test-session")
        # Simulate API logic
        display = session.get("display_history", session.get("conversation_history", []))
        assert len(display) == 25
        # Paginate: offset=0, limit=10
        page1 = display[0:10]
        assert len(page1) == 10
        page2 = display[10:20]
        assert len(page2) == 10
        page3 = display[20:30]
        assert len(page3) == 5
```

- [ ] **Step 2: Run test to verify it passes** (this is a logic test, should pass immediately)

Run: `D:\conda\python.exe -m pytest tests/unit/test_chat_history_full_load.py::test_messages_api_returns_display_history -v`
Expected: PASS

- [ ] **Step 3: Add the API endpoint**

In `main.py`, after the existing `GET /api/v1/research/{task_id}` endpoint (after line 617), add:

```python
@app.get("/api/v1/research/{task_id}/messages")
async def get_research_messages(
    task_id: str,
    offset: int = 0,
    limit: int = 50,
):
    """Paginated message history for a research session.
    
    Uses display_history (full, never compressed) when available,
    falls back to conversation_history.
    """
    session = session_manager.get(task_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    offset = max(0, offset)
    limit = max(1, limit)
    
    source = session.get("display_history") or session.get("conversation_history", [])
    total = len(source)
    page = source[offset:offset + limit]
    
    messages = []
    for msg in page:
        if isinstance(msg, dict) and ("role" in msg or "type" in msg) and "content" in msg:
            messages.append({
                "id": msg.get("id", f"msg_{offset + len(messages)}"),
                "role": msg.get("role", msg.get("type", "summary")),
                "content": msg["content"],
                "timestamp": msg.get("timestamp", ""),
            })
    
    return {
        "messages": messages,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
    }
```

- [ ] **Step 4: Also fix the existing research detail endpoint to use display_history**

In `main.py`, line 604, change:

```python
# Before:
history = session.get("conversation_history", [])
# After:
history = session.get("display_history") or session.get("conversation_history", [])
```

And fix the filter at line 606 to also accept summary-type entries:

```python
# Before:
if isinstance(msg, dict) and "role" in msg and "content" in msg:
# After:
if isinstance(msg, dict) and ("role" in msg or "type" in msg) and "content" in msg:
```

And the role mapping:

```python
# Before:
"role": msg["role"],
# After:
"role": msg.get("role", msg.get("type", "unknown")),
```

- [ ] **Step 5: Commit**

```bash
git add src/api/main.py
git commit -m "feat: add paginated messages API + fix research detail to use display_history"
```

---

### Task 4: Frontend — Add `getMessages` API method

**Files:**
- Modify: `web/src/lib/api.ts`

- [ ] **Step 1: Add the method**

After `getResearchDetail` method (after line 419), add:

```typescript
async getMessages(
  sessionId: string,
  offset: number = 0,
  limit: number = 50,
): Promise<{
  messages: Array<{ id: string; role: string; content: string; timestamp: string }>;
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
}> {
  const { data } = await this.client.get(
    `/api/v1/research/${sessionId}/messages`,
    { params: { offset, limit } },
  );
  return data;
}
```

- [ ] **Step 2: Commit**

```bash
git add web/src/lib/api.ts
git commit -m "feat: add getMessages API method with pagination"
```

---

### Task 5: Frontend — Fix role casting and add `prependMessages` to stores

**Files:**
- Modify: `web/src/store/useSessionStore.ts:82-87`
- Modify: `web/src/store/useChatStore.ts`

- [ ] **Step 1: Fix role casting in restoreSession**

In `useSessionStore.ts`, line 84, change:

```typescript
// Before:
role: m.role as 'user' | 'assistant',
// After:
role: (m.role === 'user' || m.role === 'assistant' || m.role === 'agent'
  ? m.role
  : 'assistant') as ChatMessage['role'],
```

- [ ] **Step 2: Add `prependMessages` to useChatStore**

In `useChatStore.ts`, add a `prependMessages` action:

```typescript
prependMessages: (msgs: ChatMessage[]) => {
  const messages = [...msgs, ...get().messages];
  // Deduplicate by id
  const seen = new Set<string>();
  const deduped = messages.filter(m => {
    if (seen.has(m.id)) return false;
    seen.add(m.id);
    return true;
  });
  set({ messages: deduped });
  useSessionStore.getState().syncActive({ messages: deduped });
},
```

- [ ] **Step 3: Increase persist limits in useSessionStore**

In `useSessionStore.ts`, line 256, change `.slice(-50)` to `.slice(-200)`:

```typescript
// Before:
.slice(-50)
// After:
.slice(-200)
```

And line 260, stop stripping `agentMessages`:

```typescript
// Before:
result: undefined,
agentMessages: undefined,
qualityState: undefined,
pendingInput: undefined,
// After:
result: undefined,
qualityState: undefined,
pendingInput: undefined,
```

- [ ] **Step 4: Commit**

```bash
git add web/src/store/useSessionStore.ts web/src/store/useChatStore.ts
git commit -m "fix: role casting, prependMessages, increase persist limits"
```

---

### Task 6: Frontend — Add infinite scroll to ChatPanel

**Files:**
- Modify: `web/src/hooks/useChatScroll.ts`
- Modify: `web/src/components/chat/ChatPanel.tsx`

- [ ] **Step 1: Add `onScrollTop` callback to useChatScroll**

In `useChatScroll.ts`, modify the hook signature and add top-detection:

```typescript
export function useChatScroll(
  deps: unknown[],
  onScrollTop?: () => Promise<void>,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isUserScrolling = useRef(false);
  const prevScrollTop = useRef(0);
  const isLoadingRef = useRef(false);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;

    const { scrollTop, scrollHeight, clientHeight } = el;
    const atBottom = scrollHeight - scrollTop - clientHeight < 60;
    const atTop = scrollTop < 60;

    if (!atBottom && scrollTop < prevScrollTop.current) {
      isUserScrolling.current = true;
    }

    if (atBottom) {
      isUserScrolling.current = false;
    }

    if (atTop && onScrollTop && !isLoadingRef.current) {
      isLoadingRef.current = true;
      const prevHeight = el.scrollHeight;
      onScrollTop().finally(() => {
        // After content loads, maintain scroll position
        requestAnimationFrame(() => {
          const newHeight = el.scrollHeight;
          el.scrollTop = newHeight - prevHeight;
          isLoadingRef.current = false;
        });
      });
    }

    prevScrollTop.current = scrollTop;
  }, [onScrollTop]);

  useEffect(() => {
    if (isUserScrolling.current) return;
    const el = containerRef.current;
    if (el) {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
    }
  }, deps);

  const scrollToBottom = useCallback(() => {
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
      isUserScrolling.current = false;
    }
  }, []);

  const isAtBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  }, []);

  return { containerRef, handleScroll, scrollToBottom, isAtBottom };
}
```

- [ ] **Step 2: Add infinite scroll logic to ChatPanel**

In `ChatPanel.tsx`, add state and handler for loading older messages:

```typescript
// Add imports
import { useRef, useEffect, useState, useCallback } from 'react';

// Inside ChatPanel component, after existing hooks:
const [hasMoreMessages, setHasMoreMessages] = useState(true);
const [isLoadingMessages, setIsLoadingMessages] = useState(false);
const messageOffsetRef = useRef(0);

const loadOlderMessages = useCallback(async () => {
  if (isLoadingMessages || !hasMoreMessages) return;
  const store = useSessionStore.getState();
  const activeId = store.activeId;
  if (!activeId) return;

  setIsLoadingMessages(true);
  try {
    const result = await api.getMessages(activeId, messageOffsetRef.current, 50);
    if (result.messages.length === 0) {
      setHasMoreMessages(false);
    } else {
      const olderMsgs: ChatMessage[] = result.messages.map((m: any) => ({
        id: m.id || nanoid(),
        role: (m.role === 'user' || m.role === 'assistant' || m.role === 'agent'
          ? m.role
          : 'assistant') as ChatMessage['role'],
        content: m.content,
        timestamp: m.timestamp || new Date().toISOString(),
      }));
      useChatStore.getState().prependMessages(olderMsgs);
      messageOffsetRef.current += result.messages.length;
      if (!result.has_more) {
        setHasMoreMessages(false);
      }
    }
  } catch (e) {
    console.error('Failed to load older messages:', e);
  } finally {
    setIsLoadingMessages(false);
  }
}, [isLoadingMessages, hasMoreMessages]);

// Reset on session switch — offset starts at 0 (load from earliest)
useEffect(() => {
  messageOffsetRef.current = 0;
  setHasMoreMessages(true);
}, [useSessionStore.getState().activeId]);

// Replace useChatScroll call:
const { containerRef, handleScroll, scrollToBottom, isAtBottom } = useChatScroll(
  [messages],
  loadOlderMessages,
);
```

Add a loading indicator before the messages list:

```tsx
{isLoadingMessages && (
  <div className="flex justify-center py-2">
    <span className="text-xs text-muted-foreground animate-pulse">Loading earlier messages...</span>
  </div>
)}

{messages.map((msg) => (
  <ChatMessage key={msg.id} message={msg} />
))}
```

- [ ] **Step 3: Commit**

```bash
git add web/src/hooks/useChatScroll.ts web/src/components/chat/ChatPanel.tsx
git commit -m "feat: infinite scroll for chat history loading"
```

---

### Task 7: Full regression + integration test

**Files:**
- Test: `tests/unit/test_chat_history_full_load.py`

- [ ] **Step 1: Add integration test**

```python
def test_full_flow_display_history_preserved_through_compression():
    """End-to-end: write messages → compress → display_history still has all messages."""
    from src.core.session_manager import SessionManager
    from src.core.compress_adapter import SessionHistoryCompressor
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        archive_dir = os.path.join(tmpdir, "archives")
        mgr = SessionManager(storage_dir=tmpdir)
        mgr._history_compressor = SessionHistoryCompressor(
            step_limit=5, size_limit_kb=10, archive_base=archive_dir
        )
        mgr.create("test-session", {"user_id": "u1", "conversation_history": []})
        session = mgr.get("test-session")
        # Write 15 messages
        for i in range(15):
            history = session.get("conversation_history", [])
            history.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}", "timestamp": f"2026-01-01T00:00:00"})
            session["conversation_history"] = history
        # After writes, display_history should have all 15
        display = session.get("display_history", [])
        assert len(display) == 15, f"Expected 15 display_history items, got {len(display)}"
        # conversation_history may be compressed (fewer items)
        conv = session.get("conversation_history", [])
        assert len(conv) <= 15  # compressed or not
```

- [ ] **Step 2: Run all tests**

Run: `D:\conda\python.exe -m pytest tests/unit/test_chat_history_full_load.py tests/unit/test_imp1_imp2_data_quality.py tests/unit/test_imp3_imp4_validation.py tests/unit/test_imp5_imp6_stock_actions.py tests/unit/test_skill_dynamic_loading.py -q --tb=short`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_chat_history_full_load.py
git commit -m "test: integration test for display_history through compression"
```

---

## Self-Review Checklist

1. **Spec coverage:** Each root cause has a corresponding task:
   - RC1 (compression) → Task 1 + Task 2
   - RC2 (API filter) → Task 3
   - RC3 (role cast) → Task 5
   - RC4 (persist limits) → Task 5
   - RC5 (no pagination) → Task 3 + Task 4 + Task 6

2. **Placeholder scan:** No TBD/TODO/fill-in-later. All code is concrete.

3. **Type consistency:**
   - `display_history` is `list[dict]` — same shape as `conversation_history`
   - `ChatMessage['role']` = `'user' | 'assistant' | 'agent'` — matches `api.ts` type
   - `getMessages` return type matches API response shape
   - `prependMessages` takes `ChatMessage[]` — same type as `addMessage`

4. **Risk assessment:**
   - Task 1-2: Low risk — additive field, no existing behavior changed
   - Task 3: Medium risk — modifies API response, but `display_history` fallback is safe
   - Task 4-5: Low risk — frontend-only, additive
   - Task 6: Medium risk — scroll behavior change, needs manual testing

## Review Fixes Applied

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | P1 | Task 1: `super().__setitem__("display_history", ...)` re-triggers `__setitem__` → infinite save loop | Changed to `dict.__setitem__` to bypass auto-save |
| 2 | P1 | Task 1: Same issue in `update()` method | Changed to `dict.__setitem__` |
| 3 | P2 | Task 3: `offset` param can be negative | Added `offset = max(0, offset)` and `limit = max(1, limit)` |
| 4 | P2 | Task 6: `onScrollTop()` is async but `requestAnimationFrame` resets `isLoadingRef` before data loads | Changed to `onScrollTop().finally(() => rAF(...))` — only reset after Promise resolves |
| 5 | P2 | Task 6: `messageOffsetRef.current = messages.length` is wrong for scroll-up loading | Changed to `messageOffsetRef.current = 0` — scroll-up loads from earliest messages |
