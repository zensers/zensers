# 知识管理与 Agent 专业水平深度分析及系统化提升方案

**版本**: 2.0
**日期**: 2026-06-03
**分析范围**: 评分体系 / 知识管理 / Agent 架构

---

## 第一章：执行摘要

### 1.1 问题陈述

Zensers 系统当前章节评分集中在 **40-60 分区间**，距目标 **80-100 分**存在显著差距。经过对 **74 个源文件、3 层评分体系、2 条 Agent 执行链路、12 个专业 Agent Prompt、11 个知识管理组件** 的深度审计，结论如下：

**核心矛盾**：形式化检查 ≠ 专业质量评估。当前系统能够检测"文章是否包含关键词"，但无法判断"分析是否具有专业深度"。

### 1.2 三大根因

| 根因 | 贡献度 | 核心证据 |
|------|--------|----------|
| **评分体系是形式检查而非语义评估** | 40% | 7 个关键词判定章节结构，3 个正则判定量化分解，binary 判定反证 |
| **知识库存储实体但不存储方法论** | 35% | RapidEvolver 仅 10 个硬编码领域，知识搜索主流程走 SQL LIKE（FTS5 已实现但未接入），向量检索已实现但未接入主流程，无分析框架知识 |
| **Agent 执行无自我评估与迭代** | 25% | 无评分标准注入，无优秀示例参考，无自评步骤，Valuation/Investment 仅 29 行 |

### 1.3 提升路径

```
当前评分 40-60
    │
    ├─ Phase 1: 方法论知识库建设 ──→ 评分 65-75
    │    (Agent 获得分析框架与写作标准知识)
    │
    ├─ Phase 2: 三层语义评分体系 ──→ 评分 75-85
    │    (形式检查 + 方法评估 + 深度评估)
    │
    └─ Phase 3: Agent 自评与迭代机制 ──→ 评分 85-95
         (自评 → 修订 → 反馈循环)
```

---

## 第二章：评分体系的深度诊断

### 2.1 评分架构全景

系统存在 **两条独立评分管线**，最终融合为一个分数：

```
管线 A: 编排器阶段检查器 (src/core/orchestrator/execution/engine.py)
  └─ DataCollectionQualityChecker → AnalysisQualityChecker → ReportQualityChecker
     (每阶段执行，阈值 70/70/80，最多重试 3 次)

管线 B: QualityCheckAgent 终检 (src/agents/fixed_agents/quality_check_agent.py)
  └─ 4 项全局检查 + check_by_sections 分章节检查
     (报告生成后执行，阈值 60)

最终融合: quality_score * 0.6 + section_overall * 0.4
  来源: quality_check_agent.py:173
```

### 2.2 评分指标逐项审计

#### 2.2.1 DataCollectionQualityChecker (`checkers.py:218-345`)

**公式**: `volume * 0.3 + quality_metadata.score * 0.4 + source_score * 0.3`

| 子维度 | 权重 | 计分逻辑 | 代码位置 | 评分局限 |
|--------|------|----------|----------|----------|
| 数据量 | 30% | 5 档量化：≥100→100, ≥50→80, ≥20→60, ≥10→40, ≥5→20, else→10 | `checkers.py:271-286` | 粗粒度分桶，99 条和 50 条同分(80)，纯计数不衡量相关性 |
| 质量分 | 40% | 直接读取 `quality_metadata.quality_score`，默认 50.0 | `checkers.py:261` | MetadataExtractor 默认值为 50，且从不低于此值，导致锚定偏低 |
| 来源可信度 | 30% | `80 * authoritative_ratio + 30 * (1 - ratio)` | `checkers.py:288-309` | 权威性仅通过 10 个关键词判断(gov/政府/official/官方/report/报告/statistics/统计局/association/协会)，权威来源比例再高也封顶 80 分 |

**典型得分演算**:
- 数据量 30 条 → 60分 × 30% = 18
- metadata 默认 50 分 × 40% = 20
- 3/10 来源含"官方" → ratio=0.3 → 80×0.3+30×0.7=45 × 30% = 13.5
- **总分 ≈ 51.5** → 落在 40-60 区间

#### 2.2.2 AnalysisQualityChecker (`checkers.py:347-436`)

**公式**: `structure * 0.40 + caliber * 0.30 + counter * 0.20 + quant * 0.10`

| 子维度 | 权重 | 计分逻辑 | 代码位置 | 评分局限 |
|--------|------|----------|----------|----------|
| 结构完整性 | 40% | 检查 5 段式框架关键词存在性 | `checkers.py:386-392` | **关键词游戏**：出现"如果"即表示"反证"满分，出现"贡献"即表示"因果分解"满分 |
| 数据口径覆盖率 | 30% | `caliber_refs / (nums * 0.3) * 100` | `checkers.py:394-401` | **空文本得满分**：nums=0 → return 100.0。口径仅检查 3 个正则，且第一个正则 `[A股|港股|美股|GAAP|IFRS]口径` 使用字符类`[...]`而非交替组`(?:...)`，存在匹配错误 |
| 反证完整性 | 20% | **Binary：0 或 100** | `checkers.py:403-408` | 全文任意位置出现"如果"→满分，缺失→0分。这是全系统最脆弱的子维度 |
| 量化分解率 | 10% | **Binary：0 或 100**，检查 3 个正则 | `checkers.py:410-416` | 仅匹配"贡献"、"分解为"、"个百分点源于"3 个模式，如用"driven by"等英文则漏检 |

**诊断**: 所有子维度都可以**通过插入关键词来作弊**。一篇包含"核心判断...数据来源...如果...贡献...意味着"的文本可获得 80+ 分，无论实际分析质量如何。

#### 2.2.3 LLMJudgeChecker (`llm_judge.py:18-132`)

**设计**: 作为语义评估的补充，权重 30%，规则检查器 70%

**关键缺陷**:

```python
# llm_judge.py:39-46 — 失败时的高分回退
except Exception:
    return 75.0  # 异常时回退 75
if not parsed:
    return 90.0  # JSON解析失败回退 90
```

**回退 90 分的逻辑注释**(`llm_judge.py:43-45`):
```python
# CompositeChecker threshold=70, weight=0.3
# Guarantee: even if LLM judge returns 0, rule @ 0.7 gives 49 → still < 70 threshold
# So we need analysis >= 61.4 → fallback 90 gives analysis >= 61.4 needed
```

这暴露了一个系统性问题：**为了确保通过阈值，设计了错误的回退机制**——失败应该扣分，而不是加分。

**其他缺陷**:
- 内容截断至 4000 字符(`llm_judge.py:65`)，长报告后半段不参与评估
- 使用 `settings.llm.cheap_model`（弱模型，`llm_judge.py:75`）
- JSON 解析使用原始 `{...}` 查找（`llm_judge.py:109-122`），LLM 输出若用 markdown 包裹则解析失败
- `counter_score` prompt 将"明确的边界条件"与"模板化短语"混为一谈，这是两个截然相反的信号

#### 2.2.4 ReportQualityChecker (`checkers.py:438-893`)

**公式**: `completeness*10% + consistency*35% + redundancy*20% + provenance*35% + framework_bonus(0-10)`

| 子维度 | 权重 | 计分逻辑 | 代码位置 | 关键局限 |
|--------|------|----------|----------|----------|
| 完整性 | 10% | 10+章节→100, 7+→80, 5+→60, 3+→40 | `checkers.py:539-549` | 纯数量检查，10 个空章节得满分 |
| 跨章一致性 | 35% | 10 种指标正则提取，>5%差异即矛盾 | `checkers.py:564-637` | **少于 2 个章节自动 100 分**(`:583-584`)，**未发现指标自动 100 分**(`:615-616`)，5%容差对市场研究来说过紧(不同来源 10-20%浮动正常) |
| 数据冗余 | 20% | 去重后冗余比例 | `checkers.py:643-692` | "10"和"10.0"因字符串哈希不一致被视为不同数据，未标记章节默认计入研究章节 |
| 发现溯源性 | 35% | 合成章节引用研究发现的词语重叠率 | `checkers.py:696-749` | **无发现数据时回退 80 分**(`:709-711`)，中文 claim 因空格分词无法正确分割(如"核心判断市场增长"被当做一个 token) |
| 框架合规性 | + 0-10 | 角色描述关键词在章节内容中出现比例×10 | `checkers.py:783-821` | 最大仅 10 分加分，在 0-100 量表中影响可忽略 |

#### 2.2.5 QualityCheckAgent 内部评分 (`quality_check_agent.py`)

**全局评分** (`:549-576`):

```python
base_score = 100.0
issue_penalty = min(total_issues * 5, 50)   # 每个问题统一扣 5 分
pass_rate = passed_count / total_checks     # 4 项检查通过率
score = base_score * pass_rate - issue_penalty  # 乘法后减法，数学上异常
```

**缺陷**: 10 个 typo(每个扣 5 分) = 50 分封顶，和 10 个数据幻觉(也应扣 50 分)惩罚相同。**全局评分严重性不区分**（注：章节评分 `:819` 已区分 high:15/medium:5/low:1，但全局评分未区分）。

**章节评分** (`:803-823`):

```python
structure_keywords = ["核心判断", "逻辑推导", "数据支持", "反证", "边界条件", "意义", "影响"]
found = sum(1 for kw in structure_keywords if kw in content)
```

**缺陷**: 7 个硬编码中文关键词决定"分析框架"得分。不评估分析深度、逻辑完整性、数据质量、洞察力。

**分数融合** (`:173`):

```python
quality_score = quality_score * 0.6 + section_overall * 0.4
```

