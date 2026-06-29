# 研究执行进度实时可见性改进方案

> 日期: 2026-06-28（修订: 2026-06-29，审查修正: 2026-06-29）
> 状态: **P0 + P1 已实现；P2 基础设施已实现但 GenericAgent 有严重缺陷（见 §9.5）**
> **注意**: 代码审查发现 GenericAgent 中 18 处 `self._report_progress()` 调用因继承关系缺失将全部抛出 AttributeError，详见 §9.5。
> **⚠️ 行号说明**: 本文档中的行号引用基于初稿时的代码版本，实际代码在实现过程中已多次修改，行号可能偏移 50~200 行。正文中保留原始行号作为逻辑定位参考，关键功能的位置请以审查标注为准。

## 1. 问题描述

用户进入研究执行阶段后，前端对话窗口仅在最初推送一次 agent 状态（orchestrator "Starting research on..."），之后长时间无任何状态更新，直到研究完成才推送最终结果。典型时间线如下：

```
t=0s    → agent_message: "Starting research on XXX..."
         ← 长时间沉默（1-10分钟）→
t=end   → agent_message: "Research completed!"
t=end   → chat_response: 最终摘要
```

**用户感知**: 系统卡死或进程中断。

**根因**: 后端在 orchestrator 内部执行（需求解析、智能路由、Agent 创建、批量执行、报告生成、质量检查）期间，仅通过 `_task_persistence` 写磁盘，不调用 `ProgressStreamer.update_progress()` 或 `SessionStreamer.push_agent_message()`，前端 SSE 通道完全没有事件。

## 2. 现状分析

### 2.1 双通道 SSE 架构

| 通道 | 类 | 端点 | 生命周期 | 事件类型 |
|------|-----|------|----------|----------|
| 任务进度 | `ProgressStreamer` | `/api/v1/stream/{taskId}` | 任务完成后关闭 | progress, phase_start, phase_complete, complete, error, cancelled |
| 会话流 | `SessionStreamer` | `/api/v1/session-stream/{sessionId}` | 会话级永久 | chat_response, agent_message, quality_result, section_quality, preview_refresh |

**重要**: `start_phase()` 和 `complete_phase()` 已内置推送 `agent_message`（分别推送 "Starting {phase_name}..." 和 "{phase_name} completed."），双写时需避免重复推送。

### 2.2 进度事件覆盖情况

| 执行阶段 | 耗时 | SSE 事件 | 缺失情况 |
|----------|------|----------|----------|
| Orchestrator 启动 | <1s | `phase_start`, `progress(0.05)`, `agent_message` | ✅ 已覆盖 |
| 需求解析 | 2-5s | 无 | ❌ 完全缺失 |
| 智能路由分析 | 2-10s | 无 | ❌ 完全缺失 |
| Agent 创建 | 1-3s | 无 | ❌ 完全缺失 |
| **批量 Agent 执行** | **1-10min** | **无** | ❌ **最大缺口** |
| 结果聚合 | 1-5s | 无 | ❌ 完全缺失 |
| 报告生成 | 5-30s | 无 | ❌ 完全缺失 |
| HTML 预览 | 2-10s | 仅 auto-repair 时 | ❌ 基本缺失 |
| 质量检查 | 5-30s | 无 | ❌ 完全缺失 |
| 完成 | <1s | `progress(1.0)`, `agent_message`, `chat_response`, `complete` | ✅ 已覆盖 |

**核心问题**: 典型研究任务 95%+ 的时间处于 Agent 执行阶段，但此阶段零 SSE 事件。

### 2.3 `_research_with_routing` 的进度更新无效

`orchestrator.py` 的路由路径中，进度通过 `self._task_persistence.update_task_state()` 更新：

```python
# orchestrator.py:1670-1671 (实际代码)
self._task_persistence.update_task_state(
    task_id, TaskState.RUNNING, progress=0.1, message="Requirement parsing complete"
)
```

**问题**: `_task_persistence` 仅写磁盘（`TaskPersistenceManager`，参见 `src/core/task_persistence.py:421-463`），不触发 `ProgressStreamer.update_progress()`，前端完全不可见。

**关键**: `_task_persistence` 使用 `task_id`（如 `research_abc123`），而 `ProgressStreamer` 使用 `session_id`（如 `ses_abc123`）作为 SSE 键。双写时必须使用 `requirement.session_id`（而非 `task_id`）调用 `update_progress()`，否则前端收不到事件。

**补充**: `_research_with_routing()` 中实际有 **11 处** `update_task_state()` 调用，完整列表：
- L1611-1612: `progress=0.0, message="Intelligent routing task started"` — 方法起始处
- L1670-1671: `progress=0.1, message="Requirement parsing complete"`
- L1708-1709: `progress=0.2, message="Intelligent routing analysis complete"`
- L1788-1789: `progress=0.3, message="Agent creation complete, starting execution"`
- **L1867-1869: `TaskState.FAILED, progress=0.0, message="Aborted: {error_detail}"` — quality check failure**
- **L1890-1892: `TaskState.FAILED, progress=0.0, message="Research cancelled, no partial data"` — cancelled no recovery**
- L1904-1905: `progress=0.7, message="Execution complete"`
- L1909-1910: `progress=0.8, message="Integrating analysis results..."`
- L2037-2038: `progress=0.9, message="Generating HTML preview..."`
- L2424-2425: `progress=1.0, message="Research complete"` — 成功结束
- L2460-2461: `TaskState.FAILED, progress=0.0` — 异常结束

其中 L1611-1612 和 L2424-2425 分别由 `research_executor.py` 的 `start_phase`/`complete_task` 覆盖，无需额外双写。但 **L2460-2461（异常路径）**、**L1867-1869（quality failure）** 和 **L1890-1892（cancelled no data）** 三处 FAILED 路径存在细微问题：`research_executor.py` 最终会调用 `fail_task()` 推送 SSE error 事件，延迟极短（毫秒级），但 ProgressStreamer 任务状态在空窗期内仍为 `running`，心跳可能误判。建议补充 `fail_task(_sid, ...)` 调用（详见风险 #9）。

### 2.4 前端进度展示现状

- **ProgressPanel**: 文件存在（`ProgressPanel.tsx`，159行）但已从 UI 移除（ChatPanel.tsx L20 注释："ProgressPanel removed"），是死代码
- **AgentMessage**: 静态图标卡片，无动画，无持续状态指示。`Loader2` 已导入但未使用
- **SearchIndicator**: 仅在 `searchState !== 'idle'` 时显示，研究执行期间 `searchState` 为 `idle`，横幅不可见
- **Header pulsing dot**: 仅一个小圆点，信息量不足

