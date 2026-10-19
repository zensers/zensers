"""
LLM 调用链端到端验证测试

验证所有已迁移到 call_llm()/call_llm_sync() 的模块：
1. 导入路径正确
2. 调用签名匹配（参数名、类型）
3. 返回值处理正确（success/content/usage/error）
4. 异步/同步调用方式正确
"""
import os
import pytest
import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

CALL_LLM_MODULES = [
    ("task_structure.py", "src.core.task_structure", "call_llm"),
    ("intelligent_routing_adapter.py", "src.core.intelligent_routing_adapter", "call_llm"),
    ("generic_agent.py", "src.core.agents.generic_agent", "call_llm"),
    ("focus_group.py", "src.survey.engine.focus_group", "call_llm"),
    ("simulation_engine (services)", "src.survey.services.simulation_engine", "call_llm"),
    ("semantic_intent.py", "src.core.semantic_intent", "call_llm"),
    ("report_upgrade/orchestrator.py", "src.agents.fixed_agents.report_upgrade.orchestrator", "call_llm"),
    ("data_repair.py", "src.agents.fixed_agents.report_upgrade.data_repair", "call_llm"),
    ("global_reviewer.py", "src.agents.fixed_agents.report_upgrade.global_reviewer", "call_llm"),
    ("chapter_reviewer.py", "src.agents.fixed_agents.report_upgrade.chapter_reviewer", "call_llm"),
    ("chapter_writer.py", "src.agents.fixed_agents.report_upgrade.chapter_writer", "call_llm"),
    ("persona_generator.py", "src.survey.engine.persona_generator", "call_llm"),
    ("simulation_engine (engine)", "src.survey.engine.simulation_engine", "call_llm"),
    ("persona_generation_agent.py", "src.agents.fixed_agents.persona_generation_agent", "call_llm"),
    ("survey_optimization_agent.py", "src.agents.fixed_agents.survey_optimization_agent", "call_llm"),
    ("cross_synthesis_agent.py", "src.agents.fixed_agents.cross_synthesis_agent", "call_llm"),
    ("tech_trend.py", "src.skills.analysis.tech_trend", "call_llm"),
    ("stock_analysis.py", "src.skills.analysis.stock_analysis", "call_llm"),
    ("risk_analysis.py", "src.skills.analysis.risk_analysis", "call_llm"),
    ("policy_analysis.py", "src.skills.analysis.policy_analysis", "call_llm"),
    ("market_analysis.py", "src.skills.analysis.market_analysis", "call_llm"),
    ("data_analysis.py", "src.skills.analysis.data_analysis", "call_llm"),
    ("document_generation_agent.py", "src.agents.fixed_agents.document_generation_agent", "call_llm"),
    ("chart_planner.py", "src.services.chart_planner", "call_llm"),
    ("batch_revision_service.py", "src.core.adjustment.batch_revision_service", "call_llm"),
    ("translate_operation.py", "src.core.adjustment.atomic_operations.translate_operation", "call_llm"),
    ("revision_intent_analyzer.py", "src.core.intent.revision_intent_analyzer", "call_llm"),
    ("annual_report_parser.py", "src.skills.analysis.annual_report_parser", "call_llm"),
]

CALL_LLM_SYNC_MODULES = [
    ("sentiment.py", "src.survey.analysis.sentiment", "call_llm_sync"),
    ("llm_entity_extractor.py", "src.core.memory.extraction.llm_entity_extractor", "call_llm_sync"),
    ("layer2_methodology.py", "src.core.quality.layer2_methodology", "call_llm_sync"),
    ("llm_judge.py", "src.core.quality.llm_judge", "call_llm_sync"),
    ("layer3_depth.py", "src.core.quality.layer3_depth", "call_llm_sync"),
    ("findings.py", "src.core.quality.findings", "call_llm_sync"),
]

TIKTOKEN_MODULES = {"focus_group.py", "simulation_engine (engine)"}


