# 预览报告 "Cannot preview this format" 问题分析与修复方案

> 日期: 2026-06-13
> 严重程度: P0 (用户可见的功能完全不可用)
> 影响范围: 所有质量评分未达标的 research 任务

## 1. 问题描述

用户完成 research 后，前端显示:

```
**Research Complete** ✅
Research completed. Quality score: 36.6 (warnings)
View Report
```

点击 "View Report" 后，预览区显示 **"Cannot preview this format"** 而非报告内容。

即使用户能看到质量分数和 warnings 提示，但 **无法预览报告**，用户会误以为报告不存在或系统出错了。

## 2. 根因分析

### 2.1 核心矛盾：两种完成状态 vs 硬编码检查

orchestrator 返回两种合法完成状态:

| 状态 | 含义 | 触发条件 |
|------|------|---------|
| `"completed"` | 质量达标 | `quality_passed == True` (`orchestrator.py:1104,2076`) |
| `"completed_with_warnings"` | 质量未达标但有报告 | `quality_passed == False` |

`research_executor.py:397` 将此值原样写入 `session['research_result']['status']`。

但多处代码对 `status` 做 `== 'completed'` 硬编码检查，**忽略了 `"completed_with_warnings"`**。

### 2.2 完整阻塞链路

```
orchestrator.status = "completed_with_warnings"
        │
        ▼
research_executor.py:397
  session["research_result"]["status"] = "completed_with_warnings"
        │
        ├────► 阻塞点1: get_preview (research_api.py:1973)
        │        status != 'completed' → 返回空预览
        │        结果: 前端 html_content=null, preview_url=null
        │
        ├────► 阻塞点2: get_research_detail (main.py:565)
        │        status == "completed" → False
        │        结果: has_valid_result=False, preview_url 不写入响应
        │
        └────► 阻塞点3: _handle_research_mode (research_api.py:365)
                 status == 'completed' → False
                 结果: 不进入 chat 模式, 后续交互受阻
```

### 2.3 前端行为

`DocumentPreview.tsx:370-399` 渲染逻辑:

```tsx
{format === 'html' && preview.html_content ? (
  <iframe srcDoc={preview.html_content} />      // 有 html_content → 正常渲染
) : preview.preview_url ? (
  <iframe src={buildDownloadUrl(preview.preview_url)} />  // 有 url → iframe 加载
) : (
  <p>Cannot preview this format</p>              // 都没有 → 显示错误
)}
```

后端返回 `{ html_content: null, preview_url: null }` → 走第三个分支 → "Cannot preview this format"。

## 3. 所有问题点清单

### 3.1 后端: status 硬检查 (3处关键阻塞 + 2处遗漏)

| # | 文件 | 行号 | 当前代码 | 问题 |
|---|------|------|---------|------|
| B1 | `src/api/research_api.py` | 1973 | `status != 'completed'` | **预览直接返回空 — 主要阻塞** |
| B2 | `src/api/main.py` | 565 | `status == "completed"` | detail API 不返回 preview_url |
| B3 | `src/api/research_api.py` | 365 | `status == 'completed'` | 不进入 chat 模式 |
| B5 | `src/api/research_api.py` | 2067 | `status == 'completed'` | 取消恢复场景跳过 |
| B6 | `src/api/research_executor.py` | 179 | `result.status == "completed"` | inject 结果合并被跳过 |

### 3.2 后端: status 硬编码覆盖 (1处)

| # | 文件 | 行号 | 当前代码 | 问题 |
|---|------|------|---------|------|
| B7 | `src/api/research_executor.py` | 196 | `"status": "completed"` 硬编码 | inject 合并覆盖原始 warnings |

### 3.3 后端: 完成消息误导 (1处)

| # | 文件 | 行号 | 当前代码 | 问题 |
|---|------|------|---------|------|
| B4 | `src/api/research_executor.py` | 467-472 | `"**Research Complete** ✅"` | 无论质量是否达标，都显示 ✅，对用户产生误导 |

### 3.4 后端: 正确实现参考 (已正确处理)

| 文件 | 行号 | 正确代码 |
|------|------|---------|
| `src/api/research_api.py` | 2202 | `status not in ('completed', 'completed_with_warnings')` |
| `src/api/research_api.py` | 746 | `status in ('completed', 'completed_with_warnings')` |
| `src/api/research_api.py` | 362 | `status not in ('completed', 'cancelled', 'error')` |
| `src/api/research_executor.py` | 456 | `"passed" if orchestrator_result.status == "completed" else "warning"` — 逻辑正确，`completed_with_warnings` 正确映射为 `"warning"` |

