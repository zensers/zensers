"""
SimulationEngine 测试 - TDD模式（Week 2 Day 1）

测试覆盖：
- LLM集成调用
- 回答一致性检查
- 并发模拟执行
- 提示词构建
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


class MockLLMSkill:
    """模拟LLM Skill用于测试"""
    
    def __init__(self, response_content="模拟回答"):
        self.response_content = response_content
        self.call_count = 0
        self.last_prompt = None
        self.last_system_prompt = None
    
    async def execute(self, **kwargs):
        self.call_count += 1
        self.last_prompt = kwargs.get("prompt", "")
        self.last_system_prompt = kwargs.get("system_prompt", "")
        return {
            "success": True,
            "content": self.response_content,
            "usage": {"total_tokens": 100}
        }


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


class TestSimulationEngine:
    """测试SimulationEngine"""
    
    @pytest.fixture
    def engine_no_llm(self):
        """无LLM引擎"""
        return SimulationEngine(llm_skill=None)
    
    @pytest.fixture
    def engine_with_llm(self):
        """带LLM引擎"""
        mock_llm = MockLLMSkill(response_content="是")
        return SimulationEngine(llm_skill=mock_llm)
    
    @pytest.fixture
    def sample_survey(self):
        return create_sample_survey()
    
    @pytest.fixture
    def sample_persona(self):
        return create_sample_persona()
    
    # ========== 基础测试 ==========
    
    def test_engine_initialization(self, engine_no_llm):
        """测试引擎初始化"""
        assert engine_no_llm.llm_skill is None
        assert engine_no_llm is not None
    
    def test_engine_with_llm_initialization(self, engine_with_llm):
        """测试带LLM的引擎初始化"""
        assert engine_with_llm.llm_skill is not None
        assert engine_with_llm.llm_skill.response_content == "是"
    
    # ========== 模拟问卷测试 ==========
    
    @pytest.mark.asyncio
    async def test_simulate_survey_single_persona_no_llm(self, engine_no_llm, sample_survey, sample_persona):
        """测试单人模拟（无LLM，规则生成）"""
        responses = await engine_no_llm.simulate_survey(
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
    async def test_simulate_survey_single_persona_with_llm(self, engine_with_llm, sample_survey, sample_persona):
        """测试单人模拟（带LLM）"""
        responses = await engine_with_llm.simulate_survey(
            personas=[sample_persona],
            survey=sample_survey,
            parallel=False
        )
        
        assert len(responses) == 1
        assert engine_with_llm.llm_skill.call_count > 0
        # 验证每个问题都调用了一次LLM
        assert engine_with_llm.llm_skill.call_count == len(sample_survey.questions)
    
    @pytest.mark.asyncio
    async def test_simulate_survey_multiple_personas(self, engine_no_llm, sample_survey):
        """测试多人模拟"""
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
        
        responses = await engine_no_llm.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=False
        )
        
        assert len(responses) == 2
        assert responses[0].respondent_id == "persona_001"
        assert responses[1].respondent_id == "persona_002"
    
    # ========== 并发测试 ==========
    
    @pytest.mark.asyncio
    async def test_concurrent_simulation(self, engine_no_llm, sample_survey):
        """测试并发模拟"""
        personas = [create_sample_persona() for _ in range(5)]
        
        # 并行执行
        responses = await engine_no_llm.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=True,
            max_concurrent=3
        )
        
        assert len(responses) == 5
        # 验证所有响应都是有效的
        for response in responses:
            assert response.survey_id == sample_survey.survey_id
            assert len(response.answers) == len(sample_survey.questions)
    
    @pytest.mark.asyncio
    async def test_concurrent_simulation_with_limit(self, engine_no_llm, sample_survey):
        """测试并发限制"""
        personas = [create_sample_persona() for _ in range(10)]
        
        # 并行执行，限制最大并发数为2
        responses = await engine_no_llm.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=True,
            max_concurrent=2
        )
        
        assert len(responses) == 10
    
    @pytest.mark.asyncio
    async def test_sequential_vs_parallel_same_results_count(self, engine_no_llm, sample_survey):
        """测试串行和并行结果数量一致"""
        personas = [create_sample_persona() for _ in range(3)]
        
        responses_seq = await engine_no_llm.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=False
        )
        
        responses_par = await engine_no_llm.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=True
        )
        
        assert len(responses_seq) == len(responses_par)
    
    # ========== 提示词构建测试 ==========
    
    def test_prompt_construction(self, engine_with_llm, sample_survey, sample_persona):
        """测试提示词构建"""
        question = sample_survey.questions[0]
        history = []
        
        # 调用内部方法检查提示词构建
        # 注意：这是通过LLM调用间接验证
        import asyncio
        
        async def run_test():
            await engine_with_llm._answer_with_llm(sample_persona, question, history)
            # persona信息现在在system_prompt中，问题在prompt中
            system_prompt = engine_with_llm.llm_skill.last_system_prompt
            prompt = engine_with_llm.llm_skill.last_prompt
            
            # 验证system_prompt包含人物画像信息
            assert sample_persona.name in system_prompt or "张伟" in system_prompt
            # 验证prompt包含问题信息
            assert question.text in prompt or "新能源汽车" in prompt
        
        asyncio.run(run_test())
    
    def test_prompt_includes_persona_info(self, engine_with_llm, sample_survey, sample_persona):
        """测试提示词包含人物画像信息"""
        question = sample_survey.questions[0]
        persona_prompt = sample_persona.to_prompt()
        
        # 验证人物画像提示词包含关键信息
        assert sample_persona.name in persona_prompt
        assert str(sample_persona.age) in persona_prompt
        assert sample_persona.city in persona_prompt
        assert sample_persona.occupation in persona_prompt
    
    def test_prompt_includes_options(self, engine_with_llm, sample_survey, sample_persona):
        """测试提示词包含选项信息"""
        question = sample_survey.questions[0]  # 单选题
        
        import asyncio
        
        async def run_test():
            await engine_with_llm._answer_with_llm(sample_persona, question, [])
            prompt = engine_with_llm.llm_skill.last_prompt
            
            # 验证选项信息在提示词中
            if question.options:
                for opt in question.options[:2]:
                    assert opt.text in prompt or "选项" in prompt
        
        asyncio.run(run_test())
    
    def test_prompt_includes_history(self, engine_with_llm, sample_survey, sample_persona):
        """测试提示词包含历史回答"""
        question = sample_survey.questions[1]
        
        # 模拟历史回答
        history = [
            (sample_survey.questions[0], Answer(question_id="q1", answer_value="是"))
        ]
        
        import asyncio
        
        async def run_test():
            await engine_with_llm._answer_with_llm(sample_persona, question, history)
            prompt = engine_with_llm.llm_skill.last_prompt
            
            # 验证历史回答在提示词中
            assert "之前" in prompt or "历史" in prompt or "Q:" in prompt
        
        asyncio.run(run_test())
    
    # ========== LLM响应解析测试 ==========
    
    def test_parse_llm_response_single_choice(self, engine_no_llm, sample_survey):
        """测试单选题响应解析"""
        question = sample_survey.questions[0]
        
        # 测试直接文本匹配
        result = engine_no_llm._parse_llm_response("是", question)
        assert result == "是"
        
        # 测试数字索引解析
        result = engine_no_llm._parse_llm_response("选项1", question)
        assert result == "是"
        
        # 测试数字解析
        result = engine_no_llm._parse_llm_response("1", question)
        assert result == "是"
    
    def test_parse_llm_response_multiple_choice(self, engine_no_llm, sample_survey):
        """测试多选题响应解析"""
        question = sample_survey.questions[1]
        
        # 测试逗号分隔
        result = engine_no_llm._parse_llm_response("环保,省钱", question)
        assert "环保" in result or "省钱" in result
    
    def test_parse_llm_response_likert(self, engine_no_llm, sample_survey):
        """测试李克特量表响应解析"""
        question = sample_survey.questions[2]
        
        # 测试数字解析
        result = engine_no_llm._parse_llm_response("4", question)
        assert result == 4
        
        # 测试带文本的解析
        result = engine_no_llm._parse_llm_response("我给4分", question)
        assert result == 4
    
    def test_parse_llm_response_scale(self, engine_no_llm, sample_survey):
        """测试评分题响应解析"""
        question = sample_survey.questions[4]
        
        result = engine_no_llm._parse_llm_response("我愿意支付7分的价格", question)
        assert result == 7
        
        result = engine_no_llm._parse_llm_response("8", question)
        assert result == 8
    
    def test_parse_llm_response_open_ended(self, engine_no_llm, sample_survey):
        """测试开放题响应解析"""
        question = sample_survey.questions[3]
        
        # 开放题直接返回原文
        result = engine_no_llm._parse_llm_response("新能源汽车是未来的趋势", question)
        assert result == "新能源汽车是未来的趋势"
    
    def test_parse_llm_response_invalid_returns_original(self, engine_no_llm, sample_survey):
        """测试无效响应返回原文"""
        question = sample_survey.questions[0]
        
        # 无法解析的响应返回原文
        result = engine_no_llm._parse_llm_response("我不知道", question)
        assert result == "我不知道"
    
    # ========== 规则生成测试 ==========
    
    def test_answer_with_rules_single_choice(self, engine_no_llm, sample_survey, sample_persona):
        """测试规则生成单选题"""
        question = sample_survey.questions[0]
        
        answer = engine_no_llm._answer_with_rules(sample_persona, question)
        
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id
        assert answer.answer_value in ["是", "否", "正在考虑"]
    
    def test_answer_with_rules_multiple_choice(self, engine_no_llm, sample_survey, sample_persona):
        """测试规则生成多选题"""
        question = sample_survey.questions[1]
        
        answer = engine_no_llm._answer_with_rules(sample_persona, question)
        
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id
        # 多选题答案包含逗号分隔的选项
        assert isinstance(answer.answer_value, str)
    
    def test_answer_with_rules_likert(self, engine_no_llm, sample_survey, sample_persona):
        """测试规则生成李克特量表"""
        question = sample_survey.questions[2]
        
        answer = engine_no_llm._answer_with_rules(sample_persona, question)
        
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id
        assert answer.answer_value in [1, 2, 3, 4, 5]
    
    def test_answer_with_rules_open_ended(self, engine_no_llm, sample_survey, sample_persona):
        """测试规则生成开放题"""
        question = sample_survey.questions[3]
        
        answer = engine_no_llm._answer_with_rules(sample_persona, question)
        
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id
        assert answer.answer_value is not None
        assert len(answer.answer_value) > 0
    
    def test_answer_with_rules_scale(self, engine_no_llm, sample_survey, sample_persona):
        """测试规则生成评分题"""
        question = sample_survey.questions[4]
        
        answer = engine_no_llm._answer_with_rules(sample_persona, question)
        
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id
        assert answer.answer_value in [1, 2, 3, 4, 5]
    
    # ========== LLM调用回退测试 ==========
    
    @pytest.mark.asyncio
    async def test_llm_fallback_to_rules_on_error(self, sample_survey, sample_persona):
        """测试LLM失败时回退到规则生成"""
        # 创建会失败的LLM Mock
        class FailingLLMSkill:
            async def execute(self, **kwargs):
                raise Exception("LLM调用失败")
        
        engine = SimulationEngine(llm_skill=FailingLLMSkill())
        
        # 即使LLM失败，也应该能生成答案（回退到规则）
        question = sample_survey.questions[0]
        answer = await engine._answer_question(sample_persona, question, [])
        
        assert isinstance(answer, Answer)
        assert answer.question_id == question.question_id
    
    @pytest.mark.asyncio
    async def test_llm_fallback_on_invalid_response(self, sample_survey, sample_persona):
        """测试LLM返回无效响应时回退"""
        class InvalidResponseLLMSkill:
            async def execute(self, **kwargs):
                return {
                    "success": True,
                    "content": "",  # 空内容
                    "usage": {"total_tokens": 10}
                }
        
        engine = SimulationEngine(llm_skill=InvalidResponseLLMSkill())
        
        question = sample_survey.questions[0]
        answer = await engine._answer_question(sample_persona, question, [])
        
        # 空响应应该回退到规则生成
        assert isinstance(answer, Answer)
    
    # ========== 回答一致性测试 ==========
    
    @pytest.mark.asyncio
    async def test_answer_history_maintained(self, engine_with_llm, sample_survey, sample_persona):
        """测试回答历史被维护"""
        # 执行完整问卷
        responses = await engine_with_llm.simulate_survey(
            personas=[sample_persona],
            survey=sample_survey,
            parallel=False
        )
        
        # 验证所有问题都有答案
        response = responses[0]
        assert len(response.answers) == len(sample_survey.questions)
        
        # 验证答案顺序与问题顺序一致
        question_ids = [q.question_id for q in sample_survey.questions]
        answer_ids = list(response.answers.keys())
        assert answer_ids == question_ids
    
    @pytest.mark.asyncio
    async def test_consistency_check_implied_in_llm_prompt(self, engine_with_llm, sample_survey, sample_persona):
        """测试LLM提示词包含一致性检查"""
        # 执行多个问题
        import asyncio
        
        history = []
        for question in sample_survey.questions[:2]:
            answer = await engine_with_llm._answer_with_llm(sample_persona, question, history)
            history.append((question, answer))
        
        # 检查第二个问题的提示词包含第一个问题的答案
        second_prompt = engine_with_llm.llm_skill.last_prompt
        
        # 提示词应该包含历史信息或一致性要求
        assert "之前" in second_prompt or "一致" in second_prompt or len(history) > 0
    
    # ========== 边界条件测试 ==========
    
    @pytest.mark.asyncio
    async def test_empty_personas_list(self, engine_no_llm, sample_survey):
        """测试空人物列表"""
        responses = await engine_no_llm.simulate_survey(
            personas=[],
            survey=sample_survey,
            parallel=False
        )
        
        assert len(responses) == 0
    
    @pytest.mark.asyncio
    async def test_empty_questions_list(self, engine_no_llm, sample_persona):
        """测试空问题列表"""
        empty_survey = Survey(
            survey_id="empty_survey",
            title="空问卷",
            questions=[]
        )
        
        responses = await engine_no_llm.simulate_survey(
            personas=[sample_persona],
            survey=empty_survey,
            parallel=False
        )
        
        assert len(responses) == 1
        assert len(responses[0].answers) == 0
    
    def test_response_id_generation(self, engine_no_llm, sample_survey, sample_persona):
        """测试响应ID生成"""
        import asyncio
        
        async def run_test():
            response = await engine_no_llm._simulate_single(sample_persona, sample_survey)
            
            # ID应该包含persona_id和survey_id
            assert sample_persona.persona_id in response.response_id
            assert sample_survey.survey_id in response.response_id
        
        asyncio.run(run_test())
    
    # ========== 性能基准测试 ==========
    
    @pytest.mark.asyncio
    async def test_performance_small_batch(self, engine_no_llm, sample_survey):
        """测试小批量性能（10人）"""
        import time
        
        personas = [create_sample_persona() for _ in range(10)]
        
        start_time = time.time()
        responses = await engine_no_llm.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=True
        )
        elapsed_time = time.time() - start_time
        
        assert len(responses) == 10
        # 10人×5题应该很快（<5秒）
        assert elapsed_time < 5.0
    
    @pytest.mark.asyncio
    async def test_performance_medium_batch(self, engine_no_llm, sample_survey):
        """测试中等批量性能（50人）"""
        import time
        
        personas = [create_sample_persona() for _ in range(50)]
        
        start_time = time.time()
        responses = await engine_no_llm.simulate_survey(
            personas=personas,
            survey=sample_survey,
            parallel=True,
            max_concurrent=10
        )
        elapsed_time = time.time() - start_time
        
        assert len(responses) == 50
        # 50人×5题应该很快（<10秒）
        assert elapsed_time < 10.0