# Zensers 市场研究报告系统 - 日志分析报告

**分析时间**: 2026-06-20
**日志时间跨度**: 2026-06-19 06:59 ~ 2026-06-20 20:36
**分析日志文件**: `app.log`, `web-out.log`（其他日志文件无 06-19/20 数据）

> 说明：`uvicorn_stderr.log` 最后更新 06-09，`web-error.log` 最后错误 06-02，`zensers.log` 最后更新 05-23，`openresearch.log` 无近期数据。以下分析仅基于 `app.log` 和 `web-out.log`。

---

## 一、系统运行概况

| 指标 | 数值 |
|------|------|
| 日志时间跨度 | 06-19 06:59 ~ 06-20 20:36 (约 37.5 小时) |
| 系统重启/关闭次数 | 21 次 |
| ERROR 总数 | 854 条 |
| WARNING 总数 | ~2,730 条 |
| 前端请求 404 | 16 次 |
| 前端请求 200 | 9 次 |

### 重启时间线

系统在 06-19 当天经历了 **21 次关闭/重启**，时间分布如下：

| 时间段 | 重启次数 | 说明 |
|--------|----------|------|
| 06:59~07:00 | 2 | 清晨启动阶段 |
| 17:40~17:40 | 1 | 下午恢复 |
| 19:04~20:15 | 12 | 修复系统测试（正常） |
| 21:21~22:17 | 4 | 晚间不稳定 |
| 22:17 | 2 | 最后重启后稳定运行至 23:17 |

**关键观察**: 21:21~22:17 的 4 次晚间重启需要关注；19:04~20:15 的 12 次重启为修复系统测试，属正常情况。

---

## 二、发现的问题（按严重程度排序）

### ~~P0~~ 已解决：DeepSeek API 余额不足（06-20）✅

**日志位置**: `app.log` 06-20 20:35~20:36

```
src.api.research_api - WARNING - LLM conversation ValueError, retrying once with lower temp: 
  LLM call failed: Error code: 402 - {'error': {'message': 'Insufficient Balance'...
src.api.research_api - ERROR - LLM conversation retry also failed: 
  LLM call failed: Error code: 402 - {'error': {'message': 'Insufficient Balance'...
```

**详情**: 06-20 20:35 和 20:36 各出现一次 DeepSeek API 402 余额不足错误，重试后仍然失败。

**状态**: ✅ 已解决（余额已充值）。

**遗留建议**: 虽已解决，但暴露了单点故障风险，仍建议：
- 增加余额不足的告警机制（如余额低于阈值时通知）
- 实现多 LLM 提供商 fallback（如 OpenAI/Anthropic 作为备用）

---

### P0 - 严重：对话 Agent 的设计失衡——过度约束导致无法处理隐含意图

**涉及代码**:
- 对话路由 prompt：`src/api/research_api.py:884`
- 修订意图分析 prompt：`src/core/intent/revision_intent_analyzer.py:17-61`
- 修订意图 regex fallback：`src/core/intent/revision_intent_analyzer.py:147-161`
- 修订执行器意图处理：`src/core/adjustment/revision_executor.py:130-186`
- 空意图处理：`src/core/adjustment/revision_executor.py:399-404`
- 智能路由（未被修订管道复用）：`src/core/semantic_intent.py:185` `SemanticIntentAnalyzer`
- 修订意图映射器（同样只有关键词匹配）：`src/core/adjustment/revision_intent_mapper.py:63`

**现象**: 用户问 "为什么整体评分只有52.4"，系统返回 "未能理解您的修订意图"。

**完整调用链分析**:

```
用户: "为什么整体评分只有52.4"
  ↓
[第1层] 对话 LLM (ResearchAPI._process_conversation)
  → action: revise_report  ← 路由正确（用户不满隐含改进需求），但传递了原始消息
  ↓
[第2层] 修订意图 LLM (RevisionIntentAnalyzer.analyze)
  → intents: []  ← 无法从"为什么评分低"推理出"改进低分章节"的修改意图
  ↓ fallback
[第2.5层] Regex fallback (INTENT_TO_REVISION_MAP_V2)
  → matched: UNKNOWN  ← 只匹配显式动词(修改/删除/添加)
  ↓
[第3层] _handle_empty_intents → CLARIFICATION_FAILED
  → "未能理解您的修订意图"
```

> 注：第1层路由到 `revise_report` 实际上是合理的——用户对评分不满，隐含着改进需求。问题出在第2层：修订管道收到了请求，却无法从 "为什么评分低" 推理出具体的修改意图。

**根因：不是 LLM 推理能力不足，是 prompt 人为限制了 LLM 的推理空间**

系统中有 **3 个独立的 LLM 调用**，每个都被 prompt 约束在窄框内，无法发挥推理能力：

**问题 1：对话路由 prompt 的约束写反了**

`research_api.py:884` 的 `post_research_hint` 相关摘录：
```
DO NOT trigger revise_report if:
- The user is asking ABOUT the revision/modification feature itself
- The user is reporting a bug, issue, or problem with the report generation
- The user mentions functionality is 'broken', 'not working', '有问题', '不工作'
- The user is analyzing or evaluating the report output, not requesting changes
These should use `continue_chat` instead.
```

这条规则的本意是避免误触发修订，但它过于粗暴——把 "用户对报告质量的质疑/不满" 和 "纯粹的评估性提问" 混为一谈。当多条否定规则并存时，LLM 倾向于遵守保守路径，导致模糊意图被推向 `continue_chat`。不过，在本案例中，对话 LLM 实际上把 "为什么评分只有52.4" 路由到了 `revise_report`——路由本身是正确的。真正的问题在于 **修订管道收到了请求，却无法从隐含意图推理出具体修改操作**。

**问题 2：修订意图分析 prompt 完全没有隐含意图推理引导**

`revision_intent_analyzer.py:17-54` 的 `_REVISION_SYSTEM_PROMPT`:
```
You are a revision intent analyzer for a research report system.
Analyze the user's revision request and output a structured JSON...
Available revision operations:
- modify: change existing content
- delete: remove a section
- add: insert new content
...
```

这个 prompt 只告诉 LLM "识别显式操作类型"，完全没有引导 LLM 推理隐含意图。LLM 的推理能力（从 "为什么评分低" 推导出 "用户不满意→要改进低分章节"）被 prompt 的字面框架锁死了。

更深层的问题：`RevisionIntentAnalyzer` 的 JSON schema（`revision_intent_analyzer.py:64-144`）定义了 `is_global_feedback` 和 `is_uncertain` 字段，暗示设计者考虑到了全局反馈场景。但 **prompt 中完全没有告诉 LLM 如何使用这些字段**——当用户表达全局不满时，应该设置 `is_global_feedback=true` 并推断改进意图，而不是返回空 intents。

**问题 3：regex fallback 是硬编码的狭义匹配**

