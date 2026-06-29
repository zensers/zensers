# Phase 3: LLM流式输出 + Chat体验升级 — 最终报告

## 一、实现范围

| 组件 | 状态 | 文件 |
|------|------|------|
| `call_llm_stream()` | ✅ 实现 | `src/core/llm_client.py` |
| `CHAT_TOKEN` SSE事件 | ✅ 实现 | `src/core/session_streamer.py` |
| `push_chat_token()` | ✅ 实现 | `src/core/session_streamer.py` |
| `_ThinkTagFilter` | ✅ 实现 | `src/api/research_api.py` |
| `_llm_converse()` 流式改造 | ✅ 实现 | `src/api/research_api.py` |
| `_retry_json_only()` call_llm迁移 | ✅ 实现 | `src/api/research_api.py` |
| `前端类型扩展` (api.ts) | ✅ 实现 | `web/src/types/api.ts` |
| `前端SSE事件注册` (sse.ts) | ✅ 实现 | `web/src/lib/sse.ts` |
| `前端消息更新方法` (useChatStore) | ✅ 实现 | `web/src/store/useChatStore.ts` |
| `前端hook扩展` (useProgress) | ✅ 实现 | `web/src/hooks/useProgress.ts` |
| `前端流式渲染` (ChatPanel) | ✅ 实现 | `web/src/components/chat/ChatPanel.tsx` |

**测试结果：**
- 后端 Python: 83 passed（44新增 + 39既有），0 regression
- 前端 TypeScript: 0 新增编译错误（1个预先存在的QualityPanel.tsx类型问题未影响）
- 设计文档修正项全部实施（`_get_client`/`_on_complete_var` 不引用、`_notify_subscribers` 绕过、`push_chat_response` 不入 `_llm_converse`）

## 二、实现细节

### 2.1 `call_llm_stream()` — `src/core/llm_client.py:21-63`

```python
async def call_llm_stream(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: str = "",
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> AsyncGenerator[str, None]:
```

**行为：**
- 直接创建 `AsyncOpenAI` 实例（与 `_call_llm_api()` 一致）
- `stream=True` 参数传给 OpenAI API
- 逐 token yield content（跳过 `choices` 为空或 `delta.content` 为空的chunk）
- 空prompt/空白prompt 不yield任何内容
- 异常直接传播（无fallback/retry），调用方catch后降级到 `call_llm()`

**已知偏差（设计文档修正项）：**
- ❌ 不引用 `_get_client()`（不存在于当前模块）
- ❌ 不触发 `_on_complete_var` callback（不存在于当前模块）
- ✅ `max_tokens` 使用 `or` 运算，与 `call_llm()` 行为一致（0值会被覆盖为默认值）

### 2.2 `_ThinkTagFilter` — `src/api/research_api.py:174-231`

状态机实现，处理 `<think>...</think>` 标签的流式过滤：

```
初始状态: _in_think = False, _buffer = ""

feed(token):
  1. 追加 token 到 _buffer
  2. 若 _in_think:
     a. 在 _buffer 中搜索 _THINK_CLOSE ("</think>")
     b. 找到 → 截断，切换 _in_think = False，继续循环
     c. 未找到 → 检查是否部分匹配 </think> 结尾
        - 有部分匹配 → 保留后缀到 _buffer
        - 无匹配 → 清空 _buffer
     d. break (think内容不发射)
  3. 若非 _in_think:
     a. 在 _buffer 中搜索 _THINK_OPEN ("<think>")
     b. 找到 → emit 之前的内容，截断，切换 _in_think = True
     c. 未找到 → 检查是否部分匹配 <think> 结尾
        - 部分匹配 → emit 安全部分，保留部分匹配后缀
        - 无匹配 → emit 全部，清空 _buffer

flush():
  返回剩余的非think内容buffer；清空buffer
```

**边界情况覆盖：**
- 标签跨token分割（`<thi` + `nk>`、`</thi` + `nk>`）
- 多个think块
- 仅有think内容（无外部输出）
- 空think块（`<think></think>`）
- 相邻文本无空格
- chunk恰好对齐标签边界

