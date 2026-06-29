# 数据保障方案 v2.3 — 解决报告"数据为空"问题

## 根因分析

追踪 `research_efbdc8ef`（比亚迪财务分析）的完整链路，发现**四层问题叠加**：

### 层1: context 丢失（已修复）
- `to_decomposition_plan()` 不传递 aspect/topic/skills → agent 无法获取结构化数据
- **修复**：已在 `dynamic_orchestrator.py` 中补全 context/skills 传递

### 层2: cancelled agent 不保存部分输出（核心问题）
- 8 个 phase_1 agent 中 7 个 status=cancelled
- `agent_coordinator._execute_task()` 在 `CancelledError` 分支（`agent_coordinator.py:389-407`）中：
  - 设置 `active_task.status = "cancelled"` 但**不设置 `active_task.result`**
  - 调用 `_update_session_status(status=CANCELLED, result=None)` → `session.result = None`
- `wait_for_completion()` 返回 `active_task.result`（None）→ 返回 error dict
- engine 的 `_execute_batch()` 将 `success=False` 的结果加入 `batch_results` → 写入 `stage_results`
- **但 `success=False` 的结果只含 error 字符串，不含实际采集的数据**
- timeout 分支（`agent_coordinator.py:370-371`）已有 `partial_output` 先例，cancelled 分支未复用

### 层3: ID 匹配断裂（兜底问题）
- `section_details.id` = `营收构成分析`（由 `_build_section_details_from_tree` 生成，`orchestrator.py:3350`）
- `agent._section_id` = `section_0_营收构成分析`（由 `task_structure.py:461` 生成 `f"section_{i}_{sanitize_id(aspect)}"`）
- provenance 匹配只做精确相等（`==`），不包含后缀/子串匹配
- **注意**：`_normalize_key` 已剥离 `section_\d+_` 前缀并将 `、` → `_`，理论上归一化匹配应能命中
- 但 provenance 匹配在归一化匹配**之前**执行（358行 vs 377行），且 provenance 匹配未走归一化路径
- key 包含匹配（370行）用 `agent_id`（`phase_1_agent_0`）做 `section_id_lower in key_lower`，不包含 section_name → 失败

### 层4: `_determine_section_target` heuristic 对中文标题失效
- 当 `_section_id` 为空时，fallback 到 `_determine_section_target()`（`result_aggregator.py:1054-1093`）
- analysis 阶段基于英文 keyword 映射（"market_size"/"competition"等），对中文标题完全无效
- data_collection 阶段返回 `key` 本身（agent_id 如 `phase_1_agent_0`），与 section_id 无关
- 这是层3 provenance 匹配断裂的另一个根因：section_target 本身就是错的

## 方案设计

### 修复1（P0）: agent_coordinator cancelled 分支保存部分输出

**原则**：cancelled 的 agent 可能已经由 LLM 生成了部分输出，丢弃是浪费。timeout 分支已有 `partial_output` 先例。

**改动位置**：`agent_coordinator.py:389-407`，CancelledError 分支

当前：
```python
except asyncio.CancelledError:
    active_task.status = "cancelled"
    active_task.error = "Task cancelled"
    active_task.completed_at = datetime.now()
    
    self._update_session_status(
        agent=active_task.agent,
        status=AgentSessionStatus.CANCELLED,
        error="Task cancelled",
    )
```

改为：
```python
except asyncio.CancelledError:
    active_task.status = "cancelled"
    active_task.error = "Task cancelled"
    active_task.completed_at = datetime.now()
    
    # 保存部分输出（与 timeout 分支一致）
    partial = _extract_partial_output(active_task)
    if partial:
        active_task.result = partial
        logger.info(f"Task {task_id} cancelled with partial output ({len(str(partial))} chars)")
    
    self._update_session_status(
        agent=active_task.agent,
        status=AgentSessionStatus.CANCELLED,
        result=partial if partial else None,
        error="Task cancelled",
    )
```

