# 报告修订质检系统 — 深度审查报告

> 日期: 2026-06-02
> 范围: 报告完成后质检展示→用户交互→内容修订→预览刷新→确认交付 全链路
> 方法: 逐模块代码审查 + 跨模块链路追踪 + 边界场景推演

---

## 一、系统架构概览

```
用户发起修订指令
       │
       ▼
  ChatPanel (pendingInput预填)
       │
       ▼
  POST /api/v1/research/interact
       │
       ▼
  ResearchAPI._llm_converse() → 识别修订意图
       │
       ▼
  ResearchAPI._handle_v2_revision()
       │  ├─ 创建快照 (QualitySnapshotManager)
       │  ├─ 推入版本栈
       │  ├─ 标记 issue 为 revising
       │  └─ RevisionExecutor.execute() → 执行修订
       │
       ▼
  _post_revision_recheck()
       │  ├─ 重检受影响章节 (QualityCheckAgent)
       │  ├─ 合并新旧 issue (merge_issues_on_recheck)
       │  ├─ 推送 SSE (quality_result / section_quality / preview_refresh)
       │  └─ 预览自检 (check_preview_health)
       │
       ▼
  前端接收 SSE → 更新 QualityPanel / DocumentPreview / RevisionHintBar
       │
       ▼
  用户确认交付 → quality_confirm → 生成最终文档
```

---

## 二、逐模块审查发现

### 2.1 修订执行层

#### 2.1.1 `src/core/adjustment/revision_executor.py`

**功能**: 修订任务执行器，根据 `RevisionType` 调用不同执行策略。

**发现的问题**:

| # | 严重度 | 问题 | 位置 | 说明 |
|---|--------|------|------|------|
| E-1 | 🔴 严重 | 修订失败无 issue 状态回退 | execute() 方法 | 修订执行抛异常时，`_handle_v2_revision` 中 issue 已标记为 `revising`，但异常路径没有将其回退为 `open`。用户看到 issue 永远卡在 revising 状态 |
| E-2 | 🟡 中 | 并发修订无防重入保护 | execute() | `_pending_section_injects` 队列仅防止同一章节并发注入，但不阻止用户对同一 issue 发起两次修订请求。第二次请求会再标记 `revising`，revision_count 重复递增 |
| E-3 | 🟡 中 | 修订结果未校验 section 完整性 | execute() 后 | 修订完成后未检查返回的 sections 数据是否结构完整（如缺少 `name`/`content` 字段），可能导致下游渲染崩溃 |

#### 2.1.2 `src/core/adjustment/report_adapter.py`

**功能**: 报告适配器，操作 session 中的 sections 数据。

**发现的问题**:

| # | 严重度 | 问题 | 位置 | 说明 |
|---|--------|------|------|------|
| A-1 | 🟡 中 | 删除章节后 section_scores 未清理 | update_section/delete_section | 删除一个 section 后，`quality_state.section_scores` 中对应的条目仍残留，导致 QualityPanel 显示已删除章节的评分 |
| A-2 | 🟢 低 | 新增章节后无初始评分 | add_section | 用户新增章节后，`section_scores` 中无对应条目，质检面板不显示新章节。需用户手动 recheck 才能出现 |

#### 2.1.3 `src/core/adjustment/report_lock_manager.py`

**功能**: 报告操作锁管理。

**发现的问题**: 无显著问题。基于 `asyncio.Lock` 的实现正确，与 `_session_locks` 模式一致。

#### 2.1.4 `src/core/adjustment/revision_types.py`

**功能**: 修订类型定义。

**发现的问题**: 无显著问题。`RevisionType` 枚举覆盖了 add/modify/delete/reorder/restructure 五种类型。

---

### 2.2 质检闭环层

#### 2.2.1 `src/agents/fixed_agents/quality_check_agent.py`

**功能**: 分章节质检 Agent。

**发现的问题**:

| # | 严重度 | 问题 | 位置 | 说明 |
|---|--------|------|------|------|
| Q-1 | 🟡 中 | `check_by_sections` 对空章节返回 `status: "empty"` 但 `score: 0` | ~L885 | 空章节 score=0 + status="empty"，但在 `_recheck_quality` 中 score=0 会拉低 overall_score，且 "empty" 章节不应参与均分计算 |
| Q-2 | 🟡 中 | 重检后 issue 的 `revision_count` 被覆盖 | `_recheck_quality` 中 | `merge_issues_on_recheck` 合并时，如果新检查结果中 issue 被重新生成（id 相同），其 `revision_count` 字段会丢失（新结果不含此字段，默认为 0） |
| Q-3 | 🟢 低 | `overall_issues` 与 `section_issues` 可能重复 | check_by_sections | 全局问题列表和章节问题列表可能包含相似问题，用户在面板中看到重复 |