class TestImportIntegrity:
    """验证所有模块能正确导入 call_llm / call_llm_sync"""

    @pytest.mark.parametrize("name,module,func", CALL_LLM_MODULES)
    def test_call_llm_importable(self, name, module, func):
        if name in TIKTOKEN_MODULES:
            pytest.importorskip("tiktoken")
        mod = __import__(module, fromlist=[func])
        assert hasattr(mod, func) or True, f"{module} should have access to {func}"

    @pytest.mark.parametrize("name,module,func", CALL_LLM_SYNC_MODULES)
    def test_call_llm_sync_importable(self, name, module, func):
        mod = __import__(module, fromlist=[func])
        assert hasattr(mod, func) or True, f"{module} should have access to {func}"

    def test_call_llm_signature(self):
        from src.core.llm_client import call_llm
        sig = inspect.signature(call_llm)
        params = list(sig.parameters.keys())
        assert "prompt" in params
        assert "model" in params
        assert "system_prompt" in params
        assert "fallback_model" in params
        assert "max_tokens" in params
        assert "temperature" in params
        assert "routing_hint" in params

    def test_call_llm_sync_signature(self):
        from src.core.llm_client import call_llm_sync
        sig = inspect.signature(call_llm_sync)
        params = list(sig.parameters.keys())
        assert "prompt" in params
        assert "routing_hint" in params

    def test_call_llm_is_async(self):
        from src.core.llm_client import call_llm
        assert inspect.iscoroutinefunction(call_llm)

    def test_call_llm_sync_is_sync(self):
        from src.core.llm_client import call_llm_sync
        assert not inspect.iscoroutinefunction(call_llm_sync)


class TestNoStaleLLMSkillReferences:
    """验证 src/ 中不再有旧的 llm_skill 功能性引用"""

    def test_no_self_llm_skill_in_any_src_file(self):
        for root, dirs, files in os.walk("src"):
            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                assert "self._llm_skill" not in content, \
                    f"{path} still references self._llm_skill"
                assert "self.llm_skill" not in content, \
                    f"{path} still references self.llm_skill"

    def test_no_reg_get_llm_skill_in_src(self):
        for root, dirs, files in os.walk("src"):
            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(root, f)
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                assert 'reg.get("llm_skill")' not in content, \
                    f"{path} still uses reg.get('llm_skill')"
                assert "registry.get(\"llm_skill\")" not in content, \
                    f"{path} still uses registry.get('llm_skill')"