### 3.5 前端: 无额外阻塞

前端 `DocumentPreview.tsx:44` 的 `enabled` 条件:
```tsx
enabled: !!taskId && (status === 'completed' || !!taskIdOverride)
```

这里的 `status` 来自 `useResearchStore`，由 SSE `complete` 事件设置（`useProgress.ts:104`）。SSE `complete` 事件由 `ProgressStreamer.complete_task()` 触发，此时 `task.status` 始终设为 `"completed"`（`progress_streamer.py:387`），所以前端 `enabled` 条件**始终满足**，不是阻塞点。

但前端缺少对 `completed_with_warnings` 的 **用户提示**（见 4.3 节）。

## 4. 修复方案

### 4.1 后端: 修复6处 status 硬检查/覆盖 (P0, 必须修复)

**B1: `src/api/research_api.py:1973`**
```python
# Before:
if not research_result or research_result.get('status') != 'completed':
# After:
if not research_result or research_result.get('status') not in ('completed', 'completed_with_warnings'):
```

**B2: `src/api/main.py:565`**
```python
# Before:
has_valid_result = bool(research_result and research_result.get("status") == "completed")
# After:
has_valid_result = bool(research_result and research_result.get("status") in ("completed", "completed_with_warnings"))
```

**B3: `src/api/research_api.py:365`**
```python
# Before:
if research_result and research_result.get('status') == 'completed':
# After:
if research_result and research_result.get('status') in ('completed', 'completed_with_warnings'):
```

**B5: `src/api/research_api.py:2067`**
```python
# Before:
if rr and rr.get('status') == 'completed':
# After:
if rr and rr.get('status') in ('completed', 'completed_with_warnings'):
```

**B6: `src/api/research_executor.py:179`**
```python
# Before:
if session and result and result.status == "completed":
# After:
if session and result and result.status in ("completed", "completed_with_warnings"):
```

**B7: `src/api/research_executor.py:196`** — inject 合并后保留原始 status
```python
# Before:
session["research_result"] = {
    "task_id": original.get("task_id") or original_task_id,
    "status": "completed",
    ...
}
# After:
_original_status = original.get("status", "completed")
_inject_status = result.status  # ResearchResult.status
_merged_status = "completed_with_warnings" if (
    _original_status == "completed_with_warnings" or _inject_status == "completed_with_warnings"
) else "completed"
session["research_result"] = {
    "task_id": original.get("task_id") or original_task_id,
    "status": _merged_status,
    ...
}
```

### 4.2 后端: 修复完成消息区分质量状态 (P1, 用户体验)

**B4: `src/api/research_executor.py:467-472`**

当前代码无论质量是否达标都显示 `"**Research Complete** ✅"`，应当区分:

```python
# Before:
_final_msg = f"**Research Complete** ✅\n\n{_summary_text[:1000]}" if _summary_text else (
    f"**Research Complete** ✅\n\n"
    f"Research on 「{topic}」has been completed. "
    ...
)

# After:
if orchestrator_result.status == "completed_with_warnings":
    _final_msg = (
        f"**Research Complete** ⚠️\n\n"
        f"Quality score: {getattr(orchestrator_result, 'quality_score', 0):.1f} — "
        f"report has quality issues but is available for preview.\n\n"
        f"{_summary_text[:800]}"
    ) if _summary_text else (
        f"**Research Complete** ⚠️\n\n"
        f"Research on 「{topic}」has been completed with quality warnings. "
        f"Quality score: {getattr(orchestrator_result, 'quality_score', 0):.1f}. "
        f"You can preview the report and request revisions.\n"
    )
    _suggestions = [
        {"id": "view_report", "label": "View Report", "example": "Show me the full report"},
        {"id": "improve_quality", "label": "Improve Quality", "example": "Please improve the report quality"},
    ]
else:
    _final_msg = f"**Research Complete** ✅\n\n{_summary_text[:1000]}" if _summary_text else (
        f"**Research Complete** ✅\n\n"
        f"Research on 「{topic}」has been completed. "
        f"{orchestrator_result.stages_completed} stages completed, "
        f"{_section_count} sections generated."
    )
    _suggestions = [
        {"id": "view_report", "label": "View Report", "example": "Show me the full report"},
    ]
```

