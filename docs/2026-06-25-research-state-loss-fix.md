# 研究任务状态丢失与控制失效修复方案

> 日期: 2026-06-25
> 状态: 已实施（Fix 1-5），待实施（Fix 6-8）
> 影响: 研究执行阶段 (step=6, mode=research)

---

## 1. 问题描述

用户在研究执行过程中，前端状态意外丢失（status 从 `running` 变为 `idle`），导致：

1. **停止按钮消失** — UI 无法暂停或取消研究
2. **后端任务失控** — 研究任务持续运行，但前端无法感知也无法控制
3. **状态不一致** — 后端 session 为 `paused`/`running` + `mode=research`，前端为 `idle`，两端事实分裂

---

## 2. 根因分析

### Bug 1（主因）: `handleCancel` 暂停后错误地设置 `idle` 状态 ✅ 已修复

**文件**: `web/src/components/chat/ChatPanel.tsx`

**修复前代码** (已不存在于当前代码库):

```typescript
const handleCancel = async () => {
  if (taskId && status === 'running') {
    try { await api.pauseResearch(taskId); } catch {}
    useResearchStore.getState().setStatus('idle');  // ← BUG: 应为 'paused'
    // ...
    return;
  }
  // ...
  if (taskId) {
    try { await api.cancelResearch(taskId); } catch {}
    clearResearch();
  }
};
```

**当前代码** (`ChatPanel.tsx:259-327`):

```typescript
const handleCancel = async () => {
  if (taskId && status === 'running') {
    try {
      await api.pauseResearch(taskId);
      useResearchStore.getState().setStatus('paused');  // ✅ 已修正
    } catch (e) {
      console.error('Failed to pause research:', e);
      addMessage({ /* 暂停失败提示 */ });
      return;  // ✅ 失败时保持 running，不降级
    }
    addMessage({ /* 暂停成功提示 */ });
    return;
  }
  if (taskId && status === 'paused') {  // ✅ 新增分支：暂停→取消
    try {
      await api.cancelResearch(taskId);
    } catch (e) {
      console.error('Failed to cancel research:', e);
      addMessage({ /* 取消失败提示 */ });
      return;  // ✅ 失败时保持 paused，不降级
    }
    clearResearch();
    addMessage({ /* 取消成功提示 */ });
    return;
  }
  // ... 其余分支不变
};
```

**原问题**:

- 用户点击停止按钮 → 调用 `api.pauseResearch(taskId)` → 后端进入 `paused` 状态
- 但前端立即 `setStatus('idle')` 而非 `setStatus('paused')`
- `idle` 状态下: `isRunning = status === 'running'` → false → 停止按钮不显示
- `idle` 状态下: 轮询条件 `store.status !== 'running' && store.status !== 'paused'` → 轮询不启动
- **前端与后端状态彻底分裂，用户无法通过 UI 恢复或取消**

**更严重的连锁问题**:

如果 `pauseResearch` API 调用失败（网络错误等），原代码 `catch {}` 吞掉错误，`setStatus('idle')` 仍然执行。此时后端未被暂停，前端已切到 `idle`，**后端任务完全失控**。

---

### Bug 2: SSE 事件注册缺少 `paused`/`cancelled`/`resumed` 事件类型 ✅ 已修复

**文件**: `web/src/lib/sse.ts`

**修复前代码** (已不存在于当前代码库):

```typescript
const namedEvents = [
  'progress', 'phase_start', 'phase_complete', 'complete',
  'error', 'chat_response', 'heartbeat', 'connected'
];
// ← 缺少: 'paused', 'cancelled', 'resumed'
```

**当前代码** (`sse.ts:109`):

```typescript
const namedEvents = ['progress', 'phase_start', 'phase_complete', 'complete', 'error', 'chat_response', 'heartbeat', 'connected', 'paused', 'cancelled', 'resumed'];
// ✅ 已补全
```

**后端对应定义** (`src/core/progress_streamer.py:33-43`):

```python
class SSEEventType(str, Enum):
    PROGRESS = "progress"
    PHASE_START = "phase_start"
    PHASE_COMPLETE = "phase_complete"
    ERROR = "error"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    RESUMED = "resumed"
    CHAT_RESPONSE = "chat_response"
```

**原问题**:

后端通过 `ProgressStreamer.pause_task()` / `cancel_task()` / `resume_task()` 发送命名 SSE 事件（格式为 `event: paused\ndata: {...}`）。SSE 规范中，命名事件必须通过 `addEventListener(eventType, handler)` 注册才能接收，`onmessage` 只接收无 `event:` 字段的默认事件。

由于前端 `namedEvents` 列表缺少这三个事件类型，`EventSource` 不会为它们注册监听器，事件被静默丢弃。

**影响**:

| 后端事件 | 触发场景 | 修复前前端是否收到 | 修复后 |
|---------|---------|----------------|--------|
| `paused` | 用户/系统暂停研究 | 否 | ✓ |
| `cancelled` | 用户取消研究 | 否 | ✓ |
| `resumed` | 用户恢复研究 | 否 | ✓ |

---

### Bug 3: `useProgress` SSE handler 和轮询路径缺少 `paused`/`cancelled` 处理 ✅ 已修复

**文件**: `web/src/hooks/useProgress.ts`

#### 3a. SSE handler 缺少 `paused`/`resumed` 分支 ✅ 已修复

**修复前代码** (已不存在于当前代码库):

```typescript
switch (message.event) {
  case 'chat_response': ...
  case 'progress': ...
  case 'phase_start': ...
  case 'phase_complete': ...
  case 'complete': ...
  case 'error': ...
  case 'cancelled':
    setStatus('idle');
    break;
  case 'agent_message': ...
  // ← 缺少 case 'paused'
  // ← 缺少 case 'resumed'
}
```

**当前代码** (`useProgress.ts:87-133`):

```typescript
switch (message.event) {
  // ... 其他 case 不变
  case 'cancelled':
    setStatus('idle');
    break;
  case 'paused':        // ✅ 已添加
    setStatus('paused');
    break;
  case 'resumed':       // ✅ 已添加
    setStatus('running');
    break;
  case 'agent_message': ...
}
```

#### 3b. `applyStatusToStore` 缺少 `cancelled` 处理 ✅ 已修复

**修复前代码** (已不存在于当前代码库):

```typescript
function applyStatusToStore(status, progress, store, phases) {
  switch (status) {
    case 'completed': ...
    case 'error': ...
    case 'running': ...
    case 'paused': ...
    // ← 缺少 case 'cancelled'
  }
}
```

**当前代码** (`useProgress.ts:51-53`):

```typescript
case 'cancelled':       // ✅ 已添加
  store.setStatus('idle');
  break;
```

---

### 附 Bug 4: `view_report` 可强制覆盖 `running` 状态 ✅ 已修复

**文件**: `web/src/hooks/useResearch.ts`

**修复前代码** (已不存在于当前代码库):

```typescript
if (optionId === 'view_report') {
  const rs = useResearchStore.getState();
  if (rs.status !== 'completed') {
    rs.setStatus('completed');  // ← 研究运行中点 view_report 会强制设 completed
  }
}
```

**当前代码** (`useResearch.ts:519-523`):

```typescript
if (optionId === 'view_report') {
  const rs = useResearchStore.getState();
  if (rs.status !== 'completed' && rs.status !== 'running' && rs.status !== 'paused') {
    rs.setStatus('completed');  // ✅ running/paused 状态下不覆盖
  }
  // ...
}
```

---

### 附 Bug 5: `ChatInput` 停止按钮在 `paused` 状态下不显示 ✅ 已修复

**文件**: `web/src/components/chat/ChatInput.tsx`

**修复前代码** (已不存在于当前代码库):

```typescript
const showStop = isLoading || (isRunning && !text.trim() && attachments.length === 0);
```

**当前代码** (`ChatInput.tsx:138`):

```typescript
const showStop = isLoading || ((isRunning || isPaused) && !text.trim() && attachments.length === 0);
// ✅ isPaused 已加入
```

**配套修改**:

- `ChatInputProps` 接口已添加 `isPaused?: boolean` (`ChatInput.tsx:34`)
- `ChatPanel.tsx:604` 已传入 `isPaused={status === 'paused'}`

---

## 3. 仍存在的问题（文档原版未覆盖）

### Bug 6（严重）: `cancelled` SSE 事件未触发连接关闭

**文件**: `web/src/lib/sse.ts:100`

**当前代码**:

```typescript
if (message.event === 'complete' || message.event === 'error') {
  this.close(taskId);
}
```

**问题**:

