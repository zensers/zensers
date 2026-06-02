# 质检反馈交互修订系统 — 修订方案 v9

> 日期: 2026-06-02
> 状态: **已实现** — P0/P1/P2 全部完成；五轮深度审查 + 30 个 bug 修复
> 范围: 报告研究完成后的质检展示、用户交互、内容修订、预览刷新全链路
> 核心原则: **质检让问题可见，修订让对话来做**

---

## 0. 实现进度总览

| 优先级 | 内容 | 状态 | 实现说明 |
|--------|------|------|----------|
| **P0-1** | 修复 `push_quality_confirmed()` bug + 补充 SSE 持久化 | ✅ 已实现 | `session_streamer.py` — bug 修复 + `_persist_event` 补充 |
| **P0-2** | `QualityIssue.revision_count` + `QUALITY_PASS_THRESHOLD` + `accepted` state | ✅ 已实现 | `quality_state.py` — 新增字段 + 常量 + 状态 |
| **P0-3** | `check_by_sections()` 生成稳定 issue ID | ✅ 已实现 | `quality_check_agent.py` — `generate_issue_id` 调用 |
| **P0-4** | 迁移 quality handlers 到 ResearchAPI + 5 个 handler + 锁 | ✅ 已实现 | `research_api.py` — 方法迁移 + 完整 handler |
| **P0-5** | `_handle_v2_revision()` 修订联动 + `_post_revision_recheck()` | ✅ 已实现 | `research_api.py` — 快照+版本栈+重检联动 |
| **P0-6** | 前端 SSE 扩展 + qualityState/pendingInput store + 类型 | ✅ 已实现 | `useProgress.ts`, `useSessionStore.ts`, `api.ts`, `ChatInput.tsx`, `ChatPanel.tsx`, `MainLayout.tsx`, `QualityPanel.tsx` |
| **P0-7** | QualityPanel + ChatInput pendingInput + hydration fix | ✅ 已实现 | QualityPanel 集成到 MainLayout；ChatInput `mounted` guard 修复 hydration mismatch |
| **BF-1** | Zustand persist hydration mismatch 修复 | ✅ 已实现 | `ChatInput.tsx` — `mounted` guard + `useSessionStore.ts` — `merge` 函数 |
| **P1-1** | SectionNavBar + DocumentPreview 集成 | ✅ 已实现 | `SectionNavBar.tsx` + DocumentPreview 锚点跳转（heading text fallback）+ warning 高亮 |
| **P1-2** | RevisionHintBar + preview_refresh 刷新 + 排版保护 | ✅ 已实现 | `RevisionHintBar.tsx` + DocumentPreview iframeKey 刷新 + rollback hint clear + useRef callback pattern |
| **BUG-1** | `_handle_quality_dismiss/reopen` 无 SSE push → 前端不更新 | ✅ 已修复 | 添加 `push_quality_result()` SSE 推送 |
| **BUG-2** | RevisionHintBar `onDismiss` 无限重渲染循环 | ✅ 已修复 | `useRef` 存储 callback，从 useEffect 依赖数组移除 |
| **BUG-3** | `_handle_quality_rollback` 无 deep copy → 修改原始引用 | ✅ 已修复 | 加 `copy.deepcopy()` |
| **BUG-4** | `_handle_v2_revision` 修改 quality_state 无锁 → 并发与 dismiss/rollback 冲突 | ✅ 已修复 | 加 `async with quality_lock` |
| **BUG-5** | `_post_revision_recheck` phase='reviewing' 不推送 SSE | ✅ 已修复 | 添加 `push_quality_result()` |
| **BUG-6** | SSE `subscribeSession` 关闭已有连接 → 杀死 ChatPanel 的 SSE | ✅ 已修复 | 改为共享连接：复用已有 EventSource，引用计数管理生命周期 |
| **BUG-7** | `quality_result` SSE 只在 DocumentPreview 处理 → 预览关闭时 qualityState 永不更新 | ✅ 已修复 | MainLayout 也订阅 `quality_result` + `quality_confirmed` |
| **BUG-8** | ChatPanel `pendingInput` 竞态 → 清除太早 ChatInput 未消费 | ✅ 已修复 | 延迟 100ms 清空 + `consumedRef` 防重复 |
| **BUG-9** | DocumentPreview rollback 不隐藏 RevisionHintBar | ✅ 已修复 | rollback 时 `setRevisionHintVisible(false)` |
| **BUG-10** | SectionNavBar ID 与 HTML `<section id>` 可能不匹配 | ✅ 已修复 | 添加 heading text 匹配 fallback |
| **BUG-11** | `sse.ts` `unsubscribeSession` 中 `eventSource` 变量在共享连接模式下未定义 | ✅ 已修复 | 从 `sessionConnections` Map 取连接实例 |
| **BUG-12** | `check_by_sections()` 缺少 `import re` → NameError 运行时崩溃 | ✅ 已修复 | 方法开头添加 `import re` |
| **BUG-13** | `SectionScore.status` Literal 不含 `"empty"` → Pydantic ValidationError | ✅ 已修复 | Literal 扩展为 `"passed" \| "warning" \| "empty"` |
| **BUG-14** | `_post_revision_recheck` 在 `quality_lock` 外执行 → 数据竞争 | ✅ 已修复 | `_post_revision_recheck` 内部获取 `quality_lock` |
| **BUG-15** | `sse.ts` 引用计数与连接关闭逻辑脱节 → 可能误关连接 | ✅ 已修复 | 关闭条件改为 `newRefCount <= 0 && totalRemaining === 0` |
| **BUG-16** | `QualityPanel` `section_scores` 无空值守卫 → TypeError | ✅ 已修复 | 添加 `|| {}` 兜底 |
| **BUG-17** | `ChatPanel` pendingInput 快速连续点击竞态 | ✅ 已修复 | `useRef` 存储 timer + cleanup 函数 |
| **BUG-18** | 多处 `as any` 类型断言 | ✅ 已修复 | 修正类型定义，用 `QualityStateData['phase']` 替代 `as any` |
| **BUG-19** | `handle_quality_action` TOCTOU: `lock.locked()` 检查与 `async with lock` 竞态 | ✅ 已修复 | 删除 `lock.locked()` 提前检查，直接 `async with lock` |
| **BUG-20** | `DocumentPreview` heading fallback O(n*m) 复杂度 | ✅ 已修复 | 预计算 `sectionTitleMap` Map，O(1) 查找 |
| **BUG-21** | `version_stack` 循环引用：`quality_state_snapshot` 包含完整 `version_stack` | ✅ 已修复 | 快照时排除 `version_stack` 字段 + `deepcopy` |
| **BUG-22** | `MAX_TOTAL_REVISIONS` 检查在 `quality_lock` 外 (TOCTOU) | ✅ 已修复 | 移入 `async with quality_lock` 块内 |
| **BUG-23** | `_confirm_v2_revision` 无锁保护 | ✅ 已修复 | 内部获取 `quality_lock`（`_post_revision_recheck` 在锁外调用） |
| **BUG-24** | `_recheck_quality` 中 `SectionScore(**sec_data)` 可能 ValidationError | ✅ 已修复 | 添加 `try/except` + fallback 构造 |
| **BUG-25** | `QualityPanel` 多处 `section_scores`/`version_stack` 缺空值守卫 | ✅ 已修复 | 添加 `|| {}` / `|| []` 兜底 |
| **BUG-26** | 修订失败 issue 状态不回退（卡在 revising） | ✅ 已修复 | 新增 `_rollback_revising_issues()` 方法，所有失败路径调用 |
| **BUG-27** | `merge_issues_on_recheck` 中 revising issue 未回退为 open | ✅ 已修复 | 合并时 revising → open，保留 revision_count |
| **BUG-28** | `_confirm_v2_revision` reject 路径无 SSE 推送 | ✅ 已修复 | 添加 `push_quality_result` + `_rollback_revising_issues` |
| **BUG-29** | 删除章节后 `section_scores` 残留 | ✅ 已修复 | `_recheck_quality` 清理不匹配当前 sections 的条目 |
| **BUG-30** | empty 章节参与均分拉低 overall_score | ✅ 已修复 | `status == "empty"` 不参与 overall_score 计算 |
| **BUG-31** | rollback 不恢复 sections 数据 | ✅ 已修复 | fallback 从 `quality_state_snapshot.sections` 恢复 |
| **BUG-32** | 发起修订未标记 issue 为 revising | ✅ 已修复 | 新增 `initiate_revision` action + 前端调用 |
| **BUG-33** | `initiate_revision` 后用户未发送，issue 卡 revising | ✅ 已修复 | `revising_since` 时间戳 + `_expire_stale_revising_issues()` 5分钟自动过期 |
| **P2-1** | 修订次数限制（单 issue `MAX_ISSUE_REVISIONS=3` + 总修订 `MAX_TOTAL_REVISIONS=10`） | ✅ 已实现 | `modified_sections` 从 `conv_result["aspects"]` 提取；`version_stack` 长度 ≥ 10 时阻止新修订并推送系统警告 |

v5 → v6 两轮深度审查中额外发现并修复的问题：

**第一轮审查（v5→v5.1）:**

1. **`ChatPanel` pendingInput 竞态**: `useEffect` 立即清空 `pendingInput` → ChatInput 可能还没消费。修复：延迟 100ms + `consumedRef` 防重复清除。
2. **`_handle_quality_dismiss/reopen` 无 SSE push**: 后端修改了 `quality_state` 但没有推送 `quality_result` SSE → 前端 `qualityState` 永不更新。修复：添加 `push_quality_result()`。
3. **RevisionHintBar `onDismiss` 无限重渲染**: `onDismiss` 在 `useEffect` 依赖数组中 → 父组件每次渲染引用变化 → effect 重执行 → 新 timer → 循环。修复：用 `useRef` 存储 callback。
4. **`_handle_quality_rollback` 无 deep copy**: 直接引用 `session["quality_state"]` → 可变引用共享。修复：加 `copy.deepcopy()`。
5. **`_handle_v2_revision` 修改 quality_state 无锁**: 并发与 dismiss/rollback 数据竞争。修复：加 `async with quality_lock`。
6. **`_post_revision_recheck` phase='reviewing' 不推送 SSE**: 后端状态已更新但前端不知道。修复：添加 `push_quality_result()`。

