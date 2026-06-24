# 代码审查报告 — v1.0.2 修复后全面审查（二次核实终版）

**日期**: 2026-06-12  
**审查范围**: engine.py (2795行), result_aggregator.py (1523行), research_result_store.py (593行)  
**审查背景**: v1.0.2 修复了 R1/R2/R3 三大根因后，生产环境仍出现全部 8 个章节为占位符的问题。深入审查发现更多隐藏缺陷。  
**核实方法**: 56 个行号引用逐一对照源码核实，勘误报告中的 3 处自身错误已修正。

---

## 一、审查结论摘要

| 严重级别 | engine.py | result_aggregator.py | research_result_store.py | 合计 |
|----------|-----------|---------------------|------------------------|------|
| **P0 (致命)** | 1 | 2 | 2 | **5** |
| **P1 (重要)** | 9 | 5 | 6 | **20** |
| **P2 (次要)** | 8 | 15 | 8 | **31** |

**最关键的 5 个 P0 问题必须立即修复**，否则生产环境仍会出现数据丢失/内容错配。

---

## 二、P0 致命问题详解

### P0-1: engine.py — dispatch 失败的 agent_result 被静默丢弃

**位置**: `engine.py` 约line 2219-2223  
**核实**: ✅ `error_result` 被创建后未 append 到 `batch_results`，也没有调用 `scheduler.mark_failed()`  
**现象**: 当 `dispatch_task` 抛异常时，`error_result` 被创建但**从未 append 到 batch_results**。该 agent 从结果中消失，scheduler 也不会收到 mark_failed。  
**影响**: 失败的 agent 静默丢失，下游 QC、all_results、stage_results 均不感知。  
**修复**: 在 except 块中 `batch_results.append(error_result)` 并调用 `scheduler.mark_failed(agent_id, error_result)`。

### P0-2: result_aggregator.py — `_normalize_key` 双向子串匹配导致内容交叉污染

**位置**: `result_aggregator.py` lines 380-382, 409-411, 599-601 (三处归一化匹配)  
**核实**: ✅ 三处均使用 `norm_id in norm_key or norm_key in norm_id` 双向子串匹配  
**现象**: 匹配逻辑使用双向子串包含检查，导致 `"market"` 匹配 `"market_size_analysis"`，`"trend"` 匹配 `"trend_and_policy"`。  
**影响**: **内容被分配到错误的章节**，产生数据交叉污染。  
**修复**: 将双向子串匹配改为仅允许短 key 被长 section_id/name 包含（`norm_key in norm_id or norm_key in norm_name`），不允许 section_id/name 被短 key 部分匹配。

### P0-3: result_aggregator.py — 索引映射 `phase_N_agent_M → section[M]` 可能错配

**位置**: `result_aggregator.py` lines 417-446  
**核实**: ✅ 索引映射假设 `phase_2_agent_0` → section_details[0]  
**现象**: 假设 `phase_2_agent_0` 对应 section_details[0]，但 Phase1 和 Phase2 的 agent 数量可能不同，索引不保证对应。  
**当前生产环境**: 8 个 Phase1 + 8 个 Phase2 agent 对应 8 个 section，恰好一一对应。  
**风险场景**: 如果某些 section 不需要 Phase1 agent（或 Phase2 agent），索引就会错位。  
**影响**: 内容被静默分配到错误的章节。  
**修复**: 使用 `_section_id`（已从 aspects 索引注入）进行 provenance 匹配，索引映射仅作为最后回退且需校验 agent category 与 section 的一致性。

### P0-4: research_result_store.py — 每次保存都覆盖 metadata，销毁 created_at 等字段

**位置**: `research_result_store.py` lines 341-351  
**核实**: ✅ 每次 `save_result` 都创建全新的 `ResearchResultMeta`，不加载已有 metadata  
**现象**: 每次 `save_result` 都创建全新的 `ResearchResultMeta`，`created_at` 被重置为 `datetime.now()`，`generated_formats`、`document_requests`、`document_paths` 被清空。  
**影响**: 增量保存时所有累积元数据丢失。已生成的文档记录被清除。  
**修复**: 加载已有 metadata 并合并更新，而非从零创建。

### P0-5: research_result_store.py — 并发保存的 TOCTOU 竞态条件

**位置**: `research_result_store.py` lines 276-338  
**核实**: ✅ 无任何锁机制，非原子的 read-merge-write 序列  
**现象**: `save_result` 执行非原子的 read-merge-write 序列，无文件锁/线程锁。engine.py 和 generic_agent.py 可并发调用。  
**影响**: 并发保存导致数据静默丢失。  
**修复**: 添加线程锁（`threading.Lock` per task_id），或使用文件锁。

