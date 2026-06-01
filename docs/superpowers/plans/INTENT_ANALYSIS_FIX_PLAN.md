# 意图分析系统性修复方案 v5.3

> 日期: 2026-05-18
> 版本: v5.3 (实施后代码审计修订版)
> 状态: 已实施，代码审计完成
> 方法: 先完成代码逐行审计，再基于事实撰写方案
> 修订说明: v5.2→v5.3 修订内容：(1) 全部行号引用更新至实施后实际代码位置（research_api.py 从 ~3k 行增长至 4441 行）；(2) 事实表 A 补充已实施的 3 个新字段（is_composite/sub_intents/orchestration_strategy）；(3) 事实表 D 行号全部更新；(4) §5.2 update_from_response 代码片段修正：readiness_score/readiness_level 设置移至 update_readiness() 之后（与实际代码一致）；(5) §7.3 模板快速启动路径行号标记为未找到；(6) §7.4 状态机操作行号更新；(7) §8.2 cancel 分支插入位置行号更新；(8) 移除不存在的调用点引用（行 458, 487）

---

## 零、代码审计事实表

### A. DeepIntentResult 实际字段（semantic_intent.py:31-60）

| 字段名 | 类型 | 默认值 |
|--------|------|--------|
| primary_intent | IntentType | 必填 |
| intent_confidence | float | 必填 |
| intent_reasoning | str | 必填 |
| research_types | List[ResearchType] | [] |
| primary_research_type | Optional[ResearchType] | None |
| secondary_research_types | List[ResearchType] | [] |
| task_scope | str | "medium" |
| requires_primary_data | bool | False |
| requires_secondary_data | bool | True |
| domain_context | Dict[str, Any] | {} |
| hidden_requirements | List[str] | [] |
| complexity | TaskComplexity | TaskComplexity.SINGLE |
| aspect_count | int | 0 |
| estimated_effort | str | "standard" |
| execution_preference | str | "sequential" |
| output_mode | str | "staged" |
| needs_clarification | bool | False |
| clarification_questions | List[str] | [] |
| recommended_skills | List[str] | [] |
| llm_model_used | str | "" |
| analysis_timestamp | datetime | datetime.now |
| raw_llm_response | str | "" |
| used_fallback | bool | False |
| is_composite | bool | False |
| sub_intents | List[SubIntent] | [] |
| orchestration_strategy | str | "sequential" |

**关键事实**：无 `key_aspects` 字段。`domain_context` 是 Dict[str,Any]，内容完全取决于 LLM 输出，**不保证**包含 "topic" 或 "aspects" 键。`_build_result`（行 322）直接透传 `llm_output.get("domain_context", {})`。v5.3 注：is_composite/sub_intents/orchestration_strategy 已实施（行 58-60）。

### B. ConversationStateMachine 实际签名（state_machine.py）

| 项目 | 实际值 |
|------|--------|
| `__init__` 签名 | `(self, research_id=None, context=None)` |
| 初始状态 | `self.current_state = ConversationState.UNDERSTANDING`（行 101） |
| 状态属性 | `self.current_state`（不是 `self._state`） |
| `transition()` | 无效转换时 `raise InvalidTransitionError`，不返回 bool |
| `can_transition_to()` | 返回 bool（行 173） |
| `is_in_state()` | 返回 bool（行 169） |
| `save()/load()` | 文件持久化，load 恢复 current_state 和 _history |

**VALID_TRANSITIONS 完整图**（行 45-86）：

| From | To |
|------|----|
| UNDERSTANDING | UNDERSTANDING, CLARIFYING, EXECUTING, **FRAMEWORK_CONFIRM** |

**新增路径**：UNDERSTANDING → FRAMEWORK_CONFIRM（当 readiness=SUFFICIENT 且 LLM 返回 enter_framework 时允许直接跳转，避免两步转换中 CLARIFYING 阶段停留时间过短导致矛盾）。
**已有路径**：UNDERSTANDING → EXECUTING（P2 fix，允许模板快速启动直接跳到执行）。v5.1 事实表修正：原 v5.0 事实表遗漏了此已有路径。
| CLARIFYING | CLARIFYING, FRAMEWORK_CONFIRM |
| FRAMEWORK_CONFIRM | FRAMEWORK_CONFIRM, EXECUTING, PREVIEWING, CLARIFYING |
| EXECUTING | EXECUTING, PAUSED, PREVIEWING, COMPLETED, CANCELLED |
| PAUSED | PAUSED, EXECUTING, FRAMEWORK_CONFIRM, CANCELLED |
| CANCELLED | CANCELLED |
| PREVIEWING | PREVIEWING, PAUSED, COMPLETED |
| COMPLETED | COMPLETED |

**关键事实**：每个状态都有自环。FRAMEWORK_CONFIRM 可转到 CLARIFYING（行 60）。v5.0 新增了 UNDERSTANDING → FRAMEWORK_CONFIRM 的直接路径（当 readiness=SUFFICIENT 时）。

### C. Session 结构

| 项目 | 实际值 |
|------|--------|
| session 类型 | `PersistentSessionDict(dict)`（session_manager.py:29） |
| session_id 存储 | `PersistentSessionDict._session_id`（内部属性，**不是** dict key） |
| `session.get("session_id")` | 返回 `None`（调用方不存此 key） |
| session_manager._base_dir | `Path("data/sessions")`（行 158） |
| state_machine 存储 | `session["state_machine"]`（行 354） |

### D. _llm_converse prompt 结构（行 879-1128）

变量定义顺序（行 894-995）→ f-string（行 1001-1128）：

```
行 894-899: history_text
行 901-913: context_summary
行 915-931: tools_section
行 937-967: paused_context
行 969-995: sections_context, post_research_hint
行 997-999: dialogue_context (已实施)
--- f-string 开始 ---
行 1001-1004: Current date + conversation context
行 1006-1007: Existing research information ({context_summary})
行 1008: {dialogue_context} (已实施)
行 1009: {paused_context}
行 1010: {sections_context}
行 1011: {post_research_hint}
行 1012: {self._build_research_running_context(session)}
行 1013: Latest user message: {user_input}
行 1014: {tools_section}
行 1016-1128: LANGUAGE RULE + DATA FRESHNESS + Action Selection Rules
```

**注入点**：在行 995（post_research_hint 赋值结束）之后定义变量，在 f-string 行 1007（context_summary）之后、行 1009（paused_context）之前插入。这样对话状态指导出现在"研究信息"之后、"暂停/修订上下文"之前，逻辑顺序正确。**已实施**：行 997-999 定义 dialogue_context，行 1008 插入到 f-string 中。

### E. intent_analysis_system.md 输出规范

当前（34行）**没有定义 JSON schema**，只说"Strictly output in JSON format"。LLM 输出的 `domain_context` 内容不可预测。

### F. _handle_user_message 中的硬编码路径

| 行 | 逻辑 | 与状态机的关系 |
|----|------|--------------|
| 402 | `_should_start_execution` → `_start_execution` | 不检查状态机 |
| 407-419 | `cancel research` → 状态机转换 + `session["mode"]` 对齐 | 已经过状态机（已实施） |
| 422 | `mode=="chat"` → `_handle_chat_mode` | 不检查状态机 |
| 424-425 | `mode=="framework"` → `_handle_framework_mode` | 不检查状态机 |

---

## 一、核心设计

### 1.1 设计原则

