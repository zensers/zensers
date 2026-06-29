# GenericAgent `_report_progress` 修复方案

> 日期: 2026-06-29
> 关联: `docs/2026-06-28-research-progress-visibility-improvement.md §9.5`

## 1. 问题描述

`GenericAgent` 使用 mixin 组合模式，继承链为 `StateManagementMixin → CommunicationMixin`，**不继承** `BaseAgent`。而 `_report_progress` 方法仅定义在 `BaseAgent` 上，且继承链中所有 mixin 均未定义此方法。

当前代码中已在 `generic_agent.py` 插入了 **18 处** `self._report_progress()` 调用（因回滚操作暂失），这些调用在运行时全部会抛出 `AttributeError`。

**关键数据**：
- 影响：GenericAgent 的 research/quality-check/analysis/calibration/synthesis/fallback 全部 6 条代码路径
- 调用数：18 处（分布在 ~900 行 execute() 方法中）
- 同时缺失的还有 `_current_session_id` 属性的读取通路（orchestrator 已注入该属性，但 GenericAgent 没有方法去读取它）

## 2. 现有基础设施（已就绪，无需改动）

| 组件 | 文件 | 状态 |
|------|------|------|
| `BaseAgent._report_progress` | `src/core/agents/base.py:231` | ✅ 已实现，4 tests |
| `FixedAgent._report_progress` | `src/agents/fixed_agents/base_fixed_agent.py:140` | ✅ 已实现，4 tests |
| `SessionStreamer.push_agent_message` | `src/core/session_streamer.py:247` | ✅ 200ms 节流已实现 |
| `ProgressHeartbeat` | `src/core/progress_heartbeat.py` | ✅ 7 tests |
| orchestrator `_current_session_id` 注入 | `src/core/orchestrator/orchestrator.py:749/1881` | ✅ 路由和非路由路径均已注入 |

## 3. 方案对比

### 方案 A：在 GenericAgent 中直接定义 `_report_progress`（推荐）

```python
def _report_progress(self, message: str, action: str = "analyzing"):
    _sid = getattr(self, '_current_session_id', None)
    if not _sid:
        return
    try:
        from src.core.session_streamer import SessionStreamer
        SessionStreamer.push_agent_message(_sid, {
            "agent_id": self.agent_id,
            "agent_name": self.config.get("context", {}).get("aspect", self.agent_type),
            "action": action,
            "content": message,
        })
    except Exception:
        pass
```

| 维度 | 评估 |
|------|------|
| 改动量 | 1 文件，+12 行 |
| 代码重复 | 与 BaseAgent._report_progress 完全重复（~12 行） |
| 后继维护 | BaseAgent 和 GenericAgent 两处需同步修改 |
| 风险 | 极低 — GenericAgent 已有 `agent_id`/`agent_type`/`config`/`_current_session_id` 所有依赖属性 |
| 测试 | 需新增 3-4 个 tests（覆盖 GenericAgent） |

### 方案 B：抽取为模块级辅助函数

```python
# src/core/session_streamer.py 或新文件
def push_agent_progress(sid, agent_id, agent_name, message, action):
    if not sid:
        return
    try:
        SessionStreamer.push_agent_message(sid, {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "action": action,
            "content": message,
        })
    except Exception:
        pass
```

| 维度 | 评估 |
|------|------|
| 改动量 | 2 文件（辅助函数 + GenericAgent 调用）+ 可选重构 BaseAgent/FixedAgent |
| 代码重复 | 无重复 — 单一维护点 |
| 后继维护 | 修改辅助函数即可同步所有 Agent |
| 风险 | 中 — 引入新函数，需确认导入路径；如重构 BaseAgent/FixedAgent 增加回归风险 |
| 测试 | 需新增 3-4 个 tests |

### 方案 C：将 `_report_progress` 抽取到 `CommunicationMixin`

| 维度 | 评估 |
|------|------|
| 改动量 | 3 文件（mixin + GenericAgent 移除 + BaseAgent 修改继承） |
| 风险 | 高 — `CommunicationMixin` 被 BaseAgent 和 FixedAgent 共同使用，修改 mixin 可能触发钻石继承问题 |
| 测试 | 需回归 BaseAgent + FixedAgent + GenericAgent 全部测试 |

### 方案 D：让 GenericAgent 继承 BaseAgent

```python
class GenericAgent(StateManagementMixin, CommunicationMixin, BaseAgent):
```

| 维度 | 评估 |
|------|------|
| 改动量 | 2 文件（GenericAgent + BaseAgent） |
| 风险 | **高** — `__init__` 不调用 `super()`，BaseAgent 的 `__init__` 不会被触发；`CommunicationMixin` 和 `BaseAgent` 都有 `publish_event`/`update_state` 等方法，MRO 解析顺序可能意外改变行为 |

### 方案选择

**推荐方案 A**。理由：
1. 改动最小（1 文件 +12 行），风险最低
2. 代码重复是设计层面的代价，但 12 行代码的重复远低于方案 C/D 的钻石继承风险
3. 后继如果需要统一维护，可以平滑过渡到方案 B

