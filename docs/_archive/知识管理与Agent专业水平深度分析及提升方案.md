# 知识管理与 Agent 专业水平深度分析及提升方案

> 本文档对 Zensers 系统的知识管理模块、Agent 设计、质量评分体系进行深度分析，揭示章节评分 40-60 分的根本原因，并提出系统性提升方案，目标达到 80-100 分。

---

## 一、现状诊断：评分 40-60 的根本原因

### 1.1 三类评分维度及其局限

通过对 `src/agents/fixed_agents/quality_check_agent.py`、`src/core/quality/checkers.py`、`src/core/quality/metadata_extractor.py` 的深度分析，当前质量评分体系分为三个层次：

| 评分层次 | 文件 | 核心逻辑 | 局限 |
|----------|------|----------|------|
| **章节级评分** | `quality_check_agent.py:803-823` | 关键词检查 + 数据密度 + 问题惩罚 | 仅检查 7 个固定关键词是否存在，不评估分析深度 |
| **分析级评分** | `checkers.py:374-416` | 五段式框架检查 + 口径标注 + 反证 + 量化分解 | 权重合理但仍是关键词匹配，无语义理解 |
| **报告级评分** | `checkers.py:473-530` | 完整性/一致性/冗余/溯源加权 | 35% 一致性仅做数值比对，35% 溯源性仅关键词重叠 |

### 1.2 核心发现：评分是"形式检查"而非"内容评估"

```python
# quality_check_agent.py:803-813 — 章节评分核心逻辑
structure_keywords = ["核心判断", "逻辑推导", "数据支持", "反证", "边界条件", "意义", "影响"]
found = sum(1 for kw in structure_keywords if kw in content)
structure_ratio = found / len(structure_keywords)  # 7 个关键词
if structure_ratio < 0.5:
    score -= (1 - structure_ratio) * 30  # 最多扣 30 分
```

**问题解剖**：
1. 仅检查**关键词是否存在**，不检查其后的**分析质量**
2. 一段包含所有关键词但内容空洞的文本可得高分
3. 一段真正的深度分析若未使用标准关键词则被扣分
4. **反证**、**边界条件**等仅做存在性检查，不做合理性评估

### 1.3 知识管理模块的深层缺陷

| 缺陷 | 具体表现 | 影响 |
|------|----------|------|
| **知识库缺少方法论** | `RapidEvolver` 的领域关键词硬编码在 Python 中，仅 10 个领域 | Agent 无法获取行业分析方法论 |
| **实体提取太浅** | 使用正则而非 NLP/LLM 提取实体，仅识别预定义的 20+ 公司名 | 无法提取深层专业实体 |
| **术语词典静态化** | `rapid_evolver.py:270-278` 的术语定义完全硬编码 | 无法学习新行业术语 |
| **知识搜索原始** | 使用 SQLite FTS 匹配，无语义检索 | 无法按分析维度检索知识 |
| **无行业基准数据** | 知识库只有用户积累的实体/关系，没有行业标准数据 | Agent 无法进行对标分析 |

### 1.4 Agent Prompt 的专业性差距

当前的 Agent prompt（如 `prompts/agents/technology.md`）已经包含了专业框架（TRL、Gartner Hype Cycle 等），但存在以下问题：

1. **框架是死的**：prompt 描述"你应该用 TRL 评估"，但 Agent 没有 TRL 各等级的详细判断标准
2. **缺少行业上下文**：prompt 不包含当前行业的具体 benchmark 数据
3. **无专业写作模板**：没有给出"一段优秀的行业分析应该怎么写"的示例
4. **无自我校验机制**：Agent 写完后无法自我评估分析质量

---

## 二、架构重构方案：知识驱动的专业分析系统