两个 40-60 分的值融合后仍在 40-60 区间。**无校准依据的 60/40 加权**。

### 2.3 核心诊断总结

```
评分 40-60 的根本原因：
┌──────────────────────────────────────────────────────────────┐
│ 1. 关键词存在性 ≠ 分析质量（所有子维度的共同缺陷）            │
│ 2. 失败时的高分回退扭曲了评分分布（LLM Judge 回退 90）        │
│ 3. 严重性不区分：数据幻觉和错别字惩罚相同（统一扣 5 分）       │
│ 4. 纯数量指标：10 个空章节 = 完整性满分                       │
│ 5. 无外部基准验证：不核对"数据是否正确"，只核对"章节间是否一致" │
│ 6. 语义评估缺位：唯一的 LLM Judge 被脆弱的 JSON 解析和        │
│    高分回退机制所破坏                                          │
└──────────────────────────────────────────────────────────────┘
```

---

## 第三章：知识管理模块的深度诊断

### 3.1 架构概览

```
三层记忆架构（src/core/memory/）:
  Layer 1: CoreMemory (<10KB, JSON 文件)
     ├─ UserProfile
     ├─ TopEntity (max 20, 按 mention_count 排序)
     ├─ CoreNeed (max 10, 按 frequency 排序)
     ├─ LearnedPattern (max 15, 按 recurrence_count 排序)
     └─ ExpertiseProfile

  Layer 2: KnowledgeBank (SQLite, 11 个数据库文件)
     ├─ EntityStore / RelationStore / DataPointStore / InsightStore
     ├─ TemporalKnowledge（时间序列）
     ├─ ProvenanceStore（来源追溯）
     ├─ ContradictionDetector（矛盾检测）
     ├─ LearningStore / ErrorTracker（学习模块）
     └─ research_history（研究历史）

  Layer 3: File Storage
     ├─ data/knowledge/concepts/
     ├─ data/knowledge/entities/
     └─ data/knowledge/relations/
```

### 3.2 存储层缺陷

#### 3.2.1 知识搜索：主流程走 SQL LIKE，FTS5 已实现但未接入

**代码**: `entity_store.py:321-377`（注意：`search_entities` 已标记 `@deprecated(replacement="list() with filters")`，但仍被 `knowledge_bank.py:303` 的 `search_all()` 调用）, `relation_store.py:195-?`, `data_point_store.py:190-?`

系统实际上存在三层检索基础设施，但处于不同状态：

| 模块 | 文件 | 行数 | 状态 |
|------|------|------|------|
| **FTS5 全文索引** | `src/core/memory/fts/__init__.py` | 675 | ✅ 已实现，可用，但**未接入主搜索流程** |
| **向量存储** | `src/core/memory/retrieval/vector_store.py` | 457 | ⚠️ 已实现但**未接入主流程**（`__init__.py:40` 注释掉公开导出，但 `retrieval/__init__.py` 仍正常导出，配置中仍有 `embedding_model`） |
| **语义搜索** | `src/core/memory/retrieval/semantic_search.py` | 241 | ⚠️ 已实现但**未接入主流程**（含 6 组硬编码同义词+4 组缩写，仅限新能源领域，需 Embedder 依赖） |
| **混合搜索** | `src/core/memory/retrieval/hybrid_search.py` | 412 | ⚠️ 已实现但**未接入主流程**（组合向量+语义+关键词，依赖前两者） |

**当前主搜索路径**（实际执行的代码）：

```python
# entity_store.py:321-377 — 主流程唯一搜索机制
def search_entities(self, query: str, limit: int = 100) -> List[Dict]:
    cursor = self.db.execute(
        f"SELECT * FROM entities WHERE name LIKE ? OR description LIKE ? LIMIT ?",
        (f"%{query}%", f"%{query}%", limit)
    )
```

**FTS5 已实现但未接线**：

```python
# fts/__init__.py:318-672 — FTSSearcher 已完整实现
# 包含：entities/relations/data_points/insights 四类 FTS5 索引
# 包含：前缀搜索、短语搜索、LIKE 回退
# 包含：自动触发器同步（insert/update/delete → FTS 索引更新）
# 但 EntityStore.search_entities() 未调用 FTSSearcher，直接走 SQL LIKE
```

**向量检索已实现但未接入主流程**：

```python
# src/core/memory/__init__.py:40 — 注释掉的公开导出
# from .retrieval import VectorStore, SemanticSearch, HybridSearch

# 但 retrieval/__init__.py 仍正常导出这些类
# settings.yaml 仍配置 embedding_model: "text-embedding-3-small"

# 现状：代码完整，配置保留，但主搜索流程从未调用
# 原因：向量检索需要 Embedder 依赖，且主流程已走 SQL LIKE
# 遗留代码在 retrieval/ 目录下，是否清理需根据后续需求决定
```

**影响**:
- 搜索 "EV" 不会匹配 "electric vehicle"（FTS5 也无法解决，需同义词扩展）
- 搜索 "profitability" 不会匹配 "ROE", "Net Margin", "ROA"
- **FTS5 基础设施已就绪，接入成本极低，但当前未接入导致搜索能力被浪费**
- 向量检索已实现但未接入主流程，Phase 4 需评估是否重新启用或清理

#### 3.2.2 实体提取：硬编码正则，非 LLM/NLP

系统存在两个实体提取器，均基于硬编码正则：

**RapidEvolver** (`rapid_evolver.py`): 编排器路由阶段使用

领域关键词: **仅 10 个领域，全部是中国制造业/投资**:
```python
DOMAIN_KEYWORDS = {
    "新能源汽车": ["新能源", "电动", "电池", "充电", "续航", "动力电池", "BEV", "PHEV", ...],
    "动力电池": ["锂电池", "磷酸铁锂", "三元锂", "刀片电池", ...],
    "储能": ["储能", "ESS", "电池储能", ...],
    "光伏": ["光伏", "太阳能", "硅片", ...],
    "上游材料": ["锂矿", "锂盐", "碳酸锂", ...],
    "半导体": ["芯片", "半导体", "晶圆", ...],
    "人工智能": ["AI", "人工智能", "机器学习", ...],
    "金融投资": ["市值", "估值", "PE", "PB", ...],
    "汽车": ["汽车", "车企", "整车", ...],
    "医药": ["医药", "创新药", "仿制药", ...],
}
```

硬编码实体: **13 家公司 + 7 个人 + 4 个产品**（含中英文混合）:
```python
entity_patterns = {
    "company": [
        r'([\u4e00-\u9fa5]{2,8})(?:公司|集团|有限|股份)',  # 通用中文公司模式
        r'(宁德时代|比亚迪|特斯拉|蔚来|小鹏|理想|长城|吉利|华为|小米|百度|阿里|腾讯)',  # 13家硬编码
    ],
    "product": [
        r'(Model\s*[3YXS])',
        r'(刀片电池|麒麟电池|神行电池|金砖电池)',
    ],
    "person": [r'(马斯克|王传福|李斌|何小鹏|李想|雷军|任正非)'],
}
```

**EntityExtractor** (`extraction/entity_extractor.py`, 400 行): 知识编译/导入阶段使用

比 RapidEvolver 更完善，但仍是纯正则：
- 支持 5 种实体类型（company/person/product/metric/time）
- 有中英文双语模式（中文公司后缀 + 英文 Inc/Corp/Ltd）
- 有别名映射（CATL→宁德时代, BYD→比亚迪, Tesla→特斯拉）
- 有置信度计算
- **但无法识别不在硬编码列表中的实体**

**KnowledgeExtractor** (`extraction/knowledge_extractor.py`, 155 行): 研究结果自动提取

同样基于硬编码正则，且领域覆盖更窄。

**影响**: 研究 "European MedTech SaaS Market" → 0 个实体、0 个领域、0 个术语。**知识管理系统对中国制造业之外的行业基本失效**。

#### 3.2.3 术语提取：8 个硬编码定义

```python
# rapid_evolver.py:270-278
term_definitions = {
    "LFP": "磷酸铁锂电池正极材料",
    "NCM": "三元锂电池正极材料（镍钴锰）",
    "CTP": "Cell to Pack，无模组电池包技术",
    "CTC": "Cell to Chassis，电池底盘一体化技术",
    "CTB": "Cell to Body，电池车身一体化技术",
    "刀片电池": "比亚迪LFP电池产品",
    "麒麟电池": "宁德时代第三代CTP电池产品",
    "固态电池": "使用固态电解质的锂电池",
}
```

其他术语通过 `[A-Z]{2,}` 或 `[\u4e00-\u9fa5]{2,6}(技术|工艺|材料|系统)` 提取，**上下文切片作为"定义"** (`:287-297`):
```python
context = text[max(0, pos-20):min(len(content), pos+len(match)+50)]
terminology[match] = context.strip()  # 原始文本片段，不是真正的定义
```

#### 3.2.4 知识编译器：生产死文档

**代码**: `compiler.py:230-603`

编译器将研究内容编译为 Markdown 页面写入 `data/knowledge/`，但：
- **定义提取是破碎的** (`:349-383`)：获取概念名称后的文本作为定义，如概念在句尾则定义为空
- **页面合并是破坏性的** (`:605-627`)：`_merge_pages()` 丢弃旧内容仅保留旧的反向链接
- **"相关数据"从未填充** (`:457`)：硬编码为 `(待补充)`
- **反向链接双向不一致** (`:722-753`)：A→B 关系编译后，A 更新时 B 的反向链接可能过期

#### 3.2.5 CoreMemory：简单计数驱动的晋升机制

