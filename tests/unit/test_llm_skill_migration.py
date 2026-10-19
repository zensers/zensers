# -*- coding: utf-8 -*-
"""
llm_skill → call_llm 迁移测试套件

基于 v3 迁移方案，逐项验证：
- Bug 1-4 修复
- 6 个分析 Skill 迁移
- Survey 子系统死代码/透传清理
- 直接实例化 LLMSkill 清理
- 返回格式兼容性

所有测试不依赖真实 LLM 调用，使用 mock。
"""

import pytest
import asyncio
import os
import sys
import inspect
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import Dict, Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


# ============================================================
# Bug 1: intelligent_routing_adapter.py:521 导入不存在的 src.core.llm
# ============================================================

class TestBug1WrongImportPath:
    """验证 intelligent_routing_adapter.py 不再导入不存在的 src.core.llm"""

    def test_no_src_core_llm_import(self):
        """intelligent_routing_adapter.py 中不应存在 from src.core.llm import ..."""
        with open("src/core/intelligent_routing_adapter.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "from src.core.llm import" not in content, \
            "Bug 1 未修复: 仍存在 from src.core.llm import call_llm (不存在的模块路径)"

    def test_correct_import_path_used(self):
        """intelligent_routing_adapter.py 应使用正确的 src.core.llm_client 导入路径"""
        with open("src/core/intelligent_routing_adapter.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "from src.core.llm_client import call_llm" in content, \
            "Bug 1 修复后应使用 from src.core.llm_client import call_llm"

    def test_src_core_llm_module_does_not_exist(self):
        """确认 src/core/llm.py 不存在（这是 Bug 1 的根因）"""
        assert not os.path.exists("src/core/llm.py"), \
            "src/core/llm.py 不应存在，call_llm 在 src/core/llm_client.py 中"

    def test_generate_hypotheses_with_llm_uses_correct_import(self):
        """_generate_hypotheses_with_llm 方法应能成功导入 call_llm"""
        from src.core.intelligent_routing_adapter import IntelligentRoutingAdapter
        source = inspect.getsource(IntelligentRoutingAdapter._generate_hypotheses_with_llm)
        assert "from src.core.llm import" not in source, \
            "_generate_hypotheses_with_llm 内部不应使用错误的导入路径"


# ============================================================
# Bug 2: document_generation_agent.py:1714 asyncio.run() 在 async 上下文中
# ============================================================

class TestBug2AsyncioRunInAsyncContext:
    """验证 document_generation_agent.py 不再在 async 上下文中使用 asyncio.run()"""

    def test_no_asyncio_run_wrapping_llm_execute(self):
        """document_generation_agent.py 中不应有 asyncio.run(self._llm_skill.execute(...))"""
        with open("src/agents/fixed_agents/document_generation_agent.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "asyncio.run(self._llm_skill.execute" not in content, \
            "Bug 2 未修复: 仍存在 asyncio.run(self._llm_skill.execute(...))"

    def test_no_asyncio_run_call_llm(self):
        """修复后也不应有 asyncio.run(call_llm(...))，应直接 await"""
        with open("src/agents/fixed_agents/document_generation_agent.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "asyncio.run(call_llm(" not in content, \
            "不应使用 asyncio.run(call_llm(...))，应直接 await call_llm(...)"

    def test_handle_adjust_content_is_async(self):
        """_handle_adjust_content 应改为 async def"""
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        assert inspect.iscoroutinefunction(DocumentGenerationAgent._handle_adjust_content), \
            "Bug 2 修复: _handle_adjust_content 必须是 async def"

    def test_handle_adjust_content_uses_call_llm(self):
        """_handle_adjust_content 应使用 call_llm 而非 self._llm_skill"""
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        source = inspect.getsource(DocumentGenerationAgent._handle_adjust_content)
        assert "call_llm" in source, \
            "_handle_adjust_content 应使用 call_llm()"
        assert "self._llm_skill" not in source, \
            "_handle_adjust_content 不应再引用 self._llm_skill"

    def test_no_set_llm_skill_method(self):
        """set_llm_skill() 方法应被移除（无外部调用者）"""
        from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
        assert not hasattr(DocumentGenerationAgent, "set_llm_skill"), \
            "set_llm_skill() 应被移除（无外部调用者，是死代码）"

    def test_no_self_llm_skill_attribute(self):
        """self._llm_skill 属性应被移除"""
        with open("src/agents/fixed_agents/document_generation_agent.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "self._llm_skill" not in content, \
            "self._llm_skill 应被移除，改用 call_llm()"


# ============================================================
# Bug 3: sentiment.py:284 asyncio.run() 条件性风险
# ============================================================

class TestBug3SentimentAsyncioRun:
    """验证 sentiment.py 不再使用 asyncio.run() 包裹 LLM 调用"""

    def test_no_asyncio_run_in_sentiment(self):
        """sentiment.py 中不应有 asyncio.run(self.llm_skill.execute(...))"""
        with open("src/survey/analysis/sentiment.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "asyncio.run(self.llm_skill.execute" not in content, \
            "Bug 3 未修复: 仍存在 asyncio.run(self.llm_skill.execute(...))"

    def test_llm_enhance_uses_call_llm_sync_or_async(self):
        """_llm_enhance 应使用 call_llm_sync() 或改为 async + await call_llm()"""
        with open("src/survey/analysis/sentiment.py", "r", encoding="utf-8") as f:
            content = f.read()
        uses_call_llm_sync = "call_llm_sync(" in content
        uses_await_call_llm = "await call_llm(" in content
        assert uses_call_llm_sync or uses_await_call_llm, \
            "_llm_enhance 应使用 call_llm_sync() 或 await call_llm()，而非 asyncio.run()"

    def test_no_llm_skill_param_in_sentiment(self):
        """SentimentAnalyzer 不应再接受 llm_skill 参数"""
        with open("src/survey/analysis/sentiment.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "llm_skill=" not in content, \
            "SentimentAnalyzer 不应再接受 llm_skill 参数，应直接使用 call_llm"


# ============================================================
# Bug 4: simulation_engine.py:176-177 .is_available() 不存在
# ============================================================

class TestBug4IsAvailableNotExists:
    """验证 simulation_engine.py 不再调用不存在的 .is_available() 方法"""

    def test_no_is_available_call(self):
        """simulation_engine.py (engine/) 中不应有 .is_available() 调用"""
        with open("src/survey/engine/simulation_engine.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert ".is_available()" not in content, \
            "Bug 4 未修复: 仍存在 .is_available() 调用（Skill 基类无此方法）"

    def test_skill_base_has_no_is_available(self):
        """确认 Skill 基类确实没有 is_available() 方法"""
        from src.skills.base import Skill
        assert not hasattr(Skill, "is_available"), \
            "Skill 基类没有 is_available() 方法，只有 is_enabled()"

    def test_preflight_check_does_not_call_is_available(self):
        """_preflight_check 方法不应调用 .is_available()"""
        with open("src/survey/engine/simulation_engine.py", "r", encoding="utf-8") as f:
            content = f.read()
        start = content.find("def _preflight_check")
        if start == -1:
            pytest.skip("_preflight_check 方法不存在或已重构")
        end = content.find("\n    def ", start + 1)
        method_body = content[start:end]
        assert "is_available" not in method_body, \
            "_preflight_check 不应调用 .is_available()"


# ============================================================
# 6 个分析 Skill 迁移验证
# ============================================================

class TestAnalysisSkillsMigration:
    """验证 6 个分析 Skill 已从 llm_skill 迁移到 call_llm()"""

    ANALYSIS_SKILLS = [
        ("data_analysis", "src/skills/analysis/data_analysis.py"),
        ("market_analysis", "src/skills/analysis/market_analysis.py"),
        ("policy_analysis", "src/skills/analysis/policy_analysis.py"),
        ("risk_analysis", "src/skills/analysis/risk_analysis.py"),
        ("stock_analysis", "src/skills/analysis/stock_analysis.py"),
        ("tech_trend", "src/skills/analysis/tech_trend.py"),
    ]

    @pytest.mark.parametrize("name,path", ANALYSIS_SKILLS)
    def test_no_reg_get_llm_skill(self, name, path):
        """分析 Skill 不应再使用 reg.get('llm_skill')"""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert 'reg.get("llm_skill")' not in content, \
            f"{name} 仍使用 reg.get('llm_skill')，应迁移到 call_llm()"

    @pytest.mark.parametrize("name,path", ANALYSIS_SKILLS)
    def test_imports_call_llm(self, name, path):
        """分析 Skill 应导入 call_llm"""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "from src.core.llm_client import call_llm" in content, \
            f"{name} 应导入 from src.core.llm_client import call_llm"

    @pytest.mark.parametrize("name,path", ANALYSIS_SKILLS)
    def test_no_llm_execute_call(self, name, path):
        """分析 Skill 不应再调用 llm.execute()"""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "llm.execute(" not in content, \
            f"{name} 仍调用 llm.execute()，应改为 call_llm()"

    @pytest.mark.parametrize("name,path", ANALYSIS_SKILLS)
    def test_uses_call_llm(self, name, path):
        """分析 Skill 应使用 call_llm()"""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "await call_llm(" in content, \
            f"{name} 应使用 await call_llm()"

    def test_stock_analysis_no_get_llm_helper(self):
        """stock_analysis.py 不应再有 _get_llm() 辅助方法"""
        with open("src/skills/analysis/stock_analysis.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "def _get_llm" not in content, \
            "stock_analysis.py 的 _get_llm() 辅助方法应被移除"

    def test_data_analysis_preserves_python_repl_registry(self):
        """data_analysis.py 迁移后仍需保留 get_skill_registry 给 lc_python_repl 用"""
        with open("src/skills/analysis/data_analysis.py", "r", encoding="utf-8") as f:
            content = f.read()
        if "lc_python_repl" in content or "lc_python" in content:
            assert "get_skill_registry" in content, \
                "data_analysis.py 使用 lc_python_repl，需保留 get_skill_registry 导入"

    def test_market_analysis_preserves_python_repl_registry(self):
        """market_analysis.py 迁移后仍需保留 get_skill_registry 给 lc_python_repl 用"""
        with open("src/skills/analysis/market_analysis.py", "r", encoding="utf-8") as f:
            content = f.read()
        if "lc_python_repl" in content or "lc_python" in content:
            assert "get_skill_registry" in content, \
                "market_analysis.py 使用 lc_python_repl，需保留 get_skill_registry 导入"

    def test_stock_analysis_preserves_python_repl_registry(self):
        """stock_analysis.py 迁移后仍需保留 get_skill_registry 给 lc_python_repl 用"""
        with open("src/skills/analysis/stock_analysis.py", "r", encoding="utf-8") as f:
            content = f.read()
        if "lc_python_repl" in content or "lc_python" in content:
            assert "get_skill_registry" in content, \
                "stock_analysis.py 使用 lc_python_repl，需保留 get_skill_registry 导入"


# ============================================================
# Survey 子系统死代码 & 透传清理验证
# ============================================================

class TestSurveyDeadCodeCleanup:
    """验证 survey 子系统中的死代码和 llm_skill 透传已清理"""

    def test_persona_factory_no_llm_skill_param(self):
        """persona_factory.py 不应再接受 llm_skill 参数（死代码）"""
        with open("src/survey/services/persona_factory.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "llm_skill" not in content, \
            "persona_factory.py 的 llm_skill 参数是死代码（存储但从未使用），应移除"

    def test_survey_analysis_agent_no_llm_skill_param(self):
        """survey_analysis_agent.py 不应再接受 llm_skill 参数（死代码）"""
        with open("src/agents/fixed_agents/survey_analysis_agent.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "llm_skill" not in content, \
            "survey_analysis_agent.py 的 llm_skill 参数是死代码（存储但从未使用），应移除"

    def test_survey_integration_agent_no_llm_skill_passthrough(self):
        """survey_integration_agent.py 不应再透传 llm_skill"""
        with open("src/agents/fixed_agents/survey_integration_agent.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "llm_skill=self.llm_skill" not in content, \
            "survey_integration_agent.py 不应再透传 llm_skill=self.llm_skill"

    def test_task_api_no_reg_get_llm_skill(self):
        """task_api.py 不应再使用 reg.get('llm_skill')"""
        with open("src/survey/task_api.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert 'reg.get("llm_skill")' not in content, \
            "task_api.py 不应再使用 reg.get('llm_skill')"

    def test_simulated_response_agent_no_llm_skill_param(self):
        """simulated_response_agent.py 不应再接受 llm_skill 参数"""
        with open("src/agents/fixed_agents/simulated_response_agent.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "llm_skill" not in content, \
            "simulated_response_agent.py 不应再接受 llm_skill 参数"

    def test_persona_generation_agent_uses_call_llm(self):
        """persona_generation_agent.py 应使用 call_llm() 而非 llm_skill"""
        with open("src/agents/fixed_agents/persona_generation_agent.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm" in content, \
            "persona_generation_agent.py 应使用 call_llm()"
        assert "self.llm_skill" not in content, \
            "persona_generation_agent.py 不应再引用 self.llm_skill"

    def test_survey_optimization_agent_uses_call_llm(self):
        """survey_optimization_agent.py 应使用 call_llm() 而非 llm_skill"""
        with open("src/agents/fixed_agents/survey_optimization_agent.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm" in content, \
            "survey_optimization_agent.py 应使用 call_llm()"
        assert "self.llm_skill" not in content, \
            "survey_optimization_agent.py 不应再引用 self.llm_skill"

    def test_cross_synthesis_agent_uses_call_llm(self):
        """cross_synthesis_agent.py 应使用 call_llm() 而非 llm_skill"""
        with open("src/agents/fixed_agents/cross_synthesis_agent.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm" in content, \
            "cross_synthesis_agent.py 应使用 call_llm()"
        assert "self.llm_skill" not in content, \
            "cross_synthesis_agent.py 不应再引用 self.llm_skill"


# ============================================================
# Survey 引擎层迁移验证
# ============================================================

class TestSurveyEngineMigration:
    """验证 survey 引擎层已从 llm_skill 迁移到 call_llm()"""

    def test_persona_generator_uses_call_llm(self):
        """persona_generator.py 应使用 call_llm() 而非 llm_skill"""
        with open("src/survey/engine/persona_generator.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm" in content, \
            "persona_generator.py 应使用 call_llm()"
        assert "self.llm_skill" not in content, \
            "persona_generator.py 不应再引用 self.llm_skill"

    def test_simulation_engine_uses_call_llm(self):
        """simulation_engine.py (engine/) 应使用 call_llm() 而非 llm_skill"""
        with open("src/survey/engine/simulation_engine.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm" in content, \
            "simulation_engine.py 应使用 call_llm()"
        assert "self._llm_skill" not in content, \
            "simulation_engine.py 不应再引用 self._llm_skill"

    def test_simulation_engine_preserves_timeout(self):
        """simulation_engine.py 迁移后应保留 asyncio.wait_for 超时保护"""
        with open("src/survey/engine/simulation_engine.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "asyncio.wait_for" in content, \
            "simulation_engine.py 必须保留 asyncio.wait_for() 超时保护（call_llm 无内置超时）"

    def test_focus_group_uses_call_llm(self):
        """focus_group.py 应使用 call_llm() 而非 llm_skill"""
        with open("src/survey/engine/focus_group.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm" in content, \
            "focus_group.py 应使用 call_llm()"
        assert "self.llm_skill" not in content, \
            "focus_group.py 不应再引用 self.llm_skill"

    def test_focus_group_preserves_timeout(self):
        """focus_group.py 迁移后应保留 asyncio.wait_for 超时保护"""
        with open("src/survey/engine/focus_group.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "asyncio.wait_for" in content, \
            "focus_group.py 必须保留 asyncio.wait_for() 超时保护"

    def test_services_simulation_engine_uses_call_llm(self):
        """simulation_engine.py (services/) 应使用 call_llm() 而非 llm_skill"""
        with open("src/survey/services/simulation_engine.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm" in content, \
            "services/simulation_engine.py 应使用 call_llm()"
        assert "self.llm_skill" not in content, \
            "services/simulation_engine.py 不应再引用 self.llm_skill"


# ============================================================
# 直接实例化 LLMSkill 清理验证
# ============================================================

class TestDirectLLMSkillInstantiationCleanup:
    """验证 LLMSkill 已完全移除"""

    def test_registry_no_llm_skill_import(self):
        """registry.py 不应再导入 LLMSkill"""
        with open("src/skills/registry.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "from .llm_skill import LLMSkill" not in content, \
            "registry.py 不应再导入 LLMSkill（已删除）"
        assert "llm_skill" not in content, \
            "registry.py 不应再引用 llm_skill"

    def test_skills_init_no_llm_skill_export(self):
        """skills/__init__.py 不应再导出 LLMSkill"""
        with open("src/skills/__init__.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "from src.skills.llm_skill import LLMSkill" not in content, \
            "skills/__init__.py 不应再导入 LLMSkill（已删除）"
        assert '"LLMSkill"' not in content, \
            "skills/__init__.py 的 __all__ 不应包含 LLMSkill"

    def test_llm_skill_py_does_not_exist(self):
        """src/skills/llm_skill.py 应已删除"""
        assert not os.path.exists("src/skills/llm_skill.py"), \
            "llm_skill.py 应已被删除"


# ============================================================
# 返回格式兼容性验证
# ============================================================

class TestReturnFormatCompatibility:
    """验证 call_llm() 返回格式与 llm_skill.execute() 在成功路径上兼容"""

    @pytest.mark.asyncio
    async def test_call_llm_success_has_required_keys(self):
        """call_llm() 成功返回应包含 success, content, model, usage, message"""
        from src.core.llm_client import call_llm
        mock_response = {
            "id": "test",
            "choices": [{"message": {"content": "test content"}, "finish_reason": "stop"}],
            "model": "test-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock, return_value=mock_response):
            result = await call_llm(prompt="test", system_prompt="sys")
            assert result["success"] is True
            assert "content" in result
            assert "model" in result
            assert "usage" in result
            assert "message" in result

    @pytest.mark.asyncio
    async def test_call_llm_failure_has_required_keys(self):
        """call_llm() 失败返回应包含 success, message, error"""
        from src.core.llm_client import call_llm
        result = await call_llm(prompt="")
        assert result["success"] is False
        assert "message" in result
        assert "error" in result
        assert result["error"] == "empty_prompt"

    def test_skill_failure_format(self):
        """Skill._failure() 返回格式验证"""
        from src.skills.base import Skill

        class TestSkill(Skill):
            @property
            def name(self): return "test"
            @property
            def description(self): return "test"
            async def execute(self, **kwargs): return {}

        skill = TestSkill()
        result = skill._failure("some error detail", "user message")
        assert result == {"success": False, "message": "user message", "error": "some error detail"}

    def test_skill_success_format(self):
        """Skill._success() 返回格式验证"""
        from src.skills.base import Skill

        class TestSkill(Skill):
            @property
            def name(self): return "test"
            @property
            def description(self): return "test"
            async def execute(self, **kwargs): return {}

        skill = TestSkill()
        result = skill._success({"content": "hello", "model": "gpt-4"}, "OK")
        assert result == {"success": True, "message": "OK", "content": "hello", "model": "gpt-4"}


# ============================================================
# call_llm_sync 可用性验证（Bug 3 修复依赖）
# ============================================================

class TestCallLlmSyncAvailability:
    """验证 call_llm_sync() 可用且正确处理事件循环"""

    def test_call_llm_sync_exists(self):
        """call_llm_sync() 应存在于 llm_client 模块中"""
        from src.core.llm_client import call_llm_sync
        assert callable(call_llm_sync), "call_llm_sync() 应可调用"

    def test_call_llm_sync_signature(self):
        """call_llm_sync() 签名应与 call_llm() 一致"""
        from src.core.llm_client import call_llm_sync
        sig = inspect.signature(call_llm_sync)
        params = list(sig.parameters.keys())
        assert "prompt" in params, "call_llm_sync 应有 prompt 参数"
        assert "system_prompt" in params, "call_llm_sync 应有 system_prompt 参数"

    @pytest.mark.asyncio
    async def test_call_llm_sync_works_in_async_context(self):
        """call_llm_sync() 在已有事件循环时应使用线程池而非 asyncio.run()"""
        from src.core.llm_client import call_llm_sync
        mock_response = {
            "id": "test",
            "choices": [{"message": {"content": "sync test"}, "finish_reason": "stop"}],
            "model": "test-model",
            "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
        }
        with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock, return_value=mock_response):
            result = call_llm_sync(prompt="test")
            assert result["success"] is True, \
                "call_llm_sync() 在 async 上下文中应正常工作（使用线程池桥接）"


# ============================================================
# 超时保护保留验证
# ============================================================

_TIMEOUT_FILES = [
    ("persona_generator.py", "src/survey/engine/persona_generator.py", True),
    ("simulation_engine.py", "src/survey/engine/simulation_engine.py", True),
    ("focus_group.py", "src/survey/engine/focus_group.py", True),
    ("cross_synthesis_agent.py", "src/agents/fixed_agents/cross_synthesis_agent.py", False),
]

class TestTimeoutPreservation:
    """验证需要局部超时保护的组件保留保护，深度研究组件不引入固定总超时"""

    @pytest.mark.parametrize("name,path,expected_timeout", _TIMEOUT_FILES)
    def test_timeout_policy(self, name, path, expected_timeout):
        """超时策略由组件职责决定，而不是要求所有组件复制同一实现"""
        if not os.path.exists(path):
            pytest.skip(f"{path} 不存在")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if expected_timeout:
            assert "asyncio.wait_for" in content, \
                f"{name} 需要保留局部 asyncio.wait_for() 超时保护"
        else:
            assert "asyncio.wait_for" not in content, \
                f"{name} 不应引入固定总 asyncio.wait_for() 超时"


# ============================================================
# Orchestrator 注入清理验证
# ============================================================

class TestOrchestratorInjectionCleanup:
    """验证 orchestrator.py 不再注入 llm_skill 实例"""

    def test_no_llm_skill_get_from_registry(self):
        """orchestrator.py 不应再从 registry 获取 llm_skill 实例"""
        with open("src/core/orchestrator/orchestrator.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert 'get("llm_skill")' not in content, \
            "orchestrator.py 不应再从 registry 获取 llm_skill 实例"

    def test_no_llm_skill_kwarg_in_chapter_writer(self):
        """orchestrator.py 不应再向 ChapterWriter 传 llm_skill= 参数"""
        with open("src/core/orchestrator/orchestrator.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "llm_skill=_llm_skill" not in content, \
            "orchestrator.py 不应再向子组件传 llm_skill= 参数"
        assert "llm_skill=llm_skill" not in content, \
            "orchestrator.py 不应再向子组件传 llm_skill= 参数"


# ============================================================
# 已迁移模块参数残留清理验证
# ============================================================

class TestBackwardCompatParamCleanup:
    """验证已迁移模块的 llm_skill=None 参数残留已清理"""

    PARAM_RESIDUE_FILES = [
        ("chapter_writer.py", "src/agents/fixed_agents/report_upgrade/chapter_writer.py"),
        ("chapter_reviewer.py", "src/agents/fixed_agents/report_upgrade/chapter_reviewer.py"),
        ("global_reviewer.py", "src/agents/fixed_agents/report_upgrade/global_reviewer.py"),
        ("orchestrator.py", "src/agents/fixed_agents/report_upgrade/orchestrator.py"),
        ("data_repair.py", "src/agents/fixed_agents/report_upgrade/data_repair.py"),
        ("persona_skill.py", "src/skills/builtin/persona_skill.py"),
        ("simulation_skill.py", "src/skills/builtin/simulation_skill.py"),
        ("ai_simulation.py", "src/survey/backends/ai_simulation.py"),
    ]

    @pytest.mark.parametrize("name,path", PARAM_RESIDUE_FILES)
    def test_no_llm_skill_param(self, name, path):
        """已迁移模块不应再接受 llm_skill=None 参数"""
        if not os.path.exists(path):
            pytest.skip(f"{path} 不存在")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "llm_skill" not in content, \
            f"{name} 的 llm_skill=None 参数残留应被移除（已迁移到 call_llm）"


# ============================================================
# llm_skill.py 删除验证（Phase 2 最终步骤）
# ============================================================

class TestLlmSkillFileDeletion:
    """验证 llm_skill.py 已被删除"""

    def test_llm_skill_py_does_not_exist(self):
        """src/skills/llm_skill.py 应不存在"""
        assert not os.path.exists("src/skills/llm_skill.py"), \
            "llm_skill.py 应已被删除（迁移完成）"

    def test_no_llm_skill_import_in_any_src_file(self):
        """src/ 中不应有任何文件导入 llm_skill"""
        for root, dirs, files in os.walk("src"):
            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                assert "from src.skills.llm_skill import" not in content, \
                    f"{path} 不应导入 llm_skill"
                assert "from .llm_skill import" not in content, \
                    f"{path} 不应导入 llm_skill"

    def test_no_legacy_llm_skill_in_runtime_prompts(self):
        """运行时 prompt 元数据不应再声明已删除的 llm_skill。"""
        for root, dirs, files in os.walk("prompts"):
            for f in files:
                if not f.endswith(".md"):
                    continue
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                assert "llm_skill" not in content, \
                    f"{path} 不应再声明已删除的 llm_skill"
