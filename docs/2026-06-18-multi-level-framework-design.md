# 多级研究框架支持方案

> 日期：2026-06-18
> 状态：问题分析 + 改造方案（已审查修订）
> 关联：用户反馈"前端不支持多级研究框架"

---

## 1. 问题描述

用户输入一级研究框架（8个章节），要求扩展到三级子框架。LLM 正确生成了三级框架内容，但系统无法正确处理：

1. **LLM 第一次返回**：JSON 解析失败（`Expecting ',' delimiter`），因为 LLM 在 `framework_sections` 字段中输出了多级嵌套结构，不符合 `string[]` schema
2. **LLM 第二次返回**（retry）：LLM 改为输出 markdown 格式的三级框架，但系统无法从中提取 JSON（`Could not extract JSON from LLM response`）
3. **LLM 第三次返回**（retry 成功）：LLM 放弃了多级结构，退化为扁平 `framework_sections: ["section1", "section2"]` 格式

**根因**：系统全链路只支持一级扁平框架，不支持二级/三级子框架。

---

## 2. 当前链路分析

### 2.1 数据流

`framework_sections` 在 `_handle_user_message()` 中有 3 个消费入口（L397 PAUSED状态、L450 EXECUTING状态、L622 UNDERSTANDING/CLARIFYING状态），逻辑完全相同：从 LLM 返回的 `conv_result` 中提取 `framework_sections`，存入 `context['_suggested_sections']`，然后调用 `_enter_framework_mode()`。

完整数据流：

1. 用户输入 → `_llm_converse()` → LLM 返回 JSON（含 `framework_sections: string[]`）
2. `_build_response()`（L1040-1045）将 `framework_sections` 透传到 `conv_result`
3. `_handle_user_message()` 中 3 个 `enter_framework` 分支（L397/L450/L622）提取 `framework_sections` → `context['_suggested_sections']`
4. `_enter_framework_mode()` 合并 `_suggested_sections` + `directions` → `framework = {topic, sections: string[], output_type, depth, region, time_range}`
5. `_framework_response()` 将 `framework` dict 返回前端，同时用 `_format_framework()` 格式化为文本消息
6. 用户确认 → `_should_start_execution()` 关键词匹配触发 → `_start_execution()` → `final_plan = {topic, aspects: sections, ...}`（**注意：`final_plan` 不含 `sections_tree` 和 `section_details`**）
7. `research_executor.py` → `orchestrator.research(custom_aspects=framework.get("sections"))`
8. `orchestrator.py:_parse_requirement()` → 从 aspects 自动生成 `section_details = [{id, name, content}]`（`content` 等于 `name`，无描述信息）
9. `ResearchRequirement(aspects: List[str], section_details: List[Dict])`（定义在 `smart_clarifier.py:114`）
10. `decompose()`（定义在 `src/core/decomposition/strategies.py:398`）→ 每个 aspect 生成 1 个 DATA_COLLECTION agent
11. `section_data_specs`（由 `SemanticIntentAnalyzer._analyze_with_llm()` 独立调用 LLM 生成，非 `_llm_converse` 阶段）提供二级子结构

### 2.2 各层限制

| 层级 | 当前结构 | 限制 |
|------|----------|------|
| **LLM JSON Schema** | `framework_sections: string[]` | 只允许一级字符串数组 |
| **ResearchFramework (前端类型)** | 扁平 `sections: string[]` | 扁平字符串数组 |
| **SelectOption (前端类型)** | 扁平 `id/label/description` | 无 `children`，无层级支持 |
| **SectionSelector (前端组件)** | `SelectOption[]` 扁平列表 | 无层级展示，无折叠/缩进 |
| **_format_framework()** | `1. section_name — description`（支持 `section_details` 附加描述） | 无层级格式化，`section_details` 仅提供扁平描述 |
| **_enter_framework_mode()** | `framework.sections = all_sections` | 扁平合并 |
| **_start_execution()** | `final_plan.aspects = sections` | 扁平传递，**不传递 `sections_tree` 和 `section_details`** |
| **ResearchRequirement** | `aspects: List[str]`（定义在 `smart_clarifier.py:114`） | 扁平字符串列表 |
| **decompose()** | 每个aspect → 1个agent | 一级aspect对应一个agent，二级通过section_data_specs补充 |

### 2.3 已有的二级支持（部分）

`section_data_specs`（Phase B 实现）已经提供了二级子结构。每个 `SectionDataSpec`（`src/core/decomposition/strategies.py:133`）包含 `section_id`、`name` 和 `sub_sections: List[SubSectionSpec]`，每个 `SubSectionSpec`（L125）包含 `sub_section_id`、`name`、`data_needs: List[str]` 和 `data_source_type`。

但这个二级结构：
- **来源**：由 `SemanticIntentAnalyzer._analyze_with_llm()`（`src/core/semantic_intent.py:272`）独立调用 LLM 生成（使用 `prompts/agents/intent_analysis_system.md` 作为 system prompt），并非在 `_llm_converse` 对话阶段生成
- **用途**：仅在 `decompose()` 中用于生成 `data_needs`/`search_data_needs`，影响搜索查询规划；在 `engine.py:1065` 中初始化，用于 `_unified_search`（L1928）和 `_supplement_missing_data`（L1439）
- **不展示**：前端完全看不到这个二级结构
- **不交互**：用户无法确认/修改二级子框架

### 2.4 三级框架的缺失

用户期望的三级结构：

```
1. 核心财务指标与盈利能力          ← 一级（section）
   1.1 营收与利润趋势              ← 二级（sub_section）
      1.1.1 年度营收规模及增长率    ← 三级（data_need / research_point）
      1.1.2 归母净利润走势
      1.1.3 收入结构分析
   1.2 盈利能力指标
      1.2.1 毛利率与净利率
      1.2.2 ROE与ROIC
```

当前系统中：
- **一级** = `framework.sections[i]` = `aspects[i]` → 1个DATA_COLLECTION agent + 1个DEEP_ANALYSIS agent
- **二级** = `section_data_specs[i].sub_sections[j]` → 仅影响 data_needs，不生成独立 agent
- **三级** = `sub_sections[j].data_needs[k]` → 仅影响搜索关键词，无独立实体

### 2.5 智能路由拆分：当前如何处理三级框架

当前拆分逻辑（`src/core/decomposition/strategies.py:decompose()`，L398-586）完全按一级 aspect 进行：