**晋升条件** (`core_memory.py`):
```python
ENTITY_PROMOTION_THRESHOLD = 5   # mention_count >= 5
NEED_PROMOTION_THRESHOLD = 3     # frequency >= 3
PATTERN_PROMOTION_THRESHOLD = 3  # recurrence_count >= 3
```

**缺陷**:
- **纯计数，无时间衰减**：100 次研究中提到 5 次与 1 次研究中提到 5 次权重相同
- **溢出时直接截断** (`:246`)：`top_entities = top_entities[:20]`，不是基于重要性的淘汰
- **10KB 限制未强制执行** (`:578-582`)：超过时仅 warn，不触发缩减
- **无 LRU/时间因子**：旧数据和新数据权重相同

#### 3.2.6 编排器中的知识集成

**路由阶段** (`orchestrator.py:5065-5085`):
```python
search_results = knowledge_manager.search(requirement.topic)
if len(search_results) > 5:
    routing_hints["reduce_background"] = True  # 6 个结果 = 知识丰富
else:
    routing_hints["reduce_background"] = False # 5 个结果 = 知识浅薄
```
**缺陷**: `>5` 的二元路由决策过于粗糙。5 个 vs 6 个结果之间没有本质区别，但决策完全不同。

**存入阶段** (`orchestrator.py:5089-5119`):
- 模式提取使用 **15 个硬编码中文关键词** (`:5150-5153`)：趋势、规律、关键、通常、往往、风险、机会、导致、取决于、驱动、意味着、表明、显著、持续、加速
- **英文研究中不提取任何模式**

### 3.3 知识管理诊断总结

```
根本问题：
┌──────────────────────────────────────────────────────────────┐
│ 1. 无分析框架知识：知识库里只有实体/关系/数据点，没有        │
│    "怎么写好行业分析"的方法论                                 │
│ 2. 检索能力被浪费：FTS5 全文索引已实现(675行)但未接入主      │
│    搜索流程，当前仍走 SQL LIKE；向量检索已实现(1110行)但      │
│    未接入主流程（retrieval/ 下代码完整，配置保留，需评估      │
│    是否重新启用或清理）                                        │
│ 3. 领域覆盖极端有限：10 个中国制造业领域，无西方/服务/科技   │
│ 4. 硬编码实体识别：3个提取器(RapidEvolver/EntityExtractor/    │
│    KnowledgeExtractor)均为纯正则，无法识别不在硬编码列表中的实体│
│    置信度计算，但无法识别不在硬编码列表中的实体               │
│ 5. 结构化的知识未被用于提升分析质量：存入后即遗忘            │
│ 6. 跨会话记忆缺失：每次研究从零开始，不引用已有知识          │
└──────────────────────────────────────────────────────────────┘
```

---

## 第四章：Agent 架构的深度诊断

### 4.1 Agent 团队结构

```
固定 Agent 团队 (src/agents/fixed_agents/)       动态 Agent 工厂 (src/core/agents/)
  ├─ requirement_analysis_agent.py                  ├─ factory.py
  ├─ data_collection_agent.py                       ├─ generic_agent.py
  ├─ report_generation_agent.py                     └─ agent_session.py
  ├─ document_generation_agent.py
  ├─ layout_design_agent.py               Agent Prompt 库 (prompts/agents/)
  ├─ quality_check_agent.py                ├─ technology.md (90 行)
  ├─ survey_*_agent.py                     ├─ competition.md (97 行)
  └─ cross_synthesis_agent.py              ├─ market_size.md (87 行)
                                           ├─ risk.md (80 行)
                                           ├─ financial_analysis.md (96 行)
                                           ├─ enterprise.md (75 行)
                                           ├─ policy.md (70 行)
                                            ├─ valuation.md (29 行) ← 严重不足
                                            ├─ investment.md (29 行) ← 严重不足
                                           └─ 其他 15 个文件
```

### 4.2 Agent Prompt 的专业性评估

#### 4.2.1 已具备的专业框架（正面）

| Agent | 使用的专业框架 | 数量 |
|-------|---------------|------|
| Technology | Gartner Hype Cycle, TRL ISO 16290, S-curve, Patent Landscape, Technology Roadmapping | 5 |
| Competition | Porter's Five Forces, Strategic Group Mapping, Moat Analysis, Market Structure, Disruption Assessment | 5 |
| Market Size | Top-down/Bottom-up, S-curve fitting, Cohort Analysis, Cross-market Analogy | 4 |
| Risk | 5x5 Risk Matrix, Bow-Tie, Scenario Analysis, Risk Heat Map, Monte Carlo (conceptual) | 5 |
| Financial | DuPont Analysis, Cash Flow Quality, Mean Reversion, Credit Analysis, Growth Decomposition | 5 |
| Enterprise | SWOT Cross-impact, Business Model Canvas, Moat Assessment, Management Quality, Peer Benchmarking | 5 |
| Policy | PESTEL, Regulatory Impact Assessment, Policy Cycle, Stakeholder Mapping, Scenario Planning | 5 |
| Industry Chain | Porter's Value Chain, Profit Pool Analysis, Bargaining Power, Vertical Integration, Ecosystem Mapping | 5 |
| Trend | STEEP, S-curve, Industry Lifecycle, Signal Detection, Cross-Impact Matrix | 5 |

#### 4.2.2 系统性缺失（所有 Agent 共有）

| 缺失项 | 影响 | 修复方向 |
|--------|------|----------|
| **无评分标准** | Agent 不知道什么是一篇优秀章节 | 注入评分维度说明(rubric) |
| **无优秀示例** | Agent 无法参照业界标杆写作 | 注入历年高评分章节 |
| **无自我评估步骤** | 一次性生成，既不反思也不修订 | 强制自评并迭代 |
| **无读者画像** | 不知道写给谁看（CEO/分析师/投资者） | 注入读者角色与决策场景 |
| **无最低数据阈值** | 知识缺口检测过于保守 | 声明性要求：≥8 个数据点、≥3 个趋势对比 |
| **无跨章节逻辑一致性意识** | 各章节独立写作可能产生矛盾 | 注入其他章节的初步结论供参考 |
| **无"所以呢"层** | 只报告数据，不解读含义 | 强制：每个数据点后跟"This means..." |

#### 4.2.3 严重不足的 Agent

**Valuation Analyst** (`prompts/agents/valuation.md`, **29 行**):
- 仅描述方法选择原则(DCF/相对估值/可比公司/敏感性分析)
- **无语量输出模板、无所需表格、无置信度标签、无反事实推理**
- 缺少: WACC 构建表、DCF 情景表、可比公司表、敏感性网格

**Investment Analyst** (`prompts/agents/investment.md`, **29 行**):
- 仅描述投资论点开发、价值评估、时机判断、组合建议
- **同上，处于严重不足状态**

### 4.3 Agent 执行流程诊断

#### 4.3.1 GenericAgent.execute() 执行流程

**位置**: `generic_agent.py:153-960`

```
知识查询 ─→ 数据收集 ─→ 数据验证 ─→ 深度分析 ─→ 污染过滤 ─→ 返回
  │            │            │            │            │
  │            │            │            │            └─ 检查是否复制了输入数据
  │            │            │            └─ 无质量自我评估！← 核心缺口
  │            │            └─ 仅做跨来源交叉验证
  │            └─ 搜索质量评分(阈值 5 个数据点/3 个年份/1500 字符/3 个关键词)
  └─ 注入 canonical 数据和知识富集
```

**关键缺陷**: 深度分析阶段(`:376-514`, 条件分支而非独立方法)**没有任何质量自我评估**。Agent 一次性完成分析，之后只有污染过滤，没有质量门控。

#### 4.3.2 知识注入机制

```python
# generic_agent.py:249-262
if "knowledge_query" in self._available_skills and skill_registry:
    kq_skill = skill_registry.get("knowledge_query")
    if kq_skill:
        enrichment = await kq_skill.execute(action="enrich", topic=topic, aspect=aspect)
```

知识注入执行一次，在 LLM 分析之前。注入内容包括：
- 实体知识（从 KnowledgeBank 搜索）
- **无分析框架知识、无写作示例、无方法论知识**

### 4.4 Agent 诊断总结

```
Agent 评分上不去的原因：
┌──────────────────────────────────────────────────────────────┐
│ 1. Agent 不知道评分标准（无 rubric 注入）                     │
│ 2. Agent 没有优秀示例可参考（无 exemplar 注入）               │
│ 3. Agent 不自我评估（单次生成无迭代）                          │
│ 4. Valuation/Investment Agent 严重不足（各仅 29 行）           │
│ 5. 知识注入仅限于实体/关系，无方法论知识                      │
│ 6. 无读者画像导致写作风格与报告目标脱节                        │
│ 7. 无跨章节一致性检查（仅数字通过 canonical data 对齐）        │
└──────────────────────────────────────────────────────────────┘
```

---

## 第五章：目标架构设计

### 5.1 核心理念：从"形式检查"到"知识驱动的专业分析"

```
当前范式：
  关键词检查 → 分数 → 通过/不通过
  (不关心分析深度、方法正确性、洞察力)

目标范式：
  方法论知识注入 → Agent 专业写作 → 语义评估 → 深度反馈 → 持续改进
  (关注分析框架使用质量、逻辑完整性、数据质量、洞察深度)
```

### 5.2 系统架构

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                             应用层                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ Fixed Agents │  │Dynamic Agents│  │ Quality QC   │  │ Document Gen │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
└─────────┼─────────────────┼─────────────────┼─────────────────┼────────────┘
          │ ① 方法论注入     │ ② 知识查询       │ ③ 语义评估       │
          ▼                  ▼                  ▼                  ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           知识服务层                                         │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │               Methodology Knowledge Base (MKB) 新增                   │   │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌───────┐ │   │
