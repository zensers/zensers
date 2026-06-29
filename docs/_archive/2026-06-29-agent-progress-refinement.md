# Agent 内部进度细化方案

> 日期: 2026-06-29
> 状态: 设计方案（待审查后实施）

## 1. 现状

`_report_progress()` 方法已在 `BaseAgent`（`src/core/agents/base.py:231`）和 `FixedAgent`（`src/agents/fixed_agents/base_fixed_agent.py:140`）中实现，但调用点极少：

> ⚠️ **注意**：`GenericAgent`（`generic_agent.py:88-91`）继承自 `StateManagementMixin, CommunicationMixin`，**不继承** `BaseAgent` 或 `FixedAgent`，且两个 Mixin 均未定义 `_report_progress`。但现有代码已在 6 处调用 `self._report_progress()`（L317/372/498/579 + L862/865），实施前须确认运行时该方法确实可解析（或存在动态注入机制），否则新增调用会抛出 `AttributeError`。

> ⚠️ **节流机制**：`SessionStreamer.push_agent_message()`（`session_streamer.py:247-256`）内置 **per-session 200ms 节流**（`_AGENT_MSG_THROTTLE_SECONDS = 0.2`，L79）：同一 session 内，非 heartbeat 的 `agent_message` 事件在 200ms 窗口内只推送第一条，后续静默丢弃。节流在 SSE 层而非 `_report_progress` 层，影响所有 Agent 的消息推送。

| Agent | 现有调用点 | 缺失的关键步骤 |
|-------|-----------|---------------|
| GenericAgent (research) | 入口 1 行（L317）+ 搜索 1 行（L372） | Tier 1 DB 查询汇总、Tier 2 搜索汇总、news_search 结果 |
| GenericAgent (quality-check) | 入口 1 行（L498） | 验证结果、冲突解决、重收集 |
| GenericAgent (analysis) | 入口 1 行（L579） | 搜索降级、知识缺口检测、补充搜索、自评 |
| GenericAgent (synthesis/数据富集) | LLM 前 2 行（L862、L865） | 无 — 此路径已有足够的 LLM 前进度消息 |
| GenericAgent (calibration) | 无（L749-792） | 校准执行 |
| GenericAgent（默认路径 fallback） | 无（L943-964） | 搜索+分析 |
| ReportGenerationAgent | 入口 1 行 | 各章节生成 |
| QualityCheckAgent | 入口 1 行 | 各检查项 |
| DataCollectionAgent | 入口 1 行 | 各数据源 |

用户当前只能看到 "Starting data collection..." 和 "Generating analysis for 市场规模..."，中间的搜索、校验、LLM 调用等耗时步骤完全不可见。

## 2. 设计原则

1. **Tier 级别粒度，非 Skill 级别** — 不为每个 DB 查询单独发消息（3-5 个 DB 查询在 1-2 秒内连续完成，逐条推送无感知价值且会被 session 级 200ms 节流吞掉大部分），而是在 Tier 1 全部完成后发一条汇总
2. **中文消息** — 面向中文用户，消息用中文
3. **action 语义准确** — searching（搜索）、analyzing（分析/校验）、writing（生成内容）
4. **不重复** — engine.py 已在 batch 级别推送 "Starting XXX..." / "XXX completed."，Agent 内部不再重复启停消息
5. **异常安全** — `_report_progress()` 方法自身在 try/except 内（`base.py:235-244`），调用方无需额外保护
6. **节流兼容** — 同一 session 内 200ms 节流（`SessionStreamer._AGENT_MSG_THROTTLE_SECONDS = 0.2`）会丢弃密集消息。各进度点之间通常有秒级间隔（搜索、LLM 调用），不受节流影响；但 sub-second 级连续消息（如验证+冲突解决）需评估节流吞没风险

## 3. 进度点设计

### 3.1 GenericAgent — research（DATA_COLLECTION，代码路径 L316-494）

