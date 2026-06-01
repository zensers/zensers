# Agent 数据采集与分析并行执行分析报告

> 版本: 2.0 (审查修订版)
> 日期: 2026-05-16
> 范围: 全系统 Agent 执行链路

---

## 1. 执行架构概述

### 1.1 架构层级

```
用户输入
    │
    ▼
ResearchOrchestrator.research()                     # orchestrator.py:419
    │
    ├── SmartClarifier                              # 需求澄清
    ├── IntelligentRoutingAdapter                   # 意图分析
    ├── WisdomStore                                 # 推荐 Skills
    ├── TaskDecompositionStrategy.decompose()        # strategies.py:242
    ├── DynamicAgentFactory.create_agents()           # factory.py:112
    │
    ├── ExecutionEngine.execute_with_scheduler()     # engine.py:954
    │   ├── ExecutionScheduler._topological_sort()   # scheduler.py:526
    │   └── batch 循环 (批次间串行)                   # engine.py:1035
    │       └── _execute_agents_batch()              # engine.py:1346
    │           └── _execute_batch()                 # engine.py:1512
    │               ├── dispatch_task()  (asyncio 并行分发) # agent_coordinator.py:207
    │               └── wait_for_completion() (asyncio.gather) # agent_coordinator.py:596
    │
    ├── ResultAggregator
    ├── QualityCheckAgent
    └── DocumentGenerationAgent
```

### 1.2 执行阶段定义

`src/core/decomposition/strategies.py:30-37`

```python
class ResearchPhase(Enum):
    DATA_COLLECTION   = "data_collection"
    DATA_VALIDATION   = "data_validation"
    DEEP_ANALYSIS     = "deep_analysis"
    SYNTHESIS         = "synthesis"
    REPORT_GENERATION = "report_generation"
```

固定执行顺序（拓扑排序决定，见 `scheduler.py:526-574`）：

```
DATA_COLLECTION → DATA_VALIDATION → DEEP_ANALYSIS → SYNTHESIS → REPORT_GENERATION
```

---

## 2. 执行模型

### 2.1 混合模型：批次内并行，批次间串行

```
┌─────────────────────────────────────────────────────────┐
│  批次 (串行)         批次内 (并行)                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  批次1: DATA_COLLECTION ── Agent1 ║ Agent2 ║ Agent3      │
│         (全部完成才进入下一批)                              │
│         ↓                                                │
│  批次2: DATA_VALIDATION ── Agent1 ║ Agent2 ║ Agent3      │
│         ↓                                                │
│  批次3: DEEP_ANALYSIS ──── Agent1 ║ Agent2 ║ Agent3      │
│         ↓                                                │
│  批次4: SYNTHESIS ──────── Agent1 ║ Agent2               │
│         ↓                                                │
│  批次5: REPORT ────────── Agent1                         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 2.2 核心代码链路

| 环节 | 文件:行号 | 机制 | 并行性 |
|---|---|---|---|
| 依赖定义 | `strategies.py:279-345` | `AgentSpec.dependencies = [...]` | 决定依赖关系 |
| 拓扑分批次 | `scheduler.py:526-574` | `_topological_sort(): 入度表 → BFS` | 同批次可并行 |
| 批次循环 | `engine.py:1035` | `for batch_index, batch_agent_ids in enumerate(...)` | 批次间串行 |
| Agent 分发 | `agent_coordinator.py:268` | `asyncio.create_task(self._execute_with_monitoring(...))` | Agent 并行 |
| 等待完成 | `agent_coordinator.py:628-637` | `asyncio.gather(*tasks)` | 并发等待 |
| 数据传递 | `engine.py:1643-1749` | 按依赖过滤 data_points/sources | 按依赖隔离 |

### 2.3 并行矩阵

| 比较维度 | DC Agent 之间 | Analysis Agent 之间 | DC vs Analysis |
|---|---|---|---|
| 执行关系 | **并行** | **并行** | **串行** |
| 依赖关系 | 无依赖 | 依赖 DC 完成 | DC → Analysis |
| 批次关系 | 同批次 | 同批次 | 不同批次 |
| 代码位置 | `engine.py:1035` 同批次 | `engine.py:1035` 同批次 | 拓扑排序决定顺序 |

---

## 3. 性能瓶颈分析

### 3.1 瓶颈 1 (核心): DC Agent 内部多轮搜索完全串行

**文件**: `src/core/agents/generic_agent.py:1036-1297` (`_do_deep_research`)

**执行逻辑** (三层串行嵌套):

```python
# 层级1: while 循环 (line 1169) — 多轮迭代，串行
while True:
    iteration += 1
    queries_to_execute = pending_queries[:3]

    # 层级2: for 循环 (line 1192) — 每轮3个查询，串行
    for query in queries_to_execute:
        # 层级3: await (line 1214) — 单次搜索调用
        search_result = await asyncio.wait_for(
            search_skill.execute(query=query, ...), timeout=60.0
        )

        # 层级4: 爬取 (line 1248) — 同查询串行
        enriched = await self._enrich_results_with_content(
            search_result["results"][:10], web_scraper, query,
        )

    # 质量评估 → 不达标则继续 while 循环
