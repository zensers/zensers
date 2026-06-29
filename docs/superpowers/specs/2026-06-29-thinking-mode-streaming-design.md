# 思考模式流式推送设计

> 日期: 2026-06-29
> 状态: ✅ 已完成

## 一、问题

当前 `_ThinkTagFilter` **完全丢弃** `_THINK_OPEN` ... `_THINK_CLOSE` 标签内的思考内容，用户看不到模型的推理过程。思考模式应将思考内容推送到前端，并以**不同的视觉样式**与正常回复区分。

> 标签定义：`_THINK_OPEN = "<<"` (7字符), `_THINK_CLOSE = ">>"` (8字符) — 见 `research_api.py:170-171`

## 二、方案

新增 `chat_thinking` SSE 事件类型。后端 `_ThinkTagFilter` 改为双通道输出：思考 token 推 `chat_thinking`，正常 token 推 `chat_token`。前端用折叠区块 + 浅色背景渲染思考内容。

## 三、后端改动

### 3.1 `src/core/session_streamer.py` — 新增 `CHAT_THINKING` 枚举 + `push_chat_thinking()` 方法

**现有代码** (`session_streamer.py:33-43`):

```python
class SessionSSEEventType(str, Enum):
    """Session SSE event types"""
    CHAT_RESPONSE = "chat_response"
    CHAT_TOKEN = "chat_token"
    AGENT_MESSAGE = "agent_message"
    HEARTBEAT = "heartbeat"
    CONNECTED = "connected"
    QUALITY_RESULT = "quality_result"
    SECTION_QUALITY = "section_quality"
    PREVIEW_REFRESH = "preview_refresh"
    QUALITY_CONFIRMED = "quality_confirmed"
```

**改为**:

```python
class SessionSSEEventType(str, Enum):
    """Session SSE event types"""
    CHAT_RESPONSE = "chat_response"
    CHAT_TOKEN = "chat_token"
    CHAT_THINKING = "chat_thinking"
    AGENT_MESSAGE = "agent_message"
    HEARTBEAT = "heartbeat"
    CONNECTED = "connected"
    QUALITY_RESULT = "quality_result"
    SECTION_QUALITY = "section_quality"
    PREVIEW_REFRESH = "preview_refresh"
    QUALITY_CONFIRMED = "quality_confirmed"
```

**新增方法** (紧跟 `push_chat_token` 之后，`session_streamer.py:221` 附近):

```python
@classmethod
def push_chat_thinking(cls, session_id: str, token: str):
    """Push a single thinking token for streaming display.

    Same delivery semantics as push_chat_token:
    - Bypasses _notify_subscribers() to avoid buffering in _recent_messages
    - Does NOT persist to conversation_history
    """
    message = SessionMessage(event=SessionSSEEventType.CHAT_THINKING.value, data={
        "session_id": session_id,
        "token": token,
    })
    subscribers = cls._subscribers.get(session_id)
    if not subscribers:
        return
    for queue in list(subscribers):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass
```

### 3.2 `src/api/research_api.py` — `_ThinkTagFilter` 改为双通道输出

**现有代码** (`research_api.py:174-232`):

```python
class _ThinkTagFilter:
    """Filters <<...>> blocks from streaming tokens."""
    def __init__(self):
        self._in_think = False
        self._buffer = ""

    def feed(self, token: str) -> list[str]:
        emitted = []
        self._buffer += token
        while self._buffer:
            if self._in_think:
                close_idx = self._buffer.find(_THINK_CLOSE)
                if close_idx != -1:
                    self._buffer = self._buffer[close_idx + len(_THINK_CLOSE):]
                    self._in_think = False
                else:
                    partial_len = self._partial_tag_prefix(_THINK_CLOSE, self._buffer)
                    if partial_len:
                        self._buffer = self._buffer[-partial_len:]
                    else:
                        self._buffer = ""
                    break
            else:
                # ...emits normal text only...
        return emitted
```

