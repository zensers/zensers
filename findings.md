# Zensers 深度问题分析报告（二次校验版）

## 一、Bug 1：用户第一条消息丢失

### 1.1 现象

用户发送第一条消息后，该消息（或助手的回复）在 UI 中消失或从未显示。此问题已多次修复但反复出现。

### 1.2 已排除的假设

经过逐行代码追踪，以下假设被**排除**：

| 原假设 | 排除原因 |
|--------|----------|
| `__pending__` 搬运存在竞态 | Zustand `set()` 是**同步**的。`addMessage` → `syncActive` 创建 `__pending__` → `createSession` 读取 `__pending__.messages` 全在同一 JS 执行栈中，不存在竞态 |
| `useResearchStore.subscribe` 会覆盖消息 | `useResearchStore` 不管理 `messages` 字段。订阅只在 `sessionId` 或 `status` 变化时触发 `set`，不影响 `useChatStore.messages` |
| SSE 连接延迟导致消息丢失 | 后端 `SessionStreamer` 有 replay 缓冲区（20条），晚订阅者能收到之前的事件 |

### 1.3 真实根因

**根因 1（确定性 Bug）：`status === 'processing'` 时助手消息被丢弃**

| 位置 | 说明 |
|------|------|
| `useResearch.ts:177-181` | `startResearch` 中，当后端返回 `status='processing'`，直接 `return data`，**不调用 `addMessage`** 添加 `data.message` |
| `useResearch.ts:464-468` | `sendMessage` 中，同样的问题——processing 路径不添加助手消息 |
| `research_api.py:487` | 后端返回 `{status:'processing', message:'正在搜索...'}`，但前端丢弃了这个 message |

影响：
- 用户看到的对话缺少了助手的中间确认（"好的，正在搜索..."）
- 后续 SSE 的 `chat_response` 推送最终的搜索结果回复，所以**最终助手消息不会丢失**，但**中间提示丢失**
- 如果 SSE 推送也出错（如 JSON 解析失败），用户会看到 "Sorry, failed to send message"，而之前的中间提示也不在了

**根因 2（确定性 Bug）：`handleSend` catch 块中 `addMessage` 的 "Sorry" 消息与 SSE 推送的消息可能冲突**

当 `startResearch` 或 `sendMessage` 抛出异常时（`useResearch.ts:195-203`），catch 坅添加 "Sorry, failed to send message"。但此时如果 SSE 仍在推送搜索结果，`onChatResponse` 回调也会 `addMessage`，导致消息乱序。

**根因 3（可能导致"第一条消息消失"）：`useSessionStore` 持久化的 `activeId` 策略**

`useSessionStore.ts:237-241`：`activeId` 只在 session 状态为 `running` 或 `paused` 时才被持久化到 localStorage。对于 `idle` 状态的 session，页面刷新后 `activeId` 为 `null` → `useChatStore.subscribe` 中 `active = undefined` → `next = []` → **所有消息在 UI 中不显示**。

虽然这不是"消息丢失"（消息仍保存在 localStorage 的 sessions 中），但用户看到的效果等同于消息消失——页面刷新后，聊天面板变成空白，需要手动恢复 session 才能找回消息。

### 1.4 修复方案

**方案 A（P0）：processing 路径添加助手消息**

```typescript
// useResearch.ts - startResearch 和 sendMessage
if ((data as any).status === 'processing') {
  if (data.message) {
    addMessage({ id: nanoid(), role: 'assistant', content: data.message, timestamp: new Date().toISOString() });
  }
  setStep(0, undefined);
  setIsNetworkBusy(false);
  setIsWaitingForReply(true);
  return data;
}
```

风险：SSE 的 `onChatResponse` 后续也会推送助手消息，可能产生**重复消息**。需要在 `onChatResponse` 回调中判断是否已存在相同内容的助手消息，避免重复添加。

**方案 B（P1）：`createSession` 接受 `initialMessages` 参数（防御性加固）**

