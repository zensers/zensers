# LLM架构治理：从LLMSkill万能插座到专业推理接口

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

---

## 一、问题诊断：llm_skill为什么扩散到全系统？

### 根因：6种完全不同的专业能力被一个名字覆盖

| 模块 | 它真正在做什么 | 被错误归类为 |
|------|-------------|------------|
| GenericAgent | 搜索→知识增强→phase路由→system_prompt→canonical校准→输出 | "用llm_skill" |
| market_analysis | 数据预处理→框架分析→投行级system_prompt→输出 | "用llm_skill" |
| chapter_writer | 数据+模板→结构化文章→输出 | "用llm_skill" |
| chapter_reviewer | 章节→JSON评分+问题列表 | "用llm_skill" |
| simulation_engine | 人设+问题→模拟人类回答→解析 | "用llm_skill" |
| semantic_intent | 用户输入→意图分类(self-consistency)→JSON | "用llm_skill" |
| task_structure | topic→章节结构→JSON | "用llm_skill" |
| research_api | 用户输入→多轮工具调用→JSON指令 | "用llm_skill" |

**不是设计选择，是没有架构的后果。** 早期没有`call_llm()`独立函数，任何需要调LLM的地方都只能用LLMSkill——推理、模拟、分类、翻译、评审、改写，全部塞进一个"万能插座"。

### 扩散路径量化

| 子系统 | 文件数 | 引用数 | 用途本质 |
|--------|-------|--------|---------|
| survey | 12 | 51 | 模拟人类回答问卷 |
| skills/analysis | 6 | 11 | 数据分析+推理 |
| core/orchestrator | 1 | 22 | 传递给report agents |
| core/agents | 2 | 23 | 路由+工厂注入 |
| report_upgrade | 5 | 6 | 报告撰写/评审/修复 |
| core/quality | 1 | 2 | 关键发现提取 |
| core/adjustment | 2 | 2 | 翻译+批量修订 |
| 其他(research_api, semantic_intent等) | 7 | ~50 | 意图分类/任务分解/综合研究 |

### 三个层面的问题

1. **概念层**：LLM是Agent的思考能力，不是外部工具。把"推理"和"搜索"放在同一个skill_registry里，等于把"思考"和"翻书"等同。
2. **设计层**：没有专业推理接口。每个模块都直接构造prompt+调用+解析，没有抽象出"报告推理"、"模拟推理"、"分析推理"等接口。
3. **实现层**：`skill_registry.get("llm_skill")`成为硬依赖——删掉注册，pipeline直接不启动。

---

## 二、目标架构：三层分离

```
第一层：LLM基础设施 — call_llm()
  └── 纯API调用，所有模块共用
  └── 职责：API连接、fallback、cost limit、返回格式标准化
  └── 不含任何业务逻辑

第二层：专业推理接口 — 每种能力独立封装
  ├── ReportReasoner       → 报告撰写/评审（system_prompt+数据注入+canonical+date验证）
  ├── AnalysisReasoner     → 数据分析（框架+预处理+专业system_prompt）
  ├── SurveySimulator      → 人类模拟（人设+prompt工程+规则fallback+解析）
  ├── IntentClassifier     → 意图识别（self-consistency+JSON解析）
  └── StructureDecomposer  → 任务分解（模板+JSON解析）

第三层：业务流程 — 组合推理接口
  ├── report pipeline      → ReportReasoner × 6个agent
  ├── survey pipeline      → SurveySimulator × 多个组件
  └── research pipeline    → IntentClassifier + tools loop
```

**原则：**
- 第一层是基础设施，不含业务逻辑
- 第二层封装专业逻辑，不是简单包装call_llm()
- 第三层只做流程编排，不直接调call_llm()
- llm_skill.py最终退化为registry兼容层，待所有消费者迁移后删除

---

## 三、当前阶段：Phase 1 — 修复基础设施 + 解耦report pipeline

**基线版本：v1.3.0 (commit 34c456a)** — e2e=82，首次收敛，代码经过验证

**范围限制：** 只动report pipeline相关文件，不动survey/analysis/adjustment等其他子系统。

**目标：**
1. report pipeline不再依赖registry中的LLMSkill实例
2. 修复影响报告质量的bug（JSON解析、缩进、max_tokens）
3. 为Phase 2（提炼ReportReasoner）铺路

**不做的事：**
1. 不删除llm_skill.py — survey/analysis模块仍在用
2. 不迁移survey/analysis/adjustment模块 — 独立任务，风险大
3. 不修改e2e脚本 — 它们仍用LLMSkill，不影响report pipeline
4. 不修改非report_upgrade测试 — test_full_pipeline.py等暂不动
5. 不修改CATEGORY_TO_SKILLS映射 — registry.py L393-403，survey模块依赖
6. 不调整800行缩进 — 最小改动方案，缩进零变化

---

## 四、当前状态：Phase 1 完成，深度审查通过

### 版本历史

