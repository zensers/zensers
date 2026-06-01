# 质量控制漏洞修复报告

## 概述

2026-05-13 生产环境出现严重质量问题：研究框架确认后执行研究工作，由于数据源限制导致全部采用 LLM 降级输出（无真实数据），但系统仍然生成了完整报告。质量控制环节形同虚设，未能阻断失真内容的输出。

**现场日志关键证据：**

```
Quality checker failed for batch 1: score=0.0/70, issues=['Quality score 0.0 is below threshold 70']
Execution exec_9240745a completed successfully        ← 矛盾！QC说失败但执行成功
```

---

## 根因分析

### 根本原因：质量检查失败是"空操作"（No-Op）

专业质量检查器（`DataCollectionQualityChecker`）判定了内容失真，但在代码层面没有对管线产生任何影响。具体流程：

```
execute_with_scheduler()
  │
  ├─ _check_stage_quality()           ← 基础检查：成功率≥50%？→ 通过（13/13=100%）
  │
  ├─ enable_quality_control AND batch_quality?
  │   └─ DataCollectionQualityChecker.check()
  │       └─ score=0.0 < threshold=70 → passed=False
  │           ├─ logger.warning(...)         ← 只打日志
  │           ├─ r["quality_issues"] = ...   ← 存到结果中（无人读取）
  │           └─ ← 没有任何阻断操作！        ← BUG 核心
  │
  ├─ if not batch_quality:             ← 只检查基础质量，不检查专业QC
  │   └─ abort only when 100% failed   ← 13/13成功，此检查不触发
  │
  └─ result.status = "completed"      ← 无条件完成
```

**问题代码位置：** `src/core/orchestrator/execution/engine.py:1191-1196`

```python
# 修复前的代码：
if not quality_result.passed:
    logger.warning(...)       # 只有日志
    for r in batch_results:  # 只有存储
        r["quality_issues"] = ...
        r["quality_score"] = ...
    # ← 缺少：阻断管线操作
```

### 次要原因：智能路由路径缺少后置质量检查

系统有两条执行路径：

| 路径 | 方法 | 是否有后置QC |
|---|---|---|
| 传统路径 | `research()` | 有（QualityCheckAgent 循环，lines 998-1108） |
| 智能路由 | `_research_with_routing()` | **无** — 执行完直接进聚合+预览 |

本次事故走的是智能路由路径，完全跳过了后置质量检查。

---

## 修复方案

### Fix 1: `engine.py` — 专业QC失败阻断管线

**文件：** `src/core/orchestrator/execution/engine.py:1191-1208`

当专业质量检查器判定失败时，不再静默通过，而是：
1. 将错误信息追加到 `result.errors`
2. 设置 `result.status = "failed"`
3. `break` 跳出批次循环，停止后续处理

```python
if not quality_result.passed:
    error_msg = f"Quality check failed for batch {batch_index + 1}: ..."
    logger.warning(error_msg)
    for r in batch_results:
        if r.get("success"):
            r["quality_issues"] = quality_result.issues[:3]
            r["quality_score"] = quality_result.score
    # ★ 新增：阻断管线
    result.errors.append(error_msg)
    result.status = "failed"
    break
```

### Fix 2: `orchestrator.py` — 传统路径执行后检查QC状态

**文件：** `src/core/orchestrator/orchestrator.py:808-819`

三个执行分支（`execute` / `execute_with_scheduler` / `execute_with_skip`）之后，在进入聚合前增加检查：

```python
if exec_result.status == "failed":
    error_detail = "; ".join(exec_result.errors[:5]) if exec_result.errors else "Quality check failed"
    logger.error(f"[{task_id}] Execution aborted due to quality failure: {error_detail}")
    return ResearchResult(
        task_id=task_id, status="failed",
        topic=requirement.topic,
        agents_used=[a.agent_id for a in agents] if agents else [],
        stages_completed=0,
        summary=f"Research aborted: quality check failed ({error_detail})",
    )
```

### Fix 3: `orchestrator.py` — 智能路由路径执行后检查QC状态

**文件：** `src/core/orchestrator/orchestrator.py:1674-1690`

在 `_research_with_routing()` 方法中增加同样的检查，修复该路径完全没有后置 QC 的问题：

