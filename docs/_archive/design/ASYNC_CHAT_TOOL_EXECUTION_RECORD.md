# 对话工具异步执行 + SSE 进度推送 — 实施记录

**目标：** 将 Zensers 对话阶段的工具调用从同步阻塞改为异步非阻塞，复用现有 SSE 推送机制。实施过程中修复了多个衍生问题。

---

## 最终改动清单

### 后端（2 文件）

#### `src/core/progress_streamer.py`
- 新增 `SSEEventType.CHAT_RESPONSE = "chat_response"` 事件类型
- 新增 `ProgressStreamer.push_chat_response()` 类方法
- 新增便捷函数 `push_chat_response()`
- 导出 `__all__` 中加入 `push_chat_response`

#### `src/api/research_api.py`

**ConversationToolSet 类：**
- 新增 `TOOL_TIMEOUTS` 字典：web_search=45s, news_search=45s, scrape_url=60s, get_current_datetime=5s
- 提取 `_get_handler()` 方法
- `execute_tool()` 增加 `asyncio.wait_for` 单次超时保护

**ResearchAPI 类：**
- 新增 `_background_tasks` / `_background_task_gen` — 代数计数器追踪后台任务
- 新增 `_check_cancelled()` — 关键步骤间检查取消状态
- 新增 `_cancel_existing_task()` — 新请求自动取消旧后台任务
- 新增 `_do_execute_tool_background()` — 后台执行工具 + LLM 合成 + SSE 推送

**_llm_converse() 改造：**
- 同步路径（无工具）：LLM 直接返回，`status: "done"`
- 异步路径（需工具）：启动后台任务，立即返回 `status: "processing"`
- 单次 LLM 调用超时 120s
- `msg["role"]` → `msg.get("role", "user")` 防 KeyError（持久化数据旧格式兼容）

**_handle_chat_mode()：**
- 新增 `status: "processing"` 分支处理

**_handle_user_message()：**
- 新增 `mode == "research"` 分支：暂停时自动 `resume_research()`，消息走 `_llm_converse` 分析
- 加 try/except 保护，异常时返回友好提示不影响研究任务

**Bug 修复——SSE 事件顺序：**
- `push_chat_response` 必须在 `complete_task` 之前调用，否则 SSE generator 遇到 COMPLETE 就 break，`chat_response` 被吞掉

**Bug 修复——complete_task 误杀研究任务：**
- 对话工具后台执行完成时只调 `push_chat_response`，不再调 `complete_task`
- `complete_task` 只应由 `ResearchExecutor` 在研究真正完成时调用

### 前端（5 文件）

#### `web/src/types/api.ts`
- 新增 `ChatResponseData` 接口
- `SSEMessage.event` 增加 `chat_response` | `heartbeat` | `connected` | `message` 类型
- `ChatMessage` 增加 `metadata?: Record<string, any>` 字段

#### `web/src/lib/sse.ts`
- EventSource 从仅 `onmessage` 改为 `addEventListener` 监听所有命名事件
- 新增事件类型：`progress`, `phase_start`, `phase_complete`, `complete`, `error`, `chat_response`, `heartbeat`, `connected`

#### `web/src/lib/api.ts`
- 新增 `pauseResearch()` / `resumeResearch()` 方法

#### `web/src/hooks/useProgress.ts`
- 新增 `UseProgressOptions` 接口和 `onChatResponse` 回调
- 支持 `chat_response` 事件
- **Bug 修复：** `useCallback` → `useRef` 存储回调，防止 inline 函数导致 `useEffect` 每秒重跑创建新 SSE 连接

#### `web/src/components/chat/ChatPanel.tsx`
- `useProgress` 使用 `sessionId || taskId`（对话阶段 taskId 为 null，用 sessionId 连 SSE）
- `useProgress` 传入 `onChatResponse` 回调处理 SSE 结果
- `handleSend` 新增暂停/中断研究恢复路径：任意消息自动 `sendChatMessage` + 设置 running
- `handleSend` 新增 `processing` 返回处理：添加 "🔍 正在搜索..." 消息

#### `web/src/components/chat/ChatMessage.tsx`
- processing 消息显示旋转动画圈（`animate-spin`）

---

## 防卡死体系（5 层，无硬超时）

| 防护层 | 触发条件 | 效果 |
|--------|----------|------|
| 单次工具超时 (45s/60s) | 网络请求卡住 | 返回 error 给 LLM → LLM 兜底回复 |
| 单次 LLM 超时 (120s) | LLM 调用卡死 | 外层 catch 推兜底回复，不中断整体任务 |
| 工具轮次限制 (1轮) | LLM 反复要工具 | 后台只执行一轮工具 + 一轮 LLM 合成 |
| 代数计数器 | 用户连发多请求 | 新请求自动取消旧任务，finally 不会误删新任务 |
| 用户取消检查点 | 用户点击取消 | 3 个检查点检测 cancelled 状态即停止 |

---

## 实施中修复的问题

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | `start_phase()` TypeError | 便捷函数用 `**kwargs`，调用方传了位置参数 | 加 `description=` 关键字 |
| 2 | SSE 每秒重连几十次 | `useCallback` 依赖每次渲染变化的 inline 函数 | 改为 `useRef` |
| 3 | `_llm_converse` KeyError | `conversation_history` 旧格式缺 `role` 字段 | `msg.get("role", "user")` |
| 4 | research 模式 500 | `_llm_converse` 无 try/except | 加异常保护 |
| 5 | SSE chat_response 被吞 | `complete_task` 先入队，generator 遇到 COMPLETE 就 break | 交换顺序 |
| 6 | 研究任务被误标完成 | `complete_task` 在对话工具回复中调用 | 移除 `complete_task` 调用 |
| 7 | 对话阶段 SSE 不工作 | `useProgress(taskId)` 中 taskId=null 跳过订阅 | 用 `sessionId \|\| taskId` |
| 8 | processing 无视觉反馈 | 只加了普通文本消息 | 加旋转动画 + 搜索图标 |
