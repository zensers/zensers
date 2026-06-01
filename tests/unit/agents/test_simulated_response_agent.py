"""
SimulatedResponseAgent 测试 - TDD模式（Week 2 Day 2）

测试覆盖：
- Agent初始化
- 模拟单人回答
- 输入验证
- 与SimulationEngine集成
- 错误处理
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.survey.models import (
    Survey, Question, QuestionOption, QuestionType,
    SurveyResponse, Answer
)
from src.survey.services.persona_factory import Persona


def create_sample_survey() -> Survey:
    """创建测试问卷"""
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
                text="您对新能源汽车的总体评价",
                question_type=QuestionType.LIKERT,
                options=[
                    QuestionOption(option_id="opt1", text="非常满意", value=5),
                    QuestionOption(option_id="opt2", text="满意", value=4),
                    QuestionOption(option_id="opt3", text="一般", value=3),
                ]
            ),
            Question(
                question_id="q3",
                text="请简述您的看法",
                question_type=QuestionType.OPEN_ENDED,
            ),
        ]
    )


def create_sample_persona() -> Persona:
    """创建测试人物画像"""
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


class TestSimulatedResponseAgent:
    """测试SimulatedResponseAgent"""
    
    @pytest.fixture
    def agent(self):
        """创建Agent实例"""
        from src.agents.fixed_agents.simulated_response_agent import SimulatedResponseAgent
        return SimulatedResponseAgent(
            agent_id="sim_agent_001",
            name="模拟回答Agent",
        )
    
    @pytest.fixture
    def agent_with_llm(self):
        """创建带LLM的Agent实例"""
        from src.agents.fixed_agents.simulated_response_agent import SimulatedResponseAgent
        
        # 创建Mock LLM Skill
        mock_llm = MagicMock()
        mock_llm.execute = AsyncMock(return_value={
            "success": True,
            "content": "是",
            "usage": {"total_tokens": 100}
        })
        
        return SimulatedResponseAgent(
            agent_id="sim_agent_002",
            name="模拟回答Agent",
            llm_skill=mock_llm,
        )
    
    @pytest.fixture
    def sample_survey(self):
        return create_sample_survey()
    
    @pytest.fixture
    def sample_persona(self):
        return create_sample_persona()
    
    # ========== 基础测试 ==========
    
    def test_agent_initialization(self, agent):
        """测试Agent初始化"""
        assert agent.agent_id == "sim_agent_001"
        assert agent.name == "模拟回答Agent"
        assert agent.agent_type == "simulated_response"
        assert "模拟问卷回答" in agent.capabilities or len(agent.capabilities) > 0
    
    def test_agent_has_required_attributes(self, agent):
        """测试Agent具有必需属性"""
        assert hasattr(agent, 'agent_type')
        assert hasattr(agent, 'version')
        assert hasattr(agent, 'capabilities')
        assert hasattr(agent, 'execute')
    
    def test_agent_with_llm_initialization(self, agent_with_llm):
        """测试带LLM的Agent初始化"""
        assert agent_with_llm.llm_skill is not None
    
    # ========== 输入验证测试 ==========
    
    def test_validate_input_missing_survey(self, agent):
        """测试缺少问卷的输入验证"""
        task_input = {
            "personas": [create_sample_persona()],
        }
        valid, error = agent.validate_input(task_input)
        assert valid is False
        assert "survey" in error.lower() or "问卷" in error
    
    def test_validate_input_missing_personas(self, agent):
        """测试缺少人物画像的输入验证"""
        task_input = {
            "survey": create_sample_survey().to_dict(),
        }
        valid, error = agent.validate_input(task_input)
        assert valid is False
        assert "persona" in error.lower() or "画像" in error
    
    def test_validate_input_invalid_survey_type(self, agent):
        """测试问卷类型错误的输入验证"""
        task_input = {
            "survey": "invalid_survey",  # 应该是字典
            "personas": [create_sample_persona()],
        }
        valid, error = agent.validate_input(task_input)
        assert valid is False
    
    def test_validate_input_invalid_personas_type(self, agent):
        """测试人物画像类型错误的输入验证"""
        task_input = {
            "survey": create_sample_survey().to_dict(),
            "personas": "invalid_personas",  # 应该是列表
        }
        valid, error = agent.validate_input(task_input)
        assert valid is False
    
    def test_validate_input_valid(self, agent, sample_survey, sample_persona):
        """测试有效输入验证"""
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona],
        }
        valid, error = agent.validate_input(task_input)
        assert valid is True
        assert error == ""
    
    # ========== 执行测试 ==========
    
    def test_execute_single_persona(self, agent, sample_survey, sample_persona):
        """测试单人模拟执行"""
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert "responses" in result
        assert len(result["responses"]) == 1
    
    def test_execute_multiple_personas(self, agent, sample_survey):
        """测试多人模拟执行"""
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
                personality_traits=["外向", "创新"],
                interests=["旅行", "美食"],
                values=["家庭", "事业"],
                decision_style="冲动型",
                background_story="李娜是一名产品经理。",
            )
        ]
        
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": personas,
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["responses"]) == 2
    
    def test_execute_with_parallel_option(self, agent, sample_survey, sample_persona):
        """测试并行执行选项"""
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona] * 3,
            "parallel": True,
            "max_concurrent": 2,
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["responses"]) == 3
    
    def test_execute_with_llm(self, agent_with_llm, sample_survey, sample_persona):
        """测试使用LLM执行"""
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        result = agent_with_llm.execute(task_input)
        
        assert result["success"] is True
        assert len(result["responses"]) == 1
    
    # ========== 结果格式测试 ==========
    
    def test_result_contains_required_fields(self, agent, sample_survey, sample_persona):
        """测试结果包含必需字段"""
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        result = agent.execute(task_input)
        
        assert "success" in result
        assert "responses" in result
        assert "total_count" in result or "count" in result
    
    def test_response_structure(self, agent, sample_survey, sample_persona):
        """测试响应结构"""
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        result = agent.execute(task_input)
        
        # 检查第一个响应的结构
        response = result["responses"][0]
        assert "response_id" in response or "survey_id" in response
        assert "answers" in response
    
    # ========== 错误处理测试 ==========
    
    def test_execute_with_empty_personas(self, agent, sample_survey):
        """测试空人物列表"""
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [],
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["responses"]) == 0
    
    def test_execute_with_empty_questions(self, agent, sample_persona):
        """测试空问卷"""
        empty_survey = Survey(
            survey_id="empty_survey",
            title="空问卷",
            questions=[]
        )
        
        task_input = {
            "survey": empty_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["responses"]) == 1
        assert len(result["responses"][0].get("answers", {})) == 0
    
    def test_run_with_invalid_input(self, agent):
        """测试无效输入运行"""
        result = agent.run({"invalid": "input"})
        
        assert result["success"] is False
        assert "error" in result
    
    # ========== Run方法测试 ==========
    
    def test_run_method(self, agent, sample_survey, sample_persona):
        """测试run方法"""
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        result = agent.run(task_input)
        
        assert result["success"] is True
        assert result["agent_id"] == agent.agent_id
        assert result["agent_name"] == agent.name
    
    def test_run_includes_metadata(self, agent, sample_survey, sample_persona):
        """测试run方法包含元数据"""
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        result = agent.run(task_input)
        
        assert "agent_id" in result
        assert "agent_name" in result
        assert "agent_version" in result
    
    # ========== 能力测试 ==========
    
    def test_get_capabilities(self, agent):
        """测试获取能力"""
        capabilities = agent.get_capabilities()
        
        assert isinstance(capabilities, list)
        assert len(capabilities) > 0
    
    # ========== 集成测试 ==========
    
    def test_integration_with_simulation_engine(self, agent, sample_survey, sample_persona):
        """测试与SimulationEngine集成"""
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        result = agent.execute(task_input)
        
        # 验证结果与SimulationEngine输出一致
        assert result["success"] is True
        assert len(result["responses"]) == 1
        
        # 验证答案结构
        response = result["responses"][0]
        answers = response.get("answers", {})
        assert len(answers) == len(sample_survey.questions)
    
    def test_batch_simulation_performance(self, agent, sample_survey):
        """测试批量模拟性能"""
        import time
        
        personas = [create_sample_persona() for _ in range(10)]
        
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": personas,
            "parallel": True,
        }
        
        start_time = time.time()
        result = agent.execute(task_input)
        elapsed_time = time.time() - start_time
        
        assert result["success"] is True
        assert len(result["responses"]) == 10
        # 10人×3题应该很快
        assert elapsed_time < 5.0
    
    # ========== 异步方法测试 ==========
    
    @pytest.mark.asyncio
    async def test_execute_async(self, agent, sample_survey, sample_persona):
        """测试异步执行方法"""
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        result = await agent.execute_async(task_input)
        
        assert result["success"] is True
        assert len(result["responses"]) == 1
    
    @pytest.mark.asyncio
    async def test_execute_async_multiple_personas(self, agent, sample_survey):
        """测试异步执行多人"""
        personas = [create_sample_persona() for _ in range(5)]
        
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": personas,
            "parallel": True,
        }
        
        result = await agent.execute_async(task_input)
        
        assert result["success"] is True
        assert len(result["responses"]) == 5
    
    @pytest.mark.asyncio
    async def test_execute_async_invalid_input(self, agent):
        """测试异步执行无效输入"""
        task_input = {"invalid": "input"}
        
        result = await agent.execute_async(task_input)
        
        assert result["success"] is False
        assert "error" in result
    
    # ========== 状态管理测试 ==========
    
    def test_agent_state_transition(self, agent, sample_survey, sample_persona):
        """测试Agent状态转换"""
        
        # 初始状态应该是idle
        assert agent.status == "idle"
        
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        # 执行后状态应该是completed
        result = agent.run(task_input)
        
        assert result["success"] is True
        assert agent.status == "completed"
    
    def test_agent_reset(self, agent, sample_survey, sample_persona):
        """测试Agent重置"""
        
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        # 执行任务
        agent.run(task_input)
        assert agent.status == "completed"
        
        # 重置
        agent.reset()
        assert agent.status == "idle"
    
    # ========== 错误恢复测试 ==========
    
    def test_error_recovery(self, agent):
        """测试错误恢复"""
        
        # 触发验证失败（状态保持idle）
        result = agent.run({"invalid": "input"})
        
        assert result["success"] is False
        # 验证失败时状态不变，仍为idle
        assert agent.status == "idle"
        
        # 重新执行有效任务
        task_input = {
            "survey": create_sample_survey().to_dict(),
            "personas": [create_sample_persona()],
        }
        result = agent.run(task_input)
        assert result["success"] is True
        assert agent.status == "completed"
    
    # ========== 边界条件测试 ==========
    
    def test_large_question_count(self, agent, sample_persona):
        """测试大量问题"""
        # 创建包含20个问题的问卷
        questions = []
        for i in range(20):
            questions.append(
                Question(
                    question_id=f"q{i}",
                    text=f"问题 {i+1}",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption(option_id=f"opt{j}", text=f"选项{j+1}")
                        for j in range(4)
                    ]
                )
            )
        
        large_survey = Survey(
            survey_id="large_survey",
            title="大问卷",
            questions=questions,
        )
        
        task_input = {
            "survey": large_survey.to_dict(),
            "personas": [sample_persona],
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["responses"][0].get("answers", {})) == 20
    
    def test_persona_with_minimal_attributes(self, agent, sample_survey):
        """测试最小属性的人物画像"""
        minimal_persona = Persona(
            persona_id="minimal_001",
            name="测试用户",
            age=25,
            gender="男",
            city="北京",
            occupation="测试",
            income="10万",
            education="本科",
            personality_traits=[],
            interests=[],
            values=[],
            decision_style="中性",
        )
        
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": [minimal_persona],
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["responses"]) == 1
    
    def test_all_question_types(self, agent, sample_persona):
        """测试所有问题类型"""
        from src.survey.models import QuestionType
        
        survey = Survey(
            survey_id="all_types_survey",
            title="所有类型问卷",
            questions=[
                Question(
                    question_id="q_single",
                    text="单选题",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption(option_id="opt1", text="选项A"),
                        QuestionOption(option_id="opt2", text="选项B"),
                    ]
                ),
                Question(
                    question_id="q_multiple",
                    text="多选题",
                    question_type=QuestionType.MULTIPLE_CHOICE,
                    options=[
                        QuestionOption(option_id="opt1", text="选项A"),
                        QuestionOption(option_id="opt2", text="选项B"),
                        QuestionOption(option_id="opt3", text="选项C"),
                    ]
                ),
                Question(
                    question_id="q_likert",
                    text="李克特量表",
                    question_type=QuestionType.LIKERT,
                    options=[
                        QuestionOption(option_id="opt1", text="非常满意", value=5),
                        QuestionOption(option_id="opt2", text="满意", value=4),
                        QuestionOption(option_id="opt3", text="一般", value=3),
                    ]
                ),
                Question(
                    question_id="q_scale",
                    text="评分题",
                    question_type=QuestionType.SCALE,
                ),
                Question(
                    question_id="q_open",
                    text="开放题",
                    question_type=QuestionType.OPEN_ENDED,
                ),
            ]
        )
        
        task_input = {
            "survey": survey.to_dict(),
            "personas": [sample_persona],
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        answers = result["responses"][0].get("answers", {})
        assert len(answers) == 5
    
    # ========== 版本和能力测试 ==========
    
    def test_agent_version(self, agent):
        """测试Agent版本"""
        assert agent.version is not None
        assert len(agent.version.split(".")) >= 2  # 至少有主版本和次版本
    
    def test_agent_capabilities_not_empty(self, agent):
        """测试能力列表不为空"""
        capabilities = agent.get_capabilities()
        assert len(capabilities) > 0
    
    # ========== 并发测试 ==========
    
    def test_concurrent_simulation_consistency(self, agent, sample_survey):
        """测试并发模拟的一致性"""
        personas = [create_sample_persona() for _ in range(5)]
        
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": personas,
            "parallel": True,
            "max_concurrent": 3,
        }
        
        # 执行两次，确保结果一致
        result1 = agent.execute(task_input)
        result2 = agent.execute(task_input)
        
        assert result1["success"] is True
        assert result2["success"] is True
        assert result1["total_count"] == result2["total_count"]
    
    def test_max_concurrent_limit(self, agent, sample_survey):
        """测试最大并发限制"""
        personas = [create_sample_persona() for _ in range(20)]
        
        task_input = {
            "survey": sample_survey.to_dict(),
            "personas": personas,
            "parallel": True,
            "max_concurrent": 5,
        }
        
        import time
        start_time = time.time()
        result = agent.execute(task_input)
        elapsed_time = time.time() - start_time
        
        assert result["success"] is True
        assert len(result["responses"]) == 20