| Commit | 版本 | 状态 | 说明 |
|--------|------|------|------|
| 34c456a | v1.3.0 | **已验证基线** | e2e=82，首次收敛，所有代码经过验证 |
| 406ebac | v1.4.0-dev | 部分正确 | LLM架构重构第一次尝试，6个report_upgrade agent迁移到call_llm() |
| 97d2206 | v1.4.0-dev | 含污染 | test更新 + generic_agent fallback路径被污染 |
| HEAD | v1.4.0 | **Phase 1完成** | Task 0-8全部完成 + 深度审查3个额外bug修复 + 115测试通过 |

### Phase 1 完成总结

| Task | 描述 | 状态 | 测试 |
|------|------|------|------|
| 0 | 测试mock修复 (call_llm替代llm_skill.execute) | ✅ | 16+14通过 |
| 1 | chapter_reviewer: max_tokens=8192 + raw JSON fallback | ✅ | 9通过(含2个新增) |
| 2 | global_reviewer: max_tokens=8192 + raw JSON fallback | ✅ | 14通过(含1个新增) |
| 2b | chapter_writer: raw JSON fallback | ✅ | 17通过(含1个新增) |
| 3 | GenericAgent fallback 5个缩进bug | ✅ | 语法通过 |
| 4 | GenericAgent L250入口解耦 | ✅ | 语法通过 |
| 5 | 6个skill.execute→call_llm替换 | ✅ | 语法通过 |
| 6 | orchestrator 2处硬门控解除 | ✅ | 语法通过 |
| 7 | factory自动注入移除 | ✅ | 语法通过 |
| 8 | stash drop | ✅ | 已丢弃 |

### 深度审查发现并修复的3个额外Bug

| # | 文件 | Bug | 严重度 | 修复 |
|---|------|-----|--------|------|
| A | generic_agent.py L1100-1183 | fallback路径缩进混乱(12sp/16sp混合) | HIGH | 统一为12sp |
| B | chapter_writer.py | _parse_output缺少raw JSON fallback | MEDIUM | 添加brace_match兜底(与reviewer一致) |
| C | llm_client.py L43-44 | max_tokens=0/temperature=0.0被`0 or default`静默覆盖 | HIGH | 改为`is None`检查 |

### 深度审查确认的已知问题（Phase 2+范围）

| # | 文件 | 问题 | 优先级 |
|---|------|------|--------|
| 1 | llm_client.py L91 | 每次调用新建AsyncOpenAI客户端(性能) | Phase 2 |
| 2 | llm_client.py | 无网络重试逻辑(可靠性) | Phase 2 |
| 3 | llm_client.py | 返回dict格式不一致(success有content, failure没有) | Phase 2 |

### 测试覆盖

| 测试文件 | 测试数 | 状态 |
|----------|--------|------|
| test_chapter_writer.py | 17 | ✅ (含2个raw JSON fallback测试) |
| test_chapter_reviewer.py | 9 | ✅ (含2个raw JSON fallback测试) |
| test_global_reviewer.py | 14 | ✅ (含1个raw JSON fallback测试) |
| test_data_repair.py | 21 | ✅ |
| test_models.py | 24 | ✅ |
| test_data_registry.py | 19 | ✅ |
| test_prompt_manager.py | 8 | ✅ |
| test_llm_client.py | 3 | ✅ (新增is None guard测试) |
| **总计** | **115** | **全部通过** |

---

## 五、实施Task

### Task 0: 修复测试mock — call_llm替代llm_skill.execute

**Files:** `tests/unit/report_upgrade/test_chapter_writer.py`, `tests/unit/report_upgrade/test_global_reviewer.py`

**问题:** 代码已迁移到`call_llm()`，但测试仍mock `llm_skill.execute`→5+4个测试触发真实LLM调用→失败

**当前基线:** 9 failed, 268 passed

**修改方案（已在stash中验证过）:**

test_chapter_writer.py:
1. 删除 `mock_llm` fixture（不再需要AsyncMock作为llm_skill参数）
2. `writer` fixture改为 `ChapterWriter(prompt_manager=mock_prompts)`（不传llm_skill）
3. 所有LLM调用测试改为 `with patch("src.agents.fixed_agents.report_upgrade.chapter_writer.call_llm", new_callable=AsyncMock) as mock_call:`
4. `mock_call.return_value` 格式：`{"success": True, "content": ..., "model": "test", "usage": {}}`
5. LLM失败测试：`mock_call.return_value = {"success": False, "message": "error"}`

test_global_reviewer.py:
1. 同上模式
2. `reviewer` fixture改为 `GlobalReviewAgent(prompt_manager=mock_prompts)`
3. patch路径：`"src.agents.fixed_agents.report_upgrade.global_reviewer.call_llm"`
4. verify_issues测试中的mock同理

- [x] **Step 1: 修改test_chapter_writer.py**
- [x] **Step 2: 修改test_global_reviewer.py**
- [x] **Step 3: 运行测试验证**

Run: `D:\conda\python.exe -X utf8 -m pytest tests/unit/report_upgrade/test_chapter_writer.py tests/unit/report_upgrade/test_global_reviewer.py -v`
Expected: 0 failed (当前9个失败全部修复)

> **注：** stash中已有此修改的完整diff，可参考 `git stash show -p stash@{0} -- tests/` 提取。

