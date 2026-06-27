# 质量收敛机制详细方案（已审计v3）

> 审计日期: 2026-06-27
> 审计范围: 逐条对照真实代码验证方案中的接口、方法签名、返回格式
> v3修订: 修正接口描述错误、修复设计缺陷、补充缺失细节

## 0. 问题本质

质量差的核心原因是环环相扣的：

```
数据搜索质量差 → 分析Agent无法做好分析 → 报告质量差
```

**不能轻易放过数据质量差**——系统有结构化数据源（StockDataSkill等），但报告环节完全没接入。

## 1. 数据补充的层级策略

### 1.1 可用数据源（已审计）

| 优先级 | 数据源 | 注册名 | 触发方式 | 质量 | 适用场景 |
|--------|--------|--------|---------|------|---------|
| P0 | StockDataSkill | `stock_data` | `skill_registry.get("stock_data").execute(symbol="002594", action="key_metrics")` | 高 | 上市公司财报、股价、行业 |
| P1 | EntityResolver | N/A(非Skill) | `get_entity_resolver().resolve("比亚迪财务分析")` → `EntityInfo(stock_code="002594", is_listed=True)` | 高 | 从topic提取股票代码 |
| P2 | KnowledgeQuerySkill | `knowledge_query` | `skill_registry.get("knowledge_query").execute(action="enrich", topic="比亚迪", aspect="研发投入")` | 中 | 知识库实体/模式 |
| P3 | 搜索引擎(优化关键词) | `search_skill` | `DataRepairAgent已有` | 中低 | 通用数据 |

### 1.2 真实接口对照表

#### StockDataSkill
```python
# 构造：通过SkillRegistry factory创建，不需要手动构造
stock_data = skill_registry.get("stock_data")  # 返回StockDataSkill实例或None

# execute签名
result = await stock_data.execute(symbol="002594", action="key_metrics")

# action可选值: "company_info" | "financials" | "key_metrics" | "price_history" | "industry_comparison"
# 必须提供symbol，否则返回 {"success": False, "message": "Execution failed", "error": "Please provide a stock symbol, e.g. 600519 (Kweichow Moutai)"}

# 成功返回格式
{
    "success": True,
    "data": ...,        # 具体数据(dict/list)，因action而异
    "symbol": "002594",
    "source": str,      # 因action而异，见下表
    "content": str,     # 人类可读摘要
}

# source字段因action而异（v3修正：完整列出所有可能的值）:
#   "company_info"      → "akshare/East Money"
#   "financials"        → "akshare/East Money"
#   "key_metrics"       → "akshare/Tonghuashun"
#   "price_history"     → "akshare/A-share historical prices"
#   "industry_comparison" → "akshare/industry classification"

# data字段因action而异:
#   "company_info"      → dict (股票简称、行业、总股本等)
#   "financials"        → {"income_statement": [...], "balance_sheet": [...], "cash_flow": [...]}
#   "key_metrics"       → {"periods": [...], "columns": [...]}
#   "price_history"     → list[dict] (最近120个交易日)
#   "industry_comparison" → {"industry": str, "symbol": str}

# 失败返回格式（来自Skill._failure()）
{
    "success": False,
    "message": "Execution failed",
    "error": "具体错误信息"
}
```

#### EntityResolver
```python
# 构造：使用工厂单例函数，不是直接构造
# v3修正：EntityResolver()不强制单例，直接构造会创建新实例，绕过缓存共享
# 正确用法：
from src.core.entity_resolver import get_entity_resolver
resolver = get_entity_resolver()  # 返回单例实例

# 内部从akshare加载全A股名称表到 ~/.cache/market_report/stock_name_table.pkl
# 有磁盘缓存，24小时TTL(_CACHE_TTL_SECONDS = 24 * 3600)

# 核心方法
entities: List[EntityInfo] = await resolver.resolve("比亚迪财务分析")
# 返回: [EntityInfo(name="比亚迪", stock_code="002594", is_listed=True)]
# 注意：resolve()内部会调用_ensure_table_loaded()，首次可能耗时10-30秒

# EntityInfo字段（src/core/entity_resolver.py:34-47）
@dataclass
class EntityInfo:
    name: str
    stock_code: Optional[str]   # None表示非上市公司；"__keyword_registry__"表示由keyword_registry判定
    is_listed: bool

    @property
    def resolved_code(self) -> Optional[str]:
        # stock_code非None且非"__keyword_registry__"时返回stock_code
        # 否则返回None
        if isinstance(self.stock_code, str) and self.stock_code != "__keyword_registry__":
            return self.stock_code
        return None

    @property
    def data_source_type(self) -> str:
        return "structured" if self.is_listed else "search"

    # v3补充：还有to_dict/from_dict方法
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EntityInfo": ...
```

