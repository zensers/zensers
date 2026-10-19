# -*- coding: utf-8 -*-
"""
DialogueIntentState - Cumulative dialogue state for intent tracking.

Independent from DeepIntentResult (single analysis result).
Tracks accumulated information across the entire conversation.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
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
    research_turns: int = 0
    user_aspects: List[str] = field(default_factory=list)
    framework_aspects: List[str] = field(default_factory=list)

    def merge_from_analysis(self, deep_result):
        dc = deep_result.domain_context or {}
        dc_topic = dc.get("topic", "")
        if dc_topic and (not self.topic_hint or len(dc_topic) > len(self.topic_hint)):
            self.topic_hint = dc_topic

        dc_aspects = dc.get("aspects", [])
        if isinstance(dc_aspects, list):
            for a in dc_aspects:
                if a and a not in self.confirmed_aspects:
                    self.confirmed_aspects.append(a)
                    self.user_aspects.append(a)

        for req in (deep_result.hidden_requirements or []):
            if req not in self.hidden_requirements:
                self.hidden_requirements.append(req)

        if deep_result.clarification_questions:
            self.pending_questions = deep_result.clarification_questions

        if deep_result.needs_clarification:
            if self.readiness_level == ReadinessLevel.SUFFICIENT:
                self.readiness_level = ReadinessLevel.PARTIAL
                self.readiness_score = min(self.readiness_score, 0.65)

        if dc:
            for k, v in dc.items():
                if k not in self.domain_context:
                    self.domain_context[k] = v

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
        action = conv_result.get("action", "")
        if action == "enter_framework" or conv_result.get("topic"):
            self.research_turns += 1

        if action == "enter_framework":
            sections = conv_result.get("framework_sections", [])
            for sec in sections:
                if sec not in self.confirmed_aspects:
                    self.confirmed_aspects.append(sec)
                    self.framework_aspects.append(sec)

        if conv_result.get("clarification_questions"):
            self.pending_questions = conv_result["clarification_questions"]
            self.clarification_count += 1

        for asp in (conv_result.get("identified_aspects") or []):
            if asp not in self.confirmed_aspects:
                self.confirmed_aspects.append(asp)
                self.user_aspects.append(asp)

        if conv_result.get("is_composite"):
            self.is_composite = True

        if conv_result.get("topic") and not self.topic_hint:
            self.topic_hint = conv_result["topic"]

        if action == "enter_framework":
            self.update_readiness()
            if self.topic_hint:
                self.readiness_score = max(self.readiness_score, 0.7)
                self.readiness_level = ReadinessLevel.SUFFICIENT
        else:
            self.update_readiness()

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
        self.user_aspects = []
        self.framework_aspects = []

    def clear_framework_aspects(self):
        self.framework_aspects = []
        self.confirmed_aspects = list(self.user_aspects)
        self.hidden_requirements = []
        self.readiness_score = 0.0
        self.readiness_level = ReadinessLevel.INSUFFICIENT
        self.is_composite = False
        self.sub_intents = []