│  │  │ Analytical      │ │ Writing         │ │ Data           │ │Quality│ │   │
│  │  │ Frameworks      │ │ Exemplars       │ │ Standards      │ │Rubric │ │   │
│  │  │ * Porter's Five │ │ * High-scoring  │ │ * Industry     │ │* Per- │ │   │
│  │  │ * TRL Guide     │ │   sections      │ │   benchmarks   │ │section│ │   │
│  │  │ * Market Sizing │ │ * Style guides  │ │ * Validation   │ │* Per- │ │   │
│  │  │ * ... 20+       │ │ * Templates     │ │   rules        │ │method │ │   │
│  │  └────────────────┘ └────────────────┘ └────────────────┘ └───────┘ │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │               Industry Knowledge Base (IKB)  现有增强                  │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐│   │
│  │  │Entities│ │Relation│ │Data    │ │Insights│ │Temporal│ │Proven- ││   │
│  │  │        │ │s       │ │Points  │ │        │ │        │ │ance    ││   │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘│   │
│  │  ┌────────┐ ┌────────┐                                            │   │
│  │  │FTS5    │ │Synonym │ ← 增强：FTS5 接入主流程 + 同义词扩展      │   │
│  │  │Index   │ │Expander│   （向量检索已实现但未接入，待评估）        │   │
│  │  └────────┘ └────────┘                                            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
          ▲                          ▲                          ▲
          │ 反馈                     │ 自学                      │ 评分
┌─────────┼──────────────────────────┼──────────────────────────┼────────────┐
│  ┌──────┴──────────────────────────┴──────────────────────────┴──────────┐ │
│  │                        持续学习引擎                                    │ │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐│ │
│  │  │ Score → MKB  │ │ Gap →        │ │ Exemplar →   │ │ Pattern →    ││ │
│  │  │ (高分入库)    │ │ LearningMgr  │ │ PromptInject │ │ PromptOpt    ││ │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘│ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 方法论知识库（MKB）详细设计

#### 5.3.1 数据模型

```python
@dataclass
class AnalyticalFramework:
    """分析框架知识单元——MKB 的核心资产"""
    framework_id: str                    # "porter_five_forces_v2"
    name: str                            # "波特五力分析"
    category: str                        # "industry_analysis" / "financial_analysis"
    version: str                         # "2.0"
    
    # 适用性
    applicable_section_types: List[str]  # ["competition", "industry_overview"]
    applicable_industries: List[str]     # ["all"] 或特定行业
    
    # 框架内容（结构化）
    components: List[FrameworkComponent] # 框架的各个分析要素
    # [
    #   FrameworkComponent(id="rivalry", name="现有竞争者", weight=0.25,
    #       assessment_criteria=["CR3趋势", "产能利用率", "退出壁垒", ...],
    #       evidence_required=["市场份额数据", "价格趋势", "产能数据"]),
    #   ...
    # ]
    
    # 质量标准
    quality_rubric: Dict[str, float]     # {"data_completeness": 0.3, "logical_chain": 0.3, 
                                         #  "depth_of_analysis": 0.2, "data_quality": 0.2}
    common_mistakes: List[str]           # ["混淆行业内竞争与替代品威胁", "未区分短期与长期竞争动态"]
    
    # 参考
    exemplar_ids: List[str]              # 使用此框架的优秀章节 ID
    reference_source: str                # "Porter, M.E. (1980) Competitive Strategy"


@dataclass
class FrameworkComponent:
    """框架组件——分析框架的原子单元"""
    component_id: str
    name: str
    weight: float                        # 在框架中的权重(0-1)
    assessment_criteria: List[str]       # 评估标准
    evidence_required: List[str]         # 需提供的证据类型
    common_pitfalls: List[str]           # 常见错误
    scoring_guide: Dict[str, str]        # 评分子指南


@dataclass
class WritingExemplar:
    """专业写作示例——供 Agent 参考的高质量内容"""
    exemplar_id: str                     # "exemplar_market_size_ev_2026_01"
    section_type: str                    # "market_size"
    industry: str                        # "new_energy_vehicle"
    score: float                         # 原始评分(85+)
    
    # 内容
    content: str                         # 完整章节内容
    word_count: int
    data_point_count: int
    framework_used: str                  # 使用的主要分析框架
    
    # 为什么优秀（结构化分析）
    strengths: Dict[str, str]           # {"logical_structure": "...", "data_quality": "...", "insight_depth": "..."}
    methodology_chain: List[str]         # ["top-down_sizing", "cross_market_analogy", "s_curve_forecast"]
    
    # 元数据
    created_at: str
    source_report_id: str
    tags: List[str]


@dataclass
class QualityRubric:
    """评分细则——定义如何评估一个章节的质量"""
    rubric_id: str
    section_type: str                    # 适用章节类型
    
    dimensions: List[RubricDimension]    # 评估维度
    # [
    #   RubricDimension(id="data_density", name="数据密度", weight=0.20,
    #       levels=[
    #           Level(score=0, desc="无数据支撑"),
    #           Level(score=25, desc="1-2 个数据点"),
    #           Level(score=50, desc="3-5 个数据点"),
    #           Level(score=75, desc="6-10 个数据点，有数据来源标注"),
    #           Level(score=100, desc="10+ 个数据点，多源交叉验证，有口径标注和置信度说明"),
    #       ]),
    #   ...
    # ]
    
    min_pass_score: float                # 最低通过分数
    fail_dimensions: List[str]           # 任一不合格则整体不合格的维度（如 fact_accuracy）


@dataclass
class DataStandard:
    """数据标准——行业特定的 benchmark 和校验规则"""
    standard_id: str
    industry: str
    metric: str                          # "price_to_earnings_ratio"
    
    valid_range: Tuple[float, float]     # (5, 50) — PE 合理范围
    typical_value: Optional[float]       # 20 — 行业平均 PE
    source_hierarchy: List[str]          # 推荐数据源优先级
    unit: str
    caliber_notes: str                   # 口径说明
    validation_rules: List[str]          # ["must_be_positive", "year_over_year_change < 500%"]
```

#### 5.3.2 存储结构

```
data/knowledge/methodology/
├── frameworks/
│   ├── industry_analysis/
│   │   ├── porter_five_forces.yaml
│   │   ├── market_sizing_triangulation.yaml
│   │   ├── competitive_moat_assessment.yaml
│   │   ├── strategic_group_mapping.yaml
│   │   ├── industry_lifecycle_analysis.yaml
│   │   ├── profit_pool_analysis.yaml
│   │   ├── value_chain_analysis.yaml
│   │   ├── technology_s_curve.yaml
│   │   └── disruption_assessment.yaml
│   └── financial_analysis/
│       ├── dupont_decomposition.yaml
│       ├── quality_of_earnings.yaml
│       ├── dcf_valuation.yaml
│       ├── comparable_valuation.yaml
│       ├── sum_of_the_parts.yaml
│       └── sensitivity_analysis.yaml
├── exemplars/                          # 按章节类型组织
│   ├── market_size/
│   │   ├── new_energy_vehicle_001.yaml
│   │   ├── semiconductor_001.yaml
│   │   └── ...
│   ├── competition/
│   └── technology/
├── rubrics/                            # 评分细则
│   ├── market_size_rubric.yaml
│   ├── competition_rubric.yaml
│   ├── technology_rubric.yaml
│   ├── risk_rubric.yaml
│   ├── financial_rubric.yaml
│   ├── enterprise_rubric.yaml
│   ├── policy_rubric.yaml
│   ├── industry_chain_rubric.yaml
│   ├── trend_rubric.yaml
│   └── valuation_rubric.yaml
└── data_standards/
    ├── financial_metrics.yaml
    ├── technology_metrics.yaml
    └── industry_benchmarks.db          # SQLite
```

### 5.4 三层语义评分体系设计

#### 5.4.1 架构

```python
class SemanticQualityScorer:
    """
    三层语义评分器
    
    职责：取代当前的 keyword-counting 评分，实现真正的质量评估
    
    分层：
      Layer 1: 结构完整性检查 (30%) — 快速过滤，规则引擎
      Layer 2: 方法论应用评估 (40%) — 检查框架使用质量，规则+LLM
      Layer 3: 分析深度评估 (30%) — LLM-as-Judge with rubric
    """
    
    async def score(self, content: str, section_type: str,
                    framework: Optional[AnalyticalFramework] = None) -> SectionScore:
        
        # Layer 1: 快速结构检查
        layer1 = await self._layer1_structure(content, section_type)
        if layer1.score < 30:  # 结构严重不足，直接返回
            return SectionScore(total=layer1.score, layers={"structure": layer1})
        
        # Layer 2: 方法论应用
        layer2 = await self._layer2_methodology(content, section_type, framework)
        
        # Layer 3: 深度评估
        layer3 = await self._layer3_depth(content, section_type)
        
        # 加权融合
        total = layer1.score * 0.30 + layer2.score * 0.40 + layer3.score * 0.30
        
        return SectionScore(
            total=round(total, 1),
            layers={"structure": layer1, "methodology": layer2, "depth": layer3},
            details={...}  # 子维度明细
        )
```

#### 5.4.2 Layer 1：结构完整性检查（30%）

**替代当前的关键词存在性检查**，改为**分析要素完整性评估**：

