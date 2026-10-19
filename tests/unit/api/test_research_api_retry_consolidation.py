# -*- coding: utf-8 -*-
"""research_api 三处手写重试并入引擎后的行为契约（spec §8#6-8，保守迁移）。"""
import asyncio
import importlib
import inspect
from unittest.mock import AsyncMock, patch

# ``from src.api import research_api`` binds the singleton INSTANCE (the
# package __init__ shadows the submodule), so import the real module for the
# patch/getsource seams.
research_api = importlib.import_module("src.api.research_api")


class TestRetrySiteRemoval:
    def test_adhoc_retry_markers_removed(self):
        source = inspect.getsource(research_api)
        assert "falling back to non-stream" not in source
        assert "_retry_json_only" not in source

    def test_helper_exists(self):
        assert hasattr(research_api, "_llm_call_with_engine_retry")


class TestHelper:
    def test_success_passthrough(self):
        with patch.object(research_api, "call_llm_ex", AsyncMock(return_value="OK")):
            result = asyncio.run(research_api._llm_call_with_engine_retry(
                prompt_builder=lambda v: "P"))
        assert result == "OK"

    def test_budget_exhaustion_returns_none(self):
        from src.core.llm_retry import LLMBudgetExhausted, LLMErrorClass, Classification
        with patch.object(research_api, "call_llm_ex",
                          AsyncMock(side_effect=LLMBudgetExhausted(
                              Classification(LLMErrorClass.DEGENERATE), 3, 60.0))):
            result = asyncio.run(research_api._llm_call_with_engine_retry(
                prompt_builder=lambda v: "P"))
        assert result is None

    def test_json_contract_forwarded(self):
        captured = {}
        async def fake_ex(prompt_builder, **kw):
            captured.update(kw)
            return "{}"
        with patch.object(research_api, "call_llm_ex", side_effect=fake_ex):
            asyncio.run(research_api._llm_call_with_engine_retry(
                prompt_builder=lambda v: "P", output_contract="json"))
        assert captured["output_contract"] == "json"

    def test_parse_hook_forwarded(self):
        from src.core.llm_retry import ParseOutcome
        captured = {}
        async def fake_ex(prompt_builder, **kw):
            captured.update(kw)
            return {"action": "continue_chat"}
        with patch.object(research_api, "call_llm_ex", side_effect=fake_ex):
            result = asyncio.run(research_api._llm_call_with_engine_retry(
                prompt_builder=lambda v: "P", output_contract="json",
                parse=lambda raw: ParseOutcome(True, value={"action": "continue_chat"})))
        assert callable(captured["parse"])
        assert result == {"action": "continue_chat"}
