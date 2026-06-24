# 2026-06-14 系统深度分析报告

> 分析日期: 2026-06-15
> 日志来源: `logs/app.log` (39.7 MB, 274,021 行)
> 06-14 有效行数: 13,286 行
> 分析人: opencode

## 1. 概览

| 指标 | 数值 |
|------|------|
| 日志总量 | 13,286 行 |
| INFO | 10,420 |
| WARNING | 2,565 (含 scrapling 废弃 API 2,133 条, 业务 WARNING 432 条) |
| ERROR | 297 (含 asyncio Task exception 284 条) |
| 今日新建 Session | 1 个 (`ses_cc1b9ce3`) |
| 有业务逻辑的 Session | 2 个 (`ses_cc1b9ce3` 13行, `ses_34d79000` 3行) |
| 日志中出现但仅被 session_manager 加载的 Session | 47 个 |
| 服务器重启 | 1 次 (15:59:40 shutdown, 16:00:56 restart) |

## 2. 事件时间线

### 2.1 服务器重启

```
15:59:39  SSE 断开 (ses_34d79000) — 服务器正在 shutdown
15:59:40  Zensers API shutting down
15:59:40  DreamModeScheduler shut down
15:59:40  WARNING: Failed to cancel ResearchAPI background tasks: type object 'ResearchAPI' has no attribute '_background_tasks'
16:00:56  Zensers API starting... (recovered 5 sessions)
16:00:56  ProgressStreamer recovered 3 task states from disk
16:01:38  Loaded session from disk: ses_89531f60
```

### 2.2 ses_cc1b9ce3 (今日新建, completed_with_warnings)

```
17:08:20  Session 创建
17:09:23  检测到深度研究关键词, 进入 framework 模式, 生成 8 个 section 框架
17:09:30  ResearchExecutor 启动, 开始执行 orchestrator
17:09:42  LLM intent 分析失败 (JSON 解析失败, 第1次)
17:10:05  LLM JSON 解析失败 (第2次)
17:10:07  CR-FIX-2 磁盘恢复失败: 'str' object has no attribute 'exists' (第1次)
17:10:07  data_boundary_controller: 8 个 phase_1 agent 均未找到对应章节
17:10:08  开始出现 asyncio "Task exception was never retrieved" (284 次, 持续至 18:03:42)
17:10:08  phase_1_agent_0~7 全部启动, data=[], canonical_data={}, 无任何初始数据
17:10:16  scrapling 废弃 API 警告开始出现 (共 2,133 条, 持续至 18:05:15)
17:10:16  搜索质量过滤: 20→17 results
17:10:18  DDGS failed: ConnectError (brave)
17:10:32  搜索质量过滤: 17→4 results; 16→4, 20→12, 20→10 等多轮过滤
17:10:39  LLM JSON 解析失败 (第3次)
17:14:49  首次出现 10→0 完全过滤 (30 次)
17:14~25  phase_1 agent 搜索+LLM 执行阶段, 大量搜索连接失败
17:25:56  Batch 1 质量检查失败: score=26.9/75.0
17:26:43  Retry 1/3: 185 data points 注入到 8 个 phase_1 agent
17:26:43  data_boundary 再次全部失败 (8 WARNING)
17:42:04  Retry 2/3: 359 data points 注入
17:55:42  Retry 3/3: 603 data points 注入
18:05:27  Batch 1 retry exhausted, score 仍为 26.9
18:05:28  Batch 2 (phase_2) 开始, data_boundary 再次 8 WARNING
18:05:28  CR-FIX-2 磁盘恢复失败 (第2次)
18:06:20  Batch 2 质量检查失败: score=38.8/75.0
18:12:11  Batch 2 retry 完成
18:13:01  Batch 2 retry exhausted, score 仍为 38.8
18:13:02  CR-FIX-2 磁盘恢复失败 (第3次)
18:13:46  Batch 3 (phase_3_calibrator) 质量检查失败: score=10.0/75.0
18:16:03  Batch 3 retry exhausted, score 仍为 10.0
18:16:03  Harness constraint check failed: phase_3_calibrator, 缺少数据来源+引用严谨度
18:16:04  ResultAggregator: 8 sections, phase_1 平均 ~1,350 chars, phase_2 平均 ~2,400 chars
18:16:05  Canonical data validation: 1,538 issues
18:16:23  Cross-chapter numeric contradiction: XXX_2025 values=[130.0, 54.5, 130.0, 130.0, 130.0, 130.0, 130.0]
18:16:23  Cross-chapter numeric contradiction: XXX_2026 values=[54.5, 54.5, 54.5, 54.5, 130.0, 130.0, 130.0, 130.0, 130.0]
18:16:23  Cross-chapter numeric contradiction: XXX_2025 values=[2500.0, 288.0]
18:16:23  Quality check: score=40.9, passed=False
18:16:23  Quality check not passed, delivering report with warnings
18:16:23  5 条 accuracy issues: 130.0×27次, 23.4×15次, 21.45×14次, 70.05×13次, 436.43×13次
18:16:23.913  Session 文件写入磁盘 (此时 research_result 尚未设置!)
18:16:23.914  quality_result 推送 (第1次, 路径1: completed_with_warnings)
18:16:23.920  quality_result 推送 (第2次, 路径2: _q_score>0)
18:16:23.929  chat_response 推送
18:16:23.948  Preview 复制完成
18:16:23.952  Task 标记完成
18:16:23.955  Research 完成: 17 agents (8 phase_1 + 8 phase_2 + 1 calibrator), status=completed_with_warnings
```