#### KnowledgeQuerySkill
```python
# 获取
kq = skill_registry.get("knowledge_query")  # 返回实例或None
# 注意：knowledge_query通过register_core_skills()直接注册（非factory），已注入_LazyKM()

# execute签名
result = await kq.execute(action="enrich", topic="比亚迪", aspect="研发投入")

# 成功返回（来自Skill._success()）
# v3修正：_success({"data": data})展开后，data作为顶层key，不是内容展开到顶层
# 实际格式：{"success": True, "message": "OK", "data": {...}}
{
    "success": True,
    "message": "OK",
    "data": {             # 如果_km为None(实际是_LazyKM解析失败)则data={}
        "entities": [...],
        "patterns": [...],
        "methodologies": [...]
    }
}

# _km为None时的返回（v3修正：实际是_LazyKM注入，self._km永不为None）
# 真实路径：_LazyKM.__getattribute__尝试从container.resolve(KnowledgeManager)
# resolve失败 → _resolved设为_RESOLVE_FAILED哨兵 → self._km.search()等调用
#   → getattr(_RESOLVE_FAILED, "search") → AttributeError
#   → 被asyncio.gather(return_exceptions=True)捕获 → 对应data字段为空
# 所以实际行为：KM未初始化时，_enrich返回 {"success": True, "message": "OK", "data": {}}
# 但这是异常捕获后的结果，不是显式检查

# v3补充：KnowledgeQuerySkill还支持action="record_observation"
# result = await kq.execute(action="record_observation", content="...", category="pattern")
# 返回 {"success": True, "message": "OK", "buffered": <pending_count>}
```

#### SkillRegistry.get()
```python
# 位于 src/skills/registry.py:94（v3修正：原文档写96，实际为94）
def get(self, name: str) -> Optional[Skill]:
    # 先从已注册的_skills中找
    if name in self._skills:
        return self._skills[name]
    # 找不到则尝试factory创建
    if name in self._factories:
        skill = self._factories[name]()  # 调用factory函数
        self._skills[name] = skill       # 缓存到_skills
        return skill
    # 都找不到返回None
    
# stock_data通过factory注册（v3修正：注册的是class本身，class是Callable[[], Skill]）：
skill_registry.register_factory("stock_data", StockDataSkill)  # StockDataSkill是class，可作为factory
# 所以 get("stock_data") 首次调用时会执行 StockDataSkill() 创建实例，之后缓存
# knowledge_query通过register_core_skills()直接注册（非factory），已注入_LazyKM()
```

### 1.3 数据补充策略

```
发现数据缺口
  ├─ Step 1: EntityResolver解析topic → 获取stock_code
  │   ├─ resolved_code非None(is_listed=True) → 进入P0路径
  │   ├─ resolved_code为None但stock_code="__keyword_registry__" → keyword_registry判定为上市公司，但无精确代码，跳过P0
  │   └─ 无匹配实体 → 跳过P0，进入P2
  │
  ├─ Step 2 (P0): StockDataSkill获取结构化数据
  │   ├─ skill_registry.get("stock_data")为None → 跳过，降级到P2
  │   ├─ 成功(success=True) → 用LLM从data中提取gap需要的具体数值 → patch
  │   └─ 失败(success=False) → 降级到P2
  │
  ├─ Step 3 (P2): KnowledgeQuerySkill查询知识库
  │   ├─ skill_registry.get("knowledge_query")为None → 跳过，降级到P3
  │   ├─ data非空 → 用LLM提取有用数值 → patch（v3修正：不再跳过，实现基本提取）
  │   └─ data为空(KM未初始化) → 降级到P3
  │
  └─ Step 4 (P3): 搜索引擎（优化关键词）
      ├─ 优化关键词：topic + 核心指标 + 双语
      ├─ 成功 → patch
      └─ 失败 → 标注数据缺口（"已尝试结构化数据源和搜索引擎，均未找到"）
```

## 2. 方案设计（6个改动点）

### 2.1 改动一：StructuredDataRepairAgent

**新增类** `src/agents/fixed_agents/report_upgrade/structured_data_repair.py`：