1. **DialogueIntentState 独立于 DeepIntentResult**：前者是累积对话状态，后者是单次分析结果
2. **最小化修改 VALID_TRANSITIONS**：仅增加 UNDERSTANDING → FRAMEWORK_CONFIRM 一条路径（当 readiness=SUFFICIENT 且 LLM 对齐时允许直接跳转），不删除任何现有转换
3. **session_id 通过参数传递**，不从 session dict 中读取
4. **merge_from_analysis 只使用 DeepIntentResult 的确定字段**：不依赖 domain_context 中不确定的键
5. **_llm_converse 新参数默认 None**：不破坏现有调用点（research mode 下不传 intent_state/conversation_state，dialogue_context 为空字符串）
6. **_handle_user_message 的硬编码路径逐步对齐**：Phase 1 不动，Phase 2 对齐
7. **_enter_framework_mode 必须同步状态机**：v5.1 新增原则

### 1.2 session["mode"] ↔ ConversationState 对齐

| session["mode"] | ConversationState | 说明 |
|-----------------|------------------|------|
| "chat" | UNDERSTANDING / CLARIFYING | 对话收集需求 |
| "framework" | FRAMEWORK_CONFIRM | 框架确认 |
| "research" | EXECUTING / PAUSED / PREVIEWING | 研究执行 |

**UNDERSTANDING 可直接转到 FRAMEWORK_CONFIRM**（v5.0 新增路径）。当 readiness=SUFFICIENT 且 LLM 返回 enter_framework 时一步到位；当 readiness=PARTIAL 时走 UNDERSTANDING → CLARIFYING → FRAMEWORK_CONFIRM（两步）。

---

## 二、DialogueIntentState

**文件**: 新建 `src/core/dialogue/sub_intent.py`（共用数据类）

```python
from dataclasses import dataclass, field
from typing import List
from enum import Enum


class ReadinessLevel(Enum):
    INSUFFICIENT = "insufficient"
    PARTIAL = "partial"
    SUFFICIENT = "sufficient"


@dataclass
class SubIntent:
    intent_id: str
    description: str
    aspects: List[str] = field(default_factory=list)
    research_types: List[str] = field(default_factory=list)
    dependency: str = "none"
```

**设计说明**：`ReadinessLevel` 放在 `sub_intent.py` 而非 `dialogue_intent_state.py`，因为 `state_machine.py`（底层基础设施）需要导入 `ReadinessLevel`，不能反向依赖上层业务模块。放在共用数据类模块中，两个模块都可导入，无循环依赖。

**文件**: 新建 `src/core/dialogue/dialogue_intent_state.py`

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import logging

from src.core.dialogue.sub_intent import SubIntent, ReadinessLevel

logger = logging.getLogger(__name__)


@dataclass
class DialogueIntentState:
    topic_hint: str = ""
    confirmed_aspects: List[str] = field(default_factory=list)
    pending_questions: List[str] = field(default_factory=list)
    hidden_requirements: List[str] = field(default_factory=list)
    domain_context: Dict[str, Any] = field(default_factory=dict)
    is_composite: bool = False
    sub_intents: List[SubIntent] = field(default_factory=list)
    orchestration_strategy: str = "sequential"
    readiness_score: float = 0.0
    readiness_level: ReadinessLevel = ReadinessLevel.INSUFFICIENT
    clarification_count: int = 0
    research_turns: int = 0  # 仅计研究相关轮次，不含闲聊
    user_aspects: List[str] = field(default_factory=list)      # 用户在对话中原始表达的
    framework_aspects: List[str] = field(default_factory=list)  # 来自框架生成的

    def merge_from_analysis(self, deep_result):
        """从 DeepIntentResult 合并。只使用确定存在的字段。"""
        # topic：从 domain_context 提取（可能为空，不保证存在）
        dc = deep_result.domain_context or {}
        dc_topic = dc.get("topic", "")
        if dc_topic and (not self.topic_hint or len(dc_topic) > len(self.topic_hint)):
            self.topic_hint = dc_topic

        # aspects：从 domain_context 提取（可能为空）
        dc_aspects = dc.get("aspects", [])
        if isinstance(dc_aspects, list):
            for a in dc_aspects:
                if a and a not in self.confirmed_aspects:
                    self.confirmed_aspects.append(a)
                    self.user_aspects.append(a)

        # hidden_requirements：确定存在的字段
        for req in (deep_result.hidden_requirements or []):
            if req not in self.hidden_requirements:
                self.hidden_requirements.append(req)

        # clarification_questions：确定存在的字段
        if deep_result.clarification_questions:
            self.pending_questions = deep_result.clarification_questions

        # needs_clarification：确定存在的字段
        # 如果 LLM 认为需要澄清，限制 readiness 不超过 PARTIAL
        if deep_result.needs_clarification:
            if self.readiness_level == ReadinessLevel.SUFFICIENT:
                self.readiness_level = ReadinessLevel.PARTIAL
                self.readiness_score = min(self.readiness_score, 0.65)

        # domain_context：合并
        if dc:
            for k, v in dc.items():
                if k not in self.domain_context:
                    self.domain_context[k] = v

        # composite：优先使用 deep_result.is_composite（LLM 直接判断）
        # v5.1 fix: 使用 getattr 防御，因为 Phase 1 中 DeepIntentResult 可能尚未添加 is_composite 字段
        is_composite = getattr(deep_result, "is_composite", False)
        sub_intents = getattr(deep_result, "sub_intents", [])
        orchestration_strategy = getattr(deep_result, "orchestration_strategy", "sequential")
        if is_composite:
            self.is_composite = True
            if sub_intents:
                self.sub_intents = sub_intents
                self.orchestration_strategy = orchestration_strategy
        else:
            from src.core.intent_types import TaskComplexity
            if deep_result.complexity in (TaskComplexity.MULTI, TaskComplexity.COMPLEX):
                if any(sig in (self.topic_hint or "") for sig in ["及", "和", "与", "同时", "以及"]):
                    self.is_composite = True

        self.update_readiness()

    def update_from_response(self, conv_result, user_input):
        """从 _llm_converse 响应更新状态"""
        # 仅在 action 为研究相关时计 research_turns
        action = conv_result.get("action", "")
        if action == "enter_framework" or conv_result.get("topic"):
            self.research_turns += 1

        # LLM 返回 enter_framework → 信息充分
        if action == "enter_framework":
            sections = conv_result.get("framework_sections", [])
            for sec in sections:
                if sec not in self.confirmed_aspects:
                    self.confirmed_aspects.append(sec)
                    self.framework_aspects.append(sec)

        # clarification_questions
        if conv_result.get("clarification_questions"):
            self.pending_questions = conv_result["clarification_questions"]
            self.clarification_count += 1

        # identified_aspects（用户来源）
        for asp in (conv_result.get("identified_aspects") or []):
            if asp not in self.confirmed_aspects:
                self.confirmed_aspects.append(asp)
                self.user_aspects.append(asp)

        # is_composite
        if conv_result.get("is_composite"):
            self.is_composite = True

        # topic：优先用 LLM 解析的 topic，不用用户输入截断
        if conv_result.get("topic") and not self.topic_hint:
            self.topic_hint = conv_result["topic"]

        self.update_readiness()

        # v5.3 fix: enter_framework 特殊加分在 update_readiness() 之后覆盖
        # 实际代码位置：dialogue_intent_state.py:110-112
        if action == "enter_framework" and self.topic_hint:
            self.readiness_score = max(self.readiness_score, 0.7)
            self.readiness_level = ReadinessLevel.SUFFICIENT

    def update_readiness(self):
        score = 0.0
        if self.topic_hint:
            score += 0.25
        if self.confirmed_aspects:
            score += 0.35 * min(1.0, len(self.confirmed_aspects) / 3)
        scope_keys = ["geographic_scope", "time_range", "industry_segment"]
        scope_count = sum(1 for k in scope_keys if self.domain_context.get(k))
        if scope_count:
            score += 0.15 * min(1.0, scope_count / 2)
        if self.hidden_requirements:
            addressed = sum(1 for r in self.hidden_requirements if r in self.confirmed_aspects)
            if addressed > 0:
                score += 0.1
        if self.clarification_count >= 1:
            score += 0.15
        self.readiness_score = min(1.0, score)
        if score >= 0.7:
            self.readiness_level = ReadinessLevel.SUFFICIENT
        elif score >= 0.4:
            self.readiness_level = ReadinessLevel.PARTIAL
        else:
            self.readiness_level = ReadinessLevel.INSUFFICIENT

    def to_context_string(self) -> str:
        parts = []
        if self.topic_hint:
            parts.append(f"Research topic: {self.topic_hint}")
        if self.confirmed_aspects:
            parts.append(f"Confirmed aspects: {', '.join(self.confirmed_aspects)}")
        if self.pending_questions:
            parts.append(f"Pending questions: {'; '.join(self.pending_questions)}")
        if self.hidden_requirements:
            parts.append(f"Hidden requirements: {', '.join(self.hidden_requirements)}")
        parts.append(f"Readiness: {self.readiness_level.value} ({self.readiness_score:.1f})")
        if self.is_composite:
            sub_desc = "; ".join(f"[{s.intent_id}] {s.description}" for s in self.sub_intents)
            parts.append(f"Composite intent: {sub_desc}")
        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic_hint": self.topic_hint,
            "confirmed_aspects": self.confirmed_aspects,
            "pending_questions": self.pending_questions,
            "hidden_requirements": self.hidden_requirements,
            "domain_context": self.domain_context,
            "is_composite": self.is_composite,
            "sub_intents": [
                {"intent_id": s.intent_id, "description": s.description,
                 "aspects": s.aspects, "research_types": s.research_types,
                 "dependency": s.dependency}
                for s in self.sub_intents
            ],
            "orchestration_strategy": self.orchestration_strategy,
            "readiness_score": self.readiness_score,
            "readiness_level": self.readiness_level.value,
            "clarification_count": self.clarification_count,
            "research_turns": self.research_turns,
            "user_aspects": self.user_aspects,
            "framework_aspects": self.framework_aspects,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DialogueIntentState":
        sub_intents = []
        for s in data.get("sub_intents", []):
            sub_intents.append(SubIntent(
                intent_id=s.get("intent_id", "sub_1"),
                description=s.get("description", ""),
                aspects=s.get("aspects", []),
                research_types=s.get("research_types", []),
                dependency=s.get("dependency", "none"),
            ))
        state = cls(
            topic_hint=data.get("topic_hint", ""),
            confirmed_aspects=data.get("confirmed_aspects", []),
            pending_questions=data.get("pending_questions", []),
            hidden_requirements=data.get("hidden_requirements", []),
            domain_context=data.get("domain_context", {}),
            is_composite=data.get("is_composite", False),
            sub_intents=sub_intents,
            orchestration_strategy=data.get("orchestration_strategy", "sequential"),
            readiness_score=data.get("readiness_score", 0.0),
            clarification_count=data.get("clarification_count", 0),
            research_turns=data.get("research_turns", 0),
            user_aspects=data.get("user_aspects", []),
            framework_aspects=data.get("framework_aspects", []),
        )
        state.readiness_level = ReadinessLevel(data.get("readiness_level", "insufficient"))
        return state

    def clear_framework_aspects(self):
        """cancel 时清除来自框架的 aspects，保留用户在对话中原始表达的"""
        self.framework_aspects = []
        self.confirmed_aspects = list(self.user_aspects)
        self.hidden_requirements = []
        self.readiness_score = 0.0
        self.readiness_level = ReadinessLevel.INSUFFICIENT
        self.is_composite = False
        self.sub_intents = []