**改为** — `feed()` 返回 `(type, text)` 元组列表：

```python
class _ThinkTagFilter:
    """Splits streaming tokens into thinking and normal content.

    feed() returns a list of (type, text) tuples where type is 'think' or 'text'.
    """

    def __init__(self):
        self._in_think = False
        self._buffer = ""

    @staticmethod
    def _partial_tag_prefix(tag: str, buf: str) -> int:
        for i in range(1, min(len(tag), len(buf) + 1)):
            if buf.endswith(tag[:i]):
                return i
        return 0

    def feed(self, token: str) -> list[tuple[str, str]]:
        emitted: list[tuple[str, str]] = []
        self._buffer += token
        while self._buffer:
            if self._in_think:
                close_idx = self._buffer.find(_THINK_CLOSE)
                if close_idx != -1:
                    if close_idx > 0:
                        emitted.append(('think', self._buffer[:close_idx]))
                    self._buffer = self._buffer[close_idx + len(_THINK_CLOSE):]
                    self._in_think = False
                else:
                    partial_len = self._partial_tag_prefix(_THINK_CLOSE, self._buffer)
                    safe_len = len(self._buffer) - partial_len if partial_len else len(self._buffer)
                    if safe_len > 0:
                        emitted.append(('think', self._buffer[:safe_len]))
                        self._buffer = self._buffer[safe_len:]
                    else:
                        break
            else:
                open_idx = self._buffer.find(_THINK_OPEN)
                if open_idx != -1:
                    if open_idx > 0:
                        emitted.append(('text', self._buffer[:open_idx]))
                    self._buffer = self._buffer[open_idx + len(_THINK_OPEN):]
                    self._in_think = True
                else:
                    partial_len = self._partial_tag_prefix(_THINK_OPEN, self._buffer)
                    safe_len = len(self._buffer) - partial_len if partial_len else len(self._buffer)
                    if safe_len > 0:
                        emitted.append(('text', self._buffer[:safe_len]))
                        self._buffer = self._buffer[safe_len:]
                    else:
                        break
        return emitted

    def flush(self) -> list[tuple[str, str]]:
        if not self._buffer:
            return []
        result = self._buffer
        self._buffer = ""
        if self._in_think:
            return [('think', result)]
        return [('text', result)]
```

**关键变化**:
- `feed()` 返回值从 `list[str]` → `list[tuple[str, str]]`
- `_in_think=True` 时产出 `('think', ...)` 而非丢弃
- `flush()` 返回 `list[tuple[str, str]]`，不再丢弃 buffer 中的思考内容
- `_partial_tag_prefix()` 签名不变

### 3.3 `src/api/research_api.py` — `_llm_converse` 流式循环适配

**现有代码** (`research_api.py:982-995`):

```python
if SessionStreamer and iteration == 0:
    full_content = ""
    think_filter = _ThinkTagFilter()
    try:
        async for token in call_llm_stream(...):
            full_content += token
            for emit_token in think_filter.feed(token):
                SessionStreamer.push_chat_token(session_id, emit_token)
        remaining = think_filter.flush()
        if remaining:
            SessionStreamer.push_chat_token(session_id, remaining)
```

**改为**:

```python
if SessionStreamer and iteration == 0:
    full_content = ""
    think_filter = _ThinkTagFilter()
    try:
        async for token in call_llm_stream(...):
            full_content += token
            for typ, text in think_filter.feed(token):
                if typ == 'think':
                    SessionStreamer.push_chat_thinking(session_id, text)
                else:
                    SessionStreamer.push_chat_token(session_id, text)
        for typ, text in think_filter.flush():
            if typ == 'think':
                SessionStreamer.push_chat_thinking(session_id, text)
            else:
                SessionStreamer.push_chat_token(session_id, text)
```