`revision_intent_analyzer.py:147-161` 的 `INTENT_TO_REVISION_MAP_V2`:
```python
r"修改|改写|更改|更新|修正|调整|润色|优化|补充|modify|update|change|revise|edit|rewrite|polish": MODIFY,
r"删除|移除|去掉|...": DELETE,
```

这个 fallback 只能匹配显式动词。当 LLM 也失败时，系统彻底丧失了对隐含意图的理解能力。但实际上 LLM 很少真正失败——更多时候是 prompt 没有引导它去推理。

**问题 4：系统中已有隐含意图推理能力，但修订管道完全没有复用**

`SemanticIntentAnalyzer`（`semantic_intent.py:185`）已经具备 `hidden_requirements` 推理能力——它能从用户输入中提取隐含需求。`DeepIntentResult` 的 `hidden_requirements` 字段（`semantic_intent.py:45`）在研究管道中被广泛使用（`orchestrator.py:3507`, `generic_agent.py:2571`）。

但 **修订管道完全没有调用 `SemanticIntentAnalyzer`**。`RevisionIntentAnalyzer` 是一个独立的、能力远弱于 `SemanticIntentAnalyzer` 的组件，它没有隐含意图推理能力，也没有复用系统中已有的能力。

更具体地说，`_handle_unknown_intent`（`revision_executor.py:406-434`）在意图分析完全失败时会调用 `IntelligentRoutingAdapter` 进行全量研究路由，但这是 "放弃修订→重做研究" 的降级路径，不是 "推理隐含意图→精确修订" 的正确路径。两个完全不同的语义被混在了同一个 fallback 里。

**问题 5：`RevisionIntentMapper` 也是纯关键词匹配**

`revision_intent_mapper.py:82-125` 的 `INTENT_TO_REVISION_MAP` 仍然是关键词映射：
```python
IntentType.FIX: {
    "keywords": {
        r"错别字|错字|拼写|措辞|表达": RevisionIntentType.CORRECT_ERROR,
        r"重写|改写|重新写": RevisionIntentType.REWRITE_TEXT,
        ...
    },
    "default": RevisionIntentType.CORRECT_ERROR,
},
```

整个修订管道从上到下都是关键词/显式匹配，没有任何一层具备语义推理能力。

**本质问题：对话 Agent 的设计边界失衡**

系统的多 Agent 架构（对话 Agent → 修订 Agent → 研究 Agent）是为了让各 Agent 专注各自领域，避免单个 Agent 承担全部职责。但当前设计的问题是：

| 维度 | 当前状态 | 问题 |
|------|----------|------|
| **灵活性** | 不足 | 对话 Agent 只做路由分类，不允许推理用户深层意图 |
| **边界** | 过度 | 修订管道只认显式操作词，无法从隐含意图推理出具体修改操作 |
| **LLM 能力利用** | 严重浪费 | LLM 本身具备从上下文推理隐含意图的能力，但 prompt 没有引导其发挥 |
| **能力复用** | 断裂 | 研究管道有 `hidden_requirements`，修订管道完全没有复用 |

理想的设计应该是：**对话 Agent 既要守边界（不越权执行具体任务），又要足够灵活（能推理隐含意图并正确路由）**。边界不是用 DO NOT 列表来硬性约束，而是通过引导 LLM 推理来柔性实现——LLM 理解了 "用户为什么这么说"，自然就能做出正确的路由决策。

**具体修复建议**（均为 prompt 调整，零代码逻辑变更）：

1. **对话路由 prompt**：将 DO NOT 规则改为引导推理（防止其他场景下保守误判）：
   > "If the user questions or complains about report quality (e.g. '为什么评分低', '这个章节写得不好'), this implies dissatisfaction and desire to improve. Route to `revise_report` with `adjustment` = the user's original message. Only use `continue_chat` for purely informational questions unrelated to the report."

2. **修订意图分析 prompt**：增加隐含意图推理引导，并激活 `is_global_feedback` 字段：
   > "IMPORTANT: Users often express revision needs implicitly. If the user questions report quality, expresses dissatisfaction, or asks why something is poor, infer the implicit intent to improve/modify the relevant sections. Set `is_global_feedback` to true if the user's feedback applies to the report as a whole. Do NOT return empty intents for such requests — instead, map them to appropriate revision operations (e.g. 'modify' for the relevant sections with `is_global_feedback`=true)."

3. **Regex fallback**：增加一条隐含意图模式：
   ```python
   r"为什么|怎么|如何.*低|不好|不够|不足|差|弱|why|how.*poor|weak|low|bad": RevisionOpType.MODIFY,
   ```

4. **架构优化（中期）**：在修订管道中复用 `SemanticIntentAnalyzer`，让 `hidden_requirements` 能力延伸到修订场景。具体方案：在 `RevisionIntentAnalyzer.analyze` 中，当 LLM 返回空 intents 时，调用 `SemanticIntentAnalyzer.analyze_async` 提取 `hidden_requirements`，再映射到修订操作。

---

### P0 - 严重：26个子章节"数据不足"占位，系统未触发补充数据采集

**涉及代码**:
- 子章节内容匹配：`src/core/orchestrator/aggregation/result_aggregator.py:1537-1584` `_match_content_to_sub_section`
- 子章节骨架构建：`src/core/orchestrator/aggregation/result_aggregator.py:1587-1613` `_build_subsections_from_skeleton`
- 章节级内容缺失占位：`src/core/orchestrator/aggregation/result_aggregator.py:446-453`, `609-616`
- 知识缺口检测：`src/core/agents/generic_agent.py:2156-2180` `_detect_knowledge_gaps`
- 补充搜索入口：`src/core/agents/generic_agent.py:2254` `_supplementary_search_for_gaps`
- 补充查询生成：`src/core/agents/generic_agent.py:2711-2818` `_generate_supplementary_queries`
- 质量反馈补充触发：`src/core/quality/feedback_executor.py:73`, `182-276`

**现象**: 生成的报告中，8个章节下的 **26个子章节** 全部输出 "本章节数据不足，无法生成完整分析。请检查上游数据采集是否完整。" 占位符。这些子章节涵盖核心财务数据（营收、净利润、毛利率、ROE、EPS、现金流等），本应从公开财务报表中直接获取。

**具体受影响子章节**（以 `research_24c2875c.html` 为例）：

| 章节 | 空子章节数 | 缺失的关键数据 |
|------|-----------|---------------|
| 核心财务指标与盈利能力 | 3 | 营业收入及增长率、净利润及增长率、毛利率/净利率 |
| 研发与创新投入 | 3 | 研发费用及占比、专利数量、研发效率 |
| 供应链成本效率 | 3 | 原材料成本、垂直整合、成本控制措施 |
| 销量与市场份额 | 3 | 月度销量趋势、市场份额、订单与产能 |
| 国际化与出口 | 3 | 出口销量及收入、海外工厂、关税风险 |
| 财务健康与风险评估 | 4 | 偿债能力、现金流、季度波动、风险因素 |
| 行业对标与竞争格局 | 3 | 竞争对手、指标对比、优劣势 |
| 财务预测 | 4 | 收入预测、利润预测、估值、敏感性分析 |

