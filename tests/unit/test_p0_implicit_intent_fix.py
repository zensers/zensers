# -*- coding: utf-8 -*-
"""
P0 Fix: 隐含意图识别失败

测试验证:
- regex fallback 能识别隐含不满/质疑意图（"为什么评分低"、"这个章节写得不好"等）
- LLM prompt 引导隐含意图推理（通过 mock 验证 prompt 内容）
- is_global_feedback 字段被正确设置
- 修订意图映射器支持隐含意图关键词

Bug: 用户问 "为什么整体评分只有52.4"，系统返回 "未能理解您的修订意图"
根因: regex fallback 只匹配显式动词(修改/删除/添加)，无法识别隐含意图
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.core.adjustment.revision_types import RevisionOpType, AnalysisResult
from src.core.intent.revision_intent_analyzer import (
    RevisionIntentAnalyzer,
    INTENT_TO_REVISION_MAP_V2,
    _REVISION_SYSTEM_PROMPT,
)
from src.core.adjustment.revision_intent_mapper import RevisionIntentMapper
from src.core.intent_types import IntentType, TaskComplexity


class TestImplicitIntentRegexFallback:
    """regex fallback 应能识别隐含不满/质疑意图"""

    @pytest.mark.asyncio
    async def test_why_score_low_recognized_as_modify(self):
        """'为什么整体评分只有52.4' 应被识别为 MODIFY 而非 UNKNOWN"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("为什么整体评分只有52.4")
        assert result.intents, "隐含不满意图不应返回空 intents"
        assert result.intents[0].action_type == RevisionOpType.MODIFY

    @pytest.mark.asyncio
    async def test_chapter_bad_quality_recognized(self):
        """'这个章节写得不好' 应被识别为 MODIFY"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("这个章节写得不好")
        assert result.intents, "质量不满应返回非空 intents"
        assert result.intents[0].action_type == RevisionOpType.MODIFY

    @pytest.mark.asyncio
    async def test_insufficient_depth_recognized(self):
        """'分析深度不够' 应被识别为 MODIFY"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("分析深度不够")
        assert result.intents
        assert result.intents[0].action_type == RevisionOpType.MODIFY

    @pytest.mark.asyncio
    async def test_data_not_accurate_recognized(self):
        """'数据不准确' 应被识别为 MODIFY"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("数据不准确")
        assert result.intents
        assert result.intents[0].action_type == RevisionOpType.MODIFY

    @pytest.mark.asyncio
    async def test_why_so_poor_english(self):
        """'why is the score so low' 应被识别为 MODIFY"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("why is the score so low")
        assert result.intents
        assert result.intents[0].action_type == RevisionOpType.MODIFY

    @pytest.mark.asyncio
    async def test_explicit_modify_still_works(self):
        """显式动词匹配不应被破坏"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("修改第三章的内容")
        assert result.intents
        assert result.intents[0].action_type == RevisionOpType.MODIFY

    @pytest.mark.asyncio
    async def test_delete_still_works(self):
        """删除操作仍应正确匹配"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("删除这个章节")
        assert result.intents
        assert result.intents[0].action_type == RevisionOpType.DELETE

    @pytest.mark.asyncio
    async def test_global_feedback_flag_set_for_quality_complaint(self):
        """质量不满应设置 is_global_feedback=True"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("为什么整体评分只有52.4")
        assert result.is_global_feedback is True

    @pytest.mark.asyncio
    async def test_global_feedback_alone_implies_modify(self):
        """'整体评分只有52.4' 仅含全局反馈关键词，无显式动词和隐含意图，仍应推断为 MODIFY"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("整体评分只有52.4")
        assert result.intents, "全局反馈应推断为修改意图"
        assert result.intents[0].action_type == RevisionOpType.MODIFY
        assert result.is_global_feedback is True

    @pytest.mark.asyncio
    async def test_explicit_modify_no_global_feedback(self):
        """显式修改请求不应设置 is_global_feedback"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("修改第三章的内容")
        assert result.is_global_feedback is False

    @pytest.mark.asyncio
    async def test_no_false_positive_on_travel_word(self):
        """'出差' 不应被误匹配为隐含意图"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("我去出差了")
        assert result.intents == [] or result.intents[0].action_type == RevisionOpType.UNKNOWN

    @pytest.mark.asyncio
    async def test_no_false_positive_on_gap_word(self):
        """'差距' 不应被误匹配为隐含意图"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("分析两者的差距")
        assert result.intents == [] or result.intents[0].action_type == RevisionOpType.UNKNOWN

    @pytest.mark.asyncio
    async def test_no_false_positive_on_weak_point(self):
        """'弱点' 应由语义判断，regex 不应误触发"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("讨论竞争弱点")
        assert result.intents == [] or result.intents[0].action_type == RevisionOpType.UNKNOWN

    @pytest.mark.asyncio
    async def test_very_bad_is_implicit_intent(self):
        """'质量很差' 应匹配隐含意图"""
        analyzer = RevisionIntentAnalyzer()
        result = await analyzer.fallback_to_regex("这个质量很差")
        assert result.intents
        assert result.intents[0].action_type == RevisionOpType.MODIFY


