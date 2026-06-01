# 会话状态腐败 Bug 修复计划

> **影响范围**：`src/api/research_api.py`、`src/core/dialogue/state_machine.py`、`web/src/store/useResearchStore.ts`、`web/src/hooks/useResearch.ts`、`web/src/components/chat/ChatPanel.tsx`
>
> **创建日期**：2026-05-06
>
> **状态**：待审阅

---

## 一、Bug 现象

### Bug 1：框架确认被跳过，Agent 在用户未确认时自动启动

> 用户表达 "形成一个竞争格局的分析框架" 后，系统在输出框架文案的同时启动了 Agent Sessions，没有等待用户确认框架。

### Bug 2：取消研究后发送消息，自动新建会话，丢失全部历史

> 用户取消执行中的研究任务后，再次发送消息，系统创建了一个全新的会话，原有的对话历史、上下文全部丢失。

---

## 二、根因分析

### 2.1 三层状态管理不一致（核心架构问题）

系统有三个独立的状态管理层，彼此**不同步**：

| 层级 | 实体 | 位置 | 写入点 | 读取点 |
|------|------|------|--------|--------|
| 状态机 | `ConversationStateMachine.state` | `state_machine.py` | 4处 `.transition()` | 从未用于流控 |
| 会话模式 | `session["mode"]` | `research_api.py` | `_start_execution`, `_enter_framework_mode` 等 | `_handle_user_message` 路由 |
| 步骤号 | `session["current_step"]` | `research_api.py` | `_start_execution` 等 | 前端 `useResearch.ts` + 后端路由 |

**状态机定义合法转移**（`state_machine.py:40-78`）：
```
UNDERSTANDING → CLARIFYING → FRAMEWORK_CONFIRM → EXECUTING
```

**实际调用情况**（`research_api.py`，搜索 `.transition(`）：

| 行号 | 上下文 | 目标状态 | 是否合法 |
|------|--------|----------|----------|
| 855 | `_start_execution` | EXECUTING | **非法**（当前=UNDERSTANDING） |
| 1863 | `pause_research` | PAUSED | **非法**（当前=UNDERSTANDING） |
| 1895 | `resume_research` | EXECUTING | **非法**（当前=UNDERSTANDING） |
| 1938 | `cancel_research` | CANCELLED | **非法**（当前=UNDERSTANDING） |

**结论**：`ConversationStateMachine` 的全部 4 次 `.transition()` 调用都是非法转移，异常被 `try-except` 吞掉（仅打 warning），之后代码继续执行不受影响。**状态机完全失效，从未起过流控作用。**

### 2.2 Bug 1 触发链（框架 → Agent 自动执行）

```
前提条件：会话 ses_e129a84f 处于腐败状态
  ├── mode = "research"           ← _start_execution 的残留
  ├── paused = True               ← 某次 pause 操作设置
  ├── current_step = 6            ← _start_execution 的残留
  ├── state_machine = UNDERSTANDING ← 从未被过渡（过渡全都非法失败）
  └── research_result 存在，status ≠ "paused" 开头

用户输入 "形成一个竞争格局的分析框架" → POST /api/v1/research/interact
  │
  ├── [research_api.py:282] _handle_user_message(session_id, user_input)
  │   ├── mode = "research"
  │   ├── [307] _should_start_execution → False  (mode ≠ framework)
  │   └── [315] 进入 mode == "research" 分支
  │       ├── [318-321] is_actually_running = True
  │       │   (research_result存在 AND current_step=6 AND status≠paused)
  │       ├── [323] session.get("paused") = True → 跳过 stall guard
  │       │
  │       ├── [328] ★ 日志 "User message during research: 形成一个竞争格局的分析框架"
  │       │
  │       ├── [329-330] paused=True → resume_research(session_id)
  │       │   ├── [state_machine.py:110] transition(EXECUTING)
  │       │   │   ★ 非法转移 UNDERSTANDING → EXECUTING
  │       │   │   ★ 日志 "State transition to EXECUTING failed"
  │       │   ├── [1899] session["paused"] = False
  │       │   └── [1913-1919] ★★★ asyncio.create_task(executor.execute(...))
  │       │                   ← Agent 在此被派发，无任何确认门
  │       │
  │       ├── [331-333] _llm_converse() → LLM 生成框架文案
  │       │   └── LLM 返回 action="enter_framework", 框架内容
  │       │
  │       └── [344-349] return { mode: "research", step: 6, message: 框架文案, ... }
  │           ★ LLM 的 action 字段被完全忽略
  │           ★ 返回 mode="research", step=6 → 前端触发
  │
  └── [前端 useResearch.ts:427-443]
      if (mode === 'research' && data.step === 6) {
          setStatus('running');          ← 前端也自动进入执行模式
          setStep(6, undefined);
      }
```