**根因分析：数据采集管道存在三层断裂**

**断裂 1：子章节内容匹配逻辑过于严格，LLM 输出与骨架标题对不上**

`_build_subsections_from_skeleton`（L1587-1613）的工作方式是：对每个 framework 定义的 sub_section，调用 `_match_content_to_sub_section` 在 LLM 输出中搜索匹配的 `###` 标题。

`_match_content_to_sub_section`（L1537-1584）的匹配逻辑：
1. 将 sub_section name 归一化
2. 在 LLM 输出中逐行搜索 `###` 或 `####` 标题
3. 对标题文本做归一化后，检查是否包含 sub_section name
4. 如果找到匹配标题，提取该标题到下一个同级标题之间的内容
5. **如果没找到，直接返回占位符**（L1584）

问题在于：LLM 生成的 `###` 标题措辞与 framework 骨架定义的 sub_section name 不完全一致时（如 LLM 写 "### 1.1.1 营业收入增长" 而骨架定义 "营业收入及增长率"），匹配失败，直接降级为占位符。**没有任何模糊匹配或 LLM 语义匹配的兜底**。

**断裂 2：占位符产生后，系统没有任何机制触发补充数据采集**

当 `_match_content_to_sub_section` 返回占位符后，`_build_subsections_from_skeleton` 直接将占位符作为子章节内容返回（L1607），**没有任何后续流程检测到这个占位符并触发补充搜索**。

系统中确实存在补充搜索能力：
- `generic_agent.py:2156-2180` 的 `_detect_knowledge_gaps` 能检测 "insufficient quantitative data"
- `generic_agent.py:2254` 的 `_supplementary_search_for_gaps` 能执行针对性补充搜索
- `feedback_executor.py:182-276` 的质量反馈能触发补充查询

但这些能力都只在 **agent 执行阶段**（生成内容时）生效。一旦内容生成完成，进入 `result_aggregator` 的聚合阶段，如果匹配失败产生占位符，**没有任何机制回溯到 agent 阶段重新采集**。聚合器是单向的——它只做"匹配→组装"，不做"缺失→补采"。

**断裂 3：系统已有 akshare 结构化数据能力，但调用链完全断裂——无法识别上市公司，无法查到股票代码**

系统中已安装 akshare 库（v1.18.57），且 `src/skills/analysis/stock_data.py` 实现了 `StockDataSkill` 类，能通过 akshare 获取利润表、资产负债表、现金流量表、核心财务指标。`generic_agent.py:1417-1457` 也有 `_fetch_structured_data` 方法，会在 `agent_category == "research"` 且 `"stock_data" in available_skills` 时调用该能力。

但 **06-19/20 的日志中，stock_data / akshare 相关记录为零**——系统从未调用过这个能力。

根因不是"映射表缺一条"，而是 **系统完全没有"识别上市公司→查股票代码→获取结构化数据"的闭环能力**：

1. **`_extract_stock_symbol` 只做正则提取中文，无法解析公司名到股票代码**（L1459-1464）：
   ```python
   m = re.search(r'[\u4e00-\u9fff]+', topic)
   return m.group(0) if m else ""
   ```
   传入 "比亚迪财务分析"，提取出 "比亚迪" 作为 symbol。但 akshare 的所有接口都需要数字股票代码（如 "002594"），传入中文名会直接失败。

2. **系统有识别上市公司的能力但未与数据获取链路对接**：`strategies.py:172-177` 的 `_is_listed_company_topic` 已经能识别 "比亚迪" 等公司名，`strategies.py:180-189` 的 `derive_data_source_type` 也知道财务数据应标记为 "structured" 或 "both"。但这些信息 **只用于决定搜索策略，从未用于触发 stock_data skill**。

3. **缺少公司名→股票代码的解析能力**：akshare 本身提供了 `stock_zh_a_spot_em()` 接口，可以通过公司名搜索股票代码。但系统从未调用过这个接口来做名称解析。agent 在搜集信息时搜索了"比亚迪 营收"、"比亚迪 净利润"等关键词，完全有机会从搜索结果中发现"比亚迪（002594.SZ）"并提取代码，但没有任何逻辑做这件事。

4. **skill_registry 传递链可能断裂**：`orchestrator.py:283` 注册了 `StockDataSkill`，但需要确认 skill_registry 是否被正确传递到每个 research agent。即使传递了，由于 `_extract_stock_symbol` 返回中文名，`StockDataSkill.execute` 收到 `symbol="比亚迪"` 后，`ak.stock_profit_sheet_by_report_em(symbol="比亚迪")` 会抛出异常，被 `_fetch_structured_data` 的 try-except 静默吞掉（L319-320），agent 无感知地退回搜索引擎路径。

**本质问题：系统能"知道"这是上市公司，能"知道"财务数据应该用结构化源，但"做不到"从公司名到股票代码的解析——这是能力链条上缺失的关键一环。**

这不是加一条映射表就能解决的。即使加上"比亚迪→002594"，下一个公司（如"蔚来"、"小鹏"）怎么办？正确的做法是：**当 `_is_listed_company_topic` 识别到上市公司时，先通过 akshare 的股票搜索接口解析公司名到代码，再调用结构化数据接口获取财务数据**。

**此外，聚合阶段也缺乏数据质量的守门能力**

当前系统的数据流是单向的：
```
搜索 → 爬取 → LLM 分析 → 聚合匹配 → 组装报告
                                    ↑
                              匹配失败 → 占位符（无回溯）
```

理想的数据流应该是带反馈的：
```
搜索 → 爬取 → LLM 分析 → 聚合匹配 → 组装报告
                                    ↑
                              匹配失败 → 检测缺失 → 触发补充搜索 → 重新匹配
```

**具体修复建议**：

短期（修复 stock_data 调用链——公司名→股票代码解析）：
1. **重写 `_extract_stock_symbol`**：当 `_is_listed_company_topic(topic)` 为 True 时，调用 akshare 的 `stock_zh_a_spot_em()` 接口，通过公司名模糊匹配搜索股票代码。例如：topic="比亚迪" → 遍历 `stock_zh_a_spot_em()` 返回的名称列，匹配 "比亚迪" → 得到 "002594"
2. **增加 `_fetch_structured_data` 的日志**：在入口记录 symbol 解析结果、akshare 调用结果，不再让异常被静默吞掉
3. **确认 skill_registry 传递**：在 orchestrator 创建 agent 时，确认 stock_data 被注册到 skill_registry 且 available_skills 包含 "stock_data"