### 2.5 session_id 的来源与 fallback 风险

`session_id` 不是 `ResearchRequirement` dataclass 的声明字段，而是**动态属性**，在 `_research_with_routing()` L1662-1667 设置：

```python
if isinstance(user_input, dict):
    req_session_id = user_input.get("session_id")
    if req_session_id:
        requirement.session_id = req_session_id
if not hasattr(requirement, 'session_id') or not requirement.session_id:
    requirement.session_id = task_id  # fallback
```

**风险**: 若 `user_input` 字典不含 `session_id`（如 CLI 调用），则 `requirement.session_id` fallback 为 `task_id`。此时 `_sid = "research_abc123"`，而前端按 `ses_abc123` 订阅 SSE，**事件将丢失**。

**缓解**: `research_executor.py` 在 `execute()` 方法中通过 `user_input_dict["session_id"] = session_id`（L336）将 `session_id` 注入 `user_input`，因此正常 API 调用路径下 `requirement.session_id` 始终等于前端订阅的 `session_id`。仅在直接调用 `orchestrator._research_with_routing()` 而不经过 `research_executor` 时才可能 fallback。

## 3. 改进方案

### 3.1 设计原则

1. **双写策略**: 同时更新 `ProgressStreamer` 和 `SessionStreamer`，确保两个通道同步
2. **避免重复**: `start_phase()`/`complete_phase()` 已内置推送 `agent_message`，不要在同一点再手动推送相同内容的 `agent_message`
3. **分层进度**: 宏观阶段进度 + 微观 Agent 进度，提供多粒度感知
4. **最小侵入**: 在现有架构上增量添加，不重构核心执行流程
5. **心跳保活**: Agent 执行期间定期推送心跳事件，防止前端误判连接断开
6. **`if _sid:` 守卫**: 参考 `regenerate_report_only()` 的模式（L5300），所有 ProgressStreamer 调用需守卫，防止 `_sid` 为空时异常

### 3.2 后端改进

#### 3.2.1 桥接 `_task_persistence` → `ProgressStreamer` ✅ 已实现

**文件**: `src/core/orchestrator/orchestrator.py`

**已有参考**: `regenerate_report_only()` 方法（L5289-5365）已正确使用 `session_id` 参数调用 `start_phase`/`update_progress`/`complete_phase`，且每个调用均以 `if session_id:` 守卫，可作为参考模式。

将路由路径中的 `_task_persistence.update_task_state()` 调用增加双写。

**重要**: 必须使用 `requirement.session_id`（而非 `task_id`）调用 `ProgressStreamer`，因为前端 SSE 是按 `session_id`（如 `ses_abc123`）订阅的，而 `_task_persistence` 使用的是 `task_id`（如 `research_abc123`）。

**重要**: `start_phase()` 内部已自动推送一条 `agent_message`（内容为 `"Starting {phase_name}..."`），因此在调用 `start_phase()` 的位置**不需要**再手动推送 `SessionStreamer.push_agent_message()`，否则会重复。

```python
# 在 _research_with_routing() 中，获取前端 SSE 键（与 regenerate_report_only 模式一致）：
_sid = getattr(requirement, 'session_id', task_id)

# 需求解析完成 (原 orchestrator.py:1670-1671)
self._task_persistence.update_task_state(task_id, TaskState.RUNNING, progress=0.1, ...)
if _sid:
    update_progress(_sid, 0.1, phase_id="requirement_analysis", message="Requirement parsed")
    SessionStreamer.push_agent_message(_sid, {"agent_id": "orchestrator", "agent_name": "Research Orchestrator", "action": "analyzing", "content": "Requirement analysis complete"})

# 路由分析完成 (原 orchestrator.py:1708-1709)
self._task_persistence.update_task_state(task_id, TaskState.RUNNING, progress=0.2, ...)
if _sid:
    update_progress(_sid, 0.15, phase_id="routing", message="Routing analysis complete")
    SessionStreamer.push_agent_message(_sid, {"agent_id": "orchestrator", "agent_name": "Research Orchestrator", "action": "analyzing", "content": f"Intelligent routing: {len(routing_result.execution_plan.phases)} phases planned"})

# Agent 创建完成 (原 orchestrator.py:1788-1789)
self._task_persistence.update_task_state(task_id, TaskState.RUNNING, progress=0.3, ...)
if _sid:
    update_progress(_sid, 0.2, phase_id="agent_creation", message="Agents created, starting execution...")
    start_phase(_sid, "execution", "Agent Execution", description="Running research agents...")
    # 注意：start_phase() 已自动推送 agent_message "Starting Agent Execution..."，无需重复推送
```

**涉及位置**（11处，含原文遗漏的2处FAILED路径）:
- L1611-1612: progress 0.0 — 由 `research_executor.py` 的 `start_phase("orchestrating")` 覆盖，无需双写
- L1670-1671: progress 0.1 → 添加 `update_progress(_sid, 0.1)` + `SessionStreamer.push_agent_message`
- L1708-1709: progress 0.2 → 添加 `update_progress(_sid, 0.15)` + `SessionStreamer.push_agent_message`
- L1788-1789: progress 0.3 → 添加 `update_progress(_sid, 0.2)` + `start_phase(_sid, "execution")`（start_phase 已含 agent_message，不重复）
- **L1867-1869: TaskState.FAILED** — quality check failure，补充 `fail_task(_sid, error_detail)`（见风险 #12 策略 A）
- **L1890-1892: TaskState.FAILED** — cancelled no recovery，补充 `fail_task(_sid, "Research cancelled, no partial data")`
- L1904-1905: progress 0.7 → 添加 `update_progress(_sid, 0.7)` + `complete_phase(_sid, "execution")`（complete_phase 已含 agent_message，不重复）
- L1909-1910: progress 0.8 → 添加 `update_progress(_sid, 0.8)`
- L2037-2038: progress 0.9 → 添加 `update_progress(_sid, 0.9)`
- L2424-2425: progress 1.0 — 由 `research_executor.py` 的 `complete_task()` 覆盖，无需双写
- **L2460-2461: TaskState.FAILED** — 补充 `fail_task(_sid, str(e))`（见风险 #12 策略 A）

