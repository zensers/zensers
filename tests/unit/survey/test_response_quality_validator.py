"""
Week 4 Day 1: 回答质量校验测试
==============================

TDD测试用例，用于ResponseQualityValidator。

测试覆盖:
1. 初始化测试
2. 单个回答质量校验
3. 批量校验
4. 各种质量问题检测
5. 质量分数计算
6. 与Survey系统集成
"""

import pytest
from datetime import datetime
from typing import Dict, Any, List

from src.survey.models import (
    Survey, Question, QuestionOption, QuestionType,
    SurveyResponse, Answer
)
from src.survey.services.response_quality_validator import (
    ResponseQualityValidator,
    QualityIssue,
    QualityIssueType,
    QualityReport
)


class TestQualityIssueTypes:
    """质量问题类型测试"""
    
    def test_issue_type_enum_values(self):
        """测试质量问题类型枚举"""
        assert QualityIssueType.STRAIGHT_LINE.value == "straight_line"
        assert QualityIssueType.SPEEDER.value == "speeder"
        assert QualityIssueType.INCOMPLETE.value == "incomplete"
        assert QualityIssueType.INCONSISTENT.value == "inconsistent"
        assert QualityIssueType.NONSENSE_TEXT.value == "nonsense_text"
        assert QualityIssueType.PATTERN_RESPONSE.value == "pattern_response"
        assert QualityIssueType.LOGIC_ERROR.value == "logic_error"


class TestQualityIssue:
    """质量问题测试"""
    
    def test_quality_issue_creation(self):
        """测试质量问题创建"""
        issue = QualityIssue(
            issue_type=QualityIssueType.STRAIGHT_LINE,
            severity="high",
            description="所有单选题答案相同",
            affected_questions=["q1", "q2", "q3"],
            confidence=0.9
        )
        
        assert issue.issue_type == QualityIssueType.STRAIGHT_LINE
        assert issue.severity == "high"
        assert issue.description == "所有单选题答案相同"
        assert len(issue.affected_questions) == 3
        assert issue.confidence == 0.9
    
    def test_quality_issue_to_dict(self):
        """测试质量问题转换为字典"""
        issue = QualityIssue(
            issue_type=QualityIssueType.SPEEDER,
            severity="medium",
            description="答题时间过短",
            affected_questions=["all"],
            confidence=0.8
        )
        
        result = issue.to_dict()
        
        assert result["issue_type"] == "speeder"
        assert result["severity"] == "medium"
        assert result["description"] == "答题时间过短"
        assert result["affected_questions"] == ["all"]
        assert result["confidence"] == 0.8
    
    def test_quality_issue_from_dict(self):
        """测试从字典创建质量问题"""
        data = {
            "issue_type": "incomplete",
            "severity": "high",
            "description": "缺失必答题",
            "affected_questions": ["q5"],
            "confidence": 1.0
        }
        
        issue = QualityIssue.from_dict(data)
        
        assert issue.issue_type == QualityIssueType.INCOMPLETE
        assert issue.severity == "high"


class TestQualityReport:
    """质量报告测试"""
    
    def test_quality_report_creation(self):
        """测试质量报告创建"""
        issues = [
            QualityIssue(QualityIssueType.SPEEDER, "medium", "答题过快", ["all"], 0.7)
        ]
        
        report = QualityReport(
            response_id="resp_001",
            quality_score=0.6,
            is_valid=True,
            issues=issues,
            recommendations=["建议人工复核"]
        )
        
        assert report.response_id == "resp_001"
        assert report.quality_score == 0.6
        assert report.is_valid is True
        assert len(report.issues) == 1
        assert len(report.recommendations) == 1
    
    def test_quality_report_to_dict(self):
        """测试质量报告转换为字典"""
        issues = [
            QualityIssue(QualityIssueType.STRAIGHT_LINE, "high", "直线回答", ["q1", "q2"], 0.9)
        ]
        
        report = QualityReport(
            response_id="resp_002",
            quality_score=0.4,
            is_valid=False,
            issues=issues,
            recommendations=["建议剔除"]
        )
        
        result = report.to_dict()
        
        assert result["response_id"] == "resp_002"
        assert result["quality_score"] == 0.4
        assert result["is_valid"] is False
        assert len(result["issues"]) == 1
        assert len(result["recommendations"]) == 1
    
    def test_quality_report_from_dict(self):
        """测试从字典创建质量报告"""
        data = {
            "response_id": "resp_003",
            "quality_score": 0.8,
            "is_valid": True,
            "issues": [],
            "recommendations": []
        }
        
        report = QualityReport.from_dict(data)
        
        assert report.response_id == "resp_003"
        assert report.quality_score == 0.8
        assert report.is_valid is True