```

**单 Agent 执行时间线**:

```
时间 →
query_1: [───搜索 5s───][───爬取 10个URL 10s───]
query_2:                                               [───搜索 5s───][───爬取 10s───]
query_3:                                                                              [───搜索 5s───][───爬取 10s───]
  → 质量评估 → 不达标 → 生成补充查询
query_4:                                                                                              [───搜索 5s───]...
```

**关键事实**: 相邻两个 `await search_skill.execute()` 之间无任何并发。即使 `asyncio.wait_for` 不阻塞事件循环，但 `for` 循环本身是同步的——直到前一个 `await` 返回后才进入下一个迭代。

**爬取阶段 (`_enrich_results_with_content`, `generic_agent.py:1248`)** 同样串行：

```python
# 爬取 URL 时也逐个 await
enriched_results = []
for item in results[:10]:
    content = await web_scraper.execute(url=item["href"])
    ...
```

**影响**: 5 个维度的 DC Agent 在同一批次并行，但每个 Agent 内部 10-50 次搜索完全串行。**批次总耗时 = 最慢的那个 Agent 内部所有搜索耗时之和**。

### 3.2 瓶颈 2: Analysis 等待全部 DC Agent 完成才能启动

由于拓扑排序的批次隔离，即使某个维度的 DC Agent 提前完成，其对应的 Analysis Agent 也必须等待所有其他维度的 DC Agent 完成才能开始。

```
DC_市场规模 ──────────────┐ (5s 完成，等待中)
DC_竞争格局 ──────────────────────┐ (8s 完成，等待中)
DC_政策环境 ──────────────────────────────┐ (15s 完成，等待中)
DC_技术趋势 ────────────────────────────────────┐ (20s 完成)
                                                    ↓
                                           Analysis 批次开始