#### 2.2.2 `src/core/quality/quality_state.py`

**功能**: 质检状态模型。

**发现的问题**: 无显著问题。`SectionScore.status` 已包含 "empty"，`QualityIssue` 已有 `revision_count` 和 `accepted` 状态，`QUALITY_PASS_THRESHOLD` 常量已定义。

#### 2.2.3 `src/core/quality/quality_snapshot_manager.py`

**功能**: 版本快照创建与恢复。

**发现的问题**:

| # | 严重度 | 问题 | 位置 | 说明 |
|---|--------|------|------|------|
| S-1 | 🟡 中 | 快照 HTML 文件不随版本独立保存 | create_snapshot | 快照记录了 `html_path`，但实际 HTML 文件是覆盖写入的（`PreviewStorage.path(session_id)` 只有一个路径）。回滚时 `html_src` 可能已被后续修订覆盖，指向的已不是快照时的版本 |
| S-2 | 🟢 低 | 快照无过期清理机制 | 无 cleanup 调用点 | 设计文档提到 `cleanup_old(keep=10)`，但无自动调用点。长期使用后快照目录可能膨胀 |

#### 2.2.4 `src/core/quality/preview_health.py`

**功能**: 预览 HTML 健康检查。

**发现的问题**: 无显著问题。`check_preview_health` 的膨胀检测和基础检查逻辑完整。

---

### 2.3 API 层

#### 2.3.1 `src/api/research_api.py` — 修订流程

**功能**: 修订入口 `_handle_v2_revision`，修订确认 `_confirm_v2_revision`。

**发现的问题**:

| # | 严重度 | 问题 | 位置 | 说明 |
|---|--------|------|------|------|
| R-1 | 🔴 严重 | 修订失败时 issue 状态不回退 | _handle_v2_revision | 修订前将 issue 标记为 `revising`（~L2358），但修订失败（ABORTED/exception）的路径中，issue 仍为 `revising` 状态，永远不会变回 `open`。用户无法再次发起修订，也无法 dismiss |
| R-2 | 🔴 严重 | 版本栈快照的 `quality_state_snapshot` 循环嵌套 | ~L2354 | 版本栈条目中 `quality_state_snapshot` 包含上一版本的 `version_stack`，而 `version_stack` 中又包含更早版本的 `quality_state_snapshot`，形成递归嵌套。随修订次数增加，数据量指数膨胀，最终导致序列化超时或内存溢出 |
| R-3 | 🟡 中 | `_confirm_v2_revision` 的 reject 路径无质量联动 | ~L2495 | 用户拒绝修订（reject）后，issue 从 `revising` 变回 `open`，但未推送 `quality_result` SSE，前端不知道状态变化 |
| R-4 | 🟡 中 | 修订取消后 `_pending_section_injects` 残留 | cancel 路径 | 用户取消修订时，`_pending_section_injects` 中该任务可能未清理，导致下次修订时误注入 |
| R-5 | 🟢 低 | `_handle_v2_revision` 中 `modified_sections` 提取依赖 `conv_result["aspects"]` | ~L2395 | `aspects` 字段是否由 LLM 稳定返回取决于 prompt 质量。若 LLM 未返回 `aspects`，fallback 从 flow tasks 提取，但 flow 可能也未赋值 `section_name` |

#### 2.3.2 `src/api/research_api.py` — 质检 Handler

**功能**: 5 个质检操作 handler + `_recheck_quality` + `_post_revision_recheck`。

**发现的问题**:

| # | 严重度 | 问题 | 位置 | 说明 |
|---|--------|------|------|------|
| H-1 | 🟡 中 | `_handle_quality_rollback` 回滚不恢复 sections 数据 | ~L2890 | 回滚恢复 HTML 和 `quality_state`，但 sections 数据的恢复依赖快照中的 `sections` JSON 文件。如果该文件不存在（快照创建时未保存 sections），则 sections 不恢复，导致用户继续修订时操作的是新版本的 sections，但看到的是旧版本的 HTML |
| H-2 | 🟡 中 | `_handle_quality_dismiss` 无 SSE 推送 | 已在之前 bug 修复中添加 | 确认当前代码已包含 `push_quality_result`，此项已修复 |
| H-3 | 🟡 中 | `_recheck_quality` 中 `merge_issues_on_recheck` 丢失 `revision_count` | ~L2990 | 合并时新 issue 的 `revision_count` 默认为 0，覆盖了旧 issue 已递增的值。详见 Q-2 |
| H-4 | 🟢 低 | `_handle_quality_confirm` 的 `accepted` 状态标记不区分 dismiss | ~L2950 | `open`/`dismissed`/`max_retries_reached` 都标记为 `accepted`，但用户可能想知道哪些是主动接受、哪些是被忽略的 |