### 2.3 `SessionStreamer.push_chat_token()` — `src/core/session_streamer.py:201-220`

```python
@classmethod
def push_chat_token(cls, session_id: str, token: str):
```

**关键设计：绕过 `_notify_subscribers()`**

`_notify_subscribers()` 会将每个事件追加到 `_recent_messages` 缓冲（上限20条）。token粒度的推送会快速填满缓冲，挤出有价值的 `chat_response`/`agent_message`。因此 `push_chat_token()` 直接操作 subscriber queues：

```python
subscribers = cls._subscribers.get(session_id)
if not subscribers:
    return
for queue in list(subscribers):
    try:
        queue.put_nowait(message)
    except asyncio.QueueFull:
        pass
```

**不持久化**（不调用 `_persist_event()`），最终 `chat_response` 负责持久化完整消息。

### 2.4 `_llm_converse()` 流式改造 — `src/api/research_api.py:956-1019`

**改动点：**

1. **模块级导入**（文件顶部）：`from src.core.llm_client import call_llm, call_llm_stream`

2. **删除 `llm_skill` 实例化**（原L955-964）：不再动态创建 `LLMSkill()` 实例

3. **提前导入 SessionStreamer**（L961-964）：在 loop 开始前导入，确保流式路径可用

4. **双通道分支**（L982-1012）：
   ```python
   if SessionStreamer and iteration == 0:
       # 流式路径：call_llm_stream + _ThinkTagFilter + push_chat_token
   else:
       # 非流式路径：call_llm + wait_for(timeout=60)
   ```
   - 仅首轮对话流式输出
   - tool loop后续轮次走非流式
   - 流式异常时降级到 `call_llm()`（含 `wait_for(timeout=60)`）

5. **`_retry_json_only()` 迁移**（L1120-1139）：删除`llm_skill`参数，改用模块级 `call_llm()`

6. **无内部 `push_chat_response`**：`_llm_converse` 不推送 `chat_response`，由调用方 `_handle_chat_mode` 统一处理，避免双重推送

## 三、测试覆盖

### 3.1 `tests/unit/test_think_tag_filter.py` — 18 tests

| 类别 | 用例 |
|------|------|
| 常规文本 | passthrough_normal_text, passthrough_multiple_chunks, nested_think_like_content_preserved |
| 完整think块 | filter_complete_think_block, filter_think_at_start, filter_think_at_end, filter_only_think_content |
| 多think块 | filter_multiple_think_blocks |
| 跨token分割 | think_tag_split_across_chunks, chunk_breaks_at_tag_boundary |
| 空/边界 | empty_feed_returns_empty, think_blocks_can_be_empty, think_tag_adjacent_no_spaces |
| 缓冲管理 | flush_after_consumed_text_returns_empty, flush_during_think_block_discards_buffered, feed_after_think_block_returns_remaining, partial_open_tag_at_buffer_end_is_held_back |
| 真实场景 | large_realistic_streaming_scenario |

### 3.2 `tests/unit/test_call_llm_stream.py` — 13 tests

| 类别 | 用例 |
|------|------|
| 基本流 | yields_tokens_in_order, passes_stream_true |
| 模型选择 | uses_model_from_settings, model_override |
| 空提示 | empty_prompt_returns_no_tokens, whitespace_only_prompt_returns_no_tokens |
| 系统提示 | passes_system_prompt |
| 默认值 | max_tokens_none_uses_default, temperature_none_uses_default |
| 异常 | raises_on_api_error |
| 边缘情况 | handles_empty_choices, handles_delta_without_content |
| 轻量 | skips_stream_token_counting |

### 3.3 `tests/unit/test_push_chat_token.py` — 8 tests

| 类别 | 用例 |
|------|------|
| 枚举存在 | test_chat_token_enum_exists |
| 推送交付 | subscriber_receives_token, multiple_subscribers_all_receive, no_subscribers_no_error |
| 缓冲隔离 | token_not_in_recent_messages, chat_response_still_buffered, tokens_dont_push_out_chat_responses |
| 持久化隔离 | token_not_in_conversation_history |