---

## 三、P1 重要问题详解

### engine.py 的 P1 问题

| # | 位置 | 问题 | 影响 | 核实 |
|---|------|------|------|------|
| E-P1-1 | line 776-782 | `_build_report_task` 中 dict content 被 `isinstance(content, str)` 检查静默跳过 | 报告缺失该 agent 内容 | ✅ |
| E-P1-2 | line 1705-1711 vs 1345-1346 | `mark_completed/mark_failed` 被 `_execute_agents_batch` 和调用方各调用一次 | 可能双重计数/重复事件 | ✅ |
| E-P1-3 | line 1149-1160 | 缓存结果的 dict content 导致 `content[:50000]` TypeError | 运行时崩溃（恢复/续跑时触发） | ✅ |
| E-P1-4 | line 1739-1743 | `has_content` 跳过 dict content（仅统计 str），QC 路由到错误 checker | 分析阶段被当作数据采集阶段检查 | ✅ |
| E-P1-5 | line 2320-2326 | `batch_completed` 中 `r.get("section_id","")` 为空（section_id 在 `_execute_batch` 返回后才在调用方 line 1343 注入） | 恢复/续跑无法匹配 agent 到章节 | ✅ |
| E-P1-6 | line 2317 | `agent_contents` 同样通过 `r.get("section_id","")` 取值，为空 | 同上 | ✅ |
| E-P1-7 | line 2604-2615 | `_get_section_id_from_agent_id` 用 `isdigit()` 判断索引，不识别十六进制 ID（如 `inject_市场规模_a1b2c3d4` 返回 `a1b2c3d4`） | section_id 为 UUID 而非章节名 | ✅ |
| E-P1-8 | line 2604-2615 vs 555-596 | `_get_section_id_from_agent_id`（用 `isdigit()`）与 `_extract_aspect_from_agent_id`（用 hex 判断）解析逻辑不一致 | 同一 agent_id 两种解析结果 | ✅ |
| E-P1-9 | line 1533-1542 | pending_unlocked agents 的结果缺少 section_id 注入 | 解锁 agent 的内容无法匹配到章节 | ✅ |

> **E-P1-5/E-P1-6 调用链说明**: `execute_with_scheduler`(line 1318) → `_execute_agents_batch`(line 1697) → `_execute_batch`(line 1849, 持久化在 line 2265+)。section_id 注入在 line 1343，发生在 `_execute_batch` 返回之后，因此持久化时 `r.get("section_id","")` 始终为空。

### result_aggregator.py 的 P1 问题

| # | 位置 | 问题 | 影响 | 核实 |
|---|------|------|------|------|
| A-P1-1 | line 32 | `_normalize_key` 去除 `section_\d+_` 前缀导致同名不同编号的 section 碰撞 | 如 section_0_趋势 和 section_1_趋势 归一化后相同 | ✅ |
| A-P1-2 | line 978-979 | `_determine_section_target` 对 data_collection 返回 `"data"` | 无任何 section id 为 "data"，provenance 匹配永远失败 | ✅ |
| A-P1-3 | line 975 | `_determine_section_target` 默认返回 `"analysis"` | 无 section id 为 "analysis"，provenance 匹配永远失败 | ✅ |
| A-P1-4 | line 280-282 | content_map 同时存原始大小写和 lowercase key | matched_key 可能是原始或 lowercase，导致 used_keys 追踪不一致（主要影响英文章节 ID） | ✅ |
| A-P1-5 | line 1055 | data_points 格式化截断 80 项，日志仅记录格式化数量不记录截断 | 大量数据点被静默丢弃且无截断提示 | ✅ |

> **已移除项**: 原 A-P1-1（`_to_str` 循环内重定义）降级为 P2（无闭包风险，仅代码风格）；原 A-P1-3（batch stage 重复）经核实代码逻辑保证不会产生重复（初始列表为固定名称、batch_stages 为 batch_N 格式、第三列表用 `not in` 过滤），标记为不成立并移除。

### research_result_store.py 的 P1 问题