即使 `__pending__` 搬运路径当前是正确的，显式传入消息可以消除对中间状态的依赖，增加系统鲁棒性：

```typescript
createSession: (id: string, title?: string, initialMessages?: ChatMessage[]) => {
  const pendingMsgs = initialMessages && initialMessages.length > 0
    ? initialMessages
    : (activeId === '__pending__' ? sessions['__pending__']?.messages || [] : []);
  ...
},
```

**方案 C（P2）：页面刷新后自动恢复上一个 idle session 的消息**

修改 `activeId` 持久化策略，或在页面加载时自动 `restoreSession` 最后活跃的 session。

---

## 二、Bug 2：用户要求"按照框架进行深度研究"时未启动深度研究

### 2.1 现象

用户在 09:49 输入"根据框架进行深度研究"。系统没有启动深度研究流程，而是开始了新一轮搜索循环，最终出现 "Sorry, failed to send message"。

### 2.2 时序分析

```
09:41  用户输入 "比亚迪公司财务分析"
       → startResearch() → ses_9707e8c7 → chat 模式
       → LLM 触发 web_search → status='processing'
       → SSE 搜索结果 → 助手回复8段摘要

09:45  助手回复："以上是第一轮数据收集的初步汇总..."

09:49  用户输入 "根据框架进行深度研究"
       → sendMessage(text) → POST /api/v1/research/interact
       → _handle_user_message() → mode='chat' → _handle_chat_mode()
       → _llm_converse() → LLM 应返回 action='enter_framework'
       → 实际：LLM 返回 tool_call (web_search) → status='processing'
       → 后台搜索循环开始

09:52  后台 _do_execute_tool_background 执行搜索
       → synthesis prompt 要求 LLM 返回 JSON + action='continue_chat'
       → 但 LLM 返回 Markdown 长文分析（非 JSON）
       → ValueError: LLM response contains no valid JSON
       → 重试一次（temperature=0.3）
       → 仍然返回 Markdown 分析
       → _fallback_response() → 简单 chat 回复
       → SSE 推送 fallback 回复

09:54  前端收到 SSE chat_response 或 HTTP 错误
       → 显示 "Sorry, failed to send message"
```

### 2.3 根因分析

**根因 A（确定性 Bug）：LLM 没有返回 `enter_framework` action**

后端 `_handle_chat_mode`（research_api.py:442-543）完全依赖 LLM 的 JSON 响应中的 `action` 字段来路由：
- `action='enter_framework'` → 进入 framework 模式
- `action='continue_chat'` → 继续聊天
- `action='start_execution'` → 开始执行

当用户说"根据框架进行深度研究"时，DeepSeek 模型没有返回 `action='enter_framework'`，而是返回了 `tool_call`（触发新一轮搜索）。

**根因 B（确定性 Bug）：后台搜索的 synthesis prompt 强制 `action='continue_chat'`**

`_do_execute_tool_background`（research_api.py:948）的 synthesis prompt 明确要求：
```
IMPORTANT: Set action to "continue_chat". Output the final JSON response.
```

这意味着即使搜索成功完成，后台 LLM 合成的结果也永远不会包含 `action='enter_framework'`。搜索循环完成后，系统会停留在 chat 模式，**无法自动转向 framework 模式**。

**根因 C（确定性 Bug）：JSON 解析失败时 fallback 不会触发 framework 模式**

`_handle_chat_mode` 的异常处理（research_api.py:461-467）：
- ValueError → 重试一次
- 重试也失败 → `_fallback_response()`
- `_fallback_response()` 只返回 `{step:0, mode:'chat', message:'抱歉，我临时遇到了问题...'}`

**没有任何路径能让 JSON 解析失败后自动进入 framework 模式**。

**根因 D（行为 Bug）：tool_call 循环取消后，新消息可能触发新的搜索循环**

日志显示：
```
09:53:06  Cancelling loop iteration 5 — new message detected
09:53:14  Cancelling loop iteration 6 — new message detected
```

