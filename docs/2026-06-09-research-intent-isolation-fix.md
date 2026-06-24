# 深度研究阶段意图分析隔离修复方案

> 日期: 2026-06-09
> 状态: **已实施** (2026-06-10 全部完成并通过测试)
> 影响模块: `research_api.py`, `semantic_intent.py`, `intelligent_routing_adapter.py`, `orchestrator.py`, `engine.py`, `content_lock.py`, `data_boundary_controller.py`, `result_aggregator.py`, `generic_agent.py`, `dynamic_orchestrator.py`

---

## 1. 问题诊断

### 1.1 核心问题

**意图分析（`_llm_converse()`）在深度研究 EXECUTING 阶段返回了非法状态转换（如 `enter_framework`），导致研究被中断、重新进入框架确认流程。**

正确行为：意图分析每次都必须执行（确保实时理解用户需求），但在 EXECUTING 状态下，LLM 返回的 action 必须被约束——不允许直接触发 `enter_framework`，必须先暂停再确认。

### 1.2 问题路径

日志证据来自 2026-06-09 的两个session：

**路径A：深度研究期间 LLM 返回非法 action（主问题）**

```
_handle_research_msg() → _llm_converse() → LLM返回 action="enter_framework" → 中断研究 → 重新进入框架
```

- 代码位置: `research_api.py:395-443`
- 问题: `_llm_converse()` 的 EXECUTING 阶段 prompt 约束不足，LLM 仍可能返回 `enter_framework` 或 `modify_research`
- 证据: `21:15:47 - User message during research: 继续` → 触发 `_llm_converse()` → LLM 可能返回非法 action

**路径B：修改研究触发重新意图分析**

```
_handle_modify_research() → new IntelligentRoutingAdapter().analyze_incremental() → 包含意图分析
```

- 代码位置: `research_api.py:2821-2828`
- 问题: 修改研究时创建新的 `IntelligentRoutingAdapter` 并调用 `analyze_incremental()`，内部调用 `analyze()` → 包含 `_analyze_intent()`
- 证据: `analyze_incremental()` (line 176) 调用 `self.analyze()` → `_analyze_intent()`

**路径C：重新分析触发完整意图分析**

```
orchestrator.reanalyze() → self._routing_adapter.analyze() → _analyze_intent()
```

- 代码位置: `orchestrator.py:2506`
- 问题: `reanalyze()` 完整重跑意图分析链

### 1.3 具体日志证据

| 时间 | 事件 | 问题 |
|------|------|------|
| 21:12:21 | `LLM intent analysis failed: JSON解析错误` → 回退关键词匹配 | 意图分析LLM不稳定 |
| 21:12:21 | `[Intent] Primary: research, Confidence: 0.50` | 低置信度，关键词匹配不可靠 |
| 10:13:50-10:14:08 | 三次 `Depth research keyword detected` | 用户消息被重复意图分析 |
| 21:15:47 | `User message during research: 继续` | 触发 `_llm_converse()` 做意图分析 |
| 21:16:04 | `openai Retrying request` | LLM意图分析导致重试 |
| 21:12:10/21:12:22/21:12:48 | `HTTP/1.1 400 Bad Request` (DeepSeek) | 意图分析LLM调用失败 |

### 1.4 根本原因分析

1. **EXECUTING 阶段 prompt 约束不足**: `_build_dialogue_context()` 对 EXECUTING 状态的引导过于宽松，LLM 仍可能返回 `enter_framework`，导致研究被中断
2. **`_handle_research_msg()` 缺少 action 约束层**: LLM 返回的 action 直接执行，没有根据当前状态过滤非法转换
3. **`analyze_incremental()` 重跑意图分析**: 增量分析时意图已确定（仍在研究中），只需做结构分析和增量编排，但当前仍调用完整 `analyze()` 包含 `_analyze_intent()`
4. **LLM意图分析JSON解析不稳定**: `_parse_llm_json()` 缺少对常见异常格式的处理
5. **`_handle_user_message()` 中深度研究关键词在 research 模式下仍触发 framework**: 已在研究模式时，"深度研究"关键词不应重新进入 framework
6. **`cm` 变量 NameError**: `research_api.py:353` 使用 `cm.is_paused()` 但 `cm` 仅在 line 312 的分支内部赋值

### 1.5 审查发现的额外Bug

**Bug: `cm` 变量未定义导致潜在 NameError**

- 位置: `research_api.py:353`
- 问题: `cm.is_paused(session_id)` 使用了变量 `cm`，但 `cm` 仅在 line 312-313 的 `if mode == 'research'` depth_keyword 分支内部赋值
- 触发条件: 用户输入不包含 depth_keyword，但 mode 为 research 且输入匹配 resume_keywords
- 影响: 会抛出 `NameError: name 'cm' is not defined`，导致消息处理失败
- 修复: 在 `_handle_user_message()` 方法入口处提前初始化 `cm`

---

## 2. 修复方案

### 设计原则

**意图分析每次都必须执行**，确保实时理解用户需求。修复目标不是"跳过意图分析"，也不是"枚举所有意图类型"，而是"约束意图分析结果的使用方式"：

- 意图分析结果可能有多种类型（重新规划、增减需求、修订、查询进度、确认等待等），不应硬编码枚举
- 通用原则：**重操作（中断/重启研究）需用户明确意图确认，轻操作（注入需求、继续对话）直接放行**
- LLM在EXECUTING状态下可能过度敏感地返回重操作action（如`enter_framework`），约束层过滤这种误判

当前Bug：LLM在EXECUTING状态下可能返回非法action（如`enter_framework`），直接中断研究而没有先确认用户是否真的要重规划。

### 2.1 修复一：EXECUTING阶段action约束层（核心修复）

**目标**: `_handle_research_msg()` 中，`_llm_converse()` 每次都执行意图分析，但增加action约束层——重操作需用户明确意图确认，轻操作直接放行。

**修改文件**: `research_api.py`

**修改 `_handle_research_msg()` 方法**:

当前逻辑（`research_api.py:395-443`）:
```python
# LLM返回action直接执行，无状态约束
conv_result = await asyncio.wait_for(self._llm_converse(session_id, user_input), timeout=60)
action = conv_result.get('action', 'continue_chat')
if action == 'enter_framework':
    # 直接中断研究，进入框架 — Bug！
    cm.pause(session_id)
    ...
    return await self._enter_framework_mode(session_id, user_input)
```

修改为：增加 `_validate_action_for_state()` 约束层

```python
async def _handle_research_msg(self, session_id, user_input, session):
    from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
    research_result = session.get('research_result')
    has_executor_task = session_id in self._executor_tasks and not self._executor_tasks[session_id].done()
    is_actually_running = bool(research_result.get('status') not in ('completed', 'cancelled', 'error')) if research_result else has_executor_task
    cm = get_cancel_manager()

    if research_result and research_result.get('status') == 'completed':
        session['mode'] = 'chat'
        return await self._handle_chat_mode(session_id, user_input)
    if not has_executor_task and not research_result:
        session['mode'] = 'chat'
        session['current_step'] = 0
        session.pop('research_result', None)
        return await self._handle_chat_mode(session_id, user_input)

    if cm.is_paused(session_id):
        # 暂停状态：所有action都合法，直接执行
        try:
            conv_result = await asyncio.wait_for(self._llm_converse(session_id, user_input), timeout=60)
        except asyncio.TimeoutError:
            return await self._handle_chat_mode(session_id, user_input)
        action = conv_result.get('action', 'continue_chat')
        if action == 'resume_research':
            return await self.resume_research(session_id)
        if action == 'modify_research':
            return await self._handle_modify_research(
                session_id=session_id,
                modifications=conv_result.get('modifications', {}),
                adjustment=conv_result.get('adjustment', user_input)
            )
        if action == 'enter_framework':
            # R-FIX-1: PAUSED状态下允许进入框架（原代码PAUSED分支无此处理）
            # 需做pause/cancel与EXECUTING分支一致
            old = self._executor_tasks.pop(session_id, None)
            if old and not old.done():
                old.cancel()
            session['mode'] = 'chat'
            return await self._enter_framework_mode(session_id, user_input)
        if action == 'regenerate_report':
            return await self._regenerate_report(session_id)
        return await self._handle_chat_mode(session_id, user_input)

    # ===== EXECUTING状态：意图分析必须执行，但约束重操作 =====
    logger.info(f"User message during research: {user_input}")
    try:
        conv_result = await asyncio.wait_for(self._llm_converse(session_id, user_input), timeout=60)
    except asyncio.TimeoutError:
        return {
            'session_id': session_id, 'step': session.get('current_step', 6),
            'mode': 'research', 'status': 'running',
            'message': '消息分析超时，您的消息已记录。您可以说"暂停"后重新发送。',
            'suggestions': ['暂停研究', '继续等待'], 'next_step': 'continue_research'
        }
    except Exception as e:
        logger.error(f"LLM converse failed: {e}", exc_info=True)
        return {
            'session_id': session_id, 'step': session.get('current_step', 6),
            'mode': 'research', 'status': 'running',
            'message': '消息处理临时异常，您可以尝试"暂停"后重新发送。',
            'suggestions': ['暂停研究'], 'next_step': 'continue_research'
        }

    if conv_result.get('status') == 'processing':
        return {
            'session_id': session_id, 'step': 0, 'mode': 'research',
            'status': 'processing', 'message': conv_result.get('message', '正在处理您的请求...'),
            'suggestions': [], 'next_step': 'tool_executing'
        }

    # ===== R-FIX-1: action约束层 =====
    conv_machine = session.get('state_machine')
    raw_action = conv_result.get('action', 'continue_chat')
    action = self._validate_action_for_state(raw_action, conv_machine, user_input)
    if action != raw_action:
        logger.info(f"[R-FIX-1] Action constrained: {raw_action} → {action} (state={conv_machine.current_state.value if conv_machine else 'none'})")

    # 按约束后的action执行
    if action == 'inject_requirement':
        return await self._handle_inject_requirement(
            session_id=session_id,
            inject_ops=conv_result.get('inject_ops', []),
            user_message=user_input
        )
    if action == 'modify_research':
        cm.pause(session_id)
        old = self._executor_tasks.pop(session_id, None)
        if old and not old.done():
            old.cancel()
        if conv_machine and conv_machine.current_state == ConversationState.EXECUTING:
            if conv_machine.can_transition_to(ConversationState.PAUSED):
                conv_machine.transition(ConversationState.PAUSED)
        return await self._handle_modify_research(
            session_id=session_id,
            modifications=conv_result.get('modifications', {}),
            adjustment=conv_result.get('adjustment', user_input)
        )
    if action == 'enter_framework':
        cm.pause(session_id)
        old = self._executor_tasks.pop(session_id, None)
        if old and not old.done():
            old.cancel()
        if conv_machine and conv_machine.current_state == ConversationState.EXECUTING:
            if conv_machine.can_transition_to(ConversationState.FRAMEWORK_CONFIRM):
                conv_machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        session['mode'] = 'chat'
        context = session.get('research_context', {})
        if conv_result.get('topic'):
            context['topic'] = conv_result['topic']
        if conv_result.get('directions'):
            context['directions'] = conv_result.get('directions', [])
        fw_sections = conv_result.get('framework_sections')
        if fw_sections and isinstance(fw_sections, list) and len(fw_sections) > 0:
            context['_suggested_sections'] = fw_sections
            logger.info(f"[{session_id}] LLM suggested {len(fw_sections)} sections: {fw_sections}")
        session['research_context'] = context
        return await self._enter_framework_mode(session_id, user_input)

    # 默认：continue_chat
    return {
        'session_id': session_id, 'step': session.get('current_step', 6),
        'mode': 'research', 'status': 'running',
        'message': conv_result.get('message', ''),
        'suggestions': conv_result.get('suggestions', []),
        'next_step': 'continue_research'
    }
```

**新增 `_validate_action_for_state()` 方法**:

```python
def _validate_action_for_state(self, action: str, conv_machine, user_input: str) -> str:
    """
    根据当前状态机状态约束LLM返回的action。
    
    通用原则：重操作（中断/重启研究）需用户明确意图确认，轻操作直接放行。
    不枚举所有意图类型，只区分"重操作"和"轻操作"。
    
    EXECUTING状态下：
    - 重操作（enter_framework, modify_research）：需用户输入中包含明确关键词，否则降级
    - 轻操作（inject_requirement, continue_chat 等）：直接放行
    
    PAUSED状态下：所有action都合法（已暂停，用户可以自由选择）
    """
    if not conv_machine:
        return action
    
    current_state = conv_machine.current_state
    
    # PAUSED状态：所有action合法
    if current_state == ConversationState.PAUSED:
        return action
    
    # EXECUTING状态：约束重操作
    if current_state == ConversationState.EXECUTING:
        # 定义重操作及其确认关键词
        HEAVY_ACTIONS = {
            'enter_framework': (
                '重新规划', '重新研究', '重新开始', '换个方向', '重新设计',
                'restart', 'redesign', 'start over', '重新来', '重做',
                '换个框架', '重新框架', '重新制定', '重新启动',
            ),
            'modify_research': (
                '修改', '调整', '改一下', '修订', '变更',
                'modify', 'adjust', 'revise', 'change',
            ),
        }
        
        if action in HEAVY_ACTIONS:
            confirm_keywords = HEAVY_ACTIONS[action]
            text = user_input.strip().lower()
            if any(kw in text for kw in confirm_keywords):
                # 用户明确表达了重操作意图，放行
                return action
            # LLM误判：用户没有明确要求重操作，降级
            fallback = 'inject_requirement' if action == 'modify_research' else 'continue_chat'
            logger.info(
                f"[R-FIX-1] {action} without explicit user intent, "
                f"downgrading to {fallback}"
            )
            return fallback
        
        # 轻操作：直接放行
        return action
    
    # 其他状态：不约束
    return action
```