**执行耗时**: 66.9 分钟 (17:09:30 → 18:16:23)

### 2.3 ses_34d79000 (06-11 创建, 06-14 被错误暂停)

```
06-11 10:24:38  Session 创建, 9 sections
06-11 10:26:49  ResearchExecutor 启动
06-11 11:24:44  Research 正常完成 (17 agents, quality_result 推送 2 次)
                但 session 文件中无 research_result 键 (持久化 bug)

06-14 15:59:39  SSE 断开 (服务器 shutdown 触发)
06-14 15:59:40  服务器关闭, asyncio.create_task(_delayed_pause) 残留
06-14 16:00:56  服务器重启, 从磁盘加载 session (无 research_result 键)
06-14 17:08:34  延迟暂停执行: Cancel snapshot 0 completed, 8 pending
06-14 17:08:34  PAUSE 命令发出, state_machine → paused
06-14 17:08:35  session 文件写入 (research_result 仍为 None, state_machine=paused)
```

**问题**: 这是一个已完成的 session 被错误暂停。根因见 §3.1。

## 3. 关键 Bug 分析

### 3.1 [P0] Session 持久化丢失 research_result

**现象**: 两个已完成的 session 在磁盘上没有 `research_result` 键 (key 完全缺失, 非值为 None)。

**根因**: `session_manager.py:226-228` 的 debounce 机制。

```python
# session_manager.py:216-243
def _save_to_disk(self, session_id: str) -> None:
    now = _time.time()
    last = self._last_write_time.get(session_id, 0)
    if (now - last) * 1000 < self._debounce_ms:  # _debounce_ms = 2000
        return  # ← DEBOUNCED! 跳过写入
```

**触发条件**:

```
18:16:23.913  某次 setitem 触发 _save_to_disk → 写入成功 (此时 research_result 尚未设置)
              last_write_time[ses_cc1b9ce3] = 18:16:23.913

随后 research_executor.py:427  session['research_result'] = result
              → __setitem__ → _save_to_disk
              → (now - last) = ~10ms < 2000ms → DEBOUNCED! 跳过写入

              research_executor.py:428  session['status'] = orchestrator_result.status
              → __setitem__ → _save_to_disk
              → (now - last) = ~15ms < 2000ms → DEBOUNCED! 跳过写入

              之后无更多 setitem → research_result 永远未写入磁盘
```

**影响链**:

```
research_result 未持久化
  → 服务器重启后从磁盘加载, research_result 键缺失
  → _on_sse_disconnect 检查 session.get('research_result', {}) → 返回 {} (键不存在时使用默认值)
  → {}.get('status') 返回 None, None 不在终态集合中 → 判断为 "research 未完成"
  → 调度延迟暂停
  → 已完成的 session 被错误暂停, state_machine 被覆盖为 paused
  → 用户看到已完成的报告变成 "执行中" 或 "已暂停"
```

**修复建议**:

1. `session_manager.py`: 对 `research_result` 和 `status` 等关键字段, 绕过 debounce 强制写入
2. `research_api.py:2344`: `_on_sse_disconnect` 需处理 `research_result` 键缺失或值为空的情况