#### 3.2.2 Engine 批量执行进度推送 ✅ 已实现

**文件**: `src/core/orchestrator/execution/engine.py`

在 `execute_with_scheduler()` 的批处理循环中添加进度事件。

**重要**: engine 中 `session_id` 来自 `requirement.get("session_id")`（L1295 已有此模式），与前端 SSE 键一致。

```python
# 在 batch 循环开始处（约 engine.py:1089），获取 session_id:
_sid = requirement.get("session_id") or requirement.get("task_id", "")
_total_batches = len(execution_batches)

for batch_index, batch_agent_ids in enumerate(execution_batches):
    batch_progress = 0.2 + (batch_index / _total_batches) * 0.5  # 0.2-0.7 范围
    if _sid:
        from src.core.progress_streamer import update_progress
        update_progress(_sid, batch_progress, phase_id="execution",
                        message=f"Executing batch {batch_index+1}/{_total_batches}...")

    # 为 batch 中每个 agent 推送 agent_message(start)
    for agent_id in batch_agent_ids:
        agent = scheduler.get_agent_by_id(agent_id)
        if agent and _sid:
            from src.core.session_streamer import SessionStreamer
            _agent_name = (agent.config.get("context", {}).get("aspect", "")
                           or agent.agent_type)
            SessionStreamer.push_agent_message(_sid, {
                "agent_id": agent.agent_id,
                "agent_name": _agent_name,
                "action": "analyzing",
                "content": f"Starting {_agent_name}...",
            })

    # 执行 batch（已有代码）...

    # batch 完成后，推送每个 agent 的完成通知
    for agent_result in batch_results:
        if agent_result.get("success") and _sid:
            _agent_id = agent_result.get("agent_id", "")
            _agent = scheduler.get_agent_by_id(_agent_id)
            _agent_name = (_agent.config.get("context", {}).get("aspect", "")
                           or _agent.agent_type) if _agent else _agent_id
            SessionStreamer.push_agent_message(_sid, {
                "agent_id": _agent_id,
                "agent_name": _agent_name,
                "action": "completed",
                "content": f"{_agent_name} completed.",
            })
```

**修正**: `BaseAgent`（`src/core/agents/base.py:85-116`）只有 `agent_id`、`agent_type`、`config` 三个主要属性，**没有 `name` 属性**。Agent 的显示名称应从 `config.get("context", {}).get("aspect", agent_type)` 获取，与 engine.py L1156-1157 的现有模式一致。

#### 3.2.3 Agent 级别进度事件 ✅ 已实现

**文件**: `src/core/agents/base.py`

在 `BaseAgent` 中添加可选的进度回调：

```python
class BaseAgent:
    def _report_progress(self, message: str, action: str = "analyzing"):
        _sid = getattr(self, '_current_session_id', None)
        if not _sid:
            return
        try:
            from src.core.session_streamer import SessionStreamer
            SessionStreamer.push_agent_message(_sid, {
                "agent_id": self.agent_id,
                "agent_name": self.config.get("context", {}).get("aspect", self.agent_type),
                "action": action,
                "content": message,
            })
        except Exception:
            pass
```

**前提**: orchestrator 在创建 agent 后需设置 `_current_session_id`。具体插入位置在 orchestrator.py L1782-1785 的 agent 循环中：

```python
for _agent in agents:
    _agent_section_id = getattr(_agent, 'section_id', None) or ''
    if _agent_section_id:
        agent_section_map[_agent.agent_id] = _agent_section_id
    _agent._current_session_id = getattr(requirement, 'session_id', task_id)
```

#### 3.2.4 报告生成和质量检查阶段事件 ✅ 已实现

**文件**: `src/core/orchestrator/orchestrator.py`

两条执行路径都需要添加：

**非路由路径** `research()`:
- 报告生成前（约 L967）: `start_phase` + `update_progress`
- 报告生成后（约 L1038）: `complete_phase`
- HTML 预览（约 L1047）: `update_progress`
- 质量检查前（约 L1115）: `start_phase` + `update_progress`
- 质量检查后: `complete_phase`

**路由路径** `_research_with_routing()`:
- 报告生成前（约 L2047）: `start_phase` + `update_progress`
- 报告生成后（约 L2122）: `complete_phase`
- HTML 预览/质量检查前（约 L2200）: `update_progress` + `start_phase`
- 质量检查后（约 L2286）: `complete_phase`

**注意**: `start_phase()` 和 `complete_phase()` 都已内置推送 `agent_message`（progress_streamer.py L320-329 和 L360-374），因此**不需要**再手动推送同内容的 `SessionStreamer.push_agent_message()`。

#### 3.2.5 Agent 执行心跳 ✅ 已实现

**文件**: `src/core/progress_heartbeat.py`（新建）

```python
import asyncio
import logging
from src.core.progress_streamer import ProgressStreamer
from src.core.session_streamer import SessionStreamer

logger = logging.getLogger(__name__)

class ProgressHeartbeat:
    _tasks: dict = {}
    _INTERVAL_SECONDS = 15

    @classmethod
    def start(cls, session_id: str):
        if session_id in cls._tasks:
            return
        cls._tasks[session_id] = asyncio.create_task(cls._loop(session_id))

    @classmethod
    def stop(cls, session_id: str):
        task = cls._tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    @classmethod
    async def _loop(cls, session_id: str):
        try:
            while True:
                await asyncio.sleep(cls._INTERVAL_SECONDS)
                task = ProgressStreamer.get_task_state(session_id)
                if not task or task.status not in ("running", "paused"):
                    break
                SessionStreamer.push_agent_message(session_id, {
                    "agent_id": "system",
                    "agent_name": "System",
                    "action": "heartbeat",
                    "content": f"Research in progress... ({task.progress:.0%} complete)",
                })
        except asyncio.CancelledError:
            pass
        finally:
            cls._tasks.pop(session_id, None)
```

**启动位置**: `research_executor.py:312` — `start_phase("orchestrating")` 之后
**停止位置**: `research_executor.py:525` — `complete_task()` 之前

**补充停止点**: 除正常完成外，还需在以下路径停止心跳：
- `research_executor.py:558` — `fail_task()` 之前
- `research_executor.py:565` — timeout 异常 `fail_task()` 之前
- `research_executor.py:572` — `CancelledError` `fail_task()` 之前
- `research_executor.py:580` — 通用异常 `fail_task()` 之前