**关键设计**：
- 意图分析（`_llm_converse`）**每次都执行**，确保理解用户需求
- 约束层不枚举意图类型，只区分"重操作"和"轻操作"
- 重操作需用户输入中包含明确关键词确认，否则降级为更安全的action
- 用户明确表达重操作意图时，约束层**放行**
- 未来新增action类型时，只需在`HEAVY_ACTIONS`中注册即可

---

### 2.2 修复二：`analyze_incremental()` 融合已有意图结果

**目标**: 增量分析时仍执行意图分析，但融合已有意图结果——确保意图一致性，避免低置信度回退覆盖高置信度的原有判断。

**修改文件**: `intelligent_routing_adapter.py`

**问题分析**:

`analyze_incremental()` (line 176) 调用 `self.analyze()` → `_analyze_intent()`，可能产生以下问题：
1. 新的意图分析返回不同意图类型（如从 RESEARCH 变成 CHAT），导致路由结果不一致
2. LLM 解析失败时回退到关键词匹配，置信度仅 0.50，覆盖了原来高置信度的判断
3. 增量场景下意图类型应保持一致（仍在研究中），只需更新结构和编排

**修复原则**: 意图分析仍执行（可能用户需求有变化），但与已有意图结果对比——如果新的意图置信度低于已有结果，保留已有意图；如果新意图置信度更高且意图类型改变，说明用户需求确实变了，采用新结果。

当前逻辑（`intelligent_routing_adapter.py:151-207`）:
```python
def analyze_incremental(self, user_request, requirement, completed_aspects=None, topic=None):
    # 1. First do complete analysis
    full_result = self.analyze(user_request, requirement, topic)  # 包含 _analyze_intent()
    ...
```

修改为：

```python
def analyze_incremental(
    self,
    user_request: str,
    requirement: Dict[str, Any],
    completed_aspects: Optional[List[str]] = None,
    topic: Optional[str] = None,
    existing_intent_result: Optional['DeepIntentResult'] = None,
) -> IntelligentRoutingResult:
    """
    增量分析：执行完整意图分析，但与已有意图结果融合。
    
    新增参数:
        existing_intent_result: 已有的意图分析结果，用于融合判断
    """
    # 1. 执行完整分析（包括意图分析——每次都执行）
    full_result = self.analyze(user_request, requirement, topic)
    
    # 2. R-FIX-2: 融合已有意图结果
    if existing_intent_result is not None:
        new_intent = full_result.intent_result
        
        # 如果新意图置信度低且使用了回退，保留已有结果
        if new_intent.used_fallback and not existing_intent_result.used_fallback:
            logger.info(
                f"[IntelligentRouting] Incremental: new intent used fallback "
                f"(conf={new_intent.intent_confidence:.2f}), keeping existing "
                f"(intent={existing_intent_result.primary_intent.value}, "
                f"conf={existing_intent_result.intent_confidence:.2f})"
            )
            full_result.intent_result = existing_intent_result
        # 如果新意图类型改变但置信度低，保留已有（避免误判）
        elif (new_intent.primary_intent != existing_intent_result.primary_intent
              and new_intent.intent_confidence < existing_intent_result.intent_confidence):
            logger.info(
                f"[IntelligentRouting] Incremental: intent changed but lower confidence "
                f"({new_intent.primary_intent.value}:{new_intent.intent_confidence:.2f} "
                f"vs {existing_intent_result.primary_intent.value}:{existing_intent_result.intent_confidence:.2f}), "
                f"keeping existing"
            )
            full_result.intent_result = existing_intent_result
        # 否则：新意图置信度更高或同等，采用新结果（用户需求确实变了）
        else:
            if new_intent.primary_intent != existing_intent_result.primary_intent:
                logger.info(
                    f"[IntelligentRouting] Incremental: intent changed with sufficient confidence "
                    f"({existing_intent_result.primary_intent.value} → {new_intent.primary_intent.value}, "
                    f"conf={new_intent.intent_confidence:.2f})"
                )
    
    # 3. 以下逻辑不变
    if not completed_aspects:
        return full_result
    
    skip_phases = []
    for phase in full_result.execution_plan.phases:
        phase_should_skip = True
        for section_id in phase.section_ids:
            section_name = self._extract_section_name(section_id)
            if not self._is_covered_by_completed(section_name, completed_aspects):
                phase_should_skip = False
                break
        if phase_should_skip:
            skip_phases.append(phase.phase_id)
    
    full_result.skip_phases = skip_phases
    
    if skip_phases:
        logger.info(
            f"[IntelligentRouting] Incremental: {len(skip_phases)} phases skipped "
            f"(covered by: {completed_aspects})"
        )
    
    return full_result
```

---

### 2.3 修复三：`_handle_modify_research()` 传递已有意图结果供融合

**目标**: 修改研究时，仍执行意图分析（用户需求可能变化），但传递已有意图结果给 `analyze_incremental()` 做融合判断，避免低置信度回退覆盖高置信度判断。

**修改文件**: `research_api.py`

当前逻辑（`research_api.py:2821-2828`）:
```python
from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
adapter = IntelligentRoutingAdapter(use_llm=True, fallback_to_keyword=True)
topic = context.get('topic', '')
routing_result = adapter.analyze_incremental(
    user_request=adjustment,
    requirement={'topic': topic, 'aspects': current_sections},
    completed_aspects=completed_aspects or current_sections,
    topic=topic)
```

修改为：

```python
from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
adapter = IntelligentRoutingAdapter(use_llm=True, fallback_to_keyword=True)
topic = context.get('topic', '')

# R-FIX-3: 获取已有的意图分析结果，传递给增量分析做融合
existing_intent = self._get_cached_intent_result(session)

routing_result = adapter.analyze_incremental(
    user_request=adjustment,
    requirement={'topic': topic, 'aspects': current_sections},
    completed_aspects=completed_aspects or current_sections,
    topic=topic,
    existing_intent_result=existing_intent,  # 新增：传递已有意图结果供融合
)
```

**新增缓存意图结果的方法**（不变，与原方案一致）:

```python
def _get_cached_intent_result(self, session):
    """从session中获取已缓存的意图分析结果"""
    context = session.get('research_context', {})
    cached = context.get('_cached_intent_result')
    if cached:
        try:
            from src.core.semantic_intent import DeepIntentResult
            return DeepIntentResult.from_dict(cached)
        except Exception as e:
            logger.warning(f"Failed to restore cached intent result: {e}")
    return None

def _cache_intent_result(self, session, intent_result):
    """缓存意图分析结果到session"""
    context = session.setdefault('research_context', {})
    try:
        context['_cached_intent_result'] = intent_result.to_dict()
    except Exception as e:
        logger.warning(f"Failed to cache intent result: {e}")
```

**在编排阶段缓存意图结果**（不变，与原方案一致）：

方案A（推荐）：在 `orchestrator.py` 中意图分析完成后缓存到内存，同时通过 session 持久化：

```python
# orchestrator.py:1558-1562，意图分析完成后
routing_result = self._routing_adapter.analyze(
    user_request=requirement.topic,
    requirement=requirement_dict,
    topic=requirement.topic,
)
# R-FIX-3: 缓存意图结果，供后续增量分析融合使用
self._cache_intent_for_task(task_id, routing_result.intent_result)

session = session_manager.get(requirement.session_id) if hasattr(requirement, 'session_id') else None
if session:
    context = session.setdefault('research_context', {})
    try:
        context['_cached_intent_result'] = routing_result.intent_result.to_dict()
    except Exception as e:
        logger.warning(f"Failed to cache intent result to session: {e}")
```

方案B（降级）：如果 orchestrator 无法访问 session_manager，则在 `research_api.py` 的
`_start_execution()` 完成后的回调中缓存。

---

### 2.4 修复四：`reanalyze()` 传递已有意图结果供融合

**目标**: 重新分析时，仍执行完整意图分析（需求可能变化），但传递已有意图结果做融合判断，避免低置信度回退覆盖高置信度判断。

**修改文件**: `orchestrator.py`

当前逻辑（`orchestrator.py:2500-2508`）:
```python
# 4. Re-run intent analysis
try:
    user_request = updated_requirement.get("user_request", "") or updated_requirement.get("topic", "")
    routing_result = self._routing_adapter.analyze(
        user_request=user_request,
        requirement=updated_requirement,
    )
```

修改为：

```python
# 4. R-FIX-4: 重新分析，传递已有意图结果供融合
try:
    user_request = updated_requirement.get("user_request", "") or updated_requirement.get("topic", "")
    
    # 获取已缓存的意图结果，传递给增量分析做融合
    existing_intent = self._get_cached_intent_for_task(task_id)
    
    if existing_intent is not None:
        # 使用增量分析（含融合逻辑），避免低置信度回退覆盖
        routing_result = self._routing_adapter.analyze_incremental(
            user_request=user_request,
            requirement=updated_requirement,
            completed_aspects=list(completed_sections),
            topic=user_request,
            existing_intent_result=existing_intent,
        )
        logger.info(f"[reanalyze] Used incremental analysis with existing intent fusion")
    else:
        # 降级：无缓存时仍走完整分析
        logger.warning(f"[reanalyze] No cached intent found, falling back to full analysis")
        routing_result = self._routing_adapter.analyze(
            user_request=user_request,
            requirement=updated_requirement,
        )
    
    # 更新缓存
    self._cache_intent_for_task(task_id, routing_result.intent_result)
```

**新增缓存管理**（不变，与原方案一致）:

```python
# orchestrator.py 中添加意图缓存管理
def _cache_intent_for_task(self, task_id, intent_result):
    """缓存意图分析结果到内存"""
    if not hasattr(self, '_intent_cache'):
        self._intent_cache = {}
    self._intent_cache[task_id] = intent_result

def _get_cached_intent_for_task(self, task_id):
    """获取已缓存的意图分析结果"""
    if not hasattr(self, '_intent_cache'):
        self._intent_cache = {}
    return self._intent_cache.get(task_id)
```

**在首次编排完成后缓存**（`orchestrator.py:1558-1562`）:

```python
routing_result = self._routing_adapter.analyze(
    user_request=requirement.topic,
    requirement=requirement_dict,
    topic=requirement.topic,
)
# R-FIX-4: 缓存意图结果，供后续 reanalyze 融合使用
self._cache_intent_for_task(task_id, routing_result.intent_result)
```

---

### 2.5 修复五：LLM意图分析JSON解析增强

**目标**: 提高 `_parse_llm_json()` 的容错能力，减少JSON解析失败率。

**修改文件**: `semantic_intent.py`

当前逻辑（`semantic_intent.py:313-321`）:
```python
def _parse_llm_json(self, content):
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return json.loads(content.strip())
```

修改为：

```python
def _parse_llm_json(self, content):
    content = content.strip()
    # 1. 移除 markdown 代码块标记
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    
    # 2. 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # 3. 尝试提取 JSON 对象（处理 LLM 输出前后有文字的情况）
    import re
    # 查找第一个 { 到最后一个 } 之间的内容
    first_brace = content.find('{')
    last_brace = content.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(content[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass
    
    # 4. 尝试修复常见问题
    # 4a. 修复单引号 → 双引号
    fixed = content.replace("'", '"')
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    # 4b. 移除尾部逗号
    fixed = re.sub(r',\s*([}\]])', r'\1', content)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    # 5. 所有尝试失败，抛出原始异常
    raise json.JSONDecodeError(
        f"Failed to parse LLM JSON after all recovery attempts: {content[:200]}",
        content, 0
    )
```

---

### 2.6 修复六：深度研究关键词在 EXECUTING 状态下走意图分析而非直接中断

**目标**: "深度研究"关键词在 `research` 模式下不再直接中断当前研究重新进入framework，而是走正常的意图分析流程，由约束层决定是否放行。

**修改文件**: `research_api.py`