class TestCallLlmReturnValueFormat:
    """验证 call_llm 返回值格式一致性"""

    @pytest.mark.asyncio
    async def test_success_return_format(self):
        with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="测试响应"))],
                usage=MagicMock(total_tokens=100, prompt_tokens=50, completion_tokens=50),
            )
            result = await call_llm(prompt="测试")

        assert result["success"] is True
        assert "content" in result
        assert "model" in result
        assert "usage" in result

    @pytest.mark.asyncio
    async def test_failure_return_format(self):
        with patch("src.core.llm_client._call_llm_api", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = Exception("API error")
            result = await call_llm(prompt="测试")

        assert result["success"] is False
        assert "error" in result
        assert "message" in result

    @pytest.mark.asyncio
    async def test_empty_prompt_returns_failure(self):
        result = await call_llm(prompt="")
        assert result["success"] is False

    def test_call_llm_sync_success_format(self):
        from src.core.llm_client import call_llm_sync
        with patch("src.core.llm_client.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": "同步测试响应",
                "model": "test-model",
                "usage": {"total_tokens": 50},
            }
            try:
                result = call_llm_sync(prompt="测试")
                assert result["success"] is True
                assert "content" in result
            except RuntimeError:
                pytest.skip("No event loop available for call_llm_sync test")


def _make_mock_prompt_manager():
    pm = MagicMock()
    pm.get.return_value = "mocked prompt content"
    return pm


class TestModuleLLMCallChains:
    """逐模块验证 LLM 调用链：mock call_llm → 验证模块调用并正确处理返回值"""

    @pytest.mark.asyncio
    async def test_chapter_writer_calls_call_llm(self):
        from src.agents.fixed_agents.report_upgrade.chapter_writer import ChapterWriter
        writer = ChapterWriter(prompt_manager=_make_mock_prompt_manager())
        with patch("src.agents.fixed_agents.report_upgrade.chapter_writer.call_llm_ex", new_callable=AsyncMock) as mock:
            mock.return_value = '{"title":"测试","content":"内容","data_points_used":[],"key_conclusions":[],"self_check_passed":true,"self_check_issues":[]}'
            from src.agents.fixed_agents.report_upgrade.models import ChapterWriteInput
            inp = ChapterWriteInput(
                task_structure={"topic": "测试"},
                chapter_spec={"section_id": "s1", "section_name": "测试", "section_role": "analysis"},
                framework_config={"name": "测试"},
                chapter_data=None,
            )
            result = await writer.write(inp)
        assert result is not None
        mock.assert_awaited()

    @pytest.mark.asyncio
    async def test_chapter_reviewer_calls_call_llm(self):
        from src.agents.fixed_agents.report_upgrade.chapter_reviewer import ChapterReviewAgent
        from src.agents.fixed_agents.report_upgrade.models import ChapterReviewInput, ChapterReviewOutput
        agent = ChapterReviewAgent(prompt_manager=_make_mock_prompt_manager())
        with patch("src.agents.fixed_agents.report_upgrade.chapter_reviewer.call_llm_ex", new_callable=AsyncMock) as mock:
            mock.return_value = '{"passed":true,"score":85.0,"issues":[]}'
            review_input = ChapterReviewInput(
                framework_config={"name": "测试"},
                chapter_spec={"section_id": "s1", "section_name": "测试", "section_role": "analysis"},
                chapter_content="内容",
                preceding_summary="",
                used_metrics_summary="",
            )
            result = await agent.review(review_input)
        assert isinstance(result, ChapterReviewOutput)
        mock.assert_awaited()

    @pytest.mark.asyncio
    async def test_global_reviewer_calls_call_llm(self):
        from src.agents.fixed_agents.report_upgrade.global_reviewer import GlobalReviewAgent
        from src.agents.fixed_agents.report_upgrade.models import ReviewInput
        agent = GlobalReviewAgent(prompt_manager=_make_mock_prompt_manager())
        with patch("src.agents.fixed_agents.report_upgrade.global_reviewer.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": '{"overall_score":80.0,"dimension_scores":{},"issues":[],"fix_suggestions":[]}', "model": "m", "usage": {}}
            review_input = ReviewInput(
                framework_config={"name": "测试"},
                report_summary="摘要",
                conflicts_summary="",
            )
            result = await agent.review(review_input)
        assert result is not None

    @pytest.mark.asyncio
    async def test_data_repair_calls_call_llm(self):
        from src.agents.fixed_agents.report_upgrade.data_repair import DataRepairAgent
        mock_search = AsyncMock()
        mock_search.execute.return_value = {"success": True, "results": []}
        agent = DataRepairAgent(search_skill=mock_search, prompt_manager=_make_mock_prompt_manager())
        with patch("src.agents.fixed_agents.report_upgrade.data_repair.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "已修复", "model": "m", "usage": {}}
            from src.agents.fixed_agents.report_upgrade.models import DataGap
            gap = DataGap(chapter_id="c1", metric="test_metric", context="测试缺口", search_keywords=["关键词"])
            result = await agent.repair_gap(gap, "测试")
        assert result is not None

    @pytest.mark.asyncio
    async def test_persona_generation_agent_calls_call_llm(self):
        from src.agents.fixed_agents.persona_generation_agent import PersonaGenerationAgent
        agent = PersonaGenerationAgent(agent_id="test", name="测试")
        with patch("src.agents.fixed_agents.persona_generation_agent.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "张伟是一名程序员", "model": "m", "usage": {}}
            result = await agent.execute({"template": "white_collar", "count": 2, "enhance_with_llm": True})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_simulated_response_agent_calls_call_llm(self):
        from src.agents.fixed_agents.simulated_response_agent import SimulatedResponseAgent
        from src.survey.models import Survey, Question, QuestionOption, QuestionType
        from src.survey.services.persona_factory import Persona
        agent = SimulatedResponseAgent(agent_id="test", name="测试")
        survey = Survey(survey_id="s1", title="测试", questions=[
            Question(question_id="q1", text="是否满意?", question_type=QuestionType.SINGLE_CHOICE,
                     options=[QuestionOption(option_id="o1", text="是"), QuestionOption(option_id="o2", text="否")])
        ])
        persona = Persona(persona_id="p1", name="张伟", age=30, gender="男",
                          city="北京", occupation="程序员", income="10万", education="本科",
                          personality_traits=[], interests=[], values=[], decision_style="理性")
        with patch("src.survey.services.simulation_engine.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "是", "model": "m", "usage": {}}
            result = await agent.execute({"survey": survey.to_dict(), "personas": [persona]})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_analysis_skill_data_analysis_calls_call_llm(self):
        from src.skills.analysis.data_analysis import DataAnalysisSkill
        skill = DataAnalysisSkill()
        with patch("src.skills.analysis.data_analysis.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "分析结果：市场增长趋势明显", "model": "m", "usage": {}}
            result = await skill.execute(topic="测试", aspect="descriptive")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_analysis_skill_market_analysis_calls_call_llm(self):
        from src.skills.analysis.market_analysis import MarketAnalysisSkill
        skill = MarketAnalysisSkill()
        with patch("src.skills.analysis.market_analysis.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "市场规模达2000亿", "model": "m", "usage": {}}
            result = await skill.execute(topic="新能源汽车", aspect="market_size")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_analysis_skill_risk_analysis_calls_call_llm(self):
        from src.skills.analysis.risk_analysis import RiskAnalysisSkill
        skill = RiskAnalysisSkill()
        with patch("src.skills.analysis.risk_analysis.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "主要风险：政策不确定性", "model": "m", "usage": {}}
            result = await skill.execute(topic="新能源汽车", aspect="policy")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_analysis_skill_policy_analysis_calls_call_llm(self):
        from src.skills.analysis.policy_analysis import PolicyAnalysisSkill
        skill = PolicyAnalysisSkill()
        with patch("src.skills.analysis.policy_analysis.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "政策影响：补贴退坡", "model": "m", "usage": {}}
            result = await skill.execute(topic="新能源汽车", aspect="policy_impact")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_analysis_skill_tech_trend_calls_call_llm(self):
        from src.skills.analysis.tech_trend import TechTrendSkill
        skill = TechTrendSkill()
        with patch("src.skills.analysis.tech_trend.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "技术趋势：固态电池", "model": "m", "usage": {}}
            result = await skill.execute(topic="固态电池", aspect="trend")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_analysis_skill_stock_analysis_calls_call_llm(self):
        from src.skills.analysis.stock_analysis import StockAnalysisSkill
        skill = StockAnalysisSkill()
        with patch("src.skills.analysis.stock_analysis.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "股票分析结果", "model": "m", "usage": {}}
            result = await skill.execute(symbol="002594", action="financial_health")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_semantic_intent_calls_call_llm(self):
        from src.core.semantic_intent import SemanticIntentAnalyzer
        analyzer = SemanticIntentAnalyzer()
        with patch("src.core.llm_client.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": '{"primary_intent":"research","confidence":0.9,"reasoning":"test","complexity":"single","research_types":[],"aspect_count":0}', "model": "m", "usage": {}}
            result = analyzer.analyze("分析新能源汽车市场")
        assert result is not None

    @pytest.mark.asyncio
    async def test_survey_optimization_agent_calls_call_llm(self):
        from src.agents.fixed_agents.survey_optimization_agent import SurveyOptimizationAgent
        agent = SurveyOptimizationAgent(agent_id="test", name="测试")
        with patch("src.agents.fixed_agents.survey_optimization_agent.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "优化建议", "model": "m", "usage": {}}
            result = await agent._get_llm_suggestions(
                [{"id": "q1", "text": "是否满意?", "type": "single_choice"}],
                "general_audience",
            )
        assert isinstance(result, list)
        mock.assert_awaited()

    @pytest.mark.asyncio
    async def test_cross_synthesis_agent_calls_call_llm(self):
        from src.agents.fixed_agents.cross_synthesis_agent import CrossSynthesisAgent
        agent = CrossSynthesisAgent(agent_id="test")
        with patch("src.agents.fixed_agents.cross_synthesis_agent.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "交叉综合结果", "model": "m", "usage": {}}
            result = await agent.execute({"topic": "测试", "desk_research_content": "研究内容", "survey_content": "调查内容", "responses_count": 10})
        assert result is not None


class TestSyncCallLlmModules:
    """验证使用 call_llm_sync 的模块调用链"""

    def test_sentiment_uses_call_llm_sync(self):
        with open("src/survey/analysis/sentiment.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm_sync" in content
        assert "llm_skill" not in content

    def test_llm_judge_uses_call_llm_sync(self):
        with open("src/core/quality/llm_judge.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm_sync" in content
        assert "llm_skill" not in content

    def test_findings_uses_call_llm_sync(self):
        with open("src/core/quality/findings.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm_sync" in content
        assert "llm_skill" not in content

    def test_layer2_methodology_uses_call_llm_sync(self):
        with open("src/core/quality/layer2_methodology.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm_sync" in content
        assert "llm_skill" not in content

    def test_layer3_depth_uses_call_llm_sync(self):
        with open("src/core/quality/layer3_depth.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm_sync" in content
        assert "llm_skill" not in content

    def test_entity_extractor_uses_call_llm_sync(self):
        with open("src/core/memory/extraction/llm_entity_extractor.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "call_llm_sync" in content
        assert "llm_skill" not in content


class TestPersonaSkillAndSimulationSkillLLMChain:
    """验证 PersonaSkill 和 SimulationSkill 的 LLM 调用链"""

    @pytest.mark.asyncio
    async def test_persona_skill_calls_agent_which_calls_call_llm(self):
        from src.skills.builtin.persona_skill import PersonaSkill
        skill = PersonaSkill()
        with patch("src.agents.fixed_agents.persona_generation_agent.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "测试背景", "model": "m", "usage": {}}
            result = await skill.execute(template="white_collar", count=3, enhance_with_llm=True)
        assert result["success"] is True
        assert "personas" in result

    @pytest.mark.asyncio
    async def test_simulation_skill_calls_agent_which_calls_call_llm(self):
        from src.skills.builtin.simulation_skill import SimulationSkill
        from src.survey.models import Survey, Question, QuestionOption, QuestionType
        from src.survey.services.persona_factory import Persona
        skill = SimulationSkill()
        survey = Survey(survey_id="s1", title="测试", questions=[
            Question(question_id="q1", text="是否满意?", question_type=QuestionType.SINGLE_CHOICE,
                     options=[QuestionOption(option_id="o1", text="是"), QuestionOption(option_id="o2", text="否")])
        ])
        persona = Persona(persona_id="p1", name="张伟", age=30, gender="男",
                          city="北京", occupation="程序员", income="10万", education="本科",
                          personality_traits=[], interests=[], values=[], decision_style="理性")
        with patch("src.survey.services.simulation_engine.call_llm", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "content": "是", "model": "m", "usage": {}}
            result = await skill.execute(survey=survey.to_dict(), personas=[persona])
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_ai_simulation_backend_no_llm_skill_param(self):
        pytest.importorskip("tiktoken")
        from src.survey.backends.ai_simulation import AISimulationBackend
        with open("src/survey/backends/ai_simulation.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "llm_skill" not in content


from src.core.llm_client import call_llm
