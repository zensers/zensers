"""
Phase 3 Week 3 测试 - SurveySkill, SurveyOptimizationAgent, SurveyAnalysisAgent, SurveyIntegrationAgent

TDD模式：
- Day 1: SurveySkill
- Day 2: SurveyOptimizationAgent
- Day 3: SurveyAnalysisAgent
- Day 4: SurveyIntegrationAgent
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from typing import Dict, Any, List


# ========== Test SurveySkill ==========

class TestSurveySkill:
    """测试SurveySkill"""
    
    @pytest.fixture
    def skill(self):
        """创建Skill实例"""
        from src.skills.builtin.survey_skill import SurveySkill
        from src.skills.base import SkillConfig
        return SurveySkill(SkillConfig(name="survey_skill", version="1.0.0"))
    
    def test_skill_initialization(self, skill):
        """测试初始化"""
        assert skill.name == "survey_skill"
        assert skill.description is not None
    
    @pytest.mark.asyncio
    async def test_create_survey(self, skill):
        """测试创建问卷"""
        result = await skill.execute(
            action="create",
            title="新能源汽车市场调研",
            questions=[
                {
                    "id": "q1",
                    "text": "您是否考虑购买新能源汽车？",
                    "type": "single_choice",
                    "options": ["是", "否", "正在考虑"]
                }
            ]
        )
        
        assert result["success"] is True
        assert "survey" in result
    
    @pytest.mark.asyncio
    async def test_distribute_survey(self, skill):
        """测试发放问卷"""
        # 先创建问卷
        survey_result = await skill.execute(
            action="create",
            title="测试问卷",
            questions=[
                {
                    "id": "q1",
                    "text": "是否满意？",
                    "type": "single_choice",
                    "options": ["是", "否"]
                }
            ]
        )
        
        # 发放问卷
        result = await skill.execute(
            action="distribute",
            survey=survey_result["survey"],
            target_count=10,
            backend_type="ai_simulation"
        )
        
        assert result["success"] is True
        assert "task_id" in result
    
    @pytest.mark.asyncio
    async def test_get_results(self, skill):
        """测试获取结果"""
        result = await skill.execute(
            action="get_results",
            task_id="task_001"
        )
        
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_get_statistics(self, skill):
        """测试获取统计"""
        result = await skill.execute(
            action="get_statistics",
            task_id="task_001"
        )
        
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_list_backends(self, skill):
        """测试列出后端"""
        result = await skill.execute(
            action="list_backends"
        )
        
        assert result["success"] is True
        assert "backends" in result
    
    @pytest.mark.asyncio
    async def test_invalid_action(self, skill):
        """测试无效操作"""
        result = await skill.execute(
            action="invalid_action"
        )
        
        assert result["success"] is False


# ========== Test SurveyOptimizationAgent ==========

class TestSurveyOptimizationAgent:
    """测试SurveyOptimizationAgent"""
    
    @pytest.fixture
    def agent(self):
        """创建Agent实例"""
        from src.agents.fixed_agents.survey_optimization_agent import SurveyOptimizationAgent
        return SurveyOptimizationAgent(
            agent_id="survey_opt_001",
            name="问卷优化Agent"
        )
    
    @pytest.fixture
    def sample_questions(self):
        """测试问题列表"""
        return [
            {
                "question_id": "q1",
                "text": "您喜欢这个产品吗？",
                "question_type": "single_choice",
                "options": ["是", "否"]
            },
            {
                "question_id": "q2",
                "text": "您为什么喜欢这个产品？（开放题）",
                "question_type": "open_ended"
            }
        ]
    
    def test_agent_initialization(self, agent):
        """测试初始化"""
        assert agent.agent_id == "survey_opt_001"
        assert agent.agent_type == "survey_optimization"
    
    def test_validate_input(self, agent, sample_questions):
        """测试输入验证"""
        valid, error = agent.validate_input({
            "questions": sample_questions,
            "optimization_goals": ["clarity", "completeness"]
        })
        
        assert valid is True
    
    def test_validate_input_missing_questions(self, agent):
        """测试缺少问题"""
        valid, error = agent.validate_input({
            "optimization_goals": ["clarity"]
        })
        
        assert valid is False
    
    @pytest.mark.asyncio
    async def test_analyze_questions(self, agent, sample_questions):
        """测试分析问题"""
        result = await agent.execute_async({
            "questions": sample_questions,
            "optimization_goals": ["clarity"]
        })
        
        assert result["success"] is True
        assert "analysis" in result
    
    @pytest.mark.asyncio
    async def test_optimize_questions(self, agent, sample_questions):
        """测试优化问题"""
        result = await agent.execute_async({
            "questions": sample_questions,
            "optimization_goals": ["clarity", "completeness"],
            "target_audience": "年轻消费者"
        })
        
        assert result["success"] is True
        assert "optimized_questions" in result or "suggestions" in result
    
    @pytest.mark.asyncio
    async def test_check_question_quality(self, agent):
        """测试问题质量检查"""
        # 低质量问题
        bad_questions = [
            {
                "question_id": "q1",
                "text": "这个产品好吗？",  # 模糊问题
                "question_type": "single_choice",
                "options": ["好", "不好"]
            }
        ]
        
        result = await agent.execute_async({
            "questions": bad_questions,
            "optimization_goals": ["clarity"]
        })
        
        assert result["success"] is True
        # 应该有问题识别
        assert "issues" in result or "suggestions" in result


# ========== Test SurveyAnalysisAgent ==========

class TestSurveyAnalysisAgent:
    """测试SurveyAnalysisAgent"""
    
    @pytest.fixture
    def agent(self):
        """创建Agent实例"""
        from src.agents.fixed_agents.survey_analysis_agent import SurveyAnalysisAgent
        return SurveyAnalysisAgent(
            agent_id="survey_analysis_001",
            name="问卷分析Agent"
        )
    
    @pytest.fixture
    def sample_responses(self):
        """测试响应数据"""
        return [
            {
                "response_id": "r1",
                "answers": {
                    "q1": {"answer_value": "是"},
                    "q2": {"answer_value": 5},
                    "q3": {"answer_value": "很满意"}
                }
            },
            {
                "response_id": "r2",
                "answers": {
                    "q1": {"answer_value": "否"},
                    "q2": {"answer_value": 3},
                    "q3": {"answer_value": "一般"}
                }
            }
        ]
    
    @pytest.fixture
    def sample_questions(self):
        """测试问题列表"""
        return [
            {"question_id": "q1", "text": "是否满意", "question_type": "single_choice"},
            {"question_id": "q2", "text": "评分", "question_type": "scale"},
            {"question_id": "q3", "text": "评价", "question_type": "open_ended"}
        ]
    
    def test_agent_initialization(self, agent):
        """测试初始化"""
        assert agent.agent_id == "survey_analysis_001"
        assert agent.agent_type == "survey_analysis"
    
    def test_validate_input(self, agent, sample_responses, sample_questions):
        """测试输入验证"""
        valid, error = agent.validate_input({
            "responses": sample_responses,
            "questions": sample_questions
        })
        
        assert valid is True
    
    @pytest.mark.asyncio
    async def test_analyze_responses(self, agent, sample_responses, sample_questions):
        """测试分析响应"""
        result = await agent.execute_async({
            "responses": sample_responses,
            "questions": sample_questions
        })
        
        assert result["success"] is True
        assert "statistics" in result or "analysis" in result
    
    @pytest.mark.asyncio
    async def test_generate_statistics(self, agent, sample_responses, sample_questions):
        """测试生成统计"""
        result = await agent.execute_async({
            "responses": sample_responses,
            "questions": sample_questions,
            "analysis_type": "statistics"
        })
        
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_generate_report(self, agent, sample_responses, sample_questions):
        """测试生成报告"""
        result = await agent.execute_async({
            "responses": sample_responses,
            "questions": sample_questions,
            "analysis_type": "report",
            "report_format": "markdown"
        })
        
        assert result["success"] is True
        assert "report" in result or "summary" in result


# ========== Test SurveyIntegrationAgent ==========

class TestSurveyIntegrationAgent:
    """测试SurveyIntegrationAgent"""
    
    @pytest.fixture
    def agent(self):
        """创建Agent实例"""
        from src.agents.fixed_agents.survey_integration_agent import SurveyIntegrationAgent
        return SurveyIntegrationAgent(
            agent_id="survey_integration_001",
            name="问卷集成Agent"
        )
    
    def test_agent_initialization(self, agent):
        """测试初始化"""
        assert agent.agent_id == "survey_integration_001"
        assert agent.agent_type == "survey_integration"
    
    @pytest.mark.asyncio
    async def test_full_workflow(self, agent):
        """测试完整工作流"""
        result = await agent.execute_async({
            "workflow": "full_survey",
            "title": "测试问卷",
            "questions": [
                {"question_id": "q1", "text": "是否满意？", "question_type": "single_choice", "options": ["是", "否"]}
            ],
            "target_count": 10,
            "mode": "ai_simulation"
        })
        
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_quick_survey_workflow(self, agent):
        """测试快速调研工作流"""
        result = await agent.execute_async({
            "workflow": "quick_survey",
            "topic": "新能源汽车购买意向",
            "target_count": 5  # 减少数量以加速测试
        })
        
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_workflow_with_optimization(self, agent):
        """测试带优化的工作流"""
        result = await agent.execute_async({
            "workflow": "optimized_survey",
            "title": "产品满意度调研",
            "questions": [
                {"question_id": "q1", "text": "满意吗？", "question_type": "single_choice", "options": ["是", "否"]}
            ],
            "target_count": 5,
            "optimize": True,
            "mode": "ai_simulation"
        })
        
        assert result["success"] is True


# ========== Integration Tests ==========

class TestWeek3Integration:
    """Week 3 集成测试"""
    
    @pytest.mark.asyncio
    async def test_optimize_analyze_workflow(self):
        """测试优化-分析集成"""
        # 1. 创建优化Agent
        from src.agents.fixed_agents.survey_optimization_agent import SurveyOptimizationAgent
        
        opt_agent = SurveyOptimizationAgent(
            agent_id="int_opt",
            name="优化Agent"
        )
        
        # 2. 优化问题
        questions = [
            {"question_id": "q1", "text": "满意吗？", "question_type": "single_choice", "options": ["是", "否"]}
        ]
        
        opt_result = await opt_agent.execute_async({
            "questions": questions,
            "optimization_goals": ["clarity"]
        })
        
        assert opt_result["success"] is True
    
    @pytest.mark.asyncio
    async def test_skill_agent_integration(self):
        """测试Skill-Agent集成"""
        from src.skills.builtin.survey_skill import SurveySkill
        
        skill = SurveySkill()
        
        result = await skill.execute(
            action="create",
            title="集成测试问卷",
            questions=[
                {"question_id": "q1", "text": "测试问题", "question_type": "single_choice", "options": ["A", "B"]}
            ]
        )
        
        assert result["success"] is True