后端 `progress_streamer.py:597-602` 在发送 `cancelled` 事件后 break 并关闭 SSE 流:

```python
if message.event in (
    SSEEventType.COMPLETE.value,
    SSEEventType.ERROR.value,
    SSEEventType.CANCELLED.value,  # ← 后端在 cancelled 后也关闭流
):
    break
```

但前端 `handleSSEEvent` 只在 `complete`/`error` 时调用 `this.close(taskId)`，**`cancelled` 时不关闭**。

**后果**:

1. 后端发送 `cancelled` → 服务端关闭 SSE 流
2. 前端收到 `cancelled` 事件 → handler 设置 `status='idle'` ✓
3. 前端未调用 `this.close(taskId)` → EventSource 仍认为连接存活
4. 服务端关闭 → EventSource 触发 `onerror` → `notifyConnection(taskId, false)`
5. EventSource 自动重连 → 连接到已不存在的流 → 反复重连 + `onerror` 循环
6. `this.close()` 不会被调用，`connections` Map 中残留僵尸条目，回调也不会被清理

**修复方案**:

```typescript
// 修改前
if (message.event === 'complete' || message.event === 'error') {
  this.close(taskId);
}

// 修改后
if (message.event === 'complete' || message.event === 'error' || message.event === 'cancelled') {
  this.close(taskId);
}
```

---

### Bug 7（严重）: `restoreSession` 将 `paused` 状态降级为 `idle`

**文件**: `web/src/store/useSessionStore.ts:132-148`

**当前代码**:

```typescript
} else if (status === 'running' || status === 'reporting') {
  const interrupted = detail.interrupted;
  useSessionStore.getState().syncActive({
    status: interrupted ? 'paused' : 'running',
    // ...
  });
} else {
  // paused / analyzing / idle
  useSessionStore.getState().syncActive({
    status: 'idle',  // ← BUG: paused 被强制降为 idle
    currentStep: 0,  // ← BUG: paused 研究的 currentStep 应为 6
    mode: 'chat',    // ← BUG: paused 研究的 mode 应为 'research'
    // ...
  });
}
```

**问题**:

当后端返回 `status: 'paused'` 时，不匹配 `completed` 也不匹配 `running`/`reporting`，落入 else 分支，状态被设为 `idle`。

**后果**:

1. 用户从历史页面恢复暂停的研究 → `restoreSession` → 前端 `status='idle'`
2. 停止按钮不显示（`isRunning=false`, `isPaused=false`）
3. 轮询不启动（`status !== 'running' && status !== 'paused'`）
4. `currentStep=0` + `mode='chat'` → 研究进度 UI 消失
5. 用户无法通过 UI 恢复或取消研究，后端仍在 `paused` 状态

**修复方案**:

```typescript
} else if (status === 'paused') {
  useSessionStore.getState().syncActive({
    title: detail.title || detail.topic || 'Untitled',
    taskId: id,
    messages: msgs,
    status: 'paused',
    currentStep: 6,
    phases: detail.phases || [],
    progress: detail.progress || 0,
    agentMessages: detail.agent_messages || [],
    interrupted: true,
    language: detail.language || 'zh',
    mode: detail.mode || 'research',
  });
} else {
  // analyzing / idle / unknown
  useSessionStore.getState().syncActive({
    // ... 保持原逻辑
  });
}
```

---

### Bug 8（中等）: `api.resumeResearch()` 存在但从未被调用 — 恢复路径断裂

**文件**: `web/src/lib/api.ts:481-483`

**当前代码**:

```typescript
async resumeResearch(taskId: string): Promise<{ status: string; message: string }> {
  const { data } = await this.client.post(`/api/v1/research/${taskId}/resume`);
  return data;
}
```

**问题**:

全局搜索 `resumeResearch` 调用点：**零调用**。暂停后的恢复路径完全断裂。

暂停消息提示 "You can resume later or continue chatting"，但没有任何 UI 触发 `api.resumeResearch()`。

唯一相关路径是 history 页面的 `handleResumeResearch` (`app/history/[id]/page.tsx:71-75`)，但它只做 `sessionStorage.setItem` + 路由跳转，不调用 resume API。跳转后 `restoreSession` 又因 Bug 7 将 `paused` 降为 `idle`，恢复彻底失败。

