# Fix Round 2 — 根因修复方案

> 基于6月9-10日生产日志深度分析，发现3个更深层根因。
> 本文档仅做方案设计，**不直接改代码**，需审查通过后再实施。

---

## 根因清单

| # | 严重度 | 根因 | 影响 | 日志证据 |
|---|--------|------|------|----------|
| R1 | **P0** | `_ensure_standard_result` 将 `data_points`/`sources` 排除在 `result` 子字典外 | 聚合器提取 `actual_content` 拿到元数据字符串(46-58 chars)，非实际研究数据 | `generic_agent.py:1223-1226` |
| R2 | **P0** | 6月10日 `stage_results` → `results_for_aggregation` 遍历丢失16/17条结果 | 聚合只拿到 phase_3_calibrator 1条，Phase1+Phase2全部丢失 | `"got 1 results"` (应为17) |
| R3 | P1 | `agent_contents` 判定条件 `len(content) > 50` 过滤掉 Phase1 结果 | ResearchResultStore 持久化 `0 agent results`，Phase1 结果无法被 Phase2 通过 store 注入 | `engine.py:2242` |

---

## R1 修复方案：data_points 内容格式化

### 问题

`result_aggregator.aggregate()` (line 997-1009) 提取 `actual_content` 时只检查 `content` 和 `result` 字段。
Phase1 data_collection agent 的 `content` 为空，`result` 是 `{"_section_id":..., "category":...}` 元数据字典，
`str(result_val)` 只有 ~50 chars 无意义文本。

`data_points` 虽然作为 `__meta` 存储 (line 1040-1045)，但 **从未用于生成章节内容**。

### 修复位置

`src/core/orchestrator/aggregation/result_aggregator.py` line 1009 之后

### 修复逻辑

```
当 actual_content 为空或 <100 chars 时：
  如果 result 有 data_points (list, len>0)：
    将 data_points 格式化为结构化文本：
      "- {metric}: {value} ({unit}) [来源: {source}]"
    如果格式化文本长度 > actual_content 长度：
      替换 actual_content 为格式化文本
      记录 INFO 日志
```

### 设计要点

- 阈值 100 chars：区分"真内容"和"元数据泄露"（元数据 str(dict) 通常 46-58 chars）
- 限制最多格式化 80 条 data_points（防止超大内容）
- 只在格式化文本 **更长** 时才替换（避免覆盖已有有效内容）
- 不修改 `_ensure_standard_result`，因为 data_points 排除在 result 外的设计是合理的（它确实是独立数据结构）

### 风险评估

- **低风险**：仅在 `actual_content` 为空/太短时触发，不影响正常有内容的 agent
- **边界情况**：data_points 格式多样（dict/str），需做类型判断

---

## R2 修复方案：stage_results 数据丢失

### 问题

6月10日日志：3个batch全部成功执行，但 `results_for_aggregation` 只有1条（phase_3_calibrator）。
代码分析未找到 `stage_results` 被清空/覆盖的路径。

### 根因假设（按可能性排序）

1. **agent_id 碰撞**：多个 result 有相同 `agent_id`，dict key 被覆盖（可能性：中）
2. **stage_results 中 batch_1/batch_2 的结果列表为空**：batch 执行成功但结果未正确收集（可能性：中）
3. **结果中 agent_id 和 section_id 都为空**：多个 result 落入 `f"{stage_name}_{i}"`  fallback key，跨 batch 时 i 计数器重置导致碰撞（可能性：低，因为 stage_name 不同）

### 修复方案：先诊断后修复

**Step 1：添加诊断日志**（只加日志，不改逻辑）

在 `orchestrator.py` line ~1776（`results_for_aggregation` 遍历前）加：
```python
logger.info(
    f"[{task_id}] stage_results keys: {list(exec_result.stage_results.keys())}, "
    f"total entries: {sum(len(v) for v in exec_result.stage_results.values())}"
)
for _sn, _srl in exec_result.stage_results.items():
    logger.info(
        f"[{task_id}] stage_name={_sn}, count={len(_srl)}, "
        f"agent_ids={[r.get('agent_id', 'NO_ID') for r in _srl[:5]]}"
    )
```

在 `engine.py` line ~1533（`execute_with_scheduler` 返回前）加：
```python
logger.info(
    f"[execute_with_scheduler] stage_results keys: {list(result.stage_results.keys())}, "
    f"total entries: {sum(len(v) for v in result.stage_results.values())}"
)
```

在 `orchestrator.py` line ~867 和 ~1817（`results_for_aggregation[key] = result` 前）加碰撞检测：
```python
if key in results_for_aggregation:
    logger.warning(f"[{task_id}] KEY COLLISION: key={key}, ...")
```

**Step 2：运行一次真实任务，收集诊断日志**

**Step 3：根据日志确认根因，再实施针对性修复**

### 风险评估

- **极低风险**：只加 INFO/WARNING 日志，不改任何业务逻辑
- 日志量小（每批次 ~3 条），不影响性能

---

## R3 修复方案：agent_contents 过滤条件

### 问题

`engine.py:2242` 的条件 `if content and isinstance(content, str) and len(content) > 50`：
Phase1 agent 的 `content` 为空（数据在 `data_points` 中），导致 `agent_contents` 为空 dict。
ResearchResultStore 持久化时 `0 agent results`，Phase2 无法通过 store 注入 Phase1 数据。

### 修复位置

`src/core/orchestrator/execution/engine.py` line 2240-2248

### 修复逻辑

```
当 agent 成功 (r.get("success")) 且有 agent_id 时：
  优先取 content/result 字符串
  如果字符串为空或 <50 chars：
    如果有 data_points：
      格式化 data_points 为文本作为 content
    如果有 sources：
      记录 sources 摘要
  存入 agent_contents
```

### 风险评估

- **中风险**：修改了 ResearchResultStore 的持久化行为
- 但 Phase2 通过 ResearchResultStore 注入数据本身就是已有功能，R3 只是让它正确工作
- 建议：与 R1 合并实施，格式化逻辑复用

---

## 实施顺序

1. **R2-Step1**：先加诊断日志 → 运行任务 → 确认根因
2. **R1**：实施 data_points 格式化（最核心、最安全的修复）
3. **R3**：实施 agent_contents 修复（依赖 R1 的格式化逻辑）
4. **R2-Step3**：根据诊断结果实施针对性修复

---

## 不修改的部分

- `_ensure_standard_result` (generic_agent.py:1223-1226)：排除 data_points/sources 的设计是正确的，它们是独立数据结构，不应混入 result 子字典
- `quality_check_agent.py` 的占位符检测：已在 Fix Round 1 中修复，无需再改
- `content_lock.py` 的 `mark_section_state` 返回值：非本轮范围

---

## 验证计划

1. 单元测试：为 R1 的 data_points 格式化逻辑写测试用例
2. 集成测试：运行完整报告生成，验证：
   - `results_for_aggregation` 数量 == 预期 agent 数
   - Phase1 章节内容包含实际数据（非元数据字符串）
   - ResearchResultStore 持久化 agent_results > 0
3. 回归测试：现有 99 个测试全部通过