建议在 `research_executor.py` 中封装为 try/finally 模式：
```python
ProgressHeartbeat.start(session_id)
try:
    # ... 现有执行逻辑 ...
finally:
    ProgressHeartbeat.stop(session_id)
```

### 3.3 前端改进

#### 3.3.1 恢复并升级 ProgressPanel 🔲 未完成

**文件**: `web/src/components/chat/ProgressPanel.tsx`

重新引入 ProgressPanel，但以折叠式侧边栏形式嵌入 ChatPanel，而非全屏面板：

```
┌─────────────────────────────────────────────┐
│ Chat Messages                               │
│ ...                                         │
│ [Agent] Data Collection: Starting...        │
│ [Agent] Market Size: Searching...           │
│ ─────────────────────────────────────────── │
│ ▼ Research Progress          3/8 completed  │
│ ┌─────────────────────────────────────────┐ │
│ │ ✅ Requirement Analysis     Done        │ │
│ │ ✅ Data Collection (2/5)    40% ████░░ │ │
│ │ 🔄 Market Size             Running ██░ │ │
│ │ 🔄 Competitive Landscape   Running ██░ │ │
│ │ ⏳ Deep Analysis            Waiting      │ │
│ │ ⏳ Report Synthesis         Waiting      │ │
│ └─────────────────────────────────────────┘ │
│ ─────────────────────────────────────────── │
│ [Agent] Market Size: Found 15 data points   │
│ ...                                         │
└─────────────────────────────────────────────┘
```

**现有 ProgressPanel 的 `AGENT_NAMES` 硬编码问题**: 现有 ProgressPanel.tsx L14-21 使用硬编码的 `AGENT_NAMES` 映射。修复 `useProgress.ts` 的 `phase_start` 处理器（3.3.5）后，`phase.name` 将正确传递，`AGENT_NAMES` 可移除或仅作为 fallback。

**状态**: ProgressPanel 仍为死代码，未重新引入 UI。优先级低。

#### 3.3.2 增强 AgentMessage 组件 ✅ 已实现

**文件**: `web/src/components/chat/ChatMessage.tsx`

为 `AgentMessage` 添加：
- `action === 'heartbeat'` → 半透明 pulse 动画状态条（更新最近一条同 agent_id 消息，不追加新卡片）
- `action === 'analyzing'` → 图标旋转动画（Loader2）
- `action === 'searching'` → 图标旋转动画
- `AGENT_ACTION_CONFIG` 扩展：新增 heartbeat、error 类型

#### 3.3.3 SSE 类型扩展 ✅ 已实现

**文件**: `web/src/types/api.ts`

- `AgentMessageData.action` 扩展为 `'searching' | 'analyzing' | 'writing' | 'completed' | 'heartbeat' | 'error'`
- `AgentMessageData` 新增 `progress?: number` 字段
- `PhaseData` 新增 `description?: string` 字段

#### 3.3.4 研究状态横幅 ✅ 已实现

**文件**: `web/src/components/chat/ResearchStatusBar.tsx`（新建）

替代现有 SearchIndicator，覆盖整个研究执行阶段。已集成到 `ChatPanel.tsx`。

**与 SearchIndicator 的关系**: 两者共存——`SearchIndicator` 覆盖搜索阶段，`ResearchStatusBar` 覆盖执行阶段。

#### 3.3.5 阶段数据增强 ✅ 已实现

**文件**: `web/src/hooks/useProgress.ts`

修复 `phase_start` 事件处理中 `phase_name` 丢失的 Bug：

```typescript
case 'phase_start': {
  const d = message.data as PhaseData;
  updatePhase(d.phase_id, {
    status: 'running',
    name: d.phase_name || d.phase_id,
    description: d.description || '',
  });
  break;
}
```

**后端配合**: `ProgressStreamer.start_phase()` 事件数据已添加 `description` 字段。

## 4. 改进后的预期 SSE 事件时间线

```
t=0s    → phase_start("orchestrating", "Task Orchestration")  [research_executor]
t=0s    → progress(0.05, "Starting research on XXX...")        [research_executor]
t=0s    → agent_message(orchestrator: "Starting research on XXX...")  [research_executor]
t=0s    → heartbeat.start(15s间隔)
t=2s    → progress(0.10, "Requirement parsed")                 [orchestrator 双写]
t=2s    → agent_message(orchestrator: "Requirement analysis complete")  [orchestrator 双写]
t=5s    → progress(0.15, "Routing analysis complete")          [orchestrator 双写]
t=5s    → agent_message(orchestrator: "Intelligent routing: 3 phases planned")  [orchestrator 双写]
t=8s    → progress(0.20, "Agents created, starting execution...")  [orchestrator 双写]
t=8s    → phase_start("execution", "Agent Execution")          [orchestrator 双写]
t=8s    → agent_message(execution: "Starting Agent Execution...")  [start_phase 自动推送]
t=8s    → agent_message(market_size: "Starting 市场规模分析...")  [engine 双写]
t=8s    → agent_message(competition: "Starting 竞争格局分析...")  [engine 双写]
t=15s   → agent_message(system: "Research in progress... (20% complete)")  [heartbeat]
t=20s   → agent_message(market_size: "Completed", action=completed)  [engine 双写]
t=25s   → agent_message(competition: "Completed", action=completed)  [engine 双写]
t=30s   → progress(0.35, "Executing batch 2/4...")            [engine 双写]
t=30s   → agent_message(deep_market: "Starting 深度分析...")   [engine 双写]
         ... 继续每个 batch ...
t=120s  → progress(0.70, "All agents completed")              [orchestrator 双写]
t=120s  → phase_complete("execution")                          [orchestrator 双写]
t=120s  → agent_message(execution: "Agent Execution completed.")  [complete_phase 自动推送]
t=120s  → phase_start("report_generation", "Report Generation")  [orchestrator 双写]
t=120s  → agent_message(report_generation: "Starting Report Generation...")  [start_phase 自动推送]
t=120s  → progress(0.80, "Generating report...")              [orchestrator 双写]
t=135s  → agent_message(report_gen: "Writing chapter 3/5...")  [agent _report_progress]
t=150s  → phase_complete("report_generation")                  [orchestrator 双写]
t=150s  → phase_start("quality_check", "Quality Check")       [orchestrator 双写]
t=150s  → progress(0.90, "Running quality checks...")         [orchestrator 双写]
t=165s  → phase_complete("quality_check")                      [orchestrator 双写]
t=165s  → progress(1.0, "研究完成")                            [research_executor complete_task]
t=165s  → heartbeat.stop()
t=165s  → complete(output_path, sections, statistics)          [research_executor complete_task]
```

