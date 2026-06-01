# 意图分析层 — 最终实现文档

**实施日期：** 2026-05-18
**设计原则：** 信任 LLM。系统只做三件事：传递 LLM 的决策、管理 session 模式、约束专业边界。

---

## 架构决策

放弃 V3 方案的 `need_clarity` + 信息衰减 + 动态权重等复杂算分体系，采用**信任 LLM** 的精简化方案。LLM 的 128K 上下文完全能自主处理意图理解、需求澄清、框架设计。

---

## 修改清单

### Mod 1: 删除 Readiness 仲裁和 `_force_transition_at`

**文件：** `src/api/research_api.py`
**内容：**
- 删除 `suggest_next` 调用链（行 649-674）→ 替换为 `_resolve_transition` 纯函数
- 删除 `_force_transition_at` 所有 6 处引用
- `_resolve_transition` 仲裁规则：
  | action | 结果 |
  |---|---|
  | `enter_framework` | → FRAMEWORK_CONFIRM（LLM 无条件优先） |
  | `modify_research` | → PAUSED |
  | `continue_chat` | → None（信任 LLM，不转换） |
  | `inject_requirement` | → None（在线注入，不转换） |
  | `""`（无 action） | → None（保持当前状态） |

### Mod 2: 删除 `_should_deep_analyze` 门卫

**文件：** `src/api/research_api.py`
**内容：**
- 删除 `_should_deep_analyze` 方法（22 行规则）
- 替换为 `len(user_input.strip()) >= 5` 轻量过滤（仅防无意义输入）

### Mod 3: 话题漂移重置

**文件：** `src/core/dialogue/dialogue_intent_state.py` + `src/api/research_api.py`
**内容：**
- 新增 `reset_for_new_topic(self, new_topic)` 方法
  - 重置：topic_hint, confirmed_aspects, pending_questions, hidden_requirements, domain_context, readiness, framework_aspects, user_aspects 等
  - **不重置：** `research_turns`（全局轮次计数器）
- 调用时机：`_handle_chat_mode` 中 topic 变更检测块（`if old_topic and old_topic != new_topic:`）

### Mod 4: 异步路径轮次更新

**文件：** `src/api/research_api.py`
**内容：**
- 新增 `_update_intent_state_after_async(self, session)` 方法
  - 直接在 session dict 中递增 `research_turns`
  - 不序列化还原 `DialogueIntentState` 对象，避免竞态
- 调用时机：`_do_execute_tool_background` 中 `session["research_context"] = ctx` 之后

### Mod 5: LLM Prompt 专业边界约束

**文件：** `src/api/research_api.py`
**内容：**
- 新增 `domain_guard` 变量（在 `user_prompt` f-string 之前定义）
- 插入到 `{tools_section}` 和 `## LANGUAGE RULE` 之间
- 约束领域：Industry Research, Survey Research, Market Analysis, Data Analysis, Policy Research, Report Revision
- 禁止领域：programming, medical, legal, creative writing → 必须用 `continue_chat`

### Mod 6: `enter_framework` Readiness 保底

**文件：** `src/core/dialogue/dialogue_intent_state.py`
**内容：**
- 修改 `update_from_response` 中 readiness 更新逻辑
- `enter_framework` 时：先 `update_readiness()`，若有 `topic_hint` 则保底 0.7 SUFFICIENT
- 非 `enter_framework` 时：正常 `update_readiness()`

### Mod 7: `inject_requirement` 执行中需求注入

**文件：** `src/api/research_api.py` + `src/api/research_executor.py` + `src/core/orchestrator/smart_clarifier.py`

**7.1-7.6 注入端（research_api.py）：**
- `_handle_inject_requirement` — 入口方法，fallback 到 `_handle_modify_research`（无框架时）
- `_inject_add_section` — 追加章节到 framework.sections + 写入 `_pending_section_injects`
- `_inject_cancel_section` — 从 framework.sections 移除 + 写入 `_pending_section_injects`
  - 注：`_executor_tasks` 以 session_id 为键，无法单独取消 agent
- `_get_section_status` — 从 `research_result_cache.json` 读取章节完成状态
  - 注：`PersistentSessionDict` 的 session_id 存在私有属性 `_session_id`，非 dict key
- `_inject_merge_to_section` — 写入 `section_requirements` + `_pending_section_injects`
  - pending 状态 → `merge_requirement` op
  - completed 状态 → `revise` op

