# "重新生成HTML文档"触发全量重跑问题分析

## 1. 用户场景

用户完成一次研究后，发现HTML报告有问题（如空表格），只想**重新生成HTML文档**，
但系统却**重新跑了一次完整研究**，浪费时间且覆盖了缓存数据。

同时，暂停后尝试操作时收到：
> "Research already completed while paused"

## 2. 完整链路追踪

### 2.1 用户消息入口

```
前端 ChatPanel → POST /api/v1/research/interact
  → research_api.handle_interact(session_id, step=0, response)
    → research_api._handle_user_message(session_id, user_input)
```

### 2.2 消息路由（`_handle_user_message`, L262）

```
mode = session.get('mode', 'chat')  # 研究完成后 mode='research' 或 'chat'

if mode == 'research':
    → _handle_research_msg()     # L332
if mode == 'chat':
    → _handle_chat_mode()        # L320
```

### 2.3 路径A：研究完成后的 `_handle_research_msg`（L336）

```python
# L344: 关键分支！
if research_result and research_result.get('status') == 'completed':
    session['mode'] = 'chat'  # 切换到chat模式
    return await self._handle_chat_mode(session_id, user_input)  # 走chat路径
```

**问题1**：研究完成后，`_handle_research_msg` 会把 `mode` 改为 `'chat'`，
然后走 `_handle_chat_mode`。但 `_handle_chat_mode` 中 LLM 可能解析出
`action='enter_framework'` 或 `action='start_execution'`，导致**重新启动一个全新研究**。

### 2.4 路径B：暂停状态下的 `_handle_research_msg`（L355）

```python
if cm.is_paused(session_id):
    conv_result = await self._llm_converse(session_id, user_input)
    action = conv_result.get('action', 'continue_chat')
    if action == 'resume_research':
        return await self.resume_research(session_id)       # L363
    if action == 'regenerate_report':
        return await self.resume_research(session_id)       # L366 ← BUG!
```

**问题2**：`regenerate_report` 被错误地路由到 `resume_research()`，
而 `resume_research()` 检查到 `research_result.status == 'completed'`（L1921）：

```python
rr = session.get('research_result')
if rr and rr.get('status') == 'completed':
    return {'task_id': task_id, 'status': 'completed',
            'message': 'Research already completed while paused'}
```

直接返回"Research already completed while paused"，**没有做任何文档重生成**。

### 2.5 路径C：chat模式下的 `_handle_chat_mode`（L441）

```python
# L538: chat模式也有 regenerate_report 分支
if action == 'regenerate_report':
    logger.info(f"LLM returned regenerate_report for {session_id}")
    return await self.resume_research(session_id)  # L540 ← 同样的BUG!
```

**问题3**：chat模式下 `regenerate_report` 也路由到 `resume_research()`，
同样会返回"Research already completed while paused"。

### 2.6 LLM Prompt中 `regenerate_report` 的定义

在 `_llm_converse` 的 prompt 中（L710, L714, L725）：

```
- Regenerate from cache → regenerate_report
- Regenerate → regenerate_report
```

LLM被明确告知：用户说"重新生成"时应该返回 `regenerate_report` action。
但代码将 `regenerate_report` 路由到 `resume_research()`，这是**语义错误**。

## 3. 根因总结

| 问题 | 位置 | 根因 |
|------|------|------|
| "Research already completed while paused" | `research_api.py:1921` | `regenerate_report` 路由到 `resume_research()`，后者检测到已完成直接返回 |
| 重新跑全量研究 | `research_api.py:344→320` | 研究完成后mode切chat，LLM可能返回 `enter_framework` 触发新研究 |
| `regenerate_report` 语义错误 | `research_api.py:366,540` | "重新生成文档"≠"恢复研究"，但代码将两者等价 |

## 4. 数据格式差异（测试验证）

### 4.1 session['research_result'] 格式

