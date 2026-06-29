# 报告生成Agent深度升级方案：框架驱动·逐章生成·全局审查

> 日期：2026-06-26
> 状态：设计方案
> 关联问题：报告质量失控——机械组装数据，缺乏研究框架驱动的逻辑连贯性

---

## 1. 问题诊断：当前报告生成流程的致命缺陷

### 1.1 当前流程（"机械组装"模式）

```
用户需求 → 拆章节 → 各Agent并行执行（数据采集+分析）→ 结果聚合 → 一次性拼装HTML → 质量检查 → 输出
```

**核心问题**：报告生成阶段（`ReportGenerationAgent` + `DocumentGenerationAgent`）只是一个"排版工"，它：

1. **不读数据**：`ReportGenerationAgent.execute()` 接收 `sections` 列表后，直接调用 `_integrate_body()` 将各章节内容原样拼接，不做任何内容层面的理解或改写
2. **不遵循框架**：虽然系统已有 `ResearchFramework`（`docs/RESEARCH_FRAMEWORK_DRIVEN_DESIGN.md`），但框架信息在报告生成阶段完全丢失——`ReportGenerationAgent` 的输入只有 `title` + `sections`，没有框架上下文
3. **不做交叉验证**：各章节由独立Agent并行生成，数据矛盾（如市场规模在不同章节出现不同数值）在聚合阶段仅做简单去重（`_dedup_sections`），不做语义层面的冲突检测和统一
4. **不做全局审查**：`QualityCheckAgent` 只做格式层面的检查（标题重复、段落为空等），不做内容层面的审查（逻辑连贯性、数据一致性、叙事完整性）
5. **一次性输出**：整个报告是一次性生成的，没有"写一章→审查→修正→写下一章"的迭代机制

### 1.2 缺陷的代码证据

| 缺陷 | 代码位置 | 具体表现 |
|------|----------|----------|
| 不读数据 | `report_generation_agent.py:505-533` | `_integrate_body()` 只是遍历 sections 拼接 Markdown，不调用 LLM |
| 不遵循框架 | `report_generation_agent.py:245-353` | `execute()` 输入无 framework 参数，模板只有 `template_type` |
| 不做交叉验证 | `result_aggregator.py` | 聚合只做 key 匹配和去重，无跨章节数据一致性检查 |
| 不做全局审查 | `quality_check_agent.py` | 检查项为格式层面（空标题、重复段落），无内容审查 |
| 一次性输出 | `orchestrator.py:972-980` | `DocumentGenerationAgent.execute()` 一次性生成完整 HTML |

### 1.3 后果

- **数据矛盾**：同一指标在不同章节出现不同数值（如"市场规模"在概述章写2000亿，在细分章写1800亿）
- **内容重复**：多个章节重复叙述相同背景信息
- **逻辑断裂**：章节之间缺乏逻辑递进，读起来像多篇独立文章的拼凑
- **摘要失真**：执行摘要只是从各章抽取前两句，而非基于全局视角的综合提炼
- **质量不可控**：质量检查只能发现格式问题，无法发现内容问题

---

## 2. 新方案：框架驱动·逐章生成·全局审查

### 2.1 核心理念

```
旧模式：数据 → 机械组装 → 报告（排版工）
新模式：框架 → 逐章撰写（作者）→ 逐章审查（审稿人）→ 重写闭环 → 全局审查（主编）→ 报告
```

将报告生成升级为**三角色协作**模式：

- **作者角色（ChapterWriter）**：逐章撰写，每章都基于研究框架和前文上下文，确保逻辑连贯
- **审稿人角色（ChapterReviewAgent）**：独立审查每章质量，向作者反馈问题——**自审发现不了的问题，审查来发现**
- **主编角色（GlobalReviewAgent）**：全局审查，统一数据、消除矛盾、优化叙事、提升质量

### 2.2 新流程

```
Phase 1: 框架理解
  └─ 读取 ResearchFramework，建立全局叙事线
  └─ 提取核心问题、逻辑链、各章节角色定义

Phase 2: 逐章撰写 + 自审 + 独立审查（闭环迭代）
  ├─ Chapter 1:
  │   ├─ ChapterWriter 撰写 + 实时自审（内循环，捕捉格式/遗漏等表面问题）
  │   ├─ ChapterReviewAgent 独立审查（外循环，发现逻辑/视角等深层问题）
  │   ├─ 审查通过 → 进入下一章
  │   └─ 审查不通过 → Reviewer 反馈问题 → ChapterWriter 重写 → Reviewer 再审（最多2轮）
  ├─ Chapter 2: 同样流程（自审+独立审查闭环）
  └─ ...（自审挡住低级错误，审查挡住深层问题）

Phase 3: 全局审查（主编角色）
  ├─ 数据一致性审查：同一指标跨章节必须一致
  ├─ 内容去重审查：消除跨章节重复叙述
  ├─ 逻辑连贯性审查：章节间逻辑递进是否清晰
  ├─ 叙事完整性审查：核心问题是否被完整回答
  └─ 风格统一性审查：术语、语气、格式是否一致

Phase 4: 修正与优化
  └─ 数据缺失：DataRepairAgent 定向补充搜索 → 补入报告
  └─ 数据冲突：ConflictResolver 裁决规范值 → 全局替换
  └─ 逻辑/叙事问题：ChapterWriter 定向重写
  └─ 重新生成执行摘要（基于完整报告内容）
  └─ 最终质量评分
```

**自审与审查的互补关系**

自审和独立审查不冲突，而是互补的两道防线——好比学生写完作业先自己检查一遍，然后交给老师批改：

1. **自审（实时、轻量）**：ChapterWriter 生成内容后立即自检，捕捉显而易见的问题（数据遗漏、格式错误、明显矛盾），当场修正。自审是**内循环**，发生在生成过程中，零额外延迟。
2. **独立审查（事后、深度）**：章节全部完成后，由 ChapterReviewAgent 进行独立审查，发现自审看不到的深层问题（逻辑缺陷、视角盲区、标准松懈）。审查是**外循环**，发生在章节完成后。
3. **自审发现不了的问题，审查发现后反馈给 Writer 重写**——这是闭环的关键。

因此：
- ChapterWriter 输出包含 `self_check_passed` 和 `self_check_issues`（自审结果，轻量）
- ChapterReviewAgent 的审查维度更深更严，会覆盖自审无法触及的逻辑层面
- 自审不通过 → 当场重生成；审查不通过 → 反馈重写

### 2.3 与现有系统的关系

本方案**不替换**现有的数据采集和分析流程，只**升级**报告生成阶段：

```
现有流程（保持不变）：
  用户需求 → 智能路由 → Agent创建 → 数据采集 → 深度分析 → 结果聚合

升级点（替换）：
  旧：结果聚合 → 机械拼装 → 格式检查 → 输出
  新：结果聚合 → 框架理解 → 逐章撰写(含自审)+独立审查闭环 → 全局审查 → 修正优化 → 输出
```

---

## 3. 详细设计

### 3.1 新增组件：ChapterWriter（章节撰写器）

**职责**：基于研究框架和前文上下文，使用 LLM 撰写单个章节

> **审计修正 A2（致命）**：LLM 输出是原始字符串，必须解析为结构化的 `ChapterWriteOutput` 对象。所有 LLM 调用后都必须有解析步骤，`{output_schema}` 占位符必须替换为明确的 JSON 输出格式定义。
>
> ```python
> class ChapterWriter:
>     async def write(self, input_data: ChapterWriteInput) -> ChapterWriteOutput:
>         prompt = self._build_write_prompt(input_data)
>         raw_output = await self._llm.generate(prompt)
>         return self._parse_chapter_output(raw_output, input_data.chapter_spec)
>     
>     def _parse_chapter_output(self, raw: str, spec: FrameworkDimension) -> ChapterWriteOutput:
>         """将LLM原始输出解析为结构化对象"""
>         try:
>             json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
>             if json_match:
>                 data = json.loads(json_match.group(1))
>                 return ChapterWriteOutput(
>                     chapter_id=spec.section_id,
>                     title=data.get("title", spec.section_name),
>                     content=data.get("content", ""),
>                     data_points_used=[DataPoint(**dp) for dp in data.get("data_points_used", [])],
>                     key_conclusions=data.get("key_conclusions", []),
>                     self_check_passed=data.get("self_check_passed", True),
>                     self_check_issues=data.get("self_check_issues", []),
>                 )
>         except (json.JSONDecodeError, KeyError) as e:
>             logger.warning(f"Failed to parse structured output: {e}")
>         
>         # Fallback：整个输出作为content
>         return ChapterWriteOutput(
>             chapter_id=spec.section_id,
>             title=spec.section_name,
>             content=raw,
>             data_points_used=[],
>             key_conclusions=self._extract_conclusions(raw),
>             self_check_passed=True,
>             self_check_issues=[],
>         )
> ```

**输入**：
```python
@dataclass
class ChapterWriteInput:
    framework: ResearchFramework          # 研究框架
    chapter_spec: FrameworkDimension      # 当前章节的框架定义
    chapter_data: Dict[str, Any]          # 该章节的采集数据和分析结果
    preceding_summary: str                # 前文摘要（前序章节的核心结论）
    used_metrics_summary: str             # 已使用的数据指标摘要（从DataRegistry序列化生成，供LLM读取）
    section_agent_map: Dict[str, str]     # section_id → agent_id 确定性映射（审计修正 #7）
```

> **审计修正 #7（严重）**：`_extract_chapter_data(aggregated_result, dimension.section_id)` 的映射实现未定义，当前 ResultAggregator 的模糊匹配错误率约15-20%。修正：在 Agent 创建阶段就建立 section_id → agent_id 的确定性映射，沿数据流传递到 ReportOrchestrator。

> **审计修正 #1（致命）**：原设计将 `DataRegistry` Python对象直接传入Agent输入，但LLM无法调用Python方法，导致数据注册表的核心功能失效。修正为 `used_metrics_summary: str`，由 ReportOrchestrator 在调用 Writer 之前从 DataRegistry 序列化生成：
>
> ```python
> def _serialize_used_metrics(self, data_registry: DataRegistry) -> str:
>     """将 DataRegistry 中已使用的数据点序列化为 Prompt 文本"""
>     if not data_registry._metrics:
>         return "暂无已使用的数据指标。"
>     lines = []
>     for key, entry in data_registry._metrics.items():
>         conflict_mark = " ⚠️存在冲突" if entry.conflicts else ""
>         lines.append(f"- {entry.metric}: {entry.value} {entry.unit}（来源: {entry.source}）{conflict_mark}")
>     return "\n".join(lines)
> ```

**输出**：
```python
@dataclass
class ChapterWriteOutput:
    chapter_id: str
    title: str
    content: str                          # LLM生成的章节内容
    data_points_used: List[DataPoint]     # 本章使用的数据点（注册到全局注册表）
    key_conclusions: List[str]            # 本章核心结论（传递给后续章节）
    self_check_passed: bool               # 自审是否通过（轻量级：格式、数据遗漏、明显矛盾）
    self_check_issues: List[str]          # 自审发现的问题（已当场修正的不再列出，只列出未能修正的）
```