**第二轮审查（v5.1→v6）:**

7. **SSE `subscribeSession` 关闭已有连接** (P0 严重): ChatPanel 和 DocumentPreview 都调用 `subscribeSession(sessionId, ...)` → 第二次调用关闭第一次的 EventSource → 任意组件卸载时关闭所有回调的连接。修复：共享连接模式 + 引用计数。
8. **`quality_result` SSE 只在 DocumentPreview 处理** (P0 严重): `previewVisible=false` 时 DocumentPreview 不挂载 → `onQualityResult` 回调不注册 → `qualityState` 永不更新 → QualityPanel 永不显示。修复：MainLayout 也订阅 quality SSE。
9. **SSE unsubscribe 不区分订阅者** (P1): `unsubscribeSession` 关闭整个连接 → 其他组件的回调丢失。修复：引用计数 `sessionRefCounts`，归零才关闭。
10. **DocumentPreview rollback 不隐藏 RevisionHintBar** (P1): rollback 成功后 hint bar 仍显示。修复：rollback 时 `setRevisionHintVisible(false)`。
11. **SectionNavBar ID 与 HTML 锚点不匹配** (P1): `name.toLowerCase().replace(/\s+/g, '-')` 生成的 ID 与实际 `<section id>` 不一致。修复：添加 heading text 匹配 fallback。

**第三轮审查（v6→v7）:**

12. **`check_by_sections()` 缺少 `import re`** (严重): L900 调用 `re.findall()` 但方法内无 `import re`，其他方法（L337/445/489/774/805）都有局部 import，唯独此方法漏了。运行时直接 NameError 崩溃。修复：方法开头添加 `import re`。
13. **`SectionScore.status` 不含 `"empty"`** (严重): Literal 只有 `"passed" | "warning"`，但 `check_by_sections` 对空章节返回 `status: "empty"`。`_recheck_quality` 中 `SectionScore(**sec_data)` 反序列化时 Pydantic ValidationError。修复：Literal 扩展为 `"passed" | "warning" | "empty"`。
14. **`_post_revision_recheck` 在 `quality_lock` 外执行** (高): `_handle_v2_revision` 的 `async with quality_lock` 在 L2383 结束，但 L2413/2430/2439 的 `_post_revision_recheck` 调用在锁外。`_confirm_v2_revision`（L2483）同样未获取锁。BUG-4 的修复意图未完全贯彻。修复：`_post_revision_recheck` 内部获取 `quality_lock`。
15. **SSE 引用计数与连接关闭逻辑脱节** (中): `totalRemaining` 统计回调剩余数，`newRefCount` 独立递减，关闭条件仅检查 `totalRemaining === 0` 忽略 ref count。修复：关闭条件改为 `newRefCount <= 0 && totalRemaining === 0`。
16. **`QualityPanel` `section_scores` 无空值守卫** (中): `Object.entries(qualityState.section_scores)` — 如果 `section_scores` 为 undefined，直接 TypeError。修复：添加 `|| {}` 兜底。
17. **`ChatPanel` pendingInput 快速连续点击竞态** (中): 快速点击两个 issue 时，100ms 延迟清空可能在第二个 pendingInput 未消费时触发。且 useEffect 无 cleanup 函数。修复：`useRef` 存储 timer ID + cleanup 函数。
18. **多处 `as any` 类型断言** (低): MainLayout/DocumentPreview/QualityPanel/ChatPanel 中多处 `as any`，说明 `QualityStateData` 类型定义与实际 SSE 数据结构不一致。修复：`QualityResultEventData.phase` 改为联合类型，用 `QualityStateData['phase']` 替代 `as any`。
19. **`handle_quality_action` TOCTOU** (低): `if lock.locked(): return CONFLICT` 检查与 `async with lock` 之间理论上可被其他协程插入。修复：删除 `lock.locked()` 提前检查，直接 `async with lock`。
20. **`DocumentPreview` heading fallback O(n\*m)** (低): `sectionNavItems.find()` 在循环内调用。修复：预计算 `sectionTitleMap` Map，O(1) 查找。

**第四轮审查（v7→v8）:**

21. **`version_stack` 循环引用** (严重): `quality_state_snapshot` 包含完整 `version_stack`，导致每次快照指数级增长。修复：快照时排除 `version_stack` 字段 + `deepcopy`。
22. **`MAX_TOTAL_REVISIONS` 检查在 `quality_lock` 外** (高): TOCTOU — 检查与修改之间可能被其他协程插入。修复：移入 `async with quality_lock` 块内。
23. **`_confirm_v2_revision` 无锁保护** (高): `session.pop('_pending_v2_revision')` 与其他 quality 操作并发。修复：内部获取 `quality_lock`。
24. **`_recheck_quality` 中 `SectionScore(**sec_data)` 可能 ValidationError** (高): 后端数据与 Pydantic 模型不一致时直接崩溃。修复：添加 `try/except` + fallback 构造。
25. **`QualityPanel` 多处 `section_scores`/`version_stack` 缺空值守卫** (高): 后端未返回字段时 TypeError。修复：`|| {}` / `|| []` 兜底。

---

## 0.2 关键架构决策

| 决策 | 说明 | 影响 |
|------|------|------|
| 共享 SSE 连接模式 | `subscribeSession` 复用已有 EventSource，引用计数（`sessionRefCounts`）管理生命周期，归零才关闭 | 修复 BUG-6：多组件订阅同一 session 不再互杀连接 |
| MainLayout 独立订阅 quality SSE | 即使 `previewVisible=false`，MainLayout 也订阅 `quality_result` + `quality_confirmed` | 修复 BUG-7：预览关闭时 qualityState 仍能更新 |
| `async with quality_lock` | 所有 quality_state 修改操作加锁（含 `_post_revision_recheck` 内部获取锁） | 修复 BUG-4/BUG-14：防止 dismiss/rollback/revision 并发竞争 |
| `copy.deepcopy()` | rollback/dismiss/reopen 等操作先深拷贝再修改 | 修复 BUG-3：避免可变引用共享 |
| `useRef` 存储 callback | RevisionHintBar 的 `onDismiss` 等回调用 `useRef` 存储 | 修复 BUG-2：防止 useEffect 依赖数组引用变化导致无限循环 |
| `iframeKey` 刷新 | preview_refresh 时通过 key 递增触发 iframe 完整重新挂载 | 避免浏览器缓存导致内容不更新 |
| `consumedRef` + 延迟清空 | pendingInput 消费用 consumedRef 防重复，ChatPanel 延迟 100ms 清空（timer ref + cleanup） | 修复 BUG-8/BUG-17：防止 ChatInput 未消费就被清空 + 快速连续点击竞态 |

---

## 0.3 审计说明（v4 历史）

本方案基于 v3 版本，经过逐行代码审计后修订。v3 → v4 主要修正：

1. **回滚方法未恢复 sections 数据**: `_handle_quality_rollback` 中 `restored_report` 被读取但未写回 session，回滚形同虚设
2. **`_post_revision_recheck` 与 `_handle_quality_recheck` 重复代码**: 提取公共 `_recheck_quality()` 方法
3. **`modified_sections` 变量未定义**: 修订次数限制代码引用了未定义变量，改为从 `conv_result["aspects"]` 提取
4. **并发锁非原子操作**: dict 检查-设置在异步并发下不安全，改用 `asyncio.Lock`
5. **`pendingInput` 清除机制失效**: `syncActive` 过滤 `undefined`，改用 `null` 并修改过滤逻辑
6. **`push_preview_refresh` / `push_section_quality` 缺少 `_persist_event`**: 断线重连后事件丢失
7. **`_handle_quality_recheck` 中 `section_name` 过滤时机错误**: 全量检查后再丢弃，改为调用前过滤 sections
8. **`_confirm_v2_revision()` 未集成质检联动**: 用户确认修订后评分不更新
9. **`push_quality_result` SSE 字段名 `section_results` 与前端 `section_scores` 不匹配**: 需字段映射
10. **评分阈值全局不一致**: handler 中 70 分 vs 已有代码 60 分，统一为常量 `QUALITY_PASS_THRESHOLD`
11. **`_handle_quality_dismiss`/`_reopen` 直接修改嵌套 dict 可能不触发持久化**: 改用深拷贝确保触发
12. **`quality_state.py` 同时出现在修改/无需修改两个表中**: 移除矛盾
13. **`_handle_quality_confirm` 的 `pending_issues` 无前端对接**: 补充交互规格
14. **`push_quality_confirmed` 修复方案中 `_persist_event` 缺 timestamp**: 补充一致

v2 → v3 主要修正（历史）：

1. **`push_quality_confirmed()` bug 精确定位**: L252-257 是正确代码，L258-264 是残留的 `push_section_quality` 代码
2. **`handle_quality_action()` / `get_quality_state()` 是模块级函数**: `main.py:396` 用 `research_api.handle_quality_action(req)` 调用会 AttributeError，需迁移到 ResearchAPI 类方法
3. **`QualityActionRequest` 是普通 class**，只有 `session_id/action/data`，需扩展 `issue_id/version_id/section_name`
4. **`check_by_sections(sections, ...)` 接收 `List[Dict]`，不是 session**: `_handle_quality_recheck` 和 `_post_revision_recheck` 传参错误
5. **`push_section_quality(session_id, section_name, quality_data)` 是三参数**: 文档中两参数调用错误
6. **`merge_issues_on_recheck` 期望 `Dict[str, SectionScore]`**: session 中是 plain dict，需先转换
7. **HTML 锚点已存在**: `_render_section_html` 已输出 `<section id="{section.id}"`，无需修改 `content_orchestrator.py`
8. **`check_preview_health(html_path, old_html_length)`**: 第一个参数是当前路径，第二个是旧长度
9. **ChatInput 无 pendingInput 机制**: 需新增 prop
10. **session key 映射**: `_session_id` 而非 `session_id`；`task_id` 等于 `session_id`

