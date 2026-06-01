# 问卷调研模拟系统未启动的深度分析报告

> 日期: 2026-05-12
> 状态: 待审查
> 优先级: P0（系统阻塞）

---

## 一、问题陈述

执行问卷调研任务时，系统无法触发 AI 模拟填写。任务在 Orchestrator 级别被检测到调查意图（`include_survey=True` 或关键字匹配），但整个调研工作流被静默跳过，用户最终得到一份不含问卷数据分析的报告。

---

## 二、根因分析：4 层断点链路

### 断点 #1（根因）: `_execute_survey_integration` 方法不存在

**位置**: `src/core/orchestrator/orchestrator.py:677-687`

```python
if _has_survey_intent:
    logger.info(f"[{task_id}] Survey intent detected...")
    if hasattr(self, '_execute_survey_integration'):        # ← 永远 False
        survey_result = await self._execute_survey_integration(...)  # 方法不存在
    else:
        logger.warning(f"[{task_id}] Survey integration not implemented, skipping")
```

**根因事实**:
- `_execute_survey_integration` 方法在整个代码库中**从未被定义**
- `hasattr(self, '_execute_survey_integration')` 永远返回 `False`
- 尽管 `_has_survey_intent=True`，**整个调研分支被静默跳过**
- 唯一的痕迹是一条 `logger.warning`，在生产日志中极易被淹没

**Impact**: `SurveyIntegrationAgent`（1017 行完整实现的两套调研工作流）**从未在生产路径中被调用**，是死代码。

**追溯**: 之前的多份故障分析文档（`SURVEY_INTEGRATION_FAILURE_ANALYSIS.md`、`COMPREHENSIVE_ISSUE_ANALYSIS.md`、`SYSTEMATIC_FIX_PLAN.md`）都引用了 `_execute_survey_integration`，说明该方法曾经存在，但在某次重构中被删除，替换为 `hasattr` 守卫——但替换者忘记定义它。

---

### 断点 #2: `distribute` 和 `simulate` API 均创建空白问卷

**位置**:
- `src/survey/task_api.py:111`（`distribute_survey` 端点）
- `src/survey/task_api.py:128`（`simulate_survey` 端点）

两个端点有完全相同的问题模式：

```python
# distribute 端点 — line 111
survey = Survey(survey_id=survey_id, title=req.template, questions=[])

# simulate 端点 — line 128
survey = SurveyModel(survey_id=survey_id, title=template, questions=[])
```

即使绕过 Orchestrator 直接调用 REST API，这两个端点也没有从数据库加载已有问卷，而是**直接创建了一个 questions=[] 的 Survey 对象**。将该对象传入后端 → `SimulationExecutor.execute()` → 对每个 Persona 遍历空问题列表，生成 `answers={}` 的空白响应。

**simulate 端点还有额外问题** — `SimulationExecutor(llm_skill=None)` 硬编码了 `llm_skill=None`（line 129），比 distribute 端点的间接丢失更直接。

---

### 断点 #3: `llm_skill` 未传递给后端

**位置**: `src/survey/task_api.py:51` → `src/survey/client.py:46` → `src/survey/backends/ai_simulation.py:29`

```python
# task_api.py:51
_client = SurveyClient(backend_type="ai_simulation")
# 未传入 llm_skill，backend_config = {}

# client.py:46
self._backend = BackendFactory.get_or_create(self.backend_type, **self.backend_config)
# 相当于 BackendFactory.get_or_create("ai_simulation") = AISimulationBackend()

# ai_simulation.py:97
self._executor = SimulationExecutor(llm_skill=self._llm_skill)  # self._llm_skill = None
```

`AISimulationBackend` 被创建时 `llm_skill=None`。这导致：
- `SimulationExecutor._preflight_check()` 仅记录 "No LLM skill configured" 但**不报错**
- `_answer_question()` 全部回退到 `_answer_with_rules()` 随机生成

**用户看到任务"执行成功"但回答是随机数据**。

---

### 断点 #4: 模板名称不匹配导致静默降级（4 条路径）