class TestImplicitIntentMapV2ContainsPatterns:
    """关键词应从 YAML 配置加载，包含隐含意图模式"""

    def test_registry_has_implicit_patterns(self):
        """KeywordRegistry 应包含隐含意图关键词"""
        from src.core.intent.keyword_registry import get_registry
        registry = get_registry()
        assert registry.is_implicit_intent("为什么评分低"), "注册表应识别'为什么'"
        assert registry.is_implicit_intent("深度不够"), "注册表应识别'不够'"
        assert registry.is_implicit_intent("why is it so poor"), "注册表应识别'why.*poor'"

    def test_registry_has_global_feedback_patterns(self):
        """KeywordRegistry 应包含全局反馈关键词"""
        from src.core.intent.keyword_registry import get_registry
        registry = get_registry()
        assert registry.is_global_feedback("整体评分低"), "注册表应识别'整体'"
        assert registry.is_global_feedback("overall quality"), "注册表应识别'overall'"


class TestLLMPromptContainsImplicitIntentGuidance:
    """LLM system prompt 应包含隐含意图推理引导"""

    def test_prompt_mentions_implicit_intent(self):
        """_REVISION_SYSTEM_PROMPT 应包含隐含意图推理引导"""
        prompt_lower = _REVISION_SYSTEM_PROMPT.lower()
        has_implicit_guidance = (
            "implicit" in prompt_lower
            or "dissatisf" in prompt_lower
            or "infer" in prompt_lower
            or "隐含" in _REVISION_SYSTEM_PROMPT
            or "不满" in _REVISION_SYSTEM_PROMPT
        )
        assert has_implicit_guidance, "_REVISION_SYSTEM_PROMPT 缺少隐含意图推理引导"

    def test_prompt_mentions_global_feedback(self):
        """_REVISION_SYSTEM_PROMPT 应引导使用 is_global_feedback"""
        prompt = _REVISION_SYSTEM_PROMPT
        has_global_feedback = "is_global_feedback" in prompt or "global_feedback" in prompt
        assert has_global_feedback, "_REVISION_SYSTEM_PROMPT 未引导使用 is_global_feedback"


class TestRevisionIntentMapperImplicitIntent:
    """RevisionIntentMapper 应支持隐含意图关键词"""

    def test_quality_complaint_maps_to_improve_clarity(self):
        """质量不满应映射到 IMPROVE_CLARITY 或 UPDATE_DATA"""
        mapper = RevisionIntentMapper()
        revision_intent, _ = mapper.map(
            primary_intent=IntentType.FIX,
            complexity=TaskComplexity.SINGLE,
            user_input="这个章节写得不好",
        )
        from src.core.intent_types import RevisionIntentType
        assert revision_intent in (
            RevisionIntentType.IMPROVE_CLARITY,
            RevisionIntentType.UPDATE_DATA,
            RevisionIntentType.REWRITE_TEXT,
        ), f"质量不满应映射到改进类意图，实际: {revision_intent}"

    def test_insufficient_depth_maps_to_improve(self):
        """'分析深度不够' 应映射到改进类意图"""
        mapper = RevisionIntentMapper()
        revision_intent, _ = mapper.map(
            primary_intent=IntentType.FIX,
            complexity=TaskComplexity.SINGLE,
            user_input="分析深度不够",
        )
        from src.core.intent_types import RevisionIntentType
        assert revision_intent in (
            RevisionIntentType.IMPROVE_CLARITY,
            RevisionIntentType.UPDATE_DATA,
            RevisionIntentType.REWRITE_TEXT,
        ), f"深度不足应映射到改进类意图，实际: {revision_intent}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