当 `_llm_converse` 检测到新消息时取消当前迭代，但新消息的处理可能又触发 `_llm_converse` → 新的 tool_call → 新的搜索循环。如果这个循环继续产生 JSON 解析失败，就会形成**搜索-失败-重试**的死循环。

### 2.4 修复方案

**方案 A（P0，推荐）：关键词快捷路径触发 framework 模式**

在 `_handle_user_message` 或 `_handle_chat_mode` 入口，检测明确的"深度研究"意图关键词，**直接跳过 LLM 路由**：

```python
depth_keywords = ('深度研究', 'deep research', '按框架研究', '根据框架', 
                  '开始研究', 'start research', '详细分析', 'detailed analysis')
if any(kw in user_input.lower() for kw in depth_keywords):
    if context.get('topic'):
        return await self._enter_framework_mode(session_id, user_input)
```

风险：关键词列表需要精心设计，避免误触发（如"我想了解一下深度研究的流程"不应触发）。建议只匹配**命令式**表达。

**方案 B（P1）：修改 synthesis prompt 允许 `enter_framework` action**

`_do_execute_tool_background` 的 synthesis prompt 应改为：

```
Based on the collected data and the user's request, decide the next action:
- If the user requested deep research or framework confirmation, set action="enter_framework"
- Otherwise, set action="continue_chat"
```

**方案 C（P1）：JSON 解析失败时，如果有 topic + directions，自动进入 framework 模式**

```python
# _handle_chat_mode 异常处理
except ValueError as e:
    conv_result = await self._llm_converse(..., _json_retry=True)
except Exception as e:
    context = session.get('research_context', {})
    if context.get('topic') and (context.get('directions') or context.get('_suggested_sections')):
        logger.info(f"JSON parsing failed but topic+directions exist, entering framework mode")
        return await self._enter_framework_mode(session_id, user_input)
    return self._fallback_response(session_id, context)
```

---

## 三、两个 Bug 的关联性

在 09:49 事件中，两个 Bug 彼此叠加但**不是因果关系**：

| Bug | 影响 |
|-----|------|
| Bug 1（processing 路径消息丢弃） | 助手中间提示 "正在搜索..." 不显示 |
| Bug 2（LLM 未返回 enter_framework） | 系统继续搜索而非启动深度研究 |
| Bug 2（JSON 解析失败） | 最终 fallback 回复取代了深度研究 |
| Bug 1 + Bug 2 | 用户看到 "Sorry, failed to send message"，整个交互失败 |

两个 Bug 是**独立的**，但它们的叠加效应让用户体验完全崩溃。

---

## 四、修改影响矩阵（校验版）

| 修改点 | 文件 | 风险 | 需注意的副作用 |
|--------|------|------|---------------|
| processing 路径添加助手消息 | `useResearch.ts:177,464` | 中 | SSE 后续推送可能导致**重复消息**，需在 `onChatResponse` 中去重 |
| `createSession` 增加 `initialMessages` | `useSessionStore.ts:55,199` | 低 | 向下兼容，不传参数时 fallback 到 `__pending__` 搬运 |
| 关键词触发 framework 模式 | `research_api.py:263-335` | 中 | 关键词列表需排除非命令式表达（如疑问句） |
| synthesis prompt 允许 `enter_framework` | `research_api.py:948` | 中 | LLM 可能不稳定返回该 action，需要 fallback |
| JSON 失败自动进入 framework | `research_api.py:461-467` | 中 | 需确保 topic+directions 存在才触发，避免空 framework |

---

## 五、建议修复优先级（校验版）

1. **P0**：关键词快捷路径触发 framework 模式（最直接的解决方案，消除 LLM 路由失败的影响）
2. **P0**：processing 路径添加助手消息（需配合去重机制）
3. **P1**：`createSession` 接受 `initialMessages` 参数（防御性加固）
4. **P1**：JSON 解析失败时自动进入 framework（条件触发）
5. **P2**：synthesis prompt 改进（允许 `enter_framework` action）
6. **P2**：页面刷新后自动恢复 session（用户体验改善）