1. **DATA_COLLECTION 阶段**（L440-465）：每个 aspect 生成 1 个 agent，搜索整个 aspect 范围的数据
2. **DATA_VALIDATION 阶段**（L467-489）：每个 aspect 生成 1 个验证 agent
3. **DEEP_ANALYSIS 阶段**（L491-512）：每个 aspect 生成 1 个分析 agent，LLM 自行决定如何组织分析内容
4. **SYNTHESIS 阶段**（L514-540）：dependent aspects（summary/conclusion）生成综合 agent
5. **REPORT_GENERATION 阶段**（L542-567）：1 个报告生成 agent

**二级/三级信息在拆分中的唯一作用**：通过 `section_data_specs` 影响 DATA_COLLECTION agent 的 `context["data_needs"]` 和 `context["search_data_needs"]`（L462-463），进而影响 `_unified_search` 生成的搜索查询。agent 本身的 `task_description` 和 `system_prompt` 仍然是按一级 aspect 整体构建的（`_build_data_collection_prompt(topic, aspect, framework_config)`），不区分二级子主题。

**关键问题**：如果用户提供了三级框架，但系统只按一级拆分 agent，每个 agent 需要处理范围更大的内容。LLM 在 DEEP_ANALYSIS 阶段自行决定二级/三级结构，但这个结构可能与用户提供的框架不一致。

### 2.6 报告合成：当前如何处理三级结构

报告合成链路：

1. **result_aggregator.aggregate()**（`src/core/orchestrator/aggregation/result_aggregator.py` L980-1254）：按 `section_details` 将 agent 结果映射到章节
   - `section_details` 来自 `ResearchRequirement.section_details`（L984）
   - 当前 `section_details` 格式：`[{id: "核心财务指标与盈利能力", name: ..., content: ...}]`，仅包含一级信息
   - 每个 section 的内容来自 1 个 DEEP_ANALYSIS agent 的输出
   - 内容匹配策略：先按 `section_id`/`section_name` 精确匹配，再按归一化模糊匹配，最后按索引映射（L293-444）

2. **_parse_markdown_subsections()**（L1461-1520）：从 agent 输出的 Markdown 中自动解析子章节
   - 识别 `### 标题` / `#### 标题` / `**加粗标题**` 等模式
   - 返回子章节列表，每个元素包含 `id`（基于标题生成）、`title`（标题文本）、`content`（标题下内容）
   - **这是当前系统中唯一的二级结构来源** — 完全依赖 LLM 在 DEEP_ANALYSIS 阶段输出的 Markdown 格式

3. **ContentSection**（`src/content/content_orchestrator.py` L67-85）：报告渲染的数据结构
   - 支持 `subsections: Optional[List["ContentSection"]]` 递归嵌套（L78）
   - 解析层 `_parse_sections()`（L475-546）递归调用自身，支持 `MAX_RECURSION_DEPTH=10`
   - HTML 渲染时：一级 section 用 `<h2>`，二级 subsection 用 `<h3>`（L738-751）
   - **解析支持递归，但渲染不支持**：模板渲染 `_prepare_template_variables()`（L326-335）只处理1层 subsection；HTML 回退渲染 `_render_section_html()`（L738-751）只迭代1层不检查 `subsec.subsections`

4. **document_generation_agent**（`src/agents/fixed_agents/document_generation_agent.py` L632-656）：Docx 生成也处理 `subsections`
   - 主路径 `_populate_document_content()`（L632-656）：subsection 用 `level=2` 标题，不递归
   - 回退路径 `_fallback_generate_document()`（L1506-1517）：subsection 用 `level=2` 标题，不递归
   - **两个路径都不支持嵌套 subsection**

**关键问题**：
- 当前二级结构完全由 LLM 在 DEEP_ANALYSIS 阶段自行决定（通过 Markdown 标题格式），与用户提供的框架无关
- 如果用户提供了"1.1 营收与利润趋势 / 1.2 盈利能力指标"的二级结构，LLM 可能输出不同的二级标题（如"一、收入分析 / 二、利润分析"），导致不一致
- `_parse_markdown_subsections()` 只解析到二级（`###`/`####`），没有三级解析
- `ContentSection.subsections` 解析层支持递归，但渲染层（HTML/Docx/TOC）均只支持1层，嵌套 subsection 被静默丢弃

---

## 3. 改造方案

### 3.1 设计原则

1. **框架-输出一致性（最高优先级）**：用户确认了几级框架，最终报告就必须严格按该框架输出。三级框架→三级输出，二级框架→二级输出，不允许出现框架是三级但输出降级为一级/二级的情况
2. **向后兼容**：扁平 `framework_sections: string[]` 仍然有效，多级结构是扩展
3. **最小改动**：复用现有 `section_data_specs` 机制和 `ContentSection.subsections` 递归结构，不引入全新数据结构
4. **用户可控**：用户可以确认/修改二级子框架
5. **前后端一致**：前端确认结果必须结构化传回后端，不能仅依赖自然语言文本

### 3.2 框架-输出一致性：8 个断裂点

当前系统中，用户框架到最终报告之间有 8 个断裂点，每一个都会导致输出结构与框架不一致：

| 断裂点 | 位置 | 现状 | 后果 |
|--------|------|------|------|
| **B1: Agent prompt 无二级结构** | `src/core/decomposition/strategies.py` L459 `_build_data_collection_prompt(topic, aspect, framework_config)` 和 L509 `_build_analysis_prompt(topic, aspect, framework_config)` | 只传入一级 `aspect`，不传二级子主题 | DATA_COLLECTION agent 和 DEEP_ANALYSIS agent 不知道用户框架的二级结构，LLM 自行决定搜索范围和分析结构 |
| **B2: deep_analysis.md prompt 无结构约束** | `prompts/tasks/deep_analysis.md` L47-54 | `Output Structure` 要求固定 5 段（Core Judgment / Logical Derivation / Data Support / Counter Evidence / Implication），没有要求按用户框架的二级结构组织输出 | LLM 输出的 Markdown 标题与用户框架的二级标题不一致 |
| **B3: result_aggregator 的 subsections 来自自动解析** | `src/core/orchestrator/aggregation/result_aggregator.py` L461 `_parse_markdown_subsections(content)` | 从 LLM 输出的 Markdown 标题自动解析子章节，与 `framework_tree` 无关 | 报告的二级结构与用户框架的二级结构不一致 |
| **B4: section_details 无二级信息** | `src/core/orchestrator/orchestrator.py` L3221-3224 `_parse_requirement()` | `section_details = [{id, name, content}]`，只有一级（`content` 等于 `name`，无描述） | `result_aggregator` 无法按框架二级结构组织章节 |
| **B5: 报告渲染不支持三级** | `src/content/content_orchestrator.py` L738-751（HTML）、L326-335（模板）、L587-593（TOC）；`src/agents/fixed_agents/document_generation_agent.py` L632-656（Docx主路径）、L1506-1517（Docx回退路径） | HTML/Docx/TOC 均只渲染1层 subsection，嵌套 subsection 被静默丢弃 | 即使数据中有三级结构，渲染也会丢失 |
| **X1: _start_execution() 不传递 sections_tree** | `src/api/research_api.py` L1309-1355 `_start_execution()` | `final_plan = {topic, aspects: sections}` 只有扁平 aspects，不含 `sections_tree` 和 `section_details` | 框架树结构在执行入口就丢失，后续链路无法获取多级信息 |
| **X2: 前端确认只发自然语言** | `web/src/components/chat/ChatPanel.tsx` L391-403 `handleFrameworkSectionConfirm()` | 通过 `clickSuggestion('confirm_start', exampleText)` 发送自然语言文本，无结构化数据 | 后端无法知道用户勾选了哪些二级子框架，无法更新 `sections_tree` |
| **X3: _build_response() 不透传 framework_tree** | `src/api/research_api.py` L1040-1045 `_build_response()` | 只透传 `framework_sections`，不透传 `framework_tree` | 3个消费入口永远拿不到 `framework_tree` |

