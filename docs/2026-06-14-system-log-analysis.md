# 2026-06-14 系统日志分析报告

> 分析日期: 2026-06-14
> 日志来源: `logs/app.log` (39.7 MB, 274,021 行)
> 06-14 有效行数: 13,286 行
> 分析人: opencode

## 1. 概览

| 指标 | 数值 |
|------|------|
| 日志总量 | 13,286 行 |
| INFO | 10,420 |
| WARNING | 2,565 |
| ERROR | 297 |
| 活跃 Session | 5 个 (06-14 被修改) |
| 今日新建 Session | 1 个 (`ses_cc1b9ce3`) |

## 2. 活跃 Session 时间线

### ses_cc1b9ce3 (今日新建, completed_with_warnings)

```
17:08:20  Session 创建
17:09:23  检测到深度研究关键词, 进入 framework 模式, 生成 8 个 section 框架
17:09:30  ResearchExecutor 启动, 开始执行 orchestrator
17:09:42  LLM intent 分析失败 (JSON 解析失败)
17:10:05  LLM JSON 解析再次失败
17:10:07  CR-FIX-2 磁盘恢复失败: 'str' object has no attribute 'exists'
17:10:07  data_boundary_controller: 8 个 agent 均未找到对应章节 (WARNING)
17:10:08  开始出现 asyncio "Task exception was never retrieved" (284 次)
17:10:16  搜索质量过滤开始工作 (20→17→4 结果)
17:10:32  搜索质量过滤完成, 但大量 asyncio 错误
17:10:37  scrapling 废弃 API 警告密集出现
18:16:23  quality_result 推送 (2次)
18:16:23  chat_response 推送
18:16:23  Preview 复制完成
18:16:23  Task 标记完成
18:16:23  Research 完成: 8 agents, status=completed_with_warnings, quality_score=40.9
```

**执行耗时**: 约 67 分钟 (17:09:30 → 18:16:23)

**质量检查结果** (quality_score=40.9):
- 5 条 accuracy/low: 数值重复出现 (130.0×27次, 23.4×15次, 21.45×14次, 70.05×13次, 436.43×13次)
- 2 条 format/low: 缺少顶级标题, 8 段过长段落
- 2 条 accuracy/medium: 占位符重复 ('37.52亿元'×6次无变化, '70.05亿元'×4次无变化)
- 1 条 accuracy/medium: 占位符重复 ('70.05亿元'×3次无变化)

### ses_34d79000 (06-11 创建, 今日暂停)

```
17:08:34  SSE 断开连接 → 触发延迟暂停
17:08:34  Cancel snapshot 保存: 0 completed, 8 pending
17:08:34  PAUSE 命令发出
```

**问题**: 8 个 section 均为 pending (0 completed)，说明研究刚开始就被暂停。引擎已死，无法恢复。

### ses_af9234c2, ses_cda7392e, ses_89531f60

06-14 仅被读取 (session_manager 加载)，无新业务逻辑执行。均为历史卡死 session。

## 3. 关键异常分析

### 3.1 asyncio "Task exception was never retrieved" — 284 次

**时间窗口**: 17:10:08 — 17:10:37 (约 30 秒内密集出现)

**上下文**: 与 `ses_cc1b9ce3` 的 agent 执行阶段完全重合。agent 在执行搜索+LLM 推理时，大量异步任务异常未被捕获。

**关联事件**:
- 17:10:08: `scrapling` 废弃 API 调用 → 依赖库内部抛出异常
- 17:10:16: 搜索连接失败 (`DDGS failed: ConnectError`)
- 17:10:32: 密集 asyncio 错误爆发 (18 秒内 30+ 次)

**根因推测**: `scrapling` 库的 `AsyncFetcher` 废弃调用 + 网络连接失败导致异步任务抛出异常，但调用方未 await 或未添加异常回调，异常被 asyncio 事件循环丢弃。

**影响**: 不影响最终结果 (research 仍完成)，但可能导致部分搜索结果丢失，降低报告数据质量。

### 3.2 data_boundary_controller 章节匹配失败 — 8/8

```
phase_1_agent_0 ~ phase_1_agent_7: 均未找到对应章节
```

**根因**: section 命名不匹配。框架生成的 section ID 格式为 `section_0_核心财务指标与盈利能力`，但 agent 分配的 aspects 格式可能不同，导致 data boundary 无法建立。

**影响**: agent 之间无数据共享边界，可能产生重复搜索或数据冲突。

### 3.3 CR-FIX-2 磁盘恢复失败

```
CR-FIX-2 disk recovery failed: 'str' object has no attribute 'exists'
```

**根因**: 磁盘恢复逻辑期望接收 `Path` 对象，但实际收到了 `str`。类型检查缺失。

**影响**: checkpoint 恢复失败，无法利用历史缓存数据。

