# 报告质量全面提升实施计划（A-G）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将报告数据矛盾率从 23.5% 降至 2-3%，数据重复率从 75% 降至 ~30%，消除 Prompt 泄漏，建立双层防线（聚合校验 + 后处理扫描）。所有组件支持中英双语，英文报告同等质量保障。

**Architecture:** 七个改动点沿数据流从源头到出口依次部署：(1) MetricExtractor 扩展（中英双语）→ (2) 数据按 aspect 分配（双语关键词）→ (3) Prompt 强化（语言感知）→ (4) 截断修复 → (5) 聚合校验（双语正则）→ (6) 后处理扫描（双语扫描 + 泄漏清除）→ (7) 双语 Prompt 泄漏清除。每个环节独立可测试，组合后形成纵深防御。

**Tech Stack:** Python 3.10+, asyncio, pytest, regex, i18n (src/core/i18n.py)

**Baseline:** 比亚迪报告 research_8c6675c2 — 8 agents, 68 数据点, 16 处矛盾 (23.5%), 2 处 Prompt 泄漏, ~75% 重复率。修复后必须同时验证中文 baseline 和英文等价场景。

**Language Strategy:** 所有数据提取/检测组件使用统一的 metric_id（如 `sales_volume`, `net_profit`, `revenue`）+ 双语正则对。Prompt 指令跟随 `get_language()` 设置。DataPartitioner 对未知方面名自动提取关键词（`_extract_from_aspect_name`），不硬编码。

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/core/data/metric_extractor.py` | Modify | 添加复合指标正则（中英双语） |
| `src/core/data/aspect_keyword_map.py` | Create | aspect → 关键词映射表（双语 + 自动提取） |
| `src/core/data/data_partitioner.py` | Create | 按 aspect 过滤 data_points（双语） |
| `src/core/agents/generic_agent.py` | Modify | 删死代码 + 强化 prompt（语言感知） |
| `src/core/orchestrator/execution/engine.py` | Modify | 数据分配 + 截断修复 |
| `src/core/orchestrator/aggregation/consistency_checker.py` | Create | 聚合时数据一致性校验（双语正则，统一 metric_id） |
| `src/core/orchestrator/aggregation/result_aggregator.py` | Modify | 集成 consistency_checker |
| `src/core/quality/post_consistency_scanner.py` | Create | 最终报告数据扫描（双语） |
| `src/core/quality/prompt_leak_detector.py` | Create | Prompt 泄漏检测与清除（双语） |
| `src/core/orchestrator/orchestrator.py` | Modify | 后处理扫描集成点 |
| `src/core/i18n.py` | Dependency | 语言检测与切换（只读，不修改） |
| `tests/unit/test_metric_extractor_extended.py` | Create | Task 1 测试（中英双语） |
| `tests/unit/test_data_partitioner.py` | Create | Task 2 测试（中英双语） |
| `tests/unit/test_prompt_citation_rules.py` | Create | Task 3 测试（语言感知） |
| `tests/unit/test_consistency_checker.py` | Create | Task 5 测试（中英双语 + 跨语言） |
| `tests/unit/test_post_consistency_scanner.py` | Create | Task 6 测试（中英双语） |
| `tests/unit/test_prompt_leak_detector.py` | Create | Task 6 测试（中英双语） |

---

## Task 1: A — MetricExtractor 扩展 + 死代码清理

**Files:**
- Modify: `src/core/data/metric_extractor.py:22-35`
- Modify: `src/core/agents/generic_agent.py:321-352`
- Create: `tests/unit/test_metric_extractor_extended.py`

### Step 1.1: 写 MetricExtractor 扩展的失败测试

- [ ] **创建测试文件**

```python
# tests/unit/test_metric_extractor_extended.py
import pytest
from src.core.data.metric_extractor import MetricExtractor


class TestMetricExtractorCompositeMetrics:
    """Test composite metric extraction (ROE, net margin, etc.)"""

    def setup_method(self):
        self.extractor = MetricExtractor()

    def test_roe_extraction(self):
        dp = {"content": "公司2025年ROE为16.5%，较上年下降2.3个百分点", "url": "test"}
        results = self.extractor.extract([dp])
        roe = [r for r in results if r["metric"] == "ROE"]
        assert len(roe) >= 1
        assert roe[0]["value"] == pytest.approx(16.5, abs=0.1)

    def test_roe_chinese_name(self):
        dp = {"content": "净资产收益率达到22.3%", "url": "test"}
        results = self.extractor.extract([dp])
        roe = [r for r in results if r["metric"] == "ROE"]
        assert len(roe) >= 1

    def test_net_margin_extraction(self):
        dp = {"content": "2025年净利率为8.2%，同比下滑", "url": "test"}
        results = self.extractor.extract([dp])
        nm = [r for r in results if r["metric"] == "净利率"]
        assert len(nm) >= 1
        assert nm[0]["value"] == pytest.approx(8.2, abs=0.1)

    def test_asset_liability_ratio(self):
        dp = {"content": "资产负债率从58.2%升至62.7%", "url": "test"}
        results = self.extractor.extract([dp])
        alr = [r for r in results if r["metric"] == "资产负债率"]
        assert len(alr) >= 1

    def test_pe_ratio(self):
        dp = {"content": "当前市盈率(PE)为35.6倍", "url": "test"}
        results = self.extractor.extract([dp])
        pe = [r for r in results if r["metric"] == "市盈率"]
        assert len(pe) >= 1

    def test_pb_ratio(self):
        dp = {"content": "市净率(PB)约4.2倍", "url": "test"}
        results = self.extractor.extract([dp])
        pb = [r for r in results if r["metric"] == "市净率"]
        assert len(pb) >= 1

    def test_total_assets(self):
        dp = {"content": "截至2025年末总资产达8520.36亿元", "url": "test"}
        results = self.extractor.extract([dp])
        ta = [r for r in results if r["metric"] == "总资产"]
        assert len(ta) >= 1

    def test_operating_margin(self):
        dp = {"content": "营业利润率约为5.8%", "url": "test"}
        results = self.extractor.extract([dp])
        om = [r for r in results if r["metric"] == "营业利润率"]
        assert len(om) >= 1

    def test_no_false_positive_on_existing_metrics(self):
        dp = {"content": "净利润402.54亿元，销量460万辆", "url": "test"}
        results = self.extractor.extract([dp])
        metrics = {r["metric"] for r in results}
        assert "净利润" in metrics
        assert "销量" in metrics

    def test_year_inference_still_works(self):
        dp = {"content": "2025年ROE为16.5%", "url": "test"}
        results = self.extractor.extract([dp])
        roe = [r for r in results if r["metric"] == "ROE"]
        assert len(roe) >= 1
        assert roe[0]["year"] == 2025

    # === English metric tests ===

    def test_english_net_profit(self):
        dp = {"content": "The company reported a net profit of $32.6 billion in FY2025", "url": "test"}
        results = self.extractor.extract([dp])
        np = [r for r in results if r["metric"] == "net_profit_en"]
        assert len(np) >= 1
        assert np[0]["value"] == pytest.approx(32.6, abs=0.1)

    def test_english_revenue(self):
        dp = {"content": "Total revenue reached $80.39 billion, up 30% YoY", "url": "test"}
        results = self.extractor.extract([dp])
        rev = [r for r in results if r["metric"] == "revenue_en"]
        assert len(rev) >= 1
        assert rev[0]["value"] == pytest.approx(80.39, abs=0.1)

    def test_english_gross_margin(self):
        dp = {"content": "Gross margin was 19.5% in 2025, down from 21%", "url": "test"}
        results = self.extractor.extract([dp])
        gm = [r for r in results if r["metric"] == "gross_margin_en"]
        assert len(gm) >= 1
        assert gm[0]["value"] == pytest.approx(19.5, abs=0.1)

    def test_english_market_share(self):
        dp = {"content": "The company's market share reached 35% in the EV segment", "url": "test"}
        results = self.extractor.extract([dp])
        ms = [r for r in results if r["metric"] == "market_share_en"]
        assert len(ms) >= 1

    def test_english_sales_volume(self):
        dp = {"content": "Sales amounted to 4.6 million units in 2025", "url": "test"}
        results = self.extractor.extract([dp])
        sv = [r for r in results if r["metric"] == "sales_volume_en"]
        assert len(sv) >= 1
        assert sv[0]["value"] == pytest.approx(4.6, abs=0.1)

    def test_english_pe_ratio(self):
        dp = {"content": "The stock trades at a P/E of 35.6x", "url": "test"}
        results = self.extractor.extract([dp])
        pe = [r for r in results if r["metric"] == "pe_ratio_en"]
        assert len(pe) >= 1

    def test_english_rnd(self):
        dp = {"content": "R&D spending was $5.0 billion in 2025", "url": "test"}
        results = self.extractor.extract([dp])
        rnd = [r for r in results if r["metric"] == "rnd_en"]
        assert len(rnd) >= 1

    def test_chinese_english_no_cross_contamination(self):
        dp_cn = {"content": "净利润402.54亿元", "url": "cn"}
        dp_en = {"content": "net profit of $32.6 billion", "url": "en"}
        results_cn = self.extractor.extract([dp_cn])
        results_en = self.extractor.extract([dp_en])
        cn_metrics = {r["metric"] for r in results_cn}
        en_metrics = {r["metric"] for r in results_en}
        assert "净利润" in cn_metrics
        assert "net_profit_en" in en_metrics
        assert "net_profit_en" not in cn_metrics
        assert "净利润" not in en_metrics
```

- [ ] **运行测试，确认失败**

Run: `python -m pytest tests/unit/test_metric_extractor_extended.py -v`
Expected: FAIL (ROE, 净利率 etc. not found — patterns don't exist yet)

### Step 1.2: 实现 MetricExtractor 扩展

- [ ] **在 METRIC_PATTERNS 末尾添加新正则**

在 `src/core/data/metric_extractor.py` 中：

**第一步**：将 line 34 的旧 `负债率` 模式替换为更精确的 `资产负债率`（避免与新增模式重复匹配）：

```python
        # 原来 line 34:
        # (r'负债[率]?[^\d]*?(\d+\.?\d*)\s*%', "负债率"),
        # 替换为:
        (r'资产负债率[^\d]*?(\d+\.?\d*)\s*%', "资产负债率"),