## 5. 实施优先级

### P0 — 消除"系统卡死"感知 ✅ 已实现

| 改动 | 文件 | 状态 |
|------|------|------|
| 桥接 _task_persistence → ProgressStreamer | `orchestrator.py` | ✅ |
| Engine 批量执行进度 | `engine.py` | ✅ |
| Agent 执行心跳 | `progress_heartbeat.py` + `research_executor.py` | ✅ |
| ResearchStatusBar | `ResearchStatusBar.tsx` + `ChatPanel.tsx` | ✅ |

### P1 — 完善阶段感知 ✅ 已实现

| 改动 | 文件 | 状态 |
|------|------|------|
| 阶段事件推送 | `orchestrator.py` | ✅ |
| 每个 Agent 启停通知 | `engine.py` | ✅ |
| AgentMessage 增强 | `ChatMessage.tsx` | ✅ |
| start_phase 传递 description | `progress_streamer.py` + `api.ts` + `useProgress.ts` | ✅ |

### P2 — 精细化进度（部分完成）

| 改动 | 文件 | 状态 | 说明 |
|------|------|------|------|
| Agent 内部进度回调 | `base.py` + orchestrator.py + 各 Agent | ✅ 基础设施 | `_report_progress` 方法已实现，调用点极少 |
| SSE 类型扩展 | `api.ts` | ✅ | |
| AgentMessage 合并更新 | `ChatMessage.tsx` + `useChatStore.ts` | 🔲 部分完成 | 心跳去重已实现，非心跳同 agent_id 消息仍追加 |
| agent_message 频率节流 | `session_streamer.py` | ✅ | 200ms 节流窗口 |
| ProgressPanel 死代码清理 | `ProgressPanel.tsx` | 🔲 未完成 | 优先级低 |

## 6. Agent 内部进度细化（待实施）

> 原 2026-06-29 独立文档，整合于此

### 6.1 现状

`_report_progress()` 方法已在 `BaseAgent`（`src/core/agents/base.py:231`）和 `FixedAgent`（`src/agents/fixed_agents/base_fixed_agent.py:140`）中实现，但：

> ⚠️ **严重缺陷**：`GenericAgent`（`generic_agent.py:88-91`）继承自 `StateManagementMixin, CommunicationMixin`，**不继承** `BaseAgent` 或 `FixedAgent`，且两个 Mixin 均未定义 `_report_progress`。但现有代码已有 **18 处** `self._report_progress()` 调用（见 §9.5），全部会抛出 `AttributeError`。以下进度点设计 **必须在修复此缺陷后** 才能实施。

> ⚠️ **节流机制**：`SessionStreamer.push_agent_message()`（`session_streamer.py:247-256`）内置 **per-session 200ms 节流**（`_AGENT_MSG_THROTTLE_SECONDS = 0.2`，L79）：同一 session 内，非 heartbeat 的 `agent_message` 事件在 200ms 窗口内只推送第一条，后续静默丢弃。

**注意**: 以下行号基于代码审查时的 generic_agent.py 版本，实际行号可能因后续改动偏移。

| Agent | 现有调用点 | 当前状态 | 缺失的关键步骤 |
|-------|-----------|---------|---------------|
| GenericAgent (research) | 入口 + 搜索 5 行 | ⚠️ 全部 AttributeError | Tier 1 DB 查询汇总、Tier 2 搜索汇总、news_search 结果 |
| GenericAgent (quality-check) | 入口 4 行 | ⚠️ 全部 AttributeError | 验证结果、冲突解决、重收集 |
| GenericAgent (analysis) | 入口 6 行 | ⚠️ 全部 AttributeError | 搜索降级、知识缺口检测、补充搜索、自评 |
| GenericAgent (calibration) | 无（1 行已加） | ⚠️ AttributeError | 校准执行 |
| GenericAgent（默认路径 fallback） | 无（1 行已加） | ⚠️ AttributeError | 搜索+分析 |
| ReportGenerationAgent | 入口 1 行 | ✅ FixedAgent 可用 | 各章节生成（不添加，纯拼接极快） |
| QualityCheckAgent | 入口 1 行 | ✅ FixedAgent 可用 | 各检查项（不添加，已有 push_section_quality） |
| DataCollectionAgent | 入口 1 行 | ✅ FixedAgent 可用 | 各数据源（不添加，查询极快） |

### 6.2 设计原则

1. **Tier 级别粒度，非 Skill 级别** — 不为每个 DB 查询单独发消息（3-5 个 DB 查询在 1-2 秒内连续完成，逐条推送无感知价值且会被 session 级 200ms 节流吞掉大部分），而是在 Tier 1 全部完成后发一条汇总
2. **中文消息** — 面向中文用户，消息用中文
3. **action 语义准确** — searching（搜索）、analyzing（分析/校验）、writing（生成内容）
4. **不重复** — engine.py 已在 batch 级别推送 "Starting XXX..." / "XXX completed."，Agent 内部不再重复启停消息
5. **异常安全** — `_report_progress()` 方法自身在 try/except 内（`base.py:235-244`），调用方无需额外保护
6. **节流兼容** — 同一 session 内 200ms 节流会丢弃密集消息。各进度点之间通常有秒级间隔，不受影响

### 6.3 进度点设计

#### 6.3.1 GenericAgent — research（DATA_COLLECTION，代码路径 L316-494）

| 时机 | 消息（f-string 表达式） | action | 位置 & 保护条件 |
|------|------------------------|--------|----------------|
| Tier 1 完成后（L368 之后） | `f"结构化数据库查询完成，获取 {len(data_points)} 条数据"` | searching | 在 Tier 1 循环（L338-367）之后，Tier 2 搜索之前 |
| Tier 2 搜索完成后（L407 之后） | `f"网络搜索完成，共 {len(data_points)} 条数据"` | searching | 在 `search_skill` 块（L386-406）之后、`news_search` 之前；仅在 `if "search_skill" in web_skills and skill_registry:`（L386）内 |
| news_search 完成后（L437 之后） | `f"补充 {len(news_result.get('results', []))} 条新闻数据"` | searching | 在 L437 `logger.info` 之后；仅在 `if news_result and news_result.get('success'):`（L417）时发送 |

