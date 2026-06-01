# Zensers v1.0.0 发布前清理计划（审查版）

> 生成日期：2026-05-13 | 版本：v1.0.0
> 数据目录总大小：~1.64 GB | 总文件数：~6,600
> 审查状态：已审查 ✅

---

## 总执行策略

```
Phase 0: 修复代码 Bug（必须先做）
  ├── Fix 1: agent_coordinator.py:558 registries_dir 误用
  └── Fix 2: HistoryCompressor user_id=None → "None" 目录

Phase A: 安全清理项（无数据丢失风险，立即执行）
Phase B: registries 修复后迁移合并，再清理冗余
Phase C: 归档 docs/ 历史文档
Phase D: 更新使用手册 + 全面运行测试
```

---

## 一、根目录文件

### 1.1 测试/临时脚本 — 审查结论：✅ 清理

| 文件 | 大小 | 理由 |
|------|------|------|
| `test_dialog.py` | 1.4 KB | pytest.ini 的 testpaths = tests 限定，根目录这些文件不被任何框架引用 |
| `test_export_function.py` | 5.3 KB | 同上 |
| `test_fixes.py` | 4.7 KB | 同上 |
| `test_framework_sections.py` | 4.2 KB | 同上 |
| `test_persona_engine.py` | 20.4 KB | 同上 |
| `test_save_dialog.py` | 6.5 KB | 同上 |
| `tmp_check_countries.py` | 0.5 KB | 临时脚本 |
| `tmp_test.py` | 1.5 KB | 临时脚本 |
| `verify_fixes.py` | 3.8 KB | 修复验证，已完成使命 |
| `run_tests.bat` | 0.2 KB | 未在 Makefile/CI 中引用 |

### 1.2 入口文件 — 审查结论：⚠️ 保留

| 文件 | 大小 | 理由 |
|------|------|------|
| `zensers.py` | 0.2 KB | CLI 入口 — `from cli.main import main`，与 `python -m src.cli.main` 并存是合理设计 |
| `desktop_app.py` | 16.5 KB | 543 行的完整 pywebview 桌面启动器，引用 icon.ico、WEB_DIR 等资源，属于项目功能模块 |

### 1.3 根目录日志/输出 — 审查结论：✅ 清理

- `pyresult.txt`（0 KB，空文件）
- `test_results.txt`（0.4 KB）
- `test_server.log`（0.1 KB）
- `test_server_err.log`（8.5 KB）→ 共 4 文件

### 1.4 根目录大文件/杂项 — 审查结论：补充发现

审查补充了 4 项遗漏：

| 文件 | 大小 | 源代码引用？ | 审查结论 |
|------|------|------------|---------|
| `WVS_Cross-National_Wave_7_csv_v6_0.csv` | **181.67 MB** | 仅 `scripts/convert_wvs_to_benchmark.py`（一次性转换脚本）；应用代码 `src/` 零引用；输出产物 `data/benchmarks/wvs_data.json`（480 KB）已生成 | 移入 `_cleanup_temp/` 或直接删除 |
| `Logo.psd` | 5.43 MB | 无运行时引用（Photoshop 源文件） | 移入 `_archive/` |
| `models` | 31 字节 | 内容为 "Authentication Fails (governor)"，疑似调试遗留产物 | 清理 |
| `test_resp1.json` | 197 字节 | 测试响应文件 | 清理 |

**说明：** CSV 是清理计划中最严重的遗漏——182 MB 占整个项目可回收空间的 ~10%。转换脚本运行一次后不再需要原始 CSV。

### 1.5 根目录分析/计划文档 — 审查结论：✅ 归档到 docs/_archive/

15 个 .md 文件，~192 KB，已完成使命。

---

## 二、docs/ 文档目录

### 2.1 生产文档 — 审查结论：ℹ️ 保留

| 文件 | 说明 |
|------|------|
| `README.md` | 文档索引 |
| `API.md` | API 文档 |
| `CHANGELOG.md` | 变更日志 |
| `ROADMAP.md` | 路线图 |
| `QUICK_START.md` | 快速开始 |
| `ARCHITECTURE_DESIGN.md` | 架构设计 |
| `AGENT_ARCHITECTURE.md` | Agent 架构 |
| `AGENT_SESSION_MANAGEMENT.md` | 会话管理 |
| `PROMPT_API.md` | Prompt API |
| `SYSTEM_USAGE_GUIDE.md` | 系统使用手册 **（需更新）** |
| `VERSION_MANAGEMENT_AND_UPGRADE_DESIGN.md` | 版本管理设计 |
| `SECURITY_OPTIMIZATION_TODO.md` | 安全优化 TODO |
| `NAVIGATION/`（5 文件） | 文档导航系统 |

### 2.2 历史诊断/修复文档 — 审查结论：✅ 归档（优先级低）

~25-30 个文件，全部为开发周期中的事故/修复文档。仅回收 ~1.5 MB，优先级低于 data/ 清理。

