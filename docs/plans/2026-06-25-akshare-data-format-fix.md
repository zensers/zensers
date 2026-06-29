# FIX: akshare 结构化数据提取格式修复

## 问题概述

akshare 数据通过 `StockDataSkill` 获取后，经过 `_fetch_structured_data` 转换进入 data_points，
再经 DATA_VALIDATION → DEEP_ANALYSIS → SYNTHESIS 流转，最终被 LLM 消费。

当前存在 7 个格式问题，导致结构化数据"进得来、出不去"——LLM 实际无法有效使用这些数据。

---

## Bug 清单

### BUG-1: `price_history` 数据静默丢失 [严重]

**位置**: `src/core/agents/generic_agent.py:1619`

**根因**: `_price_history()` 返回 `data` 为 list（`df.head(120).to_dict(orient="records")`），
但 `_fetch_structured_data` 只处理 `isinstance(data, dict)`，list 类型直接跳过。

**当前代码**:
```python
data = skill_result.get("data", {})
if isinstance(data, dict):  # ← list 不匹配
    result["data_points"].append(...)
```

**修复方案**: 增加 `isinstance(data, list)` 分支，将 list 包装为 dict 后统一处理。

```python
data = skill_result.get("data", {})
if isinstance(data, list):
    data = {"records": data}
if isinstance(data, dict):
    result["data_points"].append(...)
```

---

### BUG-2: `str(data)` 产生不可读输出 [严重]

**位置**: `src/core/agents/generic_agent.py:1622`

**根因**: `str(data)` 对嵌套 dict/list 产生 Python repr，如：
```
{'income_statement': [{'报告期': '2024-09-30', '营业总收入': 1234567890.0, ...
```
- 单行无格式化，几千字符
- 三个财务报表混在一起
- LLM 无法解析

**但 StockDataSkill 已生成可读 `content` 字段**（如 `"Stock Name: 贵州茅台\nIndustry: 白酒\n..."`），
却未被使用。

**当前代码**:
```python
result["data_points"].append({
    "title": f"{symbol} {action}",
    "content": str(data),  # ← 不可读
    ...
})
```

**修复方案**: 优先使用 `skill_result["content"]`，fallback 到 `json.dumps(data, ensure_ascii=False, indent=2)`。

```python
content = (
    skill_result.get("content")
    or json.dumps(data, ensure_ascii=False, indent=2)
)
result["data_points"].append({
    "title": f"{symbol} {action}",
    "content": content,
    ...
})
```

**影响评估**:
- `company_info`: content = `"Stock Name: 贵州茅台\nIndustry: 白酒\n..."` — 完整可读
- `financials`: content = `"Retrieved three financial statements for 600519"` — 过于简略，
  需要增强 StockDataSkill 的 content 生成，或在 _fetch_structured_data 中格式化
- `key_metrics`: content = `"基本每股收益: 41.75\n每股净资产: 168.28\n..."` — 可读
- `price_history`: content = `"Retrieved price data for 600519 (last 120 trading days)"` — 过于简略
- `industry_comparison`: content = `"Industry: 白酒"` — 可读但简略

**对 financials 和 price_history 的增强格式化**:

这两个 action 的 content 过于简略，需要在 `_fetch_structured_data` 中生成详细格式化文本：

```python
content = skill_result.get("content", "")
if not content or len(content) < 100:
    content = self._format_structured_data(data, action, symbol)
```

新增 `_format_structured_data` 方法，针对不同 action 生成结构化摘要：

- `financials`: 按报表分段，每段取最近 4 期关键指标，格式如：
  ```
  === 利润表 (最近4期) ===
  2024-09-30: 营业总收入 1200亿 | 净利润 300亿 | 归属净利润 299亿
  2024-06-30: ...
  === 资产负债表 (最近4期) ===
  ...
  === 现金流量表 (最近4期) ===
  ...
  ```

  **注意**: akshare 东方财富 API 的列名可能是英文大写（如 `REPORT_DATE`,
  `OPERATE_INCOME`）或中文（如 `报告期`, `营业总收入`），取决于 API 版本。
  `_format_structured_data` 必须同时处理两种列名，使用列名映射表：

  ```python
  _FINANCIALS_KEY_COLUMNS = {
      "income_statement": {
          "date": ["REPORT_DATE", "报告期", "日期"],
          "key_cols": ["OPERATE_INCOME", "营业总收入", "TOTAL_OPERATE_INCOME",
                       "NET_PROFIT", "净利润", "PARENT_NETPROFIT", "归属净利润"],
      },
      "balance_sheet": {
          "date": ["REPORT_DATE", "报告期", "日期"],
          "key_cols": ["TOTAL_ASSETS", "总资产", "TOTAL_LIABILITIES", "总负债",
                       "TOTAL_EQUITY", "所有者权益"],
      },
      "cash_flow": {
          "date": ["REPORT_DATE", "报告期", "日期"],
          "key_cols": ["OPERATE_CASH_FLOW", "经营活动现金流量", "INVEST_CASH_FLOW",
                       "投资活动现金流量"],
      },
  }
  ```

  格式化逻辑：对每个报表，找到日期列（取第一个匹配），找到关键指标列，
  每期输出一行 `日期: 指标1 值1 | 指标2 值2 | ...`。未匹配的列名直接跳过。