```

最慢的 DC Agent 决定了 Analysis 开始时间。

### 3.3 瓶颈 3: `_supplementary_search_for_gaps()` 绕过设计约束

`generic_agent.py:343-367` — Analysis Agent 内部调用 `_supplementary_search_for_gaps()`，直接从 `skill_registry` 获取搜索能力（绕过 `available_skills` 过滤）。详见第 6 节。

---

## 4. 资源约束分析

### 4.1 搜索引擎 API 速率限制

| 场景 | N 维度 × M 查询 × QPS | 风险 |
|---|---|---|
| 当前 (串行) | N=5, M=30, QPS=1 | 安全，单 Agent 约 0.3 QPS |
| 6.0 方案 (查询并行) | N=5, M=10轮, Semaphore=3 | 峰值 15 QPS |
| 无限制并行 | N=5 × M=3 = 15 并发 | **高风险** |

**典型搜索引擎限制**:
| 引擎 | 免费层 QPS | 超过表现 |
|---|---|---|
| Google Custom Search | 10 QPS | HTTP 429 |
| Bing Search | 3 QPS | 降级/限流 |
| DuckDuckGo | 无官方限制 | 可能被临时封禁 |
| 百度搜索 | 5 QPS | HTTP 429 |

### 4.2 内存压力预估

```
单轮搜索返回: ~50KB (JSON + snippet)
单 URL 爬取: ~500KB (完整 HTML → Markdown)
每轮 (3查询 × 10URL 爬取): ~15MB
整个 DC Agent (30查询): ~150MB
N=5 个并行 DC Agent: ~750MB 峰值
追加 ANALYSIS Agent + 爬取补充: ~1.2GB 峰值
```

**风险**: 在低内存环境 (<4GB) 下，`N=5 × 30查询 × 10URL` 可能导致 OOM。

### 4.3 成本影响

| 维度 | 串行 | 并行 |
|---|---|---|
| 总 API 调用次数 | 不变 | 不变 |
| 时间窗口 | 拉长 (7.5min) | 缩短 (2.5min) |
| 峰值 QPS | 低 | 高 |
| 阶梯定价影响 | 无 | 可能触发高频阶梯 |

并行化不改变 API 调用总数，但缩短时间窗口可能触发 API 提供商的速率阶梯定价或短时间配额限制。

---

## 5. 优化方案

### 5.1 方案 P0: DC Agent 内部查询并行化 (最高优先级)

**目标**: 消除第 3.1 节的核心瓶颈。

**改动范围**: `generic_agent.py:1192-1267`

```python
# ── 当前实现 (串行) ──
for query in queries_to_execute:
    search_result = await asyncio.wait_for(
        search_skill.execute(query=query, ...), timeout=60.0
    )
    if web_scraper:
        enriched = await self._enrich_results_with_content(...)

# ── 优化实现 (并行 + 信号量控制) ──
semaphore = asyncio.Semaphore(3)  # 搜索引擎并发上限

async def _search_single(query: str) -> Optional[Dict]:
    async with semaphore:
        try:
            result = await asyncio.wait_for(
                search_skill.execute(query=query, ...), timeout=60.0
            )
            if result.get("success") and web_scraper:
                urls = [item["href"] for item in result.get("results", [])[:10]
                        if item.get("href")]
                scrape_tasks = [
                    asyncio.wait_for(web_scraper.execute(url=u), timeout=30.0)
                    for u in urls
                ]
                scraped = await asyncio.gather(*scrape_tasks, return_exceptions=True)
                # 合并 scraped 内容到 result
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Search timeout: {query}")
            return None
        except Exception as e:
            logger.warning(f"Search failed: {query}: {e}")
            return None

# 并行执行当轮所有查询
tasks = [_search_single(q) for q in queries_to_execute]
done, pending = await asyncio.wait(tasks, timeout=120.0)  # 全局超时
for t in pending:
    t.cancel()  # 超时的任务不阻塞整体
for t in done:
    result = t.result()
    if result:
        all_results["searches"].append(result)
```

**设计要点**:
| 要素 | 机制 | 目的 |
|---|---|---|
| 并发控制 | `Semaphore(3)` | 遵守搜索引擎 QPS 限制 |
| 超时隔离 | 单查询 `timeout=60s` + 整体 `timeout=120s` | 不因一个慢查询拖垮整批 |
| 错误隔离 | `return_exceptions=True` + try/except | 单个查询失败不影响其他查询 |
| 爬取并行 | `asyncio.gather(*scrape_tasks)` | 消除同轮爬取的串行 |

**预期加速**:
| 指标 | 当前 | 优化后 |
|---|---|---|
| 每轮 (3 查询+爬取) | ~45s | ~15s |
| 总耗时 (30 查询, 10 轮) | ~450s | ~150s |
| **加速比** | **1x** | **~3x** |

**回滚策略**:
- 代码级：`asyncio.Semaphore(1)` = 退化为串行，通过配置开关控制
- 配置项：`search_parallelism: int = 3`，设为 1 即完全恢复当前行为

### 5.2 方案 P1: 细粒度依赖调度

**目标**: 消除第 3.2 节瓶颈——某个维度 DC 完成后立即启动对应 Analysis。

**当前**: Analysis Agent 依赖 **全部** DC Agent 完成
**优化**: Analysis Agent 只依赖 **对应维度** 的 DC Agent

**改动点**: `strategies.py:325-345`

```python
# 当前: 所有 Analysis Agent 等待所有 Validation Agent
spec = AgentSpec(dependencies=[validation_agent_id])  # 已有细粒度依赖