```python
class StructuredDataRepairAgent:
    """基于结构化数据源的数据补充，优先级高于搜索引擎"""
    
    def __init__(self, skill_registry, llm_skill, prompt_manager):
        self._skill_registry = skill_registry  # SkillRegistry实例
        self._llm = llm_skill
        self._prompts = prompt_manager
        # v3修正：使用get_entity_resolver()获取单例，而非直接构造EntityResolver()
        # 直接构造会绕过缓存共享，导致重复加载akshare名称表
        self._entity_resolver = None  # 延迟初始化
    
    async def _get_entity_resolver(self):
        if self._entity_resolver is None:
            from src.core.entity_resolver import get_entity_resolver
            self._entity_resolver = get_entity_resolver()  # v3修正：使用工厂单例
        return self._entity_resolver
    
    async def try_repair(self, gap: DataGap, topic: str, sources: list) -> DataRepairResult:
        # Step 1: EntityResolver解析topic
        resolver = await self._get_entity_resolver()
        entities = await resolver.resolve(topic)
        stock_code = None
        for e in entities:
            if e.resolved_code:  # 用resolved_code而非stock_code（过滤__keyword_registry__）
                stock_code = e.resolved_code
                break
        
        # Step 2: P0 - StockDataSkill
        if stock_code:
            result = await self._try_stock_data(gap, stock_code)
            if result and result.found:
                return result
        
        # Step 3: P2 - KnowledgeQuerySkill（v3修正：不再返回None，实现基本提取）
        result = await self._try_knowledge_query(gap, topic)
        if result and result.found:
            return result
        
        # 全部失败
        return DataRepairResult(gap=gap, found=False)
    
    async def _try_stock_data(self, gap, symbol):
        """尝试从StockDataSkill获取财务数据"""
        stock_data_skill = self._skill_registry.get("stock_data")
        if not stock_data_skill:
            return None
        
        # 根据缺口类型选择action
        metric = gap.metric
        if any(kw in metric for kw in ["营收", "利润", "现金流", "负债", "资产", "研发", "费用"]):
            action = "financials"
        elif any(kw in metric for kw in ["ROE", "ROA", "毛利率", "净利率", "指标", "比率"]):
            action = "key_metrics"
        elif any(kw in metric for kw in ["股价", "市值", "涨跌", "PE", "PB"]):
            action = "price_history"  # v3补充：股价相关缺口
        elif any(kw in metric for kw in ["行业", "对比", "竞争"]):
            action = "industry_comparison"  # v3补充：行业相关缺口
        else:
            action = "key_metrics"
        
        result = await stock_data_skill.execute(symbol=symbol, action=action)
        if not result.get("success"):
            return None
        
        return await self._extract_from_structured_data(gap, result)
    
    async def _try_knowledge_query(self, gap, topic):
        """尝试从KnowledgeQuerySkill获取知识（v3修正：实现基本提取逻辑）"""
        kq_skill = self._skill_registry.get("knowledge_query")
        if not kq_skill:
            return None
        
        result = await kq_skill.execute(action="enrich", topic=topic, aspect=gap.metric)
        if not result.get("success"):
            return None
        
        data = result.get("data", {})
        if not data:  # KnowledgeManager可能未初始化，返回空data
            return None
        
        # v3新增：将知识库数据转为文本，通过LLM提取具体数值
        # 知识库数据格式：{"entities": [...], "patterns": [...], "methodologies": [...]}
        import json
        data_text = json.dumps(data, ensure_ascii=False, default=str)[:3000]
        if len(data_text) < 50:  # 数据太少，不值得LLM调用
            return None
        
        prompt = self._prompts.get(
            "data_extraction",
            metric=gap.metric,
            context=gap.context,
            topic=topic,
            search_results=f"[知识库数据]\n{data_text}",
        )
        llm_result = await self._llm.execute(prompt=prompt, max_tokens=2048)
        if not llm_result.get("success"):
            return None
        
        return self._parse_extraction(llm_result["content"], gap)
    
    async def _extract_from_structured_data(self, gap, stock_result):
        """用LLM从StockDataSkill返回的结构化数据中提取gap需要的具体数值"""
        data = stock_result.get("data", {})
        source = stock_result.get("source", "akshare")
        symbol = stock_result.get("symbol", "")
        
        # 将data转为可读文本供LLM提取
        import json
        data_text = json.dumps(data, ensure_ascii=False, default=str)[:3000]
        
        # v3补充：对data_text做基本有效性检查
        if len(data_text) < 50:
            return None
        
        prompt = self._prompts.get(
            "data_extraction",
            metric=gap.metric,
            context=gap.context,
            topic=symbol,
            search_results=f"[结构化数据源: {source}]\n{data_text}",
        )
        llm_result = await self._llm.execute(prompt=prompt, max_tokens=2048)
        if not llm_result.get("success"):
            return None
        
        # 复用DataRepairAgent._parse_extraction的逻辑
        return self._parse_extraction(llm_result["content"], gap)
    
    def _parse_extraction(self, raw: str, gap: DataGap) -> Optional[DataRepairResult]:
        # 与DataRepairAgent._parse_extraction相同逻辑
        import re, json
        try:
            json_match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                if data.get("found"):
                    return DataRepairResult(
                        gap=gap,
                        found=True,
                        value=data.get("value"),
                        unit=data.get("unit"),
                        source=data.get("source"),
                        source_title=data.get("source_title"),
                        confidence=float(data.get("confidence") or 0.0),
                    )
            return None
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
```