- `price_history`: 取最近 30 日摘要 + 趋势描述：
  ```
  最近30日股价: 最高 1850.0 | 最低 1680.0 | 最新 1720.0
  近期走势: 2024-12-15 开盘1700 收盘1720 涨幅+1.2%
  ...
  ```

  **注意**: `stock_zh_a_hist` 列名为中文（日期/开盘/收盘/最高/最低/成交量/成交额/振幅/涨跌幅/涨跌额/换手率）。
  格式化时取：日期、开盘、收盘、涨跌幅、成交量。

---

### BUG-3: `canonical_metrics` 几乎永远为空 [中等]

**位置**: `src/core/agents/generic_agent.py:1633-1635`

**根因**: akshare 返回的财务数值全部是字符串（如 `"41.75"` 不是 `41.75`），
而 `isinstance(val, (int, float))` 只接受数字类型。

**当前代码**:
```python
for key, val in data.items():
    if isinstance(val, (int, float)):  # ← 字符串 "41.75" 不匹配
        result["canonical_metrics"][key] = val
```

**各 action 结果**:
| Action | 原因 | canonical_metrics |
|--------|------|------------------|
| company_info | 值全是字符串（"12.56亿"） | 空 |
| financials | 顶层值全是 list | 空 |
| key_metrics | 值全是字符串（"41.75"） | 空 |
| industry_comparison | 值全是字符串 | 空 |

**修复方案**: 递归提取数值，尝试将字符串转为 float：

```python
def _extract_numeric_metrics(data, prefix=""):
    metrics = {}
    if isinstance(data, dict):
        for key, val in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(val, (int, float)):
                metrics[full_key] = val
            elif isinstance(val, str):
                try:
                    metrics[full_key] = float(val)
                except (ValueError, TypeError):
                    pass
            elif isinstance(val, list) and val and isinstance(val[0], dict):
                for i, item in enumerate(val[:4]):
                    item_prefix = f"{full_key}[{i}]"
                    for ik, iv in item.items():
                        full_ik = f"{item_prefix}.{ik}"
                        if isinstance(iv, (int, float)):
                            metrics[full_ik] = iv
                        elif isinstance(iv, str):
                            try:
                                metrics[full_ik] = float(iv)
                            except (ValueError, TypeError):
                                pass
    return metrics
```

对 `financials`，深入嵌套 list-of-dicts 提取每期数值指标。
对 `key_metrics`，将字符串值尝试转 float。

**注意事项**:
- `"12.56亿"` 这种含单位的字符串无法直接转 float，需要单位解析（暂不实现，先跳过）
- 只提取纯数字字符串（如 "41.75"、"1234.56"），含单位的跳过
- financials 的 list-of-dicts 只取前 4 期（最近 4 个报告期），避免 metrics 过多

---

### BUG-4: 验证阶段覆盖质量分 95→80 [中等]

**位置**: `src/core/agents/generic_agent.py:2829-2848`（`_validate_collected_data`）

**根因**: `_validate_collected_data` 完全重算质量分，忽略原始 `quality_score: 95` 和
`credibility: "structured_source"`。`stock_data://` URL 没有匹配权威域名，
被归类为 `"general website"`（credibility_score=0.5），质量分降到 ~80。

**当前代码**:
```python
# Step 5: Quality score per data point
q_score = 0.0
q_score += credibility_score * 40.0  # 0.5 * 40 = 20（而非 1.0 * 40 = 40）
q_score += 20.0 if is_recent else 0.0
q_score += 10.0 if len(content) > 100 else 5.0
q_score += 10.0 if number_patterns else 0.0
q_score += 10.0 if len(title) > 15 else 5.0
q_score += 10.0 if url else 0.0
```

**修复方案**: 在 `_validate_collected_data` 中识别结构化数据源，保留原始高分：

```python
# 检查是否为结构化数据源（优先使用原始质量分）
# 注意：urlparse 不识别 stock_data:// 等 scheme，需用字符串匹配
is_structured = (
    dp.get("credibility") == "structured_source"
    or any(url.startswith(f"{s}://") for s in ("stock_data", "wind_data", "bloomberg_data"))
)
if is_structured:
    validated.append({
        "title": title,
        "content": content,
        "url": url,
        "domain": domain,
        "credibility_score": 1.0,
        "credibility_source": "structured_database",
        "quality_score": max(dp.get("quality_score", 0), 90),
        "year_refs": sorted(year_refs) if year_refs else [],
        "is_recent": True,
    })
    total_score += 95
    continue
```

---

### BUG-5: 内容截断摧毁财务数据 [严重]

**位置**:
- `src/core/agents/generic_agent.py:3803` — `content[:300]`（DEEP_ANALYSIS）
- `src/core/agents/generic_agent.py:4301` — `content[:200]`（SYNTHESIS）

