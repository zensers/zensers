# 研究报告数据质量修订方案：查询去重与数据完整性

> 日期：2026-06-15（初版）| 2026-06-17（修订版）
> 状态：Phase 0a/A/B/C/D 已实施，Phase 0b 待实施
> 关联分析：`docs/2026-06-15-system-deep-analysis.md`、`docs/2026-06-14-system-log-analysis.md`

---

## 1. 问题定义

### 1.1 数据铁证

2026-06-14 生产日志显示，ses_cc1b9ce3（比亚迪公司财务报告）执行中：

| 指标 | 数值 |
|------|------|
| 搜索查询总数 | 104 次（8 agent × 13 条查询） |
| 唯一查询数 | 13 条 |
| 重复率 | 100%（13 条查询被 8 个 agent 全部重复执行） |
| 章节数据需求覆盖率 | 10%（13 条通用查询仅覆盖 42 个关键词中的 4 个） |
| 报告最终评分 | 40.9/100 |
| 数据冲突 | 同一指标（营收/ROE）跨章节出现不同值 |

### 1.2 三个核心问题

**问题 P1：查询重复** — 同一查询被多个 agent 重复执行，浪费时间并产生矛盾数据

**问题 P2：数据不完整** — 查询全是通用查询（市场规模/增长率/市场份额/消费者数据），8 个章节的专业需求（营收/ROE/研发投入/供应链/杠杆...）几乎未覆盖

**问题 P3：数据冲突** — 同一指标被不同 agent 从不同来源搜到不同值，跨章节出现矛盾数字

### 1.3 根因分析

| 问题 | 根因 | 代码位置 |
|------|------|---------|
| P1 查询重复 | `executed_queries` 是 agent 局部变量，无跨 agent 协调 | `generic_agent.py:~1626` |
| P2 数据不完整 | `_generate_search_queries` 用全局 `data_focus` 生成查询，1 级框架无法推导章节具体需求 | `generic_agent.py:~2551`、`domain_role_inferrer.py:27-112` |
| P3 数据冲突 | 各 agent 独立搜索同一指标得到不同值，无跨章节一致性保证 | `engine.py:~1918`（按 agent_id 归属数据） |

三个问题相互关联：P2 导致各 agent 用通用查询搜索相同内容，加剧 P1 重复；P1 重复导致同一指标多次搜索得到不同值，引发 P3 冲突。

---

## 2. 设计原则

### 2.1 不改变 agent_id 体系

agent_id 在全链路中有 45+ 处引用，涉及：

- **调度器**：`scheduler.py` 按 agent_id 跟踪执行状态、完成标记、依赖就绪检查
- **内容锁**：`content_lock.py` 按 section_id（从 agent_id 派生）管理章节锁
- **数据路由**：`engine.py:1904-1917` 按 agent_id 索引 data_points_by_agent
- **结果聚合**：`result_aggregator.py` 按 agent_id 匹配章节内容
- **报告生成**：`engine.py:758-808` 按 agent_id 确定章节类型和名称

若改变 agent_id 体系，将导致多处死锁崩溃、数据丢失和错误输出（风险估计：5+ 死锁、12+ 数据丢失、20+ 错误输出）。

**结论**：去重只在搜索执行层生效，搜索结果仍按原 agent_id 分发给各 agent，下游依赖链、数据路由完全不变。

### 2.2 不改变已有成熟模块

以下模块已验证可用，不在本次修订范围内：

| 模块 | 用途 | 状态 |
|------|------|------|
| `MetricExtractor` | 从原始文本提取结构化指标 | 已有，直接使用 |
| `CanonicalDataRegistry` | 全局权威数据注册 + 冲突解决 | 已有，直接使用 |
| `CaliberDecisionEngine` | 口径决策（A股/港股/归母/合并）— 注：仅作为设计概念在注释中引用，尚未实现为独立类 | 待实现 |
| `SharedMemory.write_canonical` | Agent 间 canonical 数据共享 | 已有，直接使用 |
| `generic_agent.py:~490` | canonical_data 注入 prompt | 已有，直接使用 |

### 2.3 最小侵入原则

新增模块插入现有流程的间隙位置，不重构已有代码结构：

- 数据源路由：修改 `strategies.py:295` 硬编码列表，按 aspect 动态配置 skill
- 查询去重层：由 engine 层统一执行查询规划 + 去重搜索，结果按 agent_id 分发
- 3 级框架：扩展 `DecompositionPlan` 数据结构，向后兼容
- 补充搜索：由 engine 层在 phase_1 完成后执行

---

## 3. 修订方案：五阶段流水线

### 当前流程

```
IndustryResearchStrategy.decompose()
  → DecompositionPlan (1 级框架，8 个扁平章节)
    → _create_agents_from_plan()
      → 8 个 phase_1 agent 各自独立搜索 (100% 查询重复)
        → 8 个 phase_2 agent 按依赖过滤数据后分析
          → phase_3 calibrator 校准
```

### 修订后流程

```
Stage 0: 数据源路由（结构化数据源优先于搜索）
Stage 1: 3 级框架 + 查询规划
Stage 2: Engine 层统一查询去重 + 搜索执行
Stage 3: 数据对账 + 补充
Stage 4: 分析（不变）
```

---

### Stage 0：数据源路由

#### 3.0.1 问题

当前系统已有 `StockDataSkill`（`src/skills/analysis/stock_data.py`）和 `AkshareProvider`（`src/core/data_providers/sources/akshare_provider.py`），可通过 akshare 直接获取精确财务数据（无需 API Key）。但 DATA_COLLECTION 阶段的 agent 完全无法触达这些 skill，存在三层阻断：

**阻断层 1：策略层硬编码 skill 列表**（`strategies.py:295`）

`IndustryResearchStrategy.decompose()` 创建 DATA_COLLECTION agent 时硬编码：
```python
skills=["search_skill", "news_search", "llm_skill"]  # L295
```
完全没有 `stock_data`。`ASPECT_SKILL_MAP`（L41-67）只在 L342 给 DEEP_ANALYSIS 阶段使用，DATA_COLLECTION 阶段不查这个 map。

**阻断层 2：执行层只走搜索路径**（`generic_agent.py:300-304`）

`category=="research"` 的执行分支只调用 `_do_deep_research()`：
```python
if agent_category == "research":
    if topic and "search_skill" in available_skills and skill_registry:
        search_results = await self._do_deep_research(...)  # 只走搜索引擎
```
即使 skill 注册表里有 `stock_data`，这个分支也不会触达它。

**阻断层 3：架构假设错位**

`stock_data`/`stock_analysis` 被分配给 DEEP_ANALYSIS 阶段（`ASPECT_SKILL_MAP` L50-57），但该阶段**不执行数据获取**（L42-44 注释："search_skill is intentionally excluded"）。DEEP_ANALYSIS agent 期望分析 phase_1 已收集的数据——然而 phase_1 根本没调 `stock_data`，所以 `stock_data` 永远不会被触发。

#### 3.0.2 方案：分两步实施数据源路由

**Phase 0a（✅ 已实施）：修改硬编码 skill 列表，为财务相关 aspect 添加 `stock_data`**

修改 `strategies.py`，将硬编码改为按 aspect 动态配置（✅ 已实施，当前代码使用 `_get_data_collection_skills(aspect, topic)`）：

```python
# 当前（硬编码，所有 DATA_COLLECTION agent 都一样）：
skills=["search_skill", "news_search", "llm_skill"]  # L295

# 修改后（按 aspect 路由）：
skills=_get_data_collection_skills(aspect, topic, intent_result)
```

`_get_data_collection_skills` 根据研究维度和主题动态决定数据源组合：

```python
DATA_SOURCE_SKILL_MAP = {
    "financial":   ["stock_data"],
    "valuation":   ["stock_data"],
    "company":     ["stock_data"],
    "market_size": ["stock_data"],
    "competitive": [],
    "policy":      [],
    "technology":  [],
    "risk":        [],
}

def _get_data_collection_skills(aspect: str, topic: str, intent_result: Any) -> List[str]:
    skills = ["search_skill", "news_search", "llm_skill"]
    aspect_lower = aspect.lower()
    for keyword, extra_skills in DATA_SOURCE_SKILL_MAP.items():
        if keyword in aspect_lower:
            skills.extend(extra_skills)
    if intent_result:
        primary_type = getattr(intent_result, 'primary_research_type', None)
        if primary_type and primary_type.value in (
            "company_research", "investment", "competitive_analysis"
        ):
            if "stock_data" not in skills:
                skills.append("stock_data")
    return list(dict.fromkeys(skills))
```

同时扩展 `generic_agent.py` 的 `category=="research"` 分支，在搜索引擎之前优先调用结构化数据源（✅ 已实施）：

```python
if agent_category == "research":
    data_points = []
    sources = []

    # 路由 1：结构化数据源（优先）
    if "stock_data" in available_skills and skill_registry:
        stock_skill = skill_registry.get("stock_data")
        if stock_skill:
            structured = await self._fetch_structured_data(stock_skill, topic, aspect)  # 新增方法
            data_points.extend(structured.get("data_points", []))
            sources.extend(structured.get("sources", []))
            if self._shared_memory and hasattr(self._shared_memory, 'write_canonical'):
                for metric, value in structured.get("canonical_metrics", {}).items():
                    await self._shared_memory.write_canonical(
                        metric=metric, value=value,
                        caliber="structured_source",
                        source="akshare",
                        publisher=self.agent_id,
                    )  # ISSUE-G: 需 write_canonical 来源优先级保证 search_result 不覆盖此值

    # 路由 2：搜索引擎（补充定性维度）
    if topic and "search_skill" in available_skills and skill_registry:
        search_results = await self._do_deep_research(
            topic=topic, aspect=aspect, aspects=aspects, skill_registry=skill_registry,
        )
        for search in search_results.get("searches", []):
            for item in search.get("results", []):
                data_points.append({...})
                sources.append({...})
```

清理 `ASPECT_SKILL_MAP` 中的数据获取 skill：

```python
# 修改前：
"Financial Analysis": ["llm_skill", "stock_data", "stock_analysis", "data_analysis"],
# 修改后：
"Financial Analysis": ["llm_skill", "stock_analysis", "data_analysis"],
# stock_data 移到 DATA_COLLECTION 阶段的路由规则
```

`stock_analysis` 保留在 DEEP_ANALYSIS 阶段——它是分析型 skill（计算 ROE/杜邦分解/DCF），不是数据获取 skill。

**Phase 0b（3 级框架完成后）：agent 自主 skill 发现**

Phase 0a 的中心化路由有局限：关键词匹配不可靠、新 skill 需要改路由规则、无法适应运行时变化。3 级框架完成后，agent 拥有了 `data_needs`，可自主发现 skill：

1. `Skill` 基类增加 `data_capabilities` 属性，各 skill 声明自己的数据能力
2. agent 增加 `discover_and_load_skills` 方法，运行时按 `data_needs` 匹配 `data_capabilities`
3. `_available_skills` 从"创建时固定"变为"创建时初始化 + 运行时可扩展"
4. `StockDataSkill` 添加内存缓存（`(symbol, action) → result`），避免并行 agent 重复调用 akshare API
5. `write_canonical` 增加来源优先级（`structured_source` > `search_result`），防止搜索近似值覆盖结构化精确值