```python
if exec_result.status == "failed":
    error_detail = "; ".join(exec_result.errors[:5]) if exec_result.errors else "Quality check failed"
    logger.error(f"[{task_id}] Execution aborted due to quality failure: {error_detail}")
    self._task_persistence.update_task_state(
        task_id, TaskState.FAILED, progress=0.0,
        message=f"Aborted: {error_detail[:200]}"
    )
    return ResearchResult(
        task_id=task_id, status="failed",
        topic=requirement.topic, agents_used=[a.agent_id for a in agents],
        stages_completed=0,
        summary=f"Research aborted: quality check failed ({error_detail})",
    )
```

---

## 修复后的数据流

```
engine.execute_with_scheduler()
  ├─ _check_stage_quality()           → 基础检查: 通过
  ├─ DataCollectionQualityChecker     → score=0.0, failed
  │   └─ result.status = "failed", break  ← ★ 现在会阻断
  └─ 返回 exec_result (status="failed", errors=["QC failed..."])

orchestrator._research_with_routing()
  ├─ exec_result.status == "failed"   → 检测到  ← ★ 新增检查
  └─ 立即返回 ResearchResult(status="failed")
     ↓ 不再进入
     聚合结果 → 生成预览 → 返回报告
```

---

## 涉及文件

| 文件 | 修改行 | 改动说明 |
|---|---|---|
| `src/core/orchestrator/execution/engine.py` | L1191-1208 | 专业QC失败时设置 `status=failed` + `break` |
| `src/core/orchestrator/execution/engine.py` | L1226-1231 | 守卫条件防止 status 被无条件覆盖回 `completed` |
| `src/core/orchestrator/execution/engine.py` | L501 | `execute()` 日志按实际状态区分（failed 时不打印成功） |
| `src/core/orchestrator/orchestrator.py` | L808-819 | 传统路径执行后检查 `exec_result.status` |
| `src/core/orchestrator/orchestrator.py` | L1674-1690 | 路由路径执行后检查 `exec_result.status` |
| `src/api/research_executor.py` | L229-296 | 分离成功/失败处理逻辑，失败时正确标记会话状态、推送错误消息 |

---

## 第二轮修复说明

### 审查发现的问题

**问题1 — `engine.py:1226-1230` 无条件覆盖状态**

即使在第一轮修复中设置了 `result.status = "failed"`，跳出循环后仍会被无条件覆盖：

```python
# 原始代码（修复前）：
# 构建最终结果
result.status = "completed"              # ← 把 QC 设置的 "failed" 覆盖了！
result.completed_at = datetime.now()
result.final_result = self._aggregate_results(all_results)
result.stats = self._build_stats()
```

修复：添加 `if result.status != "failed":` 守卫条件，`completed_at` 外移确保总有值。

**问题2 — `research_executor.py:231` 会话状态和前端展示无条件标记成功**

即使 `orchestrator_result.status == "failed"`：
- `session["status"] = "completed"` 无条件设置（line 231）
- 前端收到 `"Research Complete ✅"` 消息
- 调用 `complete_task()` 而非 `fail_task()`

修复：将成功/失败处理逻辑完全分离，失败时：
- 会话状态设置为 `"failed"`
- 前端收到 `"Research Failed ❌"` 消息
- 调用 `fail_task()`

**问题3 — `engine.py:501` 日志误导**

无论实际状态如何，始终打印 `"Execution ... completed successfully"`。

修复：按 `result.status` 区分日志等级和消息文本。

---

## 验证

- [x] `engine.py` Python 语法检查通过
- [x] `orchestrator.py` Python 语法检查通过
- [x] `research_executor.py` Python 语法检查通过
- [ ] 需要集成测试验证：
  - 场景1：数据源正常 → QC 通过 → 正常生成报告
  - 场景2：数据源不足 → QC 失败（0分）→ 返回 `status="failed"`，不生成报告
  - 场景3：部分章节失败（非全部）→ 基础QC通过但专业QC失败 → 阻断
  - 场景4：传统路径和路由路径均应校验

---

## 修复人 / 日期

- 分析 & 修复：opencode
- 日期：2026-05-13