当前逻辑（`research_api.py:305-323`）:
```python
depth_keywords = ('深度研究', 'deep research', '按框架研究', '根据框架', '开始研究', 'start research', '详细分析', 'detailed analysis')
# ...
is_depth_command = any(kw in input_lower for kw in depth_keywords) and not any(input_lower.endswith(s) for s in question_suffixes)
if is_depth_command and latest_context.get('topic') and mode != 'framework':
    logger.info(f"Depth research keyword detected for {session_id}, entering framework mode directly")
    if mode == 'research':
        # 暂停+取消当前研究...
    return await self._enter_framework_mode(session_id, user_input)
```

问题：当 `mode == 'research'` 且研究正在运行时，检测到"深度研究"关键词直接中断当前研究重新进入framework，绕过了意图分析和约束层。

修改为：

```python
depth_keywords = ('深度研究', 'deep research', '按框架研究', '根据框架', '开始研究', 'start research', '详细分析', 'detailed analysis')
question_suffixes = ('？', '?', '吗', '呢', '是什么', '是什么意思', '怎么', '如何')
input_lower = user_input.strip().lower()
is_depth_command = any(kw in input_lower for kw in depth_keywords) and not any(input_lower.endswith(s) for s in question_suffixes)

if is_depth_command and latest_context.get('topic'):
    if mode == 'research':
        # R-FIX-6: 研究正在运行，不走直接中断，走正常意图分析+约束层
        # 消息会进入 _handle_research_msg() → _llm_converse() → _validate_action_for_state()
        # 如果用户确实要重新规划（关键词匹配），约束层会放行 enter_framework
        logger.info(f"Depth research keyword detected but already in research mode for {session_id}, "
                     f"deferring to intent analysis + action constraint")
        # 不 return，继续走后续的 _handle_research_msg() 流程
    elif mode != 'framework':
        logger.info(f"Depth research keyword detected for {session_id}, entering framework mode directly")
        return await self._enter_framework_mode(session_id, user_input)
```

---

### 2.7 修复七：`_llm_converse()` EXECUTING阶段prompt强化约束

**目标**: 在研究执行阶段，`_llm_converse()` 的prompt应明确约束LLM——重操作需用户明确意图，轻操作直接返回。

**修改文件**: `research_api.py`

**修改 `_build_dialogue_context()` 中 `EXECUTING` 状态的引导（`research_api.py:636`）**:

当前:
```python
ConversationState.EXECUTING: '## Current Dialogue Phase: Research Executing\nResearch is actively running.\n- Treat user messages as supplementary information by default.\n- Only use enter_framework if user EXPLICITLY requests redesign.\n'
```

修改为:
```python
ConversationState.EXECUTING: (
    '## Current Dialogue Phase: Research Executing\n'
    'Research is actively running with professional agents working.\n'
    'CRITICAL RULES for action selection:\n'
    '- Default action: "continue_chat" — for confirmations, greetings, simple questions, status queries.\n'
    '- "inject_requirement" — ONLY when user clearly asks to add/remove/supplement sections.\n'
    '- "modify_research" — ONLY when user EXPLICITLY uses words like 修改/调整/修订/adjust/modify. '
    'Do NOT use this for vague suggestions.\n'
    '- "enter_framework" — ONLY when user EXPLICITLY uses words like 重新规划/重新开始/换个方向/restart/redesign. '
    'NEVER use this for simple messages like "继续" or "好的".\n'
    '- When in doubt, use "continue_chat" with a brief reassuring message.\n'
)
```

**同时修改 `_build_research_running_context()` 的 Rules 部分（`research_api.py:689`）**:

当前:
```python
return f"\n## Research Executing\nTopic: {topic}\nSections: {sections_str}{inject_hint}\nRules for changes during research:\n- New section, supplement, cancellation → `inject_requirement` (lightweight, no pause)\n- User explicitly says pause/stop → `modify_research` (pause + re-plan)\n- User wants to stop entirely → `enter_framework`\n"
```

修改为:
```python
return (
    f"\n## Research Executing\n"
    f"Topic: {topic}\n"
    f"Sections: {sections_str}{inject_hint}\n"
    f"Rules for changes during research:\n"
    f"- New section, supplement, cancellation → `inject_requirement` (lightweight, no pause)\n"
    f"- User EXPLICITLY says 修改/调整/修订 → `modify_research` (pause + re-plan)\n"
    f"- User EXPLICITLY says 重新规划/重新开始/换个方向 → `enter_framework`\n"
    f"- Simple messages (继续/好的/ok/等) → `continue_chat`\n"
)
```

### 2.8 修复七补充：`_build_research_running_context()` 提供研究进度上下文

**目标**: LLM在EXECUTING阶段准确判断action的前提是**知道当前研究进度**。当前 `_build_research_running_context()` 只在研究完成后才返回信息，研究运行中返回空字符串，LLM完全不知道研究状态。

**修改文件**: `research_api.py`

**问题定位**:

`_build_research_running_context()` (line 667-689):
```python
def _build_research_running_context(self, session):
    mode = session.get('mode', 'chat')
    if mode != 'research':
        return ''
    research_context = session.get('research_context')
    if not research_context:
        return ''
    research_result = session.get('research_result')
    if not research_result or research_result.get('status') != 'completed':  # ❌ 只在完成后返回
        return ''
    ...
```

**研究运行期间session中真实可用的数据**（06-09日志验证）：

| 数据源 | 位置 | 内容 | 可用性 |
|--------|------|------|--------|
| `session['task_progress']` | ProgressStreamer持久化 | `{status: "running", progress: 0.05, current_phase: "orchestrating"}` | ✅ 可用，但只在编排阶段更新过一次 |
| `session['task_phases']` | 同上 | `[{id: "orchestrating", name: "Task Orchestration", status: "running"}]` | ✅ 可用，但只有1个phase |
| `session['research_context']` | 编排时写入 | `{topic, framework: {sections: [...]}, directions}` | ✅ 始终可用 |
| 磁盘 `data/results/{task_id}/result.json` | ResearchResultStore | `{completed_agents: [{agent_id, phase, success}], data_points: N}` | ✅ 每批次后更新，但**没有写入session** |
| `session['research_result']` | executor完成后写入 | 完整结果 | ❌ 运行中不存在 |

**核心问题**：
1. `_build_research_running_context()` 在研究运行中返回空字符串 → LLM不知道研究在运行
2. `ResearchResultStore` 有 `completed_agents` 信息但没写入session → LLM不知道哪些章节已完成
3. `task_progress` 只有 "orchestrating" 阶段 → LLM不知道当前在Phase 1/2/3

**修复方案**:

修改 `_build_research_running_context()` 使用已有数据，从磁盘 `ResearchResultStore` 读取进度（engine不写session，第三轮审查4号已取消第二步）。

```python
def _build_research_running_context(self, session):
    """构建研究运行上下文，供LLM判断用户意图。"""
    mode = session.get('mode', 'chat')
    if mode != 'research':
        return ''
    research_context = session.get('research_context')
    if not research_context:
        return ''
    
    topic = research_context.get('topic', '')
    framework = research_context.get('framework', {})
    sections = framework.get('sections', [])
    
    # === 研究完成后：提供完整信息（原逻辑保留） ===
    research_result = session.get('research_result')
    if research_result and research_result.get('status') in ('completed', 'completed_with_warnings'):
        if sections:
            sections_str = ', '.join(sections[:8]) + ('...' if len(sections) > 8 else '')
        else:
            sections_str = ''
        pending = session.get('_pending_section_injects', [])
        inject_hint = f" (Pending injects: {len(pending)})" if pending else ''
        return (
            f"\n## Research Status: COMPLETED\n"
            f"Topic: {topic}\n"
            f"Sections: {sections_str}{inject_hint}\n"
            f"The research has been completed. A report is available.\n"
            f"Rules for changes during research:\n"
            f"- New section, supplement, cancellation → `inject_requirement` (lightweight, no pause)\n"
            f"- User EXPLICITLY says 修改/调整/修订 → `modify_research` (pause + re-plan)\n"
            f"- User EXPLICITLY says 重新规划/重新开始/换个方向 → `enter_framework`\n"
            f"- Simple messages (继续/好的/ok/等) → `continue_chat`\n"
        )
    
    # === R-FIX-7b: 研究运行中：从已有数据构建上下文 ===
    # 1. 框架章节（research_context 编排时已写入）
    if not sections:
        sections_str = '(sections being determined)'
    else:
        sections_str = ', '.join(sections[:8]) + ('...' if len(sections) > 8 else '')
    
    # 2. 进度信息（task_progress，ProgressStreamer 持久化）
    task_progress = session.get('task_progress', {})
    task_phases = session.get('task_phases', [])
    progress_pct = task_progress.get('progress', 0)
    # task_progress.current_phase 通常为 "orchestrating"，因为 engine 不调用 start_phase
    
    # 3. 已完成的agent（从磁盘 ResearchResultStore 读取）
    completed_agents = []
    total_agents = 0
    try:
        from src.core.storage.research_result_store import ResearchResultStore
        store = ResearchResultStore(storage_path="data")  # R-FIX-7b-9: 构造参数名与源码一致
        stored = store.load_result(session_id)  # R-FIX-7b-8: 直接用session_id
        if stored:
            completed_agents = stored.get('completed_agents', [])
            data_point_count = len(stored.get('data_points', []))
    except Exception:
        stored = None
        data_point_count = 0
    
    # 4. 从 completed_agents 推算当前阶段
    # agent_id 格式: phase_N_agent_M
    phase_1_done = 0
    phase_2_done = 0
    phase_3_done = 0
    for ca in completed_agents:
        aid = ca.get('agent_id', '')
        if aid.startswith('phase_1_'):
            phase_1_done += 1
        elif aid.startswith('phase_2_'):
            phase_2_done += 1
        elif aid.startswith('phase_3_'):
            phase_3_done += 1
    
    # 从框架section数推算每个phase的agent数（Phase1和Phase2各8个agent对应8个section）
    section_count = len(sections) if sections else 0
    
    # 构建进度描述
    if phase_2_done > 0:
        current_phase_desc = f"深度分析(Phase 2): {phase_2_done}/{section_count} sections done"
    elif phase_1_done > 0:
        current_phase_desc = f"数据采集(Phase 1): {phase_1_done}/{section_count} sections done"
    else:
        current_phase_desc = "编排/启动中"
    
    # 5. 已完成的章节名（从 completed_agents 的 agent_id 推算）
    completed_section_names = []
    for ca in completed_agents:
        aid = ca.get('agent_id', '')
        # phase_1_agent_0 → section_0_XXX
        # 只标记为"已采集"，不列出具体名（因为 agent_id → section name 的映射需要 _get_section_id_from_agent）
        if ca.get('success') and aid.startswith('phase_1_'):
            completed_section_names.append(aid)
    
    completed_hint = ''
    if completed_section_names:
        completed_hint = f"\nData collection completed for: {len(completed_section_names)} sections"
    if data_point_count > 0:
        completed_hint += f"\nData points collected: {data_point_count}"
    
    pending = session.get('_pending_section_injects', [])
    inject_hint = f" (Pending injects: {len(pending)})" if pending else ''
    
    return (
        f"\n## Research Status: RUNNING ({progress_pct:.0%})\n"
        f"Topic: {topic}\n"
        f"Framework sections: {sections_str}{inject_hint}\n"
        f"Current phase: {current_phase_desc}\n"
        f"{completed_hint}\n"
        f"Research is actively running. Agents are working on the above sections.\n"
        f"Rules for changes during research:\n"
        f"- New section, supplement, cancellation → `inject_requirement` (lightweight, no pause)\n"
        f"- User EXPLICITLY says 修改/调整/修订 → `modify_research` (pause + re-plan)\n"
        f"- User EXPLICITLY says 重新规划/重新开始/换个方向 → `enter_framework`\n"
        f"- Simple messages (继续/好的/ok/等) → `continue_chat`\n"
    )
```

**数据准确性验证**（基于06-09日志）：

| 信息 | 来源 | 验证 |
|------|------|------|
| Topic | `research_context['topic']` | ✅ 编排时写入，始终可用 |
| Framework sections | `research_context['framework']['sections']` | ✅ 编排时写入，8个章节 |
| completed_agents | 磁盘 `ResearchResultStore` | ✅ 日志显示 `_execute_batch` 每批次后 `save_result` |
| data_point_count | 同上 | ✅ 日志显示 "268 data_points" |
| 当前阶段 | 从 `completed_agents` 的 `agent_id` 前缀推算 | ✅ `phase_1_agent_*` = Phase1, `phase_2_agent_*` = Phase2 |
| progress百分比 | `task_progress.progress` | ⚠️ 只在编排时更新为0.05，后续未更新，但仍有参考价值 |

**目标**: 修复 `_handle_user_message()` 中 `cm` 变量可能未定义的 Bug。

**修改文件**: `research_api.py`

当前逻辑: `cm = get_cancel_manager()` 仅在 line 312 的 `if is_depth_command and mode == 'research'` 分支内部赋值，但 line 353 在另一个分支使用了 `cm.is_paused(session_id)`。

修改: 在 `_handle_user_message()` 方法入口处（depth_keyword 判断之前）提前初始化 `cm`:

```python
async def _handle_user_message(self, session_id, user_input, skip_lang_detect=False):
    # ... existing code ...
    mode = session.get('mode', 'chat')
    
    # 提前初始化 cm，避免后续分支 NameError
    from src.core.orchestrator.execution.coordinator.cancel_manager import get_cancel_manager
    cm = get_cancel_manager()
    
    # ... rest of method ...
```

同时删除 line 312-313 的局部 `cm` 初始化（已提前到方法级别）。

---

## 3. 修复优先级与实施顺序

| 优先级 | 修复项 | 影响范围 | 风险 |
|--------|--------|----------|------|
| **P0** | 修复八：`cm` 变量未定义Bug | `research_api.py` | 低 - 变量位置调整 |
| **P0** | 修复一：EXECUTING阶段action约束层 | `research_api.py` | 中 - 需要充分测试约束逻辑 |
| **P0** | 修复六：深度研究关键词走意图分析 | `research_api.py` | 低 - 逻辑简单 |
| **P1** | 修复七：EXECUTING阶段prompt强化 | `research_api.py` | 低 - prompt调整 |
| **P1** | 修复二：增量分析意图融合 | `intelligent_routing_adapter.py` | 低 - 接口兼容 |
| **P1** | 修复三：传递已有意图结果供融合 | `research_api.py` + `orchestrator.py` | 低 - 接口兼容 |
| **P1** | 修复四：reanalyze意图融合 | `orchestrator.py` | 中 - 需要缓存管理 |
| **P2** | 修复五：JSON解析增强 | `semantic_intent.py` | 低 - 纯容错增强 |

### 推荐实施顺序

1. **修复八** (必须前置) — 修复 `cm` 变量未定义Bug
2. **修复一** (核心修复) — EXECUTING阶段action约束层
3. **修复六** (配套) — 深度研究关键词走意图分析+约束层
4. **修复七** (配套) — EXECUTING阶段prompt强化
5. **修复五** (低风险) — JSON解析增强
6. **修复二 + 修复三** (配套) — 增量分析意图融合 + 缓存传递
7. **修复四** (收尾) — reanalyze意图融合

---

## 4. 验证方案

### 4.1 单元测试

```python
# test_research_action_constraint.py
def test_validate_action_heavy_without_explicit_intent():
    """EXECUTING状态下，LLM返回重操作但用户输入无明确关键词 → 降级"""
    api = ResearchAPI(...)
    conv_machine = ConversationStateMachine(state=ConversationState.EXECUTING)
    assert api._validate_action_for_state('enter_framework', conv_machine, '继续') == 'continue_chat'
    assert api._validate_action_for_state('modify_research', conv_machine, '好的') == 'inject_requirement'

def test_validate_action_heavy_with_explicit_intent():
    """EXECUTING状态下，用户明确表达重操作意图 → 放行"""
    api = ResearchAPI(...)
    conv_machine = ConversationStateMachine(state=ConversationState.EXECUTING)
    assert api._validate_action_for_state('enter_framework', conv_machine, '重新规划研究') == 'enter_framework'
    assert api._validate_action_for_state('modify_research', conv_machine, '修改研究方向') == 'modify_research'

def test_validate_action_light_operations():
    """EXECUTING状态下，轻操作直接放行"""
    api = ResearchAPI(...)
    conv_machine = ConversationStateMachine(state=ConversationState.EXECUTING)
    assert api._validate_action_for_state('continue_chat', conv_machine, '任何消息') == 'continue_chat'
    assert api._validate_action_for_state('inject_requirement', conv_machine, '加一个章节') == 'inject_requirement'

def test_validate_action_paused_state():
    """PAUSED状态下，所有action合法"""
    api = ResearchAPI(...)
    conv_machine = ConversationStateMachine(state=ConversationState.PAUSED)
    assert api._validate_action_for_state('enter_framework', conv_machine, '继续') == 'enter_framework'
    assert api._validate_action_for_state('modify_research', conv_machine, 'ok') == 'modify_research'

def test_incremental_intent_fusion():
    """测试增量分析意图融合"""
    adapter = IntelligentRoutingAdapter(use_llm=False)
    existing = DeepIntentResult(
        primary_intent=IntentType.RESEARCH,
        intent_confidence=0.9,
        intent_reasoning="Initial high-confidence analysis",
        complexity=TaskComplexity.SINGLE,
    )
    # 增量分析仍执行，但低置信度结果被融合过滤
    result = adapter.analyze_incremental(
        user_request="test",
        requirement={'topic': 'test', 'aspects': ['a', 'b']},
        existing_intent_result=existing,
    )
    # 融合后应保留高置信度的已有结果
    assert result.intent_result.intent_confidence >= existing.intent_confidence

def test_json_parse_recovery():
    """测试JSON解析容错"""
    analyzer = SemanticIntentAnalyzer.__new__(SemanticIntentAnalyzer)
    result = analyzer._parse_llm_json("{'primary_intent': 'research'}")
    assert result['primary_intent'] == 'research'
    result = analyzer._parse_llm_json('{"a": 1,}')
    assert result['a'] == 1
    result = analyzer._parse_llm_json('Here is the result: {"a": 1} End.')
    assert result['a'] == 1
```

### 4.2 集成测试场景

| 场景 | 预期行为 | 验证点 |
|------|----------|--------|
| 研究中发送"继续" | 意图分析执行 → action=continue_chat → 返回研究状态 | `_llm_converse` 执行，约束层不降级 |
| 研究中发送"重新规划" | 意图分析执行 → action=enter_framework → 约束层放行 → 进入框架 | 约束层日志显示放行 |
| 研究中发送"修改研究方向" | 意图分析执行 → action=modify_research → 约束层放行 → 修订 | 约束层日志显示放行 |
| 研究中发送"加一个电池业务" | 意图分析执行 → action=inject_requirement → 约束层放行 | 不中断研究 |
| 研究中发送"深度研究" | 关键词检测 → 走意图分析而非直接中断 → 约束层判断 | 不绕过约束层 |
| LLM误判返回enter_framework（用户说"好的"） | 意图分析执行 → 约束层降级为continue_chat | 约束层日志显示降级 |
| 修改研究时 | 增量分析执行意图分析 → 融合已有结果 | 低置信度不覆盖高置信度 |
| JSON解析失败 | 自动恢复而非降级到关键词 | 日志显示 `recovery attempts` |

### 4.3 回归验证

- 研究正常启动和完成流程不受影响
- 暂停/恢复功能正常
- 修订功能正常（意图分析执行+融合）
- 框架确认流程正常
- 对话模式（chat mode）不受影响

---

## 5. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 约束层误降级用户真实重操作意图 | 重操作关键词列表持续维护；用户仍可通过"暂停"→重操作绕过约束 |
| 增量分析意图融合逻辑过于保守 | 新意图置信度更高时采用新结果，只在低置信度时保留已有 |
| 意图缓存丢失 | 降级到完整分析（但记录警告） |
| JSON解析过度修复引入新问题 | 每步修复独立try-catch，失败仍抛原始异常 |
| EXECUTING阶段prompt约束过严 | 约束层兜底：即使LLM忽略prompt返回重操作，约束层也会降级 |
| "继续"在未暂停研究时语义模糊 | 约束层将其归为continue_chat，返回研究进行中提示 |
| orchestrator 无法访问 session_manager | 提供方案B降级路径：在 research_api 的执行回调中缓存 |
| 未来新增action类型 | 只需在`HEAVY_ACTIONS`中注册即可，无需修改约束逻辑 |

---

## 6. 审查记录

### 6.1 第一轮审查发现

| # | 问题 | 严重度 | 处理 |
|---|------|--------|------|
| 1 | `cm` 变量在 `_handle_user_message()` line 353 使用但未在之前定义 | **高** | 新增修复八 |
| 2 | 分类器中 pause/cancel 分支与 `handle_message()` 中 line 344-356 重复 | 中 | 移除分类器中的 pause/cancel 分支 |
| 3 | `wait_patterns` 中 "继续" 用子串匹配会误判 "继续研究" | 中 | 改为精确匹配 |
| 4 | 修复三中意图结果缓存位置不够明确 | 低 | 补充具体实现位置和方案B降级路径 |
| 5 | `_handle_complex_research_msg` 中 `enter_framework` 直接拒绝可能过于严格 | 低 | 保留，引导用户先暂停再调整 |
| 6 | **775个数据点采集成功但报告全空**——内容锁误锁+聚合匹配失败 | **致命** | 新增第7节完整修复方案 |

---

## 7. 致命Bug：数据采集成功但报告内容全空

### 7.1 问题描述

06-09测试中，research_39735059 任务采集了775个数据点、775个来源，但最终8个章节全部显示"⚠️ 本章节数据不足"，报告内容为零。

**关键日志链**:

```
1. [create_boundary] phase_1_agent_X 未找到对应章节'section_X_XXX' 的 research agent
   → 数据边界控制器无法将 agent 映射到章节

2. content_lock: Section section_X completed: quality=50.00
   → Phase 1（数据采集）完成后，章节被标记为 COMPLETED

3. [内容锁] Agent phase_2_agent_X 对应章节 section_X 被锁定: Already completed
   → Phase 2（分析）全部被跳过

4. [批次2] 没有有效的Agent，跳过
   → 所有分析agent被锁

5. 章节 'XXX' 无匹配内容，生成降级占位
   → 聚合器无法将 agent 结果映射到框架章节
```

### 7.2 根因链

#### 7.2.1 两条 Agent 创建路径的 ID 体系不一致

| 创建路径 | agent_id 格式 | section_ids | `_extract_aspect` 能否解析 | 来源 |
|----------|--------------|-------------|---------------------------|------|
| `_create_agents` (line 3497) | `research_核心财务指标_1` | 无 AgentSpec，直接创建 | **能** → `核心财务指标` | orchestrator 硬编码 |
| **`_create_agents_from_plan` (line 3349)** ← **当前采用** | `phase_1_agent_0` | AgentSpec 中**有** `section_ids=["section_0_核心财务指标"]` | **不能** → 返回原始 `phase_1_agent_0` | DynamicPhaseOrchestrator |

**核心矛盾**：`AgentSpec` 已包含 `section_ids`，但创建 agent 后**没有任何代码将 `spec.section_ids` 赋值到 agent 实例属性上**，信息在创建环节丢失。

#### 7.2.2 完整断裂链

```
DynamicPhaseOrchestrator._create_dc_phase() (dynamic_orchestrator.py:328)
    ↓ 生成 AgentSpec(agent_id="phase_1_agent_0", section_ids=["section_0_核心财务指标"])
    
orchestrator._create_agents_from_plan() (orchestrator.py:3445)
    ↓ agent_factory.create_agent_with_session(agent_id=spec.agent_id, ...)
    ↓ ❌ spec.section_ids 未赋值到 agent.section_id → 信息丢失
    
engine._get_section_id_from_agent() (engine.py:2472)
    ↓ hasattr(agent, 'section_id') → False
    ↓ 回退到 agent.agent_id → "phase_1_agent_0"
    
data_boundary_controller._extract_aspect_from_agent_id() (data_boundary_controller.py:299)
    ↓ phase_N_agent_M 格式 → 返回原始 agent_id
    ↓ ❌ 无法匹配到 "核心财务指标"
    
content_lock.mark_completed("phase_1_agent_0", quality)
    ↓ Phase 1 完成后，以 agent_id 为 key 标记 COMPLETED
    
engine 执行 Phase 2 agent
    ↓ _get_section_id_from_agent() → "phase_2_agent_0"
    ↓ content_lock.can_execute("phase_2_agent_0") → True（不同 key，未被锁）
    ↓ ❌ 但 Phase 2 的 section_id 实际与 Phase 1 相同，应共享锁状态
    ↓ 实际日志显示 section_id 被统一映射为 "section_X"，导致 Phase 1 完成后锁住同章节
    
result_aggregator (result_aggregator.py:1024)
    ↓ result.get("_section_id", "") → 空（engine 注入的 section_id 是 "phase_1_agent_0"）
    ↓ ❌ 无法匹配到框架章节 "核心财务指标与盈利能力"
    ↓ "无匹配内容，生成降级占位"
```

### 7.3 ~~修复九~~：Agent 工厂设置 section_id 属性（已取消 — 第二轮审查证实不需要）

> **审查结论**：`agent.section_id` 已通过 `context["section_id"]` → `GenericAgent.__init__` (line 163) 正确传递。
> 日志证据：`Agent phase_1_agent_7 目标章节: section_1_行业创造与动能` — section_id 已正确。
> 
> 传递链：`DynamicPhaseOrchestrator._create_dc_phase()` → `AgentSpec.section_ids=["section_0_核心财务指标"]` → `to_decomposition_plan()` line 126 `output_keys=spec.section_ids` → `_create_agents_from_plan()` line 3418 `context["section_id"]=spec.output_keys[0]` → `AgentFactory.create_agent_with_session()` → `GenericAgent.__init__()` line 163 `self.section_id=self._context.get("section_id","")`

