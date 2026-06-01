# 多会话并行开发计划（v2）

> 更新于 2026-05-05，依据当前代码现状修订

---

## 已完成部分

### 后端基础

| 改动 | 文件 | 说明 |
|------|------|------|
| RLock 修复 | `src/core/session_manager.py:128` | `Lock` → `RLock`，消除 _wrap 重入死锁 |
| 助手消息持久化 | `src/api/research_api.py:1203-1244` | `_chat_response`/`_framework_response` 将助手消息写入 `conversation_history` |
| 全量会话 API | `src/api/main.py:191-262` | `GET /api/v1/research/sessions` 合并 SessionManager + ResearchResultStore |
| 会话详情 API | `src/api/main.py:296-320` | `GET /api/v1/research/{task_id}` 支持从 SessionManager 恢复消息 |
| Preview 500 修复 | `src/api/main.py:161-164` | 移除不存在的 `base_url` 参数 |

### 前端基础

| 改动 | 文件 | 说明 |
|------|------|------|
| 会话切换 | `Sidebar.tsx:36-108` | 直接调用 `api.getResearchDetail` + store 恢复，**无需页面跳转** |
| 侧边栏自动刷新 | `Sidebar.tsx:29-34` | 打开时 `useEffect` 自动触发 `reload()` |
| 活跃会话状态 | `Sidebar.tsx:195-210` | `isActive ? 'active' : status` 显示"进行中" |
| 新建清空消息 | `Header.tsx:22-32`, `Sidebar.tsx:111-116` | `reset()` + `clearMessages()` + `router.push('/')` |
| 预览开关 | `MainLayout.tsx`, `Header.tsx` | 右上角 👁 按钮切换预览面板显隐 |
| 文档预览修复 | `DocumentPreview.tsx:82` | 仅 `status === 'running'` 显示"研究进行中" |
| 移除误导提示 | `ChatPanel.tsx` | 移除"步骤 X/6"计数器和"研究完成"绿色卡片 |
| 状态类型扩展 | `types/api.ts` | 添加 `'paused'` 到 `ResearchResultMeta.status` |
| 会话列表 API | `useHistorySessions.ts` | 改用 `listAllSessions()` |
| Store 持久化 | `useResearchStore.ts` | `partialize` 保存所有状态（非仅 completed） |

### 当前架构

```
useSessionStore (注册中心) ← 持久化 localStorage
┌─────────────────────────────────────┐
│ activeId: 'ses_abc'                 │
│ sessions: {                         │
│   'ses_abc': { status, step, msgs } │
│ }                                    │
└──────────┬──────────────────────────┘
           │ 订阅 / 同步
     ┌─────┴──────┐
     ↓            ↓
useResearchStore  useChatStore
(委托层)          (委托层)
现有组件保持导入不变，内部状态由 session store 驱动。
```

**关键机制：**
- `useSessionStore`：真正的多会话注册中心，持所有会话的元数据 + 消息缓存
- `useResearchStore`：subscribe 到 session store，activeId 变化时自动从缓存加载状态
- `useChatStore`：subscribe 到 session store，activeId 变化时自动从缓存加载消息
- 所有 setter（`setSessionId`, `addMessage` 等）同时写回缓存，切换不丢数据

**持久化：** localStorage key `Zensers-sessions`，最多保留最近 10 个会话。

---

### Phase 2: 更新 Sidebar 切换逻辑（1天）

**目标：** Sidebar 的 `handleSelectSession` 改用 registry 的 `switchTo`，消除直接操作 API 和 store 的重复逻辑。

```typescript
// Sidebar.tsx
const switchTo = useSessionStore((s) => s.switchTo);

const handleSelectSession = async (taskId: string) => {
  if (taskId === sessionId) { onClose(); return; }

  // switchTo 内部逻辑：
  // 1. 如果 registry 已有 → 直接切换 activeId
  // 2. 如果没有 → 调用 api.getResearchDetail() → 创建新 entry → 切换
  await switchTo(taskId);
  onClose();
};
```

**注意：** 当前 Sidebar 已经实现了直接恢复的逻辑。
Phase 2 的主要工作是**将恢复逻辑从 Sidebar 搬进 Registry**，使恢复逻辑集中可复用。

---

### Phase 3: 更新 useResearch Hook（1天）

**目标：** `useResearch` hook 改为操作 registry store，不再假设单会话。

```typescript
// useResearch.ts 核心变化
export function useResearch() {
  const active = useSessionStore((s) => s.activeId ? s.sessions[s.activeId] : null);
  const registry = useSessionStore();

  const startResearch = useCallback(async (input, ...) => {
    const data = await api.startResearch(input, ...);
    registry.createSession({ id: data.session_id, ... });
    return data;
  }, []);

  const sendMessage = useCallback(async (text) => {
    if (!active) return startResearch(text);
    // 直接操作 active session
    const data = await api.sendChatMessage(active.id, text);
    registry.addMessage({ role: 'assistant', content: data.message, ... });
    return data;
  }, [active?.id]);
}
```

