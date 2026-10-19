"""
PersonaSkill 和 SimulationSkill 测试 - TDD模式（Week 2 Day 4）

测试覆盖：
- Skill初始化
- Skill注册
- 执行生成/模拟
- 错误处理
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestPersonaSkill:
    """测试PersonaSkill"""
    
    @pytest.fixture
    def skill(self):
        """创建Skill实例"""
        from src.skills.builtin.persona_skill import PersonaSkill
        from src.skills.base import SkillConfig
        return PersonaSkill(SkillConfig(name="persona_skill", version="1.0.0"))
    
    def test_skill_initialization(self, skill):
        """测试Skill初始化"""
        assert skill.name == "persona_skill"
        assert skill.description is not None
        assert skill.config.enabled is True
    
    def test_skill_has_required_properties(self, skill):
        """测试Skill具有必需属性"""
        assert hasattr(skill, 'name')
        assert hasattr(skill, 'description')
        assert hasattr(skill, 'execute')
    
    @pytest.mark.asyncio
    async def test_execute_generation(self, skill):
        """测试执行生成"""
        result = await skill.execute(
            template="一线白领",
            count=5,
        )
        
        assert result["success"] is True
        assert "personas" in result
        assert len(result["personas"]) == 5
    
    @pytest.mark.asyncio
    async def test_execute_generation_with_context(self, skill):
        """测试带上下文的生成"""
        result = await skill.execute(
            template="一线白领",
            count=3,
            context="新能源汽车购买意向调研",
        )
        
        assert result["success"] is True
        assert len(result["personas"]) == 3
    
    @pytest.mark.asyncio
    async def test_execute_generation_with_stratify(self, skill):
        """测试分层抽样生成"""
        result = await skill.execute(
            template="一线白领",
            count=10,
            stratify_by=["gender"],
        )
        
        assert result["success"] is True
        assert len(result["personas"]) == 10
    
    @pytest.mark.asyncio
    async def test_execute_invalid_parameters(self, skill):
        """测试无效参数"""
        result = await skill.execute(
            template="一线白领",
            count=0,  # 无效数量
        )
        
        assert result["success"] is False
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_execute_missing_required_params(self, skill):
        """测试缺少必需参数"""
        result = await skill.execute()
        
        assert result["success"] is False
    
    def test_is_enabled(self, skill):
        """测试是否启用"""
        assert skill.is_enabled() is True
    
    def test_skill_success_response(self, skill):
        """测试成功响应构建"""
        response = skill._success({"data": "test"}, "操作成功")
        
        assert response["success"] is True
        assert response["message"] == "操作成功"
        assert response["data"] == "test"
    
    def test_skill_failure_response(self, skill):
        """测试失败响应构建"""
        response = skill._failure("测试错误", "操作失败")
        
        assert response["success"] is False
        assert response["error"] == "测试错误"
        assert response["message"] == "操作失败"


class TestSimulationSkill:
    """测试SimulationSkill"""
    
    @pytest.fixture
    def skill(self):
        """创建Skill实例"""
        from src.skills.builtin.simulation_skill import SimulationSkill
        from src.skills.base import SkillConfig
        return SimulationSkill(SkillConfig(name="simulation_skill", version="1.0.0"))
    
    @pytest.fixture
    def skill_with_llm(self):
        from src.skills.builtin.simulation_skill import SimulationSkill
        from src.skills.base import SkillConfig
        return SimulationSkill(SkillConfig(name="simulation_skill", version="1.0.0"))
    
    @pytest.fixture
    def sample_survey(self):
        """创建测试问卷"""
        from src.survey.models import Survey, Question, QuestionOption, QuestionType
        return Survey(
            survey_id="test_survey",
            title="测试问卷",
            questions=[
                Question(
                    question_id="q1",
                    text="您是否满意？",
                    question_type=QuestionType.SINGLE_CHOICE,
                    options=[
                        QuestionOption(option_id="opt1", text="是"),
                        QuestionOption(option_id="opt2", text="否"),
                    ]
                ),
            ]
        )
    
    @pytest.fixture
    def sample_personas(self):
        """创建测试人物画像"""
        from src.survey.services.persona_factory import Persona
        return [
            Persona(
                persona_id="p1",
                name="测试用户",
                age=30,
                gender="男",
                city="北京",
                occupation="程序员",
                income="20万",
                education="本科",
                personality_traits=["理性"],
                interests=["科技"],
                values=["创新"],
                decision_style="研究型",
            )
        ]
    
    def test_skill_initialization(self, skill):
        """测试Skill初始化"""
        assert skill.name == "simulation_skill"
        assert skill.description is not None
        assert skill.config.enabled is True
    
    def test_skill_with_llm_initialization(self, skill_with_llm):
        assert skill_with_llm is not None
    
    @pytest.mark.asyncio
    async def test_execute_simulation(self, skill, sample_survey, sample_personas):
        """测试执行模拟"""
        result = await skill.execute(
            survey=sample_survey.to_dict(),
            personas=sample_personas,
        )
        
        assert result["success"] is True
        assert "responses" in result
        assert len(result["responses"]) == 1
    
    @pytest.mark.asyncio
    async def test_execute_simulation_with_llm(self, skill_with_llm, sample_survey, sample_personas):
        """测试使用LLM执行模拟"""
        result = await skill_with_llm.execute(
            survey=sample_survey.to_dict(),
            personas=sample_personas,
        )
        
        assert result["success"] is True
        assert len(result["responses"]) == 1
    
    @pytest.mark.asyncio
    async def test_execute_simulation_parallel(self, skill, sample_survey, sample_personas):
        """测试并行模拟"""
        # 创建多个人物画像
        from src.survey.services.persona_factory import Persona
        personas = [
            Persona(
                persona_id=f"p{i}",
                name=f"用户{i}",
                age=25 + i,
                gender="男" if i % 2 == 0 else "女",
                city="北京",
                occupation="测试",
                income="10万",
                education="本科",
                personality_traits=["理性"],
                interests=["科技"],
                values=["创新"],
                decision_style="研究型",
            )
            for i in range(5)
        ]
        
        result = await skill.execute(
            survey=sample_survey.to_dict(),
            personas=personas,
            parallel=True,
        )
        
        assert result["success"] is True
        assert len(result["responses"]) == 5
    
    @pytest.mark.asyncio
    async def test_execute_invalid_parameters(self, skill):
        """测试无效参数"""
        result = await skill.execute(
            survey="invalid",  # 应该是字典
            personas=[],
        )
        
        assert result["success"] is False
    
    @pytest.mark.asyncio
    async def test_execute_missing_survey(self, skill, sample_personas):
        """测试缺少问卷"""
        result = await skill.execute(
            personas=sample_personas,
        )
        
        assert result["success"] is False
    
    @pytest.mark.asyncio
    async def test_execute_missing_personas(self, skill, sample_survey):
        """测试缺少人物画像"""
        result = await skill.execute(
            survey=sample_survey.to_dict(),
        )
        
        assert result["success"] is False
    
    def test_is_enabled(self, skill):
        """测试是否启用"""
        assert skill.is_enabled() is True


class TestSkillRegistration:
    """测试Skill注册"""
    
    def test_persona_skill_registration(self):
        """测试PersonaSkill注册"""
        from src.skills.base import get_registry
        from src.skills.builtin.persona_skill import PersonaSkill
        
        registry = get_registry()
        registry.register("persona_skill", PersonaSkill)
        
        assert registry.get("persona_skill") is PersonaSkill
    
    def test_simulation_skill_registration(self):
        """测试SimulationSkill注册"""
        from src.skills.base import get_registry
        from src.skills.builtin.simulation_skill import SimulationSkill
        
        registry = get_registry()
        registry.register("simulation_skill", SimulationSkill)
        
        assert registry.get("simulation_skill") is SimulationSkill
    
    def test_list_all_skills(self):
        """测试列出所有Skills"""
        from src.skills.base import get_registry
        
        registry = get_registry()
        all_skills = registry.list_all()
        
        assert isinstance(all_skills, dict)
    
    def test_unregister_skill(self):
        """测试取消注册Skill"""
        from src.skills.base import get_registry
        from src.skills.builtin.persona_skill import PersonaSkill
        
        registry = get_registry()
        registry.register("test_skill_temp", PersonaSkill)
        
        assert registry.get("test_skill_temp") is not None
        
        result = registry.unregister("test_skill_temp")
        assert result is True
        assert registry.get("test_skill_temp") is None