### 3.2 [P0] _on_sse_disconnect 误暂停已完成 session

**代码位置**: `research_api.py:2339-2357`

```python
def _on_sse_disconnect(self, task_id):
    session = session_manager.get(task_id)
    if not session:
        return
    research_result = session.get('research_result', {})  # ← 键不存在时返回 {}, 键存在但值为 None 时返回 None
    _terminal = ('completed', 'failed', 'cancelled', 'error')
    if research_result.get('status') in _terminal:  # ← {} 时返回 None (不抛异常), None 时抛 AttributeError
        ...
        return
    logger.info(f"SSE disconnected for {task_id}, scheduling delayed pause")
    async def _delayed_pause():
        await asyncio.sleep(30)  # ← 服务器 shutdown 后此 task 残留
        ...
        get_cancel_manager().pause(task_id)  # ← 重启后执行, 暂停已完成 session
    asyncio.create_task(_delayed_pause())
```

**三个缺陷**:

1. `session.get('research_result', {})` 当键不存在时返回 `{}` (不会触发异常), 但 `{}` 没有 `status` 键, `{}.get('status')` 返回 `None`, 不在 `_terminal` 中, 流程继续到暂停; 当键存在但值为 `None` 时则返回 `None`, `None.get('status')` 抛 `AttributeError` — 两种情况都无法正确判断终态
2. 缺乏对 `research_result` 为空/None/缺失的显式检查, 逻辑依赖 `.get('status')` 的隐式行为
3. `asyncio.create_task(_delayed_pause)` 在服务器 shutdown 时不会被取消, 重启后可能执行

### 3.3 [P0] data_boundary_controller 100% 匹配失败

**现象**: 16 个 agent (8 phase_1 + 8 phase_2) 全部无法匹配 section ID, 61 条 WARNING。

**日志证据**:

```
[create_boundary] phase_1_agent_7 未找到对应章节 'section_2_供应成本效率' 中的 research agent
[DataBoundaryController] 注册边界: phase_1_agent_7 -> set()  ← 空集合, 无任何依赖
[DataBoundary] phase_1_agent_7 有 0 个数据可用, 获取 0 个
```

Phase_2 agent 虽然获得了 phase_1 的依赖映射, 但数据量为 0:

```
[DataBoundaryController] 注册边界: phase_2_agent_7 -> {'phase_1_agent_7'}  ← 有依赖
[DataBoundary] phase_2_agent_7 有 0 个数据可用, 获取 0 个  ← 但数据为 0!
```

**根因**: section ID 命名格式不匹配。框架生成的 ID 格式为 `section_0_核心财务指标与盈利能力`, 但 agent 分配的 aspects 格式与注册到 data_boundary_controller 的格式不同, 导致查找时永远 miss。

**影响**: 所有 agent 之间无数据共享边界, 每个 agent 独立工作, 产生重复搜索和矛盾数据。

### 3.4 [P0] quality_result 重复推送

**日志证据**:

```
18:16:23,914  Session stream quality_result pushed: ses_cc1b9ce3
18:16:23,920  Session stream quality_result pushed: ses_cc1b9ce3
```

**代码位置**: `research_executor.py`

- 路径 1 (L412-424): `orchestrator_result.status == "completed_with_warnings"` 时推送
- 路径 2 (L456-464): `_q_score > 0 or _q_issues` 时推送

当 status=`completed_with_warnings` 时两条路径都会触发, 间隔 6ms。

**影响**: 前端收到两次 quality_result SSE 事件, 可能导致 UI 闪烁。

### 3.5 [P1] 报告质量无法提升的根因

**最终质量**: score=40.9/100, 三个批次全部不通过。

| 批次 | 分数/阈值 | Issues | Retry 1 | Retry 2 | Retry 3 |
|------|----------|--------|---------|---------|---------|
| Batch 1 (phase_1) | 26.9/75 | 缺失市场规模数值, 缺少数据来源标注, 缺乏维度对比分析 | 26.9 | 26.9 | 26.9 |
| Batch 2 (phase_2) | 38.8/75 | 发行投资额数值来源冲突, 多处数据字段矛盾, 经营现金流异常 | 38.8 | 38.8 | 38.8 |
| Batch 3 (calibrator) | 10.0/75 | 结构严重缺失分析要素, 数值格式0%未提供维度 | 10.0 | 10.0 | 10.0 |

