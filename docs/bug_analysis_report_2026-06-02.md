# 问题分析报告（终审版 — 所有代码已验证 + 修复实施）

> **修复状态：** Bug 1/2A/2B/3 ✅ **全部已修复**，含 ValueError retry enhancement — 通过 71 单元测试 + 9 集成测试 + 240 回归测试

## 问题 1：系统中途停止，提示"抱歉，我临时遇到了问题"

### 现象
研究过程中系统偶尔中断，会话窗口显示"抱歉，我临时遇到了问题，请再试一次。你想研究什么？"

后半句"你想研究什么？"意味着 `research_context.topic` 为空——即系统认为用户还没有确定研究主题。

### 根因分析

该错误消息来自 `_fallback_response()` 方法，唯一触发点：

```python
# research_api.py:458-462
        try:
            conv_result = await self._llm_converse(session_id, user_input, conv_machine.current_state)
        except Exception as e:
            logger.error(f"LLM conversation failed: {e}")
            return self._fallback_response(session_id, context)
```

`_fallback_response` 本身的逻辑：

```python
# research_api.py:1010-1019 (修复后)
    def _fallback_response(self, session_id, context):
        """Safe fallback when LLM fails — acknowledges issue without alarming user"""
        session = session_manager.get(session_id) if session_id else None
        lang = self._get_lang(session)
        existing_topic = context.get('topic')
        if not existing_topic and session:                        # ← 修复：从 session.research_context 恢复
            existing_topic = session.get('research_context', {}).get('topic')
        if existing_topic:
            return self._chat_response(session_id, self._l(f"抱歉，我临时遇到了问题。我们刚才在讨论 **{existing_topic}**，请再试一次。", ...))
        return self._chat_response(session_id, self._l('抱歉，我临时遇到了问题，请再试一次。你想研究什么？', ...))
```

**为什么 `context.get('topic')` 可能为空：** `_handle_chat_mode` 中传入的 `context` 来自 `session.get('research_context', {})`。如果用户已确认主题但 LLM 在首次框架构建时失败（此时 `topic` 已存入 `research_context`），fallback 能正确显示主题。但如果 topic 是在当前 `_llm_converse` 调用中才确定的（如 LLM 解析出 topic 但后续 JSON 解析失败），`conv_result` 中的 topic 尚未回写到 `context`，fallback 就会丢失主题信息。

**`_llm_converse` 中会抛到外层的异常路径：**

```python
# research_api.py:759 — LLM 返回 success=False
            if not result.get('success'):
                raise ValueError(f"LLM call failed: {result.get('error', 'Unknown error')}")

# research_api.py:762 — LLM 返回空内容
            if not content or not content.strip():
                raise ValueError('LLM returned empty content')

# research_api.py:772 — 首轮 JSON 提取失败 + retry 也失败
            if not json_str:
                logger.error(f"Could not extract JSON from LLM response (iteration {iteration}), content preview: {content[:200]}")
                if iteration == 0:
                    retry_content = await self._retry_json_only(llm_skill, system_prompt, llm_config, session_id)
                    if retry_content:
                        content = retry_content
                        json_str = self._extract_json_from_llm_content(content)
                if not json_str:
                    raise ValueError(f"LLM response contains no valid JSON: {content[:200]}")
```

**不会抛到外层的路径（只 break，不 raise）：**

```python
# research_api.py:752-754 — 超时
            except asyncio.TimeoutError:
                logger.warning(f"LLM call timed out (iteration {iteration}), using accumulated results")
                break

# research_api.py:755-757 — LLM execute() 抛非超时异常
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                break

# research_api.py:773-784 — 后续轮 JSON 解析失败
            except json.JSONDecodeError as e:
                ...
                if not parsed:
                    break
```

### 补充：为什么"继续"后任务还能推进？

系统中存在两条并行的执行路径：

**1. 同步对话路径**（`_handle_chat_mode` → `_llm_converse`）：负责理解用户意图、返回即时响应。这条路径失败会触发 `_fallback_response`，但**不影响后台研究任务**。