**后端 resume API** (`research_api.py:2144-2171`) 已完整实现：清除暂停标志、唤醒引擎、发送 `resumed` SSE 事件、支持快照恢复。

**修复方案**:

需要在 `useResearch.ts` 或 `ChatPanel.tsx` 中添加恢复逻辑。建议在 `handleSend` 中检测：当 `status === 'paused'` 且用户输入非指令文本时，先调用 `api.resumeResearch(taskId)` 再发送消息。或在暂停状态下显示"恢复研究"按钮。

---

## 4. 影响范围

### 4.1 直接影响

| 场景 | Bug 1 | Bug 2 | Bug 3 | Bug 6 | Bug 7 | Bug 8 | 结果 |
|------|-------|-------|-------|-------|-------|-------|------|
| 用户点停止按钮 | ✓(已修) | - | - | - | - | - | 前端 paused，后端 paused ✓ |
| 后端自动暂停（SSE 断连） | - | ✓(已修) | ✓(已修) | - | - | - | 前端收到 paused 事件 ✓ |
| 后端取消研究 | - | ✓(已修) | ✓(已修) | ✗ | - | - | SSE 僵尸重连 |
| 轮询回退获取 cancelled | - | - | ✓(已修) | - | - | - | 前端 idle ✓ |
| 从历史恢复 paused 研究 | - | - | - | - | ✗ | ✗ | 前端 idle，无法恢复 |
| 暂停后恢复研究 | - | - | - | - | - | ✗ | 无 UI 路径调用 resume |

### 4.2 状态分裂矩阵

**Fix 1-5 修复后**，以下状态组合仍可能出错:

| 后端状态 | 前端状态 | 是否正确 | 原因 |
|---------|---------|---------|------|
| running | running | ✓ | 正常 |
| paused | paused | ✓ | Fix 1 修复后正常 |
| cancelled | idle | △ | 结果正确但 SSE 连接未关闭 (Bug 6) |
| paused | idle | ✗ | restoreSession 降级 (Bug 7) |
| running | idle | ✗ | Bug 7: restoreSession 对 paused→idle 后无法触发轮询恢复 |

---

## 5. 修复方案

### Fix 1: 修正 `handleCancel` 状态设置 ✅ 已实施

**文件**: `web/src/components/chat/ChatPanel.tsx:259-327`

**关键变更**:

1. `setStatus('idle')` → `setStatus('paused')` — 与后端状态一致
2. 暂停失败时保持 `running` 状态，不降级到 `idle`
3. 新增 `status === 'paused'` 分支 — 暂停状态下再点停止 → 取消研究
4. 取消失败时保持 `paused` 状态，不降级到 `idle`
5. 错误不再被 `catch {}` 静默吞掉

---

### Fix 2: SSE 事件注册补全 ✅ 已实施

**文件**: `web/src/lib/sse.ts:109`

`namedEvents` 已添加 `'paused', 'cancelled', 'resumed'`。

与后端 `SSEEventType` 枚举完全对齐:

| 后端事件 | 事件来源 | 状态 |
|---------|---------|------|
| progress | SSEEventType | ✓ |
| phase_start | SSEEventType | ✓ |
| phase_complete | SSEEventType | ✓ |
| complete | SSEEventType | ✓ |
| error | SSEEventType | ✓ |
| chat_response | SSEEventType | ✓ |
| heartbeat | ProgressStreamer.generate() 直接发送 | ✓ |
| connected | ProgressStreamer.generate() 直接发送 | ✓ |
| paused | SSEEventType | ✓ (已补全) |
| cancelled | SSEEventType | ✓ (已补全) |
| resumed | SSEEventType | ✓ (已补全) |

---

### Fix 3: `useProgress` SSE handler 和轮询路径补全 ✅ 已实施

**文件**: `web/src/hooks/useProgress.ts`

- 3a: `handleMessage` 已添加 `case 'paused'` 和 `case 'resumed'` (L122-127)
- 3b: `applyStatusToStore` 已添加 `case 'cancelled'` (L51-53)
- 3c: `cancelled` SSE 事件处理 `setStatus('idle')` 逻辑正确，无需改动

---

### Fix 4: `view_report` 添加 `running`/`paused` 状态保护 ✅ 已实施

**文件**: `web/src/hooks/useResearch.ts:521`

条件已从 `!== 'completed'` 改为 `!== 'completed' && !== 'running' && !== 'paused'`。

