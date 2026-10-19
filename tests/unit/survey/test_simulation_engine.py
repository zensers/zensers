"""
SimulationEngine 测试 - TDD模式

测试覆盖：
- 规则生成回答
- LLM集成调用（通过 mock call_llm）
- 回答一致性检查
- 并发模拟执行
- LLM响应解析
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.survey.models import (
    Survey, Question, QuestionOption, QuestionType,
    SurveyResponse, Answer
)
from src.survey.services.persona_factory import Persona
from src.survey.services.simulation_engine import SimulationEngine


def create_sample_survey() -> Survey:
    return Survey(
        survey_id="test_survey_001",
        title="新能源汽车购买意向调研",
        questions=[
            Question(
                question_id="q1",
                text="您是否考虑购买新能源汽车？",
                question_type=QuestionType.SINGLE_CHOICE,
                options=[
                    QuestionOption(option_id="opt1", text="是"),
                    QuestionOption(option_id="opt2", text="否"),
                    QuestionOption(option_id="opt3", text="正在考虑"),
                ]
            ),
            Question(
                question_id="q2",
                text="您最看重新能源汽车哪些特点？（可多选）",
                question_type=QuestionType.MULTIPLE_CHOICE,
                options=[
                    QuestionOption(option_id="opt1", text="环保"),
                    QuestionOption(option_id="opt2", text="省钱"),
                    QuestionOption(option_id="opt3", text="科技感"),
                    QuestionOption(option_id="opt4", text="政策优惠"),
                ]
            ),
            Question(
                question_id="q3",
                text="您对新能源汽车的总体评价",
                question_type=QuestionType.LIKERT,
                options=[
                    QuestionOption(option_id="opt1", text="非常满意", value=5),
                    QuestionOption(option_id="opt2", text="满意", value=4),
                    QuestionOption(option_id="opt3", text="一般", value=3),
                    QuestionOption(option_id="opt4", text="不满意", value=2),
                    QuestionOption(option_id="opt5", text="非常不满意", value=1),
                ]
            ),
            Question(
                question_id="q4",
                text="请简述您对新能源汽车的看法",
                question_type=QuestionType.OPEN_ENDED,
            ),
            Question(
                question_id="q5",
                text="您愿意为新能源汽车支付的价格范围（评分1-10）",
                question_type=QuestionType.SCALE,
            ),
        ]
    )


def create_sample_persona() -> Persona:
    return Persona(
        persona_id="persona_001",
        name="张伟",
        age=35,
        gender="男",
        city="北京",
        occupation="程序员",
        income="20-40万",
        education="硕士",
        personality_traits=["理性", "注重品质", "科技爱好者"],
        interests=["科技", "汽车", "旅行"],
        values=["环保", "创新", "效率"],
        decision_style="研究型",
        background_story="张伟是一名资深程序员，对新技术充满热情。",
    )


class TestSimulationEngine:

    @pytest.fixture
    def engine(self):
        return SimulationEngine()

    @pytest.fixture
    def sample_survey(self):
        return create_sample_survey()

    @pytest.fixture
    def sample_persona(self):
        return create_sample_persona()

    # ========== 基础测试 ==========

    def test_engine_initialization(self, engine):
        assert engine is not None

    # ========== 模拟问卷测试 ==========

    @pytest.mark.asyncio
    async def test_simulate_survey_single_persona_no_llm(self, engine, sample_survey, sample_persona):
        responses = await engine.simulate_survey(
            personas=[sample_persona],
            survey=sample_survey,
            parallel=False
        )
        assert len(responses) == 1
        assert isinstance(responses[0], SurveyResponse)
        assert responses[0].survey_id == sample_survey.survey_id
        assert responses[0].respondent_id == sample_persona.persona_id
        assert len(responses[0].answers) == len(sample_survey.questions)

    @pytest.mark.asyncio
    async def test_simulate_survey_with_llm_mock(self, engine, sample_survey, sample_persona):
        with patch("src.survey.services.simulation_engine.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"success": True, "content": "是", "usage": {"total_tokens": 50}}
            responses = await engine.simulate_survey(
                personas=[sample_persona],
                survey=sample_survey,
                parallel=False
            )
        assert len(responses) == 1
        assert mock_call.call_count > 0

    @pytest.mark.asyncio
    async def test_simulate_survey_multiple_personas(self, engine, sample_survey):
        personas = [
            create_sample_persona(),
            Persona(
                persona_id="persona_002",
                name="李娜",
                age=28,
                gender="女",
                city="上海",
                occupation="产品经理",
                income="15-30万",
                education="本科",
                personality_traits=["外向", "创新", "务实"],
                interests=["旅行", "美食", "电影"],
                values=["家庭", "事业", "健康"],
                decision_style="冲动型",
                background_story="李娜是一名产品经理，喜欢尝试新事物。",
            )
        ]
        responses = await engine.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=False
        )
        assert len(responses) == 2
        assert responses[0].respondent_id == "persona_001"
        assert responses[1].respondent_id == "persona_002"

    # ========== 并发测试 ==========

    @pytest.mark.asyncio
    async def test_concurrent_simulation(self, engine, sample_survey):
        personas = [create_sample_persona() for _ in range(5)]
        responses = await engine.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=True,
            max_concurrent=3
        )
        assert len(responses) == 5
        for response in responses:
            assert response.survey_id == sample_survey.survey_id
            assert len(response.answers) == len(sample_survey.questions)

    @pytest.mark.asyncio
    async def test_concurrent_simulation_with_limit(self, engine, sample_survey):
        personas = [create_sample_persona() for _ in range(10)]
        responses = await engine.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=True,
            max_concurrent=2
        )
        assert len(responses) == 10

    @pytest.mark.asyncio
    async def test_sequential_vs_parallel_same_results_count(self, engine, sample_survey):
        personas = [create_sample_persona() for _ in range(3)]
        responses_seq = await engine.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=False
        )
        responses_par = await engine.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=True
        )
        assert len(responses_seq) == len(responses_par)

    # ========== LLM响应解析测试 ==========

    def test_parse_llm_response_single_choice(self, engine, sample_survey):
        question = sample_survey.questions[0]
        result = engine._parse_llm_response("是", question)
        assert result == "是"

    def test_parse_llm_response_multiple_choice(self, engine, sample_survey):
        question = sample_survey.questions[1]
        result = engine._parse_llm_response("环保,省钱", question)
        assert "环保" in result or "省钱" in result

    def test_parse_llm_response_likert(self, engine, sample_survey):
        question = sample_survey.questions[2]
        result = engine._parse_llm_response("4", question)
        assert result == 4

    def test_parse_llm_response_scale(self, engine, sample_survey):
        question = sample_survey.questions[4]
        result = engine._parse_llm_response("8", question)
        assert result == 8

    def test_parse_llm_response_open_ended(self, engine, sample_survey):
        question = sample_survey.questions[3]
        result = engine._parse_llm_response("新能源汽车是未来的趋势", question)
        assert result == "新能源汽车是未来的趋势"

    def test_parse_llm_response_invalid_returns_original(self, engine, sample_survey):
        question = sample_survey.questions[0]
        result = engine._parse_llm_response("我不知道", question)
        assert result == "我不知道"

    # ========== 规则生成测试 ==========

    def test_answer_with_rules_single_choice(self, engine, sample_survey, sample_persona):
        question = sample_survey.questions[0]
        answer = engine._answer_with_rules(sample_persona, question)
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id
        assert answer.answer_value in ["是", "否", "正在考虑"]

    def test_answer_with_rules_multiple_choice(self, engine, sample_survey, sample_persona):
        question = sample_survey.questions[1]
        answer = engine._answer_with_rules(sample_persona, question)
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id

    def test_answer_with_rules_likert(self, engine, sample_survey, sample_persona):
        question = sample_survey.questions[2]
        answer = engine._answer_with_rules(sample_persona, question)
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id
        assert answer.answer_value in [1, 2, 3, 4, 5]

    def test_answer_with_rules_open_ended(self, engine, sample_survey, sample_persona):
        question = sample_survey.questions[3]
        answer = engine._answer_with_rules(sample_persona, question)
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id
        assert answer.answer_value is not None
        assert len(answer.answer_value) > 0

    def test_answer_with_rules_scale(self, engine, sample_survey, sample_persona):
        question = sample_survey.questions[4]
        answer = engine._answer_with_rules(sample_persona, question)
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id
        assert answer.answer_value in [1, 2, 3, 4, 5]

    # ========== LLM回退测试 ==========

    @pytest.mark.asyncio
    async def test_llm_fallback_to_rules_on_error(self, engine, sample_survey, sample_persona):
        with patch("src.survey.services.simulation_engine.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("LLM调用失败")
            question = sample_survey.questions[0]
            answer = await engine._answer_question(sample_persona, question, [])
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id

    @pytest.mark.asyncio
    async def test_llm_fallback_on_invalid_response(self, engine, sample_survey, sample_persona):
        with patch("src.survey.services.simulation_engine.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"success": True, "content": "", "usage": {"total_tokens": 10}}
            question = sample_survey.questions[0]
            answer = await engine._answer_question(sample_persona, question, [])
        assert isinstance(answer, Answer)

    # ========== 边界条件测试 ==========

    @pytest.mark.asyncio
    async def test_empty_personas_list(self, engine, sample_survey):
        responses = await engine.simulate_survey(
            personas=[],
            survey=sample_survey,
            parallel=False
        )
        assert len(responses) == 0

    @pytest.mark.asyncio
    async def test_empty_questions_list(self, engine, sample_persona):
        empty_survey = Survey(
            survey_id="empty_survey",
            title="空问卷",
            questions=[]
        )
        responses = await engine.simulate_survey(
            personas=[sample_persona],
            survey=empty_survey,
            parallel=False
        )
        assert len(responses) == 1
        assert len(responses[0].answers) == 0

    def test_response_id_generation(self, engine, sample_survey, sample_persona):
        import asyncio
        async def run_test():
            response = await engine._simulate_single(sample_persona, sample_survey)
            assert sample_persona.persona_id in response.response_id
            assert sample_survey.survey_id in response.response_id
        asyncio.run(run_test())

    # ========== 性能基准测试 ==========

    @pytest.mark.asyncio
    async def test_performance_small_batch(self, engine, sample_survey):
        import time
        personas = [create_sample_persona() for _ in range(10)]
        start_time = time.time()
        responses = await engine.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=True
        )
        elapsed_time = time.time() - start_time
        assert len(responses) == 10
        assert elapsed_time < 5.0

    @pytest.mark.asyncio
    async def test_performance_medium_batch(self, engine, sample_survey):
        import time
        personas = [create_sample_persona() for _ in range(50)]
        start_time = time.time()
        responses = await engine.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=True,
            max_concurrent=10
        )
        elapsed_time = time.time() - start_time
        assert len(responses) == 50
        assert elapsed_time < 10.0