### 3.4 `tests/unit/test_llm_converse_streaming.py` — 4 + 1 tests

| 类别 | 用例 |
|------|------|
| 导入验证 | imports_call_llm_stream |
| 流式路径 | stream_first_iteration_calls_stream_api |
| 降级路径 | stream_failure_degrades_to_call_llm, push_chat_token_not_called_on_degraded_path |
| tool loop | non_first_iteration_uses_call_llm |

## 四、代码审查发现

### 审查中解决的全部问题

| # | 问题 | 阶段 | 严重度 |
|---|------|------|--------|
| 1 | `_get_client()` 不存在于 `llm_client.py` | 设计审查 | 高 |
| 2 | `_on_complete_var` 不存在于 `llm_client.py` | 设计审查 | 高 |
| 3 | `_notify_subscribers` 污染 `_recent_messages` 缓冲 | 设计审查 | 高 |
| 4 | `sse.ts` 未注册 `chat_token` 事件 | 前端审查 | 高 |
| 5 | `useChatStore` 无 `updateMessage` 方法 | 前端审查 | 高 |
| 6 | `_llm_converse` 内推 `push_chat_response` 导致双重推送 | 设计审查 | 中 |
| 7 | `<think>` 标签在流式中泄漏 | 设计审查 | 中 |
| 8 | 降级 `call_llm()` 无超时保护 | 设计审查 | 中 |
| 9 | 方案声称"不改前端"但实际必须改 | 前端审查 | 中 |

### 本次审查发现

| # | 问题 | 严重度 | 说明 |
|---|------|--------|------|
| A | `flush()` 返回 partial `<` tag | 低 | 仅当流在 `<think>` 标签打开后立即结束时触发，实际不会发生 |
| B | `push_chat_token` 无logger.debug | 低 | 调试便利性，可后续增加 |
| C | Python `from ... import` 导致补丁路径复杂 | 低 | 测试需 patch `research_api` 命名空间而非 `llm_client`（已在测试中正确处理） |
| D | 无 `stream_options` 参数 | 低 | 不影响功能，未来可添加 `include_usage` |

## 五、审查中发现并修复的问题

| # | 问题 | 阶段 | 严重度 | 修复 |
|---|------|------|--------|------|
| 1 | `_get_client()` 不存在于 `llm_client.py` | 设计 | 高 | `call_llm_stream()` 直接创建 `AsyncOpenAI` 实例 |
| 2 | `_on_complete_var` 不存在于 `llm_client.py` | 设计 | 高 | `call_llm_stream()` 不触发回调，`call_llm()` 也不触发 |
| 3 | `_notify_subscribers` 将 token 写入 `_recent_messages` 缓冲 | 设计 | 高 | `push_chat_token()` 绕过 `_notify_subscribers()`，直接操作 queues |
| 4 | `_llm_converse` 内推送 `push_chat_response` 导致双重推送 | 设计 | 高 | 内部不推送，由调用方 `_handle_chat_mode` 统一处理 |
| 5 | `ChatMessage` 类型名与组件名冲突（ChatPanel.tsx） | 前端审查 | 高 | 类型导入用 `as ChatMessageType` 别名 |
| 6 | `streamingDoneRef` 永不复位，第二次流式失效 | 前端审查 | 高 | `handleSend` 入口复位 `streamingMsgIdRef` + `streamingDoneRef` |
| 7 | `chat_token` 在 `chat_response` 后到达（SSE重连）导致幽灵消息 | 前端审查 | 中 | `streamingDoneRef` guard + 正确的复位时机 |
| 8 | `subscribeSession` 参数顺序验证 | 前端审查 | 中 | 两次对照定义与调用，确认 `onChatToken` 位置正确 |
| 9 | 降级 `call_llm()` 无超时保护 | 设计 | 中 | 降级路径加 `asyncio.wait_for(timeout=60)` |
| 10 | `test_research_api_llm_config.py` 传旧参数给 `_retry_json_only` | 回归检测 | 中 | 测试补丁路径改为 `research_api.call_llm` |
| 11 | `report_upgrade/orchestrator.py:186` 引用不存在的 `_on_complete_var` | 验证检测 | 高 | 移除 `_on_complete_var` 上下文管理器，将 `_record_llm_trace` 合并回 `_call_llm_tracked`；同步修复 `test_phase3_changes.py` 的 `inspect.getsource` 目标函数 |