**注意**: `full_content` 仍然包含完整的原始内容（含思考标签），因为后续需要从中提取 JSON。

## 四、前端改动

### 4.1 `web/src/types/api.ts` — 新增 `ChatThinkingData` 接口

**现有代码** (`api.ts:238-241`):

```typescript
export interface ChatTokenData {
  session_id: string;
  token: string;
}
```

**其后新增**:

```typescript
export interface ChatThinkingData {
  session_id: string;
  token: string;
}
```

**修改 SSEMessage 联合类型** — 在 `api.ts:214` 的 event 联合类型中添加 `'chat_thinking'`，同时在 `api.ts:215` 的 data 联合类型中添加 `ChatThinkingData`。

### 4.2 `web/src/lib/sse.ts` — 注册 `chat_thinking` 事件

**import 变更** (`sse.ts:3`) — 添加 `ChatThinkingData`:

```typescript
import type { SSEMessage, ChatResponseData, ChatTokenData, ChatThinkingData, AgentMessageData, QualityResultEventData, SectionQualityEventData, PreviewRefreshEventData, QualityConfirmedEventData } from '@/types/api';
```

**现有代码** (`sse.ts:8`):

```typescript
type ChatTokenCallback = (data: ChatTokenData) => void;
```

**其后新增**:

```typescript
type ChatThinkingCallback = (data: ChatThinkingData) => void;
```

**新增回调注册表** (`sse.ts:162` 附近):

```typescript
private sessionChatThinkingCallbacks: Map<string, Set<ChatThinkingCallback>> = new Map();
```

**`subscribeSession` 新增参数** — 在 `onChatToken?: ChatTokenCallback` 后添加 `onChatThinking?: ChatThinkingCallback`。

**`callbackMap` 中注册** (`sse.ts:261-269`):

```typescript
const callbackMap: Record<string, Map<string, Set<any>>> = {
    chat_response: this.sessionChatCallbacks,
    chat_token: this.sessionChatTokenCallbacks,
    chat_thinking: this.sessionChatThinkingCallbacks,
    agent_message: this.sessionAgentCallbacks,
    // ...
};
```

**`eventTypes` 数组中添加** (`sse.ts:280`):

```typescript
const eventTypes = ['chat_response', 'chat_token', 'chat_thinking', 'agent_message', ...];
```

**unsubscribe 清理 + closeAll 清理** — 与 `sessionChatTokenCallbacks` 完全对称。

### 4.3 `web/src/hooks/useProgress.ts` — 新增 `onChatThinking` 选项

**import 变更** (`useProgress.ts:7`) — 添加 `ChatThinkingData`:

```typescript
import type { SSEMessage, ProgressData, PhaseData, CompleteData, Phase, ChatResponseData, ChatTokenData, ChatThinkingData, AgentMessageData, QualityResultEventData, SectionQualityEventData, PreviewRefreshEventData, QualityConfirmedEventData } from '@/types/api';
```

**`UseSessionStreamOptions` 接口新增** (`useProgress.ts:225` 附近):

```typescript
onChatThinking?: (data: ChatThinkingData) => void;
```

**`useSessionStream` 函数中** — 与 `onChatToken` 完全对称地添加 ref、传参给 `subscribeSession`。

```typescript
const onChatThinking = typeof options === 'function' ? undefined : options?.onChatThinking;
const onChatThinkingRef = useRef(onChatThinking);
onChatThinkingRef.current = onChatThinking;
```

并在 `subscribeSession` 调用中添加:

```typescript
onChatThinking ? (data) => { if (onChatThinkingRef.current) onChatThinkingRef.current(data); } : undefined,
```

### 4.4 `web/src/store/useChatStore.ts` — `ChatMessage` 增加 `thinkingContent` 字段

**当前 `ChatMessage` 类型** (`api.ts:404-415`):

```typescript
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'agent' | 'system';
  content: string;
  timestamp: string;
  metadata?: Record<string, any>;
  agent?: { id: string; name: string; action: string; };
}
```

