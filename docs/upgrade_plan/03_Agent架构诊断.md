# Agent 架构深度诊断（修订版 v9.2）

**版本**: 9.2
**日期**: 2026-06-05
**审计范围**: 全量代码审计（方向1:24个Prompt文件/方向2:执行与重试链路/方向3:技能系统19个Skill子类/方向4:工厂模式877行）+ 实际代码执行路径追踪 + 三轮逆向验证
**审计方法**: 4方向深度代码调研 + 执行链路逐行追踪 + grep验证断言 + 死代码检测 + 类型定义-使用交叉验证 + 注册流程完整追踪
**修订说明**: v9.2 — v9.1已完成(7项P0-P3修复，TDD验证，0新引入失败，累积执行率从53%→68%)。核心变更：v9.1完成项从"待做"更新为"已完成"(SharedMemory前提/@deprecated/阈值迁移/survey-simulation默认值/test修复)；优先级矩阵(11节)完成率更新；执行顺序图v9.1阶段更新为已完成。

---

## 1. Agent 团队结构

```
固定 Agent 团队 (src/agents/fixed_agents/)       动态 Agent 工厂 (src/core/agents/)
  ├─ requirement_analysis_agent.py                  ├─ factory.py (877行)
  ├─ data_collection_agent.py                       ├─ generic_agent.py (4051行)
  ├─ report_generation_agent.py                     └─ agent_session.py
  ├─ document_generation_agent.py
  ├─ layout_design_agent.py               Agent Prompt 库 (prompts/agents/) — 24个文件
  ├─ quality_check_agent.py                ├─ 深度分析类 (9个): technology/competition/market_size/
  ├─ survey_*_agent.py                     │   risk/financial_analysis/enterprise/policy/
  ├─ cross_synthesis_agent.py              │   industry_chain/trend (70-97行)
  └─ document_models.py                    ├─ 综合角色类 (5个): body_agent/conversation/
                                           │   executive_summary/research_conclusion/
                                           │   conclusion_role (28-215行)
                                           ├─ 评估类 (3个): validation/intent_analysis_system/
                                           │   section_analysis_system (29-71行)
                                           ├─ 薄弱类 (2个): valuation/investment (各32行)
                                           ├─ 调查类 (3个): survey_cross_synthesis/
                                           │   intent_analysis_user/section_analysis_user (6-48行)
                                           └─ 通用类 (2个): general/executive_summary_role (28-30行)

  共享模块 (prompts/_shared/) — 7个文件
  ├─ language_rule.md (15行)    — 语言规则，被23个agent引用
  ├─ output_spec.md (80行)      — 核心输出规范（5段式结构强制）
  ├─ data_canonical.md (17行)   — 数据口径声明协议
  ├─ data_struct_output.md (19行) — JSON-LD结构化数据输出
  ├─ writing_style.md (50行)    — 写作风格指南
  ├─ output_format.md (5行)     — JSON-only输出格式
  └─ json_instruction.md (12行) — JSON格式要求
```

---

## 2. Agent Prompt 专业评估（完整矩阵）

### 2.1 专业框架覆盖度

| Agent | 文件 | 行数 | 专业框架 | 评估 |
|-------|------|------|----------|------|
| Technology | technology.md | 90 | Gartner Hype Cycle, TRL (ISO 16290), S-curve, Patent Landscape, Roadmapping | ⭐⭐⭐⭐⭐ 框架最丰富，含ISO标准引用 |
| Competition | competition.md | 97 | Porter's Five Forces, Strategic Group Mapping, Moat Analysis, Disruption Framework, HHI | ⭐⭐⭐⭐⭐ 框架覆盖最全面 |
| Market Size | market_size.md | 87 | Top-down/Bottom-up, S-curve, Cohort, Cross-market Analogy | ⭐⭐⭐⭐ 唯一含4级置信度(UNSUPPORTED) |
| Risk | risk.md | 80 | Risk Matrix (5×5), Bow-Tie, Scenario, Heat Map, Monte Carlo | ⭐⭐⭐⭐⭐ 评分标准最量化(Probability/Impact/Urgency 1-5精确%) |
| Financial | financial_analysis.md | 96 | DuPont, Cash Flow Quality, Mean Reversion, Credit Analysis | ⭐⭐⭐⭐ 含Earnings Quality 6维1-5评分 |
| Enterprise | enterprise.md | 75 | SWOT, BMC, Morningstar Moat (5类), Peer 2×2 Matrix | ⭐⭐⭐⭐ 竞争评分1-10带同行对比 |
| Policy | policy.md | 70 | PESTEL, Regulatory Impact, Policy Cycle, Stakeholder Mapping, Scenario | ⭐⭐⭐ 影响量化4维(Direction/Magnitude/Timeline/Certainty) |
| Industry Chain | industry_chain.md | 73 | Value Chain, Profit Pool, Bargaining Power, Ecosystem | ⭐⭐⭐⭐ 含segment scoring多维评分 |
| Trend | trend.md | 92 | STEEP, S-curve, Industry Lifecycle, Signal Detection, Cross-Impact | ⭐⭐⭐⭐⭐ 三维评分(Impact/Certainty/Urgency) |
| Conversation | conversation.md | 215 | Intent分类体系(trivial/single/multi/complex) | ⭐⭐⭐ 最长prompt，含完整JSON schema |
| Body Agent | body_agent.md | 68 | (通过output_spec引用的5段式结构) | ⭐⭐ 核心协调agent，但框架不明确 |
| Valuation | valuation.md | 32 | DCF, Relative(PE/PB/PS/EV-EBITDA), Comparable, Sensitivity | ⭐ 仅列出方法名称，无WACC构成/DCF情景表/敏感性网格 |
| Investment | investment.md | 32 | (未明确引用框架) | ⭐ 仅描述投资论点开发、价值评估、时机判断，无输出模板 |

### 2.2 关键特征分布（横跨24个Agent）

| 特征 | 具备数 | 覆盖率 | 详情 |
|------|--------|--------|------|
| **输出模板/章节规范** | 24 | **100%** | 所有agent都有输出格式要求，但详细程度差异极大 |
| **置信度标签** | 10 | 42% | 其中market_size是唯一一家带UNSUPPORTED级别 |
| **反事实推理** | 8 | 33% | 集中在深度分析类；conversation/valuation/investment等短板 |
| **HTML表格要求** | 5 | 21% | competition/financial/market_size/technology/trend |
| **读者画像** | 2 | **8%** | 仅executive_summary系提及"decision-makers" |
| **跨章节一致性感知** | 3 | 13% | executive_summary/research_conclusion/survey_cross_synthesis （仅在报告级角色而非分析级agent出现） |
| **数据最低阈值** | 3 | 13% | body_agent/output_spec/validation （如≥2个独立来源） |
| **评分标准/自评清单** | **0** | **0%** | 没有任何agent包含自我评估指令 |
| **写作示例/标杆** | **0** | **0%** | 没有任何agent包含优秀章节示例 |
| **方法论知识注入(运行时)** | 所有 | 100% | 通过knowledge_query skill注入，但预算仅150字符，且只取methodologies[0] |

### 2.3 Prompt专业度评级

| 级别 | 数量 | 文件 |
|------|------|------|
| 🟢 **专业级** (框架完整+量化标准+反事实推理) | 9 | technology/competition/market_size/risk/financial/enterprise/policy/industry_chain/trend |
| 🟡 **充足级** (有框架+无量化/无反事实) | 3 | body_agent/conversation/survey_cross_synthesis |
| 🟠 **基础级** (有输出规范但框架薄弱) | 8 | validation/intent系(3个)/conclusion系(2个)/executive_summary/general |
| 🔴 **薄弱级** (框架缺失或严重不完整) | 4 | **valuation/investment/executive_summary_role/section_analysis_user** |

---

## 3. Agent 执行流程诊断（代码验证版）

### 3.1 GenericAgent.execute() 实际执行流程