**一致性保证的核心逻辑**：要从 B1→B5 + X1→X3 全链路贯通，用户框架的每一级都必须在对应环节被注入。

### 3.3 数据结构扩展

#### 3.3.1 LLM JSON Schema 扩展

**文件**：`src/api/research_api.py` L171-186

在现有 `_JSON_OUTPUT_SCHEMA` 中增加 `framework_tree` 字段，与 `framework_sections` 并列。

`framework_sections` 保持现有格式（扁平字符串数组，向后兼容）。

`framework_tree` 新增格式：对象数组，每个对象包含 `name`（一级章节名）和 `sub_sections`（二级子主题数组），每个 `sub_sections` 元素包含 `name`（二级章节名）和 `points`（三级研究要点字符串数组）。

示例：用户输入"比亚迪公司财务分析"的8章节三级框架，`framework_tree` 包含8个对象，每个对象有2-3个 `sub_sections`，每个 `sub_sections` 有2-4个 `points`。

**规则**：
- 如果 LLM 输出 `framework_tree`，从 `framework_tree` 派生扁平 `sections`（取每个 `name` 字段），`framework_tree` 优先
- 如果只有 `framework_sections`，使用扁平模式（向后兼容）
- LLM 可同时输出两者，但 `framework_sections` 将被 `framework_tree` 派生的扁平列表覆盖，避免不一致

#### 3.3.2 ResearchFramework 类型扩展

**改动位置**：`web/src/types/api.ts` L43-50

当前 `ResearchFramework` 接口包含 `topic`、`sections: string[]`、`output_type`、`depth`、`region`、`time_range`。

改造后增加两个新接口和 `sections_tree` 可选字段：

- `FrameworkSection`：包含 `name: string`（一级章节名）和 `sub_sections?: FrameworkSubSection[]`（二级子主题）
- `FrameworkSubSection`：包含 `name: string`（二级章节名）和 `points?: string[]`（三级研究要点）
- `ResearchFramework.sections_tree?: FrameworkSection[]`：新增可选字段，多级模式

**注意**：前端已有 `SectionInfo` 接口（`web/src/lib/api.ts:74-81`），包含 `children?: SectionInfo[]`、`level: number`、`parent?: string`，仅用于已完成后报告的 `getSections` API 和 `RevisionPanel` 组件。`FrameworkSection`/`FrameworkSubSection` 与 `SectionInfo` 的区别在于：前者是框架确认阶段的轻量类型（只含 name/points），后者是报告完成后的完整类型（含 id/word_count/level/parent/children）。两者用途不同，暂不复用，但后续可考虑统一。

#### 3.3.3 后端 framework dict 扩展

**改动位置**：`src/api/research_api.py` L1296（`_enter_framework_mode()` 中构建 framework dict 的位置）

当前 framework dict 包含 `topic`、`sections`、`output_type`、`depth`、`region`、`time_range` 字段。改造后增加 `sections_tree` 字段（多级嵌套结构），`sections` 保持扁平字符串列表（向后兼容）。

### 3.4 各层改造清单

#### Phase 1: LLM Prompt + 解析（后端）

| 文件 | 改动 | 说明 |
|------|------|------|
| `src/api/research_api.py:_JSON_OUTPUT_SCHEMA` | 增加 `framework_tree` 字段定义 | LLM 输出 schema 扩展 |
| `src/api/research_api.py:_build_initial_prompt()` | 增加 `framework_tree` 生成指引 | 引导 LLM 输出多级结构 |
| `src/api/research_api.py:_build_response()` | 增加 `framework_tree` 透传 | **修复 X3**：将 LLM 输出的 `framework_tree` 透传到 `conv_result` |
| `src/api/research_api.py:_enter_framework_mode()` | 解析 `framework_tree`，构建 `sections_tree` | 新增解析逻辑 |
| `src/api/research_api.py:_format_framework()` | 支持多级缩进格式化 | `1. → 1.1 → 1.1.1` |
| `src/api/research_api.py:_framework_response()` | 传递 `sections_tree` 到前端 | 响应中包含多级数据 |
| `src/api/research_api.py:_start_execution()` | 传递 `sections_tree` 和 `section_details` 到 `final_plan` | **修复 X1** |
| `src/api/research_executor.py` | 传递 `sections_tree` 和 `section_details` 到 `user_input_dict` | **X1 关键链接**：`research()` → `_parse_requirement()` 的数据通道 |
| `src/api/research_api.py:_handle_framework_mode()` | 修改框架时保留 `sections_tree` | 用户修改框架时树结构不丢失 |
| `src/api/research_api.py:_llm_framework_modify()` | prompt 增加 `new_framework_tree` 输出字段 | LLM 修改框架时也能输出多级结构 |

#### Phase 2: 前端展示 + 结构化确认

| 文件 | 改动 | 说明 |
|------|------|------|
| `web/src/types/api.ts` | `ResearchFramework` 增加 `sections_tree` | 类型定义 |
| `web/src/components/chat/SectionSelector.tsx` | 支持树形展示（折叠/缩进） | 核心UI改造 |
| `web/src/components/chat/ChatPanel.tsx` | 从 `sections_tree` 构建层级选择数据 | 数据适配 |
| `web/src/components/chat/ChatPanel.tsx` | `handleFrameworkSectionConfirm` 发送结构化数据 | **修复 X2** |
| `web/src/lib/api.ts` | 新增 `confirmFramework` API 或扩展 `clickSuggestion` | 支持结构化确认 |

#### Phase 3: 执行链路适配

