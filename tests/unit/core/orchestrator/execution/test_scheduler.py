# -*- coding: utf-8 -*-
"""
ExecutionScheduler 单元测试

测试调度器的核心功能：
1. 拓扑排序
2. 依赖解析
3. 批次生成
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import Dict, Any, List


class TestExecutionScheduler:
    """ExecutionScheduler 测试"""
    
    def test_schedule_from_agents_no_dependencies(self):
        """测试无依赖的Agent调度"""
        from src.core.orchestrator.execution.scheduler import (
            ExecutionScheduler, ExecutionState
        )
        
        # 创建调度器
        scheduler = ExecutionScheduler(max_parallel=5)
        
        # 创建无依赖的Agent
        agents = []
        for i in range(5):
            agent = Mock()
            agent.agent_id = f"agent_{i}"
            agent.context = {}
            agent.category = "research"
            agents.append(agent)
        
        # 调度
        batches = scheduler.schedule_from_agents(agents)
        
        # 验证：所有Agent应该在同一个批次（无依赖，可并行）
        assert len(batches) == 1
        assert len(batches[0]) == 5
    
    def test_schedule_from_agents_with_dependencies(self):
        """测试有依赖的Agent调度"""
        from src.core.orchestrator.execution.scheduler import (
            ExecutionScheduler, ExecutionState
        )
        
        scheduler = ExecutionScheduler(max_parallel=5)
        
        # 创建有依赖关系的Agent
        # agent_0 -> agent_1 -> agent_2
        agents = []
        
        # Agent 0: 无依赖
        agent0 = Mock()
        agent0.agent_id = "agent_0"
        agent0.context = {}
        agent0.category = "research"
        agents.append(agent0)
        
        # Agent 1: 依赖 Agent 0
        agent1 = Mock()
        agent1.agent_id = "agent_1"
        agent1.context = {"depends_on": ["agent_0"]}
        agent1.category = "research"
        agents.append(agent1)
        
        # Agent 2: 依赖 Agent 1
        agent2 = Mock()
        agent2.agent_id = "agent_2"
        agent2.context = {"depends_on": ["agent_1"]}
        agent2.category = "research"
        agents.append(agent2)
        
        # 调度
        batches = scheduler.schedule_from_agents(agents)
        
        # 验证：应该是3个批次（顺序执行）
        assert len(batches) == 3
        assert batches[0] == ["agent_0"]
        assert batches[1] == ["agent_1"]
        assert batches[2] == ["agent_2"]
    
    def test_schedule_synthesis_agents_depend_on_research(self):
        """测试综合Agent依赖研究Agent"""
        from src.core.orchestrator.execution.scheduler import (
            ExecutionScheduler, ExecutionState
        )
        
        scheduler = ExecutionScheduler(max_parallel=5)
        
        agents = []
        
        # 2个研究Agent
        for i in range(2):
            agent = Mock()
            agent.agent_id = f"research_agent_{i}"
            agent.context = {}
            agent.category = "research"
            agents.append(agent)
        
        # 1个综合Agent（依赖研究Agent）
        synthesis = Mock()
        synthesis.agent_id = "synthesis_summary"
        synthesis.context = {"depends_on": ["research_agent_0", "research_agent_1"]}
        synthesis.category = "synthesis"
        agents.append(synthesis)
        
        # 调度
        batches = scheduler.schedule_from_agents(agents)
        
        # 验证：应该是2个批次
        # 批次1: research_agent_0, research_agent_1（并行）
        # 批次2: synthesis_summary（依赖完成）
        assert len(batches) == 2
        assert len(batches[0]) == 2  # 2个研究Agent并行
        assert batches[1] == ["synthesis_summary"]
    
    def test_mark_completed_and_get_ready(self):
        """测试完成标记和获取就绪Agent"""
        from src.core.orchestrator.execution.scheduler import (
            ExecutionScheduler, ExecutionState
        )
        
        scheduler = ExecutionScheduler(max_parallel=5)
        
        # 创建Agent
        agents = []
        for i in range(3):
            agent = Mock()
            agent.agent_id = f"agent_{i}"
            agent.context = {}
            agent.category = "research"
            agents.append(agent)
        
        # 调度
        batches = scheduler.schedule_from_agents(agents)
        
        # 获取就绪Agent
        ready = scheduler.get_ready_agents()
        assert len(ready) == 3  # 全部就绪
        
        # 标记第一个运行和完成
        scheduler.mark_running("agent_0")
        scheduler.mark_completed("agent_0", {"result": "ok"})
        
        # 检查状态
        stats = scheduler.get_execution_stats()
        assert stats["completed"] == 1
        assert stats["running"] == 0
    
    def test_topological_sort_with_complex_dependencies(self):
        """测试复杂依赖的拓扑排序"""
        from src.core.orchestrator.execution.scheduler import (
            ExecutionScheduler, ExecutionState
        )
        
        scheduler = ExecutionScheduler(max_parallel=5)
        
        # 创建复杂依赖图
        # agent_a -> agent_c
        # agent_b -> agent_c
        # agent_c -> agent_d
        agents = []
        
        # A, B: 无依赖
        for name in ["agent_a", "agent_b"]:
            agent = Mock()
            agent.agent_id = name
            agent.context = {}
            agent.category = "research"
            agents.append(agent)
        
        # C: 依赖 A, B
        agent_c = Mock()
        agent_c.agent_id = "agent_c"
        agent_c.context = {"depends_on": ["agent_a", "agent_b"]}
        agent_c.category = "research"
        agents.append(agent_c)
        
        # D: 依赖 C
        agent_d = Mock()
        agent_d.agent_id = "agent_d"
        agent_d.context = {"depends_on": ["agent_c"]}
        agent_d.category = "research"
        agents.append(agent_d)
        
        # 调度
        batches = scheduler.schedule_from_agents(agents)
        
        # 验证：
        # 批次1: agent_a, agent_b（并行，无依赖）
        # 批次2: agent_c（依赖A,B完成）
        # 批次3: agent_d（依赖C完成）
        assert len(batches) == 3
        assert set(batches[0]) == {"agent_a", "agent_b"}
        assert batches[1] == ["agent_c"]
        assert batches[2] == ["agent_d"]


class TestScheduledAgent:
    """ScheduledAgent 测试"""
    
    def test_is_ready_no_dependencies(self):
        """测试无依赖时是否就绪"""
        from src.core.orchestrator.execution.scheduler import (
            ScheduledAgent, ExecutionState
        )
        
        agent = ScheduledAgent(
            agent_id="test_agent",
            agent=Mock(),
            dependencies=[],
        )
        
        assert agent.is_ready(set()) == True
    
    def test_is_ready_with_dependencies_completed(self):
        """测试依赖完成时是否就绪"""
        from src.core.orchestrator.execution.scheduler import (
            ScheduledAgent, ExecutionState
        )
        
        agent = ScheduledAgent(
            agent_id="test_agent",
            agent=Mock(),
            dependencies=["dep_1", "dep_2"],
        )
        
        # 依赖未完成
        assert agent.is_ready({"dep_1"}) == False
        
        # 依赖全部完成
        assert agent.is_ready({"dep_1", "dep_2"}) == True
    
    def test_is_ready_already_running(self):
        """测试已运行时不再就绪"""
        from src.core.orchestrator.execution.scheduler import (
            ScheduledAgent, ExecutionState
        )
        
        agent = ScheduledAgent(
            agent_id="test_agent",
            agent=Mock(),
            dependencies=[],
            state=ExecutionState.RUNNING,
        )
        
        assert agent.is_ready(set()) == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