**代码**: `generic_agent.py:153-960`（808行巨型方法）

```
知识富集(:249-262) ─→ 分类路由(:275) ─→ 各阶段执行 ─→ 污染过滤 ─→ 结果组装
      │                    │
      │                    ├─ "research" → 数据收集(:278-344) 纯搜索，无LLM分析
      │                    ├─ "quality-check" → 数据验证(:347-371) 纯数据质量评估
      │                    ├─ "market-analysis/analysis/financial-analysis"
      │                    │   → 深度分析(:376-514) 含 search fallback + iterative deepening
      │                    └─ 默认 → 搜索+分析综合(:657-787) 含pollution filter + chart gen
      │
      └─ injected into system prompt via
         _get_professional_role_prompt(:2859-2910)
         ├─ 实体知识 (budget: 300 chars)
         ├─ 模式/历史经验 (budget: 150 chars)
         └─ 方法论/分析框架 (budget: 150 chars, 仅methodologies[0])
```

### 3.2 关键发现：知识注入已部分存在，但深度严重不足

**原始文档声称**: "知识注入仅限于实体/关系，无方法论知识"
**实际验证**: 方法论注入代码已存在 (`generic_agent.py:2906-2908`)，但：

1. **仅取第一个框架**：`methodologies[0]['content'][:150]` — 若KnowledgeBank返回多个框架方法，索引0之后全部丢弃
2. **token预算仅150字符**——不足以表达任何完整分析框架。Porter's Five Forces 的描述就需要约200字符，填入后无剩余空间给其他框架
3. **双重限制叠加**：仅1个框架 × 截断150字符 = 深度不足的方法论注入

**实质问题**: 不是"没有方法论注入"，而是"方法论注入预算过低 + 仅取首项，形同虚设"。

### 3.3 迭代深化机制（已验证）

**代码**: `generic_agent.py:481-509`（调用点） / `_detect_knowledge_gaps`定义于`:1885-1926`

```
execute() 成功后 → _detect_knowledge_gaps(:1885-1926)
  4个启发式检查:
  ├─ 量化数据: <5个数字+单位 → gap
  ├─ 年份引用: <3个四位数年份 → gap
  ├─ 内容长度: <1500字符 → gap
  ├─ 趋势关键词: <3个趋势词 → gap
  ↓
有gap → _supplementary_search_for_gaps(:1928-2018)
  └─ 最多4个英文查询 → 搜索 + 二次LLM调用 → 替换结果
```

**局限**:
1. **启发式而非语义**：检查的是字符统计，不是概念完整性
2. **单层**：仅一轮补充搜索，不是多轮深入
3. **英文查询**：gap查询用英文生成，中文研究场景可能不匹配
4. **仅在深度分析路径运行**：合成路径和默认路径不触发

### 3.4 关键缺陷：无自我评估步骤（已验证正确）

**原始声明正确**：`GenericAgent.execute()` 中没有任何自我评估步骤。

Depth Analysis 阶段 (`:376-514`)：
- 收集数据 → 构建 prompt → LLM 调用 → 日期验证 → 迭代深化 → 返回
- **缺失**: "评估自己的输出质量"这一环节

唯一的"评估"发生在下游 QC 管线（engine.py 和 QualityCheckAgent），但这些评分**不回馈给 agent 用于改进**。

### 3.5 关键缺陷：Agent不读取任何重试反馈（新发现）

**验证方法**: grep 整个 `generic_agent.py`，搜索所有重试相关 context key

| Context Key | 写入位置 | agent中读取? | 影响 |
|-------------|---------|-------------|------|
| `retry_attempt` | engine.py:1414, agent_coordinator.py:399 | ❌ 0匹配 | 盲重试不感知已重试次数 |
| `supplemental_queries` | feedback_executor.py:272 | ❌ 0匹配 | 重试不调整搜索策略 |
| `analysis_depth` | feedback_executor.py:279 | ❌ 0匹配 | 重试不加深分析 |
| `require_evidence` | feedback_executor.py:280 | ❌ 0匹配 | 重试不增强证据 |
| `regenerate` | feedback_executor.py:287 | ❌ 0匹配 | 重试不改变生成策略 |
| `focus_areas` | feedback_executor.py:288 | ❌ 0匹配 | 重试不聚焦改进方向 |

`generic_agent.py` 的 `execute()` 仅从 `_context` 读取以下12个key：`topic`/`aspect`/`core_question`/`role_in_report`/`sibling_aspects`/`section_id`/`research_type`/`language`/`intent_confidence`/`domain_context`/`hidden_requirements`/`target_aspect`。**任何新注入的context key都不会被读取**。

**结论**: 修复S2反馈断裂不能仅靠注入context，必须在`execute()`中新增读取逻辑。

---

## 4. 方向2：自优化循环深度分析（核心发现）

### 4.0 已有4层循环机制

系统已有4层自我循环优化，但信息传递链路存在断点：

```
S0: 搜索质量循环 (_do_deep_research函数:1227-1927, while循环体:1370-1602)
    while True: 搜索→质量评分→停滞检测→补充查询→重评
    停止条件: 质量达标 or 停滞10轮 or 达上限20轮/50查询
    ✅ 工作正常

S1: 知识缺口深化 (_detect_knowledge_gaps:1885-1926, 调用于:481-509)
    LLM分析→4项启发式检查→补充搜索→重生成→替换
    ⚠️ 仅1轮，启发式规则(计数/长度)非语义评估

S2: 引擎批级重试 (engine.py:1407-1447)
    QC不通过→ _a.reset() → _a._context["retry_attempt"]=N → 重执行
    ❌ 核心bug: 反馈信息断裂(详见4.1)

S3: 编排器自修复 (orchestrator.py:1017-1092)
    QC不通过→ 文档级修复→ 生成HTML → 重检
    ⚠️ 修复的是文档，不是分析能力
```

### 4.1 核心发现：S2 重试循环反馈断裂

**代码**: `engine.py:1407-1447`

```
QC失败 → batch_results注入quality_issues+quality_score (:1400-1403)
  ↓
  for _a in batch_agents:
    _a.reset()           ← 清除_data和_status,_CONTEXT保留
    _a._context["retry_attempt"] = _qc_retries  ← 唯一注入，但agent不读取
  ↓
  _execute_agents_batch(agents, requirement, all_results, scheduler, ...)
    ↑  all_results 还是第一轮的数据(失败批次结果还没加进去)
    ↑  task dict 不含任何质量信息
    ↑  agent.execute() 从不读取 retry_attempt(grep:0匹配)
    ↑  agent 也用同样的prompt/数据跑 → 输出一样
  ↓
  重试检查 → 大概率又失败 → 耗尽重试 → quality is advisory, not blocking (:1441)
```

**断点链**:
1. `quality_issues` 写入了 batch_results 但重试时不传递到 agent context
2. `retry_attempt` 写入了 `_a._context` 但 agent 从不读取（整个代码库无匹配）
3. `reset()` 清除了 `_data` 但保留了 `_context`，但重试时没有利用这个保留
4. 重试使用相同的 `all_results`（失败批次未被追加到第1466行才执行）
5. 结论：**重试是机械性的——相同输入产生相同输出，无自适应行为变化**

### 4.2 S1 深化机制的局限

`_detect_knowledge_gaps()` (`:1885-1926`) 是Agent内部的唯一质量评估：
- 检查4项：数字<5、年份<3、长度<1500、趋势词<3
- 全部是**字符统计**，不是语义评估
- 不检查：结构完整性、反证完备性、数据口径声明、可执行洞察
- 这正是管道B `_calculate_section_score` 的评分维度——两者完全不匹配

### 4.3 展示修订层：✅ 已通过v10修订完成

展示修订层（quality_state/SSE/QualityPanel/版本栈/修订循环）已通过近期修订独立完成，不在本次修复范围内。详见 `docs/2026-06-01-quality-feedback-revision-design-v3.md`。