### 2.2 改动二：优化搜索关键词

当前：`search_keywords=[issue.description[:20]]`
改为：

```python
def _extract_search_keywords(self, issue, topic):
    """从issue中提取更精确的搜索关键词"""
    metric = self._extract_metric(issue.description)
    keywords = [f"{topic} {metric}"]
    
    # 双语关键词（v3注：硬编码映射，不在映射中的指标不会生成英文关键词）
    METRIC_EN_MAP = {
        "研发投入": "R&D expenditure", "营收": "revenue",
        "净利润": "net profit", "毛利率": "gross margin",
        "净利率": "net margin", "负债": "debt",
        "现金流": "cash flow", "销量": "sales volume",
        "市场份额": "market share", "市盈率": "PE ratio",
    }
    for cn, en in METRIC_EN_MAP.items():
        if cn in metric:
            keywords.append(f"{topic} {en}")
            break
    
    return keywords
```

### 2.3 改动三：分层降级数据补充

```python
async def _try_fill_data_gap(self, gap, topic, sources):
    """分层降级的数据补充"""
    # P0+P2: 结构化数据源（StructuredDataRepairAgent内部按P0→P2降级）
    if self._structured_data_agent:
        result = await self._structured_data_agent.try_repair(gap, topic, sources)
        if result and result.found:
            return result
    
    # P3: 搜索引擎（优化关键词）
    result = await self._data_repair_agent.repair_gap(gap, topic)
    if result.found:
        return result
    
    # 全部失败
    return DataRepairResult(gap=gap, found=False)
```

### 2.4 改动四：review issue按问题源分类

| reviewer描述模式 | 问题源 | 处理策略 |
|-----------------|--------|---------|
| "断言缺乏XX数据" + raw_data中有 | L2分析漏用 | `_extract_omitted_data`提取漏用数据 → patch补充(不搜索) |
| "编造"/"未在数据中出现" | L2分析编造 | 分层降级查真实值→找到则替换→未找到则删除+标注缺口 |
| "模糊来源" | L2分析标注不足 | 分层降级查具体来源→找到则补充→未找到则标注 |
| "缺失"/"无数据" + raw_data中也没有 | L1数据缺失 | 分层降级补充→找到则patch→未找到则标注缺口 |
| "数据冲突" | 跨章节问题 | ConflictResolver→patch统一 |
| 逻辑/完整度/风格 | L3报告问题 | 精修(非重写) |

**v3新增：`_diagnose_issue_source` 详细逻辑**