**2. 异步研究执行路径**（`_handle_research_msg` → 后台 `asyncio.create_task`）：研究任务一旦启动，就作为独立的 async task 在后台运行。

路由逻辑在 `_handle_user_message` 中：

```python
# research_api.py:295-332
        mode = session.get('mode', 'chat')
        ...
        if mode == 'framework':
            ...
            return await self._handle_framework_mode(session_id, user_input)

        if mode == 'chat':
            return await self._handle_chat_mode(session_id, user_input, skip_lang_detect)

        if mode == 'research':
            ...
            return await self._handle_research_msg(session_id, user_input, session)
```

当对话层 LLM 调用失败返回"临时遇到问题"时，后台研究任务仍在继续执行。用户说"继续"时，`_handle_user_message` 检测到 `mode='research'`，走 `_handle_research_msg` 路径。`_handle_research_msg` 中 LLM 失败时返回的是"研究继续执行中"而非 fallback：

```python
# research_api.py:373-377
        except asyncio.TimeoutError:
            return {'session_id': session_id, 'step': session.get('current_step', 6), 'mode': 'research', 'status': 'running', 'message': '消息分析超时，您的消息已记录，研究继续执行中。', 'suggestions': [], 'next_step': 'continue_research'}
        except Exception as e:
            logger.error(f"LLM converse failed: {e}", exc_info=True)
            return {'session_id': session_id, 'step': session.get('current_step', 6), 'mode': 'research', 'status': 'running', 'message': '消息处理临时异常，研究继续执行中。', 'suggestions': [], 'next_step': 'continue_research'}
```

---

## 问题 2：研究开始后右侧预览区没有状态提示 + 研究框架反复展示

### 现象 A：研究框架一直显示在会话窗口

### 根因分析

**前端确认路径：**

```typescript
// ChatPanel.tsx:391-403
  const handleFrameworkSectionConfirm = async (selectedIds: string[]) => {
    if (!framework) return;
    const sectionMap = new Map(framework.sections.map((s, i) => [`section-${i}`, s]));
    const selectedLabels = selectedIds
      .map(id => sectionMap.get(id))
      .filter((label): label is string => label !== undefined);
    if (selectedLabels.length === 0) return;
    const isZh = /[\u4e00-\u9fff]/.test(framework.topic);
    const exampleText = isZh
      ? `确认开始研究，包含章节：${selectedLabels.join('、')}`
      : `Confirm and start research with sections: ${selectedLabels.join(', ')}`;
    try { await handleOptionSelect('confirm_start', exampleText); } catch (error) { console.error('Failed to confirm framework:', error); }
  };
```

`handleOptionSelect('confirm_start', exampleText)` → `api.clickSuggestion(sessionId, 'confirm_start', exampleText)` 发送 `{ suggestion_id: 'confirm_start', text: '确认开始研究...' }`

**后端 suggestion_id 覆盖逻辑（原始 bug 版本）：**

```python
# research_api.py:1556-1569 (原始 bug 版本，已修复)
        if step == 0:
            mode = session.get('mode', 'chat')
            user_message = response.get('text', response.get('message', ''))  # ← 先取到 exampleText
            suggestion_id = response.get('suggestion_id', response.get('id', ''))  # ← 'confirm_start'
            skip_lang = False
            if suggestion_id:  # ← True
                suggestion_map = {'add_details': 'add some details', 'start_framework': 'form a framework'}
                user_message = suggestion_map.get(suggestion_id, suggestion_id)  # ← map 无 'confirm_start' key → 回退为 'confirm_start'
                if not user_message:
                    user_message = suggestion_id
                skip_lang = True
```

**修复后的版本：**

```python
# research_api.py:1558-1573 (修复后)
        if step == 0:
            mode = session.get('mode', 'chat')
            user_message = response.get('text', response.get('message', ''))  # ← 先取到 exampleText
            suggestion_id = response.get('suggestion_id', response.get('id', ''))  # ← 'confirm_start'
            skip_lang = False
            if suggestion_id:
                suggestion_map = {'add_details': 'add some details', 'start_framework': 'form a framework'}
                if user_message:           # ← 修复：text 非空时保留
                    pass
                else:
                    mapped = suggestion_map.get(suggestion_id)
                    if mapped:
                        user_message = mapped
                    else:
                        user_message = suggestion_id
                skip_lang = True
```