```

---

## 三、ConversationStateMachine 增强

**文件**: 修改 `src/core/dialogue/state_machine.py`

**最小化修改 VALID_TRANSITIONS**：仅增加 UNDERSTANDING → FRAMEWORK_CONFIRM 一条路径（当 readiness=SUFFICIENT 且 LLM 对齐时允许直接跳转）。新增两个方法：

```python
# state_machine.py — 新增 import + VALID_TRANSITIONS 修改 + 新增方法

import logging

logger = logging.getLogger(__name__)

# v5.2 fix: ReadinessLevel 移至 sub_intent.py，避免 state_machine 反向依赖上层模块
from src.core.dialogue.sub_intent import ReadinessLevel


class ConversationStateMachine:
    # 仅修改 UNDERSTANDING 的允许转换，增加 FRAMEWORK_CONFIRM
    VALID_TRANSITIONS = {
        ConversationState.UNDERSTANDING: [
            ConversationState.UNDERSTANDING,
            ConversationState.CLARIFYING,
            ConversationState.EXECUTING,
            ConversationState.FRAMEWORK_CONFIRM,  # 新增：readiness=SUFFICIENT 时直接跳转
        ],
        # ... 其他状态完全不变 ...
    }

    def force_set_state(self, target_state: ConversationState):
        """强制设置状态（仅用于从持久化恢复或纠正异常状态）。记录警告日志。"""
        if not isinstance(target_state, ConversationState):
            raise ValueError(f"Invalid state: {target_state}")
        logger.warning(
            f"Force setting state from {self.current_state.value} to {target_state.value}"
        )
        self.current_state = target_state
        self._record_state_change(target_state)

    def suggest_next(self, intent_state) -> Optional[ConversationState]:
        """基于 DialogueIntentState 建议下一状态"""
        if self.current_state == ConversationState.UNDERSTANDING:
            if intent_state.readiness_level == ReadinessLevel.SUFFICIENT:
                return ConversationState.FRAMEWORK_CONFIRM
            elif intent_state.readiness_level == ReadinessLevel.PARTIAL:
                return ConversationState.CLARIFYING
            return None

        if self.current_state == ConversationState.CLARIFYING:
            if intent_state.readiness_level == ReadinessLevel.SUFFICIENT:
                return ConversationState.FRAMEWORK_CONFIRM
            return None

        # v5.1 fix: FRAMEWORK_CONFIRM 状态下，readiness 降级时建议回退到 CLARIFYING
        if self.current_state == ConversationState.FRAMEWORK_CONFIRM:
            if intent_state.readiness_level in (ReadinessLevel.INSUFFICIENT, ReadinessLevel.PARTIAL):
                # 用户大幅修改需求，信息不再充分，回退到澄清阶段
                return ConversationState.CLARIFYING
            return None

        return None
```

**关键**：UNDERSTANDING → FRAMEWORK_CONFIRM 现在在 VALID_TRANSITIONS 中（新增路径），suggest_next 从 UNDERSTANDING 在 readiness=SUFFICIENT 时直接建议 FRAMEWORK_CONFIRM。当 readiness=PARTIAL 时建议 CLARIFYING（追问细节）。

---

## 四、DeepIntentResult 扩展

**文件**: 修改 `src/core/semantic_intent.py`

### 4.1 SubIntent（从共用模块导入，不重复定义）

`semantic_intent.py` 导入 `SubIntent`：

```python
from src.core.dialogue.sub_intent import SubIntent
```

### 4.2 DeepIntentResult 新增字段

```python
@dataclass
class DeepIntentResult:
    # ... 现有 23 个字段完全不变 ...

    # 新增（放在最后，有默认值，不破坏现有构造调用）
    is_composite: bool = False
    sub_intents: List[SubIntent] = field(default_factory=list)
    orchestration_strategy: str = "sequential"
