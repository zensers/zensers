# QC Retry 资源浪费分析

> 日期: 2026-06-03
> 范围: `engine.py` QC retry 机制的资源消耗与优化方向

---

## 1. 现状

### 1.1 Retry 触发条件

engine.py:1389-1440：

```
QC 失败 (composite < threshold)
  └→ 存储 quality_issues 到 agent results
       └→ 完整重跑整个 batch 的所有 agent
            └→ QC 再次检查
                 ├→ 通过 → 丢弃原始结果，使用 retry 结果
                 └→ 失败 → 继续（非阻断，v10 行为）
```

### 1.2 关键代码

```python
# engine.py:1401-1415
_max_retries = getattr(self.config, 'max_retries', 1)  # 默认 1
...
_retry_results = await self._execute_agents_batch(      # ← 全部重跑
    batch_agents, requirement, all_results, scheduler,
    f"batch_{batch_index+1}_qc_retry{_qc_retries}"
)
```

### 1.3 配置

| 参数 | 默认值 | 来源 |
|------|--------|------|
| `max_retries` | 3 (config) / 1 (engine fallback) | `settings.py:214` |
| `threshold_analysis` | 70 | `settings.py:210` |
| 权重 `[analysis, llm_judge]` | `[0.7, 0.3]` | `engine.py:1714` |

---

## 2. 问题分析

### 2.1 问题一：无差别全量重跑

当前 retry 机制对 **任何 QC 失败** 都执行完全相同的操作：**重跑 batch 中所有 agent**。没有区分：

- **微差失败**（score 69.5/70，差 0.5 分）vs **严重失败**（score 20/70）
- **单 agent 质量问题** vs **整体 batch 问题**

### 2.2 问题二：资源浪费量化

以用户遇到的 case 为例：

| 项目 | 数值 |
|------|------|
| batch agents | 5 个 |
| 每次 agent 调用 LLM | 1 次 prompt + 可能的 tool call |
| 首次 QC | score=68.6 (60.0×0.7 + 88.7×0.3) |
| Retry | 5 个 agent 全部重跑 |
| 额外消耗 | **+100% LLM 调用量** |
| 距离阈值 | **仅差 1.4 分** |

一次 retry 使该 batch 的总资源消耗翻倍，而分数差距仅 1.4 分（2%）。

### 2.3 问题三：原始结果被丢弃

```python
# engine.py:1439
batch_results = _retry_results
```

如果 retry 通过，原始结果完全被替换。但原始结果中**可能部分 agent 质量很好**，仅个别 agent 拉低分数。retry 后新的 LLM 输出可能在这些好的方面反而倒退。

### 2.4 问题四：retry 无针对性

Retry 时所有 agent 收到相同的 `retry_attempt` 信号：

```python
# engine.py:1410-1411
_a._context["retry_attempt"] = _qc_retries
```

没有指示哪些方面需要改进、哪些 agent 需要重点优化。LLM 在第二次运行时并不知道之前的不足在哪里，本质上只是"再试一次"。

---

## 3. 数据对比

```
第一次运行:                            Retry 后:
┌──────────────────────┐              ┌──────────────────────┐
│ Agent A: score 85     │              │ Agent A': score 82   │ ← 可能还退步
│ Agent B: score 45     │ ← 拉低整体    │ Agent B': score 70   │ ← 有改善
│ Agent C: score 90     │              │ Agent C': score 88   │
│ Agent D: score 30     │ ← 拉低整体    │ Agent D': score 65   │
│ Agent E: score 52     │              │ Agent E': score 55   │
├──────────────────────┤              ├──────────────────────┤
│ Composite: 60.7/70    │              │ Composite: 72.3/70   │ ← 擦边通过
│ LLM cost: 5 次调用    │              │ LLM cost: +5 次调用  │
└──────────────────────┘              └──────────────────────┘
Total cost: 10 次 LLM 调用，其中 5 次（50%）是浪费的
```

---

## 4. 优化方向

### 4.1 按差距分级决策

```
┌─ score 差距 < 5% ─→ 不 retry，直接继续（附 quality_issues 供修订）
├─ 5% ≤ 差距 < 25% ─→ 选择性 retry（仅分数最低的 1-2 个 agent）
└─ 差距 ≥ 25% ─────→ 全 batch retry（但仍考虑选择性优化）
```

### 4.2 选择性 retry

分析每个 agent 的 quality_issues，仅重跑**分数最低的 N 个 agent**，而非整个 batch。

```python
# 伪代码
if passes_threshold(rescore):
    return  # 不 retry
if gap < 0.05 * threshold:
    continue  # 接近阈值，直接继续
if gap < 0.25 * threshold:
    bad_agents = select_worst_agents(batch_agents, batch_results)
    retry_results = await re_execute(bad_agents, ...)
else:
    retry_results = await re_execute(batch_agents, ...)
```

### 4.3 带反馈的 retry

向 agent 传递上一次的 quality_issues，指示改进方向：

```python
_a._context["quality_feedback"] = quality_result.issues
_a._context["retry_target"] = f"improve score from {current:.1f} to above {threshold:.1f}"
```

### 4.4 合并原始 + retry 结果

不丢弃原始结果——合并每个 agent 中质量更好的一版：

```python
for original, retried in zip(original_results, retry_results):
    if original.get("quality_score", 0) > retried.get("quality_score", 0):
        final_results.append(original)  # 保留原始
    else:
        final_results.append(retried)   # 用 retry
```

---

## 5. 建议优先级

| 优先级 | 改动 | 影响 |
|--------|------|------|
| **P0** | QC 不合格不阻断执行（已实施 v10） | 解决阻断问题 |
| **P1** | 接近阈值时不 retry，直接继续 | 节省 60-80% 的 retry 资源 |
| **P2** | 选择性 retry（仅最低分 agent） | 进一步减少浪费 |
| **P3** | 带 quality_issues 反馈的 retry | 提高 retry 成功率 |
| **P4** | 合并原始+retry 最优结果 | 防止好结果被覆盖 |

---

## 6. 结论

当前 retry 机制的**最大问题是无差别全量重跑**。对于接近阈值的微差失败（如 68.6/70），retry 消耗翻倍资源但提升有限。建议优先实施 **P1：差距分级决策**——差距 < 5% 时不 retry，直接携带 quality_issues 进入修订环节，这是投入产出比最高的优化。