**五层叠加问题**:

#### L1: 搜索引擎大面积失败

```
失败引擎统计 (ConnectError):
  grokipedia: 74 次
  wikipedia:  64 次
  mojeek:    60 次
  yandex:    52 次
  duckduckgo: 49 次
  brave:     47 次
  yahoo:     46 次

DDGS 成功搜索: 187 次
DDGS 失败搜索: 113 次 (失败率 37.7%)
```

成功搜索的结果量也偏低: 99 次仅返回 7 条结果。仅 bing_cn (248次, 平均8.8条) 和 bing_intl (53次, 平均6.5条) 可用, 其他引擎全部 ConnectError。

#### L2: 质量过滤过于激进

```
过滤模式统计 (前5):
  10 → 0:   30 次  ← 100% 过滤, agent 完全无搜索数据
  20 → 17:  25 次
  17 → 6:   20 次
  20 → 20:  18 次
  20 → 16:  17 次
```

30 次搜索结果被完全过滤 (10→0), agent 在无真实数据的情况下只能靠 LLM 编造内容。

#### L3: data_boundary 完全失效

参见 §3.3。所有 agent 独立工作, 无跨章节数据共享, 产生重复和矛盾数据。

#### L4: CR-FIX-2 检查点恢复失败

```
17:10:07  CR-FIX-2 disk recovery failed: 'str' object has no attribute 'exists' (第1次)
18:05:28  CR-FIX-2 disk recovery failed (第2次)
18:13:02  CR-FIX-2 disk recovery failed (第3次)
```

类型错误: 磁盘恢复逻辑期望 `Path` 对象, 但收到 `str`。导致 checkpoint 恢复失败, 无法利用历史缓存数据。

#### L5: Retry 机制无效

Retry 注入了递增的数据量 (185→359→603 data points), 但:

1. 所有 agent 收到的是**同一份无差别的全量数据** (因 data_boundary 失效)
2. Agent 搜索同样的 query, 得到同样的结果
3. LLM 用同样数据生成同样内容
4. `engine.py:1513-1515` 的 "exhausted" 日志复用了**原始 error_msg**, 所以显示相同分数

**Agent 输出极薄**:

| Phase | 输出范围 | 平均 | 对标专业报告 |
|-------|---------|------|-------------|
| Phase_1 | 1,073-1,564 chars | ~1,350 chars (~200字中文) | 2,000-5,000字/章 |
| Phase_2 | 1,696-3,693 chars | ~2,400 chars (~400字中文) | 2,000-5,000字/章 |
| Calibrator | 0 chars (harness 失败) | — | 应补充维度和格式 |

**数据矛盾严重**:

```
Cross-chapter numeric contradiction (字段名因编码问题不可读, 以 XXX 表示):
  XXX_2025: values=[130.0, 54.5, 130.0, 130.0, 130.0, 130.0, 130.0]  ← 130.0 出现 6 次, 54.5 出现 1 次, 章节间数据矛盾
  XXX_2026: values=[54.5, 54.5, 54.5, 54.5, 130.0, 130.0, 130.0, 130.0, 130.0]  ← 同一指标跨章节值不一致
  XXX_2025: values=[2500.0, 288.0]  ← 9 倍差异

Canonical data validation: 1,538 issues

Quality metadata: total_data_volume=0, total_sources=0 (所有批次)
```

### 3.6 [P1] asyncio Task exception 未捕获 — 284 次

**时间窗口**: 17:10:08 — 18:03:42 (53 分钟, 伴随整个 agent 执行过程)

**5 分钟分布**:

| 时段 | 次数 |
|------|------|
| 17:10 | 36 |
| 17:15 | 47 |
| 17:20 | 25 |
| 17:25 | 22 |
| 17:30 | 35 |
| 17:35 | 14 |
| 17:40 | 11 |
| 17:45 | 22 |
| 17:50 | 14 |
| 17:55 | 36 |
| 18:00 | 22 |

**根因**: `scrapling` 库的 `AsyncFetcher` 废弃 API 调用 (2,133 条 WARNING) + 网络连接失败, 异步任务抛出异常但调用方未 await 或未添加异常回调。

**影响**: 不影响最终完成, 但可能导致部分搜索结果丢失, 降低报告数据质量。

### 3.7 [P1] 僵尸 Session 无超时清理