**新增可选字段**:

```typescript
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'agent' | 'system';
  content: string;
  thinkingContent?: string;
  timestamp: string;
  metadata?: Record<string, any>;
  agent?: { id: string; name: string; action: string; };
}
```

**`useChatStore` 的 `updateMessage`** (`useChatStore.ts:35-41`) 已支持 `Partial<ChatMessage>` 更新，无需修改。

**生命周期说明**: `thinkingContent` 不持久化到 `conversation_history`。`push_chat_thinking` 绕过 `_persist_event`，刷新页面后该字段丢失。从 `conversation_history` 恢复的消息不含 `thinkingContent`，这是预期行为——思考内容属于实时流式体验，无需跨会话保留。

### 4.5 `web/src/components/chat/ChatPanel.tsx` — 处理 `chat_thinking` 事件

**import 变更** (`ChatPanel.tsx:6`) — 添加 `ChatThinkingData`:

```typescript
import type { AgentMessageData, ChatMessage as ChatMessageType, ChatTokenData, ChatThinkingData, SelectOption } from '@/types/api';
```

**在 `useSessionStream` 的 `onChatToken` 回调之后新增 `onChatThinking` 回调**:

```typescript
onChatThinking: (data: ChatThinkingData) => {
  const storeSessionId = useSessionStore.getState().activeId;
  const matches = data.session_id === sessionId
    || data.session_id === taskId
    || data.session_id === storeSessionId;
  if (!matches) return;
  if (streamingDoneRef.current) return;

  if (!streamingMsgIdRef.current) {
    streamingMsgIdRef.current = nanoid();
    addMessage({
      id: streamingMsgIdRef.current,
      role: 'assistant',
      content: '',
      thinkingContent: data.token,
      timestamp: new Date().toISOString(),
    });
  } else {
    const currentMsg = useChatStore.getState().messages.find(m => m.id === streamingMsgIdRef.current);
    if (currentMsg) {
      updateMessage(streamingMsgIdRef.current, {
        thinkingContent: (currentMsg.thinkingContent || '') + data.token,
      });
    }
  }
},
```

### 4.6 `web/src/components/chat/ChatMessage.tsx` — 思考内容渲染

**在消息气泡内，`message.content` 之前添加思考区块**:

```tsx
{message.thinkingContent && (
  <details className="mb-2 rounded-lg bg-muted/50 border border-border/50 px-3 py-2">
    <summary className="text-xs text-muted-foreground cursor-pointer select-none flex items-center gap-1.5">
      <Brain className="h-3 w-3" />
      思考过程
    </summary>
    <p className="mt-2 text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
      {message.thinkingContent}
    </p>
  </details>
)}
```

**视觉效果**:
- `<details>` 默认折叠，用户点击展开
- 浅色背景 (`bg-muted/50`) + 细边框 (`border-border/50`) 与正常回复区分
- 小号字体 (`text-xs`) + 灰色文字 (`text-muted-foreground`)
- Brain 图标标识 (已在 `ChatMessage.tsx:7` 导入，无需额外 import)

## 五、降级路径（防御性兜底）

当 `call_llm_stream` 失败降级到 `call_llm()` 时（`research_api.py:996-1004`），`full_content` 可能包含思考标签。但后续 `_extract_json_from_llm_content` + `json.loads` 提取 JSON 后，`parsed['message']` 不含思考标签。因此 **`chat_response.message` 在正常和降级路径下都不含标签**。

前端 `onChatResponse` 的降级拆分逻辑是**防御性兜底**——如果未来有其他代码路径直接将含标签的内容推入 `chat_response.message`，前端仍能正确处理。该逻辑必须覆盖 **两个分支**（streaming 和 non-streaming），否则防御不完整。

在 `ChatPanel.tsx` 的 `onChatResponse` 回调中完整替换为:

```typescript
onChatResponse: (data) => {
  const THINK_OPEN = '<think>';
  const THINK_CLOSE = '</think>';
  const thinkOpen = data.message.indexOf(THINK_OPEN);
  const thinkClose = data.message.indexOf(THINK_CLOSE, thinkOpen + THINK_OPEN.length);
  let finalContent = data.message;
  let finalThinking: string | undefined;
  if (thinkOpen !== -1 && thinkClose !== -1) {
    finalThinking = data.message.substring(thinkOpen + THINK_OPEN.length, thinkClose);
    finalContent = data.message.substring(0, thinkOpen) + data.message.substring(thinkClose + THINK_CLOSE.length);
  }
  if (streamingMsgIdRef.current) {
    updateMessage(streamingMsgIdRef.current, {
      content: finalContent,
      ...(finalThinking !== undefined ? { thinkingContent: finalThinking } : {}),
    });
    streamingMsgIdRef.current = null;
    streamingDoneRef.current = true;
  } else {
    addMessage({
      id: nanoid(),
      role: 'assistant',
      content: finalContent,
      ...(finalThinking !== undefined ? { thinkingContent: finalThinking } : {}),
      timestamp: data.timestamp || new Date().toISOString(),
    });
  }
  if (data.suggestions && data.suggestions.length > 0) {
    useResearchStore.getState().setStep(0, data.suggestions);
  }
  useResearchStore.getState().setSearchState('completed');
  setIsWaitingForReply(false);
  clearTimeout(searchStateTimerRef.current);
  searchStateTimerRef.current = setTimeout(() => {
    useResearchStore.getState().setSearchState('idle');
  }, 2000);
},
```

## 六、`chat_response` 的 `message` 字段无需清洗

`push_chat_response` 推送的 `message` 来自 `_llm_converse` 返回的 `parsed['message']`。由于 `_llm_converse` 从 `full_content` 中提取 JSON（`_extract_json_from_llm_content` + `json.loads`），`parsed['message']` 不含思考标签。JSON 提取过程已天然剥离（`research_api.py:1105` 用 `re.sub` 移除思考标签后再提取 JSON）。

唯一例外是降级路径（第五节），由前端兜底处理。

## 七、测试改动

### 7.1 修改 `tests/unit/test_think_tag_filter.py`

现有 18 个测试需要适配新的 `feed()` 返回类型 `list[tuple[str, str]]`:

| 测试 | 现有断言 | 新断言 |
|------|---------|--------|
| `test_passthrough_normal_text` | `== ["Hello world"]` | `== [('text', 'Hello world')]` |
| `test_passthrough_multiple_chunks` | `== ["Hello "]` / `["world "]` / `["test"]` | `== [('text', 'Hello ')]` / `[('text', 'world ')]` / `[('text', 'test')]` |
| `test_filter_complete_think_block` | `== ["Before ", " After"]` | `== [('text', 'Before '), ('think', 'internal'), ('text', ' After')]` |
| `test_filter_think_at_start` | `== ["Output"]` | `== [('think', 'thinking...'), ('text', 'Output')]` |
| `test_filter_think_at_end` | `== ["Output"]` | `== [('text', 'Output'), ('think', 'thinking...')]` |
| `test_filter_only_think_content` | `== []` | `== [('think', 'thinking...')]` |
| `test_filter_multiple_think_blocks` | `== ["A", "B", "C"]` | `== [('text', 'A'), ('think', 'first'), ('text', 'B'), ('think', 'second'), ('text', 'C')]` |
| `test_think_tag_split_across_chunks` | `== ["Before "]` / `== []` / `== [" After"]` | `== [('text', 'Before ')]` / `== []` / `== [('text', ' After')]` |
| `test_empty_feed_returns_empty` | `== []` | `== []` |
| `test_flush_after_consumed_text_returns_empty` | `== ""` | `== []` |
| `test_feed_after_think_block_returns_remaining` | `== ["End"]` | `== [('text', 'End')]` |
| `test_flush_during_think_block_discards_buffered` | `== ""` | `== [('think', 'thinking...')]` |
| `test_partial_open_tag_at_buffer_end_is_held_back` | `== ["text "]` | `== [('text', 'text ')]` |
| `test_think_tag_adjacent_no_spaces` | `== ["A", "B"]` | `== [('text', 'A'), ('think', 't'), ('text', 'B')]` |
| `test_chunk_breaks_at_tag_boundary` | `== ["A"]` / `== []` / `== []` / `== []` / `== ["B"]` | `== [('text', 'A')]` / `== []` / `== [('think', 'inner')]` / `== []` / `== [('text', 'B')]` |
| `test_large_realistic_streaming_scenario` | `"".join(results) == "..."` | 见下方 |
| `test_think_blocks_can_be_empty` | `== ["Hello"]` | `== [('text', 'Hello')]` |
| `test_nested_think_like_content_preserved` | `== ["I think this is a good idea"]` | `== [('text', 'I think this is a good idea')]` |