**关键故障点**：

| # | 位置 | 问题 |
|---|------|------|
| 1 | `research_api.py:329-330` | 用户发送消息到 research 模式的会话时，**无条件检查并调用 `resume_research`**，不判断用户意图 |
| 2 | `research_api.py:1913-1919` | `resume_research` **无条件启动 executor**，无确认门控 |
| 3 | `research_api.py:344-348` | research 模式返回时 **忽略 LLM 返回的 `action` 字段**，始终返回 `mode="research", step=6` |
| 4 | `useResearch.ts:427-443` | 前端收到 `mode="research", step=6` 时**自动进入执行模式**，无条件信任后端 |

### 2.3 Bug 2 触发链（取消后新建会话，丢失历史）

```
用户取消研究 → 前端 handleCancel()
  │
  ├── [ChatPanel.tsx:173-176]
  │   if (taskId) {
  │       await api.cancelResearch(taskId);   ← 调后端 /cancel
  │       reset();                             ← 重置前端状态
  │   }
  │
  ├── [useResearchStore.ts:113-119] reset():
  │   └── set({ taskId: null, sessionId: null, ... })  ★ sessionId 被清空
  │   └── const newId = nanoid()
  │   └── useSessionStore.createSession(newId)          ★ 创建新本地空会话
  │
  └── [后端 cancel_research, research_api.py:1929-1963]
      ├── session["paused"] = False
      ├── session["status"] = "cancelled"
      └── ★ mode 未重置 (仍为 "research")
      └── ★ current_step 未重置 (仍为 6)
      └── ★ state_machine → transition(CANCELLED) 非法失败，吞掉异常

用户发送下一条消息 → 前端 handleSend()
  │
  ├── [ChatPanel.tsx:125]
  │   if (sessionId && (currentStep === null || currentStep === 0)) {
  │       sendMessage(text);      ← sessionId=null → 条件为 false
  │   } else {
  │       startResearch(text);    ← ★★★ 走入此分支，创建全新会话
  │   }
  │
  └── 旧会话 ses_e129a84f 及其全部对话历史被遗弃
```

**关键故障点**：

| # | 位置 | 问题 |
|---|------|------|
| 5 | `useResearchStore.ts:114-119` | `reset()` 将 `sessionId` 设为 null 并**立即创建新空会话**，导致原有会话引用丢失 |
| 6 | `ChatPanel.tsx:137` | `handleSend` 中 `!sessionId` 时无条件走 `startResearch` 创建新会话，不尝试恢复旧会话 |
| 7 | `research_api.py:1929-1963` | `cancel_research` **不清除** `mode`、`current_step`、`research_result` 等残留字段，使会话永久处于腐败状态 |

### 2.4 前端 `sendMessage` 的自动执行路径

`useResearch.ts:427-443` 中存在**三条自动进入执行**的路径：

```typescript
// 路径 A — sendMessage 响应 (line 427-443)
} else if (mode === 'research' && data.step === 6) {
    setStatus('running');    // 自动执行

// 路径 B — handleOptionSelect 响应 (line 486-499)
} else if (mode === 'research' && data.step === 6) {
    setStatus('running');    // 自动执行

// 路径 C — quickStartResearch 响应 (line 93-103)
} else {
    setStatus('running');    // 自动执行 (legacy 兼容)
```

**问题**：路径 A 和 B 对 `mode === 'research' && data.step === 6` 的信任是**盲目的**——不检查是否经过了确认流程。一旦后端因状态腐败返回这个组合，前端就跳过了所有确认步骤。

---

## 三、修订方案

### 3.1 原则

