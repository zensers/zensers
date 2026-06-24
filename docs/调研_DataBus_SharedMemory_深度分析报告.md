# DataBus / SharedMemory 深度调研报告

**日期**: 2026-06-06  
**背景**: 比亚迪财务分析报告（research_8c6675c2）暴露严重数据一致性问题（市占率90%、销量三处矛盾、毛利率5个百分点差异），需调查系统级数据协调机制是否有效工作。

---

## 一、组件概览

| 组件 | 位置 | 设计目标 | 当前状态 |
|------|------|----------|----------|
| SharedMemory | `src/core/communication.py:112-304` | Agent 间实时状态同步、规范数据共享 | **部分生效** |
| DataBus | `src/core/data_providers/bus.py:12-155` | 统一数据查询入口、缓存、路由 | **未集成** |
| DataBusV2 | `src/core/data_providers/databus.py:388-734` | 多级缓存、健康检查、限流 | **未集成** |
| MessageBus | `src/core/communication.py:32-111` | 事件发布/订阅 | **部分生效** |

---

## 二、SharedMemory 详细分析

### 2.1 设计架构

```
SharedMemory（内存字典 + asyncio.Lock）
├── _data: Dict[str, Any]           # 核心存储
├── _version: Dict[str, int]        # 版本追踪
├── _lock: asyncio.Lock              # 异步锁
├── _message_bus: MessageBus         # 事件广播（可选）
│
├── 异步接口（线程安全）
│   ├── read(key) → value
│   ├── write(key, value)
│   ├── write_canonical(metric, value, caliber, source, publisher) → ConflictRecord?
│   └── get_canonical(metric) → Dict?
│
└── 同步接口（无线程安全保证，性能优先）
    ├── get(key, default) → value
    ├── set(key, value)
    └── get_all_canonical() → Dict
```

### 2.2 实例化链路

```
ResearchOrchestrator.__init__()                    # orchestrator.py:265
  │
  ├── self._shared_memory = SharedMemory()         # 创建单例
  │
  ├──→ ExecutionEngine(shared_memory=...)          # orchestrator.py:310
  │     ├── AgentCoordinator(shared_memory=...)     # engine.py:478/1017
  │     └── engine._shared_memory.set(...)          # engine.py:1059,1343
  │
  ├──→ DynamicAgentFactory(shared_memory=...)       # orchestrator.py:364
  │     └── agent._shared_memory = ...             # factory.py:386
  │
  ├──→ DocumentGenerationAgent.set_shared_memory()  # orchestrator.py:339
  │
  └──→ QualityCheckAgent.set_shared_memory()        # orchestrator.py:347
```

**结论**: 同一 SharedMemory 实例在整个研究流程中被传递，初始化链路完整。

### 2.3 实际调用追踪

#### 写入路径

| # | 位置 | 时机 | 写入内容 |
|---|------|------|----------|
| W1 | engine.py:1059 | execute_with_scheduler 启动 | `_canonical_registry` = {} （清空） |
| W2 | engine.py:1343 | 每批次完成后 | `_canonical_registry` = {metric: {value, unit, caliber...}} |
| W3 | generic_agent.py:336 | research agent 搜索后 | `canonical:{metric}` = {value, caliber, source...} |

#### 读取路径

| # | 位置 | 时机 | 读取内容 |
|---|------|------|----------|
| R1 | generic_agent.py:444 | analysis agent 构建 prompt | `_canonical_registry` → 注入规范数据段 |
| R2 | generic_agent.py:479 | analysis agent LLM 调用前 | `_canonical_registry` → "实时更新规范数据"段 |
| R3 | generic_agent.py:600 | synthesis agent 构建prompt | `_canonical_registry` → 注入规范数据段 |
| R4 | document_generation_agent.py:501 | 文档生成 | `research_result_{task_id}` → **永远返回 None** |

### 2.4 关键发现

#### 发现 1：SharedMemory 的规范数据**确实在工作**，但存在两条数据流分离

**路径 A（engine 主路径，agent 实际读取）**：

engine.py:1320-1343 的流程：
1. 从 batch_results 提取 data_points
2. 通过 **MetricExtractor** 提取结构化指标（**12 种**：净利润、营收、销量、海外销量、研发投入、毛利率、市占率、增长率、单车利润、财务费用、现金流、负债率）→ 见 `metric_extractor.py:22-35`
3. 注册到 CanonicalDataRegistry（含口径推断、年份推断、置信度计算）
4. 广播到 SharedMemory `_canonical_registry` 键