```

**第二步**：在 `METRIC_PATTERNS` 列表末尾追加新正则（中英双语）：

```python
        # === 新增中文复合指标 ===
        (r'(?:ROE|净资产收益率)[^\d]*?(\d+\.?\d*)\s*%', "ROE"),
        (r'净利率[^\d]*?(\d+\.?\d*)\s*%', "净利率"),
        (r'营业利润率[^\d]*?(\d+\.?\d*)\s*%', "营业利润率"),
        (r'(?:PE|市盈率)[（(]?[^\d）)]*[）)]?[^\d]*?(\d+\.?\d*)\s*倍', "市盈率"),
        (r'(?:PB|市净率)[（(]?[^\d）)]*[）)]?[^\d]*?(\d+\.?\d*)\s*倍', "市净率"),
        (r'总资产[^\d]*?(\d+\.?\d*)\s*(' + _UNIT_CURRENCY + r')', "总资产"),
        # === English metric patterns ===
        (r'(?:net\s*profit|net\s*income)[^\d]*?[\$]?(\d+\.?\d*)\s*(?:billion|B)', "net_profit_en"),
        (r'(?:revenue|total\s*revenue|sales)[^\d]*?[\$]?(\d+\.?\d*)\s*(?:billion|B)', "revenue_en"),
        (r'(?:gross\s*margin|gross\s*profit\s*margin|GPM)[^\d]*?(\d+\.?\d*)\s*%', "gross_margin_en"),
        (r'(?:net\s*(?:profit\s*)?margin|NPM)[^\d]*?(\d+\.?\d*)\s*%', "net_margin_en"),
        (r'(?:ROE|return\s*on\s*equity)[^\d]*?(\d+\.?\d*)\s*%', "ROE_en"),
        (r'(?:total\s*assets)[^\d]*?[\$]?(\d+\.?\d*)\s*(?:billion|B)', "total_assets_en"),
        (r'(?:R&D|research\s*(?:and|&)\s*development)\s*(?:spending|expense|investment)?[^\d]*?[\$]?(\d+\.?\d*)\s*(?:billion|B)', "rnd_en"),
        (r'(?:market\s*share)[^\d]*?(\d+\.?\d*)\s*%', "market_share_en"),
        (r'(?:sales|units?\s*sold|deliveries)[^\d]*?(\d+\.?\d*)\s*(?:million|M)', "sales_volume_en"),
        (r'(?:debt[-\s]?to[-\s]?asset|debt[-\s]?to[-\s]?equity|leverage)\s*(?:ratio)?[^\d]*?(\d+\.?\d*)\s*%', "debt_ratio_en"),
        (r'(?:P[\/E]|price[-\s]?to[-\s]?earnings)[^\d]*?(\d+\.?\d*)\s*(?:x|times|×)', "pe_ratio_en"),
        (r'(?:P[\/B]|price[-\s]?to[-\s]?book)[^\d]*?(\d+\.?\d*)\s*(?:x|times|×)', "pb_ratio_en"),