```

### 4.3 to_dict 扩展

在现有 to_dict 返回的 dict 中追加：

```python
"is_composite": self.is_composite,
"sub_intents": [
    {"intent_id": s.intent_id, "description": s.description,
     "aspects": s.aspects, "research_types": s.research_types,
     "dependency": s.dependency}
    for s in self.sub_intents
],
"orchestration_strategy": self.orchestration_strategy,
```

### 4.4 from_dict 新增

```python
@classmethod
def from_dict(cls, data: Dict[str, Any]) -> "DeepIntentResult":
    """从 to_dict() 输出反序列化。输入 key 使用字段名（非 LLM 原始 key）。
    注意：LLM 原始输出用 "confidence" 而非 "intent_confidence"，
    用 "reasoning" 而非 "intent_reasoning"——这些映射在 _build_result 中完成。
    from_dict 仅用于从 to_dict 的序列化结果恢复，不用于解析 LLM 原始输出。"""
    research_types = []
    for rt_str in data.get("research_types", []):
        try:
            research_types.append(ResearchType(rt_str))
        except ValueError:
            pass
    primary_rt = None
    if data.get("primary_research_type"):
        try:
            primary_rt = ResearchType(data["primary_research_type"])
        except ValueError:
            pass
    secondary_rts = []
    for rt_str in data.get("secondary_research_types", []):
        try:
            secondary_rts.append(ResearchType(rt_str))
        except ValueError:
            pass
    sub_intents = []
    for s in data.get("sub_intents", []):
        sub_intents.append(SubIntent(
            intent_id=s.get("intent_id", "sub_1"),
            description=s.get("description", ""),
            aspects=s.get("aspects", []),
            research_types=s.get("research_types", []),
            dependency=s.get("dependency", "none"),
        ))
    return cls(
        primary_intent=IntentType(data.get("primary_intent", "open_ended")),
        intent_confidence=data.get("intent_confidence", 0.5),
        intent_reasoning=data.get("intent_reasoning", ""),
        research_types=research_types,
        primary_research_type=primary_rt,
        secondary_research_types=secondary_rts,
        task_scope=data.get("task_scope", "medium"),
        requires_primary_data=data.get("requires_primary_data", False),
        requires_secondary_data=data.get("requires_secondary_data", True),
        domain_context=data.get("domain_context", {}),
        hidden_requirements=data.get("hidden_requirements", []),
        complexity=TaskComplexity(data.get("complexity", "single")),
        aspect_count=data.get("aspect_count", 0),
        estimated_effort=data.get("estimated_effort", "standard"),
        execution_preference=data.get("execution_preference", "sequential"),
        output_mode=data.get("output_mode", "staged"),
        needs_clarification=data.get("needs_clarification", False),
        clarification_questions=data.get("clarification_questions", []),
        recommended_skills=data.get("recommended_skills", []),
        llm_model_used=data.get("llm_model_used", ""),
        raw_llm_response=data.get("raw_llm_response", ""),
        used_fallback=data.get("used_fallback", False),
        is_composite=data.get("is_composite", False),
        sub_intents=sub_intents,
        orchestration_strategy=data.get("orchestration_strategy", "sequential"),
        analysis_timestamp=datetime.fromisoformat(data["analysis_timestamp"]) if data.get("analysis_timestamp") else datetime.now(),
    )
```

### 4.5 _build_result 解析复合意图

在 `_build_result`（行 322-381）的 return 语句中，新增关键字参数：

```python
is_composite=llm_output.get("is_composite", False),
sub_intents=[
    SubIntent(
        intent_id=s.get("intent_id", f"sub_{i+1}"),
        description=s.get("description", ""),
        aspects=s.get("aspects", []),
        research_types=s.get("research_types", []),
        dependency=s.get("dependency", "none"),
    )
    for i, s in enumerate(llm_output.get("sub_intents", []))
    if isinstance(s, dict)
],
orchestration_strategy=llm_output.get("orchestration_strategy", "sequential"),
```

---

## 五、_handle_chat_mode 改动

### 5.1 改动点（精确标注）

| 插入位置 | 插入内容 | 行数 |
|---------|---------|------|
| 行 554 之后（语言检测后） | 恢复 DialogueIntentState + ConversationStateMachine | +8 |
| 行 563-564（_llm_converse 调用前） | 按需深度分析 | +12 |
| 行 584-589 | _llm_converse 调用签名增加 2 个可选参数 | 修改 |
| 行 645 之后（topic/directions 更新后） | update_from_response + 状态机转换 + 保存 | +25 |

### 5.2 具体代码

```python
async def _handle_chat_mode(self, session_id, user_input, skip_lang_detect=False):
    session = session_manager.get(session_id)
    context = session.get("research_context", {})

    if not skip_lang_detect:
        current_lang = detect_language(user_input).value
        session["language"] = current_lang
        set_global_language(current_lang)

    # === 新增：恢复对话状态 ===
    intent_state = self._get_or_create_intent_state(session)
    conv_machine = self._get_or_create_conv_machine(session)

    # === 新增：按需深度意图分析 ===
    if self._should_deep_analyze(user_input, intent_state, conv_machine.current_state):
        try:
            deep_result = await asyncio.wait_for(
                self._intent_analyzer.analyze_async(
                    user_input,
                    requirement={
                        "topic": intent_state.topic_hint or context.get("topic", ""),
                        "aspects": intent_state.confirmed_aspects or context.get("directions", []),
                    },
                ),
                timeout=15,
            )
            intent_state.merge_from_analysis(deep_result)
        except asyncio.TimeoutError:
            logger.warning(f"[{session_id}] Deep intent analysis timed out")
        except Exception as e:
            logger.warning(f"[{session_id}] Deep intent analysis failed: {e}")

    # === 修改：注入状态 ===
    try:
        conv_result = await self._llm_converse(
            session_id, user_input,
            intent_state=intent_state,
            conversation_state=conv_machine.current_state,
        )
    except Exception as e:
        logger.error(f"LLM conversation failed: {e}")
        return self._fallback_response(session_id, context)

    # ... 异步路径处理不变 ...
    # ... topic/directions 更新不变 ...

    # === 新增：更新意图状态 + 状态机转换 ===
    # 注意：此逻辑仅在同步路径（status=="done"）中执行。
    # 异步路径（status=="processing"）的 response_data 通过 ProgressStreamer 推送，
    # 不经过此处，因此异步路径中不更新 DialogueIntentState。
    # 这是安全的：异步路径发生在 EXECUTING 状态，不需要对话阶段引导。
    intent_state.update_from_response(conv_result, user_input)

    suggested = conv_machine.suggest_next(intent_state)
    llm_action = conv_result.get("action", "")
    if suggested and conv_machine.can_transition_to(suggested):
        if self._action_aligns_with_state(llm_action, suggested):
            conv_machine.transition(suggested)
        else:
            # v5.1 fix: 冲突时基于绝对对话轮次（len(history)）强制转换
            # 原方案用 research_turns，但闲聊不计入 research_turns，导致阈值永远不触发
            force_at = context.get("_force_transition_at", 0)
            current_turn = len(session.get("conversation_history", []))
            if current_turn >= force_at > 0:
                logger.warning(f"[{session_id}] Forcing transition at turn={current_turn}")
                conv_machine.transition(suggested)

    # 记录强制转换阈值（首次 suggested 出现时）
    # v5.1 fix: 使用绝对对话轮次而非 research_turns
    if suggested and not context.get("_force_transition_at"):
        current_turn = len(session.get("conversation_history", []))
        context["_force_transition_at"] = current_turn + 3

    # topic 变更时清除强制转换阈值（避免旧阈值影响新 topic）
    if conv_result.get("topic") and context.get("topic") and conv_result["topic"] != context["topic"]:
        context.pop("_force_transition_at", None)

    self._save_dialogue_state(session_id, session, intent_state, conv_machine)
    self._sync_mode_with_state(session, conv_machine)

    # v5.1 fix: 如果状态机已转到 FRAMEWORK_CONFIRM 但 LLM action 不是 enter_framework，
    # 不应将 mode 设为 framework——否则下一轮对话会进入 _handle_framework_mode 而非
    # _handle_chat_mode，导致用户收到框架确认 UI 但实际内容是闲聊。
    # 解决方案：仅在 action 对齐时才同步 mode，否则维持当前 mode。
    # 上面的 _sync_mode_with_state 已执行，但此处做二次校验：
    # 如果 suggested == FRAMEWORK_CONFIRM 且 llm_action 不对齐，回退 mode。
    if suggested == ConversationState.FRAMEWORK_CONFIRM and not self._action_aligns_with_state(llm_action, suggested):
        # 状态机已转到 FRAMEWORK_CONFIRM（可能是强制转换），但 LLM 仍在闲聊
        # 回退 mode 到 chat，让下一轮仍走 _handle_chat_mode
        if session.get("mode") == "framework":
            session["mode"] = "chat"
            logger.info(f"[{session_id}] State machine at FRAMEWORK_CONFIRM but LLM action={llm_action}, keeping mode=chat")

    # ... action 路由不变 ...
