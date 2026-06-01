"""
Week 4 Day 4: 最终验收测试
========================

Phase 3 完整验收测试，验证所有功能正确集成。

验收标准:
1. 完整工作流测试
2. 性能基准测试
3. 质量校验测试
4. 结果校准测试
5. 端到端测试
"""

import pytest
import asyncio
import time
from typing import Dict, Any, List
from datetime import datetime

from src.survey.models import (
    Survey, Question, QuestionOption, QuestionType,
    SurveyResponse, Answer, QuotaConfig, DistributionConfig
)
from src.survey.services.simulation_engine import SimulationEngine
from src.survey.services.persona_factory import PersonaFactory
from src.survey.services.response_quality_validator import (
    ResponseQualityValidator,
    QualityReport
)
from src.survey.services.performance_optimizer import PerformanceOptimizer
from src.agents.fixed_agents.result_calibration_agent import ResultCalibrationAgent
from src.agents.fixed_agents.survey_optimization_agent import SurveyOptimizationAgent
from src.agents.fixed_agents.survey_analysis_agent import SurveyAnalysisAgent
from src.agents.fixed_agents.survey_integration_agent import SurveyIntegrationAgent


class TestPhase3Acceptance:
    """Phase 3 验收测试"""
    
    @pytest.fixture
    def complex_survey(self) -> Survey:
        """创建复杂问卷"""
        return Survey(
            survey_id="acceptance_survey",
            title="用户满意度调研",
            questions=[
                Question(
                    question_id="q1",
                    text="您对我们的产品整体满意度如何？",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "非常满意"),
                        QuestionOption("opt2", "满意"),
                        QuestionOption("opt3", "一般"),
                        QuestionOption("opt4", "不满意"),
                        QuestionOption("opt5", "非常不满意"),
                    ],
                    required=True
                ),
                Question(
                    question_id="q2",
                    text="您使用我们产品的频率是？",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "每天"),
                        QuestionOption("opt2", "每周几次"),
                        QuestionOption("opt3", "每月几次"),
                        QuestionOption("opt4", "很少使用"),
                    ],
                    required=True
                ),
                Question(
                    question_id="q3",
                    text="您最常使用哪些功能？（可多选）",
                    question_type=QuestionType.MULTIPLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "功能A"),
                        QuestionOption("opt2", "功能B"),
                        QuestionOption("opt3", "功能C"),
                        QuestionOption("opt4", "功能D"),
                    ],
                    required=True
                ),
                Question(
                    question_id="q4",
                    text="您是否愿意推荐我们的产品？",
                    question_type=QuestionType.LIKERT,
                    options=[
                        QuestionOption("opt1", "1分-绝不推荐"),
                        QuestionOption("opt2", "2分"),
                        QuestionOption("opt3", "3分"),
                        QuestionOption("opt4", "4分"),
                        QuestionOption("opt5", "5分-强烈推荐"),
                    ],
                    required=True
                ),
                Question(
                    question_id="q5",
                    text="您有什么建议或意见？",
                    question_type=QuestionType.OPEN_ENDED,
                    required=False
                ),
            ]
        )
    
    @pytest.mark.asyncio
    async def test_full_simulation_workflow(self, complex_survey):
        """测试完整模拟工作流"""
        # 1. 生成画像
        factory = PersonaFactory()
        personas = factory.generate_population("一线白领", 50)
        
        assert len(personas) == 50
        for persona in personas:
            assert persona.age >= 25
            assert persona.age <= 40
            assert persona.occupation is not None
        
        # 2. 模拟回答
        engine = SimulationEngine()
        responses = await engine.simulate_survey(personas, complex_survey)
        
        assert len(responses) == 50
        for response in responses:
            assert len(response.answers) == 5  # 5个问题
            # duration_seconds may be 0 for simulated responses
            assert response.duration_seconds >= 0
    
    @pytest.mark.asyncio
    async def test_quality_validation_workflow(self, complex_survey):
        """测试质量校验工作流"""
        # 生成回答
        factory = PersonaFactory()
        personas = factory.generate_population("一线白领", 30)
        
        engine = SimulationEngine()
        responses = await engine.simulate_survey(personas, complex_survey)
        
        # 质量校验
        validator = ResponseQualityValidator()
        reports = validator.validate_batch(responses, complex_survey)
        
        assert len(reports) == 30
        
        # 统计质量
        stats = validator.get_quality_statistics(reports)
        
        assert stats["total_count"] == 30
        assert stats["valid_count"] + stats["invalid_count"] == 30
        assert stats["avg_quality_score"] > 0
    
    @pytest.mark.asyncio
    async def test_calibration_workflow(self, complex_survey):
        """测试校准工作流"""
        # 生成回答
        factory = PersonaFactory()
        personas = factory.generate_population("一线白领", 40)
        
        engine = SimulationEngine()
        responses = await engine.simulate_survey(personas, complex_survey)
        
        # 添加demographics
        for i, response in enumerate(responses):
            if response.demographics is None:
                response.demographics = {"age": personas[i].age}
        
        # 校准
        calibration_agent = ResultCalibrationAgent()
        target_dist = {"age": {"25-30": 0.4, "31-35": 0.4, "36-40": 0.2}}
        
        result = calibration_agent.execute({
            "responses": responses,
            "survey": complex_survey,
            "target_distribution": target_dist,
            "calibration_dimension": "age"
        })
        
        assert result["success"] is True
        assert len(result["calibrated_responses"]) == 40
        assert "calibration_report" in result
    
    @pytest.mark.asyncio
    async def test_analysis_workflow(self, complex_survey):
        """测试分析工作流"""
        # 生成回答
        factory = PersonaFactory()
        personas = factory.generate_population("一线白领", 25)
        
        engine = SimulationEngine()
        responses = await engine.simulate_survey(personas, complex_survey)
        
        # 分析
        analysis_agent = SurveyAnalysisAgent(
            agent_id="test_analysis",
            name="测试分析Agent"
        )
        
        # 准备分析输入 - 使用正确的字段名
        questions = [
            {
                "question_id": q.question_id,
                "text": q.text,
                "question_type": q.question_type.value,
                "options": [{"option_id": o.option_id, "text": o.text} for o in q.options] if q.options else []
            }
            for q in complex_survey.questions
        ]
        
        analysis_input = {
            "questions": questions,
            "responses": [
                {
                    "response_id": r.response_id,
                    "answers": {
                        qid: ans.answer_value for qid, ans in r.answers.items()
                    }
                }
                for r in responses
            ]
        }
        
        result = analysis_agent.execute(analysis_input)
        
        assert result["success"] is True
        assert "statistics" in result
        assert "report" in result