> **审计修正 #4（严重）**：`data_points_used` 由 LLM 自报，存在遗漏、幻觉、数值错误三种风险。增加后置提取验证环节——从生成的 Markdown 内容中用正则提取数据点，与 LLM 自报数据交叉验证：
>
> ```python
> async def _extract_and_validate_data_points(self, chapter: ChapterWriteOutput) -> List[DataPoint]:
>     """从章节内容中提取数据点，与 LLM 自报数据交叉验证"""
>     
>     # 方法1：正则提取（快速，但不理解语义）
>     regex_extracted = self._extract_data_points_by_regex(chapter.content)
>     
>     # 方法2：LLM 自报（理解语义，但不可靠）
>     reported = chapter.data_points_used
>     
>     # 交叉验证：取两者并集，以正文中实际出现的值为准
>     validated = []
>     reported_metrics = {dp.metric.lower(): dp for dp in reported}
>     
>     for dp in regex_extracted:
>         key = dp.metric.lower()
>         if key in reported_metrics:
>             reported_dp = reported_metrics[key]
>             if dp.value != reported_dp.value:
>                 logger.warning(f"Data point value mismatch for '{dp.metric}': "
>                              f"content says {dp.value}, reported says {reported_dp.value}")
>             validated.append(DataPoint(
>                 metric=dp.metric,
>                 value=dp.value,        # 以正文中实际出现的值为准
>                 unit=dp.unit,
>                 source=reported_dp.source or dp.source,
>             ))
>         else:
>             validated.append(dp)  # 正则找到但自报没提 → 遗漏
>     
>     # 自报了但正则没找到的 → 可能是幻觉，记录警告但不注册
>     for dp in reported:
>         if dp.metric.lower() not in {d.metric.lower() for d in validated}:
>             logger.warning(f"Reported data point '{dp.metric}' not found in content, possible hallucination")
>     
>     return validated
> ```
>
> ReportOrchestrator 在注册数据点时使用验证后的结果：
> ```python
> # 注册本章使用的数据点（使用验证后的数据，而非LLM自报）
> validated_dps = await self._extract_and_validate_data_points(chapter)
> for dp in validated_dps:
>     self._data_registry.register(
>         metric=dp.metric, value=dp.value, unit=dp.unit,
>         chapter_id=chapter.chapter_id, source=dp.source
>     )
> ```

**自审说明**：
- `self_check_passed` / `self_check_issues` 是 Writer 的实时自检结果，属于**内循环**
- 自审关注的是显而易见的问题：格式规范、数据是否遗漏、与已使用的数据指标摘要中的已有值是否明显矛盾
- 自审不通过时 Writer 当场重生成，不额外增加 LLM 调用（自检+重生成合并为一次调用）
- 自审通过后，仍需由独立的 ChapterReviewAgent 进行深度审查（外循环）

**核心Prompt设计**：

```markdown
# 章节撰写任务

## 研究框架
核心问题：{core_question}
核心叙事线：{core_narrative}
逻辑链：{logic_chain}

## 你的章节角色
章节名：{chapter_name}
在报告中的角色：{role_in_report}
需要回答的子问题：{sub_questions}

## 前文脉络
{preceding_summary}

## 已使用的数据指标（避免重复引用，如有冲突请标注）
{used_metrics_summary}

## 可用数据
{chapter_data}

## 撰写要求
1. 基于研究框架和前文脉络，撰写本章内容
2. 与前文逻辑衔接，避免重复前文已述内容
3. 使用尚未使用的数据点，避免数据重复引用（参考"已使用的数据指标"部分）
4. 每个核心判断必须有数据支撑，标注数据来源
5. 如发现与前文数据矛盾，明确标注并给出你的判断
6. 内容长度：{min_length}字以上

## 自审检查（生成后立即执行）
完成撰写后，请自行检查以下项：
- [ ] 格式是否规范（标题层级、列表格式、表格格式）
- [ ] 是否遗漏了关键数据点
- [ ] 数据数值是否与"已使用的数据指标"中的已有值矛盾
- [ ] 是否有大段与前文重复的内容
如发现问题，请直接修正后输出最终版本，并在 self_check_issues 中列出未能修正的问题。

## 输出格式（严格JSON，包裹在 ```json ``` 中）
```json
{
  "title": "章节标题",
  "content": "Markdown格式的章节正文",
  "data_points_used": [
    {"metric": "指标名", "value": "数值", "unit": "单位", "source": "来源"}
  ],
  "key_conclusions": ["结论1", "结论2"],
  "self_check_passed": true,
  "self_check_issues": []
}
```（章节审查Agent）

**职责**：独立审查单章质量，向 ChapterWriter 反馈问题。**与 ChapterWriter 完全独立，负责自审无法覆盖的深层问题。**

**自审 vs 独立审查的分工**

| | 自审（Writer内循环） | 独立审查（ReviewAgent外循环） |
|---|---|---|
| **时机** | 生成时实时检查 | 章节完成后事后审查 |
| **范围** | 格式、数据遗漏、明显矛盾 | 逻辑深度、视角盲区、标准松懈 |
| **能发现** | "这个数据我忘了引用" | "这段论证逻辑跳跃，缺乏过渡" |
| **不能发现** | 自己的确认偏误、标准松懈 | — |
| **处理** | 当场修正，零额外延迟 | 反馈给 Writer 重写，需要额外调用 |

**为什么独立审查不可被自审替代？**

同一个Agent既写内容又做质量评估，存在根本性的利益冲突：
1. **认知盲区**：作者对自己写的内容有"确认偏误"，自审能看到"格式不对"，但看不到"这段论证本身就有问题"
2. **标准松懈**：自评时深层标准会不自觉地降低——"逻辑差不多通顺就行了"
3. **缺乏外部视角**：审查需要站在读者角度提问，自审很难跳出作者视角
4. **重写不彻底**：自审发现的问题往往是表面问题，深层的逻辑缺陷会被遗漏

因此，ChapterReviewAgent 是**独立Agent**：
- 使用与 ChapterWriter 不同的 LLM 调用（不同 system prompt，不同 temperature）
- 审查时**不看到** ChapterWriter 的生成过程，只看到最终输出
- 审查反馈是结构化的，包含具体问题定位和修正方向

**输入**：
```python
@dataclass
class ChapterReviewInput:
    framework: ResearchFramework          # 研究框架
    chapter_spec: FrameworkDimension      # 当前章节的框架定义
    chapter_content: str                  # 待审查的章节内容
    preceding_summary: str                # 前文摘要（用于检查逻辑衔接）
    used_metrics_summary: str             # 已使用的数据指标摘要（从DataRegistry序列化，供LLM检查数据一致性）
    writer_self_check_issues: List[str]    # Writer自审发现但未能修正的问题（审查线索）
```

> **审计修正 #1（致命）**：同 ChapterWriteInput，将 `data_registry: DataRegistry` 替换为 `used_metrics_summary: str`。

**输出**：
```python
@dataclass
class ChapterReviewOutput:
    passed: bool                          # 是否通过审查
    score: float                          # 质量评分 (0-100)
    issues: List[ChapterIssue]            # 发现的问题（结构化，传递给 Writer 重写）
    
@dataclass
class ChapterIssue:
    category: str                         # data_support / logic / completeness / redundancy / style
    severity: str                         # CRITICAL / HIGH / MEDIUM / LOW
    location: str                         # 问题在章节中的位置描述
    description: str                      # 问题描述
    suggestion: str                       # 修正建议（指导 Writer 如何改）
```

**核心Prompt设计**：

```markdown
# 章节审查任务

你是一位严格的审稿人，你的职责是找出章节中的一切问题。你必须比作者更苛刻。

## 研究框架
核心问题：{core_question}
本章角色：{role_in_report}
本章需回答的子问题：{sub_questions}

## 前文脉络
{preceding_summary}

## 已使用的数据指标（用于检查数据一致性）
{used_metrics_summary}

## 待审查章节内容
{chapter_content}

## 作者自审遗留问题（需重点关注）
{writer_self_check_issues}

## 审查维度与标准

### 1. 数据支撑度（权重30%）
- 每个核心判断是否有数据支撑？
- 数据是否标注了来源？
- 数据是否与前文引用的数据一致？（参考已使用的数据指标摘要）
- 是否存在无数据支撑的断言？

### 2. 逻辑清晰度（权重25%）
- 论点之间是否有逻辑递进？
- 是否存在逻辑跳跃或循环论证？
- 结论是否从论据自然推导而来？
- 是否与前文逻辑衔接？

### 3. 内容完整度（权重20%）
- 框架定义的子问题是否都被回答？
- 是否遗漏了关键论点？
- 分析是否足够深入，还是停留在表面？

### 4. 内容冗余度（权重15%）
- 是否与前文有大段重复？
- 同一观点是否在本章内反复陈述？

### 5. 风格规范性（权重10%）
- 术语使用是否一致？
- 格式是否符合报告规范？

## 输出要求
1. 给出总分（0-100），60分以下为不通过
2. 每个问题必须给出具体的修正建议（不能只说"逻辑不清"，要说"第3段到第4段缺少过渡，建议补充XXX"）
3. 问题按严重程度排序，CRITICAL问题必须全部修正才能通过

## 输出格式（严格JSON，包裹在 ```json ``` 中）
```json
{
  "passed": true,
  "score": 85,
  "issues": [
    {
      "category": "data_support",
      "severity": "HIGH",
      "location": "data:市场规模",
      "description": "市场规模断言无数据支撑",
      "suggestion": "在第3段补充市场规模数据及来源"
    }
  ]
}
```
```

### 3.3 新增组件：GlobalReviewAgent（全局审查Agent）

**职责**：对完整报告进行内容层面的全局审查。**与 ChapterWriter、ChapterReviewAgent 完全独立，是"主编"角色。**

**审查维度**：

| 维度 | 检查内容 | 严重级别 |
|------|----------|----------|
| 数据一致性 | 同一指标在不同章节的数值是否一致 | CRITICAL |
| 内容去重 | 跨章节是否有大段重复叙述 | HIGH |
| 逻辑连贯性 | 章节间逻辑递进是否清晰，过渡是否自然 | HIGH |
| 叙事完整性 | 核心问题是否被完整回答，逻辑链是否闭合 | HIGH |
| 术语统一性 | 同一概念是否使用统一术语 | MEDIUM |
| 风格一致性 | 语气、格式、详略程度是否一致 | MEDIUM |
| 数据引用完整性 | 引用的数据是否都有来源标注 | LOW |

**输入**：
```python
@dataclass
class ReviewInput:
    framework: ResearchFramework
    report_summary: str                   # 结构化报告摘要（非完整报告原文）
    conflicts_summary: str                # 数据冲突摘要（从DataRegistry序列化）