| 文件 | 改动 | 说明 |
|------|------|------|
| `src/core/orchestrator/orchestrator.py:_parse_requirement()` | `section_details` 从 `sections_tree` 构建 | 保留二级信息 |
| `src/core/decomposition/strategies.py:decompose()` | 使用 `section_details` 中的二级信息增强 agent | 复用 section_data_specs 机制 |

### 3.5 关键设计决策

#### Q1: 二级子框架是否生成独立 agent？

**建议：否**。原因：
- 当前每个一级 section 对应 1 个 DATA_COLLECTION agent + 1 个 DEEP_ANALYSIS agent
- 为每个二级生成独立 agent 会大幅增加 agent 数量（8 section × 2-3 sub = 16-24 agent），增加调度复杂度

**但必须解决 B1 断裂点**：当前 `_build_data_collection_prompt()` 和 `_build_analysis_prompt()` 只传入一级 `aspect`，agent 不知道二级结构。修复方案：

- `decompose()` 中 DATA_COLLECTION agent 的 `context` 增加 `"sub_aspects": [sub.name for sub in matched_spec.sub_sections]`
- DEEP_ANALYSIS agent 的 `context` 同样增加 `"sub_aspects"`
- `_build_data_collection_prompt()` 在 prompt 中注入二级子主题列表，引导 agent 按指定结构搜索
- `_build_analysis_prompt()` 在 prompt 中注入二级子主题列表，要求 LLM 按指定二级标题输出分析

#### Q2: 三级研究要点如何处理？

**建议：作为 `data_needs` 传入**。原因：
- 三级要点（如"年度营收规模及增长率"）本质上是具体的数据需求
- 已有 `SubSectionSpec.data_needs` 机制完美匹配
- LLM 在 `section_data_specs` 中生成的 `data_needs` 就是三级要点

**但必须保证三级要点在输出中可见**：解决 B2 断裂点，`deep_analysis.md` prompt 需要增加"按框架子主题逐项分析"的要求，使 LLM 输出的 Markdown 在每个二级标题下包含三级要点对应的内容段落。

#### Q3: 报告合成如何保证框架-输出一致性？

**必须解决 B3 和 B4 两个断裂点**：

**B4 修复**：`_parse_requirement()` 中，当 `framework_tree` 存在时，`section_details` 必须包含二级子结构：

- 当前 `section_details` 每个元素只有 `id`、`name`、`content` 三个字段
- 修复后增加 `sub_sections` 字段，每个 `sub_sections` 元素包含 `name` 和 `points`

具体改动位置：`src/core/orchestrator/orchestrator.py` L3221-3224。当 `user_input["aspects"]` 存在且 `user_input` 包含 `sections_tree` 时，从 `sections_tree` 构建带二级信息的 `section_details`。

**B3 修复**：`result_aggregator` 中，当 `section_details` 包含 `sub_sections` 时，不再依赖 `_parse_markdown_subsections()` 自动解析，而是用框架的二级结构作为骨架：

1. 遍历 `section.sub_sections`，每个 sub_section 对应报告中的一个 subsection
2. 将 LLM 输出内容按二级标题匹配到框架的 sub_section 中（复用现有的归一化匹配逻辑）
3. 如果 LLM 输出的某个二级标题在框架中找不到匹配，记录警告但仍然保留
4. `_parse_markdown_subsections()` 保留为 fallback：当 `section_details` 不包含二级信息时仍使用自动解析

#### Q4: 报告渲染如何支持三级？

**必须解决 B5 断裂点**，需要 **5 处**改造（非仅2处）：

1. `result_aggregator` 在构建 subsection 时，如果 `sub_section` 有 `points`（三级要点），将 LLM 输出中对应的段落内容提取出来，作为 subsection 的嵌套 `subsections`
2. `src/content/content_orchestrator.py` 的模板渲染 `_prepare_template_variables()`（L326-335）增加递归处理：subsection 的 subsection 用 `<h4>` 标题
3. `src/content/content_orchestrator.py` 的 HTML 回退渲染 `_render_section_html()`（L738-751）增加递归：检查 `subsec.subsections` 并渲染为 `<h4>`
4. `src/content/content_orchestrator.py` 的 TOC 渲染（L587-593）增加三级目录项
5. `src/agents/fixed_agents/document_generation_agent.py` 的 Docx 渲染增加三级支持：
   - 主路径 `_populate_document_content()`（L632-656）：检查 `subsection.get("subsections")`，三级标题用 `level=3`
   - 回退路径 `_fallback_generate_document()`（L1506-1517）：同上

#### Q5: 用户确认时能否勾选/取消二级子框架？

**建议：Phase 1 仅展示，Phase 2 支持勾选**。原因：
- Phase 1 先让用户看到完整的多级框架，确认一级即可
- Phase 2 再增加二级勾选功能，允许用户精细控制

**但 Phase 2 必须解决 X2 断裂点**：当前前端 `handleFrameworkSectionConfirm()`（`ChatPanel.tsx:391-403`）只发送自然语言文本，必须改为结构化确认。方案：

1. 新增 `confirmFramework` API 方法（或扩展 `clickSuggestion`），发送结构化 payload：
   ```typescript
   payload = {
     suggestion_id: 'confirm_start',
     selected_sections: ['section-0', 'section-2'],           // 一级勾选
     selected_sub_sections: ['section-0.sub-1', ...],        // 二级勾选
     sections_tree_override: modifiedSectionsTree             // 用户修改后的树结构（可选）
   }
   ```
2. 后端 `_handle_user_message()` 新增 `confirm_framework` action 处理，根据结构化数据更新 `framework['sections']` 和 `framework['sections_tree']`，再调用 `_start_execution()`
3. 当前 `_should_start_execution()`（`research_api.py:304`）依赖关键词匹配触发确认，结构化确认需要新增触发路径

#### Q6: `framework_tree` 和 `section_data_specs` 的关系？

**建议：统一**。`framework_tree` 是用户可见的框架结构，`section_data_specs` 是执行层的数据规格。两者应该对齐：
- `framework_tree[i].name` = `section_data_specs[i].name`
- `framework_tree[i].sub_sections[j].name` = `section_data_specs[i].sub_sections[j].name`
- `framework_tree[i].sub_sections[j].points` = `section_data_specs[i].sub_sections[j].data_needs`

理想情况下，`section_data_specs` 应该从 `framework_tree` 派生，而非由 intent_analysis LLM 独立生成。但这需要更大的重构，建议分步实施。

**P0 阶段的对齐策略**：`framework_tree` 和 `section_data_specs` 独立生成时可能产生二级标题不一致。例如：
- `framework_tree` 的二级: `["营收与利润趋势", "盈利能力指标"]`
- `section_data_specs` 的二级: `["收入分析", "利润分析"]`（由 intent_analysis LLM 独立生成）

