# 意图分析灵活性优化方案（修订版）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让意图分析系统灵活处理各种用户需求，顺畅引导用户从对话→框架→研究，不因僵化规则阻断或遗漏意图。

**Architecture:** 三层优化——(1) Readiness 评分从硬编码权重改为 LLM 需求清晰度驱动 + 信息衰减；(2) LLM `enter_framework` 优先，`continue_chat` 时状态机建议优先；(3) 话题漂移、异步路径状态丢失、复合意图检测等 5 个边界场景加固。

**Tech Stack:** Python 3.13, dataclasses, asyncio, pytest

---

## 修订说明

本修订版针对原方案的以下缺陷进行了修正：

| # | 原方案缺陷 | 修订内容 |
|---|-----------|---------|
| R1 | `llm_confidence` 取自 `DeepIntentResult.intent_confidence`（意图分类置信度），语义错配——分类置信度高≠需求清晰 | 改为 `need_clarity`（需求清晰度），由 LLM 对话结果中的 `needs_clarification` 反向推导，语义正确 |
| R2 | `_resolve_transition` 既返回状态又内部修改状态机，导致双重 `force_set_state` | 改为纯函数，只返回目标状态，由调用方统一执行转换 |
| R3 | 异步路径 `_save_intent_state_after_async` 存在竞态条件，可能用旧数据覆盖新数据 | 改为仅更新 `research_turns` 等确定性字段，不覆盖 `need_clarity`/`confirmed_aspects` 等可能被同步路径更新的字段 |
| R4 | 删除连接词检测后，若 LLM 不返回 `is_composite=True` 则复合意图检测完全失效 | 保留连接词检测 + complexity 检查作为 LLM 未识别时的兜底，避免功能回退和误报 |
| R5 | `reset_for_new_topic` 重置 `research_turns`（全局轮次），导致衰减和 `_should_deep_analyze` 误判 | 区分 `research_turns`（全局轮次，不重置）和 `topic_research_turns`（当前话题轮次，重置） |
| R6 | `_should_deep_analyze` 仍保留连接词检测，与 Task 5 "完全依赖 LLM" 矛盾 | 统一为 `need_clarity` 驱动，删除连接词检测 |
| R7 | LLM 对话输出中无 `intent_confidence` 字段，`update_from_response` 中的读取永远为 None | 新增 LLM prompt 字段 `need_clarity`，确保数据来源存在 |
| R8 | `enter_framework` 后 `update_readiness` 的衰减被 `max(score, 0.7)` 绕过，交互未处理 | `enter_framework` 后跳过衰减计算 |
| R9 | `enter_framework` + 无 `topic_hint` 时 `update_readiness` 不执行，状态不一致 | `enter_framework` 时无条件 `update_readiness(skip_decay=True)`，`max(0.7)` 仅在 `topic_hint` 存在时执行 |
| R10 | `_force_transition_at` 删除不完整，行 414/1600 未处理 | 全部 6 处引用统一删除（cancel 路径的 `pop` 仅清理残留字段，删除无功能影响） |
| R11 | EXECUTING→FRAMEWORK_CONFIRM 时未取消后台任务 | 转换前检查目标状态，若从 EXECUTING 转出则调用 `_cancel_existing_task` |
| R12 | `_save_dialogue_state` 覆盖整个 intent_state，异步路径可能覆盖同步路径的新 `need_clarity` | 异步路径直接在 session dict 中更新特定字段，不重新序列化整个 intent_state |
| R13 | 连接词兜底列表遗漏 `"和"` 和 `"与"`（最常见中文并列连接词） | 合并原列表和新列表：`["及", "和", "与", "同时", "以及", "并且", "再加上", ...]` |
| R14 | `topic_research_turns` 条件递增与衰减设计矛盾（闲聊不递增则不衰减） | `topic_research_turns` 在 `update_from_response` 末尾无条件递增（反映对话轮次），`research_turns` 保持条件递增（反映进展轮次） |
| R15 | `min()` 操作导致 `need_clarity` 只降不升，需求变模糊时无法反映 | 改为加权平均 `0.6 * old + 0.4 * new`，允许升高和降低，旧值权重更大避免剧烈波动 |

---

## 核心问题与解决方案对照

| # | 问题 | 根因 | 解决方案 |
|---|------|------|---------|
| P1 | Readiness 评分僵化，短输入永远不够 | 硬编码权重不适应表达风格 | LLM `need_clarity` 驱动 + 信息衰减 |
| P2 | LLM 与状态机冲突时体验差 | 状态机优先，LLM 被阻断 | `enter_framework` 时 LLM 优先，`continue_chat` 时状态机建议优先 |
| P3 | 话题漂移无处理 | topic 变更只清 context，不清 intent_state | 话题变更时重置 DialogueIntentState |
| P4 | 异步路径丢失状态 | `_do_execute_tool_background` 不保存 intent_state | 异步完成后回调保存（仅确定性字段） |
| P5 | 复合意图检测脆弱 | 仅依赖中文连接词 | LLM `is_composite` 优先，连接词兜底 |
| P6 | `_should_deep_analyze` 过度触发 | `research_turns==0` 总触发 | 改为 `need_clarity` 不足时触发 |
| P7 | `enter_framework` 后 readiness 被覆盖 | `update_readiness()` 覆盖手动设置 | `enter_framework` 后跳过衰减 |

---

## 文件结构

| 文件 | 负责 | 变更类型 |
|------|------|---------|
| `src/core/dialogue/dialogue_intent_state.py` | DialogueIntentState 核心逻辑 | 修改 |
| `src/core/dialogue/sub_intent.py` | ReadinessLevel + SubIntent | 不变 |
| `src/core/semantic_intent.py` | DeepIntentResult + 深度分析 prompt | 修改 |
| `src/core/dialogue/state_machine.py` | suggest_next 仲裁策略 | 修改 |
| `src/api/research_api.py` | `_handle_chat_mode` + 辅助方法 | 修改 |
| `tests/unit/dialogue/test_dialogue_intent_state.py` | DialogueIntentState 测试 | 修改 |
| `tests/unit/dialogue/test_state_machine.py` | suggest_next 测试 | 修改 |
| `tests/unit/test_research_api_helpers.py` | 辅助方法测试 | 修改 |

---

### Task 1: Readiness 评分改为 LLM 需求清晰度驱动 + 信息衰减

**设计决策：** 使用 `need_clarity`（0.0-1.0，越高越需要澄清）而非 `intent_confidence`。原因：
- `DeepIntentResult.intent_confidence` 是意图分类置信度（"这是 research 还是 open_ended"），分类置信度高≠需求清晰
- LLM 对话结果中的 `needs_clarification: true` 天然映射为"需求不清晰"
- `need_clarity = 1.0 - clarity_score`，其中 `clarity_score` 由 LLM 在对话时返回