### 4.3 前端: 质量警告提示 (P2, 增强体验, 可后续迭代)

当前前端 `DocumentPreview` 通过 SSE `quality_result` 事件已经能显示 `RevisionHintBar`，但仅在 revision 后触发。初次加载时，如果 `qualityState.overall_status === 'warning'`，应当在预览区顶部显示提示条:

> ⚠️ 报告质量未达标 (分数: 36.6)，你可以要求修改特定章节以提升质量。

这不需要在本次修复中实现，可作为后续增强。

## 5. 修复优先级与验证

| 优先级 | 修复项 | 预期效果 |
|--------|--------|---------|
| **P0** | B1+B2+B3+B5+B6+B7: status 硬检查/覆盖 | 预览功能恢复，无论质量达标与否均可查看 |
| **P1** | B4: 完成消息区分 | 用户不再被误导，明确知道质量状态 |
| P2 | 前端质量提示条 | 增强体验，鼓励用户要求修改 |

### 验证方法

1. **P0 验证**: 运行一个 research 任务使其产生 `completed_with_warnings` 状态，确认:
   - `GET /api/v1/research/preview/{task_id}` 返回 `html_content` 非空
   - `GET /api/v1/research/{task_id}` 返回 `preview_url` 非空
   - 前端预览区正常显示报告内容

2. **P1 验证**: 确认 chat 面板消息:
   - `completed` → "Research Complete ✅"
   - `completed_with_warnings` → "Research Complete ⚠️ ... Quality score: XX.X"

3. **回归测试**: 运行 `pytest tests/unit/core/orchestrator/ tests/unit/storage/ tests/integration/` 确认无回归

## 6. 补充发现: 同类潜在风险

以下是代码中使用 `research_result.get('status')` 或 `result.status` 做判定的完整清单，标注了是否需要修复:

| 文件 | 行号 | 检查方式 | 是否需修复 | 说明 |
|------|------|---------|-----------|------|
| `research_api.py` | 1973 | `!= 'completed'` | **是 (B1)** | 预览阻塞 |
| `main.py` | 565 | `== "completed"` | **是 (B2)** | detail API 阻塞 |
| `research_api.py` | 365 | `== 'completed'` | **是 (B3)** | chat 模式阻塞 |
| `research_api.py` | 362 | `not in ('completed', 'cancelled', 'error')` | 否 | 判断是否仍在运行，逻辑正确 |
| `research_api.py` | 746 | `in ('completed', 'completed_with_warnings')` | 否 | 已正确处理 |
| `research_api.py` | 2202 | `not in ('completed', 'completed_with_warnings')` | 否 | 已正确处理 |
| `research_api.py` | 2067 | `== 'completed'` | **是 (B5)** | 取消恢复场景跳过 |
| `research_api.py` | 2165 | `'status': 'cancelled'` | 否 | 取消场景，与完成状态无关 |
| `research_api.py` | 2169 | `'status': 'completed'` | 否 | `_generate_documents_from_cache` 主动设为 completed，正确 |
| `research_executor.py` | 179 | `result.status == "completed"` | **是 (B6)** | inject 操作后检查 ResearchResult 状态，`completed_with_warnings` 时跳过合并 |
| `research_executor.py` | 196 | `"status": "completed"` 硬编码 | **是 (B7)** | inject 合并后覆盖原始 status，丢失 warnings 信息 |
| `research_executor.py` | 456 | `== "completed"` (三元表达式) | 否 | `"passed" if orchestrator_result.status == "completed" else "warning"` — `completed_with_warnings` 正确映射为 `"warning"` |
| `orchestrator.py` | 2873 | `== "completed"` | 否 | 检查 survey_result，非 research_result |
| `orchestrator.py` | 4103 | `!= "completed"` | 否 (死代码) | 见下方详细分析 |

### B5: `research_api.py:2067` 详细说明

```python
if rr and rr.get('status') == 'completed':
```
这是在取消恢复逻辑中，`completed_with_warnings` 时也会跳过此分支。需要同步修复。

### B6: `research_executor.py:179` 详细说明

```python
if session and result and result.status == "completed":
```
这里的 `result` 是 `ResearchResult` 对象（`orchestrator.py:158-177`）。当 inject 操作返回 `"completed_with_warnings"` 时，合并逻辑被跳过，导致 inject 的结果丢失。应改为:
```python
if session and result and result.status in ("completed", "completed_with_warnings"):
```