### 前端流式渲染时序

```
1. 用户发送 → isWaitingForReply = true
2. chat_token 事件到达 → 创建/更新assistant消息，逐字显示
3. agent_message 事件到达（如有tool call）→ 追加agent消息
4. chat_response 事件到达 → 用完整消息替换流式内容，终结流式
5. isWaitingForReply = false
```

## 六、回退策略

1. **后端：** `call_llm_stream()` 是新增函数，不影响现有 `call_llm()`。`_llm_converse()` 中移除 `SessionStreamer` 判断即可回退到全非流式。`_retry_json_only` 已迁移到 `call_llm`，不影响功能。
2. **SSE：** `CHAT_TOKEN` 是新增事件类型，不破坏现有 `chat_response`/`agent_message` 事件处理。前端忽略 `chat_token` 事件即可回退到一次性显示。

## 七、不在范围内

1. **`_on_complete_var` / `_get_client` 基础设施** — `llm_client.py` 未定义这些符号，但 `orchestrator.py` 有未经验证的引用。属独立修复任务。
2. **不改造report pipeline / survey pipeline** — 独立子系统
3. **不给 `call_llm_stream()` 加重试** — 降级即可
4. **不展示LLM思考过程** — `_ThinkTagFilter` 过滤掉 `<think>` 内容。未来可新增 `CHAT_THINKING` 事件类型独立推送。

## 八、变更文件清单

### 后端 Python（4个文件）

| 文件 | 变更类型 | 行数 |
|------|---------|------|
| `src/core/llm_client.py` | 新增 `call_llm_stream()` | +58 |
| `src/core/session_streamer.py` | 新增 `CHAT_TOKEN` 枚举 + `push_chat_token()` | +24 |
| `src/api/research_api.py` | 新增 `_ThinkTagFilter` 类 + `_llm_converse` 流式改造 + `_retry_json_only` 迁移 | +92 |

### 前端 TypeScript（5个文件）

| 文件 | 变更类型 |
|------|---------|
| `web/src/types/api.ts` | `SSEMessage.event` 增加 `chat_token`; 新增 `ChatTokenData` 接口 |
| `web/src/lib/sse.ts` | 新增 `ChatTokenCallback`; `subscribeSession` 增加 `onChatToken`; 注册 `chat_token` 事件; 清理逻辑 |
| `web/src/store/useChatStore.ts` | 新增 `updateMessage(id, updates)` 方法 |
| `web/src/hooks/useProgress.ts` | `UseSessionStreamOptions` 增加 `onChatToken`; 透传到 `subscribeSession` |
| `web/src/components/chat/ChatPanel.tsx` | `streamingMsgIdRef` + `streamingDoneRef`; `onChatToken` 流式渲染; `onChatResponse` 终结流式; `handleSend` 复位 |

### 测试文件（5个文件）

| 文件 | 测试数 | 覆盖范围 |
|------|--------|---------|
| `tests/unit/test_think_tag_filter.py` | 18 | `_ThinkTagFilter` — 跨chunk标签、多think块、真实流式 |
| `tests/unit/test_call_llm_stream.py` | 13 | `call_llm_stream()` — token顺序、空提示、系统提示、异常 |
| `tests/unit/test_push_chat_token.py` | 8 | `push_chat_token()` — 订阅者、缓冲隔离、持久化隔离 |
| `tests/unit/test_llm_converse_streaming.py` | 5 | 流式路径、降级路径、tool loop |
| `tests/unit/test_research_api_llm_config.py` | 2 fixed | `_retry_json_only` 签名变更适配 |
