# Skill 动态加载修复方案

**日期**: 2026-06-24
**状态**: 已实施（FIX-1~4 全部完成，35 tests passing）
**关联**: `docs/system_log_analysis_2026-06-20.md` P0 — akshare 未调用 / 26 子章节数据不足

---

## 一、问题分析

### 1.1 当前架构

```
Orchestrator.__init__()                       ← 启动时一次性注册
  ├── register_core_skills()                  ← 9 个核心 skill（search, llm, web_scraper 等）
  ├── auto_discover_langchain_tools()         ← LangChain skill（tavily, arxiv, wikipedia, python_repl）
  ├── 7 个分析 skill 直接注入 _skills dict     ← market_analysis, stock_data 等（绕过 register()）
  └── 传给 DynamicAgentFactory
        │
        ├── create_agent_with_session(category)     ← 创建时按 category 加载
        │     └── load_skills_for_category()        ← 仅加载 lc_* LangChain skill
        │
        └── GenericAgent.execute()                  ← 运行时发现
              ├── ACTION_TO_SKILL 硬编码映射          ← action → skill_name
              ├── discover_skills(action)             ← 仅能发现 lc_* skill
              └── LLM fallback                        ← 可绕过 available_skills，但只用于搜索
```

### 1.2 每阶段 Skill 需求模型（核心）

**关键发现 1**：所有 agent 执行时 `action="execute"`（`engine.py:2125,2207`），统一映射到 `llm_skill`（`generic_agent.py:218`）。
`llm_skill` 内部按 `agent_category` 分支到不同阶段逻辑（`generic_agent.py:297-632`），每个分支执行后直接 `return`。

**关键发现 2**：分析 skill **不是通过 `ACTION_TO_SKILL` 直接调用的**，而是在 `llm_skill` 的阶段分支中通过 `available_skills` 检查间接使用。但由于 `action="execute"` 总是映射到 `llm_skill` 并在阶段分支中 `return`，`generic_agent.py:924` 的 `discover_skills` 路径**对正常执行流程不可达**。

因此，**"某阶段需要什么 skill"的本质是：该阶段的代码路径中，有哪些条件检查依赖 `_available_skills`**。

#### DATA_COLLECTION 阶段（category="research"）

**代码路径**：`generic_agent.py:300-387`

| 检查点 | 代码 | 需要 skill | 为什么需要 |
|--------|------|-----------|-----------|
| 结构化数据获取 | `if "stock_data" in available_skills` (304行) | `stock_data` | 调用 akshare 获取财务报表/股价等结构化数据 |
| 网络搜索 | `if "search_skill" in available_skills` (322行) | `search_skill` | 搜索网页获取非结构化数据 |
| 新闻搜索 | 隐含在 `llm_skill` 中 | `news_search` | 辅助搜索 |

**当前分配**：`_get_data_collection_skills()` → `["search_skill", "news_search", "llm_skill"]` + 条件追加 `["stock_data"]`

**结论**：DATA_COLLECTION 是**数据获取层**，需要的是能**主动获取数据**的 skill。`stock_data` 在此阶段被调用 `execute(action=..., symbol=...)` 获取原始数据。**不需要分析 skill**（如 `stock_analysis`），因为此阶段只收集不分析。

#### DATA_VALIDATION 阶段（category="quality-check"）

**代码路径**：`generic_agent.py:390-414`

| 检查点 | 代码 | 需要 skill | 为什么需要 |
|--------|------|-----------|-----------|
| 数据校验 | `_validate_collected_data(data_points, sources)` | `llm_skill` | 纯 LLM 校验，无额外 skill |

**当前分配**：`["llm_skill"]`

**结论**：DATA_VALIDATION 是**数据校验层**，纯 LLM 操作，不需要额外 skill。

#### DEEP_ANALYSIS 阶段（category="market-analysis"）

**代码路径**：`generic_agent.py:416-586`