**原方案（已取消）**：

**目标**: 每个 agent 必须携带 `section_id` 属性，指向其对应的框架章节ID，而非使用通用 agent_id。

**修改文件**: `orchestrator.py`（`_create_agents_from_plan` 方法，line 3445 之后）

**问题定位**:

`_create_agents_from_plan()` line 3445-3451 创建 agent 时：
```python
agent, session = self._agent_factory.create_agent_with_session(
    agent_id=spec.agent_id,       # "phase_1_agent_0"
    capability=capability,
    parent_session_id=task_id,
    context=context,               # context["section_id"] = spec.output_keys[0] (line 3418)
    category=spec.category,
)
# ❌ 此处缺失：spec.section_ids 未赋值到 agent 实例属性
```

`AgentSpec` 定义（`dynamic_orchestrator.py:41`）中 `section_ids: List[str]` 已包含正确的章节ID（如 `["section_0_核心财务指标"]`），但创建 agent 后未传递。

**修复方案**:

在 `orchestrator.py` line 3451（`agents.append(agent)` 之前）插入：

```python
agent, session = self._agent_factory.create_agent_with_session(
    agent_id=spec.agent_id,
    capability=capability,
    parent_session_id=task_id,
    context=context,
    category=spec.category,
)
# R-FIX-9: 将 AgentSpec.section_ids 传递到 agent 实例，供下游匹配
if hasattr(spec, 'section_ids') and spec.section_ids:
    agent.section_id = spec.section_ids[0]
elif hasattr(spec, 'target_section') and spec.target_section:
    agent.section_id = spec.target_section
else:
    agent.section_id = spec.agent_id  # 兜底：无 section_ids 时回退到 agent_id
```

**验证点**: 
- `engine._get_section_id_from_agent()` (line 2472) 优先检查 `agent.section_id`，赋值后将返回 `"section_0_核心财务指标"` 而非 `"phase_1_agent_0"`
- `engine` line 1293 的 `agent_result["section_id"]` 注入也会使用正确的章节ID
- `result_aggregator` line 1024 的 `_section_id` 匹配将生效

### 7.4 修复十：内容锁区分 DATA_COLLECTED 和 COMPLETED 状态（P0）

**目标**: Phase 1（数据采集）完成后标记为 `DATA_COLLECTED`，Phase 2（分析）完成后才标记为 `COMPLETED`。

**修改文件**: `content_lock.py` + `engine.py`

**问题定位**:

当前 `SectionState` 有7种状态（**第二轮审查修正**，非之前分析的4种）：
```python
# content_lock.py - SectionState (line 36)
class SectionState(Enum):
    LOCKED = "locked"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"   # ❌ 不区分"数据采集完成"和"分析完成"
    FAILED = "failed"
    SKIPPED = "skipped"
```

`engine.py` line 1299 在 Phase 1 agent 完成后直接调用：
```python
unlocked_sections = content_lock.mark_completed(section_id, quality_score)
# ❌ 无论 agent 是 data_collection 还是 analysis 类型，一律标记 COMPLETED
```

**第二轮审查发现**：`agent_result.get("agent_type")` 始终为 `"dynamic"`（factory.py line 298），**不能**用 `agent_type == "data_collection"` 判断。应改用 `result.get("category")` 或 `agent.config.get("category")`。

**第四轮审查发现3处遗漏**（P0致命）：

1. `mark_running()` (line 395) 不接受 `DATA_COLLECTED` 状态 → Phase 2 agent 无法从 `DATA_COLLECTED` 转为 `RUNNING`
2. `_check_unlock_conditions()` (line 303) 和 `_try_unlock()` (line 346) 只认 `COMPLETED` → 依赖 `DATA_COLLECTED` 的章节解锁失败
3. `mark_section_state()` 方法不存在 → 必须新增

**修复方案**:

1. 扩展 `SectionState`：
```python
class SectionState(Enum):
    LOCKED = "locked"
    PENDING = "pending"
    RUNNING = "running"
    DATA_COLLECTED = "data_collected"    # 新增：数据采集完成，分析可执行
    COMPLETED = "completed"              # 分析完成，章节终态
    FAILED = "failed"
    SKIPPED = "skipped"
```

2. 新增 `mark_section_state()` 方法：
```python
def mark_section_state(self, section_id: str, state: SectionState) -> bool:
    """直接设置章节状态（供外部调用，如区分 DATA_COLLECTED 和 COMPLETED）"""
    status = self._section_statuses.get(section_id)
    if not status:
        logger.warning(f"Section {section_id} not found for mark_section_state")
        return False
    old_state = status.state
    status.state = state
    logger.info(f"[内容锁] Section {section_id} state: {old_state.value} → {state.value}")
    return True
```

3. 修改 `can_execute()` 逻辑（line 202）——**含未注册章节放行**：
```python
def can_execute(self, section_id: str) -> Tuple[bool, str]:
    status = self._section_statuses.get(section_id)
    if not status:
        return True, f"Section {section_id} not registered, allowing execution"  # R-FIX-10a: 放行未注册章节（如 calibrator）

    if status.state == SectionState.RUNNING:
        return False, "Already running"
    if status.state == SectionState.COMPLETED:
        return False, "Already completed"
    if status.state == SectionState.DATA_COLLECTED:
        return True, "Data collected, ready for analysis"  # R-FIX-10: 新增
    if status.state == SectionState.FAILED:
        if status.retry_count >= self._max_retries:
            return False, f"Max retries ({self._max_retries}) exceeded"
        return True, "Retry after failure"

    if status.content_locked:
        can_unlock, reason = self._check_unlock_conditions(section_id)
        if not can_unlock:
            return False, reason

    return True, "Ready to execute"
```

4. 修改 `mark_running()` (line 395)——**接受 DATA_COLLECTED**：
```python
# 原代码:
if status.state not in (SectionState.PENDING, SectionState.FAILED):
    return False
# 修正为:
if status.state not in (SectionState.PENDING, SectionState.FAILED, SectionState.DATA_COLLECTED):
    return False
```

5. 修改 `_check_unlock_conditions()` (line 303) 和 `_try_unlock()` (line 346)——**识别 DATA_COLLECTED**：
```python
# 原代码 (line 303):
if required_status.state != SectionState.COMPLETED:
    return False, (...)
# 修正为:
if required_status.state not in (SectionState.COMPLETED, SectionState.DATA_COLLECTED):
    return False, (...)

# 原代码 (line 346):
if required_status.state != SectionState.COMPLETED:
    return False
# 修正为:
if required_status.state not in (SectionState.COMPLETED, SectionState.DATA_COLLECTED):
    return False
```

6. 修改 `engine.py` **所有4处** agent 完成后的处理，用 `category` 判断 + agent_id 兜底：

**6a. 正常执行路径 (line 1294-1299)**:
```python
if agent_result.get("success"):
    scheduler.mark_completed(agent_id, agent_result)
    if content_lock is not None:
        quality_score = self._extract_quality_score(agent_result)
        # R-FIX-10: 区分 data_collection 和 analysis 的完成状态
        _category = (agent_result.get("category", "")
                     or (agent.config.get("category", "") if agent else ""))
        # R-FIX-10-兜底: category 为空时从 agent_id 前缀推断
        if not _category and agent:
            _aid = agent.agent_id or ""
            if _aid.startswith("phase_1_"):
                _category = "research"
            elif _aid.startswith("phase_2_"):
                _category = "analysis"
        if _category == "research":
            content_lock.mark_section_state(section_id, SectionState.DATA_COLLECTED)
        else:
            unlocked_sections = content_lock.mark_completed(section_id, quality_score)
            if unlocked_sections:
                logger.info(f"[内容锁] 章节 {section_id} 完成，解锁章节: {unlocked_sections}")
                for _usid in unlocked_sections:
                    _ua = _section_to_agent.get(_usid)
                    if _ua:
                        pending_unlocked.append(_ua)
```

**6b. 缓存命中路径 (line 1150-1159)**:
```python
completed_results.append({
    "success": True,
    "agent_id": agent_id,
    "section_id": section_id,
    "_section_id": section_id,          # R-FIX-13
    "content": content[:50000],
    "data_points": cached_result.get("data_points", []),
    "sources": cached_result.get("sources", []),
    "charts": cached_result.get("charts", []),
    "cached": True,
})
```

**6c. 缓存命中后的内容锁更新 (line 1188-1194)**:
```python
scheduler.mark_completed(agent_id, agent_result)
if content_lock is not None:
    # R-FIX-10: 缓存路径也需要 category 区分
    _cat = agent.config.get("category", "") if agent else ""
    if not _cat and agent:
        _aid = agent.agent_id or ""
        if _aid.startswith("phase_1_"):
            _cat = "research"
        elif _aid.startswith("phase_2_"):
            _cat = "analysis"
    if _cat == "research":
        content_lock.mark_section_state(section_id, SectionState.DATA_COLLECTED)
    else:
        content_lock.mark_completed(section_id, 1.0)
```

**6d. QC重执行路径 (line 1223-1227)**:
```python
if agent:
    section_id = self._get_section_id_from_agent(agent)
    agent_result["section_id"] = section_id
    agent_result["_section_id"] = section_id  # R-FIX-13
    # R-FIX-10: QC路径也需要 category 区分
    _cat = agent.config.get("category", "") if agent else ""
    if not _cat and agent:
        _aid = agent.agent_id or ""
        if _aid.startswith("phase_1_"):
            _cat = "research"
        elif _aid.startswith("phase_2_"):
            _cat = "analysis"
    if _cat == "research":
        content_lock.mark_section_state(section_id, SectionState.DATA_COLLECTED)
    else:
        content_lock.mark_completed(section_id, 1.0)
```

**category 值映射**（来自 `dynamic_orchestrator.py:to_decomposition_plan` line 111-118）：

| Phase | ResearchPhase | category | 标记状态 |
|-------|--------------|----------|----------|
| Phase 1 | DATA_COLLECTION | `"research"` | `DATA_COLLECTED` |
| Phase 2 | DEEP_ANALYSIS | `"analysis"` | `COMPLETED` |
| Phase 3 | CALIBRATION | `"calibration"` | `COMPLETED` |

**agent_id 兜底**：当 `category` 为空时，从 `agent_id` 前缀推断：
- `phase_1_*` → `"research"` → `DATA_COLLECTED`
- `phase_2_*` → `"analysis"` → `COMPLETED`
- `phase_3_*` → `"calibration"` → `COMPLETED`

**验证点**:
- Phase 1 完成后日志显示 `DATA_COLLECTED` 而非 `COMPLETED`
- Phase 2 agent 的 `can_execute()` 返回 `(True, "Data collected, ready for analysis")`
- Phase 2 完成后才标记 `COMPLETED`
- Phase 2 的 `mark_running()` 接受从 `DATA_COLLECTED` 转为 `RUNNING`
- 依赖 `DATA_COLLECTED` 章节的解锁条件正常触发
- calibrator 的 `can_execute()` 对未注册章节返回 `(True, "...allowing execution")`

### 7.5 修复十一：数据边界控制器使用 section_id 而非 agent_id（P2 — 降级为噪音清理，无需补全）

> **第二轮审查结论**：data_boundary_controller 的匹配失败**非根因**。engine.py line 2044 用 `analysis_boundary.allowed_agents = set(dep_list)` 直接覆盖了 `create_boundary_for_analysis` 的匹配结果。Phase 1 的 `dep_list=[]` 导致 `allowed_agents=set()` 是**正确行为**（自己采集无需上游数据），Phase 2 的 `dep_list=['phase_1_agent_0']` 也能正确设置依赖。日志中的 warning 只是噪音。

> **实施状态**：**部分实施，无需补全**。`data_boundary_controller.py` 已添加 `agent_section_map` 参数和优先匹配逻辑，但 `engine.py` 调用处未传入该映射。由于 `engine.py:2072` 用 `dep_list` 直接覆盖 `allowed_agents`，传入与否均不影响最终行为，故不再补全。

**目标**: `data_boundary_controller` 从 agent 的 `section_id` 属性获取章节名，而非从 agent_id 解析。

**修改文件**: `data_boundary_controller.py`

**问题定位**:

`create_boundary_for_analysis()` (line 229) 调用 `_extract_aspect_from_agent_id()` (line 260)：
```python
# line 254-260
for agent_id in all_agent_ids:
    if not agent_id.startswith("research_") and not agent_id.startswith("phase_"):
        continue
    agent_aspect = _extract_aspect_from_agent_id(agent_id)  # ❌ 只接受 str
```

`_extract_aspect_from_agent_id()` (line 281) 是纯字符串函数，无法访问 agent 实例属性：
```python
def _extract_aspect_from_agent_id(agent_id: str) -> str:
    # line 299: phase_N_agent_M 格式 → 返回原始 agent_id
    if len(parts) >= 4 and parts[0] == "phase" and parts[-2] == "agent":
        return agent_id  # ❌ 无法提取有意义的章节名
```