> **Phase 0a 与 Phase 0b 的关系**：0a 是 0b 的过渡方案，可立即实施，不依赖 3 级框架。0b 完成后，0a 的中心化路由规则可逐步废弃。

#### 3.0.3 数据源路由对后续阶段的影响

| 数据获取方式 | 比亚迪营收 | 可靠性 | 时效性 | 冲突风险 |
|-------------|-----------|--------|--------|---------|
| 搜索引擎（当前） | 6800/6420/130/54.5 亿（4 个不同值） | 低 | 取决于网页 | 极高（P3 根因） |
| akshare（已有） | 6800.28 亿@2025Q3（精确值） | 高 | T+1 | 零 |

1. **P3（数据冲突）对财务指标被根本消除**：akshare 提供精确值，不需要对账
2. **P1（查询重复）大幅减少**：财务数据不再搜索，搜索仅用于定性维度
3. **P2（数据不完整）大幅改善**：akshare 可覆盖大部分财务 data_needs
4. **去重器仍有价值**：但仅用于定性维度的搜索去重，规模大幅缩减

---

### Stage 1：3 级框架 + 查询规划

#### 3.1.1 问题

当前 1 级框架（扁平章节名）无法推导出具体数据需求：

```
section_0: "核心指标与盈利能力"  ← 无法确定需要[营收, 净利润, 毛利率, ROE]还是其他
```

`_generate_search_queries` 只能用全局 `data_focus = ["市场规模", "增长率", "市场份额", "消费者数据"]` 生成通用查询，导致 8 个 agent 查询 100% 重复，覆盖率仅 10%。

#### 3.1.2 方案

扩展为 3 级框架：**章节 → 子章节 → 数据需求（data_needs）**

```
section_0: 核心指标与盈利能力
  sub_0_0: 营收分析
    data_needs: [营收, 营收增长率, 营收构成]
    data_source_type: structured
  sub_0_1: 利润分析
    data_needs: [净利润, 毛利率, 净利率]
    data_source_type: structured
  sub_0_2: 盈利能力指标
    data_needs: [ROE, ROA, 单车利润]
    data_source_type: structured

section_1: 研发创新投资
  sub_1_0: 研发投入
    data_needs: [研发费用, 研发费用率, 研发增速]
    data_source_type: structured
  sub_1_1: 技术专利
    data_needs: [专利数量, 技术突破]
    data_source_type: search

section_2: 供应成本效率
  sub_2_0: 供应链
    data_needs: [供应商集中度, 原材料成本]
    data_source_type: search
  sub_2_1: 成本结构
    data_needs: [营业成本, 成本率]
    data_source_type: both

section_3: 核心市场规模
  sub_3_0: 市场规模
    data_needs: [TAM, SAM, 市场增速]
    data_source_type: search
  sub_3_1: 销量与份额
    data_needs: [销量, 产量, 市场份额, 营收]  ← 营收与 section_0 共享
    data_source_type: both

section_4: 资本回报率
  sub_4_0: 回报指标
    data_needs: [ROE, ROIC, 资本效率]  ← ROE 与 section_0 共享
    data_source_type: structured
  sub_4_1: 资本结构
    data_needs: [资产负债率, 权益乘数]
    data_source_type: structured

section_5: 稳健性
  sub_5_0: 杠杆
    data_needs: [资产负债率, 产权比率]
    data_source_type: structured
  sub_5_1: 流动性
    data_needs: [流动比率, 速动比率, 现金流]
    data_source_type: structured

section_6: 业内比较竞争力
  sub_6_0: 同行对比
    data_needs: [营收排名, 市场份额对比, 利润率对比]
    data_source_type: both
  sub_6_1: 竞争地位
    data_needs: [竞争优势, 行业排名]
    data_source_type: search

section_7: 投资预测
  sub_7_0: 估值
    data_needs: [PE, PB, DCF 估值]
    data_source_type: both
  sub_7_1: 增长预测
    data_needs: [营收预测, 利润预测, 风险评估]
    data_source_type: search
```

#### 3.1.3 跨章节共享指标自动识别

3 级框架声明了每个章节的 data_needs 后，共享指标自动浮现：

| 共享指标 | 需要的章节 | 搜索次数 |
|---------|-----------|---------|
| 营收 | section_0 + section_3 | 1 次（当前 2 次） |
| ROE | section_0 + section_4 | 1 次（当前 2 次） |
| 资产负债率 | section_4 + section_5 | 1 次（当前 2 次） |

#### 3.1.4 实现方式

3 级框架由 LLM 在 `requirement_analysis_agent` 阶段生成。输入为主题 + 1 级框架，输出为子章节 + data_needs。

> **v2.2 修正**：`data_source_type` 不由 LLM 生成，而由规则推导。LLM 生成 `data_needs`，`data_source_type` 在 `decompose()` 中由 `derive_data_source_type()` 根据已知结构化数据源能力推导填充（详见 ISSUE-F）。这消除了 LLM 不了解 akshare 覆盖范围导致标注错误的风险。

> **v2.4 补充**：LLM prompt 已实现。`prompts/agents/intent_analysis_system.md` 增加了 `section_data_specs` 生成规则和示例输出，`prompts/agents/intent_analysis_user.md` 增加了 `section_data_specs` 输出要求。`SemanticIntentAnalyzer._build_result()` 已实现从 LLM JSON 输出解析 `section_data_specs`，`to_dict()`/`from_dict()` 已包含该字段。`_convert_specs_from_dicts()` 在 `decompose()` 中自动将 LLM 返回的 dict 列表转换为 `SectionDataSpec`/`SubSectionSpec` 对象。engine.py 也添加了防御性转换。

生成方式：
1. 由 LLM 根据主题语义和章节名称扩展 `data_needs`（灵活，适应不同主题）
2. `data_source_type` 由规则推导，不依赖 LLM 对数据源的了解
3. 不在 YAML 模板中硬编码（不同主题差异太大）

数据结构扩展：

```python
@dataclass
class SubSectionSpec:
    sub_section_id: str          # "sub_0_0"
    name: str                    # "营收分析"
    data_needs: List[str]        # ["营收", "营收增长率", "营收构成"]
    data_source_type: str = "search"  # "structured" | "search" | "both" — 由 derive_data_source_type() 推导填充

@dataclass
class SectionDataSpec:
    section_id: str              # "section_0"
    name: str                    # "核心指标与盈利能力"
    sub_sections: List[SubSectionSpec] = field(default_factory=list)
    
    @property
    def all_data_needs(self) -> List[str]:
        needs = []
        for sub in self.sub_sections:
            needs.extend(sub.data_needs)
        return list(dict.fromkeys(needs))  # 去重保序
    
    @property
    def search_data_needs(self) -> List[str]:
        """仅需要搜索引擎获取的 data_needs"""
        needs = []
        for sub in self.sub_sections:
            if sub.data_source_type in ("search", "both"):
                needs.extend(sub.data_needs)
        return list(dict.fromkeys(needs))
    
    @property
    def structured_data_needs(self) -> List[str]:
        """可通过结构化数据源获取的 data_needs"""
        needs = []
        for sub in self.sub_sections:
            if sub.data_source_type in ("structured", "both"):
                needs.extend(sub.data_needs)
        return list(dict.fromkeys(needs))
```

`data_source_type` 规则推导：

```python
STRUCTURED_DATA_CAPABILITIES = {
    "stock_data": {
        "zh": ["营收", "净利润", "毛利率", "净利率", "ROE", "ROA", "ROIC",
               "资产负债率", "流动比率", "速动比率", "现金流", "研发费用",
               "销量", "产量", "市场份额", "PE", "PB", "利润表", "资产负债表", "现金流量表"],
    },
}

def derive_data_source_type(data_need: str, topic: str, intent_result: Any) -> str:
    # 1. 检查已知结构化数据源是否覆盖该 need
    for skill_name, capabilities in STRUCTURED_DATA_CAPABILITIES.items():
        for lang, keywords in capabilities.items():
            if data_need in keywords:
                return "structured"

    # 2. 上市公司主题 + 财务关键词 → both（结构化可能有，搜索补充）
    if _is_listed_company_topic(topic):
        FINANCIAL_KEYWORDS = ["营收", "利润", "率", "费用", "ROE", "ROA", "ROIC", "PE", "PB", "DCF"]
        if any(kw in data_need for kw in FINANCIAL_KEYWORDS):
            return "both"

    # 3. 默认搜索
    return "search"
```

> **命名说明**：`task_structure.py:56` 已有 `SectionSpec` 类（章节角色/依赖定义），为避免命名冲突，本方案使用 `SectionDataSpec` 和 `SubSectionSpec`。`strategies.py:98` 的类是 `AgentSpec`（Agent 规格定义），与 `SectionDataSpec` 不冲突。

扩展 `DecompositionPlan`，新增 `section_data_specs: List[SectionDataSpec]`，向后兼容（无 sub_sections 时退化为 1 级）。

> **v2.4 修正**：`decompose()` 中 `section_spec_map` 的键匹配已修正。当存在 dependent aspects（如 summary/conclusion）时，`normal_aspects` 的索引 `i` 与 LLM 生成的 `section_N` 不对齐。修正为使用 `seq_idx`（顺序计数器）生成 `section_id`，并增加按 `spec.name` 的双重匹配（`section_spec_by_id` + `section_spec_by_name`）。

#### 3.1.5 3 级框架验证与回退

LLM 输出不可控，需添加验证 + 回退机制：

```python
def validate_section_data_specs(
    specs: List[SectionDataSpec], 
    section_names: List[str]
) -> Tuple[List[SectionDataSpec], bool]:
    valid = True
    for spec in specs:
        if not re.match(r'section_\d+', spec.section_id):
            valid = False
        if not spec.all_data_needs:
            valid = False
    if len(specs) != len(section_names):
        valid = False
    
    if not valid:
        specs = _fallback_specs_from_names(section_names)
    
    return specs, valid


def _fallback_specs_from_names(section_names: List[str]) -> List[SectionDataSpec]:
    """从 1 级框架章节名称生成基础 data_needs"""
    specs = []
    for i, name in enumerate(section_names):
        specs.append(SectionDataSpec(
            section_id=f"section_{i}",
            name=name,
            sub_sections=[SubSectionSpec(
                sub_section_id=f"sub_{i}_0",
                name=name,
                data_needs=[name],
                data_source_type="search",
            )],
        ))
    return specs
```

#### 3.1.6 data_needs 传播路径

data_needs 从生成到消费的完整传播路径：

```
requirement_analysis_agent
  → LLM 生成 3 级框架 (section_data_specs)
  → 写入 DeepIntentResult.section_data_specs（新增字段，默认空列表，向后兼容）
  
orchestrator.py:705
  → decomposition_plan = strategy.decompose(requirement, intent_result, framework_config)
  → intent_result.section_data_specs 传入 decompose()
  
strategies.py decompose()
  → 写入 DecompositionPlan.section_data_specs
  
orchestrator.py:727
  → _create_agents_from_plan(decomposition_plan, ...)
  → 每个 AgentSpec.context["data_needs"] = section.all_data_needs
  → 每个 AgentSpec.context["search_data_needs"] = section.search_data_needs
  → 每个 AgentSpec.context["section_id"] = section.section_id
  → 同时：_get_data_collection_skills(aspect, topic, intent_result) 按 aspect 路由 skill
  
generic_agent.py:243
  → context.get("data_needs") 获取章节专属数据需求
  → 当 data_needs 存在时，_generate_search_queries 使用 data_needs 替代全局 data_focus
```

