# 研究框架未生成问题 — 根因分析报告

## 问题描述

用户在研究"英伟达H200入华市场影响与产业链分析"时，系统未能生成包含章节的研究框架。用户看到的是空框架：

```
**研究主题**: 英伟达H200入华市场影响与产业链分析

**研究框架**:

请确认这个框架是否满足你的需求，或提出修改建议。
```

## 复现步骤

1. 输入任意搜索话题（如"英伟达H200入华"）
2. 系统返回搜索结果并进入 `continue_chat`
3. 输入"你形成一个详细的分析框架"
4. **期望**：框架包含多个章节；**实际**：框架为空

## 实际会话数据证据

从 `data/sessions/ses_2c7db708.json` 中提取的关键状态：

```json
"research_context": {
    "topic": "英伟达H200入华市场影响与产业链分析",
    "directions": [],
    "framework": {
        "topic": "英伟达H200入华市场影响与产业链分析",
        "sections": [
            "行业影响",
            "竞争格局",
            "政策环境",
            "上下游产业链分析",
            "对中国LLM大模型供应商的影响"
        ],
        ...
    }
}
```

**对话历史关键片段**：

| 时间 | 角色 | 内容 |
|------|------|------|
| 18:24:15 | assistant | 返回搜索结果，`"action": "continue_chat"`, `"topic": "英伟达H200入华..."`, **`"directions": []`** |
| 18:25:09 | user | "你形成一个详细的分析框架" |
| 18:25:26 | assistant | "根据我们的讨论，我整理了以下研究框架" — **但框架为空** |
| 18:25:34 | user | "取消研究" |
| 18:25:37 | assistant | "研究框架尚未完整定义" |
| 18:26:43 | user | "你没有形成框架啊..." |
| 18:26:48 | assistant | "好的，我重新构建了..." — **这次框架有5个sections** |

## 根因分析

### 直接原因

`_enter_framework_mode()` 生成框架时，`directions` 列表为空，导致 `_generate_research_framework()` 返回空 sections。

### 完整调用链追踪

```
用户: "你形成一个详细的分析框架"
  → _handle_user_message()
    → _handle_chat_mode()
      → _llm_converse(mode="chat", ...)  ← 未传入框架上下文！LLM不知道框架模式需要什么数据
      → LLM 返回 action="enter_framework"
      → conv_result.get("directions") = []  ← LLM 没有返回 directions！
      → conv_result.get("framework_sections") = undefined ← LLM 也没返回 framework_sections！
      → context["directions"] 仍为 []
      → _enter_framework_mode()
        → context.get("_suggested_sections") = []  ← 没有 suggested_sections
        → context.get("directions") = []  ← directions 为空
        → _generate_research_framework(context)
          → sections = []  ← 从空 directions 生成空 sections
        → framework = {"topic": "...", "sections": []}
      → 返回给用户: "研究框架为空"
```

### 五层根因

#### 根因0（根本性原因）: `_handle_chat_mode` 调用 `_llm_converse` 时未传入框架上下文

**位置**: `research_api.py` `_handle_chat_mode()` → `_llm_converse()` 调用处

`_llm_converse(mode="chat", ...)` 在没有研究框架上下文的情况下直接让 LLM 决策是否 `enter_framework`。LLM 看到的是纯聊天历史，**没有当前框架结构的数据契约感知**——它不知道 `enter_framework` 这个 action 需要同时输出 `directions` 或 `framework_sections` 才能成功。

这是根因1（LLM未输出directions）的**上游原因**：LLM不知道该输出什么，因为调用方没有告诉它框架模式需要什么。

#### 根因1: LLM (`_llm_converse`) 未输出 `directions` 和 `framework_sections`

**位置**: `research_api.py:712` `_llm_converse()` 方法

当用户说"你形成一个详细的分析框架"时，LLM 正确识别了 `action: "enter_framework"`，但**没有同时输出 `directions` 或 `framework_sections`**。

从会话数据可以看到，之前搜索结果的 chat_response 中：
```json
"action": "continue_chat",
"topic": "英伟达H200入华市场影响与产业链分析",
"directions": []
```

**原因分析**：
- `_llm_converse` 的 prompt 中，`directions` 的提取规则是："When users mention specific points of interest, extract as direction"
- 但用户说的是"你形成一个详细的分析框架"，这是一个**元指令**（要求系统生成框架），而不是直接提及研究方向
- LLM 理解了用户要进入框架模式，但没有主动从**对话历史**中提取讨论过的研究维度
- `framework_sections` 字段在 prompt 中被标记为"Optional"，且使用条件是"Conversation history contains substantive data/discussion"，LLM 可能判断条件不满足而省略