---

## 1. 背景与问题

当前系统在报告研究完成后，质检信息无法被用户感知，更无法交互：

| 断点 | 现状 | 影响 |
|------|------|------|
| 前端SSE | `sse.ts` `subscribeSession()` 只监听 `chat_response` / `agent_message` | 质检分数被静默丢弃 |
| 前端组件 | 无质量面板 | 用户看不到章节评分 |
| 后端API | `handle_quality_action()` 只处理 `approve`，且是空壳 | 无质检专用操作 |
| 后端SSE | `push_quality_confirmed()` 有 bug（L258-264 残留代码）；`push_preview_refresh`/`push_section_quality` 缺少持久化 | 质检确认事件推送错误；断线重连后事件丢失 |
| 修订闭环 | `_handle_v2_revision()` 无质检联动 | 无"修订→重检→刷新"循环 |
| 质检Agent | `check_by_sections()` 返回的 issue 无稳定 ID | 重检时无法追踪同一问题 |
| 预览刷新 | 修订后无自动刷新 | 用户不知道修订是否生效 |

### 1.1 已有实现（可复用）

| 模块 | 文件 | 状态 |
|------|------|------|
| 数据模型 | `src/core/quality/quality_state.py` | ✅ 完整 + 已扩展（revision_count, accepted, QUALITY_PASS_THRESHOLD） |
| 快照管理 | `src/core/quality/quality_snapshot_manager.py` | ✅ 完整 |
| 预览自检 | `src/core/quality/preview_health.py` | ✅ 完整 |
| SSE事件类型 | `src/core/session_streamer.py` L33-42 | ✅ 枚举已定义 |
| SSE push方法 | `src/core/session_streamer.py` L214-264 | ✅ **已修复**: push_quality_confirmed bug 修复；push_preview_refresh/push_section_quality 补充持久化 |
| API端点注册 | `src/api/main.py` L392-401 | ✅ 路由已注册 |
| HTML锚点 | `src/content/content_orchestrator.py` L734 | ✅ `<section id="{section.id}">` 已有 |
| 请求模型 | `src/api/research_api.py` | ✅ **已扩展**: QualityActionRequest 添加 issue_id/version_id/section_name；迁移为 ResearchAPI 实例方法 |
| 质检Agent | `src/agents/fixed_agents/quality_check_agent.py` | ✅ **已修复**: check_by_sections 生成稳定 issue ID |
| Quality handlers | `src/api/research_api.py` | ✅ **已实现**: 5 个 handler + _recheck_quality + _post_revision_recheck + _get_quality_lock |

---

## 2. 设计目标

1. **可见**: 研究完成后前端实时展示分章节评分、整体评分、问题列表
2. **可对话**: 质检问题通过对话发起修订，用户可精细控制修订方向和范围
3. **可观测**: 每次修订后预览自动刷新，评分实时更新
4. **可恢复**: 排版错乱时可一键回滚到修订前版本（回滚同时恢复 HTML 和 sections 数据）
5. **有终态**: 明确"确认交付"出口；仍有未解决问题时需二次确认，确认后 issue 标记为 `accepted`

---

## 3. 整体流程

```
研究报告完成
    │
    ▼
┌─────────────────────────┐
│  阶段A: 质检展示         │  前端接收 quality_result / section_quality SSE
│  - 整体评分              │  显示质量面板 + 各章节评分卡
│  - 分章节评分            │  章节导航条高亮有问题的章节
│  - 问题列表              │
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│  阶段B: 对话式修订       │  用户点击 issue → 问题详情填入聊天输入框
│  - 用户点击 issue        │    用户可补充具体要求后提交
│  - 系统预填修订指令      │    走现有 _llm_converse → _handle_v2_revision 链路
│  - 用户微调后发送        │    RevisionService 执行修订
│  - 对话驱动修订执行      │
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│  阶段C: 修订后刷新       │  修订完成
│  - 重新生成预览          │    SSE 推送 preview_refresh 刷新预览
│  - 重检受影响章节        │    SSE 推送新的 section_quality
│  - 更新评分              │    修订提示条: 如排版异常可[一键回滚]
│  - 推送评分更新          │
└─────────┬───────────────┘
          │
          ▼
┌─────────────────────────┐
│  阶段D: 确认交付         │  用户满意后点击"确认交付"
│  - 生成最终文档          │  生成 DOCX/PPTX/PDF
│  - 退出修订模式          │  关闭质量面板
└─────────────────────────┘
```

---

## 4. 数据模型

### 4.1 QualityState（已实现 ✅）

`src/core/quality/quality_state.py` 已完整实现，直接使用。关键类型：

- `QualityIssue` — `id/type/severity/message/section/state`
- `SectionScore` — `score/status/issues`
- `VersionInfo` — `id/created_at/html_path/md_path/quality_state_snapshot/overall_score/label`
- `QualityState` — `phase/overall_score/overall_status/section_scores/version_stack/current_version`
- `generate_issue_id(section, issue_type, message)` — 稳定哈希 `q-{md5[:8]}`
- `merge_issues_on_recheck(existing_sections: Dict[str, SectionScore], new_section_results: Dict[str, dict]) -> Dict[str, SectionScore]`

**新增字段**: `QualityIssue` 需新增 `revision_count: int = 0`（支持修订次数限制）。

### 4.2 session 中存储方式

```python
session["quality_state"] = QualityState(...).model_dump()
```

`session["quality_state"]` 是 **plain dict**（`model_dump()` 的结果），不是 Pydantic 对象。需要调用 `merge_issues_on_recheck` 时，须先反序列化为 `SectionScore` 对象。

### 4.3 session key 映射

| 用途 | session 中的 key | 备注 |
|------|------------------|------|
| session_id | `_session_id` | `session.get("_session_id")` |
| task_id | 等于 session_id | 此项目中 task_id == session_id |
| 章节 sections | `research_result.report.sections` | `session["research_result"]["report"]["sections"]` |
| HTML 预览路径 | `PreviewStorage.path(session_id)` | `data/html_reports/{session_id}.html` |
| HTML 预览 URL | `PreviewStorage.url(session_id)` | `/api/v1/html-reports/{session_id}.html` |
| quality_state | `quality_state` | plain dict |
| Markdown 源路径 | 无固定 key | 修订系统使用 `SessionReportAdapter` 操作 `research_result.report.sections` |

---

## 5. 后端修改清单

### 5.1 修复 Bug: `push_quality_confirmed()`

**文件**: `src/core/session_streamer.py`
**行号**: L252-264

**当前代码**:
```python
251:     @classmethod
252:     def push_quality_confirmed(cls, session_id: str, final_document_path: str):
253:         """Push a quality confirmed event to session subscribers"""
254:         cls._notify_subscribers(session_id, SessionSSEEventType.QUALITY_CONFIRMED, {
255:             "session_id": session_id,
256:             "final_document_path": final_document_path,
257:         })
258:         cls._persist_event(session_id, SessionSSEEventType.SECTION_QUALITY.value, {
259:             "session_id": session_id,
260:             "section_name": section_name,  # ❌ NameError
261:             "score": quality_data.get("score", 0),  # ❌ NameError
262:             "status": quality_data.get("status", "unknown"),  # ❌ NameError
263:         })
264:         logger.debug(f"Session stream section_quality pushed: {session_id}/{section_name}")
```

**修复**: 删除 L258-264（残留的 `push_section_quality` 持久化代码），替换为正确的持久化和日志：

```python
@classmethod
def push_quality_confirmed(cls, session_id: str, final_document_path: str):
    """Push a quality confirmed event to session subscribers"""
    event_data = {
        "session_id": session_id,
        "final_document_path": final_document_path,
        "timestamp": datetime.now().isoformat(),
    }
    cls._notify_subscribers(session_id, SessionSSEEventType.QUALITY_CONFIRMED, event_data)
    cls._persist_event(session_id, SessionSSEEventType.QUALITY_CONFIRMED.value, event_data)
    logger.info(f"Session stream quality_confirmed pushed: {session_id}")
```

---

### 5.2 迁移 `handle_quality_action()` / `get_quality_state()` 到 ResearchAPI 类

**问题**: 这两个函数当前是 `src/api/research_api.py` 末尾的**模块级函数**（L2677-2696），但 `main.py:396` 和 `main.py:401` 用 `research_api.handle_quality_action(req)` / `research_api.get_quality_state(session_id)` 调用，会 AttributeError。

**方案**: 将这两个函数迁移为 `ResearchAPI` 的实例方法。同时重构 `QualityActionRequest`。

---

### 5.3 扩展 `QualityActionRequest`

**文件**: `src/api/research_api.py`

**当前代码** (L2669-2674):
```python
class QualityActionRequest:
    def __init__(self, **kwargs):
        self.session_id = kwargs.get('session_id')
        self.action = kwargs.get('action')
        self.data = kwargs.get('data', {})
```

**修改为**:
```python
class QualityActionRequest:
    def __init__(self, **kwargs):
        self.session_id = kwargs.get('session_id')
        self.action = kwargs.get('action')
        self.data = kwargs.get('data', {})
        self.issue_id = kwargs.get('issue_id')
        self.version_id = kwargs.get('version_id')
        self.section_name = kwargs.get('section_name')
```

同时 `main.py:393-396` 调用方式不变，`QualityActionRequest(**request)` 会自动忽略多余字段。`data` 字段保留以传递 `force` 等扩展参数。

---

### 5.4 重写 `handle_quality_action()` 和 `get_quality_state()`

**文件**: `src/api/research_api.py`

将 L2677-2696 的模块级函数**删除**，在 `ResearchAPI` 类内新增以下方法：