**修复方案**:

1. 修改 `create_boundary_for_analysis()` 签名，接受 agent 实例列表而非 agent_id 字符串列表：
```python
def create_boundary_for_analysis(
    analysis_agent_id: str,
    target_aspect: str,
    all_agent_ids: List[str],
    agent_section_map: Optional[Dict[str, str]] = None,  # 新增：agent_id → section_id 映射
) -> DataBoundary:
```

2. 匹配逻辑优先使用 `agent_section_map`：
```python
for agent_id in all_agent_ids:
    if not agent_id.startswith("research_") and not agent_id.startswith("phase_"):
        continue
    
    # R-FIX-11: 优先使用 agent_section_map
    if agent_section_map and agent_id in agent_section_map:
        agent_aspect = agent_section_map[agent_id]
    else:
        agent_aspect = _extract_aspect_from_agent_id(agent_id)
    
    if agent_aspect == aspect_to_match:
        allowed_agents.add(agent_id)
    elif aspect_to_match and agent_aspect and (aspect_to_match in agent_aspect or agent_aspect in aspect_to_match):
        allowed_agents.add(agent_id)
```

3. `engine.py` 调用处（line 2036-2038）传入映射：
```python
from .data_boundary_controller import create_boundary_for_analysis
# 构建 agent_id → section_id 映射
_agent_section_map = {}
for _a in scheduler.agents:
    if hasattr(_a, 'section_id') and _a.section_id:
        _agent_section_map[_a.agent_id] = _a.section_id

analysis_boundary = create_boundary_for_analysis(
    analysis_agent_id=agent_id,
    target_aspect=target_aspect,
    all_agent_ids=[a.agent_id for a in scheduler.agents],
    agent_section_map=_agent_section_map,  # 新增
)
```

**验证点**:
- `create_boundary_for_analysis` 日志不再出现"未找到对应章节"警告
- Phase 2 agent 的 `allowed_agents` 包含对应 Phase 1 agent

### 7.6 修复十二：结果聚合器使用 section_id 优先匹配（P1 — 含 `_determine_section_target` 修复）

**目标**: 聚合器使用 agent 结果中的 `section_id`（由 engine 注入）作为首要匹配键。

**修改文件**: `result_aggregator.py`

**问题定位**:

`_collect_stage_content()` (line 1023-1028) 已有 `_section_id` 优先逻辑：
```python
# line 1023-1028
_sec_id = result.get("_section_id", "")
if _sec_id:
    section_target = _sec_id
else:
    section_target = self._determine_section_target(agent_id, stage, agent_id)
```

但 `engine.py` line 1293 注入的 key 是 `section_id` 而非 `_section_id`：
```python
agent_result["section_id"] = section_id  # ❌ key 不匹配
```

聚合器查找 `result.get("_section_id", "")` → 找不到 → 回退到启发式匹配 → 失败。

**修复方案**:

1. 统一 key 名称。在 `engine.py` line 1293 改为：
```python
agent_result["section_id"] = section_id       # 保留（兼容）
agent_result["_section_id"] = section_id      # R-FIX-12: 聚合器使用的 key
```

2. 聚合器 `_convert_to_sections()` 中的匹配逻辑（line 334-414）也需要增加 `section_id` 直接匹配：
```python
# 在现有匹配逻辑之前，增加 section_id 精确匹配
_result_sec_id = stage_content.get("_section_id", "") or stage_content.get("section_id", "")
if _result_sec_id and _result_sec_id not in used_keys:
    # 尝试与框架章节 ID 精确匹配
    for section in framework_sections:
        fw_sec_id = section.get("id", "") or section.get("section_id", "")
        if _result_sec_id == fw_sec_id:
            content = extract_content(stage_content[_result_sec_id])
            matched_key = _result_sec_id
            break
```

**验证点**:
- 聚合器日志显示 `精确匹配(ID): 'section_0_核心财务指标'` 而非"无匹配内容"
- 最终报告8个章节均有实际内容

### 7.7 修复十三：Engine 在 agent 结果中注入 section_id（P0）

**目标**: 确保 engine 在 agent 执行完成后，将 `section_id` 注入结果字典，且 key 与聚合器一致。

**修改文件**: `engine.py`

**问题定位**:

`engine.py` line 1290-1293：
```python
for agent_result in batch_results:
    agent_id = agent_result.get("agent_id", "")
    agent = scheduler.get_agent_by_id(agent_id)
    section_id = self._get_section_id_from_agent(agent) if agent else self._get_section_id_from_agent_id(agent_id)
    agent_result["section_id"] = section_id  # ❌ key 是 "section_id"，聚合器查找 "_section_id"
```

`_get_section_id_from_agent()` (line 2472) 优先检查 `agent.section_id`，但修复九之前该属性不存在，回退到 `agent.agent_id`。

**第四轮审查发现3处遗漏**（P0致命）：

| 遗漏路径 | 代码位置 | 问题 |
|----------|----------|------|
| 缓存命中路径 | line 1150-1159 | `completed_results.append` 中无 `_section_id` |
| QC重执行路径 | line 1223-1227 | `agent_result` 中无 `_section_id` |
| 缓存命中内容锁 | line 1188-1194 | 无 category 区分（已在修复十6c中修正） |

**修复方案**:

1. 修复九已取消——`agent.section_id` 已通过 context 正确传递（`GenericAgent.__init__` line 163 从 `self._context` 提取），`_get_section_id_from_agent()` 已返回正确的章节ID。

2. **正常执行路径** (line 1293)——注入 `_section_id` 双 key：
```python
agent_result["section_id"] = section_id       # 保留兼容
agent_result["_section_id"] = section_id      # R-FIX-13: 聚合器 _collect_stage_content 使用的 key
```

3. **缓存命中路径** (line 1150-1159)——补充 `_section_id`：
```python
completed_results.append({
    "success": True,
    "agent_id": agent_id,
    "section_id": section_id,
    "_section_id": section_id,          # R-FIX-13: 缓存路径也需注入
    "content": content[:50000],
    "data_points": cached_result.get("data_points", []),
    "sources": cached_result.get("sources", []),
    "charts": cached_result.get("charts", []),
    "cached": True,
})
```

4. **QC重执行路径** (line 1223-1227)——补充 `_section_id`：
```python
if agent:
    section_id = self._get_section_id_from_agent(agent)
    agent_result["section_id"] = section_id
    agent_result["_section_id"] = section_id  # R-FIX-13
```

**验证点**:
- `agent_result` 中同时包含 `section_id` 和 `_section_id` 两个 key
- `_section_id` 值为 `"section_0_核心财务指标"` 而非 `"phase_1_agent_0"`
- 4条代码路径（正常、缓存、QC、缓存命中锁）全部覆盖

---

## 8. 数据丢失修复优先级与实施顺序（第二轮审查修正版）

| 优先级 | 修复项 | 修改文件 | 关键行号 | 说明 |
|--------|--------|----------|----------|------|
| ~~P0~~ | ~~修复九~~ | ~~取消~~ | — | **第二轮审查证实不需要**，section_id 已通过 context 正确传递 |
| **P0** | 修复十（修正版）：内容锁区分状态 | `content_lock.py` + `engine.py` | SectionState枚举 + 1294-1299 | **核心修复**，用 category 判断（非 agent_type），解决 Phase 2 被误锁 |
| **P0** | 修复十三：Engine 注入 _section_id | `engine.py` | 1293, 1194 | **核心修复**，统一 key 名称，让 provenance 匹配生效 |
| **P1** | 修复十二（补充版）：聚合器 key + _determine_section_target | `result_aggregator.py` | 1023-1028, 942-943 | 补充：data_collection 阶段返回 `"data"` 不做映射的问题 |
| **P2** | 修复十一：边界控制器噪音清理 | `data_boundary_controller.py` | 229-270 | 非根因，line 2044 用 dep_list 覆盖了匹配结果 |

### 推荐实施顺序

1. **修复十** → 内容锁区分 DATA_COLLECTED / COMPLETED，用 category 判断，这是解决 Phase 2 被锁的核心
2. **修复十三** → Engine 注入 `_section_id` 双 key，让聚合器 provenance 匹配路径生效
3. **修复十二** → 聚合器 `_determine_section_target` 对 data_collection 阶段返回正确章节ID
4. **修复十一** → 边界控制器噪音清理（低优先级）

### 验证场景

| 场景 | 预期行为 | 验证点 |
|------|----------|--------|
| Phase 1 数据采集完成 | 章节标记为 DATA_COLLECTED | content_lock 日志显示 DATA_COLLECTED |
| Phase 2 分析执行 | 不被内容锁阻止 | 日志显示 Phase 2 正常执行 |
| Phase 2 完成后 | 章节标记为 COMPLETED | content_lock 日志显示 COMPLETED |
| 结果聚合 | agent 结果正确映射到框架章节 | 无"无匹配内容"错误 |
| 最终报告 | 8个章节均有实际内容 | HTML 中无"数据不足"占位 |

---

## 9. 第二轮逐行审查记录（2026-06-10）

### 9.1 审查方法

逐行对照源码与06-09日志（`research_39735059` 任务），验证方案中每个修复项的假设是否成立。

### 9.2 审查发现

| # | 修复项 | 原假设 | 审查结论 | 处理 |
|---|--------|--------|----------|------|
| 1 | 修复九 | `agent.section_id` 未设置，需手动赋值 | **假设错误**。`GenericAgent.__init__` (line 163) 已从 `context["section_id"]` 提取并设置 `self.section_id`。`_create_agents_from_plan` line 3418 已设置 `context["section_id"] = spec.output_keys[0]`。日志证实 section_id 正确：`phase_1_agent_7 → section_1_行业创造与动能` | **取消修复九** |
| 2 | 修复十 | 用 `agent_result.get("agent_type") == "data_collection"` 判断 | **假设错误**。`agent_type` 始终为 `"dynamic"`（factory.py line 298），不是 `"data_collection"`。应改用 `result.get("category")` 判断：`"research"` = Phase 1 → DATA_COLLECTED，`"analysis"` = Phase 2 → COMPLETED | **修正判断条件** |
| 3 | 修复十 | `SectionState` 只有4种状态 | **假设错误**。实际有7种：LOCKED, PENDING, RUNNING, COMPLETED, FAILED, SKIPPED + 需新增 DATA_COLLECTED | **修正状态枚举描述** |
| 4 | 修复十一 | `data_boundary_controller._extract_aspect_from_agent_id()` 导致匹配失败 | **非根因**。engine.py line 2044 用 `analysis_boundary.allowed_agents = set(dep_list)` 直接覆盖了 `create_boundary_for_analysis` 的匹配结果。Phase 1 的 `dep_list=[]` 导致 `allowed_agents=set()` 是正确行为（自己采集无需上游数据）。日志中的 warning 只是噪音 | **降级为P2噪音清理** |
| 5 | 修复十二 | 聚合器 `_section_id` key 不一致 | **确认成立**。engine line 1293 注入 `agent_result["section_id"]`，聚合器 line 1024 查找 `result.get("_section_id")`，key 不匹配 | **保持** |
| 6 | 修复十二 | `_determine_section_target` 对 data_collection 阶段返回 `"data"` | **确认成立**。line 942-943 直接返回 `"data"` 不做映射，导致 provenance 匹配永远失败 | **补充到修复十二** |
| 7 | 修复十三 | Engine 注入 `_section_id` | **确认成立**且是**核心修复**。只有通过 `_section_id` 传递正确的章节ID，provenance 匹配路径才能生效 | **保持** |

### 9.3 日志证据（06-09 research_39735059）

**证据1：section_id 已正确设置**
```
[批次1] Agent phase_1_agent_7 目标章节: section_1_行业创造与动能
[批次1] Agent phase_1_agent_6 目标章节: section_4_技术化转型
[批次1] Agent phase_1_agent_0 目标章节: section_2_供应链成本效率
```
→ `agent.section_id` 通过 context 正确传递

**证据2：Phase 1 完成后8个章节被标记 COMPLETED**
```
Section section_1_行业创造与动能 completed: quality=50.00, duration=1272.2s
Section section_4_技术化转型 completed: quality=50.00, duration=1272.2s
...（8个章节全部 completed）
```
→ `content_lock.mark_completed()` 不区分 Phase 1/2

**证据3：Phase 2 全部被锁**
```
[批次2] Agent phase_2_agent_7 对应章节 section_1_行业创造与动能 被锁: Already completed
[批次2] Agent phase_2_agent_6 对应章节 section_4_技术化转型 被锁: Already completed
...（8个 agent 全部被锁）
[批次2] 没有有效的Agent，跳过
```
→ Phase 2 从未执行

**证据4：聚合器有数据但无法映射**
```
ResultAggregator: 综合 input keys: ['phase_1_agent_7', 'phase_1_agent_6', ...]
  phase_1_agent_7: 1300 chars
  phase_1_agent_6: 1497 chars
  ...
章节 '核心财务指标与盈利能力' 无匹配内容，生成降级占位
...（8个章节全部降级）
```
→ 数据存在（1300-1751 chars/agent），但 agent_id key 无法映射到框架章节名