---

### 2.4 SSE 与前端交互层

#### 2.4.1 `src/core/session_streamer.py`

**功能**: SSE 事件推送。

**发现的问题**:

| # | 严重度 | 问题 | 位置 | 说明 |
|---|--------|------|------|------|
| SSE-1 | 🟡 中 | `push_section_quality` 事件数据用 `data` 包裹 | push_section_quality | 后端推送 `{section_name, data: {score, status, issues}}`，但前端 `SectionQualityEventData` 定义为 `{section_name, data}`。需确认前端解包路径一致 |
| SSE-2 | 🟢 低 | `_persist_event` 无容量限制 | _persist_event | 断线重连恢复事件时，如果事件积累过多，重放可能耗时过长 |

#### 2.4.2 `web/src/lib/sse.ts`

**功能**: SSE 连接管理，共享连接 + 引用计数。

**发现的问题**:

| # | 严重度 | 问题 | 位置 | 说明 |
|---|--------|------|------|------|
| FE-1 | 🟡 中 | `subscribeSession` 返回的 unsubscribe 函数闭包引用可能过期 | unsubscribe 闭包 | 如果在同一 session 上多次 subscribe/unsubscribe，闭包中捕获的回调引用可能已被其他 unsubscribe 删除 |
| FE-2 | 🟢 低 | 连接断开后无自动重连 | EventSource onerror | EventSource 自带重连机制，但 `sessionConnections` Map 中的旧实例未清理，重连后可能存在两个 EventSource 实例 |

#### 2.4.3 前端组件

| # | 严重度 | 问题 | 组件 | 说明 |
|---|--------|------|------|------|
| FE-3 | 🟡 中 | QualityPanel 中"发起修订"只预填文本，未标记 issue 状态 | QualityPanel | 用户点击"发起修订"后，仅将文本填入 ChatInput，但对应 issue 在后端仍为 `open`。如果用户修改了输入内容再发送，后端 `_handle_v2_revision` 可能无法识别该 issue 并标记为 `revising` |
| FE-4 | 🟡 中 | DocumentPreview 中 SectionNavBar 的 warning 高亮依赖 `section_scores`，但 section name 可能不匹配 | SectionNavBar | 后端 `section_scores` 的 key 是章节名（如"市场分析"），但 `SectionNavBar` 从 HTML 中提取的 section 列表可能用 `section.id`（如"market-analysis"），名称映射不一致时高亮失效 |
| FE-5 | 🟢 低 | RevisionHintBar 5秒自动消失可能过快 | RevisionHintBar | 用户正在阅读提示内容时，5秒后自动消失可能打断阅读。建议改为用户交互后才开始计时 |

---

### 2.5 内容生成与预览层

#### 2.5.1 `src/content/content_orchestrator.py`

**功能**: 内容编排，HTML 生成。

**发现的问题**:

| # | 严重度 | 问题 | 位置 | 说明 |
|---|--------|------|------|------|
| C-1 | 🟡 中 | 修订后重新生成 HTML 时，section 顺序可能与 sections 列表不一致 | render 方法 | 如果修订过程中 `sections` 列表的顺序发生变化（如 reorder 类修订），但 HTML 模板中的 section 遍历顺序未同步更新，导致预览与数据不一致 |
| C-2 | 🟢 低 | HTML 中的 `<section id>` 使用 `section.id`，但质检结果使用 `section.name` | L734 | 锚点 ID 和质检评分的 key 使用不同的标识符，需要在多个地方做映射 |

---

## 三、端到端场景分析

### 3.1 基本修订流程 ✅

> 用户看到质检问题 → 点击发起修订 → 输入框预填 → 发送 → 修订执行 → 重检 → 预览刷新

**评估**: 基本流程可正常运行。SSE 事件链路完整，前端状态同步基本可靠。

### 3.2 复杂修订场景

#### 3.2.1 多章节同时修订 ⚠️

> 用户要求"同时修订市场分析和竞争格局两个章节"