# 但本应通过拓扑排序产生更细的批次
# 然而当前 _topological_sort 只检查直接依赖，实际上如果每个 Analysis
# 只依赖对应的 Validation，它们应该可以和 Validation 同批次
```

**注**: 当前依赖定义已经是细粒度（每个 Analysis 只依赖对应的 Validation Agent）。但因为 `scheduler.py` 的 `schedule_from_decomposition` 使用的是按 `ResearchPhase` 分组的执行顺序（`strategies.py:147-154` 的 `PHASE_ORDER`），所以批次还是按阶段排列。如果要实现"DC 完成一个就启动一个 Analysis"，需要修改调度器的批次生成逻辑。

**影响**:
- 改动范围：调度器 + 分解策略
- 复杂度：中
- 风险：依赖计算更复杂，可能出现循环依赖

### 5.3 方案 P2: 流式处理管道

**目标**: 使用 `asyncio.Queue` 构建生产者-消费者管道。

```python
data_queue = asyncio.Queue()

# DC Agent 产出数据放入队列
async def producer():
    for query in queries:
        data = await search(query)
        await data_queue.put(data)

# Analysis Agent 从队列消费，不必等待全部 DC 完成
async def consumer():
    while True:
        data = await data_queue.get()
        if data is None:
            break
        result = await analyze(data)
```

**评估**: 低成本方案（查询并行化）已能带来 3x 加速，流式管道额外收益有限但复杂度高。当前不值得实施。

---

## 6. 架构违规: DEEP_ANALYSIS 阶段隐式搜索

### 6.1 问题描述

**文件**: `src/core/agents/generic_agent.py:343-367`

尽管 ASPECT_SKILL_MAP (`strategies.py:41-66`) 中 DEEP_ANALYSIS Agent 的 `available_skills` **不包含** `search_skill`，实际执行时 Analysis Agent 仍会搜索：

```python
# generic_agent.py:343-348 — DEEP_ANALYSIS 路径
gaps = self._detect_knowledge_gaps(result["content"])
if gaps:
    supp_result = await self._supplementary_search_for_gaps(
        topic=topic, aspect=aspect, gaps=gaps, skill_registry=skill_registry,
    )
```

`_supplementary_search_for_gaps()` (`generic_agent.py:1727-1817`) **绕过 `available_skills`**：

```python
# 直接从 skill_registry 获取，不检查 available_skills
search_skill = (
    skill_registry.get("web_search") or
    skill_registry.get("search_skill")
)
```

### 6.2 严重性

| 维度 | 影响 |
|---|---|
| 架构完整性 | **设计违规**。"数据采集由 DATA_COLLECTION 独占处理"的约束形同虚设 |
| DC 阶段价值 | 如果所有 Analysis Agent 都会自行补充搜索，DC 阶段的存在意义被削弱 |
| 行为不可见 | 隐式搜索无日志区分，运维难以识别 |
| 性能分析污染 | 分析阶段的耗时包含了搜索耗时，导致性能评估失真 |

### 6.3 修复方案

选项 A (推荐——使行为可见):

```python
# 在 strategies.py ASPECT_SKILL_MAP 中正式添加搜索能力
ASPECT_SKILL_MAP = {
    "Market Size": ["llm_skill", "data_analysis", "lc_python_repl"],
    # ... 不变
}
# 同时将 _supplementary_search_for_gaps 改为显式调用，
# 并在 DEEP_ANALYSIS 阶段正式注册 search_skill
```

选项 B (严格——禁用违规搜索):

```python
async def _supplementary_search_for_gaps(self, ...):
    if "search_skill" not in self._available_skills and \
       "web_search" not in self._available_skills:
        logger.info(f"Agent {self.agent_id}: search not authorized, skipping gap fill")
        return {}
    # ... 原逻辑