```python
# 每种章节类型有独立的分析要素清单
ANALYSIS_ELEMENTS = {
    "market_size": [
        Element("current_size", "当前市场规模", 
               evidence_patterns=[r'\d+\.?\d*\s*(亿元|亿美元)', r'TAM|SAM|SOM'],
               min_count=1, weight=0.15),
        Element("growth_analysis", "增长分析",
               evidence_patterns=[r'CAGR|同比增长|复合增长|增速'],
               min_count=1, weight=0.15),
        Element("structural_breakdown", "结构分解",
               evidence_patterns=[r'分[布拆]|按[产品区域客户]|segment|Segment'],
               min_count=1, weight=0.15),
        Element("growth_driver", "增长驱动因素",
               evidence_patterns=[r'驱动|推动|因素|驱动力|driver'],
               min_count=2, weight=0.20),
        Element("data_cross_validation", "数据交叉验证",
               evidence_patterns=[r'交叉验证|cross.valid|多源|multiple.source|对比'],
               min_count=1, weight=0.15),
        Element("forecast", "预测与假设",
               evidence_patterns=[r'预[测算]|估计|预计|forecast|projection'],
               min_count=1, weight=0.10),
        Element("uncertainty", "不确定性说明",
               evidence_patterns=[r'不确定性|置信|confiden|range|区间'],
               min_count=1, weight=0.10),
    ],
    "competition": [
        Element("concentration", "市场集中度",
               evidence_patterns=[r'CR[3458]|HHI|集中|concentration'],
               min_count=1, weight=0.15),
        Element("top_players", "主要参与者分析",
               evidence_patterns=[r'(?:前|top)\s*\d+|头部|领先|leading'],
               min_count=3, weight=0.20),
        Element("barriers", "进入/退出壁垒",
               evidence_patterns=[r'壁垒|barrier|moat|护城河|门槛'],
               min_count=2, weight=0.15),
        Element("competitive_dynamics", "竞争动态",
               evidence_patterns=[r'份额变化|share.*change|竞争格局|landscape'],
               min_count=1, weight=0.15),
        Element("porter_forces", "五力分析或等效框架",
               evidence_patterns=[r'五力|Porter|supplier.*power|buyer.*power|替代威胁'],
               min_count=3, weight=0.20),
        Element("strategic_positioning", "战略定位",
               evidence_patterns=[r'定位|position|差异化|成本领先|差异化|strategy'],
               min_count=1, weight=0.15),
    ],
    "technology": [
        Element("tech_categories", "技术路线分类",
               evidence_patterns=[r'技术路线|approach|方向.*技术|technical.*path'],
               min_count=1, weight=0.10),
        Element("maturity_assessment", "成熟度评估",
               evidence_patterns=[r'成熟度|TRL|研发阶段|试验|量产|prototype'],
               min_count=1, weight=0.20),
        Element("patent_analysis", "专利分析",
               evidence_patterns=[r'专利|IP|知识产权|布局|申请.*量'],
               min_count=1, weight=0.15),
        Element("competitive_landscape", "技术竞争格局",
               evidence_patterns=[r'技术.*格局|技术.*竞争|研发.*投入|efficiency|learning.*curve'],
               min_count=2, weight=0.20),
        Element("commercialization", "商业化进程",
               evidence_patterns=[r'商业化|落地|应用.*场景|客户.*验证|pilot'],
               min_count=1, weight=0.15),
        Element("roadmap", "技术路线图",
               evidence_patterns=[r'路线图|roadmap|规划|202[5-9]|2030'],
               min_count=1, weight=0.10),
        Element("impact_analysis", "产业影响分析",
               evidence_patterns=[r'影响|颠覆|重构|重塑|替代|disruption'],
               min_count=1, weight=0.10),
    ],
}
```

**评分公式**：
```python
def score_layer1(content: str, section_type: str) -> Layer1Score:
    elements = ANALYSIS_ELEMENTS[section_type]
    total_weight = sum(e.weight for e in elements)
    weighted_score = 0.0
    
    for element in elements:
        presence_score = 0.0
        for pattern in element.evidence_patterns:
            matches = re.findall(pattern, content)
            if len(matches) >= element.min_count:
                presence_score = 100.0
                break
            elif len(matches) > 0:
                presence_score = max(presence_score, (len(matches) / element.min_count) * 100)
        
        weighted_score += presence_score * (element.weight / total_weight)
    
    return Layer1Score(score=weighted_score)
```

#### 5.4.3 Layer 2：方法论应用评估（40%）

**评估 Agent 是否正确应用了分析框架**，这是当前系统完全缺乏的维度：

```python
async def score_layer2(content: str, section_type: str,
                       framework: AnalyticalFramework) -> Layer2Score:
    """
    方法论应用质量评估（规则引擎 + LLM辅助）
    
    评估维度：
    1. 框架匹配度：所选框架是否适合该章节类型
    2. 组件覆盖率：框架的各个组件是否都被覆盖
    3. 数据支撑度：框架分析是否有数据支撑
    4. 逻辑一致性：框架内部逻辑是否自洽
    
    如未提供 framework，先通过 LLM 识别内容中使用了什么框架。
    """
    
    # 1. 如果未指定框架，通过 LLM 识别
    if framework is None:
        framework = await identify_framework(content, section_type)
    
    # 2. 组件覆盖率评分
    component_scores = {}
    for component in framework.components:
        # 对每个组件，检查内容是否覆盖了其评估标准
        coverage = 0.0
        for criterion in component.assessment_criteria:
            if any(criterion_keyword in content for criterion_keyword in 
                   extract_keywords(criterion)):
                coverage += 1.0
        component_scores[component.component_id] = (coverage / len(component.assessment_criteria)) * 100
    
    coverage_score = sum(component_scores.values()) / len(component_scores)
    
    # 3. 数据支撑度（通过数据点密度和来源相关性评估）
    data_support_score = assess_data_support(content, framework)
    
    # 4. 逻辑一致性（通过 LLM 评估）
    logic_score = await assess_logic_consistency(content, framework)
    
    total = coverage_score * 0.40 + data_support_score * 0.30 + logic_score * 0.30
    return Layer2Score(score=total, component_scores=component_scores)
```

**框架识别 LLM Prompt**（当未预先注入时使用）：

```
你是一个分析框架识别专家。分析以下市场研究章节，识别其使用的分析框架。

可识别的框架列表：
- industry_analysis: porter_five_forces, market_sizing, competitive_analysis, value_chain, s_curve, ...
- financial_analysis: dupont, dcf, comparable_valuation, quality_of_earnings, ...

对每个识别到的框架，输出：
1. 框架名称
2. 置信度 (0-100)
3. 证据 (文本中哪些部分使用了该框架)

章节内容：
{content}

输出 JSON 格式。
```

#### 5.4.4 Layer 3：分析深度评估（30%）

**使用 LLM-as-Judge 配合结构化 rubric，替代当前的脆弱 LLM Judge 实现**：

```python
async def score_layer3(content: str, section_type: str) -> Layer3Score:
    """
    分析深度评估（LLM-as-Judge with structured rubric）
    
    评估维度：
    1. 洞察力 (25%)：是否超越表面数据，有独特见解
    2. 逻辑链完整性 (25%)：推理是否完整严密
    3. 数据批判性 (20%)：是否评估了数据质量和局限性
    4. 前瞻性 (15%)：是否有前瞻性判断
    5. 可验证性 (15%)：结论是否可被验证或证伪
    """
    
    # 加载该章节类型的评分 rubric
    rubric = load_rubric(section_type)
    
    # 构建结构化评估 prompt
    prompt = build_depth_assessment_prompt(content, rubric, section_type)
    
    # 调用 LLM 评估（严格 JSON 格式）
    response = await llm_judge.evaluate_structured(
        prompt=prompt,
        response_schema=RubricScore,
        temperature=0.2,       # 低温度保证一致性
        model="default_model",  # 不使用 cheap_model
        max_retries=2,          # 重试避免解析失败
    )
    
    if response is None:
        # 真正的回退：使用规则引擎做保守评估
        return await rule_based_depth_fallback(content, section_type)
    
    # 验证评分合理性
    response = validate_scores(response, content)
    
    # 加权汇总
    total = sum(
        rubric.dimensions[i].weight * response.dimensions[rubric.dimensions[i].dimension_id].score
        for i in range(len(rubric.dimensions))
        if rubric.dimensions[i].dimension_id in response.dimensions
    )
    
    return Layer3Score(
        score=total,
        dimensions=response.dimensions,
        reasoning=response.reasoning,  # LLM 的推理过程
    )
```

**深度评估 Prompt 模板**：

```
你是一位资深行业研究质量评估专家。请评估以下章节的分析深度。

章节类型：{section_type}
评分细则：{rubric_json}

待评估内容：
{content}

请对以下每个维度评分 (0-100)，并提供具体的推理依据：

1. 洞察力 (权重 25%)：文章是否超越表面数据？
   - 0-20: 仅复述事实，无个人见解
   - 21-40: 有基础判断但缺乏深度
   - 41-60: 有独立的分析视角
   - 61-80: 能识别数据背后的模式和趋势
   - 81-100: 有独创性洞察，挑战现有认知

2. 逻辑链完整性 (权重 25%)：...
3. 数据批判性 (权重 20%)：...
4. 前瞻性 (权重 15%)：...
5. 可验证性 (权重 15%)：...

请严格按照以下 JSON 格式输出：
{{
    "dimensions": {{
        "insight": {{"score": <int>, "reasoning": "<string>", "evidence": ["<string>"]}},
        "logic": {{"score": <int>, "reasoning": "<string>", "evidence": ["<string>"]}},
        "data_critique": {{"score": <int>, "reasoning": "<string>", "evidence": ["<string>"]}},
        "forward_looking": {{"score": <int>, "reasoning": "<string>", "evidence": ["<string>"]}},
        "verifiability": {{"score": <int>, "reasoning": "<string>", "evidence": ["<string>"]}}
    }},
    "overall_assessment": "<string>",
    "improvement_suggestions": ["<string>"]
}}
```