**`test_large_realistic_streaming_scenario` 特殊适配**:

现有代码 `"".join(results)` 在 `list[tuple[str, str]]` 上会抛 `TypeError`。需改为:

```python
def test_large_realistic_streaming_scenario(self):
    """Simulate a realistic streaming sequence with think tags."""
    from src.api.research_api import _ThinkTagFilter
    f = _ThinkTagFilter()
    chunks = [
        "Based", " on", " the", " analysis", ",", " I", " ",
        "The", " user", " wants", " market", " data", " for", " 2024", ".",
        " recommend", " searching", " for", " the", " latest", " reports.",
    ]
    results: list[tuple[str, str]] = []
    for chunk in chunks:
        results.extend(f.feed(chunk))
    text_parts = [text for typ, text in results if typ == 'text']
    think_parts = [text for typ, text in results if typ == 'think']
    assert "".join(text_parts) == "Based on the analysis, I  recommend searching for the latest reports."
    assert "".join(think_parts) == "The user wants market data for 2024."
```

**`test_chunk_breaks_at_tag_boundary` 适配**:

```python
def test_chunk_breaks_at_tag_boundary(self):
    """Token chunk ends exactly at tag boundary."""
    from src.api.research_api import _ThinkTagFilter
    f = _ThinkTagFilter()
    assert f.feed("A") == [('text', 'A')]
    assert f.feed("<<") == []                       # enter think mode
    assert f.feed("inner") == [('think', 'inner')]  # thinking content emitted
    assert f.feed(">>") == []                       # close tag, no content
    assert f.feed("B") == [('text', 'B')]
```

> 注意: 上例中 `<<` / `>>` 仅为示意，实际标签为 `_THINK_OPEN` / `_THINK_CLOSE`。

核心原则：原来被丢弃的思考内容现在以 `('think', ...)` 形式返回。所有使用 `"".join()` 合并结果的测试必须按 `typ` 分组后再 join。

### 7.2 新增 `tests/unit/test_push_chat_thinking.py`

与 `test_push_chat_token.py` 完全对称:

| 类 | 用例 |
|----|------|
| `TestChatThinkingEnum` | `CHAT_THINKING` 枚举存在且值为 `"chat_thinking"` |
| `TestPushChatThinkingDelivery` | 订阅者收到 thinking token、多订阅者、无订阅者不报错 |
| `TestPushChatThinkingNoBuffer` | thinking token 不进入 `_recent_messages` |
| `TestPushChatThinkingNoPersist` | thinking token 不写入 `conversation_history` |

### 7.3 修改 `tests/unit/test_llm_converse_streaming.py`

`test_stream_first_iteration_calls_stream_api` 需验证思考 token 调用 `push_chat_thinking` 而非 `push_chat_token`。