| # | 位置 | 问题 | 影响 | 核实 |
|---|------|------|------|------|
| S-P1-1 | line 285-303 | data_points/sources 仅按 URL 去重，无 URL 的项累积重复 | 结果文件膨胀 | ✅ |
| S-P1-2 | line 329-330 | sections/key_findings 不合并，直接覆盖 | engine.py 传空 sections 时销毁已有数据 | ✅ |
| S-P1-3 | line 327-328 | title/topic 被新值覆盖（可能为空） | 原始标题/主题丢失 | ✅ |
| S-P1-4 | line 320 | agent_contents.update() 静默覆盖 | 重试 agent 的部分保存覆盖完整内容 | ✅ |
| S-P1-5 | line 242-245 | _atomic_write_json 清理可能掩盖原始异常 | 错误诊断困难 | ✅ |
| S-P1-6 | line 338-351 | result.json 和 metadata.json 非原子写入 | result.json 写入成功后 metadata.json 写入失败将导致不可恢复的不一致状态 | ✅ |

---

## 四、P2 次要问题

### engine.py (8 个)

| # | 问题 | 核实 |
|---|------|------|
| E-P2-1 | `_extract_aspect_from_agent_id` 短 ID（<6字符字母数字，如 `12abc`）处理错误，不识别为索引 | ✅ |
| E-P2-2 | `_check_stage_quality` dict content 的 `str(dict)` 字符数包含 Python repr 语法开销（花括号/引号/逗号），不反映真实内容长度，误导质量指标 | ✅ 修正描述 |
| E-P2-3 | cache-hit 路径中 content_lock 跳过的 agent 记入 errors 但不存入 stage_results | ✅ |
| E-P2-4 | `_build_report_task` 定义两次（line 613 是死代码，line 724 是实际定义） | ✅ |
| E-P2-5 | `_extract_raw_output` 中空列表 `[]` 被 or 链跳过；非空列表也可能被前面字段短路 | ✅ 补充说明 |
| E-P2-6 | calibration gate 用 `deepcopy(all_results)` 后替换 all_results 变量，实践中不丢数据但增加了不必要的内存开销 | ✅ 修正描述 |
| E-P2-7 | `_merge_retry_results` 仅替换第一个匹配 agent_id 的条目，重复 agent_id 时遗漏 | ✅ |
| E-P2-8 | `_execute_stage_with_quality` 调用 `self.quality_executor.execute_with_retry` 但 quality_executor=None（dead code + latent crash） | ✅ 补充 latent crash |

### result_aggregator.py (15 个)

| # | 问题 | 核实 |
|---|------|------|
| A-P2-1 | `_to_str` 偏好英文（`en`）而非中文（`zh`），与中文系统不符 | ✅ |
| A-P2-2 | `_normalize_key` 无 Unicode 归一化，全角/半角字符可能不匹配 | ✅ |
| A-P2-3 | provenance 和传统路径使用独立的 `used_keys` 集合，互不感知 | ✅ |
| A-P2-4 | `extract_content` depth=0 时可能泄露 `priority`、`timestamp`、`metadata` 等内部字段到报告 | ✅ |
| A-P2-5 | `_merge_values` 对 dict 用 `update()` 静默覆盖，无冲突日志 | ✅ |
| A-P2-6 | `_deduplicate` 仅处理列表值，不处理跨 key 的字符串重复 | ✅ |
| A-P2-7 | `_normalize_key` 中局部变量 `result` 与函数概念混淆 | ✅ |
| A-P2-8 | `_strip_parsed_subsections` 去除标题后只跳过一个空行，可能产生不一致空白 | ✅ |
| A-P2-9 | `_extract_stage_from_agent_id` 中 `"market"` 关键词过宽，数据采集 agent 被误分为 analysis | ✅ |
| A-P2-10 | 浮点数精确相等比较 (`set()`) 导致假冲突报告 | ✅ |
| A-P2-11 | `to_dict()` 副作用修改 `self.data` | ✅ |
| A-P2-12 | `_content_from_dict_str` 标志在 early continue 时可能泄漏到下一迭代（当前安全但脆弱） | ✅ |
| A-P2-13 | 索引回退仅处理 `phase_{1,2}_agent_` 前缀，不处理 `phase_3_` 等新格式 | ✅ |
| A-P2-14 | `_to_str` 在循环内每次迭代重新定义（无闭包风险，仅代码风格问题） | ✅ 从 P1 降级 |
| A-P2-15 | `_determine_section_target` synthesis 默认返回 `"summary"`（line 960），当 synthesis 内容应去 "conclusion" 时会被错误分配到 "summary" | ✅ 新增遗漏 |

### research_result_store.py (8 个)