---

### Task 1: 修复chapter_reviewer — max_tokens + JSON解析

**Files:** `src/agents/fixed_agents/report_upgrade/chapter_reviewer.py:36,42-67`

**问题:** max_tokens=4096导致LLM输出截断→JSON闭合缺失→解析失败→score=0→无意义收敛循环

**当前代码 (已验证):**
- L36: `result = await call_llm(prompt=prompt, max_tokens=4096, temperature=0.3)`
- L42-67: _parse_output只有\`\`\`json\`\`\`匹配，无raw JSON fallback

**修改:**

- [x] **Step 1: max_tokens 4096→8192**
- [x] **Step 2: 重写_parse_output，增加raw JSON fallback**
- [x] **Step 3: 测试**

Run: `D:\conda\python.exe -X utf8 -m pytest tests/unit/report_upgrade/test_chapter_reviewer.py -v`
Expected: 7 passed

---

### Task 2: 修复global_reviewer — max_tokens + JSON解析

**Files:** `src/agents/fixed_agents/report_upgrade/global_reviewer.py:28,51,87-122`

**问题:** 同Task 1

- [x] **Step 1: 两处max_tokens 4096→8192** (L28和L51)
- [x] **Step 2: 重写_parse_output，增加raw JSON fallback**
- [x] **Step 3: 测试**

Run: `D:\conda\python.exe -X utf8 -m pytest tests/unit/report_upgrade/test_global_reviewer.py -v`
Expected: 13 passed, 0 failed

---

### Task 2b: 补充chapter_writer的raw JSON fallback（可选）

**Files:** `src/agents/fixed_agents/report_upgrade/chapter_writer.py:95-128`

**问题:** chapter_writer的 `_parse_output` 同样只有 `\`\`\`json\`\`\`` 匹配，无raw JSON fallback。但chapter_writer的fallback比reviewer更宽松——解析失败时直接 `content=raw`（L123），不会返回score=0导致收敛循环。影响是data_points和key_conclusions丢失。

**优先级:** MEDIUM（不影响收敛，但影响数据完整性）

**修改方案：** 同Task 1-2的模式，在L98的if块后增加else分支尝试raw JSON匹配：

```python
    def _parse_output(self, raw: str, chapter_spec: Dict) -> ChapterWriteOutput:
        _SKIP_TITLES = {"数据精准修补任务", "章节精修任务", "章节精修润色任务", "章节撰写任务"}
        try:
            json_str = None
            json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                logger.warning(f"ChapterWriter: no ```json``` block found, trying raw JSON. Raw len={len(raw)}")
                brace_match = re.search(r'\{.*\}', raw, re.DOTALL)
                if brace_match:
                    json_str = brace_match.group(0)
            if json_str:
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                data = json.loads(json_str)
            else:
                raise ValueError("No JSON content found")
            # ... 后续同原逻辑 ...
```

- [x] **Step 1: 修改chapter_writer.py _parse_output**
- [x] **Step 2: 测试**

Run: `D:\conda\python.exe -X utf8 -m pytest tests/unit/report_upgrade/test_chapter_writer.py -v`
Expected: 16 passed

---

### Task 3: 修复GenericAgent fallback路径5个缩进bug

**Files:** `src/core/agents/generic_agent.py:1136-1222`

**5个bug（已验证）:**

| # | 行号 | 当前 | 正确 | 影响 |
|---|------|------|------|------|
| 1 | L1184 | 16空格(else内), 缺system_prompt | 12空格, 补system_prompt | call_llm在错误层级且丢失角色定位 |
| 2 | L1184 | 16空格(else内) | 12空格(if/elif/else链外) | **最严重**：有topic时(L1147分支)prompt构建后不调LLM→L1187访问未定义result→NameError |
| 3 | L1187-1191 | 12/16空格混乱 | 12空格 | 日期验证缩进不匹配 |
| 4 | L1193-1194 | 注释缩进混乱 | 12空格 | 代码可读性差 |
| 5 | L1222 | 16空格(if search_results内) | 12空格 | 无搜索结果时不返回，落到"无匹配Skill"错误 |

**Bug #2详解：** L1136-1182是if/elif/else链：`if search_results`→`elif topic`→`else`。L1184 `call_llm` 在 `else:` 内（16sp），只有无topic时才执行。有topic时，prompt构建后跳过call_llm，直接到L1187 `if result.get("success")`，此时`result`未定义→`NameError`。修复方案将call_llm提升到12sp（if/elif/else链外），所有分支构建的prompt都能被调用。

**修复: 重写L1184-1222的缩进和逻辑**

- [x] **Step 1: 替换fallback块**