1. **最小侵入**：优先修复逻辑漏洞，不重写架构
2. **治本优先**：先修腐败的根源（会话清理），再修腐败的后果（自动执行路径）
3. **向后兼容**：`/template` 快速通道保留参数配置→确认→执行的正常流程
4. **渐进式**：分阶段提交，每阶段独立可验证

### 3.2 阶段一：阻断异常执行路径（后端）

#### 3.2.1 `_handle_user_message` research 分支 —— 处理 LLM action 字段

**文件**：`src/api/research_api.py`，行 315-349

**现状**：
```python
return {"session_id": session_id, "step": session.get("current_step", 6),
        "mode": "research",
        "status": "running",
        "message": conv_result.get("message", ""),
        "suggestions": conv_result.get("suggestions", []),
        "next_step": "continue_research"}
```

**问题**：LLM 返回的 `action` 字段被忽略。如果 LLM 判定为 `enter_framework`，框架文案被当作普通消息返回，`mode` 仍为 `research`。

**修改**：
```python
action = conv_result.get("action", "continue_chat")

# If LLM determined this should enter framework mode,
# honor that decision instead of staying in stale research mode
if action in ("enter_framework", "start_execution"):
    # Clean up stale research state, switch to framework
    session["mode"] = "chat"
    context = session.get("research_context", {})
    if conv_result.get("topic"):
        context["topic"] = conv_result["topic"]
    if conv_result.get("directions"):
        context["directions"] = conv_result.get("directions", [])
    session["research_context"] = context
    return await self._enter_framework_mode(session_id, user_input)

return {"session_id": session_id, "step": session.get("current_step", 6),
        "mode": "research",
        "status": "running",
        "message": conv_result.get("message", ""),
        "suggestions": conv_result.get("suggestions", []),
        "next_step": "continue_research"}
```

#### 3.2.2 `resume_research` —— 添加确认门控

**文件**：`src/api/research_api.py`，行 1886-1927

**问题**：`resume_research` 由 `_handle_user_message` 的 `paused` 检查无条件触发（行 329-330），不区分用户意图是"恢复"还是"发新消息"。

**修改方案 A（推荐）**：从 `_handle_user_message` research 分支中**移除自动 resume**。

```python
# 行 329-330 删除：
# if session.get("paused"):
#     await self.resume_research(session_id)
```

`resume_research` 只保留给 API 端点 `/resume` 显式调用。

**修改方案 B（保守）**：保留 auto-resume 但仅当用户消息是恢复意图时触发。

```python
# 行 329-330 替换为：
if session.get("paused"):
    resume_keywords = ["继续", "resume", "恢复", "接着", "continue"]
    if any(kw in user_input.lower() for kw in resume_keywords):
        return await self.resume_research(session_id)
    else:
        # User is asking a new question → treat as new conversation
        session["paused"] = False
        session["mode"] = "chat"
        session["current_step"] = 0
        return await self._handle_chat_mode(session_id, user_input)
```

#### 3.2.3 `cancel_research` —— 清理腐败字段

**文件**：`src/api/research_api.py`，行 1929-1963

**现状**：取消后 `mode`、`current_step`、`research_result` 不清理。

**修改**：在 `cancel_research` 末尾增加清理：

```python
# 在 session["status"] = "cancelled" 之后添加：
session["mode"] = "chat"
session["current_step"] = 0
if session.get("research_result"):
    session.pop("research_result")
```

#### 3.2.4 `pause_research` —— 同步更新

**文件**：`src/api/research_api.py`，行 1854-1884

同样的残留问题。暂停后 `mode` 应为 `research`（保持），但其他字段不需要改。主要修复点在于 `resume_research` 的门控（3.2.2 已覆盖）。

### 3.3 阶段二：前端状态管理修复

#### 3.3.1 `reset()` —— 不清空 sessionId

**文件**：`web/src/store/useResearchStore.ts`，行 113-119

**现状**：
```typescript
reset: () => {
    const cleared = { taskId: null, sessionId: null, ... };
    set(cleared);
    const newId = nanoid();
    useSessionStore.getState().createSession(newId);
}
```

**问题**：`sessionId: null` 导致后续消息走 `startResearch`（新建会话）。`createSession(newId)` 注释写"避免订阅恢复旧状态"，但副作用是丢失会话引用。

