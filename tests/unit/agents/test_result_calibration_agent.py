"""
Week 4 Day 2: 结果校准测试
========================

TDD测试用例，用于ResultCalibrationAgent。

测试覆盖:
1. 初始化测试
2. 分布校准
3. 权重校准
4. 人口统计校准
5. 统计显著性检验
6. 校准报告生成
"""

import pytest
from datetime import datetime
from typing import Dict, Any, List
import statistics

from src.survey.models import (
    Survey, Question, QuestionOption, QuestionType,
    SurveyResponse, Answer, QuotaConfig, DistributionConfig
)
from src.agents.fixed_agents.result_calibration_agent import (
    ResultCalibrationAgent,
    CalibrationMethod,
    CalibrationConfig,
    CalibrationReport
)


class TestCalibrationMethod:
    """校准方法测试"""
    
    def test_method_enum_values(self):
        """测试校准方法枚举"""
        assert CalibrationMethod.WEIGHTING.value == "weighting"
        assert CalibrationMethod.RATIO_ADJUSTMENT.value == "ratio_adjustment"
        assert CalibrationMethod.STRATIFICATION.value == "stratification"
        assert CalibrationMethod.RAKING.value == "raking"


class TestCalibrationConfig:
    """校准配置测试"""
    
    def test_config_creation(self):
        """测试校准配置创建"""
        config = CalibrationConfig(
            method=CalibrationMethod.WEIGHTING,
            target_distribution={"age": {"18-30": 0.3, "31-50": 0.5, "51+": 0.2}},
            confidence_level=0.95,
            min_sample_size=30
        )
        
        assert config.method == CalibrationMethod.WEIGHTING
        assert config.confidence_level == 0.95
        assert config.min_sample_size == 30
    
    def test_config_defaults(self):
        """测试默认配置"""
        config = CalibrationConfig()
        
        assert config.method == CalibrationMethod.WEIGHTING
        assert config.confidence_level == 0.95
        assert config.min_sample_size == 30
        assert config.apply_quality_weights is True
    
    def test_config_to_dict(self):
        """测试配置转换为字典"""
        config = CalibrationConfig(
            method=CalibrationMethod.RAKING,
            confidence_level=0.90
        )
        
        result = config.to_dict()
        
        assert result["method"] == "raking"
        assert result["confidence_level"] == 0.90
    
    def test_config_from_dict(self):
        """测试从字典创建配置"""
        data = {
            "method": "stratification",
            "confidence_level": 0.99,
            "min_sample_size": 50
        }
        
        config = CalibrationConfig.from_dict(data)
        
        assert config.method == CalibrationMethod.STRATIFICATION
        assert config.confidence_level == 0.99


class TestCalibrationReport:
    """校准报告测试"""
    
    def test_report_creation(self):
        """测试校准报告创建"""
        report = CalibrationReport(
            original_count=100,
            calibrated_count=100,
            calibration_weights={},
            distribution_changes={},
            confidence_intervals={},
            recommendations=[]
        )
        
        assert report.original_count == 100
        assert report.calibrated_count == 100
    
    def test_report_to_dict(self):
        """测试报告转换为字典"""
        report = CalibrationReport(
            original_count=50,
            calibrated_count=50,
            calibration_weights={"resp_001": 1.2},
            distribution_changes={"age": {"before": 0.4, "after": 0.3}},
            confidence_intervals={"q1": {"lower": 0.25, "upper": 0.35}},
            recommendations=["建议增加样本量"]
        )
        
        result = report.to_dict()
        
        assert result["original_count"] == 50
        assert result["calibrated_weights"]["resp_001"] == 1.2