generic_agent.py:444-492, 600 的流程（R1/R2/R3 读取点）：
1. analysis/synthesis agent 从 SharedMemory 读取 `_canonical_registry`
2. 注入到 LLM prompt 中："**重要**: 以上数据已经过口径校准和权威性验证"
3. LLM 调用前再检查一次"最后一毫秒"更新

**路径 B（agent 自己写入，无人读取）**：

generic_agent.py:321-352（W3 写入点）在 research agent 搜索后，通过内联正则提取 **5 种**指标：
```python
# generic_agent.py:327-332 — 仅 5 种模式
(r'(?:净利润|归母|扣非)[^\d]*?(\d+\.?\d*)\s*亿元', "净利润"),
(r'(?:(?:营业)?收入|营收)[^\d]*?(\d+\.?\d*)\s*亿元', "营收"),
(r'销量[^\d]*?(\d+\.?\d*)\s*万辆', "销量"),
(r'研发[^\d]*?(\d+\.?\d*)\s*亿元', "研发投入"),
(r'毛利率[^\d]*?(\d+\.?\d*)\s*%', "毛利率"),
```
这些数据通过 `write_canonical()` 写入 `canonical:{metric}` 键，但**从未被读取**——`get_canonical()` / `get_canonical_sync()` 在生产代码中零调用。

**结论**：agent 实际读取的是 engine 通过 MetricExtractor 提取的 12 种指标（路径 A），覆盖面比 agent 内联正则更广（含市占率、增长率等）。但 agent 自己写入的 `canonical:{metric}` 是死数据。

#### 发现 2：规范数据**无法阻止数据矛盾**

SharedMemory 的 `write_canonical()` 有冲突检测（5% 阈值），但：
- 冲突仅**记录**（返回 ConflictRecord），不**解决**
- 冲突通过 MessageBus 发布事件，但**无人订阅处理**
- agent 在 prompt 中看到的规范数据段标注"优先使用这些值"，但 LLM **可以忽略**

#### 发现 3：同步 vs 异步接口混用

- engine.py:1343 用**同步** `self._shared_memory.set()` 写入
- generic_agent.py:444 用**同步** `self._shared_memory.get()` 读取
- generic_agent.py:336 用**异步** `await self._shared_memory.write_canonical()` 写入

混用导致：
- W3（异步 write_canonical）写入 `canonical:{metric}` 键，W2（同步 set）写入 `_canonical_registry` 键——**不同的命名空间，不会互相覆盖**
- agent 读取 `_canonical_registry`（W2 写入），不读取 `canonical:{metric}`（W3 写入）——**agent 自己写入的规范数据是死数据**（`get_canonical()` / `get_canonical_sync()` 在生产代码中零调用）
- 同步 `get()`/`set()` 无锁保护，理论上存在竞态条件，但当前 research agent 在批次内并行执行时都先完成搜索再写入，实际竞态概率较低

#### 发现 4：agent 间主要数据传递不经过 SharedMemory

engine.py:1815-1866 显示，agent 间的数据传递通过 `all_results` 列表：
```python
aggregated_data_points = []  # 从 previous_results 提取
aggregated_sources = []       # 从 previous_results 提取
aggregated_content = []       # 从 previous_results 提取（content[:2000] 截断）
```

**关键问题**：`content[:2000]` 截断意味着每个 agent 只能看到前序 agent 的前 2000 字符分析内容。

---

## 三、DataBus / DataBusV2 详细分析

### 3.1 设计架构

**DataBus**（bus.py:12-155）：
```
DataBus
├── register_provider(name, provider)   # 注册数据源
├── query(source, params) → data        # 查询数据
├── _route_query(source, params)        # 路由到对应 Provider
├── _cache: Dict[str, Dict]             # 内存缓存（TTL 300s）
└── _stats: Dict                        # 统计信息
```

**DataBusV2**（databus.py:388-734）：
```
DataBusV2
├── register_source(config)             # 注册数据源配置
├── query(source, params, ...) → data   # 增强查询
├── MultiLevelCache                     # 内存+磁盘+Redis 缓存
├── 健康检查（定期检查 Provider 可用性）
├── 成本追踪（记录每次查询的成本）
└── 限流控制（防止过载）
```