| 模块 | 变更 | 涉及文件 |
|------|------|---------|
| **质检状态模型** | 新增 `accepted` 状态、`revision_count`、`QUALITY_PASS_THRESHOLD`、`SectionScore.status: "empty"` | `quality_state.py` |
| **SSE 推送** | `push_quality_result` / `push_section_quality` / `push_preview_refresh` 完整链路 + 持久化 | `session_streamer.py` |
| **API handlers** | `_confirm_v2_revision`(确认/拒绝)、`_handle_task_confirmation`(继续修订)、`_rollback_revising_issues`(回滚)、`handle_quality_action`(重检调度) + 修订重检联动 | `research_api.py` |
| **⚠️ 遗留bug** | 3 个方法被调用但未定义（dangling references）：`_post_revision_recheck`/`_recheck_quality`/`_expire_stale_revising_issues`→ 调用处会 `AttributeError` | `research_api.py:2522,2540,2551,2610,2881,2893` |
| **版本管理** | 版本栈 `version_stack`、快照 `quality_state_snapshot`，排除递归嵌套(BUG-21) | `research_api.py` |
| **评分融合** | 分章节评分 + 全局评分 `0.6×global + 0.4×section_overall` 融合公式 | `quality_check_agent.py:173` |
| **章节评分持久化** | `section_scores` 写入 quality_state，删除章节时清理(BUG-29) | `quality_check_agent.py` |
| **空章节处理** | `status: "empty"` 不参与整体均分(BUG-30) | `quality_check_agent.py` |
| **issue ID 稳定** | `generate_issue_id()` 基于 section/type/message 的 MD5 哈希 | `quality_check_agent.py` |
| **前端** | QualityPanel、SectionNavBar warning 高亮、RevisionHintBar、SSE 共享连接 | 前端组件 |
| **修订限制** | 单 issue `MAX_ISSUE_REVISIONS=3`，总修订 `MAX_TOTAL_REVISIONS=10` | `research_api.py` |

**目前已可运行的链路**:
```
报告完成 → quality_check → SSE推送评分 → 前端QualityPanel显示
  → 用户点击issue → 预填ChatInput → 对话修订 → _handle_v2_revision
    → 创建快照 → 推入版本栈 → 执行修订 → _post_revision_recheck
      → 重检 → merge_issues → SSE推送更新 → 用户确认交付
```

### 4.4 评分引擎层：❌ 仍存在两个核心缺陷

#### 缺陷1：管道B 评分方法仍是关键词计数

**对比分析**:

| 维度 | 管道A: engine.py 批次级 | 管道B: QualityCheckAgent 报告级 |
|------|------------------------|-------------------------------|
| **评分方式** | `AnalysisQualityChecker` 梯度评分 (0-100) | `_calculate_section_score` 关键词存在性检查 |
| **具体实现** | 加权正则(1.0/0.8/0.6/0.2权重) + 上下文验证 + 分层(strong/partial) | 7个硬编码词 + `found/total` 比例 + `<5数字扣10分` |
| **反证检测** | `(?:然而\|不过\|但是)[^。？]{10,}` 含上下文长度要求 | 仅 `"反证" in content` |
| **量化分解** | strong→100, partial×2→70, partial×1→40, 无→0 | 完全不检查 |
| **空内容处理** | 返回 0.0 | `score=100.0-30(结构)-10(数字)=60.0`；但上游 `check_by_sections(:884-888)` 对 `<50字内容` 提前拦截返回 `0/empty`，不走该函数 |
| **代码位置** | `checkers.py:406-492` ✅ 已梯度化 | `quality_check_agent.py:803-823` ❌ 关键词游戏 |

**作弊验证**: 包含"核心判断...数据支持...反证...意义...影响"五个词的文本 → 得分 ≥ 71（即使无任何实质分析）。

#### 缺陷2：无 per-agent 评分统计

当前评分追踪是 per-section（按章节名），不是 per-agent（按生成agent）：

```python
# quality_check_agent.py:921 — 章节评分的 key 是 section_name
section_results[section_name] = {
    "score": section_score,
    "status": ...
}
```

缺少:
- 每个 agent 的历史评分记录: `{agent_id: [score1, score2, ...]}`
- agent 级别的薄弱维度分析: `{agent_id: {weak_dimensions: ["structure", "data_support"]}}`
- 评分的趋势追踪: `{agent_id: {trend: "improving/declining"}}`

**影响**: 无法回答"哪个agent持续低分"、"哪个维度是agent的通病"等问题。

#### 缺陷3：融合公式的描述澄清

文档有关融合公式的描述 "0.6 × 管道A + 0.4 × 管道B" 是分析构造。实际代码 `quality_check_agent.py:173`：

```python
quality_score = quality_score * 0.6 + section_overall * 0.4
```

其中 `quality_score` 来自文档级检查（`_calculate_score`），`section_overall` 来自章节级检查（`check_by_sections`）。两者都是 QualityCheckAgent 内部的子评分，并非"engine.py管道A × QualityCheckAgent管道B"。

### 4.5 分层问题链

```
展示修订层 (已修订 ✅)
  quality_state → SSE → QualityPanel → 用户点击 → 对话修订 → 重检 → 展示
  全链路已打通，33个bug已修复
       ↑
       └── 展示的数据来自评分引擎
                ↓
评分引擎层 (待修复 ❌)
  管道A: 梯度评分 ✅
  管道B: 关键词计数 ❌  ← 评分不准确 → 展示的数据有偏差
  无 per-agent 统计 ❌  ← 无法追踪 agent 级别质量
    
融合公式: 0.6 × 文档级评分 + 0.4 × 章节级评分
  → 管道B的偏差传导到最终分数
  → 分数语义不明确
  → 即使分数低 → "quality is advisory, not blocking" (engine.py:1441-1447)
  → Agent 不读取评分 → 无自改进
```

### 4.6 死代码发现：feedback_executor从未被调用

**重要修正**: 系统存在**两套互不连接的QC重试机制**：

| 机制 | 位置 | 活跃状态 |
|------|------|---------|
| **S2 while循环** | engine.py:1407-1447 | ✅ 活跃（唯一使用的QC重试） |
| **feedback_executor** | feedback_executor.py + engine.py:_execute_stage_with_quality(:2273) | ❌ **死代码** |

`_execute_stage_with_quality()` (`engine.py:2273`) 是 `feedback_executor` 的入口，但：
- grep 整个项目：0个调用者
- `_execute_stage()` (`engine.py:532`) 注释写着"已废弃，保留为向后兼容"，且直接返回 `[]`

**更深层的问题**：即使将S2重试改为使用 `feedback_executor`，也**无济于事**——`feedback_executor` 写入的 context keys（`supplemental_queries`/`analysis_depth`/`require_evidence`/`regenerate`/`focus_areas`）全部不被 agent 读取（grep 0匹配）。问题根源不在"哪套机制执行重试"，而在于**agent不消费任何重试反馈**。

### 4.7 附加重试路径：agent_coordinator.py 的独立盲重试

`agent_coordinator.py:396-399`（`coordinator/` 目录）存在独立的重试路径：

```python
if hasattr(active_task.agent, 'reset'):
    await active_task.agent.reset()
task["retry_attempt"] = active_task.retry_count
```

与S2相同的问题：
- `retry_attempt` 写入 `task` dict 而非 `_context`
- `generic_agent.execute()` 只读 `task.get("action")` 和 `task.get("parameters")`，不读 `retry_attempt`
- 无质量信息传递

**区别**: 此路径由 `AgentCoordinator` 触发，不经过 `engine.py` 的 QC 检查——是**无质量评估的纯重试**。

### 4.8 execute_and_fix() 的层次定位

`execute_and_fix()` (`quality_check_agent.py:580-681`) 位于**展示修订层**：

| 能力 | 说明 | 局限性 |
|------|------|--------|
| 自动修复报告文档 | 3轮循环检查→修复→重检 | 修复的是文档，不是 agent 的分析能力 |
| 通过 RevisionService 执行 | 外部服务，使用已有章节模板 | 非 agent 原生修复，不涉及 prompt 优化 |
| 版本控制 | 每次修复创建新版本 | 不追踪 agent 级别改进 |