**新增辅助函数**（文件顶部或 class 内）：

```python
def _extract_partial_output(active_task) -> Optional[Dict[str, Any]]:
    """从 cancelled/failed agent 中提取已有输出"""
    agent = active_task.agent
    
    # 1. 尝试从 agent context 提取
    ctx = getattr(agent, '_context', {}) or {}
    last_output = ctx.get("last_output", "")
    
    # 2. 尝试从 active_task.partial_output 提取（timeout 分支已设置）
    if not last_output:
        last_output = getattr(active_task, 'partial_output', '') or ''
    
    if not last_output:
        return None
    
    result = {
        "success": False,
        "content": str(last_output)[:50000],
        "agent_id": agent.agent_id,
        "_partial": True,
    }
    
    # 保留 section_id 信息
    section_id = getattr(agent, 'section_id', '') or ''
    if section_id:
        result["section_id"] = section_id
        result["_section_id"] = section_id
    
    # 保留已收集的 data_points/sources
    if ctx.get("data_points"):
        result["data_points"] = ctx["data_points"]
    if ctx.get("sources"):
        result["sources"] = ctx["sources"]
    
    return result
```

同样修改 timeout 分支（`agent_coordinator.py:370-387`），复用 `_extract_partial_output`。

### 修复2（P0）: orchestrator 处理 exec_result.status == "cancelled"

**改动位置**：`orchestrator.py:816-827`

当前只检查 `"failed"` 状态。如果 engine 返回 `status="cancelled"`，代码继续执行聚合，但 `stage_results` 可能为空。

```python
# 现有代码
if exec_result.status == "failed":
    error_detail = ...
    return ResearchResult(task_id=..., status="failed", ...)

# 新增：cancelled 也尝试恢复数据
if exec_result.status == "cancelled":
    # 不直接返回 failed，而是尝试从已收集的数据恢复
    if not exec_result.stage_results or not any(
        isinstance(v, list) and len(v) > 0
        for v in exec_result.stage_results.values()
    ):
        recovered = self._recover_results_from_sessions(task_id, session_registry)
        if recovered:
            exec_result.stage_results["recovered"] = recovered
            logger.info(f"[{task_id}] Recovered {len(recovered)} results from cancelled agents")
        else:
            return ResearchResult(
                task_id=task_id, status="cancelled",
                topic=requirement.topic,
                agents_used=[a.agent_id for a in agents] if agents else [],
                stages_completed=0,
                summary="Research cancelled, no partial data available",
                created_at=start_time, completed_at=datetime.now(),
            )
    # 继续聚合流程（不再 return）
```

### 修复3（P1）: provenance 匹配增强 + 归一化

**改动位置**：`result_aggregator.py` 第 358-364 行

当前 provenance 匹配只做精确相等，应在精确匹配失败后尝试归一化匹配：

```python
if key in self.content_provenance:
    provenance = self.content_provenance[key]
    # 精确匹配
    if provenance.section_target == section_id:
        content = extract_content(value)
        matched_key = key
        matched_stage = stage
        break
    # 归一化匹配（利用已有的 _normalize_key）
    norm_target = _normalize_key(provenance.section_target)
    norm_sid = _normalize_key(section_id)
    norm_sname = _normalize_key(section_name)
    if norm_target and (norm_target == norm_sid or norm_target == norm_sname
                        or norm_sid in norm_target or norm_sname in norm_target
                        or norm_target in norm_sid or norm_target in norm_sname):
        content = extract_content(value)
        matched_key = key
        matched_stage = stage
        logger.info(f"Provenance 归一化匹配: '{section_name}' -> provenance.target='{provenance.section_target}' norm='{norm_target}'")
        break
```

这解决了 `section_0_营收构成分析` vs `营收构成分析` 的问题，因为 `_normalize_key` 已能剥离 `section_\d+_` 前缀。

### 修复4（P2）: 聚合器语义匹配兜底