### 2.1 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Application Layer                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────────┐  ┌───────────────────┐  ┌──────────────┐ │
│  │  Fixed Agents      │  │  Dynamic Agents    │  │  Quality QC  │ │
│  │  (14 specialized)  │  │  (Chapter-specfic) │  │  (Scoring)   │ │
│  └────────┬──────────┘  └────────┬──────────┘  └──────┬───────┘ │
└───────────┼──────────────────────┼─────────────────────┼─────────┘
            │ Inject Methodology  │ Query Knowledge     │ Evaluate
            ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Knowledge Service Layer                        │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              Methodology Knowledge Base (MKB)             │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │    │
│  │  │ Analytical│ │ Writing  │ │ Data     │ │ Quality  │   │    │
│  │  │Frameworks │ │ Exemplars│ │Standards │ │Criteria  │   │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │    │
│  └──────────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              Industry Knowledge Base (IKB)                │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │    │
│  │  │Entities  │ │Relations │ │Benchmarks│ │Terminology│   │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
            ▲                      ▲                      ▲
            │ Store Learnings      │ Self-improve         │ Feedback
┌───────────┼──────────────────────┼─────────────────────┼─────────┐
│  ┌────────┴──────────────────────┴─────────────────────┴──────┐ │
│  │              Continuous Learning Engine                     │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │ │
│  │  │Quality   │ │Pattern   │ │Knowledge │ │Prompt    │     │ │
│  │  │Feedback   │ │Learning  │ │Evolution │ │Optimizer │     │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │ │
│  └──────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 方法论知识库（MKB）设计

这是将评分从 40-60 提升到 80-100 的核心——为 Agent 提供**专业级方法论知识**。

#### 存储结构

```
data/knowledge/methodology/
├── frameworks/                    # 分析框架库
│   ├── industry_analysis/
│   │   ├── porter_five_forces.yaml
│   │   ├── market_sizing.yaml     # 市场空间测算方法
│   │   ├── technology_assessment.yaml  # 技术评估方法
│   │   └── competitive_analysis.yaml
│   └── financial_analysis/
│       ├── valuation_methods.yaml
│       └── financial_forecast.yaml
├── writing_exemplars/             # 专业写作示例
│   ├── high_quality_sections/     # 高评分章节存档
│   └── style_guides/              # 写作风格指南
├── data_standards/                # 数据标准
│   ├── industry_metrics.yaml      # 各行业关键指标
│   ├── data_validation_rules.yaml # 数据校验规则
│   └── credible_sources.yaml      # 权威数据源清单
└── quality_criteria/              # 质量标准（供 QC 使用）
    ├── section_scoring_criteria.yaml
    └── analysis_depth_rubric.yaml
```

#### 关键数据模型

**`AnalyticalFramework`** — 分析框架知识单元：

```python
@dataclass
class AnalyticalFramework:
    """分析框架知识单元"""
    id: str                           # porter_five_forces_v2
    name: str                         # 波特五力分析
    category: str                     # industry_analysis
    version: str                      # 2.0
    applicability: List[str]          # ["industry_report", "competitor_analysis]
    components: List[FrameworkComponent]  # 框架组成
    typical_metrics: List[str]        # 典型指标
    common_pitfalls: List[str]        # 常见错误
    quality_rubric: Dict[str, float]  # 评分细则
    exemplar_section_id: Optional[str]  # 优秀示例引用
```

**`WritingExemplar`** — 专业写作示例：

```python
@dataclass
class WritingExemplar:
    """专业写作示例"""
    id: str
    section_type: str                 # market_size / competition / technology
    industry: str
    score: float                      # 原始评分
    content: str                      # 章节内容
    analysis: ExemplarAnalysis        # 为什么这是优秀的
    methodology_used: List[str]       # 使用的分析方法
    data_quality: Dict                # 数据质量标注
```

### 2.3 Agent 增强方案

#### 方法论注入机制

当前的 Agent prompt 只描述"该做什么"，注入机制让 Agent 同时知道"怎么做、怎样算好"：