**关键 bug：** `suggestion_id` 存在时无条件覆盖 `text`。`suggestion_map` 没有 `confirm_start` key，导致 `user_message = 'confirm_start'`（非自然语言）。

**完整调用链：**

```
前端 SectionSelector 确认按钮
  → handleFrameworkSectionConfirm (ChatPanel.tsx:391-403)
    → handleOptionSelect('confirm_start', exampleText)
      → POST /api/research/interact { suggestion_id: 'confirm_start', text: '确认开始研究...' }
        → handle_interact (research_api.py:1528-1577)
          → step==0 → suggestion_id 存在 → user_message = suggestion_map.get('confirm_start', 'confirm_start') = 'confirm_start'
          → _handle_user_message(session_id, 'confirm_start', skip_lang_detect=True)
            → mode=='framework' → _handle_framework_mode(session_id, 'confirm_start')
              → _llm_framework_modify(session_id, 'confirm_start')
                → LLM 看到 'confirm_start'，不在确认词列表 → 返回 action='modify'
              → _framework_response → 前端再次显示 SectionSelector
```

**LLM 确认词列表：**

```python
# research_api.py:1031 (在 _llm_framework_modify 的 prompt 中)
1. If the user confirms (e.g., '确认', '没问题', 'ok', '好的', '开始吧', 'looks good', 'proceed'), set action="confirm".
```

`'confirm_start'` 不在确认词列表中，LLM 大概率返回 `action='modify'`。

**LLM 调用失败时的默认返回：**

```python
# research_api.py:1048-1049
        except Exception:
            return {'action': 'modify', 'message': "I understand you'd like to adjust the framework. Please tell me what changes you'd like to make.", 'new_sections': None}

# research_api.py:1050-1051
        if not result.get('success'):
            return {'action': 'modify', 'message': "I understand you'd like to adjust the framework. Please tell me what changes you'd like to make.", 'new_sections': None}
```

所有失败路径都返回 `action='modify'`，导致框架反复展示。

**前端框架展示条件：**

```typescript
// ChatPanel.tsx:262
      if (framework && framework.sections && framework.sections.length > 0) {
        // 渲染 SectionSelector
```

后端 `_framework_response` 返回 `mode='framework'` + `framework` 数据：

```python
# research_api.py:1513-1524
    def _framework_response(self, session_id, message, suggestions=None):
        ...
        return {'session_id': session_id, 'step': 5, 'mode': 'framework', 'message': message, 'instruction': '', 'suggestions': suggestions, 'framework': framework_data, 'next_step': 'confirm_framework'}
```

前端收到 `mode='framework'` 后设置 `setStep(0, ...)` + `setFrameworkAction(data.framework)`，触发 SectionSelector 再次渲染。

### 现象 B：右侧预览区没有状态提示

**后端 `_start_execution` 返回值（原始 bug 版本，已修复）：**

```python
# research_api.py:1217 (原始 bug 版本)
return {'session_id': session_id, 'task_id': session_id, 'step': 'research', 'mode': 'executing', 'status': 'success', ...}
```

```python
# research_api.py:1217 (修复后)
return {'session_id': session_id, 'task_id': session_id, 'step': 6, 'mode': 'research', 'status': 'running', ...}
```

注意：`mode='executing'`, `step='research'`（字符串）, `status='success'`

**前端判断逻辑（两处）：**

```typescript
// useResearch.ts:479 (sendMessage 中)
        } else if (mode === 'research' && data.step === 6) {

// useResearch.ts:551 (handleOptionSelect 中)
        } else if (mode === 'research' && data.step === 6) {
```

前端期望 `mode === 'research'` 且 `data.step === 6`（数字），但后端返回 `mode='executing'` 且 `step='research'`（字符串），两个条件都不匹配。