**规则引擎回退**（当 LLM 调用失败时）：

```python
async def rule_based_depth_fallback(content: str, section_type: str) -> Layer3Score:
    """
    LLM 评估失败时的保守回退方案。
    相比当前系统回退 90 分，此处回退 50 分(中等)，且不通过阈值。
    """
    # 基于可测量的指标做保守评估
    score = 50.0
    
    # 正向信号
    if has_comparative_analysis(content):
        score += 5
    if has_causal_claims(content):
        score += 5
    if has_contradiction_discussion(content):
        score += 5
    
    # 负向信号
    if is_only_descriptive(content):
        score -= 10
    if has_placeholder_patterns(content):
        score -= 10
    
    return Layer3Score(score=max(0, min(100, score)), fallback=True)
```

### 5.5 Agent 增强设计

#### 5.5.1 方法论注入器

```python
class MethodologyInjector:
    """
    方法论注入器
    
    在 Agent 执行工作前，将方法论知识注入到 prompt 中。
    注入内容：
    1. 适用的分析框架（含详细评估标准）
    2. 行业 benchmark 数据
    3. 优秀写作示例
    4. 评分细则（让 Agent 知道自己将被如何评估）
    """
    
    def __init__(self, mkb: MethodologyKnowledgeBase):
        self.mkb = mkb
    
    async def inject(self, base_prompt: str, task_context: TaskContext) -> str:
        """注入方法论知识到 Agent prompt"""
        
        enhancements = []
        
        # 1. 注入分析框架
        framework = await self.mkb.get_best_framework(
            section_type=task_context.section_type,
            industry=task_context.industry
        )
        if framework:
            enhancements.append(self._format_framework(framework))
        
        # 2. 注入行业 benchmark
        benchmarks = await self.mkb.get_benchmarks(
            industry=task_context.industry,
            metrics=task_context.metrics
        )
        if benchmarks:
            enhancements.append(self._format_benchmarks(benchmarks))
        
        # 3. 注入优秀示例
        if task_context.section_type != "executive_summary":  # 概要章节不需要
            exemplar = await self.mkb.get_best_exemplar(
                section_type=task_context.section_type,
                industry=task_context.industry,
                min_score=85
            )
            if exemplar:
                enhancements.append(self._format_exemplar(exemplar))
        
        # 4. 注入评分细则
        rubric = await self.mkb.get_rubric(task_context.section_type)
        if rubric:
            enhancements.append(self._format_rubric(rubric))
        
        # 5. 组装增强 prompt
        if enhancements:
            enhanced = base_prompt + "\n\n## 方法论指南（系统注入）\n\n"
            enhanced += "\n\n---\n\n".join(enhancements)
            return enhanced
        
        return base_prompt
    
    def _format_framework(self, framework: AnalyticalFramework) -> str:
        """格式化分析框架为 prompt 可读内容"""
        lines = [
            f"### 推荐分析框架：{framework.name}",
            f"适用章节：{', '.join(framework.applicable_section_types)}",
            "",
            "#### 框架组件及评估标准",
        ]
        for comp in framework.components:
            lines.append(f"- **{comp.name}** (权重 {comp.weight*100:.0f}%)")
            for criterion in comp.assessment_criteria:
                lines.append(f"  - 评估标准：{criterion}")
            for evidence in comp.evidence_required:
                lines.append(f"  - 需提供证据：{evidence}")
        lines.append("")
        lines.append("#### 常见错误（避免）")
        for mistake in framework.common_mistakes:
            lines.append(f"- {mistake}")
        return "\n".join(lines)
    
    def _format_exemplar(self, exemplar: WritingExemplar) -> str:
        """格式化优秀示例为参考内容"""
        return (
            f"### 优秀示例参考（评分 {exemplar.score}/100）\n\n"
            f"**分析亮点**：\n"
            + "\n".join(f"- {k}：{v}" for k, v in exemplar.strengths.items()) + "\n\n"
            f"**使用的分析方法**：{', '.join(exemplar.methodology_chain)}\n\n"
            "```\n" + exemplar.content[:2000] + "\n```\n"
        )
    
    def _format_rubric(self, rubric: QualityRubric) -> str:
        """格式化评分细则"""
        lines = [
            "### 本章节评分标准",
            f"最低通过分数：{rubric.min_pass_score}",
            "",
        ]
        for dim in rubric.dimensions:
            lines.append(f"#### {dim.name}（权重 {dim.weight*100:.0f}%）")
            for level in dim.levels:
                lines.append(f"- [{level.score}分] {level.desc}")
            lines.append("")
        return "\n".join(lines)
```

#### 5.5.2 Agent 自我评估步骤

在 GenericAgent.execute() 的深度分析阶段末尾，增加强制自评步骤：

```python
# generic_agent.py — 在 deep_analysis 阶段末尾增加
async def _self_evaluate_and_revise(
    self,
    draft_content: str,
    section_type: str,
    rubric: Optional[QualityRubric] = None,
    max_iterations: int = 2
) -> str:
    """
    自我评估与修订
    
    Agent 对自己的输出进行评分，如果低于阈值则自动修订。
    """
    current = draft_content
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        # 自评
        evaluation = await self._evaluate_own_output(current, section_type, rubric)
        
        if evaluation.passed:
            logger.info(f"Self-evaluation passed at iteration {iteration}: {evaluation.score:.1f}")
            break
        
        # 修订
        logger.info(f"Self-evaluation: {evaluation.score:.1f}, revising (iteration {iteration})")
        current = await self._revise_output(current, evaluation, section_type)
    
    return current


async def _evaluate_own_output(
    self,
    content: str,
    section_type: str,
    rubric: Optional[QualityRubric]
) -> EvaluationResult:
    """
    使用注入的评分标准评估自己的输出。
    如果 rubric 可用，使用结构化评分；否则使用通用评估。
    """
    prompt = f"""请评估你刚刚撰写的以下市场研究章节的质量。

章节类型：{section_type}

"""
    if rubric:
        prompt += f"""
评分标准：
{rubric.to_prompt_string()}
"""
    else:
        prompt += f"""
请从以下维度评分（0-100）：
1. 数据支撑度：是否有足够的数据支持核心结论
2. 分析深度：是否进行了深入分析，而非表面描述
3. 逻辑结构：推理是否清晰，论证是否严密
4. 洞察力：是否有超越数据的独特见解
5. 前瞻性：是否包含前瞻性判断
    
评估内容：
{content}

请输出 JSON:
{{"scores": {{"data": int, "depth": int, "logic": int, "insight": int, "forward": int}}, "passed": bool, "weaknesses": [str], "improvement_plan": str}}
"""
    # 使用 LLM 自评，temperature=0.2 保证一致性
    response = await self._llm.generate(prompt, temperature=0.2)
    
    try:
        result = EvaluationResult.from_json(response)
    except (json.JSONDecodeError, KeyError):
        # 回退：保守评估
        result = EvaluationResult.fallback(content)
    
    return result
```

#### 5.5.3 Agent Prompt 升级计划

针对所有 24 个 prompt，增加以下标准节：

```
## 质量评分标准（本章节将被按以下维度评估）

1. 数据密度 (20%)：需要至少 {min_data_points} 个量化数据点
   - 1-2 个数据点：25 分
   - 3-5 个数据点：50 分  
   - 6-10 个数据点：75 分（需标注来源）
   - 10+ 数据点且多源交叉验证：100 分

2. 分析方法应用 (25%)：正确应用 {recommended_framework} 框架
   - 覆盖至少 {min_components} 个框架组件
   - 每个组件需有数据支撑
   - 包含反证/边界条件

3. 分析深度 (25%)：超越表面数据
   - 包含因果分析（"X 导致 Y 因为..."）
   - 包含比较分析（历史/同业/跨市场）
   - 识别数据异常或矛盾

4. 逻辑完整性 (20%)：论证链完整
   - 核心判断 → 数据支撑 → 逻辑推导 → 结论
   - 反证 → 反驳/承认边界 → 修正结论

5. 数据质量 (10%)：来源可信且标注清晰
   - 每个数据点标注来源和口径
   - 使用置信度标签（HIGH/MEDIUM/LOW）
   - 预测数据标注假设条件

## 自我检查清单（输出前完成）
□ 包含至少 {min_data_points} 个量化数据点
□ 使用了 {recommended_framework} 或等效框架
□ 包含反证或边界条件讨论
□ 每个核心判断都有数据支撑
□ 标注了数据来源和置信度
□ "所以呢"层已覆盖（对投资者/决策者的含义）
```

### 5.6 知识反馈循环