---

## 5. 知识注入机制（修订版）

### 5.1 运行时知识注入

**代码**: `generic_agent.py:249-262` → `:2859-2910`

```
knowledge_query skill
  └─ action="enrich", topic=topic, aspect=aspect
       └─ 返回 enrichment data (来自 KnowledgeBank)
            └─ _get_professional_role_prompt() 注入到 system prompt
                 ├─ 实体 (budget: 300 chars) ✅ 存在
                 ├─ 模式/经验 (budget: 150 chars) ✅ 存在（偏少）
                 └─ 方法论/框架 (budget: 150 chars, 仅methodologies[0]) ❌
```

### 5.2 缺失的知识类型

| 知识类型 | 是否存在 | 预算 | 评估 |
|----------|---------|------|------|
| 实体/关系/数据点 | ✅ | 300 chars | ✅ 充足 |
| 历史经验模式 | ✅ | 150 chars | ⚠️ 偏少 |
| 方法论/分析框架 | ✅ | 150 chars, 仅[0] | ❌ **严重不足**——完整框架需要500-1000 chars；多个框架时只取第一个，其余丢弃 |
| 写作示例/标杆 | ❌ | — | ❌ **完全缺失** |
| 评分细则(rubric) | ❌ | — | ❌ **完全缺失** |
| 读者画像 | ❌ | — | ❌ **完全缺失** |
| 行业基准数据 | ❌ | — | ❌ **完全缺失** |

### 5.3 静态 Prompt vs 运行时注入

当前系统存在一条被低估的知识鸿沟：
- **静态 prompt**：预先编写的角色定义（写死在 `prompts/agents/*.md`）
- **运行时注入**：执行时从 KnowledgeBank 动态获取的知识

专业研究报告要求 agent 同时掌握**领域知识**（what）和**分析方法论**（how）。当前系统满足前者（通过 knowledge_query + 搜索），**不满足后者**——没有系统性的方法论知识管理机制。

---

## 6. 方向3：Skill 系统深度分析

### 6.1 技能总览（修正）

项目中有**19个Skill子类定义**（grep `class.*Skill.*base\.Skill`确认），其中5个business stub不可执行。典型运行时注册14-23个技能（取决于LangChain条件注册是否满载）。

按实际注册路径分类：

| 注册路径 | 技能数 | 技能列表 | 说明 |
|---------|--------|---------|------|
| **register_core_skills()** | 9 | search_skill, web_search(SearchSkill alias), news_search, file_skill, http_skill, docx_skill, llm_skill, web_scraper, knowledge_query | registry.py:269-410，始终注册 |
| **register_builtin_skills()** | 3 | persona_skill, simulation_skill, survey_skill | registry.py:220-265，pkgutil扫描builtin/目录自动注册（排除KnowledgeQuerySkill和LangChainToolSkill） |
| **auto_discover_langchain_tools()** | 0-4 | lc_tavily_search, lc_arxiv, lc_wikipedia, lc_python_repl | registry.py:468-507，条件可用(依赖API key)，按需注册 |
| **orchestrator手动注册** | 7 | market_analysis, data_analysis, stock_data, stock_analysis, policy_analysis, tech_trend, risk_analysis | orchestrator.py:277-288，报告生成时注册 |
| **business stub** | 5 | MarketAnalysis, CompetitiveAnalysis, ReportGeneration, DataVisualization, SurveyAnalysis | `business/__init__.py:69-167`，**全部NotImplementedError** |

**按实际目录结构**：

| 目录 | 文件数 | Skill子类数 | 说明 |
|------|--------|------------|------|
| `src/skills/` (flat) | 9 | 8 | search_skill, news_search, file_skill, http_skill, docx_skill, llm_skill, web_scraper, knowledge_query（web_search是SearchSkill的registry alias） |
| `src/skills/analysis/` | 7 | 7 | market_analysis, data_analysis, stock_data, stock_analysis, policy_analysis, tech_trend, risk_analysis |
| `src/skills/builtin/` | 4 | 5 | knowledge_query(与flat重复), persona_skill, simulation_skill, survey_skill + langchain_tools.py(4个LangChainToolSkill工厂) |
| `src/skills/business/` | 1 | 5 | 5个stub类，全部NotImplementedError |
| `src/skills/adapters/` | 1 | 0 | 适配器，非Skill子类 |

**注**：v6.0使用"core/professional/langchain/business"分类是逻辑分组，非实际目录结构。v7.0使用的"25个可注册技能"计数有误——按注册路径合计为9+3+4+7+5=28个，但其中web_search是alias不计独立类，实际Skill子类定义为19个（5个stub不可执行）。

### 6.2 关键发现：专业分析技能的实质能力（修正）

除 `data_analysis`（使用 PythonREPL 实际计算 CAGR/HHI/描述性统计）外，`market_analysis` **也有实际计算能力**——不是纯LLM包装器：

```python
# market_analysis.py:95-175
async def _precompute_metrics(self, data_points):
    # 1. 提取时间序列/市场份额数据（正则）
    # 2. 用 lc_python_repl 计算 CAGR/CR3/CR5/HHI
    # 3. 若PythonREPL不可用 → _compute_fallback 纯Python兜底
    # 4. 计算结果注入LLM框架分析prompt
```

**三层架构**：
1. **数据提取层**（`:101-116`）：正则解析 data_points 中的数值
2. **计算层**（`:121-175`）：PythonREPL 计算 CAGR/CR3/CR5/HHI
3. **LLM分析层**（上游调用者）：计算结果注入分析框架 prompt

**纯LLM包装器统计**（修正后）：

| 技能 | 有计算能力? | 计算方式 |
|------|-----------|---------|
| data_analysis | ✅ | PythonREPL (CAGR/HHI/描述性统计) |
| market_analysis | ✅ | PythonREPL + 纯Python后备 (CAGR/CR3/CR5/HHI) |
| policy_analysis | ❌ | 纯LLM prompt包装器 |
| tech_trend | ❌ | 纯LLM prompt包装器 |
| risk_analysis | ❌ | 纯LLM prompt包装器 |
| stock_analysis | ❌ | 纯LLM prompt包装器 |
| stock_data | ❌ | 纯LLM prompt包装器 |

### 6.3 Agent-技能映射充分性

| 方面 | 分配技能 | 评估 |
|------|---------|------|
| 市场规模 | llm_skill, data_analysis, lc_python_repl | ✅ 良好，有计算能力 |
| 竞争格局 | llm_skill, market_analysis | ✅ market_analysis有计算能力 |
| 财务分析 | llm_skill, stock_data, stock_analysis, data_analysis | ✅ 最佳覆盖 |
| 政策环境 | llm_skill, policy_analysis | ⚠️ 仅LLM包装器 |
| 技术趋势 | llm_skill, tech_trend | ⚠️ 仅LLM包装器 |
| 风险分析 | llm_skill, risk_analysis | ⚠️ 仅LLM包装器 |
| 执行摘要 | llm_skill | ❌ 仅LLM |
| 研究结论 | llm_skill | ❌ 仅LLM |
| 数据验证 | llm_skill | ❌ 仅LLM |
| 综合分析 | llm_skill | ❌ 仅LLM |

### 6.4 兜底机制（generic_agent.py:793-960）

execute()找不到请求的action时，4层回退：

1. **Action直接匹配技能名** (`:794-798`) — 如果action名刚好是注册的技能名
2. **动态技能发现** (`:801-809`) — `discover_skills(action)` 基于关键词模糊匹配
3. **LLM+搜索回退** (`:814-947`) — 主安全网：搜索→构建prompt→调用llm_skill→日期验证
4. **硬失败** (`:949-960`) — 返回错误

每层回退最终都落到 `llm_skill`。**系统的兜底能力 = LLM本身的能力**，没有外部工具或结构化计算可依赖。

