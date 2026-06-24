# DATA_COLLECTION 数据质量闭环改进方案

**版本**: v1.0
**日期**: 2026-06-24
**关联**: v1.0.4 skill 动态加载修复 + 系统日志分析报告数据质量根因

---

## 一、问题全景

当前 DATA_COLLECTION → DATA_VALIDATION → DEEP_ANALYSIS 数据流存在 **7 个断裂点**，导致数据质量不可控：

| # | 断裂点 | 位置 | 现象 | 影响 |
|---|--------|------|------|------|
| A | `news_search` 已分配但从未调用 | `generic_agent.py:300-387` | 声明了 `news_search` 但代码中无检查 | 缺少时效性新闻数据 |
| B | `stock_data` 失败无降级 | `generic_agent.py:319-320` | akshare 异常 → 仅 warning → 继续 | 财务分析缺关键指标 |
| C | DATA_VALIDATION 不反馈到重收集 | `generic_agent.py:389-414` | validation 结果仅标注，不触发重新收集 | 低质量数据直接传递 |
| D | 冲突检测无解决机制 | `generic_agent.py:2564-2575` | 数值冲突被记录但不解决 | 报告中出现矛盾数据 |
| E | `_infer_stock_actions` 只支持中文 | `generic_agent.py:1555-1568` | English aspect 无法精确选择 action | 数据获取不精确 |
| F | `_supplement_missing_data` 仅补搜索 | `engine.py:3027-3121` | 结构化数据 gap 不触发 `stock_data` 重试 | 财务数据缺口未补 |
| G | 覆盖率检查用子串匹配 | `engine.py:3011-3025` | `need="营收"` 匹配到无关上下文 | 虚假覆盖 |

---

## 二、设计原则

1. **结构化数据优先，非结构化补充**：能用 akshare 获取的精确数据，不依赖搜索摘要
2. **降级有界**：每一层降级必须记录 gap，确保下游知道数据来源的可靠性降级
3. **验证反馈闭环**：DATA_VALIDATION 发现质量问题 → 触发定向重收集（不是全部重来）
4. **冲突可解决**：数值冲突时，按权威性 + 时效性规则自动裁决，标记裁决依据
5. **增量式改进**：每项改进独立可测试，不破坏现有流程

---

## 三、改进方案（按优先级排序）

### IMP-1: DATA_COLLECTION 阶段实际调用 `news_search`（P0）

**问题**: `news_search` 在 `_get_data_collection_skills()` 中声明（`strategies.py:110`），但 `generic_agent.py:300-387` 从未检查和调用。

**方案**: 在 `search_skill` 之后增加 `news_search` 调用阶段。

**改动位置**: `src/core/agents/generic_agent.py` 行 375 附近（`search_skill` 结果收集完成后、return 之前）

**改动逻辑**:

```
Phase 1: stock_data → 结构化财务数据（已有）
Phase 2: search_skill → 网页搜索 + 两阶段爬取（已有）
Phase 3: news_search → 新闻补充（新增）
  ├── 查询词: "{topic} {aspect} 最新 动态"
  ├── 最多获取 10 条新闻
  ├── 数据点标记: source_type="news", credibility="news_source"
  └── 失败降级: warning 日志，不阻塞
```

**关键设计**:
- news_search 的查询词与 search_skill 不同：search_skill 侧重研究性查询，news_search 侧重时效性查询
- 新闻数据点加 `source_type: "news"` 标记，下游可区分数据来源类型
- news_search 在 search_skill **之后**调用：搜索结果可能已包含部分新闻，避免重复
- 失败时仅 warning，不影响已收集的搜索数据

**测试**: `tests/unit/test_data_collection_news.py`
- `news_search` 在 `available_skills` 中时被调用
- `news_search` 不在 `available_skills` 中时跳过
- `news_search` 失败时仍返回搜索数据
- 新闻数据点包含 `source_type: "news"` 标记

---

### IMP-2: `stock_data` 失败时降级到搜索补充（P0）

**问题**: `_fetch_structured_data` 失败（akshare 异常 / 无 symbol）→ 仅 warning → `canonical_metrics` 为空。DEEP_ANALYSIS 阶段无精确财务数据可用。

**方案**: `stock_data` 失败时，生成针对性财务搜索查询补充。

**改动位置**: `src/core/agents/generic_agent.py` 行 320 之后（stock_data 异常 catch 块内）

**改动逻辑**:

```
stock_data 成功:
  → canonical_metrics 写入 SharedMemory
  → 继续 search_skill

stock_data 失败:
  → 记录 gap: {missing: "structured_financial_data", aspect: aspect}
  → 生成针对性查询词列表:
      ["{topic} {aspect} 财务数据 年报",
       "{topic} {aspect} 营收 净利润 最新",
       "{topic} 年报 财务报表"]
  → 注入到 search_skill 的查询词队列（preloaded 或追加）
  → 标记降级: canonical_metrics 中记录 caliber="degraded_from_search"
  → search_skill 执行时优先使用这些补充查询
```

**关键设计**:
- 降级不是"跳过"，而是"用不同方式获取同类数据"
- 降级获取的数据 `quality_score` 低于结构化数据（搜索摘要 60-70 vs 结构化 95）
- gap 信息传递给下游，DEEP_ANALYSIS 知道精确财务数据缺失
- 查询词通过 `_generate_structured_fallback_queries(topic, aspect)` 方法生成

**新增方法**: `_generate_structured_fallback_queries(self, topic: str, aspect: str) -> List[str]`

**测试**: `tests/unit/test_stock_data_fallback.py`
- stock_data 成功时不触发降级搜索
- stock_data 失败时生成针对性查询词
- 降级数据点标记 `caliber: "degraded_from_search"`
- 无 symbol 时也触发降级

---

### IMP-3: DATA_VALIDATION 质量反馈触发定向重收集（P1）

**问题**: DATA_VALIDATION 发现数据质量低（`quality_rating == "low"`）或覆盖不足，但结果仅标注，不触发重新收集。

**方案**: 在 engine.py 的 DATA_VALIDATION 完成后，检查验证结果，对质量不达标的 section 触发定向重收集。

**改动位置**: `src/core/orchestrator/execution/engine.py` DATA_VALIDATION 结果处理处

**改动逻辑**:

```
DATA_VALIDATION 完成后:
  if validation_result.quality_rating == "low":
      识别低质量原因:
        - timeliness不足 → 生成时效性补充查询
        - credibility不足 → 生成权威来源补充查询
        - coverage不足 → 生成覆盖面补充查询
      触发定向重收集:
        1. 生成针对性查询词（基于 warnings 类型）
        2. 使用 search_skill 执行补充搜索
        3. 合并到已有 data_points
        4. 重新验证（最多 1 轮）
```

**关键设计**:
- 最多 1 轮重收集，避免无限循环
- 重收集查询词基于 warnings 类型生成（不是盲目重搜）
- 只对 `quality_rating == "low"` 的 section 触发（medium 不触发）
- 重收集后更新 `quality_rating`
- 整个过程在 engine 的执行循环中完成，不需要新 agent

**新增方法**: `_recollect_for_quality(self, validation_result, requirement) -> Dict`

**测试**: `tests/unit/test_validation_recollect.py`
- quality_rating="high" 时不触发重收集
- quality_rating="low" + timeliness warning → 生成时效性查询
- quality_rating="low" + credibility warning → 生成权威来源查询
- 重收集后 quality_rating 更新
- 最多 1 轮重收集

---

### IMP-4: 数值冲突自动裁决（P1）

**问题**: `_validate_collected_data` 检测到数值冲突（同一指标不同来源给出不同值），但仅记录不解决。

**方案**: 按权威性 + 时效性规则自动裁决，标记裁决依据。

**改动位置**: `src/core/agents/generic_agent.py` 行 2564-2575（冲突检测后）

**裁决规则**:
```
1. 结构化源 (akshare) > 权威网站 (gov.cn, worldbank) > 咨询公司 > 一般网站
2. 同权威性时，更新年份的数据优先
3. 同权威性同年份时，取均值并标记 "averaged"
4. 裁决结果写入 canonical_metrics，标记裁决依据
```

**数据结构扩展**:
```python
conflict_resolution = {
    "claim": "num_35.6%",
    "resolved_value": "35.6%",
    "resolution_method": "authority_priority",
    "winning_source": {"url": "...", "domain": "eastmoney.com"},
    "losing_sources": [{"url": "...", "domain": "sina.com.cn"}],
}
```

**测试**: `tests/unit/test_conflict_resolution.py`
- 结构化源 vs 一般网站 → 结构化源胜出
- 同权威性 → 更新年份胜出
- 同权威性同年份 → 取均值
- 裁决结果包含 resolution_method

---

### IMP-5: `_infer_stock_actions` 支持英文 aspect（P2）

**问题**: `_infer_stock_actions` 只匹配中文关键词，English aspect 如 "Financial Analysis" 无法精确选择 action。

**方案**: 使用配置化映射表替代硬编码 if-else。

