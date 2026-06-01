# `/template` 命令故障分析报告 — 深度审查最终结论

## 报告整体评估

| 维度 | 结论 |
|------|------|
| 逻辑链完整性 | ✅ 完整 — 从前端输入到后端返回，8 层调用链逐层追踪 |
| 证据充分性 | ✅ 充分 — 97 处引用全部核查，35 处有效引用四象限分类 |
| 修正正确性 | ✅ 正确 — 3 处自我修正已验证 |
| 可实施性 | ✅ 可实施 — 5 行修改，3 个文件，零风险 |

---

## 结论 1：根因确认 — template_id 格式不匹配

**前后端模板 ID 格式约定不一致：前端连字符（`industry-research`）vs 后端下划线（`industry_research`）。**

### 证据链（8 层，从用户输入到虚假成功）

| 层 | 位置 | 输入/输出 | 证据 |
|----|------|-----------|------|
| L1 用户输入 | 终端 | `/template industry-research 固态电池竞争格局` | 用户复述 |
| L2 前端解析 | `templates.ts:107-127` | `templateId = "industry-research"` | 代码第 117 行 `t.id === templateKeyword` |
| L3 前端调用 | `useResearch.ts:59` | `api.quickStart(input, "industry-research", ...)` | 代码第 59 行 |
| L4 API 发送 | `api.ts:302` | `FormData.append("template_id", "industry-research")` | 代码第 302 行 |
| L5 后端路由 | `main.py:275` | `template_id = "industry-research"` (Form) | 代码第 275 行 |
| L6 字典查询 | `research_api.py:2290` | `TEMPLATES.get("industry-research") → None` | 代码第 2268-2288 行 dict key 为下划线 |
| L7 错误返回 | `research_api.py:2292` | `{"error": "Unknown template: ..."}` (HTTP 200) | 代码第 2292 行 |
| L8 前端误判 | `useResearch.ts:80-102` | `data.step === undefined → 进入 else 分支` | 代码第 80-102 行 |

### 替代假说排除（7 项全部排除）

SmartClarifier 异常、`get_framework_config` 异常、axios 拦截器误拦截、前端 catch 误吞、`session_manager.create` 异常、表单解析错误、缓存 — 均有直接证据排除。

---

## 结论 2：隔离验证 — 无下游影响

**35 处有效引用按四象限分类，全部确认不影响：**

| 象限 | 描述 | 数量 | 确认 |
|------|------|------|------|
| I | quick_start 直接路径（修复目标） | 3 | 修复直接作用于此处 |
| II | 同名变量、不同数据源 | 2 | SmartClarifier.TEMPLATES 来自 YAML；orchestrator 使用独立 ID 体系 |
| III | 接口兼容层（仅透传） | 3 | FastAPI 路由、FormData、函数参数均不校验内容 |
| IV | 完全无关的 template_id | 27 | workflow 模板、文档排版、类型定义等 |

**特别验证：SmartClarifier 与 quick_start 无数据通路。** `quick_start` 中 `template_id` 从未传入 `clarifier`（仅传入 `user_input`、`output_type`、`"detailed"`）。

---

## 结论 3：边缘情况分析纠错

**原始审查的推论路径存在一处事实错误，结论碰巧正确。**

| 场景 | 原始审查表述 | 实际行为 |
|------|------------|---------|
| `/template industry_research 某某`（手动下划线） | "通过关键词匹配后返回 t.id（连字符）→ 后端替换后匹配成功" | **❌ 根本不会进入 quick-start**。`parseTemplateCommand` 返回 `templateId: null`（空格 ≠ 下划线，`String.includes()` 不匹配），程序进入正常对话流 |

**关键词匹配的精确验证：** `"industry research".includes("industry_research")` → false（字符位置 8：`' '` 0x20 ≠ `'_'` 0x5F）。下划线输入无法通过关键词匹配命中任何模板。

---

## 结论 4：错失发现的严重程度校正

### 4.1 `createSession(undefined)` 脏数据污染

**严重程度：🔶 中低（根因症状，非独立漏洞）**