---

### Fix 5: `ChatInput` 停止按钮在 `paused` 状态下也显示 ✅ 已实施

**文件**: `web/src/components/chat/ChatInput.tsx`

- `ChatInputProps` 已添加 `isPaused?: boolean` (L34)
- `showStop` 已改为 `isLoading || ((isRunning || isPaused) && ...)` (L138)
- `ChatPanel.tsx:604` 已传入 `isPaused={status === 'paused'}`

---

### Fix 6: `cancelled` SSE 事件触发连接关闭 ❌ 待实施

**文件**: `web/src/lib/sse.ts:100`

**修改内容**:

```typescript
// 修改前
if (message.event === 'complete' || message.event === 'error') {
  this.close(taskId);
}

// 修改后
if (message.event === 'complete' || message.event === 'error' || message.event === 'cancelled') {
  this.close(taskId);
}
```

**理由**: 后端 `progress_streamer.py:597-602` 在 `cancelled` 后 break 关闭流，前端必须同步关闭 EventSource，否则产生僵尸重连循环。

---

### Fix 7: `restoreSession` 正确处理 `paused` 状态 ❌ 待实施

**文件**: `web/src/store/useSessionStore.ts:132-148`

**修改内容**:

在 `else if (status === 'running' || status === 'reporting')` 分支之后、`else` 分支之前，插入 `paused` 专用分支:

```typescript
} else if (status === 'paused') {
  useSessionStore.getState().syncActive({
    title: detail.title || detail.topic || 'Untitled',
    taskId: id,
    messages: msgs,
    status: 'paused',
    currentStep: 6,
    phases: detail.phases || [],
    progress: detail.progress || 0,
    agentMessages: detail.agent_messages || [],
    interrupted: true,
    language: detail.language || 'zh',
    mode: detail.mode || 'research',
  });
} else {
  // analyzing / idle / unknown
  useSessionStore.getState().syncActive({
    // ... 保持原逻辑不变
  });
}
```

**理由**: `paused` 状态的研究应保持 `currentStep=6`、`mode='research'`、`interrupted=true`，与 `running` 分支类似但 `status='paused'`。否则恢复后 UI 退回聊天模式，研究进度丢失。

---

### Fix 8: 添加暂停→恢复的 UI 路径 ❌ 待实施

**文件**: `web/src/hooks/useResearch.ts` 或 `web/src/components/chat/ChatPanel.tsx`

**问题**: `api.resumeResearch()` 已定义但零调用。暂停后无任何 UI 方式恢复研究。

**方案 A（推荐）: 在 `handleSend` 中自动恢复**

当 `status === 'paused'` 且用户发送新消息时，先调用 `api.resumeResearch(taskId)`:

```typescript
// handleSend 开头添加
if (status === 'paused' && taskId) {
  try {
    await api.resumeResearch(taskId);
    useResearchStore.getState().setStatus('running');
  } catch (e) {
    console.error('Failed to resume research:', e);
  }
}
```

**方案 B: 在暂停状态下显示"恢复研究"按钮**

在 `ChatPanel` 的 `renderStepContent` 或消息中添加恢复按钮，点击调用 `api.resumeResearch(taskId)` + `setStatus('running')`。

**方案 C: 修复 history 页面的 `handleResumeResearch`**

`app/history/[id]/page.tsx:71-75` 当前只做路由跳转，应先调用 `api.resumeResearch(meta.task_id)` 再跳转。

---

## 6. 修复验证清单

### 6.1 功能测试