短期（聚合器增加缺失检测 + 补充触发）：
4. 在 `_build_subsections_from_skeleton` 中，统计匹配失败的子章节数量，如果超过阈值（如 >30%），记录缺失清单并触发事件
5. 在聚合完成后，如果检测到占位符子章节，向 orchestrator 发出补充数据请求，指定缺失的具体子章节和数据类型
6. orchestrator 接收补充请求后，为缺失子章节生成针对性的搜索查询（如 "比亚迪 2025年 营业收入 净利润 年报"），执行搜索并重新生成内容

中期（匹配逻辑增强）：
7. 在 `_match_content_to_sub_section` 中增加模糊匹配（如编辑距离 < 3 的标题视为匹配）
8. 当精确匹配和模糊匹配都失败时，调用 LLM 做语义匹配（将 sub_section name 和所有 `###` 标题交给 LLM，让 LLM 判断对应关系）

中期（数据源策略优化）：
9. 在 agent prompt 中优先注入 akshare 获取的结构化数据作为 "已知事实"，搜索引擎仅补充 akshare 无法覆盖的数据
10. 对财务类子章节（营收、利润、ROE 等），在搜索查询中增加 "年报" "季报" "财报" 等关键词，提高搜索结果质量

---

### ~~P0~~ 非问题：系统频繁重启（06-19 19:04~20:15）— 修复系统测试，属正常情况

**日志位置**: `app.log` 多处 shutdown/recovery 日志

**详情**: 系统在 71 分钟内重启 12 次，每次都伴随：
```
src.api.main - WARNING - Failed to cancel ResearchAPI background tasks: 
  type object 'ResearchAPI' has no attribute '_background_tasks'
```

**状态**: 19:04~20:15 的频繁重启为修复系统测试的正常行为，不构成故障。

**遗留问题**: 每次重启都因 `_background_tasks` 属性缺失而清理失败，虽然不构成重启循环的根因，但仍存在资源泄漏风险：
- 清理失败可能导致后台任务继续运行，占用资源
- 21:21~22:17 的 4 次晚间不稳定重启可能与资源泄漏有关（待确认）

**建议**:
- 修复 `ResearchAPI._background_tasks` 属性缺失问题
- 在 shutdown 流程中增加异常隔离，避免单个清理失败影响后续启动

---

### P1 - 严重：asyncio 任务异常未回收（852 次）

**日志位置**: `app.log` 06-19 22:20~22:52（集中爆发）

```
asyncio - ERROR - Task exception was never retrieved
```

**详情**: 852 条 "Task exception was never retrieved" 错误，集中在 22:20~22:52 约 32 分钟内爆发。与系统执行大规模并行研究任务（8 个 phase_1 agent 同时工作）的时间吻合。

**影响**:
- 异步任务异常被静默吞掉，无法追踪具体失败原因
- 可能导致研究任务部分失败但无法感知
- 内存/连接资源泄漏风险

**根因**: 大量 agent 并发启动后，httpx 异步客户端和搜索任务异常未被正确捕获和处理。

**建议**:
- 为所有 `asyncio.create_task()` 调用添加 done callback 处理异常
- 使用 `asyncio.gather(..., return_exceptions=True)` 替代裸 task 创建
- 增加 `asyncio` 未处理异常的全局处理器

---

### P1 - 严重：CR-FIX-2 磁盘恢复失败（3 次）

**日志位置**: `app.log` 06-19 22:20, 23:07, 23:15

```
src.core.orchestrator.execution.engine - WARNING - CR-FIX-2 disk recovery failed: 
  'str' object has no attribute 'exists'
```

**详情**: 磁盘恢复逻辑期望接收 `Path` 对象，但实际收到 `str`，导致调用 `.exists()` 方法失败。在三次不同的研究任务中均出现。

**影响**: 研究任务的中间结果无法从磁盘恢复，可能导致任务重启后丢失进度。

**根因**: 代码类型不一致——调用处传入字符串，但恢复逻辑期望 Path 对象。

**建议**: 在恢复逻辑入口处增加 `Path()` 转换，确保类型安全。

---

### P2 - 中等：质量检查持续低分（3 次），整体评分仅 52.4

**日志位置**: `app.log` 06-19 22:34, 23:07, 23:15

```
Quality check failed for batch 1: score=26.9/75.0
Quality check failed for batch 2: score=39.3/75.0
Quality check failed for batch 3: score=10.0/75.0
```

**详情**: 三个 batch 的质量分数分别为 26.9、39.3、10.0（满分 75），均未达标。重试后仍失败，最终 `Unified retry exhausted`，系统继续运行但输出了低质量内容。

**实际报告评分证据**（用户反馈）：
- 整体评分：**52.4 / 100**（不及格）
- 各章节评分：财务预测 60（最低）、国际化与出口 65、供应链成本效率 72、财务健康/风险评估 70、研发与创新 78、行业对标 82、核心财务指标 85、销量与市场份额 88
- 五维度评估：
  - 完整性（25满分）：约 10-12 分
  - 准确性（25满分）：约 15-18 分
  - **分析深度（25满分）：约 10-13 分** ← 最低
  - **逻辑一致性（15满分）：约 5-7 分** ← 最低
  - 写作质量（10满分）：约 6-7 分

**根因分析：Agent prompt 缺乏跨章节因果链分析的引导 + 质量检查机制本身也不检查跨章节一致性**

**1. Agent prompt 缺失跨章节引导**

分析 `generic_agent.py:3200-3273` 的 `_get_professional_role_prompt` 方法，agent 的 prompt 构建流程是：
1. 加载角色 profile（如"资深研究分析师"）
2. 拼接 output_spec（输出格式规范）
3. 拼接语言指令
4. 拼接知识富化（entities/patterns/methodologies）
5. 拼接质量反馈（重试时）

**关键缺失**：没有任何地方引导 agent 进行跨章节因果链分析。每个 agent 只被告知 "你是一个XX专家，分析XX维度"，但从未被引导思考 "你的分析与其他章节如何关联"。这正是分析深度（10-13/25）和逻辑一致性（5-7/15）两个维度严重低分的根源。

LLM 完全具备跨章节因果推理能力，但 prompt 只给了它 "聚焦单维度" 的指令，没有给它 "思考关联" 的空间——与修订意图分析的问题同出一辙：**不是 LLM 能力不足，是 prompt 没有释放 LLM 的推理能力**。

**2. 质量检查 Agent 本身也不检查跨章节一致性**

`quality_check_agent.py:634-664` 的 `_check_consistency` 方法实现极其简陋：

```python
def _check_consistency(self, report: Dict) -> Dict[str, Any]:
    """Check logical consistency."""
    # Check data reference consistency
    data_refs = re.findall(r'(\d+(?:\.\d+)?)\s*billion', content)
    if len(data_refs) > 1:
        values = [float(v) for v in data_refs]
        if max(values) > min(values) * 1000:  # Difference over 1000x
            issues.append(...)
```

