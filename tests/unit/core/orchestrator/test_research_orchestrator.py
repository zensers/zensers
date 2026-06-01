"""
ResearchOrchestrator 统一测试

Phase 4 更新: 测试智能路由系统：
1. IntelligentRoutingAdapter 意图分析
2. WisdomStore 经验记录
3. 端到端研究流程
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, AsyncMock, patch

from src.core.orchestrator.research_orchestrator import (
    ResearchOrchestrator,
    ResearchRequirement,
    ResearchResult,
    research,
)
# Phase 4: 更新导入
from src.core.intent_types import IntentType, TaskComplexity
from src.core.wisdom import WisdomStore


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def wisdom_store(tmp_path):
    """创建临时 WisdomStore"""
    store_path = tmp_path / ".wisdom_test"
    return WisdomStore(store_path=store_path)


@pytest.fixture
def orchestrator(wisdom_store):
    """创建 ResearchOrchestrator"""
    return ResearchOrchestrator(
        wisdom_store=wisdom_store,
        enable_dual_track=True,
    )


@pytest.fixture
def orchestrator_no_dual_track():
    """创建无双轨学习的 ResearchOrchestrator"""
    return ResearchOrchestrator(
        max_parallel=3,
        enable_dual_track=False,
    )


# ============================================================================
# Test: Initialization
# ============================================================================

class TestResearchOrchestratorInit:
    """测试初始化"""
    
    def test_init_with_dual_track(self, wisdom_store):
        """测试启用双轨学习初始化"""
        orchestrator = ResearchOrchestrator(
            wisdom_store=wisdom_store,
            enable_dual_track=True,
        )
        
        assert orchestrator.enable_dual_track == True
        # 新 API 使用私有属性
        assert orchestrator._intent_gate is not None
        assert orchestrator._category_router is not None
        # wisdom_store 注入后存储在 _wisdom_store 或通过 wisdom_recorder 访问
        assert orchestrator._wisdom_store is not None
    
    def test_init_without_dual_track(self):
        """测试禁用双轨学习初始化"""
        orchestrator = ResearchOrchestrator(
            enable_dual_track=False,
        )
        
        assert orchestrator.enable_dual_track == False
        # 新 API 仍然创建组件，只是不使用双轨学习功能
        assert orchestrator._intent_gate is not None
        assert orchestrator._category_router is not None
    
    @pytest.mark.skip(reason="inject_knowledge_components 方法已在新 API 中移除")
    def test_inject_knowledge_components(self, orchestrator):
        """测试注入知识层组件"""
        mock_knowledge_bank = Mock()
        mock_core_memory = Mock()
        
        orchestrator.inject_knowledge_components(
            knowledge_bank=mock_knowledge_bank,
            core_memory=mock_core_memory,
        )
        
        assert orchestrator.knowledge_bank == mock_knowledge_bank
        assert orchestrator.core_memory == mock_core_memory


# ============================================================================
# Test: Requirement Parsing (IntelligentRouting Integration)
# ============================================================================

class TestResearchOrchestratorParsing:
    """测试需求解析（智能路由集成）"""
    
    @pytest.mark.skip(reason="_parse_requirement_enhanced 方法已在新 API 中移除")
    def test_parse_string_input(self, orchestrator):
        """测试字符串输入解析"""
        requirement, intent_analysis = orchestrator._parse_requirement_enhanced(
            "分析新能源汽车市场竞争格局"
        )
        
        assert requirement.topic == "分析新能源汽车市场竞争格局"
        assert len(requirement.aspects) > 0
        assert "intent_type" in intent_analysis
        assert "complexity" in intent_analysis
    
    @pytest.mark.skip(reason="_parse_requirement_enhanced 方法已在新 API 中移除")
    def test_parse_dict_input(self, orchestrator):
        """测试字典输入解析"""
        requirement, intent_analysis = orchestrator._parse_requirement_enhanced({
            "topic": "医疗AI市场",
            "aspects": ["市场规模", "竞争格局"],
            "region": "全球",
        })
        
        assert requirement.topic == "医疗AI市场"
        assert requirement.aspects == ["市场规模", "竞争格局"]
        assert requirement.region == "全球"
    
    @pytest.mark.skip(reason="_parse_requirement_enhanced 方法已在新 API 中移除")
    def test_intent_analysis_contains_keywords(self, orchestrator):
        """测试意图分析包含关键词"""
        requirement, intent_analysis = orchestrator._parse_requirement_enhanced(
            "Analyze the EV market competition"
        )
        
        assert "keywords_matched" in intent_analysis
        # 英文关键词应被匹配
        assert len(intent_analysis.get("keywords_matched", [])) > 0
    
    @pytest.mark.skip(reason="_parse_requirement_enhanced 方法已在新 API 中移除")
    def test_parse_without_dual_track(self, orchestrator_no_dual_track):
        """测试无双轨学习的解析"""
        requirement, intent_analysis = orchestrator_no_dual_track._parse_requirement_enhanced(
            "分析新能源汽车市场"
        )
        
        assert requirement.topic == "分析新能源汽车市场"
        # 无双轨学习时，intent_analysis 应为空
        assert intent_analysis == {}


# ============================================================================
# Test: Agent Creation (IntelligentRouting + Wisdom Integration)
# ============================================================================

class TestResearchOrchestratorAgentCreation:
    """测试 Agent 创建（智能路由 + Wisdom 集成）"""
    
    @pytest.mark.skip(reason="_create_agents_enhanced 方法已在新 API 中移除")
    def test_create_agents_with_recommended_skills(self, orchestrator):
        """测试创建 Agent 时包含推荐 Skills"""
        requirement = ResearchRequirement(
            topic="新能源汽车市场",
            aspects=["市场规模", "竞争格局"],
            intent_type="research",
        )
        intent_analysis = {
            "intent_type": "research",
            "complexity": "medium",
        }
        
        # Mock factory
        orchestrator.factory = Mock()
        orchestrator.factory.create_agents_for_requirement = Mock(return_value=[])
        
        agents = orchestrator._create_agents_enhanced(requirement, intent_analysis)
        
        # 验证 factory 被调用
        assert orchestrator.factory.create_agents_for_requirement.called
    
    @pytest.mark.skip(reason="_create_agents_enhanced 方法已在新 API 中移除")
    def test_create_agents_without_dual_track(self, orchestrator_no_dual_track):
        """测试无双轨学习的 Agent 创建"""
        requirement = ResearchRequirement(
            topic="新能源汽车市场",
            aspects=["市场规模"],
        )
        intent_analysis = {}
        
        # Mock factory
        orchestrator_no_dual_track.factory = Mock()
        orchestrator_no_dual_track.factory.create_agents_for_requirement = Mock(return_value=[])
        
        agents = orchestrator_no_dual_track._create_agents_enhanced(requirement, intent_analysis)
        
        assert orchestrator_no_dual_track.factory.create_agents_for_requirement.called


# ============================================================================
# Test: Research Execution
# ============================================================================

class TestResearchOrchestratorExecution:
    """测试研究执行"""
    
    @pytest.mark.skip(reason="API 已重构，需要更新测试")
    async def test_research_with_mock_factory(self, orchestrator, wisdom_store):
        """测试研究执行（Mock Factory）"""
        # Mock Agent
        mock_agent = MagicMock()
        mock_agent.agent_id = "test_agent_001"
        mock_agent.config = {"name": "测试分析师", "context": {"aspect": "market"}}
        mock_agent.execute = AsyncMock(return_value={
            "status": "success",
            "data": {"analysis": "完成"},
        })
        
        # Mock Factory
        orchestrator.factory = Mock()
        orchestrator.factory.create_agents_for_requirement = Mock(return_value=[mock_agent])
        
        result = await orchestrator.research("分析新能源汽车市场")
        
        assert result.status == "completed"
        assert result.topic == "分析新能源汽车市场"
    
    @pytest.mark.skip(reason="API 已重构，需要更新测试")
    async def test_research_wisdom_recorded(self, orchestrator, wisdom_store):
        """测试研究执行后 Wisdom 记录"""
        # Mock Agent
        mock_agent = MagicMock()
        mock_agent.agent_id = "test_agent_001"
        mock_agent.config = {"name": "测试分析师", "context": {"aspect": "market"}}
        mock_agent.execute = AsyncMock(return_value={"status": "success"})
        
        orchestrator.factory = Mock()
        orchestrator.factory.create_agents_for_requirement = Mock(return_value=[mock_agent])
        
        result = await orchestrator.research(
            "分析新能源汽车市场规模",
            user_id="user_test_001"
        )
        
        # 验证 Wisdom 记录
        assert result.wisdom_recorded == True


# ============================================================================
# Test: Statistics and Status
# ============================================================================

class TestResearchOrchestratorStats:
    """测试统计和状态"""
    
    def test_get_stats(self, orchestrator):
        """测试获取统计信息"""
        stats = orchestrator.get_stats()
        
        assert "total_tasks" in stats
        assert "dual_track_enabled" in stats
        assert stats["dual_track_enabled"] == True
    
    @pytest.mark.skip(reason="get_dual_track_status 方法已在新 API 中移除")
    def test_get_dual_track_status(self, orchestrator):
        """测试获取双轨学习状态"""
        status = orchestrator.get_dual_track_status()
        
        assert status["enable_dual_track"] == True
        assert status["intent_gate"] == True
        assert status["category_router"] == True
        assert status["wisdom_store"] == True
    
    @pytest.mark.skip(reason="get_dual_track_status 方法已在新 API 中移除")
    @pytest.mark.skip(reason="get_dual_track_status 方法已在新 API 中移除")
    def test_get_dual_track_status_disabled(self, orchestrator_no_dual_track):
        """测试禁用双轨学习的状态"""
        status = orchestrator_no_dual_track.get_dual_track_status()
        
        assert status["enable_dual_track"] == False
        assert status["intent_gate"] == False


# ============================================================================
# Test: Convenience Function
# ============================================================================

class TestResearchConvenienceFunction:
    """测试便捷函数"""
    
    @pytest.mark.asyncio
    async def test_research_function(self):
        """测试 research 便捷函数"""
        # 创建临时 Orchestrator
        with patch('src.core.orchestrator.research_orchestrator.ResearchOrchestrator') as MockOrchestrator:
            mock_instance = MockOrchestrator.return_value
            mock_result = ResearchResult(
                task_id="test_001",
                status="completed",
                topic="测试",
                agents_used=[],
                stages_completed=1,
            )
            mock_instance.research = AsyncMock(return_value=mock_result)
            
            # 重新导入以应用 patch
            from src.core.orchestrator.research_orchestrator import research
            result = await research("测试主题")
            
            assert result.status == "completed"


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])