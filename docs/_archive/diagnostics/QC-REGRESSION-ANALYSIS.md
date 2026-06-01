# 质量控制修复导致的回归分析

## 问题描述

QC 修复后，所有研究报告均无法生成。追踪日志可见每次研究都在质量检查步骤被阻断：

```
Quality check failed for batch 1: score=0.0/70
[research_xxx] Execution aborted due to quality failure
Task state updated: research_xxx running -> failed
```

但 0 分并非内容质量问题——这是假阳性。

---

## 根因：数据接口不匹配

### 代码位置

`src/core/orchestrator/execution/engine.py:1190-1191`

```python
# 实际传递的数据格式：
{"batch_results": [agent1_result, agent2_result, ...]}

# 检查器期望的数据格式：
{"content": "实际内容文本", "sources": [...], ...}
```

### 详细追踪

```
engine.py:1190  checker.check({"batch_results": batch_results}, context)
                                ↑
checker 收到的是 batch 的包装层

AnalysisQualityChecker.calculate_score(data, context):
    content = data.get("content", "")   ← data = {"batch_results": [...]}
                                         data["content"] 不存在
                                         返回 "" (空字符串)

    insight_score = 0.0    ← content 为空
    consistency_score = 0.0
    depth_score = 0.0

    final_score = 0.0 ✅ 永远得 0 分

DataCollectionQualityChecker.calculate_score(data, context):
    quality_metadata = data.get("quality_metadata", {})
                                         data["quality_metadata"] 不存在
                                         返回 {} (空字典)

    volume_score = 10.0   ← data_volume=0 → 10分
    quality_score = 50.0  ← 默认值
    source_score = 30.0   ← 无来源 → 30分

    final_score = 10*0.3 + 50*0.4 + 30*0.3 = 32.0 ✅ 也只能得 32 分
```

**无论研究内容质量如何，检查器永远得 0 分（analysis）或 32 分（data_collection），永远低于阈值 70/75。**

### 根本原因

| 问题 | 文件 | 说明 |
|---|---|---|
| 数据格式不匹配 | `engine.py:1190-1191` | 传 `{"batch_results": [...]}` 但 checkers 读顶层 key |
| QualityMetadataExtractor 未集成 | `engine.py:281` | 初始化了但 `execute_with_scheduler` 中从未调用 |
| Checker 与 Engine 无契约 | `checkers.py` / `engine.py` | 两者对 data 结构的假设完全不匹配 |

### 时间线

| 步骤 | 操作 | 效果 |
|---|---|---|
| 修复前 | QC 失败是空操作（只打日志） | 报告能生成（质量差） |
| 修复 #1 | QC 失败时设置 `status="failed"` + `break` | **所有研究被阻断** ← 回归 |
| 修复 #2 | 编排器检查 `status` 后提前返回 | 回归暴露 |
| 修复 #3 | research_executor 分离成功/失败路径 | 回归暴露 |

**修复 #1 给了 QC 牙齿，但 QC 本身是坏的（数据接口不对）。结果是：牙齿咬到了错误的东西。**

---

## 正确的修复顺序

应该先修数据接口，再给 QC 加阻断能力。

### Step 1: 修复数据接口（优先级最高）

将 `{"batch_results": [...]}` 改为 checkers 能消费的格式：

```python
# engine.py:1190-1191 修改为：
combined_content = "\n\n".join([
    r.get("content", "") or r.get("result", "")
    for r in batch_results if r.get("success")
])
all_sources = []
all_data_points = []
for r in batch_results:
    if r.get("success"):
        all_sources.extend(r.get("sources", []))
        all_data_points.extend(r.get("data_points", []))

# 或调用 metadata_extractor 提取质量元数据
quality_metadata = {}
if self.metadata_extractor and batch_results:
    try:
        # 提取综合元数据
        combined_raw = {"batch_results": batch_results}
        quality_metadata = self.metadata_extractor.extract(
            combined_raw, skill_name="batch_analysis"
        ).to_dict()
    except Exception:
        pass

check_data = {
    "content": combined_content,
    "sources": all_sources,
    "data_points": all_data_points,
}
if quality_metadata:
    check_data["quality_metadata"] = quality_metadata

quality_result = checker.check(check_data, quality_context)
```

### Step 2: 验证检查器能正确打分

修复数据接口后验证：
- 高质量内容 → score ≥ 70 → 通过
- 低质量/空内容 → score < 70 → 阻断

### Step 3: 恢复 QC 阻断能力（当前已实现但前提不正确）

确认 Step 1 和 Step 2 通过后，当前 engine.py 中的 `status="failed"` + `break` + 编排器检查逻辑是正确的。

---

## 影响范围

| 组件 | 影响 |
|---|---|
| 所有 research 请求 | 每个请求都会被 QC 阻断，无法生成任何报告 |
| 传统路径 `research()` | exec_result.status == "failed" → 提前返回失败 |
| 路由路径 `_research_with_routing()` | 同上 |
| API 层 `research_executor.py` | 收到 `status="failed"` → 推送错误消息 |

---

## 修复建议

### 方案 A（推荐）：先修数据接口，保留阻断逻辑

1. 修复 `engine.py:1190-1191` 的数据格式
2. 验证检查器能正确打分
3. 阻断逻辑继续生效

### 方案 B（临时恢复）：关闭质量控制

```python
# orchestrator.py:308
self._execution_engine = execution_engine or ExecutionEngine(
    config=self._execution_config,
    message_bus=self._message_bus,
    shared_memory=self._shared_memory,
    enable_quality_control=False,  # ← 临时关闭
)
```

### 方案 C（保守）：保持阻断但降低阈值

修复数据接口前，将 QC 阈值设为 0，使其永远通过，但保留日志：
```python
# settings.quality.threshold_analysis = 0
```

---

## 验证清单

- [ ] 修复前：研究执行但得分恒为 0
- [ ] Step 1 后：检查器能正确读取 content/sources/data_points
- [ ] Step 1 后：高质量内容得分 ≥ 阈值
- [ ] Step 1 后：低质量内容得分 < 阈值
- [ ] Step 1 + Step 3：QC 失败时正确阻断，QC 通过时正常生成报告