```python
async def handle_quality_action(self, request: QualityActionRequest) -> Dict[str, Any]:
    action = request.action
    session_id = request.session_id
    session = session_manager.get(session_id)
    if not session:
        return {"error": "Session not found", "error_code": "SESSION_NOT_FOUND"}

    if action == "quality_dismiss":
        return await self._handle_quality_dismiss(session, request.issue_id)
    elif action == "quality_reopen":
        return await self._handle_quality_reopen(session, request.issue_id)
    elif action == "quality_rollback":
        return await self._handle_quality_rollback(session, request.version_id)
    elif action == "quality_confirm":
        force = request.data.get("force", False) if request.data else False
        return await self._handle_quality_confirm(session, force=force)
    elif action == "quality_recheck":
        return await self._handle_quality_recheck(session, request.section_name)
    else:
        return {"error": f"Unknown action: {action}", "error_code": "UNKNOWN_ACTION"}

async def get_quality_state(self, session_id: str) -> Dict[str, Any]:
    session = session_manager.get(session_id)
    if not session:
        return {"error": "Session not found", "error_code": "SESSION_NOT_FOUND"}
    return session.get("quality_state", {})
```

> **注意**：`QualityActionRequest` 保留 `data` 字段以传递 `force` 等扩展参数，同时新增 `issue_id/version_id/section_name`。

---

### 5.5 实现 5 个 quality handler

**文件**: `src/api/research_api.py`（ResearchAPI 类内）

以下所有方法中 `session` 是 `PersistentSessionDict`，对其 key 赋值（如 `session["quality_state"] = ...`）会自动持久化。

#### `_handle_quality_dismiss`

```python
async def _handle_quality_dismiss(self, session, issue_id: str) -> Dict[str, Any]:
    import copy
    quality_data = copy.deepcopy(session.get("quality_state", {}))
    if not quality_data:
        return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}

    found = False
    for section_name, section_data in quality_data.get("section_scores", {}).items():
        for issue in section_data.get("issues", []):
            if issue.get("id") == issue_id:
                issue["state"] = "dismissed"
                found = True
                break
        if found:
            break

    if not found:
        return {"error": f"Issue {issue_id} not found", "error_code": "ISSUE_NOT_FOUND"}

    session["quality_state"] = quality_data
    return {"success": True, "issue_id": issue_id, "state": "dismissed"}
```

#### `_handle_quality_reopen`

```python
async def _handle_quality_reopen(self, session, issue_id: str) -> Dict[str, Any]:
    import copy
    quality_data = copy.deepcopy(session.get("quality_state", {}))
    if not quality_data:
        return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}

    found = False
    for section_name, section_data in quality_data.get("section_scores", {}).items():
        for issue in section_data.get("issues", []):
            if issue.get("id") == issue_id and issue.get("state") == "dismissed":
                issue["state"] = "open"
                found = True
                break
        if found:
            break

    if not found:
        return {"error": f"Issue {issue_id} not found or not dismissed", "error_code": "ISSUE_NOT_FOUND"}

    session["quality_state"] = quality_data
    return {"success": True, "issue_id": issue_id, "state": "open"}
```

#### `_handle_quality_rollback`

```python
async def _handle_quality_rollback(self, session, version_id: str) -> Dict[str, Any]:
    quality_data = session.get("quality_state", {})
    if not quality_data:
        return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}

    version_stack = quality_data.get("version_stack", [])
    target_version = None
    for v in version_stack:
        if v.get("id") == version_id:
            target_version = v
            break

    if not target_version:
        return {"error": f"Version {version_id} not found", "error_code": "VERSION_NOT_FOUND"}

    session_id = session.get("_session_id", "")

    from src.core.quality.quality_snapshot_manager import QualitySnapshotManager
    snap_mgr = QualitySnapshotManager()
    snapshot = await snap_mgr.restore_snapshot(session_id, version_id)
    if not snapshot:
        return {"error": "Snapshot restore failed", "error_code": "SNAPSHOT_RESTORE_FAILED"}

    html_src = Path(snapshot["html_path"])
    md_src = Path(snapshot.get("md_path", ""))

    from src.core.preview_storage import PreviewStorage
    html_dest = PreviewStorage.path(session_id)

    if html_src.exists():
        PreviewStorage.ensure_dirs()
        shutil.copy2(str(html_src), str(html_dest))

    restored_quality = snapshot["quality_state"]

    if md_src.exists():
        quality_json_path = md_src.parent / f"{version_id}_quality.json"
        if quality_json_path.exists():
            restored_snapshot_data = json.loads(quality_json_path.read_text(encoding="utf-8"))
            restored_sections = restored_snapshot_data.get("sections", [])
            if restored_sections:
                report = session.setdefault("research_result", {}).setdefault("report", {})
                report["sections"] = restored_sections

    for section_name, section_data in restored_quality.get("section_scores", {}).items():
        for issue in section_data.get("issues", []):
            if issue.get("state") == "resolved":
                issue["state"] = "open"

    session["quality_state"] = restored_quality

    from src.core.session_streamer import SessionStreamer
    SessionStreamer.push_preview_refresh(
        session_id,
        preview_url=PreviewStorage.url(session_id),
        version_id=version_id,
    )
    SessionStreamer.push_quality_result(session_id, restored_quality)

    return {"success": True, "version_id": version_id, "quality_state": restored_quality}
```

#### `_handle_quality_confirm`

```python
async def _handle_quality_confirm(self, session, force: bool = False) -> Dict[str, Any]:
    import copy
    quality_data = copy.deepcopy(session.get("quality_state", {}))
    if not quality_data:
        return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}

    open_issues = []
    for section_name, section_data in quality_data.get("section_scores", {}).items():
        for issue in section_data.get("issues", []):
            if issue.get("state") in ("open", "max_retries_reached"):
                open_issues.append({
                    "id": issue.get("id"),
                    "section": section_name,
                    "message": issue.get("message"),
                    "severity": issue.get("severity"),
                    "state": issue.get("state"),
                })

    if open_issues and not force:
        return {
            "status": "pending_issues",
            "open_issues": open_issues,
            "message": "仍有未解决的问题，请确认是否仍要交付",
        }

    for section_name, section_data in quality_data.get("section_scores", {}).items():
        for issue in section_data.get("issues", []):
            if issue.get("state") in ("open", "dismissed", "max_retries_reached"):
                issue["state"] = "accepted"

    quality_data["phase"] = "confirmed"
    session["quality_state"] = quality_data

    session_id = session.get("_session_id", "")
    from src.core.preview_storage import PreviewStorage
    from src.core.session_streamer import SessionStreamer
    SessionStreamer.push_quality_confirmed(session_id, PreviewStorage.url(session_id))

    return {"status": "confirmed", "quality_state": quality_data}
```

> **前端对接**：`ConfirmDeliveryDialog` 收到 `pending_issues` 响应时，展示未解决 issue 列表，提供"仍要交付"（force=True）和"继续修订"两个按钮。用户选择"仍要交付"时，前端以 `action=quality_confirm&force=true` 再次请求。

#### `_handle_quality_recheck`

注意：`check_by_sections` 接收 `sections: List[Dict]`，不是 session。从 session 获取 sections 的路径是 `session["research_result"]["report"]["sections"]`。

注意：当指定 `section_name` 时，**在调用前过滤 sections**，避免全量检查后再丢弃结果。

注意：`merge_issues_on_recheck` 接收 `existing_sections: Dict[str, SectionScore]`（Pydantic 对象），但 session 中 `quality_state.section_scores` 是 plain dict。需要先反序列化。

注意：`push_section_quality` 签名是 `(session_id, section_name, quality_data)` 三参数，需要逐章节推送。

```python
async def _handle_quality_recheck(self, session, section_name: Optional[str] = None) -> Dict[str, Any]:
    quality_data = session.get("quality_state", {})
    if not quality_data:
        return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}

    session_id = session.get("_session_id", "")

    sections = session.get("research_result", {}).get("report", {}).get("sections", [])
    if not sections:
        return {"error": "No sections in session", "error_code": "NO_SECTIONS"}

    if section_name:
        sections = [s for s in sections if s.get("name") == section_name or s.get("id") == section_name]
        if not sections:
            return {"error": f"Section {section_name} not found", "error_code": "SECTION_NOT_FOUND"}

    result = await self._recheck_quality(session, sections, section_name=section_name)
    return result
```

#### `_recheck_quality`（公共重检方法）

提取自 `_handle_quality_recheck` 和 `_post_revision_recheck` 的公共逻辑，消除重复代码。

```python
async def _recheck_quality(
    self, session, sections: List[Dict], section_name: Optional[str] = None,
    push_preview: bool = False,
) -> Dict[str, Any]:
    import copy
    quality_data = copy.deepcopy(session.get("quality_state", {}))
    if not quality_data:
        return {"error": "No quality state", "error_code": "NO_QUALITY_STATE"}

    session_id = session.get("_session_id", "")

    from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
    from src.core.quality.quality_state import generate_issue_id, merge_issues_on_recheck, SectionScore, QUALITY_PASS_THRESHOLD
    quality_agent = QualityCheckAgent()
    result = await quality_agent.check_by_sections(sections, session_id=session_id, research_id=session_id)

    new_section_results = result.get("section_results", {})

    for sec_name, sec_data in new_section_results.items():
        for issue in sec_data.get("issues", []):
            issue["id"] = generate_issue_id(sec_name, issue.get("type", ""), issue.get("message", ""))
            issue["section"] = sec_name
            if "state" not in issue:
                issue["state"] = "open"

    existing_section_scores = {}
    for sec_name, sec_data in quality_data.get("section_scores", {}).items():
        existing_section_scores[sec_name] = SectionScore(**sec_data) if isinstance(sec_data, dict) else sec_data

    merged = merge_issues_on_recheck(existing_section_scores, new_section_results)

    overall_score = 0.0
    count = 0
    for sec_name, section_score_obj in merged.items():
        score = section_score_obj.score
        status = "passed" if score >= QUALITY_PASS_THRESHOLD else "warning"
        quality_data["section_scores"][sec_name] = {
            "score": score,
            "status": status,
            "issues": [iss.model_dump() for iss in section_score_obj.issues],
        }
        overall_score += score
        count += 1

    if count > 0:
        quality_data["overall_score"] = round(overall_score / count, 1)
        quality_data["overall_status"] = "passed" if quality_data["overall_score"] >= QUALITY_PASS_THRESHOLD else "warning"

    session["quality_state"] = quality_data

    from src.core.session_streamer import SessionStreamer
    if push_preview:
        from src.core.preview_storage import PreviewStorage
        SessionStreamer.push_preview_refresh(
            session_id,
            preview_url=PreviewStorage.url(session_id),
            version_id=quality_data.get("current_version", "v0"),
        )
    SessionStreamer.push_quality_result(session_id, quality_data)
    for sec_name, sec_data in quality_data.get("section_scores", {}).items():
        if not section_name or sec_name == section_name:
            SessionStreamer.push_section_quality(session_id, sec_name, sec_data)

    return {"success": True, "quality_state": quality_data}
```