## 4. 实施步骤

### Step 1：在 GenericAgent 添加 `_report_progress` 方法

- **文件**: `src/core/agents/generic_agent.py`
- **插入位置**: `__init__` 之后（L177 之后），`# === 核心执行方法` 注释之前
- **代码**: 见方案 A

### Step 2：恢复 18 处 `_report_progress()` 调用

- **文件**: `src/core/agents/generic_agent.py`
- **分布**: 参考 docs/2026-06-28-research-progress-visibility-improvement.md §6.3 的规定位置
- **受保护条件**：每条调用都必须有对应的条件保护，仅在相关分支被执行时才触发

#### 准确调用位置清单

| # | agent_category | 位置（execute 方法内） | 消息 | action | 条件 |
|---|---------------|----------------------|------|--------|------|
| 1 | research | Phase 1 入口 | `"Starting data collection..."` | searching | `agent_category == "research"` |
| 2 | research | Tier 1 完成后 | `"结构化数据库查询完成，获取 {n} 条数据"` | searching | after struct DB loop |
| 3 | research | Tier 2 搜索前 | `"Searching web sources for '{topic}'..."` | searching | `if topic and tiered_skills.get("web_search")` |
| 4 | research | Tier 2 搜索后 | `"网络搜索完成，共 {n} 条数据"` | searching | after search_skill block |
| 5 | research | news_search 后 | `"新闻搜索补充 {n} 条"` | searching | `if news_result and news_result.get('success')` |
| 6 | quality-check | Phase 2 入口 | `"Validating collected data..."` | analyzing | `agent_category == "quality-check"` |
| 7 | quality-check | 验证完成后 | `"数据验证完成，{n}/{m} 个数据点，质量评分 {s}"` | analyzing | `if data_points:` |
| 8 | quality-check | 冲突解决后 | `"冲突解决完成，{n} 个冲突已处理"` | analyzing | `if validation_result.get("has_conflicts")` |
| 9 | quality-check | 重收集后 | `"补充收集后重新验证，{n} 个有效数据点"` | analyzing | `if recollection_attempted:` |
| 10 | analysis | Phase 3 入口 | `"Analyzing {topic}..."` | analyzing | `agent_category in ("market-analysis", "analysis", ...)` |
| 11 | analysis | 降级搜索后 | `"降级搜索完成，获取 {n} 条数据"` | searching | after search fallback block |
| 12 | analysis | 知识缺口检测后 | `"分析内容知识检测完成{', 发现 '+str(n)+' 个缺口' if gaps else ', 无需补充'}"` | analyzing | `if gaps:` |
| 13 | analysis | 补充搜索修订后 | `"补充搜索后修订完成，新增 {n} 数据点"` | analyzing | `if supp_result and supp_result.get('data_points')` |
| 14 | analysis | 自评完成后 | `"分析内容自评完成，评分 {s}"` | analyzing | `if max_self_eval > 0 and result.get("success")` |
| 15 | calibration | Phase 入口 | `"校准跨章节数值一致性..."` | analyzing | `agent_category == "calibration"` |
| 16 | synthesis | LLM 调用前 | `"Generating analysis for {topic}..."` | writing | enrichment 分支 |
| 17 | synthesis | LLM 调用前（无 enrichment） | `"Generating analysis for {topic}..."` | writing | 无 enrichment 分支 |
| 18 | fallback | 搜索完成后 | `"搜索完成，获取 {n} 条结果"` | searching | `if search_results:` |

### Step 3：新增单元测试

- **文件**: `tests/unit/test_generic_agent_report_progress.py`（新建）
- **测试内容**:
  1. `test_report_progress_no_session_id` — 无 `_current_session_id` 时静默跳过
  2. `test_report_progress_with_session_id` — 有 `_current_session_id` 时推送正确消息
  3. `test_report_progress_agent_name_from_context` — `context.aspect` 正确映射到 `agent_name`
  4. `test_report_progress_fallback_to_agent_type` — 无 `context.aspect` 时回退到 `agent_type`
  5. `test_report_progress_exception_swallowed` — 异常时不崩溃

### Step 4：验证端到端

- **测试路径**: execute() 中每个 `agent_category` 分支至少走一次
- **验证方式**: 前端 SSE 事件日志中应出现对应的 `agent_message` 事件

## 5. 不在此方案范围内的项目

| 项目 | 原因 |
|------|------|
| `_current_session_id` 在 GenericAgent `__init__` 中声明 | 该属性由 orchestrator 动态注入（现有代码模式），无需在 `__init__` 中预设默认值 |
| BaseAgent/FixedAgent 的重构 | 与本次问题无关 |
| 12 个新增进度点（§6.3） | 需等修复方案部署后再实施，避免在修复前引入更多 AttributeError |

## 6. 回滚方案

如果修复后出现问题，只需删除 Step 1 添加的方法定义即可回滚。Step 2 的 18 处调用已在当前代码中存在（或恢复后存在），它们原本就会抛 AttributeError，所以删除方法定义后行为与修复前一致。