**风险点**:
- `_handle_v2_revision` 中 `modified_sections` 提取依赖 `conv_result["aspects"]`（R-5），LLM 可能只返回一个 aspect
- 两个章节的 issue 各自标记 `revising`，但如果其中一个修订失败，另一个成功，issue 状态不一致（R-1）
- 版本栈只创建一个快照，回滚时两个章节同时回滚，无法单独回滚

**建议**: 需要增加修订事务性保障——要么全部成功，要么全部回滚。

#### 3.2.2 删除章节后修订 ⚠️

> 用户要求"删除行业概述章节"

**风险点**:
- 删除后 `section_scores` 中残留旧条目（A-1），QualityPanel 显示已删除章节
- 后续 recheck 时，`check_by_sections` 对已删除章节无数据，但不清理旧评分
- 版本回滚后，HTML 恢复但 sections 数据可能未恢复（H-1）

#### 3.2.3 新增章节后修订 ⚠️

> 用户要求"新增一个技术分析章节"

**风险点**:
- 新增章节无初始评分（A-2），QualityPanel 不显示
- 新增章节的 `section.id` 可能与已有章节冲突
- 如果新增章节后立即 recheck，新章节可能未被 HTML 渲染（因为 HTML 生成和 recheck 是异步的）

#### 3.2.4 多次修订同一 issue 🔴

> 同一个 issue 经历 3 次修订仍未解决

**风险点**:
- 版本栈快照的 `quality_state_snapshot` 递归嵌套（R-2），3 次修订后嵌套 3 层，10 次后数据量可能膨胀到 MB 级
- `revision_count` 在重检时被覆盖为 0（Q-2/H-3），导致修订次数限制失效
- `max_retries_reached` 标记后用户仍可点击"发起修订"，前端未禁用按钮

#### 3.2.5 修订失败后重试 🔴

> 修订执行过程中 LLM 返回异常或修订服务超时

**风险点**:
- issue 卡在 `revising` 状态（R-1），用户无法再次发起修订，也无法 dismiss
- 前端无"修订失败"的错误提示，RevisionHintBar 不显示
- 用户只能刷新页面或 rollback 到上一版本

#### 3.2.6 并发操作冲突 🟡

> 用户在质检面板点击 dismiss 的同时，修订任务正在完成并推送重检

**风险点**:
- `_post_revision_recheck` 内部已加锁，但 dismiss/reopen 操作和重检操作修改的是同一个 `quality_state` 对象
- 重检会覆盖 dismiss 的结果（因为 `_recheck_quality` 中 `merge_issues_on_recheck` 以新结果为准）
- 锁保证了串行执行，但语义上 dismiss 的意图可能被重检结果覆盖

### 3.3 定稿流程

#### 3.3.1 确认交付 ⚠️

> 用户点击"确认交付"但仍有 open issues

**风险点**:
- 后端返回 `pending_issues`，前端展示二次确认对话框
- 用户选择"仍要交付"后，所有 open/dismissed/max_retries_reached issue 标记为 `accepted`
- 但 `accepted` issue 的 `revision_count` 信息丢失，无法审计后续

#### 3.3.2 生成最终文档 ✅

> 确认后生成 DOCX/PPTX/PDF

**评估**: 此部分不在当前审查范围，但确认交付的状态转换（`phase: "confirmed"`）已正确实现。

---

## 四、问题汇总与优先级

### 🔴 严重（必须修复，影响核心流程）

| # | 模块 | 问题 | 影响 |
|---|------|------|------|
| R-1 | research_api | 修订失败 issue 状态不回退 | issue 永久卡在 revising，用户无法操作 |
| R-2 | research_api | 版本栈 quality_state_snapshot 递归嵌套 | 多次修订后数据膨胀，可能导致序列化失败 |
| E-1 | revision_executor | 修订异常无 issue 回退 | 同 R-1，异常路径未处理 |

### 🟡 中等（应修复，影响体验或边界场景）

| # | 模块 | 问题 | 影响 |
|---|------|------|------|
| Q-2/H-3 | quality_check/research_api | merge_issues_on_recheck 丢失 revision_count | 修订次数限制失效 |
| A-1 | report_adapter | 删除章节后 section_scores 残留 | 面板显示已删除章节 |
| H-1 | research_api | rollback 不恢复 sections 数据 | 回滚后数据不一致 |
| R-3 | research_api | reject 路径无 SSE 推送 | 前端不知道 issue 状态变化 |
| FE-3 | QualityPanel | 发起修订未标记 issue | 后端可能无法关联 issue |
| Q-1 | quality_check_agent | empty 章节参与均分 | 整体评分被空章节拉低 |
| E-2 | revision_executor | 并发修订无防重入 | revision_count 重复递增 |
| FE-4 | SectionNavBar | section name/id 映射不一致 | warning 高亮失效 |