---

### 5.6 修改 `check_by_sections()` 生成稳定 Issue ID

**文件**: `src/agents/fixed_agents/quality_check_agent.py`

在 `check_by_sections()` 方法中（L873-976），当前返回的 issue 只有 `type/severity/message`，无 `id` 和 `state`。需在返回结果的 issue 中添加稳定 ID。

在 L913 `section_results[section_name] = {...}` 之前，为 issues 添加 id 和 state：

```python
from src.core.quality.quality_state import generate_issue_id

# 在 section_results[section_name] = {...} 之前
for issue in issues:
    issue["id"] = generate_issue_id(section_name, issue.get("type", ""), issue.get("message", ""))
    issue["section"] = section_name
    if "state" not in issue:
        issue["state"] = "open"
```

同样对 `overall_issues`（L928-946）中新增的 issue 也需添加 id：

```python
for issue in overall_issues:
    if "id" not in issue:
        issue["id"] = generate_issue_id("overall", issue.get("type", ""), issue.get("message", ""))
    if "section" not in issue:
        issue["section"] = "overall"
    if "state" not in issue:
        issue["state"] = "open"
```

---

### 5.7 修订与质检联动：修改 `_handle_v2_revision()`

**文件**: `src/api/research_api.py`

在 `_handle_v2_revision()` 方法中（L2325 起），修订执行前创建快照并标记 issue 为 revising，修订完成后自动重检。

**修订前** — 在 L2345 `revision_task = asyncio.create_task(...)` 之前插入：

```python
quality_state_data = session.get("quality_state", {})
if quality_state_data and quality_state_data.get("phase") in ("reviewing", "revising"):
    quality_state_data["phase"] = "revising"
    session["quality_state"] = quality_state_data

    from src.core.quality.quality_snapshot_manager import QualitySnapshotManager
    from src.core.preview_storage import PreviewStorage
    snap_mgr = QualitySnapshotManager()
    html_path = str(PreviewStorage.path(session_id))
    md_path = ""
    version_id = await snap_mgr.create_snapshot(
        session_id, html_path, md_path, quality_state_data
    )

    version_n = len(quality_state_data.get("version_stack", []))
    quality_state_data["version_stack"].append({
        "id": version_id,
        "created_at": datetime.now().isoformat(),
        "html_path": f"data/snapshots/{session_id}/{version_id}.html",
        "md_path": f"data/snapshots/{session_id}/{version_id}.md",
        "quality_state_snapshot": quality_state_data,
        "overall_score": quality_state_data.get("overall_score", 0),
        "label": f"修订前快照 v{version_n}",
    })
    quality_state_data["current_version"] = version_id
    session["quality_state"] = quality_state_data
```

**修订后** — 在 L2358 `self._sync_lightweight_to_preview(...)` 之后，及 L2366 `return self._chat_response(session_id)` 之前（即 LIGHTWEIGHT_DONE 分支完成时），以及在其他修订成功返回之前（如 PREVIEW_READY 确认后、ABORTED/ROLLED_BACK 之后），调用重检：

```python
    if quality_state_data:
        await self._post_revision_recheck(session)
```

**确认修订后** — 在 `_confirm_v2_revision()`（L2394-2432）中 `accept=True` 分支的文档生成完成后（L2421 之后），同样调用重检：

```python
    if session.get("quality_state"):
        await self._post_revision_recheck(session)
```

新增 `_post_revision_recheck` 方法（内部调用公共 `_recheck_quality`）：

```python
async def _post_revision_recheck(self, session):
    quality_data = session.get("quality_state", {})
    if not quality_data:
        return

    session_id = session.get("_session_id", "")

    sections = session.get("research_result", {}).get("report", {}).get("sections", [])
    if not sections:
        return

    await self._recheck_quality(session, sections, push_preview=True)

    quality_data = session.get("quality_state", {})
    quality_data["phase"] = "reviewing"
    session["quality_state"] = quality_data

    from src.core.quality.preview_health import check_preview_health
    from src.core.preview_storage import PreviewStorage
    from src.core.session_streamer import SessionStreamer
    html_path = str(PreviewStorage.path(session_id))
    old_html_length = 0
    if quality_data.get("version_stack"):
        last_version = quality_data["version_stack"][-1]
        old_snap_html = Path(last_version.get("html_path", ""))
        if old_snap_html.exists():
            old_html_length = len(old_snap_html.read_text(encoding="utf-8"))

    health = check_preview_health(html_path, old_html_length)
    if not health["healthy"]:
        SessionStreamer.push_agent_message(session_id, {
            "agent_id": "system",
            "agent_name": "系统",
            "action": "warning",
            "content": f"修订完成但预览可能存在排版问题: {', '.join(i['message'] for i in health['issues'])}。可在质量面板中使用版本回滚恢复。",
        })
```

---

### 5.8 修订次数限制与评分阈值常量

**文件**: `src/core/quality/quality_state.py`

在 `QualityIssue` 类新增字段：

```python
revision_count: int = 0
```

在 `quality_state.py` 中新增评分阈值常量（与 `quality_check_agent.py` 的 60 分阈值统一）：

```python
QUALITY_PASS_THRESHOLD = 60  # 质检通过分数阈值
```

> **阈值统一说明**: `quality_check_agent.py` 中 `check_by_sections` 用 60 分为 passed 阈值（L915），`_generate_summary` 用 60 分（L864-866），`execute()` 用 60 分（L183）。v3 版本中 handler 代码用 70 分不一致，v4 统一为 `QUALITY_PASS_THRESHOLD = 60`。

**文件**: `src/api/research_api.py`

在 `_handle_v2_revision()` 中标记 issue 为 revising 之前，检查并递增：

```python
MAX_ISSUE_REVISIONS = 3
MAX_TOTAL_REVISIONS = 10

modified_sections = []
aspects = conv_result.get("aspects", [])
if aspects:
    modified_sections = aspects
else:
    flow = session.get("_pending_v2_revision")
    if flow:
        for task in flow.get("flow", {}).tasks:
            if task.section_name:
                modified_sections.append(task.section_name)

for section_name, section_data in quality_state_data.get("section_scores", {}).items():
    for issue in section_data.get("issues", []):
        if issue.get("state") == "open" and issue.get("section") in modified_sections:
            if issue.get("revision_count", 0) >= MAX_ISSUE_REVISIONS:
                issue["state"] = "max_retries_reached"
            else:
                issue["state"] = "revising"
                issue["revision_count"] = issue.get("revision_count", 0) + 1
```

总修订次数限制通过 `len(quality_data.get("version_stack", []))` 检查是否 >= `MAX_TOTAL_REVISIONS`。

### 5.9 补充 `push_preview_refresh` / `push_section_quality` 持久化

**文件**: `src/core/session_streamer.py`

当前 `push_preview_refresh`（L241-249）和 `push_section_quality`（L232-238）缺少 `_persist_event` 调用，断线重连后事件无法恢复。

**修改 `push_section_quality`**:

```python
@classmethod
def push_section_quality(cls, session_id: str, section_name: str, quality_data: dict):
    """Push a section quality check result to session subscribers"""
    event_data = {
        "session_id": session_id,
        "section_name": section_name,
        "data": quality_data,
    }
    cls._notify_subscribers(session_id, SessionSSEEventType.SECTION_QUALITY, event_data)
    cls._persist_event(session_id, SessionSSEEventType.SECTION_QUALITY.value, event_data)
    logger.debug(f"Session stream section_quality pushed: {session_id}/{section_name}")
```

**修改 `push_preview_refresh`**:

```python
@classmethod
def push_preview_refresh(cls, session_id: str, preview_url: str, version_id: str):
    """Push a preview refresh event to session subscribers"""
    from datetime import datetime
    event_data = {
        "session_id": session_id,
        "preview_url": preview_url,
        "version_id": version_id,
        "timestamp": datetime.now().isoformat(),
    }
    cls._notify_subscribers(session_id, SessionSSEEventType.PREVIEW_REFRESH, event_data)
    cls._persist_event(session_id, SessionSSEEventType.PREVIEW_REFRESH.value, event_data)
    logger.info(f"Session stream preview_refresh pushed: {session_id}")
```

### 5.10 质检操作并发锁改用 `asyncio.Lock`

**文件**: `src/api/research_api.py`

v3 中 dict 检查-设置方式在异步并发下不安全。改为复用已有的 `_session_locks` 模式：

```python
def _get_quality_lock(self, session_id: str) -> asyncio.Lock:
    key = f"_quality_{session_id}"
    if key not in self._session_locks:
        self._session_locks[key] = asyncio.Lock()
    return self._session_locks[key]
```

在 `handle_quality_action` 中使用：

```python
async def handle_quality_action(self, request: QualityActionRequest) -> Dict[str, Any]:
    session_id = request.session_id
    lock = self._get_quality_lock(session_id)
    if lock.locked():
        return {"error": "Concurrent operation in progress", "error_code": "CONFLICT"}
    async with lock:
        session = session_manager.get(session_id)
        if not session:
            return {"error": "Session not found", "error_code": "SESSION_NOT_FOUND"}
        # ... 原 action 分发逻辑 ...
```

---

## 6. 前端修改清单

### 6.1 修改 `sse.ts` — 扩展 SSE 事件监听

**文件**: `web/src/lib/sse.ts`