---

## 问题 3：数据重复存储导致内存爆炸

### 现象
系统运行一段时间后变得极慢甚至卡死。日志显示 `data_points` 数量异常增长到 125,857 个。磁盘上单个 registry 文件最大 327 MB，数据目录总计 2.25 GB。

### 根因分析

#### 1. `PersistentSessionDict` 每次 key 变更都全量序列化写磁盘

```python
# session_manager.py:31-59
class PersistentSessionDict(dict):
    def __setitem__(self, key, value):
        ...
        super().__setitem__(key, value)
        self._manager._save_to_disk(self._session_id)  # ← 每次 key 变更都触发全量写入

    def update(self, *args, **kwargs):
        ...
        super().update(*args, **kwargs)
        self._manager._save_to_disk(self._session_id)  # ← 同上

    def pop(self, key, *args):
        result = super().pop(key, *args)
        self._manager._save_to_disk(self._session_id)  # ← 同上
        return result

    def clear(self):
        super().clear()
        self._manager._save_to_disk(self._session_id)  # ← 同上
```

```python
# session_manager.py:214-234
    def _save_to_disk(self, session_id: str) -> None:
        """Persist single session to disk using atomic write (temp file + rename)."""
        ...
        serialized = _serialize_value(session)  # ← 序列化整个 session 对象
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, ensure_ascii=False, indent=2)  # ← 全量 JSON 写入
        os_mod.replace(str(tmp_path), str(path))
```

当 session 中 `aggregated_data_points` 增长到 125,857 条时，每次 `session["key"] = value` 都要序列化数百 MB 数据并全量写入磁盘。

#### 2. QC 重试循环中数据追加不清理

```python
# engine.py:1310 — 在 QC 检查之前就已将 batch_results 追加到 all_results
                all_results.extend(batch_results)

# engine.py:1404-1442 (QC retry 循环)
                                # L-FIX-1: retry before failing (max 1 retry to avoid data accumulation)
                                _max_retries = getattr(self.config, 'max_retries', 1)
                                _qc_retries = 0
                                while _qc_retries < _max_retries:
                                    _qc_retries += 1
                                    ...
                                    _retry_results = await self._execute_agents_batch(
                                        batch_agents, requirement, all_results, scheduler,
                                        f"batch_{batch_index+1}_qc_retry{_qc_retries}"
                                    )
```

**双重累积问题：**

1. `all_results.extend(batch_results)` (L1310) 在 QC 检查之前执行，原始（质量不达标的）结果已追加到 `all_results`。
2. QC 重试时 `_execute_agents_batch` (L1415-1417) 接收已包含原始结果的 `all_results` 作为参数，P1-1 数据注入会从 `all_results` 中加载更多数据注入到重试 agent。
3. 重试通过后 `batch_results = _retry_results` (L1442) 仅替换局部变量，`all_results` 中仍保留原始结果。
4. 重试 agent 的 GenericAgent 实时持久化 (L1487-1518) 将新搜索结果全量写入 ResearchResultStore，与已有数据叠加。

#### 3. ResearchResultStore 全量覆盖写入

```python
# research_result_store.py:276-288
        result_data = {
            "task_id": task_id,
            "title": result.get("title", ""),
            "topic": result.get("topic", ""),
            "sections": result.get("sections", []),
            "key_findings": result.get("key_findings", []),
            "data_points": result.get("data_points", []),  # ← 全量写入，不增量
            "sources": result.get("sources", []),
            "completed_agents": result.get("completed_agents", []),
            "saved_at": datetime.now().isoformat()
        }
        self._atomic_write_json(result_path, result_data)
```

每次 `save_result` 都全量覆盖写入 `result.json`，当 `data_points` 增长到 125,857 条时，单次写入就涉及数百 MB。

#### 4. P1-1 数据注入：从 ResearchResultStore 加载全量数据注入到每个 agent

