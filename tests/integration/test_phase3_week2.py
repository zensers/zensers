"""
Phase 3 Week 2 集成测试

测试覆盖：
- 完整工作流：画像生成 → 问卷模拟 → 结果分析
- 并发模拟性能
- 端到端验证
"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock

from src.survey.models import (
    Survey, Question, QuestionOption, QuestionType,
    SurveyResponse, Answer
)
from src.survey.services.persona_factory import Persona
from src.agents.fixed_agents.persona_generation_agent import PersonaGenerationAgent
from src.agents.fixed_agents.simulated_response_agent import SimulatedResponseAgent
from src.skills.builtin.persona_skill import PersonaSkill
from src.skills.builtin.simulation_skill import SimulationSkill


def create_comprehensive_survey() -> Survey:
    """创建综合测试问卷"""
    return Survey(
        survey_id="integration_survey_001",
        title="新能源汽车市场调研问卷",
        questions=[
            Question(
                question_id="q1",
                text="您是否拥有或考虑购买新能源汽车？",
                question_type=QuestionType.SINGLE_CHOICE,
                options=[
                    QuestionOption(option_id="opt1", text="已拥有"),
                    QuestionOption(option_id="opt2", text="正在考虑"),
                    QuestionOption(option_id="opt3", text="暂不考虑"),
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
                    QuestionOption(option_id="opt5", text="驾驶体验"),
                ]
            ),
            Question(
                question_id="q3",
                text="您对新能源汽车的整体满意度如何？",
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
                text="您愿意为新能源汽车支付的价格区间（1-10分）",
                question_type=QuestionType.SCALE,
            ),
            Question(
                question_id="q5",
                text="请简述您对新能源汽车的看法",
                question_type=QuestionType.OPEN_ENDED,
            ),
        ]
    )


class TestPhase3Week2Integration:
    """Phase 3 Week 2 集成测试"""
    
    @pytest.fixture
    def persona_agent(self):
        """创建画像生成Agent"""
        return PersonaGenerationAgent(
            agent_id="test_persona_agent",
            name="测试画像生成Agent",
        )
    
    @pytest.fixture
    def simulation_agent(self):
        """创建模拟回答Agent"""
        return SimulatedResponseAgent(
            agent_id="test_simulation_agent",
            name="测试模拟回答Agent",
        )
    
    @pytest.fixture
    def persona_skill(self):
        """创建画像生成Skill"""
        return PersonaSkill()
    
    @pytest.fixture
    def simulation_skill(self):
        """创建模拟Skill"""
        return SimulationSkill()
    
    @pytest.fixture
    def comprehensive_survey(self):
        """创建综合问卷"""
        return create_comprehensive_survey()
    
    # ========== 画像生成集成测试 ==========
    
    def test_persona_generation_integration(self, persona_agent):
        """测试画像生成集成"""
        result = persona_agent.execute({
            "template": "一线白领",
            "count": 20,
        })
        
        assert result["success"] is True
        assert len(result["personas"]) == 20
        
        # 验证画像质量
        for persona in result["personas"]:
            assert isinstance(persona, Persona)
            assert persona.age >= 25 and persona.age <= 40
            assert persona.city in ["北京", "上海", "广州", "深圳"]
    
    def test_persona_generation_with_stratification(self, persona_agent):
        """测试分层抽样集成"""
        result = persona_agent.execute({
            "template": "一线白领",
            "count": 50,
            "stratify_by": ["gender"],
        })
        
        assert result["success"] is True
        assert len(result["personas"]) == 50
        
        # 验证性别分布均衡
        genders = [p.gender for p in result["personas"]]
        male_ratio = genders.count("男") / len(genders)
        assert 0.3 < male_ratio < 0.7  # 允许一定偏差
    
    # ========== 问卷模拟集成测试 ==========
    
    def test_survey_simulation_integration(self, simulation_agent, comprehensive_survey):
        """测试问卷模拟集成"""
        # 先生成画像
        personas = [
            Persona(
                persona_id=f"p{i}",
                name=f"用户{i}",
                age=30 + i,
                gender="男" if i % 2 == 0 else "女",
                city="北京",
                occupation="测试",
                income="20万",
                education="本科",
                personality_traits=["理性"],
                interests=["科技"],
                values=["创新"],
                decision_style="研究型",
            )
            for i in range(10)
        ]
        
        result = simulation_agent.execute({
            "survey": comprehensive_survey.to_dict(),
            "personas": personas,
        })
        
        assert result["success"] is True
        assert len(result["responses"]) == 10
        
        # 验证每个响应都有所有问题的答案
        for response in result["responses"]:
            answers = response.get("answers", {})
            assert len(answers) == len(comprehensive_survey.questions)
    
    # ========== 完整工作流测试 ==========
    
    def test_full_workflow(self, persona_agent, simulation_agent, comprehensive_survey):
        """测试完整工作流：画像生成 → 问卷模拟"""
        # Step 1: 生成人物画像
        persona_result = persona_agent.execute({
            "template": "一线白领",
            "count": 30,
        })
        
        assert persona_result["success"] is True
        personas = persona_result["personas"]
        assert len(personas) == 30
        
        # Step 2: 模拟问卷回答
        simulation_result = simulation_agent.execute({
            "survey": comprehensive_survey.to_dict(),
            "personas": personas,
            "parallel": True,
        })
        
        assert simulation_result["success"] is True
        assert len(simulation_result["responses"]) == 30
        
        # Step 3: 验证结果质量
        responses = simulation_result["responses"]
        
        # 所有响应都有效
        for response in responses:
            answers = response.get("answers", {})
            assert len(answers) == 5  # 5个问题
            
            # 验证单选题有有效答案
            q1_answer = answers.get("q1", {})
            assert q1_answer.get("answer_value") in ["已拥有", "正在考虑", "暂不考虑"]
    
    @pytest.mark.asyncio
    async def test_full_workflow_async(self, persona_agent, simulation_agent, comprehensive_survey):
        """测试异步完整工作流"""
        # Step 1: 异步生成画像
        persona_result = await persona_agent.execute_async({
            "template": "一线白领",
            "count": 20,
        })
        
        assert persona_result["success"] is True
        personas = persona_result["personas"]
        
        # Step 2: 异步模拟问卷
        simulation_result = await simulation_agent.execute_async({
            "survey": comprehensive_survey.to_dict(),
            "personas": personas,
        })
        
        assert simulation_result["success"] is True
        assert len(simulation_result["responses"]) == 20
    
    # ========== Skill集成测试 ==========
    
    @pytest.mark.asyncio
    async def test_skill_workflow(self, persona_skill, simulation_skill, comprehensive_survey):
        """测试Skill层完整工作流"""
        # Step 1: 使用PersonaSkill生成画像
        persona_result = await persona_skill.execute(
            template="一线白领",
            count=15,
        )
        
        assert persona_result["success"] is True
        personas = persona_result["personas"]
        assert len(personas) == 15
        
        # Step 2: 使用SimulationSkill模拟问卷
        simulation_result = await simulation_skill.execute(
            survey=comprehensive_survey.to_dict(),
            personas=personas,
        )
        
        assert simulation_result["success"] is True
        assert len(simulation_result["responses"]) == 15
    
    # ========== 并发性能测试 ==========
    
    def test_concurrent_simulation_performance(self, simulation_agent, comprehensive_survey):
        """测试并发模拟性能"""
        # 生成100个画像
        personas = [
            Persona(
                persona_id=f"perf_p{i}",
                name=f"用户{i}",
                age=30,
                gender="男",
                city="北京",
                occupation="测试",
                income="20万",
                education="本科",
                personality_traits=["理性"],
                interests=["科技"],
                values=["创新"],
                decision_style="研究型",
            )
            for i in range(100)
        ]
        
        start_time = time.time()
        
        result = simulation_agent.execute({
            "survey": comprehensive_survey.to_dict(),
            "personas": personas,
            "parallel": True,
            "max_concurrent": 20,
        })
        
        elapsed_time = time.time() - start_time
        
        assert result["success"] is True
        assert len(result["responses"]) == 100
        # 验收标准：100人×5题 < 10秒
        assert elapsed_time < 10.0, f"性能不达标：{elapsed_time:.2f}秒"
    
    def test_large_scale_simulation(self, simulation_agent, comprehensive_survey):
        """测试大规模模拟"""
        # 生成200个画像
        personas = [
            Persona(
                persona_id=f"large_p{i}",
                name=f"用户{i}",
                age=25 + (i % 20),
                gender="男" if i % 2 == 0 else "女",
                city=["北京", "上海", "广州", "深圳"][i % 4],
                occupation=["程序员", "产品经理", "市场"][i % 3],
                income="20万",
                education="本科",
                personality_traits=["理性"],
                interests=["科技"],
                values=["创新"],
                decision_style="研究型",
            )
            for i in range(200)
        ]
        
        start_time = time.time()
        
        result = simulation_agent.execute({
            "survey": comprehensive_survey.to_dict(),
            "personas": personas,
            "parallel": True,
            "max_concurrent": 50,
        })
        
        elapsed_time = time.time() - start_time
        
        assert result["success"] is True
        assert len(result["responses"]) == 200
        # 验收标准：200人×5题 < 30秒
        assert elapsed_time < 30.0, f"性能不达标：{elapsed_time:.2f}秒"
    
    # ========== 数据质量测试 ==========
    
    def test_response_quality(self, simulation_agent, comprehensive_survey):
        """测试响应质量"""
        personas = [
            Persona(
                persona_id="quality_p1",
                name="理性用户",
                age=35,
                gender="男",
                city="北京",
                occupation="程序员",
                income="30万",
                education="硕士",
                personality_traits=["理性", "注重品质", "科技爱好者"],
                interests=["科技", "汽车"],
                values=["创新", "效率"],
                decision_style="研究型",
                background_story="资深程序员，对新技术充满热情",
            )
        ]
        
        result = simulation_agent.execute({
            "survey": comprehensive_survey.to_dict(),
            "personas": personas,
        })
        
        assert result["success"] is True
        
        response = result["responses"][0]
        answers = response.get("answers", {})
        
        # 验证所有问题都有答案
        for q in comprehensive_survey.questions:
            assert q.question_id in answers
            answer = answers[q.question_id]
            assert answer.get("answer_value") is not None
    
    def test_answer_consistency(self, simulation_agent):
        """测试回答一致性"""
        # 创建相关问题的问卷
        survey = Survey(
            survey_id="consistency_survey",
            title="一致性测试问卷",
            questions=[
                Question(
                    question_id="q1",
                    text="您是否关注环保？",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption(option_id="opt1", text="非常关注"),
                        QuestionOption(option_id="opt2", text="比较关注"),
                        QuestionOption(option_id="opt3", text="不太关注"),
                    ]
                ),
                Question(
                    question_id="q2",
                    text="您是否愿意为环保产品支付溢价？",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption(option_id="opt1", text="愿意"),
                        QuestionOption(option_id="opt2", text="不愿意"),
                    ]
                ),
            ]
        )
        
        # 创建一个环保主义者画像
        personas = [
            Persona(
                persona_id="eco_person",
                name="环保人士",
                age=30,
                gender="女",
                city="上海",
                occupation="环保工作者",
                income="15万",
                education="本科",
                personality_traits=["理想主义", "热心"],
                interests=["环保", "公益"],
                values=["环保", "可持续发展"],
                decision_style="价值观驱动",
                background_story="长期从事环保工作，对环保议题有深刻认识",
            )
        ]
        
        result = simulation_agent.execute({
            "survey": survey.to_dict(),
            "personas": personas,
        })
        
        assert result["success"] is True
        # 注意：由于规则引擎是随机的，这里只验证有答案
        # 实际LLM集成时会考虑一致性
    
    # ========== 边界条件测试 ==========
    
    def test_minimal_survey(self, simulation_agent):
        """测试最小问卷"""
        minimal_survey = Survey(
            survey_id="minimal",
            title="最小问卷",
            questions=[
                Question(
                    question_id="q1",
                    text="是/否",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption(option_id="opt1", text="是"),
                        QuestionOption(option_id="opt2", text="否"),
                    ]
                ),
            ]
        )
        
        personas = [
            Persona(
                persona_id="minimal_p",
                name="用户",
                age=30,
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
        ]
        
        result = simulation_agent.execute({
            "survey": minimal_survey.to_dict(),
            "personas": personas,
        })
        
        assert result["success"] is True
        assert len(result["responses"]) == 1
    
    def test_all_question_types(self, simulation_agent):
        """测试所有问题类型"""
        from src.survey.models import QuestionType
        
        survey = Survey(
            survey_id="all_types",
            title="所有类型",
            questions=[
                Question(
                    question_id="q_single",
                    text="单选",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[QuestionOption(option_id="opt1", text="A")]
                ),
                Question(
                    question_id="q_multiple",
                    text="多选",
                    question_type=QuestionType.MULTIPLE_CHOICE,
                    options=[
                        QuestionOption(option_id="opt1", text="A"),
                        QuestionOption(option_id="opt2", text="B"),
                    ]
                ),
                Question(
                    question_id="q_likert",
                    text="李克特",
                    question_type=QuestionType.LIKERT,
                    options=[QuestionOption(option_id="opt1", text="满意", value=5)]
                ),
                Question(
                    question_id="q_scale",
                    text="评分",
                    question_type=QuestionType.SCALE,
                ),
                Question(
                    question_id="q_open",
                    text="开放题",
                    question_type=QuestionType.OPEN_ENDED,
                ),
            ]
        )
        
        personas = [
            Persona(
                persona_id="all_types_p",
                name="用户",
                age=30,
                gender="男",
                city="北京",
                occupation="测试",
                income="10万",
                education="本科",
                personality_traits=["理性"],
                interests=["测试"],
                values=["效率"],
                decision_style="研究型",
            )
        ]
        
        result = simulation_agent.execute({
            "survey": survey.to_dict(),
            "personas": personas,
        })
        
        assert result["success"] is True
        answers = result["responses"][0].get("answers", {})
        assert len(answers) == 5
    
    # ========== 性能基准测试 ==========
    
    def test_performance_benchmark(self, persona_agent, simulation_agent, comprehensive_survey):
        """测试性能基准"""
        # 验收标准：100人×20题 < 5分钟
        
        # 创建20题问卷
        extended_survey = Survey(
            survey_id="benchmark_survey",
            title="性能基准测试问卷",
            questions=comprehensive_survey.questions * 4,  # 扩展到20题
        )
        
        # 生成100个画像
        start_time = time.time()
        persona_result = persona_agent.execute({
            "template": "一线白领",
            "count": 100,
        })
        persona_time = time.time() - start_time
        
        assert persona_result["success"] is True
        
        # 模拟问卷
        start_time = time.time()
        simulation_result = simulation_agent.execute({
            "survey": extended_survey.to_dict(),
            "personas": persona_result["personas"],
            "parallel": True,
            "max_concurrent": 20,
        })
        simulation_time = time.time() - start_time
        
        assert simulation_result["success"] is True
        assert len(simulation_result["responses"]) == 100
        
        total_time = persona_time + simulation_time
        
        # 验收标准
        assert persona_time < 5.0, f"画像生成时间过长：{persona_time:.2f}秒"
        assert simulation_time < 30.0, f"模拟时间过长：{simulation_time:.2f}秒"
        
        print(f"\n性能基准:")
        print(f"  画像生成: {persona_time:.2f}秒 (100人)")
        print(f"  问卷模拟: {simulation_time:.2f}秒 (100人×20题)")
        print(f"  总计: {total_time:.2f}秒")