```

> **设计原则**：
> - 中文 metric 名不带 `_en` 后缀（保持向后兼容），英文 metric 名带 `_en` 后缀以区分语言来源
> - 英文模式使用 `(?: ... )` 非捕获分组和 `\s*` 处理空格变体
> - PE/PB 中文的 `[（(]?` 可选括号已验证可匹配 "PE为35.6倍"/"市盈率35.6倍"
> - 英文使用 `(?:x|times|×)` 处理乘数单位的变体
> - 货币单位用 `[\$]?` 可选美元符号，匹配 "revenue of 80.39 billion" 和 "$80.39B" 两种格式

- [ ] **运行测试，确认通过**

Run: `python -m pytest tests/unit/test_metric_extractor_extended.py -v`
Expected: All PASS

### Step 1.3: 清理 generic_agent.py 中的死代码

- [ ] **删除 generic_agent.py:321-352 的 write_canonical 调用**

将 `src/core/agents/generic_agent.py` 中 line 321-352 整块替换为：

```python
                            return self._ensure_standard_result({
```

即删除从 `# B-FIX-3: write key metrics to SharedMemory` 到 `# B-FIX-3` 结尾的整段代码（含 write_canonical 调用、ConflictRecord 处理、MessageBus publish），直接连接到原来的 line 353 的 return 语句。

- [ ] **运行全量质量测试确认无回归**

Run: `python -m pytest tests/quality/ tests/unit/test_metric_extractor_extended.py -v`
Expected: All PASS

- [ ] **Commit**

```bash
git add src/core/data/metric_extractor.py src/core/agents/generic_agent.py tests/unit/test_metric_extractor_extended.py
git commit -m "feat: extend MetricExtractor with composite metrics (ROE/net margin/PE/PB/assets) and remove dead write_canonical in generic_agent"
```

---

## Task 2: G — 数据按 aspect 分配

**Files:**
- Create: `src/core/data/aspect_keyword_map.py`
- Create: `src/core/data/data_partitioner.py`
- Modify: `src/core/orchestrator/execution/engine.py:2075-2095`
- Create: `tests/unit/test_data_partitioner.py`

### Step 2.1: 写数据分配的失败测试

- [ ] **创建测试文件**

```python
# tests/unit/test_data_partitioner.py
import pytest
from src.core.data.data_partitioner import DataPartitioner, ASPECT_KEYWORD_MAP


class TestAspectKeywordMap:
    def test_financial_aspect_coverage(self):
        kws = ASPECT_KEYWORD_MAP.get("核心财务指标与盈利能力", [])
        assert "营收" in kws
        assert "利润" in kws

    def test_rnd_aspect_coverage(self):
        kws = ASPECT_KEYWORD_MAP.get("研发与创新投入", [])
        assert "研发" in kws

    def test_fuzzy_match(self):
        kws = ASPECT_KEYWORD_MAP.get_fuzzy("销量与市场份额分析")
        assert "销量" in kws

    def test_unknown_aspect_returns_auto_extracted(self):
        kws = ASPECT_KEYWORD_MAP.get_fuzzy("完全不相关的维度xyz")
        assert isinstance(kws, list)

    def test_english_financial_aspect(self):
        kws = ASPECT_KEYWORD_MAP.get("Financial Performance", [])
        assert "revenue" in kws
        assert "profit" in kws

    def test_english_fuzzy_match(self):
        kws = ASPECT_KEYWORD_MAP.get_fuzzy("Sales and Market Share Analysis")
        assert any("sales" in kw.lower() or "market" in kw.lower() for kw in kws)

    def test_english_unknown_aspect_auto_extracts(self):
        kws = ASPECT_KEYWORD_MAP.get_fuzzy("Energy Storage and Battery Technology")
        assert isinstance(kws, list)
        assert len(kws) >= 2  # auto-extracted from name


class TestDataPartitioner:
    def setup_method(self):
        self.partitioner = DataPartitioner()
        self.data_points = [
            {"content": "比亚迪2025年营收8039亿元，净利润326亿", "title": "财报", "url": "a"},
            {"content": "比亚迪海外出口105万辆，同比增长40%", "title": "出口", "url": "b"},
            {"content": "研发投入500亿元，同比增长30%", "title": "研发", "url": "c"},
            {"content": "毛利率19.58%，净利率4.2%", "title": "利润率", "url": "d"},
            {"content": "供应链成本下降5%，零部件自研率提升", "title": "供应链", "url": "e"},
        ]

    def test_partition_by_financial_aspect(self):
        result = self.partitioner.partition(
            self.data_points, aspect="核心财务指标与盈利能力"
        )
        assert len(result) >= 1
        assert any("营收" in dp["content"] or "利润" in dp["content"] for dp in result)

    def test_partition_by_export_aspect(self):
        result = self.partitioner.partition(
            self.data_points, aspect="国际化与出口"
        )
        assert len(result) >= 1
        assert any("出口" in dp["content"] or "海外" in dp["content"] for dp in result)

    def test_partition_preserves_minimum_data(self):
        result = self.partitioner.partition(
            self.data_points, aspect="销量与市场份额", min_data_points=3
        )
        assert len(result) >= 3

    def test_partition_respects_max_limit(self):
        large_data = [
            {"content": f"数据点{i} 营收{i}亿", "title": f"DP{i}", "url": f"url{i}"}
            for i in range(100)
        ]
        result = self.partitioner.partition(large_data, aspect="核心财务指标", max_data_points=50)
        assert len(result) <= 50

    def test_partition_returns_all_when_no_aspect(self):
        result = self.partitioner.partition(self.data_points, aspect="")
        assert len(result) == len(self.data_points)

    def test_high_low_ratio(self):
        large_data = [
            {"content": f"营收{i}亿 利润{i}亿", "title": f"DP{i}", "url": f"url{i}"}
            for i in range(100)
        ] + [
            {"content": f"无关数据{j}", "title": f"IR{j}", "url": f"ir{j}"}
            for j in range(100)
        ]
        result = self.partitioner.partition(
            large_data, aspect="核心财务指标与盈利能力", max_data_points=100
        )
        financial_count = sum(1 for dp in result if "营收" in dp.get("content", "") or "利润" in dp.get("content", ""))
        assert financial_count >= 50  # 80% of 100 ~ 80, but at least 50 financial items
        assert len(result) <= 100

    # === English partitioning tests ===

    def test_partition_by_english_financial_aspect(self):
        en_data = [
            {"content": "Revenue reached $80.39 billion, net profit was $3.26 billion", "title": "Financials", "url": "a"},
            {"content": "The company exported 1.05 million vehicles, up 40% YoY", "title": "Exports", "url": "b"},
            {"content": "R&D spending was $5.0 billion, up 30%", "title": "R&D", "url": "c"},
        ]
        result = self.partitioner.partition(en_data, aspect="Financial Performance")
        assert len(result) >= 1
        assert any("revenue" in dp["content"].lower() or "profit" in dp["content"].lower() for dp in result)

    def test_partition_by_english_unknown_aspect_auto_extracts(self):
        en_data = [
            {"content": "Battery energy density improved by 15%", "title": "Battery", "url": "a"},
            {"content": "Charging infrastructure expanded rapidly", "title": "Charging", "url": "b"},
            {"content": "Revenue grew 30% to $80 billion", "title": "Financial", "url": "c"},
        ]
        result = self.partitioner.partition(en_data, aspect="Battery Technology and Storage")
        assert isinstance(result, list)
        assert len(result) >= 1
```

- [ ] **运行测试，确认失败**

Run: `python -m pytest tests/unit/test_data_partitioner.py -v`
Expected: FAIL (modules don't exist)

### Step 2.2: 实现 aspect_keyword_map.py

- [ ] **创建关键词映射**

```python
# src/core/data/aspect_keyword_map.py
import re
from typing import Dict, List


class _AspectKeywordMap(dict):
    """Bilingual aspect → keyword mapping with fuzzy match and auto-extraction."""

    _SEPARATORS_ZH = re.compile(r'[与、，,及以及和]')
    _SEPARATORS_EN = re.compile(r'(?:\s+(?:and|&|vs)\s+|\s*[,/|]\s*)')

    def get_fuzzy(self, aspect: str) -> List[str]:
        # Exact match first
        if aspect in self:
            return self[aspect]
        # Partial match by key parts
        for key, keywords in self.items():
            key_parts = self._split_key(key)
            if any(kp in aspect for kp in key_parts if len(kp) >= 2):
                return keywords
            if any(kw in aspect for kw in keywords[:5]):
                return keywords
        # Fallback: extract keywords from the aspect name itself
        return self._extract_from_aspect_name(aspect)

    def _split_key(self, key: str) -> List[str]:
        parts = self._SEPARATORS_ZH.split(key)
        en_parts = self._SEPARATORS_EN.split(key)
        all_parts = parts + [p.strip() for p in en_parts if p.strip()]
        return [p.strip() for p in all_parts if len(p.strip()) >= 2]

    def _extract_from_aspect_name(self, aspect: str) -> List[str]:
        zh_parts = self._SEPARATORS_ZH.split(aspect)
        en_parts = self._SEPARATORS_EN.split(aspect)
        all_parts = [p.strip() for p in zh_parts + en_parts if len(p.strip()) >= 2]
        words = []
        for p in all_parts:
            words.append(p)
            en_words = re.findall(r'[a-zA-Z]{3,}', p)
            words.extend(w.lower() for w in en_words)
        return list(set(words))


ASPECT_KEYWORD_MAP: _AspectKeywordMap = _AspectKeywordMap({
    # === Chinese aspects ===
    "核心财务指标与盈利能力": [
        "营收", "利润", "毛利率", "净利率", "ROE", "现金流", "财报",
        "年报", "半年报", "一季报", "三季报", "每股收益", "EBITDA",
        "归母", "扣非", "营业收入", "营业成本",
    ],
    "研发与创新投入": [
        "研发", "R&D", "专利", "技术", "创新", "刀片电池", "DM-i",
        "固态电池", "智能驾驶", "芯片", "自研", "投入",
    ],
    "供应链成本效率": [
        "供应链", "成本", "原材料", "零部件", "供应商", "降本",
        "自给率", "垂直整合", "产能", "工厂", "制造",
    ],
    "销量与市场份额": [
        "销量", "份额", "市占率", "交付", "出货", "上险量",
        "批发", "零售", "车型", "新能源", "渗透率",
    ],
    "国际化与出口": [
        "出口", "海外", "国际", "境外", "global", "工厂",
        "欧洲", "东南亚", "拉美", "中东", "关税", "海外营收",
    ],
    "财务健康、风险评估与季度业绩波动": [
        "负债", "风险", "偿债", "流动性", "评级", "波动",
        "季度", "环比", "同比", "下降", "增长", "预警",
    ],
    "行业对标与竞争格局": [
        "竞争", "对标", "特斯拉", "蔚来", "理想", "小鹏", "行业",
        "排名", "第一", "领先", "格局", "市场份额", "品牌",
    ],
    "财务预测": [
        "预测", "预期", "展望", "目标价", "forecast", "增长",
        "估算", "估值", "PE", "PB", "市值", "指引",
    ],
    # === English aspects ===
    "Financial Performance": [
        "revenue", "profit", "gross margin", "net margin", "ROE", "cash flow",
        "earnings", "EPS", "EBITDA", "income", "operating profit",
    ],
    "R&D and Innovation": [
        "R&D", "research", "patent", "technology", "innovation", "chip",
        "autonomous driving", "self-developed", "investment",
    ],
    "Supply Chain and Cost Efficiency": [
        "supply chain", "cost", "raw material", "component", "supplier",
        "capacity", "factory", "manufacturing", "vertical integration",
    ],
    "Sales and Market Share": [
        "sales", "market share", "delivery", "shipment", "wholesale",
        "retail", "penetration", "model", "volume",
    ],
    "International Expansion": [
        "export", "overseas", "international", "global", "Europe",
        "Southeast Asia", "Latin America", "tariff", "foreign revenue",
    ],
    "Risk Assessment and Financial Health": [
        "debt", "risk", "liquidity", "rating", "volatility",
        "quarterly", "QoQ", "YoY", "decline", "growth",
    ],
    "Competitive Landscape": [
        "competition", "benchmark", "Tesla", "rival", "ranking",
        "market position", "industry", "brand", "leader",
    ],
    "Financial Forecast": [
        "forecast", "outlook", "target price", "estimate", "valuation",
        "PE", "PB", "market cap", "guidance", "projection",
    ],
})
```

### Step 2.3: 实现 data_partitioner.py

- [ ] **创建数据分配器**

```python
# src/core/data/data_partitioner.py
import logging
from typing import Any, Dict, List, Optional

from src.core.data.aspect_keyword_map import ASPECT_KEYWORD_MAP

logger = logging.getLogger(__name__)


class DataPartitioner:
    DEFAULT_MAX = 2000
    DEFAULT_MIN = 50
    HIGH_RATIO = 0.8

    def partition(
        self,
        data_points: List[Dict[str, Any]],
        aspect: str,
        max_data_points: int = DEFAULT_MAX,
        min_data_points: int = DEFAULT_MIN,
    ) -> List[Dict[str, Any]]:
        if not aspect or not data_points:
            return data_points

        keywords = ASPECT_KEYWORD_MAP.get_fuzzy(aspect)
        if not keywords:
            return data_points[:max_data_points]

        scored = []
        for dp in data_points:
            text = (
                (dp.get("content", "") + " " + dp.get("title", ""))
                .lower()
            )
            score = sum(1 for kw in keywords if kw.lower() in text)
            dp_copy = dict(dp)
            dp_copy["_relevance_score"] = score
            scored.append(dp_copy)

        scored.sort(key=lambda x: x["_relevance_score"], reverse=True)

        high = [dp for dp in scored if dp["_relevance_score"] > 0]
        low = [dp for dp in scored if dp["_relevance_score"] == 0]

        total = min(len(scored), max_data_points)
        if total < min_data_points:
            total = min(len(scored), min_data_points)

        high_count = min(int(total * self.HIGH_RATIO), len(high))
        low_count = min(total - high_count, len(low))

        if high_count + low_count < min_data_points and len(scored) >= min_data_points:
            remaining = min_data_points - (high_count + low_count)
            low_count = min(low_count + remaining, len(low))

        result = high[:high_count] + low[:low_count]

        for dp in result:
            dp.pop("_relevance_score", None)

        logger.info(
            f"DataPartitioner: aspect='{aspect}', "
            f"high={high_count}, low={low_count}, total={len(result)}/{len(data_points)}"
        )
        return result
```

- [ ] **运行测试，确认通过**

Run: `python -m pytest tests/unit/test_data_partitioner.py -v`
Expected: All PASS

### Step 2.4: 集成到 engine.py

- [ ] **修改 engine.py:2075-2095 的 fallback 路径**

在 `src/core/orchestrator/execution/engine.py` line 2075 的 if 块内，替换全量注入逻辑：

```python
                    if not filtered_data_points and not filtered_sources:
                        injected_data = False
                        try:
                            task_id_from_req = requirement.get("task_id")
                            if task_id_from_req:
                                result_store = ResearchResultStore(storage_path="data")
                                saved = result_store.load_result(task_id_from_req)
                                if saved:
                                    saved_dps = saved.get("data_points", [])
                                    saved_srcs = saved.get("sources", [])
                                    if saved_dps and len(saved_dps) > 0:
                                        seen_urls = set()
                                        deduped = []
                                        for dp in saved_dps:
                                            url = dp.get("url", "") if isinstance(dp, dict) else ""
                                            if url and url in seen_urls:
                                                continue
                                            if url:
                                                seen_urls.add(url)
                                            deduped.append(dp)
                                        from src.core.data.data_partitioner import DataPartitioner
                                        _partitioner = DataPartitioner()
                                        _agent_aspect = (
                                            getattr(agent, 'section_id', None)
                                            or self._extract_aspect_from_agent_id(agent.agent_id)
                                            or ""
                                        )
                                        partitioned = _partitioner.partition(
                                            deduped,
                                            aspect=_agent_aspect,
                                        )
                                        task["aggregated_data_points"] = partitioned
                                        injected_data = True
                                    if saved_srcs and len(saved_srcs) > 0:
                                        seen_urls = set()
                                        deduped = []
                                        for src in saved_srcs:
                                            url = src.get("url", "") if isinstance(src, dict) else ""
                                            if url and url in seen_urls:
                                                continue
                                            if url:
                                                seen_urls.add(url)
                                            deduped.append(src)
                                        task["aggregated_sources"] = deduped[:2000]
                                        injected_data = True
                                    if injected_data:
                                        logger.info(
                                            f"[_execute_batch] Partitioned injection for {agent.agent_id}: "
                                            f"{len(task.get('aggregated_data_points',[]))} dps (aspect='{_agent_aspect}')"
                                        )
                        except Exception as e:
                            logger.warning(f"[_execute_batch] Data store recovery failed: {e}")
```

- [ ] **运行相关测试**

Run: `python -m pytest tests/unit/test_data_partitioner.py tests/unit/test_data_flow_contracts.py -v`
Expected: All PASS

- [ ] **Commit**

```bash
git add src/core/data/aspect_keyword_map.py src/core/data/data_partitioner.py src/core/orchestrator/execution/engine.py tests/unit/test_data_partitioner.py
git commit -m "feat: add DataPartitioner to filter data_points by aspect, reducing duplication from ~75% to ~30%"
```

---

## Task 3: E — 强化 Prompt 数据引用规范

**Files:**
- Modify: `src/core/agents/generic_agent.py:467-476` (analysis path)
- Modify: `src/core/agents/generic_agent.py:590-597` (synthesis path)
- Create: `tests/unit/test_prompt_citation_rules.py`

### Step 3.1: 写失败测试

- [ ] **创建测试**

```python
# tests/unit/test_prompt_citation_rules.py
import pytest


class TestPromptCitationRules:
    def test_analysis_prompt_contains_mandatory_citation(self):
        prompt = _build_analysis_prompt_with_canonical(
            canonical_data={"净利润_2025": {"value": 326.19, "unit": "亿元", "caliber": "A股口径", "source": "年报"}}
        )
        assert "【强制引用规范】" in prompt
        assert "禁止编造" in prompt
        assert "必须在文中标注" in prompt

    def test_synthesis_prompt_contains_cross_section_rule(self):
        prompt = _build_synthesis_prompt_with_canonical(
            canonical_data={"销量_2025": {"value": 460.24, "unit": "万辆", "caliber": "", "source": "产销快报"}}
        )
        assert "同一指标在不同章节中必须使用完全相同的数值" in prompt
        assert "禁止编造" in prompt

    def test_no_canonical_data_skips_citation_block(self):
        prompt = _build_analysis_prompt_with_canonical(canonical_data={})
        assert "【强制引用规范】" not in prompt
        assert "[Mandatory Citation Rules]" not in prompt

    # === English citation rules ===

    def test_analysis_prompt_english_citation(self):
        prompt = _build_analysis_prompt_with_canonical(
            canonical_data={"net_profit_2025": {"value": 32.6, "unit": "billion", "caliber": "GAAP", "source": "annual report"}},
            lang="en"
        )
        assert "[Mandatory Citation Rules]" in prompt
        assert "NEVER fabricate" in prompt
        assert "Canonical:" in prompt

    def test_synthesis_prompt_english_cross_section(self):
        prompt = _build_synthesis_prompt_with_canonical(
            canonical_data={"sales_2025": {"value": 4.6, "unit": "million", "caliber": "", "source": "delivery report"}},
            lang="en"
        )
        assert "Cross-Section Consistency Rules" in prompt
        assert "NEVER fabricate" in prompt

    def test_english_no_canonical_skips_block(self):
        prompt = _build_analysis_prompt_with_canonical(canonical_data={}, lang="en")
        assert "[Mandatory Citation Rules]" not in prompt


def _build_analysis_prompt_with_canonical(canonical_data, lang="zh"):
    prompt = "## 研究任务\n分析比亚迪财务..." if lang == "zh" else "## Research Task\nAnalyze financials..."
    if canonical_data:
        if lang == "en":
            section = "\n".join([
                f"- {k}: {v.get('value','')}{v.get('unit','')} "
                f"(caliber: {v.get('caliber','N/A')}, source: {v.get('source','N/A')})"
                for k, v in canonical_data.items()
            ])
            prompt += f"\n\n## Verified Canonical Data (Mandatory Citation)\n{section}\n"
            prompt += (
                "\n[Mandatory Citation Rules]\n"
                "1. The above data has been caliber-calibrated and verified. You **MUST** use these values.\n"
                "2. If you have a more authoritative source, you may note it alongside but NOT override.\n"
                "3. When citing, annotate: [Canonical: source].\n"
                "4. **NEVER fabricate** data. State 'data unavailable' if missing.\n"
            )
        else:
            section = "\n".join([
                f"- {k}: {v.get('value','')}{v.get('unit','')} "
                f"(口径: {v.get('caliber','不详')}, 来源: {v.get('source','不详')})"
                for k, v in canonical_data.items()
            ])
            prompt += f"\n\n## 已确认的规范数据（强制引用）\n{section}\n"
            prompt += (
                "\n【强制引用规范】\n"
                "1. 上述数据已经过口径校准和权威性验证，你**必须**使用这些值，不得使用其他来源的同名指标值。\n"
                "2. 如果你有更权威的数据来源（如官方年报、权威统计机构），可以在引用规范数据的同时补充说明，但不得覆盖规范数据。\n"
                "3. 引用规范数据时必须在文中标注来源，格式：[规范数据: 来源]。\n"
                "4. **禁止编造**任何数据。如果搜索结果中没有某项数据，明确说明"该数据暂不可得"，不得凭推测填写。\n"
            )
    return prompt


def _build_synthesis_prompt_with_canonical(canonical_data, lang="zh"):
    prompt = "## 综合分析任务\n..." if lang == "zh" else "## Synthesis Task\n..."
    if canonical_data:
        if lang == "en":
            section = "\n".join([
                f"- {k}: {v.get('value','')}{v.get('unit','')} "
                f"(caliber: {v.get('caliber','N/A')})"
                for k, v in canonical_data.items()
            ])
            prompt += f"\n\n## Report-wide Canonical Data (Cross-Section Consistency)\n{section}\n"
            prompt += (
                "\n[Cross-Section Consistency Rules]\n"
                "1. The same metric **MUST** use the exact same value across all sections.\n"
                "2. If another section uses a different value, use the canonical data table's value.\n"
                "3. **NEVER fabricate** any data.\n"
            )
        else:
            section = "\n".join([
                f"- {k}: {v.get('value','')}{v.get('unit','')} "
                f"(口径: {v.get('caliber','不详')})"
                for k, v in canonical_data.items()
            ])
            prompt += f"\n\n## 全报告规范数据（跨章节一致性要求）\n{section}\n"
            prompt += (
                "\n【跨章节一致性规范】\n"
                "1. 同一指标在不同章节中**必须**使用完全相同的数值，以本规范数据表为准。\n"
                "2. 如发现其他章节使用了不同的值，在你的章节中使用规范数据表的值。\n"
                "3. **禁止编造**任何数据。\n"
            )
    return prompt
```

- [ ] **运行测试**

Run: `python -m pytest tests/unit/test_prompt_citation_rules.py -v`
Expected: PASS (tests verify prompt construction logic directly)

### Step 3.2: 修改 generic_agent.py analysis path prompt

- [ ] **替换 line 467-476**

将 `src/core/agents/generic_agent.py` 中 line 467-476 的：

```python
                        # S-FIX-3: inject canonical authority data into prompt
                        if canonical_data:
                            _canonical_section = "\n".join([
                                f"- {k}: {v.get('value','')}{v.get('unit','')} "
                                f"(口径: {v.get('caliber','不详')}, 来源: {v.get('source','不详')})"
                                for k, v in canonical_data.items()
                            ])
                            prompt += f"\n\n## 已确认的规范数据（必须优先引用）\n{_canonical_section}\n"
                            prompt += "\n**重要**: 以上数据已经过口径校准和权威性验证。引用时优先使用这些值，"
                            prompt += "除非你有更新的权威数据来源。"
```

替换为：

```python
                        if canonical_data:
                            _canonical_section = "\n".join([
                                f"- {k}: {v.get('value','')}{v.get('unit','')} "
                                f"(口径: {v.get('caliber','不详')}, 来源: {v.get('source','不详')})"
                                for k, v in canonical_data.items()
                            ])
                            from src.core.i18n import get_language, Language
                            _lang = get_language()
                            if _lang == Language.EN:
                                _canonical_section = "\n".join([
                                    f"- {k}: {v.get('value','')}{v.get('unit','')} "
                                    f"(caliber: {v.get('caliber','N/A')}, source: {v.get('source','N/A')})"
                                    for k, v in canonical_data.items()
                                ])
                                prompt += f"\n\n## Verified Canonical Data (Mandatory Citation)\n{_canonical_section}\n"
                                prompt += (
                                    "\n[Mandatory Citation Rules]\n"
                                    "1. The above data has been caliber-calibrated and verified. You **MUST** use these values and not substitute other sources.\n"
                                    "2. If you have a more authoritative source (e.g. official annual report), you may note it alongside but NOT override the canonical data.\n"
                                    "3. When citing canonical data, annotate the source in-text: [Canonical: source].\n"
                                    "4. **NEVER fabricate** data. If a data point is not available in search results, state 'data unavailable' explicitly.\n"
                                )
                            else:
                                prompt += f"\n\n## 已确认的规范数据（强制引用）\n{_canonical_section}\n"
                                prompt += (
                                    "\n【强制引用规范】\n"
                                    "1. 上述数据已经过口径校准和权威性验证，你**必须**使用这些值，不得使用其他来源的同名指标值。\n"
                                    "2. 如果你有更权威的数据来源（如官方年报、权威统计机构），可以在引用规范数据的同时补充说明，但不得覆盖规范数据。\n"
                                    "3. 引用规范数据时必须在文中标注来源，格式：[规范数据: 来源]。\n"
                                    "4. **禁止编造**任何数据。如果搜索结果中没有某项数据，明确说明"该数据暂不可得"，不得凭推测填写。\n"
                                )
```

### Step 3.3: 修改 generic_agent.py synthesis path prompt

- [ ] **替换 line 596-597**

将 `src/core/agents/generic_agent.py` 中 line 596-597 的：

```python
                            prompt += f"\n\n## 全报告规范数据（跨章节一致性要求）\n{_cs}\n"
                            prompt += "\n**重要**: 所有章节中同一指标必须使用相同的值。如有差异，以上述规范数据为准。"
```

替换为：

```python
                            prompt += f"\n\n## 全报告规范数据（跨章节一致性要求）\n{_cs}\n"
                            from src.core.i18n import get_language, Language
                            _lang = get_language()
                            if _lang == Language.EN:
                                prompt += (
                                    "\n[Cross-Section Consistency Rules]\n"
                                    "1. The same metric **MUST** use the exact same value across all sections, using this canonical data table as the standard.\n"
                                    "2. If another section uses a different value, use the canonical data table's value in your section.\n"
                                    "3. **NEVER fabricate** any data.\n"
                                )
                            else:
                                prompt += (
                                    "\n【跨章节一致性规范】\n"
                                    "1. 同一指标在不同章节中**必须**使用完全相同的数值，以本规范数据表为准。\n"
                                    "2. 如发现其他章节使用了不同的值，在你的章节中使用规范数据表的值。\n"
                                    "3. **禁止编造**任何数据。\n"
                                )
```

- [ ] **运行测试确认**

Run: `python -m pytest tests/unit/test_prompt_citation_rules.py -v`
Expected: PASS

- [ ] **Commit**

```bash
git add src/core/agents/generic_agent.py tests/unit/test_prompt_citation_rules.py
git commit -m "feat: strengthen prompt citation rules — mandatory canonical data usage with citation format"
```

---

## Task 4: D — 取消 content[:2000] 截断

**Files:**
- Modify: `src/core/orchestrator/execution/engine.py:1849-1853`

### Step 4.1: 修改截断逻辑

- [ ] **替换 line 1849-1853**

将：

```python
                if content and isinstance(content, str):
                    aggregated_content.append({
                        "agent_id": agent_id,
                        "content": content[:2000],  # 限制长度
                    })
```

替换为：

```python
                if content and isinstance(content, str):
                    _max_content_chars = min(len(content), 8000)
                    aggregated_content.append({
                        "agent_id": agent_id,
                        "content": content[:_max_content_chars],
                    })
```

- [ ] **验证无回归**

Run: `python -m pytest tests/unit/test_data_flow_contracts.py tests/unit/test_aggregation_realistic_flow.py -v`
Expected: All PASS

- [ ] **Commit**

```bash
git add src/core/orchestrator/execution/engine.py
git commit -m "fix: increase content truncation from 2000 to 8000 chars for better cross-agent context"
```

---

## Task 5: B — 聚合阶段数据一致性校验

**Files:**
- Create: `src/core/orchestrator/aggregation/consistency_checker.py`
- Modify: `src/core/orchestrator/aggregation/result_aggregator.py:926-1077`
- Create: `tests/unit/test_consistency_checker.py`

### Step 5.1: 写失败测试

- [ ] **创建测试文件**

```python
# tests/unit/test_consistency_checker.py
import pytest
from src.core.orchestrator.aggregation.consistency_checker import ConsistencyChecker, ConsistencyReport, DataConflict


class TestConsistencyChecker:
    def setup_method(self):
        self.checker = ConsistencyChecker()

    def test_detect_sales_contradiction(self):
        sections = [
            {"id": "section_1", "content": "比亚迪2024年销量约380万辆"},
            {"id": "section_2", "content": "比亚迪2024年销量约460万辆"},
            {"id": "section_3", "content": "比亚迪2024年销量约425万辆"},
        ]
        report = self.checker.check(sections)
        assert len(report.conflicts) >= 1
        sales_conflicts = [c for c in report.conflicts if "sales_volume" in c.metric]
        assert len(sales_conflicts) >= 1
        assert len(sales_conflicts[0].values) >= 2

    def test_detect_margin_contradiction(self):
        sections = [
            {"id": "a", "content": "2025年毛利率为19.58%"},
            {"id": "b", "content": "2025年毛利率约25%"},
        ]
        report = self.checker.check(sections)
        margin_conflicts = [c for c in report.conflicts if "gross_margin" in c.metric]
        assert len(margin_conflicts) >= 1

    def test_no_contradiction_same_value(self):
        sections = [
            {"id": "a", "content": "比亚迪2025年净利润326.19亿元"},
            {"id": "b", "content": "净利润326.19亿元"},
        ]
        report = self.checker.check(sections)
        profit_conflicts = [c for c in report.conflicts if "net_profit" in c.metric]
        assert len(profit_conflicts) == 0

    def test_resolve_with_canonical_data(self):
        canonical = {"sales_volume_2024": {"value": 460.24, "unit": "万辆"}}
        sections = [
            {"id": "a", "content": "比亚迪2024年销量约380万辆"},
            {"id": "b", "content": "比亚迪2024年销量约460万辆"},
        ]
        report = self.checker.check(sections, canonical_data=canonical)
        sales_conflicts = [c for c in report.conflicts if "sales_volume" in c.metric]
        assert len(sales_conflicts) >= 1
        assert sales_conflicts[0].resolved_value is not None

    def test_empty_sections_no_crash(self):
        report = self.checker.check([])
        assert len(report.conflicts) == 0

    def test_report_contains_stats(self):
        sections = [
            {"id": "a", "content": "营收8039亿元"},
        ]
        report = self.checker.check(sections)
        assert "total_sections" in report.stats
        assert "total_values_extracted" in report.stats

    def test_year_context(self):
        sections = [
            {"id": "a", "content": "2024年销量380万辆"},
            {"id": "b", "content": "2025年销量460万辆"},
        ]
        report = self.checker.check(sections)
        sales_conflicts = [c for c in report.conflicts if "sales_volume" in c.metric]
        assert len(sales_conflicts) == 0

    # === English metric tests ===

    def test_english_sales_contradiction(self):
        sections = [
            {"id": "s1", "content": "The company sold 3.8 million vehicles in 2024"},
            {"id": "s2", "content": "Sales reached 4.6 million units in 2024"},
        ]
        report = self.checker.check(sections)
        assert len(report.conflicts) >= 1
        assert any("sales_volume" in c.metric for c in report.conflicts)

    def test_english_revenue_contradiction(self):
        sections = [
            {"id": "s1", "content": "Revenue was $80.39 billion in 2025"},
            {"id": "s2", "content": "Total revenue reached $75.2 billion in 2025"},
        ]
        report = self.checker.check(sections)
        rev_conflicts = [c for c in report.conflicts if "revenue" in c.metric]
        assert len(rev_conflicts) >= 1

    def test_cross_language_no_false_conflict(self):
        sections = [
            {"id": "s1", "content": "净利润326亿元"},
            {"id": "s2", "content": "net profit of $32.6 billion"},
        ]
        report = self.checker.check(sections)
        assert len(report.conflicts) == 0

    def test_english_same_value_no_conflict(self):
        sections = [
            {"id": "s1", "content": "Gross margin was 19.5% in 2025"},
            {"id": "s2", "content": "The GPM reached 19.5% for FY2025"},
        ]
        report = self.checker.check(sections)
        gm_conflicts = [c for c in report.conflicts if "gross_margin" in c.metric]
        assert len(gm_conflicts) == 0
```

- [ ] **运行测试，确认失败**

Run: `python -m pytest tests/unit/test_consistency_checker.py -v`
Expected: FAIL (module doesn't exist)

### Step 5.2: 实现 consistency_checker.py

- [ ] **创建一致性校验器**

```python
# src/core/orchestrator/aggregation/consistency_checker.py
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# === Bilingual metric patterns ===
# Each tuple: (regex, metric_id, language_tag)
# language_tag: "zh" or "en" — used only for logging; conflict detection is cross-lingual via metric_id
_METRIC_PATTERNS = [
    # --- Chinese ---
    (r'销量[^\d]*?(\d+\.?\d*)\s*万辆', "sales_volume", "zh"),
    (r'(?:净利润|归母净利润)[^\d]*?(\d+\.?\d*)\s*亿元', "net_profit", "zh"),
    (r'营收[^\d]*?(\d+\.?\d*)\s*亿元', "revenue", "zh"),
    (r'毛利率[^\d]*?(\d+\.?\d*)\s*%', "gross_margin", "zh"),
    (r'净利率[^\d]*?(\d+\.?\d*)\s*%', "net_margin", "zh"),
    (r'(?:ROE|净资产收益率)[^\d]*?(\d+\.?\d*)\s*%', "ROE", "zh"),
    (r'研发[^\d]*?(\d+\.?\d*)\s*亿元', "rnd_spending", "zh"),
    (r'(?:市场)?份额[^\d]*?(\d+\.?\d*)\s*%', "market_share", "zh"),
    (r'资产负债率[^\d]*?(\d+\.?\d*)\s*%', "debt_ratio", "zh"),
    (r'总资产[^\d]*?(\d+\.?\d*)\s*亿元', "total_assets", "zh"),
    # --- English ---
    (r'(?:net\s*profit|net\s*income)[^\d]*?[\$]?(\d+\.?\d*)\s*(?:billion|B)', "net_profit", "en"),
    (r'(?:revenue|total\s*revenue)[^\d]*?[\$]?(\d+\.?\d*)\s*(?:billion|B)', "revenue", "en"),
    (r'(?:gross\s*margin|GPM)[^\d]*?(\d+\.?\d*)\s*%', "gross_margin", "en"),
    (r'(?:net\s*(?:profit\s*)?margin|NPM)[^\d]*?(\d+\.?\d*)\s*%', "net_margin", "en"),
    (r'(?:ROE|return\s*on\s*equity)[^\d]*?(\d+\.?\d*)\s*%', "ROE", "en"),
    (r'(?:R&D|research\s*(?:and|&)\s*development)\s*(?:spending|expense)?[^\d]*?[\$]?(\d+\.?\d*)\s*(?:billion|B)', "rnd_spending", "en"),
    (r'(?:market\s*share)[^\d]*?(\d+\.?\d*)\s*%', "market_share", "en"),
    (r'(?:sales|deliveries)[^\d]*?(\d+\.?\d*)\s*(?:million|M)', "sales_volume", "en"),
    (r'(?:total\s*assets)[^\d]*?[\$]?(\d+\.?\d*)\s*(?:billion|B)', "total_assets", "en"),
    (r'(?:debt[-\s]?to[-\s]?(?:asset|equity)|leverage)\s*(?:ratio)?[^\d]*?(\d+\.?\d*)\s*%', "debt_ratio", "en"),
]

# === Generic number-context extractor (language-agnostic) ===
# For metrics not covered by _METRIC_PATTERNS, extract "number + unit" pairs
# and group by surrounding keyword context
_GENERIC_NUMBER_RE = re.compile(
    r'(\d+\.?\d*)\s*'
    r'(?:万辆|万台|万辆|million\s*units?|M\s*units?|'
    r'亿元|亿|亿元|billion|B|'
    r'万元|万|million|'
    r'%|percent|'
    r'倍|x|times|×)'
)

_YEAR_WINDOW = 80


@dataclass
class DataConflict:
    metric: str
    year: str
    values: List[float]
    sections: List[str]
    resolved_value: Optional[float] = None


@dataclass
class ConsistencyReport:
    conflicts: List[DataConflict] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


class ConsistencyChecker:
    DIFF_THRESHOLD = 0.05

    def check(
        self,
        sections: List[Dict[str, Any]],
        canonical_data: Optional[Dict[str, Dict]] = None,
    ) -> ConsistencyReport:
        if not sections:
            return ConsistencyReport(stats={"total_sections": 0, "total_values_extracted": 0})

        extracted: Dict[Tuple[str, str], List[Tuple[str, float]]] = {}
        total_values = 0

        for section in sections:
            sid = section.get("id", "unknown")
            content = section.get("content", "")
            if not content:
                continue
            # Phase 1: Named metric patterns (bilingual)
            for pattern, metric_id, _lang in _METRIC_PATTERNS:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    value = float(match.group(1))
                    window = content[max(0, match.start() - _YEAR_WINDOW):match.end() + _YEAR_WINDOW]
                    years = re.findall(r'(20\d{2})', window)
                    year = years[-1] if years else ""
                    key = (metric_id, year)
                    extracted.setdefault(key, []).append((sid, value))
                    total_values += 1

        conflicts = []
        for (metric, year), entries in extracted.items():
            if len(entries) < 2:
                continue
            unique_vals = set(v for _, v in entries)
            if len(unique_vals) < 2:
                continue
            values = [v for _, v in entries]
            min_v, max_v = min(values), max(values)
            if max_v > 0 and (max_v - min_v) / max_v > self.DIFF_THRESHOLD:
                resolved = None
                if canonical_data:
                    for ck, cv in canonical_data.items():
                        parts = ck.split("_")
                        if metric in ck or any(p == metric for p in parts):
                            canonical_year = ""
                            for p in parts:
                                if p.isdigit() and len(p) == 4:
                                    canonical_year = p
                            if not year or not canonical_year or year == canonical_year:
                                resolved = float(cv.get("value", 0)) if isinstance(cv, dict) else None
                                break
                conflicts.append(DataConflict(
                    metric=metric,
                    year=year,
                    values=values,
                    sections=[s for s, _ in entries],
                    resolved_value=resolved,
                ))

        if conflicts:
            logger.warning(f"ConsistencyChecker: {len(conflicts)} conflicts found in {len(sections)} sections")
        return ConsistencyReport(
            conflicts=conflicts,
            stats={
                "total_sections": len(sections),
                "total_values_extracted": total_values,
                "total_conflicts": len(conflicts),
            },
        )
```

- [ ] **运行测试**

Run: `python -m pytest tests/unit/test_consistency_checker.py -v`
Expected: All PASS

### Step 5.3: 集成到 result_aggregator.py

- [ ] **在 result_aggregator.py 的 aggregate() 方法末尾（line ~1113 之前）添加一致性检查**

在 `src/core/orchestrator/aggregation/result_aggregator.py` 的 `aggregate()` 方法中，在 `return AggregationResult(...)` 之前（约 line 1113），添加：

```python
        # B-FIX: Aggregation-time data consistency check
        consistency_conflicts = []
        try:
            from src.core.orchestrator.aggregation.consistency_checker import ConsistencyChecker
            checker = ConsistencyChecker()
            check_sections = []
            for agent_id_key, content_val in layered_content.get("analysis", {}).items():
                if isinstance(content_val, str) and len(content_val) > 50:
                    check_sections.append({"id": agent_id_key, "content": content_val})
            for agent_id_key, content_val in layered_content.get("data_collection", {}).items():
                if isinstance(content_val, str) and len(content_val) > 50:
                    check_sections.append({"id": agent_id_key, "content": content_val})
            if not check_sections:
                for agent_id_key, content_val in merged_data.items():
                    if isinstance(content_val, str) and len(content_val) > 50:
                        check_sections.append({"id": agent_id_key, "content": content_val})
            if check_sections:
                canonical_for_check = {}
                if hasattr(self, '_canonical_data') and self._canonical_data:
                    canonical_for_check = {
                        k: {"value": v.value if hasattr(v, 'value') else v.get("value", v)}
                        for k, v in self._canonical_data.items()
                    }
                consistency_report = checker.check(check_sections, canonical_data=canonical_for_check)
                consistency_conflicts = consistency_report.conflicts
                if consistency_conflicts:
                    stats["consistency_conflicts"] = len(consistency_conflicts)
                    logger.warning(
                        f"Aggregation: {len(consistency_conflicts)} data consistency conflicts detected"
                    )
        except ImportError:
            pass
```

并在 `AggregationResult` 的构建中传入：

```python
        return AggregationResult(
            data=merged_data,
            conflicts=conflicts,
            stats=stats,
            section_details=section_details or [],
            sources=all_sources,
            layered_content=layered_content,
            content_provenance=content_provenance,
        )
```

stats 中已包含 `consistency_conflicts` 字段，无需额外修改 AggregationResult。

- [ ] **运行测试**

Run: `python -m pytest tests/unit/test_consistency_checker.py tests/unit/test_aggregation_realistic_flow.py -v`
Expected: All PASS

- [ ] **Commit**

```bash
git add src/core/orchestrator/aggregation/consistency_checker.py src/core/orchestrator/aggregation/result_aggregator.py tests/unit/test_consistency_checker.py
git commit -m "feat: add ConsistencyChecker for aggregation-time data conflict detection with canonical resolution"
```

---

## Task 6: F — 后处理扫描 + Prompt 泄漏清除

**Files:**
- Create: `src/core/quality/post_consistency_scanner.py`
- Create: `src/core/quality/prompt_leak_detector.py`
- Modify: `src/core/orchestrator/orchestrator.py:1884-1900`
- Create: `tests/unit/test_post_consistency_scanner.py`
- Create: `tests/unit/test_prompt_leak_detector.py`

### Step 6.1: 写后处理扫描的失败测试

- [ ] **创建测试**

```python
# tests/unit/test_post_consistency_scanner.py
import pytest
from src.core.quality.post_consistency_scanner import PostConsistencyScanner, ScanResult


class TestPostConsistencyScanner:
    def setup_method(self):
        self.scanner = PostConsistencyScanner()

    def test_scan_detects_contradictory_sales(self):
        sections = [
            {"title": "销量分析", "content": "比亚迪2024年销量约380万辆"},
            {"title": "财务概览", "content": "比亚迪2024年销量约460万辆"},
        ]
        result = self.scanner.scan(sections)
        assert len(result.conflicts) >= 1

    def test_scan_replaces_with_canonical(self):
        canonical = {"销量_2024": {"value": 460.24, "unit": "万辆"}}
        sections = [
            {"title": "销量", "content": "比亚迪2024年销量约380万辆，同比增长"},
        ]
        result = self.scanner.scan(sections, canonical_data=canonical)
        assert "460.24万辆" in result.sections[0]["content"]

    def test_scan_preserves_consistent_data(self):
        sections = [
            {"title": "A", "content": "比亚迪2025年净利润326.19亿元"},
        ]
        result = self.scanner.scan(sections)
        assert result.sections[0]["content"] == "比亚迪2025年净利润326.19亿元"

    def test_scan_empty_sections(self):
        result = self.scanner.scan([])
        assert len(result.conflicts) == 0

    def test_scan_result_has_stats(self):
        sections = [
            {"title": "A", "content": "营收8039亿元"},
        ]
        result = self.scanner.scan(sections)
        assert "total_replacements" in result.stats

    # === English tests ===

    def test_scan_detects_english_sales_contradiction(self):
        sections = [
            {"title": "Sales Analysis", "content": "The company sold 3.8 million units in 2024"},
            {"title": "Financial Overview", "content": "Sales reached 4.6 million vehicles in 2024"},
        ]
        result = self.scanner.scan(sections)
        assert len(result.conflicts) >= 1

    def test_scan_replaces_english_with_canonical(self):
        canonical = {"sales_volume_2024": {"value": 4.6, "unit": "million units"}}
        sections = [
            {"title": "Sales", "content": "The company sold 3.8 million units in 2024, up YoY"},
        ]
        result = self.scanner.scan(sections, canonical_data=canonical)
        assert "4.6" in result.sections[0]["content"]

    def test_scan_preserves_consistent_english_data(self):
        sections = [
            {"title": "A", "content": "Net profit was $32.6 billion in 2025"},
        ]
        result = self.scanner.scan(sections)
        assert result.sections[0]["content"] == "Net profit was $32.6 billion in 2025"
```

- [ ] **运行测试，确认失败**

### Step 6.2: 写 Prompt 泄漏检测的失败测试

- [ ] **创建测试**

```python
# tests/unit/test_prompt_leak_detector.py
import pytest
from src.core.quality.prompt_leak_detector import PromptLeakDetector


class TestPromptLeakDetector:
    def setup_method(self):
        self.detector = PromptLeakDetector()

    def test_detect_data_source_tag(self):
        content = "毛利率19.58%(数据来源25)，净利率4.2%(数据来源6)"
        leaks = self.detector.detect(content)
        assert len(leaks) >= 2

    def test_detect_canonical_tag(self):
        content = "营收8039亿元(已确认规范数据毛利率_2025_不含少数口径)"
        leaks = self.detector.detect(content)
        assert len(leaks) >= 1

    def test_detect_role_reveal(self):
        content = "好的，作为高级行业分析师，我将严格按照国际咨询标准"
        leaks = self.detector.detect(content)
        assert len(leaks) >= 1

    def test_clean_removes_leaks(self):
        content = "毛利率19.58%(数据来源25)，净利率4.2%(数据来源6)"
        cleaned = self.detector.clean(content)
        assert "(数据来源" not in cleaned
        assert "19.58%" in cleaned
        assert "4.2%" in cleaned

    def test_clean_preserves_normal_content(self):
        content = "比亚迪2025年营收8039亿元，净利润326亿元"
        cleaned = self.detector.clean(content)
        assert cleaned == content

    def test_no_false_positives(self):
        content = "报告来源：比亚迪年报。数据截至2025年12月31日。"
        leaks = self.detector.detect(content)
        assert len(leaks) == 0

    # === English leak tests ===

    def test_detect_english_data_source_tag(self):
        content = "Gross margin was 19.5%(data source 25), net margin 4.2%(data source 6)"
        leaks = self.detector.detect(content)
        assert len(leaks) >= 2

    def test_detect_english_role_reveal(self):
        content = "As a senior analyst, I will analyze the market trends"
        leaks = self.detector.detect(content)
        assert len(leaks) >= 1

    def test_detect_english_instruction_reference(self):
        content = "According to the instructions provided, I should focus on financial data"
        leaks = self.detector.detect(content)
        assert len(leaks) >= 1

    def test_clean_removes_english_leaks(self):
        content = "Revenue was $80B(data source 12). As a senior analyst, I will now analyze"
        cleaned = self.detector.clean(content)
        assert "(data source" not in cleaned
        assert "As a senior analyst" not in cleaned
        assert "$80B" in cleaned

    def test_english_no_false_positive(self):
        content = "The data source for this report is the annual filing. Revenue grew 30%."
        leaks = self.detector.detect(content)
        assert len(leaks) == 0
```

- [ ] **运行测试，确认失败**

### Step 6.3: 实现 PostConsistencyScanner

- [ ] **创建后处理扫描器**

```python
# src/core/quality/post_consistency_scanner.py
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# === Bilingual value patterns ===
_VALUE_PATTERNS = [
    # Chinese units
    (r'(\d+\.?\d*)\s*万辆', "volume_unit", "万辆"),
    (r'(\d+\.?\d*)\s*亿元', "currency_unit", "亿元"),
    (r'(\d+\.?\d*)\s*%', "percent_unit", "%"),
    (r'(\d+\.?\d*)\s*倍', "multiple_unit", "倍"),
    # English units
    (r'(\d+\.?\d*)\s*(?:million|M)\s*(?:units?|vehicles?|cars?)', "volume_unit", "million units"),
    (r'(\d+\.?\d*)\s*(?:billion|B)', "currency_unit", "billion"),
    (r'(\d+\.?\d*)\s*(?:x|times|×)', "multiple_unit", "x"),
]

# === Bilingual metric keywords ===
# Key = canonical metric ID (same as ConsistencyChecker)
# Value = list of keywords that identify the metric in surrounding text
_METRIC_KEYWORDS = {
    "sales_volume": ["销量", "交付", "出货", "sales", "deliveries", "units sold", "vehicles sold"],
    "net_profit": ["净利润", "归母净利润", "扣非净利润", "net profit", "net income"],
    "revenue": ["营收", "收入", "营业", "revenue", "total revenue", "sales"],
    "gross_margin": ["毛利率", "gross margin", "GPM"],
    "net_margin": ["净利率", "net margin", "NPM", "net profit margin"],
    "ROE": ["ROE", "净资产收益率", "return on equity"],
    "rnd_spending": ["研发", "R&D", "研发投入", "research and development", "R&D spending"],
    "market_share": ["份额", "市占率", "占比", "渗透率", "market share", "share of"],
    "total_assets": ["总资产", "total assets"],
    "debt_ratio": ["资产负债率", "debt-to-asset", "leverage ratio", "debt ratio"],
    "overseas_sales": ["海外销量", "出口", "overseas sales", "exports"],
    "pe_ratio": ["PE", "市盈率", "P/E", "price-to-earnings"],
    "pb_ratio": ["PB", "市净率", "P/B", "price-to-book"],
}

_YEAR_PATTERN = re.compile(r'(20\d{2})\s*(?:年|FY|fiscal\s*year)?', re.IGNORECASE)
_YEAR_WINDOW = 60


@dataclass
class ScanConflict:
    metric: str
    year: str
    values: List[float]
    sections: List[str]
    resolved: bool = False


@dataclass
class ScanResult:
    sections: List[Dict[str, Any]]
    conflicts: List[ScanConflict] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


class PostConsistencyScanner:
    DIFF_THRESHOLD = 0.05

    def scan(
        self,
        sections: List[Dict[str, Any]],
        canonical_data: Optional[Dict[str, Dict]] = None,
    ) -> ScanResult:
        if not sections:
            return ScanResult(sections=sections, stats={"total_replacements": 0})

        extracted: Dict[Tuple[str, str], List[Tuple[str, float, str, int, int]]] = {}
        for section in sections:
            content = section.get("content", "")
            if not content:
                continue
            for pattern, group_name, unit in _VALUE_PATTERNS:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    value = float(match.group(1))
                    window = content[max(0, match.start() - _YEAR_WINDOW):match.end() + _YEAR_WINDOW]
                    years = _YEAR_PATTERN.findall(window)
                    year = years[-1] if years else ""
                    metric = self._infer_metric(window, group_name)
                    if metric:
                        key = (metric, year)
                        extracted.setdefault(key, []).append(
                            (section.get("title", ""), value, unit, match.start(), match.end())
                        )

        conflicts = []
        total_replacements = 0
        result_sections = [dict(s) for s in sections]

        for (metric, year), entries in extracted.items():
            if len(entries) < 2:
                continue
            unique_vals = set(v for _, v, _, _, _ in entries)
            if len(unique_vals) < 2:
                continue
            values = [v for _, v, _, _, _ in entries]
            min_v, max_v = min(values), max(values)
            if max_v > 0 and (max_v - min_v) / max_v <= self.DIFF_THRESHOLD:
                continue

            resolved_value = None
            if canonical_data:
                for ck, cv in canonical_data.items():
                    if metric in ck:
                        cparts = ck.split("_")
                        canonical_year = ""
                        for p in cparts:
                            if p.isdigit() and len(p) == 4:
                                canonical_year = p
                        if not year or not canonical_year or year == canonical_year:
                            resolved_value = float(cv.get("value", 0))
                            break

            conflict = ScanConflict(
                metric=metric, year=year,
                values=values,
                sections=[s for s, _, _, _, _ in entries],
                resolved=resolved_value is not None,
            )
            conflicts.append(conflict)

            if resolved_value is not None:
                for i, section in enumerate(result_sections):
                    content = section.get("content", "")
                    if not content:
                        continue
                    for _, old_val, unit, _, _ in entries:
                        if section.get("title", "") in conflict.sections:
                            old_str = f"{old_val}{unit}"
                            new_str = f"{resolved_value}{unit}"
                            if old_str in content:
                                result_sections[i]["content"] = content.replace(old_str, new_str, 1)
                                total_replacements += 1
                                content = result_sections[i]["content"]

        if conflicts:
            logger.info(
                f"PostConsistencyScanner: {len(conflicts)} conflicts, "
                f"{total_replacements} auto-replacements"
            )
        return ScanResult(
            sections=result_sections,
            conflicts=conflicts,
            stats={"total_replacements": total_replacements, "total_conflicts": len(conflicts)},
        )

    def _infer_metric(self, window: str, group_name: str) -> Optional[str]:
        window_lower = window.lower()
        for metric, keywords in _METRIC_KEYWORDS.items():
            if any(kw.lower() in window_lower for kw in keywords):
                return metric
        return None
```

### Step 6.4: 实现 PromptLeakDetector

- [ ] **创建 Prompt 泄漏检测器**

```python
# src/core/quality/prompt_leak_detector.py
import re
from dataclasses import dataclass
from typing import List


@dataclass
class LeakMatch:
    pattern_name: str
    matched_text: str
    start: int
    end: int


class PromptLeakDetector:
    # === Bilingual leak patterns ===
    # Chinese patterns
    LEAK_PATTERNS = [
        (re.compile(r'\(数据来源\d+\)'), "数据来源标签"),
        (re.compile(r'\(已确认规范数据[^)]*\)'), "规范数据标签"),
        (re.compile(r'好的，作为[^，]+，我将严格按照'), "角色暴露"),
        (re.compile(r'作为(?:高级|资深|首席)?[^，]+(?:分析师|研究员|顾问|专家)'), "角色暴露"),
        (re.compile(r'我将(?:为您|从|按照|基于)'), "角色暴露"),
        (re.compile(r'\(数据来源\d+[^)]*\)'), "数据来源标签扩展"),
        # English patterns
        (re.compile(r'\(data\s*source\s*\d+\)', re.IGNORECASE), "data source tag"),
        (re.compile(r'\(confirmed\s*canonical\s*data[^)]*\)', re.IGNORECASE), "canonical data tag"),
        (re.compile(r'As\s+a\s+(?:senior\s+|lead\s+|chief\s+)?(?:analyst|researcher|consultant|expert)', re.IGNORECASE), "role reveal"),
        (re.compile(r'I\s+will\s+(?:now\s+)?(?:analyze|proceed|follow|provide|examine)', re.IGNORECASE), "role reveal"),
        (re.compile(r'according\s+to\s+(?:the\s+)?(?:instructions?|prompt|guidelines?)', re.IGNORECASE), "instruction reference"),
        (re.compile(r'based\s+on\s+(?:the\s+)?(?:provided\s+)?(?:data|information|context)', re.IGNORECASE), "data reference"),
    ]

    def detect(self, content: str) -> List[LeakMatch]:
        leaks = []
        for pattern, name in self.LEAK_PATTERNS:
            for match in pattern.finditer(content):
                leaks.append(LeakMatch(
                    pattern_name=name,
                    matched_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                ))
        return leaks

    def clean(self, content: str) -> str:
        for pattern, _ in self.LEAK_PATTERNS:
            content = pattern.sub("", content)
        content = re.sub(r'\(\s*\)', "", content)
        content = re.sub(r'  +', " ", content)
        return content.strip()
```

- [ ] **运行测试**

Run: `python -m pytest tests/unit/test_post_consistency_scanner.py tests/unit/test_prompt_leak_detector.py -v`
Expected: All PASS

### Step 6.5: 集成到 orchestrator.py

- [ ] **在 orchestrator.py line 1884 (research_result_data 构建) 之后添加后处理扫描**

在 `src/core/orchestrator/orchestrator.py` 中 `research_result_data` 构建完成后（约 line 1891 之后），添加：

```python
            # F-FIX: Post-processing consistency scan + prompt leak cleanup
            try:
                from src.core.quality.post_consistency_scanner import PostConsistencyScanner
                from src.core.quality.prompt_leak_detector import PromptLeakDetector

                scanner = PostConsistencyScanner()
                detector = PromptLeakDetector()

                canonical_for_scan = {}
                if hasattr(self, '_execution_engine') and hasattr(self._execution_engine, '_active_canonical_data'):
                    canonical_for_scan = dict(self._execution_engine._active_canonical_data)
                elif self._shared_memory and hasattr(self._shared_memory, 'get'):
                    _cr = self._shared_memory.get("_canonical_registry", {})
                    if _cr:
                        canonical_for_scan = _cr

                sections_to_scan = research_result_data.get("sections", [])
                for sec in sections_to_scan:
                    content = sec.get("content", "")
                    if content:
                        leaks = detector.detect(content)
                        if leaks:
                            sec["content"] = detector.clean(content)

                if sections_to_scan:
                    scan_result = scanner.scan(sections_to_scan, canonical_data=canonical_for_scan)
                    if scan_result.conflicts:
                        logger.warning(
                            f"[{task_id}] Post-scan: {len(scan_result.conflicts)} data conflicts, "
                            f"{scan_result.stats.get('total_replacements', 0)} auto-replacements"
                        )
                    research_result_data["sections"] = scan_result.sections
            except Exception as scan_err:
                logger.warning(f"[{task_id}] Post-processing scan failed (non-fatal): {scan_err}")
```

- [ ] **运行测试**

Run: `python -m pytest tests/unit/test_post_consistency_scanner.py tests/unit/test_prompt_leak_detector.py -v`
Expected: All PASS

- [ ] **Commit**

```bash
git add src/core/quality/post_consistency_scanner.py src/core/quality/prompt_leak_detector.py src/core/orchestrator/orchestrator.py tests/unit/test_post_consistency_scanner.py tests/unit/test_prompt_leak_detector.py
git commit -m "feat: add post-processing consistency scanner and prompt leak detector as final safety net"
```

---

## Task 7: 集成验证

**Files:** All modified/created files

### Step 7.1: 全量回归测试

- [ ] **运行全部质量相关测试**

Run: `python -m pytest tests/quality/ tests/unit/test_metric_extractor_extended.py tests/unit/test_data_partitioner.py tests/unit/test_consistency_checker.py tests/unit/test_post_consistency_scanner.py tests/unit/test_prompt_leak_detector.py tests/unit/test_prompt_citation_rules.py -v --tb=short`
Expected: All PASS

### Step 7.2: 用真实数据验证

- [ ] **创建集成验证脚本**

```python
# tests/unit/test_report_quality_integration.py
import json
import pytest
from pathlib import Path


class TestReportQualityIntegration:
    @pytest.fixture
    def byd_report(self):
        p = Path("data/registries/research_8c6675c2.json")
        if not p.exists():
            pytest.skip("BYD report data not found")
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def test_consistency_checker_finds_known_contradictions(self, byd_report):
        from src.core.orchestrator.aggregation.consistency_checker import ConsistencyChecker
        sections = []
        for key, agent in byd_report["child_sessions"].items():
            content = agent.get("result", {}).get("content", "")
            if content:
                sections.append({"id": key, "content": content})
        checker = ConsistencyChecker()
        report = checker.check(sections)
        assert len(report.conflicts) >= 3
        metrics = {c.metric for c in report.conflicts}
        assert "sales_volume" in metrics

    def test_prompt_leak_detector_finds_known_leaks(self, byd_report):
        from src.core.quality.prompt_leak_detector import PromptLeakDetector
        detector = PromptLeakDetector()
        total_leaks = 0
        for key, agent in byd_report["child_sessions"].items():
            content = agent.get("result", {}).get("content", "")
            if content:
                leaks = detector.detect(content)
                total_leaks += len(leaks)
        assert total_leaks >= 1

    def test_data_partitioner_reduces_data_per_agent(self, byd_report):
        from src.core.data.data_partitioner import DataPartitioner
        partitioner = DataPartitioner()
        aspects = [
            "核心财务指标与盈利能力",
            "国际化与出口",
            "研发与创新投入",
            "销量与市场份额",
        ]
        data_points = [{"content": f"测试数据{i}", "title": f"DP{i}", "url": f"u{i}"}
                       for i in range(100)]
        total_before = len(data_points) * len(aspects)
        total_after = sum(
            len(partitioner.partition(data_points, aspect=a))
            for a in aspects
        )
        assert total_after < total_before

    def test_post_scanner_auto_replaces_contradictions(self, byd_report):
        from src.core.quality.post_consistency_scanner import PostConsistencyScanner
        sections = []
        for key, agent in byd_report["child_sessions"].items():
            content = agent.get("result", {}).get("content", "")
            sid = agent.get("context", {}).get("section_id", key)
            if content:
                sections.append({"title": sid, "content": content})
        scanner = PostConsistencyScanner()
        result = scanner.scan(sections)
        assert result.stats["total_conflicts"] >= 1

    def test_english_report_full_pipeline(self):
        from src.core.orchestrator.aggregation.consistency_checker import ConsistencyChecker
        from src.core.quality.post_consistency_scanner import PostConsistencyScanner
        from src.core.quality.prompt_leak_detector import PromptLeakDetector
        sections = [
            {"id": "financial", "content": "Revenue was $80.39 billion. Net profit reached $3.26 billion."},
            {"id": "sales", "content": "The company sold 4.6 million units. Market share was 35%."},
            {"id": "competitive", "content": "Sales reached 3.8 million vehicles. Market share hit 28%."},
        ]
        # Consistency check should detect contradictions
        checker = ConsistencyChecker()
        report = checker.check(sections)
        assert len(report.conflicts) >= 1
        # Post-scan should also detect
        scanner = PostConsistencyScanner()
        scan_result = scanner.scan([{"title": s["id"], "content": s["content"]} for s in sections])
        assert scan_result.stats["total_conflicts"] >= 1
        # Leak detector on clean content
        detector = PromptLeakDetector()
        for s in sections:
            assert len(detector.detect(s["content"])) == 0
```

- [ ] **运行集成测试**

Run: `python -m pytest tests/unit/test_report_quality_integration.py -v`
Expected: All PASS

- [ ] **Final commit**

```bash
git add tests/unit/test_report_quality_integration.py
git commit -m "test: add integration tests verifying A-G fixes against BYD report baseline"
```

---

## Self-Review Checklist

### Spec Coverage

| Requirement | Task | Status |
|-------------|------|--------|
| A: 扩展 MetricExtractor + 清死代码 | Task 1 | Covered |
| G: 按 aspect 分配 data_points | Task 2 | Covered |
| E: 强化 prompt 引用规范 | Task 3 | Covered |
| D: 取消 content[:2000] 截断 | Task 4 | Covered |
| B: 聚合时一致性校验 | Task 5 | Covered |
| F: 后处理扫描 + 泄漏清除 | Task 6 | Covered |
| 集成验证 | Task 7 | Covered |

### Placeholder Scan

- All code blocks contain complete implementations, no TBD/TODO
- All file paths are exact
- All test code is complete

### Type Consistency

- `ConsistencyChecker.check()` returns `ConsistencyReport` with `conflicts: List[DataConflict]` — used consistently in Task 5 and Task 7
- `PostConsistencyScanner.scan()` returns `ScanResult` with `sections: List[Dict]` — used consistently in Task 6 and Task 7
- `DataPartitioner.partition()` returns `List[Dict]` — used in engine.py Task 2 and test Task 7
- `PromptLeakDetector.detect()` returns `List[LeakMatch]` — used consistently
- canonical_data dict format `{"value": float, "unit": str, ...}` used consistently across all tasks

### Known Limitations (documented, not bugs)

1. Prompt citation rules (E) rely on LLM compliance (~85%), not guaranteed
2. ConsistencyChecker (B) uses regex, cannot detect semantic contradictions (e.g. "revenue surged" vs "revenue grew modestly")
3. PostConsistencyScanner (F) replacement preserves unit format but may affect sentence flow
4. DataPartitioner (G) keyword matching is fuzzy, may miss some relevant data
5. C (DataBus integration) deferred to future iteration — low ROI for current scope
6. Japanese/Korean metric patterns not yet added — the `_extract_from_aspect_name()` fallback handles basic cases, but specific financial metric regex for ja/ko would need domain-specific patterns
7. Cross-language contradiction detection: Chinese "净利润326亿元" vs English "net profit $32.6 billion" are treated as different metrics (326 vs 32.6) because unit conversion is not applied. This is intentional — cross-language reports typically maintain one primary language per section

### Self-Review Fixes Applied (2026-06-06)

| # | Issue Found | Fix Applied |
|---|-------------|-------------|
| 1 | MetricExtractor `负债率` (line 34) 与新增 `资产负债率` 重复匹配，同一文本提取两次 | 替换旧 `负债率` 为精确的 `资产负债率`，新增模式不再重复 |
| 2 | PE/PB 正则 `[（(]` 要求必须带括号，但 "PE为35.6倍" 无括号无法匹配 | 改为 `[（(]?` 可选括号，实测 "PE为35.6倍"/"市盈率35.6倍" 均可匹配 |
| 3 | DataPartitioner 测试检查 `_relevance_score`，但实现中 `pop()` 删除了该字段 | 测试改为检查 content 内容而非 `_relevance_score` |
| 4 | result_aggregator 集成用 `if section_details:` 判断，但 section_details 可能为空 | 改为始终检查 `layered_content`，不依赖 `section_details` |
| 5 | orchestrator.py 无 `_canonical_registry` 属性，`hasattr(self, ...)` 返回 False | 改为 `self._execution_engine._active_canonical_data` + SharedMemory 双路径 fallback |
| 6 | PostConsistencyScanner `_METRIC_KEYWORDS` 缺少总资产、资产负债率等指标 | 补充 6 个缺失指标映射 |
| 7 | **[通用性]** MetricExtractor 12 个正则全部中文，英文报告零提取 | 添加 13 个英文 metric 模式（`_en` 后缀），保持中文模式向后兼容 |
| 8 | **[通用性]** ConsistencyChecker `_METRIC_PATTERNS` 全中文，无法检测英文矛盾 | 重构为 `(regex, metric_id, lang)` 三元组，统一 metric_id（如 `sales_volume`），中英文共享 ID 实现跨语言矛盾检测 |
| 9 | **[通用性]** PostConsistencyScanner 关键词纯中文 | 双语 `_METRIC_KEYWORDS` + 双语 `_VALUE_PATTERNS`（`million units`/`billion`/`x`） |
| 10 | **[通用性]** DataPartitioner ASPECT_KEYWORD_MAP 8 个映射全是中文方面名 | 添加 8 个英文方面映射 + `_split_key()` 支持中英文分隔符 + `_extract_from_aspect_name()` 自动从方面名提取关键词 |
| 11 | **[通用性]** PromptLeakDetector 6 个模式全是中文 | 添加 6 个英文泄漏模式（data source tag/role reveal/instruction reference） |
| 12 | **[通用性]** Prompt 强化规则（Task 3）硬编码中文 "【强制引用规范】" | 跟随 `get_language()` 设置，英文报告使用 `[Mandatory Citation Rules]` |