**根因**: 财务数据 content 长度通常 2000-15000 字符，截断到 300/200 字符后，
LLM 只能看到 income_statement 的前几个字段。

**但截断本身是合理设计**（控制 prompt 长度），问题在于 **内容格式**：
如果内容本身就是精炼的结构化摘要（如 BUG-2 修复后的格式），300 字符足以展示关键指标。

**修复方案**: 不增加截断长度，而是依赖 BUG-2 的格式化修复。
格式化后的内容优先展示最关键指标，确保前 300 字符包含核心数据。

如果格式化后内容仍超过 300 字符，按 action 类型使用差异化的截断策略：

```python
# 结构化数据源使用更长截断（注意：urlparse 不识别 stock_data:// scheme）
url = dp.get("url", "")
is_structured = any(url.startswith(f"{s}://") for s in ("stock_data", "wind_data", "bloomberg_data"))
max_content_len = 800 if is_structured else 300
content = dp.get("content", "")[:max_content_len]
```

SYNTHESIS 阶段同理：结构化数据 `max_content_len = 500`，普通 `200`。

---

### BUG-6: `_infer_stock_actions` 不返回 `price_history` [低]

**位置**: `src/core/agents/generic_agent.py:1716-1738`

**根因**: 没有关键词映射到股价数据。

**修复方案**: 添加 price_history 关键词映射：

```python
if any(kw in aspect_lower for kw in ["price", "股价", "行情", "走势", "market_cap", "市值变动"]):
    actions.append("price_history")
```

依赖 BUG-1 的修复才能生效（否则数据仍会被丢弃）。

---

### BUG-7: `"structured_source"` 可信度标签未识别 [低]

**位置**: `src/core/agents/generic_agent.py:3808-3815`

**根因**: `cred_labels` 字典没有 `"structured_source"` 条目。

**修复方案**: 添加条目：

```python
cred_labels = {
    "tier1_authority": " [AUTHORITY]",
    "tier2_professional": " [PROFESSIONAL]",
    "tier3_reputable": " [REPUTABLE]",
    "tier4_general": " [GENERAL]",
    "tier5_low_quality": " [LOW QUALITY]",
    "structured_source": " [STRUCTURED DB]",  # ← 新增
}
```

注意：BUG-4 修复后 validation 阶段会保留 `credibility: "structured_source"`，
此处标签才会生效。如果 validation 仍然覆盖了 credibility，此条目无意义。

---

## 修复依赖关系

```
BUG-2 (str→格式化) ──→ BUG-5 (截断策略)  ── 内容可读性链路
BUG-1 (list处理)  ──→ BUG-6 (price_history) ── 股价数据链路
BUG-3 (数值提取)  ── 独立，canonical 体系
BUG-4 (质量分保留) ──→ BUG-7 (标签识别) ── 可信度链路
```

## 修复顺序

1. BUG-2 + BUG-5 — 最高优先，LLM 能否看到有效数据
2. BUG-1 + BUG-6 — 次高优先，股价数据链路
3. BUG-3 — 中等优先，canonical 体系
4. BUG-4 + BUG-7 — 中等优先，可信度体系

## 新增方法

### `_format_structured_data(self, data: dict, action: str, symbol: str) -> str`

位于 `generic_agent.py`，将 akshare 原始数据格式化为 LLM 可读的结构化摘要。

各 action 格式化策略：

| Action | 格式化策略 |
|--------|-----------|
| `company_info` | 已有可读 content，无需额外格式化 |
| `financials` | 按报表分段，每段取最近 4 期，每期只保留关键指标 |
| `key_metrics` | 已有可读 content，无需额外格式化 |
| `price_history` | 最近 30 日摘要 + 趋势统计 |
| `industry_comparison` | 已有可读 content，无需额外格式化 |

核心需求：**确保前 300 字符包含最重要的数据**。

### `_extract_numeric_metrics(self, data: Any, prefix: str = "") -> Dict[str, float]`

位于 `generic_agent.py`，递归提取数值指标用于 canonical_metrics。

---

## 测试计划

### test_akshare_data_format.py

1. `test_list_data_not_dropped` — price_history 返回 list 时 data_point 不为空
2. `test_content_uses_skill_result_content` — 优先使用 skill_result["content"]
3. `test_content_fallback_to_json_dumps` — 无 content 时 fallback 到 json.dumps
4. `test_financials_formatted_readable` — financials 内容可读，前 300 字符含关键指标
5. `test_price_history_formatted_readable` — price_history 内容可读
6. `test_canonical_metrics_extracts_string_numbers` — "41.75" → float 41.75
7. `test_canonical_metrics_extracts_nested_numbers` — financials 嵌套 list 中的数值
8. `test_canonical_metrics_skips_unit_strings` — "12.56亿" 不提取
9. `test_validation_preserves_structured_quality` — stock_data:// URL 保持 quality_score ≥ 90
10. `test_infer_stock_actions_includes_price_history` — "股价" 关键词触发 price_history
11. `test_structured_source_credibility_label` — "structured_source" → [STRUCTURED DB]
12. `test_analysis_truncation_longer_for_structured` — 结构化数据截断 800 vs 普通 300
