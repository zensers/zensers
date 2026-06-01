# 对话到框架的智能推导方案设计

> 基于 LLM 输出扩展，实现从对话历史自动推导研究框架

---

## 1. 问题陈述

### 1.1 场景

用户通过多轮对话完成了数据收集、初步分析后，说：

> "整理这些数据形成一个报告吧"

系统应将这些对话内容编译成一份结构化的研究报告。

### 1.2 当前失败原因

系统有**两条并行的数据轨道**，但框架生成只用了一条：

```
轨道 A: research_context.directions  ← 对话中提取的研究方向（轻量、可能为空）
轨道 B: conversation_history         ← 完整对话记录（丰富、含搜索结果和分析内容）

_generate_research_framework() 只用轨道 A
→ directions 为空 → sections 为空 → _start_execution() 阻断
```

### 1.3 核心矛盾

| 方面 | 现状 | 期望 |
|------|------|------|
| 框架数据来源 | `directions`（用户显式说的方向） | `conversation_history`（对话中实际讨论的内容） |
| 框架生成方式 | 模板映射（`_generate_research_framework`） | LLM 基于对话推导 |
| 用户确认 | ✅ 有框架确认环节 | ✅ 保留 |
| 执行阶段 | 标准数据收集→分析→报告 | **标准流程正常执行** — agents 从 session 读取已有数据，补充缺口 |

> 注意：不要跳过数据收集阶段。用户说"整理数据形成报告"意味着"基于现有内容进一步搜集分析"，agents 在执行时可以从 `session.conversation_history` 读到已有的数据，自行决定补充什么。

---

## 2. 设计原则

1. **不新增 action 类型** — 复用 `enter_framework`
2. **保留框架确认环节** — 用户始终可见并确认框架
3. **LLM 是自然的桥梁** — LLM 在 `_llm_converse` 中已看到完整对话，应输出推导结果
4. **最小改动** — 不改动执行器、编排器等下游组件
5. **向后兼容** — 不影响现有 `directions` 路径
6. **不跳过标准执行流程** — agents 天然能读到对话历史，让它们自己利用已有数据

---

## 3. 数据流（修改后）

```
用户: "整理这些数据形成一个报告吧"
  │
  ▼
_llm_converse()     ← LLM 看到完整对话历史（conversation_history + context + directions）
  │
  │  LLM 输出（新增 framework_sections 字段）:
  │  {
  │    "action": "enter_framework",
  │    "topic": "新能源汽车市场分析",
  │    "directions": [],
  │    "framework_sections": [        ← NEW
  │      "市场规模与增长趋势",
  │      "竞争格局与主要企业分析",
  │      "技术路线对比",
  │      "政策环境评估",
  │      "投资机会与风险"
  │    ]
  │  }
  │
  ▼
_handle_chat_mode()
  → 检测到 action == "enter_framework"
  → 提取 framework_sections 存入 context._suggested_sections
  │
  ▼
_enter_framework_mode()
  → 检测到 context._suggested_sections 有值
  → 优先使用它生成框架（跳过 directions→sections 的模板路径）
  → 展示给用户确认
  │
  ▼  用户确认
_start_execution()
  → sections 有内容 → 正常启动执行
  → agents 在执行时从 session.conversation_history 读取已有数据
  → 已有数据的章节：agents 基于现有信息补充完善
  → 无数据的章节：agents 正常搜集
```

---

## 4. 详细改动

### 4.1 Prompt 层：`prompts/agents/conversation.md`

#### 改动：扩展 LLM 输出 schema

```markdown
## Output Format (JSON)

```json
{
    "message": "Friendly reply to the user, Markdown format",
    "action": "continue_chat | enter_framework",
    "topic": "Extracted research topic, null if none",
    "directions": ["direction1", "direction2"],
    "framework_sections": ["Section 1", "Section 2"],  // ← NEW
    "suggestions": [
        {"id": "suggestion_id", "label": "Display label", "example": "Example text"}
    ],
    "tool_call": null
}
```

#### 新增规则说明

在 `action=enter_framework` 的条件部分追加：

```markdown
### framework_sections 字段规则（NEW）

当 `action="enter_framework"` 时，可以输出 `framework_sections`：

- **用途**：基于当前对话历史中实际讨论的内容，推导出报告应包含的章节
- **触发条件**：对话历史中包含足够的数据和分析内容，用户要求整理为报告
- **来源**：从对话中提取用户实际讨论过的话题，而非系统模板
- **数量**：3-8 个章节
- **命名**：使用清晰、具有描述性的章节名称，与对话中讨论的内容一致