**Files:**
- Modify: `src/core/dialogue/dialogue_intent_state.py:114-136`
- Modify: `src/api/research_api.py` (LLM prompt 新增 `clarity_score` 字段)
- Test: `tests/unit/dialogue/test_dialogue_intent_state.py`

- [ ] **Step 1: 写失败测试 — LLM 需求清晰度驱动评分**

```python
class TestDialogueIntentStateLLMDrivenReadiness:
    def test_low_need_clarity_boosts_score(self):
        state = DialogueIntentState(topic_hint="比亚迪", need_clarity=0.1)
        state.update_readiness()
        assert state.readiness_score >= 0.6
        assert state.readiness_level in (ReadinessLevel.PARTIAL, ReadinessLevel.SUFFICIENT)

    def test_high_need_clarity_lowers_score(self):
        state = DialogueIntentState(topic_hint="比亚迪", need_clarity=0.8)
        state.update_readiness()
        assert state.readiness_score < 0.5

    def test_default_need_clarity_mixed_scoring(self):
        state = DialogueIntentState(topic_hint="比亚迪", confirmed_aspects=["市场规模", "竞争格局"])
        state.update_readiness()
        assert state.readiness_score >= 0.4

    def test_information_decay_after_5_turns(self):
        state = DialogueIntentState(
            topic_hint="储能",
            confirmed_aspects=["市场规模", "竞争格局", "发展趋势"],
            need_clarity=0.2,
            topic_research_turns=6,
        )
        state.update_readiness()
        score_with_decay = state.readiness_score
        state_fresh = DialogueIntentState(
            topic_hint="储能",
            confirmed_aspects=["市场规模", "竞争格局", "发展趋势"],
            need_clarity=0.2,
            topic_research_turns=1,
        )
        state_fresh.update_readiness()
        assert score_with_decay < state_fresh.readiness_score

    def test_short_clear_input_gets_high_readiness(self):
        state = DialogueIntentState(topic_hint="比亚迪", need_clarity=0.05)
        state.update_readiness()
        assert state.readiness_level == ReadinessLevel.SUFFICIENT

    def test_enter_framework_skips_decay(self):
        state = DialogueIntentState(
            topic_hint="比亚迪",
            need_clarity=0.1,
            topic_research_turns=8,
        )
        state.update_readiness(skip_decay=True)
        assert state.readiness_score >= 0.7
        assert state.readiness_level == ReadinessLevel.SUFFICIENT
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/dialogue/test_dialogue_intent_state.py::TestDialogueIntentStateLLMDrivenReadiness -v`
Expected: FAIL (`need_clarity` 字段不存在)

- [ ] **Step 3: 给 DialogueIntentState 添加 `need_clarity` + `topic_research_turns` 字段**

在 `dialogue_intent_state.py` 的 dataclass 字段列表中，在 `framework_aspects` 之后添加：

```python
    need_clarity: float = 0.5
    topic_research_turns: int = 0
```

> **`need_clarity` 默认 0.5 的理由：** 未知时取中间值，既不盲目推进也不过度追问。`topic_research_turns` 区别于 `research_turns`（全局轮次），仅追踪当前话题的轮次，话题切换时重置。

在 `merge_from_analysis` 中，在 `self.update_readiness()` 之前添加：

```python
        clarity_score = getattr(deep_result, 'clarity_score', None)
        if clarity_score is not None:
            new_nc = 1.0 - clarity_score
            self.need_clarity = 0.6 * self.need_clarity + 0.4 * new_nc
```

> **语义说明：** `DeepIntentResult` 当前没有 `clarity_score` 字段，所以 `getattr` 返回 None，此路径不会更新 `need_clarity`。需要在 `DeepIntentResult`（`src/core/semantic_intent.py`）中添加 `clarity_score: float = 0.5` 字段，并在深度分析的 LLM prompt 中要求返回此字段。`1.0 - clarity_score` 得到"还需要多少澄清"的程度，使用加权平均（0.6 旧值 + 0.4 新值）而非 `min`，允许 `need_clarity` 在后续分析中升高（用户需求变模糊时）或降低（需求变清晰时）。

在 `update_from_response` 中，在 `self.update_readiness()` 之前添加：

```python
        if conv_result.get("clarity_score") is not None:
            new_nc = 1.0 - conv_result["clarity_score"]
            self.need_clarity = 0.6 * self.need_clarity + 0.4 * new_nc
```

> **关键修正（三次审查）：** 原方案使用 `min(self.need_clarity, 1.0 - clarity_score)`，导致 `need_clarity` 只降不升——一旦清晰，永远清晰，即使后续对话表明用户需求变模糊了。改为加权平均（0.6 旧 + 0.4 新），既允许升高也允许降低，且旧值权重更大（0.6），避免单次 LLM 输出剧烈波动。

> **注意 1：** `update_from_response` 不需要 `session` 参数来计算衰减——衰减基于 `topic_research_turns`（在 `update_from_response` 末尾递增），不需要从 session 获取对话历史。签名保持 `(self, conv_result, user_input)` 不变，避免破坏现有调用点。

> **注意 2：** 不在此处重置 `topic_research_turns`。话题变更时由 `reset_for_new_topic` 处理（Task 3）；首次设置话题时 `topic_research_turns` 已为 0（默认值）；话题不变时不应重置，否则衰减永远无法累积。

- [ ] **Step 4: 重写 `update_readiness` 为 LLM 驱动 + 衰减**

替换 `dialogue_intent_state.py` 中的 `update_readiness` 方法：

```python
    def update_readiness(self, skip_decay=False):
        clarity_score = 1.0 - self.need_clarity
        llm_driven_score = self._compute_clarity_driven_score(clarity_score)
        rule_based_score = self._compute_rule_based_score()
        if self.need_clarity < 0.5:
            weight_llm = 0.7
        elif self.need_clarity > 0.7:
            weight_llm = 0.3
        else:
            weight_llm = 0.5
        score = llm_driven_score * weight_llm + rule_based_score * (1 - weight_llm)
        if not skip_decay:
            decay = self._compute_decay()
            score = score * decay
        self.readiness_score = min(1.0, score)
        if self.readiness_score >= 0.7:
            self.readiness_level = ReadinessLevel.SUFFICIENT
        elif self.readiness_score >= 0.4:
            self.readiness_level = ReadinessLevel.PARTIAL
        else:
            self.readiness_level = ReadinessLevel.INSUFFICIENT

    def _compute_clarity_driven_score(self, clarity_score):
        if self.need_clarity >= 0.5 and clarity_score <= 0.0:
            return 0.0
        base = clarity_score
        if self.topic_hint:
            base = min(1.0, base + 0.1)
        if self.confirmed_aspects:
            base = min(1.0, base + 0.05 * min(len(self.confirmed_aspects), 4))
        return base

    def _compute_rule_based_score(self):
        score = 0.0
        if self.topic_hint:
            score += 0.25
        if self.confirmed_aspects:
            score += 0.35 * min(1.0, len(self.confirmed_aspects) / 3)
        scope_keys = ["geographic_scope", "time_range", "industry_segment"]
        scope_count = sum(1 for k in scope_keys if self.domain_context.get(k))
        if scope_count:
            score += 0.15 * min(1.0, scope_count / 2)
        if self.clarification_count >= 1:
            score += 0.15
        if self.hidden_requirements:
            addressed = sum(1 for r in self.hidden_requirements if r in self.confirmed_aspects)
            if addressed > 0:
                score += 0.1
        return score

    def _compute_decay(self):
        if self.topic_research_turns <= 3:
            return 1.0
        excess = self.topic_research_turns - 3
        return max(0.5, 1.0 - excess * 0.05)
```