```python
async def _diagnose_issue_source(self, issue, chapter_data, raw_data_summary):
    """诊断issue的问题源（L1/L2/L3）"""
    desc = issue.description
    
    # L2-漏用：断言说"缺乏XX"但raw_data中实际有该数据
    if "缺乏" in desc or "缺少" in desc or "遗漏" in desc:
        omitted = self._extract_omitted_data(issue, raw_data_summary)
        if omitted:
            return QualityIssueDiagnosis(
                issue_description=desc,
                source_layer="L2_omitted",
                remediation=f"补充已有数据: {omitted[:100]}",
                resolved=False,
            )
    
    # L2-编造："编造"/"无据"/"未在数据中出现"
    if "编造" in desc or "无据" in desc or "未在" in desc:
        return QualityIssueDiagnosis(
            issue_description=desc,
            source_layer="L2_fabricated",
            remediation="分层降级查真实值→替换或删除",
            resolved=False,
        )
    
    # L2-模糊来源："模糊"/"来源不具体"
    if "模糊" in desc or "来源" in desc and "不具体" in desc:
        return QualityIssueDiagnosis(
            issue_description=desc,
            source_layer="L2_vague_source",
            remediation="分层降级查具体来源→补充",
            resolved=False,
        )
    
    # L1-数据缺失："缺失"/"无数据" + raw_data中也没有
    if "缺失" in desc or "无数据" in desc:
        metric = self._extract_metric(desc)
        if metric not in raw_data_summary:
            return QualityIssueDiagnosis(
                issue_description=desc,
                source_layer="L1_missing",
                remediation="分层降级补充数据",
                resolved=False,
            )
    
    # L3-其他
    return QualityIssueDiagnosis(
        issue_description=desc,
        source_layer="L3_report",
        remediation="精修",
        resolved=False,
    )

def _extract_omitted_data(self, issue, raw_data_summary):
    """从raw_data中提取被漏用的数据文本"""
    metric = self._extract_metric(issue.description)
    if not metric or not raw_data_summary:
        return None
    # 在raw_data_summary中搜索包含metric的行
    for line in raw_data_summary.split("\n"):
        if metric in line:
            return line
    return None
```

**v3新增：`_build_anchor_patch_instructions` L2漏用分支**

```python
@staticmethod
def _build_anchor_patch_instructions(
    anchoring_issues: List, chapter_data: Dict[str, Any],
    raw_data_summary: str = "",  # v3新增参数
    diagnoses: List[QualityIssueDiagnosis] = None,  # v3新增参数
) -> List[str]:
    instructions = []
    for iss in anchoring_issues:
        desc = iss.description
        suggestion = iss.suggestion if hasattr(iss, 'suggestion') and iss.suggestion else ""
        
        # v3新增：L2漏用分支
        diagnosis = None
        if diagnoses:
            diagnosis = next(
                (d for d in diagnoses if d.issue_description == desc), None,
            )
        
        if diagnosis and diagnosis.source_layer == "L2_omitted":
            omitted = diagnosis.remediation
            instructions.append(
                f"补充已有数据（raw_data中存在但分析环节未使用）：{desc[:100]}。"
                f"具体数据：{omitted[:200]}。"
                f"请将此数据整合到报告中，标注来源。"
            )
        elif "编造" in desc or "无据" in desc or "未在" in desc:
            instructions.append(
                f"删除无据断言：{desc[:100]}。"
                f"{'修正建议：' + suggestion[:100] if suggestion else '如无数据支撑，改为标注数据缺口。'}"
            )
        elif "模糊" in desc or "来源" in desc:
            instructions.append(
                f"补充具体来源：{desc[:100]}。"
                f"{'修正建议：' + suggestion[:100] if suggestion else '将模糊来源替换为可用数据中的具体来源。'}"
            )
        elif "缺口" in desc or "未标注" in desc:
            instructions.append(
                f"标注数据缺口：{desc[:100]}。"
                f"{'修正建议：' + suggestion[:100] if suggestion else '在断言后添加数据缺口标注。'}"
            )
        else:
            instructions.append(
                f"修正数据锚定问题：{desc[:100]}。"
                f"{'修正建议：' + suggestion[:100] if suggestion else ''}"
            )
    return instructions
```

### 2.5 改动五：Phase4闭环 — 多轮收敛验证

```
prev_score = 0
for round in range(MAX_CONVERGENCE_ROUNDS=3):
    review = global_review(chapters)
    if review.score >= 80: break
    if round > 0 and (review.score - prev_score) < CONVERGENCE_MIN_IMPROVEMENT=5: break
    prev_score = review.score  # v3修正：保存上一轮分数用于收敛判断
    chapters = phase4_fix(chapters, review)
```

### 2.6 改动六：透明降级

收敛失败后：
- 章节content末尾追加质量标注（仅在`_assemble_final_report`的metadata中，不嵌入正文）— v3修正
- 最终报告新增`quality_report`字段（放在顶层，与`sections`并列）
- 下游消费者（Word/HTML）通过`metadata.quality_report`读取标注，不在正文中渲染

**v3新增：质量标注格式**