| 检查点 | 代码 | 需要 skill | 为什么需要 |
|--------|------|-----------|-----------|
| 降级搜索 | `if "search_skill" in available_skills` (423行) | `search_skill` | 无上游数据时的降级搜索（**不应分配**，见下） |
| LLM 分析 | `skill.execute(prompt=prompt)` (517行) | `llm_skill` | 核心分析能力 |
| 补充搜索 | `_supplementary_search_for_gaps()` (543行) | 隐含在 `llm_skill` 中 | 检测知识缺口后补充 |

**当前分配**：`get_skills_for_aspect("Financial Analysis")` → `["llm_skill", "stock_analysis", "data_analysis"]`

**关键问题**：`stock_analysis` 和 `data_analysis` 被分配到 `available_skills` 中，**但代码中从未检查它们**！

DEEP_ANALYSIS 阶段的数据来源是：
1. `task.get("aggregated_data_points")` — 上游 DATA_COLLECTION 传入
2. `task.get("canonical_data")` — SharedMemory 中的校准数据
3. 降级搜索（当无上游数据时）

DEEP_ANALYSIS 阶段**不需要 `stock_data`**（因为数据已由 DATA_COLLECTION 阶段获取），也**不会直接调用 `stock_analysis`**（因为所有分析走 `llm_skill` 的 prompt 构建路径）。

#### SYNTHESIS 阶段（category="synthesis"）

**代码路径**：`generic_agent.py:634+`

纯 LLM 整合，不需要额外 skill。

### 1.3 Skill 使用方式分类

7 个分析 skill 按使用方式分为两类：

| 类别 | Skill | 使用方式 | 被谁调用 |
|------|-------|---------|---------|
| **数据获取型** | `stock_data` | `stock_skill.execute(action=..., symbol=...)` → 返回原始数据 | DATA_COLLECTION agent 直接调用（`generic_agent.py:305-308`） |
| **分析框架型** | `stock_analysis`, `market_analysis`, `data_analysis`, `policy_analysis`, `tech_trend`, `risk_analysis` | 通过 `get_skill_registry()` 自行获取 `llm_skill` 和 `lc_python_repl`，接受 `data_points`/`topic`/`aspect` 参数 | **当前未被任何代码路径调用** |

**核心矛盾**：6 个分析框架型 skill 被分配到 `available_skills` 中，但从未被 `llm_skill` 的阶段分支代码实际调用。它们存在的意义仅限于 `discover_skills()` 运行时发现路径——但该路径对正常执行流程不可达（见 1.2 节关键发现 2）。

### 1.4 两种修复策略

**策略 A：保持当前架构**——分析框架型 skill 仍分配到 `available_skills`，但实际不被调用
- 修复注册/验证/发现机制即可
- 不改变 `llm_skill` 内部的阶段分支逻辑
- **问题**：分析框架型 skill 在 `available_skills` 中是"死代码"，浪费理解成本

**策略 B：让 DEEP_ANALYSIS 阶段实际调用分析框架型 skill**
- 修改 `llm_skill` 的 DEEP_ANALYSIS 分支：在构建 prompt 前先调用对应分析 skill 的预计算层
- 分析框架型 skill 的三层架构（计算层 → 分析层 → 输出层）中，计算层和 system_prompt 可以被复用
- **好处**：`stock_analysis` 的 PythonREPL 精确计算（ROE/ROA/负债率）、`data_analysis` 的 CAGR/CR3/HHI 计算、`market_analysis` 的 SWOT/PEST 框架可以真正生效
- **问题**：改动更大，需要修改 `generic_agent.py` 的 DEEP_ANALYSIS 分支

**建议**：本次修复采用**策略 A**，确保注册/验证/发现机制正确。策略 B 作为后续优化单独规划。

### 1.5 数据流断裂点