| 时机 | 消息（f-string 表达式） | action | 位置 & 保护条件 |
|------|------------------------|--------|----------------|
| Tier 1 完成后（L368 之后） | `f"结构化数据库查询完成，获取 {len(data_points)} 条数据"` | searching | 在 Tier 1 循环（L338-367）之后，Tier 2 搜索之前 |
| Tier 2 搜索完成后（L407 之后） | `f"网络搜索完成，共 {len(data_points)} 条数据"` | searching | 在 `search_skill` 块（L386-406）之后、`news_search` 之前；仅在 `if "search_skill" in web_skills and skill_registry:`（L386）内 |
| news_search 完成后（L437 之后） | `f"补充 {len(news_result.get('results', []))} 条新闻数据"` | searching | 在 L437 `logger.info` 之后；仅在 `if news_result and news_result.get('success'):`（L417）时发送 |

**不添加的点**：
- Tier 1 每个 DB 查询前 — 1-2 秒内完成，逐条无感知价值，且会被 session 级 200ms 节流吞掉
- Tier 2 搜索前 — 已有入口消息 "Searching web sources..."

### 3.2 GenericAgent — quality-check（DATA_VALIDATION，代码路径 L496-573）

| 时机 | 消息（f-string 表达式） | action | 位置 & 保护条件 |
|------|------------------------|--------|----------------|
| 验证完成后（L508 之后） | `f"数据验证完成，{validation_result['total_validated']}/{validation_result['total_input']} 通过，质量={validation_result['average_quality_score']}"` | analyzing | 在 `logger.info`（L503-508）之后、冲突处理前（L509）；仅在 `if data_points:`（L501）内。**节流风险**：验证完成和冲突解决可能 <200ms，第二条可能被节流吞掉 |
| 冲突解决后（L518 之后） | `f"解决 {len(resolved_conflicts)} 个数据冲突"` | analyzing | 在 L518 `logger.info` 之后；仅在 `if resolved_conflicts:`（L515）时发送 |
| 重收集后（L557 之后） | `"低质量数据，已重新搜索补充"` | searching | 在 `try/except` 块结束后（L557 之后）；仅在 `if recollection_attempted:` 时发送。**注意**：`recollection_attempted = True`（L550）在 `try` 内，若 `except`（L556）则仍为 `False`，需在 `try/except` 之后用 `if recollection_attempted:` 保护 |

### 3.3 GenericAgent — analysis（DEEP_ANALYSIS，代码路径 L575-746）

| 时机 | 消息（f-string 表达式） | action | 位置 & 保护条件 |
|------|------------------------|--------|----------------|
| 搜索降级后（L604 之后） | `f"无上游数据，降级搜索获取 {len(aggregated_data_points)} 条"` | searching | 在 L604 `logger.info` 之后；仅在降级搜索块内（L583-604，`if not aggregated_data_points and "search_skill" in self._available_skills and self._skill_registry:`） |
| 知识缺口检测后（L702 之后） | `f"检测到 {len(gaps)} 个知识缺口，补充搜索中..."` | searching | 在 L702 `logger.info` 之后、`_supplementary_search_for_gaps`（L703）之前；仅在 `if gaps:`（L701）时 |
| 补充搜索+修订完成后（L734 之后） | `"基于补充数据修订分析"` | writing | 在 L734 `logger.info` 之后；仅在 `if supp_result and supp_result.get('data_points'):`（L707）时 |
| 自评完成后（L741 之后） | `f"自评完成，得分 {eval_result['score']}/100"` | analyzing | 在 L741 `result["self_evaluation"] = eval_result` 之后；仅在 `if max_self_eval > 0 and result.get("success") and result.get("content"):`（L738）时 |

**不添加的点**：
- LLM 调用前 — 此路径没有 "Generating analysis for..." 消息（该消息在 synthesis 路径 L862/865），无需新增
- 规范数据注入 — 内部步骤，用户无需知道

### 3.4 GenericAgent — synthesis/数据富集（代码路径 L800-931）

此路径处理有前序数据（`aggregated_data_points` 或 `aggregated_content`）的 Agent（如 synthesis 类型），已有 2 行 `_report_progress`（L862、L865）覆盖 LLM 调用前。

| 时机 | 消息 | action |
|------|------|--------|
| 各步骤间 | 不添加 | 现有 2 行（L862、L865）已覆盖 LLM 前进度，数据构建和规范注入为内部步骤 |

