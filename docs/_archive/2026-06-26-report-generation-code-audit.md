# v2 代码实现深度审计

> 日期：2026-06-26
> 审计对象：v2 代码实现（7个.py + 9个.tmpl）

## 审计结论

代码实现与v2设计文档对齐，发现 **7个缺陷**（1 CRITICAL / 3 HIGH / 3 MEDIUM），已全部修复。123个单元测试全部通过。

| # | 等级 | 文件 | 缺陷 | 修复 |
|---|------|------|------|------|
| A1 | CRITICAL | data_repair.py | `repair_gap` 搜索query缺少topic前缀，与v2设计不一致 | 改为 `f"{topic} {gap.metric} {' '.join(gap.search_keywords[:3])}"` |
| A2 | HIGH | data_repair.py | `ConflictResolver.resolve()` 高权威分支未设置 `chapters_to_update`，冲突修正不生效 | 补充 `chapters_to_update` 计算 |
| A3 | HIGH | data_repair.py | `_resolve_by_search` 中 `self._scraper` 可能为None但直接调用 | 增加 `if self._scraper is None` 分支，fallback到搜索摘要 |
| A4 | HIGH | data_repair.py | `_parse_extraction` 使用简单 `json.loads` 而非 `re.search` 提取JSON | 改为 `re.search(r'\{[^{}]*\}', raw, re.DOTALL)` |
| A5 | MEDIUM | data_repair.py | `self._pm` 属性名与其他Agent的 `self._prompts` 不一致 | 统一为 `self._prompts` |
| A6 | MEDIUM | orchestrator.py | `_checkpoint_chapter` 中 `mkdir()` 是同步调用，阻塞事件循环 | 将 `mkdir` + `write_text` 合并到 `_write_checkpoint()` 中用 `asyncio.to_thread` 执行 |
| A7 | MEDIUM | v2文档 | C1修复过度：`get_framework_config` 是模块级便捷函数，原版 `from ... import get_framework_config` 是对的 | 恢复为模块级导入 |

## 集成验证

### 真实代码环境对齐

| 对接点 | 真实代码 | 实现代码 | 状态 |
|--------|---------|---------|------|
| LLM接口 | `llm_skill.execute(prompt=, model=, max_tokens=, temperature=)` → `{"success": bool, "content": str}` | `self._llm.execute(prompt=, max_tokens=, temperature=)` | ✅ 对齐 |
| 搜索接口 | `search_skill.execute(query=, max_results=)` → `{"success": bool, "results": [{"href": str, "body": str}]}` | `self._search.execute(query=, max_results=)` + `item.get("href")` | ✅ 对齐 |
| Skill获取 | `self._skill_registry.get("llm_skill")` | 集成代码中使用相同方式 | ✅ 对齐 |
| AggregationResult | 对象含 `layered_content`, `content_provenance`, `sources`；`to_dict()` 不含前两者 | `generate_report()` 直接接收对象，`getattr` 访问属性 | ✅ 对齐 |
| ContentProvenance | dataclass 含 `section_target` 属性 | `hasattr(provenance, 'section_target')` + `isinstance(provenance, dict)` 双路径 | ✅ 对齐 |
| ResearchFrameworkConfig | 无 `to_dict()` 方法 | 集成代码中手动逐字段序列化 | ✅ 对齐 |
| get_framework_config | 模块级便捷函数（L279） | `from ... import get_framework_config` | ✅ 对齐 |
| routing_result.task_structure | `TaskStructure` 对象含 `.sections`，`.to_dict()` 序列化 | 集成代码中 `routing_result.task_structure.to_dict()` | ✅ 对齐 |
| 输出格式 | `{"topic", "title", "aspects", "sections", "sources", "key_findings"}` | `_assemble_final_report()` 产出相同结构 | ✅ 对齐 |

### 测试覆盖

| 模块 | 测试数 | 状态 |
|------|--------|------|
| models.py | 24 | ✅ |
| data_registry.py | 19 | ✅ |
| prompt_manager.py | 8 | ✅ |
| chapter_writer.py | 12 | ✅ |
| chapter_reviewer.py | 7 | ✅ |
| global_reviewer.py | 13 | ✅ |
| data_repair.py | 19 | ✅ |
| orchestrator.py | 21 | ✅ |
| **总计** | **123** | **全部通过** |

## 系统集成

### 已完成的集成点

| 集成点 | 文件 | 行号 | 状态 |
|--------|------|------|------|
| `_research_with_routing()` | `src/core/orchestrator/orchestrator.py` | ~L1972 | ✅ 已改造，try/except fallback |
| `research()` | `src/core/orchestrator/orchestrator.py` | ~L967 | ✅ 已改造，try/except fallback |

### 集成策略

采用 **try/except fallback** 模式：
- **主路径**：尝试使用 ReportOrchestrator 生成框架驱动报告
- **回退路径**：如果升级模块失败（import失败、LLM不可用等），自动降级为原有的 `aggregated.to_dict()` 机械组装

这确保了：
1. 升级模块的任何问题不会阻塞整个报告生成流程
2. 可以通过日志区分两条路径的执行情况
3. 渐进式上线：初期可观察 fallback 频率，逐步修复问题

### 两个集成点的差异

| | `_research_with_routing()` | `research()` |
|---|---|---|
| task_structure | ✅ 从 `routing_result.task_structure.to_dict()` 获取 | ⚠️ 无routing_result，传空dict |
| framework_config | ✅ 从 `get_framework_config()` 获取 | ✅ 同上 |
| aggregated_result | ✅ 直接传 AggregationResult 对象 | ✅ 同上 |
| fallback | `aggregated_dict` 手动构建 | `aggregated.to_dict()` |

**注意**：`research()` 非路由路径传 `task_structure={}`，此时 ReportOrchestrator 会从 `aggregated_result` 的 `layered_content` 推断章节结构，功能不受影响。

```
src/agents/fixed_agents/report_upgrade/
├── __init__.py
├── models.py              # 138行 - 13个dataclass
├── data_registry.py       # 99行 - DataRegistry
├── prompt_manager.py      # 39行 - PromptManager
├── prompts/               # 9个.tmpl模板文件
│   ├── chapter_write.tmpl
│   ├── chapter_rewrite.tmpl
│   ├── chapter_patch_data.tmpl
│   ├── chapter_review.tmpl
│   ├── global_review.tmpl
│   ├── global_verify_issues.tmpl
│   ├── data_extraction.tmpl
│   ├── conflict_resolution.tmpl
│   └── exec_summary.tmpl
├── chapter_writer.py      # 118行 - ChapterWriter
├── chapter_reviewer.py    # 63行 - ChapterReviewAgent
├── global_reviewer.py     # 136行 - GlobalReviewAgent + serialize_report_for_review
├── data_repair.py         # ~240行 - DataRepairAgent + ConflictResolver
└── orchestrator.py        # 588行 - ReportOrchestrator + RetryPolicy

tests/unit/report_upgrade/
├── __init__.py
├── test_models.py
├── test_data_registry.py
├── test_prompt_manager.py
├── test_chapter_writer.py
├── test_chapter_reviewer.py
├── test_global_reviewer.py
├── test_data_repair.py
└── test_orchestrator.py
```