```python
# engine.py:2080-2105
                    if not filtered_data_points and not filtered_sources:
                        injected_data = False
                        try:
                            task_id_from_req = requirement.get("task_id")
                            if task_id_from_req:
                                result_store = ResearchResultStore(storage_path="data")
                                saved = result_store.load_result(task_id_from_req)  # ← 加载全量数据
                                if saved:
                                    saved_dps = saved.get("data_points")
                                    saved_srcs = saved.get("sources")
                                    if saved_dps is not None and len(saved_dps) > 0:
                                        task["aggregated_data_points"] = saved_dps  # ← 注入全量 125857 条
```

#### 5. GenericAgent 实时持久化：每次搜索迭代后全量写入

```python
# generic_agent.py:1487-1518
                # 实时持久化：每次搜索迭代后保存已收集数据到 ResearchResultStore
                try:
                    task_id = (self._context or {}).get("task_id", "")
                    if task_id and all_results.get("total_sources", 0) > 0:
                        from src.core.storage import ResearchResultStore, ResearchStatus
                        store = ResearchResultStore(storage_path="data")
                        saved_data_points = []
                        saved_sources = []
                        for search in all_results.get("searches", []):
                            for item in search.get("results", []):
                                saved_data_points.append({
                                    "title": item.get("title", ""),
                                    "content": item.get("body", "") or item.get("snippet", ""),
                                    "url": item.get("href", "") or item.get("url", ""),
                                })
                                saved_sources.append({
                                    "title": item.get("title", ""),
                                    "url": item.get("href", "") or item.get("url", ""),
                                })
                        store.save_result(
                            task_id=task_id,
                            result={
                                "topic": self._context.get("topic", ""),
                                "sections": [],
                                "data_points": saved_data_points,
                                "sources": saved_sources,
                            },
                            status=ResearchStatus.COLLECTING,
                        )
```

每个 agent 每次搜索迭代都调用 `store.save_result()` 全量覆盖写入。

#### 6. AgentSessionRegistry 全量序列化

```python
# agent_session.py:477-491
    def save(self, storage_path: Path) -> Path:
        data = self.to_dict()
        path = storage_path / "registries" / f"{self.parent_session_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
```

`to_dict()` 序列化所有 `child_sessions`，每个 `AgentSession` 包含 `result`（含 `data_points`），导致 registry 文件也膨胀到数百 MB。

### 数据膨胀的完整链路

```
章节执行 → 子agent搜索 → all_results.extend(batch_results) [L1310, QC前已追加]
  → GenericAgent 实时持久化 → ResearchResultStore.save_result (全量写入)
    → QC 不通过 → 重试 → _execute_agents_batch(all_results, ...) [L1415, 传入已累积的 all_results]
      → P1-1: load_result (加载全量 data_points) → 注入到 task["aggregated_data_points"]
        → 子agent收到膨胀数据 → LLM 处理超时或产出低质量
          → 新搜索结果追加 → save_result (全量写入更大的数据)
            → session.__setitem__ 触发 _save_to_disk (全量序列化 + 写入)
              → AgentSessionRegistry.save (全量序列化，含 result.data_points) → 文件膨胀
                → 循环加剧 → 内存爆炸 → 系统卡死
```

**注意：** `all_results.extend(batch_results)` (L1310) 在 QC 检查前执行，意味着即使 QC 重试成功替换了 `batch_results`，`all_results` 中仍保留原始失败结果。这是数据重复累积的重要来源之一。

---

## 修复方案建议

### 修复 1：问题 1 — LLM 调用失败 fallback 机制 ✅ 已修复

**文件：** `src/api/research_api.py:1010-1015, 458-465, 658-670`

1. ✅ 在 `_fallback_response` (L1010-1015) 中从 `session.research_context` 恢复 topic，而非仅依赖调用时传入的 `context` 快照。因为 `context` 在 LLM 调用前已获取 (L446)，如果 topic 是在当次 `_llm_converse` 中才确定的，`context` 快照中不会包含。修复为：
   ```python
   existing_topic = context.get('topic')
   if not existing_topic and session:
       existing_topic = session.get('research_context', {}).get('topic')
   ```