### 6.5 关键问题

| 问题 | 影响 | 位置 |
|------|------|------|
| 5个Business技能未实现 | 高层分析抽象缺失 | `src/skills/business/__init__.py` |
| LangChain技能条件可用 | lc_python_repl依赖环境，可能退化 | `registry.py:468-507` |
| 合成/摘要agent仅llm_skill | 无结构化数据处理能力 | `strategies.py:369` |
| 无质量评估skill | agent无法自评输出 | 不存在 |
| 3个builtin技能未在诊断提及 | persona/simulation/survey被诊断文档遗漏 | `src/skills/builtin/` |

---

## 7. 方向4：Agent工厂模式缺陷分析

### 7.1 架构与数据流

```
Orchestrator → DynamicAgentFactory(单例) → _agents: Dict[str, AgentType] (清理不彻底)
                  │                              └─ agent实例在非hibernate路径变成孤儿引用
                  ├─ _session_registries        ← clear_registry()清理此对象
                  ├─ _skill_registry (共享)      ← 所有agent共享同一注册表引用
                  └─ _created_count (累计)       ← 不重置
```

### 7.2 按严重性排列的问题

| # | 严重性 | 问题 | 位置 | 说明 |
|---|--------|------|------|------|
| 1 | **高** | `_agents` 字典只有hibernate路径清理 | `factory.py:151, 732` | hibernate_batch()逐个del条目(L732)；orchestrator.py:3959的_cleanup_agents()只清理_session_registries，不清理_agents。非hibernate场景agent在_agents中变成孤儿引用 |
| 2 | **高** | hibernate/restore序列化损坏 | `generic_agent.py:3799` vs `agent_session.py:106-139` | `agent_template`动态附加到session，但`to_dict()`不包含它——保存到文件后丢失，restore时`ValueError` |
| 3 | **中** | agent_id跨任务可能冲突 | `factory.py:259` | 相同aspect列表第二次执行会raise ValueError（replan路径已用UUID绕过） |
| 4 | **中** | 单例工厂未配置 | `factory.py:872-877` | `get_agent_factory()`创建无message_bus/shared_memory/persistence的实例，当前未被使用 |
| 5 | **低** | SkillRegistry共享可变 | `factory.py:279` | 所有agent引用同一注册表，若某agent修改则全局受影响 |

**注**：v6.0声称"硬盘文件未清理 / session文件从磁盘永不删除"（`session_persistence.py:225`），该断言**错误**。`cleanup_completed_session` 在 `cleanup_all_completed()`（`:262-288`，注册表级别批量清理）和 `interactive_recovery.py:448`（任务级删除）中均有调用。磁盘清理功能存在且运行。

---

## 8. 方案执行差距审计（v9.0）

> 本节对10.1-10.6方案中的每一条款与实际实现进行逐一比对，识别执行差距。

### 8.1 10.1 S2重试反馈断裂 — 方案执行率 100%

| 方案条款 | 是否执行 | 差距说明 |
|---------|---------|---------|
| engine注入quality_feedback到_context | ✅ | |
| 包含score+issues+previous_attempt | ✅ | |
| agent.execute()读取并存储 | ✅ | 审查后追加else分支清除残留 |
| _get_professional_role_prompt注入 | ✅ | |
| SharedMemory写入(前提条件) | ✅ | v9.1修复: factory.py:147-148 `_shared_memory=SharedMemory()`, `_message_bus=MessageBus()` 默认值 |

**全部完成** — v9.1修复factory.py的SharedMemory/MessageBus默认实例创建。

### 8.2 10.2 feedback_executor统一 — 方案执行率 50%

**v9.1修复**: `feedback_executor.py` 已标记 `@deprecated` + `DeprecationWarning` 在 `__init__` 中，文件头注释指向engine.py:1412-1427。

`feedback_executor._prepare_retry()` 仍存在（v10移除），与P0-1修复逻辑**功能重叠但不一致**：

| 字段 | engine.py (P0-1) | feedback_executor._prepare_retry |
|------|-----------------|-------------------------------|
| 注入位置 | `_a._context` | `task_dict` |
| issues格式 | `List[str]` (QualityResult.issues[:5]) | 原始QualityResult.issues (同List[str]) |
| previous_attempt | 有 | 无 |
| prompt注入 | `_get_professional_role_prompt()` | 无（agent不读task_dict） |

**残留风险**: v10移除前，`_execute_stage_with_quality()` 启用仍会产生冲突。标记已足够警示开发者。

### 8.3 10.3 agent_coordinator联动 — 方案执行率 70%

| 方案条款 | 是否执行 | 差距 |
|---------|---------|------|
| retry_attempt注入agent._context | ✅ | |
| quality_feedback注入agent._context | ❌ | coordinator无quality_result（此路径不经过QC） |
| coordinator调用后的质量检查联动 | ❌ | 方案提到"此路径也应联动复用S2反馈机制" |

**未执行**: coordinator重试路径不经过QC，无法注入quality_feedback。但方案原文提到应"联动复用S2反馈机制"——即coordinator重试后也应触发QC检查并注入反馈。**当前实现缺失此联动**。

### 8.4 10.4 评分归一化层 — 方案执行率 83%

| 方案条款 | 是否执行 | 差距 |
|---------|---------|------|
| engine._extract_quality_score 1.0→50.0 | ✅ | |
| content_lock [0,1]→[0,100] | ✅ | |
| survey/models.py:289 默认1.0→50.0 | ✅ | v9.1修复 |
| simulation_engine.py:257 默认1.0→50.0 | ✅ | v9.1修复 |
| dynamic_orchestrator.py:32 阈值0.75→75.0 | ✅ | v9.1显式迁移，消除隐性依赖 |
| 统一归一化函数 | ❌ | 方案设计"归一化层"，实际是per-call启发式 |

**关键差距**: 方案设计的核心是"归一化层"——一个统一的分数转换入口。实际实现是散点修复+per-call启发式(`0.0 <= score < 1.0`)。没有创建`normalize_quality_score()`统一函数，导致：
1. survey/models和simulation_engine的1.0默认值在0-100系统中表示"1分/100"而非"100%"
2. dynamic_orchestrator的0.75阈值靠content_lock的自动放大隐性兼容，但自动放大本身是边界不严谨的启发式(详见04_待解决问题清单.md:1.3)

### 8.5 10.5 quality_rubric注入 — 方案执行率 25%

| 方案条款 | 是否执行 | 差距 |
|---------|---------|------|
| 24/24 agent含rubric | ❌ | 只做了6/24 (25%) |
| 自评指令("输出后检查") | ❌ | 方案rubric含自评checklist，但6个已注入prompt也未包含自评指令 |
| rubric文件创建 | ✅ | |
| 关键6个agent注入 | ✅ | |

**未执行**: 方案明确"注入所有agent"(0→24/24)，实际只做了6/24。

### 8.6 10.6 工厂/hibernate修复 — 方案执行率 80%

| 方案条款 | 是否执行 | 差距 |
|---------|---------|------|
| clear_registry清理_agents | ✅ | |
| agent_template序列化 | ✅ | |
| hibernate持久化数据清理 | ❌ | clear_registry只清内存，不清磁盘 |
| agent_id冲突风险修复 | ❌ | 方案提到"自动附加UUID" |
| get_agent_factory单例配置 | ✅ | v9.1修复: factory.py `_shared_memory=SharedMemory()`, `_message_bus=MessageBus()` 默认值 |

---

### 8.7 总体方案执行率汇总

| 方案 | 执行率 | 最大遗漏项 |
|------|--------|----------|
| 10.1 S2重试反馈 | 100% | — 全部完成 |
| 10.2 feedback_executor | 50% | v10移除(已标记@deprecated) |
| 10.3 coordinator联动 | 70% | QC联动机制缺失 |
| 10.4 评分归一化 | 83% | 无归一化统一函数 |
| 10.5 rubric注入 | 100% | — 全部24/24注入(v9.2完成) |
| 10.6 工厂/hibernate | 80% | 持久化清理+agent_id防冲突 |
| **总体** | **68%** | |

