"""
Agent分类测试

验证Agent分类逻辑是否正确：
1. research 类别 → DATA_COLLECTION
2. synthesis 类别 → SYNTHESIS  
3. market-analysis 类别 → ANALYSIS
4. Agent ID 以 research_ 开头 → DATA_COLLECTION
"""

import pytest
from unittest.mock import Mock, MagicMock


class TestAgentClassification:
    """测试Agent分类逻辑"""
    
    def test_research_category_maps_to_data_collection(self):
        """测试 research 类别映射到 DATA_COLLECTION"""
        from src.core.orchestrator.execution.engine import ExecutionEngine, AgentCategory, ExecutionConfig
        from src.core.communication import MessageBus, SharedMemory
        
        # 创建引擎
        engine = ExecutionEngine(
            config=ExecutionConfig(),
            message_bus=MessageBus(),
            shared_memory=SharedMemory(),
            enable_quality_control=False,
        )
        
        # 创建模拟Agent，设置 category="research"
        agent = Mock()
        agent.agent_id = "research_test_1"
        agent.config = {"category": "research"}
        
        # 分类
        category = engine.classify_agent(agent)
        
        assert category == AgentCategory.DATA_COLLECTION, \
            f"Expected DATA_COLLECTION, got {category}"
    
    def test_synthesis_category_maps_to_synthesis(self):
        """测试 synthesis 类别映射到 SYNTHESIS"""
        from src.core.orchestrator.execution.engine import ExecutionEngine, AgentCategory, ExecutionConfig
        from src.core.communication import MessageBus, SharedMemory
        
        engine = ExecutionEngine(
            config=ExecutionConfig(),
            message_bus=MessageBus(),
            shared_memory=SharedMemory(),
            enable_quality_control=False,
        )
        
        agent = Mock()
        agent.agent_id = "synthesis_test_1"
        agent.config = {"category": "synthesis"}
        
        category = engine.classify_agent(agent)
        
        assert category == AgentCategory.SYNTHESIS, \
            f"Expected SYNTHESIS, got {category}"
    
    def test_market_analysis_maps_to_analysis(self):
        """测试 market-analysis 类别映射到 ANALYSIS"""
        from src.core.orchestrator.execution.engine import ExecutionEngine, AgentCategory, ExecutionConfig
        from src.core.communication import MessageBus, SharedMemory
        
        engine = ExecutionEngine(
            config=ExecutionConfig(),
            message_bus=MessageBus(),
            shared_memory=SharedMemory(),
            enable_quality_control=False,
        )
        
        agent = Mock()
        agent.agent_id = "analysis_test_1"
        agent.config = {"category": "market-analysis"}
        
        category = engine.classify_agent(agent)
        
        assert category == AgentCategory.ANALYSIS, \
            f"Expected ANALYSIS, got {category}"
    
    def test_agent_id_prefix_research_maps_to_data_collection(self):
        """测试 Agent ID 以 research_ 开头映射到 DATA_COLLECTION"""
        from src.core.orchestrator.execution.engine import ExecutionEngine, AgentCategory, ExecutionConfig
        from src.core.communication import MessageBus, SharedMemory
        
        engine = ExecutionEngine(
            config=ExecutionConfig(),
            message_bus=MessageBus(),
            shared_memory=SharedMemory(),
            enable_quality_control=False,
        )
        
        # 创建没有显式category的Agent
        agent = Mock()
        agent.agent_id = "research_market_size_1"
        agent.config = {}  # 没有category
        
        category = engine.classify_agent(agent)
        
        assert category == AgentCategory.DATA_COLLECTION, \
            f"Expected DATA_COLLECTION (by ID prefix), got {category}"
    
    def test_classify_agents_separates_correctly(self):
        """测试批量分类Agent正确分离"""
        from src.core.orchestrator.execution.engine import ExecutionEngine, AgentCategory, ExecutionConfig
        from src.core.communication import MessageBus, SharedMemory
        
        engine = ExecutionEngine(
            config=ExecutionConfig(),
            message_bus=MessageBus(),
            shared_memory=SharedMemory(),
            enable_quality_control=False,
        )
        
        # 创建不同类型的Agent
        agents = [
            # 数据收集Agent
            Mock(agent_id="research_市场规模_1", config={"category": "research"}),
            Mock(agent_id="research_竞争格局_2", config={"category": "research"}),
            # 综合Agent
            Mock(agent_id="synthesis_summary_1", config={"category": "synthesis"}),
            Mock(agent_id="synthesis_conclusion_2", config={"category": "synthesis"}),
        ]
        
        data_agents, analysis_agents, synthesis_agents, report_agents = \
            engine.classify_agents(agents)
        
        # 验证分类结果
        assert len(data_agents) == 2, \
            f"Expected 2 data agents, got {len(data_agents)}"
        assert len(synthesis_agents) == 2, \
            f"Expected 2 synthesis agents, got {len(synthesis_agents)}"
        assert len(analysis_agents) == 0, \
            f"Expected 0 analysis agents, got {len(analysis_agents)}"
        assert len(report_agents) == 0, \
            f"Expected 0 report agents, got {len(report_agents)}"


class TestOrchestratorAgentCreation:
    """测试Orchestrator创建Agent的分类"""
    
    def test_orchestrator_creates_research_agents(self):
        """测试Orchestrator创建的Agent使用research类别"""
        import inspect
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        
        source = inspect.getsource(ResearchOrchestrator._create_agents)
        
        assert 'spec.category' in source or 'category=' in source, \
            "Orchestrator应该使用 spec.category 或 category 参数创建Agent"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