class TestPerformanceBenchmarks:
    """性能基准测试"""
    
    @pytest.mark.asyncio
    async def test_simulation_performance(self):
        """测试模拟性能"""
        survey = Survey(
            survey_id="perf_survey",
            title="性能测试",
            questions=[
                Question(
                    question_id=f"q{i}",
                    text=f"问题{i}",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "选项1"),
                        QuestionOption("opt2", "选项2"),
                    ],
                    required=True
                )
                for i in range(10)
            ]
        )
        
        factory = PersonaFactory()
        personas = factory.generate_population("一线白领", 100)
        
        optimizer = PerformanceOptimizer()
        
        start_time = time.time()
        result = await optimizer.optimize_simulation(personas, survey)
        elapsed = time.time() - start_time
        
        # 性能要求：100人×10题 < 30秒
        assert elapsed < 30, f"模拟耗时{elapsed:.2f}秒，超过30秒限制"
        assert len(result["responses"]) == 100
    
    @pytest.mark.asyncio
    async def test_validation_performance(self):
        """测试校验性能"""
        # 创建简单问卷和回答
        survey = Survey(
            survey_id="val_perf_survey",
            title="校验性能测试",
            questions=[
                Question(
                    question_id="q1",
                    text="问题1",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[QuestionOption("opt1", "选项1")],
                    required=True
                )
            ]
        )
        
        responses = [
            SurveyResponse(
                response_id=f"resp_{i}",
                survey_id="val_perf_survey",
                answers={"q1": Answer("q1", "opt1")},
                duration_seconds=60
            )
            for i in range(500)
        ]
        
        validator = ResponseQualityValidator()
        
        start_time = time.time()
        reports = validator.validate_batch(responses, survey)
        elapsed = time.time() - start_time
        
        # 性能要求：500个回答校验 < 5秒
        assert elapsed < 5, f"校验耗时{elapsed:.2f}秒，超过5秒限制"
        assert len(reports) == 500