```python
{
    "task_id": "xxx",
    "status": "completed",
    "topic": "Topic",
    "report": {                    # ← sections 在 report 下
        "sections": [...]
    },
    "summary": "...",
}
```

### 4.2 research_result_cache.json 格式

```python
{
    "task_id": "xxx",
    "topic": "Topic",
    "title": "Topic",
    "aspects": [...],
    "sections": [...],             # ← sections 在顶层
    "sources": [...],
    "key_findings": [...],
}
```

### 4.3 _document_agent 期望格式

`ContentOrchestrator.transform_to_html()` L170:
```python
sections = self._parse_sections(research_result.get("sections", []))
```

**关键发现**：`_document_agent` 期望 `sections` 在顶层，但 `session['research_result']`
的 `sections` 在 `report` 下。直接传入会导致空 sections。

### 4.4 格式转换逻辑

```python
def convert_session_to_cache_format(session_rr):
    """将 session['research_result'] 转换为 _document_agent 期望的格式"""
    converted = dict(session_rr)
    if "report" in converted and "sections" not in converted:
        report = converted.get("report", {})
        converted["sections"] = report.get("sections", [])
        converted["topic"] = converted.get("topic", report.get("topic", ""))
        converted["title"] = converted.get("topic", "")
    return converted
```

## 5. 已有的正确实现

### 5.1 `_generate_documents_from_cache()` 方法（L1994）

**已存在**，但未被 `regenerate_report` action 调用！

```python
async def _generate_documents_from_cache(self, session_id, research_result_data, output_dir, session):
    """Generate preview + document from cached research result, skipping orchestrator."""
    preview_input = {
        'action': 'produce_document',
        'research_result': research_result_data,  # ← 必须是 cache 格式
        'output_format': 'html',
        ...
    }
    preview_result = await self._orchestrator._document_agent.execute(preview_input)
    PreviewStorage.copy_file(session_id, Path(preview_path))
    ...
```

**调用场景**：仅被 revision 确认流程调用（L2518）。

### 5.2 `generate_document_later()` 方法（orchestrator.py:4088）

**已存在**，但数据源是 `_task_history` 或 `_storage_manager`，不是 session。

```python
async def generate_document_later(self, task_id, output_format, ...):
    # 从 _task_history 或 _storage_manager.load() 获取数据
    task_record = ...
    research_result = dict(task_record.get("result", {}))
    doc_result = await self._document_agent.execute({
        "action": "produce_document",
        "research_result": research_result,
        ...
    })
```

**问题**：`research_executor.py` 每次执行都创建新的 `ResearchOrchestrator` 实例，
`_task_history` 是空的。`_storage_manager` 从磁盘加载，但需要确认数据是否正确保存。

## 6. 修复方案

### 6.1 新增 `_regenerate_report` 方法（`research_api.py`）

```python
async def _regenerate_report(self, session_id, output_format='html'):
    """基于已有研究结果重新生成文档，不重新执行研究"""
    session = session_manager.get(session_id)
    if not session:
        return {'error': 'Session not found', 'error_code': 'SESSION_NOT_FOUND'}

    research_result = session.get('research_result', {})
    if not research_result or research_result.get('status') != 'completed':
        return {'error': 'No completed research to regenerate from',
                'error_code': 'NO_COMPLETED_RESEARCH'}

    # 1. 尝试从缓存文件加载（cache 格式）
    task_id = research_result.get('task_id', session_id)
    cache_path = Path('data') / task_id / 'research_result_cache.json'
    if not cache_path.exists():
        cache_path = Path('data') / session_id / 'research_result_cache.json'

    if cache_path.exists():
        import json
        research_result_data = json.loads(cache_path.read_text(encoding='utf-8'))
    else:
        # 2. 从 session 数据转换格式
        research_result_data = self._convert_session_to_cache_format(research_result)

    # 3. 调用已有的文档生成方法
    output_dir = Path('data') / session_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        await self._generate_documents_from_cache(
            session_id, research_result_data, output_dir, session
        )
    except Exception as e:
        logger.error(f"Regenerate report failed: {e}")
        return {'error': str(e), 'error_code': 'REGENERATE_FAILED'}

    # 4. 推送SSE事件
    try:
        from src.core.session_streamer import SessionStreamer
        SessionStreamer.push_preview_refresh(session_id, {})
    except Exception:
        pass

    return {
        'session_id': session_id,
        'status': 'completed',
        'message': '文档已重新生成',
    }

def _convert_session_to_cache_format(self, session_rr):
    """将 session['research_result'] 转换为 _document_agent 期望的格式"""
    converted = dict(session_rr)
    if "report" in converted and "sections" not in converted:
        report = converted.get("report", {})
        converted["sections"] = report.get("sections", [])
        converted["topic"] = converted.get("topic", report.get("topic", ""))
        converted["title"] = converted.get("topic", "")
    return converted
```

