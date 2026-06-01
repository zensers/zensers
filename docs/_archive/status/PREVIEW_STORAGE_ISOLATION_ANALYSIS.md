# 预览文件隔离问题深度分析（修正版 v2）

> **审核修正**: 2026-05-11
> 初版断言"前端不请求后端"是错误的。`DocumentPreview` 的 `usePreview` 钩子每次 mount 都独立调用后端 API。

---

## 问题

新标签页打开后显示早期研究报告的预览 HTML。修复后端 API 和 Session 生命周期后，问题依然存在。

---

## 真实请求链路

```
新标签页打开
  → Zustand persist 从 localStorage 恢复
  → activeId = ses_86cd6b72（最后一次活跃会话，已完成）
  → DocumentPreview 组件 mount
  → usePreview("ses_86cd6b72").fetchPreview()        ← 独立请求
  → GET /api/v1/research/ses_86cd6b72/preview
  → 后端检查 data/previews/ses_86cd6b72.html → 存在！
  → 返回 { preview_url: "/api/v1/previews/ses_86cd6b72.html" }
  → 前端 iframe 渲染 → 显示比亚迪旧报告
```

**关键**: `DocumentPreview` 确实重新请求了后端。但后端返回了有效 preview（因为文件仍在磁盘上）。

---

## 根因分析

### 根因 1（P0）：新标签页恢复了旧 completed session 的 activeId

**文件**: `web/src/store/useSessionStore.ts:222-243`

```typescript
persist(
  {
    name: 'Zensers-sessions',
    partialize: (state) => ({
      activeId: state.activeId === '__pending__' ? null : state.activeId,
      // ...
    }),
  }
)
```

当最后活跃的是 `ses_86cd6b72`（非 `__pending__`），`localStorage` 保存 `activeId = ses_86cd6b72`。新标签页加载时：

1. `localStorage` 恢复 `activeId = ses_86cd6b72`
2. 前端的入口逻辑没有检查：这是一个**已经 completed 的旧会话**，不应该直接恢复为当前页面
3. 应该创建空白新会话，或显示会话列表而非直接展示旧会话

### 根因 2（P0）：后端 get_preview 无 research_result 校验

**文件**: `src/api/research_api.py:2405-2426`

```python
async def get_preview(self, task_id, format="html"):
    session = session_manager.get(task_id)
    research_result = session.get("research_result", {})

    preview_path = Path("data/previews") / f"{task_id}.html"
    if preview_path.exists():                  # ← 只检查文件存在
        preview_url = f"/api/v1/previews/{task_id}.html"
        # ...
```

后端只检查文件是否存在，不检查该 session 是否真的有完成的研究结果。对于 `ses_86cd6b72`：

- 文件 `data/previews/ses_86cd6b72.html` ✅ 存在
- `research_result.get("status") != "completed"` — 但有会话记录
- 后端返回有效 preview → 前端显示旧报告

即使前端创建一个全新的 session（新标签页 + 新会话），`get_preview` 对新 session 返回 null，但旧 session 的 `activeId` 被恢复，所以 `DocumentPreview` 渲染的是旧 session 的预览。

---

## 真实双根因

| # | 根因 | 位置 | 说明 |
|---|------|------|------|
| 1 | 新标签页恢复了旧 completed session 的 activeId | `useSessionStore.ts` persist + 入口 | 新窗口应创建新会话或显示列表，而非恢复已完成会话 |
| 2 | 后端 get_preview 只检查文件存在，不校验 research_result | `research_api.py:2405-2426` | 即使文件存在，如果 session 没有有效结果，应返回 null |

---

## 修复方案

### 修复 1（P0）：后端 get_preview 增加 research_result 校验

```python
async def get_preview(self, task_id, format="html"):
    session = session_manager.get(task_id)
    research_result = session.get("research_result", {})

    # 如果没有有效的研究结果，不返回预览
    if not research_result or research_result.get("status") != "completed":
        return {
            "task_id": task_id,
            "preview_url": None,
            "html_content": None,
            "preview_format": format,
            "download_url": None,
        }

    preview_path = Path("data/previews") / f"{task_id}.html"
    if preview_path.exists():
        preview_url = f"/api/v1/previews/{task_id}.html"
        # ...
```

### 修复 2（P0）：新标签页不恢复旧 completed session

在入口逻辑（前端页面加载时）添加：若 `persist` 恢复的 `activeId` 对应的 session 状态是 `completed` 且没有正在运行的任务，则创建新空白会话。

```typescript
// 在页面入口或 App 初始化时
const activeSession = store.sessions[store.activeId];
if (activeSession && activeSession.status === 'completed') {
  // 不恢复已完成会话，创建新会话
  const newId = nanoid();
  store.createSession(newId);
}
```

---

## 文档初版错误记录

| 错误 | 描述 |
|------|------|
| 断言"前端不请求后端" | DocumentPreview 的 usePreview 钩子独立请求后端 API |
| 遗漏真实链路 | 路径是：新标签页→恢复 old activeId→请求后端→后端有旧文件→返回 preview |
| 修复方案 A 单独无效 | restoreSession 始终请求后端 → 后端仍有旧文件 → 仍返回有效 preview |
| 误判根源 | 将 localStorage 缓存列为根源，实际根源是 activeId 恢复 + 后端无校验 |
