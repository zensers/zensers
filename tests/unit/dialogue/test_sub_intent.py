# -*- coding: utf-8 -*-
"""
SubIntent & ReadinessLevel 单元测试
"""

import pytest
from src.core.dialogue.sub_intent import SubIntent, ReadinessLevel


class TestReadinessLevel:
    def test_values(self):
        assert ReadinessLevel.INSUFFICIENT.value == "insufficient"
        assert ReadinessLevel.PARTIAL.value == "partial"
        assert ReadinessLevel.SUFFICIENT.value == "sufficient"

    def test_from_value(self):
        assert ReadinessLevel("insufficient") == ReadinessLevel.INSUFFICIENT
        assert ReadinessLevel("partial") == ReadinessLevel.PARTIAL
        assert ReadinessLevel("sufficient") == ReadinessLevel.SUFFICIENT

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ReadinessLevel("unknown")


class TestSubIntent:
    def test_defaults(self):
        si = SubIntent(intent_id="sub_1", description="test")
        assert si.intent_id == "sub_1"
        assert si.description == "test"
        assert si.aspects == []
        assert si.research_types == []
        assert si.dependency == "none"

    def test_with_values(self):
        si = SubIntent(
            intent_id="sub_2",
            description="市场调研",
            aspects=["市场规模", "竞争格局"],
            research_types=["industry_research"],
            dependency="moderate",
        )
        assert si.aspects == ["市场规模", "竞争格局"]
        assert si.dependency == "moderate"