### 3.2 集成状态

**在整个 `src/` 目录中搜索 DataBus/DataBusV2 的生产代码引用**：

| 搜索模式 | 匹配数（排除定义/测试） |
|---------|:------------:|
| `from src.core.data_providers.bus import` | 0 |
| `from src.core.data_providers.databus import` | 0 |
| `from src.core.data_providers import.*DataBus` | 0 |
| `DataBus.query(` | 0 |
| `DataBusV2.query(` | 0 |
| `create_databus_with_defaults(` | 0（仅测试文件） |

**结论：DataBus/DataBusV2 在任何生产代码路径中都未被实例化或调用。**

### 3.3 根因分析

DataBus 被设计为统一数据查询入口，但实际上：

1. **搜索功能被 Skill 架构替代**：
   - 设计路径：Agent → DataBus → Provider（Akshare/DuckDuckGo/Tavily）
   - 实际路径：Agent → SkillRegistry → search_skill → DuckDuckGo/Tavily
   - DataBus 从未被接入 Skill 调用链

2. **缓存被其他机制覆盖**：
   - DataBus 的缓存设计（多级缓存）→ 被 ResearchResultStore（磁盘持久化）和 SharedMemory（内存）分别替代
   - 无需 DataBus 的缓存层

3. **AkshareDataBusAdapter 已定义但从未实例化**：
   - `src/core/data_providers/sources/akshare_provider.py` 定义了适配器
   - 但从未在 orchestrator/engine/factory 中注册到 DataBus

---

## 四、报告质量问题的根因分析

### 4.1 数据一致性失败的根因链

```
问题：8 个 agent 产出矛盾数据（市占率 90% vs 35%、销量 380/425/460 万、毛利率 19.58% vs 25%）

根因链：
│
├── 原因 1：agent 间数据传递机制不足
│   ├── engine.py 只传递 content[:2000]（前 2000 字符）
│   ├── engine 路径规范数据覆盖 12 种指标（MetricExtractor），但仍有盲区（ROE、资产负债率等）
│   ├── 规范数据为正则匹配提取，无法处理需要计算的复合指标
│   └── LLM 看到 "优先使用规范数据" 指令但可以忽略
│
├── 原因 2：DataBus 未集成 = 无统一数据源
│   ├── 如果 DataBus 被集成，agent 可以 query("byd_sales_2024") 获取权威值
│   ├── 实际上每个 agent 独立从搜索结果中提取数据
│   └── 同一搜索结果被 8 个 agent 不同解读
│
├── 原因 3：SharedMemory 规范数据对 LLM 无强制约束力
│   ├── engine 路径 MetricExtractor 覆盖 12 种指标（含市占率、增长率等），覆盖面尚可
│   ├── 但正则匹配无法处理复合指标（ROE=净利润/净资产）和需要上下文推断的指标
│   ├── MetricExtractor 有口径推断（_infer_caliber），但区分度有限（仅识别 A股/港股/含少数/不含少数）
│   └── 规范数据在 prompt 中仅为"建议优先使用"，LLM 可以忽略并使用搜索结果中的值
│
└── 原因 4：无报告级数据一致性校验
    ├── 聚合时（result_aggregator.py）无数据交叉验证
    ├── 8 个章节独立生成，无合并时的数据冲突检查
    └── SharedMemory 的冲突检测仅记录不解决
```

### 4.2 具体问题定位

| 报告问题 | 根因 | 涉及组件 |
|---------|------|----------|
| 市占率 90% 失实 | LLM 幻觉 + 规范数据约束力不足 | MetricExtractor 有市占率正则但 LLM 可忽略 |
| 销量三处矛盾 | 3 个 agent 独立从不同搜索结果提取 | SharedMemory 有销量指标但 LLM 忽略 |
| 毛利率 19.58% vs 25% | 口径不一致（综合 vs 整车、含税 vs 不含税） | MetricExtractor 有 caliber 推断但区分度有限 |
| AI prompt 泄漏 | agent 输出后处理缺失 | 无 SharedMemory/DataBus 相关 |
| 数据重复率 >75% | 8 个 agent 看到相同 data_points 列表 | engine.py all_results 无去重/分工 |

