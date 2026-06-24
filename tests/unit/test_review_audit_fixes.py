# -*- coding: utf-8 -*-
"""
Deep Code Review Fixes — Test Suite

Tests for bugs found during systematic code review:
- BUG-1: revision_intent_analyzer accessed registry._raw bypassing encapsulation
- BUG-2: safe_create_task created but never used (62 bare asyncio.create_task)
- BUG-3: register_global_exception_handler never called
- BUG-4: _is_likely_company_name ignored chinese_text, only checked full_topic
- BUG-5: YAML duplicate header line
- BUG-6: get_revision_pattern_strings re-parsed _raw instead of using cached data
- Circular import: task_utils top-level import in communication.py / document_generation_agent.py
"""

import pytest
import asyncio
import re
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock


class TestKeywordRegistryPublicAPI:
    """BUG-1 fix: analyzer 应使用 registry 公共 API，而非 _raw"""

    def test_get_implicit_pattern_strings_returns_dict(self):
        from src.core.intent.keyword_registry import get_registry
        registry = get_registry()
        result = registry.get_implicit_pattern_strings()
        assert isinstance(result, dict)
        assert "chinese" in result
        assert "english" in result
        assert isinstance(result["chinese"], list)
        assert isinstance(result["english"], list)

    def test_get_implicit_pattern_strings_has_content(self):
        from src.core.intent.keyword_registry import get_registry
        registry = get_registry()
        result = registry.get_implicit_pattern_strings()
        assert len(result["chinese"]) > 0, "隐含意图中文模式不应为空"
        assert len(result["english"]) > 0, "隐含意图英文模式不应为空"

    def test_get_global_feedback_pattern_strings_returns_dict(self):
        from src.core.intent.keyword_registry import get_registry
        registry = get_registry()
        result = registry.get_global_feedback_pattern_strings()
        assert isinstance(result, dict)
        assert "chinese" in result
        assert "english" in result

    def test_get_global_feedback_pattern_strings_has_content(self):
        from src.core.intent.keyword_registry import get_registry
        registry = get_registry()
        result = registry.get_global_feedback_pattern_strings()
        assert len(result["chinese"]) > 0, "全局反馈中文关键词不应为空"

    def test_analyzer_does_not_access_raw(self):
        """revision_intent_analyzer.py 不应直接访问 registry._raw"""
        with open("src/core/intent/revision_intent_analyzer.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "registry._raw" not in content, "analyzer 不应直接访问 registry._raw"


class TestSafeCreateTaskIntegration:
    """BUG-2 fix: safe_create_task 应被实际使用"""

    def test_research_api_uses_safe_create_task(self):
        """research_api.py 应使用 safe_create_task 而非裸 asyncio.create_task"""
        with open("src/api/research_api.py", "r", encoding="utf-8") as f:
            content = f.read()
        bare_count = content.count("asyncio.create_task(")
        assert bare_count == 0, f"research_api.py 仍有 {bare_count} 处裸 asyncio.create_task"

    def test_main_api_uses_safe_create_task(self):
        """main.py 应使用 safe_create_task"""
        with open("src/api/main.py", "r", encoding="utf-8") as f:
            content = f.read()
        bare_count = content.count("asyncio.create_task(")
        assert bare_count == 0, f"main.py 仍有 {bare_count} 处裸 asyncio.create_task"

    def test_communication_uses_safe_create_task(self):
        """communication.py 应使用 safe_create_task"""
        with open("src/core/communication.py", "r", encoding="utf-8") as f:
            content = f.read()
        bare_count = content.count("asyncio.create_task(")
        assert bare_count == 0, f"communication.py 仍有 {bare_count} 处裸 asyncio.create_task"

    def test_coordinator_files_use_safe_create_task(self):
        """coordinator 文件应使用 safe_create_task"""
        files = [
            "src/core/orchestrator/execution/coordinator/agent_coordinator.py",
            "src/core/orchestrator/execution/coordinator/cancel_manager.py",
            "src/core/orchestrator/execution/coordinator/heartbeat_monitor.py",
        ]
        for fp in files:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            bare_count = content.count("asyncio.create_task(")
            assert bare_count == 0, f"{fp} 仍有 {bare_count} 处裸 asyncio.create_task"

    @pytest.mark.asyncio
    async def test_safe_create_task_logs_exception(self):
        """safe_create_task 应记录任务异常"""
        from src.core.orchestrator.execution.task_utils import safe_create_task

        async def boom():
            raise RuntimeError("kaboom")

        with patch("src.core.orchestrator.execution.task_utils.logger") as mock_logger:
            task = safe_create_task(boom(), name="test_boom")
            await asyncio.sleep(0.1)
        assert task.exception() is not None
        error_calls = mock_logger.error.call_args_list
        assert len(error_calls) > 0, "异常应被 error 日志记录"


class TestGlobalExceptionHandlerRegistered:
    """BUG-3 fix: register_global_exception_handler 应在启动时调用"""

    def test_startup_event_calls_register(self):
        """main.py startup_event 应调用 register_global_exception_handler"""
        with open("src/api/main.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "register_global_exception_handler" in content, \
            "main.py startup_event 应调用 register_global_exception_handler"

    def test_handler_function_exists(self):
        from src.core.orchestrator.execution.task_utils import register_global_exception_handler
        assert callable(register_global_exception_handler)


class TestIsLikelyCompanyNameLogic:
    """BUG-4 fix: _is_likely_company_name 应检查 chinese_text 而非仅 full_topic"""

    def test_company_name_in_chinese_text(self):
        """chinese_text 本身含公司名时应返回 True"""
        from src.core.decomposition.strategies import _is_listed_company_topic
        assert _is_listed_company_topic("比亚迪") is True

    def test_company_name_in_full_topic_only(self):
        """chinese_text 不含公司名但 full_topic 含时也应返回 True"""
        from src.core.decomposition.strategies import _is_listed_company_topic
        assert _is_listed_company_topic("比亚迪财务分析") is True

    def test_no_company_in_either(self):
        """两者都不含公司关键词时应返回 False"""
        from src.core.decomposition.strategies import _is_listed_company_topic
        assert _is_listed_company_topic("财务分析") is False

    def test_generic_agent_checks_chinese_text_first(self):
        """_is_likely_company_name 应先检查 chinese_text"""
        with open("src/core/agents/generic_agent.py", "r", encoding="utf-8") as f:
            content = f.read()
        fn_start = content.find("def _is_likely_company_name")
        fn_block = content[fn_start:fn_start + 300]
        assert "chinese_text" in fn_block, "_is_likely_company_name 应使用 chinese_text 参数"
        assert "_is_listed_company_topic(chinese_text)" in fn_block, \
            "_is_likely_company_name 应先检查 chinese_text"


class TestYAMLNoDuplicateHeader:
    """BUG-5 fix: YAML 不应有重复标题行"""

    def test_no_duplicate_header(self):
        with open("config/keyword_mappings.yaml", "r", encoding="utf-8") as f:
            lines = f.readlines()
        header_count = sum(1 for l in lines if l.strip() == "# Keyword Mapping Configuration")
        assert header_count == 1, f"YAML 标题行重复 {header_count} 次，应为 1 次"


class TestRevisionPatternStringsFromCache:
    """BUG-6 fix: get_revision_pattern_strings 应从缓存数据构建"""

    def test_method_does_not_access_raw(self):
        """get_revision_pattern_strings 不应重新解析 _raw"""
        with open("src/core/intent/keyword_registry.py", "r", encoding="utf-8") as f:
            content = f.read()
        fn_start = content.find("def get_revision_pattern_strings")
        fn_end = content.find("\n    def ", fn_start + 1)
        fn_body = content[fn_start:fn_end]
        assert "_raw" not in fn_body, "get_revision_pattern_strings 不应访问 _raw，应使用 _revision_patterns"

    def test_pattern_strings_match_compiled(self):
        """get_revision_pattern_strings 返回值应与已编译模式一致"""
        from src.core.intent.keyword_registry import get_registry
        registry = get_registry()
        compiled = registry.get_revision_patterns()
        strings = registry.get_revision_pattern_strings()
        for pattern_str, action_type in strings.items():
            assert action_type in compiled, f"action_type {action_type} 不在编译后模式中"
            assert len(compiled[action_type]) > 0


class TestNoCircularImport:
    """循环导入修复: communication.py 和 document_generation_agent.py 使用延迟导入"""

    def test_communication_no_top_level_task_utils(self):
        """communication.py 不应在顶层导入 task_utils"""
        with open("src/core/communication.py", "r", encoding="utf-8") as f:
            lines = f.readlines()
        top_level_imports = [l for l in lines[:30] if "task_utils" in l and not l.strip().startswith("#")]
        assert len(top_level_imports) == 0, "communication.py 不应在顶层导入 task_utils"

    def test_document_agent_no_top_level_task_utils(self):
        """document_generation_agent.py 不应在顶层导入 task_utils"""
        with open("src/agents/fixed_agents/document_generation_agent.py", "r", encoding="utf-8") as f:
            lines = f.readlines()
        top_level_imports = [l for l in lines[:40] if "task_utils" in l and not l.strip().startswith("#")]
        assert len(top_level_imports) == 0, "document_generation_agent.py 不应在顶层导入 task_utils"

    def test_all_modules_importable(self):
        """所有核心模块应能正常导入，无循环导入"""
        from src.core.orchestrator.execution.task_utils import safe_create_task
        from src.core.communication import MessageBus
        from src.core.intent.keyword_registry import get_registry
        from src.core.intent.revision_intent_analyzer import RevisionIntentAnalyzer
        from src.core.adjustment.revision_intent_mapper import RevisionIntentMapper
        from src.core.decomposition.strategies import _is_listed_company_topic
        from src.api.research_api import ResearchAPI


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