**修改**：
```typescript
reset: () => {
    const cleared = {
        taskId: null,
        progress: 0,
        phases: [],
        status: 'idle' as const,
        currentStep: null,
        stepOptions: null,
        parameterConfig: null,
        summary: null,
        statistics: null,
        viewingResearch: false,
        // sessionId 不清空，保持与当前后端会话的连接
    };
    set(cleared);
    // 不再创建新空会话，保留当前会话的引用
},
```

> **注意**：删除 `createSession(newId)` 后需验证订阅恢复行为是否正常。如果原有 Bug 是因为订阅恢复了被 reset 的旧状态，需要在 `useSessionStore.subscribe` 的回调中增加判断逻辑。

#### 3.3.2 `handleSend` —— 发送消息前检查会话有效性

**文件**：`web/src/components/chat/ChatPanel.tsx`，行 72-159

**现状**：`!sessionId` 时直接 `startResearch`，不尝试复用后端已有会话。

**修改**：
```typescript
// 在行 125 的 if/else 之前添加：
// 如果有 research 状态残留（status === 'running' 但实际已取消），先清理
if (status === 'running' && taskId) {
    try { await api.cancelResearch(taskId); } catch {}
    useResearchStore.getState().setStatus('idle');
    useResearchStore.getState().setPhases([]);
    useResearchStore.getState().setProgress(0);
    addMessage({
        id: nanoid(),
        role: 'assistant',
        content: 'Previous research was cancelled. You can continue the conversation.',
        timestamp: new Date().toISOString(),
    });
}
```

> 这段代码已存在（行 75-86），但只在 `status === 'running'` 时触发。需确认 `currentStep === 6` 且 `status === 'idle'` 的情况也能被捕获。

#### 3.3.3 `sendMessage` —— 收紧自动执行的门控条件

**文件**：`web/src/hooks/useResearch.ts`，行 427-443, 486-499

**问题**：`mode === 'research' && data.step === 6` 就自动进入执行，不检查是否经过确认。

**修改**：增加一个显式的 `confirmed` 标记：

```typescript
// 后端在 _start_execution 返回中增加 confirmed: true
// 前端仅在 confirmed === true 时自动进入执行

} else if (mode === 'research' && data.step === 6 && data.confirmed === true) {
    setTaskId(data.session_id);
    setStatus('running');
    setStep(6, undefined);
    ...
}
```

对应**后端** `_start_execution` 返回增加 `"confirmed": True`：

```python
return {
    "session_id": session_id,
    "task_id": session_id,
    "step": 6,
    "mode": "research",
    "status": "executing",
    "confirmed": True,           # ← 新增
    "message": ...,
    "final_plan": final_plan,
    "next_step": "execute",
}
```

而 research 模式 handler 的返回**不包含** `confirmed` 字段，前端因此不会自动执行。

### 3.4 阶段三：状态机修复（结构性修复，可选）

> 此阶段为结构性改进，不影响 Bug 修复效果，可在阶段一二完成后迭代。

#### 3.4.1 填补缺失的过渡调用

在 LLM 驱动的对话流程中增加状态机过渡：

| 调用点 | 文件 | 过渡 |
|--------|------|------|
| LLM 返回 `action="enter_framework"` | `research_api.py:_handle_chat_mode` | `UNDERSTANDING → CLARIFYING` |
| `_enter_framework_mode` | `research_api.py:805` | `CLARIFYING → FRAMEWORK_CONFIRM` |
| `_should_start_execution` 返回 True | `research_api.py:307` | `FRAMEWORK_CONFIRM → EXECUTING` |

#### 3.4.2 用状态机驱动流控

将 `session["mode"]` 的读写替换为从状态机派生：

```python
def _derive_mode_from_state(self, state: ConversationState) -> str:
    mapping = {
        ConversationState.UNDERSTANDING: "chat",
        ConversationState.CLARIFYING: "chat",
        ConversationState.FRAMEWORK_CONFIRM: "framework",
        ConversationState.EXECUTING: "research",
        ConversationState.PAUSED: "research",
        ConversationState.PREVIEWING: "research",
        ConversationState.COMPLETED: "chat",
        ConversationState.CANCELLED: "chat",
    }
    return mapping.get(state, "chat")
```

此部分为可选改进，核心修复不需要。

---

## 四、依赖关系