**示例场景**：
- 用户搜索了市场规模、分析了竞争格局 → `framework_sections: ["市场规模分析", "竞争格局分析", "发展趋势"]`
- 用户讨论了技术路线和政策 → `framework_sections: ["技术路线对比", "政策环境分析"]`

**不适用场景**：
- 对话中未收集实质性数据 → 不输出 framework_sections，走标准 directions 路径
- 用户明确要求使用特定模板 → 不输出 framework_sections
```

### 4.2 API 层：`src/api/research_api.py`

#### 改动 A：`_handle_chat_mode()` — 存储 LLM 建议章节

**位置**：`enter_framework` 分支（约第 525-527 行）

```python
if action == "enter_framework":
    # LLM determined this needs formal research — enter framework for user review
    # ★ NEW: 存储 LLM 基于对话推导的框架章节
    fw_sections = conv_result.get("framework_sections")
    if fw_sections and isinstance(fw_sections, list) and len(fw_sections) > 0:
        context["_suggested_sections"] = fw_sections
        logger.info(
            f"LLM suggested {len(fw_sections)} sections from conversation: {fw_sections}"
        )
    session["research_context"] = context
    return await self._enter_framework_mode(session_id, user_input)
```

#### 改动 B：`_enter_framework_mode()` — 使用建议章节生成框架

**位置**：约第 1250-1319 行

```python
async def _enter_framework_mode(self, session_id, user_input):
    session = session_manager.get(session_id)
    context = session.get("research_context", {})
    lang = self._get_lang(session)

    # Idempotency check
    existing_fw = context.get("framework")
    if existing_fw and existing_fw.get("sections"):
        logger.info(f"Framework already exists for {session_id}, returning existing")
        session["mode"] = "framework"
        return self._framework_response(...)

    # ★ NEW: 优先使用 LLM 基于对话推导的章节
    suggested = context.get("_suggested_sections", [])
    if suggested:
        framework = {
            "topic": context.get("topic", "Research Report"),
            "sections": suggested,
            "output_type": "industry_report",
            "depth": context.get("details", {}).get("depth", "standard"),
            "region": context.get("details", {}).get("region", "China"),
            "time_range": context.get("details", {}).get("time_range", "Last 3 years"),
        }
        logger.info(
            f"Framework derived from conversation: {len(suggested)} sections"
        )
    else:
        # 标准路径：从 directions 生成
        framework = self._generate_research_framework(context)

    context["framework"] = framework
    session["research_context"] = context
    session["mode"] = "framework"

    return self._framework_response(
        session_id,
        message=self._l(
            f"根据我们的讨论，我整理了以下研究框架：\n\n"
            f"**研究主题**: {context.get('topic')}\n\n"
            f"**报告章节**:\n{self._format_framework(framework)}\n\n"
            f"请确认这个框架是否准确反映了我们讨论的内容。",
            f"Based on our discussion, I have organized the following research framework:\n\n"
            f"**Research Topic**: {context.get('topic')}\n\n"
            f"**Report Sections**:\n{self._format_framework(framework)}\n\n"
            f"Please confirm if this framework accurately reflects our discussion.",
            lang,
        ),
        suggestions=[
            {"id": "confirm", "label": self._l("框架可以", "Framework OK", lang),
             "example": self._l("这个框架可以", "This framework works", lang)},
            {"id": "modify", "label": self._l("需要调整", "Needs Adjustment", lang),
             "example": self._l("我想调整一下...", "I'd like to adjust...", lang)},
        ]
    )
```

#### 改动 C：`_start_execution()` — 守卫加推导兜底

**位置**：约第 1339-1344 行

```python
# Guard: validate research context before execution
topic = context.get("topic", "")
framework = context.get("framework", {})
sections = framework.get("sections", [])
if not topic:
    return {"session_id": session_id, "error": "No research topic specified",
            "error_code": "EMPTY_TOPIC", "status": "error"}
if not sections:
    # ★ NEW: 尝试从 LLM 建议章节恢复（防御性编程）
    suggested = context.get("_suggested_sections", [])
    if suggested:
        framework["sections"] = suggested
        sections = suggested
        context["framework"] = framework
        session["research_context"] = context
        logger.info(f"Recovered {len(sections)} sections from _suggested_sections")
    else:
        return {"session_id": session_id, "error": "No research sections defined",
                "error_code": "EMPTY_SECTIONS", "status": "error"}