B1 修复会注入 `framework_tree` 的二级结构到 agent prompt，但 `section_data_specs` 的 `data_needs` 基于自己的二级结构生成搜索关键词。两者冲突时 agent 收到的指令矛盾。

**P0 最小对齐**：在 `decompose()` 中（`src/core/decomposition/strategies.py:425-427`），当 `framework_tree` 存在时，用 `framework_tree` 的 `sub_sections.name` 覆盖 `section_data_specs` 中对应的 `sub_sections[j].name`，保持 `data_needs` 不变。具体逻辑：
1. 按 `section_id` 匹配 `framework_tree[i]` 和 `section_data_specs[k]`
2. 对每个匹配的 section，用 `framework_tree[i].sub_sections` 的 `name` 和 `points` 更新 `section_data_specs[k].sub_sections` 的 `name` 和 `data_needs`
3. 如果 `framework_tree` 中有 `section_data_specs` 没有的 sub_section，追加到 `section_data_specs`

### 3.6 实施优先级

| 优先级 | 内容 | 解决的断裂点 | 价值 |
|--------|------|-------------|------|
| **P0** | LLM prompt + 解析支持 `framework_tree` | — | 解决当前 JSON 解析失败问题 |
| **P0** | X3: `_build_response()` 透传 `framework_tree` | X3 | 3个消费入口能拿到 `framework_tree` |
| **P0** | `_format_framework()` 多级格式化 | — | 用户能在聊天中看到多级框架 |
| **P0** | X1: `_start_execution()` 传递 `sections_tree` 和 `section_details` | X1 | 框架树结构不在执行入口丢失 |
| **P0** | B1: Agent prompt 注入二级结构 | B1 | LLM 按框架结构输出分析 |
| **P0** | B2: `deep_analysis.md` 增加结构约束 | B2 | LLM 输出 Markdown 标题与框架二级标题一致 |
| **P0** | B4: `section_details` 包含二级信息 | B4 | `result_aggregator` 可按框架组织章节 |
| **P0** | B3: `result_aggregator` 用框架骨架替代自动解析 | B3 | 报告二级结构与用户框架一致 |
| **P0** | `framework_tree` → `section_data_specs` P0 对齐 | — | 避免二级标题冲突 |
| **P1** | 前端 `SectionSelector` 树形展示 | — | 用户能在UI中看到层级结构 |
| **P1** | B5: 报告渲染支持三级（5处改造） | B5 | 三级框架→三级输出不丢信息 |
| **P1** | `_handle_framework_mode()` 修改时保留 `sections_tree` | — | 用户修改框架时树结构不丢失 |
| **P2** | X2: 前端结构化确认 API | X2 | 前端勾选结果可传回后端 |
| **P2** | 前端二级勾选 | — | 用户能精细控制子框架 |
| **P3** | `framework_tree` → `section_data_specs` 完全统一 | — | 消除两套独立生成的二级结构 |
| **P3** | `_infer_framework_sections_from_conversation()` 返回 `sections_tree` | — | Fallback 路径也支持多级 |

---

## 4. P0 实施细节

### 4.1 `_JSON_OUTPUT_SCHEMA` 扩展

**文件**：`src/api/research_api.py` L171-186

在现有 `_JSON_OUTPUT_SCHEMA` 中增加 `framework_tree` 字段定义，与 `framework_sections` 并列。同时在 schema 说明中增加规则：当 `action="enter_framework"` 时，如果用户提供了多级框架，优先使用 `framework_tree`；简单场景仍可用 `framework_sections`。

### 4.2 X3 修复：`_build_response()` 透传 `framework_tree`

**文件**：`src/api/research_api.py` L1040-1045

当前 `_build_response()` 只透传 `framework_sections`，必须增加 `framework_tree` 的透传：

```python
# L1040-1045 当前代码
def _build_response(self, parsed, tool_results, note):
    response = {
        'status': 'done',
        'message': parsed.get('message', ''),
        'action': parsed.get('action', 'continue_chat'),
        'topic': parsed.get('topic'),
        'directions': parsed.get('directions', []),
        'framework_sections': parsed.get('framework_sections'),
        # ← 必须增加下一行
        'framework_tree': parsed.get('framework_tree'),
        'clarification_questions': parsed.get('clarification_questions', []),
        ...
    }
```

**如果不改此处，LLM 输出的 `framework_tree` 在 `_build_response()` 阶段就被丢弃，§4.3 中3个消费入口永远拿不到。**

### 4.3 `framework_tree` 数据提取 — 3 个消费入口

**核心问题**：`framework_sections` 在 `_handle_user_message()` 中有 3 个提取入口（L397/L450/L622），`framework_tree` 必须在同样的 3 个位置同步提取。

**改动位置**：

1. **L397**（PAUSED 状态 `enter_framework` 分支）：在 `fw_sections = conv_result.get('framework_sections')` 之后，增加 `fw_tree = conv_result.get('framework_tree')`，存入 `context['_framework_tree']`
2. **L450**（EXECUTING 状态 `enter_framework` 分支）：同上
3. **L622**（UNDERSTANDING/CLARIFYING 状态 `enter_framework` 分支）：同上

**注意**：`conv_result` 仅在 `_handle_user_message()` 中可用，`_enter_framework_mode()` 无法直接访问。因此 `framework_tree` 必须通过 `context['_framework_tree']` 传递。

### 4.4 `_enter_framework_mode()` 改造

**文件**：`src/api/research_api.py` L1265-1307

在 `_enter_framework_mode()` 中（L1286 之后），从 `context` 读取 `_framework_tree`：

- 如果 `_framework_tree` 存在且有效，从其 `name` 字段派生扁平 `sections`（覆盖 `_suggested_sections` 和 `directions` 的合并结果），并将 `sections_tree` 存入 `framework` dict
- 如果 `_framework_tree` 不存在，保持现有逻辑不变

构建 framework dict 时增加 `sections_tree` 字段：

- `framework['sections']` = 扁平字符串列表（向后兼容）
- `framework['sections_tree']` = 多级嵌套结构（新增）

### 4.5 `_format_framework()` 改造

**文件**：`src/api/research_api.py` L1627-1648

现有代码处理 `section_details`（L1630-1638），支持 list/dict 两种格式，格式化时附加 `— {desc}`。改造时保留 `section_details` 逻辑作为 fallback，增加 `sections_tree` 的多级格式化：

- 如果 `framework` 包含 `sections_tree`，按 `1. → 1.1 → 1.1.1` 三级格式化输出
- 如果没有 `sections_tree` 但有 `section_details`，保持现有 `1. section_name — description` 格式
- 如果两者都没有，输出 `1. section_name` 纯编号列表