| # | 问题 | 核实 |
|---|------|------|
| S-P2-1 | `load_result` 吞掉 `InvalidTaskIdError` 返回 None，与"未找到"不可区分 | ✅ |
| S-P2-2 | `list_results` 在排序前应用 limit，可能遗漏比已选子集更新的结果 | ✅ 修正描述 |
| S-P2-3 | 路径遍历检查用 `startswith` 无分隔符，理论上可被前缀相似路径绕过（受 regex 限制实际安全） | ✅ |
| S-P2-4 | `if status:` 应为 `if status is not None:`，假值 status 被忽略 | ✅ |
| S-P2-5 | data_points/sources 合并无上限，可无限增长 | ✅ |
| S-P2-6 | `completed_at` 在非 COMPLETED 状态保存时丢失（与 P0-4 同根因） | ✅ |
| S-P2-7 | 无孤立 `.tmp_*` 文件清理机制 | ✅ |
| S-P2-8 | `save_result` 不验证 `result` 参数类型，非 dict 输入导致深层 AttributeError | ✅ |

---

## 五、数据流全景问题图

```
Agent执行 → batch_results → [section_id注入(在调用方!)] → all_results → aggregator
                ↓                                           ↓
          ResearchResultStore                    layered_content + provenance
          (section_id尚未注入! → 为空!)                  ↓
                                           section匹配（3层可能全失败）
                                                ↓
                                           占位符内容
```

**关键断裂点**:

1. **section_id 注入时机错误**: 在 `_execute_batch` 内部持久化时（line 2265+）section_id 尚未注入（注入在 line 1343，`_execute_batch` 返回之后）→ 存储的数据缺少映射
2. **provenance 匹配失效**: `_determine_section_target` 返回 `"data"`/`"analysis"` 等不存在的 id
3. **归一化匹配过宽**: 双向子串匹配导致内容交叉污染

> 注: layer 匹配名不匹配问题已在 v1.0.2 中修复，且经核实代码逻辑保证不会产生重复（A-P1-3 原报告不成立）。

---

## 六、修复优先级建议

### 立即修复（阻塞生产）

| 优先级 | 问题 | 预计工作量 |
|--------|------|-----------|
| **1** | P0-2: 归一化匹配改为单向包含（仅 `norm_key in norm_id/name`） | 2h |
| **2** | P0-4: metadata 合并而非覆盖 | 1h |
| **3** | P0-1: dispatch error_result append + mark_failed | 0.5h |
| **4** | E-P1-3: 缓存 dict content 在 `content[:50000]` 前转 str | 0.5h |
| **5** | E-P1-5/E-P1-6: section_id 注入移到 _execute_batch 内部（持久化之前） | 1h |
| **6** | A-P1-2/A-P1-3: `_determine_section_target` 返回 key 本身而非固定字符串 | 1h |
| **7** | E-P1-1/E-P1-9: dict content 在报告和 unlocked agents 中转 str | 1h |

### 短期修复（1周内）

| 优先级 | 问题 | 预计工作量 |
|--------|------|-----------|
| 1 | P0-3: 索引映射添加验证（检查 category 一致性） | 1h |
| 2 | P0-5: 并发保存加锁 | 2h |
| 3 | E-P1-4: has_content 中 dict content 转 str 后计入 | 0.5h |
| 4 | S-P1-2: sections/key_findings 合并逻辑 | 1h |
| 5 | A-P1-4: content_map 和 used_keys 统一使用 lowercase | 1h |
| 6 | A-P1-5: data_points 截断时记录总数 | 0.5h |

### 中期修复（2周内）

- E-P1-7/E-P1-8: 统一 agent_id 解析逻辑
- S-P1-1: data_points 按内容去重（非仅 URL）
- A-P1-1: _normalize_key 保留 section 编号
- E-P1-2: 消除 mark_completed 双重调用
- 所有 P2 问题

---

## 七、v1.0.2 已修复问题回顾

| 修复 | 状态 | 遗留问题 |
|------|------|---------|
| R2: 缩进修复 | ✅ 正确 | 无 |
| R1: data_points 格式化 | ✅ 正确 | 无（仅 `len < 100` 时替换，非无条件） |
| R1-additional: QC crash | ✅ 正确 | E-P1-4: has_content 仍跳过 dict |
| R3: agent_contents filter | ✅ 正确 | E-P1-5: section_id 注入时机 |
| ResearchResultStore merge | ⚠️ 部分正确 | P0-4: metadata 覆盖; S-P1-2: sections 不合并 |
| layer 匹配修复 | ✅ 正确 | 无（A-P1-3 原报告不成立） |
| _section_id aspects 映射 | ⚠️ 部分正确 | P0-3: 索引可能错配 |
| 索引回退映射 | ⚠️ 临时方案 | P0-3: 需要验证逻辑 |
| content dict→str 转换（6处） | ✅ 正确 | E-P1-1/E-P1-3 仍有遗漏 |