> **`DeepIntentResult` 字段扩展**：当前 `DeepIntentResult`（`semantic_intent.py:31-62`）没有 `section_data_specs` 字段。新增 `section_data_specs: List[SectionDataSpec] = field(default_factory=list)`，由于有默认值，向后兼容。`to_intent_analysis_result()` 不需要传播该字段（`IntentAnalysisResult` 不需要，下游直接使用 `DeepIntentResult`）。

---

### Stage 2：Engine 层统一查询去重 + 搜索执行

#### 3.2.1 设计决策：Engine 层统一规划 vs 透明代理

> **修订说明**：初版方案将去重器作为"透明拦截层"插入 `_do_deep_research` 内部。经审计发现，此方案与 `_do_deep_research` 的多轮搜索+质量评估循环存在根本冲突（详见附录 AUDIT-9/10）。修订后改为 engine 层统一查询规划。

**透明代理方案的问题**：

1. `_do_deep_research` 是多轮循环（`while True:`，L1536），去重器缓存命中返回共享结果，但各 agent 的质量评估独立运行，可能一个达标一个不达标，导致空循环
2. `executed_queries` 是 agent 局部变量，缓存命中时 agent 仍标记为"已执行"，但搜索结果来自缓存不是本 agent，状态不一致
3. agent_3 因质量不足触发 LLM 扩展生成新查询，新查询又被去重器拦截，形成"搜索→缓存命中→仍不足→扩展→又缓存命中"的死循环

**Engine 层统一规划方案**：

```
engine._execute_batch():
  1. 从 DecompositionPlan.section_data_specs 提取所有章节的 search_data_needs
  2. 合并去重：收集所有唯一查询（考虑共享指标）
  3. 统一执行搜索（SearchQueryDeduplicator 协调）
  4. 搜索结果按 agent_id 分发给各 phase_1 agent
  5. phase_1 agent 接收预分发数据 + 执行补充搜索（_do_deep_research 改为补充模式）
```

#### 3.2.2 查询生成

从 `section.search_data_needs` 生成章节专属搜索查询（仅对 `data_source_type="search"` 或 `"both"` 的 data_needs 生成搜索查询）：

```python
def _generate_section_queries(self, topic: str, section: SectionDataSpec) -> List[str]:
    queries = []
    search_topic = self._extract_keywords(topic)
    for need in section.search_data_needs:
        queries.append(f"{search_topic} {need} {current_year}")
        queries.append(f"{search_topic} {need} 数据")
    queries.append(f"{search_topic} {section.name} {current_year}")
    return list(dict.fromkeys(queries))
```

> **变体数量说明**：每个 need 生成 2 条变体（而非初版的 4 条），加上章节聚合查询 1 条。`data_source_type="structured"` 的 need 不生成搜索查询（由 akshare 覆盖），大幅减少搜索量。

当 `data_needs` 存在时，`_generate_search_queries` 跳过 `DomainRoleInferrer.data_focus` 查询生成（避免通用查询重新引入重复），`DomainRoleInferrer` 的 `role` 和 `expertise` 字段仍可用于 LLM prompt 构建。

现有 aspect-specific 硬编码分支（`generic_agent.py:2504-2558`）保留作为 fallback：当 `data_needs` 为空或 3 级框架生成失败时触发；当 `data_needs` 足够具体时跳过。

#### 3.2.3 跨章节查询去重

新增 **SearchQueryDeduplicator** 模块，使用 per-query lock 替代全局锁：

```python
class SearchQueryDeduplicator:
    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._query_sections: Dict[str, List[str]] = {}
        self._query_locks: Dict[str, asyncio.Lock] = {}   # per-query lock
        self._meta_lock = asyncio.Lock()                    # protects _query_locks dict
    
    def _normalize_query(self, query: str) -> str:
        normalized = ' '.join(query.split())
        return normalized.lower()
    
    async def search(self, query: str, section_id: str, search_skill) -> Dict:
        normalized = self._normalize_query(query)
        
        async with self._meta_lock:
            if normalized not in self._query_locks:
                self._query_locks[normalized] = asyncio.Lock()
            query_lock = self._query_locks[normalized]
        
        async with query_lock:
            if normalized in self._cache:
                self._query_sections[normalized].append(section_id)
                return copy.deepcopy(self._cache[normalized])
            
            result = await search_skill.execute(query=query)
            self._cache[normalized] = result
            self._query_sections[normalized] = [section_id]
            return copy.deepcopy(result)
    
    def get_shared_queries(self) -> Dict[str, List[str]]:
        return {q: ss for q, ss in self._query_sections.items() if len(ss) > 1}
```

> **设计说明**：
> - **per-query lock**：不同查询可并行搜索，只有同一查询的并发请求才串行化（第一个执行搜索，后续命中缓存）
> - **`_normalize_query`**：合并多余空格、去首尾空格、统一小写。注意：同义词（比亚迪/BYD）不规范化为同一键，避免错误去重
> - **`copy.deepcopy`**：返回缓存结果的深拷贝，避免 agent 间互相干扰
> - **缓存不可变**：一旦写入不再更新，避免缓存更新导致各 agent 状态不一致

#### 3.2.4 搜索执行流程

> **v2.2 修正**：统一查询规划在 `_execute_batch` 内部、agent 循环之前执行，搜索结果通过 task dict 传递（而非 `receive_preloaded_data` 方法）。搜索使用 `asyncio.gather` 并行执行。通过 agent category 判断当前 batch 是否为 DATA_COLLECTION 阶段（ISSUE-H：stage_name 传入值是 `"batch_N"` 而非 `"data_collection"`）。

```
engine._execute_batch():
  
  # === 新增：统一查询规划（仅对 DATA_COLLECTION 阶段） ===
  # ISSUE-H: 通过 agent category 判断，而非 stage_name
  _is_data_collection = any(
      getattr(a, 'config', {}).get('category', '') == 'research'
      for a in agents
  )
  preloaded_data = {}  # agent_id -> [search_results]
  if _is_data_collection and self._section_data_specs:
      preloaded_data = await self._unified_search(agents, requirement)
  
  # 2. _unified_search 内部逻辑：
  #    a. 从 section_data_specs 提取所有章节的 search_data_needs
  #    b. 按 agent_id 生成查询（每个 need 2 条变体）
  #    c. 合并去重：收集所有唯一查询（normalized_query -> [section_ids]）
  #    d. 使用 asyncio.gather 并行执行所有唯一查询
  #    e. 搜索结果按 agent_id 分发（同一查询被多章节共享时深拷贝）
  
  # 3. 现有 data_points_by_agent 构建逻辑不变 ...
  
  # 4. agent 循环：构建 task dict 时注入预分发数据
  for agent in agents:
      task = { ... }  # 现有 task 构建
      
      # 注入预分发数据（通过 task dict，与 canonical_data 传递方式一致）
      if agent.agent_id in preloaded_data:
          task["preloaded_search_results"] = preloaded_data[agent.agent_id]
      
      # 调度 agent 执行
      await self._coordinator.dispatch_task(agent, task, ...)
```

`_unified_search` 的并行执行：

```python
async def _unified_search(self, agents, requirement) -> Dict[str, List[Dict]]:
    # 收集所有唯一查询及其对应的 section_ids
    unique_queries = {}  # normalized_query -> (original_query, [section_ids])
    agent_section_map = {}  # agent_id -> section_id
    
    for agent in agents:
        section_spec = self._get_section_spec(agent)
        section_id = section_spec.section_id
        agent_section_map[agent.agent_id] = section_id
        queries = self._generate_section_queries(requirement.get("topic", ""), section_spec)
        for query in queries:
            normalized = self._deduplicator._normalize_query(query)
            if normalized not in unique_queries:
                unique_queries[normalized] = (query, [section_id])
            else:
                unique_queries[normalized][1].append(section_id)
    
    # 并行执行所有唯一查询
    async def _search_one(original_query, section_ids, search_skill):
        result = await self._deduplicator.search(original_query, section_ids[0], search_skill)
        # search() 内部调用 search_skill.execute(query=query)
        return original_query, section_ids, result
    
    search_skill = self._get_search_skill()
    search_tasks = [
        _search_one(q, sids, search_skill) 
        for q, (q, sids) in unique_queries.items()
    ]
    all_results = await asyncio.gather(*search_tasks)
    
    # 按 agent_id 分发搜索结果
    preloaded_data = {}  # agent_id -> [results]
    for original_query, section_ids, result in all_results:
        for agent_id, section_id in agent_section_map.items():
            if section_id in section_ids:
                preloaded_data.setdefault(agent_id, []).append(
                    copy.deepcopy(result) if len(section_ids) > 1 else result
                )
    
    return preloaded_data
```

每个 agent 的 result 仍然带有自己的 agent_id，下游 phase_2 按 agent_id 依赖过滤不变。

#### 3.2.5 `_do_deep_research` 改为补充模式

当前 `_do_deep_research` 假设从零开始搜索。修改为接收预分发数据：

> **v2.2 修正**：
> - 预分发数据通过 task dict 传递（`task["preloaded_search_results"]`），而非 `receive_preloaded_data` 方法。agent 从 `self._context` 或 task 参数中读取。
> - 4 处调用点中仅 L302（`category=="research"`，DATA_COLLECTION 阶段）需传递 `preloaded_search_results`，其余 3 处（L404 降级、L759 旧版兼容、L948 异常恢复）为 fallback 路径，传 `None` 即可。
> - ISSUE-I：L302 的传递路径为 `task.get("preloaded_search_results")` → `_do_deep_research(preloaded_search_results=preloaded)`。

```python
# 新增参数：preloaded_search_results
async def _do_deep_research(self, topic, aspect, aspects, skill_registry,
                            preloaded_search_results=None):
    # 1. 先将预分发数据加入 all_results
    if preloaded_search_results:
        for result in preloaded_search_results:
            all_results.append(result)
            executed_queries.add(result.get("query", ""))
    
    # 2. 质量评估：预分发数据是否已足够
    quality_score = self._evaluate_quality(all_results)
    if quality_score >= threshold:
        return format_results(all_results)  # 足够，跳过补充搜索
    
    # 3. 补充搜索（仅搜索预分发未覆盖的内容）
    # ... 现有循环逻辑不变，但 starting from preloaded data
```

**调用点适配**：

| 调用点 | 位置 | agent_category | preloaded_search_results |
|--------|------|---------------|--------------------------|
| L302 | `category=="research"` | DATA_COLLECTION | 从 task dict 传入 |
| L404 | `category=="market-analysis"` fallback | DEEP_ANALYSIS | `None`（降级路径） |
| L759 | fallback 路径 | 旧版兼容 | `None`（旧版路径） |
| L948 | 异常恢复 fallback | 通用 | `None`（恢复路径） |

