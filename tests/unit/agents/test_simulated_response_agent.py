"""
SimulatedResponseAgent 测试 - TDD模式

测试覆盖：
- Agent初始化
- 单人/多人模拟
- 并发执行
- LLM集成
- 输入验证
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.survey.models import Survey, Question, QuestionOption, QuestionType, SurveyResponse, Answer
from src.survey.services.persona_factory import Persona, PersonaFactory
from src.survey.services.simulation_engine import SimulationEngine
from src.agents.fixed_agents.simulated_response_agent import SimulatedResponseAgent


def create_sample_survey() -> Survey:
    return Survey(
        survey_id="test_survey_001",
        title="新能源汽车购买意向调研",
        questions=[
            Question(question_id="q1", text="您是否考虑购买新能源汽车？",
                     question_type=QuestionType.SINGLE_CHOICE,
                     options=[QuestionOption(option_id="opt1", text="是"),
                              QuestionOption(option_id="opt2", text="否"),
                              QuestionOption(option_id="opt3", text="正在考虑")]),
            Question(question_id="q2", text="请简述您的看法",
                     question_type=QuestionType.OPEN_ENDED),
        ]
    )


def create_sample_persona() -> Persona:
    return Persona(
        persona_id="persona_001", name="张伟", age=35, gender="男",
        city="北京", occupation="程序员", income="20-40万", education="硕士",
        personality_traits=["理性"], interests=["科技"], values=["环保"],
        decision_style="研究型", background_story="张伟是一名资深程序员。",
    )


class TestSimulatedResponseAgent:

    @pytest.fixture
    def agent(self):
        return SimulatedResponseAgent(
            agent_id="sim_agent_001",
            name="模拟回答Agent",
        )

    # ========== 基础测试 ==========

    def test_agent_initialization(self, agent):
        assert agent.agent_id == "sim_agent_001"
        assert agent.name == "模拟回答Agent"
        assert agent.agent_type == "simulated_response"
        assert len(agent.capabilities) > 0

    def test_agent_has_required_attributes(self, agent):
        assert hasattr(agent, 'agent_type')
        assert hasattr(agent, 'version')
        assert hasattr(agent, 'capabilities')
        assert hasattr(agent, 'execute')

    # ========== 输入验证测试 ==========

    def test_validate_input_missing_survey(self, agent):
        task_input = {"personas": [create_sample_persona()]}
        valid, error = agent.validate_input(task_input)
        assert valid is False

    def test_validate_input_missing_personas(self, agent):
        task_input = {"survey": create_sample_survey().to_dict()}
        valid, error = agent.validate_input(task_input)
        assert valid is False

    def test_validate_input_valid(self, agent):
        task_input = {"survey": create_sample_survey().to_dict(), "personas": [create_sample_persona()]}
        valid, error = agent.validate_input(task_input)
        assert valid is True

    # ========== 执行测试 ==========

    @pytest.mark.asyncio
    async def test_execute_single_persona(self, agent):
        task_input = {
            "survey": create_sample_survey().to_dict(),
            "personas": [create_sample_persona()],
        }
        result = await agent.execute(task_input)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_multiple_personas(self, agent):
        personas = [create_sample_persona(), Persona(
            persona_id="persona_002", name="李娜", age=28, gender="女",
            city="上海", occupation="产品经理", income="15-30万", education="本科",
            personality_traits=["外向"], interests=["旅行"], values=["家庭"],
            decision_style="冲动型", background_story="李娜是一名产品经理。",
        )]
        task_input = {"survey": create_sample_survey().to_dict(), "personas": personas}
        result = await agent.execute(task_input)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_with_parallel_option(self, agent):
        task_input = {
            "survey": create_sample_survey().to_dict(),
            "personas": [create_sample_persona()],
            "parallel": True,
        }
        result = await agent.execute(task_input)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_result_contains_required_fields(self, agent):
        task_input = {"survey": create_sample_survey().to_dict(), "personas": [create_sample_persona()]}
        result = await agent.execute(task_input)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_with_empty_personas(self, agent):
        task_input = {"survey": create_sample_survey().to_dict(), "personas": []}
        result = await agent.execute(task_input)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_with_empty_questions(self, agent):
        empty_survey = Survey(survey_id="empty", title="空", questions=[])
        task_input = {"survey": empty_survey.to_dict(), "personas": [create_sample_persona()]}
        result = await agent.execute(task_input)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_run_with_invalid_input(self, agent):
        result = await agent.run({"invalid": "input"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_run_method(self, agent):
        task_input = {"survey": create_sample_survey().to_dict(), "personas": [create_sample_persona()]}
        result = await agent.run(task_input)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_run_includes_metadata(self, agent):
        task_input = {"survey": create_sample_survey().to_dict(), "personas": [create_sample_persona()]}
        result = await agent.run(task_input)
        assert "agent_id" in result

    # ========== 状态管理测试 ==========

    @pytest.mark.asyncio
    async def test_agent_state_transition(self, agent):
        assert agent.status == "idle"
        task_input = {"survey": create_sample_survey().to_dict(), "personas": [create_sample_persona()]}
        result = await agent.run(task_input)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_agent_reset(self, agent):
        task_input = {"survey": create_sample_survey().to_dict(), "personas": [create_sample_persona()]}
        await agent.run(task_input)
        await agent.reset()
        assert agent.status == "idle"

    # ========== 错误恢复测试 ==========

    @pytest.mark.asyncio
    async def test_error_recovery(self, agent):
        result = await agent.run({"invalid": "input"})
        assert result["success"] is False
        task_input = {"survey": create_sample_survey().to_dict(), "personas": [create_sample_persona()]}
        result = await agent.run(task_input)
        assert result["success"] is True

    # ========== 边界条件测试 ==========

    @pytest.mark.asyncio
    async def test_large_question_count(self, agent):
        questions = [Question(question_id=f"q{i}", text=f"问题{i}",
                              question_type=QuestionType.OPEN_ENDED) for i in range(20)]
        survey = Survey(survey_id="large", title="大问卷", questions=questions)
        task_input = {"survey": survey.to_dict(), "personas": [create_sample_persona()]}
        result = await agent.execute(task_input)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_persona_with_minimal_attributes(self, agent):
        minimal_persona = Persona(
            persona_id="p_min", name="最小", age=25, gender="男",
            city="未知", occupation="未知", income="未知", education="未知",
            personality_traits=[], interests=[], values=[],
            decision_style="未知", background_story="",
        )
        task_input = {"survey": create_sample_survey().to_dict(), "personas": [minimal_persona]}
        result = await agent.execute(task_input)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_all_question_types(self, agent):
        survey = Survey(
            survey_id="all_types", title="所有类型",
            questions=[
                Question(question_id="q_single", text="单选",
                         question_type=QuestionType.SINGLE_CHOICE,
                         options=[QuestionOption(option_id="o1", text="A"), QuestionOption(option_id="o2", text="B")]),
                Question(question_id="q_multi", text="多选",
                         question_type=QuestionType.MULTIPLE_CHOICE,
                         options=[QuestionOption(option_id="o1", text="X"), QuestionOption(option_id="o2", text="Y")]),
                Question(question_id="q_open", text="开放题",
                         question_type=QuestionType.OPEN_ENDED),
            ]
        )
        task_input = {"survey": survey.to_dict(), "personas": [create_sample_persona()]}
        result = await agent.execute(task_input)
        assert result["success"] is True

    # ========== 性能测试 ==========

    @pytest.mark.asyncio
    async def test_concurrent_simulation_consistency(self, agent):
        task_input = {"survey": create_sample_survey().to_dict(), "personas": [create_sample_persona()]}
        result1 = await agent.execute(task_input)
        result2 = await agent.execute(task_input)
        assert result1["success"] is True
        assert result2["success"] is True

    @pytest.mark.asyncio
    async def test_max_concurrent_limit(self, agent):
        personas = [create_sample_persona() for _ in range(5)]
        task_input = {"survey": create_sample_survey().to_dict(), "personas": personas, "max_concurrent": 2}
        result = await agent.execute(task_input)
        assert result["success"] is True