### 2.3 docs/STATUS/ — 审查结论：✅ 归档（优先级低）

23 个事故/审计报告文件。

### 2.4 设计提案 — 审查结论：✅ 归档

~20 个文件，包含前端设计、UI 对比、提案文档等。

### 2.5 superpowers/specs/ — 审查结论：ℹ️ 保留最新终版

8 个知识模块设计文件，保留 `-deep-analysis.md` 终版，其余归档。

### 2.6 其他文档 — 审查结论：✅ 归档/清理

| 路径 | 审查结论 |
|------|---------|
| `development/`（2 文件） | 归档 |
| `research_results/`（24 json） | 清理 |
| `CHANGES_20260425.md` | 归档 |
| `cleanup-plan.md` | 归档（本计划替代） |

---

## 三、data/ 运行时数据 — 最关键

### 3.1 `data/registries/` — 审查结论：🚨 先修 Bug 再清理

**审查发现的关键模式：**

- 87 个文件同时存在于顶层和嵌套目录 — 全部 87 个案例中，嵌套文件比顶层大 **1000~735,000 倍**
  - 顶层 ~5 KB（小存根）
  - 嵌套层包含完整会话数据
- 5 个文件仅存在于嵌套目录
- 103 个文件仅存在于顶层目录
- **两套数据各有独立内容，不能简单删除任一套**

**Bug 根因确认：**

`src/core/orchestrator/execution/coordinator/agent_coordinator.py:558`：
```python
storage_path = Path(getattr(settings.system, 'registries_dir', 'data/registries'))
```
将 `registries_dir` 的值当做 `storage_path` 传入 `AgentSessionRegistry.save()`，而 `agent_session.py:481` 的 `save()` 执行 `storage_path / "registries" / filename`，导致 `data/registries/registries/` 嵌套。

**修复方案：**
1. 修复 `agent_coordinator.py:558` — 传 `storage_path="data"` 而非 `registries_dir`
2. 修复前两套数据都不能删除
3. 修复后，系统运行时自动将新数据写入正确路径
4. 编写迁移脚本将嵌套数据同步回正确位置，再清理重复

### 3.2 `data/sessions/archives/` — 审查结论：✅ 可清理 + 🐛 额外 Bug

**审查发现的额外问题：**

| 子目录 | 文件数 | 说明 |
|--------|--------|------|
| `default/` | 4 | 正常 |
| `None/` | 12 | **Bug！** user_id=None 导致创建了 "None" 字符串目录名 |
| `t/` | 5398 | 测试用户，占 99.6% 的归档文件，但仅 ~0.77 MB |

**Bug 根因：** `HistoryCompressor` 中当 `user_id=None` 时字符串格式化产生了 `None` 目录。

**建议：** 清理 `t/` 和 `None/` 目录，并修复 user_id=None 的代码路径。

### 3.3 `data/results/` — 审查结论：⚠️ 保留活跃，清理历史

56 个研究结果目录，112 文件，共 ~91.5 MB。
每个目录含 `result.json` + `metadata.json`。报告已生成至 `data/reports/` 的可全部清理。

### 3.4 `data/backups/` — 审查结论：✅ 可清理

151 个 .md 文件，仅 0.12 MB。

### 3.5 `data/revisions/` — 审查结论：⚠️ 保留近 7 天

修订操作记录，删除后无法回退报告编辑。建议保留最近 7 天。

### 3.6 `data/previews/` — 审查结论：✅ 可清理

91 文件，可自动重新生成。

### 3.7 其他子目录

| 子目录 | 审查结论 |
|--------|---------|
| `data/sentiment/` | ✅ 清理 |
| `data/research_*/` | ✅ 清理 |
| `data/temp/` | ✅ 清理 |
| `data/checkpoints/` | ✅ 清理（空目录） |
| `data/html_reports/` | ✅ 清理（空目录） |
| `data/.wisdom/` | ✅ 清理 |
| `data/survey_tasks/` | ⚠️ 保留活跃 |
| `data/users/t/ + test_user/` | ✅ 清理（测试用户） |
| `data/knowledge_bank_t*.db + test_user*.db` | ✅ 清理（测试库，每用户 3 文件） |
| `data/knowledge/` | ℹ️ 保留 |
| `data/users/{default, user_001}/` | ℹ️ 保留 |
| `data/uploads/` | ℹ️ 保留（可能被功能使用） |
| `data/documents/` | ℹ️ 保留（doc_gen_agent.py:102 引用） |
| `data/tasks/` | ℹ️ 保留（113 文件，0.07 MB，`task_persistence.py` 使用） |
| `data/test_task_001/` | ✅ 清理（测试遗留，148 字节） |

---

## 四、logs/ 日志文件