#### 根因2: `_enter_framework_mode()` 没有从对话历史推断 sections 的能力

**位置**: `research_api.py:1461` `_enter_framework_mode()` 方法

```python
suggested = context.get("_suggested_sections", [])
if suggested:
    # ... 使用 suggested_sections
else:
    framework = self._generate_research_framework(context)
    # ← 当 directions 为空时，sections 也为空！
```

**缺失的逻辑**：当 `_suggested_sections` 和 `directions` 都为空时，系统没有任何回退机制来从对话历史中推断章节。系统已有的成熟框架生成组件**完全没有被调用**。

#### 根因3: `_generate_research_framework()` 是纯映射函数，没有智能生成能力

**位置**: `research_api.py:2065` `_generate_research_framework()` 方法

```python
def _generate_research_framework(self, context: Dict) -> Dict:
    topic = context.get("topic", "")
    directions = context.get("directions", [])
    sections = []
    for d in directions:
        sections.append(d)
    return {"topic": topic, "sections": sections, ...}
    # ← directions 为空 → sections 为空，没有任何默认值或智能推断
```

这个方法只是一个简单的 `directions → sections` 映射，没有任何基于 topic 的默认章节生成逻辑。注意 `output_type` 参数在方法签名中存在但未被使用。

#### 根因4: `_framework_response` 返回 `step: 0` 导致前端渲染路径错误

**位置**: `research_api.py` `_framework_response()` 方法

`_framework_response` 返回 `step: 0, mode: "framework", suggestions: [确认, 取消]`。前端收到后：
1. `setStep(0, suggestions)` → `currentStep = 0`
2. `isChatMode = currentStep === null || currentStep === 0` → `true`
3. "确认/取消"按钮被渲染为**普通聊天建议按钮**（chat 模式分支）
4. 用户点击"确认" → `handleOptionSelect` 调用 `api.clickSuggestion`（而非 `confirmResearch`）

**正确行为**：`step: 5` → `currentStep = 5` → 前端走 `OptionSelector` 渲染路径 → `onSelect` 调用 `handleConfirm` → `confirmResearch`。

**为什么之前没暴露**：修复前框架 sections 为空，用户看到空框架后直接放弃，根本不会点按钮。修复后框架有内容了，按钮才被渲染出来，这个一直存在的 bug 才被触发。

#### 根因5（新发现）: `suggested_sections` 与 `directions` 合并时缺少语义去重

**位置**: `research_api.py:1521` `_enter_framework_mode()` 中的合并逻辑

当 LLM 同时返回了 `framework_sections`（如 `["市场规模分析", "竞争格局分析", ...]`）和 `directions`（如 `["市场规模", "竞争格局", ...]`）时，合并逻辑使用 `dict.fromkeys(suggested + directions)` 做字符串精确去重。但语义相同、字符串不同的条目（如"市场规模" vs "市场规模分析"）无法被识别为重复，导致框架出现 13 条重复章节：

```
1. 市场规模分析      ← framework_sections
2. 竞争格局分析      ← framework_sections
3. 细分市场分析      ← framework_sections
4. 主力犬种分析      ← framework_sections
5. 供应商分析        ← framework_sections
6. 价格趋势分析      ← framework_sections
7. 行业趋势与展望    ← framework_sections
8. 市场规模          ← directions（与1重复）
9. 竞争格局          ← directions（与2重复）
10. 细分市场         ← directions（与3重复）
11. 主力犬种         ← directions（与4重复）
12. 供应商           ← directions（与5重复）
13. 价格趋势         ← directions（与6重复）
```

### 次要问题：历史压缩导致上下文丢失

从日志可以看到：
```
History compressed: 21 -> 6 steps, ratio=86.74%
```

此处的 `ratio=86.74%` 是 **size reduction ratio**（压缩掉了86.74%的内容），即从21步压缩到6步，仅保留了约13%的原始对话。这可能导致 LLM 在 `_llm_converse` 中看不到完整的对话上下文，进一步降低了 LLM 提取 `framework_sections` 的能力。

## 系统已有的成熟框架生成能力（未被利用）

系统中存在多个可以生成研究框架的组件，但在 `_enter_framework_mode` 路径中**均未被调用**：