**关键约束**：
- 搜索结果按原 agent_id 分发给各 agent，下游依赖链、数据路由完全不变
- 预分发数据来自 engine 层统一搜索（已去重），agent 的补充搜索是对质量不足的补充
- agent 的质量评估基于完整数据（预分发 + 自行补充），不是仅基于共享缓存

#### 3.2.6 效果预估

| | 当前 | 修订后 |
|---|---|---|
| 查询总数 | 104 次（8×13） | ~40-60 次（去重后，含补充搜索） |
| 唯一查询数 | 13 条（全通用） | ~25-35 条（全章节专属） |
| 章节覆盖率 | 10% | 90%+ |
| 同一指标搜索次数 | 8 次（矛盾） | 1 次（共享） |
| 财务指标搜索次数 | 8×9=72 次 | 0 次（akshare 覆盖） |

> **预估说明**：初版预估 ~20 次过于乐观。按 8 章节 × ~6 个 search data_needs × 2 变体 + 8 聚合 = ~104 条原始查询，去重后约 40-60 条（考虑共享指标去重 + akshare 覆盖财务指标），加上补充搜索约 10 条。仍比当前 104 次减少 40-50%。

---

### Stage 3：数据对账 + 补充

#### 3.3.1 数据对账

**问题**：共享搜索结果 ≠ 共享同一个值。A 和 C 都拿到"比亚迪 营收"的 3 个网页片段，但 A 可能提取 2025 年 6800 亿，C 可能提取 2024 年 6420 亿。

**方案**：在 phase_1 全部完成后、phase_2 开始前，对搜索结果做数据对账。

> **v2.2 修正**：对账和补充不在 `_execute_batch` 内部执行，而在 `engine.py:1082` 的 batch 循环中，DATA_COLLECTION batch 完成后、下一个 batch 开始前执行。phase_1 和 phase_2 是通过拓扑排序分配到不同 batch 的，`all_results` 在 batch 间累积传递。现有 S-FIX-2 机制（L1389-1421）已自动从 data_points 提取指标注册到 canonical_registry，我们的对账在此基础上增强。

```python
# engine.py batch 循环（简化）：
for batch_index, batch_agent_ids in enumerate(execution_batches):
    batch_results = await self._execute_agents_batch(...)
    all_results.extend(batch_results)
    
    # S-FIX-2: 现有 canonical data 提取（L1389-1421）
    ...
    
    # === 新增：对账 + 补充（仅 DATA_COLLECTION batch 完成后） ===
    _is_data_collection = any(
        getattr(scheduler.get_agent_by_id(aid), 'config', {}).get('category', '') == 'research'
        for aid in batch_agent_ids
    )
    if _is_data_collection and self._section_data_specs:
        canonical_data = await self._reconcile_data(batch_results)
        supplement_data = await self._supplement_missing_data(batch_results)
        # 将补充数据合并到 all_results 中
        for need, supp in supplement_data.items():
            for result in all_results:
                agent_id = result.get("agent_id", "")
                section_spec = self._get_section_spec_by_agent_id(agent_id)
                if section_spec and need in section_spec.all_data_needs:
                    result.setdefault("data_points", []).extend(supp["data_points"])
                    result.setdefault("sources", []).extend(supp["sources"])
```

使用已有模块：

```
搜索结果（raw text）
  → MetricExtractor.extract()   → 提取结构化指标（营收=6800亿@2025，净利润=300亿@2025）
  → CanonicalDataRegistry.register()  → 同指标多来源取最权威值（CaliberDecisionEngine 决策）
  → canonical_data
```

对账结果通过 `canonical_data` 注入每个 phase_2 agent 的 prompt（已有机制 `generic_agent.py:468-477`），LLM 优先引用 canonical_data 中的值。

> **对账压力减轻**：Stage 0 的数据源路由使财务指标直接从 akshare 获取精确值，在 DATA_COLLECTION agent 内部就写入 canonical_data（caliber="structured_source"），无需对账。对账仅处理定性维度的搜索结果冲突。

#### 3.3.2 数据补充

**问题**：去重后某些章节可能仍有数据缺失（某些 data_needs 未被任何查询覆盖）。

**方案**：检查每个章节的 data_needs 覆盖率，缺失的进行补充搜索。

```python
def _get_covered_needs(self, section: SectionDataSpec, data_points: List[Dict]) -> Set[str]:
    covered = set()
    all_text = " ".join(dp.get("content", "") + dp.get("title", "") for dp in data_points)
    for need in section.search_data_needs:
        if need in all_text:
            covered.add(need)
    return covered

async def _supplement_missing_data(self, section_specs, data_pool, search_skill):
    for section in section_specs:
        covered = self._get_covered_needs(section, data_pool)
        missing = [n for n in section.search_data_needs if n not in covered]
        
        if not missing:
            continue
        
        for need in missing:
            query = f"{self._extract_keywords(topic)} {need} {current_year}"
            result = await self._deduplicator.search(query, section.section_id, search_skill)
            data_pool.append(result)
```

补充搜索也走走重逻辑（同一 need 只搜一次），最多 2 轮补充，覆盖率达到 80% 即停止。

**补充数据的 agent_id 归属与注入**：

1. 补充搜索结果追加到**所有需要该指标的 agent** 的 `data_points_by_agent[agent_id]`
2. 补充搜索结果同时写入 `canonical_data`（避免 phase_2 分析时同一指标出现不同值）
3. agent_id 与 section_id 的映射通过 `AgentSpec.context["section_id"]` 反向查找

> **v2.2 修正**：补充搜索发生在两次 `_execute_batch` 调用之间（phase_1 完成后、phase_2 开始前），不在 `_execute_batch` 内部。补充数据直接修改 `phase_1_results` 中的 `data_points` 和 `sources`，然后作为 `previous_results` 传入 phase_2 的 `_execute_batch`。

data_pool 使用 `aggregated_data_points`（扁平列表，包含所有 agent 的搜索结果），而非 `data_points_by_agent`（按 agent 分桶，只看单个 agent 的结果会导致误判缺失）。

补充搜索由 engine 在两次 `_execute_batch` 调用之间统一执行，结果追加到 `phase_1_results` 中所有需要该指标的 agent 的 `data_points` 和 `sources`：

```python
# 在 engine.py，phase_1 batch 完成后、phase_2 batch 开始前：
for need, supplement_data in supplement_results.items():
    for result in phase_1_results:
        agent_id = result.get("agent_id", "")
        section_spec = self._get_section_spec_by_agent_id(agent_id)
        if section_spec and need in section_spec.all_data_needs:
            result.setdefault("data_points", []).extend(supplement_data["data_points"])
            result.setdefault("sources", []).extend(supplement_data["sources"])
```

#### 3.3.3 补充与共享的闭环

```
Round 1: 按章节 data_needs 生成查询 → 去重 → 搜索 → 数据池
         检查覆盖率: section_0 缺 [毛利率]

Round 2: 补充搜索 "比亚迪 毛利率" → 检查去重缓存
         → 缓存未命中 → 执行搜索 → 结果加入数据池
         → 同时检查其他 section 是否也需要毛利率 → 如有则一并标记

终止条件: 覆盖率 >= 80% 或已执行 2 轮补充
```

---

### Stage 4：分析（不变）

每个 phase_2 agent 拿到：

| 数据类型 | 来源 | 作用 |
|---------|------|------|
| chapter_data | phase_1 对应 agent 的搜索结果（按 agent_id 依赖过滤） | 章节原始数据，供分析细节 |
| canonical_data | 对账后的全局一致指标 | 跨章节一致性锚定，LLM 优先引用 |

phase_2 agent 生成章节报告时：canonical_data 优先引用，chapter_data 补充细节。跨章节数据一致性由 canonical_data 保证。

---

## 4. 改动范围

### 4.1 新增模块

| 模块 | 位置 | 职责 |
|------|------|------|
| `SearchQueryDeduplicator` | `src/core/search/query_deduplicator.py` | 搜索查询去重缓存（含 per-query lock + 缓存键规范化 + deep copy） |
| `SectionDataSpec` / `SubSectionSpec` | `src/core/decomposition/strategies.py`（扩展） | 3 级框架数据结构（含 data_source_type） |
| 框架扩展逻辑 | `src/agents/fixed_agents/requirement_analysis_agent.py` | LLM 生成 3 级框架 |
| `validate_section_data_specs` | `src/core/decomposition/strategies.py`（扩展） | 3 级框架验证 + fallback |
| `derive_data_source_type` | `src/core/decomposition/strategies.py`（扩展） | 规则推导 data_source_type（ISSUE-F） |
| `STRUCTURED_DATA_CAPABILITIES` | `src/core/decomposition/strategies.py`（扩展） | 已知结构化数据源能力映射 |
| `SOURCE_PRIORITY` | `src/core/communication.py`（扩展） | 来源优先级映射（ISSUE-G） |

### 4.2 修改模块

| 模块 | 改动 | 影响范围 |
|------|------|---------|
| `strategies.py:295` | 硬编码 skill 列表改为按 aspect 动态路由 | DATA_COLLECTION agent 的 skill 配置 |
| `generic_agent.py:300-304` | `category=="research"` 分支增加结构化数据源路由 + 从 task dict 提取 `preloaded_search_results` 传入 `_do_deep_research`（ISSUE-I） | DATA_COLLECTION agent 的执行流程 |
| `_fetch_structured_data` | 新增方法：调用 stock_data skill 获取结构化数据（使用 `_infer_stock_actions` 推导 action 名，action 名与 `StockDataSkill.execute()` 对齐：`company_info`/`financials`/`key_metrics`/`price_history`/`industry_comparison`） | `generic_agent.py`（新增） |
| `_generate_search_queries` | 当 data_needs 存在时跳过 data_focus，从 data_needs 生成查询；aspect 分支保留为 fallback | `generic_agent.py:2471-2598` |
| `_do_deep_research` | 新增 `preloaded_search_results` 可选参数（默认 None，向后兼容），仅 L302 调用点需适配（其余 3 处为 fallback 路径，传 None）；预分发数据通过 task dict 传递（无需 `receive_preloaded_data` 方法） | `generic_agent.py:1393-1771` |
| `DecompositionPlan` | 新增 `section_data_specs` 字段（`field(default_factory=list)`，向后兼容） | `strategies.py:117-133` |
| `DeepIntentResult` | 新增 `section_data_specs` 字段 | `semantic_intent.py:31-62` |
| `engine.py:_execute_batch` | 新增统一查询规划（在 agent 循环前执行，通过 agent category 判断 DATA_COLLECTION 阶段（ISSUE-H），通过 task dict 注入预分发数据）；对账/补充在 batch 循环内 DATA_COLLECTION batch 完成后执行 | `_execute_batch` 内部 + batch 循环 |
| `_unified_search` | 新增方法：统一查询规划 + 去重搜索 + 结果分发 | `engine.py`（新增） |
| `_get_section_spec` | 新增方法：通过 agent 的 section_id 查找 SectionDataSpec | `engine.py`（新增） |
| `_get_search_skill` | 新增方法：获取可用的搜索 skill 实例 | `engine.py`（新增） |
| `ASPECT_SKILL_MAP` | 从 DEEP_ANALYSIS 的 skill 列表中移除 `stock_data` | `strategies.py:41-67` |
| `write_canonical` | 增加来源优先级（structured_source > search_result），低优先级来源不覆盖高优先级（ISSUE-G） | `communication.py:185-229` |
| `StockDataSkill` | 添加内存缓存 | `src/skills/analysis/stock_data.py` |
| `_infer_stock_actions` | 新增方法（generic_agent.py）：根据 aspect 推导 `StockDataSkill` 的 action 名，与 `StockDataSkill.execute()` 对齐（`financials`/`key_metrics`/`industry_comparison`/`company_info`） | `generic_agent.py`（新增） |
| `_convert_specs_from_dicts` | 新增函数（strategies.py）：将 LLM 返回的 dict 列表转换为 `SectionDataSpec`/`SubSectionSpec` 对象，缺失字段使用默认值，空 sub_sections 自动填充 fallback | `strategies.py`（新增） |