| 类型 | 数量 | 最久时长 | 说明 |
|------|------|---------|------|
| 卡死 executing (引擎死) | 4 | 390.7h (16天) | 用户看到"一直在运行" |
| 卡死 paused 无 result | 6 | 775.7h (32天) | 无法恢复 |
| completed 但无 result | 4 | — | 结果丢失 (持久化 bug) |
| failed 无详细错误 | 14 | — | 错误信息不足 |
| mode 未切换到 chat | 14 | — | B3 bug 历史痕迹 |
| paused+completed+mode!=chat | 2 | — | B3 bug 历史痕迹 |

### 3.8 [P2] LLM JSON 解析失败 — 3 次

```
17:09:42  LLM intent analysis failed: Failed to parse LLM JSON after all recovery attempts: {
17:10:05  Failed to parse LLM JSON: Expecting value: line 1 column 1 (char 0)
17:10:39  Failed to parse LLM JSON: Expecting value: line 1 column 1 (char 0)
```

**根因**: LLM 返回空内容或非 JSON 格式。deepseek-v4-flash 模型偶尔输出不稳定。

**影响**: 降级到默认路径, 不影响最终完成。

## 4. B1-B7 修复验证

| 验证项 | 方式 | 结果 |
|--------|------|------|
| B1 (get_preview) | API 调用 `GET /api/v1/research/preview/ses_cc1b9ce3` | ✅ html_content=51160 字节 |
| B2 (has_valid_result) | API 调用 `GET /api/v1/research/ses_cc1b9ce3` | ✅ preview_url 非空 |
| B4 (完成消息) | 日志中 chat_response 推送 | ✅ 已区分 ⚠️/✅ |
| B3 (chat mode) | ses_cc1b9ce3 尚未触发 (session 文件 mode=research) | ⏳ 需用户下次发消息触发 |
| B5 (resume) | ses_34d79000 已被错误暂停, 无 research_result | ⏳ 无法验证 |
| B6+B7 (inject) | ses_cc1b9ce3 未触发 inject | ⏳ 需用户请求追加章节 |

**B1-B7 修复的局限性**: 修复解决了 `completed_with_warnings` 状态被硬编码 `== 'completed'` 检查阻塞的问题, 让结果能被预览和访问。但**不触及内容生成质量**。报告质量低 (40.9分) 的根因是 §3.5 中的五层叠加问题, 需要独立修复。

## 5. 修复优先级

| 优先级 | Bug | 位置 | 修复建议 |
|--------|-----|------|---------|
| **P0** | Session 持久化丢失 research_result | `session_manager.py:226-228` | 对 `research_result`/`status` 等关键字段绕过 debounce 强制写入; 或在 `_save_to_disk` 中添加 `force` 参数 |
| **P0** | _on_sse_disconnect 误暂停已完成 session | `research_api.py:2339-2357` | 处理 `research_result is None` 的情况; 在 shutdown 时取消所有 pending 的 delayed_pause task |
| **P0** | data_boundary 100% 匹配失败 | `data_boundary_controller.py` | 统一 section ID 命名规范, 或在匹配逻辑中增加模糊匹配/fallback |
| **P0** | quality_result 重复推送 | `research_executor.py:412-424, 456-464` | 路径 2 排除 `completed_with_warnings` 状态, 或合并为单次推送 |
| **P1** | 搜索引擎大面积失败 | `search_skill.py` | 添加重试机制; 降级策略 (多引擎冗余); 增加本地缓存 |
| **P1** | 质量过滤过度 (30次 10→0) | `search_quality_filter.py` | 降低 threshold 或添加保底机制 (至少保留 N 条结果) |
| **P1** | Retry 机制无效 | `engine.py:1488-1518` | retry 时只注入当前 agent 相关数据 (需 data_boundary 修复); 记录实际新分数而非复用原始 error_msg |
| **P1** | asyncio Task exception 未捕获 | agent 执行层 | 添加异常回调或 try/except 包裹 |
| **P1** | 僵尸 session 无超时清理 | `session_manager.py` | 添加引擎心跳机制 + executing 状态超时自动降级为 failed |
| **P2** | CR-FIX-2 磁盘恢复类型错误 | `engine.py` | 添加 `Path()` 转换 |
| **P2** | session 持久化 debounce 过长 | `session_manager.py:168` | `_debounce_ms` 从 2000 降至 500, 或改为只 debounce 非关键字段 |
| **P2** | Agent 输出过薄 | `generic_agent.py` | 增加 min_content_length 检查, 不达标时补充搜索 |