```

### 5.3 _llm_converse 改动

签名：`async def _llm_converse(self, session_id: str, user_input: str, intent_state=None, conversation_state=None) -> Dict[str, Any]:`

新参数默认 None，所有现有调用点不受影响（research mode 下不传 intent_state/conversation_state，dialogue_context 为空字符串）。

prompt 注入：在行 995 之后定义变量，在 f-string 行 1007 之后插入。

```python
# 行 995 之后新增
dialogue_context = ""
if intent_state is not None and conversation_state is not None:
    dialogue_context = self._build_dialogue_context(intent_state, conversation_state)
```

f-string 中，行 1007 之后插入 `{dialogue_context}`：

```
Existing research information:
{context_summary if context_summary else "(Research topic not yet confirmed, need to guide user to express needs)"}
{dialogue_context}
{paused_context}
```

JSON 解析增强（行 1171-1182）：

```python
return {
    "status": "done",
    "message": parsed.get("message", ""),
    "action": parsed.get("action", "continue_chat"),
    "topic": parsed.get("topic"),
    "directions": parsed.get("directions", []),
    "framework_sections": parsed.get("framework_sections"),
    "clarification_questions": parsed.get("clarification_questions", []),
    "identified_aspects": parsed.get("identified_aspects", []),
    "is_composite": parsed.get("is_composite", False),
    "suggestions": [...],
}
```

异步路径（行 1383-1393）同样增加字段提取：

```python
# 异步路径 response_data 增强（替换原行 1383-1393）
response_data = {
    "message": parsed.get("message", ""),
    "action": parsed.get("action", "continue_chat"),
    "topic": parsed.get("topic"),
    "directions": parsed.get("directions", []),
    "framework_sections": parsed.get("framework_sections"),
    "clarification_questions": parsed.get("clarification_questions", []),
    "identified_aspects": parsed.get("identified_aspects", []),
    "is_composite": parsed.get("is_composite", False),
    "suggestions": parsed.get("suggestions", []),
}
```

**注意**：异步路径的 `response_data` 在 `_do_execute_tool_background` 中构建后直接通过 `ProgressStreamer.push_chat_response` 推送给前端，**不经过** `_handle_chat_mode` 的状态更新逻辑。因此异步路径中**不需要**调用 `intent_state.update_from_response` 和状态机转换——这些仅在 `_handle_chat_mode` 的同步路径中执行。

---

## 六、辅助方法

### 6.1 状态存取（session_id 通过参数传递）

```python
def _get_or_create_intent_state(self, session):
    context = session.get("research_context", {})
    state_dict = context.get("_dialogue_intent_state")
    if state_dict:
        try:
            return DialogueIntentState.from_dict(state_dict)
        except Exception as e:
            # v5.1 fix: 记录反序列化失败，避免静默丢失数据
            logger.warning(f"DialogueIntentState.from_dict failed: {e}, creating fresh instance")
    return DialogueIntentState()

def _get_or_create_conv_machine(self, session):
    # 优先使用 session 中已有的 state_machine
    machine = session.get("state_machine")
    if machine and isinstance(machine, ConversationStateMachine):
        return machine
    # v5.1 fix: 反序列化失败时 session 中无 state_machine，新建实例会丢失历史
    # 记录警告以便排查
    logger.warning(
        f"state_machine missing or invalid in session, creating new instance "
        f"(previous state history lost)"
    )
    return ConversationStateMachine()

def _save_dialogue_state(self, session_id, session, intent_state, conv_machine):
    # v5.1 fix: 使用 update() 批量写入，触发单次磁盘持久化而非多次 __setitem__
    context = session.get("research_context", {})
    context["_dialogue_intent_state"] = intent_state.to_dict()
    context["_conversation_state"] = conv_machine.current_state.value
    # PersistentSessionDict.update() 只触发一次 _save_to_disk
    session.update({
        "research_context": context,
        "state_machine": conv_machine,
    })

def _sync_mode_with_state(self, session, conv_machine):
    state = conv_machine.current_state
    if state in (ConversationState.UNDERSTANDING, ConversationState.CLARIFYING):
        if session.get("mode") != "chat":
            session["mode"] = "chat"
    elif state == ConversationState.FRAMEWORK_CONFIRM:
        if session.get("mode") != "framework":
            session["mode"] = "framework"
    elif state in (ConversationState.EXECUTING, ConversationState.PAUSED, ConversationState.PREVIEWING):
        if session.get("mode") != "research":
            session["mode"] = "research"
    elif state == ConversationState.COMPLETED:
        # v5.1 fix: 研究完成后回退到 chat，允许后续对话
        if session.get("mode") != "chat":
            session["mode"] = "chat"
```

**关键**：`_get_or_create_conv_machine` 直接复用 `session["state_machine"]`（行 354 已创建），不需要 initial_state 参数，不需要 force_set_state。若反序列化失败导致 `session["state_machine"]` 不存在，新建实例并记录警告（v5.1 fix）。

### 6.2 冲突仲裁

```python
def _action_aligns_with_state(self, llm_action, target_state):
    alignment = {
        ConversationState.UNDERSTANDING: ["continue_chat", "enter_framework"],
        ConversationState.CLARIFYING: ["continue_chat", "enter_framework"],
        ConversationState.FRAMEWORK_CONFIRM: ["enter_framework"],
    }
    return llm_action in alignment.get(target_state, [])
```

### 6.3 _build_dialogue_context

```python
def _build_dialogue_context(self, intent_state, conversation_state):
    state_guidance = {
        ConversationState.UNDERSTANDING: (
            "## Current Dialogue Phase: Understanding\n"
            "Focus on understanding the user's research need.\n"
            "- If the request is vague, ask 1-2 targeted questions.\n"
            "- Do NOT propose a research framework yet.\n"
        ),
        ConversationState.CLARIFYING: (
            "## Current Dialogue Phase: Clarifying\n"
            "The topic is identified but details may be missing.\n"
            "- Ask focused questions about specific gaps. Max 2 per turn.\n"
            "- If enough information, you may propose a framework.\n"
        ),
        ConversationState.FRAMEWORK_CONFIRM: (
            "## Current Dialogue Phase: Framework Confirmation\n"
            "Requirements are clear. Propose a research framework.\n"
            "- Use action=\"enter_framework\" with framework_sections.\n"
        ),
        # v5.1 fix: 补充 EXECUTING/PAUSED/PREVIEWING 状态的 guidance
        ConversationState.EXECUTING: (
            "## Current Dialogue Phase: Research Executing\n"
            "Research is actively running.\n"
            "- Treat user messages as supplementary information by default.\n"
            "- Only use enter_framework if user EXPLICITLY requests redesign.\n"
        ),
        ConversationState.PAUSED: (
            "## Current Dialogue Phase: Research Paused\n"
            "Research was interrupted. Cached data available.\n"
            "- Resume → resume_research; Modify → modify_research; Chat → continue_chat.\n"
        ),
        ConversationState.PREVIEWING: (
            "## Current Dialogue Phase: Report Preview\n"
            "Report is being previewed.\n"
            "- Handle user feedback on the report.\n"
        ),
    }
    guidance = state_guidance.get(conversation_state, "")
    intent_ctx = intent_state.to_context_string()
    return f"\n{guidance}\n{intent_ctx}\n"