### 4.6 `_framework_response()` 改造

**文件**：`src/api/research_api.py` L1673-1684

现有代码已将 `framework` dict 完整返回前端（L1681: `framework_data = session.get('research_context', {}).get('framework')`），只需确保 `framework` dict 中包含 `sections_tree` 字段即可。无需额外改动，因为 §4.4 已将 `sections_tree` 存入 `framework` dict。

### 4.7 X1 修复：`_start_execution()` 传递 `sections_tree` 和 `section_details`

**文件**：`src/api/research_api.py` L1309-1355

当前 `_start_execution()` 构建的 `final_plan` 只有扁平 `aspects`，不含 `sections_tree` 和 `section_details`。必须扩展：

```python
# L1309-1355 当前关键代码
final_plan = {
    'topic': topic,
    'aspects': sections,    # ← 扁平列表
    'region': ...,
    'time_range': ...,
    'framework': framework.get('depth', 'standard'),
    'language': session.get('language', 'zh')
    # ← 缺少 sections_tree 和 section_details
}

# 改造后
sections_tree = framework.get('sections_tree')
final_plan = {
    'topic': topic,
    'aspects': sections,
    'sections_tree': sections_tree,                          # 新增
    'section_details': self._build_section_details_from_tree(sections_tree)
                               if sections_tree else [],     # 新增
    'region': ...,
    'time_range': ...,
    'framework': framework.get('depth', 'standard'),
    'language': session.get('language', 'zh')
}
```

其中 `_build_section_details_from_tree()` 新增辅助方法，从 `sections_tree` 构建带二级信息的 `section_details`：

```python
def _build_section_details_from_tree(self, sections_tree):
    if not sections_tree:
        return []
    details = []
    for st in sections_tree:
        name = st.get('name', '')
        sub_sections = st.get('sub_sections', [])
        detail = {
            'id': name.lower().replace(' ', '_'),
            'name': name,
            'content': name,
            'sub_sections': [
                {'name': sub.get('name', ''), 'points': sub.get('points', [])}
                for sub in sub_sections
            ]
        }
        details.append(detail)
    return details
```

**后续链路对接**：`final_plan` 传给 `research_executor.execute()`，最终到 `ResearchOrchestrator.research()`。在 `_parse_requirement()` 中（§4.12），当 `user_input` 包含 `sections_tree` 和 `section_details` 时，优先使用它们。

### 4.7a X1 关键链接：`research_executor.py` 传递 `sections_tree`/`section_details`

**文件**：`src/api/research_executor.py` L335-340

`_start_execution()` 将 `sections_tree` 和 `section_details` 存入 `final_plan`，但 `ResearchExecutor.execute()` 构建 `user_input_dict` 时未从中提取。这是完整数据流的关键断裂点。

```python
# 当前代码（L335-340）
user_input_dict = {
    "session_id": session_id,
    "topic": topic or user_input,
    "output_type": output_type,
    "aspects": framework.get("sections", None),
    # ← 缺少 sections_tree 和 section_details
}

# 改造后
user_input_dict = {
    "session_id": session_id,
    "topic": topic or user_input,
    "output_type": output_type,
    "aspects": framework.get("sections", None),
    "sections_tree": plan.get("sections_tree"),           # 新增
    "section_details": plan.get("section_details", []),    # 新增
}
```

**如果不改此处，`_parse_requirement()` 永远看不到 `sections_tree`/`section_details`，整个多级框架功能失效。**

### 4.8 `_handle_framework_mode()` 改造

**文件**：`src/api/research_api.py` L1224-1263

当前用户修改框架时，`_llm_framework_modify()` 返回 `new_sections`（扁平列表），新 framework 丢失 `sections_tree`：

```python
# 当前代码（L1246 附近）
new_framework = {
    'topic': topic,
    'sections': new_sections,     # ← 扁平
    'output_type': framework.get('output_type', 'industry_report'),
    'depth': framework.get('depth', 'standard'),
    ...
    # ← sections_tree 丢失
}
```

改造方案：
1. `_llm_framework_modify()` prompt 增加 `new_framework_tree` 输出字段：当原 framework 包含 `sections_tree` 时，prompt 中展示当前多级结构，并要求 LLM 在修改时也输出 `new_framework_tree`
2. 如果 LLM 返回了 `new_framework_tree`，使用新树结构
3. 如果 LLM 只返回了 `new_sections`（无 `new_framework_tree`），保留原 `framework.get('sections_tree')` 但尝试匹配更新
4. 最简方案：修改后的 framework 保留原 `sections_tree`，如果 `new_sections` 与 `sections_tree` 的扁平列表长度或内容不匹配，则清除 `sections_tree`（降级为扁平模式）

### 4.9 Fallback 路径覆盖

`_enter_framework_mode()` 有 3 条 fallback 路径，当前均只返回扁平结构：

- **`_generate_research_framework()`**（L1466-1486，L1299 调用）：从 `context['directions']` 去重生成 `sections`
- **`_build_framework_with_fallback()`**（L1488-1506，L1301 调用）：三级 fallback 链
  - `_infer_framework_sections_from_conversation()`（L1508-1566）：LLM 推断框架
  - `_get_template_sections_for_topic()`（L1568-1601）：模板章节
  - `_generate_default_sections_for_topic()`（L1603-1625）：关键词默认章节

**P0 范围**：这些 fallback 路径暂不改造。仅当用户在对话中提供了多级框架（`framework_tree` 非空）时才启用多级展示；fallback 路径仍然返回扁平结构，前端降级为现有展示。

**P3 范围**：改造 `_infer_framework_sections_from_conversation()` 使其也能返回 `sections_tree`。

### 4.10 B1 修复：Agent prompt 注入二级结构

**改动位置**：

1. **`src/core/decomposition/strategies.py` L460-463**：DATA_COLLECTION agent 的 `context` 增加 `"sub_aspects"` 字段
   - 当前 context 包含 `aspect`、`topic`、`section_id`、`data_needs`、`search_data_needs`
   - 修复后增加 `"sub_aspects"`：取 `matched_spec.sub_sections` 中每个 `SubSectionSpec.name` 组成列表，如果 `matched_spec` 不存在则为空列表

2. **`src/core/decomposition/strategies.py` L510**：DEEP_ANALYSIS agent 的 `context` 同样增加 `"sub_aspects"`

3. **`src/core/decomposition/strategies.py` L588-627 `_build_data_collection_prompt()`**：增加 `sub_aspects` 参数，在 prompt 中注入二级子主题列表
   - 如果 `sub_aspects` 非空，在 prompt 末尾追加"请按以下子主题分别搜索数据"指令，并列出子主题