### 3.5 GenericAgent — calibration（代码路径 L749-792）

| 时机 | 消息 | action | 位置 |
|------|------|--------|------|
| 入口（L749 之后） | `"校准跨章节数值一致性..."` | analyzing | `if agent_category == "calibration":` 块内第一行 |

### 3.6 GenericAgent — 默认路径搜索 fallback（代码路径 L943-964，所有 category 不匹配且无前序数据时的兜底路径）

| 时机 | 消息（f-string 表达式） | action | 位置 & 保护条件 |
|------|------------------------|--------|----------------|
| 搜索完成后（L950 之后） | `f"搜索完成，获取 {_total_search_results} 条结果"` | searching | 在 `_do_deep_research`（L945-950）之后；仅在 `if topic and "search_skill" in available_skills:`（L944）时。`_total_search_results = sum(len(s.get('results',[])) for s in (search_results or {}).get('searches',[]))` |

### 3.7 ReportGenerationAgent

| 时机 | 消息 | action |
|------|------|--------|
| 各步骤间 | 不添加 | 报告生成步骤（cover/toc/summary/body/conclusion/appendix）均在 1 秒内完成，无感知延迟 |

**理由**：ReportGenerationAgent 的各步骤是纯字符串拼接，不涉及 LLM 调用或网络请求，耗时极短。入口消息已足够。

### 3.8 QualityCheckAgent

| 时机 | 消息 | action |
|------|------|--------|
| 各检查项间 | 不添加 | 质量检查项在 1-2 秒内完成，且已有 `push_section_quality` SSE 事件推送详细进度 |

**理由**：QualityCheckAgent 已通过 `SessionStreamer.push_section_quality()`（`session_streamer.py:314`）和 `push_quality_result()`（`session_streamer.py:296`）推送细粒度进度，无需再通过 `_report_progress` 重复。

### 3.9 DataCollectionAgent（fixed_agents）

| 时机 | 消息 | action |
|------|------|--------|
| 各数据源间 | 不添加 | 每个 source 查询极快，且入口消息已足够 |

## 4. 消息洪泛风险评估

节流机制：`SessionStreamer.push_agent_message()` 对同一 session 内非 heartbeat 消息实施 200ms 节流（`session_streamer.py:251-255`）。各进度点之间通常有秒级间隔（搜索 2-5s、LLM 调用 10-30s），不受节流影响。仅 sub-second 级连续操作（如验证+冲突解决在同一同步块内）的连续消息可能被节流吞掉第二条。

| 场景 | 理论消息数 | 节流后实际数 | 风险 |
|------|-----------|-------------|------|
| research（Tier1汇总 + web汇总 + news汇总） | 3 | 3（各间隔 >2s） | 低 |
| quality-check（验证 + 冲突 + 重收集） | 1-3 | 1-2（验证+冲突 <200ms 时第二条被吞；重收集 >2s 不受影响） | 低 |
| analysis（降级搜索 + 缺口 + 修订 + 自评） | 0-4 | 0-4（各间隔 >1s） | 低 |
| calibration | 1 | 1 | 无 |
| synthesis/数据富集 | 0（不新增） | 0 | 无 |

最坏情况：单个 analysis Agent 在所有条件分支均触发时最多产生 **4 条**内部消息（节流后仍为 4 条，因为各消息间隔 >1s）。加上 engine.py 的启停消息（2 条/agent）和心跳（1 条/15s），用户在 2-3 分钟内单 Agent 最多看到约 **7 条**消息（4 内部 + 2 启停 + 1 心跳），前端通知栏可正常展示。不同 category 的 Agent 不在同一 batch 中并行，不会叠加显示。

## 5. 实施清单

| 文件 | 改动行数 | 说明 |
|------|---------|------|
| `src/core/agents/generic_agent.py` | ~15-20 行 | research 3 处 + quality-check 3 处 + analysis 4 处 + calibration 1 处 + fallback 1 处（含条件保护的额外行）。synthesis 路径不新增。 |
| 其他 Agent | 0 行 | 不添加 |

总计约 15-20 行新增，零风险。