```

### 6.4 _should_deep_analyze

```python
def _should_deep_analyze(self, user_input, intent_state, conv_state):
    if conv_state not in (ConversationState.UNDERSTANDING, ConversationState.CLARIFYING):
        return False
    research_keywords = [
        "研究", "分析", "市场", "行业", "调研", "问卷", "报告", "趋势", "竞争",
        "research", "analyze", "market", "industry", "survey", "report", "trend",
    ]
    if len(user_input.strip()) < 20 and not any(kw in user_input for kw in research_keywords):
        return False
    if intent_state.research_turns == 0:
        return True
    if len(user_input) > 50:
        return True
    composite_connectors = ["及", "以及", "同时", "并且", "再加上",
                            "along with", "as well as", "in addition to"]
    has_connector = any(c in user_input for c in composite_connectors)
    has_research_kw = any(kw in user_input for kw in research_keywords)
    if has_connector and has_research_kw:
        return True
    if intent_state.topic_hint and len(user_input) > 30:
        return True
    return False
```

**注意**：`research_turns == 0` 时总是触发深度分析，意味着第一轮对话会增加一次 LLM 调用（`_intent_analyzer.analyze_async`，timeout=15s）。如果首轮延迟敏感，可改为仅在输入包含 research_keywords 时触发。

---

## 七、_handle_user_message 对齐（Phase 2）

### 7.0 _enter_framework_mode 状态机同步（行 1667-1763）

当前 `_enter_framework_mode` 设置 `session["mode"] = "framework"` 但不转换状态机。有**两个**设置 mode 的路径需同步：

**路径 1**：幂等检查路径（行 1687），`session["mode"] = "framework"` 后直接 return。需在 `session["mode"] = "framework"` 之后、return 之前插入：

```python
# v5.1 fix: 同步状态机到 FRAMEWORK_CONFIRM（幂等路径）
self._sync_state_machine_to_framework(session, session_id)
```

**路径 2**：正常生成路径（行 1741），`session["mode"] = "framework"` 之后。需在 `session["mode"] = "framework"` 之后插入：

```python
# v5.1 fix: 同步状态机到 FRAMEWORK_CONFIRM（正常路径）
self._sync_state_machine_to_framework(session, session_id)
```

**共用辅助方法**（避免两处重复代码）：

```python
def _sync_state_machine_to_framework(self, session, session_id):
    conv_machine = session.get("state_machine")
    if conv_machine:
        if conv_machine.current_state in (ConversationState.UNDERSTANDING, ConversationState.CLARIFYING):
            if conv_machine.can_transition_to(ConversationState.FRAMEWORK_CONFIRM):
                conv_machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        elif conv_machine.current_state == ConversationState.PAUSED:
            if conv_machine.can_transition_to(ConversationState.FRAMEWORK_CONFIRM):
                conv_machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        elif conv_machine.current_state == ConversationState.EXECUTING:
            # EXECUTING 不能直接转到 FRAMEWORK_CONFIRM，需先 PAUSED
            if conv_machine.can_transition_to(ConversationState.PAUSED):
                conv_machine.transition(ConversationState.PAUSED)
                conv_machine.transition(ConversationState.FRAMEWORK_CONFIRM)
            else:
                logger.warning(
                    f"[{session_id}] Cannot transition EXECUTING→PAUSED→FRAMEWORK_CONFIRM, force setting"
                )
                conv_machine.force_set_state(ConversationState.FRAMEWORK_CONFIRM)
        elif not conv_machine.is_in_state(ConversationState.FRAMEWORK_CONFIRM):
            logger.warning(
                f"[{session_id}] _enter_framework_mode but state is {conv_machine.current_state.value}, "
                f"force setting to FRAMEWORK_CONFIRM"
            )
            conv_machine.force_set_state(ConversationState.FRAMEWORK_CONFIRM)
        session["state_machine"] = conv_machine
```

### 7.1 cancel research 硬编码路径（行 407-419，已实施）

当前直接设 `session["mode"]="chat"`，不经过状态机。修改为：

```python
if mode == "framework" and user_input.strip().lower() == "cancel research":
    logger.info(f"User cancelled framework for {session_id}")
    # 状态机转换：FRAMEWORK_CONFIRM → CLARIFYING（在允许转换中）
    conv_machine = session.get("state_machine")
    if conv_machine and conv_machine.can_transition_to(ConversationState.CLARIFYING):
        conv_machine.transition(ConversationState.CLARIFYING)
    # 清除旧框架
    context = session.get("research_context", {})
    context["framework"] = None
    # v5.1 fix: cancel 时清除 _force_transition_at，避免残留阈值影响后续对话
    context.pop("_force_transition_at", None)
    intent_state = self._get_or_create_intent_state(session)
    intent_state.clear_framework_aspects()
    self._save_dialogue_state(session_id, session, intent_state, conv_machine)
    self._sync_mode_with_state(session, conv_machine)
    return await self._handle_chat_mode(session_id, "这个研究框架不符合我的需求，请重新了解我的具体需求后重新设计。", skip_lang_detect=True)
```

### 7.2 _should_start_execution（行 539-552，已实施）

增加 `session_id` 参数和状态机检查：

```python
def _should_start_execution(self, user_input: str, mode: str, context: Dict, session_id: str = "") -> bool:
    if mode != "framework":
        return False
    if not context.get("framework"):
        return False
    if user_input.strip().lower() != "confirm start":
        return False
    # 新增：检查状态机是否在 FRAMEWORK_CONFIRM
    if session_id:
        session = session_manager.get(session_id)
        conv_machine = session.get("state_machine") if session else None
        if conv_machine and not conv_machine.is_in_state(ConversationState.FRAMEWORK_CONFIRM):
            logger.warning(f"confirm start but state is {conv_machine.current_state.value}, correcting")
            conv_machine.force_set_state(ConversationState.FRAMEWORK_CONFIRM)
    return True