| 影响项 | 实际表现 | 严重度 |
|--------|---------|--------|
| `sessions["undefined"]` 脏条目 | 在 store 中产生 key 为字符串 `"undefined"` 的 session | 🔶 中 |
| `activeId` 变为 `undefined` | `!undefined === true`，`syncActive()` 保护守卫**仍然有效** | ✅ 无影响 |
| `taskId` 变为 `undefined` | `useResearchStore.ts:132` → `taskId = undefined`（违反 `string \| null` 类型签名）→ `handleCancel` 中 `taskId && ...` 为 false → 用户无法取消，卡在虚假 "running" 状态，只能刷新页面恢复 | 🔶 中（UX 问题） |
| 修复根因后此路径 | 不可达 | ✅ 自动消除 |

### 4.2 error path 缺失日志

**严重程度：🔶 中（已可修复，logger 已 import）**

`research_api.py:2291-2292`：无 `logger.warning()`，错误静默消失。`line 23` 已 `import logging`，`line 31` 已 `logger = logging.getLogger(__name__)`，直接加 1 行即可。

### 4.3 报告外发现：ResearchAPI 双实例

**位置：** `main.py:156`（已用实例）vs `research_api.py:3385`（未用默认实例）

**评估：不影响修复。** `quick_start` 方法不依赖 `self.orchestrator` 和 `self.knowledge_manager`，两个实例间无共享可变状态。系代码残留，非 bug。

### 4.4 已移除的误标发现

| 原条目 | 移除原因 |
|--------|---------|
| 路径注入风险 (`orchestrator.py:2961`) | 该路径 `template_id` 来自 orchestrator 独立上下文，非用户可控 |
| SmartClarifier 耦合风险 | 已确认无数据通路 |

---

## 结论 5：修复方案

### 5.1 安全性验证表的微小不精确

表中 `"industry_research" → replace → "industry_research" → 匹配成功 ✅` 一行，通过前端界面**不可达**（`parseTemplateCommand` 不匹配下划线），只能通过 curl 等工具手动触发。后端接受它无害，保留该行作为 API 直接调用的兼容性保证。

### 5.2 最终修复方案

| # | 文件 | 位置 | 修改内容 | 风险 | 回滚 |
|---|------|------|---------|------|------|
| 1 | `src/api/research_api.py` | `quick_start` 内, TEMPLATES 查询前 | `template_id = template_id.replace('-', '_')` | 零 | 删除该行 |
| 1b | 同上 | error return 前 | `logger.warning(f"Unknown template_id: {template_id}")` | 零 | 删除该行 |
| 2 | `web/src/hooks/useResearch.ts` | `api.quickStart()` 后 | `if ((data as any).error) throw new ApiError(...)` | 零 | 删除代码块 |
| 2b | 同上 | `createSession` 前 | `if (data.session_id) { createSession(...) }` | 零 | 恢复原调用 |
| 3 | `web/src/components/chat/ChatPanel.tsx` | catch 块 | 显示 `error.message` 而非通用文案 | 低 | 恢复原文案 |

**总计：5 行新增代码，3 个文件修改，零/低风险，可独立回滚。**

### 5.3 无需修改清单

| 文件 | 原因 |
|------|------|
| `web/src/lib/templates.ts` | 前端连字符格式**是正确的**，后端应适配前端 |
| `research_api.py:2267-2288` TEMPLATES dict keys | 下划线保持不动，做输入规范化 |
| `web/src/lib/api.ts` 返回类型 | 联合类型搁置，实施成本 > 收益 |
| `src/core/orchestrator/*` | 独立 template_id 体系 |
| `src/core/orchestrator/smart_clarifier.py` | TEMPLATES 来自 YAML，独立字典 |

---

## 最终验证命令

```bash
# 正常路径 — 修复后应返回 step=4 和 parameters
curl -s -X POST http://localhost:8000/api/v1/research/quick-start \
  -F "user_input=固态电池竞争格局" \
  -F "template_id=industry-research" \
  | python -c "import sys,json; d=json.load(sys.stdin); print('step:', d.get('step'), '| params:', d.get('parameters') is not None)"
# 期望: step: 4 | params: True

# 错误路径 — 应记录日志
curl -s -X POST http://localhost:8000/api/v1/research/quick-start \
  -F "user_input=测试" \
  -F "template_id=nonexistent" \
  | python -c "import sys,json; d=json.load(sys.stdin); print('error:', d.get('error'))"
# 期望: error: Unknown template: nonexistent
# 期望后端日志: WARNING  Unknown template_id: nonexistent
```

---

*审查完成。2026-05-11。*
