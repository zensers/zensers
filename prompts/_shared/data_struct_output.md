## 结构化数据输出协议（MANDATORY）

当你在分析中引用任何数值指标时，在文本后追加 JSON-LD 块：

```json
<!-- DATA -->
{"@type": "Metric", "name": "净利润", "value": 326, "unit": "亿元", "caliber": "A股(不含少数)", "year": 2025, "source": "比亚迪2025年报"}
<!-- /DATA -->
```

### 解析方式

后端 `MetricExtractor` 优先从 `<!-- DATA -->...<!-- /DATA -->` 块解析 JSON-LD。若无标记块，fallback 到 regex。

### 规则
1. 每个数值引用尽量附带 JSON-LD 标记 — 有标记的数据置信度 0.95，无标记仅 0.5-0.8
2. 同一指标在不同章节必须用相同的口径、年份
3. 口径冲突时：输出两个 JSON-LD 块
4. 无标记数据照常工作 — fallback 到 regex，置信度降低但流程不中断