**新增回调类型和存储**（在类私有属性区域，L154 之后）:

```typescript
type QualityResultCallback = (data: QualityResultEventData) => void;
type SectionQualityCallback = (data: SectionQualityEventData) => void;
type PreviewRefreshCallback = (data: PreviewRefreshEventData) => void;
type QualityConfirmedCallback = (data: QualityConfirmedEventData) => void;

private sessionQualityResultCallbacks: Map<string, Set<QualityResultCallback>> = new Map();
private sessionSectionQualityCallbacks: Map<string, Set<SectionQualityCallback>> = new Map();
private sessionPreviewRefreshCallbacks: Map<string, Set<PreviewRefreshCallback>> = new Map();
private sessionQualityConfirmedCallbacks: Map<string, Set<QualityConfirmedCallback>> = new Map();
```

**`subscribeSession()` 签名扩展**（L171）:

```typescript
subscribeSession(
  sessionId: string,
  onChatResponse: ChatResponseCallback,
  onAgentMessage?: AgentMessageCallback,
  onQualityResult?: QualityResultCallback,
  onSectionQuality?: SectionQualityCallback,
  onPreviewRefresh?: PreviewRefreshCallback,
  onQualityConfirmed?: QualityConfirmedCallback,
): () => void;
```

**在 `subscribeSession()` 内 `eventSource.addEventListener` 区域新增 4 个监听**:

```typescript
eventSource.addEventListener('quality_result', (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    const cbs = this.sessionQualityResultCallbacks.get(sessionId);
    if (cbs) cbs.forEach(cb => cb(data));
  } catch (e) { console.error('quality_result parse error:', e); }
});

eventSource.addEventListener('section_quality', (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    const cbs = this.sessionSectionQualityCallbacks.get(sessionId);
    if (cbs) cbs.forEach(cb => cb(data));
  } catch (e) { console.error('section_quality parse error:', e); }
});

eventSource.addEventListener('preview_refresh', (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    const cbs = this.sessionPreviewRefreshCallbacks.get(sessionId);
    if (cbs) cbs.forEach(cb => cb(data));
  } catch (e) { console.error('preview_refresh parse error:', e); }
});

eventSource.addEventListener('quality_confirmed', (event: MessageEvent) => {
  try {
    const data = JSON.parse(event.data);
    const cbs = this.sessionQualityConfirmedCallbacks.get(sessionId);
    if (cbs) cbs.forEach(cb => cb(data));
  } catch (e) { console.error('quality_confirmed parse error:', e); }
});
```

**回调注册/注销逻辑**（在现有 `subscribeSession` 方法内，与 chat/agent 回调同一模式）:

```typescript
if (onQualityResult) {
  if (!this.sessionQualityResultCallbacks.has(sessionId))
    this.sessionQualityResultCallbacks.set(sessionId, new Set());
  this.sessionQualityResultCallbacks.get(sessionId)!.add(onQualityResult);
}
// 同理 onSectionQuality, onPreviewRefresh, onQualityConfirmed
```

**注销时清理**（在 unsubscribe 函数内）:

```typescript
// 在现有的 chat/agent 清理之后
const qrc = this.sessionQualityResultCallbacks.get(sessionId);
if (qrc) qrc.delete(onQualityResult!);
// 同理其他三个回调
// 当所有回调集合为空时，关闭连接
```

> **共享连接模式**: 多个组件（MainLayout、DocumentPreview、ChatPanel）对同一 sessionId 调用 `subscribeSession()` 时，复用已有 EventSource，通过引用计数（`sessionRefCounts` Map）管理生命周期。仅当引用计数归零时才关闭连接。`unsubscribeSession()` 减少引用计数而非直接关闭。

> **字段名映射**: 后端 `push_quality_result` 推送的数据中章节评分字段名为 `section_results`，前端 `QualityStateData` 使用 `section_scores`。前端 SSE 回调中需做映射：
> ```typescript
> onQualityResult?: (data: QualityResultEventData) => {
>   const mapped: QualityStateData = {
>     ...data,
>     section_scores: data.section_results || {},
>   };
>   delete (mapped as any).section_results;
>   // 写入 store
> }
> ```

---

### 6.2 修改 `useProgress.ts` — 扩展 `UseSessionStreamOptions`

**文件**: `web/src/hooks/useProgress.ts` (L219)

```typescript
export interface QualityResultEventData {
  session_id: string;
  overall_score: number;
  overall_status: string;
  section_results: Record<string, any>;
  issues: any[];
  timestamp: string;
}

export interface SectionQualityEventData {
  session_id: string;
  section_name: string;
  data: any;
}

export interface PreviewRefreshEventData {
  session_id: string;
  preview_url: string;
  version_id: string;
  timestamp: string;
}

export interface QualityConfirmedEventData {
  session_id: string;
  final_document_path: string;
  timestamp: string;
}

export interface UseSessionStreamOptions {
  onChatResponse?: (data: ChatResponseData) => void;
  onAgentMessage?: (data: AgentMessageData) => void;
  onQualityResult?: (data: QualityResultEventData) => void;
  onSectionQuality?: (data: SectionQualityEventData) => void;
  onPreviewRefresh?: (data: PreviewRefreshEventData) => void;
  onQualityConfirmed?: (data: QualityConfirmedEventData) => void;
}
```

**在 `useSessionStream()` 内**（L240 `sseManager.subscribeSession` 调用处），将新增回调透传：

```typescript
const unsubscribe = sseManager.subscribeSession(
  sessionId,
  (data) => { if (onChatResponseRef.current) onChatResponseRef.current(data); },
  (data) => { if (onAgentMessageRef.current) onAgentMessageRef.current(data); },
  (data) => { if (onQualityResultRef.current) onQualityResultRef.current(data); },
  (data) => { if (onSectionQualityRef.current) onSectionQualityRef.current(data); },
  (data) => { if (onPreviewRefreshRef.current) onPreviewRefreshRef.current(data); },
  (data) => { if (onQualityConfirmedRef.current) onQualityConfirmedRef.current(data); },
);
```

同时为新增的 4 个回调添加 `useRef` 模式（与 `onChatResponseRef` 同模式）。

---

### 6.3 修改 `useSessionStore.ts` — 新增 qualityState 字段

**文件**: `web/src/store/useSessionStore.ts`

**新增类型**:

```typescript
export interface QualityIssueData {
  id: string;
  type: 'completeness' | 'accuracy' | 'consistency' | 'format' | 'hallucination';
  severity: 'high' | 'medium' | 'low';
  message: string;
  section: string;
  state: 'open' | 'dismissed' | 'revising' | 'resolved' | 'max_retries_reached';
  revision_count?: number;
}

export interface SectionQualityData {
  score: number;
  status: 'passed' | 'warning';
  issues: QualityIssueData[];
}

export interface VersionInfoData {
  id: string;
  created_at: string;
  overall_score: number;
  label: string;
}

export interface QualityStateData {
  phase: 'reviewing' | 'revising' | 'confirmed';
  overall_score: number;
  overall_status: 'passed' | 'warning';
  section_scores: Record<string, SectionQualityData>;
  version_stack: VersionInfoData[];
  current_version: string;
}
```

**`SessionCache` 新增字段** (L21 区域):
```typescript
qualityState: QualityStateData | null;
pendingInput: string | null;
```

**`emptyCache()` 初始化** (L156 区域):
```typescript
qualityState: null,
pendingInput: null,
```

**`partialize` 中排除**（与 result/agentMessages 同样处理，避免持久化过大数据）:
```typescript
qualityState: undefined,
pendingInput: undefined,
```

**`syncActive` 过滤逻辑修改** — 允许 `null` 覆盖但继续过滤 `undefined`：

```typescript
syncActive: (patch: Partial<SessionCache>) => {
  const { activeId, sessions } = get();
  const cleanPatch = Object.fromEntries(
    Object.entries(patch).filter(([, v]) => v !== undefined)
  ) as Partial<SessionCache>;
  // ... 其余逻辑不变
}
```

> **说明**: 原过滤 `v !== undefined` 已正确允许 `null` 通过。v3 的问题是清除时用了 `undefined` 而非 `null`。v4 修正清除代码使用 `null`，过滤逻辑无需修改。

---

### 6.4 修改 `types/api.ts` — 扩展 SSEMessage event 类型

**文件**: `web/src/types/api.ts` (L202)

```typescript
export interface SSEMessage {
  event: 'progress' | 'phase_start' | 'phase_complete' | 'error' | 'complete'
       | 'chat_response' | 'agent_message' | 'heartbeat' | 'connected' | 'message' | 'cancelled'
       | 'quality_result' | 'section_quality' | 'preview_refresh' | 'quality_confirmed';
  data: ProgressData | PhaseData | ErrorData | CompleteData | ChatResponseData | AgentMessageData | QualityResultEventData | SectionQualityEventData | PreviewRefreshEventData | QualityConfirmedEventData | any;
}
```

---

### 6.5 修改 `ChatInput.tsx` — 新增 `pendingInput` prop

**文件**: `web/src/components/chat/ChatInput.tsx`

当前 `ChatInput` 使用 `const [text, setText] = useState('')`（L49），不对外暴露 setText。需新增 prop 以支持质检面板预填：

```typescript
interface ChatInputProps {
  onSend: (text: string, attachments?: File[], model?: string) => void;
  onCancel?: () => void;
  disabled?: boolean;
  placeholder?: string;
  isLoading?: boolean;
  isNetworkBusy?: boolean;
  isWaitingForReply?: boolean;
  isRunning?: boolean;
  pendingInput?: string;
}
```

在组件内部添加 effect：

```typescript
useEffect(() => {
  if (pendingInput !== undefined && pendingInput !== '') {
    setText(pendingInput);
  }
}, [pendingInput]);
```

> **注意**: `pendingInput` 清除见 6.6，使用 `null` 而非 `undefined`。

---

### 6.6 新增前端组件