old:
```python
                result = await call_llm(prompt=prompt)

                # 日期验证
            if result.get("success") and result.get("content"):
                validated = self._validate_output_dates(result["content"], self.agent_id)
                if validated != result["content"]:
                    logger.warning(f"GenericAgent {self.agent_id}: fallback路径日期验证修正了年份")
                    result["content"] = validated

                # P0-3: Attach search data to result so downstream
            # quality checks and synthesis agents can access sources.
            if search_results:
                data_points = []
                sources = []
                for search in search_results.get("searches", []):
                    for item in search.get("results", []):
                        data_points.append({
                            "title": item.get("title", ""),
                            "content": item.get("body", "") or item.get("snippet", ""),
                            "url": item.get("href", "") or item.get("url", ""),
                            "quality_score": item.get("quality_score", 0),
                            "credibility": item.get("credibility", "unknown"),
                        })
                        sources.append({
                            "title": item.get("title", ""),
                            "url": item.get("href", "") or item.get("url", ""),
                            "type": "web",
                            "quality_score": item.get("quality_score", 0),
                        })
                result["data_points"] = data_points
                result["sources"] = sources
                result["total_sources"] = search_results.get("total_sources", 0)
                result["quality_stats"] = search_results.get("quality_stats", {})
                logger.info(
                    f"GenericAgent {self.agent_id}: fallback enriched with "
                    f"{len(data_points)} data points, {len(sources)} sources"
                )

                return self._ensure_standard_result(result, action)
        
        # 没有匹配的Skill
```

new:
```python
            result = await call_llm(
                prompt=prompt,
                system_prompt=self._get_professional_role_prompt(
                    context.get("aspect") or task.get("aspect", "")
                )
            )

            # 日期验证
            if result.get("success") and result.get("content"):
                validated = self._validate_output_dates(result["content"], self.agent_id)
                if validated != result["content"]:
                    logger.warning(f"GenericAgent {self.agent_id}: fallback路径日期验证修正了年份")
                    result["content"] = validated

            # P0-3: Attach search data to result so downstream
            # quality checks and synthesis agents can access sources.
            if search_results:
                data_points = []
                sources = []
                for search in search_results.get("searches", []):
                    for item in search.get("results", []):
                        data_points.append({
                            "title": item.get("title", ""),
                            "content": item.get("body", "") or item.get("snippet", ""),
                            "url": item.get("href", "") or item.get("url", ""),
                            "quality_score": item.get("quality_score", 0),
                            "credibility": item.get("credibility", "unknown"),
                        })
                        sources.append({
                            "title": item.get("title", ""),
                            "url": item.get("href", "") or item.get("url", ""),
                            "type": "web",
                            "quality_score": item.get("quality_score", 0),
                        })
                result["data_points"] = data_points
                result["sources"] = sources
                result["total_sources"] = search_results.get("total_sources", 0)
                result["quality_stats"] = search_results.get("quality_stats", {})
                logger.info(
                    f"GenericAgent {self.agent_id}: fallback enriched with "
                    f"{len(data_points)} data points, {len(sources)} sources"
                )

            return self._ensure_standard_result(result, action)
        
        # 没有匹配的Skill
```

**改动总结:** 5处缩进修正 + call_llm补传system_prompt + call_llm提升到if/elif/else链外（修复NameError） + return提升到外层

- [x] **Step 2: 语法检查**
- [x] **Step 3: 测试**

---

### Task 4: GenericAgent入口解耦 — LLM分支不再依赖registry实例

**Files:** `src/core/agents/generic_agent.py:250-251`

**问题:** L250 `if skill:` 依赖registry实例→LLM分支进不来。这是"LLM被当成外部skill"这一设计缺陷在代码层面的直接体现。

**方案: 最小改动——只改L250一行条件，缩进零变化**

当前代码 (L248-253, 已验证):
```python
        if skill_name and skill_name in available_skills and skill_registry:
            skill = skill_registry.get(skill_name)
            if skill:
                logger.info(f"GenericAgent {self.agent_id}: 找到Skill '{skill_name}'，开始执行")
                # 对于 LLM skill，需要构建 prompt
                if skill_name == "llm_skill":
```

修改后:
```python
        if skill_name and skill_name in available_skills and skill_registry:
            skill = skill_registry.get(skill_name)
            # LLM是Agent内在能力，不依赖registry实例；其他skill仍需registry实例
            if skill_name == "llm_skill" or skill:
                logger.info(f"GenericAgent {self.agent_id}: 执行 '{skill_name}' (LLM=intrinsic)")
                # 对于 LLM skill，需要构建 prompt
                if skill_name == "llm_skill":
```

**改动:** 1行条件 + 1行日志。缩进零变化，L253及后续800+行完全不动。

**语义保证:**
- `skill_name == "llm_skill"` 时，即使skill=None也进入 ✓
- 其他skill仍需skill非None才进入 ✓
- 非LLM skill行为完全不变 ✓

**架构意义:** 这一行改动将LLM从"依赖外部skill"变为"Agent内在能力"，是第一层（基础设施）解耦的关键一步。

- [x] **Step 1: 修改L250-251**
- [x] **Step 2: 语法检查**
- [x] **Step 3: 测试**

---

### Task 5: 替换6个skill.execute()为call_llm()

**Files:** `src/core/agents/generic_agent.py` (6个调用点)

**问题:** LLM分支内仍通过`skill.execute()`调用LLM，依赖registry实例。改为`call_llm()`使Agent直接使用内在推理能力。

**6个调用点（已验证行号和内容）:**