```

> **审计修正 #1（致命）**：移除 `data_registry: DataRegistry`，替换为 `conflicts_summary: str`（序列化文本）。
>
> **审计修正 #3（致命）**：将 `full_report: Dict[str, Any]` 替换为 `report_summary: str`（结构化摘要）。原设计将完整报告原文传入GlobalReviewAgent，10章报告约27K tokens，导致注意力稀释和成本爆炸。修正为两步审查：
>
> ```
> Step 1: 全局摘要审查（发现跨章节问题）
>   输入：结构化摘要（紧凑，每章仅标题+核心结论+关键数据）
>   输出：问题列表（定位到具体章节和指标）
>
> Step 2: 问题验证（对发现的问题，读原文确认）
>   输入：仅问题涉及章节的原文（局部）
>   输出：确认/否定 + 精确的问题描述和修正建议
> ```
>
> 结构化摘要的生成：
> ```python
> def _serialize_report_for_review(self, chapters, data_registry) -> str:
>     """将完整报告序列化为全局审查用的紧凑摘要"""
>     sections_summary = []
>     for i, ch in enumerate(chapters):
>         data_summary = []
>         for dp in ch.data_points_used:
>             data_summary.append(f"  {dp.metric}: {dp.value} {dp.unit}")
>         sections_summary.append(
>             f"### 第{i+1}章：{ch.title}\n"
>             f"核心结论：{'; '.join(ch.key_conclusions)}\n"
>             f"关键数据：\n" + ("\n".join(data_summary) if data_summary else "  无数据")
>         )
>
>     conflicts = data_registry.get_conflicts()
>     conflict_summary = ""
>     if conflicts:
>         conflict_summary = "\n## ⚠️ 已知数据冲突\n" + "\n".join(
>             f"- {c.metric}: " + ", ".join(f'{e.value}{e.unit}（来源:{e.source}）' for e in c.entries)
>             for c in conflicts
>         )
>
>     return "\n\n".join(sections_summary) + conflict_summary
> ```

**输出**：
```python
@dataclass
class ReviewOutput:
    overall_score: float                  # 总体质量分 (0-100)
    dimension_scores: Dict[str, float]    # 各维度评分
    issues: List[ReviewIssue]             # 发现的问题
    fix_suggestions: List[FixSuggestion]  # 修正建议

@dataclass
class ReviewIssue:
    dimension: str                        # 审查维度
    severity: str                         # CRITICAL/HIGH/MEDIUM/LOW
    description: str                      # 问题描述
    location: str                         # 问题位置（章节ID或跨章节）
    evidence: str                         # 证据（矛盾数据的具体内容）

@dataclass
class FixSuggestion:
    target_chapter: str                   # 需要修正的章节
    issue_id: str                         # 关联的问题ID
    fix_type: str                         # rewrite/patch/data_fix
    fix_instruction: str                  # 修正指令
    priority: str                         # CRITICAL/HIGH/MEDIUM/LOW
```

**核心Prompt设计**：

```markdown
# 全局审查任务

你是一位资深主编，你的职责是对整份报告进行全局审查。你比章节审稿人站位更高——他们关注单章质量，你关注跨章节的系统性问题。你必须比任何作者都更苛刻。

## 研究框架
核心问题：{core_question}
逻辑链：{logic_chain}

## 报告结构化摘要
{report_summary}

## 已知数据冲突
{conflicts_summary}

## 审查要求
请从以下维度审查报告，发现所有问题：

### 1. 数据一致性（CRITICAL）
- 检查同一指标在不同章节的数值是否一致
- 例如：市场规模在概述章和细分章的数值是否匹配
- 发现矛盾时，标注具体位置和矛盾数值

### 2. 内容去重（HIGH）
- 检查是否有大段内容在不同章节重复出现
- 标注重复段落的位置

### 3. 逻辑连贯性（HIGH）
- 章节间是否有逻辑递进
- 过渡是否自然
- 是否有逻辑跳跃或断裂

### 4. 叙事完整性（HIGH）
- 核心问题是否被完整回答
- 逻辑链是否闭合
- 是否有遗漏的关键论点

### 5. 术语和风格统一性（MEDIUM）
- 同一概念是否使用统一术语
- 语气和格式是否一致

## 输出格式（严格JSON，包裹在 ```json ``` 中）
```json
{
  "overall_score": 75,
  "dimension_scores": {"data_consistency": 60, "content_uniqueness": 90, "logic_coherence": 70, "narrative_completeness": 80, "style_uniformity": 85},
  "issues": [
    {
      "dimension": "data_consistency",
      "severity": "CRITICAL",
      "description": "市场规模在概述章为2000亿，细分章为1800亿",
      "location": "chapter_1, chapter_3",
      "evidence": "概述章'市场规模约2000亿元' vs 细分章'市场规模达1800亿元'"
    }
  ],
  "fix_suggestions": [
    {
      "target_chapter": "chapter_3",
      "issue_id": "issue_1",
      "fix_type": "patch",
      "fix_instruction": "将细分章市场规模统一为2000亿元",
      "priority": "CRITICAL"
    }
  ]
}
```
```

### 3.4 新增组件：DataRegistry（全局数据注册表）

**职责**：跟踪所有已使用的数据点，确保跨章节数据一致性

```python
class DataRegistry:
    """全局数据注册表"""
    
    def __init__(self):
        self._metrics: Dict[str, MetricEntry] = {}  # metric_name → entry
    
    def register(self, metric: str, value: str, unit: str, 
                 chapter_id: str, source: str) -> None:
        """注册一个数据点。如果同名指标已存在且值不同，标记为冲突"""
        key = self._normalize_metric(metric)
        if key in self._metrics:
            existing = self._metrics[key]
            if existing.value != value:
            existing.conflicts.append(ConflictEntry(
                chapter_id=chapter_id, value=value, unit=unit, source=source
            ))
            # 【审计修正 A6】ConflictEntry 必须包含 unit 字段，与 3.6.2 定义一致
        else:
            self._metrics[key] = MetricEntry(
                metric=metric, value=value, unit=unit,
                canonical_chapter=chapter_id, source=source,
                conflicts=[]
            )
    
    def get_canonical_value(self, metric: str) -> Optional[str]:
        """获取指标的规范值（首次注册的值，或冲突解决后的值）"""
        key = self._normalize_metric(metric)
        entry = self._metrics.get(key)
        return entry.value if entry else None
    
    def get_conflicts(self) -> List[DataConflict]:
        """获取所有数据冲突（按指标分组）【审计修正 A6】"""
        conflicts = []
        for entry in self._metrics.values():
            if entry.conflicts:
                # 将原始条目和冲突条目合并为 DataConflict
                all_entries = [ConflictEntry(
                    chapter_id=entry.canonical_chapter,
                    value=entry.value, unit=entry.unit, source=entry.source
                )] + entry.conflicts
                conflicts.append(DataConflict(
                    metric=entry.metric, entries=all_entries
                ))
        return conflicts
    
    def is_used(self, metric: str, value: str) -> bool:
        """检查某数据点是否已被使用"""
        key = self._normalize_metric(metric)
        entry = self._metrics.get(key)
        if not entry:
            return False
        return entry.value == value
```

### 3.5 升级组件：ReportOrchestrator（报告编排器）

> **审计修正 #9（中等）**：Phase 2-3 的中间结果无持久化，崩溃即丢失。增加检查点机制：
>
> ```python
> async def _checkpoint_chapter(self, task_id, chapter, data_registry):
>     """章节完成后保存检查点"""
>     from pathlib import Path
>     checkpoint_dir = Path("data") / task_id / "checkpoints"
>     checkpoint_dir.mkdir(parents=True, exist_ok=True)
>     
>     chapter_data = {
>         "chapter_id": chapter.chapter_id,
>         "title": chapter.title,
>         "content": chapter.content,
>         "data_points_used": [dp.__dict__ for dp in chapter.data_points_used],
>         "key_conclusions": chapter.key_conclusions,
>         "self_check_passed": chapter.self_check_passed,
>         "self_check_issues": chapter.self_check_issues,
>         "data_registry_snapshot": self._serialize_registry(data_registry),
>         "timestamp": datetime.now().isoformat(),
>     }
>     
>     checkpoint_path = checkpoint_dir / f"chapter_{chapter.chapter_id}.json"
>     checkpoint_path.write_text(
>         json.dumps(chapter_data, ensure_ascii=False, indent=2), encoding="utf-8"
>     )
> 
> async def _restore_from_checkpoint(self, task_id):
>     """从检查点恢复"""
>     from pathlib import Path
>     checkpoint_dir = Path("data") / task_id / "checkpoints"
>     if not checkpoint_dir.exists():
>         return None
>     
>     chapters = []
>     registry_snapshot = {}
>     for path in sorted(checkpoint_dir.glob("chapter_*.json")):
>         data = json.loads(path.read_text(encoding="utf-8"))
>         chapter = ChapterWriteOutput(
>             chapter_id=data["chapter_id"],
>             title=data["title"],
>             content=data["content"],
>             data_points_used=[DataPoint(**dp) for dp in data["data_points_used"]],
>             key_conclusions=data["key_conclusions"],
>             self_check_passed=data["self_check_passed"],
>             self_check_issues=data["self_check_issues"],
>         )
>         chapters.append(chapter)
>         registry_snapshot = data.get("data_registry_snapshot", {})
>     
>     return (chapters, registry_snapshot) if chapters else None
> ```

**职责**：编排整个报告生成流程（框架理解 → 逐章撰写+审查闭环 → 全局审查 → 修正优化）

> **审计修正 #7（严重）**：`_extract_chapter_data` 必须优先使用确定性映射，仅在映射缺失时 fallback 到模糊匹配：
>
> ```python
> def _extract_chapter_data(self, aggregated_result, section_id, section_agent_map=None):
>     """从聚合结果中提取章节数据（确定性映射优先）"""
>     # 优先：确定性映射
>     if section_agent_map:
>         agent_id = section_agent_map.get(section_id)
>         if agent_id and agent_id in aggregated_result:
>             return aggregated_result[agent_id]
>     
>     # Fallback: 模糊匹配（保留现有逻辑，但记录警告）
>     logger.warning(f"No deterministic mapping for section_id={section_id}, using fuzzy match")
>     return self._fuzzy_match_chapter_data(aggregated_result, section_id)
> ```

```python
class ReportOrchestrator:
    """报告编排器：框架驱动·逐章生成·独立审查·全局审查"""
    
    MAX_CHAPTER_REWRITE_ROUNDS = 2  # 每章最多重写2轮（写→审→改→审→改→审）
    
    def __init__(self, llm_skill, chapter_writer, chapter_reviewer, global_reviewer,
                 data_repair_agent, conflict_resolver):
        self._llm = llm_skill
        self._chapter_writer = chapter_writer       # 作者
        self._chapter_reviewer = chapter_reviewer   # 审稿人（独立Agent）
        self._global_reviewer = global_reviewer     # 主编（独立Agent）
        self._data_repair_agent = data_repair_agent # 数据修补Agent
        self._conflict_resolver = conflict_resolver # 冲突裁决器
        self._data_registry = DataRegistry()
    
    async def generate_report(
        self,
        framework: ResearchFramework,
        aggregated_result: Dict[str, Any],
        section_details: List[Dict],
        task_id: str = None,                # 【审计修正 #9】用于检查点持久化
        topic: str = "",                    # 【审计修正 A8】研究主题，用于数据修补搜索
    ) -> Dict[str, Any]:
        """
        生成报告（新流程）
        
        Args:
            framework: 研究框架
            aggregated_result: 聚合后的分析结果
            section_details: 章节详情
            
        Returns:
            完整报告数据
        """
        # Phase 1: 框架理解
        narrative_context = self._understand_framework(framework)
        
        # Phase 2: 逐章撰写 + 独立审查闭环
        # 【审计修正 #9】尝试从检查点恢复
        # 【审计修正 A3】恢复后必须跳过已完成章节
        chapters = []
        preceding_summary = ""
        completed_section_ids = set()
        
        if task_id:
            restored = await self._restore_from_checkpoint(task_id)
            if restored:
                chapters, registry_snapshot = restored
                self._data_registry = self._restore_registry(registry_snapshot)
                preceding_summary = self._rebuild_preceding_summary(chapters)
                completed_section_ids = {ch.chapter_id for ch in chapters}
                logger.info(f"Restored {len(chapters)} chapters from checkpoint")
        
        for dimension in framework.dimensions:
            # 跳过已恢复的章节
            if dimension.section_id in completed_section_ids:
                continue
            
            chapter_data = self._extract_chapter_data(
                aggregated_result, dimension.section_id
            )
            
            # 撰写章节
            chapter = await self._chapter_writer.write(
                ChapterWriteInput(
                    framework=framework,
                    chapter_spec=dimension,
                    chapter_data=chapter_data,
                    preceding_summary=preceding_summary,
                    used_metrics_summary=self._serialize_used_metrics(self._data_registry),
                )
            )
            
            # 注册本章使用的数据点（使用验证后的数据，而非LLM自报）
            validated_dps = await self._extract_and_validate_data_points(chapter)
            for dp in validated_dps:
                self._data_registry.register(
                    metric=dp.metric, value=dp.value, unit=dp.unit,
                    chapter_id=chapter.chapter_id, source=dp.source
                )
            
            # 自审不通过：当场重生成（内循环，零额外延迟开销）
            if not chapter.self_check_passed:
                logger.info(
                    f"Chapter {dimension.section_id} self-check failed: {chapter.self_check_issues}"
                )
                # 自审问题已由 Writer 在生成时尝试修正，此处记录未修正项
                # 这些未修正项会传递给 ChapterReviewAgent 作为审查线索
            
            # 独立审查闭环：审稿人审查 → 不通过则作者重写 → 再审
            # 【审计修正 #6】版本对比保底：保留最佳版本，防止重写质量退化
            best_chapter = chapter
            best_score = 0.0
            
            for rewrite_round in range(self.MAX_CHAPTER_REWRITE_ROUNDS):
                review = await self._chapter_reviewer.review(
                    ChapterReviewInput(
                        framework=framework,
                        chapter_spec=dimension,
                        chapter_content=chapter.content,
                        preceding_summary=preceding_summary,
                        used_metrics_summary=self._serialize_used_metrics(self._data_registry),
                        writer_self_check_issues=chapter.self_check_issues,
                    )
                )
                
                if review.passed:
                    if review.score > best_score:
                        best_chapter = chapter
                        best_score = review.score
                    break  # 审查通过，进入下一章
                
                # 记录当前版本为候选最佳
                if review.score > best_score:
                    best_chapter = chapter
                    best_score = review.score
                
                # 审查不通过：将审稿人的反馈传递给作者，指导重写
                logger.info(
                    f"Chapter {dimension.section_id} review round {rewrite_round+1}: "
                    f"score={review.score}, issues={len(review.issues)}"
                )
                chapter = await self._chapter_writer.rewrite(
                    original_chapter=chapter,
                    review_feedback=review,  # 传递审查反馈
                    framework=framework,
                    chapter_spec=dimension,
                    preceding_summary=preceding_summary,
                )
            
            # 使用最佳版本（而非最后一次重写的版本）
            chapter = best_chapter
            
            chapters.append(chapter)
            preceding_summary += f"\n【{chapter.title}】{'; '.join(chapter.key_conclusions)}"
            
            # 【审计修正 #9】每章完成后保存检查点
            if task_id:
                await self._checkpoint_chapter(task_id, chapter, self._data_registry)
        
        # Phase 3: 全局审查（主编角色）——两步审查
        # Step 1: 摘要审查（发现跨章节问题）
        report_summary = self._serialize_report_for_review(chapters, self._data_registry)
        conflicts_summary = self._serialize_conflicts(self._data_registry)
        
        review = await self._global_reviewer.review(
            ReviewInput(
                framework=framework,
                report_summary=report_summary,
                conflicts_summary=conflicts_summary,
            )
        )
        
        # Step 2: 问题验证（对发现的问题，读原文确认）
        if review.issues:
            verified_issues = await self._global_reviewer.verify_issues(
                review.issues, chapters
            )
            review.issues = verified_issues
        
        # Phase 4: 修正与优化（数据修补 + 冲突解决 + 内容重写）
        if review.overall_score < 80:
            chapters = await self._phase4_fix_and_optimize(
                chapters, review, framework, topic  # 【审计修正 A8】使用参数 topic
            )
        
        # 重新生成执行摘要（基于完整报告）
        exec_summary = await self._generate_exec_summary(chapters, framework)
        
        # 组装最终报告
        return self._assemble_final_report(chapters, exec_summary, review)