**改动位置**：`result_aggregator.py` 第 446-453 行，在 `if not content:` 生成占位符之前

**新增函数**（文件顶部，class 外部）：

```python
_ZH_STOPWORDS = frozenset({"分析", "与", "的", "及", "和", "在", "了", "是", "对", "等", "中", "为", "以", "到", "从", "上", "下", "内", "外", "及", "其", "或"})

def _tokenize_zh(text: str) -> Set[str]:
    """中文 2-gram + 英文空格分词，去除停用词"""
    if not text:
        return set()
    tokens = set()
    buf = []
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff':
            buf.append(ch)
        else:
            if len(buf) >= 2:
                for i in range(len(buf) - 1):
                    gram = buf[i] + buf[i+1]
                    if gram not in _ZH_STOPWORDS:
                        tokens.add(gram)
            elif buf:
                w = ''.join(buf)
                if w not in _ZH_STOPWORDS:
                    tokens.add(w)
            buf = []
            if ch.isalpha():
                tokens.add(ch.lower())
    if len(buf) >= 2:
        for i in range(len(buf) - 1):
            gram = buf[i] + buf[i+1]
            if gram not in _ZH_STOPWORDS:
                tokens.add(gram)
    return tokens

def _compute_jaccard(tokens_a: Set[str], tokens_b: Set[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    inter = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(inter) / len(union)

def _compute_edit_similarity(s1: str, s2: str) -> float:
    from src.core.orchestrator.aggregation.result_aggregator import _edit_distance
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    dist = _edit_distance(s1, s2)
    max_len = max(len(s1), len(s2))
    return 1.0 - dist / max_len

def _title_fuzzy_score(section_name: str, agent_aspect: str) -> float:
    """0.6 * jaccard + 0.4 * edit_similarity"""
    tokens_name = _tokenize_zh(section_name)
    tokens_aspect = _tokenize_zh(agent_aspect)
    jaccard = _compute_jaccard(tokens_name, tokens_aspect)
    edit_sim = _compute_edit_similarity(section_name, agent_aspect)
    return 0.6 * jaccard + 0.4 * edit_sim

def _semantic_match_section(
    section_name: str,
    section_id: str,
    unused_agents: Dict[str, Tuple[str, str]],
) -> Optional[Tuple[str, str, float]]:
    """
    语义匹配：标题模糊 → 全局回退（带最低相关性）
    返回 (matched_key, matched_content, score) 或 None
    """
    best_key = None
    best_content = None
    best_score = 0.0
    
    # 阶段1: 标题模糊匹配
    for key, (content, aspect_or_sid) in unused_agents.items():
        # 先归一化 aspect
        norm_aspect = _normalize_key(aspect_or_sid) if aspect_or_sid else ""
        norm_name = _normalize_key(section_name)
        norm_sid = _normalize_key(section_id)
        
        # 尝试归一化匹配
        if norm_aspect and (norm_aspect == norm_name or norm_aspect == norm_sid
                           or norm_name in norm_aspect or norm_aspect in norm_name
                           or norm_sid in norm_aspect or norm_aspect in norm_sid):
            return (key, content if isinstance(content, str) else str(content), 0.9)
        
        # 语义分数
        score = _title_fuzzy_score(section_name, aspect_or_sid or key)
        if score > best_score:
            best_score = score
            best_key = key
            best_content = content
    
    if best_score >= 0.3:
        return (best_key, best_content if isinstance(best_content, str) else str(best_content), best_score)
    
    # 阶段2: 全局回退 — 内容关键词覆盖
    section_tokens = _tokenize_zh(section_name)
    if section_tokens:
        for key, (content, _) in unused_agents.items():
            content_str = (content if isinstance(content, str) else str(content))[:500]
            content_tokens = _tokenize_zh(content_str)
            jaccard = _compute_jaccard(section_tokens, content_tokens)
            if jaccard > best_score and jaccard >= 0.2:
                best_score = jaccard
                best_key = key
                best_content = content
    
    if best_score >= 0.2:
        return (best_key, best_content if isinstance(best_content, str) else str(best_content), best_score)
    
    return None
```