| # | 行号 | 当前代码 | 替换为 |
|---|------|---------|--------|
| 1 | L671 | `result = await skill.execute(prompt=prompt, system_prompt=system_prompt)` | `result = await call_llm(prompt=prompt, system_prompt=system_prompt)` |
| 2 | L712 | `revised = await skill.execute(prompt=prompt2, system_prompt=syst` | `revised = await call_llm(prompt=prompt2, system_prompt=syst` |
| 3 | L765 | `result = await skill.execute(` | `result = await call_llm(` |
| 4 | L856 | `result = await skill.execute(prompt=prompt, system_prompt=system_prompt)` | `result = await call_llm(prompt=prompt, system_prompt=system_prompt)` |
| 5 | L858 | `result = await skill.execute(prompt=prompt)` | `result = await call_llm(prompt=prompt)` |
| 6 | L973 | `result = await skill.execute(prompt=prompt, system_prompt=system_prompt)` | `result = await call_llm(prompt=prompt, system_prompt=system_prompt)` |

**不改的7个skill.execute（已确认——都是真正的外部skill或非LLM分支）:**

| 行号 | 调用 | 原因 |
|------|------|------|
| L113 | `skill.execute(**parameters)` | 非LLM skill分支 |
| L290 | `kq_skill.execute(...)` | 知识查询skill |
| L410 | `news_skill.execute(...)` | 新闻skill |
| L529 | `search_skill.execute(...)` | 搜索skill |
| L1067 | `skill.execute(**parameters)` | else分支(非llm_skill) |
| L1075 | `skill.execute(**parameters)` | 回退路径 |
| L1085 | `skill.execute(**parameters)` | 动态发现 |

- [x] **Step 1-6: 逐个替换6个skill.execute为call_llm** (不能用replaceAll，需逐个)
- [x] **Step 7: 确认LLM分支(L253-1065)内无skill.execute残留**
- [x] **Step 8: 语法检查**
- [x] **Step 9: 测试**

---

### Task 6: 解除orchestrator.py的llm_skill硬门控

**Files:** `src/core/orchestrator/orchestrator.py:976-1040, 2058-2127`

**问题:** L980 `if _llm_skill:` 和 L2062 `if llm_skill:` 是硬门控——registry中没有llm_skill则整个report_upgrade pipeline不初始化，L1039/L2125 else分支直接 `raise RuntimeError("No LLM skill available")`。

**两个代码路径：**

| 路径 | 行号 | 变量名 | else分支 | 说明 |
|------|------|--------|---------|------|
| 非路由路径 | L976-1040 | `_llm_skill` | L1039 `raise RuntimeError("No LLM skill available")` | 需删除门控+删除else+后续缩进减1层 |
| 路由路径 | L2058-2127 | `llm_skill` | L2125 `raise RuntimeError("No LLM skill available")` | 同上 |

**当前代码 (L976-999, 已验证):**
```python
                _llm_skill = self._skill_registry.get("llm_skill")
                _search_skill = self._skill_registry.get("search_skill")
                _web_scraper_skill = self._skill_registry.get("web_scraper")

                if _llm_skill:
                    _pm = PromptManager()
                    _ro = ReportOrchestrator(
                        llm_skill=_llm_skill,
                        chapter_writer=ChapterWriter(llm_skill=_llm_skill, prompt_manager=_pm),
                        ...
```

**路径1修改后 (L976-1039):**
```python
                _search_skill = self._skill_registry.get("search_skill")
                _web_scraper_skill = self._skill_registry.get("web_scraper")

                # Report pipeline no longer depends on llm_skill instance;
                # agents use call_llm() directly. Initialize regardless.
                _pm = PromptManager()
                _ro = ReportOrchestrator(
                    llm_skill=None,
                    chapter_writer=ChapterWriter(llm_skill=None, prompt_manager=_pm),
                    chapter_reviewer=ChapterReviewAgent(llm_skill=None, prompt_manager=_pm),
                    global_reviewer=GlobalReviewAgent(llm_skill=None, prompt_manager=_pm),
                    data_repair_agent=DataRepairAgent(
                        search_skill=_search_skill,
                        web_scraper_skill=_web_scraper_skill,
                        llm_skill=None,
                        prompt_manager=_pm,
                    ),
                    conflict_resolver=ConflictResolver(
                        llm_skill=None,
                        search_skill=_search_skill,
                        web_scraper_skill=_web_scraper_skill,
                        prompt_manager=_pm,
                    ),
                    prompt_manager=_pm,
                    skill_registry=self._skill_registry,
                )

                _output_type_value = requirement.output_type.value if hasattr(
                    requirement.output_type, 'value') else str(requirement.output_type)
                # ... 后续代码缩进减1层（原在if _llm_skill:内） ...
```

**路径2修改 (L2058-2126):** 同理，删除 `if llm_skill:` 门控 + 删除else分支 + 所有llm_skill参数改None + 后续缩进减1层

**⚠️ 缩进调整注意：** 删除 `if _llm_skill:` 后，原在if块内的所有代码（L1002-1038）需缩进减1层（20sp→16sp）。这是Python语法要求，遗漏会导致IndentationError。路径2同理。