### 4.3 不改模块

| 模块 | 原因 |
|------|------|
| agent_id 体系 | 45+ 处引用，改则崩溃 |
| scheduler.py | 按 agent_id 调度，不变 |
| content_lock.py | 按 section_id 锁定，不变 |
| data_points_by_agent | 按 agent_id 索引数据，不变 |
| result_aggregator.py | 按 agent_id 匹配章节，不变 |
| MetricExtractor | 已有，直接使用 |
| CanonicalDataRegistry | 已有，直接使用 |
| CaliberDecisionEngine | 已有，直接使用 |
| SharedMemory | 已有，直接使用 |
| factory.py | 工厂本身不需要改（_available_skills 运行时扩展在 generic_agent.py 内实现） |

---

## 5. 数据流对比

### 5.1 当前数据流

```
8 个 phase_1 agent
  各自独立搜索 13 条相同查询 (104 次搜索)
  各自得到不同的数字 (营收: 6800/6420/130/54.5...)
  result.agent_id = 自己的 agent_id

8 个 phase_2 agent
  按 agent_id 依赖过滤 → 只看到自己对应 phase_1 的结果
  同一指标跨章节不一致 (section_0 营收=6800, section_3 营收=6420)
  
phase_3 calibrator
  试图修复矛盾 → 1538 个冲突 → 修复失败 → score=10.0/75
```

### 5.2 修订后数据流

```
Stage 0: 数据源路由
  section_0 (财务维度) → agent_0 加载 stock_data
  section_6 (竞争维度) → agent_6 不加载 stock_data
  agent_0 调用 akshare → 营收=6800.28亿@2025Q3 → 写入 canonical_data

Stage 1: 3 级框架
  section_0.data_needs = [营收, 净利润, ROE, 毛利率]
  section_0.search_data_needs = []  ← 全部 structured，无需搜索
  section_3.search_data_needs = [销量, 市场份额]  ← 营收已由 structured 覆盖
  section_4.search_data_needs = []  ← ROE/ROIC 已由 structured 覆盖

Stage 2: Engine 层统一查询规划 + 去重搜索
  仅搜索定性维度：
  agent_0 无搜索查询（全部 structured）
  agent_3 搜 [比亚迪 销量, 比亚迪 市场份额]
  agent_6 搜 [比亚迪 竞争优势, 比亚迪 行业排名]
  → ~40-50 次搜索 (当前 104 次)
  → 每个 agent result 仍带自己的 agent_id

Stage 3: 对账 + 补充
  财务指标已由 canonical_data 保证一致（akshare 精确值）
  搜索维度：MetricExtractor 提取 → canonical_data
  section_0 缺竞争数据 → 补搜 → 加入 agent_0 的 data_points

Stage 4: 分析 (不变)
  phase_2_agent_0 按 agent_id 拿到 phase_1_agent_0 的数据 + canonical_data
  → LLM 优先引用 canonical_data 中的营收=6800.28亿
  phase_2_agent_3 按 agent_id 拿到 phase_1_agent_3 的数据 + canonical_data
  → LLM 也引用 canonical_data 中的营收=6800.28亿 (同一个值)
  → 跨章节一致性保证
```

---

## 6. 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| LLM 生成 3 级框架不准确 | 中 | 验证规则 + fallback（从 1 级框架章节名生成基础 data_needs） |
| 去重缓存导致数据单一来源 | 低 | 缓存的是原始搜索结果（含多网页片段），不是单一值；对账阶段多来源取权威值 |
| 补充搜索无法覆盖所有 data_needs | 中 | 设定覆盖率阈值 80%，未覆盖的由 LLM 在分析阶段推理补充 |
| canonical_data 注入后 LLM 仍不引用 | 中 | 双重保障：(1) prompt 中明确指令优先引用 canonical_data；(2) `_enforce_canonical_values` 后处理（`generic_agent.py:1245-1309`）做正则替换。LLM 释义指标名时，`MetricExtractor` 的 `ENGLISH_ALIASES` 和中文别名映射可覆盖常见变体 |
| 去重部署顺序错误（先去重后框架） | 高 | **必须先部署 3 级框架（Phase A），再部署去重（Phase B）**。否则所有 agent 拿到相同缓存数据，失去章节差异化 |
| akshare API 限流 | 低 | StockDataSkill 添加内存缓存；akshare 无 API Key 限制，但高频请求可能触发反爬 |
| 中心化路由关键词匹配不可靠 | 中 | Phase 0a 用关键词匹配作为过渡；Phase 0b 改为 agent 自主 skill 发现（基于 data_capabilities 匹配） |
| 搜索近似值覆盖 akshare 精确值 | 中 | write_canonical 增加来源优先级：structured_source > search_result；优先级解决时不再发 MANUAL 冲突事件 |
| `write_canonical` 非数值 value 崩溃 | 低 | 已增加 `isinstance(value, (int, float))` 类型检查，非数值 value 跳过冲突检测 |

---

## 7. 实施计划

### Phase 0a：数据源路由修复（✅ 已实施，P0，解决 P3 财务指标冲突）

1. ✅ 修改 `strategies.py`，硬编码 skill 列表改为按 aspect 动态路由
2. ✅ 扩展 `generic_agent.py` 的 `category=="research"` 分支，增加结构化数据源路由
3. ✅ 清理 `ASPECT_SKILL_MAP` 中的 `stock_data`（移到 DATA_COLLECTION 阶段）
4. ✅ 为 `StockDataSkill` 添加内存缓存
5. ✅ 为 `write_canonical` 增加来源优先级
6. 测试：验证财务维度 agent 能调用 stock_data，获取精确值

> **✅ Phase 0a 已实施**，立即缓解 P3 财务指标冲突。

### Phase A：3 级框架 + 章节专属查询（✅ 已实施，P0，解决 P2）

1. 扩展 `DecompositionPlan` 数据结构（新增 `SectionDataSpec` / `SubSectionSpec`，含 data_source_type）
2. 扩展 `DeepIntentResult`，新增 `section_data_specs` 字段
3. 实现 LLM 生成 3 级框架逻辑
4. 实现 `validate_section_data_specs` 验证 + fallback
5. 实现 data_needs 传播路径（requirement_analysis → decompose → AgentSpec.context）
6. 修改 `_generate_search_queries`：当 data_needs 存在时跳过 data_focus，从 data_needs 生成查询；aspect 分支保留为 fallback
7. 测试：验证各章节查询不再重复，覆盖率达 90%+

> **必须先于 Phase B 实施**：3 级框架是去重的前提。没有章节专属查询，所有 agent 仍生成相同查询，去重后所有 agent 拿到完全相同的数据，失去章节差异化。

### Phase B：Engine 层统一查询去重（✅ 已实施，P0，解决 P1，依赖 Phase A）

1. 实现 `SearchQueryDeduplicator`（含 per-query lock + 缓存键规范化 + deep copy + 缓存不可变；搜索调用使用 `search_skill.execute(query=query)` 而非 `.search()`）
2. 在 `engine.py:_execute_batch` 中新增统一查询规划逻辑（在 agent 循环前执行 `_unified_search`，通过 task dict 注入预分发数据）
3. 修改 `_do_deep_research` 新增 `preloaded_search_results` 可选参数，改为补充模式（仅 L302 调用点需适配，L425 降级路径也传递 `preloaded_search_results`，其余 2 处传 None）
4. 测试：验证同一查询只搜一次，结果正确分发，agent_id 不变

### Phase C：数据对账强化（✅ 已实施，P1，解决 P3 定性维度冲突）

1. ✅ 在 phase_1 `_execute_batch` 完成后、phase_2 `_execute_batch` 开始前，执行 MetricExtractor + CanonicalDataRegistry 对账
2. ✅ 对账插入点：`engine.py` batch 循环内，DATA_COLLECTION batch 完成后触发补充逻辑
3. ✅ 将对账结果写入 canonical_data 并注入后续 agent prompt
4. ✅ `write_canonical` 增加非数值类型保护（`isinstance(value, (int, float))`），优先级解决时不再发 MANUAL 冲突事件
5. 测试：验证跨章节同一指标值一致

### Phase D：数据补充（✅ 已实施，P2，完善）

1. ✅ 实现 `_get_covered_needs` 覆盖率检查函数（基于 `aggregated_data_points`，关键词匹配）
2. ✅ 实现 `_supplement_missing_data` 多轮补充搜索（asyncio.gather 并行 + coverage_threshold=0.8 + max_rounds=2）
3. ✅ 补充搜索由 engine 在 batch 循环内 DATA_COLLECTION batch 完成后执行，结果追加到 `phase_1_results` 中所有需要该指标的 agent 的 `data_points` 和 `sources`
4. ✅ 补充搜索结果同时写入 `canonical_data`
5. ✅ 补充数据按 `section_data_specs` 注入 all_results（agent_id 与 section_id 通过 `AgentSpec.context["section_id"]` 反向查找）
6. 测试：验证各章节覆盖率达 80%+

### Phase 0b：Agent 自主 skill 发现（⏳ 未实施，P1，替代 Phase 0a 中心化路由）

1. `Skill` 基类增加 `data_capabilities` 属性
2. 各 skill 声明自己的数据能力（如 StockDataSkill 声明财务指标关键词）
3. agent 增加 `discover_and_load_skills` 方法
4. `_available_skills` 从"创建时固定"变为"创建时初始化 + 运行时可扩展"
5. 测试：验证相同 data_needs 的 agent 自主发现相同 skill

> **依赖 Phase A**：agent 需要 data_needs 才能匹配 data_capabilities。

---

## 8. 预期效果

| 指标 | 当前 | 预期 |
|------|------|------|
| 搜索次数 | 104 | ~40-60（减少 40-50%） |
| 查询覆盖率 | 10% | 90%+ |
| 财务指标冲突 | 占冲突总量 ~70% | 0（akshare 精确值） |
| 定性维度跨章节数据冲突 | 占冲突总量 ~30% | <50 处（对账+canonical_data 缓解） |
| 报告评分 | 40.9 | >70 |
| phase_1 执行时间 | 16 分钟 | 8-12 分钟（搜索减少 + 结构化源即时返回） |

