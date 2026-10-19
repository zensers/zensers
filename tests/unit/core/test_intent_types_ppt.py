import pytest
from src.core.intent_types import IntentType


class TestIntentTypePptGeneration:
    def test_ppt_generation_exists(self):
        assert hasattr(IntentType, "PPT_GENERATION")

    def test_ppt_generation_value(self):
        assert IntentType.PPT_GENERATION.value == "ppt_generation"

    def test_intent_type_count(self):
        assert len(IntentType) == 9