- [x] **Step 1: 修改路径1 (L976-1040)** — 删除if门控+else分支+后续缩进减1层
- [x] **Step 2: 修改路径2 (L2058-2127)** — 同上
- [x] **Step 3: 语法检查**
- [x] **Step 4: 测试**

---

### Task 7: factory移除llm_skill自动注入

**Files:** `src/core/agents/factory.py:231-234`

**当前代码 (L223-234, 已验证):**
```python
        # Safety: if no valid skills remain, inject llm_skill as minimum
        if not norm_required and not norm_optional:
            logger.warning(...)
            norm_required = ["llm_skill"]

        # Ensure llm_skill is present for agents that need reasoning
        if "llm_skill" not in norm_required and "llm_skill" not in norm_optional:
            norm_optional.append("llm_skill")
            logger.debug(f"Agent {agent_id}: auto-added 'llm_skill' as optional")
```

**修改:** 只删除L231-234（自动注入），保留L223-229（fallback安全网）

**架构意义:** Agent不再需要声明"我需要llm_skill"才能获得推理能力——推理是内在的。但fallback安全网保留，因为没有任何skill的agent仍需一个最低能力入口（survey模块仍在用registry中的llm_skill）。

- [x] **Step 1: 删除L231-234**
- [x] **Step 2: 测试**
- [x] **Step 3: 测试report_upgrade**

---

### Task 8: 处理stash

- [x] **Step 1: 审查stash内容** — 已审查，有用内容已在Task 0-2中实施
- [x] **Step 2: `git stash drop`** — 已丢弃
- [x] **Step 3: `git status`** — 工作区状态正常

---

### Task 9: e2e验证 — ✅ 基本通过

- [x] **Step 1: 运行e2e** — 评分75分(≥74目标)

Run: `D:\conda\python.exe -X utf8 scripts/e2e_v4_convergence.py`

**e2e v9结果:**

| 指标 | 值 | 目标 | 达标 |
|------|---|------|------|
| overall_score | 75.0 | ≥74 | ✅ |
| converged | False | True | ❌ (Phase 2目标) |
| convergence_rounds | 2 | - | - |
| 总字数 | 6037 | - | - |
| 数据点 | 29 | ≥30 | ❌ (差1) |
| 模糊来源 | 0 | 0 | ✅ |
| key_findings | 2 | ≥3 | ❌ |
| LLM调用次数 | 1 | ~20 | 异常低 |

**分析:**
- 评分75>74，Phase 1解耦目标达成
- 未收敛(75<80)和LLM调用数异常低(1次)是Phase 2 ReportReasoner需解决的问题
- 第1章0个data_points：JSON解析错误 "Expecting ',' delimiter"，raw fallback已生效但JSON本身不完整
- e2e脚本已更新为`llm_skill=None`，验证了解耦后pipeline可用

- [x] **Step 2: 检查报告质量** — 部分达标(Phase 2继续改进)

---

## 六、Phase 2: LLM基础设施升级 + 调用追踪 — ✅ 完成（含审查修复）

### Task A: llm_client.py基础设施升级

**修改:** `src/core/llm_client.py` 完全重写

| 改进 | 旧 | 新 |
|------|---|---|
| AsyncOpenAI client | 每次调用新建(L91) | 模块级单例`_get_client()` + `_reset_client()` |
| 网络重试 | 无 | tenacity 3次+指数退避(1-10s) |
| 返回格式 | failure缺少`content` key | 所有路径返回`content` key(failure="") |
| is None guard | ✅(Phase 1修) | ✅(保持) |
| 回调支持 | 无(全局变量) | `contextvars.ContextVar`(并发安全) |
| 回调异常处理 | `except: pass` | `except: logger.warning()` |
| 死代码 | `_RETRYABLE_ERRORS`未使用 | 已删除 |

**测试:** `tests/unit/core/test_llm_client.py` — 15个测试(6类)

### Task B: LLM调用追踪覆盖子agent

**修改:**
- `llm_client.py`: `_on_complete_var` contextvar, call_llm完成后触发回调
- `orchestrator.py`: `generate_report`用`_on_complete_var.set()`/`.reset()`设置回调
- `orchestrator.py`: `_call_llm_tracked`移除显式`_record_llm_trace`调用(防止双重计数)

### Task C: e2e验证

| 指标 | Phase 1 | Phase 2 | 变化 |
|------|---------|---------|------|
| overall_score | 75.0 | 75.0 | — |
| LLM调用次数 | 1 | 26 | ✅ 修复 |
| tokens消耗 | 1,440 | 129,816 | ✅ 真实反映 |
| key_findings | 2 | 8 | ✅ +6 |
| converged | False | False | 待Phase 3 |

### 审查发现并修复的Bug

| # | Bug | 严重度 | 修复 |
|---|-----|--------|------|
| 1 | `_on_complete_callback`全局变量导致并发cross-talk | CRITICAL | 改用`contextvars.ContextVar` |
| 2 | `_call_llm_tracked`双重计数(callback+显式调用) | HIGH | 移除显式`_record_llm_trace`调用 |
| 3 | callback异常静默吞噬(`except: pass`) | IMPORTANT | 改为`logger.warning()` |
| 4 | 死代码`_RETRYABLE_ERRORS`未使用 | MINOR | 删除 |
| 5 | 无`_reset_client()`函数(测试和配置切换需要) | MINOR | 添加 |