**调用代码**：

```python
if not content:
    unused = {}
    for _stage_name, _sd in self.layered_content.items():
        if not isinstance(_sd, dict):
            continue
        for _k, _v in _sd.items():
            if _k in used_keys:
                continue
            if _k.endswith("__meta"):
                continue
            _aspect = ""
            if _k in self.content_provenance:
                _aspect = self.content_provenance[_k].section_target or ""
            unused[_k] = (_v if isinstance(_v, str) else str(_v), _aspect)
    
    semantic_result = _semantic_match_section(section_name, section_id, unused_agents=unused)
    if semantic_result:
        matched_key, content, score = semantic_result
        matched_stage = "semantic_fallback"
        logger.info(f"语义匹配: '{section_name}' -> '{matched_key}' (score={score:.3f})")

if not content:
    logger.error(...)
    content = 占位符
```

### 修复5（P2）: orchestrator 从 session 恢复（仅用于 cancelled 后无 stage_results 的场景）

**改动位置**：`orchestrator.py`，修复2中已包含调用点

**新增方法**：

```python
def _recover_results_from_sessions(self, task_id, session_registry):
    """从 AgentSession registry 中恢复 cancelled/failed agent 的结果数据"""
    from src.core.agents.agent_session import AgentSessionStatus
    if not session_registry or not hasattr(session_registry, 'child_sessions'):
        return []
    results = []
    for sid, session in (session_registry.child_sessions or {}).items():
        if not hasattr(session, 'status') or not hasattr(session, 'result'):
            continue
        if session.status not in (AgentSessionStatus.CANCELLED, AgentSessionStatus.FAILED):
            continue
        # 修复1 后 session.result 可能不为 None（partial output）
        if not session.result:
            continue
        result = dict(session.result) if isinstance(session.result, dict) else {"content": str(session.result)}
        result["agent_id"] = session.agent_id
        result["_recovered"] = True
        ctx = session.context or {}
        if "section_id" in ctx:
            result["_section_id"] = ctx["section_id"]
        results.append(result)
    return results
```

## 改动文件清单

| 文件 | 改动 | 优先级 | 说明 |
|------|------|--------|------|
| `agent_coordinator.py` | 新增 `_extract_partial_output` + cancelled/timeout 分支调用 | P0 | 数据保存根因修复 |
| `orchestrator.py` | 新增 cancelled 处理 + `_recover_results_from_sessions` | P0 | 防止 cancelled 任务空聚合 |
| `result_aggregator.py` | provenance 归一化匹配 + 语义匹配函数 + 调用点 | P1/P2 | 匹配兜底 |

## 预期效果

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| agent cancelled 但有部分输出 | output 丢失 → success=False 无内容 | partial output 保存 → 有内容可用 |
| exec_result.status == "cancelled" | 继续空聚合 → 全空 | 恢复 session 数据 → 部分可用 |
| provenance section_target 含前缀 | 精确匹配失败 | 归一化匹配 → 命中 |
| agent_id 与 section_name 无关 | 包含匹配失败 | 语义匹配 → 命中 |
| `_determine_section_target` 返回 agent_id | provenance 记录错误 | 归一化兜底 + 语义匹配覆盖 |

## 风险

| 风险 | 缓解 |
|------|------|
| cancelled 结果数据不完整 | 标记 `_partial=True`/`_recovered=True`，内容可能较短但优于占位符 |
| 语义匹配错配 | score 阈值过滤 + 仅在精确+归一化匹配全失败后触发 + warning 日志 |
| provenance 归一化匹配误命中 | 利用已验证的 `_normalize_key`（有现有测试覆盖），双向子串检查 |
| 全局回退分配弱相关内容 | Jaccard >= 0.2 门槛（v2.1 的 0.1 太低），完全无关不分配 |
| `_extract_partial_output` 提取到空内容 | 返回 None → 不覆盖 active_task.result → 原有行为不变 |

