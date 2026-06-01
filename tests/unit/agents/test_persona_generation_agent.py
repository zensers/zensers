"""
PersonaGenerationAgent 测试 - TDD模式（Week 2 Day 3）

测试覆盖：
- Agent初始化
- 单个画像生成
- 批量画像生成
- 分层抽样
- LLM增强生成
- 输入验证
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.survey.services.persona_factory import Persona


class TestPersonaGenerationAgent:
    """测试PersonaGenerationAgent"""
    
    @pytest.fixture
    def agent(self):
        """创建Agent实例"""
        from src.agents.fixed_agents.persona_generation_agent import PersonaGenerationAgent
        return PersonaGenerationAgent(
            agent_id="persona_gen_001",
            name="画像生成Agent",
        )
    
    @pytest.fixture
    def agent_with_llm(self):
        """创建带LLM的Agent实例"""
        from src.agents.fixed_agents.persona_generation_agent import PersonaGenerationAgent
        
        # 创建Mock LLM Skill
        mock_llm = MagicMock()
        mock_llm.execute = AsyncMock(return_value={
            "success": True,
            "content": "张伟是一名资深程序员，热爱新技术，对新能源汽车充满兴趣。",
            "usage": {"total_tokens": 50}
        })
        
        return PersonaGenerationAgent(
            agent_id="persona_gen_002",
            name="画像生成Agent",
            llm_skill=mock_llm,
        )
    
    # ========== 基础测试 ==========
    
    def test_agent_initialization(self, agent):
        """测试Agent初始化"""
        assert agent.agent_id == "persona_gen_001"
        assert agent.name == "画像生成Agent"
        assert agent.agent_type == "persona_generation"
        assert len(agent.capabilities) > 0
    
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
    
    def test_validate_input_missing_count(self, agent):
        """测试缺少数量的输入验证"""
        task_input = {
            "template": "一线白领",
        }
        valid, error = agent.validate_input(task_input)
        assert valid is False
        assert "count" in error.lower() or "数量" in error
    
    def test_validate_input_invalid_count_type(self, agent):
        """测试数量类型错误的输入验证"""
        task_input = {
            "template": "一线白领",
            "count": "invalid",
        }
        valid, error = agent.validate_input(task_input)
        assert valid is False
    
    def test_validate_input_invalid_count_value(self, agent):
        """测试数量值无效的输入验证"""
        task_input = {
            "template": "一线白领",
            "count": 0,
        }
        valid, error = agent.validate_input(task_input)
        assert valid is False
    
    def test_validate_input_valid(self, agent):
        """测试有效输入验证"""
        task_input = {
            "template": "一线白领",
            "count": 10,
        }
        valid, error = agent.validate_input(task_input)
        assert valid is True
        assert error == ""
    
    def test_validate_input_with_context(self, agent):
        """测试带上下文的输入验证"""
        task_input = {
            "template": "一线白领",
            "count": 5,
            "context": "新能源汽车购买意向调研",
        }
        valid, error = agent.validate_input(task_input)
        assert valid is True
    
    # ========== 单个画像生成测试 ==========
    
    def test_generate_single_persona(self, agent):
        """测试生成单个画像"""
        task_input = {
            "template": "一线白领",
            "count": 1,
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert "personas" in result
        assert len(result["personas"]) == 1
        assert result["total_count"] == 1
    
    def test_generated_persona_structure(self, agent):
        """测试生成画像的结构"""
        task_input = {
            "template": "一线白领",
            "count": 1,
        }
        
        result = agent.execute(task_input)
        
        persona = result["personas"][0]
        assert isinstance(persona, Persona)
        assert persona.persona_id is not None
        assert persona.name is not None
        assert persona.age > 0
        assert persona.gender in ["男", "女"]
        assert persona.city is not None
        assert persona.occupation is not None
    
    def test_generated_persona_has_required_fields(self, agent):
        """测试生成画像具有必需字段"""
        task_input = {
            "template": "一线白领",
            "count": 1,
        }
        
        result = agent.execute(task_input)
        
        persona = result["personas"][0]
        # 检查所有必需字段
        assert hasattr(persona, 'persona_id')
        assert hasattr(persona, 'name')
        assert hasattr(persona, 'age')
        assert hasattr(persona, 'gender')
        assert hasattr(persona, 'city')
        assert hasattr(persona, 'occupation')
        assert hasattr(persona, 'income')
        assert hasattr(persona, 'education')
        assert hasattr(persona, 'personality_traits')
        assert hasattr(persona, 'interests')
        assert hasattr(persona, 'values')
        assert hasattr(persona, 'decision_style')
        assert hasattr(persona, 'background_story')
    
    # ========== 批量生成测试 ==========
    
    def test_batch_generation(self, agent):
        """测试批量生成画像"""
        task_input = {
            "template": "一线白领",
            "count": 10,
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 10
        assert result["total_count"] == 10
    
    def test_batch_generation_uniqueness(self, agent):
        """测试批量生成的唯一性"""
        task_input = {
            "template": "一线白领",
            "count": 20,
        }
        
        result = agent.execute(task_input)
        
        # 检查所有画像ID唯一
        persona_ids = [p.persona_id for p in result["personas"]]
        assert len(set(persona_ids)) == len(persona_ids)
    
    def test_batch_generation_diversity(self, agent):
        """测试批量生成的多样性"""
        task_input = {
            "template": "一线白领",
            "count": 30,
        }
        
        result = agent.execute(task_input)
        
        # 检查生成结果具有多样性
        ages = [p.age for p in result["personas"]]
        cities = [p.city for p in result["personas"]]
        
        # 至少有3个不同的年龄
        assert len(set(ages)) >= 3
        # 至少有2个不同的城市
        assert len(set(cities)) >= 2
    
    def test_large_batch_generation(self, agent):
        """测试大批量生成"""
        task_input = {
            "template": "一线白领",
            "count": 100,
        }
        
        import time
        start_time = time.time()
        result = agent.execute(task_input)
        elapsed_time = time.time() - start_time
        
        assert result["success"] is True
        assert len(result["personas"]) == 100
        # 100个画像应该在5秒内生成
        assert elapsed_time < 5.0
    
    # ========== 模板测试 ==========
    
    def test_default_template(self, agent):
        """测试默认模板"""
        task_input = {
            "template": "invalid_template",
            "count": 5,
        }
        
        result = agent.execute(task_input)
        
        # 无效模板应使用默认模板
        assert result["success"] is True
        assert len(result["personas"]) == 5
    
    def test_first_tier_white_collar_template(self, agent):
        """测试一线白领模板"""
        task_input = {
            "template": "一线白领",
            "count": 10,
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        # 检查年龄范围（25-40）
        for persona in result["personas"]:
            assert 25 <= persona.age <= 40
        # 检查城市在一线城市
        first_tier_cities = ["北京", "上海", "广州", "深圳"]
        assert all(p.city in first_tier_cities for p in result["personas"])
    
    def test_second_tier_family_template(self, agent):
        """测试二三线家庭用户模板"""
        task_input = {
            "template": "二三线家庭用户",
            "count": 10,
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        # 检查年龄范围（30-50）
        for persona in result["personas"]:
            assert 30 <= persona.age <= 50
    
    # ========== 分层抽样测试 ==========
    
    def test_stratified_sampling(self, agent):
        """测试分层抽样"""
        task_input = {
            "template": "一线白领",
            "count": 20,
            "stratify_by": ["gender"],
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 20
        
        # 检查性别分布相对均衡
        genders = [p.gender for p in result["personas"]]
        male_count = genders.count("男")
        female_count = genders.count("女")
        
        # 不应该全部是同一性别
        assert male_count > 0
        assert female_count > 0
    
    def test_stratified_sampling_by_age(self, agent):
        """测试按年龄分层抽样"""
        task_input = {
            "template": "一线白领",
            "count": 30,
            "stratify_by": ["age_group"],
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 30
    
    # ========== LLM增强生成测试 ==========
    
    def test_llm_enhanced_generation(self, agent_with_llm):
        """测试LLM增强生成"""
        task_input = {
            "template": "一线白领",
            "count": 5,
            "context": "新能源汽车购买意向调研",
            "enhance_with_llm": True,
        }
        
        result = agent_with_llm.execute(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 5
        # LLM增强应该生成更丰富的背景故事
        for persona in result["personas"]:
            assert persona.background_story is not None
    
    @pytest.mark.asyncio
    async def test_llm_enhancement_async(self, agent_with_llm):
        """测试异步LLM增强"""
        task_input = {
            "template": "一线白领",
            "count": 3,
            "context": "新能源汽车调研",
            "enhance_with_llm": True,
        }
        
        result = await agent_with_llm.execute_async(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 3
    
    # ========== 上下文感知测试 ==========
    
    def test_context_aware_generation(self, agent):
        """测试上下文感知生成"""
        task_input = {
            "template": "一线白领",
            "count": 10,
            "context": "新能源汽车购买意向调研",
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 10
    
    # ========== 结果格式测试 ==========
    
    def test_result_contains_required_fields(self, agent):
        """测试结果包含必需字段"""
        task_input = {
            "template": "一线白领",
            "count": 5,
        }
        
        result = agent.execute(task_input)
        
        assert "success" in result
        assert "personas" in result
        assert "total_count" in result
    
    # ========== Run方法测试 ==========
    
    def test_run_method(self, agent):
        """测试run方法"""
        task_input = {
            "template": "一线白领",
            "count": 5,
        }
        
        result = agent.run(task_input)
        
        assert result["success"] is True
        assert result["agent_id"] == agent.agent_id
        assert result["agent_name"] == agent.name
    
    def test_run_includes_metadata(self, agent):
        """测试run方法包含元数据"""
        task_input = {
            "template": "一线白领",
            "count": 5,
        }
        
        result = agent.run(task_input)
        
        assert "agent_id" in result
        assert "agent_name" in result
        assert "agent_version" in result
    
    def test_run_with_invalid_input(self, agent):
        """测试无效输入运行"""
        result = agent.run({"invalid": "input"})
        
        assert result["success"] is False
        assert "error" in result
    
    # ========== 状态管理测试 ==========
    
    def test_agent_state_transition(self, agent):
        """测试Agent状态转换"""
        # 初始状态
        assert agent.status == "idle"
        
        task_input = {
            "template": "一线白领",
            "count": 5,
        }
        
        result = agent.run(task_input)
        
        assert result["success"] is True
        assert agent.status == "completed"
    
    def test_agent_reset(self, agent):
        """测试Agent重置"""
        task_input = {
            "template": "一线白领",
            "count": 5,
        }
        
        agent.run(task_input)
        assert agent.status == "completed"
        
        agent.reset()
        assert agent.status == "idle"
    
    # ========== 能力测试 ==========
    
    def test_get_capabilities(self, agent):
        """测试获取能力"""
        capabilities = agent.get_capabilities()
        
        assert isinstance(capabilities, list)
        assert len(capabilities) > 0
    
    def test_agent_version(self, agent):
        """测试Agent版本"""
        assert agent.version is not None
    
    # ========== 边界条件测试 ==========
    
    def test_minimum_count(self, agent):
        """测试最小数量"""
        task_input = {
            "template": "一线白领",
            "count": 1,
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 1
    
    def test_maximum_count(self, agent):
        """测试最大数量"""
        task_input = {
            "template": "一线白领",
            "count": 500,
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 500
    
    # ========== 性能测试 ==========
    
    def test_performance_small_batch(self, agent):
        """测试小批量性能"""
        import time
        
        task_input = {
            "template": "一线白领",
            "count": 10,
        }
        
        start_time = time.time()
        result = agent.execute(task_input)
        elapsed_time = time.time() - start_time
        
        assert result["success"] is True
        assert elapsed_time < 1.0
    
    def test_performance_medium_batch(self, agent):
        """测试中等批量性能"""
        import time
        
        task_input = {
            "template": "一线白领",
            "count": 50,
        }
        
        start_time = time.time()
        result = agent.execute(task_input)
        elapsed_time = time.time() - start_time
        
        assert result["success"] is True
        assert elapsed_time < 2.0
    
    # ========== 异步执行测试 ==========
    
    @pytest.mark.asyncio
    async def test_execute_async(self, agent):
        """测试异步执行"""
        task_input = {
            "template": "一线白领",
            "count": 5,
        }
        
        result = await agent.execute_async(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 5
    
    @pytest.mark.asyncio
    async def test_execute_async_with_stratify(self, agent):
        """测试异步执行分层抽样"""
        task_input = {
            "template": "一线白领",
            "count": 10,
            "stratify_by": ["gender"],
        }
        
        result = await agent.execute_async(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 10
    
    @pytest.mark.asyncio
    async def test_execute_async_invalid_input(self, agent):
        """测试异步执行无效输入"""
        task_input = {"invalid": "input"}
        
        result = await agent.execute_async(task_input)
        
        assert result["success"] is False
    
    # ========== 模板管理测试 ==========
    
    def test_get_available_templates(self, agent):
        """测试获取可用模板"""
        templates = agent.get_available_templates()
        
        assert isinstance(templates, list)
        assert len(templates) > 0
        assert "一线白领" in templates
    
    # ========== 分层抽样边界测试 ==========
    
    def test_stratified_sampling_odd_count(self, agent):
        """测试奇数数量分层抽样"""
        task_input = {
            "template": "一线白领",
            "count": 11,
            "stratify_by": ["gender"],
        }
        
        result = agent.execute(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 11
    
    def test_stratified_sampling_unknown_dimension(self, agent):
        """测试未知分层维度"""
        task_input = {
            "template": "一线白领",
            "count": 10,
            "stratify_by": ["unknown_dimension"],
        }
        
        result = agent.execute(task_input)
        
        # 未知维度应该回退到普通生成
        assert result["success"] is True
        assert len(result["personas"]) == 10
    
    # ========== LLM增强边界测试 ==========
    
    def test_llm_enhancement_without_llm_skill(self, agent):
        """测试无LLM时的增强请求"""
        task_input = {
            "template": "一线白领",
            "count": 5,
            "enhance_with_llm": True,
        }
        
        result = agent.execute(task_input)
        
        # 无LLM时应正常生成，只是不增强
        assert result["success"] is True
        assert len(result["personas"]) == 5
    
    # ========== 输入验证边界测试 ==========
    
    def test_validate_count_exceeds_maximum(self, agent):
        """测试数量超过最大值"""
        task_input = {
            "template": "一线白领",
            "count": 1001,
        }
        
        valid, error = agent.validate_input(task_input)
        
        assert valid is False
        assert "1000" in error
    
    def test_validate_invalid_stratify_by_type(self, agent):
        """测试分层维度类型错误"""
        task_input = {
            "template": "一线白领",
            "count": 10,
            "stratify_by": "gender",  # 应该是列表
        }
        
        valid, error = agent.validate_input(task_input)
        
        assert valid is False
    
    def test_validate_invalid_enhance_type(self, agent):
        """测试enhance类型错误"""
        task_input = {
            "template": "一线白领",
            "count": 10,
            "enhance_with_llm": "yes",  # 应该是布尔
        }
        
        valid, error = agent.validate_input(task_input)
        
        assert valid is False
    
    # ========== 错误恢复测试 ==========
    
    def test_error_recovery_after_invalid_input(self, agent):
        """测试无效输入后的恢复"""
        # 先发送无效输入
        result = agent.run({"invalid": "input"})
        assert result["success"] is False
        
        # 然后发送有效输入
        task_input = {
            "template": "一线白领",
            "count": 5,
        }
        result = agent.run(task_input)
        
        assert result["success"] is True
        assert len(result["personas"]) == 5