---

## 9. 审计发现（2026-06-15，修订版更新于 2026-06-17）

> 以下问题通过对照实际代码验证发现，按严重程度排序。修订版已将审计修复整合到正文中。

### 9.1 严重问题（已在修订版中修复）

#### AUDIT-1：asyncio.Lock 全局锁会串行化所有搜索

**位置**：3.2.3 `SearchQueryDeduplicator._lock`

**问题**：`asyncio.Lock` 是全局互斥锁，8 个 phase_1 agent 并行执行时，同一时刻只有 1 个 agent 能执行搜索。预估 20 次搜索串行执行 ~40s，而当前 104 次搜索按 8 并行批次执行 ~26s。

**修复**：改为 per-query lock + meta lock。不同查询可并行搜索，只有同一查询的并发请求才串行化。已整合到 §3.2.3。

---

#### AUDIT-2：DomainRoleInferrer.data_focus 会与 data_needs 并行生效，重新引入重复查询

**位置**：3.1.6 data_needs 传播路径 vs `_do_deep_research` 中 L1481-1485

**问题**：`data_needs` 和 `data_focus` 同时生效，通用查询重新引入重复。

**修复**：当 `data_needs` 存在时，`_generate_search_queries` 跳过 `data_focus` 查询生成。`DomainRoleInferrer` 的 `role` 和 `expertise` 字段仍可用于 LLM prompt 构建。已整合到 §3.2.2。

---

#### AUDIT-9：去重器与 `_do_deep_research` 多轮循环存在语义冲突

**位置**：3.2.1 Issue J（去重器作为搜索前置拦截层）vs `_do_deep_research` 循环逻辑（`generic_agent.py:1536-1771`）

**问题**：去重器作为"透明代理"插入搜索调用前，与 `_do_deep_research` 的多轮搜索+质量评估循环存在根本冲突：
1. 缓存命中返回共享结果，但各 agent 质量评估独立运行，可能一个达标一个不达标
2. `executed_queries` 是 agent 局部变量，缓存命中时状态不一致
3. agent 质量不足触发 LLM 扩展，新查询又被去重器拦截，形成空循环

**修复**：改为 engine 层统一查询规划 + 预分发 + 补充搜索模式。去重器在 engine 层使用，不在 agent 内部使用。已整合到 §3.2.1/3.2.4/3.2.5。

---

#### AUDIT-10：跨 agent 缓存共享 vs agent 局部质量评估的矛盾

**位置**：同 AUDIT-9

**问题**：去重器打破了 `_do_deep_research` 的假设（搜索结果是 agent 独有的），但质量评估仍独立运行。

**修复**：同 AUDIT-9，改为 engine 层统一规划。预分发数据直接加入 agent 的 `all_results` 和 `executed_queries`，质量评估基于完整数据。

---

### 9.2 中等问题（已在修订版中修复）

#### AUDIT-3：现有 aspect-specific 硬编码分支（L2504-2558）的命运未指定

**修复**：保留作为 fallback。当 `data_needs` 足够具体时跳过 aspect 分支；当 `data_needs` 为空或 3 级框架生成失败时触发。已整合到 §3.2.2。

---

#### AUDIT-4：缓存键规范化未指定

**修复**：添加 `_normalize_query` 函数（合并多余空格、去首尾空格、统一小写）。同义词不规范化为同一键。已整合到 §3.2.3。

---

#### AUDIT-5：LLM 生成的 3 级框架缺乏验证规则和回退机制

**修复**：添加 `validate_section_data_specs` + `_fallback_specs_from_names`。已整合到 §3.1.5。

---

#### AUDIT-6：intent_result.section_data_specs 字段不存在于当前数据类

**修复**：在 `DeepIntentResult` 中新增 `section_data_specs: List[SectionDataSpec] = field(default_factory=list)`，有默认值，向后兼容。已整合到 §3.1.6。

---

#### AUDIT-11：补充搜索的 agent_id 归属逻辑未定义

**修复**：补充搜索结果追加到所有需要该指标的 agent 的 `data_points_by_agent`，同时写入 `canonical_data`。agent_id 与 section_id 映射通过 `AgentSpec.context["section_id"]` 反向查找。已整合到 §3.3.2。

---

#### AUDIT-12：data_needs 覆盖率检查函数不存在

**修复**：明确"覆盖"定义为搜索结果 title+content 中包含 data_need 关键词；实现 `_get_covered_needs`；使用 `aggregated_data_points`（扁平列表）。已整合到 §3.3.2。

---

### 9.3 低优先级问题（已在修订版中修复）

#### AUDIT-7：补充数据注入机制需明确

**修复**：明确注入方式——直接 append 到 `data_points_by_agent` 和 `sources_by_agent`。已整合到 §3.3.2。

---

#### AUDIT-13：`_generate_section_queries` 每个 need 4 条查询变体，查询数爆炸

**修复**：每个 need 生成 2 条变体（`{topic} {need} {year}`, `{topic} {need} 数据`）；`data_source_type="structured"` 的 need 不生成搜索查询。已整合到 §3.2.2。

---

### 9.4 架构级问题（已在修订版中修复）

#### AUDIT-8：财务数据应优先从结构化数据源获取，而非搜索引擎爬取

**修复**：新增 Stage 0（数据源路由），分 Phase 0a（中心化路由）和 Phase 0b（agent 自主发现）两步实施。已整合到 §3.0。

---

### 9.5 审计结论

| 编号 | 严重度 | 问题 | 修订版状态 |
|------|--------|------|-----------|
| AUDIT-8 | **架构级** | 缺少数据源智能路由，所有维度都走搜索引擎 | 已修复（§3.0 Stage 0） |
| AUDIT-9 | **严重** | 去重器与 _do_deep_research 多轮循环存在语义冲突 | 已修复（§3.2.1 engine 层统一规划） |
| AUDIT-10 | **严重** | 跨 agent 缓存共享 vs agent 局部质量评估的矛盾 | 已修复（§3.2.1 engine 层统一规划） |
| AUDIT-1 | **严重** | 全局锁串行化搜索 | 已修复（§3.2.3 per-query lock） |
| AUDIT-2 | **严重** | data_focus 与 data_needs 并行引入重复 | 已修复（§3.2.2 data_needs 优先） |
| AUDIT-3 | 中等 | aspect 硬编码分支命运未指定 | 已修复（§3.2.2 保留为 fallback） |
| AUDIT-4 | 中等 | 缓存键无规范化 | 已修复（§3.2.3 _normalize_query） |
| AUDIT-5 | 中等 | 3 级框架无验证/回退 | 已修复（§3.1.5 validate + fallback） |
| AUDIT-6 | 中等 | section_data_specs 字段不存在 | 已修复（§3.1.6 DeepIntentResult 扩展） |
| AUDIT-11 | 中等 | 补充搜索的 agent_id 归属逻辑未定义 | 已修复（§3.3.2 多 agent 追加 + canonical） |
| AUDIT-12 | 中等 | data_needs 覆盖率检查函数不存在 | 已修复（§3.3.2 _get_covered_needs） |
| AUDIT-7 | 低 | 补充数据注入方式未明确 | 已修复（§3.3.2 明确注入代码） |
| AUDIT-13 | 低 | _generate_section_queries 每个 need 4 条变体，查询数爆炸 | 已修复（§3.2.2 2 条变体 + data_source_type 过滤） |

---

### 9.6 修订版事实性修正

> 以下为初版文档中对照实际代码发现的事实性错误，修订版已修正。

| 编号 | 初版内容 | 实际代码 | 修正 |
|------|---------|---------|------|
| ERR-1 | `strategies.py:98` 已有 `SectionSpec` 类 | `strategies.py:98` 是 `AgentSpec`；`SectionSpec` 在 `task_structure.py:56` | 修正引用为 `task_structure.py:56`，`SectionDataSpec` 与 `SectionSpec` 不冲突 |
| ERR-2 | P3 根因代码位置 `generic_agent.py:1904-1917` | `generic_agent.py:1904-1917` 是中英文关键词映射字典；`data_points_by_agent` 在 `engine.py:1904-1917` | 修正为 `engine.py:1904-1917` |
| ERR-3 | 对账/补充搜索插入点"phase_1 后、phase_2 前" | L2163 是通用 task dict 构建（适用于所有 agent 类型，非特定于 synthesis/analysis）；phase_1 和 phase_2 是两次不同的 `_execute_batch` 调用 | v2.2 修正：对账/补充在两次 `_execute_batch` 调用之间执行，不在 `_execute_batch` 内部（详见 ISSUE-E） |
| ERR-4 | `_enforce_canonical_values` 行范围 L1245-1279 | 实际方法延伸至 L1309 | 修正为 L1245-1309 |

---