class TestResponseQualityValidator:
    """回答质量校验器测试"""
    
    def test_validator_initialization(self):
        """测试校验器初始化"""
        validator = ResponseQualityValidator()
        
        assert validator.min_duration_seconds == 30
        assert validator.max_duration_seconds == 1800
        assert validator.straight_line_threshold == 0.7
        assert validator.min_quality_score == 0.5
    
    def test_validator_initialization_with_config(self):
        """测试带配置的校验器初始化"""
        config = {
            "min_duration_seconds": 60,
            "max_duration_seconds": 900,
            "straight_line_threshold": 0.8,
            "min_quality_score": 0.6
        }
        
        validator = ResponseQualityValidator(config)
        
        assert validator.min_duration_seconds == 60
        assert validator.max_duration_seconds == 900
        assert validator.straight_line_threshold == 0.8
        assert validator.min_quality_score == 0.6
    
    def test_validate_single_response(self):
        """测试单个回答校验"""
        # 创建测试问卷
        survey = self._create_test_survey()
        
        # 创建正常回答
        response = SurveyResponse(
            response_id="resp_001",
            survey_id="survey_001",
            answers={
                "q1": Answer("q1", "opt1"),
                "q2": Answer("q2", "opt2"),
                "q3": Answer("q3", "opt3"),
            },
            duration_seconds=120
        )
        
        validator = ResponseQualityValidator()
        report = validator.validate_response(response, survey)
        
        assert report.response_id == "resp_001"
        assert report.quality_score >= 0.7
        assert report.is_valid is True
        assert len(report.issues) == 0
    
    def test_detect_straight_line(self):
        """测试检测直线回答"""
        survey = self._create_test_survey()
        
        # 创建直线回答（所有单选题答案相同）
        response = SurveyResponse(
            response_id="resp_002",
            survey_id="survey_001",
            answers={
                "q1": Answer("q1", "opt1"),
                "q2": Answer("q2", "opt1"),  # 相同答案
                "q3": Answer("q3", "opt1"),  # 相同答案
            },
            duration_seconds=120
        )
        
        validator = ResponseQualityValidator()
        report = validator.validate_response(response, survey)
        
        assert len(report.issues) > 0
        # 找到直线回答问题
        straight_line_issue = None
        for issue in report.issues:
            if issue.issue_type == QualityIssueType.STRAIGHT_LINE:
                straight_line_issue = issue
                break
        
        assert straight_line_issue is not None
        assert straight_line_issue.severity in ["high", "medium"]
    
    def test_detect_speeder(self):
        """测试检测速答者"""
        survey = self._create_test_survey()
        
        # 创建速答（时间过短）
        response = SurveyResponse(
            response_id="resp_003",
            survey_id="survey_001",
            answers={
                "q1": Answer("q1", "opt1"),
                "q2": Answer("q2", "opt2"),
                "q3": Answer("q3", "opt3"),
            },
            duration_seconds=5  # 5秒完成，太快
        )
        
        validator = ResponseQualityValidator()
        report = validator.validate_response(response, survey)
        
        # 找到速答问题
        speeder_issue = None
        for issue in report.issues:
            if issue.issue_type == QualityIssueType.SPEEDER:
                speeder_issue = issue
                break
        
        assert speeder_issue is not None
        assert speeder_issue.severity == "high"
    
    def test_detect_incomplete(self):
        """测试检测不完整回答"""
        survey = self._create_test_survey()
        
        # 创建不完整回答（缺失必答题）
        response = SurveyResponse(
            response_id="resp_004",
            survey_id="survey_001",
            answers={
                "q1": Answer("q1", "opt1"),
                # q2缺失
                "q3": Answer("q3", "opt3"),
            },
            duration_seconds=120
        )
        
        validator = ResponseQualityValidator()
        report = validator.validate_response(response, survey)
        
        # 找到不完整问题
        incomplete_issue = None
        for issue in report.issues:
            if issue.issue_type == QualityIssueType.INCOMPLETE:
                incomplete_issue = issue
                break
        
        assert incomplete_issue is not None
        assert "q2" in incomplete_issue.affected_questions
    
    def test_detect_nonsense_text(self):
        """测试检测无意义文本"""
        survey = self._create_open_ended_survey()
        
        # 创建无意义开放题回答
        response = SurveyResponse(
            response_id="resp_005",
            survey_id="survey_002",
            answers={
                "q1": Answer("q1", "asdfasdfasdf"),  # 无意义文本
            },
            duration_seconds=120
        )
        
        validator = ResponseQualityValidator()
        report = validator.validate_response(response, survey)
        
        # 找到无意义文本问题
        nonsense_issue = None
        for issue in report.issues:
            if issue.issue_type == QualityIssueType.NONSENSE_TEXT:
                nonsense_issue = issue
                break
        
        assert nonsense_issue is not None
    
    def test_validate_batch_responses(self):
        """测试批量校验回答"""
        survey = self._create_test_survey()
        
        responses = [
            SurveyResponse(
                response_id=f"resp_{i}",
                survey_id="survey_001",
                answers={
                    "q1": Answer("q1", f"opt{i % 3 + 1}"),
                    "q2": Answer("q2", f"opt{(i + 1) % 3 + 1}"),
                    "q3": Answer("q3", f"opt{(i + 2) % 3 + 1}"),
                },
                duration_seconds=100 + i * 10
            )
            for i in range(10)
        ]
        
        validator = ResponseQualityValidator()
        reports = validator.validate_batch(responses, survey)
        
        assert len(reports) == 10
        for report in reports:
            assert report.response_id.startswith("resp_")
            assert report.quality_score >= 0.0
            assert report.quality_score <= 1.0
    
    def test_calculate_quality_score(self):
        """测试质量分数计算"""
        validator = ResponseQualityValidator()
        
        # 无问题 -> 高分数
        score1 = validator._calculate_quality_score([])
        assert score1 >= 0.9
        
        # 一个中等问题 -> 中等分数
        issues = [
            QualityIssue(QualityIssueType.SPEEDER, "medium", "答题过快", ["all"], 0.7)
        ]
        score2 = validator._calculate_quality_score(issues)
        assert 0.7 <= score2 <= 0.95
        
        # 多个高严重性问题 -> 低分数
        issues = [
            QualityIssue(QualityIssueType.STRAIGHT_LINE, "high", "直线回答", ["all"], 0.9),
            QualityIssue(QualityIssueType.INCOMPLETE, "high", "不完整", ["q2"], 1.0),
        ]
        score3 = validator._calculate_quality_score(issues)
        assert score3 < 0.5
    
    def test_filter_valid_responses(self):
        """测试筛选有效回答"""
        survey = self._create_test_survey()
        
        responses = [
            SurveyResponse(
                response_id="valid_001",
                survey_id="survey_001",
                answers={
                    "q1": Answer("q1", "opt1"),
                    "q2": Answer("q2", "opt2"),
                    "q3": Answer("q3", "opt3"),
                },
                duration_seconds=120
            ),
            SurveyResponse(
                response_id="invalid_001",
                survey_id="survey_001",
                answers={
                    "q1": Answer("q1", "opt1"),
                    "q2": Answer("q2", "opt1"),
                    "q3": Answer("q3", "opt1"),
                },
                duration_seconds=5  # 速答 + 直线
            ),
        ]
        
        validator = ResponseQualityValidator()
        valid, invalid = validator.filter_valid_responses(responses, survey)
        
        assert len(valid) == 1
        assert len(invalid) == 1
        assert valid[0].response_id == "valid_001"
        assert invalid[0].response_id == "invalid_001"
    
    def test_get_statistics(self):
        """测试获取统计数据"""
        survey = self._create_test_survey()
        
        responses = [
            SurveyResponse(
                response_id=f"resp_{i}",
                survey_id="survey_001",
                answers={
                    "q1": Answer("q1", "opt1" if i % 2 == 0 else "opt2"),
                    "q2": Answer("q2", "opt2" if i % 2 == 0 else "opt3"),
                    "q3": Answer("q3", "opt3" if i % 2 == 0 else "opt1"),
                },
                duration_seconds=50 + i * 20
            )
            for i in range(20)
        ]
        
        validator = ResponseQualityValidator()
        reports = validator.validate_batch(responses, survey)
        stats = validator.get_quality_statistics(reports)
        
        assert "total_count" in stats
        assert "valid_count" in stats
        assert "invalid_count" in stats
        assert "avg_quality_score" in stats
        assert "issue_distribution" in stats
        
        assert stats["total_count"] == 20
        assert stats["valid_count"] + stats["invalid_count"] == 20
    
    def test_custom_validity_threshold(self):
        """测试自定义有效性阈值"""
        survey = self._create_test_survey()
        
        response = SurveyResponse(
            response_id="resp_custom",
            survey_id="survey_001",
            answers={
                "q1": Answer("q1", "opt1"),
                "q2": Answer("q2", "opt2"),
                "q3": Answer("q3", "opt3"),
            },
            duration_seconds=120
        )
        
        # 使用高阈值（更严格）
        validator = ResponseQualityValidator({"min_quality_score": 0.9})
        report = validator.validate_response(response, survey)
        
        # 正常回答应该通过高阈值
        assert report.quality_score >= 0.5
    
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
                        QuestionOption("opt3", "选项3"),
                    ],
                    required=True
                ),
                Question(
                    question_id="q2",
                    text="问题2",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "选项1"),
                        QuestionOption("opt2", "选项2"),
                        QuestionOption("opt3", "选项3"),
                    ],
                    required=True
                ),
                Question(
                    question_id="q3",
                    text="问题3",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "选项1"),
                        QuestionOption("opt2", "选项2"),
                        QuestionOption("opt3", "选项3"),
                    ],
                    required=True
                ),
            ]
        )
    
    def _create_open_ended_survey(self) -> Survey:
        """创建开放题问卷"""
        return Survey(
            survey_id="survey_002",
            title="开放题问卷",
            questions=[
                Question(
                    question_id="q1",
                    text="请描述您的看法",
                    question_type=QuestionType.OPEN_ENDED,
                    required=True
                ),
            ]
        )