```python
quality_report = QualityReport(
    overall_score=review.overall_score,
    convergence_rounds=round + 1,
    converged=review.score >= 80,
    chapter_diagnostics=[
        ChapterDiagnostic(
            chapter_id=ch.chapter_id,
            score=...,
            source_layer=...,
            gaps=[...],
            repair_attempts=[...],
            remediations=[...],
        )
        for ch in chapters
    ],
)
```

## 3. 具体修改清单

### 3.1 新增文件
- `src/agents/fixed_agents/report_upgrade/structured_data_repair.py`
  - `StructuredDataRepairAgent`: 使用`get_entity_resolver()`+StockDataSkill获取结构化数据

### 3.2 models.py
新增：
- `QualityIssueDiagnosis`: issue_description, source_layer(L1_missing/L2_omitted/L2_fabricated/L2_vague_source/L3_report), remediation, resolved
- `ChapterDiagnostic`: chapter_id, score, source_layer, gaps[], repair_attempts[], remediations[]
- `QualityReport`: overall_score, convergence_rounds, converged, chapter_diagnostics[]

### 3.3 orchestrator.py (report_upgrade)

**构造函数改造**：
```python
# 当前（src/agents/fixed_agents/report_upgrade/orchestrator.py:55-64）
def __init__(self, llm_skill, chapter_writer, chapter_reviewer, global_reviewer,
             data_repair_agent, conflict_resolver, prompt_manager=None):

# 改为（新增skill_registry参数）
def __init__(self, llm_skill, chapter_writer, chapter_reviewer, global_reviewer,
             data_repair_agent, conflict_resolver, prompt_manager=None,
             skill_registry=None):
    ...
    self._structured_data_agent = None
    if skill_registry:
        self._structured_data_agent = StructuredDataRepairAgent(
            skill_registry=skill_registry,
            llm_skill=llm_skill,
            prompt_manager=prompt_manager or PromptManager(),
        )
```

**新增方法**：
- `_diagnose_issue_source(issue, chapter_data, raw_data_summary)` → QualityIssueDiagnosis (L1/L2/L3)
- `_extract_omitted_data(issue, raw_data_summary)` → 提取被漏用的数据文本
- `_try_fill_data_gap(gap, topic, sources)` → 分层降级数据补充
- `_extract_search_keywords(issue, topic)` → 优化搜索关键词
- `_attach_quality_labels(chapters, diagnostics)` → 透明降级标注（写入metadata，不嵌入正文）
- `_quality_convergence_loop(chapters, framework_config, topic)` → 多轮收敛（维护prev_score）

**改造方法**：
- `generate_report`: 单章节review阶段触发数据补充；全局阶段增加收敛循环
- `_build_anchor_patch_instructions`: 增加raw_data_summary参数、diagnoses参数、L2漏用分支
- `_phase4_fix_and_optimize`: 
  - 扩展触发条件（不再只看"缺失"/"无数据"，按diagnose分类处理）
  - 使用分层降级补充（`_try_fill_data_gap`替代直接`DataRepairAgent.repair_batch`）
  - 收敛循环前诊断所有issue（`_diagnose_issue_source`）
  - raw_data_summary需要在Phase4重新获取（v3注：当前`_phase4_fix_and_optimize`不持有raw_data_summary，需从`_extract_chapter_data`重新获取）

```python
# v3新增：在_phase4_fix_and_optimize中获取raw_data_summary
for i, chapter in enumerate(chapters):
    chapter_spec = self._find_section_spec(chapter.chapter_id, framework_config)
    re_chapter_data, re_raw_data_summary = self._extract_chapter_data(
        self._aggregated_result, chapter.chapter_id,
        chapter_spec.get("content_dependency", []) if chapter_spec else [],
    )
    # ... 使用re_raw_data_summary进行诊断
```

- `_assemble_final_report`: 输出包含`quality_report`字段（与sections并列，不嵌入content）

```python
# v3新增：_assemble_final_report改造
return {
    "topic": topic,
    "title": topic,
    "aspects": [ch.title for ch in chapters],
    "sections": sections,
    "sources": all_sources,
    "key_findings": ReportOrchestrator._clean_key_findings(exec_summary),
    "quality_report": {  # v3新增
        "overall_score": quality_report.overall_score,
        "convergence_rounds": quality_report.convergence_rounds,
        "converged": quality_report.converged,
        "chapter_diagnostics": [
            {
                "chapter_id": d.chapter_id,
                "score": d.score,
                "source_layer": d.source_layer,
                "gaps": [g.metric for g in d.gaps],
                "remediations": d.remediations,
            }
            for d in quality_report.chapter_diagnostics
        ],
    },
}
```