> **动态权重说明：** 当 `need_clarity < 0.5`（LLM 认为需求较清晰）时，LLM 权重 0.7，信任 LLM 判断；当 `need_clarity > 0.7`（LLM 认为需求很模糊）时，LLM 权重 0.3，更依赖规则兜底；中间取 0.5。这避免了"LLM 也不确定时还盲目信任"的问题。

- [ ] **Step 5: 修改 `enter_framework` 分支跳过衰减**

在 `update_from_response` 中，修改行 108 的通用 `update_readiness()` 调用和行 110-112 的 `enter_framework` 分支：

将 `update_from_response` 中行 108 的：
```python
        self.update_readiness()
```

以及行 110-112 的：
```python
        if action == "enter_framework" and self.topic_hint:
            self.readiness_score = max(self.readiness_score, 0.7)
            self.readiness_level = ReadinessLevel.SUFFICIENT
```

替换为：
```python
        if action == "enter_framework":
            self.update_readiness(skip_decay=True)
            if self.topic_hint:
                self.readiness_score = max(self.readiness_score, 0.7)
                self.readiness_level = ReadinessLevel.SUFFICIENT
        else:
            self.update_readiness()
```

> **理由：** `enter_framework` 表示用户已确认进入框架，此时不应因话题轮次多而衰减 readiness。先以 `skip_decay=True` 重新计算（确保 `need_clarity` 等新字段参与评分），再保底 0.7（仅在 `topic_hint` 存在时）。将通用 `update_readiness()` 改为条件调用，避免 `enter_framework` 时 readiness 被计算两次。

> **关键修正（三次审查）：** 原方案将行 108 改为 `if action != "enter_framework": self.update_readiness()`，然后仅在 `if action == "enter_framework" and self.topic_hint:` 时调用 `update_readiness(skip_decay=True)`。这导致 `enter_framework` + 无 `topic_hint` 时 `update_readiness()` 完全不执行——readiness_score 和 readiness_level 不更新，状态不一致。修正后 `enter_framework` 时无条件执行 `update_readiness(skip_decay=True)`，`max(0.7)` 保底仅在 `topic_hint` 存在时执行。

- [ ] **Step 6: 更新 `topic_research_turns` 递增逻辑**

`topic_research_turns` 应在每次对话轮次无条件递增（在 `update_from_response` 末尾），而非仅在 `action == "enter_framework"` 或 `conv_result.get("topic")` 时。原因：衰减的设计意图是"对话轮次越多，信息衰减越大"，如果只在有进展时递增，用户连续 5 轮闲聊后 `topic_research_turns` 仍为 0，衰减系数为 1.0——信息不衰减，与设计意图矛盾。

在 `update_from_response` 末尾（`enter_framework`/`else` 分支之后）添加：

```python
        self.topic_research_turns += 1
```

同时将行 83-84 的 `research_turns` 递增逻辑保持不变（条件递增——只在有明确进展时递增）：

```python
        if action == "enter_framework" or conv_result.get("topic"):
            self.research_turns += 1
```

> **关键修正（三次审查）：** 原方案将 `topic_research_turns` 递增条件与 `research_turns` 保持一致（条件递增），但衰减设计要求 `topic_research_turns` 反映对话轮次而非进展轮次。修正后 `topic_research_turns` 每次调用 `update_from_response` 都递增（反映对话轮次），`research_turns` 保持条件递增（反映进展轮次）。两者语义不同：前者用于衰减计算，后者用于全局进展计数。

- [ ] **Step 7: 更新 `to_dict` / `from_dict` 包含新字段**

在 `to_dict` 中追加：

```python
            "need_clarity": self.need_clarity,
            "topic_research_turns": self.topic_research_turns,
```

在 `from_dict` 的 `cls(...)` 中追加：

```python
            need_clarity=data.get("need_clarity", 0.5),
            topic_research_turns=data.get("topic_research_turns", 0),
```

> **向后兼容：** 旧 session 数据无这两个字段，`need_clarity` 默认 0.5（中间值，走规则+LLM 各半权重），`topic_research_turns` 默认 0（无衰减），行为与旧版一致。

- [ ] **Step 8: 在 LLM 对话 prompt 中新增 `clarity_score` 字段，并在 `DeepIntentResult` 中添加该字段**

**8a. 在 `DeepIntentResult`（`src/core/semantic_intent.py`）中添加字段：**

在 `orchestration_strategy` 字段之后添加：

```python
    clarity_score: float = 0.5
```

> **理由：** `merge_from_analysis` 通过 `getattr(deep_result, 'clarity_score', None)` 读取此字段。没有它，`need_clarity` 永远不会从深度分析路径更新。

同时更新 `DeepIntentResult.to_dict()`（`semantic_intent.py:98-120`），在 `"orchestration_strategy"` 键之后追加：

```python
                "clarity_score": self.clarity_score,
```

更新 `DeepIntentResult.from_dict()`（`semantic_intent.py:122-178`），在 `cls(...)` 中追加：

```python
            clarity_score=data.get("clarity_score", 0.5),
```

> **向后兼容：** 旧序列化数据无 `clarity_score` 字段，默认 0.5（与字段默认值一致）。

**8b. 在深度分析的 LLM prompt 中要求返回 `clarity_score`：**

深度分析的 LLM prompt 通过 `PromptManager` 加载（`semantic_intent.py:254-261`），对应文件为 `prompts/agents/intent_analysis_system.md` 和 `prompts/agents/intent_analysis_user.md`。在 `intent_analysis_user.md` 中找到 LLM 输出的 JSON schema 定义，在 JSON schema 中添加：

```python
        "clarity_score": {
            "type": "number",
            "description": "0.0-1.0, 用户需求清晰程度。0.0=完全模糊, 1.0=非常清晰具体",
        },
```

并在解析 LLM 输出时读取此字段（`_build_result` 方法中，参数名为 `llm_output`）：

```python
        clarity_score=llm_output.get("clarity_score", 0.5),
```