| 断裂点 | 位置 | 现象 | 影响 |
|--------|------|------|------|
| **A** | `orchestrator.py:280-288` | 7 个分析 skill 直接赋值 `_skills` dict，绕过 `register()` | 不走正规注册路径，`discover_skills()` 找不到 |
| **B** | `factory.py:195` | `_validate_and_normalize_skills()` 只检查 `_skills` 不检查 `_factories` | 改为 factory 注册后 skill 被误判为 unknown 丢弃 |
| **C** | `registry.py:390-399` | `CATEGORY_TO_LANGCHAIN_SKILLS` 不含分析 skill | category 辅路径无法加载分析 skill |
| **D** | `skill_keywords.py:30-96` | `SKILL_KEYWORDS` 只覆盖 `lc_*` | `discover_skills()` 发现不了分析 skill |
| **E** | `generic_agent.py:151` | `_available_skills` 创建后不可变 | 运行时无法扩展 |
| **F** | `generic_agent.py:928` | `discover_skills` 发现的 skill 须在 `available_skills` 或以 `lc_` 开头 | 分析 skill 两个条件都不满足；但此分支对主流程不可达（`action="execute"` 总先匹配 `llm_skill`） |
| **G** | `research_api.py:59-168` | `ConversationToolSet` 独立实例化 skill | 脱离 SkillRegistry |

### 1.6 实际数据流路径

分析 skill 的主分配路径**不是** category 映射，而是：

```
ASPECT_SKILL_MAP (strategies.py:41-67)
  → AgentSpec.skills (strategies.py:475 / 527)
    → AgentCapability.required_skills (orchestrator.py:3484)
      → _validate_and_normalize_skills() (factory.py:195)  ← 断裂点 B
        → agent._available_skills (factory.py:269 → generic_agent.py:151)
```

### 1.7 具体影响

**场景 1：DATA_COLLECTION 阶段 — `stock_data` 被 factory 验证丢弃（主路径）**

```
strategies.py: _get_data_collection_skills("Financial Analysis")
  → ["search_skill", "news_search", "llm_skill", "stock_data"]
  → AgentSpec.skills → AgentCapability.required_skills

factory.py:195: _validate_and_normalize_skills()
  → 改为 register_factory 后: "stock_data" 在 _factories 不在 _skills → 判定 unknown → 丢弃
  → ❌ agent._available_skills 中无 "stock_data"
  → generic_agent.py:304: if "stock_data" in available_skills → False → akshare 从未调用
```

**场景 2：DEEP_ANALYSIS 阶段 — 分析 skill 被 factory 验证丢弃**

```
strategies.py: get_skills_for_aspect("Financial Analysis")
  → ["llm_skill", "stock_analysis", "data_analysis"]
  → AgentSpec.skills → AgentCapability.required_skills

factory.py:195: _validate_and_normalize_skills()
  → "stock_analysis" 在 _factories 不在 _skills → 判定 unknown → 丢弃
  → ❌ agent._available_skills = ["llm_skill"]  ← 丢失 stock_analysis, data_analysis
```

> **注**：当前即使 `stock_analysis` 在 `available_skills` 中，也不会被 DEEP_ANALYSIS 代码路径调用
> （见 1.2 节分析）。但修复注册/验证机制是后续让分析 skill 真正生效的前提。

**场景 3：运行时智能发现找不到分析 skill**

```
discover_skills("financial data", auto_load=True)
  → match_skills → SKILL_KEYWORDS 中无分析 skill → 只返回 ["llm_skill"]
  → ❌ 发现不了 stock_data / stock_analysis
```

---

## 二、修复方案

### FIX-1：分析 skill 走 `register_factory()` 懒加载 + `_validate_and_normalize_skills` 修复

**优先级**: P0（原子变更，不可分步）
**文件**: `src/core/orchestrator/orchestrator.py:276-289`, `src/core/agents/factory.py:195`

> **⚠️ 不可分步原因**：`register_factory` 改动与 `_validate_and_normalize_skills` 修复必须同时上线。
> 否则 7 个分析 skill 从 `_skills` 移到 `_factories` 后被验证丢弃，**比当前状态更严重**。

**现状**:
```python
# orchestrator.py:280-288 — 直接赋值，绕过 register()
skill_registry._skills["market_analysis"] = MarketAnalysisSkill()
skill_registry._skills["stock_data"] = StockDataSkill()
# ... 其余 5 个同理

# factory.py:195 — 只查 _skills
registered_names = set(self._skill_registry._skills.keys())
```

**修复 A — orchestrator.py 改用 register_factory**:

```python
for name, cls in [
    ("market_analysis", MarketAnalysisSkill),
    ("data_analysis", DataAnalysisSkill),
    ("stock_data", StockDataSkill),
    ("stock_analysis", StockAnalysisSkill),
    ("policy_analysis", PolicyAnalysisSkill),
    ("tech_trend", TechTrendSkill),
    ("risk_analysis", RiskAnalysisSkill),
]:
    skill_registry.register_factory(name, cls)
```

> `register_factory(name: str, factory: Callable[[], Skill])` 接受零参可调用对象。
> Python 类本身就是 Callable，调用 `cls()` 等价于实例化，传类引用合法。

**修复 B — factory.py `_validate_and_normalize_skills` 同时检查 `_factories`**:

```python
# 现状（BUG）:
registered_names = set(self._skill_registry._skills.keys())

# 修复:
registered_names = set(self._skill_registry._skills.keys()) | set(self._skill_registry._factories.keys())
```

**效果**:
- 走正规注册路径，`get()` 可正常发现和创建
- 首次 `get(name)` 时才实例化，节省启动资源
- `_validate_and_normalize_skills` 不再误丢 factory 注册的 skill
- **DATA_COLLECTION 阶段的 `stock_data` 不再被丢弃 → akshare 可被调用**

---

### FIX-2：`load_skills_for_category()` 支持分析 skill

**优先级**: P1（前瞻性兼容，非当前问题主路径）
**文件**: `src/skills/registry.py:379-411`

**现状**:
```python
CATEGORY_TO_LANGCHAIN_SKILLS = {
    "market-analysis": ["lc_tavily_search", "lc_wikipedia", "llm_skill"],
    "financial-analysis": ["lc_tavily_search", "lc_wikipedia", "llm_skill"],  # 缺 stock_data
    "data-collection": ["lc_tavily_search", "lc_wikipedia"],
    # ... 缺 "research" 和 "synthesis" category
}
```

**问题**: 分析 skill 的主分配路径是 `ASPECT_SKILL_MAP` → `AgentSpec.skills` → `required_skills`（见 1.2 节），不依赖 category 映射。但 `load_skills_for_category()` 是 agent 创建时的辅路径，补全后可增加灵活度。

**修复 — 扩展 category 映射 + 加载逻辑**:

```python
CATEGORY_TO_SKILLS = {
    "market-analysis": ["market_analysis", "lc_tavily_search", "lc_wikipedia", "llm_skill"],
    "financial-analysis": ["stock_data", "stock_analysis", "lc_tavily_search", "lc_wikipedia", "llm_skill"],
    "data-collection": ["lc_tavily_search", "lc_wikipedia"],
    "research": ["lc_tavily_search", "lc_wikipedia", "llm_skill"],
    "academic-research": ["lc_arxiv", "lc_wikipedia", "llm_skill"],
    "data-analysis": ["data_analysis", "lc_python_repl", "llm_skill"],
    "report-generation": ["llm_skill"],
    "quality-check": ["llm_skill"],
    "visual-engineering": [],
    "synthesis": ["llm_skill"],
}
```

加载逻辑改为支持 factory skill：

```python
def load_skills_for_category(self, category: str) -> List[str]:
    needed_skills = CATEGORY_TO_SKILLS.get(category, [])
    loaded = []
    for skill_name in needed_skills:
        if skill_name in self._skills:
            loaded.append(skill_name)
            continue
        if skill_name in self._factories:
            skill = self.get(skill_name)
            if skill:
                loaded.append(skill_name)
            continue
        if skill_name.startswith("lc_"):
            if self.load_langchain_skill(skill_name):
                loaded.append(skill_name)
    if loaded:
        logger.info(f"Loaded {len(loaded)} skills for category '{category}': {loaded}")
    return loaded
```

---

### FIX-3：`SKILL_KEYWORDS` 增加分析 skill 关键词 + `discover_skills` 支持 factory

**优先级**: P1
**文件**: `src/skills/skill_keywords.py:30-96`, `src/skills/registry.py:444-459`

**修复 A — 新增分析 skill 关键词**:

```python
SKILL_KEYWORDS: Dict[str, Set[str]] = {
    # --- 现有 LangChain Skills 保持不变 ---
    "lc_tavily_search": { ... },
    "lc_wikipedia": { ... },
    "lc_arxiv": { ... },
    "lc_python_repl": { ... },

    # --- 新增：专业分析 Skills ---
    "market_analysis": {
        "market analysis", "competitive landscape", "market share", "market size",
        "行业分析", "竞争格局", "市场份额", "市场规模",
    },
    "stock_data": {
        "stock data", "financial data", "akshare", "stock quote",
        "financial statement", "profit sheet", "balance sheet", "cash flow",
        "财务数据", "股票数据", "利润表", "资产负债表", "现金流量表",
    },
    "stock_analysis": {
        "stock analysis", "valuation analysis", "financial health",
        "growth analysis", "investment value",
        "股票分析", "估值分析", "财务健康", "成长性分析",
    },
    "data_analysis": {
        "statistical analysis", "quantitative analysis",
        "cagr", "cr3", "hhi", "descriptive statistics",
        "统计分析", "定量分析", "集中度", "描述性统计",
    },
    "policy_analysis": {
        "policy analysis", "regulation analysis", "compliance",
        "government policy", "regulatory impact",
        "政策分析", "监管分析", "合规分析",
    },
    "tech_trend": {
        "technology trend", "patent analysis",
        "innovation", "technology roadmap",
        "技术趋势", "专利分析", "技术路线",
    },
    "risk_analysis": {
        "risk analysis", "risk assessment", "risk factor",
        "risk management", "credit risk", "market risk",
        "风险分析", "风险评估", "风险管理",
    },
}
```

**修复 B — `discover_skills()` 支持 factory skill**（`registry.py:444-459`）:

```python
if auto_load:
    for skill_name in matched:
        if skill_name in self._skills:
            loaded.append(skill_name)
        elif skill_name in self._factories:
            skill = self.get(skill_name)
            if skill:
                loaded.append(skill_name)
        elif skill_name.startswith("lc_"):
            if self.load_langchain_skill(skill_name):
                loaded.append(skill_name)
        elif skill_name == "llm_skill":
            if skill_name not in self._skills:
                self.register_core_skills()
            if skill_name in self._skills:
                loaded.append(skill_name)
```

**⚠️ 须配合 FIX-4**：`generic_agent.py:928` 要求 `skill_name in available_skills or skill_name.startswith("lc_")`。
但 `discover_skills` 分支对 `action="execute"` 的主流程不可达（见 FIX-4 可达性分析），因此此修复的影响范围有限。

---

### FIX-4：`_available_skills` 运行时可扩展 + `discover_skills` 执行条件修复

**优先级**: P2（当前主流程不可达）
**文件**: `src/core/agents/generic_agent.py`

**⚠️ 可达性分析**：

当前主流程中，所有 agent 的 `action="execute"`，映射到 `llm_skill` 并在各阶段分支中 `return`（`generic_agent.py:586`）。
`discover_skills` 分支（`generic_agent.py:924`）只在 `action` 不匹配 `ACTION_TO_SKILL` 任何条目时才可达。
因此 **FIX-4 对当前主流程无直接影响**，但为未来非 `execute` action 的调用路径（如外部直接调用 agent）提供能力。

**修复 A — 新增 `add_skill()` 方法**:

```python
def add_skill(self, skill_name: str) -> bool:
    if skill_name not in self._available_skills:
        if self._skill_registry and self._skill_registry.get(skill_name) is None:
            logger.warning(
                f"GenericAgent {self.agent_id}: cannot add skill '{skill_name}', "
                f"not found in registry"
            )
            return False
        self._available_skills.append(skill_name)
        if self._session and hasattr(self._session, 'agent_template') and self._session.agent_template:
            template = self._session.agent_template
            if "skill_names" in template:
                if skill_name not in template["skill_names"]:
                    template["skill_names"].append(skill_name)
        logger.info(f"GenericAgent {self.agent_id}: dynamically added skill '{skill_name}'")
        return True
    return False
```

> **与原方案的区别**：
> - 增加 registry 验证（`get(skill_name) is None` 检查）
> - 增加 `self._session.agent_template` 非 None 检查（`agent_template` 在 hibernate 前为 None）
> - session 同步确保 hibernate/restore 后不丢失