4. **`src/core/decomposition/strategies.py` L651-681 `_build_analysis_prompt()`**：增加 `sub_aspects` 参数，在 prompt 中注入二级子主题列表
   - 如果 `sub_aspects` 非空，在 prompt 末尾追加"请按以下子主题分别分析，每个子主题使用 ### 标题"指令，并列出子主题

5. **`src/core/agents/generic_agent.py` L3378-3463 `_build_analysis_prompt_with_data()`**：增加 `sub_aspects` 参数，在 `framework_context` 中注入二级子主题

6. **`src/core/agents/generic_agent.py` L474 和 L547 `_build_analysis_prompt_with_data()` 调用点**：两处调用均增加 `sub_aspects=self._context.get("sub_aspects")` 参数，从 agent context 中提取 `sub_aspects` 并传递给 prompt 构建方法

### 4.11 B2 修复：`deep_analysis.md` 增加结构约束

**改动位置**：`prompts/tasks/deep_analysis.md` L47-54

当前 `Output Structure` 要求固定 5 段结构。需要增加条件性规则：

- 如果 prompt 中包含二级子主题列表（由 B1 修复注入），要求 LLM 必须按该列表的顺序和标题输出分析，每个二级子主题使用 `### 标题` 格式
- 每个二级子主题下的内容仍然遵循 5 段结构（Core Judgment / Logical Derivation / Data Support / Counter Evidence / Implication）
- 如果 prompt 中没有二级子主题列表，保持现有 5 段结构不变

### 4.12 B4 修复：`section_details` 包含二级信息

**改动位置**：`src/core/orchestrator/orchestrator.py` L3221-3224

当前 `_parse_requirement()` 在自定义 aspects 路径下，`section_details` 只包含 `{id, name, content}`。需要扩展：

- 当 `user_input` 包含 `section_details`（由 §4.7 从 `_start_execution()` 传入）时，直接使用传入的 `section_details`
- 当 `user_input` 不含 `section_details` 但包含 `sections_tree` 时，从 `sections_tree` 构建带二级信息的 `section_details`
- 每个 section 的 `sub_sections` 字段包含 `[{name, points}]`
- 当 `sections_tree` 和 `section_details` 均不存在时，保持现有逻辑不变

```python
# L3221-3224 当前代码
section_details = [
    {"id": a.lower().replace(" ", "_"), "name": a, "content": a}
    for a in aspects
]

# 改造后
if user_input.get("section_details"):
    section_details = user_input["section_details"]
elif user_input.get("sections_tree"):
    section_details = self._build_section_details_from_tree(user_input["sections_tree"])
else:
    section_details = [
        {"id": a.lower().replace(" ", "_"), "name": a, "content": a}
        for a in aspects
    ]
```

### 4.13 B3 修复：`result_aggregator` 用框架骨架替代自动解析

**改动位置**：`src/core/orchestrator/aggregation/result_aggregator.py` L461-463

当前 `_parse_markdown_subsections(content)` 从 LLM Markdown 输出中自动解析子章节。需要增加框架骨架匹配逻辑：

1. 在 `_convert_to_sections()` 的 section 构建循环中（L258 开始），检查 `section_detail` 是否包含 `sub_sections` 字段
2. 如果有，遍历 `section_detail["sub_sections"]`，对每个 sub_section：
   - 在 LLM 输出的 Markdown 中查找匹配的 `###` 标题（使用归一化匹配）
   - 提取该标题下的内容段落
   - 构建子章节对象，`title` 使用框架的 `sub_section.name`，`content` 使用匹配到的内容段落
3. 如果 LLM 输出中找不到匹配的标题，生成降级占位内容
4. 如果 `section_detail` 没有 `sub_sections` 字段，保持 `_parse_markdown_subsections()` 自动解析

### 4.14 `framework_tree` → `section_data_specs` P0 对齐

**改动位置**：`src/core/decomposition/strategies.py` L425-427

在 `decompose()` 中，`section_data_specs` 从 `intent_result` 获取后，如果 `framework_tree` 存在（通过 `requirement.dynamic_fields` 或 `section_details` 传入），用 `framework_tree` 的二级结构覆盖 `section_data_specs` 中对应 section 的 `sub_sections`：

```python
section_data_specs = getattr(intent_result, 'section_data_specs', []) or []
if section_data_specs and isinstance(section_data_specs[0], dict):
    section_data_specs = _convert_specs_from_dicts(section_data_specs)

# P0 对齐：用 framework_tree 覆盖 section_data_specs 的二级结构
sections_tree = None
if hasattr(requirement, 'dynamic_fields') and requirement.dynamic_fields.get('sections_tree'):
    sections_tree = requirement.dynamic_fields['sections_tree']
elif hasattr(requirement, 'section_details') and requirement.section_details:
    for sd in requirement.section_details:
        if sd.get('sub_sections'):
            sections_tree = requirement.section_details
            break

if sections_tree:
    for tree_section in sections_tree:
        tree_name = tree_section.get('name', '')
        for spec in section_data_specs:
            if spec.name == tree_name:
                tree_subs = tree_section.get('sub_sections', [])
                for j, tree_sub in enumerate(tree_subs):
                    if j < len(spec.sub_sections):
                        spec.sub_sections[j].name = tree_sub.get('name', spec.sub_sections[j].name)
                        tree_points = tree_sub.get('points', [])
                        if tree_points:
                            spec.sub_sections[j].data_needs = tree_points
                    else:
                        from src.core.decomposition.strategies import SubSectionSpec
                        spec.sub_sections.append(SubSectionSpec(
                            sub_section_id=f"sub_{spec.section_id}_{j}",
                            name=tree_sub.get('name', ''),
                            data_needs=tree_sub.get('points', []),
                            data_source_type="search"
                        ))
                break
```