```
                    ┌─────────────────────────┐
                    │ 3.2.3 cancel_research    │ ← 无依赖，可独立实施
                    │ 清理腐败字段              │
                    └───────────┬─────────────┘
                                │ 消除腐败状态源
                    ┌───────────┴─────────────┐
                    │ 3.2.1 research 分支      │
                    │ 处理 LLM action 字段      │
                    └───────────┬─────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
    ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
    │ 3.2.2         │   │ 3.3.1         │   │ 3.3.3         │
    │ resume 门控    │   │ reset 修复     │   │ confirmed 标记 │
    └───────────────┘   └───────┬───────┘   └───────────────┘
                                │
                        ┌───────┴───────┐
                        │ 3.3.2         │
                        │ handleSend 修复 │
                        └───────────────┘

[可选阶段]
3.4.1 ──→ 3.4.2  (状态机修复，依赖 3.2 完成后稳定)
```

---

## 五、验证方案

### 5.1 Bug 1 验证

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 启动系统，进入任意研究对话 | |
| 2 | 使研究进入 paused 状态（手动暂停或模拟） | 后端 `paused=True` |
| 3 | 在聊天框输入非恢复类消息，如"分析竞争格局" | 系统进入 framework 确认流程，**Agent 不启动** |
| 4 | 点击"确认开始" | Agent 启动执行 |
| 5 | 检查日志 | 无 "State transition ... failed" warning |

### 5.2 Bug 2 验证

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 启动研究执行 | |
| 2 | 取消研究 (`/cancel`) | 研究取消，对话保留 |
| 3 | 输入新消息 | **仍在同一会话**，历史可见 |
| 4 | 检查 URL/会话 ID | session ID 未变化 |

### 5.3 回归验证

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | `/template competitive_analysis` | 快速模板正常 |
| 2 | 正常对话 → LLM 判定 `enter_framework` → 确认开始 | 完整流程正常 |
| 3 | 暂停 → 显式恢复 (`/resume` 或按钮) | 恢复正常 |
| 4 | 多次取消再发消息 | 每次保持同一会话 |
| 5 | 并发两个会话分别操作 | 互不干扰 |

---

## 六、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| `reset()` 不清 sessionId 导致前端状态混乱 | 前端显示错乱 | 验证 `useSessionStore.subscribe` 回调不会恢复被 reset 的旧状态 |
| `resume_research` 移除 auto-resume 后用户无法通过普通消息恢复 | 用户体验下降 | 在 `_handle_user_message` 中对恢复关键词做检测（方案 B） |
| `confirmed` 标记导致旧前端版本不兼容 | API 兼容性 | 前端做兼容处理：无 `confirmed` 时按现有逻辑（视为需确认） |
| 状态机引入后与现有 session 持久化冲突 | 状态不一致 | 阶段三独立迭代，可回滚 |

---

## 七、变更清单

### 后端 (`src/api/research_api.py`)

| 行号 | 变更 | 所属修复 |
|------|------|----------|
| 329-330 | 删除或条件化 `resume_research` 调用 | 3.2.2 |
| 344-349 | 增加 LLM `action` 字段处理（`enter_framework` 切换） | 3.2.1 |
| 937-946 | `_start_execution` 返回增加 `"confirmed": True` | 3.3.3 |
| 1942-1943 后 | `cancel_research` 增加 `mode`/`current_step` 清理 | 3.2.3 |

### 前端

| 文件 | 行号 | 变更 | 所属修复 |
|------|------|------|----------|
| `useResearchStore.ts` | 113-119 | `reset()` 保留 `sessionId`，删 `createSession` | 3.3.1 |
| `useResearch.ts` | 427-443, 486-499 | `confirmed` 字段门控 | 3.3.3 |
| `ChatPanel.tsx` | 72-86 | 扩大残留状态清理的触发条件 | 3.3.2 |

### 可选

| 文件 | 行号 | 变更 | 阶段 |
|------|------|------|------|
| `research_api.py` | 417-419 | 增加 `CLARIFYING` 过渡 | 3.4.1 |
| `research_api.py` | 822 后 | 增加 `FRAMEWORK_CONFIRM` 过渡 | 3.4.1 |
| `state_machine.py` | 40-78 | 从 UNDERSTANDING 增加直接到 FRAMEWORK_CONFIRM 的过渡（或保留严格要求） | 3.4.1 |