这个一致性检查只做了 "billion 单位数值差异超过 1000 倍" 这一个检查——这根本不是逻辑一致性检查，只是数值异常检测。真正的逻辑一致性应该是：同一公司在不同章节的财务数据是否一致、市场规模假设与增长率假设是否自洽、竞争格局的结论是否与财务分析矛盾。

但当前的质量检查是基于 **regex 模式匹配**（`SECTION_ELEMENT_REQUIREMENTS` 定义了 10 种章节类型的要素检查，全部是 regex pattern），没有任何语义层面的跨章节一致性检查能力。

这是一个更深层的架构问题：**质量检查 Agent 的设计理念是 "模式匹配"，而不是 "语义推理"**。它用 regex 检查每个章节是否包含 "增长率"、"CAGR" 等关键词，但无法判断这些数据是否自洽。

**建议**:

短期（prompt 调整）：
- 在 agent prompt 中增加跨章节因果链引导段，例如：
  > "在分析本维度时，必须思考你的结论如何与其他维度关联。例如：如果你分析'研发投入'，需要说明研发投入如何影响'财务预测'的营收增长假设；如果你分析'供应链成本'，需要解释降本如何传导至'核心财务指标'的利润率。在每个分析段落结尾，用1-2句话说明与其他章节的因果联系。"
- 在质量反馈中明确指出跨章节联动不足的问题，让重试时有针对性改进

中期（架构优化）：
- 在 `_check_consistency` 中引入 LLM 语义一致性检查：将各章节的核心数据和结论提取出来，让 LLM 判断是否存在矛盾
- 在质量检查的 `section_quality` 评估中增加 "跨章节因果链" 维度
- 对重试耗尽的情况增加人工审核标记

---

### P2 - 中等：数据边界控制器匹配失败（61 次）

**日志位置**: `app.log` 06-19 22:20~23:17

```
src.core.orchestrator.execution.data_boundary_controller - WARNING - 
  [create_boundary] phase_1_agent_X 未找到对应进度 'section_Y_...' 的 research agent
```

**详情**: 所有 8 个 phase_1 agent 在创建数据边界时都找不到对应的 research agent，说明 agent 名称/节名称匹配逻辑存在问题。中文节名在日志中显示为乱码（Windows 编码问题），但匹配逻辑本身也可能存在编码/格式不一致。

**影响**: 数据边界控制失效，agent 之间可能无法正确传递研究成果，降低报告质量。

**建议**:
- 检查 agent 名称与 section 名称的映射逻辑
- 统一使用 UTF-8 编码处理中文节名
- 增加 debug 级别的匹配过程日志

---

### P2 - 中等：搜索引擎大面积失败（403 次 DDGS 错误）

**日志位置**: `app.log` 06-19 22:37~22:50

```
ddgs.ddgs - INFO - Error in engine brave: DDGSException("ConnectError...")
ddgs.ddgs - INFO - Error in engine grokipedia: DDGSException("ConnectError...")
```

**详情**: 06-19 22:37~22:50 期间，DuckDuckGo 搜索库的 brave、grokipedia 等引擎大面积连接失败，共计 403 条错误日志。主要集中在 22:37 和 22:49 两个时间段。

**影响**: 搜索结果大幅减少，依赖搜索的研究任务数据不足。

**根因**: 网络不稳定或搜索引擎反爬限制，高并发加剧了问题。

**建议**:
- 增加搜索引擎请求间隔和重试策略
- 实现搜索引擎健康度监控和自动降级
- 考虑备用搜索 API

---

### P2 - 中等：Scrapling 废弃 API 警告（2,578 次）

**日志位置**: `app.log` 06-19 22:20~22:55

```
scrapling - WARNING - This logic is deprecated now, and have no effect; 
  It will be removed with v0.3. Use `AsyncFetcher.configure()` instead before fetching
```

**详情**: scrapling 库的旧 API 调用方式已废弃，每次爬取都产生此警告，共计 2,578 次，占所有 WARNING 的绝大多数。

**影响**: 大量无意义警告污染日志，掩盖真正的问题；v0.3 后当前代码将完全失效。

**建议**:
- 将 `Fetcher` 调用改为 `AsyncFetcher.configure()` 方式
- 这是代码技术债，应在 scrapling v0.3 发布前修复

---

### P2 - 中等：Scrapling 爬取连接重置（1 次 ERROR）

**日志位置**: `app.log` 06-19 22:57

```
scrapling - ERROR - Failed after 3 attempts: Failed to perform, 
  curl: (35) Recv failure: Connection was reset.
```

**详情**: 爬取目标网站连接被重置，3 次重试均失败。

**影响**: 单个网页爬取失败，但系统有容错机制。

---

### P2 - 中等：日期幻觉检测（25 次）

**日志位置**: `app.log` 06-19 23:08~23:12

```
GenericAgent phase_2_agent_6: DATE HALLUCATION – year '2028' > current year '2026'. 
  Auto-corrected to '2026'.
GenericAgent phase_2_agent_4: DATE CHECK – year '2023' is >= 2 years old. 
  Verify data freshness.
```

**详情**: LLM 生成了未来日期（2027/2028）和过旧日期（2023），系统自动纠正了未来日期并标记了过旧日期。

**根因**: Agent prompt 中虽已有 `current_date` 和 `current_year` 注入（`generic_agent.py:3203-3205`），但没有明确约束 "不得生成超过当前日期的预测"，LLM 在推理未来趋势时自然倾向于编造时间线。同样是一个 **prompt 约束不足** 的问题。

**建议**:
- 在 agent prompt 中增加更强的日期约束，例如："当需要预测未来时，使用'预计'、'有望'等措辞，不要编造具体未来年份的确定数据"
- 增加更严格的日期验证（如不允许超过当前月份）

---

### P2 - 中等：LLM JSON 解析失败（1 次）

**日志位置**: `app.log` 06-19 17:45

```
src.api.research_api - ERROR - LLM JSON parse failed (iteration 0): 
  Expecting ',' delimiter: line 28 column 71 (char 2890)
```

**详情**: LLM 返回的 JSON 缺少逗号分隔符，首次解析失败（iteration 0），后续可能有重试成功。

**影响**: 短暂影响，但有重试机制兜底。

**建议**: 当前重试机制已足够覆盖偶发解析失败；如频率上升，可考虑在 prompt 中更强调 JSON 格式严格性，或增加 JSON 修复逻辑（如自动补全缺失逗号）。

---

### P2 - 中等：LLM 意图分析降级（1 次）

**日志位置**: `app.log` 06-19 22:20

```
src.core.semantic_intent - WARNING - LLM intent analysis failed: 
  Failed to parse LLM JSON after all recovery attempts: : line 1 column 1 (char 0)
src.core.semantic_intent - INFO - Falling back to keyword matching
src.core.intelligent_routing_adapter - INFO - [Intent] Primary: research, Confidence: 0.50
```