**核心事实**: `PersonaTemplateRegistry`（`src/survey/engine/persona_templates.py:20`）的键为**中文字符串 `"一线白领"`**，而非拼音或英文。

4 条路径使用的模板名均不匹配：

| # | 位置 | 代码 | 实际值 | 匹配结果 |
|---|---|---|---|---|
| 4a | `DistributeRequest` 默认值 | `task_api.py:27` | `"yi xian bai ling"`（空格拼音） | ❌ 不匹配 |
| 4b | `simulate` 端点默认值 | `task_api.py:123` | `"yi xian bai ling"`（空格拼音） | ❌ 不匹配 |
| 4c | `AISimulationBackend.distribute()` 硬编码后备 | `ai_simulation.py:90` | `"yi xian bai ling"`（空格拼音） | ❌ 不匹配 |
| 4d | `SurveyIntegrationAgent._ai_simulation_workflow` 默认值 | `survey_integration_agent.py:306` | `"first_tier_white_collar"`（英文） | ❌ 不匹配 |
| — | `PersonaTemplateRegistry` 实际键 | `persona_templates.py:20` | `"一线白领"`（中文） | ✅ 正确值 |

因为 `PersonaGeneratorV2.generate_batch()` 使用 `PersonaTemplateRegistry.get_template(template_name)` 查找，找不到键时会**抛出 `PersonaGenerationError`**（非静默降级）。这意味着所有 4 条路径**都会报错**而非降级——问题更严重。

另外，V1 `PersonaFactory.POPULATION_TEMPLATES`（`persona_factory.py:68`）使用 `"white_collar"` 作为键，这是另一个独立的模板体系，与 V2 引擎不互通。

---

## 三、文档审计：此前设计文档的错误

对 `docs/respondent_agent/` 目录下 4 份设计文档的审查结论：

### 核心错误：错误的前提假设

文档声称 **"Agent 层缺失"**、**"SimulationEngine 绕过了 Agent 层"**。但代码库中已存在完整的 V2 引擎（`src/survey/engine/`），实现了文档声称要构建的所有功能：

| 文档声称要构建的 | 实际存在的位置 |
|---|---|
| `RespondentAgent.answer_question()` | `SimulationExecutor._answer_question()` |
| 状态保持（history） | `_simulate_persona()` 中的 `history: List[Tuple]` |
| Prompt 构建 | `SimulationPromptBuilder` + 4 级 Prompt 体系 |
| 一致性保证 | Prompt 中注入 history |
| 成本控制 | `LLMCostTracker` + `BudgetExceededError` |
| 并发执行 | `asyncio.Semaphore` + `asyncio.gather` |
| 降级策略 | `_answer_with_rules()` |
| 重试机制 | `RetryHandler` 指数退避 |
| 焦点小组 | `FocusGroupSimulator` |
| 分布对齐 | `DistributionAligner`（6 地区人口数据） |
| 跳题逻辑 | `_is_skipped()`（5 种条件） |
| 温度调度 | `TemperatureScheduler`（按题型差异化） |

**文档设计的 Persona 模型（11 字段）是对现有 `PersonaV2`（25+ 字段）的大幅回退**。

### 附加错误

| 错误 | 详情 |
|---|---|
| 建议创建 8 个新文件 | 未考虑已有 V2 引擎，制造冗余 |
| 开发计划预算 5 周 | 实际只需 3-5 天适配 |
| ConsistencyChecker 幼稚 | 4 组关键词匹配对比 Prompt 注入 |
| 忽略 FocusGroupSimulator | 文档声称"Agent 交互不包含"但已实现 |
| 忽略 DistributionAligner | 文档 SurveyCoordinatorAgent 无配额控制 |

---

## 四、修复方案（待审查）

### P0 修改 — `orchestrator.py`

#### 修改 1：删除 `hasattr` 守卫，直接调用（带异常保护）