### 6.2 修改 `regenerate_report` 路由（2处）

**文件**: `src/api/research_api.py`

| 行号 | 当前代码 | 修改为 |
|------|----------|--------|
| L366 | `return await self.resume_research(session_id)` | `return await self._regenerate_report(session_id)` |
| L540 | `return await self.resume_research(session_id)` | `return await self._regenerate_report(session_id)` |

### 6.3 防止chat模式误触发新研究

**文件**: `src/api/research_api.py` L725

当前prompt：
```
If the user asks to retry, regenerate, or modify the research, use `enter_framework`.
```

修改为：
```
If the user asks to retry or start a new research, use `enter_framework`.
If the user asks to regenerate or refresh the report/document, use `regenerate_report`.
```

### 6.4 `resume_research` 的已完成检测保持不变

**文件**: `src/api/research_api.py` L1921

保持当前行为：研究已完成时返回 "already completed"。
`regenerate_report` action 不应路由到 `resume_research()`。

## 7. 测试验证

测试文件：`tests/unit/test_regenerate_report_bug.py`

### 7.1 Bug 确认测试（全部通过）

| 测试 | 验证内容 |
|------|----------|
| `test_resume_research_returns_already_completed` | `resume_research()` 对已完成研究返回 "already completed" |
| `test_paused_mode_completed_routes_to_resume_research` | 暂停+已完成场景下 `regenerate_report` 路由到 `resume_research()` |
| `test_chat_mode_routes_to_resume_research` | chat模式下 `regenerate_report` 路由到 `resume_research()` |
| `test_completed_research_in_research_mode_falls_to_chat` | research模式下已完成研究切换到chat模式 |

### 7.2 数据格式测试（全部通过）

| 测试 | 验证内容 |
|------|----------|
| `test_session_format_has_sections_under_report` | session 格式 sections 在 report 下 |
| `test_cache_format_has_top_level_sections` | cache 格式 sections 在顶层 |
| `test_document_agent_expects_top_level_sections` | `_document_agent` 期望顶层 sections |
| `test_session_data_needs_format_conversion` | session 数据需要格式转换 |

### 7.3 现有方法测试（通过）

| 测试 | 验证内容 |
|------|----------|
| `test_method_exists_and_works` | `_generate_documents_from_cache()` 存在且可用 |

## 8. 影响范围

- `src/api/research_api.py`: 2处路由修改 + 1处prompt修改 + 2个新方法
- 无前端修改（前端只需正确处理返回的status/message）
- 无数据库/存储结构变更

## 9. 修复后测试用例

1. 已完成研究后说"重新生成HTML" → 应只生成文档，不跑研究
2. 暂停后说"重新生成" → 应生成文档，不返回"already completed"
3. chat模式下说"重新生成报告" → 应走 `_regenerate_report`，不走 `enter_framework`
4. 无缓存数据时"重新生成" → 应从 session 数据转换格式后生成
5. 完全无数据时"重新生成" → 应返回明确错误