```python
class KnowledgeFeedbackLoop:
    """
    知识反馈循环——让每次写作都变成一次学习
    
    高分章节 → 入库作为示例
    低分章节 → 分析薄弱维度 → 存入 LearningManager
    模式和经验 → 持续优化 prompt 和 rubric
    """
    
    async def on_section_completed(
        self,
        section_id: str,
        content: str,
        score: SectionScore,
        context: SectionContext,
        mkb: MethodologyKnowledgeBase,
        learning_mgr: LearningManager
    ):
        """章节完成后触发"""
        
        if score.total >= 85:
            # 高分：存为示例
            exemplar = WritingExemplar(
                exemplar_id=f"exemplar_{context.section_type}_{context.industry}_{datetime.now():%Y%m%d_%H%M%S}",
                section_type=context.section_type,
                industry=context.industry,
                score=score.total,
                content=content,
                word_count=len(content),
                data_point_count=self._count_data_points(content),
                framework_used=score.layers.get("methodology", {}).get("framework_used") if isinstance(score.layers.get("methodology"), dict) else getattr(score.layers.get("methodology"), "framework_used", None),
                strengths={
                    "logical_structure": self._extract_strength_description(score, "structure"),
                    "data_quality": self._extract_strength_description(score, "methodology"),
                    "insight_depth": self._extract_strength_description(score, "depth"),
                },
                methodology_chain=self._identify_methodology_chain(score),
                created_at=datetime.now().isoformat(),
                source_report_id=context.report_id,
                tags=[context.industry, context.section_type]
            )
            await mkb.store_exemplar(exemplar)
            logger.info(f"High-quality exemplar stored: {exemplar.exemplar_id}")
        
        elif score.total < 60:
            # 低分：记录学习
            weak_dimensions = self._identify_weak_dimensions(score)
            
            # 存入 LearningManager 作为改进依据
            await learning_mgr.record_quality_issue(
                section_type=context.section_type,
                industry=context.industry,
                score=score.total,
                weak_dimensions=weak_dimensions,
                improvement_suggestion=self._generate_suggestion(score, weak_dimensions),
                section_id=section_id,
                report_id=context.report_id
            )
            
            # 如果特定维度的评分持续低于阈值，触发 prompt 优化
            if weak_dimensions.get("depth", 100) < 30:
                await self._trigger_prompt_optimization(
                    section_type=context.section_type,
                    weak_dimension="depth",
                    learning_mgr=learning_mgr
                )
    
    async def _trigger_prompt_optimization(
        self,
        section_type: str,
        weak_dimension: str,
        learning_mgr: LearningManager
    ):
        """触发 prompt 优化流程"""
        
        # 收集该章节类型在 weak_dimension 上的所有低分记录
        issues = await learning_mgr.get_quality_issues(
            section_type=section_type,
            dimension=weak_dimension,
            min_count=3  # 至少 3 次才触发
        )
        
        if len(issues) < 3:
            return
        
        # 分析共性问题 → 生成 prompt 改进建议
        common_patterns = self._analyze_common_failures(issues)
        
        prompt_suggestion = PromptOptimizationSuggestion(
            section_type=section_type,
            target_dimension=weak_dimension,
            common_patterns=common_patterns,
            suggested_prompt_addition=self._generate_prompt_fix(common_patterns),
            evidence_count=len(issues)
        )
        
        await learning_mgr.store_prompt_suggestion(prompt_suggestion)
        logger.info(f"Prompt optimization triggered for {section_type}.{weak_dimension}")
```

---

## 第六章：分阶段实施路线图

### Phase 1：方法论知识库建设（3 周）

**目标**: 建立 MKB 基础设施，使 Agent 首次获得分析框架和写作标准知识

| 周 | 任务 | 产出物 | 关键文件 |
|----|------|--------|----------|
| 1 | MKB 数据模型设计 | AnalyticalFramework, WritingExemplar, QualityRubric, DataStandard 数据类 | `src/core/methodology/models.py` |
| 1 | MKB 存储层实现 | YAML 加载器, JSON 索引, SQLite 元数据存储 | `src/core/methodology/store.py` |
| 1 | 首批框架入库 | Porter's Five Forces, Market Sizing Triangulation, TRL Assessment, DuPont Analysis (4 个) | `data/knowledge/methodology/frameworks/*.yaml` |
| 2 | MethodologyInjector 实现 | 动态 Prompt 注入器 | `src/core/methodology/injector.py` |
| 2 | Rubric 设计(每个章节类型) | 10 个评分细则文件 | `data/knowledge/methodology/rubrics/*.yaml` |
| 2 | Data Standards 入库 | 金融指标、技术指标、行业基准 | `data/knowledge/methodology/data_standards/*` |
| 3 | DataCollectionQualityChecker 增强 | 改进数据量评分(连续函数替代 5 档)、来源可信度评分(域名分级) | `src/core/quality/checkers.py` |
| 3 | AnalysisQualityChecker 增强 | 用分析要素清单替代关键词存在性检查 | `src/core/quality/checkers.py` |

**预期效果**: 章节评分从 40-60 提升至 65-75

### Phase 2：三层语义评分体系（3 周）

**目标**: 构建真正的质量评估体系，从"关键词检查"升级到"语义评估"

| 周 | 任务 | 产出物 | 关键文件 |
|----|------|--------|----------|
| 1 | Layer 1 结构检查 | 分析要素完整性评分器(每种章节类型独立要素清单) | `src/core/quality/layer1_structure.py` |
| 1 | Layer 2 方法论评估 | 框架组件覆盖率 + 数据支撑度评分器 | `src/core/quality/layer2_methodology.py` |
| 2 | Layer 3 深度评估 | LLM-as-Judge with rubric(替换现有 LLM Judge) | `src/core/quality/layer3_depth.py` |
| 2 | 规则引擎回退 | LLM 失败时的保守评分(回退 50 分而非 90) | `src/core/quality/layer3_depth.py` |
| 2 | 评分融合器 | 三层加权 + 历史校准 | `src/core/quality/semantic_scorer.py` |
| 3 | QualityCheckAgent 替换 | 用 SemanticQualityScorer 替换 _calculate_section_score | `src/agents/fixed_agents/quality_check_agent.py` |
| 3 | ReportQualityChecker 增强 | 一致性检查(5%→10%容差)、溯源检查(中文分词修复)、去重(数值归一化) | `src/core/quality/checkers.py` |
| 3 | LLM Judge 修复 | 严格 JSON 解析(支持代码块包裹)、移除高分回退、增加重试 | `src/core/quality/llm_judge.py` |

**预期效果**: 章节评分从 65-75 提升至 75-85

### Phase 3：Agent 自评与迭代（3 周）

**目标**: 使 Agent 具备自我评估和迭代改进能力

| 周 | 任务 | 产出物 | 关键文件 |
|----|------|--------|----------|
| 1 | Agent 自评步骤实现 | _self_evaluate_and_revise 方法 | `src/core/agents/generic_agent.py` |
| 1 | 方法论注入集成 | MethodologyInjector 接入 Agent 执行流程 | `src/core/agents/generic_agent.py` |
| 2 | Valuation/Investment prompt 重写 | 从 29 行扩展至 120+ 行 | `prompts/agents/valuation.md`, `investment.md` |
| 2 | 所有 Prompt 增加评分标准节 | 24 个 prompt 统一升级 | `prompts/agents/*.md` |
| 2 | 读者画像注入 | Agent 知道写给谁看 | `prompts/_shared/reader_persona.md` |
| 3 | 知识反馈循环实现 | 高分入库、低分分析、Prompt 优化触发 | `src/core/quality/feedback_loop.py` |
| 3 | 跨章节逻辑一致性注入 | 合成章节 Agent 获取研究章节初步结论 | `src/core/orchestrator/execution/engine.py` |
| 3 | 数据标准校验集成 | Agent 生成时实时校验数据合理性 | `src/core/methodology/validator.py` |

**预期效果**: 章节评分从 75-85 提升至 85-95

### Phase 4：知识管理基础设施升级（3 周，可与 Phase 1-3 并行）

**目标**: 解决知识管理的根本性架构缺陷——FTS5 接入主流程、评估/清理未接入的检索模块、扩展搜索能力

**关键前提**: 向量检索（`retrieval/` 下 VectorStore/SemanticSearch/HybridSearch 共 1110 行）已实现但未接入主流程。`__init__.py:40` 注释掉公开导出，但 `retrieval/__init__.py` 仍正常导出，`settings.yaml` 仍配置 `embedding_model`。Phase 4 需评估是否重新启用或清理。FTS5 全文索引（`fts/` 下 675 行）已实现但未接入主搜索流程。

| 周 | 任务 | 产出物 | 关键文件 |
|----|------|--------|----------|
| 1 | **FTS5 接入主搜索流程** | EntityStore/RelationStore/DataPointStore 优先调用 FTSSearcher，FTS 不可用时回退 LIKE | `src/core/memory/stores/entity_store.py`, `src/core/memory/fts/__init__.py` |
| 1 | **KnowledgeBank 接入 FTSManager** | search_all() 改用 FTSManager.global_search() | `src/core/memory/knowledge_bank.py` |
| 1 | **评估/清理 retrieval 模块** | 评估向量检索是否重新启用；若不启用则移除或标记废弃 `src/core/memory/retrieval/` 下 1110 行代码，移除 `__init__.py:40` 注释行 | `src/core/memory/retrieval/`, `src/core/memory/__init__.py` |
| 2 | **LLM 驱动同义词扩展** | 替代 SemanticSearch 中 6 组硬编码同义词，按研究领域动态扩展 | `src/core/memory/fts/synonym_expander.py` |
| 2 | **LLM 实体提取** | 替代硬编码正则实体识别，接入已有 EntityExtractor 接口 | `src/core/memory/extraction/llm_entity_extractor.py` |
| 2 | **领域可扩展检测** | 基于研究内容动态识别领域，替代 10 个硬编码领域白名单 | `src/core/memory/extraction/domain_detector.py` |
| 3 | **时间感知知识** | CoreMemory 晋升加入时间衰减因子 | `src/core/memory/core/core_memory.py` |
| 3 | **跨会话记忆** | 编排器在路由时查询历史知识 | `src/core/orchestrator/orchestrator.py` |
| 3 | **Dream Mode 增强** | LLM 驱动的整合和模式发现 | `src/core/memory/dream/dream_mode.py` |

---

## 第七章：预期效果与衡量指标

### 7.1 评分提升路径