```
Agent Execution Pipeline (Enhanced):

1. Receive Task (chapter type + industry)
2. Query MKB for relevant analytical frameworks
   → 获取该章节类型的分析框架知识
3. Query IKB for industry benchmarks
   → 获取该行业的 benchmark 数据
4. Query Exemplar for similar high-quality sections
   → 获取类似章节的优秀示例
5. Inject all into Agent context
   → 知识注入后 Agent 开始分析
6. Generate analysis with methodology-aware writing
7. Self-check against quality rubric
8. Submit for scoring
```

#### 动态 Prompt 组装器

在 `src/core/agents/generic_agent.py` 中新增 `MethodologyInjector`：

```python
class MethodologyInjector:
    def inject(
        self,
        base_prompt: str,
        section_type: str,
        industry: str,
        knowledge_manager: KnowledgeManager
    ) -> str:
        # 1. 获取分析框架
        frameworks = knowledge_manager.get_frameworks(section_type)
        
        # 2. 获取行业 benchmark
        benchmarks = knowledge_manager.get_industry_benchmarks(industry)
        
        # 3. 获取优秀示例
        exemplars = knowledge_manager.get_exemplars(section_type, industry)
        
        # 4. 组装增强 prompt
        enhanced = base_prompt + self._format_methodology(frameworks)
        enhanced += self._format_benchmarks(benchmarks)
        enhanced += self._format_exemplars(exemplars)
        
        return enhanced
```

#### 场景示例：技术分析 Agent 增强前后

**增强前**（当前）：
```
## Technology Maturity Scoring
- TRL level (1-9) with specific evidence
- Estimated years to commercialization
```

**增强后**（注入方法论知识后）：
```
## Technology Maturity Scoring

### TRL Assessment Criteria (from MKB)
| TRL | Definition | Evidence Required | Industry Benchmark |
|-----|------------|-------------------|-------------------|
| 1   | Basic principles observed | Published research | Emerging tech |
| 3   | Experimental proof of concept | Lab validation paper | Pre-seed stage |
| 5   | Validated in relevant environment | Prototype demo | Pilot project |
| 7   | System prototype in operational environment | Field trial data | Early commercial |
| 9   | System proven in operational environment | Commercial deployment | Mature market |

### {industry} Industry Benchmarks (from IKB)
- Average R&D intensity: 8.5% of revenue
- Patent filing growth rate: 15.2% YoY
- Technology adoption cycle: 3-5 years from demo to mass adoption
- Key technology nodes: {specific to industry}

### Writing Quality Standard (from Exemplar)
- Each TRL assessment MUST include specific evidence (not just "TRL 7")
- Technology comparison MUST include at least 3 competing alternatives
- Timeline projection MUST explicitly state assumptions
```

---

## 三、质量评分体系升级

### 3.1 当前评分体系问题总结

```
当前评分 = 形式检查（关键词存在性） + 数据密度（数量） + 问题惩罚（规则匹配）
```

**评分上限分析**：
- 即使内容极好，如果没使用标准关键词，结构分最多 70 分
- 即使内容空洞，如果使用了所有关键词 + 足够数字，可获得 80+ 分
- 这解释了为什么很多章节卡在 40-60 分——**评分与质量不相关**

### 3.2 新型评分体系设计

#### 三层语义评估

```python
class SemanticQualityScorer:
    """
    三层语义质量评分器
    
    Layer 1: 形式检查（30%）— 快速过滤
    Layer 2: 方法评估（40%）— 分析框架使用质量
    Layer 3: 深度评估（30%）— 逻辑链、洞察力
    """
    
    def score_section(self, content: str, section_type: str, 
                      framework: AnalyticalFramework) -> SectionScore:
        # Layer 1: 形式检查
        structure_score = self.check_analysis_structure(content, section_type)
        
        # Layer 2: 方法评估
        methodology_score = self.assess_methodology_application(
            content, framework
        )
        
        # Layer 3: 深度评估
        depth_score = self.assess_analytical_depth(content)
        
        # 加权合成
        final = structure_score * 0.3 + methodology_score * 0.4 + depth_score * 0.3
        return SectionScore(final, {
            "structure": structure_score,
            "methodology": methodology_score,
            "depth": depth_score,
        })
```