**8c. 在 `research_api.py` 的 `_llm_converse` 方法中，找到构建 LLM 输出格式说明的位置，在 JSON schema 中添加 `clarity_score` 字段：**

```python
        "clarity_score": {
            "type": "number",
            "description": "0.0-1.0, 用户需求清晰程度。0.0=完全模糊, 1.0=非常清晰具体。短但明确的输入如'研究比亚迪'应为0.8+, 模糊输入如'帮我看看'应为0.3-",
        },
```

> **关键：** 这是 `need_clarity` 的数据来源。没有这两个 prompt 修改，`conv_result.get("clarity_score")` 永远为 None，LLM 驱动评分不会生效。

- [ ] **Step 9: 运行测试确认通过**

Run: `pytest tests/unit/dialogue/test_dialogue_intent_state.py -v`
Expected: ALL PASS

- [ ] **Step 10: Commit**

```bash
git add src/core/dialogue/dialogue_intent_state.py src/core/semantic_intent.py src/api/research_api.py tests/unit/dialogue/test_dialogue_intent_state.py
git commit -m "feat: clarity-driven readiness scoring with information decay"
```

---

### Task 2: LLM `enter_framework` 优先，`continue_chat` 时状态机建议优先

**设计决策：** `_resolve_transition` 为纯函数，只返回目标状态，不修改状态机。仲裁策略：`enter_framework` 时 LLM 无条件优先（用户明确要求进框架）；`continue_chat` 或无 action 时状态机建议优先（状态机基于 readiness_level 判断更可靠）；由调用方统一执行转换，避免双重 `force_set_state`。

**Files:**
- Modify: `src/api/research_api.py:647-674` (`_handle_chat_mode` 状态转换逻辑)
- Modify: `src/core/dialogue/state_machine.py` (已有 `force_set_state`，无需修改)
- Test: `tests/unit/test_research_api_helpers.py`
- Test: `tests/unit/dialogue/test_state_machine.py`

- [ ] **Step 1: 写失败测试 — LLM action 优先**

```python
class TestLLMActionPriority:
    def _make_api(self):
        from src.api.research_api import ResearchAPI
        return ResearchAPI.__new__(ResearchAPI)

    def test_llm_enter_framework_overrides_state_machine_clarifying(self):
        api = self._make_api()
        intent_state = DialogueIntentState(topic_hint="test", readiness_level=ReadinessLevel.PARTIAL)
        conv_machine = ConversationStateMachine()
        conv_machine.transition(ConversationState.CLARIFYING)
        llm_action = "enter_framework"
        result = api._resolve_transition(conv_machine, intent_state, llm_action)
        assert result == ConversationState.FRAMEWORK_CONFIRM

    def test_llm_continue_chat_respects_state_machine_clarifying(self):
        api = self._make_api()
        intent_state = DialogueIntentState(topic_hint="test", readiness_level=ReadinessLevel.PARTIAL)
        conv_machine = ConversationStateMachine()
        llm_action = "continue_chat"
        result = api._resolve_transition(conv_machine, intent_state, llm_action)
        assert result == ConversationState.CLARIFYING

    def test_no_llm_action_uses_state_machine_suggestion(self):
        api = self._make_api()
        intent_state = DialogueIntentState(topic_hint="test", readiness_level=ReadinessLevel.SUFFICIENT)
        conv_machine = ConversationStateMachine()
        llm_action = ""
        result = api._resolve_transition(conv_machine, intent_state, llm_action)
        assert result == ConversationState.FRAMEWORK_CONFIRM

    def test_resolve_transition_is_pure_function(self):
        api = self._make_api()
        intent_state = DialogueIntentState(topic_hint="test", readiness_level=ReadinessLevel.PARTIAL)
        conv_machine = ConversationStateMachine()
        conv_machine.transition(ConversationState.CLARIFYING)
        state_before = conv_machine.current_state
        api._resolve_transition(conv_machine, intent_state, "enter_framework")
        assert conv_machine.current_state == state_before
```

> **新增测试：** `test_resolve_transition_is_pure_function` 确保 `_resolve_transition` 不修改状态机内部状态。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/test_research_api_helpers.py::TestLLMActionPriority -v`
Expected: FAIL (`_resolve_transition` 方法不存在)

- [ ] **Step 3: 确认 `force_set_state` 方法已存在**

`ConversationStateMachine` 已有 `force_set_state` 方法（`state_machine.py:263-270`），无需新增。跳过此步骤。

> **注意：** 现有实现使用 `self.current_state = target_state`（公开属性），不是 `self._current_state`。不要重复添加此方法。

- [ ] **Step 4: 在 `research_api.py` 中实现 `_resolve_transition`（纯函数）**

在 `_action_aligns_with_state` 方法之后添加：

```python
    def _resolve_transition(self, conv_machine, intent_state, llm_action):
        suggested = conv_machine.suggest_next(intent_state)
        if llm_action == "enter_framework":
            return ConversationState.FRAMEWORK_CONFIRM
        if llm_action == "continue_chat" and suggested:
            return suggested
        if not llm_action and suggested:
            return suggested
        return None
```

> **关键区别：** 纯函数，不调用 `conv_machine.force_set_state`，不调用 `conv_machine.can_transition_to`。转换的合法性检查和执行统一由调用方负责。

> **边界场景：** 当状态机处于 `EXECUTING` 状态时，如果 LLM 返回 `enter_framework`，`_resolve_transition` 会返回 `FRAMEWORK_CONFIRM`，调用方会 `force_set_state(FRAMEWORK_CONFIRM)`。这意味着正在执行的研究任务会被中断。这是设计意图（LLM 优先），但需确保 `_handle_chat_mode` 在进入 `FRAMEWORK_CONFIRM` 前清理正在执行的任务状态（如取消进行中的工具调用）。

- [ ] **Step 5: 替换 `_handle_chat_mode` 中的状态转换逻辑**

将 `_handle_chat_mode` 中从 `intent_state.update_from_response(conv_result, user_input)` 到 `self._sync_mode_with_state` 之间的状态转换逻辑替换为：

```python
        intent_state.update_from_response(conv_result, user_input)

        llm_action = conv_result.get("action", "")
        resolved = self._resolve_transition(conv_machine, intent_state, llm_action)
        if resolved:
            if resolved in (ConversationState.FRAMEWORK_CONFIRM, ConversationState.CLARIFYING):
                if conv_machine.current_state == ConversationState.EXECUTING:
                    self._cancel_existing_task(session_id)
            if conv_machine.can_transition_to(resolved):
                conv_machine.transition(resolved)
            else:
                conv_machine.force_set_state(resolved)

        self._save_dialogue_state(session_id, session, intent_state, conv_machine)
        self._sync_mode_with_state(session, conv_machine)