```python
# 修改前
if hasattr(self, '_execute_survey_integration'):
    survey_result = await self._execute_survey_integration(requirement, task_id)
else:
    logger.warning("...skipping")

# 修改后 — 要求：必须包裹 try/except，确保调研失败不阻塞主研究流程
try:
    survey_result = await self._execute_survey_integration(requirement, task_id)
except Exception as e:
    logger.error(f"[{task_id}] Survey integration failed: {e}")
    survey_result = None
```

#### 修改 2：新增 `_execute_survey_integration` 方法

| 项目 | 内容 |
|---|---|
| 位置 | `ResearchOrchestrator` 类中，`_create_agents_for_sections` 之后 |
| 签名 | `async def _execute_survey_integration(self, requirement, task_id: str) -> Optional[Dict[str, Any]]` |
| 获取 LLM skill | `llm_skill = self._skill_registry.get("llm_skill")` ✅ 已核实注册键：`LLMSkill.name` 返回 `"llm_skill"`（`llm_skill.py:26`），`register(LLMSkill())` 默认使用 `skill.name` 作为键（`registry.py:73`）。⚠️ **注意**: `ResearchOrchestrator` **没有** `self.llm_skill` 属性，必须通过 `self._skill_registry` 获取 |
| 创建 Agent | `SurveyIntegrationAgent(agent_id=f"{task_id}_survey", llm_skill=llm_skill)` |
| 传入参数 | `workflow=requirement.survey_mode`, `topic=requirement.topic`, `target_count=requirement.survey_target_count` |
| 模板名 | `"一线白领"`（必须与 `PersonaTemplateRegistry` 的实际键一致） |
| 返回值 | 调研结果 dict 或 `None`（失败时） |
| **questions** | ⚠️ **必须传入实际问题列表**，而非 `[]`。`auto_generate` 应作为后备而非默认行为，否则 REST API 和 Orchestrator 路径行为不一致 |

**必须避免的问题**:
- ❌ `llm_skill=self.llm_skill` — `ResearchOrchestrator` 无此属性
- ❌ `"persona_template": "yi_xian_bai_ling"` — 键是中文 `"一线白领"`
- ❌ `"questions": []  # 自动生成` — 导致行为不一致

---

### P1 — 修复 REST API 路径

#### 1. `distribute` 和 `simulate` 端点：从数据库加载已有问卷

`task_api.py:111` 和 `task_api.py:128` 均需修改：不创建 `questions=[]` 的空白 Survey，而是从 `SurveyTaskStore` 加载已保存的问卷问题列表。

具体调用链（以 `distribute` 端点为例）：

```python
# task_api.py distribute_survey 内，替换 line 111
import asyncio
from .stores import SurveyTaskStore
store = SurveyTaskStore()
task = await asyncio.to_thread(store.get, f"task_{survey_id[:8]}")  # SQLiteStore.get() 是同步方法
if task and task.get("questions"):
    # SurveyTaskStore._row_to_item 已自动解析 JSON → list（stores.py:51-56）
    questions = task["questions"]
    survey = Survey(survey_id=survey_id, title=req.template, questions=questions)
else:
    survey = Survey(survey_id=survey_id, title=req.template, questions=[])
```

**注意**: `SurveyTaskStore` 继承自 `SQLiteStore[Dict[str, Any]]`，`get(id)` 是同步方法（`base_store.py:744`），在 async handler 中需用 `asyncio.to_thread` 包装。`_row_to_item` 已自动将 JSON 字段解析为 Python 对象（`stores.py:51-56`），无需二次 `json.loads`。

#### 2. `simulate` 端点：传递 `llm_skill`

`task_api.py:129` `SimulationExecutor(llm_skill=None)` 需要改为从全局 `SkillRegistry` 获取 LLM skill 实例并传入。

#### 3. 统一 `DistributeRequest` 和 `simulate` 端点的默认模板名

所有 `"yi xian bai ling"`（带空格）→ `"一线白领"`（中文，匹配 `PersonaTemplateRegistry`）：