**修复 B — 修改 `discover_skills` 分支执行逻辑**:

```python
if skill_registry and action not in ["", "default"]:
    discovered = skill_registry.discover_skills(action, auto_load=True)
    for skill_name in discovered:
        skill = skill_registry.get(skill_name)
        if skill:
            self.add_skill(skill_name)
            result = await skill.execute(**parameters)
            return self._ensure_standard_result(result, action)
```

> 移除原 `skill_name in available_skills or skill_name.startswith("lc_")` 限制。

**效果**:
- 为非 `execute` action 的调用路径提供运行时 skill 发现和扩展能力
- 主流程（`action="execute"` → `llm_skill` 分支）不受影响
- `add_skill()` 同步 session 数据，hibernate/restore 后不丢失

### FIX-5：对话阶段接入 SkillRegistry（中期，不纳入本次）

同前版，不重复。

---

## 三、每阶段 Skill 需求规范

> 本节明确回答"什么阶段需要什么 skill"，作为所有 skill 分配逻辑的依据。

### 3.1 阶段 × Skill 矩阵

| Skill \ 阶段 | DATA_COLLECTION | DATA_VALIDATION | DEEP_ANALYSIS | SYNTHESIS | CALIBRATION |
|---------------|:-:|:-:|:-:|:-:|:-:|
| `search_skill` | ✅ 主用 | - | ❌ 不分配 | - | - |
| `news_search` | ✅ 主用 | - | ❌ 不分配 | - | - |
| `llm_skill` | ✅ | ✅ | ✅ 主用 | ✅ | ✅ |
| `stock_data` | ✅ 条件分配 | - | ❌ 不需要 | - | - |
| `stock_analysis` | ❌ 不需要 | - | ✅ 分配但未调用 | - | - |
| `market_analysis` | ❌ 不需要 | - | ✅ 分配但未调用 | - | - |
| `data_analysis` | ❌ 不需要 | - | ✅ 分配但未调用 | - | - |
| `policy_analysis` | ❌ 不需要 | - | ✅ 分配但未调用 | - | - |
| `tech_trend` | ❌ 不需要 | - | ✅ 分配但未调用 | - | - |
| `risk_analysis` | ❌ 不需要 | - | ✅ 分配但未调用 | - | - |
| `lc_tavily_search` | ✅ 可选 | - | ✅ 可选（降级搜索） | - | - |
| `lc_python_repl` | - | - | ✅ 可选 | - | - |

### 3.2 分配原则

**原则 1：数据获取型 skill 只分配给 DATA_COLLECTION 阶段**

- `stock_data`、`search_skill`、`news_search` 是数据获取型 skill
- 它们通过 `execute(action=..., symbol=...)` 主动获取原始数据
- DATA_COLLECTION agent 代码路径中**显式检查**这些 skill 并调用（`generic_agent.py:304`、`322`）
- **不应分配给 DEEP_ANALYSIS**：该阶段使用上游已收集的数据，不应重新搜索

**原则 2：分析框架型 skill 分配给 DEEP_ANALYSIS 阶段**

- `stock_analysis`、`market_analysis` 等 6 个是分析框架型 skill
- 它们接受 `topic`/`aspect`/`data_points` 参数，内部调用 `llm_skill` + `lc_python_repl`
- **当前状态**：分配了但未被 `llm_skill` 的 DEEP_ANALYSIS 分支调用（"死 skill"）
- **本次修复**：确保注册/验证机制正确，使这些 skill 可通过 `discover_skills()` 发现
- **后续优化**：修改 DEEP_ANALYSIS 分支，在 LLM 调用前先调用分析 skill 的预计算层

**原则 3：DEEP_ANALYSIS 不分配 search_skill**

- `ASPECT_SKILL_MAP` 已明确排除 `search_skill`（`strategies.py:42-44` 注释）
- 原因：DEEP_ANALYSIS 应使用上游已收集的数据，避免重复搜索和结果污染
- 降级搜索（`generic_agent.py:423`）是兜底机制，不应作为常规路径

