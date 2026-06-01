# 重大生产事故报告：会话管理混乱与僵尸任务（修正版 v3）

> **报告日期**: 2026-05-11
> **事故等级**: P0（严重）
> **涉及系统**: ResearchAPI, ResearchExecutor, ProgressStreamer, SSE
> **代码基线**: 回滚后状态（仅保留 converter 等非 session 修复）

---

## 1. 代码状态说明

在审核过程中，对话中的未经授权修改已被回滚。回滚影响：

| 被移除的代码 | 文件 | 说明 |
|-------------|------|------|
| `_disconnect_callbacks` 类字段 | progress_streamer.py | 断连回调基础设施已全部删除 |
| `set_disconnect_callback` / `clear_disconnect_callback` | progress_streamer.py | — |
| `generate()` finally 中的断连回调触发 | progress_streamer.py | — |
| `pause_research` 中的 `exec_task.cancel()` | research_api.py | 恢复为原始版本（无取消逻辑） |
| `_start_execution` 中的 `set_disconnect_callback` 注册 | research_api.py | 恢复为原始版本 |

**后果**: 报告 v2 分析的根因1（`_on_sse_disconnect` 未定义）、根因5（resume 缺回调）、断连回调基础设施问题**在当前代码中已不存在**。报告必须重新与代码对齐。

> **基线说明**：原始代码中从未存在断连回调机制。v2 分析的是审核期间添加的代码中的 Bug，该代码已被移除。断连回调的缺失不是回归，而是基线状态的特征。

---

## 2. 当前真实 Bug 清单

### Bug 1（P0）：CancelledError 不被 except Exception 捕获

**文件**: `src/api/research_executor.py:291`

```python
except Exception as e:
    logger.error(f"Research failed: {session_id} - {e}", exc_info=True)
    fail_task(session_id, str(e))
    if session:
        session["paused"] = True
    return {"error": str(e)}
```

`asyncio.CancelledError` 继承自 `BaseException`（Python 3.8+），不是 `Exception`。任何 `exec_task.cancel()` 调用（包括 `cancel_research` 中的两处）触发的取消异常都会被此 except 漏掉，异常被 asyncio 吞没，导致：

- `fail_task()` 不执行 → ProgressStreamer 状态卡在 "running"
- `session["paused"]` 不设置 → session 状态不一致
- Agent Session Registry 不清理 → 资源泄漏

**影响**: `cancel_research` 的双重取消代码（见 Bug 4）实际上都无法正确清理状态。

### Bug 2（P0）：执行过程中无暂停检测

**文件**: `src/api/research_executor.py:49-82`

`_check_paused()` 具有暂停等待循环，但**只在 `orchestrator.research()` 之前调用一次**。一旦进入 orchestrator，没有再检查 `session["paused"]` 的机制。

**影响**: 用户点击暂停后，已在执行的 orchestrator 任务继续运行，LLM 调用继续消耗 token。

### Bug 3（P1）：pause_research 不取消后台任务

**文件**: `src/api/research_api.py:2552-2582`

```python
async def pause_research(self, task_id):
    session["paused"] = True
    # ← 没有 exec_task.cancel()
    # ← 没有 ProgressStreamer.fail_task()
    return {"status": "paused"}
```

与 `cancel_research`（第2738-2740行，有 `_executor_tasks.pop()` + `exec_task.cancel()`）对比，pause 路径完全不触及执行中的任务。

**影响**: 用户点击暂停后，前端显示 "paused"，但后台 orchestrator 继续运行。且暂停后 session 处于「半清除」状态：
- `session["mode"]` 仍为 "research"（cancel 会设成 "chat"）
- `session["research_result"]` 未清理
- `session["final_plan"]` 未清理

### Bug 4（P1）：cancel_research 有重复取消代码

**文件**: `src/api/research_api.py:2738-2740` 与 `2762-2764`

```python
# 第一次（第2738行）：
exec_task = self._executor_tasks.pop(task_id, None)
if exec_task and not exec_task.done():
    exec_task.cancel()

# ... 中间 24 行清理逻辑 ...

# 第二次（第2762行，变量名不同）：
executor_task = self._executor_tasks.pop(task_id, None)  # ← 必然返回 None
if executor_task and not executor_task.done():
    executor_task.cancel()
```