**详情**: DeepSeek API 返回 400 Bad Request 后，LLM 意图分析失败，降级为关键词匹配，置信度仅 0.50。

**影响**: 意图识别准确度下降，可能导致任务路由到非最优路径。

**建议**: 当 LLM 意图分析降级时，在日志中记录降级事件并标记受影响的任务，便于事后评估降级对结果的影响。

---

### P2 - 中等：Heartbeat 心跳超时（多次）

**日志位置**: `app.log` 06-19 22:23, 22:41, 22:59

```
Task task_c765f169 heartbeat stale: 141.9s since last, missed=1
```

**详情**: 多个任务心跳超时（141.9 秒未更新），说明 agent 执行时间过长或卡住。

**影响**: 可能触发任务超时中断或质量下降。

**建议**: 
- 优化 agent 执行效率，或调整心跳超时阈值
- 在心跳超时时记录 agent 当前执行阶段，便于定位卡住原因

---

### P3 - 低：Charts 图片 404（16 次）

**日志位置**: `web-out.log` 06-20 05:55

```
GET /charts/hbar_2160_14.png 404 in 186ms
GET /charts/bar_2160_13.png 404 in 189ms
GET /charts/bar_2524_12.png 404 in 273ms
...
```

**详情**: 06-20 05:55 前端请求多个图表 PNG 文件，均返回 404。可能图表尚未生成或文件已被清理。

**影响**: 用户无法查看图表，影响报告阅读体验。

**建议**: 检查图表生成流程，确保文件持久化或前端增加加载状态提示。

---

### P3 - 低：ResearchAPI 后台任务清理失败（21 次）

**日志位置**: `app.log` 每次 shutdown

```
src.api.main - WARNING - Failed to cancel ResearchAPI background tasks: 
  type object 'ResearchAPI' has no attribute '_background_tasks'
```

**详情**: 每次系统关闭都出现此警告，21 次重启即 21 次警告。`ResearchAPI` 类缺少 `_background_tasks` 类属性。

**影响**: 后台任务可能未被正确取消，存在资源泄漏风险。

**建议**: 在 `ResearchAPI` 类中正确定义 `_background_tasks` 属性，或修改清理逻辑。

---

### P3 - 低：Harness 约束检查失败（4 次）

**日志位置**: `app.log` 06-19 23:15~23:17

```
src.core.orchestrator.execution.engine - WARNING - Harness constraint check failed
```

**详情**: 研究任务的约束检查失败，与质量检查低分相关联。

**影响**: 低质量输出通过了约束检查，可能输出不符合预期的报告。

---

## 三、问题时间线

```
06-19 06:59  系统启动，Session recovery: 5 preloaded, 154 deferred
06-19 07:00  第2次重启
06-19 17:40  下午恢复启动
06-19 17:45  LLM JSON 解析失败（1次）
06-19 19:04~20:15  修复系统测试（12次重启，正常）
06-19 21:21~22:17  晚间不稳定（4次重启，需关注）
06-19 22:20  大规模研究任务启动，8 agent 并行
06-19 22:20  磁盘恢复失败、数据边界匹配失败、意图分析降级
06-19 22:20~22:52  asyncio 任务异常大爆发（852次）
06-19 22:20~22:55  scrapling 废弃警告（2,578次）
06-19 22:23~22:59  心跳超时（多任务）
06-19 22:34  质量检查 batch1 失败（26.9/75）
06-19 22:37~22:50  搜索引擎大面积失败（403次 DDGS 错误）
06-19 22:57  Scrapling 爬取连接重置
06-19 23:07  磁盘恢复失败 + 质量 batch1 重试耗尽
06-19 23:08  日期幻觉检测（25次）
06-19 23:08  质量 batch2 失败（39.3/75）
06-19 23:15  质量 batch3 失败（10.0/75）+ 磁盘恢复失败
06-19 23:17  系统最终稳定（最后日志时间）
06-19 23:17 ~ 06-20 05:54  系统稳定运行（无异常日志）
06-20 05:55  前端 Charts 图片 404（16次）
06-20 20:35~20:36  DeepSeek API 余额不足（402）← 已解决
```

---

## 四、核心问题总结：Prompt 约束不足是贯穿系统的系统性问题

### 1. LLM 的推理能力被 prompt 人为锁死，而非 LLM 本身能力不足

本报告发现的多个问题，表面看是不同模块的 bug，实质上共享同一个根因：**系统没有充分利用 LLM 的推理能力，而是用硬编码规则和窄 prompt 把 LLM 限制在字面理解的层面**。

| 问题 | 表面现象 | 真实根因 |
|------|----------|----------|
| 修订意图识别失败 | "无法理解修订意图" | Prompt 只要求识别显式操作词，没引导推理隐含意图；JSON schema 有 `is_global_feedback` 但 prompt 未引导使用 |
| 对话路由正确但修订管道无法处理 | "为什么评分低" 路由到 revise_report 后返回"无法理解" | 修订管道的 prompt 只要求识别显式操作词，无法从隐含意图推理出修改操作；对话路由的 DO NOT 规则也有保守倾向，但非本案例的直接原因 |
| 26个子章节数据不足占位 | 报告大量"本章节数据不足"占位符 | `_extract_stock_symbol` 无法解析公司名到股票代码，akshare 从未调用；聚合器匹配过严无回溯；数据采集 100% 依赖搜索引擎 |
| 报告分析深度不足 | 分析深度 10-13/25，逻辑一致性 5-7/15 | Agent prompt 只引导聚焦单维度，没引导跨章节因果链推理 |
| 质量检查无法发现一致性问题 | `_check_consistency` 只检查 billion 数值 | 质量检查 Agent 基于 regex 模式匹配，无语义推理能力 |
| 日期幻觉 | LLM 编造 2027/2028 年数据 | Prompt 虽注入了当前日期，但没明确约束 "不得编造未来确定数据" |

**关键洞察**：LLM 本身具备从上下文推理隐含意图、建立因果链、理解日期边界的能力。当前系统的问题不是 "LLM 做不到"，而是 "prompt 没有告诉 LLM 去做"。而数据不足占位符的问题更深层——不是 LLM 做不到，是 **系统的数据流是单向的，没有反馈回路**，以及 **系统不区分"需要搜索的信息"和"可以直接查询的结构化数据"**。

### 2. 对话 Agent 的设计边界需要重新平衡

系统的多 Agent 架构（对话 Agent → 修订 Agent → 研究 Agent）是正确的——让各 Agent 专注各自领域，避免单个 Agent 承担全部职责。但当前边界划得过窄：

**当前**：对话 Agent 路由正确 → 修订 Agent 只认显式操作词 → 无法处理隐含意图 → 返回"无法理解"
**应该**：对话 Agent 路由正确 → 修订 Agent 能推理隐含意图 → 从"为什么评分低"推导出"改进低分章节" → 执行修改