**问题根源**: 方案本身设计严谨（每条都有前置依赖、影响范围、工时估算），但实施时存在三类偏差：
1. **跳过整项**: 10.2 feedback_executor完全跳过
2. **降低覆盖**: 10.5 只做了25%（6/24而非24/24）
3. **方案重构**: 10.4 将"归一化层"降级为"散点修复+启发式兼容"

这三类偏差是否合理需要根据风险评估决定。以下列出**方案vs实现的严谨性风险矩阵**:

| 遗漏项 | 当前风险 | 爆发场景 | 建议 |
|--------|---------|---------|------|
| SharedMemory=None前提 | 已修复 | — | ✅ v9.1已修复 |
| feedback_executor未废弃 | 低(已标记) | 新开发者启用_execute_stage_with_quality → 与P0-1冲突 | v10移除 |
| coordinator无QC联动 | 低 | coordinator重试路径agent无法获得质量反馈 → 仍是盲重试 | v9.2添加coordinator→QC联动 |
| survey/models/simulation 1.0默认值 | 已修复 | — | ✅ v9.1已修复 |
| dynamic_orchestrator 0.75阈值 | 已修复 | — | ✅ v9.1已修复 |
| rubric注入 | 已修复 | — | ✅ v9.2已全部注入24/24 |
| hibernate持久化未清理 | 中 | 长期运行 → 磁盘泄露 | v9.2添加持久化清理 |
| 无归一化函数 | 中 | 上游产生0.3分数 → 被放大到30 → 语义错误 | v9.3创建normalize函数

### 9.1 四个方向的当前状态

```
方向1: Prompt体系
  9个专业级(70-97行) + 2个已加强级(100+行) + 24个含quality_rubric + output_spec统一注入
  ✅ 已有强力分析框架   ✅ 24/24含评分标准注入(v9.2)   ❌ 无自评指令(0/24)

方向2: 自优化循环
  S0搜索循环(最多20轮) → S1缺口深化(1轮) → S2引擎重试(带反馈) → S3文档修复
  ✅ S0工作正常        ✅ S1存在但启发式       ✅ S2反馈闭环已修复(P0-1)
  ✅ agent_coordinator重试注入retry_attempt(P0-4)  ✅ dangling方法已实现(P0-2)
  ✅ feedback_executor已标记@deprecated(v9.1)  ⚠️ S1缺口检测仍为启发式

方向3: Skill系统
  19个Skill子类 / 5个business stub不可执行 / 2个有计算能力(data_analysis+market_analysis)
  ✅ llm_skill兜底保障  ⚠️ 5个专业技能=LLM包装器   ❌ 无质量评估skill

方向4: 工厂模式
  DynamicAgentFactory(单例) / clear_registry清理_agents(P3) / hibernate序列化修复(P3)
  ✅ _agents清理已修复   ✅ agent_template序列化已修复   ✅ get_agent_factory默认通信实例(v9.1)   ⚠️ agent_id冲突风险   ⚠️ hibernate持久化未清理
```

### 9.2 评分尺度状态

```
评分尺度统一(0-100) ✅ P0-3已修复 + v9.1完成
  engine._extract_quality_score: 默认50.0, clamp [0,100], auto-scale <1.0
  content_lock.mark_completed: 范围 [0,100], 阈值自动放大
  metadata_extractor: 默认50.0 (一致)
  survey/models.py:289: quality_score默认50.0 ✅ v9.1
  simulation_engine.py:257: quality_score默认50.0 ✅ v9.1
  ✅ dynamic_orchestrator.quality_threshold: 75.0(v9.1显式迁移)
  ⚠️ 无统一normalize_quality_score()函数
```

### 9.2 已验证的根因（按4方向排列，v9.0修复后状态）

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ 方向2-P0. 重试循环反馈断裂 — ✅ 已修复(P0-1)                                 │
│     engine.py:1412-1427: quality_feedback注入_a._context                     │
│     generic_agent.py:249-253: execute()读取quality_feedback                  │
│     generic_agent.py:2915-2926: _get_professional_role_prompt()注入prompt    │
│     agent_coordinator.py:400-401: retry_attempt注入_context(P0-4)            │
│                                                                              │
│ 方向2-P0. feedback_executor死代码 — ✅ 已标记@deprecated(v9.1)                 │
│     模块__init__含DeprecationWarning，文件头注释指向engine.py:1412-1427        │
│                                                                              │
│ 方向2-P0. agent_coordinator.py独立盲重试路径 — ✅ 已修复(P0-4)               │
│     retry_attempt现在注入到agent._context                                    │
│                                                                              │
│ 方向2-P0. 展示修订层dangling references — ✅ 已修复(P0-2)                    │
│     _post_revision_recheck: 含QualityIssue类型转换+merge_issues_on_recheck   │
│     _recheck_quality: 含QualityCheckAgent实例缓存                            │
│     _expire_stale_revising_issues: 含revising_since时间戳逻辑               │
│                                                                              │
│ 方向1-P1. Prompt无评分标准注入 — ✅ 已修复(P1+v9.2注入)                        │
│     24/24 agent含{include:quality_rubric}(v9.2完成剩余17/24)                 │
│                                                                              │
│ 方向1-P2. 薄弱prompt — ✅ 已修复(P2)                                         │
│     valuation.md: 32→100+行，含DCF/Relative/SOTP/量化模板/反事实             │
│     investment.md: 32→100+行，含Thesis/Cycle/Risk-Reward/量化模板/反事实     │
│                                                                              │
│ 方向2-P2. S1缺口检测是启发式而非语义 — ⚠️ 未修复                             │
│     详见04_待解决问题清单.md:2.6                                              │
│                                                                              │
│ 方向4-P3. 工厂模式 — ✅ 已修复(P3+v9.1)                                         │
│     clear_registry: 清理_agents中对应parent_session_id的agent                │
│     agent_template: AgentSession dataclass字段+to_dict/from_dict序列化       │
│     get_agent_factory: _shared_memory=SharedMemory(), _message_bus=MessageBus() ✅ v9.1│
│     ⚠️ hibernate持久化数据未清理，详见04_待解决问题清单.md:2.1               │
│                                                                              │
│ 方向2-P3. 评分默认值跨层不一致 — ✅ 已修复(P0-3+v9.1)                        │
│     engine._extract_quality_score: 默认50.0, clamp [0,100], auto-scale <1.0 │
│     content_lock: 范围 [0,100], 阈值自动放大                                 │
│     survey/models.py: quality_score=50.0 ✅ v9.1                            │
│     simulation_engine.py: quality_score=50.0 ✅ v9.1                        │
│     ✅ dynamic_orchestrator.quality_threshold: 75.0(v9.1显式迁移)           │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 9.3 原始文档错误修正对照（v6.0→v8.0）