**不添加的点**：
- Tier 1 每个 DB 查询前 — 1-2 秒内完成，逐条无感知价值，且会被 session 级 200ms 节流吞掉
- Tier 2 搜索前 — 已有入口消息 "Searching web sources..."

#### 6.3.2 GenericAgent — quality-check（DATA_VALIDATION，代码路径 L496-573）

| 时机 | 消息（f-string 表达式） | action | 位置 & 保护条件 |
|------|------------------------|--------|----------------|
| 验证完成后（L508 之后） | `f"数据验证完成，{validation_result['total_validated']}/{validation_result['total_input']} 通过，质量={validation_result['average_quality_score']}"` | analyzing | 在 `logger.info`（L503-508）之后、冲突处理前（L509）；仅在 `if data_points:`（L501）内。**节流风险**：验证完成和冲突解决可能 <200ms，第二条可能被节流吞掉 |
| 冲突解决后（L518 之后） | `f"解决 {len(resolved_conflicts)} 个数据冲突"` | analyzing | 在 L518 `logger.info` 之后；仅在 `if resolved_conflicts:`（L515）时发送 |
| 重收集后（L557 之后） | `"低质量数据，已重新搜索补充"` | searching | 在 `try/except` 块结束后（L557 之后）；仅在 `if recollection_attempted:` 时发送 |

#### 6.3.3 GenericAgent — analysis（DEEP_ANALYSIS，代码路径 L575-746）

| 时机 | 消息（f-string 表达式） | action | 位置 & 保护条件 |
|------|------------------------|--------|----------------|
| 搜索降级后（L604 之后） | `f"无上游数据，降级搜索获取 {len(aggregated_data_points)} 条"` | searching | 在 L604 `logger.info` 之后；仅在降级搜索块内（L583-604） |
| 知识缺口检测后（L702 之后） | `f"检测到 {len(gaps)} 个知识缺口，补充搜索中..."` | searching | 在 L702 `logger.info` 之后、`_supplementary_search_for_gaps`（L703）之前；仅在 `if gaps:`（L701）时 |
| 补充搜索+修订完成后（L734 之后） | `"基于补充数据修订分析"` | writing | 在 L734 `logger.info` 之后；仅在 `if supp_result and supp_result.get('data_points'):`（L707）时 |
| 自评完成后（L741 之后） | `f"自评完成，得分 {eval_result['score']}/100"` | analyzing | 在 L741 `result["self_evaluation"] = eval_result` 之后；仅在 `if max_self_eval > 0 and result.get("success") and result.get("content"):`（L738）时 |

#### 6.3.4 GenericAgent — synthesis/数据富集（代码路径 L800-931）

不添加。现有 2 行 `_report_progress`（L862、L865）已覆盖 LLM 前进度。

#### 6.3.5 GenericAgent — calibration（代码路径 L749-792）

| 时机 | 消息 | action | 位置 |
|------|------|--------|------|
| 入口（L749 之后） | `"校准跨章节数值一致性..."` | analyzing | `if agent_category == "calibration":` 块内第一行 |

#### 6.3.6 GenericAgent — 默认路径搜索 fallback（代码路径 L943-964）

| 时机 | 消息（f-string 表达式） | action | 位置 & 保护条件 |
|------|------------------------|--------|----------------|
| 搜索完成后（L950 之后） | `f"搜索完成，获取 {_total_search_results} 条结果"` | searching | 在 `_do_deep_research`（L945-950）之后；仅在 `if topic and "search_skill" in available_skills:`（L944）时 |

#### 6.3.7 不添加进度的 Agent

| Agent | 理由 |
|-------|------|
| ReportGenerationAgent | 各步骤均为纯字符串拼接，1秒内完成，入口消息已足够 |
| QualityCheckAgent | 已有 `push_section_quality` / `push_quality_result` SSE 事件推送细粒度进度 |
| DataCollectionAgent | 每个 source 查询极快，入口消息已足够 |

### 6.4 消息洪泛风险评估

节流机制：`SessionStreamer.push_agent_message()` 对同一 session 内非 heartbeat 消息实施 200ms 节流。

| 场景 | 理论消息数 | 节流后实际数 | 风险 |
|------|-----------|-------------|------|
| research（Tier1汇总 + web汇总 + news汇总） | 3 | 3（各间隔 >2s） | 低 |
| quality-check（验证 + 冲突 + 重收集） | 1-3 | 1-2（验证+冲突 <200ms 时第二条被吞；重收集 >2s 不受影响） | 低 |
| analysis（降级搜索 + 缺口 + 修订 + 自评） | 0-4 | 0-4（各间隔 >1s） | 低 |
| calibration | 1 | 1 | 无 |

最坏情况：单个 analysis Agent 在所有条件分支均触发时最多产生 **4 条**内部消息。加上 engine.py 的启停消息（2 条/agent）和心跳（1 条/15s），用户在 2-3 分钟内单 Agent 最多看到约 **7 条**消息，前端可正常展示。

### 6.5 实施清单

| 文件 | 改动行数 | 说明 |
|------|---------|------|
| `src/core/agents/generic_agent.py` | ~15-20 行 | research 3 处 + quality-check 3 处 + analysis 4 处 + calibration 1 处 + fallback 1 处（含条件保护的额外行） |
| 其他 Agent | 0 行 | 不添加 |

总计约 15-20 行新增，零风险。

## 7. 改动清单总览

### 后端

| 文件 | 改动类型 | 改动量 | 状态 |
|------|----------|--------|------|
| `src/core/orchestrator/orchestrator.py` | 修改 | ~70 行 | ✅ |
| `src/core/orchestrator/execution/engine.py` | 修改 | ~50 行 | ✅ |
| `src/core/agents/base.py` | 修改 | ~20 行 | ✅ |
| `src/api/research_executor.py` | 修改 | ~10 行 | ✅ |
| `src/core/progress_heartbeat.py` | 新建 | ~50 行 | ✅ |
| `src/core/progress_streamer.py` | 修改 | ~3 行 | ✅ |
| `src/core/session_streamer.py` | 修改 | ~5 行 | ✅ |
| `src/core/agents/generic_agent.py` | 修改 | ~15-20 行 | 🔲 待实施 |

### 前端