| 文件 | 行号 | 当前值 | 目标值 |
|---|---|---|---|
| `src/survey/task_api.py` | 27 | `"yi xian bai ling"` | `"一线白领"` |
| `src/survey/task_api.py` | 123 | `"yi xian bai ling"` | `"一线白领"` |
| `src/survey/backends/ai_simulation.py` | 90 | `"yi xian bai ling"` | `"一线白领"` |
| `src/agents/fixed_agents/survey_integration_agent.py` | 306 | `"first_tier_white_collar"` | `"一线白领"` |

---

### P2 — 清理与文档

| 任务 | 具体操作 |
|---|---|
| 清理错误设计文档 | ✅ 已完成 — `docs/respondent_agent/` 下 4 份文档已删除 |
| 更新架构文档 | `docs/KNOWLEDGE_BASE/02_ARCHITECTURE/SURVEY_ORCHESTRATOR_INTEGRATION.md` 标注真实状态 |
| 更新故障分析 | `docs/STATUS/SURVEY_INTEGRATION_FAILURE_ANALYSIS.md` 补充根因（`_execute_survey_integration` 缺失） |

---

## 五、验证标准

修复后需验证以下各项：

| # | 验证项 | 验证方法 | 预期结果 |
|---|---|---|---|
| 1 | Orchestrator 调研路径触发 | 查看日志 | 出现 `"Survey intent detected"` 然后 `"Survey workflow completed"` |
| 2 | `llm_skill` 正确传递 | 查看日志 | `SimulationExecutor._answer_question` 调用 LLM，**非** `_answer_with_rules` |
| 3 | 问题列表已传递到模拟引擎 | `distribute`/`simulate` 端点返回的 `responses[0].answers` 中非空比例 | 首条 response 的 `answers` 字典中 key 数量 > 80% 的问题总数，即 `len(answers) / len(survey.questions) > 0.8`（有跳题逻辑时 > 50%） |
| 4 | 数据库有记录 | 查询 `survey_responses` 表 | `count_by_task(task_id) > 0` |
| 5 | 报告包含问卷章节 | 检查最终报告 | 应有 `"Survey Data Analysis"` 或等效章节标题 |
| 6 | 调研失败不阻塞主流程 | 模拟 `SurveyIntegrationAgent` 抛异常 | Orchestrator 主流程继续执行，`survey_result=None` |
| 7 | REST API 模板名正确 | 调用 `POST /api/v1/surveys/{id}/simulate` | `PersonaGeneratorV2` 使用 `"一线白领"` 模板成功 |
| 8 | API 问卷非空 | 检查 `SimulationExecutor` 接收的 `survey.questions` | `len(questions) > 0` |

---

## 六、涉及文件清单

| 文件 | 修改内容 | 风险 |
|---|---|---|
| `src/core/orchestrator/orchestrator.py` | 新增 `_execute_survey_integration` + 删除 `hasattr` + try/except | 低 |
| `src/survey/task_api.py` | distribute/simulate 端点：加载已有问卷 + 传入 llm_skill + 修正模板名 | 中 |
| `src/survey/backends/ai_simulation.py` | line 90 模板名 `"yi xian bai ling"` → `"一线白领"` | 低 |
| `src/agents/fixed_agents/survey_integration_agent.py` | line 306 模板名 `"first_tier_white_collar"` → `"一线白领"` | 低 |

---

## 七、结论

系统未启动的直接原因是 **`_execute_survey_integration` 方法缺失**，导致 Orchestrator 检测到调研意图后无法触发 `SurveyIntegrationAgent`。深层原因是**代码重构时删除了集成方法但未补全**，后续的分析文档也未追溯到这一根本问题，而是错误地诊断为"数据返回不完整"（问题在网络中更下游的位置）。

此外存在 **3 个重合的阻塞路径**（distribute 端点、simulate 端点、AISimulationBackend 直连路径），均存在 `questions=[]`、`llm_skill=None`、模板名不匹配三合一的静默失败模式。

此前编写的 4 份 RespondentAgent 设计文档基于**错误的前提假设**（"Agent 层缺失"），完全忽略了已有的 V2 引擎实现，建议创建冗余的 8 个新文件和 5 周开发计划。这些文档已被移除。