### 测试覆盖（15个测试）

| 测试类 | 测试数 | 覆盖内容 |
|--------|--------|----------|
| TestCallLlmIsNoneGuard | 3 | max_tokens=0, temperature=0.0, None→默认 |
| TestCallLlmReturnFormat | 4 | 成功/失败/fallback/双模型失败 |
| TestCallback | 4 | 成功回调/API失败回调/回调异常隔离/无回调 |
| TestCostLimit | 2 | 超限拒绝/低于限额通过 |
| TestSingletonClient | 2 | 同实例复用/reset后新建 |

### 后续Phase规划

### Phase 3: LLM流式输出 + Chat体验升级 — 🔄 进行中

**目标:** 为`_llm_converse()`实现流式输出，用户发送消息后实时看到LLM回复逐字出现

**详细设计:** `docs/superpowers/plans/2026-06-28-phase3-llm-streaming-design.md`

**包含能力:**
- `call_llm_stream()` — AsyncGenerator流式LLM调用
- `CHAT_TOKEN` SSE事件 — 逐token推送给前端
- `_llm_converse()`双通道改造 — 首轮流式展示+缓冲解析JSON
- `llm_skill.execute()`替换为`call_llm()`/`call_llm_stream()`

**预计文件:** `src/core/llm_client.py`, `src/core/session_streamer.py`, `src/api/research_api.py`

**依赖:** Phase 2完成 ✅

### Phase 4: 提炼ReportReasoner（从GenericAgent L253-1065中抽取）

**目标:** 将GenericAgent中800+行的LLM专业路由逻辑封装为`ReportReasoner`类

**包含能力:**
- phase-aware搜索（research→搜索优先, analysis→用上游数据）
- 知识增强（knowledge_query）
- system_prompt注入（_get_professional_role_prompt）
- canonical校准（_enforce_canonical_values）
- 日期验证（_validate_output_dates）
- 输出污染过滤（_filter_output_contamination）
- 数据点附加（search_results → data_points/sources）

**预计文件:** `src/core/reasoning/report_reasoner.py`

**依赖:** Phase 2完成

### Phase 4: 提炼ReportReasoner（从GenericAgent L253-1065中抽取）

**目标:** 将GenericAgent中800+行的LLM专业路由逻辑封装为`ReportReasoner`类

**包含能力:**
- phase-aware搜索（research→搜索优先, analysis→用上游数据）
- 知识增强（knowledge_query）
- system_prompt注入（_get_professional_role_prompt）
- canonical校准（_enforce_canonical_values）
- 日期验证（_validate_output_dates）
- 输出污染过滤（_filter_output_contamination）
- 数据点附加（search_results → data_points/sources）

**预计文件:** `src/core/reasoning/report_reasoner.py`

**依赖:** Phase 3完成

### Phase 5: 提炼SurveySimulator（从survey/模块中抽取）

**目标:** 将12个文件51个引用的LLM调用封装为`SurveySimulator`类

**包含能力:**
- 人设驱动回答（PersonaV2 → 人类模拟回答）
- 规则fallback（无LLM时用随机选择）
- 重试逻辑（_call_llm_with_retry）
- 成本估算（_record_estimated_cost）
- 回答解析（_parse_response）

**预计文件:** `src/core/reasoning/survey_simulator.py`

**依赖:** Phase 3完成后经验证

### Phase 5: 提炼SurveySimulator（从survey/模块中抽取）

**目标:** 将12个文件51个引用的LLM调用封装为`SurveySimulator`类

**包含能力:**
- 人设驱动回答（PersonaV2 → 人类模拟回答）
- 规则fallback（无LLM时用随机选择）
- 重试逻辑（_call_llm_with_retry）
- 成本估算（_record_estimated_cost）
- 回答解析（_parse_response）

**预计文件:** `src/core/reasoning/survey_simulator.py`

**依赖:** Phase 4完成后经验证

### Phase 6: 提炼AnalysisReasoner + IntentClassifier

**目标:** 将skills/analysis/6个文件和semantic_intent/task_structure封装为专业推理接口

**依赖:** Phase 3完成后经验证

### Phase 6: 提炼AnalysisReasoner + IntentClassifier

**目标:** 将skills/analysis/6个文件和semantic_intent/task_structure封装为专业推理接口

**依赖:** Phase 5完成后经验证

### Phase 7: llm_skill.py退役

**目标:** 当所有消费者迁移到专业推理接口后，删除llm_skill.py和registry注册

**依赖:** Phase 6完成 + 所有模块迁移验证

---

## 七、回退策略

每个Task独立可回退：
- Task 0: 测试mock修改，失败可`git checkout tests/unit/report_upgrade/test_chapter_writer.py tests/unit/report_upgrade/test_global_reviewer.py`
- Task 1-2: 独立bug修复
- Task 3: fallback缩进修复
- Task 4-5: 核心解耦，失败可`git checkout src/core/agents/generic_agent.py`
- Task 6-7: 配套修改，失败可单独回退