```

调用点修改（行 402）：
```python
# 原：self._should_start_execution(user_input, mode, latest_context)
# 新：self._should_start_execution(user_input, mode, latest_context, session_id)
```

### 7.3 模板快速启动路径

模板快速启动路径直接创建 `ConversationStateMachine` 并跳到 EXECUTING，不经过 UNDERSTANDING/CLARIFYING/FRAMEWORK_CONFIRM。此路径**不需要修改**，因为：
1. 模板启动时用户已明确需求，无需对话引导
2. 状态机在 `create_session_from_template` 中直接初始化为 EXECUTING
3. `DialogueIntentState` 在此路径下不会被创建（`_get_or_create_intent_state` 返回空实例）

但需确认：如果用户在模板启动后 cancel research，回退到 chat mode 时 `_get_or_create_intent_state` 会创建空实例，不会出错。

### 7.4 research mode 路径（行 426-537）

research mode 路径已有状态机操作（行 1804-1811 的 `_start_execution` 中 `transition(EXECUTING)`，行 3271+ 的暂停，行 3322+ 的恢复，行 3471+ 的取消）。这些**不需要修改**。

但需注意：research mode 下的 `_llm_converse` 调用目前不传入 `intent_state`/`conversation_state`，因此 `dialogue_context` 为空字符串，不影响现有行为。Phase 2 中可以考虑传入，但不是必须的——research mode 下 LLM 的主要任务是处理暂停/修改/闲聊，不需要对话阶段引导。

---

## 八、框架修订可靠性

### 8.1 _llm_framework_modify prompt 增强

增加 cancel action + 明确确认关键词：

```python
prompt = (
    f"You are helping the user refine their research framework.\n\n"
    f"Current research topic: {topic}\n"
    f"Current framework sections:\n{sections_str}\n\n"
    f"User's request: {user_input}\n\n"
    f"## Rules\n\n"
    f"1. If the user confirms (e.g., '确认', '没问题', 'ok', '好的', '开始吧', "
    f"'looks good', 'proceed'), set action=\"confirm\".\n"
    f"2. If the user wants ANY change, set action=\"modify\" with COMPLETE new section list in `new_sections`.\n"
    f"3. If the user wants to cancel, set action=\"cancel\".\n"
    f"4. When action=\"modify\", `new_sections` MUST be a non-empty array.\n"
    f"5. Remove duplicate or semantically overlapping sections.\n"
    f"6. Your `message` MUST be in {user_lang}.\n\n"
    f"Output JSON only:\n"
    f'{{"action": "confirm" | "modify" | "cancel", "message": "...", "new_sections": [...]}}\n\n'
    f"Note: `new_sections` REQUIRED when action=\"modify\", IGNORED otherwise."
)
```

### 8.2 _handle_framework_mode 容错 + cancel

**插入位置**：在 `action = conv_result.get("action", "modify")`（行 1593）之后、`if action == "confirm":`（行 1611）之前插入 cancel 分支。

```python
# 行 1593 之后插入
if action == "cancel":
    conv_machine = session.get("state_machine")
    if conv_machine and conv_machine.can_transition_to(ConversationState.CLARIFYING):
        conv_machine.transition(ConversationState.CLARIFYING)
    context["framework"] = None
    # v5.1 fix: cancel 时清除 _force_transition_at，避免残留阈值影响后续对话
    context.pop("_force_transition_at", None)
    session["research_context"] = context
    intent_state = self._get_or_create_intent_state(session)
    intent_state.clear_framework_aspects()
    self._save_dialogue_state(session_id, session, intent_state, conv_machine)
    self._sync_mode_with_state(session, conv_machine)
    return self._chat_response(
        session_id,
        message=self._l("好的，我们重新讨论你的需求。", "Sure, let's reconsider your needs.", lang),
    )

# 原行 1611 不变
if action == "confirm":
```

### 8.3 _merge_sections_dedup 语义去重

```python
def _merge_sections_dedup(self, primary, secondary):
    def _tokenize(name):
        cleaned = name.replace("与", " ").replace("及", " ").replace("和", " ")\
                         .replace("、", " ").replace("：", " ").replace(":", " ")\
                         .replace("的", " ").replace("中", " ")
        tokens = [t for t in cleaned.split() if len(t) >= 2]
        if not tokens:
            tokens = [name[i:i+2] for i in range(len(name)-1)]
        return tokens
    merged = list(primary)
    for sec in secondary:
        if sec in merged:
            continue
        is_dup = False
        for i, existing in enumerate(merged):
            if sec in existing or existing in sec:
                if len(sec) > len(existing):
                    merged[i] = sec
                is_dup = True
                break
            sec_tokens = set(_tokenize(sec))
            existing_tokens = set(_tokenize(existing))
            if sec_tokens and existing_tokens:
                overlap = sec_tokens & existing_tokens
                ratio = len(overlap) / max(len(sec_tokens), len(existing_tokens))
                # v5.1 fix: 阈值从 0.5 调至 0.65，避免"市场分析"与"竞争分析"等
                # 语义不同但共享"分析" token 的 section 被误合并
                if ratio >= 0.65:
                    if len(sec) > len(existing):
                        merged[i] = sec
                    is_dup = True
                    break
        if not is_dup:
            merged.append(sec)
    return merged
```

---

## 九、Prompt 增强

### 9.1 conversation.md

在末尾增加：

```markdown
## Dialogue State Context

You may receive a "Current Dialogue Phase" section. Adapt your behavior:
- **Understanding**: Focus on understanding the need. Ask clarifying questions if vague. Do NOT propose a framework.
- **Clarifying**: Ask targeted questions about gaps. Max 2 per turn. If enough info, propose a framework.
- **Framework Confirmation**: Requirements are clear. Propose a framework.

You may also receive an "Intent Analysis Result" showing confirmed/pending info. Use this to avoid re-asking.

### Composite Intent
When the request contains multiple independent subtasks, identify them and propose a combined framework. Set is_composite=true.

### Additional Output Fields
- "clarification_questions": string[] — questions to ask
- "identified_aspects": string[] — aspects mentioned by the user
- "is_composite": boolean — multiple independent subtasks
```

### 9.2 intent_analysis_system.md

在末尾增加（含 JSON 示例，注意 domain_context 规范）：

```markdown
## Composite Intent Detection

When the request contains multiple independent research subtasks:
- Set "is_composite": true
- Include "sub_intents" array
- Include "orchestration_strategy": "sequential" | "hybrid" | "parallel"

## domain_context Required Keys

Always include these keys in "domain_context" when available:
- "topic": the research topic string
- "aspects": array of specific research aspects/directions
- "geographic_scope": geographic scope if mentioned
- "time_range": time range if mentioned

## Composite Example Output

    {
      "primary_intent": "research",
      "complexity": "multi",
      "confidence": 0.9,
      "reasoning": "User wants both market research and survey",
      "research_types": ["industry_research", "survey"],
      "hidden_requirements": ["regulatory environment"],
      "needs_clarification": false,
      "clarification_questions": [],
      "is_composite": true,
      "sub_intents": [
        {"intent_id": "sub_1", "description": "Pet cat market research", "aspects": ["market size", "competition", "trends"], "research_types": ["industry_research"], "dependency": "none"},
        {"intent_id": "sub_2", "description": "Consumer preference survey", "aspects": ["breed preference", "spending habits"], "research_types": ["survey"], "dependency": "moderate"}
      ],
      "orchestration_strategy": "hybrid",
      "domain_context": {"topic": "Pet cat market and consumer survey", "aspects": ["market size", "competition", "breed preference", "spending habits"]}
    }