class TestResultCalibrationAgent:
    """结果校准Agent测试"""
    
    def test_agent_initialization(self):
        """测试Agent初始化"""
        agent = ResultCalibrationAgent(
            agent_id="calibration_001",
            name="结果校准Agent"
        )
        
        assert agent.agent_id == "calibration_001"
        assert agent.name == "结果校准Agent"
        assert agent.agent_type == "fixed"
    
    def test_agent_has_capabilities(self):
        """测试Agent能力清单"""
        agent = ResultCalibrationAgent(
            agent_id="calibration_002",
            name="结果校准Agent"
        )
        
        capabilities = agent.get_capabilities()
        
        assert len(capabilities) > 0
        assert "分布校准" in capabilities or "distribution_calibration" in capabilities
    
    def test_validate_input(self):
        """测试输入验证"""
        agent = ResultCalibrationAgent(
            agent_id="calibration_003",
            name="结果校准Agent"
        )
        
        # 有效输入
        valid_input = {
            "responses": [],
            "survey": None,
            "target_distribution": {}
        }
        is_valid, error = agent.validate_input(valid_input)
        assert is_valid is True
        
        # 无效输入 - 缺少responses
        invalid_input = {"survey": None}
        is_valid, error = agent.validate_input(invalid_input)
        assert is_valid is False
        assert "responses" in error
    
    def test_calculate_distribution(self):
        """测试分布计算"""
        agent = ResultCalibrationAgent(
            agent_id="calibration_004",
            name="结果校准Agent"
        )
        
        responses = [
            SurveyResponse(
                response_id="resp_001",
                survey_id="survey_001",
                answers={"q1": Answer("q1", "opt1")},
                demographics={"age": "18-30"}
            ),
            SurveyResponse(
                response_id="resp_002",
                survey_id="survey_001",
                answers={"q1": Answer("q1", "opt2")},
                demographics={"age": "31-50"}
            ),
            SurveyResponse(
                response_id="resp_003",
                survey_id="survey_001",
                answers={"q1": Answer("q1", "opt1")},
                demographics={"age": "18-30"}
            ),
        ]
        
        distribution = agent._calculate_distribution(responses, "age")
        
        assert "18-30" in distribution
        assert "31-50" in distribution
        assert distribution["18-30"] == 2/3
        assert distribution["31-50"] == 1/3
    
    def test_calculate_answer_distribution(self):
        """测试答案分布计算"""
        survey = self._create_test_survey()
        
        responses = [
            SurveyResponse(
                response_id="resp_001",
                survey_id="survey_001",
                answers={"q1": Answer("q1", "opt1")}
            ),
            SurveyResponse(
                response_id="resp_002",
                survey_id="survey_001",
                answers={"q1": Answer("q1", "opt2")}
            ),
            SurveyResponse(
                response_id="resp_003",
                survey_id="survey_001",
                answers={"q1": Answer("q1", "opt1")}
            ),
        ]
        
        agent = ResultCalibrationAgent(
            agent_id="calibration_005",
            name="结果校准Agent"
        )
        
        distribution = agent._calculate_answer_distribution(responses, survey, "q1")
        
        assert "opt1" in distribution
        assert "opt2" in distribution
        assert distribution["opt1"] == 2/3
        assert distribution["opt2"] == 1/3
    
    def test_calculate_calibration_weights(self):
        """测试校准权重计算"""
        agent = ResultCalibrationAgent(
            agent_id="calibration_006",
            name="结果校准Agent"
        )
        
        # 当前分布: 18-30: 80%, 31-50: 20%
        # 目标分布: 18-30: 30%, 31-50: 70%
        current_distribution = {"18-30": 0.8, "31-50": 0.2}
        target_distribution = {"18-30": 0.3, "31-50": 0.7}
        
        weights = agent._calculate_weights(current_distribution, target_distribution)
        
        # 18-30组的权重应该降低，31-50组的权重应该提高
        assert weights["18-30"] < 1.0
        assert weights["31-50"] > 1.0
    
    def test_apply_weights_to_responses(self):
        """测试权重应用到回答"""
        agent = ResultCalibrationAgent(
            agent_id="calibration_007",
            name="结果校准Agent"
        )
        
        responses = [
            SurveyResponse(
                response_id="resp_001",
                survey_id="survey_001",
                answers={"q1": Answer("q1", "opt1")},
                demographics={"age": "18-30"},
                quality_score=1.0
            ),
            SurveyResponse(
                response_id="resp_002",
                survey_id="survey_001",
                answers={"q1": Answer("q1", "opt2")},
                demographics={"age": "31-50"},
                quality_score=1.0
            ),
        ]
        
        weights = {"resp_001": 0.5, "resp_002": 1.5}
        
        weighted_responses = agent._apply_weights(responses, weights)
        
        # 检查权重是否被应用到 quality_score
        assert weighted_responses[0].quality_score == 0.5
        assert weighted_responses[1].quality_score == 1.5
    
    def test_calculate_confidence_interval(self):
        """测试置信区间计算"""
        agent = ResultCalibrationAgent(
            agent_id="calibration_008",
            name="结果校准Agent"
        )
        
        # 100个样本，比例0.5
        proportion = 0.5
        sample_size = 100
        confidence_level = 0.95
        
        ci = agent._calculate_confidence_interval(proportion, sample_size, confidence_level)
        
        assert "lower" in ci
        assert "upper" in ci
        assert ci["lower"] < proportion
        assert ci["upper"] > proportion
        # 95%置信区间大约是 ±10%
        assert ci["lower"] >= 0.35
        assert ci["upper"] <= 0.65
    
    def test_execute_calibration(self):
        """测试执行校准"""
        survey = self._create_test_survey()
        
        responses = [
            SurveyResponse(
                response_id=f"resp_{i}",
                survey_id="survey_001",
                answers={"q1": Answer("q1", "opt1" if i < 80 else "opt2")},
                demographics={"age": "18-30" if i < 80 else "31-50"}
            )
            for i in range(100)
        ]
        
        target_distribution = {
            "age": {"18-30": 0.3, "31-50": 0.7}
        }
        
        agent = ResultCalibrationAgent(
            agent_id="calibration_009",
            name="结果校准Agent"
        )
        
        result = agent.execute({
            "responses": responses,
            "survey": survey,
            "target_distribution": target_distribution,
            "calibration_dimension": "age"
        })
        
        assert result["success"] is True
        assert "calibration_report" in result
        assert "calibrated_responses" in result
        assert len(result["calibrated_responses"]) == 100
    
    def test_generate_recommendations(self):
        """测试生成建议"""
        agent = ResultCalibrationAgent(
            agent_id="calibration_010",
            name="结果校准Agent"
        )
        
        # 小样本
        recommendations = agent._generate_recommendations(
            sample_size=20,
            distribution_shift=0.1,
            avg_weight=0.7
        )
        
        assert len(recommendations) > 0
        assert any("样本量" in r or "sample" in r for r in recommendations)
    
    def test_empty_responses(self):
        """测试空回答列表"""
        survey = self._create_test_survey()
        
        agent = ResultCalibrationAgent(
            agent_id="calibration_011",
            name="结果校准Agent"
        )
        
        result = agent.execute({
            "responses": [],
            "survey": survey,
            "target_distribution": {}
        })
        
        assert result["success"] is False
        assert "error" in result
    
    # Helper methods
    
    def _create_test_survey(self) -> Survey:
        """创建测试问卷"""
        return Survey(
            survey_id="survey_001",
            title="测试问卷",
            questions=[
                Question(
                    question_id="q1",
                    text="问题1",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "选项1"),
                        QuestionOption("opt2", "选项2"),
                    ],
                    required=True
                ),
            ]
        )