## v2.3 深度审计发现与修复

### 审计发现6: semantic match 用 str() 替代 extract_content()（High）

`_semantic_match_section` 内部将 dict 值用 `str()` 转换后返回，导致 dict 的 Python repr 出现在最终报告中。

**修复**：`_semantic_match_section` 返回 raw value（不转换），由调用方用 `extract_content()` 处理非字符串值。调用方代码改为：
```python
_sem_content = extract_content(_sem_raw) if not isinstance(_sem_raw, str) else _sem_raw
```

### 审计发现7: `_research_with_routing` 缺少 cancelled 处理（High）

`orchestrator.py` 中只有 `research()` 方法添加了 cancelled 处理，`_research_with_routing()` 缺失。cancelled 执行在此路径会被忽略，产生空"completed"报告。

**修复**：在 `_research_with_routing()` 的 `exec_result.status == "failed"` 检查之后，添加相同的 cancelled 处理逻辑。

### 审计发现8: result_status 忽略 cancelled 状态（Medium）

两个研究方法中 `result_status` 仅基于 quality_passed 决定，忽略了 `exec_result.status == "cancelled"`。用户看到 "completed" 而非 "completed_with_warnings"。

**修复**：在 `result_status` 赋值时优先检查 cancelled 状态：
```python
if exec_result.status == "cancelled":
    result_status = "completed_with_warnings"
elif quality_passed:
    result_status = "completed"
else:
    result_status = "completed_with_warnings"
```

### 审计发现9: replan/reanalyze 无 stage_results None guard（High）

`replan()` 和 `reanalyze()` 直接调用 `exec_result.stage_results.items()` 而不检查 None。如果执行失败/取消且 stage_results 为 None，将抛出 AttributeError。

**修复**：在遍历前添加 `if exec_result.stage_results:` 检查。

### 审计发现10: _tokenize_zh 英文按字符分词（Medium）

英文文本被逐字符加入 tokens，"Market" → {"m","a","r","k","e","t"} 而非 {"market"}，导致语义匹配对英文标题不可靠。

**修复**：重构 `_tokenize_zh`，增加 `eng_buf` 缓冲区，累积连续英文/数字字符为完整单词后再添加到 tokens。

### 审计发现11: `_semantic_match_section` 缺少防御性检查（Low）

- 无 `unused_agents` 空值检查（传 None 会 crash）
- 无 `__meta` key 内部过滤（依赖调用方）

**修复**：添加 `if not unused_agents: return None` 开头检查 + 循环内 `if key.endswith("__meta"): continue`。

### 审计发现12: `_recover_results_from_sessions` 不设置 _section_id

恢复逻辑只设置 `result["section_id"]` 但不设置 `result["_section_id"]`，导致下游 provenance 匹配失败。

**修复**：在设置 `section_id` 时同时设置 `_section_id`。

## v2.3 改动文件清单

| 文件 | v2.2 改动 | v2.3 新增改动 |
|------|-----------|--------------|
| `agent_coordinator.py` | 新增 `_extract_partial_output` + cancelled/timeout 分支调用 | — |
| `orchestrator.py` | 新增 cancelled 处理 + `_recover_results_from_sessions` 调用 | `_research_with_routing` 添加 cancelled 处理；result_status 优先检查 cancelled；replan/reanalyze 添加 stage_results None guard；`_recover_results_from_sessions` 同时设置 `_section_id` |
| `result_aggregator.py` | provenance 归一化匹配 + 语义匹配函数 + 调用点 | 语义匹配返回 raw value + 调用方用 extract_content；`_tokenize_zh` 英文单词分词；`_semantic_match_section` 添加空值/`__meta` 防御 |