### B7: `research_executor.py:196` 详细说明

```python
session["research_result"] = {
    "task_id": ...,
    "status": "completed",    # 硬编码，丢失了原始的 "completed_with_warnings"
    ...
}
```
应保留原始 status 或取两者中更差的状态:
```python
_original_status = original.get("status", "completed")
_inject_status = result.status  # ResearchResult.status
_status = "completed_with_warnings" if (_original_status == "completed_with_warnings" or _inject_status == "completed_with_warnings") else "completed"
```

### `orchestrator.py:4103` 详细分析

```python
if task_record.get("result", {}).get("status") != "completed":
```

此行属于 `complete_research()` 方法（`orchestrator.py:4059`）。经确认，**该方法在整个代码库中无任何调用方**（搜索 `complete_research` 仅出现定义本身），属于死代码。

此外，即使未来被调用，此行也存在两个 bug:

**Bug 1: 存储路径始终返回错误** — `StorageManager.load()` 返回 `data.get("result")`（`storage_manager.py:294`），即 `aggregated.to_dict()`。该 dict 的结构为 `{"data": ..., "conflicts": ..., "sections": ..., "key_findings": ...}`，没有 `"result"` 键。因此 `.get("result", {})` 返回 `{}`，`.get("status")` 返回 `""`，`!= "completed"` 始终为 True → 永远返回 `RESEARCH_NOT_COMPLETED`。

**Bug 2: 内存路径 AttributeError** — 当 `task_record` 来自 `self._task_history`（`orchestrator.py:1402-1406`）时，`task_record["result"]` 是 `ResearchResult` dataclass 对象，没有 `.get()` 方法，调用 `.get("status")` 会抛出 `AttributeError`。

若将来启用此方法，修复方案:
```python
_result = task_record.get("result", {})
if hasattr(_result, 'status'):
    _status = _result.status
else:
    _status = _result.get("status", "")
if _status not in ("completed", "completed_with_warnings"):
    return {
        "success": False,
        "error": f"Research {task_id} not completed",
        "error_code": "RESEARCH_NOT_COMPLETED",
    }
```

### `document_api.py:736` 详细分析

```python
return await self._research_result_store.list_results(limit=limit, status="completed")
```

此行在当前运行配置中**不会执行**。`DocumentAPI` 在 `main.py:786` 实例化时未传入 `research_result_store` 参数，因此 `self._research_result_store` 为 `None`，`if self._research_result_store:` 判断为 `False`，代码走入 mock 分支。

若将来注入 `research_result_store`，还存在额外 bug: `list_results()` 是同步方法（`research_result_store.py:519` 为 `def` 非 `async def`），`await` 一个非协程对象会抛出 `TypeError`。

若将来启用此路径，修复方案:
1. 移除 `await`（`list_results` 是同步方法）
2. 将 `status="completed"` 改为支持 `completed_with_warnings`:
   - 方案A: 传 `status=None` 跳过状态过滤
   - 方案B: 修改 `research_result_store.py:557` 的过滤逻辑:
     ```python
     # Before:
     if status and metadata.status != status:
         continue
     # After:
     if status and metadata.status != status:
         if not (status == "completed" and metadata.status == "completed_with_warnings"):
             continue
     ```

### CLI 文件 (不影响前端，仅记录)

| 文件 | 行号 | 检查方式 | 是否需修复 | 说明 |
|------|------|---------|-----------|------|
| `cli/main.py` | 451 | `result.status == "completed"` | 否 | CLI 路径，不影响前端预览 |
| `cli/commands/session.py` | 156 | `result.status == "completed"` | 否 | CLI resume，不影响前端预览 |
| `cli/commands/session.py` | 249 | `result.status == "completed"` | 否 | CLI revise，不影响前端预览 |

> CLI 中 `completed_with_warnings` 会走 `else` 分支显示 "Resume/Revision failed: completed_with_warnings"，对用户有误导但非前端阻塞，建议后续统一修复。

## 7. 实施计划

1. 修复 B1+B2+B3+B5+B6+B7 (6处 status 硬检查/覆盖) — 统一改为 `in ('completed', 'completed_with_warnings')` 或保留原始 status
2. 修复 B4 (完成消息区分) — 区分 ✅ 和 ⚠️
3. 运行测试套件确认无回归
4. 手动运行 research 任务验证端到端流程