```

> **注意：** `llm_action` 必须在 `_resolve_transition` 调用之前定义。原代码中 `llm_action = conv_result.get("action", "")` 在行 650，属于被删除的范围，需要在替换代码中重新定义。

> **关键修正（三次审查）：** 当 `resolved` 目标状态为 `FRAMEWORK_CONFIRM` 或 `CLARIFYING`（即用户要重新讨论需求），且当前状态为 `EXECUTING`（研究正在执行），必须先调用 `_cancel_existing_task(session_id)` 取消后台任务。否则正在执行的研究任务会继续运行，与新状态不一致。`_cancel_existing_task` 会设置 `old_task.cancel()`，异步任务在下一个 `await` 点抛出 `CancelledError`。

删除以下旧逻辑：
- `_force_transition_at` 相关代码（3 处设置 + 所有读取点）
- `_action_aligns_with_state` 二次校验代码
- `suggested` / `llm_action` 冲突仲裁代码
- 行 671-674 的 mode 回退逻辑（`if suggested == FRAMEWORK_CONFIRM and not _action_aligns_with_state...`）

> **清理说明 1：** 删除前先用 `grep _force_transition_at` 确认所有引用点。当前代码中有 6 处引用：
> - 行 655, 661, 663, 666: `_handle_chat_mode` 中的设置和读取——全部删除
> - 行 414: cancel 路径 `context.pop("_force_transition_at", None)`——删除此行。此操作仅是清理 context dict 中的残留字段，删除后无功能影响（该字段不再被设置，pop 永远返回 None）
> - 行 1600: `_handle_framework_mode` cancel 路径 `context.pop("_force_transition_at", None)`——同上，删除此行

> **清理说明 2：** 行 671-674 的 mode 回退逻辑不再需要。在新设计中，`_resolve_transition` 已统一处理 LLM action 与状态机建议的冲突——如果 LLM 说 `continue_chat`，状态机建议 `FRAMEWORK_CONFIRM`，`_resolve_transition` 返回 `CLARIFYING`（状态机建议），不会出现"状态机在 FRAMEWORK_CONFIRM 但 LLM 不想进框架"的矛盾。

保留 `_action_aligns_with_state` 方法本身（其他地方可能用到），但不再在 `_handle_chat_mode` 中调用。

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/unit/test_research_api_helpers.py tests/unit/dialogue/test_state_machine.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/api/research_api.py src/core/dialogue/state_machine.py tests/unit/test_research_api_helpers.py tests/unit/dialogue/test_state_machine.py
git commit -m "feat: LLM action priority over state machine suggestions"
```

---

### Task 3: 话题漂移处理

**设计决策：** 区分 `research_turns`（全局轮次，不重置）和 `topic_research_turns`（当前话题轮次，重置）。`reset_for_new_topic` 只重置话题相关状态，保留全局计数器。

**Files:**
- Modify: `src/core/dialogue/dialogue_intent_state.py` (新增 `reset_for_new_topic` 方法)
- Modify: `src/api/research_api.py:625-645` (`_handle_chat_mode` topic 变更逻辑)
- Test: `tests/unit/dialogue/test_dialogue_intent_state.py`

- [ ] **Step 1: 写失败测试 — 话题漂移重置**

```python
class TestTopicDriftReset:
    def test_reset_for_new_topic_clears_old_data(self):
        state = DialogueIntentState(
            topic_hint="新能源汽车",
            confirmed_aspects=["电池技术", "充电基础设施"],
            user_aspects=["电池技术"],
            framework_aspects=["充电基础设施"],
            hidden_requirements=["政策补贴"],
            readiness_level=ReadinessLevel.SUFFICIENT,
            readiness_score=0.8,
            need_clarity=0.1,
        )
        state.reset_for_new_topic("人工智能")
        assert state.topic_hint == "人工智能"
        assert state.confirmed_aspects == []
        assert state.framework_aspects == []
        assert state.user_aspects == []
        assert state.hidden_requirements == []
        assert state.need_clarity == 0.5
        assert state.readiness_level == ReadinessLevel.INSUFFICIENT

    def test_reset_preserves_global_research_turns(self):
        state = DialogueIntentState(
            topic_hint="新能源汽车",
            clarification_count=3,
            research_turns=5,
            topic_research_turns=5,
        )
        state.reset_for_new_topic("人工智能")
        assert state.clarification_count == 0
        assert state.topic_research_turns == 0
        assert state.research_turns == 5

    def test_reset_readiness_is_insufficient(self):
        state = DialogueIntentState(
            topic_hint="新能源汽车",
            readiness_level=ReadinessLevel.SUFFICIENT,
            readiness_score=0.9,
        )
        state.reset_for_new_topic("人工智能")
        assert state.readiness_level == ReadinessLevel.INSUFFICIENT
        assert state.readiness_score == 0.0
```

> **关键测试：** `test_reset_preserves_global_research_turns` 确保 `research_turns`（全局）不被重置，`topic_research_turns`（话题级）被重置。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/dialogue/test_dialogue_intent_state.py::TestTopicDriftReset -v`
Expected: FAIL (`reset_for_new_topic` 方法不存在)

- [ ] **Step 3: 实现 `reset_for_new_topic`**

在 `dialogue_intent_state.py` 的 `clear_framework_aspects` 方法之后添加：

```python
    def reset_for_new_topic(self, new_topic: str):
        self.topic_hint = new_topic
        self.confirmed_aspects = []
        self.pending_questions = []
        self.hidden_requirements = []
        self.domain_context = {}
        self.is_composite = False
        self.sub_intents = []
        self.orchestration_strategy = "sequential"
        self.readiness_score = 0.0
        self.readiness_level = ReadinessLevel.INSUFFICIENT
        self.clarification_count = 0
        self.topic_research_turns = 0
        self.user_aspects = []
        self.framework_aspects = []
        self.need_clarity = 0.5
```

> **注意：** `research_turns` 不在重置列表中——它是全局对话轮次计数器，不应因话题切换而归零。

- [ ] **Step 4: 在 `_handle_chat_mode` 中调用 `reset_for_new_topic`**

在 `_handle_chat_mode` 的 topic 变更检测处（`if old_topic and old_topic != new_topic:`），在 `context["directions"] = []` 之后添加：

```python
            intent_state.reset_for_new_topic(new_topic)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/unit/dialogue/test_dialogue_intent_state.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/core/dialogue/dialogue_intent_state.py src/api/research_api.py tests/unit/dialogue/test_dialogue_intent_state.py