2. ✅ `_handle_chat_mode` (L458-465) 中对 `ValueError` 增加 1 次有限重试。非 `ValueError` 异常仍直接 fallback。
3. ✅ 重试时调用 `_llm_converse(..., temperature=0.3, _json_retry=True)`：
   - `temperature=0.3`：降低 LLM 创造力，输出更结构化
   - `_json_retry=True`：在初始 prompt 前插入 `## CRITICAL: ... You MUST respond with ONLY a valid JSON object ...` 严格指令
   - `_llm_converse` 新增 `temperature` 和 `_json_retry` 可选参数，向下兼容

### 修复 2：问题 2A — 框架确认循环 ✅ 已修复

**文件：** `src/api/research_api.py:1558-1573`

✅ 修改 `handle_interact` 中的 `suggestion_id` 覆盖逻辑：当 `user_message`（来自 `text`）非空时，不再被 `suggestion_id` 覆盖。

**修复原理：** 前端 `ChatPanel.tsx:402` 发送 `{suggestion_id: 'confirm_start', text: '确认开始研究，包含章节：...'}`，修复后 `text` 不再被覆盖为 `'confirm_start'`，LLM 收到自然语言能正确识别为确认意图。

**向后兼容：** 当 `text` 为空时，仍走 `suggestion_map` 映射或回退为 `suggestion_id`，不影响 `add_details`、`start_framework` 等已有 suggestion。

### 修复 3：问题 2B — _start_execution 返回值类型不匹配 ✅ 已修复

**文件：** `src/api/research_api.py:1197, 1217, 1641, 1677, 1686` + `web/src/hooks/useResearch.ts:375`

✅ 将所有研究启动路径的返回值改为：

1. `_start_execution` (L1197): `step: 6, mode: 'research', status: 'running'`
2. `_start_execution_with_routing` (L1217): `step: 6, mode: 'research', status: 'running'`
3. `_handle_research_flow` step=5 confirmed (L1641): `step: 6, mode: 'research', status: 'running'`
4. `quick_start` session data (L1677): `status: 'running'`
5. `quick_start` return (L1686): `step: 6, status: 'running'`
6. `useResearch.ts:375`: `data.status === 'running'`（原为 `'executing'`）

**修改内容：** 三字段修复 + 前端同步
1. `step: 'research'`（字符串）→ `6`（数字），匹配前端 `data.step === 6` 严格比较
2. `mode: 'executing'` → `'research'`，匹配前端 `mode === 'research'` 严格比较
3. `status: 'success'` / `'executing'` → `'running'`，语义正确：研究刚启动应返回 `'running'`
4. 前端 `useResearch.ts:375` 同步修改 `status === 'executing'` → `status === 'running'`

前端三处判断逻辑：
- `useResearch.ts:479` 和 `useResearch.ts:551`：只检查 `mode === 'research' && data.step === 6`（不检查 status）✅
- `useResearch.ts:375`：检查 `data.step === 6 && data.status === 'executing'` → 改为 `=== 'running'` ✅

### 修复 4：问题 3 — 数据重复存储 / 内存爆炸（部分已修复）

#### 4a：`aggregated_data_points` 去重 + 上限 ✅ 已修复

**文件：** `src/core/orchestrator/execution/engine.py:2080-2105`

在 P1-1 数据注入前，根据 `url` 去重，并设置上限 5000 条。去重逻辑：同 url 保留第一次出现的条目。

#### 4b：`PersistentSessionDict` 写入节流 ✅ 已修复

**文件：** `src/core/session_manager.py:31-59`

`SessionManager.__new__` 新增 `_last_write_time` 和 `_debounce_ms = 2000`。`_save_to_disk` 检查距上次写入是否超过 2 秒，不足则跳过。快速连续修改（如 agent 执行时的多次 `session["key"] = value`）合并为一次实际 I/O。

#### 4c：QC 重试前清理上一轮临时数据 ✅ 已修复