#### Layer 1: 形式检查（30%）— 增强版

不再仅检查关键词存在，而是检查**分析要素完整性**：

```python
def check_analysis_structure(self, content: str, section_type: str) -> float:
    """
    检查分析结构完整性
    
    不同章节类型有不同的分析要素清单：
    - market_size: 市场总量 + 增长驱动 + 结构分析 + 数据交叉验证
    - competition: 集中度 + 壁垒 + 战略分组 + 竞争趋势
    - technology: 技术路线 + 成熟度 + 专利分析 + 商业化
    """
    required_elements = self.get_analysis_elements(section_type)
    
    found = 0
    for element in required_elements:
        # 检查该要素是否被充分覆盖（不仅是关键词，而是有实质内容）
        if self._element_is_adequately_covered(content, element):
            found += 1
    
    return (found / len(required_elements)) * 100
```

#### Layer 2: 方法评估（40%）

评估 Agent 是否正确应用了分析方法论：

```python
def assess_methodology_application(
    self, content: str, framework: AnalyticalFramework
) -> float:
    """
    评估分析方法论的应用质量
    
    1. 是否选择了合适的框架？
    2. 框架是否被正确应用？
    3. 是否有数据支撑框架分析？
    4. 是否有反证/边界条件？
    """
    score = 0.0
    
    # 检查框架组件覆盖率
    for component in framework.components:
        if self._component_is_applied(content, component):
            score += component.weight * 100  # 各组件有不同权重
    
    # 检查数据支撑
    data_quality = self._assess_data_support(content, framework)
    
    # 检查逻辑一致性
    logic_quality = self._assess_logic_chain(content)
    
    return (score + data_quality + logic_quality) / 3
```

#### Layer 3: 深度评估（30%）

评估分析的真正深度——这需要 LLM 辅助：

```python
async def assess_analytical_depth(self, content: str) -> float:
    """
    深度评估（LLM辅助）
    
    评估维度：
    1. 洞察力：是否超越表面数据，有独特见解
    2. 逻辑链：推理是否完整严密
    3. 数据批判：是否评估了数据质量、局限性
    4. 前瞻性：是否有前瞻性判断（不是只是描述现状）
    5. 可验证性：结论是否可被验证或证伪
    """
    prompt = self._build_depth_assessment_prompt(content)
    llm_judge = LLMJudge()
    result = await llm_judge.evaluate(prompt)
    return result.score
```

### 3.3 知识反馈循环

```
写作 → 评分 → 剖析 → 入库 → 改进
  │      │       │        │       │
  │      │       │        └── 低分问题存入 LearningManager
  │      │       │           高分示例存入 MKB (WritingExemplars)
  │      │       │
  │      │       └── 剖析为什么高分/低分
  │      │
  │      └── 新评分体系给出多维评分
  │
  └── Agent 使用增强后的方法论知识
```

关键反馈机制：**每当一个章节获得 80+ 分，自动将其存为写作示例**，供后续 Agent 参考：

```python
# 在评分流程完成后自动触发
async def on_section_scored(section_result, score: float):
    if score >= 80:
        # 存入方法论知识库作为示例
        exemplar = WritingExemplar(
            section_type=section_result.section_type,
            industry=section_result.industry,
            score=score,
            content=section_result.content,
            analysis=section_result.quality_details,
            methodology_used=section_result.methodologies_used
        )
        await methodology_knowledge_base.store_exemplar(exemplar)
    
    elif score < 60:
        # 存入学习管理器
        await learning_manager.record_quality_issue(
            section_type=section_result.section_type,
            score=score,
            weak_dimensions=section_result.weak_dimensions,
            suggestion=self._generate_improvement_suggestion(section_result)
        )
```

---

## 四、实施路线图

### Phase 1（2 周）：方法论知识库建设

