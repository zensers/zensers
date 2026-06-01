# -*- coding: utf-8 -*-
"""
DeepIntentResult 扩展测试 (is_composite, sub_intents, from_dict)
"""

import pytest
from datetime import datetime
from src.core.semantic_intent import DeepIntentResult
from src.core.intent_types import IntentType, TaskComplexity
from src.core.research_type import ResearchType
from src.core.dialogue.sub_intent import SubIntent


class TestDeepIntentResultCompositeFields:
    def test_default_composite_fields(self):
        result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test",
        )
        assert result.is_composite is False
        assert result.sub_intents == []
        assert result.orchestration_strategy == "sequential"

    def test_composite_with_sub_intents(self):
        sub = SubIntent(intent_id="sub_1", description="市场研究", aspects=["市场规模"])
        result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test",
            is_composite=True,
            sub_intents=[sub],
            orchestration_strategy="hybrid",
        )
        assert result.is_composite is True
        assert len(result.sub_intents) == 1
        assert result.orchestration_strategy == "hybrid"


class TestDeepIntentResultToDictExtension:
    def test_to_dict_includes_composite_fields(self):
        sub = SubIntent(intent_id="sub_1", description="市场研究", aspects=["市场规模"])
        result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test",
            is_composite=True,
            sub_intents=[sub],
            orchestration_strategy="hybrid",
        )
        d = result.to_dict()
        assert d["is_composite"] is True
        assert len(d["sub_intents"]) == 1
        assert d["sub_intents"][0]["intent_id"] == "sub_1"
        assert d["orchestration_strategy"] == "hybrid"

    def test_to_dict_includes_timestamp(self):
        result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test",
        )
        d = result.to_dict()
        assert "analysis_timestamp" in d


class TestDeepIntentResultFromDict:
    def test_from_dict_round_trip(self):
        result = DeepIntentResult(
            primary_intent=IntentType.RESEARCH,
            intent_confidence=0.9,
            intent_reasoning="test reasoning",
            research_types=[ResearchType.INDUSTRY_RESEARCH],
            primary_research_type=ResearchType.INDUSTRY_RESEARCH,
            hidden_requirements=["政策环境"],
            needs_clarification=False,
            is_composite=True,
            sub_intents=[SubIntent(intent_id="sub_1", description="市场研究")],
            orchestration_strategy="hybrid",
        )
        d = result.to_dict()
        restored = DeepIntentResult.from_dict(d)
        assert restored.primary_intent == IntentType.RESEARCH
        assert restored.intent_confidence == 0.9
        assert restored.intent_reasoning == "test reasoning"
        assert restored.is_composite is True
        assert len(restored.sub_intents) == 1
        assert restored.orchestration_strategy == "hybrid"
        assert restored.hidden_requirements == ["政策环境"]
        assert restored.analysis_timestamp is not None

    def test_from_dict_default_values(self):
        d = {"primary_intent": "open_ended", "intent_confidence": 0.5, "intent_reasoning": ""}
        restored = DeepIntentResult.from_dict(d)
        assert restored.is_composite is False
        assert restored.sub_intents == []
        assert restored.orchestration_strategy == "sequential"

    def test_from_dict_preserves_timestamp(self):
        ts = "2026-05-17T10:30:00"
        d = {"primary_intent": "research", "intent_confidence": 0.9, "intent_reasoning": "test", "analysis_timestamp": ts}
        restored = DeepIntentResult.from_dict(d)
        assert restored.analysis_timestamp == datetime.fromisoformat(ts)

    def test_from_dict_missing_timestamp_uses_now(self):
        d = {"primary_intent": "research", "intent_confidence": 0.9, "intent_reasoning": "test"}
        restored = DeepIntentResult.from_dict(d)
        assert restored.analysis_timestamp is not None