**7.7 消费端（research_executor.py）：**
- `_process_pending_injects` — 3 轮循环消费 `_pending_section_injects`
  - cancel-only → 不调用 orchestrator（已在 inject 方法中完成 sections 更新）
  - add/merge → 调用 `analyze_incremental` + 重新执行 orchestrator（含 `skip_phases`）
  - revise → 调用 `RevisionService.revise_from_user_feedback`
- 防重入：`_inject_in_progress` 标志
- 调用时机：`execute()` 中 `session["status"]="completed"` 之后、state transition 之前

**7.8 `_build_research_running_context` 重写：**
- 原代码检查 `research_result.status=="running"` 始终为 False（死代码）
- 新代码检查 `research_context` 是否存在 + 是否已完成
- 增加 `_pending_section_injects` 队列提示 + 四种 action 说明

**7.9 `section_requirements` 数据流：**
- `ResearchRequirement` 新增 `section_requirements` 字段（data-flow ready）
- `_parse_requirement` 透传到 `ResearchRequirement`
- 注：消费端（ExecutionEngine → agent）未实现，留待后续

**7.10 `inject_ops` 透传：**
- `_llm_converse` 同步路径 + 异步路径的 return dict 均新增 `"inject_ops"` 字段

### Mod 8: EXECUTING 状态合法转换

**文件：** `src/core/dialogue/state_machine.py`
**内容：**
- EXECUTING 的 VALID_TRANSITIONS 新增 `CLARIFYING` + `FRAMEWORK_CONFIRM`

### Mod 9: Research 模式状态机同步 + P5 修复

**文件：** `src/api/research_api.py`

**9.1 `_handle_user_message` research 分支：**
- 新增 `conv_machine = session.get("state_machine")`
- `inject_requirement` dispatch（新增）
- `modify_research` dispatch：`session["paused"] = True` → state transition → 调用 handler
- `enter_framework` dispatch：`session["paused"] = True` → state transition → 原有逻辑

**9.2 `_handle_modify_research`：**
- 保留原有的 `_cancel_existing_task`（仅取消后台工具任务）
- executor task 的取消由 `_monitor` 通过 `session["paused"]` 检测触发（≤5s）

---

## 竞态条件说明

### `paused=True` + CancelledError handler

`_cancel_executor_task` 不直接调用 `task.cancel()`，而是设置 `session["paused"] = True`。原因是 `task.cancel()` 触发 `CancelledError` handler（`research_executor.py:334-341`），该 handler 无条件写 `mode="chat"`，与 `enter_framework` 需要的 `mode="framework"` 冲突。

采用 `paused=True` 方式与原始代码 `_handle_modify_research` 路径一致，不引入新竞态。`_monitor`（轮询间隔 5s）检测到暂停后取消 executor task。此竞态在原始代码中已存在。

---

## 未修改的部分

| 组件 | 文件 | 原因 |
|------|------|------|
| `_action_aligns_with_state` | `research_api.py` | 保留调试 |
| `_sync_mode_with_state` | `research_api.py` | 状态→模式映射 |
| `_save_dialogue_state` | `research_api.py` | 序列化对话状态 |
| `_sync_state_machine_to_framework` | `research_api.py` | 框架模式同步 |
| `suggest_next` | `state_machine.py` | 保留不删（兼容性） |
| `update_readiness` | `dialogue_intent_state.py` | 保留（用于 to_context_string 展示） |
| `merge_from_analysis` | `dialogue_intent_state.py` | 保留连接词兜底 |
| `_handle_modify_research` | `research_api.py` | 保留，与 inject_requirement 互补 |
| `_enter_framework_mode` | `research_api.py` | 保留 |

---

## 文件修改总表

| 文件 | 新增方法 | 修改 | 删除 |
|------|---------|------|------|
| `state_machine.py` | — | VALID_TRANSITIONS EXECUTING | — |
| `dialogue_intent_state.py` | `reset_for_new_topic` | `update_from_response` readiness 逻辑 | — |
| `smart_clarifier.py` | — | `ResearchRequirement.section_requirements` | — |
| `orchestrator.py` | — | `_parse_requirement` 返回参数 | — |
| `research_executor.py` | `_process_pending_injects` | `__init__` 加 `_inject_in_progress`；`execute()` 加调用点 | — |
| `research_api.py` | `_resolve_transition`, `_update_intent_state_after_async`, `_handle_inject_requirement`, `_inject_add_section`, `_inject_cancel_section`, `_get_section_status`, `_inject_merge_to_section` | 649-674 替换；`_build_research_running_context` 重写；`domain_guard` 插入；`inject_ops` 透传；行 414/1600 删除 | `_should_deep_analyze`；`_force_transition_at` |