第二次 pop 在上一次 pop 之后必然返回 `None`，这段代码不执行任何实际操作。更严重的是：两段代码都在 `except Exception` 保护范围外，它们触发的 `CancelledError` 成为无人捕获的孤儿异常（见 Bug 1）。

### Bug 5（P1）：SSE 断连后无任何自动处理

**文件**: `src/core/progress_streamer.py:567-568`

断连回调基础设施（`_disconnect_callbacks`、`set_disconnect_callback`）已在回滚中被完全移除。当前代码中，SSE 客户端断开连接后不触发任何操作：

- `progress_streamer.py` 的 `generate()` 方法在 `finally` 中仅调用 `self.unsubscribe()`
- 没有通知 ResearchAPI 的机制
- 没有自动暂停/取消正在执行的任务

**影响**: 用户关闭浏览器后，后台任务继续运行直到自然完成。

### Bug 6（P1）：resume 重新执行路径遗漏 _executor_tasks 注册

**文件**: `src/api/research_api.py:2640`

```python
# 缓存路径（L2622） — 正确注册：
self._executor_tasks[task_id] = cache_task

# 重新执行路径（L2640） — 遗漏注册：
asyncio.create_task(executor.execute(task_id, plan, session_manager))
# ← 返回值未存入 _executor_tasks！
```

**影响**: 无缓存时重新执行的任务不在 `_executor_tasks` 字典中。`cancel_research` 第2738行的 `pop(task_id)` 返回 `None`，该任务变得不可取消。

### Bug 6b（P1）：_generate_documents_from_cache 无 CancelledError 保护

**文件**: `src/api/research_api.py:2652-2722`

`await self._orchestrator._document_agent.execute()` 可被 `exec_task.cancel()` 取消，但路径中没有 `except asyncio.CancelledError` 处理。取消后 `session["research_result"]` 不写入、`session["mode"]` 不切为 "chat"。这是 Bug 1 在 cache 路径的重复。

---

## 3. 影响范围

| 指标 | 数值 |
|------|------|
| 真实 P0 Bug 数 | **2 个**（CancelledError 不捕获、无暂停检测） |
| 真实 P1 Bug 数 | **5 个**（见下文 #3a/3b/4/5/6） |
| 受影响功能 | 暂停、取消、恢复、前端断开、执行中控 |
| 修复优先级 | 修复1（CancelledError）→ 修复2（暂停检测）→ 修复3-7 按需 |

---

## 4. 修复方案

> **修复依赖声明**：修复2（暂停监控）检测到暂停后调用 `main_task.cancel()` → 触发 `CancelledError`。如果修复1（CancelledError 独立捕获）未先实施，该 `CancelledError` 同样不被捕获，导致相同的 session 状态不一致。**修复1 和 修复2 必须捆绑实施，或严格按 1 → 2 顺序执行。**

### 修复 1（P0）：CancelledError 独立捕获

```python
try:
    orchestrator_result = await asyncio.wait_for(...)
except asyncio.CancelledError:
    logger.info(f"Research cancelled: {session_id}")
    fail_task(session_id, "Task cancelled")
    if session:
        session["paused"] = True
        session["status"] = "cancelled"
        session["mode"] = "chat"
    raise
except Exception as e:
    ...
```

### 修复 2（P0）：执行中添加暂停监控

> ⚠️ `ResearchExecutor` 是全局单例（`get_executor()`），不能用实例属性存主任务引用。同时运行两个研究任务时，后启动的任务会覆盖前一个的引用，导致监控器误取消。

**方案**：使用 `Dict[str, asyncio.Task]` 替代实例属性：

```python
class ResearchExecutor:
    def __init__(self):
        self._main_tasks: Dict[str, asyncio.Task] = {}  # session_id → main_task
    
    async def execute(self, session_id, plan, session_manager):
        self._main_tasks[session_id] = asyncio.current_task()
        
        async def _monitor(sid):
            while True:
                await asyncio.sleep(5)
                session = session_manager.get(sid)
                if not session:
                    return
                if session.get("paused") or session.get("status") == "cancelled":
                    main = self._main_tasks.get(sid)
                    if main and not main.done():
                        main.cancel()
                    return
        
        monitor = asyncio.create_task(_monitor(session_id))
        try:
            result = await orchestrator.research(...)
        finally:
            monitor.cancel()
            self._main_tasks.pop(session_id, None)
```