## 10. 修订日志

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-15 | v1 | 初版：四阶段流水线（Stage 1-4） |
| 2026-06-17 | v2 | 修订版：主要变更如下 |
| | | 新增 Stage 0（数据源路由），解决架构级问题 AUDIT-8 |
| | | Stage 2 从"透明代理"改为"Engine 层统一查询规划"，解决 AUDIT-9/10 |
| | | 去重器从全局锁改为 per-query lock，解决 AUDIT-1 |
| | | 查询变体从 4 条/need 改为 2 条/need + data_source_type 过滤，解决 AUDIT-13 |
| | | 新增 3 级框架验证+回退机制，解决 AUDIT-5 |
| | | 新增缓存键规范化，解决 AUDIT-4 |
| | | 明确 data_needs 优先于 data_focus，aspect 分支保留为 fallback，解决 AUDIT-2/3 |
| | | 明确补充搜索 agent_id 归属 + 覆盖率检查函数，解决 AUDIT-7/11/12 |
| | | 修正 4 处事实性错误（ERR-1/2/3/4） |
| | | 效果预估从 ~20 次搜索修正为 ~40-60 次 |
| | | 实施计划从 Phase A-D 扩展为 Phase 0a/A/B/C/D/0b |
| | | SubSectionSpec 新增 data_source_type 字段 |
| | | SectionDataSpec 新增 search_data_needs / structured_data_needs 属性 |
| 2026-06-17 | v2.1 | 自审修正： |
| | | 修正 data_points_by_agent 构建完成位置为 L1917（非 L1922，L1922 是 sources_by_agent） |
| | | 明确 L2163 是通用 task dict 构建（适用所有 agent 类型，非特定于 synthesis/analysis） |
| | | 明确 `receive_preloaded_data` 是需新增的方法（当前不存在） |
| | | 明确 `_do_deep_research` 接口变更细节：4 处调用点（L302, L404, L759, L948）需适配 |
| 2026-06-17 | v2.2 | 深度自审修正（6 处）： |
| | | **ISSUE-A**：统一查询规划的执行时机与 `_execute_batch` 循环矛盾——修正为 task dict 注入 |
| | | **ISSUE-B**：`receive_preloaded_data` 方法多余——修正为通过 task dict 传递 |
| | | **ISSUE-C**：统一搜索在 `_execute_batch` 内的并行执行问题——修正为 per-query 并行 |
| | | **ISSUE-D**：`_do_deep_research` 4 处调用点中仅 L302 需适配——其余 3 处无预分发 |
| | | **ISSUE-E**：对账/补充的插入点与 `_execute_batch` 单次调用模型不匹配——补充跨 batch 协调说明 |
| | | **ISSUE-F**：`data_source_type` 的 LLM 生成可靠性——修正为规则推导为主、LLM 补充 |
| | | **ISSUE-G**：write_canonical 无来源优先级，search_result 会覆盖 structured_source——增加优先级比较 |
| | | **ISSUE-H**：stage_name 传入值与文档假设不匹配——改用 agent category 判断 |
| | | **ISSUE-I**：preloaded_search_results 传递路径未完整描述——补充 task dict → _do_deep_research 路径 |
| | | **ISSUE-J**：§4 改动范围遗漏 7 个新增方法/函数/常量——补充完整 |
| 2026-06-17 | v2.3 | 深度代码对照审查修正（52 项发现）： |
| | | **状态更新**：文档状态从"方案设计"改为"Phase 0a/A/B 已实施，Phase C/D/0b 待实施" |
| | | **HIGH**: `CaliberDecisionEngine` 不存在为独立类，标注为"待实现" |
| | | **HIGH**: Phase 0a/A/B 全部标记为 ✅ 已实施 |
| | | **HIGH**: `StockDataSkill` 内存缓存补实现（类级 `_memory_cache` 字典） |
| | | **MEDIUM**: 修正 §1.3 全部行号引用（executed_queries~L1626, _generate_search_queries~L2551, data_points_by_agent~L1918） |
| | | **MEDIUM**: `SOURCE_PRIORITY` 从局部变量提升为模块级常量 |
| | | **MEDIUM**: `validate_section_data_specs` 补充 `re.match(r'section_\\d+')` section_id 格式验证 |
| | | **MEDIUM**: `_get_section_spec` 提取为 engine.py 独立方法（原先内联在 `_unified_search` 中） |
| | | **MEDIUM**: 修正 canonical_data 注入 prompt 行号为 ~L490（非 L468-477） |
| | | **MEDIUM**: 修正"5死锁12数据丢失"为"风险估计"措辞 |
| | | **MEDIUM**: Phase C 标记为 ⏳ 部分实施，Phase D/0b 标记为 ⏳ 未实施 |
| | | **LOW**: 修正 `_enforce_canonical_values` 行号为 ~L1266-1330 |
| | | **LOW**: 修正 `AgentSpec` 位置为 ~L224（非 L98） |
| | | **LOW**: 修正 `DecompositionPlan` 位置为 ~L244-261 |
| | | **LOW**: 删除 engine.py 末尾死代码（_filter_data_by_aspect 重复片段） |
| 2026-06-17 | v2.4 | 代码审查修复 + 文档更新： |
| | | **状态更新**：Phase C/D 从"⏳ 部分实施/未实施"改为"✅ 已实施" |
| | | **HIGH**: `SearchQueryDeduplicator.search()` 调用 `search_skill.search(query)` — 该方法不存在，修正为 `search_skill.execute(query=query)` |
| | | **HIGH**: `_infer_stock_actions` 返回的 action 名（`income_statement`/`balance_sheet`/`cash_flow`/`valuation`）与 `StockDataSkill.execute()` 期望的 action 名（`company_info`/`financials`/`key_metrics`/`price_history`/`industry_comparison`）完全不匹配，修正对齐 |
| | | **HIGH**: `write_canonical` 对非数值类型 value 执行算术运算会 `TypeError`，增加 `isinstance(value, (int, float))` 类型检查 |
| | | **MEDIUM**: `section_spec_map` 键在 dependent aspects 存在时与 LLM 生成的 `section_N` 索引不对齐，修正为 `seq_idx` 顺序计数器 + 按 `spec.name` 双重匹配 |
| | | **MEDIUM**: `write_canonical` 优先级解决冲突时仍返回 `MANUAL` ConflictRecord，修正为设 `conflict=None`（已由优先级自动解决） |
| | | **MEDIUM**: `engine.py:_section_data_specs` 初始化无防御性 dict→`SectionDataSpec` 转换，增加 `_convert_specs_from_dicts` 转换 |
| | | **MEDIUM**: 深度分析降级路径（L425）未传递 `preloaded_search_results`，补充传递 |
| | | **新增**：LLM prompt 实现 — `intent_analysis_system.md` 增加 `section_data_specs` 生成规则和示例，`intent_analysis_user.md` 增加输出要求，`_build_result()` 解析 LLM 输出中的 `section_data_specs`，`_convert_specs_from_dicts()` 自动转换 |
| | | **新增**：10 个测试覆盖 `section_data_specs` LLM 解析 + dict→对象转换 + `to_dict`/`from_dict` roundtrip + `decompose` 集成 |
| | | **测试**：94 passed（含原有 84 + 新增 10），0 regression |
| 2026-06-17 | v2.5 | 运行时路径深度审查修复： |
| | | **HIGH**: `_supplement_missing_data` 注入循环遍历 `all_results`（仅含前序批次），当前 `batch_results` 尚未加入，导致补充数据永远无法注入到触发补充的 agent。修正为遍历 `batch_results` |
| | | **MEDIUM**: `_get_section_id_from_agent` 在 `agent.section_id` 为空时回退到 `agent.agent_id`，产生无效 section key 导致 spec 查找静默失败。修正为返回空字符串 |
| | | **MEDIUM**: 补充注入循环变量 `result` 遮蔽外层 `ExecutionResult`，修正为 `_res` |
| | | **LOW**: `_unified_search` 非共享查询结果按引用传递，存在下游修改风险。修正为统一 `copy.deepcopy` |
| | | **测试**：108 passed（94 unit + 28 e2e），0 regression |
| 2026-06-18 | v2.6 | 二次深度审查修复： |
| | | **MEDIUM**: `_supplement_missing_data` 使用独立 `SearchQueryDeduplicator` 实例，无法复用 `_unified_search` 缓存，导致重复搜索 API 调用。修正为共享 `self._search_deduplicator` 实例 |
| | | **MEDIUM**: `_get_covered_needs` 子串匹配过于宽泛（单字误匹配风险）。修正为跳过 len<2 的 need，保留子串匹配（中文词间无分隔符，边界检查不适用） |
| | | **MEDIUM**: cached results / content lock 路径中 `section_id` 为空字符串导致断联。修正为 fallback 查 `_agent_id_to_section_id` 映射 |
| | | **LOW**: `_unified_search`/`_get_section_spec` 中冗余 fallback `getattr(agent, 'section_id', '')` 已被 `_get_section_id_from_agent` 覆盖，删除死代码 |
| | | **LOW**: `search_topic = self._extract_keywords(topic)` 在 per-agent 循环内重复计算，提到循环外 |
| | | **测试**：108 passed，0 regression |

---

## 11. 深度自审发现（2026-06-17 v2.2）

> 以下问题在逐行审视修订版与实际代码交互时发现，均为方案内部逻辑矛盾或与代码实际运行方式不一致之处。

### ISSUE-A：统一查询规划的执行时机与 `_execute_batch` 循环矛盾

**文档描述**（§3.2.4）：

```
engine._execute_batch():
  1. 从 section_data_specs 提取所有章节的 search_data_needs
  2. 合并去重：收集所有唯一查询
  3. 统一执行搜索（SearchQueryDeduplicator 协调）
  4. 搜索结果按 agent_id 分发给各 phase_1 agent
  5. phase_1 agent 接收预分发数据 + 执行补充搜索
```

**实际代码逻辑**（`engine.py:1875-2242`）：

`_execute_batch` 是一个**单次调用**的循环，对传入的 `agents` 列表逐个构建 task dict 并通过 `_coordinator.dispatch_task` 调度。它不是"先统一搜索再分发"的两阶段结构——它是"逐个构建 task → 调度 → 等结果"的单阶段循环。

文档描述的"统一查询规划"需要发生在 `_execute_batch` 循环**之前**，但 `_execute_batch` 的调用方是 `engine.py:1723`，此时 phase_1 的 agents 已经准备好了，`previous_results` 为空（phase_1 无前序结果）。

**问题**：如果统一查询规划发生在 `_execute_batch` 调用之前，需要一个新的入口函数。如果发生在 `_execute_batch` 内部（在 agent 循环之前），则需要修改 `_execute_batch` 的内部结构。

**修正**：统一查询规划应在 `_execute_batch` 内部、agent 循环之前执行，搜索结果通过 task dict 传递给各 agent（无需 `receive_preloaded_data` 方法）：

```python
async def _execute_batch(self, agents, requirement, previous_results, scheduler, stage_name=""):
    # === 新增：统一查询规划（仅对 DATA_COLLECTION 阶段） ===
    preloaded_data = {}
    if stage_name == "data_collection" and self._section_data_specs:
        preloaded_data = await self._unified_search(agents, requirement)
    
    # ... 现有 data_points_by_agent 构建逻辑不变 ...
    
    for agent in agents:
        task = { ... }  # 现有 task 构建
        
        # 注入预分发数据
        if agent.agent_id in preloaded_data:
            task["preloaded_search_results"] = preloaded_data[agent.agent_id]
        
        # ... 现有调度逻辑不变 ...
```

**影响**：删除 `receive_preloaded_data` 方法需求，改为通过 task dict 传递（与现有 `canonical_data`、`aggregated_data_points` 的传递方式一致）。

### ISSUE-B：`receive_preloaded_data` 方法多余

**文档描述**（§3.2.4/3.2.5/§4.2/§10 v2.1）：

> `GenericAgent` 需新增 `receive_preloaded_data` 方法（当前不存在），由 engine 层在 agent 执行前调用

**问题**：engine 层与 agent 之间的数据传递是通过 task dict 实现的——`task = {"action": "execute", "data": ..., "aggregated_data_points": ..., "canonical_data": ...}`。所有数据都通过这个 dict 传递，agent 在 `execute(task)` 中读取。不存在"在执行前调用 agent 方法注入数据"的模式——engine 不直接调用 agent 的方法来注入数据，而是通过 task dict 传递。

**修正**：预分发搜索结果通过 task dict 的新 key 传递（如 `task["preloaded_search_results"]`），与现有模式一致。`receive_preloaded_data` 方法不再需要。`_do_deep_research` 从 `task` 参数中读取预分发数据（通过 `self._context` 或直接参数传递）。

### ISSUE-C：统一搜索在 `_execute_batch` 内的并行执行问题

**文档描述**（§3.2.4）：

```python
# 2. 统一去重搜索
for agent_id, queries in all_queries.items():
    for query in queries:
        result = await deduplicator.search(query, section_id, search_skill)
```

**问题**：这段伪代码是**串行**执行所有查询（`for` 循环 + `await`），没有利用并行性。虽然 per-query lock 允许不同查询并行，但单线程 `for await` 循环无法实现并行。

**修正**：使用 `asyncio.gather` 批量并行执行：