```

---

## 十、实施计划

### Phase 1: 基础设施（2天）

| 任务 | 文件 |
|------|------|
| 新建 SubIntent（共用数据类） | `src/core/dialogue/sub_intent.py` |
| 新建 DialogueIntentState（含 getattr 防御） | `src/core/dialogue/dialogue_intent_state.py` |
| DeepIntentResult 增加 SubIntent（从共用模块导入）+ is_composite + from_dict | `src/core/semantic_intent.py` |
| _build_result 解析复合意图 | `src/core/semantic_intent.py` |
| ConversationStateMachine 增加 suggest_next（含 FRAMEWORK_CONFIRM 回退）+ force_set_state | `src/core/dialogue/state_machine.py` |

**注意**：Phase 1 必须同时完成 DialogueIntentState 和 DeepIntentResult 的修改，确保 `is_composite`/`sub_intents` 字段在 `merge_from_analysis` 调用前已存在。getattr 防御是额外保障。

### Phase 2: 对话Agent增强（3天）

| 任务 | 文件 |
|------|------|
| conversation.md 增加状态感知 | `prompts/agents/conversation.md` |
| intent_analysis_system.md 增加复合意图+示例 | `prompts/agents/intent_analysis_system.md` |
| _llm_converse 签名 + prompt 注入 + JSON 解析（同步+异步路径） | `src/api/research_api.py` |
| _handle_chat_mode 插入状态管理（含绝对轮次强制转换） | `src/api/research_api.py` |
| 辅助方法（含 update() 批量写入） | `src/api/research_api.py` |
| _enter_framework_mode 状态机同步 | `src/api/research_api.py` |

### Phase 3: 框架修订 + 对齐（2天）

| 任务 | 文件 |
|------|------|
| _llm_framework_modify prompt 增强（含 cancel action） | `src/api/research_api.py` |
| _handle_framework_mode cancel 分支（行 1593-1611 之间插入） | `src/api/research_api.py` |
| _merge_sections_dedup 语义去重（阈值 0.65） | `src/api/research_api.py` |
| _handle_user_message cancel/confirm 对齐 | `src/api/research_api.py` |

### Phase 4: 测试（2天）

| 任务 |
|------|
| 单元测试：DialogueIntentState.merge_from_analysis（使用 DeepIntentResult 实际字段名 + getattr 防御） |
| 单元测试：DialogueIntentState.update_readiness |
| 单元测试：ConversationStateMachine.suggest_next（含 FRAMEWORK_CONFIRM 回退） |
| 单元测试：DeepIntentResult.from_dict / to_dict 往返 |
| 单元测试：_should_deep_analyze 边界 |
| 单元测试：_merge_sections_dedup 阈值 0.65 |
| 端到端：模板快速启动不受影响 |
| 端到端：对话式研究渐进引导 + 状态转换 |
| 端到端：报告修订不受影响 |
| 端到端：cancel research → CLARIFYING 回退 |

**总工期**：约 9天 + 2天缓冲 = **11天**。

---

## 十一、风险评估

| 风险 | 缓解 |
|------|------|
| conversation.md 增强后 LLM 行为不稳定 | 新增指导为增强非替代；dialogue_context 可设为空字符串回滚 |
| 状态机与 LLM 冲突 | 冲突时维持当前状态；基于绝对对话轮次（v5.1 fix）强制转换 |
| DeepIntentResult 新字段破坏 to_intent_analysis_result | 新字段不被 to_intent_analysis_result 使用 |
| domain_context 中无 topic/aspects | merge_from_analysis 用 .get() 安全取值，空则不合并 |
| _handle_user_message 对齐引入回归 | Phase 3 单独实施，充分测试 |
| UNDERSTANDING→FRAMEWORK_CONFIRM 新路径导致过早跳转 | 仅在 readiness=SUFFICIENT 且 LLM 返回 enter_framework 时触发；PARTIAL 仍走 CLARIFYING 路径 |
| _force_transition_at 在 topic 变更时残留 | topic 变更时清除 _force_transition_at |
| merge_from_analysis 引用尚不存在的字段 | v5.1 fix: 使用 getattr 防御，Phase 1 同时修改 semantic_intent.py 和创建 DialogueIntentState |
| _enter_framework_mode 未同步状态机 | v5.1 fix: 新增 7.0 节，在 _enter_framework_mode 中同步状态机转换 |
| _sync_mode_with_state 不覆盖 EXECUTING 等状态 | v5.1 fix: 补充 EXECUTING/PAUSED/PREVIEWING/COMPLETED 的 mode 映射 |
| suggest_next 不覆盖 FRAMEWORK_CONFIRM 回退 | v5.1 fix: 新增 FRAMEWORK_CONFIRM→CLARIFYING 回退建议 |
| PersistentSessionDict 多次磁盘写入 | v5.1 fix: _save_dialogue_state 使用 update() 批量写入 |
| _merge_sections_dedup 误合并语义不同 section | v5.1 fix: token 重叠阈值从 0.5 调至 0.65 |
| 状态机转到 FRAMEWORK_CONFIRM 但 LLM 仍在闲聊 | v5.1 fix: 二次校验，action 不对齐时回退 mode 到 chat |
| cancel 时 _force_transition_at 残留 | v5.1 fix: cancel 路径中清除 _force_transition_at |
| state_machine.py 反向依赖 dialogue_intent_state.py | v5.2 fix: ReadinessLevel 移至 sub_intent.py，避免底层依赖上层 |
| _user_aspects/_framework_aspects 下划线前缀泄漏到 JSON | v5.2 fix: 改为 user_aspects/framework_aspects |
| action="clarify" 不存在于 LLM 输出 | v5.2 fix: 移除所有 "clarify" 引用，LLM 仅支持 continue_chat/enter_framework/start_execution |
| EXECUTING 直接 force_set_state 到 FRAMEWORK_CONFIRM | v5.2 fix: 先 EXECUTING→PAUSED→FRAMEWORK_CONFIRM，遵循合法转换路径 |
| DeepIntentResult.from_dict 丢失 analysis_timestamp | v5.2 fix: 补充 analysis_timestamp 反序列化 |

---

## 十二、修订记录

### v5.2 → v5.3（实施后代码审计）

| 项 | v5.2 内容 | v5.3 修正 | 原因 |
|----|----------|----------|------|
| 事实表 A | 列出 20 个原始字段（行 30-56） | 补充 is_composite/sub_intents/orchestration_strategy 3 个已实施字段（行 31-60） | 实施后字段已存在 |
| 事实表 A `_build_result` 行号 | 行 294 | 行 322 | 代码增长导致偏移 |
| 事实表 B 行号 | 行 95/167/163/40-80 | 行 101/173/169/45-86 | state_machine.py 代码增长 |
| 事实表 C 行号 | 行 156/352 | 行 158/354 | session_manager.py 代码增长 |
| 事实表 D | 行 712-956（_llm_converse） | 行 879-1128 | research_api.py 从 ~3k 增长至 4441 行 |
| 事实表 D 变量行号 | 行 727-828 | 行 894-995 | 同上 |
| 事实表 D f-string 行号 | 行 830-954 | 行 1001-1128 | 同上 |
| 事实表 D 注入点 | 行 828/836/837 | 行 995/1007/1009 | 同上 |
| 事实表 F | 行 400-422 | 行 402-425 | 同上 |
| §1.1 原则 5 | "行 458, 487 等调用点" | "research mode 下不传 intent_state/conversation_state" | 行 458/487 不存在，实际调用点在 research mode 路径中 |
| §4.5 _build_result 行号 | 行 282-298 | 行 322-381 | 代码增长 |
| §5.1 改动点行号 | 行 565/567-569/569/636 | 行 554/563-564/584-589/645 | 代码增长 |
| §5.2 update_from_response | readiness_score/level 在 enter_framework 块内（update_readiness 前） | 移至 update_readiness() 之后（dialogue_intent_state.py:110-112） | 实际代码将特殊加分放在 update_readiness 之后覆盖 |
| §5.3 _llm_converse 行号 | 行 828/836/999-1010/1211-1217 | 行 995/1007/1171-1182/1383-1393 | 代码增长 |
| §7.0 _enter_framework_mode | 行 1472-1566/1492/1545 | 行 1667-1763/1687/1741 | 代码增长 |
| §7.1 cancel research | 行 405-415 | 行 407-419 | 代码增长 |
| §7.2 _should_start_execution | 行 535-542/400 | 行 539-552/402 | 代码增长 |
| §7.3 模板快速启动 | 行 2427 | 移除行号引用（未找到对应位置） | create_session_from_template 不在 research_api.py 中 |
| §7.4 research mode | 行 422-531/1607-1614/3069-3072/3120-3123/3269-3272 | 行 426-537/1804-1811/3271+/3322+/3471+ | 代码增长 |
| §7.4 _llm_converse 调用点 | "行 458, 487" | "research mode 下不传" | 行号不存在 |
| §8.2 cancel 分支 | 行 1414-1416 | 行 1593-1611 | 代码增长 |
| §十 Phase 3 | 行 1414-1416 | 行 1593-1611 | 代码增长 |
| §6.1 state_machine 存储 | 行 352 | 行 354 | 代码增长 |