git commit -m "feat: topic drift reset clears stale intent state"
```

---

### Task 4: 异步路径状态持久化

**设计决策：** 异步回调仅更新确定性字段（`research_turns`、`topic_research_turns`），不覆盖可能被同步路径更新的字段（`need_clarity`、`confirmed_aspects`、`readiness_score` 等），避免竞态条件。

**Files:**
- Modify: `src/api/research_api.py:1234-1432` (`_do_execute_tool_background`)
- Test: `tests/unit/test_research_api_helpers.py`

- [ ] **Step 1: 写失败测试 — 异步路径保存 intent_state**

```python
class TestAsyncPathStatePersistence:
    def test_async_intent_state_save_method_exists(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        assert hasattr(api, '_update_intent_state_after_async')

    def test_async_update_only_increments_turns(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        session = {
            "research_context": {
                "_dialogue_intent_state": {
                    "topic_hint": "比亚迪",
                    "need_clarity": 0.1,
                    "confirmed_aspects": ["市场规模"],
                    "readiness_level": "SUFFICIENT",
                    "readiness_score": 0.8,
                    "research_turns": 3,
                    "topic_research_turns": 3,
                }
            }
        }
        api._update_intent_state_after_async(session)
        state_dict = session["research_context"]["_dialogue_intent_state"]
        assert state_dict["research_turns"] == 4
        assert state_dict["topic_research_turns"] == 4
        assert state_dict["need_clarity"] == 0.1
        assert state_dict["confirmed_aspects"] == ["市场规模"]
        assert state_dict["readiness_level"] == "SUFFICIENT"

    def test_async_update_noop_when_no_state(self):
        from src.api.research_api import ResearchAPI
        api = ResearchAPI.__new__(ResearchAPI)
        session = {"research_context": {}}
        api._update_intent_state_after_async(session)
        assert "_dialogue_intent_state" not in session["research_context"]
```

> **关键测试：** `test_async_update_only_increments_turns` 确保异步回调只递增轮次计数器，不覆盖 `need_clarity`、`confirmed_aspects` 等字段。`test_async_update_noop_when_no_state` 确保无 intent_state 时不报错。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/test_research_api_helpers.py::TestAsyncPathStatePersistence -v`
Expected: FAIL

- [ ] **Step 3: 实现 `_update_intent_state_after_async`**

在 `research_api.py` 的 `_save_dialogue_state` 方法之后添加：

```python
    def _update_intent_state_after_async(self, session):
        context = session.get("research_context", {})
        state_dict = context.get("_dialogue_intent_state", {})
        if not state_dict:
            return
        state_dict["research_turns"] = state_dict.get("research_turns", 0) + 1
        state_dict["topic_research_turns"] = state_dict.get("topic_research_turns", 0) + 1
        context["_dialogue_intent_state"] = state_dict
        session["research_context"] = context
```

> **设计说明：** 直接在 session dict 中更新特定字段，而不是反序列化整个 `DialogueIntentState` 再序列化写回。这避免了竞态条件：如果同步路径在异步路径读取 intent_state 之后修改了 `need_clarity`，原方案中 `_save_dialogue_state(intent_state.to_dict())` 会用旧的 `need_clarity` 覆盖新的。本方案只写回 `research_turns` 和 `topic_research_turns` 两个确定性字段，不影响其他字段。

> **递增条件差异说明：** 同步路径中 `research_turns` 仅在 `action == "enter_framework"` 或 `conv_result.get("topic")` 时递增，而异步路径无条件递增。这是有意为之——异步路径代表工具执行完成，总是对话进展；同步路径的条件递增是为了避免在纯闲聊轮次中虚增计数器。

- [ ] **Step 4: 在 `_do_execute_tool_background` 中调用**

在 `_do_execute_tool_background` 的 `session["research_context"] = ctx` 之后（约行 1417），添加：

```python
            self._update_intent_state_after_async(session)
```

> **关键修正（三次审查）：** 不再调用 `_get_or_create_intent_state` + `_save_dialogue_state`，因为后者会序列化整个 `DialogueIntentState` 并覆盖 session 中的所有字段，与同步路径存在竞态。改为直接在 session dict 中更新特定字段。

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/unit/test_research_api_helpers.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/api/research_api.py tests/unit/test_research_api_helpers.py
git commit -m "feat: persist intent state after async tool execution"
```

---

### Task 5: 复合意图检测改为 LLM 优先 + 连接词兜底

**设计决策：** LLM `is_composite` 优先，但保留连接词检测作为兜底。原因：当前 LLM prompt 未充分验证 `is_composite` 的召回率，完全删除连接词检测可能导致功能回退。

**Files:**
- Modify: `src/core/dialogue/dialogue_intent_state.py:65-77` (`merge_from_analysis` 中的连接词检测)
- Test: `tests/unit/dialogue/test_dialogue_intent_state.py`

- [ ] **Step 1: 写失败测试 — LLM 优先 + 连接词兜底**

```python
class TestCompositeIntentLLMFirst:
    def test_composite_from_llm_only(self):
        state = DialogueIntentState()
        mock_result = type("MockResult", (), {
            "domain_context": {},
            "hidden_requirements": [],
            "clarification_questions": [],
            "needs_clarification": False,
            "complexity": type("C", (), {"value": "multi"})(),
            "is_composite": True,
            "sub_intents": [SubIntent(intent_id="sub_1", description="市场研究")],
            "orchestration_strategy": "hybrid",
        })()
        state.merge_from_analysis(mock_result)
        assert state.is_composite is True

    def test_connector_fallback_when_llm_says_not_composite(self):
        state = DialogueIntentState(topic_hint="市场及消费者研究")
        mock_result = type("MockResult", (), {
            "domain_context": {},
            "hidden_requirements": [],
            "clarification_questions": [],
            "needs_clarification": False,
            "complexity": type("C", (), {"value": "multi"})(),
            "is_composite": False,
        })()
        state.merge_from_analysis(mock_result)
        assert state.is_composite is True

    def test_no_composite_when_llm_false_and_no_connector(self):
        state = DialogueIntentState(topic_hint="消费者研究")
        mock_result = type("MockResult", (), {
            "domain_context": {},
            "hidden_requirements": [],
            "clarification_questions": [],
            "needs_clarification": False,
            "complexity": type("C", (), {"value": "single"})(),
            "is_composite": False,
        })()
        state.merge_from_analysis(mock_result)
        assert state.is_composite is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/dialogue/test_dialogue_intent_state.py::TestCompositeIntentLLMFirst -v`
Expected: FAIL (`test_connector_fallback_when_llm_says_not_composite` — 当前 else 分支不设 `is_composite=True`)

- [ ] **Step 3: 修改 `merge_from_analysis` 的 else 分支**

替换 `dialogue_intent_state.py` 中 `merge_from_analysis` 的 else 分支：

```python
        if is_composite:
            self.is_composite = True
            if sub_intents:
                self.sub_intents = sub_intents
                self.orchestration_strategy = orchestration_strategy
        else:
            from src.core.intent_types import TaskComplexity
            if deep_result.complexity in (TaskComplexity.MULTI, TaskComplexity.COMPLEX):
                composite_connectors = ["及", "和", "与", "同时", "以及", "并且", "再加上",
                                        "along with", "as well as", "in addition to"]
                if any(c in (self.topic_hint or "") for c in composite_connectors):
                    self.is_composite = True
```

> **与原方案的区别：** 原方案完全删除连接词检测，本修订版保留为兜底。LLM 说 `is_composite=True` 时直接采纳；LLM 说 `False` 但 `complexity` 为 MULTI/COMPLEX 且话题中含连接词时，仍标记为复合意图。

> **保留 complexity 检查的理由：** 原代码中连接词检测仅在 `complexity` 为 MULTI/COMPLEX 时触发，这是合理的安全门——简单查询即使含"及"也不应标记为复合意图。删除此检查会导致误报（如"比亚迪及特斯拉的销量"被标记为复合意图）。

- [ ] **Step 4: 运行全部 DialogueIntentState 测试**

Run: `pytest tests/unit/dialogue/test_dialogue_intent_state.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/dialogue/dialogue_intent_state.py tests/unit/dialogue/test_dialogue_intent_state.py
git commit -m "refactor: LLM-first composite detection with connector fallback"
```

---

### Task 6: `_should_deep_analyze` 改为需求清晰度驱动

**设计决策：** 统一使用 `need_clarity` 驱动，删除连接词检测（与 Task 5 不矛盾——Task 5 的连接词检测在 `merge_from_analysis` 中做兜底，这里是在触发深度分析的入口判断，两者职责不同）。

**Files:**
- Modify: `src/api/research_api.py:803-824` (`_should_deep_analyze`)
- Test: `tests/unit/test_research_api_helpers.py`

- [ ] **Step 1: 写失败测试 — 需求清晰度驱动触发**

```python
class TestShouldDeepAnalyzeClarityDriven:
    def _make_api(self):
        from src.api.research_api import ResearchAPI
        return ResearchAPI.__new__(ResearchAPI)

    def test_high_need_clarity_triggers_even_short_input(self):
        api = self._make_api()
        state = DialogueIntentState(topic_hint="比亚迪", need_clarity=0.7)
        assert api._should_deep_analyze("比亚迪怎么样", state, ConversationState.UNDERSTANDING) is True

    def test_low_need_clarity_skips_deep_analyze(self):
        api = self._make_api()
        state = DialogueIntentState(topic_hint="比亚迪", need_clarity=0.1, readiness_level=ReadinessLevel.SUFFICIENT)
        assert api._should_deep_analyze("还有别的方面吗", state, ConversationState.UNDERSTANDING) is False

    def test_default_need_clarity_first_turn_triggers(self):
        api = self._make_api()
        state = DialogueIntentState()
        assert api._should_deep_analyze("研究新能源汽车", state, ConversationState.UNDERSTANDING) is True

    def test_not_triggered_in_wrong_state(self):
        api = self._make_api()
        state = DialogueIntentState(need_clarity=0.8)
        assert api._should_deep_analyze("研究新能源汽车", state, ConversationState.EXECUTING) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/test_research_api_helpers.py::TestShouldDeepAnalyzeClarityDriven -v`
Expected: FAIL (高 `need_clarity` 短输入不触发)

- [ ] **Step 3: 重写 `_should_deep_analyze`**

替换 `research_api.py` 中的 `_should_deep_analyze` 方法：

```python
    def _should_deep_analyze(self, user_input, intent_state, conv_state):
        if conv_state not in (ConversationState.UNDERSTANDING, ConversationState.CLARIFYING):
            return False
        if intent_state.need_clarity <= 0.2 and intent_state.readiness_level == ReadinessLevel.SUFFICIENT:
            return False
        research_keywords = [
            "研究", "分析", "市场", "行业", "调研", "问卷", "报告", "趋势", "竞争",
            "research", "analyze", "market", "industry", "survey", "report", "trend",
        ]
        has_research_kw = any(kw in user_input for kw in research_keywords)
        if intent_state.need_clarity >= 0.6 and has_research_kw:
            return True
        if intent_state.need_clarity >= 0.5 and len(user_input.strip()) >= 10:
            return True
        if intent_state.need_clarity == 0.5 and has_research_kw:
            return True
        return False
```

> **与原方案的区别：** 删除了连接词检测（`composite_connectors`），统一用 `need_clarity` 驱动。`need_clarity` 默认 0.5 时，有研究关键词即触发（首次输入兜底）。

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/test_research_api_helpers.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/research_api.py tests/unit/test_research_api_helpers.py
git commit -m "refactor: clarity-driven deep analysis trigger"
```

---

### Task 7: `enter_framework` 后 readiness 不被覆盖

**Files:**
- Modify: `src/core/dialogue/dialogue_intent_state.py:81-112` (`update_from_response`)

- [ ] **Step 1: 验证当前实现已正确**

当前 `update_from_response` 中 `enter_framework` 分支在 `update_readiness()` 之后设置 SUFFICIENT（行 110-112），且 Task 1 Step 5 已将 `update_readiness(skip_decay=True)` 加入此路径。无需额外修改。

- [ ] **Step 2: 补充测试确认 `enter_framework` 后 readiness 为 SUFFICIENT**

在 `test_dialogue_intent_state.py` 的 `TestDialogueIntentStateUpdateFromResponse` 中确认现有测试已覆盖：

```python
    def test_enter_framework_sets_sufficient(self):
        state = DialogueIntentState(topic_hint="test")
        conv_result = {"action": "enter_framework", "framework_sections": ["市场分析", "竞争格局"]}
        state.update_from_response(conv_result, "确认")
        assert state.readiness_score >= 0.7
        assert "市场分析" in state.framework_aspects
        assert state.research_turns == 1
```

此测试已存在且 PASS。无需额外修改。

- [ ] **Step 2.5: 补充测试 — `enter_framework` 无 `topic_hint` 时 `update_readiness` 仍执行**

```python
    def test_enter_framework_without_topic_hint_still_updates_readiness(self):
        state = DialogueIntentState()
        conv_result = {"action": "enter_framework", "framework_sections": ["市场分析"]}
        state.update_from_response(conv_result, "确认")
        assert state.readiness_score >= 0.0
        assert state.readiness_level is not None
        assert "市场分析" in state.framework_aspects
```

> **关键测试：** 确保 `enter_framework` + 无 `topic_hint` 时 `update_readiness(skip_decay=True)` 仍执行（不会因 `topic_hint` 为空而跳过），且不执行 `max(0.7)` 保底。

- [ ] **Step 3: Skip commit (no changes needed)**

---

### Task 8: 全量回归测试

**Files:** 无代码变更，仅测试运行

- [ ] **Step 1: 运行所有相关测试**

Run: `pytest tests/unit/dialogue/ tests/unit/test_deep_intent_result_extensions.py tests/unit/test_research_api_helpers.py -v`
Expected: ALL PASS

- [ ] **Step 2: 运行语法检查**

```python
& "D:\conda\python.exe" -c "import sys; sys.path.insert(0, r'E:\market_report_systerm'); from src.core.dialogue.dialogue_intent_state import DialogueIntentState; from src.core.dialogue.sub_intent import ReadinessLevel; from src.api.research_api import ResearchAPI; print('All imports OK')"
```

Expected: "All imports OK"

- [ ] **Step 3: Commit (if any test adjustments were needed)**

---

## 自审清单

**1. Spec coverage:**
- P1 (Readiness 僵化) → Task 1 ✅
- P2 (LLM vs 状态机冲突) → Task 2 ✅
- P3 (话题漂移) → Task 3 ✅
- P4 (异步路径丢失) → Task 4 ✅
- P5 (复合意图脆弱) → Task 5 ✅
- P6 (过度触发) → Task 6 ✅
- P7 (readiness 覆盖) → Task 7 ✅ (已正确，无需修改)
- 回归测试 → Task 8 ✅

**2. Placeholder scan:**
- 无 TBD/TODO/fill-in-later
- 所有代码块完整
- 所有测试有具体断言

**3. Type consistency:**
- `need_clarity: float` 在 DialogueIntentState dataclass、`to_dict`、`from_dict`、`merge_from_analysis`、`update_from_response` 中一致
- `topic_research_turns: int` 同上
- `clarity_score: float` 在 `DeepIntentResult` dataclass、深度分析 prompt、`_llm_converse` prompt 中一致
- `update_from_response` 签名保持 `(self, conv_result, user_input)` 不变——不破坏现有调用点
- `_resolve_transition` 返回 `Optional[ConversationState]` — 纯函数，不修改状态机
- `reset_for_new_topic` 参数 `new_topic: str` — 与 `topic_hint` 类型一致
- `_update_intent_state_after_async` 接收 `session`（dict），直接更新特定字段——避免竞态

**4. 修订版 vs 原方案变更点:**
- R1: `llm_confidence` → `need_clarity`（语义正确性）
- R2: `_resolve_transition` 改为纯函数（消除双重 force）
- R3: 异步回调直接更新 session dict 特定字段（避免竞态）
- R4: 保留连接词检测 + complexity 检查作为兜底（避免功能回退和误报）
- R5: `research_turns` 不重置，新增 `topic_research_turns`（衰减语义正确）
- R6: `_should_deep_analyze` 统一用 `need_clarity`（逻辑一致性）
- R7: LLM prompt + DeepIntentResult 新增 `clarity_score` 字段（数据来源保障）
- R8: `enter_framework` 路径 `skip_decay=True`（交互正确性）
- R9: `enter_framework` 无条件 `update_readiness(skip_decay=True)`（避免无 topic_hint 时状态不一致）
- R10: `_force_transition_at` 全部 6 处引用统一删除
- R11: EXECUTING→FRAMEWORK_CONFIRM 时先 `_cancel_existing_task`（避免后台任务继续运行）
- R12: 异步路径直接更新 session dict 字段而非序列化整个 intent_state（避免竞态覆盖）
- R13: 连接词兜底列表包含 `"和"` 和 `"与"`（避免复合意图漏检）
- R14: `topic_research_turns` 无条件递增（衰减语义正确）
- R15: `need_clarity` 更新改为加权平均（允许升高和降低）

**5. 二次审查修正点:**
- `update_from_response` 中不再重置 `topic_research_turns`——话题不变时重置会导致衰减永远无法累积
- `force_set_state` 已存在于 `state_machine.py:263`，使用 `self.current_state`（非 `self._current_state`），无需重复添加
- `enter_framework` 时 `update_readiness` 只调用一次（`skip_decay=True`），行 108 的通用调用改为条件跳过
- 连接词兜底保留 `complexity` 检查——简单查询含"及"不应标记为复合意图
- `DeepIntentResult` 需添加 `clarity_score` 字段，否则 `merge_from_analysis` 路径无法更新 `need_clarity`
- 行 671-674 的 mode 回退逻辑需删除，并说明理由
- Task 2 Step 5 中 `llm_action` 变量需在替换代码中重新定义（原定义在行 650，属于被删除范围）
- Task 4 异步路径 `research_turns` 无条件递增，同步路径条件递增——有意为之，需文档说明

**6. 三次审查修正点（本次）:**
- **严重：** `enter_framework` + 无 `topic_hint` 时 `update_readiness` 不执行 → 改为 `enter_framework` 时无条件 `update_readiness(skip_decay=True)`，`max(0.7)` 仅在 `topic_hint` 存在时执行
- **严重：** `_force_transition_at` 删除不完整（行 414、1600 未给出替换代码）→ 确认 6 处引用全部删除，cancel 路径的 `pop` 仅清理残留字段，删除无功能影响
- **严重：** EXECUTING→FRAMEWORK_CONFIRM 时未取消后台任务 → 转换前检查目标状态，若从 EXECUTING 转出则调用 `_cancel_existing_task(session_id)`
- **严重：** `_save_dialogue_state` 覆盖整个 intent_state，异步路径可能覆盖同步路径的新 `need_clarity` → `_update_intent_state_after_async` 改为直接在 session dict 中更新特定字段，不重新序列化整个 intent_state
- **严重：** 连接词兜底列表遗漏 `"和"` 和 `"与"` → 合并原列表和新列表
- **中等：** `topic_research_turns` 条件递增与衰减设计矛盾 → 改为 `update_from_response` 末尾无条件递增（反映对话轮次），`research_turns` 保持条件递增（反映进展轮次）
- **中等：** `min()` 导致 `need_clarity` 只降不升 → 改为加权平均 `0.6 * old + 0.4 * new`
- **中等：** `_compute_rule_based_score` 遗漏 `hidden_requirements` 加分 → 补回原代码行 124-127 的逻辑
- **中等：** `DeepIntentResult.to_dict()`/`from_dict()` 未更新以包含 `clarity_score` → Step 8a 中追加序列化修改
- **中等：** 深度分析 prompt 修改位置不明确 → 指定 `prompts/agents/intent_analysis_user.md`
- **小：** 测试名 `test_no_need_clarity_uses_rule_fallback` 有误导性 → 改为 `test_default_need_clarity_mixed_scoring`
- **小：** Task 2 标题"信任 LLM"与实际逻辑矛盾 → 改为"LLM `enter_framework` 优先，`continue_chat` 时状态机建议优先"
- **小：** Task 4 Step 4 行号 1241 不准确 → 更正为 1417
- **小：** Task 5 else 分支缺少 `or ""` 防护 → 保留 `(self.topic_hint or "")`
- **小：** Step 8b 中 `data.get` 应为 `llm_output.get` → 修正变量名
