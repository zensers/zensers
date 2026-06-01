# QC 回归分析审核报告

## 审核结论：根因分析正确 ✅

QC-REGRESSION-ANALYSIS.md 的根因判断完全正确。

## 验证细节

### 1. 数据接口不匹配（确认）

`engine.py:1190-1191`:
```python
quality_result = checker.check(
    {"batch_results": batch_results},  # ← 传了包装层
    quality_context,
)
```

三个 checker 全部读顶层 key：
- `AnalysisQualityChecker.calculate_score` → `data.get("content", "")` → `""` → score=0
- `DataCollectionQualityChecker.calculate_score` → `data.get("quality_metadata", {})` → `{}` → score=32
- `ReportQualityChecker.calculate_score` → `data.get("sections", data.get("content", ""))` → `""` → score=0

### 2. 日志确认

日志显示：
- `batch_quality` = passed ✅（成功率 100%, 13/13, 内容 34617 字符）
- `[analysis] score=0.0, threshold=70, passed=False` ✅（checker 读到空 content）
- 结果：task 状态 running → failed ✅

34617 字符的内容，修复后预计得分 76-100，远高于阈值 70。

### 3. QualityMetadataExtractor 未集成（确认）

`engine.py:281` 初始化了 `self.metadata_extractor = QualityMetadataExtractor()`，但 `execute_with_scheduler` 流程中从未调用过。

### 4. 执行时间线（确认）

文档中的三步修复分析准确。修复 #1（QC failure → status=failed + break）让 QC 有了阻断能力，但 QC 本身数据接口坏了。

## 方案评估

### 方案 A：修复数据接口（推荐）

| 维度 | 评估 |
|---|---|
| 根因修复 | ✅ 直接解决数据格式不匹配 |
| 恢复后得分预估 | ~76-100（34617 字符，含数据引用） |
| 影响范围 | engine.py:1190-1191 局部修改 |
| 风险 | 低 |
| 工作量 | 小 |

检查器预期结果验证：
- `AnalysisQualityChecker`: 读 `data["content"]` → 需要从 batch_results 聚合 content
- `DataCollectionQualityChecker`: 读 `data["quality_metadata"]` → 需要从 batch_results 提取元数据，或调用 QualityMetadataExtractor
- `ReportQualityChecker`: 读 `data["content"]`/`data["sections"]` + `data["sources"]` → 需要聚合

### 方案 B：关闭 QC

| 维度 | 评估 |
|---|---|
| 速度 | ⚡ 最快 |
| 后果 | ❌ 所有质量检查失效 |
| 适用 | 仅限紧急临时恢复 |

### 方案 C：阈值归零

| 维度 | 评估 |
|---|---|
| 效果 | ❌ 同方案 B，防御作废 |
| 误导性 | ⚠️ 日志显示"检查通过"但实际没检查 |
| 不推荐 | |

## 推荐修复方案

实施方案 A，关键代码变更：

```python
# engine.py:1190-1191 改为
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

check_data = {
    "content": combined_content,
    "sources": all_sources,
    "data_points": all_data_points,
}

if self.metadata_extractor:
    try:
        quality_metadata = self.metadata_extractor.extract(
            {"batch_results": batch_results},
            skill_name="batch_analysis",
        ).to_dict()
        check_data["quality_metadata"] = quality_metadata
    except Exception:
        pass

quality_result = checker.check(check_data, quality_context)
```