```

**ChapterWriter.rewrite() 设计**：审查反馈如何指导重写

```python
async def rewrite(self, original_chapter, review_feedback, framework, chapter_spec, preceding_summary):
    """根据审查反馈重写章节"""
    
    # 将审查问题格式化为具体的重写指令
    issue_instructions = []
    for issue in review_feedback.issues:
        issue_instructions.append(
            f"- [{issue.severity}] {issue.description}\n  修正方向：{issue.suggestion}"
        )
    
    prompt = f"""
    # 章节重写任务
    
    ## 当前章节内容
    {original_chapter.content}
    
    ## 审稿人反馈（必须逐条修正）
    {chr(10).join(issue_instructions)}
    
    ## 重写要求
    1. 逐条修正审稿人指出的每一个问题
    2. 不要删除没有问题的内容
    3. 修正后确保整体逻辑仍然连贯
    4. 保持原有的数据引用，除非审稿人指出数据有误
    
    ## 输出格式（严格JSON，包裹在 ```json ``` 中）
    ```json
    {
      "title": "章节标题",
      "content": "Markdown格式的重写后章节正文",
      "data_points_used": [{"metric": "指标名", "value": "数值", "unit": "单位", "source": "来源"}],
      "key_conclusions": ["结论1", "结论2"],
      "self_check_passed": true,
      "self_check_issues": []
    }
    ```
    """
    
    raw_output = await self._llm.generate(prompt)
    return self._parse_chapter_output(raw_output, chapter_spec)
```

### 3.6 新增组件：DataRepairAgent + ConflictResolver（数据修补与冲突解决）

**职责**：针对审查发现的数据缺失和数据冲突，执行定向搜索和修补。**审查只负责发现问题，修补是另一个独立能力。**

#### 3.6.1 数据缺失的修补

审查发现某章节缺少关键数据（如"市场规模章节未引用具体数值"），需要定向补充搜索。

```python
@dataclass
class DataGap:
    """数据缺失描述"""
    chapter_id: str                       # 哪个章节缺数据
    metric: str                           # 缺什么指标（如"市场规模"、"增长率"）
    context: str                          # 缺失上下文（审查Agent的描述）
    search_keywords: List[str]            # 建议的搜索关键词

@dataclass
class DataRepairResult:
    """数据修补结果"""
    gap: DataGap                          # 原始缺失描述
    found: bool                           # 是否找到数据
    value: Optional[str] = None           # 找到的数值
    unit: Optional[str] = None            # 单位
    source: Optional[str] = None          # 来源URL
    source_title: Optional[str] = None    # 来源标题
    confidence: float = 0.0               # 置信度 (0-1)
```

**修补流程**：

```python
class DataRepairAgent:
    """数据修补Agent：定向搜索缺失数据"""
    
    def __init__(self, search_skill, web_scraper_skill, llm_skill):
        self._search = search_skill
        self._scraper = web_scraper_skill
        self._llm = llm_skill
    
    async def repair_gap(self, gap: DataGap, topic: str) -> DataRepairResult:
        """修补单个数据缺失"""
        
        # Step 1: 构造精确的搜索查询
        query = f"{topic} {gap.metric} {' '.join(gap.search_keywords[:3])}"
        search_results = await self._search.execute({"query": query, "max_results": 10})
        
        if not search_results:
            return DataRepairResult(gap=gap, found=False)
        
        # Step 2: 抓取 top 3 搜索结果的内容
        scraped_contents = []
        for result in search_results[:3]:
            url = result.get("url", "")
            if url:
                content = await self._scraper.execute({"url": url})
                if content:
                    scraped_contents.append({
                        "url": url,
                        "title": result.get("title", ""),
                        "content": content[:3000],  # 截断控制 token
                    })
        
        if not scraped_contents:
            return DataRepairResult(gap=gap, found=False)
        
        # Step 3: 用 LLM 从抓取内容中提取目标数据
        extraction_prompt = f"""
        从以下搜索结果中提取"{gap.metric}"的具体数值。
        缺失上下文：{gap.context}
        研究主题：{topic}
        
        搜索结果：
        {chr(10).join(f'--- 来源: {c["title"]} ({c["url"]}) ---{chr(10)}{c["content"]}' for c in scraped_contents)}
        
        要求：
        1. 只提取有明确来源的数据，不要推断
        2. 如果多个来源给出不同数值，列出所有及来源
        3. 如果搜索结果中没有相关数据，返回 found=false
        """
        
        extraction = await self._llm.generate(extraction_prompt)
        return self._parse_extraction(extraction, gap, scraped_contents)
    
    async def repair_batch(self, gaps: List[DataGap], topic: str) -> List[DataRepairResult]:
        """批量修补数据缺失（并行搜索）"""
        tasks = [self.repair_gap(gap, topic) for gap in gaps]
        return await asyncio.gather(*tasks)
```

#### 3.6.2 数据冲突的解决

DataRegistry 检测到同一指标在不同章节出现不同数值时，需要裁决哪个是规范值。

```python
@dataclass
class DataConflict:
    """数据冲突描述"""
    metric: str                           # 冲突指标名
    entries: List[ConflictEntry]          # 所有冲突条目（含章节、数值、来源）

@dataclass
class ConflictEntry:
    chapter_id: str
    value: str
    unit: str
    source: str                           # 数据来源

@dataclass
class ConflictResolution:
    """冲突解决结果"""
    conflict: DataConflict
    canonical_value: str                  # 裁决后的规范值
    canonical_unit: str                   # 规范单位
    canonical_source: str                 # 规范来源
    reason: str                           # 裁决理由
    chapters_to_update: List[str]         # 需要更新数值的章节