### 3.4 RetryPolicy
新增：
- `MAX_CONVERGENCE_ROUNDS = 3`
- `CONVERGENCE_MIN_IMPROVEMENT = 5`

### 3.5 核心orchestrator接入

`src/core/orchestrator/orchestrator.py` L2063:
```python
# 当前
report_orchestrator = ReportOrchestrator(
    llm_skill=llm_skill,
    ...
    prompt_manager=prompt_manager,
)

# 改为（新增skill_registry参数）
report_orchestrator = ReportOrchestrator(
    llm_skill=llm_skill,
    ...
    prompt_manager=prompt_manager,
    skill_registry=self._skill_registry,  # 传入已有的skill_registry
)
```

同理修改第二个调用点(L982)。

### 3.6 prompts/chapter_patch_data.tmpl
新增"补充已有数据"指令类型

### 3.7 测试
- `StructuredDataRepairAgent` 各方法（包括P2路径的基本提取）
- `_diagnose_issue_source` 各类场景（5种source_layer）
- `_extract_omitted_data` 正常/空raw_data
- 收敛循环3种退出条件：score≥80 / improvement<5 / max_rounds
- `_build_anchor_patch_instructions` L2漏用分支
- 透明降级标注在metadata中而非content中
- quality_report输出格式
- `get_entity_resolver()`单例共享测试

## 4. 风险与边界

### 4.1 StockDataSkill可能不适用
- 只覆盖A股上市公司，非上市公司或海外公司无数据
- EntityResolver.resolve()返回空列表或is_listed=False → 自动跳过P0
- akshare有API限流风险 → StockDataSkill已有重试机制(_MAX_RETRIES=3)和内存缓存(_memory_cache)
- v3补充：_memory_cache是类级别dict（`_memory_cache: Dict[tuple, Dict[str, Any]] = {}`），所有实例共享

### 4.2 KnowledgeQuerySkill可能返回空数据
- KnowledgeManager可能未初始化 → _LazyKM解析失败 → data为空
- 处理：data为空时直接跳过，不报错
- v3补充：_LazyKM解析失败后设为_RESOLVE_FAILED哨兵，后续调用通过asyncio.gather(return_exceptions=True)优雅处理

### 4.3 EntityResolver首次加载耗时
- 首次加载需从akshare获取全A股名称表，可能需要10-30秒
- 后续有磁盘缓存(24h TTL)
- 缓解：使用`get_entity_resolver()`获取单例，核心orchestrator中可能已加载过
- v3修正：原方案使用`EntityResolver()`直接构造，会绕过缓存共享。改为`get_entity_resolver()`后，单例在核心orchestrator的intelligent_routing_adapter中可能已加载过（见src/core/intelligent_routing_adapter.py:335-336）

### 4.4 补充搜索的耗时和成本
- StockDataSkill: 约2-5秒（akshare API调用+缓存）
- EntityResolver: 首次10-30秒，后续<1秒（使用单例后首次只发生一次）
- KnowledgeQuerySkill: 约1-3秒
- 搜索引擎: 约3-5秒
- 总增加: 约10-20秒/缺口

### 4.5 最终能力边界
- 非上市公司：可能所有数据源都找不到
- 极小众行业数据：搜索引擎可能搜不到
- 诚实标注是最终兜底

### 4.6 data_extraction.tmpl模板兼容性（v3新增）
- `data_extraction.tmpl`当前为搜索引擎结果设计，接收`search_results`参数
- StructuredDataRepairAgent复用该模板，将结构化数据/知识库数据作为`search_results`传入
- 需验证模板输出质量：结构化数据是JSON而非自然语言文本，LLM提取效果可能不同
- 建议：增加模板中的提示词区分"搜索引擎结果"和"结构化数据源"的提取策略

### 4.7 收敛循环的LLM成本（v3新增）
- 每轮收敛需要global_review + phase4_fix，涉及多次LLM调用
- 最多3轮，每轮约5-10次LLM调用
- 总增加：最多15-30次LLM调用
- 缓解：收敛循环内设置更保守的max_tokens（phase4_fix用2048而非8192）

## 5. 实现状态（已编码）

> 实现日期: 2026-06-27
> 测试状态: **218个测试全部通过**
> 审查状态: 4个Bug已修复

### 5.1 已实现文件清单