| 组件 | 位置 | 能力 | 是否被调用 |
|------|------|------|-----------|
| `SmartClarifier` | `src/core/orchestrator/smart_clarifier.py` | 根据输出类型生成章节模板 | ❌ 未调用 |
| `TemplateLoader` | `src/core/orchestrator/smart_clarifier.py` 内部 | 加载预定义章节模板 | ❌ 未调用 |
| `research_frameworks.yaml` | `config/research_frameworks.yaml` | 定义了 industry_report 等框架的 focus_areas 和 section_weights | ❌ 仅用于配置，未用于生成 sections |
| `_get_section_details_for_type()` | `research_api.py:2621` | 根据 output_type 获取章节详情 | ❌ 仅在 `quick_start` 路径使用 |
| `quick_start` 模板 | `research_api.py:2396` | 预定义了 industry_research 等模板的 aspects | ❌ 仅在 `/template` 命令路径使用 |

**关键发现**：`quick_start()` 方法（`research_api.py:2376`）中已经定义了完整的模板：

```python
TEMPLATES = {
    "industry_research": {
        "output_type": "industry_report",
        "aspects": ["市场规模", "竞争格局", "产业链分析", "发展趋势", "政策环境", "投资机会"],
    },
    ...
}
```

但 `_enter_framework_mode()` 完全没有使用这些模板作为回退。

**核心结论**：修复的本质不是修bug，而是**打通两条独立的代码路径**——对话路径（`_enter_framework_mode`）和模板路径（`quick_start`/`SmartClarifier`）之间缺少桥接。

## 修复方案

### 方案A: 在 `_enter_framework_mode` 中增加回退逻辑（推荐）✅ 已实施

当 `_suggested_sections` 和 `directions` 都为空时，按以下优先级回退：

1. **LLM推断**：新增 `_infer_framework_sections_from_conversation` 方法
   - 入参：`session_id`（从中获取对话历史 + topic + output_type）
   - 调用方式：调用 LLM 的简化版 prompt，从对话历史中提取研究维度
   - 降级机制：LLM调用失败时，进入步骤2

2. **模板章节**：调用 `_get_section_details_for_type(output_type)` 获取模板章节
   - 如果 output_type 已知（如 `industry_report`），直接获取预定义 sections
   - 降级机制：output_type 未知时，进入步骤3

3. **默认aspects**：使用 `quick_start` 中的 TEMPLATES 字典获取默认 aspects
   - 根据 topic 关键词匹配模板类型（引用 `config/research_frameworks.yaml` 中的标签体系，避免硬编码）
   - 最终回退：使用通用研究模板

### 方案B: 改进 `_llm_converse` prompt（辅助方案）✅ 已实施

在 `_llm_converse` 的 prompt 中，当用户触发 `enter_framework` 时，**强制要求** LLM 同时输出 `framework_sections`：

```
When action="enter_framework", you MUST also output framework_sections:
- Derive 4-8 sections from the conversation history and research topic
- If no specific dimensions were discussed, use standard industry research sections
```

同时，在 `_handle_chat_mode` 调用 `_llm_converse` 时，传入框架上下文（当前 research_context 中的 output_type、已有的 directions 等），让 LLM 感知框架模式的数据契约。

### 方案C: 改进 `_generate_research_framework`（补充方案）

当 `directions` 为空但 `topic` 不为空时，基于 topic 关键词匹配生成默认章节。关键词匹配应引用 `config/research_frameworks.yaml` 中的标签体系，避免硬编码。

### 方案D: 语义去重合并 `suggested_sections` 与 `directions` ✅ 已实施

新增 `_merge_sections_dedup` 方法，当短名称是长名称的子串时，保留更详细的版本。例如"市场规模"是"市场规模分析"的子串，合并时保留"市场规模分析"。

### 方案E: 修复 `_framework_response` 返回 step 值 ✅ 已实施

将 `_framework_response` 返回的 `step: 0` 改为 `step: 5`，使前端走 `OptionSelector` 渲染路径，正确处理框架确认/取消按钮。

**根因**：`step: 0` 导致前端 `isChatMode=true`，将"确认/取消"渲染为普通聊天建议按钮，点击后走 `clickSuggestion` 而非 `confirmResearch`。此 bug 一直存在，但修复前框架为空时用户不会点按钮，故从未触发。

### 推荐优先级

**A（主）+ B（辅）+ D（去重）+ E（step修复）> C**：方案A最可靠，在框架生成环节增加多层保护；方案B从源头改善LLM输出质量；方案D解决合并去重问题；方案C过于简单化，仅作为兜底。

## 已实施修复清单

### Fix A: 回退逻辑（方案A）

**文件**: `src/api/research_api.py`