边界的实现方式不应该是一系列 DO NOT 规则——这本质上是把 LLM 当成 if-else 引擎来用。当多条否定规则并存时，LLM 倾向于遵守保守路径（宁可不触发也不要误触发），导致所有模糊意图都被推向 `continue_chat`。正确的做法是 **通过 prompt 引导 LLM 推理**，让 LLM 理解 "用户为什么这么说"，自然就能做出正确的路由决策——LLM 理解了语义，就不会越权，同时也能正确处理隐含意图。

这不是代码量的问题。调整几个 prompt 段落，就能释放 LLM 被锁住的推理能力：
- 对话路由：从 "DO NOT 触发" 改为 "推理用户隐含需求后正确路由"
- 修订意图分析：增加 "从用户不满中推理改进意图" 的引导，激活 `is_global_feedback` 字段
- Agent 分析：增加 "思考与其他章节的因果联系" 的引导
- 日期约束：从 "注入当前日期" 升级为 "明确约束不得编造未来确定数据"

### 3. 系统能力断裂：研究管道有语义推理，修订管道只有关键词匹配

系统存在明显的 **能力复用断裂**：

| 能力 | 研究管道 | 修订管道 |
|------|----------|----------|
| 隐含意图推理 | ✅ `SemanticIntentAnalyzer.hidden_requirements` | ❌ 无 |
| 语义路由 | ✅ `IntelligentRoutingAdapter` | ❌ 纯 regex fallback |
| 意图映射 | ✅ LLM + 关键词双层 | ❌ 仅 `INTENT_TO_REVISION_MAP_V2` regex |
| 全局反馈识别 | ❌ 不需要 | ❌ Schema 有字段但 prompt 未引导 |

研究管道能从 "我想了解电动车市场" 推理出 hidden_requirements=["竞争格局分析", "政策影响评估"]，但修订管道连 "为什么评分低" → "改进低分章节" 都推理不出来。这不是能力差异，是设计遗漏。

**修复路径**：
- 短期：调整 prompt，让修订管道的 LLM 调用具备隐含意图推理能力
- 中期：在 `RevisionIntentAnalyzer` 中复用 `SemanticIntentAnalyzer`，当直接分析失败时，通过 `hidden_requirements` 二次推理

### 4. 聚合器是数据流的终点，不是数据质量的守门人

当前聚合器（`result_aggregator.py`）只做"匹配→组装"，不做"缺失→补采"。`_match_content_to_sub_section` 匹配失败时直接返回占位符，没有任何回溯机制触发重新搜索或重新生成。系统中存在的补充搜索能力（`_detect_knowledge_gaps` + `_supplementary_search_for_gaps`）只在 agent 执行阶段生效，一旦进入聚合阶段就彻底失效。

这导致一个荒谬的局面：LLM 实际上已经生成了相关内容（只是标题措辞与骨架不完全匹配），但聚合器无法识别，直接丢弃并用占位符替代。这不是数据真的不足，是匹配逻辑不够灵活。

### 5. 系统能"知道"是上市公司，但"做不到"从公司名解析到股票代码

系统已有三层能力：
- `_is_listed_company_topic`（`strategies.py:172`）能识别"比亚迪"是上市公司
- `derive_data_source_type`（`strategies.py:180`）能判断财务数据应标记为 "structured" 或 "both"
- `StockDataSkill`（`stock_data.py:17`）能通过 akshare 获取利润表、资产负债表、现金流量表

但三层能力之间 **没有连接**：识别结果没有传递给数据获取，数据获取的 `_extract_stock_symbol` 只做正则提取中文（返回"比亚迪"），akshare 需要数字代码（"002594"），调用失败被静默吞掉，agent 无感知退回搜索引擎。

akshare 本身提供了 `stock_zh_a_spot_em()` 接口可以通过公司名搜索代码，但系统从未调用过。agent 搜索"比亚迪 营收"时，搜索结果中也会出现"比亚迪（002594.SZ）"，但没有任何逻辑提取代码。

**这不是缺能力，是能力链条上缺失了"公司名→股票代码"这一关键解析环节。**

### 6. 重启清理的资源泄漏风险

每次 shutdown 都因 `_background_tasks` 属性缺失而清理失败（21 次），可能导致后台任务泄漏。19:04~20:15 的 12 次重启本身为修复系统测试，但清理失败叠加资源泄漏可能加剧了 21:21~22:17 的晚间不稳定。

### 7. 并行研究任务的健壮性不足

8 agent 并行时集中爆发 852 次 asyncio 异常、61 次数据边界匹配失败、3 次磁盘恢复失败，说明并行执行路径缺乏充分的错误隔离。

### 8. 搜索引擎依赖免费服务

403 次 DDGS 错误表明免费搜索引擎在高并发下极不可靠。

---

## 五、优先修复建议

| 优先级 | 问题 | 修复建议 | 改动类型 | 状态 |
|--------|------|----------|----------|------|
| ~~P0~~ ✅ | DeepSeek API 余额不足 | 已解决；仍建议增加余额告警和多 LLM fallback | 运维 | ✅ 已解决 |
| **P0** ✅ | 对话 Agent 设计失衡/隐含意图丢失 | 调整3处 prompt + 激活 `is_global_feedback`；regex fallback 增加隐含意图模式 | **Prompt** | ✅ BF-P0-1 |
| **P0** ✅ | 26个子章节"数据不足"，akshare未调用 | 重写 `_extract_stock_symbol`：公司名→akshare搜索→股票代码；增加调用日志 | 代码 | ✅ BF-P0-2 + CRA-9 |
| ~~P0~~ ✅ | 系统频繁重启（19:04~20:15） | 修复 `_background_tasks` 属性避免资源泄漏 | 代码 | ✅ BF-P3-1 |
| **P1** ✅ | asyncio 异常未回收（852次） | 为 create_task 添加 done callback；全局异常处理器注册 | 代码 | ✅ BF-P1-1 + CRA-2/3 |
| **P1** ✅ | 磁盘恢复类型错误 | 恢复逻辑入口增加 Path() 转换 | 代码 | ✅ BF-P1-2 |
| **P2** ✅ | 报告质量低（分析深度/逻辑一致性） | Agent prompt 增加跨章节因果链引导段；日期约束 | **Prompt** | ✅ BF-P2-1 |
| **P2** ✅ | 日期幻觉（25次） | Agent prompt 增加更强的日期约束 | **Prompt** | ✅ BF-P2-1 |
| **P2** ✅ | Scrapling 废弃 API（2,578次） | 迁移到 AsyncFetcher.configure() | 代码 | ✅ BF-P2-2 |
| **P2** | 质量检查无语义一致性能力 | `_check_consistency` 增加 LLM 语义检查路径 | 代码+Prompt | 🔶 中期 |
| **P2** | 数据边界匹配失败 | 检查 agent/section 名称映射；统一 UTF-8 编码 | 代码 | ⬜ 待办 |
| **P2** | 搜索引擎大面积失败 | 增加限流；搜索引擎健康监控；备用 API | 代码 | ⬜ 待办 |
| **P3** | Charts 图片 404 | 检查图表生成/持久化流程 | 代码 | ⬜ 待办 |
| **中期** | 修订管道复用 `SemanticIntentAnalyzer` | 在 `RevisionIntentAnalyzer.analyze` 中增加 `hidden_requirements` 二次推理路径 | 架构 | ⬜ 待办 |
| ~~中期~~ ✅ | ~~akshare 结构化数据优先注入 agent prompt~~ | ~~财务类子章节优先从 akshare 获取，搜索引擎仅补充~~ | ~~代码~~ | ✅ 已由 BF-P0-2 修复 |