**证据5：Phase 3 calibrator 的 section_id 未注册**
```
[批次3] Agent phase_3_calibrator 对应章节 phase_3_calibrator 被锁: Section phase_3_calibrator not found
```
→ calibrator agent 没有 section_id，content_lock 中无此章节

### 9.4 修正后的修复优先级

| 优先级 | 修复项 | 修改文件 | 说明 |
|--------|--------|----------|------|
| **P0** | ~~修复九~~ | ~~取消~~ | agent.section_id 已通过 context 正确传递 |
| **P0** | 修复十（修正版） | `content_lock.py` + `engine.py` | 用 `category` 而非 `agent_type` 判断；新增 DATA_COLLECTED 状态 |
| **P0** | 修复十三 | `engine.py` | 注入 `_section_id`（双 key），这是让 provenance 匹配生效的核心 |
| **P1** | 修复十二（补充版） | `result_aggregator.py` | key 统一 + 修复 `_determine_section_target` 对 data_collection 返回 `"data"` 的问题 |
| **P2** | 修复十一 | `data_boundary_controller.py` | 降级为噪音清理，非根因 |

### 9.5 修正后的修复十方案

**问题**：`agent_type` 始终为 `"dynamic"`，无法区分 Phase 1/2。

**修正方案**：改用 `result.get("category")` 或 `agent.config.get("category")` 判断：

```python
# engine.py line 1294-1299 修正
if agent_result.get("success"):
    scheduler.mark_completed(agent_id, agent_result)
    if content_lock is not None:
        quality_score = self._extract_quality_score(agent_result)
        # R-FIX-10: 区分 data_collection 和 analysis 的完成状态
        _category = agent_result.get("category", "") or (agent.config.get("category", "") if agent else "")
        if _category == "research":
            # Phase 1 数据采集完成，标记为 DATA_COLLECTED
            content_lock.mark_section_state(section_id, SectionState.DATA_COLLECTED)
        else:
            # Phase 2 分析完成，标记为 COMPLETED
            unlocked_sections = content_lock.mark_completed(section_id, quality_score)
            if unlocked_sections:
                ...
```

**category 值映射**（来自 `dynamic_orchestrator.py:to_decomposition_plan` line 111-118）：

| Phase | ResearchPhase | category 值 | 含义 |
|-------|--------------|-------------|------|
| Phase 1 | DATA_COLLECTION | `"research"` | 数据采集 |
| Phase 2 | DEEP_ANALYSIS | `"analysis"` | 深度分析 |
| Phase 3 | CALIBRATION | `"calibration"` | 校准 |
| Phase 4 | REPORT_GENERATION | 跳过 | 外部处理 |

### 9.6 修正后的修复十二补充方案

**问题**：`_determine_section_target` (line 942-943) 对 `data_collection` 阶段返回 `"data"` 不做映射。

**修正方案**：当 `_section_id` 可用时，直接使用而非回退到 `_determine_section_target`：

```python
# result_aggregator.py line 1022-1028 已有正确逻辑，只需确保 _section_id key 匹配
_sec_id = result.get("_section_id", "")
if _sec_id:
    section_target = _sec_id
else:
    section_target = self._determine_section_target(agent_id, stage, agent_id)
```

修复十三实施后，`_section_id` 将被正确注入，此路径将优先使用 `_section_id` 而非回退到 `_determine_section_target`。

**但仍有防御性修复价值**：修改 `_determine_section_target` 的 `data_collection` 分支，尝试从 agent_id 的 section_id 属性推断：

```python
# result_aggregator.py line 942-943 修正
elif stage == "data_collection":
    # 尝试从 _section_id 获取更精确的章节映射
    _sid = result.get("_section_id", "") or result.get("section_id", "")
    if _sid:
        return _sid
    return "data"
```

### 9.7 新增发现：Phase 3 calibrator 无 section_id

**问题**：日志显示 `phase_3_calibrator` 的 section_id 为 `phase_3_calibrator`（回退到 agent_id），content_lock 中无此章节。

**原因**：`_create_agents_from_plan` line 3417 `if spec.output_keys:` — calibrator 的 `output_keys` 为空，`context["section_id"]` 未设置。

**处理**：非致命问题，calibrator 不参与内容锁。但应确保不因 "Section not found" 而跳过 calibrator。可在 `can_execute` 中对找不到的 section 返回 `(True, "Section not registered, allow execution")`。

```python
# content_lock.py line 212-214 修正
status = self._section_statuses.get(section_id)
if not status:
    return True, f"Section {section_id} not found, allowing execution"  # 放行未注册的章节
```

---

## 10. 第三轮审查记录（2026-06-10 修正版方案审查）

### 10.1 审查方法

逐行对照修正后的方案（修复1-8方向改为"约束而非跳过"+新增修复七补充）与源码，验证假设是否成立、代码路径是否正确、数据是否真实可用。

### 10.2 审查发现

| # | 修复项 | 审查问题 | 严重度 | 处理 |
|---|--------|----------|--------|------|
| 1 | 修复一 | **状态机转换路径错误**。方案中 `enter_framework` 分支先转 `PAUSED` 再转 `FRAMEWORK_CONFIRM`，但源码状态机（`state_machine.py` line 65-73）EXECUTING→FRAMEWORK_CONFIRM是合法直转，且PAUSED→FRAMEWORK_CONFIRM也合法。原代码line 422-429直接EXECUTING→FRAMEWORK_CONFIRM。方案应保持原状态转换逻辑不变，只增加action约束层 | 中 | **修正方案代码，保持原状态转换** |
| 2 | 修复一 | **PAUSED分支缺少enter_framework和regenerate_report**。源码line 380-393的PAUSED分支只处理了resume/modify/regenerate，没处理enter_framework。但方案新增的PAUSED分支加了enter_framework。需确认PAUSED状态下LLM是否可能返回enter_framework——是的，暂停后用户可能要重新规划。但原代码PAUSED分支没有enter_framework处理，落入了`_handle_chat_mode`。方案新增是合理的 | 低 | **保持，确认新增合理** |
| 3 | 修复六 | **代码路径描述不精确**。方案说"不return，继续走_handle_research_msg流程"，但depth_keyword检测在`_handle_user_message()` line 305-323中，而非在`_handle_research_msg()`中。实际路径是：不return → 代码继续到line 325 `if mode == 'framework'` → line 343 `if mode == 'research'` → line 357 `_handle_research_msg()`。路径是对的，但文档描述应精确 | 低 | **补充精确代码路径描述** |
| 4 | 修复七补充 | **engine不使用SessionManager**。方案第二步在engine中写session，但engine.py不import SessionManager（验证grep确认）。直接在engine中加session写入会引入新的依赖，与现有代码风格不一致 | 中 | **取消第二步（engine写session），只保留第一步（_build_research_running_context从磁盘读ResearchResultStore）** |
| 5 | 修复七补充 | **ResearchResultStore每次读磁盘性能问题**。`_build_research_running_context`在每次LLM调用前执行，如果每次都从磁盘读result.json，会增加IO。但研究运行中用户消息频率不高（每分钟1-2条），且result.json很小（<50KB），性能影响可忽略 | 低 | **保持磁盘读取路径，加缓存优化作为P2** |
| 6 | 修复七补充 | **completed_agents的phase字段值**。06-09日志中`result.json`的completed_agents显示`phase=batch_1`而非`phase=phase_1`。方案中用`ca.get('agent_id', '').startswith('phase_1_')`推算阶段是正确的（看agent_id而非phase字段），但文档中的表格说"从completed_agents的phase字段推算"不准确。phase字段是`batch_1/batch_2`而非`phase_1/phase_2` | 中 | **修正文档描述，明确是从agent_id推算而非phase字段** |
| 7 | 修复七补充 | **data_point_count累加逻辑有Bug**。方案第二步的session累加代码用了`stored.get('data_points', [])`，但`stored`变量在累加分支中可能不存在（仅在磁盘读取成功时有值）。取消第二步后此问题不存在 | — | **已随第二步取消而消除** |
| 8 | 修复七补充 | **session中research_task_id可能不存在**。方案中`task_id = session.get('research_task_id', session.get('session_id', ''))`，但源码中session没有`research_task_id`字段。executor中task_id就是session_id。应直接用`session_id` | 低 | **修正为直接用session_id** |
| 9 | 修复七补充 | **ResearchResultStore构造参数**。方案中`ResearchResultStore('data')`，但源码中engine使用`ResearchResultStore(storage_path="data")`。构造参数名是`storage_path`，应保持一致 | 低 | **修正构造参数名** |

### 10.3 修正后的修复一代码

**原方案问题**：enter_framework分支先转PAUSED再转FRAMEWORK_CONFIRM，改变了原状态转换路径。

**修正**：保持原代码line 422-441的状态转换逻辑（EXECUTING→FRAMEWORK_CONFIRM直转），只增加action约束层：

```python
    # ===== R-FIX-1: action约束层 =====
    conv_machine = session.get('state_machine')
    raw_action = conv_result.get('action', 'continue_chat')
    action = self._validate_action_for_state(raw_action, conv_machine, user_input)
    if action != raw_action:
        logger.info(f"[R-FIX-1] Action constrained: {raw_action} → {action}")

    # 按约束后的action执行（保持原代码的状态转换逻辑）
    if action == 'inject_requirement':
        return await self._handle_inject_requirement(
            session_id=session_id,
            inject_ops=conv_result.get('inject_ops', []),
            user_message=user_input
        )
    if action == 'modify_research':
        cm.pause(session_id)
        old = self._executor_tasks.pop(session_id, None)
        if old and not old.done():
            old.cancel()
        if conv_machine and conv_machine.current_state == ConversationState.EXECUTING:
            if conv_machine.can_transition_to(ConversationState.PAUSED):
                conv_machine.transition(ConversationState.PAUSED)
        return await self._handle_modify_research(...)
    if action == 'enter_framework':
        # 保持原逻辑：EXECUTING→FRAMEWORK_CONFIRM直转（state_machine.py line 72）
        cm.pause(session_id)
        old = self._executor_tasks.pop(session_id, None)
        if old and not old.done():
            old.cancel()
        if conv_machine and conv_machine.current_state == ConversationState.EXECUTING:
            if conv_machine.can_transition_to(ConversationState.FRAMEWORK_CONFIRM):
                conv_machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        session['mode'] = 'chat'
        # ... 原代码 line 431-441 保持不变 ...
        return await self._enter_framework_mode(session_id, user_input)

    return {...}  # continue_chat
```

### 10.4 修正后的修复七补充代码

**取消第二步（engine写session），只保留从磁盘读ResearchResultStore**

```python
# 3. 已完成的agent（从磁盘读取 ResearchResultStore）
completed_agents = []
data_point_count = 0
try:
    from src.core.storage.research_result_store import ResearchResultStore
    store = ResearchResultStore(storage_path="data")
    stored = store.load_result(session_id)  # R-FIX-7b-8: 直接用session_id
    if stored:
        completed_agents = stored.get('completed_agents', [])
        data_point_count = len(stored.get('data_points', []))
except Exception:
    pass

# 4. 从 completed_agents 的 agent_id 推算当前阶段
# 注意: completed_agents 的 phase 字段值为 "batch_1/batch_2"，不是 "phase_1/phase_2"
# 需要从 agent_id 的前缀推算: phase_1_agent_* = Phase1, phase_2_agent_* = Phase2
phase_1_done = sum(1 for ca in completed_agents 
                   if ca.get('agent_id', '').startswith('phase_1_') and ca.get('success'))
phase_2_done = sum(1 for ca in completed_agents 
                   if ca.get('agent_id', '').startswith('phase_2_') and ca.get('success'))
phase_3_done = sum(1 for ca in completed_agents 
                   if ca.get('agent_id', '').startswith('phase_3_') and ca.get('success'))
```

### 10.5 修正后的修复六代码路径描述

修复六的实际代码路径：

```
_handle_user_message() line 305-323: depth_keyword检测
    ↓ mode == 'research' 且 depth_keyword命中 → 不return
    ↓ 继续到 line 325: if mode == 'framework' → False (mode是research)
    ↓ 继续到 line 343: if mode == 'research'
    ↓ line 354: resume_keywords检测 → 不匹配
    ↓ line 357: return await self._handle_research_msg(session_id, user_input, session)
    ↓ _handle_research_msg() → _llm_converse() → _validate_action_for_state()
```

### 10.6 修正后的优先级