### 3.3 DEEP_ANALYSIS 阶段是否需要数据获取型 skill？

**不需要。** 原因：

1. **数据已由 DATA_COLLECTION 阶段获取**，通过 `task["aggregated_data_points"]` 传入
2. `stock_data` 获取的 akshare 原始数据已在 DATA_COLLECTION 阶段写入 `SharedMemory`，DEEP_ANALYSIS 可通过 `canonical_data` 读取
3. 如果 DEEP_ANALYSIS 也获取 `stock_data`，会导致**重复 API 调用**和**数据不一致**

**例外**：降级搜索路径（`generic_agent.py:422-444`）在无上游数据时需要 `search_skill`，但这是异常路径，不应在 `available_skills` 中分配 `search_skill`（代码已正确处理：只有 `"search_skill" in available_skills` 时才执行降级搜索，而 `ASPECT_SKILL_MAP` 不分配 `search_skill`）。

---

## 四、实施计划

### 4.1 实施顺序

```
Step 1 (原子变更，不可分步):
  FIX-1 修复 A (register_factory) + FIX-1 修复 B (_validate_and_normalize_skills)
  │
  │ 核心：注册规范化 + 验证逻辑同步修复
  │ 解决：DATA_COLLECTION 的 stock_data 被 akshare 调用 + DEEP_ANALYSIS 的分析 skill 不被丢弃
  ▼
  TDD 测试 + 回归验证

Step 2 (可独立上线):
  FIX-2 (CATEGORY_TO_SKILLS) + FIX-3 (SKILL_KEYWORDS)
  │
  │ 增强：category 辅路径 + 运行时发现能力
  │ 不依赖 FIX-4：discover_skills 的调用方不仅限于 GenericAgent.execute
  ▼
  TDD 测试 + 回归验证

Step 3 (低优先级，主流程不可达):
  FIX-4 (add_skill + discover_skills 执行条件修复)
  │
  │ 仅对非 execute action 的调用路径生效
  │ 对当前主流程无直接影响
  ▼
  TDD 测试 + 回归验证
```

### 4.2 测试计划

| 测试文件 | 覆盖 |
|----------|------|
| `test_skill_dynamic_loading.py` | FIX-1~4 全覆盖 |

**Step 1 测试**:

| 编号 | 测试内容 |
|------|----------|
| 1 | `register_factory` 注册的分析 skill 可通过 `get()` 获取 |
| 2 | `get()` 首次调用触发 factory 实例化，第二次直接返回缓存 |
| 3 | 分析 skill factory 创建的实例类型正确 |
| 4 | `_validate_and_normalize_skills` 同时检查 `_skills` 和 `_factories` |
| 5 | factory 注册的 skill 名在 `_validate_and_normalize_skills` 中不被误判为 unknown |
| 6 | `_get_data_collection_skills` 返回的 `stock_data` 通过 factory 验证后不被丢弃 |
| 7 | DEEP_ANALYSIS agent 的 `required_skills` 含 `stock_analysis` 时 `_available_skills` 正确包含 |

**Step 2 测试**:

| 编号 | 测试内容 |
|------|----------|
| 8 | `load_skills_for_category("financial-analysis")` 返回包含 `stock_data` |
| 9 | `load_skills_for_category("research")` 返回非空 |
| 10 | `discover_skills("financial data")` 返回 `stock_data` |

**Step 3 测试（FIX-4）**:

| 编号 | 测试内容 |
|------|----------|
| 11 | `add_skill()` 将 skill 加入 `_available_skills` |
| 12 | `add_skill()` 不重复添加 |
| 13 | `add_skill()` 对 registry 中不存在的 skill 返回 False |
| 14 | `add_skill()` 同步更新 session.agent_template["skill_names"]（当 agent_template 非 None 时） |
| 15 | agent `discover_skills` 发现新 skill 后自动 `add_skill()` 并执行 |

**集成测试**:

| 编号 | 测试内容 |
|------|----------|
| 16 | 端到端：Financial Analysis aspect → DATA_COLLECTION agent 的 `_available_skills` 含 `stock_data` → `_fetch_structured_data` 可执行 |
| 17 | 端到端：Financial Analysis aspect → DEEP_ANALYSIS agent 的 `_available_skills` 含 `stock_analysis` |