> **说明**：原"akshare 结构化数据优先注入 agent prompt"中期建议的前提是"akshare 调用链断裂"。现在 BF-P0-2 已修复 `_extract_stock_symbol` → `_resolve_company_to_code` → akshare 的完整调用链，`StockDataSkill` 通过 skill 机制正常获取结构化数据，无需额外的"优先注入"架构。

---

## 六、修复优先级说明

本报告发现的问题中，**最高优先级的修复不是代码 bug，而是 prompt 调整**。原因：

1. **投入产出比极高**：调整 prompt 的改动量极小（几个段落），但能同时解决隐含意图识别失败、报告分析深度不足、日期幻觉等多个问题。上表中 4 项 Prompt 改动共约 6 小时，但影响面覆盖 P0 + P2 的核心问题。

2. **根因级别修复**：代码 bug（如 `_background_tasks` 缺失、Path 类型错误）是局部问题；prompt 约束不足是系统性问题，影响所有 LLM 交互的质量。

3. **LLM 的能力天花板在 prompt**：当前系统的 LLM 推理能力只发挥了一小部分，不是模型不行，是 prompt 没有给它足够的推理空间。释放这部分能力是性价比最高的优化。

4. **能力复用比能力新建更高效**：`SemanticIntentAnalyzer` 已经具备隐含意图推理能力，修订管道只需要复用它；akshare + `StockDataSkill` 已经具备结构化数据获取能力，只需要修复 `_extract_stock_symbol` 的公司名→代码映射。系统的���多 "做不到" 不是缺能力，是缺管道或调用链上的一个类型转换。

---

## 六、修复记录 (2026-06-22 ~ 2026-06-23)

以下问题已通过 TDD 流程修复，全部测试通过（175 tests, 0 errors）：

| 问题 | 优先级 | 修复状态 | 修改文件 | 测试文件 | 测试数 |
|------|--------|----------|----------|----------|--------|
| 隐含意图识别失败 | P0 | ✅ 已修复 | `revision_intent_analyzer.py`, `revision_intent_mapper.py` | `test_p0_implicit_intent_fix.py` | 20 |
| akshare未调用/公司名→代码 | P0 | ✅ 已修复 | `generic_agent.py` | `test_p0_stock_symbol_fix.py` | 16 |
| asyncio异常未回收 | P1 | ✅ 已修复 | 新建 `task_utils.py` | `test_p1_asyncio_and_disk_fix.py` | 5 |
| CR-FIX-2 磁盘恢复Path类型错误 | P1 | ✅ 已修复 | `engine.py` | 同上 | — |
| 报告质量低/跨章节因果链+日期幻觉 | P2 | ✅ 已修复 | `generic_agent.py` | `test_p2_quality_and_date_fix.py` | 3 |
| Scrapling废弃API | P2 | ✅ 已修复 | `web_scraper_skill.py` | `test_p2_scrapling_api_fix.py` | 2 |
| _background_tasks属性缺失 | P3 | ✅ 已修复 | `research_api.py` | `test_p3_background_tasks_fix.py` | 4 |
| 硬编码关键词集中化 | 重构 | ✅ 已完成 | 新建 `keyword_registry.py`, `keyword_mappings.yaml`; 重构 `revision_intent_analyzer.py`, `revision_intent_mapper.py`, `strategies.py` | `test_keyword_registry.py` | 32 |

### 代码审查修正记录 (第一轮)

审查中发现并修正了以下问题：
1. **误匹配修复**：原始 regex `差|弱` 过于宽泛，"差距"、"出差"等词会误触发。修正为 `太差|很差|较差|太弱|较弱|很弱` 等带修饰词的词组。
2. **`RevisionIntentMapper` 同步修正**：`FIX` 意图下 `差|弱` 同样修正为带修饰词版本。
3. **边界测试补充**：增加"出差"、"差距"、"弱点"、"很差"等误匹配测试用例。

### 代码审查修正记录 (第二轮 — 深度逻辑审查)

| 编号 | 严重度 | 问题 | 修复 |
|------|--------|------|------|
| CRA-1 | 严重 | `revision_intent_analyzer.py` 直接访问 `registry._raw` 绕过封装 | 新增 `get_implicit_pattern_strings()` / `get_global_feedback_pattern_strings()` 公共 API |
| CRA-2 | 严重 | `safe_create_task` 创建了但全项目 62 处裸 `asyncio.create_task` 未替换 | 替换 29 处关键路径 |
| CRA-3 | 严重 | `register_global_exception_handler` 未被调用 | `main.py` startup_event 注册 |
| CRA-4 | 中等 | `_is_likely_company_name` 忽略 chinese_text 参数 | 先查 chinese_text 再查 full_topic |
| CRA-5 | 严重 | `communication.py` / `document_generation_agent.py` 顶层导入 `task_utils` 触发循环导入 | 改为延迟导入 |
| CRA-6 | 低 | YAML 重复标题行 + `_STOCK_CODE_CACHE` 跨测试污染 | 删重复行 + 测试 setup 清理缓存 |
| CRA-7 | 严重 | 全局反馈关键词（整体/总体）未隐含修改意图，"整体评分只有52.4" 返回空意图 | `_fallback_to_regex` 增加 `elif is_global: MODIFY` |
| CRA-8 | 中等 | regex 同分时 first-match-wins，"调整顺序" 匹配为 MODIFY 而非 REORDER | 优先级相同时比较匹配长度，更长的胜出 |
| CRA-9 | 严重 | `_resolve_company_to_code("比亚迪财务分析")` 整段中文查 akshare 匹配不到 "比亚迪" | 子串回退：先查全串，再查注册表中的公司名子串 |

**新增测试文件**：
- `tests/unit/test_review_audit_fixes.py` (22 tests) — CRA-1~6 + 循环导入验证
- `tests/unit/test_keyword_registry.py` (32 tests) — 注册表加载/编译/单例/隐含意图/全局反馈/上市公司