**改动位置**: `src/core/agents/generic_agent.py` 行 1555-1568

**改动逻辑**:

```python
ASPECT_ACTION_RULES = [
    (["financial", "盈利", "利润", "营收", "收入", "研发", "技术", "创新", "profit", "revenue", "income", "rd"], ["financials"]),
    (["valuation", "估值", "价值", "pe", "pb", "回报", "roe", "roa", "roic", "value", "return"], ["key_metrics"]),
    (["leverage", "杠杆", "负债", "资本结构", "稳健", "风险", "debt", "capital structure"], ["financials"]),
    (["industry", "行业", "对比", "竞争", "competitive", "comparison"], ["industry_comparison"]),
    (["price", "股价", "走势", "行情", "stock price", "trend"], ["price_history"]),
]
```

**关键设计**:
- 每条规则包含中英文关键词
- 多条规则可匹配同一 aspect（如 "Financial Valuation" → financials + key_metrics）
- 去重后返回 action 列表
- 无匹配时仍 fallback 到 `["company_info", "financials"]`

**测试**: `tests/unit/test_infer_stock_actions_en.py`
- "Financial Analysis" → ["financials", "key_metrics"]
- "Valuation Analysis" → ["key_metrics"]
- "Competitive Landscape" → ["industry_comparison"]
- "技术趋势" → []（非财务类 aspect，不触发 stock action）
- "投资回报 ROE" → ["key_metrics"]

---

### IMP-6: `_supplement_missing_data` 支持 stock_data 重试（P2）

**问题**: `_supplement_missing_data` 仅补充搜索数据，结构化数据 gap 不触发 `stock_data` 重试。

**方案**: 补充逻辑增加对 `structured_data_needs` 的检查和 `stock_data` 重试。

**改动位置**: `src/core/orchestrator/execution/engine.py` 行 3063-3120

**改动逻辑**:

```
现有逻辑: 只检查 search_data_needs
新增逻辑:
  1. 检查 structured_data_needs 覆盖率
  2. 对未覆盖的结构化需求:
     a. 检查 skill_registry 中是否有 stock_data
     b. 有 → 调用 stock_data.execute(action=..., symbol=...)
     c. 无 → 降级到搜索补充（与 IMP-2 同逻辑）
  3. 合并结构化补充结果
```

**关键设计**:
- 结构化补充在搜索补充**之前**执行（精确数据优先）
- stock_data 的 symbol 从 task 的 topic 中提取
- 失败时降级到搜索（不阻塞）
- 补充结果标记 `source_type: "supplement_structured"` 或 `source_type: "supplement_search"`

**测试**: `tests/unit/test_supplement_structured.py`
- structured_data_needs 未覆盖时触发 stock_data
- stock_data 不可用时降级到搜索
- 补充结果正确标记 source_type

---

### IMP-7: 覆盖率检查从子串匹配改为语义匹配（P3，长期）

**问题**: `_get_covered_needs` 使用子串匹配（`if need in text`），`need="营收"` 可能匹配到无关上下文。

**方案**: 引入轻量级语义匹配，替换子串匹配。

**改动位置**: `src/core/orchestrator/execution/engine.py` 行 3011-3025

**方案选项**:
- **A（简单）**: 要求匹配出现在同一句子中（按句号分割后检查），减少误匹配
- **B（中等）**: 用 LLM 判断 data_point 是否真正覆盖了 need（1 次 LLM 调用）
- **C（长期）**: 嵌入向量相似度匹配

**建议**: 先实施方案 A，效果不足时升级到 B。

---

## 四、数据流架构（改进后）