| 新增方法 | 行号 | 功能 |
|----------|------|------|
| `_build_framework_with_fallback` | ~2086 | 协调三层回退链：LLM推断 → 模板章节 → 默认aspects |
| `_infer_framework_sections_from_conversation` | ~2138 | Level 1: 从对话历史中用LLM推断研究章节 |
| `_get_template_sections_for_topic` | ~2231 | Level 2: SmartClarifier → 关键词匹配模板章节 |
| `_generate_default_sections_for_topic` | ~2265 | Level 3: 通用默认章节 |

**调用点**: `_enter_framework_mode` 中 `else` 分支（`_suggested_sections` 和 `directions` 均为空时）调用 `_build_framework_with_fallback`。

### Fix B: Prompt 增强（方案B）

**文件**: `src/api/research_api.py`

1. **`context_summary` 增加框架契约感知**（~line 739）：当 topic 已存在但 framework 尚未生成时，向 LLM 提示 `enter_framework` 必须输出 `framework_sections`
2. **`enter_framework` action 规则增强**（~line 882）：添加 MANDATORY 输出要求，明确要求输出 `framework_sections` 数组
3. **新增触发短语**（~line 886）：添加"你形成一个详细的分析框架"、"你形成一个框架"、"形成框架"等用户常见表述
4. **`_llm_converse` 返回值**（~line 989）：`framework_sections` 已包含在同步返回 dict 中

**文件**: `prompts/agents/conversation.md`

1. `framework_sections` 从 Optional 改为 **MANDATORY** when `action=enter_framework`
2. 输出格式注释更新：`// MANDATORY when action=enter_framework`
3. 添加"形成分析框架"触发条件

### Fix D: 语义去重合并（方案D）

**文件**: `src/api/research_api.py`

1. **新增 `_merge_sections_dedup` 方法**（~line 2056）：子串匹配去重，保留更详细的版本
2. **替换合并逻辑**（~line 1521）：`dict.fromkeys(suggested + directions)` → `_merge_sections_dedup(suggested, directions)`

去重规则：
- `"市场规模"` 是 `"市场规模分析"` 的子串 → 保留 `"市场规模分析"`
- `"竞争格局"` 是 `"竞争格局分析"` 的子串 → 保留 `"竞争格局分析"`
- primary（framework_sections）优先级高于 secondary（directions），当两者长度相同时保留 primary 的版本

### Fix E: 修复 `_framework_response` step 值（方案E）

**文件**: `src/api/research_api.py`

1. **`_framework_response` 返回值**（~line 2397）：`step: 0` → `step: 5`

**前端渲染路径变化**：
- 修复前：`step=0` → `currentStep=0` → `isChatMode=true` → 渲染为 chat 建议按钮 → `handleOptionSelect` → `api.clickSuggestion`
- 修复后：`step=5` → `currentStep=5` → `OptionSelector` 组件 → `handleConfirm` → `confirmResearch`

**此 bug 一直存在但未暴露的原因**：修复前框架 sections 为空，用户看到空框架后直接放弃，不会点击按钮。修复 Fix A 后框架有内容，按钮才被渲染出来，触发此 bug。

### 已验证的既有逻辑（无需修改）

| 路径 | 行号 | 说明 |
|------|------|------|
| `_handle_chat_mode` research路径 | ~517 | 已捕获 `framework_sections` → `context["_suggested_sections"]` |
| `_handle_chat_mode` chat路径 | ~654 | 已捕获 `framework_sections` → `context["_suggested_sections"]` |
| `_do_execute_tool_background` | ~1211 | 强制 `action="continue_chat"`，不需要 `framework_sections` |

## 验证方案

1. **手动验证**：按照复现步骤操作，确认框架包含 >=4 个 sections
2. **按钮验证**：框架生成后，确认出现"确认/取消"按钮（而非普通聊天建议按钮），点击"确认"能正确进入研究执行
3. **单元测试**：覆盖 `_enter_framework_mode` 在以下场景的回退逻辑：
   - `directions=[]`, `_suggested_sections=[]` → 回退到模板章节
   - `directions=[]`, `_suggested_sections=[]`, output_type 未知 → 回退到默认 aspects
   - `directions=[]`, `_suggested_sections=[]`, LLM 推断失败 → 最终回退
4. **去重验证**：`suggested=["市场规模分析"]`, `directions=["市场规模"]` → 合并后仅1条
5. **step 验证**：`_framework_response` 返回 `step=5`，前端 `currentStep=5` 走 `OptionSelector` 渲染
6. **集成测试**：完整对话流程，验证从"搜索 → 要求形成框架 → 框架包含章节 → 点击确认 → 开始研究"的端到端行为