| 文件 | 大小 | 审查结论 |
|------|------|---------|
| `app.log` | 9.17 MB | 轮转后清空保留文件 |
| `app.log.2026-05-0*`（5 个） | 1.74 MB | 清理 |
| `openresearch.log` | 3.42 MB | 轮转后清空保留文件 |
| `web-error.log` | 0.15 MB | 轮转后清空 |
| `web-out.log` | 0.09 MB | 轮转后清空 |
| `uvicorn_stderr.log` | 0.07 MB | 轮转后清空 |
| 其余(~4文件) | ~0 KB | 清理 |

---

## 五、其他目录

| 目录 | 审查结论 |
|------|---------|
| `_cleanup_backup_20260503_095703/` | ✅ 删除（含 desktop_app.py 备份，但原件仍在根目录） |
| `_archive/legacy_routing/` | ✅ 如 Git 有记录则清理 |
| `tests/_archive/` | ✅ 清理（pytest.ini 已 --ignore） |
| `__pycache__/` | ✅ 清理 |
| `.pytest_cache/` | ✅ 清理 |
| `.sisyphus/` | ℹ️ 保留（开发辅助，不干扰运行） |
| `node_modules/` | ℹ️ 保留（前端依赖） |

---

## 六、汇总

| 阶段 | 项目 | 回收空间 |
|------|------|---------|
| **Phase 0** | 修复 3 个 Bug | — |
| **Phase A** | 安全清理 26 项 | ~200 MB（含 CSV 移入 _cleanup_temp/ 不计回收，实际回收 ~108 MB） |
| **Phase B** | registries 修复后迁移去重 | ~1.5 GB |
| **Phase C** | docs/ 历史文档归档 | ~1.5 MB |
| **Phase D** | 文档更新 + 全面测试 | — |
| **总计** | **~6,000+ 文件** | **~1.7 GB** |

## 七、执行计划

### Phase 0：修复代码 Bug

1. **Fix 1:** `agent_coordinator.py:558` — 将 `registries_dir` 改为 `storage_path="data"`
2. **Fix 2:** `HistoryCompressor` 中处理 `user_id=None` 的情况（已在压缩适配器和历史压缩器中排查）
3. **Fix 3:** `data/sessions/archives/None/` 根因修复 — `compress_adapter.py:57` 中 `f"{self._archive_base}/{user_id}"` 当 `user_id=None` 时产生字符串 "None"

### Phase A：安全清理项（立即执行）

1. 删除根目录 test_*.py / tmp_*.py / verify_fixes.py（10 文件）
2. 删除根目录日志/输出文件（4 文件）
3. **处理 WVS_Cross-National_Wave_7_csv_v6_0.csv（182 MB）→ 移入 _cleanup_temp/**（已有 benchmark 产物）
4. **清理 Logo.psd（5.43 MB）→ 移入 _archive/**
5. **清理 models（31 字节）→ 删除（调试遗留）**
6. **清理 test_resp1.json（197 字节）→ 删除**
7. 删除 data/backups/（151 文件）
8. 删除 data/previews/（91 文件）
9. 删除 data/sentiment/（9 文件）
10. 删除 data/results/（56 研究结果目录，~91.5 MB，报告已生成至 data/reports/ 的可删）
11. 删除 data/temp/ 内容
12. 清理 data/revisions/ — 删除 7 天前的修订记录（136 文件，保留近期用于回退）
13. 清理 data/sessions/*.json（69 会话文件）+ data/sessions/agents/（126 agent 文件）— 保留活跃，清理已完成
14. 删除 data/test_task_001/（148 字节，测试遗留）
15. 删除 data/checkpoints/（空目录）
16. 删除 data/html_reports/（空目录）
17. 删除 data/.wisdom/（空目录）
18. 删除 data/sessions/archives/None/（12 文件，Bug 产物）
19. 删除 data/sessions/archives/t/（5398 .gz，~0.77 MB）
20. 删除 data/users/t/ + test_user/
21. 删除 data/knowledge_bank_t*.db + test_user*.db
22. 删除 docs/research_results/（24 json）
23. 删除 logs/ 归档日志（轮转后清空）
24. 删除 _cleanup_backup_20260503_095703/
25. 删除 tests/_archive/（17 文件）
26. 删除所有 __pycache__/
27. 删除 .pytest_cache/
28. 根目录 15 个分析文档移入 docs/_archive/

### Phase B：registries 修复后处理

1. 修复 coordinator 路径 bug → 部署到运行环境
2. 等待系统运行同步数据到正确位置
3. 确认正确路径数据完整性后，清理嵌套目录冗余

### Phase C：文档归档

1. 创建 docs/_archive/ 目录
2. 移入历史诊断/修复文档
3. 移入 STATUS/ 目录
4. 移入设计提案文档
5. 移入 development/ 目录
6. superpowers/specs/ 保留终版，其余移入

### Phase D：更新手册 + 全面测试

1. 更新 docs/SYSTEM_USAGE_GUIDE.md
2. 运行 pytest tests/unit -v
3. 运行 pytest tests/integration -v
4. 运行 pytest tests/e2e -v
5. 修复测试中发现的问题
6. 更新 CHANGELOG.md