```

**冲突解决流程**：

```python
class ConflictResolver:
    """数据冲突裁决器"""
    
    def __init__(self, llm_skill, search_skill=None, web_scraper_skill=None):
        self._llm = llm_skill
        self._search = search_skill        # 可选：需要时再搜索验证
        self._scraper = web_scraper_skill
    
    async def resolve(self, conflict: DataConflict, topic: str) -> ConflictResolution:
        """解决单个数据冲突"""
        
        # 策略1：基于来源权威性裁决（不需要额外搜索）
        # 优先级：官方统计 > 行业报告 > 新闻媒体 > 博客/自媒体
        # 【审计修正 #8】扩展为可配置来源权威性表+描述规则，覆盖国际来源
        source_authority = {
            # 政府
            "gov.cn": 10, "gov": 8,
            # 国际组织
            "worldbank.org": 9, "imf.org": 9, "oecd.org": 9,
            # 国内研究机构
            "iimedia.cn": 8, "iresearch.cn": 8,
            # 国际咨询/研究
            "mckinsey.com": 8, "bcg.com": 8, "idc.com": 8, "gartner.com": 8,
            "statista.com": 7,
            # 学术
            "nature.com": 8, "arxiv.org": 7, "sciencedirect.com": 7,
            # 财经媒体
            "bloomberg.com": 6, "reuters.com": 6,
            "eastmoney.com": 6, "10jqka.com.cn": 6,
            # 科技/综合媒体
            "36kr.com": 4, "sohu.com": 3,
        }
        
        # 基于来源描述的规则（当域名匹配不到时使用）
        description_rules = [
            (r"国家统计局|官方统计|政府公告", 10),
            (r"年报|季报|财报|IPO招股书", 8),
            (r"研究报告|白皮书|行业报告", 7),
            (r"新闻报道|媒体报道", 4),
        ]
        
        # 尝试按来源权威性裁决
        best_entry = None
        best_score = -1
        for entry in conflict.entries:
            score = 0
            # 域名匹配
            for domain, authority in source_authority.items():
                if domain in (entry.source or ""):
                    score = authority
                    break
            # 描述规则匹配（当域名匹配不到时）
            if score == 0 and entry.source:
                import re
                for pattern, rule_score in description_rules:
                    if re.search(pattern, entry.source):
                        score = rule_score
                        break
            if score > best_score:
                best_score = score
                best_entry = entry
        
        # 如果有明确的高权威来源，直接裁决
        if best_entry and best_score >= 6:
            chapters_to_update = [
                e.chapter_id for e in conflict.entries 
                if e.value != best_entry.value
            ]
            return ConflictResolution(
                conflict=conflict,
                canonical_value=best_entry.value,
                canonical_unit=best_entry.unit,
                canonical_source=best_entry.source,
                reason=f"来源 {best_entry.source} 权威性更高（评分={best_score}），采用其数值",
                chapters_to_update=chapters_to_update,
            )
        
        # 策略2：来源权威性无法裁决时，定向搜索验证
        search_query = f"{topic} {conflict.metric} 最新数据"
        search_results = await self._search.execute({"query": search_query, "max_results": 5})
        
        # 用 LLM 综合原始冲突 + 搜索结果进行裁决
        resolution_prompt = f"""
        以下数据存在冲突，请裁决哪个数值更可靠：
        
        指标：{conflict.metric}
        冲突条目：
        {chr(10).join(f'- 章节{e.chapter_id}：{e.value} {e.unit}（来源：{e.source}）' for e in conflict.entries)}
        
        补充搜索结果：
        {chr(10).join(f'- {r.get("title","")}: {r.get("snippet","")}' for r in (search_results or [])[:5])}
        
        裁决要求：
        1. 优先采用官方统计/权威研究机构的数据
        2. 优先采用更新日期更近的数据
        3. 优先采用更详细的数值（如"2180亿元"优先于"约2000亿元"）
        4. 给出裁决理由
        5. 给出规范值、规范单位、规范来源
        """
        
        resolution = await self._llm.generate(resolution_prompt)
        return self._parse_resolution(resolution, conflict)
```

#### 3.6.3 数据修补结果如何回写报告

修补后的数据不是简单地替换文本，而是通过 ChapterWriter 定向重写：

> **审计修正 #2（致命）**：patch_data 修改章节后，必须重新执行 ChapterReviewAgent 审查，否则修补可能引入新的逻辑错误。同时，修补可能改变了 key_conclusions，后续章节的 preceding_summary 需要重建。

```python
async def _apply_data_repairs(self, chapters, repair_results, conflict_resolutions, framework):
    """将数据修补和冲突解决结果应用到报告"""
    
    # 1. 收集每个章节需要更新的数据
    chapter_updates: Dict[str, List[Dict]] = {}  # chapter_id → [{metric, old_value, new_value, source}]
    
    for result in repair_results:
        if result.found:
            chapter_updates.setdefault(result.gap.chapter_id, []).append({
                "type": "gap_filled",
                "metric": result.gap.metric,
                "new_value": result.value,
                "unit": result.unit,
                "source": result.source,
            })
    
    for resolution in conflict_resolutions:
        for chapter_id in resolution.chapters_to_update:
            chapter_updates.setdefault(chapter_id, []).append({
                "type": "conflict_resolved",
                "metric": resolution.conflict.metric,
                "canonical_value": resolution.canonical_value,
                "canonical_unit": resolution.canonical_unit,
                "canonical_source": resolution.canonical_source,
                "reason": resolution.reason,
            })
    
    # 2. 对有数据更新的章节，调用 ChapterWriter 定向修补
    # 【审计修正 A1】返回修补的章节ID集合，而非依赖 _patched 动态属性
    patched_chapter_ids = set()
    
    for i, chapter in enumerate(chapters):
        updates = chapter_updates.get(chapter.chapter_id, [])
        if not updates:
            continue
        
        # 构造修补指令
        patch_instructions = []
        for update in updates:
            if update["type"] == "gap_filled":
                patch_instructions.append(
                    f"补充缺失数据：{update['metric']} = {update['new_value']} {update['unit']}（来源：{update['source']}）"
                )
            elif update["type"] == "conflict_resolved":
                patch_instructions.append(
                    f"数据冲突修正：{update['metric']} 统一为 {update['canonical_value']} {update['canonical_unit']}"
                    f"（来源：{update['canonical_source']}，理由：{update['reason']}）"
                )
        
        # 调用 Writer 定向修补（不是全文重写，只修正数据相关段落）
        chapters[i] = await self._chapter_writer.patch_data(
            chapter=chapter,
            patch_instructions=patch_instructions,
            framework=framework,
        )
        patched_chapter_ids.add(chapter.chapter_id)
        
        # 更新 DataRegistry 中的规范值
        for update in updates:
            if update["type"] == "conflict_resolved":
                self._data_registry.set_canonical_value(
                    metric=update["metric"],
                    value=update["canonical_value"],
                    source=update["canonical_source"],
                )
    
    return chapters, patched_chapter_ids
```

**ChapterWriter.patch_data() 设计**：数据修补不是全文重写，只修正涉及数据的段落

```python
async def patch_data(self, chapter, patch_instructions, framework):
    """定向修补章节中的数据，不重写全文"""
    
    prompt = f"""
    # 数据修补任务
    
    ## 当前章节内容
    {chapter.content}
    
    ## 需要修补的数据（只修正涉及这些数据的段落，不要重写整章）
    {chr(10).join(f'- {inst}' for inst in patch_instructions)}
    
    ## 修补要求
    1. 只修改涉及上述数据的句子，逐句替换，不要重写段落
    2. 替换格式：将"旧数值 旧单位"替换为"新数值 新单位"，其他文字不变
    3. 如果原文是"市场规模约为2000亿元"，只能改为"市场规模约为2180亿元"，不能改写为其他表述
    4. 不要改动与数据无关的任何内容
    5. 补充数据来源标注
    6. 修补后输出完整章节内容，标注哪些行做了修改（用 [MODIFIED] 标记）
    
    ## 输出格式（严格JSON，包裹在 ```json ``` 中）
    ```json
    {
      "title": "章节标题",
      "content": "Markdown格式的修补后完整章节正文（用 [MODIFIED] 标记修改行）",
      "data_points_used": [{"metric": "指标名", "value": "数值", "unit": "单位", "source": "来源"}],
      "key_conclusions": ["结论1", "结论2"],
      "self_check_passed": true,
      "self_check_issues": []
    }
    ```
    """
    
    raw_output = await self._llm.generate(prompt)
    return self._parse_chapter_output(raw_output, chapter_spec)
```

#### 3.6.4 完整的 Phase 4 流程

```python
async def _phase4_fix_and_optimize(self, chapters, review, framework, topic):
    """Phase 4: 修正与优化（数据修补 + 冲突解决 + 内容重写）"""
    
    # Step 1: 从审查结果中提取数据问题
    data_gaps = []       # 数据缺失
    data_conflicts = []  # 数据冲突
    
    for issue in review.issues:
        if issue.category == "data_support" and "缺失" in issue.description:
            data_gaps.append(DataGap(
                chapter_id=issue.location,
                metric=self._extract_metric(issue.description),
                context=issue.description,
                search_keywords=self._generate_search_keywords(issue, topic),
            ))
        elif issue.category == "data_consistency":
            conflict = self._data_registry.get_conflict(issue.location)
            if conflict:
                data_conflicts.append(conflict)
    
    # Step 2: 并行执行数据修补和冲突解决
    repair_task = self._data_repair_agent.repair_batch(data_gaps, topic)
    resolve_tasks = [self._conflict_resolver.resolve(c, topic) for c in data_conflicts]
    
    repair_results, *resolution_results = await asyncio.gather(
        repair_task, *resolve_tasks
    )
    
    # Step 3: 将修补结果回写报告
    chapters, patched_chapter_ids = await self._apply_data_repairs(
        chapters, repair_results, resolution_results, framework
    )
    
    # Step 4: 【审计修正 #2 / A1】修补后的章节必须重新审查
    for i, chapter in enumerate(chapters):
        if chapter.chapter_id not in patched_chapter_ids:
            continue
            
        re_review = await self._chapter_reviewer.review(
            ChapterReviewInput(
                framework=framework,
                chapter_spec=self._find_dimension(framework, chapter.chapter_id),
                chapter_content=chapter.content,
                preceding_summary="",  # 先用空值，下面会重建
                used_metrics_summary=self._serialize_used_metrics(self._data_registry),
                writer_self_check_issues=[],
            )
        )
        
        if not re_review.passed:
            chapter = await self._chapter_writer.rewrite(
                original_chapter=chapter,
                review_feedback=re_review,
                framework=framework,
                chapter_spec=self._find_dimension(framework, chapter.chapter_id),
                preceding_summary="",
            )
            chapters[i] = chapter
    
    # Step 5: 【审计修正 #5】重建 preceding_summary
    # patch_data 可能改变了 key_conclusions，后续章节的 preceding_summary 必须重建
    preceding_summary = self._rebuild_preceding_summary(chapters)
    
    # Step 6: 【审计修正 #5】验证后续章节的一致性
    await self._verify_downstream_consistency(chapters, patched_chapter_ids, framework)
    
    # Step 7: 对非数据问题（逻辑/叙事），调用 ChapterWriter 定向重写
    content_issues = [i for i in review.issues if i.category not in ("data_support", "data_consistency")]
    if content_issues:
        chapters = await self._apply_content_fixes(chapters, content_issues, framework)
    
    return chapters

def _rebuild_preceding_summary(self, chapters) -> str:
    """重建前文摘要（修补后必须调用）"""
    summary_parts = []
    for ch in chapters:
        summary_parts.append(f"【{ch.title}】{'; '.join(ch.key_conclusions)}")
    return "\n".join(summary_parts)

async def _verify_downstream_consistency(self, chapters, patched_chapter_ids, framework):
    """验证被修改章节的后续章节是否仍然一致"""
    import re
    for i, chapter in enumerate(chapters):
        if chapter.chapter_id in patched_chapter_ids:
            continue
        for patched_id in patched_chapter_ids:
            patched_ch = next((c for c in chapters if c.chapter_id == patched_id), None)
            if not patched_ch:
                continue
            for dp in patched_ch.data_points_used:
                if dp.metric and dp.metric in chapter.content:
                    pattern = re.compile(re.escape(dp.value) + r'\s*' + re.escape(dp.unit))
                    if not pattern.search(chapter.content):
                        logger.warning(
                            f"Chapter {chapter.chapter_id} references '{dp.metric}' "
                            f"with outdated value after patch of chapter {patched_id}"
                        )
```
```

### 3.7 报告内容格式：Markdown，不是HTML

#### 3.7.1 当前系统的格式链路

```
Agent输出(Markdown文本)
  → ContentOrchestrator._content_to_html()  [Markdown→HTML转换]
    → HTML中间格式
      → html_to_word.py  [HTML→DOCX]
      → html_to_pdf.py   [HTML→PDF]
      → html_to_ppt.py   [HTML→PPTX]
      → 直接输出          [HTML预览]
```