**变更 1**：移除 L1310 的 `all_results.extend(batch_results)` 和 L1311 的 `stage_results[...]=batch_results`
**变更 2**：在 QC 检查 + 基本质量检查之后（L1465）、C-FIX-1 之前重新插入两行
**效果**：QC 重试产生的干净数据取代而非追加到 `all_results`。QC 全部失败时 `break` 不会走到 extend。

#### 4d：ResearchResultStore 增量写入 ✅ 已修复

**文件：** `src/core/storage/research_result_store.py:248-305`

`save_result` 先 `load_result` 检查是否存在，若存在则合并 `data_points` 和 `sources`（url 去重），再写入。非直接覆盖。

#### 4e：AgentSessionRegistry 排除大数据 ✅ 已修复

**文件：** `src/core/agents/agent_session.py:106-139`

✅ `AgentSession.to_dict()` 中排除 `result.data_points` 和 `result.sources`（这些已由 ResearchResultStore 单独持久化），改为只保留 `data_points_count` 和 `sources_count`，避免 registry 文件膨胀。

```python
result_for_dict = self.result
if isinstance(result_for_dict, dict):
    result_for_dict = dict(result_for_dict)
    if "data_points" in result_for_dict:
        dp = result_for_dict.pop("data_points")
        result_for_dict["data_points_count"] = len(dp) if isinstance(dp, list) else 0
    if "sources" in result_for_dict:
        src = result_for_dict.pop("sources")
        result_for_dict["sources_count"] = len(src) if isinstance(src, list) else 0
```

---

## 修复验证

### 测试文件

| 文件 | 测试数 | 类型 | 说明 |
|------|--------|------|------|
| `tests/unit/test_bug1_llm_fallback_loses_topic.py` | 7 | 单元 | Bug 1: LLM fallback 丢失 topic |
| `tests/unit/test_bug2a_framework_confirm_loop.py` | 10 | 单元 | Bug 2A: suggestion_id 覆盖导致框架循环 |
| `tests/unit/test_bug2b_start_execution_type_mismatch.py` | 12 | 单元 | Bug 2B: step/mode 类型不匹配 |
| `tests/unit/test_bug3_data_duplication_memory.py` | 14 | 单元 | Bug 3: 数据重复/内存爆炸 |
| `tests/unit/test_bug3_remaining_fixes.py` | 19 | 单元(纯逻辑) | Bug 3 4a/4b/4c/4d 纯逻辑验证 |
| `tests/integration/test_bug3_fixes_integration.py` | 9 | 集成(TestClient) | P1-1+Store+QC+API 端到端 |

### 测试结果（最终）

- Bug 修复验证测试：**71 passed**（5 个单元文件，含 ValueError retry）
- 集成测试：**9 passed**（引擎路径 + FastAPI TestClient）
- 现有回归测试（storage/api helper/cancel resume）：**240 passed**
- 总计：**320 passed**，**零回归**
- 修复中发现的 6 项测试修复：
  1. `test_fallback_context_snapshot_loses_topic`：断言从 RED（期望旧行为）→ GREEN（修复后）
  2. `test_fallback_recovers_topic`：补缺失的 `_make_api` 方法
  3. 3 个 `TestFrameworkModifyFailureReturnsModify`：mock 路径修正
  4. `test_step5_confirmed_return_value`：添加缺失的 `async def`
  5. `test_start_execution_return_value`：patch 路径 `research_api.ProgressStreamer` → `core.progress_streamer.ProgressStreamer`
  6. `test_save_result_overwrites_not_appends`：断言从旧行为（覆盖=1条）改为新行为（合并=3条）

### 审查补充发现

1. **Bug 2B 扩展修复**：`status: 'executing'` 不仅存在于 `_start_execution` 两处返回，还存在于：
   - `research_api.py:1641`（`_handle_research_flow` step=5 confirmed 直接返回）
   - `research_api.py:1677`（`quick_start` session data）
   - `research_api.py:1686`（`quick_start` 返回值）
   - 全部已修复为 `status: 'running'`

2. **前端同步修复**：`useResearch.ts:375` 检查 `data.status === 'executing'` 已同步改为 `=== 'running'`，否则 `confirmResearch` 路径无法正确设置 taskId 和 status