---

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| LLM 不稳定输出 `framework_tree` | 向后兼容 `framework_sections`，两者同时支持 |
| `framework_tree` JSON 格式错误 | 复用现有 `_retry_json_only`（`research_api.py:1019-1038`）重试机制，解析失败时降级使用 `framework_sections` |
| 前端未升级时收到 `sections_tree` | 前端忽略未知字段，降级为扁平展示 |
| `framework_tree` 与 `section_data_specs` 不一致 | P0 最小对齐（§4.14），P3 完全统一 |
| `framework_tree` 与 `framework_sections` 名称不一致 | 从 `framework_tree` 派生的扁平列表覆盖 `framework_sections`，不使用 LLM 提供的 `framework_sections` |
| 3 个消费入口遗漏提取 `framework_tree` | 在 §4.3 中明确列出 3 个改动位置，逐个确认 |
| X1: `_start_execution()` 丢失树结构 | §4.7 扩展 `final_plan` 增加 `sections_tree` 和 `section_details`；§4.7a 修复 `research_executor.py` 传递 |
| X2: 前端确认不发结构化数据 | P2 阶段新增结构化确认 API |
| X3: `_build_response()` 不透传 `framework_tree` | §4.2 增加 `framework_tree` 透传 |
| 用户修改框架后 `sections_tree` 丢失 | §4.8 改造 `_handle_framework_mode()`；`_llm_framework_modify()` 增加 `new_framework_tree` |
| `_retry_json_only()` 重试场景 | 扩展 `_JSON_OUTPUT_SCHEMA` 后验证重试提示包含 `framework_tree` 定义 |
| `research_executor.py` 不传递 `sections_tree` | §4.7a 修复：`user_input_dict` 增加 `sections_tree` 和 `section_details` |
| `generic_agent.py` 不传递 `sub_aspects` | L474 和 L547 调用点增加 `sub_aspects=self._context.get("sub_aspects")` |
| `_build_data_collection_prompt()` 不注入 sub_aspects | 增加 `sub_aspects` 参数，在 prompt 末尾追加子主题列表；调用点传入 `sub_aspects` |
| `_build_analysis_prompt()` 不注入 sub_aspects | 增加 `sub_aspects` 参数，在 prompt 末尾追加子主题列表；调用点传入 `sub_aspects` |
| LLM 无 framework_tree 输出引导 | `context_summary` NOTE 增加 framework_tree 输出指引；`FRAMEWORK_CONFIRM` 状态指引增加 framework_tree 提示 |
| `_JSON_OUTPUT_SCHEMA` 缺少 framework_tree 优先规则 | schema 末尾增加 RULE：当 action="enter_framework" 且主题有多级结构时，优先使用 framework_tree |

---

## 6. 测试要点

### 6.1 基础功能

1. **LLM 输出 `framework_tree`**：验证 3 个消费入口（L397/L450/L622）均正确提取并存入 `context['_framework_tree']`
2. **LLM 输出 `framework_sections`**：验证向后兼容，`_framework_tree` 为空时不影响现有逻辑
3. **LLM 同时输出两者**：验证 `framework_tree` 派生的扁平列表覆盖 `framework_sections`
4. **LLM 输出无效 `framework_tree`**（非 list / 字段缺失 / `name` 为空）：验证降级到 `framework_sections`
5. **`_format_framework()` 多级格式化**：验证 `sections_tree` 存在时输出 `1. → 1.1 → 1.1.1` 格式
6. **`_format_framework()` fallback**：验证 `sections_tree` 不存在时仍使用 `section_details` 附加描述
7. **Fallback 路径**：验证 `_generate_research_framework()` / `_build_framework_with_fallback()` 返回的 framework 不含 `sections_tree`，前端降级为扁平展示
8. **X3 验证**：`_build_response()` 正确透传 `framework_tree` 到 `conv_result`
9. **X1 验证**：`_start_execution()` 构建的 `final_plan` 包含 `sections_tree` 和 `section_details`
10. **`_build_section_details_from_tree()` 验证**：从 `sections_tree` 构建的 `section_details` 包含正确的 `sub_sections` 字段

### 6.2 框架-输出一致性验证（核心）

11. **B1 验证**：DEEP_ANALYSIS agent 的 prompt 中包含二级子主题列表时，LLM 输出的 Markdown 标题与框架二级标题一致
12. **B2 验证**：`deep_analysis.md` prompt 注入二级结构约束后，LLM 输出按 `### 二级标题` 格式组织
13. **B4 验证**：`_parse_requirement()` 返回的 `section_details` 包含 `sub_sections` 字段，且 `sub_sections[i].name` 与 `framework_tree[i].sub_sections[j].name` 一致
14. **B3 验证**：`result_aggregator` 使用框架骨架匹配时，报告的 subsections 标题与框架二级标题一致
15. **B5 验证**：报告渲染中三级要点可见（HTML `<h4>` / Docx `level=3` / TOC 三级目录）
16. **P0 对齐验证**：`section_data_specs` 的 `sub_sections.name` 与 `framework_tree` 的 `sub_sections.name` 一致

### 6.3 端到端一致性

17. **三级框架→三级输出**：用户输入三级框架 → 确认 → 执行 → 报告中每个一级章节包含二级子章节，每个二级子章节包含三级要点对应的内容段落
18. **二级框架→二级输出**：用户输入二级框架（无 points）→ 报告中每个一级章节包含二级子章节，无三级段落
19. **一级框架→一级输出**：用户输入一级框架（无 sub_sections）→ 报告中每个一级章节无 subsections，与现有行为一致

### 6.4 修改路径与恢复

20. **框架修改路径**：用户在框架确认阶段修改框架后，`sections_tree` 不丢失（或正确降级为扁平模式）
21. **前端 session 恢复**：`useResearchStore` 缓存的 `framework` 包含 `sections_tree` 时，恢复后类型兼容
22. **`_retry_json_only()` 重试**：扩展 `_JSON_OUTPUT_SCHEMA` 后，JSON 重试机制正确引导 LLM 输出含 `framework_tree` 的 JSON
23. **Docx 回退路径**：`_fallback_generate_document()`（L1506-1517）也能正确渲染 subsections
24. **数据流完整性**：`research_executor.py` 的 `user_input_dict` 包含 `sections_tree` 和 `section_details`，确保 `_parse_requirement()` 可以获取多级信息
25. **`generic_agent.py` 调用点**：两处 `_build_analysis_prompt_with_data()` 调用均传递 `sub_aspects=self._context.get("sub_aspects")`
26. **`_llm_framework_modify` 输出**：prompt 包含 `new_framework_tree` 输出字段，LLM 修改框架时也能返回多级结构
27. **`_build_data_collection_prompt()` sub_aspects 注入**：方法签名包含 `sub_aspects` 参数，且调用点传入子主题列表，prompt 文本中包含子主题列表
28. **`_build_analysis_prompt()` sub_aspects 注入**：方法签名包含 `sub_aspects` 参数，且调用点传入子主题列表，prompt 文本中包含子主题列表
29. **LLM 输出 `framework_tree` 引导**：`_build_initial_prompt()` 的 context_summary NOTE 和 `FRAMEWORK_CONFIRM` 状态指引均包含 `framework_tree` 输出指导
30. **`_JSON_OUTPUT_SCHEMA` 优先规则**：schema 包含 `RULE` 说明，当 `action="enter_framework"` 且主题有天然多级结构时，优先使用 `framework_tree`