关键事实：**LLM Agent 的原生输出就是 Markdown**。当前系统中 `content_orchestrator.py:801` 的 `_content_to_html()` 做的就是把 Markdown 文本逐行解析转换为 HTML 标签（`## Title` → `<h2>Title</h2>`，`**bold**` → `<strong>bold</strong>` 等）。

#### 3.7.2 新方案的选择：ChapterWriter 输出 Markdown

**结论：ChapterWriter 和 ChapterReviewAgent 的输入输出都应该是 Markdown，不是 HTML。**

理由：

| 考量 | Markdown | HTML |
|------|----------|------|
| LLM原生能力 | LLM天然擅长生成Markdown | LLM生成HTML容易出错（标签不闭合、属性错误） |
| 可读性 | 人可读，审查Agent容易理解内容 | 嵌套标签难以阅读，审查Agent需要额外解析 |
| 修补难度 | 定位段落直接改文本 | 需要在HTML结构中定位节点，容易破坏DOM |
| 数据冲突定位 | 直接搜索数值即可 | 需要剥离HTML标签才能找到数值 |
| 格式转换 | 已有 `_content_to_html()` 转换 | 直接可用，但失去中间层的灵活性 |
| 审查反馈 | "第3段数据有误" → 直接定位 | "第3个`<p>`标签数据有误" → 需要DOM定位 |

**核心原则内容层用Markdown，表现层用HTML，格式转换由已有的 ContentOrchestrator 统一处理。**

```
新方案格式链路：

ChapterWriter 输出 Markdown
  → ChapterReviewAgent 审查 Markdown（人可读，容易定位问题）
  → ConflictResolver/DataRepairAgent 修补 Markdown（直接改文本，不破坏结构）
  → ReportOrchestrator 组装完整报告（Markdown格式的sections）
  → ContentOrchestrator.transform_to_html()  [已有，Markdown→HTML]
    → HTML中间格式
      → html_to_word / html_to_pdf / html_to_ppt  [已有，不变]
```

#### 3.7.3 具体影响

1. **ChapterWriteOutput.content** 是 Markdown 字符串，不是 HTML
2. **ChapterReviewInput.chapter_content** 是 Markdown，审查Agent直接读Markdown
3. **DataRepairAgent / ConflictResolver** 修补的是 Markdown 文本，定位和替换都是纯文本操作
4. **patch_data()** 修补Markdown段落，然后由 ContentOrchestrator 统一转HTML
5. **最终输出**：ReportOrchestrator 组装的 `research_result` 中 sections 的 content 是 Markdown，传入 `DocumentGenerationAgent` 后由 ContentOrchestrator 转为 HTML——**这条链路完全复用现有代码，不需要改**

#### 3.7.4 审查反馈的定位方式

Markdown格式下，审查反馈可以精确到段落级别：

```python
@dataclass
class ChapterIssue:
    category: str
    severity: str
    location: str                         # Markdown定位方式：
                                          #   "paragraph:3" → 第3段
                                          #   "heading:2.1" → 2.1小节
                                          #   "table:1" → 第1个表格
                                          #   "data:市场规模" → 包含"市场规模"的段落
    description: str
    suggestion: str
```

```python
def locate_in_markdown(content: str, location: str) -> str:
    """在Markdown内容中定位问题段落"""
    if location.startswith("paragraph:"):
        idx = int(location.split(":")[1])
        paragraphs = [p for p in content.split("\n\n") if p.strip()]
        return paragraphs[idx] if idx < len(paragraphs) else ""
    
    elif location.startswith("heading:"):
        target = location.split(":", 1)[1]
        # 找到该标题下的内容直到下一个同级/更高级标题
        ...
    
    elif location.startswith("data:"):
        keyword = location.split(":", 1)[1]
        # 找到包含该关键词的段落
        for para in content.split("\n\n"):
            if keyword in para:
                return para
        return ""
```

### 3.8 串行 vs 并行的权衡

**关键设计决策**：逐章生成必须是**串行**的，因为每章需要前文上下文。

> **审计修正 A11（中等）**：本节描述的章节分组并行策略是**性能优化项**，非核心设计。实施路线图中 Phase 2 先实现串行版本确保功能正确，Phase 5 性能优化时再集成并行策略。

但这会显著增加总耗时。解决方案：

1. **章节分组并行**：将逻辑上无依赖的章节分组，组内并行、组间串行
   ```
   Group 1 (并行): 市场规模 + 政策环境（无逻辑依赖）
   Group 2 (串行于Group1后): 竞争格局（依赖市场规模数据）
   Group 3 (串行于Group2后): 投资建议（依赖前面所有章节）
   ```

2. **前文摘要压缩**：不传递完整前文，只传递核心结论摘要（每章3-5条），控制 token 消耗

3. **数据注册表预填充**：在并行组执行前，预先从聚合结果中提取数据点填充注册表，避免数据冲突

```python
@dataclass
class ChapterGroup:
    """章节分组"""
    group_id: str
    chapters: List[FrameworkDimension]  # 组内章节（可并行）
    depends_on: List[str]               # 依赖的前序分组ID
```

分组策略由 `ResearchFramework.logic_chain` 决定：

```python
def _plan_chapter_groups(self, framework: ResearchFramework) -> List[ChapterGroup]:
    """根据逻辑链规划章节分组"""
    groups = []
    processed = set()
    
    for i, link in enumerate(framework.logic_chain):
        # 找出逻辑链中同一层级的章节
        same_level = [d for d in framework.dimensions 
                      if d.role_in_report == link and d.section_id not in processed]
        if same_level:
            groups.append(ChapterGroup(
                group_id=f"group_{i}",
                chapters=same_level,
                depends_on=[f"group_{j}" for j in range(i) if j < len(groups)]
            ))
            processed.update(d.section_id for d in same_level)
    
    # 未被逻辑链覆盖的章节归入最后一组
    remaining = [d for d in framework.dimensions if d.section_id not in processed]
    if remaining:
        groups.append(ChapterGroup(
            group_id=f"group_{len(groups)}",
            chapters=remaining,
            depends_on=[g.group_id for g in groups]
        ))
    
    return groups
```

---

## 4. 与现有代码的集成方案

### 4.1 改造点清单

| 序号 | 改造点 | 现有代码 | 改造方式 |
|------|--------|----------|----------|
| 1 | `orchestrator.py` 报告生成阶段 | L972-980 直接调用 `DocumentGenerationAgent` | 替换为调用 `ReportOrchestrator.generate_report()` |
| 2 | `ReportGenerationAgent` | 纯排版工，不调用 LLM | 保留作为 fallback，新增 `ChapterWriter` 作为主路径 |
| 3 | `DocumentGenerationAgent` | 负责格式转换 | 不变，在 `ReportOrchestrator` 输出后调用 |
| 4 | `QualityCheckAgent` | 只做格式检查 | 保留格式检查职责，内容审查由 `ChapterReviewAgent` + `GlobalReviewAgent` 接管 |
| 5 | `ResultAggregator` | 简单聚合 | 不变，继续负责数据聚合，输出供 `ReportOrchestrator` 消费 |
| 6 | `ResearchFramework` | 已有数据结构 | 扩展 `logic_chain` 和 `dimensions` 字段，确保框架信息传递到报告生成阶段 |
| 7 | **新增** `ChapterReviewAgent` | 无 | 独立审查Agent，与 ChapterWriter 完全解耦 |
| 8 | **新增** `DataRepairAgent` | 无 | 数据修补Agent，使用 SearchSkill + WebScraperSkill 定向搜索补充缺失数据 |
| 9 | **新增** `ConflictResolver` | 无 | 数据冲突裁决器，基于来源权威性或定向搜索验证裁决规范值 |
| 10 | `SearchSkill` + `WebScraperSkill` | 已有 | 不变，被 `DataRepairAgent` 调用执行定向搜索和内容抓取 |

### 4.2 改造后的 orchestrator.py 流程

```python
# 现有代码（L972-980）：
preview_result = await self._document_agent.execute({
    "action": "get_preview",
    "output_format": "html",
    "research_result": research_result_data,
    ...
})

# 改造后：
# Step 1: 使用 ReportOrchestrator 生成高质量内容（含独立审查闭环）
report_orchestrator = ReportOrchestrator(
    llm_skill=self._get_llm_skill(),
    chapter_writer=ChapterWriter(llm_skill=self._get_llm_skill()),
    chapter_reviewer=ChapterReviewAgent(llm_skill=self._get_review_llm_skill()),  # 独立审查Agent
    global_reviewer=GlobalReviewAgent(llm_skill=self._get_review_llm_skill()),     # 独立全局审查Agent
    data_repair_agent=DataRepairAgent(                                             # 数据修补Agent
        search_skill=self._skill_registry.get("search"),
        web_scraper_skill=self._skill_registry.get("web_scraper"),
        llm_skill=self._get_llm_skill(),
    ),
    conflict_resolver=ConflictResolver(                                            # 冲突裁决器
        llm_skill=self._get_llm_skill(),
        search_skill=self._skill_registry.get("search"),
        web_scraper_skill=self._skill_registry.get("web_scraper"),
    ),
)
enriched_report = await report_orchestrator.generate_report(
    framework=research_framework,  # 从 routing_result 或 requirement 中获取
    aggregated_result=aggregated_dict,
    section_details=requirement.section_details,
)

# Step 2: 使用 DocumentGenerationAgent 做格式转换（不变）
preview_result = await self._document_agent.execute({
    "action": "get_preview",
    "output_format": "html",
    "research_result": enriched_report,  # 使用经过审查优化的报告
    ...
})
```

### 4.3 框架信息的传递

当前 `ResearchFramework` 在智能路由阶段生成，但在报告生成阶段丢失。需要确保框架信息沿以下路径传递：

```
IntelligentRoutingAdapter.analyze()
  → RoutingResult.task_structure (含 framework)
    → orchestrator._research_with_routing()
      → ReportOrchestrator.generate_report(framework=...)
```

具体改造：

1. 在 `RoutingResult` 中保存 `ResearchFramework`（当前只有 `TaskStructure`，需扩展）
2. 在 `orchestrator.py` 中将 framework 传递给报告生成阶段
3. 如果没有 framework（旧路径），从 `requirement.aspects` 自动生成一个简化版 framework

```python
def _ensure_framework(self, requirement, routing_result=None):
    """确保有可用的研究框架"""
    if routing_result and hasattr(routing_result, 'framework'):
        return routing_result.framework
    
    # Fallback: 从 aspects 自动生成简化框架
    return ResearchFramework(
        core_question=requirement.topic,
        core_narrative=f"关于{requirement.topic}的综合研究",
        dimensions=[
            FrameworkDimension(
                section_id=f"section_{i}",
                section_name=aspect,
                role_in_report=f"分析{aspect}维度",
                sub_questions=[f"{aspect}的现状如何？", f"{aspect}的趋势如何？"],
                keywords=[aspect],
            )
            for i, aspect in enumerate(requirement.aspects)
        ],
        logic_chain=requirement.aspects,
    )
```

---

## 5. 执行摘要的特殊处理

### 5.1 当前问题

`ReportGenerationAgent._generate_exec_summary()` 只是从各章节抽取前两句拼接，不是真正的综合提炼。

### 5.2 新方案