| 文件 | 改动类型 | 改动量 | 状态 |
|------|----------|--------|------|
| `web/src/components/chat/ResearchStatusBar.tsx` | 新建 | ~60 行 | ✅ |
| `web/src/components/chat/ChatPanel.tsx` | 修改 | ~5 行 | ✅ |
| `web/src/components/chat/ChatMessage.tsx` | 修改 | ~30 行 | ✅ |
| `web/src/types/api.ts` | 修改 | ~8 行 | ✅ |
| `web/src/hooks/useProgress.ts` | 修改 | ~10 行 | ✅ |
| `web/src/components/chat/ProgressPanel.tsx` | 修改 | ~30 行 | 🔲 待清理 |

## 8. 风险与注意事项

1. **session_id vs task_id 混淆（关键）**: 所有 `update_progress()`、`start_phase()`、`complete_phase()` 调用必须使用 `requirement.session_id`（从 `user_input` 传入），否则前端收不到事件。
2. **session_id fallback 风险**: 若 `user_input` 不含 `session_id`，`requirement.session_id` 会 fallback 为 `task_id`，前端按 `session_id` 订阅将无法收到事件。
3. **`start_phase()`/`complete_phase()` 已内置推送 `agent_message`**: 调用后不需要再手动推送同内容 `agent_message`，否则前端会收到两条重复消息。
4. **SSE 事件频率控制**: Agent 执行期间可能产生大量事件，需控制推送频率。已通过 200ms 节流实现。
5. **心跳停止条件**: 心跳必须在任务完成/失败/取消时停止。已通过 try/finally 模式确保。
6. **ProgressStreamer vs SessionStreamer 一致性**: `update_progress()` 仅推送 `progress` 事件到 ProgressStreamer，不推送 `agent_message` 到 SessionStreamer。如需双通道可见，需在 `update_progress` 后手动推送 `agent_message`。
7. **前端去重**: 心跳消息已实现去重（更新最近一条同 agent_id 消息），非心跳消息仍追加新卡片。
8. **性能**: `update_progress()` 每次写磁盘，高频调用时需评估 IO 压力。engine 批量循环中每完成一个 batch 才调用一次。
9. **异常路径中间进度缺失**: 三处 FAILED 路径已补充 `fail_task(_sid, ...)` 调用（策略 A），前端可能收到两个 error 事件，但心跳能立即退出。
10. **BaseAgent 无 name 属性**: Agent 显示名称应从 `config.get("context", {}).get("aspect", agent_type)` 获取。
11. **进度值衔接**: `research_executor.py` 设置 `progress(0.05)`，orchestrator 内部进度值从 0.1 开始衔接。
12. **GenericAgent 不继承 BaseAgent（关键）**: `GenericAgent` 使用 mixin 组合，不继承 `BaseAgent` 或 `FixedAgent`，且继承链中 `StateManagementMixin` 和 `CommunicationMixin` 均未定义 `_report_progress`。当前 `generic_agent.py` 中已有 **18 处** `self._report_progress()` 调用，全部会抛出 `AttributeError`。**所有 GenericAgent 的进度报告功能完全不可用**，必须在实施 §6.3 的进度点之前先修复此缺陷。

## 9. 实现状态（2026-06-29 更新）

### 9.1 已完成

#### 后端

| # | 改动 | 文件 | 测试 | 状态 |
|---|------|------|------|------|
| P0-1 | `ProgressHeartbeat` | `src/core/progress_heartbeat.py` | 7 tests ✅ | ✅ |
| P0-2 | `start_phase` description 字段 | `src/core/progress_streamer.py` L312-317 | 3 tests ✅ | ✅ |
| P0-3 | Orchestrator 桥接（路由路径） | `src/core/orchestrator/orchestrator.py` | 手动审查 ✅ | ✅ |
| P0-4 | Engine 批量进度 | `src/core/orchestrator/execution/engine.py` | 手动审查 ✅ | ✅ |
| P0-5 | `BaseAgent._report_progress` | `src/core/agents/base.py` | 4 tests ✅ | ✅ |
| P0-6 | 心跳集成（try/finally） | `src/api/research_executor.py` | 手动审查 ✅ | ✅ |
| P2-1 | Agent 内部 `_report_progress` 调用 | `generic_agent.py` + 各 FixedAgent | ⚠️ **仅 BaseAgent/FixedAgent 有 8 tests** | ⚠️ **GenericAgent 有严重缺陷** |
| P2-2 | 非路由路径 `research()` 桥接 | `src/core/orchestrator/orchestrator.py` | 手动审查 ✅ | ✅ |
| P2-5 | agent_message 频率节流 | `src/core/session_streamer.py` | 3 tests ✅ | ✅ |

**Orchestrator 桥接详情（P0-3）**：

| 位置 | 进度值 | SSE 事件 | 事件来源 |
|------|--------|----------|----------|
| 需求解析完成 | 0.1 | `update_progress` + `agent_message` | orchestrator 手动双写 |
| 路由分析完成 | 0.15 | `update_progress` + `agent_message` | orchestrator 手动双写 |
| Agent 创建完成 | 0.2 | `update_progress` + `start_phase("execution")` | start_phase 自动推送 agent_message |
| Agent 执行完成 | 0.7 | `update_progress` + `complete_phase("execution")` | complete_phase 自动推送 agent_message |
| 结果整合中 | 0.8 | `update_progress` | 无 agent_message（无阶段转换） |
| 报告生成前 | 0.8 | `start_phase("report_generation")` + `update_progress` | start_phase 自动推送 agent_message |
| 报告生成后/质量检查前 | 0.9 | `complete_phase("report_generation")` + `start_phase("quality_check")` + `update_progress` | complete/start_phase 自动推送 |
| 质量检查后 | - | `complete_phase("quality_check")` | complete_phase 自动推送 |

**FAILED 路径详情**：

| 位置 | SSE 事件 | 说明 |
|------|----------|------|
| quality check failure | `fail_task(_sid, error_detail)` | 策略 A，心跳立即退出 |
| cancelled no recovery | `fail_task(_sid, "Research cancelled...")` | 策略 A |
| 外部 except | `fail_task(_sid or task_id, str(e))` | `_sid or task_id` fallback |

#### 前端