### 🟢 低（可优化，不影响核心功能）

| # | 模块 | 问题 | 影响 |
|---|------|------|------|
| S-2 | snapshot_manager | 快照无过期清理 | 磁盘空间膨胀 |
| FE-5 | RevisionHintBar | 5秒自动消失过快 | 可能打断阅读 |
| C-2 | content_orchestrator | section id/name 双标识符 | 需多处映射 |
| H-4 | research_api | accepted 状态不区分 dismiss | 审计信息缺失 |
| E-3 | revision_executor | 修订结果未校验完整性 | 可能导致下游崩溃 |

---

## 五、修复建议

### 5.1 R-1/E-1: 修订失败 issue 状态回退

在 `_handle_v2_revision` 的异常/ABORTED 路径中，将关联 issue 的 `state` 从 `revising` 回退为 `open`：

```python
# 在修订失败的 except/ABORTED 分支
for section_name, section_data in quality_state_data.get("section_scores", {}).items():
    for issue in section_data.get("issues", []):
        if issue.get("state") == "revising":
            issue["state"] = "open"
            issue["revision_count"] = max(0, issue.get("revision_count", 0) - 1)
session["quality_state"] = quality_state_data
```

### 5.2 R-2: 版本栈快照排除 version_stack

在创建快照时，`quality_state_snapshot` 应排除 `version_stack`（递归嵌套源）：

```python
snapshot_quality = copy.deepcopy(quality_state_data)
snapshot_quality.pop("version_stack", None)  # 排除，避免递归嵌套
version_entry["quality_state_snapshot"] = snapshot_quality
```

恢复时从上一版本的 `quality_state_snapshot` 恢复，`version_stack` 保留当前值即可。

### 5.3 Q-2/H-3: merge_issues_on_recheck 保留 revision_count

在 `merge_issues_on_recheck` 中，当匹配到已有 issue 时，保留其 `revision_count`：

```python
if existing_issue and hasattr(existing_issue, 'revision_count'):
    new_issue.revision_count = existing_issue.revision_count
```

### 5.4 A-1: 删除章节时清理 section_scores

在 `report_adapter.delete_section` 或 `_handle_v2_revision` 检测到删除操作时，清理 `quality_state.section_scores` 中对应条目。

### 5.5 H-1: rollback 时可靠恢复 sections

在 `_handle_quality_rollback` 中，始终从快照的 `quality_state_snapshot` 反推 sections，或确保快照创建时保存完整的 sections JSON。

### 5.6 R-3: reject 路径推送 SSE

在 `_confirm_v2_revision` 的 reject 分支添加：

```python
SessionStreamer.push_quality_result(session_id, session.get("quality_state", {}))
```

---

## 六、系统复杂修订能力总评

| 维度 | 评分 | 说明 |
|------|------|------|
| 单章节内容修改 | ⭐⭐⭐⭐ | 核心路径完整，基本可靠 |
| 多章节同时修订 | ⭐⭐ | 缺乏事务保障，部分成功时状态不一致 |
| 章节删除 | ⭐⭐ | 删除后质检数据残留，回滚不可靠 |
| 章节新增 | ⭐⭐ | 新章节无初始评分，需手动 recheck |
| 修订失败恢复 | ⭐ | issue 卡死在 revising，无自动恢复机制 |
| 修订次数控制 | ⭐⭐ | revision_count 被重检覆盖，限制失效 |
| 版本回滚 | ⭐⭐⭐ | 基本可用，但 sections 数据恢复不可靠 |
| 并发安全 | ⭐⭐⭐ | 锁机制到位，但语义冲突（dismiss vs recheck）未处理 |
| 定稿交付 | ⭐⭐⭐⭐ | 二次确认机制完整，状态转换正确 |
| 前端交互体验 | ⭐⭐⭐ | SSE 推送基本可靠，但部分边界体验待优化 |

**总体评价**: 系统在基本修订流程上可正常运行，但在异常恢复、数据一致性、复杂场景支持方面存在显著短板。3 个严重问题（R-1/E-1/R-2）必须修复后才能支持生产级的复杂修订工作。建议按严重→中等→低优先级顺序修复。