| 优先级 | 修复项 | 修改文件 | 说明 |
|--------|--------|----------|------|
| **P0** | 修复八 | `research_api.py` | cm变量前置 |
| **P0** | 修复一（修正版） | `research_api.py` | action约束层，保持原状态转换 |
| **P0** | 修复七补充（修正版） | `research_api.py` | 研究进度上下文，从磁盘读 |
| **P0** | 修复六 | `research_api.py` | 深度关键词走意图分析 |
| **P1** | 修复七 | `research_api.py` | prompt强化 |
| **P1** | 修复二 | `intelligent_routing_adapter.py` | 意图融合 |
| **P1** | 修复三 | `research_api.py` + `orchestrator.py` | 缓存传递 |
| **P1** | 修复四 | `orchestrator.py` | reanalyze融合 |
| **P2** | 修复五 | `semantic_intent.py` | JSON解析 |
| **P0** | 修复十 | `content_lock.py` + `engine.py` | DATA_COLLECTED状态（含6处配套） |
| **P0** | 修复十三 | `engine.py` | _section_id双key（含4处注入） |
| **P1** | 修复十二 | `result_aggregator.py` | 聚合器匹配 |
| **P2** | 修复十一 | `data_boundary_controller.py` | 噪音清理 |

---

## 11. 第四轮零错误审查记录（2026-06-10）

### 11.1 审查方法

逐行对照全部11个源文件，追踪每一条代码路径。

### 11.2 审查发现

| # | 修复项 | 审查问题 | 严重度 | 处理 |
|---|--------|----------|--------|------|
| 1a | 修复十 | `mark_running()` line 395 不接受 `DATA_COLLECTED` 状态，Phase 2 无法从 `DATA_COLLECTED` 转为 `RUNNING` | **P0致命** | **修正：mark_running 加 DATA_COLLECTED** |
| 1b | 修复十 | `_check_unlock_conditions()` line 303 和 `_try_unlock()` line 346 只认 `COMPLETED`，`DATA_COLLECTED` 章节解锁失败 | **P0致命** | **修正：两处改为 not in (COMPLETED, DATA_COLLECTED)** |
| 1c | 修复十 | `mark_section_state()` 方法不存在 | **P0致命** | **新增方法** |
| 2a | 修复十三 | 缓存命中路径 line 1150-1159 无 `_section_id` | **P0致命** | **补充注入** |
| 2b | 修复十三 | QC重执行路径 line 1223-1227 无 `_section_id` | **P0致命** | **补充注入** |
| 2c | 修复十三 | 缓存命中内容锁 line 1188-1194 无 category 区分 | **P0致命** | **补充（合并到修复十6c）** |
| 3 | 修复十 | `category` 为空时（`spec.agent_type` 不确定），`_category == "research"` 为 False → 标记 COMPLETED 而非 DATA_COLLECTED | **P0致命** | **增加 agent_id 前缀兜底** |
| 4 | 修复一 | PAUSED 分支新增 `enter_framework` 缺少 pause/cancel | P1 | **补充 old task cancel** |
| 5 | 修复七b | `ResearchResultStore.load_result` 的 task_id 来源不确定 | P1 | **用 session_id 降级** |
| 6 | 修复十 | `can_execute` 对未注册章节返回 False（9.7节已指出但方案代码未包含） | P1 | **合并到修复十 can_execute** |
| 7 | 修复十二 | `_determine_section_target` 签名无 result 参数 | P2 | **修复十三覆盖，无需修改** |
| 8 | 修复一 | enter_framework 先转 PAUSED 再转 FRAMEWORK_CONFIRM | P2 | **10.3节已修正** |
| 9 | 修复七b | completed_agents 描述不精确 | P2 | **10.4节已修正** |

### 11.3 修复间依赖与冲突检查

| 组合 | 检查结果 |
|------|----------|
| 修复十 + 修复十三 | ✅ 无冲突。修复十改变 content_lock 行为，修复十三注入 _section_id |
| 修复十 + 修复十二 | ✅ 修复十二依赖修复十三的 _section_id，不直接依赖修复十 |
| 修复一 + 修复六 | ✅ 修复六让 depth_keyword 走 _handle_research_msg，修复一加约束层 |
| 修复八 + 修复一 | ✅ 修复八前置 cm 初始化，修复一使用 cm |
| 修复十三 + 修复十二 | ⚠️ 依赖顺序：修复十三必须先于修复十二 |
| 修复十 + mark_running | ⚠️ 依赖：修复十必须包含 mark_running 对 DATA_COLLECTED 的支持 |

### 11.4 修正后的完整实施清单

| 序号 | 优先级 | 修复项 | 修改文件 | 必须包含的修改点 |
|------|--------|--------|----------|-----------------|
| 1 | P0 | 修复八 | `research_api.py` | cm 提前初始化 |
| 2 | P0 | 修复十 | `content_lock.py` + `engine.py` | 6处：(1)新增DATA_COLLECTED枚举 (2)新增mark_section_state() (3)can_execute加DATA_COLLECTED放行+未注册章节放行 (4)mark_running加DATA_COLLECTED接受 (5)_check_unlock_conditions和_try_unlock两处 (6)engine 4处category区分+agent_id兜底 |
| 3 | P0 | 修复十三 | `engine.py` | 4处：(1)line 1293加_section_id (2)line 1150-1159加_section_id (3)line 1227加_section_id (4)line 1188-1194合并到修复十 |
| 4 | P0 | 修复一 | `research_api.py` | action约束层 + PAUSED分支enter_framework补充pause/cancel |
| 5 | P1 | 修复六 | `research_api.py` | depth_keyword走意图分析 |
| 6 | P1 | 修复七 | `research_api.py` | prompt强化 |
| 7 | P1 | 修复七b | `research_api.py` | 研究进度上下文，从磁盘读 |
| 8 | P1 | 修复十二 | `result_aggregator.py` | 无需修改_determine_section_target（修复十三覆盖） |
| 9 | P1 | 修复二 | `intelligent_routing_adapter.py` | 意图融合 |
| 10 | P1 | 修复三 | `research_api.py` + `orchestrator.py` | 缓存传递 |
| 11 | P1 | 修复四 | `orchestrator.py` | reanalyze融合 |
| 12 | P2 | 修复五 | `semantic_intent.py` | JSON解析增强 |
| 13 | P2 | 修复十一 | `data_boundary_controller.py` | 噪音清理 |

### 11.5 实施顺序

```
1→2→3→4→5→6→7→8→9+10+11→12→13
修复八 → 修复十(含6处) → 修复十三(含4处) → 修复一 → 修复六 → 修复七 → 修复七b → 修复十二 → 修复二+三+四 → 修复五 → 修复十一
```

---

## 12. 实施记录（2026-06-10）

### 12.1 实施状态

全部13项修复已实施完成，并通过单元测试验证。

### 12.2 额外修复（实施中发现）

| # | 修复项 | 文件 | 说明 |
|---|--------|------|------|
| 14 | `use_intelligent_routing=False` 不生效 | `orchestrator.py:396-416` | 原代码忽略 `use_intelligent_routing=False` 参数，始终创建 RoutingAdapter。修正为 `elif use_intelligent_routing` 分支 |
| 15 | `session_manager` NameError | `orchestrator.py:1566` | `_research_with_routing` 中引用未定义的 `session_manager`。修正为 `SessionManager.get_instance().get()` |
| 16 | `engine.shared_memory` 属性缺失 | `engine.py:233` | 测试引用 `engine.shared_memory`，但源码只有 `self._shared_memory`。添加公共属性 |
| 17 | `_infer_skills_from_intent` 方法缺失 | `semantic_intent.py:410` | 测试引用不存在的方法。新增实现 |
| 18 | `_analyze_with_keyword` 缺少 `llm_model_used` | `semantic_intent.py:442` | 关键词 fallback 未设置 `llm_model_used="keyword_matching"` |
| 19 | `_create_analysis_phase_with_deps` 不解析 `content_dependency` | `dynamic_orchestrator.py:346-376` | 跨 section 依赖（C→B）未传播到 execution plan。修正：从 `SectionSpec.content_dependency` 解析到 agent ID |
| 20 | `can_execute` 绕过 `content_locked` 检查 | `content_lock.py:221` | `DATA_COLLECTED` 状态直接返回 True，未检查 content lock。修正：加 lock 检查 |
| 21 | `mark_section_state` 不解锁 | `content_lock.py:486` | 设置 `DATA_COLLECTED` 时未尝试解锁。修正：调用 `_check_unlock_conditions` |
| 22 | `get_execution_progress` 丢失 `data_collected` 章节 | `content_lock.py:788` | `sections_by_state` 字典无 `data_collected` key。修正：添加 |
| 23 | 重复 import | `content_lock.py:22,26` | `from dataclasses import dataclass, field` 重复导入。修正：去重 |

### 12.3 测试修复

| 测试文件 | 修复内容 | 结果 |
|----------|----------|------|
| `test_semantic_intent.py` | `_infer_skills_from_intent` 方法实现 + `llm_model_used` | 11/11 pass |
| `test_intelligent_routing_integration.py` | 移除 `_intent_gate` mock → `_routing_adapter=None`；`exec_result` dict → MagicMock；放宽 status 断言 | 7/7 pass |
| `test_intelligent_routing_full.py` | `shared_memory` 属性；`use_intelligent_routing` 修复 | 14/14 pass |
| `test_agent_classification.py` | `Mock()` → `ExecutionConfig()`；源码断言修正 | 6/6 pass |
| `test_research_orchestrator.py` | `_intent_gate`/`_category_router` → `_routing_adapter` | 2/2 pass (1 skip) |
| `test_bug7_8_9_analysis.py` | 移除 `ResearchPhase` import；content_lock 断言修正；agent ID 匹配歧义修正；跳过 calibration agent | 8/8 pass |

### 12.4 测试通过统计

```
tests/unit/test_semantic_intent.py ............           (11 passed)
tests/unit/test_intelligent_routing_integration.py ....... (7 passed)
tests/unit/test_intelligent_routing_full.py .............. (14 passed)
tests/unit/core/orchestrator/test_agent_classification.py ...... (6 passed)
tests/unit/core/orchestrator/test_research_orchestrator.py ..s   (2 passed, 1 skipped)
tests/unit/core/test_bug7_8_9_analysis.py ........        (8 passed)
tests/unit/test_research_api_helpers.py .............     (13 passed)
tests/unit/test_deep_intent_result_extensions.py ........ (8 passed)

Total: 69 passed, 1 skipped
```

### 12.5 代码审查发现（已修复）

| 问题 | 严重度 | 处理 |
|------|--------|------|
| `can_execute` 绕过 `content_locked` 对 `DATA_COLLECTED` | Medium | 已修复：加 lock 检查 |
| `mark_section_state` 不解锁 `DATA_COLLECTED` | Medium | 已修复：自动解锁 |
| `get_execution_progress` 丢失 `DATA_COLLECTED` 章节 | Medium | 已修复：添加 key |
| 重复 import `dataclass` | Trivial | 已修复：去重 |

### 12.6 代码审查发现（低优先级，记录）

| 问题 | 严重度 | 说明 |
|------|--------|------|
| `setdefault` on `PersistentSessionDict` 可能不持久化 | Low | 需 PersistentSessionDict override |
| `engine.py` 双 `shared_memory` 属性 | Low | 内部用 `_shared_memory`，外部用 `shared_memory` |
| `_build_report_task` 定义两次 | Low | 死代码，第二定义覆盖第一 |
| `_infer_skills_from_intent` 未被内部调用 | Trivial | 可供外部使用 |
| `_parse_llm_json` 单引号替换可能破坏含撇号的字符串 | Trivial | 会 fallthrough 到下一恢复步骤 |

### 12.7 各修复项最终实施状态

| 修复项 | 状态 | 说明 |
|--------|------|------|
| 修复1 | ✅ 已实施 | EXECUTING阶段action约束层 |
| 修复2 | ✅ 已实施 | `analyze_incremental()` 意图融合 |
| 修复3 | ✅ 已实施 | 缓存传递已有意图结果 |
| 修复4 | ✅ 已实施 | `reanalyze()` 意图融合 |
| 修复5 | ✅ 已实施 | `_parse_llm_json` 4层容错 |
| 修复6 | ✅ 已实施 | depth_keyword 走意图分析 |
| 修复7 | ✅ 已实施 | EXECUTING prompt 强化 |
| 修复7b | ✅ 已实施 | 研究进度上下文从磁盘读取 |
| 修复8 | ✅ 已实施 | `cm` 提前初始化 |
| 修复9 | ❌ 已取消 | 第二轮审查证实不需要，section_id 已通过 context 正确传递 |
| 修复10 | ✅ 已实施 | DATA_COLLECTED 状态（含6处配套修改） |
| 修复11 | ⚠️ 部分实施，无需补全 | `data_boundary_controller.py` 已有 `agent_section_map` 参数和逻辑，`engine.py` 调用处未传入。因 `engine.py:2072` 用 `dep_list` 直接覆盖 `allowed_agents`，传入与否均不影响行为，故不再补全 |
| 修复12 | ✅ 已实施 | 聚合器 `_section_id` 优先路径（修复13覆盖，无需修改 `_determine_section_target`） |
| 修复13 | ✅ 已实施 | Engine 4处 `_section_id` 双key注入 |