### 4.3 SharedMemory 规范数据的实际效果

以比亚迪报告为例，SharedMemory 在研究流程中的数据流：

```
阶段 1：8 个 research agent 并行搜索
  ├── 每个 agent 搜索 → 获取 ~531 个 data_points
  ├── 每个 agent 调用 write_canonical() 写入 `canonical:{metric}`（5 种内联正则）
  │   ├── 正则匹配到"营收 8039.65 亿" → SharedMemory["canonical:营收"] = 8039.65
  │   ├── 正则匹配到"净利润 326.19 亿" → SharedMemory["canonical:净利润"] = 326.19
  │   └── 注意：这些 `canonical:*` 数据**从未被读取**（死数据）
  │
  └── 问题：8 个 agent 并行执行，共享同一个 SharedMemory
      ├── 先写入的值可能被后来者覆盖
      └── write_canonical 的冲突检测仅记录不解决

阶段 2：engine 批次完成
  └── engine.py:1343 同步写入 `_canonical_registry`（MetricExtractor 12 种指标，含口径/年份/置信度）
      └── 这是 agent 实际读取的规范数据来源

阶段 3：8 个 analysis agent 并行生成报告
  ├── 每个 agent 从 SharedMemory 读取 `_canonical_registry`（12 种指标）
  ├── 规范数据被注入 prompt："以上数据已经过口径校准"
  ├── 但规范数据仅为"建议优先使用"，LLM 可以忽略
  └── 缺少复合指标（ROE、净利率等需要计算的值不在 12 种正则覆盖中）

阶段 4：聚合
  └── result_aggregator 无数据一致性校验
```

---

## 五、结论

### 5.1 SharedMemory：设计了但不够

| 维度 | 评价 |
|------|------|
| 初始化和传递 | ✅ 完整——单例从 orchestrator 传到所有组件 |
| 规范数据写入 | ✅ 生效——engine + generic_agent 双路径写入 |
| 规范数据读取 | ✅ 生效——3 处 agent prompt 注入 |
| 冲突检测 | ⚠️ 仅记录不解决——ConflictRecord 被忽略 |
| 覆盖范围 | ⚠️ engine 路径 12 种指标（含市占率/增长率等），但无法覆盖复合指标（ROE/净利率等） |
| 对 LLM 的约束力 | ❌ "优先使用"是建议非强制——LLM 可忽略 |
| agent 间主要数据流 | ❌ 不经过 SharedMemory——通过 all_results 列表传递 |

### 5.2 DataBus：设计了但从未集成

| 维度 | 评价 |
|------|------|
| 代码完整度 | ✅ DataBus + DataBusV2 + AkshareAdapter 均已实现 |
| 生产集成 | ❌ 零调用——从未在 orchestrator/engine/factory 中实例化 |
| 替代方案 | Skill 架构 + ResearchResultStore + SharedMemory 组合 |

### 5.3 核心问题

报告数据一致性失败**不是因为 SharedMemory/DataBus 没起作用**，而是：

1. **SharedMemory 起了作用但约束力不足**——engine 路径覆盖 12 种指标（含市占率），但正则无法处理复合指标，且对 LLM 无强制约束力；agent 自己写入的 `canonical:{metric}` 是死数据
2. **DataBus 从未被集成**——如果集成，可提供统一权威数据源查询
3. **缺少报告级数据一致性校验**——聚合时无交叉验证和去重
4. **agent 间信息传递不足**——content[:2000] 截断导致后续 agent 无法充分了解前序结论

---

## 六、改进方向（待讨论）

| # | 方向 | 复杂度 | 效果 |
|---|------|:------:|:----:|
| A | 清理 agent 端死数据（`canonical:{metric}` 写入），扩展 MetricExtractor 支持复合指标（ROE、净利率等） | 低 | 中 |
| B | 聚合阶段增加数据一致性校验（对比各章节的关键数据） | 中 | 高 |
| C | 将 DataBus 集成为 agent 的权威数据查询通道 | 高 | 高 |
| D | 取消 content[:2000] 截断，改用摘要 | 低 | 中 |
| E | 在 prompt 中增加"数据引用规范"强制指令 | 低 | 中 |
| F | 后处理阶段：扫描最终报告，标记数据矛盾 | 中 | 高 |