| 文件 | 说明 |
|------|------|
| `web/src/components/quality/QualityPanel.tsx` | 质量面板主组件 |
| `web/src/components/quality/IssueRow.tsx` | Issue 交互行，点击「发起修订」预填 ChatInput |
| `web/src/components/quality/RevisionHintBar.tsx` | 修订提示条，5秒自动消失 |
| `web/src/components/quality/ConfirmDeliveryDialog.tsx` | 确认交付对话框 |
| `web/src/components/quality/SectionNavBar.tsx` | 章节导航条，利用已有 `<section id>` 锚点跳转 |

**IssueRow「发起修订」预填机制**:

```typescript
function handleStartRevision(issue: QualityIssueData) {
  const input = `【质检问题】${issue.section}: ${issue.message}\n请帮我修订这部分内容。`;
  useSessionStore.getState().syncActive({ pendingInput: input });
}
```

ChatPanel 读取 `pendingInput` 并传递给 ChatInput：

```typescript
const pendingInput = useSessionStore((s) => {
  const sid = s.activeId;
  return sid ? s.sessions[sid]?.pendingInput : undefined;
});

useEffect(() => {
  if (pendingInput) {
    // 延迟 100ms 清空，确保 ChatInput 已消费（BUG-8 修复）
    const timer = setTimeout(() => {
      useSessionStore.getState().syncActive({ pendingInput: null });
    }, 100);
    return () => clearTimeout(timer);
  }
}, [pendingInput]);
```

ChatInput 内部用 `consumedRef` 防重复消费：

```typescript
const consumedRef = useRef(false);
useEffect(() => {
  if (pendingInput && !consumedRef.current) {
    setText(pendingInput);
    consumedRef.current = true;
  }
  if (!pendingInput) {
    consumedRef.current = false;
  }
}, [pendingInput]);
```

> **v4 修复**: 使用 `null` 而非 `undefined` 清除 `pendingInput`。`syncActive` 的过滤逻辑过滤 `undefined` 但允许 `null`（见 6.3 `syncActive` 修改）。

**RevisionHintBar 逻辑**:

- 收到 `preview_refresh` SSE 后显示
- 包含：修订完成提示 + 评分变化 + 「一键回滚」按钮
- 5 秒后自动消失
- `onDismiss` 回调用 `useRef` 存储，避免无限重渲染循环（BUG-2 修复）

**DocumentPreview 预览刷新**:

收到 `preview_refresh` SSE 后重新加载 iframe（通过 `iframeKey` state 触发完整重新挂载，避免缓存问题）：

```typescript
const [iframeKey, setIframeKey] = useState(0);
// preview_refresh callback:
setIframeKey(prev => prev + 1);
```

**SectionNavBar 跳转**:

由于 HTML 中已有 `<section id="{section.id}">`，点击导航条中的章节名时：

```typescript
// 优先用 section.id 匹配
let targetEl = iframe.contentWindow?.document?.getElementById(sectionId);
// Fallback: 用 heading text 匹配（BUG-10 修复）
if (!targetEl) {
  const headings = iframe.contentWindow?.document?.querySelectorAll('h1, h2, h3');
  for (const h of headings || []) {
    if (h.textContent?.trim() === sectionName) {
      targetEl = h.closest('section');
      break;
    }
  }
}
targetEl?.scrollIntoView({ behavior: 'smooth' });
```

注意：跨域 iframe 无法访问 contentWindow.document。如果 HTML 由同源 `/api/v1/html-reports/` 提供则无此问题。若存在跨域，改用 `iframe.src = url + #sectionId` 配合锚点滚动。

---

### 6.7 修改 `MainLayout.tsx` — 集成质量面板

**文件**: `web/src/components/layout/MainLayout.tsx`

在现有布局中，当 `qualityState` 不为 null 且 `phase !== 'confirmed'` 时，在报告预览右侧展示 `QualityPanel`。

**MainLayout 也订阅 `quality_result` + `quality_confirmed` SSE**（BUG-7 修复）：当 `previewVisible=false` 时 DocumentPreview 不挂载，其 SSE 回调不注册。MainLayout 需独立订阅以确保 `qualityState` 始终更新。

---

### 6.8 修改 `DocumentPreview.tsx` — 集成导航条 + 提示条

**文件**: `web/src/components/preview/DocumentPreview.tsx`

- iframe 上方增加 `SectionNavBar`（warning 高亮 + 锚点跳转 + heading text fallback）
- 预览工具栏下方增加 `RevisionHintBar`（5秒自动消失 + 回滚按钮 + useRef callback pattern）
- 监听 `preview_refresh` SSE 事件刷新 iframe（通过 `iframeKey` state 触发重新挂载）
- rollback 成功后 `setRevisionHintVisible(false)` 隐藏提示条（BUG-9 修复）

---

## 7. 对话式修订集成

### 7.1 完整流程

1. 用户在质检面板点击 issue 的「发起修订」按钮
2. 前端将 issue 描述填入聊天输入框（通过 `pendingInput` prop）
3. 用户可在此基础上补充具体要求后发送
4. 发送走现有 `POST /api/v1/research/interact` 端点
5. 后端 `_llm_converse()` 处理对话，识别修订意图后调用 `_handle_v2_revision()`
6. `_handle_v2_revision()` 内执行修订联动逻辑（5.7）
7. 修订完成后，后端自动重检 + 推送 SSE 事件

---

## 8. 版本快照与回滚

### 8.1 快照管理（已实现 ✅）

`src/core/quality/quality_snapshot_manager.py` 已完整实现。

### 8.2 版本栈更新

在 `_handle_v2_revision()` 中创建快照后更新版本栈（5.7 中已包含）。

### 8.3 回滚流程

见 5.5 中 `_handle_quality_rollback()` 实现。

---

## 9. 排版错乱处理

### 9.1 预览自检（已实现 ✅）

`src/core/quality/preview_health.py` 已实现 `check_preview_health(html_path: str, old_html_length: int = 0)`。

注意：第一个参数是**当前** HTML 文件路径，第二个是**旧** HTML 文件长度（用于膨胀检测）。

### 9.2 修订后自检

在 `_post_revision_recheck()` 中已集成（5.7）。

### 9.3 修订提示条

前端收到 `preview_refresh` 后显示 `RevisionHintBar`。

---

## 10. 并发与幂等

### 10.1 修订锁

对话修订走现有 `_pending_section_injects` 队列，已有 `_inject_in_progress` 防重入。

### 10.2 质检操作锁

使用 `asyncio.Lock`（复用 `ResearchAPI._session_locks` 模式），确保异步并发下原子性：

```python
def _get_quality_lock(self, session_id: str) -> asyncio.Lock:
    key = f"_quality_{session_id}"
    if key not in self._session_locks:
        self._session_locks[key] = asyncio.Lock()
    return self._session_locks[key]

async def handle_quality_action(self, request: QualityActionRequest) -> Dict[str, Any]:
    session_id = request.session_id
    lock = self._get_quality_lock(session_id)
    if lock.locked():
        return {"error": "Concurrent operation in progress", "error_code": "CONFLICT"}
    async with lock:
        session = session_manager.get(session_id)
        if not session:
            return {"error": "Session not found", "error_code": "SESSION_NOT_FOUND"}
        # ... action 分发 ...
```

### 10.3 幂等性

- 重复 dismiss → 幂等
- 重复 rollback → 幂等
- 重复 recheck → 幂等
- 重复 confirm → 幂等

---

## 11. 修订次数限制

| 限制项 | 阈值 | 实现 |
|--------|------|------|
| 单 issue 修订轮次 | 3次 | `QualityIssue.revision_count` 字段 |
| 总修订轮次 | 10次 | `len(version_stack)` 检查 |
| 版本栈深度 | 10个 | `QualitySnapshotManager.cleanup_old(keep=10)` |

---

## 12. 错误处理

| 错误场景 | 处理 |
|----------|------|
| 修订服务调用失败 | `SessionStreamer.push_agent_message()` 推送错误，issue 从 `revising` 回退为 `open` |
| 预览生成失败 | 推送 `agent_message` 警告 |
| 排版自检失败 | 推送 `agent_message` 警告 + 提示条显示回滚选项 |
| 修订超限 | issue 标记 `max_retries_reached` |
| 并发操作冲突 | `asyncio.Lock` 拦截，返回 CONFLICT 409 |
| 快照恢复失败 | 返回错误，提示刷新 |
| 重检失败 | 保持当前评分不变，推送通知 |

---

## 13. 文件变更清单

### 新增文件（已实现）

| 文件 | 说明 |
|------|------|
| `web/src/components/quality/QualityPanel.tsx` | ✅ 质量面板主组件（含内联 IssueRow + ConfirmDeliveryDialog） |
| `web/src/components/quality/SectionNavBar.tsx` | ✅ 章节导航条（warning 高亮 + 锚点跳转） |
| `web/src/components/quality/RevisionHintBar.tsx` | ✅ 修订提示条（5秒自动消失 + 回滚按钮 + 排版警告） |

### 新增文件（待实现）

（无）

### 修改文件（已实现）