> **代码复用机会**：`_check_paused`（L71-80）已有暂停等待循环。可将该循环改造为可被监控器复用的协程，避免维护两套暂停检测逻辑。

### 修复 3（P1）：pause_research 取消并清理

> ⚠️ `fail_task` 发送 `SSEEventType.ERROR`，前端会显示"任务失败"而非"任务已暂停"。需区分：暂停发送专用事件或改用 `cancel_task`（发送 `SSEEventType.CANCELLED`）。

```python
async def pause_research(self, task_id):
    session["paused"] = True
    # 取消后台任务
    exec_task = self._executor_tasks.pop(task_id, None)
    if exec_task and not exec_task.done():
        exec_task.cancel()
    # 清理 session 状态
    session["mode"] = "chat"
    session["current_step"] = 0
    session.pop("research_result", None)
    session.pop("final_plan", None)
    # 更新 ProgressStreamer（用 cancel_task 避免前端显示"错误"）
    from src.core.progress_streamer import ProgressStreamer
    ProgressStreamer.cancel_task(task_id, "Task paused by user")
    ...
```

> 若需在前端区分"暂停"与"取消"，需在 `ProgressStreamer` 中新增 `PAUSED` 事件类型和对应通知方法。

### 修复 4（P1）：清理 cancel_research 重复代码 + 对齐 SSE 事件

移除第 2762-2764 行的重复 `pop+cancel`。保留单次取消逻辑，并确保 `cancel_task` 发送 `SSEEventType.CANCELLED`（而非 `ERROR`）。

### 修复 5（P1）：SSE 断连自动暂停

重建断连回调机制：

```python
# ProgressStreamer 类新增
_disconnect_callbacks: Dict[str, Callable] = {}

@classmethod
def set_disconnect_callback(cls, task_id, callback):
    cls._disconnect_callbacks[task_id] = callback

# generate() finally 中触发：
finally:
    self.unsubscribe()
    cb = self._disconnect_callbacks.pop(self.task_id, None)
    if cb:
        asyncio.create_task(cb(self.task_id))

# ResearchAPI 中定义回调并注册：
def _on_sse_disconnect(self, task_id):
    asyncio.create_task(self.pause_research(task_id))

# 在 _start_execution 和 resume_research 中注册：
ProgressStreamer.set_disconnect_callback(session_id, self._on_sse_disconnect)
```

### 修复 6（P1）：resume 重新执行路径注册 task

```python
# research_api.py:2640 — 补上 _executor_tasks 注册
new_task = asyncio.create_task(executor.execute(task_id, plan, session_manager))
self._executor_tasks[task_id] = new_task  # ← 新增
new_task.add_done_callback(lambda _: self._executor_tasks.pop(task_id, None))
```

### 修复 7（P1）：_generate_documents_from_cache 加 CancelledError 处理

```python
async def _generate_documents_from_cache(self, ...):
    try:
        ...
        preview_result = await self._orchestrator._document_agent.execute(...)
        ...
    except asyncio.CancelledError:
        logger.info(f"Cache doc generation cancelled: {session_id}")
        session["research_result"] = {"status": "cancelled"}
        session["mode"] = "chat"
        raise
    except Exception as e:
        ...
```

---

## 5. 版本演化

| 版本 | 特点 | 问题 |
|------|------|------|
| v1（初版） | 根因1完全错误；遗漏 `_on_sse_disconnect`；误判 session list | 多处事实错误 |
| v2（修正） | 修正根因1为 `_on_sse_disconnect`；新增 CancelledError、重复代码 | 代码已在审核中被移除（见注1），报告与实际不符 |
| **v3（当前）** | **与当前代码对齐**；删除已不存在的根因；聚焦 2×P0 + 3×P1 | — |

> **注1**：v1→v2 审核期间对话中添加的代码（`_disconnect_callbacks`、`set_disconnect_callback`、`_on_sse_disconnect` 引用、`pause_research` 中的 `exec_task.cancel()`）被移除，恢复为原始基线。这不是严格的"回滚"（原始代码中不存在这些机制），而是"移除新增代码"。