```

**优先级**: P0 (架构违规必须先修复)

---

## 7. 实施优先级

### 7.1 优先级总表

| 排名 | 方案 | 优先级 | 预估工作量 | 预期加速 | 风险 |
|---|---|---|---|---|---|
| 1 | **P0: DC 内部查询并行化** | P0 | 1-2 人日 | ~3x | 低 (可降级回串行) |
| 2 | **P0: 隐式搜索修复 (选项A)** | P0 | 0.5 人日 | — | 低 (仅做配置变更) |
| 3 | P1: DC 内部爬取并行化 | P1 | 0.5 人日 | 额外 ~1.5x | 低 |
| 4 | P2: 细粒度依赖调度 | P2 | 3-5 人日 | ~1.5-2x | 中 |
| 5 | P3: 流式处理管道 | P3 | 5-10 人日 | 边际 | 高 |

### 7.2 灰度与回滚策略

| 方案 | 灰度步骤 | 回滚方式 |
|---|---|---|
| P0 (查询并行) | 1. 配置 `search_parallelism: int = 1` (`Semaphore(1)` = 串行)<br>2. 逐步提升到 2 → 3 | 设为 1 即恢复 |
| P1 (爬取并行) | 1. 添加 `scrape_parallelism: int = 1`<br>2. 逐步提升 | 设为 1 即恢复 |
| P2 (细粒度调度) | 1. 新调度器与旧调度器并存<br>2. 10% 流量切到新调度器 | 回退到旧调度器 |

---

## 8. 验收标准

优化效果应基于**实际 Profiling 数据**验证，而非估算。

### 8.1 必须收集的基线数据 (实施前)

```
执行一次 python -m cProfile 或使用 asyncio 事件循环耗时统计:
- DC Agent 总耗时 (P50 / P95 / P99)
- DC Agent 内部: 搜索耗时 / 爬取耗时 / LLM 扩展耗时
- Analysis Agent 等待 DC 完成的空闲时间
- 内存峰值 (process.memory_info().rss)
- 搜索引擎 API 调用次数
```

### 8.2 验证指标

| 指标 | 当前基线 | 目标 | 测量方法 |
|---|---|---|---|
| 同输入下 P50 耗时 | [待测量] | 降低 50%+ | `asyncio` 事件循环耗时 |
| 同输入下 P95 耗时 | [待测量] | 降低 60%+ | `asyncio` 事件循环耗时 |
| API 调用成功率 | [待测量] | 无降级 | HTTP 429 计数 |
| 内存峰值 | [待测量] | 不高于当前 1.5x | `tracemalloc` |
| 输出质量 | [待测量] | 不变或提升 | 同输入下内容对比 |

---

## 9. 关键文件索引 (仅正文引用)

| 文件 | 行数 | 职责 | 正文引用 |
|---|---|---|---|
| `src/core/orchestrator/execution/engine.py` | 2083 | 执行引擎: 批次调度、Agent 分类、质量控制 | §2.2, §5.2 |
| `src/core/orchestrator/execution/scheduler.py` | 540 | 拓扑排序、批次生成、依赖转换 | §2.2, §5.2 |
| `src/core/orchestrator/execution/coordinator/agent_coordinator.py` | 815 | 任务分发、异步并行执行 | §2.2 |
| `src/core/agents/generic_agent.py` | 3718 | 动态 Agent 实现、Skill 路由、搜索执行 | §3.1, §6.1 |
| `src/core/decomposition/strategies.py` | 773 | 研究类型分解策略、依赖定义、Skill 映射 | §1.2, §2.2, §5.2 |
| `src/core/orchestrator/orchestrator.py` | 4137 | 主编排器 | §1.1 |
| `src/core/parallel.py` | 360 | 线程/进程池并行基础设施 | §2.2 (背景) |

---

*文档结束 — 第 8.1 节的基线数据待实施前补充*