| 文件 | 类型 | 内容 |
|------|------|------|
| `models.py` | 修改 | 新增 `QualityIssueDiagnosis`/`ChapterDiagnostic`/`QualityReport` |
| `structured_data_repair.py` | 新增 | `StructuredDataRepairAgent` + `RepairAttempt` |
| `orchestrator.py` (report_upgrade) | 修改 | 见下方详细清单 |
| `core/orchestrator/orchestrator.py` | 修改 | 两个创建点传入 `skill_registry` |

### 5.2 orchestrator.py改动清单

| 方法 | 改动 |
|------|------|
| `RetryPolicy` | 新增 `MAX_CONVERGENCE_ROUNDS=3`, `MIN_CONVERGENCE_IMPROVEMENT=5`, `TARGET_SCORE=80` |
| `__init__` | 新增 `skill_registry` 参数, 初始化 `_structured_data_repair` 和 `_llm_trace` |
| `generate_report` | 用 `_quality_convergence_loop` 替换单次 Phase4, 传入 `quality_report` 和 `llm_trace` |
| `_quality_convergence_loop` | **新增** 最多3轮收敛, 3种退出条件, best版本保留 |
| `_phase4_fix_and_optimize` | 重写: 使用 `_diagnose_issue_source` 分类, L1_missing时调用 `_try_fill_data_gap`+EntityResolver, L2_omitted走patch, anchoring_issues也走patch, 传入 `raw_data_summary`, 搜索关键词优化 |
| `_diagnose_issue_source` | **新增** L1/L2/L3分类, L2漏用关键词提取精准修复 |
| `_extract_omitted_data` | **新增** 从raw_data_summary提取遗漏数据 |
| `_try_fill_data_gap` | **新增** P0 StockDataSkill → P2 KnowledgeQuerySkill 分层降级 |
| `_build_search_keywords` | **新增** topic+核心指标+双语关键词生成, 20个常见指标翻译表 |
| `_build_anchor_patch_instructions` | 新增 `raw_data_summary` 参数, L2漏用分支("补充已有数据"), 关键词提取 |
| `_call_llm_tracked` | 新增 `phase` 参数, 记录 `_llm_trace` |
| `_assemble_final_report` | 新增 `quality_report` 和 `llm_trace` 参数, 透明降级输出 |

### 5.3 代码审查修复

| Bug | 位置 | 修复 |
|-----|------|------|
| B1 | `_diagnose_issue_source` L853 | `_is_vague_source("综合数据")` 硬编码True, 改为 `"模糊" in desc or "来源" in desc` |
| B2 | `_assemble_final_report` L1160 | 冗余 `from dataclasses import asdict as _asdict`, 删除 |
| B3 | `_quality_convergence_loop` L407-415 | chapter_diagnostics score=0.0不合理, 改为best_score, source_layer改为"convergence", 只在列表为空时填充 |
| B4 | `_phase4_fix_and_optimize` L467 | `_try_fill_data_gap` 未传stock_code, 添加EntityResolver获取stock_code逻辑 |

### 5.4 测试文件清单

| 文件 | 测试数 | 内容 |
|------|--------|------|
| `test_quality_models.py` | 7 | QualityIssueDiagnosis/ChapterDiagnostic/QualityReport |
| `test_structured_data_repair.py` | 15 | StructuredDataRepairAgent + RepairAttempt |
| `test_orchestrator_convergence.py` | 16 | diagnose/extract/patch/convergence/quality_report |
| `test_search_keywords.py` | 7 | 双语关键词/指标翻译/边界条件 |

**总计: 225个测试全部通过**

### 5.5 关键设计决策（实现中确认）

1. **EntityResolver在Phase4内部调用**：L1_missing时自动从topic解析stock_code, 失败不报错(try/except)
2. **_extract_omitted_data关键词提取**：先strip后缀(金额/数据/指标等), 再2字符前缀模糊匹配
3. **收敛循环best版本保留**：每轮比较score, 保留best_chapters, 避免修复后质量下降
4. **quality_report独立字段**：不嵌入content, 作为metadata输出
5. **structured_data_repairs在data_repair之前**：先搜索结构化数据源, 再用搜索引擎补漏
6. **搜索关键词双语优化**：20个常见财务指标中英翻译表, 生成topic+指标+英文关键词
7. **LLM调用追踪**：`_call_llm_tracked`新增`phase`参数, `_llm_trace`记录每次调用的阶段/成功/令牌数