```
评分区间    当前    Phase 1   Phase 2   Phase 3   Phase 4
           (仅 MKB)  (语义评分)  (Agent 增强) (知识管理升级)

市场空间     55       70        80        88        90
竞争格局     52       68        78        86        88
技术分析     50       65        76        85        87
财务分析     48       64        75        83        86
风险分析     54       69        79        86        88
政策分析     50       66        77        85        87
企业分析     52       67        78        85        87
估值分析     45       60        72        82        85
行业链       50       66        77        85        87
趋势分析     48       65        76        85        87

综合平均     50.4     66.0      76.8      85.0     87.2
```

**注**: Phase 4 预期效果从原方案的 88.9 调整为 87.2，原因：(1) 搜索质量提升主要依靠 FTS5 接入（增量确定、可控），向量检索是否重新启用需评估后再决定，不计入本阶段预期；(2) 知识管理升级的边际效益在评分体系已改善后递减；(3) 各阶段预期需经 A/B 测试验证后方可确认。

### 7.2 关键质量指标 (KQI)

| 指标 | 当前 | 目标(Phase 3 后) | 衡量方法 |
|------|------|------------------|----------|
| 章节平均分 | 50.4 | 85+ | SemanticQualityScorer |
| 高分章节比例(≥80) | <5% | 60%+ | 分数分布统计 |
| 低分章节比例(<60) | 50%+ | <10% | 分数分布统计 |
| 数据幻觉率 | 未知 | <1% | 人工抽检 + 交叉验证 |
| 框架使用率 | 0%(未追踪) | 80%+ | Layer 2 方法论评估 |
| 数据来源标注率 | 50% | 95%+ | Layer 1 要素检查 |
| 置信度标签使用率 | 30% | 90%+ | 正则检测 |
| 反证/边界条件覆盖率 | 20% | 80%+ | Layer 1 要素检查 |
| 跨章节一致率 | 60% | 95%+ | ReportQualityChecker 增强版 |

### 7.3 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| LLM-as-Judge 评分偏离人工判断 | 中 | 高 | 设计校准数据集(500+ 人工标注章节)，定期校准评分权重 |
| 方法论注入增加 token 消耗 | 高 | 中 | 控制注入内容长度(框架摘要而非全文)，使用 cheaper model 做自评 |
| Agent 自评循环增加延迟 | 高 | 中 | max_iterations=2，超时保护，异步执行 |
| MKB 知识质量不足导致误导 | 中 | 高 | 框架入库需审核，版本管理，AB 测试新旧 prompt |
| 现有评分系统与新系统分数不一致 | 高 | 中 | 双轨运行 2 周，对比新旧评分，校准后再切换 |
| FTS5 接入后性能不如预期 | 低 | 中 | FTSSearcher 已有 LIKE 回退机制，FTS5 不可用时自动降级 |
| 清理 retrieval 模块误删有用代码 | 低 | 高 | 先评估向量检索是否重新启用；若不启用，先标记 @deprecated 运行 2 周，确认无引用后再移除 |

---

## 附录 A：代码修改清单

| 优先级 | 文件 | 修改内容 | 预估工时 |
|--------|------|----------|----------|
| P0 | `src/core/methodology/models.py` | 新建：数据模型 | 4h |
| P0 | `src/core/methodology/store.py` | 新建：YAML/SQLite 存储 | 8h |
| P0 | `src/core/methodology/injector.py` | 新建：Prompt 注入器 | 6h |
| P0 | `data/knowledge/methodology/frameworks/*.yaml` | 新建：首批 4 个框架 | 16h |
| P0 | `data/knowledge/methodology/rubrics/*.yaml` | 新建：10 个评分细则 | 20h |
| P0 | `src/core/quality/semantic_scorer.py` | 新建：三层评分器 | 16h |
| P0 | `src/core/quality/layer1_structure.py` | 新建：结构检查 | 8h |
| P0 | `src/core/quality/layer2_methodology.py` | 新建：方法评估 | 12h |
| P0 | `src/core/quality/layer3_depth.py` | 新建：深度评估 | 16h |
| P0 | `src/core/quality/llm_judge.py` | 重写：JSON 解析、移除高分回退 | 4h |
| P1 | `src/core/agents/generic_agent.py` | 新增：_self_evaluate_and_revise | 12h |
| P1 | `src/core/quality/checkers.py` | 修改：Analysis/Report 检查器增强 | 8h |
| P1 | `src/agents/fixed_agents/quality_check_agent.py` | 修改：替换为 SemanticScorer | 6h |
| P1 | `prompts/agents/valuation.md` | 重写：29 行→120+ 行 | 4h |
| P1 | `prompts/agents/investment.md` | 重写：29 行→120+ 行 | 4h |
| P1 | `prompts/agents/*.md` | 修改：增加评分标准和自检清单 | 16h |
| P2 | `src/core/quality/feedback_loop.py` | 新建：知识反馈循环 | 8h |
| P2 | `src/core/quality/layer3_depth.py` | 新增：规则引擎回退 | 4h |
| P3 | `src/core/memory/stores/entity_store.py` | 修改：search_entities 优先调用 FTSSearcher | 4h |
| P3 | `src/core/memory/knowledge_bank.py` | 修改：search_all 改用 FTSManager.global_search | 3h |
| P3 | `src/core/memory/fts/synonym_expander.py` | 新建：LLM 驱动同义词扩展 | 8h |
| P3 | `src/core/memory/extraction/llm_entity_extractor.py` | 新建：LLM 实体提取 | 12h |
| P3 | `src/core/memory/retrieval/` | 评估：决定向量检索是否重新启用；若不启用则标记废弃/移除 1110 行代码 | 2h |

---

## 附录 B：关键文件索引

| 文件 | 作用 | 行数 | 关键方法/函数 |
|------|------|------|---------------|
| `src/agents/fixed_agents/quality_check_agent.py` | 章节质检 | 980 | execute(:87), _calculate_score(:549), check_by_sections(:873), _calculate_section_score(:803) |
| `src/core/quality/checkers.py` | 三阶段质检器 | 967 | DataCollectionQualityChecker(:218), AnalysisQualityChecker(:347), ReportQualityChecker(:438), CompositeChecker(:960) |
| `src/core/quality/llm_judge.py` | LLM 评审 | 111 | LLMJudgeChecker._call_llm_sync(:67), fallback 90(:46) |
| `src/core/quality/metadata_extractor.py` | 数据质量元数据 | 450 | QualityMetadataExtractor.extract(:129) |
| `src/core/quality/quality_state.py` | 质量状态 | thin | QUALITY_PASS_THRESHOLD = 60 |
| `src/core/memory/knowledge_bank.py` | 知识银行核心 | 1038 | deposit_from_research(:163), get_relevant_knowledge(:229), search_all(:301) |
| `src/core/memory/knowledge_manager.py` | 知识管理入口 | 464 | deposit(:132), search(:233) |
| `src/core/memory/core/core_memory.py` | 核心记忆 | 548 | add_top_entity(:200), add_core_need(:267), 10KB limit(:119) |
| `src/core/memory/core/expertise_profile.py` | 专业画像 | 136 | primary_domains, domain_depth, terminology |
| `src/core/memory/core/rapid_evolver.py` | 快速进化器 | 387 | 10 领域硬编码(:75), 公司硬编码(:213) |
| `src/core/memory/extraction/entity_extractor.py` | 实体提取器 | 400 | 5 类型实体正则，中英双语，别名映射，置信度计算 |
| `src/core/memory/extraction/knowledge_extractor.py` | 知识自动提取 | 155 | 硬编码正则提取 |
| `src/core/memory/fts/__init__.py` | FTS5 全文索引 | 675 | FTSSearcher(:318), FTSManager，四类索引，**已实现但未接入主搜索流程** |
| `src/core/memory/retrieval/vector_store.py` | 向量存储（未接入主流程） | 457 | `__init__.py:40` 注释掉公开导出，`retrieval/__init__.py` 仍正常导出，配置中仍有 embedding_model，未接入主搜索流程 |
| `src/core/memory/retrieval/semantic_search.py` | 语义搜索（未接入主流程） | 241 | 含 6 组硬编码同义词+4 组缩写，需 Embedder 依赖，未接入主搜索流程 |
| `src/core/memory/retrieval/hybrid_search.py` | 混合搜索（未接入主流程） | 412 | 依赖向量+语义搜索，未接入主搜索流程 |
| `src/core/memory/knowledge/compiler.py` | 知识编译器 | 753 | compile_research(:230), 定义提取破碎(:349) |
| `src/core/memory/knowledge/importer.py` | 知识导入器 | 1135 | import_file(:727), import_url(:1013), 无 OCR |
| `src/core/memory/dream/dream_mode.py` | 做梦模式 | 491 | 6 phase 流程(:54), 无真正 AI 整合 |
| `src/core/agents/generic_agent.py` | 动态 Agent | 3995 | execute(:153), knowledge injection(:249), deep_analysis(:376), 无自评 |
| `src/core/agents/factory.py` | Agent 工厂 | 849 | create_agent(:238), ASPECT_SKILL_MAP |
| `src/core/orchestrator/orchestrator.py` | 主编排器 | 4545 | research(:421), _phase2_knowledge_for_routing(:5065), _phase5_deposit_knowledge(:5089) |
| `src/core/orchestrator/execution/engine.py` | 执行引擎 | 2399 | _execute_batch(:1810), QualityFeedbackExecutor |
| `config/research_frameworks.yaml` | 研究框架 | 473 | 章节权重、搜索策略 |
| `config/agents.yaml` | Agent 配置 | 265 | LLM 参数、能力 |
| `prompts/agents/*.md` | 24 个 Agent 提示词 | 32-215 each | 专业框架、定量模板 |