| 编号 | 测试场景 | 预期结果 | 涉及 Fix | 状态 |
|------|---------|---------|----------|------|
| T1 | 研究运行中点停止按钮 | 前端 status 变为 `paused`，停止按钮仍显示 | Fix 1 | ✅ |
| T2 | 研究暂停后再点停止按钮 | 调用 cancelResearch，前端清空 | Fix 1 | ✅ |
| T3 | 研究暂停后等待 SSE `paused` 事件 | 前端收到事件并更新 | Fix 2+3 | ✅ |
| T4 | 后端取消研究，SSE 推送 cancelled | 前端收到事件，status 变为 `idle` | Fix 2+3 | ✅ |
| T5 | 后端恢复研究，SSE 推送 resumed | 前端收到事件，status 变为 `running` | Fix 2+3 | ✅ |
| T6 | SSE 断连后轮询回退获取 cancelled | 前端 status 变为 `idle` | Fix 3b | ✅ |
| T7 | pauseResearch API 失败 | 前端保持 `running`，显示错误消息 | Fix 1 | ✅ |
| T8 | 研究运行中点 view_report | status 保持 `running`，不被覆盖 | Fix 4 | ✅ |
| T9 | 研究暂停状态下停止按钮是否显示 | 显示停止按钮 | Fix 5 | ✅ |
| T10 | 后端 cancelled 后 SSE 连接是否关闭 | EventSource 关闭，无僵尸重连 | Fix 6 | ❌ |
| T11 | 从历史页面恢复 paused 研究 | 前端 status 为 `paused`，停止按钮显示 | Fix 7 | ❌ |
| T12 | 暂停后恢复研究 | 调用 resumeResearch，status 变 running | Fix 8 | ❌ |

### 6.2 回归测试

| 编号 | 测试场景 | 预期结果 |
|------|---------|---------|
| R1 | 正常启动研究 → 完成 | 全流程正常 |
| R2 | 正常启动研究 → 取消 | 前端 idle，后端 cancelled，SSE 连接关闭 |
| R3 | 页面刷新后恢复 running 任务 | SSE 重连 + 轮询对账正常 |
| R4 | 页面刷新后恢复 paused 任务 | 前端 paused，停止按钮显示，可恢复或取消 |
| R5 | 快速连续点击停止按钮 | 状态一致，不出现分裂 |
| R6 | 网络断开后恢复 | 轮询回退对账到正确状态 |
| R7 | cancelled 后 EventSource 不重连 | 连接关闭，无反复 onerror |

---

## 7. 不修复项及理由

### 7.1 `partialize` 过滤 `result` 字段

**现象**: `useSessionStore` 的 persist `partialize` 将 `result` 设为 `undefined`，页面刷新后 `result` 丢失。

**不修复理由**: `result` 是大型对象（包含完整报告），不适合存 localStorage。页面刷新后通过 `restoreSession` 从后端重新拉取。这不是"状态中途丢失"的原因。

### 7.2 服务重启后 CancelManager 状态丢失

**现象**: CancelManager 是内存单例，服务重启后 `_cancelled`/`_paused` 字典清空。

**不修复理由**: `main.py:74-75` 已将过期 running 任务标记为 paused，`cancel_research` API 仍能正确更新 session 状态。这是已知限制而非 Bug。

### 7.3 session-stream 端点断连检测

**现象**: `/api/v1/session-stream/{session_id}` 断连时不像 `/api/v1/stream/{task_id}` 那样触发延迟暂停。

**不修复理由**: session-stream 是持久连接，断连后 EventSource 自动重连。重连后 SessionStreamer 会 replay 最近消息。这不会导致"状态丢失"，但可考虑后续优化。

---

## 8. 修改文件汇总

| 文件 | Fix | 修改类型 | 修改量 | 状态 |
|------|-----|---------|-------|------|
| `web/src/components/chat/ChatPanel.tsx` | Fix 1 | 逻辑修正 | ~30 行 | ✅ 已实施 |
| `web/src/lib/sse.ts` | Fix 2 | 列表扩展 | 1 行 | ✅ 已实施 |
| `web/src/hooks/useProgress.ts` | Fix 3a | switch 分支添加 | ~6 行 | ✅ 已实施 |
| `web/src/hooks/useProgress.ts` | Fix 3b | switch 分支添加 | ~3 行 | ✅ 已实施 |
| `web/src/hooks/useResearch.ts` | Fix 4 | 条件修正 | 1 行 | ✅ 已实施 |
| `web/src/components/chat/ChatInput.tsx` | Fix 5 | 属性扩展 | ~5 行 | ✅ 已实施 |
| `web/src/components/chat/ChatPanel.tsx` | Fix 5 | prop 传递 | 1 行 | ✅ 已实施 |
| `web/src/lib/sse.ts` | Fix 6 | 条件扩展 | 1 行 | ❌ 待实施 |
| `web/src/store/useSessionStore.ts` | Fix 7 | 分支添加 | ~15 行 | ❌ 待实施 |
| `web/src/hooks/useResearch.ts` 或 `ChatPanel.tsx` | Fix 8 | 恢复逻辑添加 | ~10 行 | ❌ 待实施 |