### 3.4 LLM JSON 解析失败 — 2 次

```
17:09:42  LLM intent analysis failed: Failed to parse LLM JSON
17:10:05  Failed to parse LLM JSON: Expecting value: line 1 column 1 (char 0)
```

**根因**: LLM 返回空内容或非 JSON 格式。deepseek-v4-flash 模型偶尔输出不稳定。

**影响**: intent 分析和 task 结构解析失败，降级到默认路径，不影响最终完成。

### 3.5 搜索连接失败

```
DDGS failed: ConnectError (brave.com, yahoo.com)
```

**根因**: 外部搜索引擎 API 不稳定，Brave 和 Yahoo 连接超时。

**影响**: 搜索结果减少，可能影响数据覆盖度，直接导致 quality_score 偏低。

### 3.6 quality_result 推送 2 次

```
18:16:23,914  Session stream quality_result pushed: ses_cc1b9ce3
18:16:23,920  Session stream quality_result pushed: ses_cc1b9ce3
```

**根因**: `research_executor.py` 中存在两条推送路径:
- 路径 1: `orchestrator_result.status == "completed_with_warnings"` 时推送 (`research_executor.py:411-417`)
- 路径 2: `_q_score > 0 or _q_issues` 时推送 (`research_executor.py:453-459`)

当 status=`completed_with_warnings` 时两条路径都会触发，导致重复推送。

**影响**: 前端可能收到两次 quality_result SSE 事件，第二次会覆盖第一次。当前无功能影响，但浪费资源且可能导致 UI 闪烁。

## 4. Session 状态一致性

### 4.1 ses_cc1b9ce3: session 文件 vs API 返回不一致

| 属性 | Session 文件 | API 返回 |
|------|-------------|---------|
| mode | `research` | N/A (不暴露) |
| state_machine | `executing` | N/A |
| research_result | `None` | `completed_with_warnings` |
| status (API) | — | `completed` |

**问题**: Session 文件中 `research_result` 为 None，但 API 返回 `completed_with_warnings`。这说明 `research_result` 写入后 session 文件未被及时持久化，或者 API 从其他来源 (如 ProgressStreamer) 读取了状态。

### 4.2 ses_34d79000: 暂停后无法恢复

- state_machine=`paused`, research_result=None
- 8 个 section 全部 pending
- Cancel snapshot 已保存但引擎已死
- `resume_research` 将尝试 snapshot 恢复，若无 snapshot 则返回 `failed`

## 5. 历史卡死 Session 统计

| 类型 | 数量 | 最久时长 | 说明 |
|------|------|---------|------|
| 卡死 executing (引擎死) | 4 | 390.7h (16天) | 用户看到"一直在运行" |
| 卡死 paused 无 result | 6 | 775.7h (32天) | 无法恢复 |
| completed 但无 result | 4 | — | 结果丢失 |
| failed 无详细错误 | 14 | — | 错误信息不足 |
| mode 未切换到 chat | 14 | — | B3 bug 历史痕迹 |
| paused+completed+mode!=chat | 2 | — | B3 bug 历史痕迹 |

## 6. B1-B7 修复验证

| 验证项 | 方式 | 结果 |
|--------|------|------|
| B1 (get_preview) | API 调用 `GET /api/v1/research/preview/ses_cc1b9ce3` | ✅ html_content=51160 字节 |
| B2 (has_valid_result) | API 调用 `GET /api/v1/research/ses_cc1b9ce3` | ✅ preview_url 非空 |
| B4 (完成消息) | 日志中 chat_response 推送 | ✅ 已区分 ⚠️/✅ |
| B3 (chat mode) | ses_cc1b9ce3 尚未触发 (session 文件 mode=research) | ⏳ 需用户下次发消息触发 |
| B5 (resume) | ses_34d79000 已暂停但无 result | ⏳ 无 completed_with_warnings 可验证 |
| B6+B7 (inject) | ses_cc1b9ce3 未触发 inject | ⏳ 需用户请求追加章节 |

## 7. 建议优先级

| 优先级 | 问题 | 建议 |
|--------|------|------|
| **P0** | quality_result 重复推送 | 合并两条推送路径，避免 `completed_with_warnings` 时重复 |
| **P1** | asyncio Task exception 未捕获 | 在 agent 执行层添加异常回调或 try/except 包裹 |
| **P1** | 僵尸 session 无超时清理 | 添加引擎心跳机制 + executing 状态超时自动降级为 failed |
| **P1** | data_boundary_controller 章节匹配全部失败 | 统一 section ID 命名规范 |
| **P2** | CR-FIX-2 磁盘恢复类型错误 | 添加 `Path()` 转换 |
| **P2** | session 文件持久化不及时 | 检查 PersistentSessionDict 在 research_result 写入后的 flush 时机 |
| **P2** | 搜索连接不稳定 | 添加重试机制或降级策略 |