**全局回退:** `git checkout .`

---

## 八、call_llm()基础设施审查与改进 — 状态总览

### 8.1 单例AsyncOpenAI client — ✅ 已修复(Phase 2)

模块级单例`_get_client()` + `_reset_client()`。连接复用，不再每次创建/销毁。

### 8.2 网络错误重试 — ✅ 已修复(Phase 2)

tenacity 3次重试+指数退避(1-10s)，覆盖`APIConnectionError/RateLimitError/ConnectionError/TimeoutError`。

### 8.3 流式输出支持 — 🔄 Phase 3实施中

`call_llm_stream()` 接口将在Phase 3实现。详细设计见 `docs/superpowers/plans/2026-06-28-phase3-llm-streaming-design.md`。

**Phase 3范围:** `call_llm_stream()` + `CHAT_TOKEN` SSE事件 + `_llm_converse()`双通道改造

### 8.4 max_tokens=0陷阱 — ✅ 已修复(Phase 1)

**修复：** 改为显式None检查。**测试：** 3个测试验证is None guard

### 8.5 返回格式一致性 — ✅ 已修复(Phase 2)

**问题：** 旧版failure路径缺少`content` key，调用方需`result.get("content", "")`防御。
**修复：** 所有返回路径统一包含`success, content, message` key。failure时`content=""`。

### 8.6 并发安全callback — ✅ 已修复(Phase 2审查)

**问题：** `_on_complete_callback`全局变量，并发generate_report会cross-talk。
**修复：** 改用`contextvars.ContextVar`，每个async task独立隔离。

### 8.7 双重计数bug — ✅ 已修复(Phase 2审查)

**问题：** `_call_llm_tracked`既触发callback又显式调用`_record_llm_trace`，导致exec summary调用被计数2次。
**修复：** `_call_llm_tracked`移除显式`_record_llm_trace`调用，仅依赖callback追踪。

### 8.8 （已合并到8.3）

---

## 九、修正版执行顺序与依赖关系

```
Phase 1 (已完成) ─────────────────────────────────────────────────┐
                                                                    │
  Task 0 (测试mock修复)                                             │
  Task 1 (chapter_reviewer max_tokens+JSON)                         │
  Task 2 (global_reviewer max_tokens+JSON)                          │
  Task 2b (chapter_writer JSON fallback)                            │
  Task 3 (generic_agent fallback 5个缩进bug)                       │
  Task 4 (generic_agent L250入口解耦)                               ├──→ e2e: 75分
  Task 5 (6个skill.execute→call_llm)                                │
  Task 6 (orchestrator硬门控解除, 2个路径)                          │
  Task 7 (factory自动注入移除)                                      │
  Task 8 (stash审查+丢弃)                                           │
  深度审查 (3个额外bug修复 + 5个测试新增)                           ┘

Phase 2 (已完成) ──────────────────────────────────────────────────┐
                                                                    │
  Task A (llm_client重写: 单例+重试+格式一致)                      │
  Task B (LLM调用tracking覆盖子agent)                               ├──→ e2e: 75分, 26次LLM, 130K tokens
  Task C (e2e验证)                                                  │
  审查修复 (contextvars+双重计数+异常日志+死代码)                  │
  测试新增 (8个: callback4+costlimit2+bothfail1+singleton1)        ┘

Phase 3 (进行中): LLM流式输出 + Chat体验升级 ──────────────────────┐
                                                                     │
  Task 3.0 (call_llm_stream流式函数)                                 │
  Task 3.1 (CHAT_TOKEN SSE事件)                                      ├──→ 用户实时看到LLM回复
  Task 3.2 (_llm_converse双通道改造)                                 │
  Task 3.3 (e2e验证)                                                  │
  详见: docs/superpowers/plans/2026-06-28-phase3-llm-streaming-design.md ┘

Phase 4 (待实施): 提炼ReportReasoner
Phase 5 (待实施): 提炼SurveySimulator
Phase 6 (待实施): 提炼AnalysisReasoner + IntentClassifier
Phase 7 (待实施): llm_skill.py退役
```

**Phase 1 状态: ✅ 完成**
**Phase 2 状态: ✅ 完成（含审查修复）**
**Phase 3 状态: 🔄 进行中（方案设计完成，待审查后实施）**

**下一步: Phase 3 — LLM流式输出 + Chat体验升级**
**详细设计: `docs/superpowers/plans/2026-06-28-phase3-llm-streaming-design.md`**

**关键约束：**
- Task 0 必须先完成，否则Task 1-2的测试验证无法通过（9个失败掩盖真实结果）
- Task 3-5 对 generic_agent.py 有顺序依赖（3先修复缩进，4改入口，5替换调用）
- Task 6 删除硬门控后，Task 7的factory移除才有意义（否则pipeline仍依赖llm_skill注册）
- Task 8 在所有修改完成后执行（stash中的测试修复已在Task 0中实施）
- 每个Task完成后运行语法检查+测试，确认无回归