具体地，当 mock 的 `SessionStreamer` 被注入含 `_THINK_OPEN` ... `_THINK_CLOSE` 标签的 token 时，`push_chat_thinking` 应被调用而非 `push_chat_token`。

## 八、文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `src/core/session_streamer.py` | 修改 | 新增 `CHAT_THINKING` 枚举 + `push_chat_thinking()` |
| `src/api/research_api.py` | 修改 | `_ThinkTagFilter` 双通道 + `_llm_converse` 适配 |
| `web/src/types/api.ts` | 修改 | `ChatThinkingData` + `SSEMessage.event` 联合类型 + `ChatMessage.thinkingContent` |
| `web/src/lib/sse.ts` | 修改 | `ChatThinkingCallback` + import 变更 + 回调注册表 + 事件注册 |
| `web/src/hooks/useProgress.ts` | 修改 | `ChatThinkingData` import 变更 + `onChatThinking` 选项 |
| `web/src/store/useChatStore.ts` | 无改动 | `updateMessage` 已支持 `Partial<ChatMessage>` |
| `web/src/components/chat/ChatPanel.tsx` | 修改 | `ChatThinkingData` import 变更 + `onChatThinking` 回调 + 降级路径拆分（两分支完整覆盖） |
| `web/src/components/chat/ChatMessage.tsx` | 修改 | 折叠思考区块渲染（Brain 图标已导入，无需额外 import） |
| `tests/unit/test_think_tag_filter.py` | 修改 | 适配新返回类型（全部 18 个测试 + `join` 适配） |
| `tests/unit/test_push_chat_thinking.py` | 新增 | 与 `test_push_chat_token.py` 对称 |
| `tests/unit/test_llm_converse_streaming.py` | 修改 | 验证 thinking 路由 |

## 九、审查清单

- [x] `push_chat_thinking` 与 `push_chat_token` 的绕过 `_recent_messages` 逻辑一致 — 实现完全对称
- [x] `flush()` 在 `_in_think=True` 时不再丢弃，返回 `('think', ...)` — 语义变更，测试需同步更新
- [x] 降级路径前端拆分 — 防御性兜底。`chat_response.message` 在正常/降级路径下均不含标签（JSON 提取已剥离），前端拆分逻辑理论上不触发，但作为安全网保留。**两分支（streaming/non-streaming）均覆盖**
- [x] `chat_response.message` 无需清洗 — JSON 提取过程已天然剥离思考标签（第六节已论证，`research_api.py:1105` `re.sub` 移除）
- [x] `thinkingContent` 不持久化到 `conversation_history` — `push_chat_thinking` 绕过 `_notify_subscribers` 和 `_persist_event`，与 `push_chat_token` 对称。**刷新页面后丢失，属于预期行为（4.4 节已声明生命周期）**
- [x] `SSEMessage.event` 联合类型 — 需在 `api.ts:214` 添加 `'chat_thinking'`，`api.ts:215` 的 data 联合类型添加 `ChatThinkingData`
- [x] `_ThinkTagFilter` 返回类型变更 — `list[str]` → `list[tuple[str, str]]`，所有 18 个现有测试需适配
- [x] `_llm_converse` 中 `full_content` 仍含思考标签 — 正确，后续 JSON 提取需要完整原始内容
- [x] **import 变更清单** — `sse.ts:3`、`useProgress.ts:7`、`ChatPanel.tsx:6` 三处须添加 `ChatThinkingData` import
- [x] **`test_large_realistic_streaming_scenario` 适配** — `"".join(results)` 在 tuple 列表上抛 TypeError，须按 `typ` 分组后 join
- [x] **`test_chunk_breaks_at_tag_boundary` 适配** — think 模式下的 `f.feed("inner")` 从 `== []` 改为 `== [('think', 'inner')]`
- [x] **Brain 图标** — 已在 `ChatMessage.tsx:7` 导入，无需额外 import