class TestIntegrationAgents:
    """Agent集成测试"""
    
    def test_survey_optimization_agent(self):
        """测试问卷优化Agent"""
        agent = SurveyOptimizationAgent(
            agent_id="test_opt",
            name="测试优化Agent"
        )
        
        questions = [
            {
                "question_id": "q1",
                "text": "问题1",
                "question_type": "single_choice",
                "options": ["选项1", "选项2"]
            }
        ]
        
        result = agent.execute({
            "questions": questions,
            "optimization_goals": ["clarity", "completeness"]
        })
        
        assert result["success"] is True
    
    def test_survey_analysis_agent(self):
        """测试问卷分析Agent"""
        agent = SurveyAnalysisAgent(
            agent_id="test_analysis",
            name="测试分析Agent"
        )
        
        # 使用正确的字段名
        questions = [
            {
                "question_id": "q1",
                "text": "问题1",
                "question_type": "single_choice",
                "options": [{"option_id": "opt1", "text": "选项1"}]
            }
        ]
        
        responses = [
            {
                "response_id": f"resp_{i}",
                "answers": {"q1": "opt1"}
            }
            for i in range(10)
        ]
        
        result = agent.execute({
            "questions": questions,
            "responses": responses
        })
        
        assert result["success"] is True
    
    def test_survey_integration_agent(self):
        """测试问卷集成Agent"""
        agent = SurveyIntegrationAgent(
            agent_id="test_integration",
            name="测试集成Agent"
        )
        
        survey_config = {
            "title": "测试问卷",
            "questions": [
                {
                    "question_id": "q1",
                    "text": "问题1",
                    "question_type": "single_choice",
                    "options": [
                        {"option_id": "opt1", "text": "选项1"},
                        {"option_id": "opt2", "text": "选项2"}
                    ]
                }
            ]
        }
        
        result = agent.execute({
            "workflow": "quick_survey",  # 使用 workflow 而不是 action
            "survey_config": survey_config,
            "title": "测试问卷",
            "questions": survey_config["questions"],
            "target_count": 10
        })
        
        assert result["success"] is True