```

> 改动 D（skip_phases）和 4.3 节（research_executor.py）已移除。理由：
> - 用户意图是"基于已有数据进一步搜集分析"，不是跳过数据收集
> - agents 在执行时可以从 `session.conversation_history` 读取已有数据，自行决定补充
> - 保持标准执行流程不变，减少特殊分支

---

## 5. 改动汇总

| # | 文件 | 改动类型 | 说明 |
|---|------|----------|------|
| 1 | `prompts/agents/conversation.md` | 修改 | 新增 `framework_sections` 字段 + 规则说明 |
| 2 | `src/api/research_api.py:_handle_chat_mode()` | 修改 | 提取并存储 `framework_sections` |
| 3 | `src/api/research_api.py:_enter_framework_mode()` | 修改 | 优先使用建议章节生成框架 |
| 4 | `src/api/research_api.py:_start_execution()` | 修改 | 守卫加推导兜底（防御性恢复） |

总代码改动量：约 **30 行**（含注释和日志）

不涉及的文件：`research_executor.py`、`orchestrator.py`、`intelligent_routing_adapter.py`、`task_structure.py` — 执行链路不受影响。

---

## 6. 对比

| 维度 | 原方案（数据链路传递） | 本方案（LLM 输出扩展） |
|------|----------------------|----------------------|
| 核心思路 | 5 个文件串行传递 conversation_history | LLM 输出 schema 扩展 |
| 改动量 | ~90 行 | ~30 行 |
| 涉及文件 | 5 个 | 2 个 + 1 个 prompt |
| Token 消耗 | 额外 LLM 调用推导 sections | 零额外 — 复用已有 LLM 调用 |
| 安全性 | 移除守卫，有风险 | 保留守卫，加推导兜底 |
| 执行流程 | 修改了执行器（skip_phases） | 执行链路不变 |
| 框架确认 | 无变化 | 增强 — 框架内容更准确匹配对话 |
| 向后兼容 | ✅ | ✅ |
| 可维护性 | 数据链路长，容易断 | LLM 输出扩展，耦合度低 |

---

## 7. 边界情况处理

### 7.1 framework_sections 与 directions 都有值

优先使用 `framework_sections`（更丰富、基于完整对话），同时将 `directions` 作为补充：

```python
if suggested and directions:
    # 合并去重
    all_sections = list(dict.fromkeys(suggested + directions))
    framework["sections"] = all_sections
```

### 7.2 LLM 误判 — 输出 framework_sections 但对话内容不足

- `_start_execution()` 的守卫仍会检查 `sections` 是否为空
- 如果 framework_sections 包含无关章节，用户可在框架确认环节调整
- `_suggested_sections` 只在本次会话有效，不会被持久化

### 7.3 用户修改建议章节

当前框架确认逻辑（`_handle_framework_mode` → `_llm_framework_modify`）已支持用户修改 sections，无需额外改动。

### 7.4 对话历史为空或过短

LLM 不会输出 `framework_sections`（prompt 中已有"不适用场景"规则），系统走标准 `directions` 路径。

### 7.5 多轮 enter_framework 切换

如果用户从 framework 模式切回 chat 再重新进入，`_enter_framework_mode()` 的幂等性检查会检测到已有 framework，直接返回现有框架。`_suggested_sections` 会在每次 enter_framework 时被覆盖，不会累积。

### 7.6 Agents 如何利用对话历史中的已有数据

agents 在执行阶段可以通过 session 访问 `conversation_history`。例如：
- 如果用户在对话中已搜索了"2025 年新能源汽车市场规模"，agents 的搜索结果中会包含这些信息
- Agents 的 LLM prompt 中包含了 session 的 research_context，天然能感知已有内容
- 不需要额外的数据传递机制

---

## 8. 实现顺序

```
Step 1: Prompt 层
  └─ prompts/agents/conversation.md  ← 扩展 LLM 输出 schema（增加 framework_sections）
      ↓（LLM 开始输出 framework_sections）

Step 2: API 层（核心逻辑）
  ├─ _handle_chat_mode()       ← 接收 framework_sections 存入 context
  ├─ _enter_framework_mode()   ← 优先使用建议章节生成框架
  └─ _start_execution()        ← 守卫 + 推导兜底（防御性恢复）
      ↓

Step 3: 验证
  ├─ 单元测试：LLM 返回 framework_sections 的解析
  ├─ 集成测试：完整链路 对话→框架→确认→执行
  └─ 回归测试：标准 directions 路径不受影响
```

---

## 9. 附录：关键代码路径参考

| 方法 | 文件 | 行号 |
|------|------|------|
| `_llm_converse` | `src/api/research_api.py` | 545-826 |
| `_handle_chat_mode` | `src/api/research_api.py` | 421-543 |
| `_enter_framework_mode` | `src/api/research_api.py` | 1250-1319 |
| `_start_execution` | `src/api/research_api.py` | 1321-1407 |
| `_generate_research_framework` | `src/api/research_api.py` | 1788-1816 |
| Conversation prompt | `prompts/agents/conversation.md` | 全文件 |