```
DATA_COLLECTION (category="research")
  │
  ├── Phase 1: stock_data → 结构化数据（akshare）
  │     ↓ 成功 → canonical_metrics (caliber="structured_source", quality=95)
  │     ↓ 失败 → 降级查询注入 search_skill ← IMP-2
  │
  ├── Phase 2: search_skill → 网页搜索 + 两阶段爬取
  │     ↓ 质量循环：不够 → 扩展查询 → 继续搜索
  │     ↓ 接收 stock_data 降级查询（如有）← IMP-2
  │
  ├── Phase 3: news_search → 新闻补充 ← IMP-1
  │     ↓ 时效性数据（财报发布、政策变化、突发事件）
  │     ↓ source_type="news"
  │
  └── Phase 4: 质量自评
        ↓ 标记降级信息（gap、caliber）
        ↓ 传递给下游
        ↓
Engine: _supplement_missing_data
  │
  ├── 结构化补充: structured_data_needs → stock_data 重试 ← IMP-6
  │     ↓ 失败 → 降级到搜索
  │
  ├── 搜索补充: search_data_needs → search_skill
  │     ↓ 覆盖率检查（语义匹配）← IMP-7
  │
  └── Canonical Registry → SharedMemory
        ↓
DATA_VALIDATION (category="quality-check")
  │
  ├── 去重 + 权威性 + 时效性 + 数值提取
  ├── 冲突检测 → 自动裁决 ← IMP-4
  ├── 质量评分 → quality_rating
  │
  ├── quality_rating == "low" → 定向重收集 ← IMP-3
  │     ↓ 生成针对性查询（基于 warnings）
  │     ↓ 重新验证（最多 1 轮）
  │
  └── 输出: validated_data_points + resolutions
        ↓
DEEP_ANALYSIS (category="market-analysis/analysis/financial-analysis")
  │
  ├── 使用 canonical_data（校准后的结构化数据）
  ├── 知识缺口检测 → 补充搜索 → 重新分析（已有）
  └── 输出: 分析内容 + canonical 执行结果
```

---

## 五、实施计划

### Step 1 (P0, 原子变更): IMP-1 + IMP-2

IMP-1 (news_search 调用) + IMP-2 (stock_data 降级) 必须同时上线：
- IMP-2 的降级查询注入依赖 search_skill 阶段存在
- IMP-1 的 news_search 在 search_skill 之后调用
- 两者共同提升数据完整性

**文件改动**:
- `src/core/agents/generic_agent.py` — DATA_COLLECTION 分支新增 Phase 3 + stock_data 降级逻辑
- 新增 `_generate_structured_fallback_queries()` 方法

**测试**:
- `tests/unit/test_data_collection_news.py`
- `tests/unit/test_stock_data_fallback.py`

### Step 2 (P1, 独立上线): IMP-3 + IMP-4

IMP-3 (验证反馈重收集) + IMP-4 (冲突裁决) 可独立上线：
- IMP-3 在 engine.py 中实现，不改动 generic_agent.py
- IMP-4 在 generic_agent.py 的 `_validate_collected_data` 中实现

**文件改动**:
- `src/core/orchestrator/execution/engine.py` — 验证后重收集逻辑
- `src/core/agents/generic_agent.py` — 冲突裁决逻辑

**测试**:
- `tests/unit/test_validation_recollect.py`
- `tests/unit/test_conflict_resolution.py`

### Step 3 (P2, 独立上线): IMP-5 + IMP-6

IMP-5 (英文 action 映射) + IMP-6 (结构化补充) 可独立上线。

**文件改动**:
- `src/core/agents/generic_agent.py` — `_infer_stock_actions` 重构
- `src/core/orchestrator/execution/engine.py` — `_supplement_missing_data` 扩展

**测试**:
- `tests/unit/test_infer_stock_actions_en.py`
- `tests/unit/test_supplement_structured.py`

### Step 4 (P3, 长期): IMP-7

覆盖率语义匹配，按需实施。

---

## 六、风险评估

| 风险 | 概率 | 严重度 | 缓解 |
|------|------|--------|------|
| IMP-1 news_search 超时拖慢数据收集 | 中 | 低 | 设置 30s 超时；失败不阻塞 |
| IMP-2 降级搜索查询词不精准 | 中 | 低 | 查询词基于 aspect 关键词动态生成，有 fallback |
| IMP-3 重收集导致引擎超时 | 低 | 中 | 最多 1 轮；总超时由 engine 的 batch timeout 控制 |
| IMP-4 冲突裁决规则误判 | 低 | 中 | 保留所有原始值，裁决结果标记依据，下游可审查 |
| IMP-5 英文关键词不完整 | 低 | 低 | 有 fallback 到默认 actions |
| IMP-6 stock_data 重试重复调用 akshare | 中 | 低 | 利用 StockDataSkill._memory_cache 缓存 |
| 所有改动引入回归 | 低 | 严重 | 每步 TDD + 全量回归测试 |

---

## 七、预期效果

| 指标 | 当前 | IMP-1+2 后 | 全部实施后 |
|------|------|-----------|-----------|
| 财务 aspect 结构化数据获取率 | ~60% (akshare 不稳定) | ~85% (降级补充) | ~90% |
| 新闻时效性数据覆盖率 | 0% | ~70% | ~80% |
| 低质量数据触发重收集率 | 0% | 0% | ~60% |
| 数值冲突解决率 | 0% | 0% | ~80% |
| English aspect 精确 action 选择率 | ~20% | ~20% | ~80% |