执行摘要必须在**所有章节完成后**生成，且必须基于完整报告内容：

```python
async def _generate_exec_summary(self, chapters, framework):
    """基于完整报告生成执行摘要"""
    # 收集所有章节的核心结论
    all_conclusions = []
    for ch in chapters:
        all_conclusions.extend(ch.key_conclusions)
    
    # 收集数据冲突（需要在摘要中标注）
    # 【审计修正 A7】ConflictEntry 无 description 字段，改用已有字段构造
    conflicts = self._data_registry.get_conflicts()
    conflict_descriptions = []
    for c in conflicts:
        if isinstance(c, DataConflict):
            values_str = ', '.join(f'{e.value}{e.unit}（来源:{e.source}）' for e in c.entries)
            conflict_descriptions.append(f'{c.metric}: {values_str}')
    
    prompt = f"""
    # 执行摘要撰写任务
    
    ## 研究框架
    核心问题：{framework.core_question}
    核心叙事线：{framework.core_narrative}
    
    ## 各章节核心结论
    {chr(10).join(f'- {c}' for c in all_conclusions)}
    
    ## 数据冲突（需在摘要中谨慎处理）
    {chr(10).join(f'- {d}' for d in conflict_descriptions) if conflict_descriptions else '无'}
    
    ## 撰写要求
    1. 基于核心叙事线，将各章节结论整合为连贯的执行摘要
    2. 突出最重要的3-5个发现
    3. 对数据冲突给出明确判断
    4. 长度：800-1200字
    5. 面向决策层，语言精炼有力
    """
    
    return await self._llm.generate(prompt)
```

---

## 6. 质量保障机制

### 6.1 四级质量门控

```
Level 0: 自审（ChapterWriter 内循环，实时）
  - 生成内容后立即自检：格式、数据遗漏、明显矛盾
  - 发现问题当场修正，零额外延迟
  - 自审是第一道防线，挡住低级错误，不让它们流到后续环节

Level 1: 章节独立审查（ChapterReviewAgent，事后）
  - 每章完成后由独立审查Agent审查
  - 覆盖自审无法触及的深层问题：逻辑缺陷、视角盲区、标准松懈
  - 不通过则将审查反馈传递给 ChapterWriter 重写
  - 最多2轮重写闭环

Level 2: 全局审查（GlobalReviewAgent）
  - 所有章节完成后由独立主编Agent审查
  - 检查5大维度（数据一致性、内容去重、逻辑连贯、叙事完整、风格统一）
  - 输出具体问题和修正建议

Level 3: 修正验证（FixApplier）
  - 根据全局审查结果定向修正
  - 修正后重新审查修正部分
  - 最多2轮修正

Level 4: 最终确认
  - 审查修正后仍存在 MEDIUM/LOW 级问题时，在报告中标注质量警告
  - CRITICAL/HIGH 级问题必须全部解决才能输出
```

### 6.2 质量评分体系

```python
@dataclass
class ReportQualityScore:
    """报告质量评分"""
    data_consistency: float     # 数据一致性 (0-100)
    content_uniqueness: float   # 内容去重率 (0-100)
    logic_coherence: float      # 逻辑连贯性 (0-100)
    narrative_completeness: float  # 叙事完整性 (0-100)
    style_uniformity: float     # 风格统一性 (0-100)
    
    @property
    def overall(self) -> float:
        weights = {
            'data_consistency': 0.30,
            'content_uniqueness': 0.15,
            'logic_coherence': 0.25,
            'narrative_completeness': 0.20,
            'style_uniformity': 0.10,
        }
        return sum(getattr(self, k) * v for k, v in weights.items())
```

---

## 7. 性能优化

### 7.1 Token 消耗控制

逐章生成会增加 LLM 调用次数。优化策略：

1. **前文摘要压缩**：每章只传递前文的核心结论（3-5条），不传递完整内容
2. **数据选择性传递**：只传递与当前章节相关的数据，不传递全部聚合结果
3. **框架缓存**：框架理解阶段的结果缓存，避免重复计算
4. **审查Agent用小模型**：ChapterReviewAgent 使用 GPT-4o-mini 等小模型（审查不需要创造力，需要严谨性），ChapterWriter 和 GlobalReviewAgent 使用大模型

### 7.2 耗时控制

| 阶段 | 预估耗时 | 优化措施 |
|------|----------|----------|
| 框架理解 | 5s | 一次 LLM 调用 |
| 逐章撰写 | N × 30s | 分组并行，N为分组数（非章节数） |
| 逐章审查 | N × 15s | 使用小模型（GPT-4o-mini），分组并行 |
| 重写闭环 | 0-N × 45s | 仅未通过审查的章节触发，最多2轮 |
| 全局审查 | 20s | 一次 LLM 调用 |
| 数据修补 | 5-30s/个 | 定向搜索+LLM提取，并行执行 |
| 冲突裁决 | 5-15s/个 | 来源权威性优先，必要时定向搜索验证 |
| 数据回写 | 15s/章 | 仅涉及数据的章节，patch_data 非全文重写 |
| 修正优化 | 0-60s | 最多2轮，每轮只修正问题章节 |
| **总计** | **约5-8分钟** | 对比现有流程约2分钟，但质量根本性提升 |

### 7.3 重试策略

**原则**：绝不降级到机械组装模式。机械组装的输出存在严重的数据冲突和质量问题，几乎没有可用价值，降级到它等于放弃质量。

采用**分级重试**策略：

```python
class RetryPolicy:
    """分级重试策略"""
    
    MAX_CHAPTER_RETRIES = 3       # 单章节最大重试次数
    MAX_REVIEW_RETRIES = 2        # 全局审查修正最大轮数
    MAX_FULL_RETRIES = 1          # 整体流程最大重试次数
    RETRY_BACKOFF_BASE = 2        # 退避基数（秒）
    
    @staticmethod
    def get_delay(attempt: int) -> float:
        """指数退避：2s → 4s → 8s"""
        return RetryPolicy.RETRY_BACKOFF_BASE ** attempt
```

**三级重试机制**：

```
Level 1: 章节级重试
  触发条件：自审不通过（当场重生成）或 ChapterReviewAgent 审查不通过
  处理方式：
    - 自审不通过 → Writer 当场修正（内循环，已合并到单次调用中）
    - 审查不通过 → 将审查反馈传递给 ChapterWriter 重写（最多2轮闭环）
  超时处理：2轮重写仍不通过 → 接受当前版本，在全局审查阶段重点处理该章节

Level 2: 审查级重试
  触发条件：全局审查评分 < 70，存在 CRITICAL/HIGH 级问题
  处理方式：根据修正建议定向修正问题章节（最多2轮）
  超时处理：2轮修正仍未通过 → 接受当前版本，在报告中标注"质量警告"

Level 3: 整体级重试
  触发条件：整体流程异常（如 LLM 服务间歇性不可用）
  处理方式：等待退避时间后，从断点恢复重新执行整体流程（最多1次）
  失败处理：1次重试仍失败 → 标记任务为"failed"，明确告知用户失败原因，
            不输出低质量的机械组装报告
```

**实现**：

> **审计修正 A4（致命）**：原文档存在两版 `generate_report`（3.5节主版本和7.3节重试版本），两版逻辑不一致。7.3节的独立代码已删除，其重试逻辑应作为主版本的异常处理扩展集成。以下是主版本增加重试逻辑后的关键补充点：
>
> 1. **章节级异常重试**：在 Phase 2 的章节撰写循环中，对 `LLMTimeoutError` / `LLMRateLimitError` 做异常捕获和重试（最多3次，指数退避）
> 2. **重试时注入失败原因**：将上次失败原因作为 `previous_failures` 传入 ChapterWriteInput
> 3. **章节撰写失败兜底**：3次重试仍失败时，标记为 MissingChapter，在全局审查后补写
> 4. **整体级重试**：最外层 try/except，整体异常时从检查点恢复重试（最多1次）
>
> ```python
> # Phase 2 中章节级异常重试的关键代码片段
> for dimension in framework.dimensions:
>     if dimension.section_id in completed_section_ids:
>         continue
>     
>     chapter = None
>     last_chapter_error = None
>     
>     for chapter_attempt in range(RetryPolicy.MAX_CHAPTER_RETRIES):
>         try:
>             chapter = await self._chapter_writer.write(
>                 ChapterWriteInput(
>                     ...,
>                     previous_failures=[last_chapter_error] if last_chapter_error else None,
>                 )
>             )
>             # ... 审查闭环（版本对比保底） ...
>             break  # 成功
>         except (LLMTimeoutError, LLMRateLimitError) as e:
>             last_chapter_error = str(e)
>             delay = RetryPolicy.get_delay(chapter_attempt)
>             logger.warning(f"Chapter attempt {chapter_attempt+1} failed: {e}, retrying in {delay}s")
>             await asyncio.sleep(delay)
>     
>     if chapter is None:
>         chapters.append(MissingChapter(placeholder=dimension))
>         continue
>     
>     chapters.append(chapter)
>     ...
> ```
>
> ```python
> # 最外层整体级重试
> async def generate_report(self, framework, aggregated_result, section_details, task_id=None, topic=""):
>     last_error = None
>     for full_attempt in range(RetryPolicy.MAX_FULL_RETRIES + 1):
>         try:
>             # ... 主流程（Phase 1-4） ...
>             return result
>         except Exception as e:
>             last_error = e
>             if full_attempt < RetryPolicy.MAX_FULL_RETRIES:
>                 delay = RetryPolicy.get_delay(full_attempt)
>                 logger.warning(f"Full attempt {full_attempt+1} failed: {e}, retrying in {delay}s")
>                 await asyncio.sleep(delay)
>     
>     raise ReportGenerationError(
>         f"Report generation failed after {RetryPolicy.MAX_FULL_RETRIES + 1} attempts. "
>         f"Last error: {last_error}"
>     )
> ```

**关键设计**：

1. **绝不降级到机械组装**：所有重试用尽后，标记任务失败而非输出低质量报告。用户可以通过"重试"按钮触发新的生成流程。
2. **断点恢复**：已成功生成的章节会被缓存，整体重试时跳过已完成章节。
3. **重试时注入失败原因**：让 LLM 知道上次为什么失败，避免重复犯错。
4. **缺失章节补写**：单章节多次重试失败后，用简化 prompt 再尝试一次补写，而非直接跳过。
5. **质量警告标注**：审查修正后仍不完美时，在报告中明确标注质量警告，而非隐瞒问题。

---

## 8. 实施路线图

### Phase 1: 基础设施（1-2天）

- [ ] 实现 `DataRegistry` 全局数据注册表
- [ ] 扩展 `ResearchFramework` 数据结构，确保 `logic_chain` 和 `dimensions` 完整
- [ ] 在 `orchestrator.py` 中确保 framework 信息传递到报告生成阶段

### Phase 2: ChapterWriter + ChapterReviewAgent（3-4天）

- [ ] 实现 `ChapterWriter`，包含章节撰写 Prompt
- [ ] 实现 `ChapterReviewAgent`（独立审查Agent），包含5维度审查 Prompt
- [ ] 实现审查反馈→重写的闭环机制
- [ ] 实现前文摘要传递机制
- [ ] 实现章节分组并行策略

### Phase 3: GlobalReviewAgent + DataRepairAgent + ConflictResolver（3-4天）