## 6. 06-14 日志分析报告勘误

> 以下为 `docs/2026-06-14-system-log-analysis.md` 中的错误, 供修正参考。

### 错误

| # | 位置 | 原报告内容 | 实际数据 | 严重度 |
|---|------|-----------|---------|--------|
| E1 | §1 概览 | "活跃 Session 5 个" | 06-14 日志中出现 49 个 session ID; 仅 2 个有业务逻辑 | 高 |
| E2 | §2 ses_34d79000 | "17:08:34 SSE 断开连接" | SSE 断开在 **15:59:39** (服务器 shutdown), 17:08:34 是延迟暂停执行时间; 且该 session 在 06-11 已完成 | 高 |
| E3 | §2 ses_34d79000 | "研究刚开始就被暂停" | Research 在 06-11 已正常完成, 06-14 是被 _on_sse_disconnect 错误暂停 | 高 |
| E4 | §3.1 | "asyncio 时间窗口: 17:10:08—17:10:37 (约 30 秒)" | 实际 **17:10:08—18:03:42 (约 53 分钟)** | 高 |
| E5 | §2 时间线 L34 | "17:10:37 scrapling 废弃 API 警告密集出现" | scrapling 首次出现在 **17:10:16**, 持续至 18:05:15, 共 2,133 条 | 高 |
| E6 | §2 时间线 L39 | "Research 完成: 8 agents" | 实际 **17 个 agents** (8 phase_1 + 8 phase_2 + 1 calibrator) | 高 |
| E7 | §3.1 关联事件 | "17:10:08: scrapling 废弃 API 调用" | 17:10:08 无 scrapling 警告 (首次在 17:10:16); 该时刻是 asyncio ERROR + agent 启动 | 中 |
| E8 | §3.1 关联事件 | "17:10:32: 密集 asyncio 错误爆发 (18秒内30+次)" | 17:10:32-17:10:50 内仅 **19 次** | 中 |
| E9 | §3.4 | "LLM JSON 解析失败 — 2 次" | 实际 **3 次** (17:09:42, 17:10:05, 17:10:39) | 中 |
| E10 | §2 ses_af9234c2/cda7392e | "06-14 仅被读取" | 这两个 session 在 06-14 日志中 **0 行**, 完全不出现 | 高 |
| E11 | §3.5 | "DDGS failed: ConnectError (brave.com, yahoo.com)" | 实际 7 个引擎全部失败: grokipedia(74), wikipedia(64), mojeek(60), yandex(52), duckduckgo(49), brave(47), yahoo(46) | 中 |
| E12 | §3.6 路径1行号 | "research_executor.py:411-417" | 实际 **412-424** | 低 |
| E13 | §3.6 路径2行号 | "research_executor.py:453-459" | 实际 **456-464** | 低 |

### 遗漏

| # | 内容 | 详情 |
|---|------|------|
| M1 | 服务器重启 | 15:59:40 shutdown, 16:00:56 restart, 这是 ses_34d79000 SSE 断开的直接原因 |
| M2 | scrapling WARNING 占比 | 2,133/2,565 = 83%, 真正业务 WARNING 仅 432 条 |
| M3 | asyncio 错误持续 53 分钟 | 伴随整个 agent 执行过程, 不是 "30 秒爆发" |
| M4 | 测试活动 | 13:12 和 13:55 有测试运行, 含 6 条 agent 创建失败 |
| M5 | data_boundary 完整规模 | 16 个 agent, 61 条 WARNING, 8 个时间批次; phase_2 有依赖映射但数据量为 0 |
| M6 | CR-FIX-2 发生 3 次 | 报告只提了 1 次 |
| M7 | 批量质量检查失败 | Batch 1=26.9/75, Batch 2=38.8/75, Batch 3=10.0/75, 全部 retry 耗尽 |
| M8 | Canonical data validation | 1,538 个数据冲突问题 |
| M9 | Session 持久化 bug | research_result 键从未写入磁盘 (debounce 导致), 两个 session 文件均缺失此键 |
| M10 | Agent 输出极薄 | Phase_1 平均 ~1,350 chars, Phase_2 平均 ~2,400 chars |
