"""
PersonaGenerationAgent 测试 - TDD模式

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

    @pytest.fixture
    def agent(self):
        from src.agents.fixed_agents.persona_generation_agent import PersonaGenerationAgent
        return PersonaGenerationAgent(
            agent_id="persona_gen_001",
            name="画像生成Agent",
        )

    # ========== 基础测试 ==========

    def test_agent_initialization(self, agent):
        assert agent.agent_id == "persona_gen_001"
        assert agent.name == "画像生成Agent"
        assert agent.agent_type == "persona_generation"
        assert len(agent.capabilities) > 0

    def test_agent_has_required_attributes(self, agent):
        assert hasattr(agent, 'agent_type')
        assert hasattr(agent, 'version')
        assert hasattr(agent, 'capabilities')
        assert hasattr(agent, 'execute')

    # ========== 输入验证测试 ==========

    def test_validate_input_missing_count(self, agent):
        task_input = {"template": "一线白领"}
        valid, error = agent.validate_input(task_input)
        assert valid is False
        assert "count" in error.lower() or "数量" in error

    def test_validate_input_invalid_count_type(self, agent):
        task_input = {"template": "一线白领", "count": "invalid"}
        valid, error = agent.validate_input(task_input)
        assert valid is False

    def test_validate_input_invalid_count_value(self, agent):
        task_input = {"template": "一线白领", "count": 0}
        valid, error = agent.validate_input(task_input)
        assert valid is False

    def test_validate_input_valid(self, agent):
        task_input = {"template": "一线白领", "count": 10}
        valid, error = agent.validate_input(task_input)
        assert valid is True
        assert error == ""

    def test_validate_input_with_context(self, agent):
        task_input = {"template": "一线白领", "count": 5, "context": "新能源汽车购买意向调研"}
        valid, error = agent.validate_input(task_input)
        assert valid is True

    # ========== 单个画像生成测试 ==========

    @pytest.mark.asyncio
    async def test_generate_single_persona(self, agent):
        task_input = {"template": "一线白领", "count": 1}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert "personas" in result
        assert len(result["personas"]) == 1
        assert result["total_count"] == 1

    @pytest.mark.asyncio
    async def test_generated_persona_structure(self, agent):
        task_input = {"template": "一线白领", "count": 1}
        result = await agent.execute(task_input)
        persona = result["personas"][0]
        assert isinstance(persona, Persona)
        assert persona.persona_id is not None
        assert persona.name is not None
        assert persona.age > 0
        assert persona.gender is not None
        assert persona.city is not None
        assert persona.occupation is not None

    @pytest.mark.asyncio
    async def test_generated_persona_has_required_fields(self, agent):
        task_input = {"template": "一线白领", "count": 1}
        result = await agent.execute(task_input)
        persona = result["personas"][0]
        for attr in ['persona_id', 'name', 'age', 'gender', 'city', 'occupation',
                      'income', 'education', 'personality_traits', 'interests',
                      'values', 'decision_style', 'background_story']:
            assert hasattr(persona, attr)

    # ========== 批量生成测试 ==========

    @pytest.mark.asyncio
    async def test_batch_generation(self, agent):
        task_input = {"template": "一线白领", "count": 10}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 10
        assert result["total_count"] == 10

    @pytest.mark.asyncio
    async def test_batch_generation_uniqueness(self, agent):
        task_input = {"template": "一线白领", "count": 20}
        result = await agent.execute(task_input)
        persona_ids = [p.persona_id for p in result["personas"]]
        assert len(set(persona_ids)) == len(persona_ids)

    @pytest.mark.asyncio
    async def test_batch_generation_diversity(self, agent):
        task_input = {"template": "一线白领", "count": 30}
        result = await agent.execute(task_input)
        ages = [p.age for p in result["personas"]]
        cities = [p.city for p in result["personas"]]
        assert len(set(ages)) >= 3
        assert len(set(cities)) >= 2

    @pytest.mark.asyncio
    async def test_large_batch_generation(self, agent):
        import time
        task_input = {"template": "一线白领", "count": 100}
        start_time = time.time()
        result = await agent.execute(task_input)
        elapsed_time = time.time() - start_time
        assert result["success"] is True
        assert len(result["personas"]) == 100
        assert elapsed_time < 5.0

    # ========== 模板测试 ==========

    @pytest.mark.asyncio
    async def test_default_template(self, agent):
        task_input = {"template": "invalid_template", "count": 5}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 5

    @pytest.mark.asyncio
    async def test_first_tier_white_collar_template(self, agent):
        task_input = {"template": "一线白领", "count": 10}
        result = await agent.execute(task_input)
        assert result["success"] is True
        for persona in result["personas"]:
            assert persona.age >= 18


    @pytest.mark.asyncio
    async def test_second_tier_family_template(self, agent):
        task_input = {"template": "二三线家庭用户", "count": 10}
        result = await agent.execute(task_input)
        assert result["success"] is True
        for persona in result["personas"]:
            assert persona.age >= 18

    # ========== 分层抽样测试 ==========

    @pytest.mark.asyncio
    async def test_stratified_sampling(self, agent):
        task_input = {"template": "一线白领", "count": 20, "stratify_by": ["gender"]}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 20
        genders = [p.gender for p in result["personas"]]
        assert genders.count("男") > 0
        assert genders.count("女") > 0

    @pytest.mark.asyncio
    async def test_stratified_sampling_by_age(self, agent):
        task_input = {"template": "一线白领", "count": 30, "stratify_by": ["age_group"]}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 30

    # ========== LLM增强生成测试 ==========

    @pytest.mark.asyncio
    async def test_llm_enhanced_generation(self, agent):
        with patch("src.agents.fixed_agents.persona_generation_agent.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": "张伟是一名资深程序员，热爱新技术，对新能源汽车充满兴趣。",
                "usage": {"total_tokens": 50},
            }
            task_input = {"template": "一线白领", "count": 5, "context": "新能源汽车购买意向调研", "enhance_with_llm": True}
            result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 5

    @pytest.mark.asyncio
    async def test_llm_enhancement_async(self, agent):
        with patch("src.agents.fixed_agents.persona_generation_agent.call_llm", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "success": True,
                "content": "李娜是一名产品经理，注重效率和品质。",
                "usage": {"total_tokens": 40},
            }
            task_input = {"template": "一线白领", "count": 3, "context": "新能源汽车调研", "enhance_with_llm": True}
            result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 3

    # ========== 上下文感知测试 ==========

    @pytest.mark.asyncio
    async def test_context_aware_generation(self, agent):
        task_input = {"template": "一线白领", "count": 10, "context": "新能源汽车购买意向调研"}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 10

    # ========== 结果格式测试 ==========

    @pytest.mark.asyncio
    async def test_result_contains_required_fields(self, agent):
        task_input = {"template": "一线白领", "count": 5}
        result = await agent.execute(task_input)
        assert "success" in result
        assert "personas" in result
        assert "total_count" in result

    # ========== Run方法测试 ==========

    @pytest.mark.asyncio
    async def test_run_method(self, agent):
        task_input = {"template": "一线白领", "count": 5}
        result = await agent.run(task_input)
        assert result["success"] is True
        assert result["agent_id"] == agent.agent_id
        assert result["agent_name"] == agent.name

    @pytest.mark.asyncio
    async def test_run_includes_metadata(self, agent):
        task_input = {"template": "一线白领", "count": 5}
        result = await agent.run(task_input)
        assert "agent_id" in result
        assert "agent_name" in result
        assert "agent_version" in result

    @pytest.mark.asyncio
    async def test_run_with_invalid_input(self, agent):
        result = await agent.run({"invalid": "input"})
        assert result["success"] is False
        assert "error" in result

    # ========== 状态管理测试 ==========

    @pytest.mark.asyncio
    async def test_agent_state_transition(self, agent):
        assert agent.status == "idle"
        task_input = {"template": "一线白领", "count": 5}
        result = await agent.run(task_input)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_agent_reset(self, agent):
        task_input = {"template": "一线白领", "count": 5}
        await agent.run(task_input)
        await agent.reset()
        assert agent.status == "idle"

    # ========== 能力测试 ==========

    def test_get_capabilities(self, agent):
        capabilities = agent.get_capabilities()
        assert isinstance(capabilities, list)
        assert len(capabilities) > 0

    def test_agent_version(self, agent):
        assert agent.version is not None

    # ========== 边界条件测试 ==========

    @pytest.mark.asyncio
    async def test_minimum_count(self, agent):
        task_input = {"template": "一线白领", "count": 1}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 1

    @pytest.mark.asyncio
    async def test_maximum_count(self, agent):
        task_input = {"template": "一线白领", "count": 500}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 500

    # ========== 性能测试 ==========

    @pytest.mark.asyncio
    async def test_performance_small_batch(self, agent):
        import time
        task_input = {"template": "一线白领", "count": 10}
        start_time = time.time()
        result = await agent.execute(task_input)
        elapsed_time = time.time() - start_time
        assert result["success"] is True
        assert elapsed_time < 1.0

    @pytest.mark.asyncio
    async def test_performance_medium_batch(self, agent):
        import time
        task_input = {"template": "一线白领", "count": 50}
        start_time = time.time()
        result = await agent.execute(task_input)
        elapsed_time = time.time() - start_time
        assert result["success"] is True
        assert elapsed_time < 2.0

    # ========== 异步执行测试 ==========

    @pytest.mark.asyncio
    async def test_execute_async(self, agent):
        task_input = {"template": "一线白领", "count": 5}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 5

    @pytest.mark.asyncio
    async def test_execute_async_with_stratify(self, agent):
        task_input = {"template": "一线白领", "count": 10, "stratify_by": ["gender"]}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 10

    @pytest.mark.asyncio
    async def test_execute_async_invalid_input(self, agent):
        task_input = {"invalid": "input"}
        valid, error = agent.validate_input(task_input)
        assert valid is False

    # ========== 模板管理测试 ==========

    def test_get_available_templates(self, agent):
        templates = agent.get_available_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0

    # ========== 分层抽样边界测试 ==========

    @pytest.mark.asyncio
    async def test_stratified_sampling_odd_count(self, agent):
        task_input = {"template": "一线白领", "count": 11, "stratify_by": ["gender"]}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 11

    @pytest.mark.asyncio
    async def test_stratified_sampling_unknown_dimension(self, agent):
        task_input = {"template": "一线白领", "count": 10, "stratify_by": ["unknown_dimension"]}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 10

    # ========== LLM增强边界测试 ==========

    @pytest.mark.asyncio
    async def test_llm_enhancement_uses_intrinsic_llm(self, agent):
        task_input = {"template": "一线白领", "count": 5, "enhance_with_llm": True}
        result = await agent.execute(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 5

    # ========== 输入验证边界测试 ==========

    def test_validate_count_exceeds_maximum(self, agent):
        task_input = {"template": "一线白领", "count": 1001}
        valid, error = agent.validate_input(task_input)
        assert valid is False
        assert "1000" in error

    def test_validate_invalid_stratify_by_type(self, agent):
        task_input = {"template": "一线白领", "count": 10, "stratify_by": "gender"}
        valid, error = agent.validate_input(task_input)
        assert valid is False

    def test_validate_invalid_enhance_type(self, agent):
        task_input = {"template": "一线白领", "count": 10, "enhance_with_llm": "yes"}
        valid, error = agent.validate_input(task_input)
        assert valid is False

    # ========== 错误恢复测试 ==========

    @pytest.mark.asyncio
    async def test_error_recovery_after_invalid_input(self, agent):
        result = await agent.run({"invalid": "input"})
        assert result["success"] is False
        task_input = {"template": "一线白领", "count": 5}
        result = await agent.run(task_input)
        assert result["success"] is True
        assert len(result["personas"]) == 5