### 4.3 风险评估

| 风险 | 概率 | 严重度 | 缓解 |
|------|------|--------|------|
| **FIX-1 分步上线导致分析 skill 被丢弃** | **如分步则必现** | **严重** | **修复 A + B 原子提交** |
| 分析 skill 实例化失败 | 低 | 中 | `register_factory` 不执行实例化，`get()` 时 try-except 兜底 |
| `add_skill()` 动态 skill 在 hibernate/restore 后丢失 | 中 | 低 | `add_skill()` 中同步 session 数据；`agent_template` 在 hibernate 前为 None 时跳过同步 |
| 分析框架型 skill 在 DEEP_ANALYSIS 中仍为"死 skill" | **确认** | 中 | 本次修复注册机制，后续优化调用路径（策略 B） |
| FIX-4 的 discover_skills 分支对主流程不可达 | **确认** | 低 | 仅对非 execute action 的调用路径生效，当前主流程走 llm_skill 分支 |

### 4.4 回归验证

```bash
D:\conda\python.exe -m pytest tests/unit/test_skill_dynamic_loading.py \
  tests/unit/test_p0_stock_symbol_fix.py \
  tests/unit/test_p0_implicit_intent_fix.py \
  tests/unit/test_keyword_registry.py \
  tests/unit/test_review_audit_fixes.py \
  tests/unit/skills/test_registry.py \
  tests/unit/agents/test_agent_factory.py \
  -q --tb=short
```

---

## 五、修复后架构

```
Orchestrator.__init__()
  ├── register_core_skills()                    ← 9 核心 skill（即时注册）
  ├── auto_discover_langchain_tools()           ← LangChain skill（即时注册）
  ├── register_factory(name, cls) × 7           ← 分析 skill（懒加载）
  └── 传给 DynamicAgentFactory

主路径（ASPECT_SKILL_MAP → AgentSpec.skills → required_skills）:
  DATA_COLLECTION: ["search_skill", "news_search", "llm_skill", "stock_data"(条件)]
    → _validate_and_normalize_skills()          ← 同时检查 _skills + _factories ✓
    → agent._available_skills 含 stock_data     → _fetch_structured_data 可执行 ✓

  DEEP_ANALYSIS: ["llm_skill", "stock_analysis", "data_analysis"]
    → _validate_and_normalize_skills()          ← 同时检查 _skills + _factories ✓
    → agent._available_skills 含分析 skill       ← 当前未被调用（后续优化）

辅路径（category → load_skills_for_category → optional_skills）:
  load_skills_for_category(category)
    ├── skill in _skills → 直接使用
    ├── skill in _factories → get() 触发实例化
    └── lc_* → load_langchain_skill()

运行时发现路径（仅对非 execute action 可达）:
  discover_skills(action, auto_load=True)
    ├── SKILL_KEYWORDS 匹配 → 含分析 skill 关键词
    ├── factory → 实例化
    ├── add_skill() → 加入 _available_skills + 同步 session
    └── 执行 skill

主流程执行路径（action="execute" → llm_skill → 阶段分支 → return）:
  discover_skills 分支不可达，FIX-4 仅对非 execute action 生效
```

**关键改进**:
1. 分析 skill 通过 factory 按需实例化
2. `_validate_and_normalize_skills` 同时检查 `_skills` 和 `_factories`，skill 不再被丢弃
3. **DATA_COLLECTION 阶段的 `stock_data` 可被 `akshare` 调用**（最直接的业务效果）
4. `discover_skills()` 可发现分析 skill（对非 execute action 路径生效）

**后续优化（策略 B）**:
- 修改 DEEP_ANALYSIS 分支，在 LLM 调用前先调用分析 skill 的预计算层
- 例如：`stock_analysis._precompute_ratios()` → 将精确财务比率注入 LLM prompt
- 例如：`data_analysis._calc_time_series()` → 将 CAGR/CR3/HHI 注入 LLM prompt
- 这将使分析框架型 skill 从"死 skill"变为"活 skill"