| 文件 | 变更 |
|------|------|
| `src/core/session_streamer.py` | ✅ L258-264: 修复 `push_quality_confirmed()` bug；L232-238: `push_section_quality` 补充 `_persist_event` + 日志；L241-249: `push_preview_refresh` 补充 `_persist_event` + 日志 |
| `src/core/quality/quality_state.py` | ✅ `QualityIssue.state` 添加 `"accepted"`；新增 `revision_count: int = 0` 字段；新增 `QUALITY_PASS_THRESHOLD = 60` 常量；`SectionScore.status` Literal 添加 `"empty"` |
| `src/agents/fixed_agents/quality_check_agent.py` | ✅ `check_by_sections()` L913/952: 为 section_issues + overall_issues 添加稳定 id + section + state；L876: 添加 `import re` |
| `src/api/research_api.py` | ✅ 删除模块级 `QualityActionRequest`/`handle_quality_action`/`get_quality_state`，迁移为 ResearchAPI 方法；新增 `handle_quality_action()`/`get_quality_state()` + 5 个 handler + `_recheck_quality()` + `_post_revision_recheck()` + `_get_quality_lock()`；`_handle_v2_revision()` L2345 前插入快照+版本栈逻辑，各修订成功分支后调用 `_post_revision_recheck()`；`_confirm_v2_revision()` accept 分支后也调用 `_post_revision_recheck()`；修订次数限制：单 issue `MAX_ISSUE_REVISIONS=3` + 总修订 `MAX_TOTAL_REVISIONS=10`（`version_stack` 长度检查）；`_session_id` 字段；keyword cancel/pause 检测；ConversationToolSet async + OpenAI function-calling 格式；`_post_revision_recheck()` 内部获取 `quality_lock`；`handle_quality_action()` 删除 TOCTOU `lock.locked()` 检查 |
| `web/src/types/api.ts` | ✅ 新增 QualityIssueData/SectionScoreData/QualityStateData/PendingInputData/VersionInfoData 类型；SSEMessage.event 扩展联合类型；`QualityResultEventData.phase` 改为联合类型 |
| `web/src/hooks/useProgress.ts` | ✅ `UseSessionStreamOptions` 扩展 4 个质量回调（含具体事件类型）；`useSessionStream()` 透传新回调到 `sseManager.subscribeSession()` |
| `web/src/store/useSessionStore.ts` | ✅ `SessionCache` 新增 `qualityState` + `pendingInput`；`emptyCache()` 初始化；`partialize` 排除；`merge` 函数用 emptyCache 填充缺失字段；清除 `pendingInput` 用 `null` 不用 `undefined` |
| `web/src/components/chat/ChatInput.tsx` | ✅ 新增 `pendingInput?: string` prop + useEffect 监听；**mounted guard** 修复 hydration mismatch（provider/model Select + 底部提示延迟渲染） |
| `web/src/components/chat/ChatPanel.tsx` | ✅ 读取 `pendingInput` 传给 ChatInput；清除用 `null`；timer ref + cleanup 防竞态 |
| `web/src/components/layout/MainLayout.tsx` | ✅ 集成 QualityPanel（w-80 右侧边栏）；移除 `as any`，用 `QualityStateData['phase']` 类型断言 |
| `web/src/components/preview/DocumentPreview.tsx` | ✅ revision phase 完成后自动 refetch；FinalizeToolbar（Convert→Download 两步流程）；SectionNavBar 集成；RevisionHintBar 集成；preview_refresh SSE → iframeKey 刷新；rollback 时 setRevisionHintVisible(false)；移除 `as any`；预计算 `sectionTitleMap` Map |
| `web/src/lib/sse.ts` | ✅ 共享连接模式 + 引用计数；关闭条件改为 `newRefCount <= 0 && totalRemaining === 0` |
| `web/src/components/quality/QualityPanel.tsx` | ✅ 质量面板主组件；`section_scores || {}` 空值守卫；移除 `as any` |

### 修改文件（待实现）

（无 — P1-1/P1-2 已完成，SectionNavBar 和 RevisionHintBar 已集成到 DocumentPreview）

### 无需修改的文件

| 文件 | 说明 |
|------|------|
| `src/core/quality/quality_snapshot_manager.py` | ✅ 完整实现 |
| `src/core/quality/preview_health.py` | ✅ 完整实现 |
| `src/core/quality/__init__.py` | ✅ 已有 |
| `src/api/main.py` | ✅ 路由已注册，调用方式随 ResearchAPI 方法迁移自动兼容 |
| `src/content/content_orchestrator.py` | ✅ **HTML 锚点已存在**（L734 `<section id="{section.id}">`），无需修改 |

---

## 14. 实施优先级与进度

| 优先级 | 内容 | 依赖 | 涉及文件 | 状态 |
|--------|------|------|----------|------|
| **P0-1** | 修复 `push_quality_confirmed()` bug + 补充 `push_preview_refresh`/`push_section_quality` 持久化 | 无 | `session_streamer.py` | ✅ 已实现 |
| **P0-2** | `QualityIssue` 新增 `revision_count`/`accepted` 字段 + `QUALITY_PASS_THRESHOLD` 常量 | 无 | `quality_state.py` | ✅ 已实现 |
| **P0-3** | `check_by_sections()` 生成稳定 issue ID | 无 | `quality_check_agent.py` | ✅ 已实现 |
| **P0-4** | 迁移 `handle_quality_action`/`get_quality_state` 到 ResearchAPI + 扩展 `QualityActionRequest`（保留 `data` 字段）+ 实现 5 个 handler + `_recheck_quality()` + `_get_quality_lock()` | P0-2, P0-3 | `research_api.py` | ✅ 已实现 |
| **P0-5** | `_handle_v2_revision()` 修订联动 + `_post_revision_recheck()` + `_confirm_v2_revision()` 集成 | P0-4 | `research_api.py` | ✅ 已实现 |
| **P0-6** | 前端 SSE 扩展 + qualityState/pendingInput store + 字段映射 `section_results`→`section_scores` | 无（可与后端并行） | `useProgress.ts`, `useSessionStore.ts`, `api.ts` | ✅ 已实现 |
| **P0-7** | QualityPanel + ChatInput pendingInput + hydration fix + ConfirmDeliveryDialog（含 pending_issues 二次确认） | P0-6 | `QualityPanel.tsx`, `ChatInput.tsx`, `ChatPanel.tsx`, `MainLayout.tsx` | ✅ 已实现 |
| **BF-1** | React hydration mismatch 修复（useSettingsStore SSR/客户端值不一致） | 无 | `ChatInput.tsx`, `useSessionStore.ts` | ✅ 已实现 |
| **P1-1** | SectionNavBar + DocumentPreview 集成 | P0-7 | `SectionNavBar.tsx`, `DocumentPreview.tsx` | ✅ 已实现 |
| **P1-2** | RevisionHintBar + preview_refresh 刷新 + 排版保护 | P0-5, P0-7 | `RevisionHintBar.tsx`, `DocumentPreview.tsx` | ✅ 已实现 |
| **P2-1** | 修订次数限制（单 issue `MAX_ISSUE_REVISIONS=3` + 总修订 `MAX_TOTAL_REVISIONS=10`） | P0-5 | `research_api.py` | ✅ 已实现 |

### 已实现文件变更清单

#### 后端

| 文件 | 实际变更 |
|------|----------|
| `src/core/session_streamer.py` | ✅ L258-264 残留代码删除，替换为正确 `_persist_event` + timestamp；`push_section_quality` 补充 `_persist_event` + 日志；`push_preview_refresh` 补充 `_persist_event` + 日志 |
| `src/core/quality/quality_state.py` | ✅ `QualityIssue.state` Literal 添加 `"accepted"`；新增 `revision_count: int = 0`；新增 `QUALITY_PASS_THRESHOLD = 60` 常量 |
| `src/agents/fixed_agents/quality_check_agent.py` | ✅ L913+: 为 section_issues 添加 `id`/`section`/`state`；L952+: 为 overall_issues 添加 `id`/`section`/`state` |
| `src/api/research_api.py` | ✅ 删除模块级 `handle_quality_action`/`get_quality_state`，迁移为 ResearchAPI 方法；扩展 `QualityActionRequest`（issue_id/version_id/section_name）；5 个 handler；`_recheck_quality()`；`_post_revision_recheck()`；`_get_quality_lock()`；`_handle_v2_revision()` 修订联动；`_confirm_v2_revision()` 集成；`_session_id` 字段；keyword cancel/pause 检测；ConversationToolSet async + OpenAI function-calling 格式 |

#### 前端

| 文件 | 实际变更 |
|------|----------|
| `web/src/types/api.ts` | ✅ 新增 QualityIssueData/SectionScoreData/QualityStateData/PendingInputData/VersionInfoData 类型；SSEMessage.event 扩展 |
| `web/src/hooks/useProgress.ts` | ✅ UseSessionStreamOptions 扩展 4 个质量回调；导入新类型 |
| `web/src/store/useSessionStore.ts` | ✅ SessionCache 新增 qualityState + pendingInput；emptyCache() 初始化；partialize 排除；merge 函数（用 emptyCache 填充缺失字段）；清除用 null |
| `web/src/components/chat/ChatInput.tsx` | ✅ pendingInput prop + useEffect 监听；**mounted guard** 修复 hydration mismatch（provider/model Select + 底部提示延迟渲染） |
| `web/src/components/chat/ChatPanel.tsx` | ✅ 读取 pendingInput 传给 ChatInput；清除用 null |
| `web/src/components/layout/MainLayout.tsx` | ✅ 集成 QualityPanel（w-80 右侧边栏，qualityState 存在且 phase≠confirmed 时显示） |
| `web/src/components/quality/QualityPanel.tsx` | ✅ 新增：质量面板主组件（评分、问题列表、确认交付、版本历史） |
| `web/src/components/quality/SectionNavBar.tsx` | ✅ 新增：章节导航条（warning 高亮 + 锚点跳转 + heading text fallback） |
| `web/src/components/quality/RevisionHintBar.tsx` | ✅ 新增：修订提示条（5秒自动消失 + 回滚按钮 + 排版警告 + useRef callback pattern） |
| `web/src/components/preview/DocumentPreview.tsx` | ✅ revision phase 完成后自动 refetch；FinalizeToolbar（Convert→Download 两步流程）；SectionNavBar 集成（warning 高亮 + 锚点跳转）；RevisionHintBar 集成（5秒自动消失 + 回滚按钮）；preview_refresh SSE → iframeKey 刷新；rollback 时 setRevisionHintVisible(false) |

#### 已实现的前端组件（P1 补充）

所有前端组件已完成实现，无未实现项。

| 组件 | 状态 | 说明 |
|------|------|------|
| `QualityPanel.tsx` | ✅ | 质量面板主组件（含内联 ConfirmDeliveryDialog） |
| `SectionNavBar.tsx` | ✅ | 章节导航条（warning 高亮 + 锚点跳转 + heading text fallback） |
| `RevisionHintBar.tsx` | ✅ | 修订提示条（5秒自动消失 + 回滚按钮 + useRef callback pattern） |