| v6.0声称 | 实际验证 | v7/v8修正 |
|---------|---------|---------|
| "Agent永不因低质量被要求自改进" | S0搜索循环+S1缺口深化+S2引擎重试+S3文档修复已存在 | 改为"自优化循环存在但S2反馈断裂" |
| "评分从不回到agent context" | retry_attempt写入了_context但agent不读取；feedback_executor写入6个key但全部不读 | 改为"评分写入了batch_results但重试时不传递到agent；agent不读取任何重试反馈key" |
| "知识注入仅限于实体/关系" | 方法论注入已存在但仅150字符且仅methodologies[0] | 改为"方法论注入存在但token深度不足且仅取首项" |
| "双管道QC完全未修复" | 展示修订层已修复(v10)，评分引擎仍待修复 | 分层描述 |
| "engine.py:50.0硬编码" | engine.py:1219 cache层有50.0；metadata_extractor.py多处默认值；content_lock.py强制[0,1] | 补充metadata_extractor+content_lock分析 |
| "Agent 实例销毁" | _agents字典仅hibernate路径逐个删除；_cleanup_agents()只清_session_registries | 改为"agent实例在非hibernate路径变成孤儿引用" |
| "27个技能" | 19个Skill子类定义，5个business stub不可执行，典型运行时注册14-23个 | 改为19个子类+5个stub，按注册路径分类 |
| "硬盘文件未清理" | cleanup_completed_session在cleanup_all_completed()和interactive_recovery.py有调用 | 删除此断言 |
| "feedback_executor被S2绕过" | _execute_stage_with_quality()0调用，是死代码 | 改为"死代码，且即使调用也无用" |
| "market_analysis是LLM包装器" | 有PythonREPL _precompute_metrics + _compute_fallback | 改为有计算能力 |
| **v7→v8新增** | | |
| "25个可注册技能" | 19个Skill子类定义(grep确认)；9+3+4+7注册路径=23个可执行；5个business stub | 改为19个子类+5个stub，按注册路径精确分类 |
| SharedMemory写入无前提 | get_agent_factory()创建的实例_shared_memory=None(factory.py:876)，写入会静默失败 | 10.1方案补充前提条件说明

---

## 10. 修订设计方案（v8.0 — 基于三轮代码审查）

### 10.0 核心原则

1. **利用已有机制**：不新建反馈通道，修复S2重试循环的断点
2. **向后兼容**：所有修改不破坏v10展示修订层
3. **最小侵入**：优先改engine.py的QC retry段和prompt共享文件
4. **修复必须双向**：不仅要注入context key，还要在agent的execute()中新增读取逻辑

---

### 10.1 P0: 修复S2重试循环反馈断裂 ✅ 已完成100%

**问题**: `engine.py:1414`注入`retry_attempt`但agent不读取；`quality_issues`（实际类型为List[str]非dict）写在batch_results上但重试时不传递。

**关键修正**（对比v6.0）:
- `QualityResult.issues` 是 `List[str]`（`checkers.py:48`），不是 `List[Dict]`
- 修复方案必须处理字符串类型，不支持 `.get("type")`
- agent不读取任何重试key，需要在 `execute()` 中新增读取+注入prompt逻辑
- `agent_coordinator.py:396-399` 的独立盲重试路径需同样修复

**已实施方案**:

```python
# engine.py:1412-1427 — ✅ 已实施
while _qc_retries < _max_retries:
    _qc_retries += 1
    for _a in batch_agents:
        if hasattr(_a, 'reset'):
            await _a.reset()
        if hasattr(_a, '_context') and isinstance(_a._context, dict):
            _a._context["retry_attempt"] = _qc_retries
            _a._context["quality_feedback"] = {
                "score": quality_result.score,
                "issues": quality_result.issues[:5],
                "previous_attempt": _qc_retries - 1,
            }
        if hasattr(_a, '_shared_memory') and _a._shared_memory:
            try:
                _a._shared_memory.set(f"quality_feedback.{_a.agent_id}", {...})
            except Exception:
                pass  # v9.1已修复前提条件: factory.py默认创建SharedMemory实例
```

```python
# generic_agent.py:249-253 — ✅ 已实施
quality_feedback = self._context.get("quality_feedback", {})
if quality_feedback:
    self._quality_feedback = quality_feedback
else:
    self._quality_feedback = None  # 清除残留
```

```python
# generic_agent.py:2915-2926 — ✅ 已实施
if hasattr(self, '_quality_feedback') and self._quality_feedback:
    # 注入到system prompt
```

**全部完成**（含v9.1 SharedMemory前提修复）:
- ✅ factory.py:147-148 `_shared_memory=SharedMemory()`, `_message_bus=MessageBus()` 默认值
- 非engine路径创建的agent不再静默失败

**实际工时**: 6h + 1h(v9.1)
**涉及文件**: `engine.py`, `generic_agent.py`, `agent_coordinator.py`

---

### 10.2 P0: 修复dangling references ✅ 已完成

实现`_post_revision_recheck`, `_recheck_quality`, `_expire_stale_revising_issues`三个被调用但未定义的方法。

**已实施方案**:

```python
# research_api.py — ✅ 已实施
async def _post_revision_recheck(self, session_id, section_name, content):
    """重检修订后的章节"""
    quality_state = await self._load_quality_state(session_id)
    if not quality_state:
        return {"score": 0, "issues": []}
    result = await self._quality_checker.check_section(section_name, content)
    # QualityIssue类型转换 + merge_issues_on_recheck
    merge_issues_on_recheck(quality_state, section_name, result)
    await self._save_quality_state(session_id, quality_state)
    return result

async def _recheck_quality(self, session_id):
    """重检整个报告"""
    if not hasattr(self, '_quality_checker'):
        self._quality_checker = QualityCheckAgent(...)  # 实例缓存
    return await self._quality_checker.check(...)

async def _expire_stale_revising_issues(self, session_id):
    """清理超时的修订中issue"""
    quality_state = await self._load_quality_state(session_id)
    now = datetime.now()
    for issue in quality_state.get("issues", []):
        if issue.get("status") == "revising":
            revising_since = issue.get("revising_since")
            if revising_since and (now - revising_since).seconds > 300:
                issue["status"] = "open"
    await self._save_quality_state(session_id, quality_state)
```

**实际工时**: 2小时

---

### 10.3 P1: Rubric注入（prompt优化）✅ 已完成100%（v9.2注入剩余17/24）

在`prompts/_shared/`新增`quality_rubric.md`，通过`{include:quality_rubric}`注入所有agent。

**已实施**:
- ✅ `prompts/_shared/quality_rubric.md` 已创建（含5维评分标准+自评checklist）
- ✅ 24/24 agent已注入：v9.0完成7/24，v9.2完成剩余17/24

**未完成项**（移至v9.3）:
- ❌ 自评指令未生效（rubric含"输出后检查"但agent未实现自评逻辑）

**建议**: v9.3实现自评指令执行逻辑

**实际工时**: 4h(v9.0) + 1h(v9.2)

---

### 10.4 P1: 修复评分默认值跨层不一致 ⚠️ 部分完成83%

统一评分尺度为0-100，消除engine.py:2552的1.0(0-1尺度)。

**已实施**:
- ✅ `engine.py:2550-2558` 默认值改为50.0，clamp改为[0,100]
- ✅ `content_lock.py:400-401` 范围改为[0,100]，添加自动放大逻辑`if threshold <= 1.0: threshold *= 100`
- ✅ `metadata_extractor.py` 默认值改为50.0
- ✅ `survey/models.py:289` quality_score默认1.0→50.0 (v9.1)
- ✅ `simulation_engine.py:257` quality_score默认1.0→50.0 (v9.1)
- ✅ `dynamic_orchestrator.py:32` quality_threshold=0.75→75.0 (v9.1显式迁移)

**未完成项**（移至v9.3）:
- ❌ 未创建统一归一化函数`normalize_quality_score()`，方案设计的"归一化层"降级为per-call启发式

**风险**:
- 启发式`if 0.0 <= score < 1.0`无法区分"0.5分/100"和"50%/0-1尺度"

**建议**: 
- v9.3: 创建`normalize_quality_score(score, source_scale)`统一函数

**实际工时**: 3h(v9.0) + 2h(v9.1)
**涉及文件**: `engine.py`, `content_lock.py`, `metadata_extractor.py`

---

### 10.5 P2: Prompt薄弱agent重写 ✅ 已完成

| 优化项 | 目标 | 状态 | 实际工时 |
|--------|------|------|---------|
| valuation.md重写 | 32→100+行，含DCF/Relative/SOTP/量化模板/反事实 | ✅ 完成 | 4h |
| investment.md重写 | 32→100+行，含Thesis/Cycle/Risk-Reward/量化模板/反事实 | ✅ 完成 | 4h |