class TestPhase3FinalAcceptance:
    """Phase 3 最终验收"""
    
    @pytest.mark.asyncio
    async def test_complete_survey_pipeline(self):
        """测试完整调研管道"""
        # 1. 创建问卷
        survey = Survey(
            survey_id="final_acceptance",
            title="最终验收测试问卷",
            questions=[
                Question(
                    question_id="q1",
                    text="满意度",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "满意"),
                        QuestionOption("opt2", "不满意"),
                    ],
                    required=True
                ),
            ]
        )
        
        # 2. 生成画像
        factory = PersonaFactory()
        personas = factory.generate_population("一线白领", 50)
        
        # 3. 模拟回答
        optimizer = PerformanceOptimizer()
        sim_result = await optimizer.optimize_simulation(personas, survey)
        responses = sim_result["responses"]
        
        # 添加demographics
        for i, response in enumerate(responses):
            if response.demographics is None:
                response.demographics = {"age": personas[i].age}
        
        # 4. 质量校验
        validator = ResponseQualityValidator()
        reports = validator.validate_batch(responses, survey)
        
        # 5. 筛选有效回答
        valid_responses, invalid_responses = validator.filter_valid_responses(
            responses, survey
        )
        
        # 6. 结果校准
        calibration_agent = ResultCalibrationAgent()
        calibration_result = calibration_agent.execute({
            "responses": valid_responses,
            "survey": survey,
            "target_distribution": {"age": {"25-30": 0.5, "31-40": 0.5}},
            "calibration_dimension": "age"
        })
        
        # 7. 生成分析报告
        # 准备分析输入
        questions = [
            {
                "question_id": q.question_id,
                "text": q.text,
                "question_type": q.question_type.value,
                "options": [{"option_id": o.option_id, "text": o.text} for o in q.options] if q.options else []
            }
            for q in survey.questions
        ]
        
        analysis_responses = [
            {
                "response_id": r.response_id,
                "answers": {
                    qid: ans.answer_value for qid, ans in r.answers.items()
                }
            }
            for r in calibration_result["calibrated_responses"]
        ]
        
        analysis_agent = SurveyAnalysisAgent(
            agent_id="final_analysis",
            name="最终分析Agent"
        )
        
        analysis_result = analysis_agent.execute({
            "questions": questions,
            "responses": analysis_responses
        })
        
        # 验收检查
        assert len(responses) == 50
        assert len(valid_responses) >= 40  # 至少80%有效
        assert calibration_result["success"] is True
        assert analysis_result["success"] is True
        
        # 性能检查
        assert sim_result["performance_report"].throughput > 0
    
    def test_all_agents_registered(self):
        """测试所有Agent已注册"""
        from src.agents.fixed_agents import __all__ as fixed_agents_all
        
        expected_agents = [
            "SurveyOptimizationAgent",
            "SurveyAnalysisAgent",
            "SurveyIntegrationAgent",
            "ResultCalibrationAgent",
        ]
        
        for agent_name in expected_agents:
            assert agent_name in fixed_agents_all, f"Agent {agent_name} 未注册"
    
    def test_all_services_available(self):
        """测试所有服务可用"""
        from src.survey.services import __all__ as services_all
        
        expected_services = [
            "PersonaFactory",
            "SimulationEngine",
        ]
        
        for service_name in expected_services:
            assert service_name in services_all, f"服务 {service_name} 不可用"


class TestPhase3Summary:
    """Phase 3 总结"""
    
    def test_phase3_completion_criteria(self):
        """测试Phase 3 完成标准"""
        # 检查所有组件是否存在
        components = {
            "Week 1 - 基础框架": [
                "src.survey.models",
                "src.survey.backends.base",
                "src.survey.backends.factory",
                "src.survey.backends.mock_backend",
            ],
            "Week 2 - AI模拟": [
                "src.survey.services.simulation_engine",
                "src.agents.fixed_agents.simulated_response_agent",
                "src.agents.fixed_agents.persona_generation_agent",
            ],
            "Week 3 - 用户调研Agent": [
                "src.skills.builtin.survey_skill",
                "src.agents.fixed_agents.survey_optimization_agent",
                "src.agents.fixed_agents.survey_analysis_agent",
                "src.agents.fixed_agents.survey_integration_agent",
            ],
            "Week 4 - 高级功能": [
                "src.survey.services.response_quality_validator",
                "src.agents.fixed_agents.result_calibration_agent",
                "src.survey.services.performance_optimizer",
            ],
        }
        
        for week, modules in components.items():
            for module_path in modules:
                try:
                    __import__(module_path)
                except ImportError as e:
                    pytest.fail(f"{week}: 模块 {module_path} 导入失败 - {e}")
        
        # 如果所有模块都能导入，Phase 3 完成
        assert True, "Phase 3 所有组件验证通过"