- [ ] 实现 `GlobalReviewAgent`，包含5维度全局审查 Prompt
- [ ] 实现 `DataRepairAgent`，利用 SearchSkill + WebScraperSkill 定向搜索补充缺失数据
- [ ] 实现 `ConflictResolver`，基于来源权威性+定向搜索验证裁决数据冲突
- [ ] 实现 `FixApplier`，根据全局审查结果定向修正
- [ ] 实现数据修补结果回写机制（ChapterWriter.patch_data）
- [ ] 实现修正验证机制

### Phase 4: ReportOrchestrator 集成（2-3天）

- [ ] 实现 `ReportOrchestrator`，编排完整流程（含审查闭环）
- [ ] 改造 `orchestrator.py`，替换报告生成阶段
- [ ] 实现重试策略（绝不降级到机械组装）
- [ ] 实现执行摘要的特殊处理

### Phase 5: 测试与调优（2-3天）

- [ ] 端到端测试：对比新旧流程的输出质量
- [ ] 闭环验证：测试审查→重写闭环是否有效提升质量
- [ ] Prompt 调优：优化章节撰写、章节审查、全局审查的 Prompt
- [ ] 性能测试：确保耗时在可接受范围内
- [ ] 重试测试：模拟 LLM 失败场景

**总预估工期：12-17天**

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 调用成本增加 | 每份报告多8-15次 LLM 调用 | 审查Agent用小模型；分组并行减少调用次数 |
| 逐章生成耗时增加 | 总耗时增加50-150% | 分组并行；异步执行；进度实时推送 |
| LLM 生成质量不稳定 | 章节内容可能偏离框架 | 独立审查Agent审查+反馈重写闭环；全局审查+修正 |
| 框架信息不完整 | 旧路径无 framework | 自动生成简化框架作为 fallback |
| 数据注册表误报冲突 | 不同指标同名导致假冲突 | 归一化匹配 + 语义相似度过滤 |
| 数据修补搜索无果 | 定向搜索找不到所需数据 | 3次搜索无果则标记为"数据不可获取"，报告中标注缺失 |
| 冲突裁决误判 | 来源权威性判断错误导致规范值选错 | 多来源交叉验证 + LLM裁决时要求给出理由 |
| LLM 服务不可用 | 重试耗尽后任务失败 | 分级重试+指数退避；断点恢复跳过已完成章节；明确告知用户失败原因 |

---

## 10. 预期效果

| 指标 | 当前 | 升级后 |
|------|------|--------|
| 数据一致性 | 无保障，经常矛盾 | DataRegistry 跟踪 + 冲突裁决器（来源权威性+定向验证）+ 全局替换，矛盾率 < 5% |
| 内容重复率 | 10-20% | 前文摘要传递 + 去重审查，重复率 < 3% |
| 逻辑连贯性 | 章节独立，缺乏衔接 | 框架驱动 + 前文上下文，逻辑链清晰 |
| 执行摘要质量 | 拼接前两句 | 基于完整报告综合提炼 |
| 数据缺失率 | 发现缺失无法补充 | DataRepairAgent 定向搜索补充，可修补率 > 70% |
| 整体质量可控性 | 只能发现格式问题 | 自审挡住低级错误 + 独立审查挡住深层问题 + 全局审查 + 定向修正 |
| 质量评分 | 无内容评分 | 多维度量化评分，可追踪可对比 |

---

## 附录A：关键方法实现说明

> **审计修正 A10（中等）**：以下方法在主流程中被调用但未在正文定义，此处补充实现说明。

### A.1 `_serialize_conflicts(data_registry)` — 与 `_serialize_report_for_review` 合并

`_serialize_report_for_review` 已包含冲突摘要部分。`_serialize_conflicts` 不需单独实现，Phase 3 中直接复用：

```python
report_summary = self._serialize_report_for_review(chapters, self._data_registry)
# report_summary 已包含冲突摘要，conflicts_summary 可直接从中提取或留空
conflicts_summary = ""  # 已包含在 report_summary 中
```

### A.2 `verify_issues(issues, chapters)` — 两步审查的 Step 2

```python
async def verify_issues(self, issues: List[ReviewIssue], chapters: List[ChapterWriteOutput]) -> List[ReviewIssue]:
    """对摘要审查发现的问题，读原文确认"""
    verified = []
    for issue in issues:
        # 找到涉及章节的原文
        relevant_content = self._extract_relevant_chapters(issue, chapters)
        
        verification_prompt = f"""
        以下问题是在摘要审查中发现的，请阅读原文确认是否确实存在：
        
        问题：{issue.description}
        位置：{issue.location}
        
        相关章节原文：
        {relevant_content}
        
        请确认：1=确实存在 0=误报。如确认存在，请补充精确的问题描述和修正建议。
        输出JSON：{{"confirmed": true/false, "refined_description": "...", "refined_suggestion": "..."}}
        """
        
        result = await self._llm.generate(verification_prompt)
        parsed = self._parse_verification(result)
        if parsed.get("confirmed"):
            verified.append(ReviewIssue(
                dimension=issue.dimension,
                severity=issue.severity,
                description=parsed.get("refined_description", issue.description),
                location=issue.location,
                evidence=issue.evidence,
            ))
    
    return verified
```

### A.3 `set_canonical_value(metric, value, source)` — DataRegistry 方法

```python
def set_canonical_value(self, metric: str, value: str, source: str) -> None:
    """更新指标的规范值（冲突解决后调用）"""
    key = self._normalize_metric(metric)
    entry = self._metrics.get(key)
    if entry:
        entry.value = value
        entry.source = source
        entry.conflicts = []  # 清除冲突
```

### A.4 `_find_dimension(framework, chapter_id)` — 查找 FrameworkDimension

```python
def _find_dimension(self, framework: ResearchFramework, chapter_id: str) -> FrameworkDimension:
    """按 chapter_id 查找 FrameworkDimension"""
    for dim in framework.dimensions:
        if dim.section_id == chapter_id:
            return dim
    return None
```

### A.5 `_assemble_final_report(chapters, exec_summary, review)` — 组装最终报告

```python
def _assemble_final_report(self, chapters, exec_summary, review) -> Dict[str, Any]:
    """组装最终报告，输出格式与 DocumentGenerationAgent 对接"""
    sections = []
    for ch in chapters:
        sections.append({
            "section_id": ch.chapter_id,
            "title": ch.title,
            "content": ch.content,  # Markdown格式，由 ContentOrchestrator 转HTML
            "data_points": [dp.__dict__ for dp in ch.data_points_used],
            "quality_score": None,  # 可选：单章评分
        })
    
    return {
        "executive_summary": exec_summary,
        "sections": sections,
        "quality": {
            "overall_score": review.overall_score,
            "dimension_scores": review.dimension_scores,
        },
    }
```

---

## 附录B：设计审计修正记录

> 日期：2026-06-26
> 审计报告：`docs/2026-06-26-report-generation-design-audit.md`
> 以下修正已回写到本文档对应章节，此处为汇总索引。

| # | 等级 | 缺陷 | 修正位置 | 修正方式 |
|---|------|------|----------|----------|
| 1 | 致命 | DataRegistry 是 Python 对象，LLM 无法查询 | 3.1 ChapterWriteInput、3.2 ChapterReviewInput、3.3 ReviewInput、3.5 ReportOrchestrator | 将 `data_registry: DataRegistry` 替换为 `used_metrics_summary: str` / `conflicts_summary: str`，由 ReportOrchestrator 序列化后注入 Prompt |
| 2 | 致命 | patch_data 破坏审查结果 | 3.6.3、3.6.4 Phase 4 | patch_data 后对被修改章节重新执行 ChapterReviewAgent 审查；不通过则 Writer 再修一次 |
| 3 | 致命 | GlobalReviewAgent 接收完整报告，token 爆炸 | 3.3 ReviewInput、3.5 Phase 3 | 改为两步审查：Step 1 传入结构化摘要（紧凑），Step 2 对发现的问题读原文验证（局部） |
| 4 | 严重 | data_points_used 由 LLM 自报，不可靠 | 3.1 ChapterWriteOutput | 增加后置提取验证：正则从内容提取数据点 + 与 LLM 自报交叉验证，以正文中实际出现的值为准 |
| 5 | 严重 | preceding_summary 在 patch_data/rewrite 后过期 | 3.6.4 Phase 4 | Phase 4 修补后调用 `_rebuild_preceding_summary()` 重建 + `_verify_downstream_consistency()` 验证后续章节 |
| 6 | 严重 | rewrite 闭环可能导致质量退化 | 3.5 ReportOrchestrator Phase 2 | 增加版本对比保底：保留审查评分最高的版本，而非默认使用最后一次重写版本 |
| 7 | 严重 | 框架 dimensions 与聚合数据的映射未定义 | 3.1 ChapterWriteInput、3.5 ReportOrchestrator | 增加 `section_agent_map` 确定性映射，优先使用确定性映射，fallback 到模糊匹配时记录警告 |
| 8 | 中等 | 来源权威性表不完整，仅覆盖中文 | 3.6.2 ConflictResolver | 扩展为覆盖国际来源（Bloomberg/Reuters/WorldBank等）+ 基于来源描述的规则匹配 |
| 9 | 中等 | Phase 2-3 中间结果无持久化 | 3.5 ReportOrchestrator | 增加检查点机制：每章完成后保存 JSON 检查点，崩溃后从检查点恢复 |

### 第二轮审计修正（2026-06-26）

> 审计报告：`docs/2026-06-26-report-generation-design-audit-round2.md`

| # | 等级 | 缺陷 | 修正位置 | 修正方式 |
|---|------|------|----------|----------|
| A1 | 致命 | _patched标志未设置，修正#2完全失效 | 3.6.3 _apply_data_repairs、3.6.4 Phase 4 | 改为返回 patched_chapter_ids 集合，Phase 4 用ID集合判断 |
| A2 | 致命 | LLM输出未解析为结构化对象 | 3.1 ChapterWriter | 增加 _parse_chapter_output()，所有 {output_schema} 替换为明确JSON格式 |
| A3 | 致命 | 检查点恢复不跳过已完成章节 | 3.5 ReportOrchestrator Phase 2 | 增加 completed_section_ids 集合，循环中跳过已恢复章节 |
| A4 | 致命 | 两版generate_report不一致 | 7.3 重试策略 | 删除独立重试版本，将重试逻辑作为主版本的异常处理扩展 |
| A5 | 严重 | Reviewer Prompt缺used_metrics_summary | 3.2 ChapterReviewAgent Prompt | 在"前文脉络"后增加"已使用的数据指标"部分 |
| A6 | 严重 | ConflictEntry类型不匹配 | 3.4 DataRegistry | register()增加unit参数；get_conflicts()返回List[DataConflict] |
| A7 | 严重 | ConflictEntry.description不存在 | 5.2 执行摘要 | 改用已有字段构造冲突描述字符串 |
| A8 | 严重 | requirement.topic不在作用域 | 3.5 generate_report | 增加topic参数，Phase 4使用参数而非requirement属性 |
| A9 | 中等 | 自审说明仍引用DataRegistry | 3.1 自审说明 | 改为"与已使用的数据指标摘要中的已有值是否明显矛盾" |
| A10 | 中等 | 多个关键方法未定义 | 附录A | 补充 verify_issues、set_canonical_value、_find_dimension、_assemble_final_report 等方法定义 |
| A11 | 中等 | 并行策略未集成主流程 | 3.8 | 标注为"性能优化项"，Phase 2先串行，Phase 5再集成 |