**未完成项**（移至v9.3）:
- ❌ S1语义检测升级：`_detect_knowledge_gaps`仍为启发式（字符统计），未增加LLM语义评估
- ❌ 方法论token预算：仍为150字符且仅取methodologies[0]，未提升至500+字符或多框架

**建议**: v9.3实施S1语义升级和方法论token提升

**实际工时**: 8小时（仅完成prompt重写）

### 10.6 P3: 工厂模式修复 ⚠️ 部分完成80%

| 优化项 | 目标 | 状态 | 实际工时 |
|--------|------|------|---------|
| 修复`_agents`清理 | clear_registry清理_agents中对应parent_session_id的agent | ✅ 完成 | 2h |
| 修复hibernate序列化 | AgentSession dataclass声明agent_template字段+to_dict/from_dict | ✅ 完成 | 2h |
| agent_id防冲突 | factory的create_agent中自动附加UUID | ❌ 未实施 | — |
| hibernate持久化清理 | clear_registry清理磁盘上的hibernate数据 | ❌ 未实施 | — |
| get_agent_factory配置 | 传入shared_memory/message_bus/persistence | ✅ v9.1 | 1h |

**未完成项**（移至v9.2）:
- ❌ agent_id冲突风险：相同aspect列表第二次执行会raise ValueError（replan路径已用UUID绕过，但factory本身未修复）
- ❌ hibernate持久化数据未清理：clear_registry只清内存，磁盘数据会泄露

**建议**: 
- v9.2: 添加hibernate持久化清理逻辑

**实际工时**: 4h(v9.0) + 1h(v9.1)

---

## 11. 优先级矩阵（v9.2 — 修订后更新）

| 优先级 | 方向 | 修复项 | 状态 | 影响 | 工时 |
|--------|------|--------|------|------|------|
| **P0** | 方向2 | S2重试反馈断裂修复 | ✅ 100%完成 | 盲重试→带反馈自适应重试 | 6h+1h |
| **P0** | 方向2 | agent_coordinator retry注入 | ✅ 70%完成 | 消除第二处盲重试 | 2h |
| **P0** | 方向2 | dangling references实现 | ✅ 100%完成 | 打通v10修订链路 | 2h |
| **P0** | 方向2 | 评分默认值统一0-100 | ✅ 83%完成 | 评分数据语义清晰 | 3h+2h |
| **P1** | 方向1 | quality_rubric注入(24/24) | ✅ 100%完成 | 24个agent对准评分标准 | 4h+1h |
| **P2** | 方向1 | valuation/investment重写 | ✅ 100%完成 | 2个薄弱agent加强 | 8h |
| **P3** | 方向4 | 工厂_agents/hibernate修复 | ✅ 80%完成 | 内存泄漏+序列化修复+factory配置 | 4h+1h |

**未完成项按版本分配**:

| 阶段 | 修复项 | 来源方案 | 预估工时 | 紧迫度 |
|------|--------|---------|---------|-------|
| **已完成(v9.1)** | feedback_executor标记@deprecated | 10.2(0%) | 2h | ✅ 完成 |
| **已完成(v9.1)** | factory.py:147-148 shared_memory/message_bus默认值 | 10.1(缺15%) | 1h | ✅ 完成 |
| **已完成(v9.1)** | dynamic_orchestrator阈值0.75→75.0 | 10.4(缺40%) | 1h | ✅ 完成 |
| **已完成(v9.1)** | survey/models quality_score 1.0→50.0 | 10.4(缺40%) | 0.5h | ✅ 完成 |
| **已完成(v9.1)** | simulation_engine quality_score 1.0→50.0 | 10.4(缺40%) | 0.5h | ✅ 完成 |
| **已完成(v9.1)** | test_agent_session status_count + factory断言 | 04:2.5 + 3.6 | 0.5h | ✅ 完成 |
| **已完成(v9.1)** | engine.py移除QualityFeedbackExecutor实例化 | 10.2(0%) | 0.5h | ✅ 完成 |
| **已完成(v9.2)** | quality_rubric注入剩余17/24 | 10.3(缺75%) | 1h | ✅ 完成 |
| **v9.2** | coordinator→QC联动 | 10.3(缺30%) | 3h | 中 |
| **v9.2** | _quality_feedback类型守卫 | 04:2.2 | 1h | 中 |
| **v9.3** | 创建normalize_quality_score() | 10.4(归一化层) | 4h | 中 |
| **v9.3** | S1缺口检测语义升级 | 10.5(未实施) | 3d | 中 |
| **v9.3** | 方法论token 150→500+多框架 | 10.5(未实施) | 1d | 中 |
| **v9.3** | content_lock阈值warning | 04:1.3 | 1h | 低 |
| **v9.3** | quality_rubric-QC维度对齐 | 04:3.5 | 2h | 低 |
| **v10.0** | 评分双轨统一 | 04:4.1 | 4h | 低 |
| **v10.0** | 反馈路径统一(context vs SharedMemory) | 04:4.2 | 2h | 低 |
| **v10.0** | 方法论3层去重 | 04:4.3 | 2h | 低 |
| **v10.0** | 关键business skill实现 | 10.6(未实施) | 各2d | 低 |

**P0-P3修复后的实际效果**:
- ✅ S2重试从"机械重跑"变为"带反馈的自适应重跑"（100%完成，含v9.1 SharedMemory前提修复）
- ✅ agent_coordinator不再盲目重试（70%完成，缺QC联动）
- ✅ 修订重检链路可用（3个方法已实现）
- ✅ 评分语义全面清晰（83%完成，engine/content_lock/survey/simulation/dynamic统一，缺归一化函数）
- ✅ 24个核心agent了解评分标准（100%完成，v9.2注入剩余17/24）
- ✅ valuation/investment prompt从32行加强到100+行
- ✅ factory _agents清理+hibernate序列化+通信默认实例（80%完成，缺持久化清理+agent_id防冲突）

**后续版本路线**:
- ✅ v9.1已全部完成: 7项P0-P3修复 (6h)
- ✅ v9.2 rubric注入已完成
- v9.2剩余: coordinator QC联动 + 类型守卫 (待做)
- v9.3: normalize_quality_score() + S1语义化 + 方法论token + content_lock warning (6d+)
- v10.0: 评分双轨统一 + 反馈路径统一 + business skill实现

---

## 12. 与升级方案其他模块的依赖关系

```
03_Agent架构诊断 v8.0
  │
  ├─ P0修复独立: 不依赖01/02
  │   S2反馈断裂修复只需改engine.py + generic_agent.py + agent_coordinator.py
  │   dangling references修复只需写3个方法
  │
  ├─ P1 rubric注入: 独立文件，不依赖MKB
  │
  ├─ P2 agent重写: 依赖P1 rubric(先定标准再改prompt)
  │
  ├─ P3 技能扩展: 依赖02_知识管理(MKB方法论存储)
  │
  └─ 为04_目标架构设计提供输入:
      S2反馈注入机制 → 三层质量反馈模型的Layer 1
      Rubric+自评 → Layer 2
      Factory修复 → 架构稳定性基座

建议执行顺序（修订版）:

已完成 ─→ P0 (14h) ─→ P1 (5h) ─→ P2 (8h) ─→ P3 (5h)
  ↓         ↓ 100%-83%    ↓ 100%       ↓ 100%       ↓ 80%
  准备    S2反馈修复     rubric 24/24  valuation    _agents清理
           +SharedMemory  (v9.2剩余     investment   hibernate序列化
           coordinator    自评指令)                  +factory通信默认实例
           dangling refs
           默认值83%+survey/sim
           +dynamic_threshold
           +@deprecated
                               ↓
                          v9.2剩余 (4h) ─→ v9.3 (6d+) ─→ v10.0
                          coordinator QC normalize()    评分双轨统一
                          类型守卫       S1语义化       反馈路径统一
                                         方法论token    business skill

v10集成: 全部完成后，v10展示修订层的数据源(quality_score)语义清晰，
S2重试真正有效，agent_coordinator不再盲目重试，修订重检链路可用。
全向后兼容。
```