**文件变更：**
| 操作 | 文件 |
|------|------|
| 重写 | `web/src/hooks/useResearch.ts` |

---

### Phase 4: 会话标签栏 UI（2天）

**目标：** ChatPanel 上方添加标签栏，显示所有 open 会话，支持即时切换。

```
┌──────────────────────────────────────────┐
│  Header                                  │
├──────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌────┐         │
│ │ 行业研究  │ │ 市场规模  │ │ ＋ │  ← tabs │
│ └──────────┘ └──────────┘ └────┘         │
├──────────────────────────────────────────┤
│  Chat messages                            │
│  ...                                       │
├──────────────────────────────────────────┤
│  Input                                    │
└──────────────────────────────────────────┘
```

**交互：**
- 每个 tab 显示会话标题 + 状态指示器圆点
- active tab 高亮（底部横线或背景色）
- 点击 tab → `switchTo(id)` → 内容即时切换
- "＋" → `createSession()` → `router.push('/')`（清空输入区）
- 非活跃的 running 会话显示脉冲圆点
- Tab 上的 ✕ → `closeSession(id)`，确认后移除（保留后端数据）

**组件：**
- 新建 `web/src/components/chat/SessionTabs.tsx`
- `ChatPanel.tsx` → 上方渲染 `<SessionTabs />`

**状态栏调整：**
当前 ChatPanel 底部的状态栏（"执行中"+"重新开始"）应改为仅在 active 会话 running 时显示。

---

### Phase 5: 侧边栏深度联动（0.5天）

**目标：** 侧边栏与标签栏双向同步。

- 侧边栏点击 → `switchTo(id)` → 标签栏高亮对应的 tab
- 标签栏点击 → `switchTo(id)` → 侧边栏同步高亮
- 侧边栏中 active 的 session 已自动高亮（`sessionId` 比较），当前逻辑可用
- 新会话从侧边栏"新建研究"创建后，自动在标签栏出现

---

### Phase 6: 消息懒加载与一致性（1天）

**目标：** 切换即时显示 + 后台同步。

```
switchTo(id)
  │
  ├─ sessions[id] 有缓存 → 立即显示
  │     └─ 异步 GET /api/v1/research/{id}
  │           └─ 新消息比缓存多 → 追加到缓存尾部
  │
  └─ sessions[id] 无缓存 → 显示 loading
        └─ GET /api/v1/research/{id} → 创建 entry → 显示
```

**消息去重：** 以 `msg.id` 为准，已存在的跳过。

---

### Phase 7: 并发执行支持（1天）

**目标：** 多个 research 同时在后台执行，每个独立连接 SSE。

**前端：**
- `useProgress(taskId)` 改为按 session 管理连接
- registry 中 `status === 'running'` 的 session 自动建立 SSE
- 标签栏 running 的 tab 显示进度指示器
- 最多同时 3 路 SSE 连接，超出则排队

**后端：** `ProgressStreamer` 和 `ResearchExecutor` 已支持并发，无需改动。

---

## 时间线

| Phase | 内容 | 前置 | 估算 |
|-------|------|------|------|
| Phase | 内容 | 前置 | 状态 |
|-------|------|------|------|
| **P1** | **Session Registry Store** | — | **✅ 已完成** |
| **P2** | **Sidebar → switchTo** | P1 | **✅ 已完成** |
| **P3** | **useResearch Hook 改造** | P1 | **✅ 已完成** |
| **P4** | **会话标签栏 UI** | P1+P3 | **✅ 已完成** |
| P5 | 侧边栏深度联动 | P2+P4 | ⏳ 待开始 |
| P6 | 消息懒加载 | P1 | ⏳ 待开始 |
| P7 | 并发执行 | P4 | ⏳ 待开始 |

---

## 风险与注意事项

1. **消息体积** — `sessions[id].messages` 随对话增长，建议单会话上限 200 条，超出后截断最早的消息
2. **localStorage 限额** — 约 5MB。10 个会话各 100 条消息 ≈ 200KB，安全。但加上 phase/progress 等会更大，建议限制缓存 5 个最近会话
3. **SSE 资源** — 每个 running 会话一条 SSE 长连接。浏览器限制同域 6 条，建议前端限制 3 条并发
4. **标签栏 UX** — 移动端屏幕窄，标签可横向滑动 (`overflow-x-auto`)
5. **消息同步** — 后端是权威源，前端缓存可能滞后。切换时静默刷新，用户无感知