| 任务 | 详细内容 | 文件/模块 |
|------|----------|----------|
| MKB 数据模型 | 设计 `AnalyticalFramework`、`WritingExemplar` 等数据类 | `src/core/methodology/models.py` |
| MKB 存储层 | 基于 SQLite + JSON 的存储实现 | `src/core/methodology/store.py` |
| Framework 入库 | 将 Agent prompt 中的框架转为结构化知识 | `data/knowledge/methodology/frameworks/` |
| 框架注入器 | 实现 `MethodologyInjector` | `src/core/methodology/injector.py` |

### Phase 2（2 周）：评分体系升级

| 任务 | 详细内容 | 文件/模块 |
|------|----------|----------|
| 三层评分器 | 实现 `SemanticQualityScorer` | `src/core/quality/semantic_scorer.py` |
| Layer 1 增强 | 分析要素完整性检查 | `src/core/quality/layer1_structure.py` |
| Layer 2 实现 | 方法论应用质量评估 | `src/core/quality/layer2_methodology.py` |
| Layer 3 实现 | LLM 深度评估 | `src/core/quality/layer3_depth.py` |

### Phase 3（2 周）：Agent 增强

| 任务 | 详细内容 | 文件/模块 |
|------|----------|----------|
| 方法论查询 Skill | Agent 查询 MKB 的 Skill | `src/skills/business/methodology_skill.py` |
| 动态 Prompt 组装 | 整合 MKB 知识到 Agent prompt | `src/core/agents/prompt_assembler.py` |
| 写作示例注入 | 高评分示例作为上下文 | `src/core/agents/exemplar_injector.py` |

### Phase 4（持续）：知识反馈循环

| 任务 | 详细内容 | 文件/模块 |
|------|----------|----------|
| 自动入库示例 | 80+ 分章节自动转为 exemplar | `src/core/quality/feedback_loop.py` |
| 低分改进建议 | 60- 分章节生成改进方案 | `src/core/quality/improvement_advisor.py` |
| 评估指标跟踪 | Dashboard 显示评分变化趋势 | `web/src/components/quality/` |

---

## 五、预期效果

### 评分预期提升

| 维度 | 当前（平均） | Phase 1 后 | Phase 2 后 | Phase 3 后 |
|------|------------|-----------|-----------|-----------|
| 章节结构评分 | 55 | 70 | 80 | 90 |
| 分析方法评分 | 50 | 65 | 80 | 90 |
| 分析深度评分 | 45 | 55 | 70 | 85 |
| 数据质量评分 | 50 | 65 | 75 | 85 |
| **综合评分** | **50** | **66** | **78** | **88** |

### 核心提升逻辑

```
评分低（40-60）的根本原因不是"Agent 不努力"
而是：
1. Agent 不知道行业分析的专业标准 → 注入方法论知识库
2. Agent 没有高质量示例可参考 → 注入写作示例
3. 评分体系不反映真实质量 → 三层语义评估
4. 没有持续改进机制 → 知识反馈循环

当这四个问题都解决后，80-100 分是可达的。
```

---

## 附录：关键文件索引

| 文件 | 作用 |
|------|------|
| `src/agents/fixed_agents/quality_check_agent.py` | 章节质检、评分主逻辑（_calculate_section_score, check_by_sections）|
| `src/core/quality/checkers.py` | 三级质检器（DataCollection/Analysis/Report）|
| `src/core/quality/metadata_extractor.py` | 数据质量元数据提取器 |
| `src/core/memory/core/expertise_profile.py` | 专业画像数据结构 |
| `src/core/memory/core/rapid_evolver.py` | 快速进化器（领域/实体/术语提取）|
| `src/core/memory/knowledge_manager.py` | 知识管理统一入口 |
| `src/core/memory/knowledge_bank.py` | 知识银行（三层记忆架构核心）|
| `src/core/agents/generic_agent.py` | 动态 Agent 实现 |
| `prompts/agents/*.md` | 24 个 Agent 角色提示词 |
| `config/research_frameworks.yaml` | 研究框架配置（章节权重、搜索策略）|
| `src/core/quality/llm_judge.py` | LLM 评审（当前未用于章节评分）|