class TestCalibrationIntegration:
    """校准集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_calibration_workflow(self):
        """测试完整校准工作流"""
        from src.survey.services.simulation_engine import SimulationEngine
        from src.survey.services.persona_factory import PersonaFactory
        
        # 创建问卷
        survey = Survey(
            survey_id="survey_integration",
            title="集成测试问卷",
            questions=[
                Question(
                    question_id="q1",
                    text="您的满意度如何？",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "非常满意"),
                        QuestionOption("opt2", "满意"),
                        QuestionOption("opt3", "一般"),
                        QuestionOption("opt4", "不满意"),
                    ],
                    required=True
                ),
            ]
        )
        
        # 生成画像和模拟回答
        factory = PersonaFactory()
        personas = factory.generate_population("一线白领", 30)
        
        engine = SimulationEngine()
        responses = await engine.simulate_survey(personas, survey)
        
        # 确保每个response都有demographics
        for i, response in enumerate(responses):
            if response.demographics is None:
                response.demographics = {"age": personas[i].age}
        
        # 执行校准
        target_distribution = {
            "age": {"18-30": 0.4, "31-50": 0.5, "51+": 0.1}
        }
        
        agent = ResultCalibrationAgent(
            agent_id="calibration_integration",
            name="结果校准Agent"
        )
        
        result = agent.execute({
            "responses": responses,
            "survey": survey,
            "target_distribution": target_distribution,
            "calibration_dimension": "age"
        })
        
        assert result["success"] is True
        assert "calibration_report" in result
        assert len(result["calibrated_responses"]) == 30
    
    def test_calibration_with_quality_validator(self):
        """测试校准与质量校验集成"""
        from src.survey.services.response_quality_validator import ResponseQualityValidator
        
        # 创建有效和无效回答
        survey = Survey(
            survey_id="survey_quality",
            title="质量测试问卷",
            questions=[
                Question(
                    question_id="q1",
                    text="问题1",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "选项1"),
                        QuestionOption("opt2", "选项2"),
                    ],
                    required=True
                ),
            ]
        )
        
        responses = [
            SurveyResponse(
                response_id="valid_001",
                survey_id="survey_quality",
                answers={"q1": Answer("q1", "opt1")},
                demographics={"age": "18-30"},
                duration_seconds=60,
                quality_score=0.9
            ),
            SurveyResponse(
                response_id="invalid_001",
                survey_id="survey_quality",
                answers={"q1": Answer("q1", "opt1")},
                demographics={"age": "18-30"},
                duration_seconds=5,
                quality_score=0.3
            ),
        ]
        
        # 先校验质量
        validator = ResponseQualityValidator()
        valid_responses, _ = validator.filter_valid_responses(responses, survey)
        
        # 再校准
        agent = ResultCalibrationAgent(
            agent_id="calibration_quality",
            name="结果校准Agent"
        )
        
        result = agent.execute({
            "responses": valid_responses,
            "survey": survey,
            "target_distribution": {"age": {"18-30": 0.5}},
            "calibration_dimension": "age"
        })
        
        assert result["success"] is True