class TestWeek4Integration:
    """Week 4 集成测试"""
    
    @pytest.mark.asyncio
    async def test_validator_with_survey_system(self):
        """测试校验器与调研系统集成"""
        from src.survey.services.simulation_engine import SimulationEngine
        from src.survey.services.persona_factory import PersonaFactory
        
        # 创建问卷
        survey = self._create_complex_survey()
        
        # 生成画像
        factory = PersonaFactory()
        personas = factory.generate_population("一线白领", 5)
        
        # 模拟回答（异步）
        engine = SimulationEngine()
        responses = await engine.simulate_survey(personas, survey)
        
        # 校验质量
        validator = ResponseQualityValidator()
        reports = validator.validate_batch(responses, survey)
        
        # 检查结果
        assert len(reports) == 5
        valid_count = sum(1 for r in reports if r.is_valid)
        assert valid_count >= 3  # 至少60%有效
    
    def _create_complex_survey(self) -> Survey:
        """创建复杂问卷"""
        return Survey(
            survey_id="survey_complex",
            title="综合性问卷",
            questions=[
                Question(
                    question_id="q1",
                    text="您对这个产品的满意度如何？",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "非常满意"),
                        QuestionOption("opt2", "满意"),
                        QuestionOption("opt3", "一般"),
                        QuestionOption("opt4", "不满意"),
                    ],
                    required=True
                ),
                Question(
                    question_id="q2",
                    text="您使用该产品的频率？",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption("opt1", "每天"),
                        QuestionOption("opt2", "每周"),
                        QuestionOption("opt3", "每月"),
                        QuestionOption("opt4", "很少"),
                    ],
                    required=True
                ),
                Question(
                    question_id="q3",
                    text="您有什么建议？",
                    question_type=QuestionType.OPEN_ENDED,
                    required=False
                ),
            ]
        )