```python
# 收集所有唯一查询及其对应的 section_ids
unique_queries = {}  # normalized_query -> [section_ids]
for agent_id, queries in all_queries.items():
    section_id = ...
    for query in queries:
        normalized = deduplicator._normalize_query(query)
        unique_queries.setdefault(normalized, []).append(section_id)

# 并行执行所有唯一查询
async def _search_one(query, section_ids, search_skill):
    result = await deduplicator.search(query, section_ids[0], search_skill)
    # 缓存命中时，后续 section_ids 已在 deduplicator 内部记录
    for sid in section_ids[1:]:
        # 为其他 section 分发深拷贝
        ...
    return query, result

search_tasks = [
    _search_one(q, sids, search_skill) 
    for q, sids in unique_queries.items()
]
results = await asyncio.gather(*search_tasks)
```

### ISSUE-D：`_do_deep_research` 4 处调用点中仅 L302 需适配

**文档描述**（§3.2.5/§4.2/§10 v2.1）：

> 4 处调用点（L302, L404, L759, L948）需适配

**实际代码分析**：

| 调用点 | 位置 | agent_category | 是否需要预分发数据 |
|--------|------|---------------|-------------------|
| L302 | `category=="research"` | DATA_COLLECTION | **是** — 这是 phase_1 agent |
| L404 | `category=="market-analysis"` fallback | DEEP_ANALYSIS | **否** — 这是降级搜索，无预分发 |
| L759 | fallback 路径 | 旧版兼容路径 | **否** — 旧版路径，无预分发 |
| L948 | 异常恢复 fallback | 通用 | **否** — 恢复路径，无预分发 |

仅 L302 需要适配 `preloaded_search_results` 参数。其余 3 处是 fallback/降级路径，不应接收预分发数据（它们是在没有预分发数据时才触发的）。

**修正**：仅 L302 传递 `preloaded_search_results`，其余 3 处保持 `None`（默认值，向后兼容）。文档中"4 处调用点需适配"改为"仅 L302 需适配，其余 3 处为 fallback 路径，传 None 即可"。

### ISSUE-E：对账/补充的插入点与 `_execute_batch` 单次调用模型不匹配

**文档描述**（§3.3.1/§3.3.2/§4.2）：

> 对账插入点：`engine.py:_execute_batch` 中，phase_1 结果已收集、`data_points_by_agent` 已构建后（约 L1917 之后），构建后续 task 前（约 L2163 之前）

**实际代码分析**：

`_execute_batch` 的执行模型是：**接收一组 agents 和前序结果 → 构建所有 agent 的 task → 调度 → 收集结果**。它不是"phase_1 执行完 → 对账 → phase_2 开始"的两阶段模型。

实际上，phase_1 和 phase_2 是通过**两次不同的 `_execute_batch` 调用**实现的（`engine.py:1723` 的调用方管理阶段切换）。对账和补充搜索应发生在**两次 `_execute_batch` 调用之间**，而非单次 `_execute_batch` 内部。

**修正**：对账/补充的插入点不在 `_execute_batch` 内部，而在 `engine.py:1082` 的 batch 循环中，DATA_COLLECTION batch 完成后、下一个 batch 开始前。通过检查 batch_agents 的 category 判断当前 batch 是否为 DATA_COLLECTION：

```python
# engine.py batch 循环（简化）：
for batch_index, batch_agent_ids in enumerate(execution_batches):
    batch_results = await self._execute_agents_batch(...)
    all_results.extend(batch_results)
    
    # S-FIX-2: 现有 canonical data 提取
    ...
    
    # === 对账 + 补充（仅 DATA_COLLECTION batch 完成后） ===
    _is_data_collection = any(
        getattr(scheduler.get_agent_by_id(aid), 'config', {}).get('category', '') == 'research'
        for aid in batch_agent_ids
    )
    if _is_data_collection and self._section_data_specs:
        supplement_data = await self._supplement_missing_data(batch_results)
        # 合并到 all_results
```

文档中"约 L1917 之后、约 L2163 之前"的描述不准确——L1917 是 `_execute_batch` 内部构建 `data_points_by_agent` 的位置，这是在**同一次** batch 调用内为当前 batch 的 agents 准备数据，不是跨阶段对账的插入点。

### ISSUE-F：`data_source_type` 的 LLM 生成可靠性

**文档描述**（§3.1.2/§3.1.4）：

3 级框架由 LLM 生成，包括 `data_source_type` 字段。示例中 section_0 所有 sub_section 的 `data_source_type` 都是 `"structured"`。

**问题**：LLM 不一定知道哪些指标 akshare 能覆盖。例如：
- LLM 可能标注 `data_source_type="structured"` 给"TAM"（市场总量），但 akshare 的 `StockDataSkill` 没有 TAM 数据
- LLM 可能标注 `data_source_type="search"` 给"净利润"，但 akshare 利润表有此数据
- 不同行业的上市公司，akshare 覆盖的数据范围不同（A股 vs 港股 vs 美股）

如果 `data_source_type` 标注错误，会导致：
1. 标为 `structured` 但实际无法获取 → 该 need 无数据
2. 标为 `search` 但实际有结构化源 → 错过精确数据，仍用搜索近似值

**修正**：`data_source_type` 不应由 LLM 生成，而应由**规则推导**：

```python
# 已知的结构化数据源能力（硬编码，可扩展）
STRUCTURED_DATA_CAPABILITIES = {
    "stock_data": {
        "zh": ["营收", "净利润", "毛利率", "净利率", "ROE", "ROA", "ROIC", 
               "资产负债率", "流动比率", "速动比率", "现金流", "研发费用",
               "销量", "产量", "市场份额", "PE", "PB", "利润表", "资产负债表", "现金流量表"],
    },
}

def derive_data_source_type(data_need: str, topic: str, intent_result: Any) -> str:
    """根据 data_need 和主题推导数据源类型"""
    # 1. 检查已知结构化数据源是否覆盖该 need
    for skill_name, capabilities in STRUCTURED_DATA_CAPABILITIES.items():
        for lang, keywords in capabilities.items():
            if data_need in keywords:
                return "structured"
    
    # 2. 如果主题涉及上市公司，部分财务指标默认 structured
    if _is_listed_company_topic(topic):
        FINANCIAL_KEYWORDS = ["营收", "利润", "率", "费用", "ROE", "ROA", "ROIC", "PE", "PB", "DCF"]
        if any(kw in data_need for kw in FINANCIAL_KEYWORDS):
            return "both"  # 结构化可能有，但搜索补充
    
    # 3. 默认搜索
    return "search"
```

LLM 仍生成 `data_needs`，但 `data_source_type` 由规则推导，不依赖 LLM 对数据源的了解。这消除了 LLM 标注错误的风险。

> **对 §3.1.4 的影响**：LLM 输出格式从 `SubSectionSpec(data_needs=..., data_source_type=...)` 改为 `SubSectionSpec(data_needs=...)`，`data_source_type` 在 `decompose()` 中由 `derive_data_source_type()` 推导填充，默认值 `"search"` 作为兜底。

### ISSUE-G：write_canonical 无来源优先级，search_result 会覆盖 structured_source

**位置**：§3.0.2 + `communication.py:185-229`

**问题**：文档要求 `write_canonical` 增加来源优先级（structured_source > search_result），但当前实现（L211-216）是无条件覆盖——后写入的值总是覆盖先写入的值。如果 DATA_COLLECTION agent 先通过 akshare 写入营收=6800.28（caliber="structured_source"），然后搜索结果写入营收=6420（caliber="search_result"），6420 会覆盖 6800.28。

**修正**：`write_canonical` 需要增加来源优先级比较：

```python
SOURCE_PRIORITY = {
    "structured_source": 100,
    "search_result": 50,
    "llm_inference": 10,
}

async def write_canonical(self, metric, value, caliber="", source="", publisher=""):
    ...
    if existing:
        existing_priority = SOURCE_PRIORITY.get(existing.get("caliber", ""), 0)
        new_priority = SOURCE_PRIORITY.get(caliber, 0)
        if new_priority <= existing_priority and new_priority != existing_priority:
            # 低优先级来源不覆盖高优先级（同优先级仍覆盖，保留最新值语义）
            return conflict  # 仍返回冲突记录，但不更新值
    self._data[key] = {...}
```

> **对 §3.0.2 的影响**：§3.0.2 中 DATA_COLLECTION agent 先写 structured_source、后写 search_result 的顺序正确，但需要 `write_canonical` 的来源优先级机制保证 search_result 不覆盖 structured_source。

### ISSUE-H：stage_name 传入值与文档假设不匹配

**位置**：§3.2.4 + `engine.py:1331`

**问题**：文档假设 `stage_name == "data_collection"` 可以判断当前 batch 是 DATA_COLLECTION 阶段，但实际 `_execute_batch` 的调用方传入的是 `"batch_1"`, `"batch_2"` 等（L1331: `stage_name=f"batch_{batch_index + 1}"`）。

**修正**：不修改 stage_name 传入值（避免影响现有逻辑），改为在 `_execute_batch` 内通过检查 agents 的 category 判断：

```python
# 在 _execute_batch 开头，agent 循环之前：
_is_data_collection = any(
    getattr(a, 'config', {}).get('category', '') == 'research'
    for a in agents
)
preloaded_data = {}
if _is_data_collection and self._section_data_specs:
    preloaded_data = await self._unified_search(agents, requirement)
```

> **对 §3.2.4 的影响**：伪代码中 `if stage_name == "data_collection"` 改为 `if _is_data_collection`。

### ISSUE-I：preloaded_search_results 传递路径未完整描述

**位置**：§3.2.5

**问题**：文档说"预分发数据通过 task dict 传递"，但未描述从 task dict 到 `_do_deep_research` 的传递路径。当前 L302 调用 `_do_deep_research` 时，task dict 已经在 `execute()` 方法的作用域内（L167），但 `_do_deep_research` 不接收 task 参数。

**修正**：在 L300-304 的 `category=="research"` 分支中，从 task dict 提取 preloaded_search_results 并传入：

```python
if agent_category == "research":
    preloaded = task.get("preloaded_search_results")
    if topic and "search_skill" in available_skills and skill_registry:
        search_results = await self._do_deep_research(
            topic=topic, aspect=aspect, aspects=aspects,
            skill_registry=skill_registry,
            preloaded_search_results=preloaded,  # 新增
        )
```

> **对 §3.2.5 的影响**：调用点适配表中 L302 的"从 task dict 传入"需具体化为 `task.get("preloaded_search_results")`。

### ISSUE-J：§4 改动范围遗漏 7 个新增方法/函数/常量

**位置**：§4.1/§4.2

**遗漏项**：

| 模块 | 类型 | 用途 |
|------|------|------|
| `_fetch_structured_data` | 新增方法（generic_agent.py） | 调用 stock_data skill 获取结构化数据 |
| `_get_section_spec` | 新增方法（engine.py） | 通过 agent 的 section_id 查找 SectionDataSpec |
| `_get_search_skill` | 新增方法（engine.py） | 获取可用的搜索 skill 实例 |
| `_unified_search` | 新增方法（engine.py） | 统一查询规划 + 去重搜索 + 结果分发 |
| `derive_data_source_type` | 新增函数（strategies.py） | 规则推导 data_source_type |
| `STRUCTURED_DATA_CAPABILITIES` | 新增常量（strategies.py） | 已知结构化数据源能力映射 |
| `SOURCE_PRIORITY` | 新增常量（communication.py） | 来源优先级映射 |