| # | 改动 | 文件 | TS 编译 | 状态 |
|---|------|------|---------|------|
| P1-1 | `ResearchStatusBar` | `ResearchStatusBar.tsx` | ✅ | ✅ |
| P1-2 | `ChatPanel` 集成 | `ChatPanel.tsx` | ✅ | ✅ |
| P1-3 | AgentMessage 增强 | `ChatMessage.tsx` | ✅ | ✅ |
| P1-4 | SSE 类型扩展 | `api.ts` | ✅ | ✅ |
| P1-5 | useProgress phase_start 修复 | `useProgress.ts` | ✅ | ✅ |
| P1-6 | ChatToken 流式支持 | `useProgress.ts` + `ChatPanel.tsx` | ✅ | ✅ |
| P2-4 | 心跳消息去重 | `ChatPanel.tsx` | ✅ | ✅ |

### 9.2 未完成

| 改动 | 文件 | 说明 | 严重性 |
|------|------|------|--------|
| GenericAgent `_report_progress` 缺失 | `generic_agent.py` | **18 处调用全部会抛出 AttributeError**（见 §9.5） | 🔴 CRITICAL |
| Agent 内部进度细化（新增调用） | `generic_agent.py` | 待新增 12 个进度点（见 §6.3），当前 18 处调用已全部不可用 | 🔴 阻塞 |
| ProgressPanel 死代码清理 | `ProgressPanel.tsx` | 死代码未清理/重构 | 🟡 低 |
| AgentMessage 非 heartbeat 合并 | `ChatMessage.tsx` + `useChatStore.ts` | 非心跳同 agent_id 消息合并而非追加 | 🟢 低 |

### 9.3 审查修订记录

**问题 1: 冗余 `_sid` 重赋值**（已修复）

`_research_with_routing()` 中 `_sid` 在 L1669 已设置为 `requirement.session_id`，但后续 6 个插入点重复使用 `_sid = getattr(requirement, 'session_id', task_id)` 重赋值。审查后移除所有冗余重赋值，统一使用 L1669 设置的 `_sid` 变量。

**问题 2: `_sid` 变量名冲突**（已修复）

原 orchestrator.py L1811 的 agent 循环使用 `_sid` 作为 section_id 遍历变量，与 session_id 变量冲突。已重命名为 `_asec`（agent section），并引入 `_session_id_for_agents` 存储设置给 agents 的 session_id。

**问题 3: `SearchIndicator` 保留**

审查确认 `SearchIndicator` 和 `ResearchStatusBar` 共存：`SearchIndicator` 覆盖 `searchState` 驱动的搜索阶段，`ResearchStatusBar` 覆盖 `status === 'running'` 的执行阶段。两者不冲突，不替换。

**问题 4: `start_phase`/`complete_phase` 内置 `agent_message`**

审查确认所有调用 `start_phase`/`complete_phase` 的位置均未再手动推送 `agent_message`，无重复风险。

**问题 5: `fail_task` 幂等性**

审查确认 `ProgressStreamer.fail_task()` 将 `task.status` 设为 `"error"`，`research_executor.py` 后续调用 `fail_task()` 会再次设为 `"error"`（幂等）。前端可能收到两个 `SSEEventType.ERROR` 事件，但无崩溃风险。

**问题 6: 非路由路径 `research()` 的 `_sid` 变量名冲突**

与路由路径相同的问题：`research()` L745 的 agent 循环使用 `_sid` 作为 section_id，与 session_id 变量冲突。已重命名为 `_asec`，引入 `_session_id_for_agents`。

**问题 7: `FixedAgent._report_progress` 实现**

`FixedAgent` 不继承 `BaseAgent`（使用 mixin 组合），需单独添加 `_report_progress` 方法。FixedAgent 有 `self.name` 属性，直接使用而非从 config 推断。

**问题 8: agent_message 节流策略**

在 `SessionStreamer.push_agent_message()` 中添加 200ms 节流窗口，但心跳消息（`action === 'heartbeat'`）不受节流影响。

### 9.4 测试覆盖

| 测试文件 | 测试数 | 状态 |
|----------|--------|------|
| `tests/unit/test_progress_heartbeat.py` | 7 | ✅ |
| `tests/unit/test_start_phase_description.py` | 3 | ✅ |
| `tests/unit/test_base_agent_report_progress.py` | 4 | ✅ |
| `tests/unit/test_sse_persistence.py` | 4 | ✅ |
| `tests/unit/test_fixed_agent_report_progress.py` | 4 | ✅ |
| `tests/unit/test_agent_message_throttle.py` | 3 | ✅ |
| **总计** | **25** | **✅** |

TypeScript 编译: ✅ 无新增错误（仅预存 QualityPanel.tsx TS2367）

### 9.5 ⚠️ 严重缺陷：GenericAgent 缺少 `_report_progress` 实现

**发现**: 代码审查发现 `GenericAgent` 中现有 **18 处** `self._report_progress()` 调用（generic_agent.py L317/368/373/408/439/501/512/524/562/586/612/708/744/752/761/874/877/965），但 `GenericAgent` 不继承 `BaseAgent`，继承链 `StateManagementMixin + CommunicationMixin` 中均未定义 `_report_progress`，也无动态注入机制。

**后果**: 上述 18 处调用全部会抛出 `AttributeError: 'GenericAgent' object has no attribute '_report_progress'`。

**原因**: 原 06-29 设计文档（已合并入 §6）明确标注了此风险（"实施前须确认运行时该方法确实可解析"），但始终未解决，且在未解决的情况下新增了大量调用（从 6 处增至 18 处）。

**影响范围**:

| Agent 类型 | 调用数 | 代码路径 | 触发条件 |
|-----------|--------|---------|---------|
| GenericAgent (research) | 5 | L317/368/373/408/439 | 数据分析类任务 |
| GenericAgent (quality-check) | 3 | L501/512/524/562 | 数据验证类任务 |
| GenericAgent (analysis) | 6 | L586/612/708/744/752 | 深度分析类任务 |
| GenericAgent (calibration) | 1 | L761 | 校准类任务 |
| GenericAgent (synthesis) | 2 | L874/877 | 数据富集类任务 |
| GenericAgent (fallback) | 1 | L965 | 兜底搜索路径 |

**修复方案**: 详见独立设计文档 [`docs/fix-generic-agent-report-progress.md`](fix-generic-agent-report-progress.md)

**推荐方案**: 在 GenericAgent 类中直接定义 `_report_progress` 方法（方案 A）— 1 文件 +12 行，风险最低。详见设计文档 §3 方案对比。

**现有测试**: `test_base_agent_report_progress.py`（4 tests）和 `test_fixed_agent_report_progress.py`（4 tests）均不覆盖 GenericAgent。修复后需新增 `test_generic_agent_report_progress.py`（~5 tests）。
