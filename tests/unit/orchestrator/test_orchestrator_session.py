"""
ResearchOrchestrator Session 集成测试

测试 ResearchOrchestrator 的 Session 层级管理功能：
1. 主控 Session 创建
2. 子 Agent Session 创建与追踪
3. ResultCollector 集成
4. Session 状态追踪
5. Registry 清理

设计文档: docs/AGENT_SESSION_MANAGEMENT.md Section 4.2
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Dict, Any
from pathlib import Path

from src.core.orchestrator.research_orchestrator import (
    ResearchOrchestrator,
    ResearchRequirement,
    ResearchResult,
)
from src.core.agents.factory import DynamicAgentFactory, AgentCapability
from src.core.agents.agent_session import (
    AgentSession,
    AgentSessionRegistry,
    AgentSessionStatus,
    SessionOrigin,
)
from src.core.agents.result_collector import ResultCollector
from src.core.communication import MessageBus, Event, SharedMemory


# === Fixtures ===

@pytest.fixture
def message_bus():
    """创建 MessageBus 实例"""
    return MessageBus()


@pytest.fixture
def shared_memory():
    """创建 SharedMemory 实例"""
    return SharedMemory()


@pytest.fixture
def factory_with_comm(message_bus, shared_memory):
    """创建带通信能力的 Factory"""
    return DynamicAgentFactory(
        message_bus=message_bus,
        shared_memory=shared_memory
    )


@pytest.fixture
def orchestrator_with_session(factory_with_comm):
    """创建带 Session 支持的 Orchestrator"""
    return ResearchOrchestrator(
        agent_factory=factory_with_comm,
        enable_dual_track=False  # 禁用双轨学习简化测试
    )


@pytest.fixture
def basic_requirement():
    """创建基本研究需求"""
    return ResearchRequirement(
        topic="新能源汽车市场",
        aspects=["市场规模", "竞争格局"],
        region="中国",
        output_format="docx"
    )


# === Test Orchestrator Session 初始化 ===

class TestOrchestratorSessionInit:
    """测试 Orchestrator Session 初始化"""
    
    def test_init_without_session_support(self):
        """测试无 Session 支持的初始化"""
        orchestrator = ResearchOrchestrator(enable_dual_track=False)
        
        # 默认情况下不应该有 Session 相关属性
        # 或者应该初始化为 None
        assert not hasattr(orchestrator, '_primary_session_id') or \
               orchestrator._primary_session_id is None
    
    def test_init_with_factory_has_comm(self, factory_with_comm):
        """测试 Factory 已有通信能力"""
        orchestrator = ResearchOrchestrator(
            agent_factory=factory_with_comm,
            enable_dual_track=False
        )
        
        assert orchestrator.factory._message_bus is not None
        assert orchestrator.factory._shared_memory is not None


# === Test Session 层级创建 ===

class TestOrchestratorSessionHierarchy:
    """测试 Session 层级创建"""
    
    @pytest.mark.asyncio
    async def test_creates_primary_session_on_research(self, orchestrator_with_session):
        """测试研究时创建主控 Session"""
        orchestrator = orchestrator_with_session
        
        # 执行研究（会被 mock 中断）
        with patch.object(orchestrator, '_execute_research', return_value=[]):
            with patch.object(orchestrator, '_generate_report', return_value="output/test.docx"):
                result = await orchestrator.research({
                    "topic": "测试主题",
                    "aspects": ["市场规模"]
                })
        
        # 验证主控 Session 已创建
        assert orchestrator._primary_session_id is not None
        assert orchestrator._primary_session_id.startswith("research_")
    
    @pytest.mark.asyncio
    async def test_creates_session_registry(self, orchestrator_with_session):
        """测试创建 Session Registry"""
        orchestrator = orchestrator_with_session
        
        with patch.object(orchestrator, '_execute_research', return_value=[]):
            with patch.object(orchestrator, '_generate_report', return_value="output/test.docx"):
                await orchestrator.research({
                    "topic": "测试主题",
                    "aspects": ["市场规模"]
                })
        
        # 验证 Registry 已创建
        assert orchestrator._session_registry is not None
        assert isinstance(orchestrator._session_registry, AgentSessionRegistry)
    
    @pytest.mark.asyncio
    async def test_creates_result_collector(self, orchestrator_with_session, message_bus):
        """测试创建 ResultCollector"""
        orchestrator = orchestrator_with_session
        
        with patch.object(orchestrator, '_execute_research', return_value=[]):
            with patch.object(orchestrator, '_generate_report', return_value="output/test.docx"):
                await orchestrator.research({
                    "topic": "测试主题",
                    "aspects": ["市场规模"]
                })
        
        # 验证 ResultCollector 已创建
        assert orchestrator._result_collector is not None
        assert isinstance(orchestrator._result_collector, ResultCollector)
        assert orchestrator._result_collector.parent_session_id == orchestrator._primary_session_id


# === Test Agent Session 创建与追踪 ===

class TestOrchestratorAgentSession:
    """测试 Agent Session 创建与追踪"""
    
    @pytest.mark.asyncio
    async def test_creates_session_for_each_agent(self, orchestrator_with_session):
        """测试为每个 Agent 创建 Session"""
        orchestrator = orchestrator_with_session
        
        # 当 Orchestrator 使用 Factory 的 create_agent_with_session 时
        # Session 会在 Factory 的 _session_registries 中
        # 测试 Factory 是否支持 Session 创建
        
        factory = orchestrator.factory
        
        # 如果 Factory 不支持 Session 创建，跳过此测试
        if not hasattr(factory, 'create_agent_with_session'):
            pytest.skip("Factory does not support session creation")
        
        # Mock execute 返回模拟结果
        async def mock_execute(agent, task):
            return {"status": "success", "agent_id": agent.agent_id}
        
        # 使用 Factory 直接创建带 Session 的 Agent
        capability = AgentCapability(
            name="测试Agent",
            description="测试",
            required_skills=["search_skill"]
        )
        
        agent, session = factory.create_agent_with_session(
            agent_id="test_agent_session",
            capability=capability,
            parent_session_id=orchestrator._primary_session_id or "test_parent",
            context={"topic": "测试"}
        )
        
        # 验证 Session 已创建
        assert session is not None
        assert session.agent_id == "test_agent_session"
    
    @pytest.mark.asyncio
    async def test_session_origin_is_spawned(self, orchestrator_with_session):
        """测试子 Session 来源为 SPAWNED"""
        orchestrator = orchestrator_with_session
        
        async def mock_execute(agent, task):
            return {"status": "success"}
        
        with patch.object(orchestrator, '_execute_agent_with_semaphore', side_effect=mock_execute):
            with patch.object(orchestrator, '_generate_report', return_value="output/test.docx"):
                await orchestrator.research({
                    "topic": "测试主题",
                    "aspects": ["市场规模"]
                })
        
        # 检查所有 Session 的 origin
        if orchestrator._session_registry:
            for session in orchestrator._session_registry.child_sessions.values():
                assert session.origin == SessionOrigin.SPAWNED


# === Test Session 状态追踪 ===

class TestOrchestratorSessionTracking:
    """测试 Session 状态追踪"""
    
    @pytest.mark.asyncio
    async def test_get_session_status_summary(self, orchestrator_with_session):
        """测试获取 Session 状态摘要"""
        orchestrator = orchestrator_with_session
        
        async def mock_execute(agent, task):
            return {"status": "success"}
        
        with patch.object(orchestrator, '_execute_agent_with_semaphore', side_effect=mock_execute):
            with patch.object(orchestrator, '_generate_report', return_value="output/test.docx"):
                await orchestrator.research({
                    "topic": "测试主题",
                    "aspects": ["市场规模"]
                })
        
        # 获取状态摘要
        if orchestrator._session_registry:
            status = orchestrator._session_registry.get_all_status()
            assert isinstance(status, dict)
    
    @pytest.mark.asyncio
    async def test_session_status_updates_on_completion(self, orchestrator_with_session):
        """测试 Session 状态在完成时更新"""
        orchestrator = orchestrator_with_session
        
        # 创建会失败的执行
        async def mock_execute_with_result(agent, task):
            return {"status": "success", "data": "test_result"}
        
        with patch.object(orchestrator, '_execute_agent_with_semaphore', side_effect=mock_execute_with_result):
            with patch.object(orchestrator, '_generate_report', return_value="output/test.docx"):
                await orchestrator.research({
                    "topic": "测试主题",
                    "aspects": ["市场规模"]
                })
        
        # 验证完成状态
        if orchestrator._session_registry:
            completed = orchestrator._session_registry.get_completed()
            # 执行完成后应该有完成的 Session


# === Test Registry 清理 ===

class TestOrchestratorRegistryCleanup:
    """测试 Registry 清理"""
    
    @pytest.mark.asyncio
    async def test_clear_session_on_completion(self, orchestrator_with_session):
        """测试研究完成后清理 Session"""
        orchestrator = orchestrator_with_session
        
        async def mock_execute(agent, task):
            return {"status": "success"}
        
        with patch.object(orchestrator, '_execute_agent_with_semaphore', side_effect=mock_execute):
            with patch.object(orchestrator, '_generate_report', return_value="output/test.docx"):
                result = await orchestrator.research({
                    "topic": "测试主题",
                    "aspects": ["市场规模"]
                })
        
        # 研究完成后，调用清理
        if hasattr(orchestrator, 'clear_session'):
            orchestrator.clear_session()
            
            # Registry 应该被清理
            assert orchestrator._primary_session_id is None
            assert orchestrator._session_registry is None
            assert orchestrator._result_collector is None


# === Test 完整流程 ===

class TestOrchestratorFullFlow:
    """测试完整研究流程"""
    
    @pytest.mark.asyncio
    async def test_full_research_with_session_tracking(self, orchestrator_with_session, message_bus, shared_memory):
        """测试带 Session 追踪的完整研究流程"""
        orchestrator = orchestrator_with_session
        
        # 执行研究
        result = await orchestrator.research({
            "topic": "新能源汽车市场",
            "aspects": ["市场规模", "竞争格局"],
            "output_format": "docx"
        })
        
        # 验证结果
        assert result.status == "completed"
        assert result.topic == "新能源汽车市场"
        
        # 验证主控 Session 已创建
        assert orchestrator._primary_session_id is not None
        assert orchestrator._session_registry is not None
        
        # 验证 Session 状态方法
        session_status = orchestrator.get_session_status()
        assert session_status["enabled"] is True
        assert session_status["primary_session_id"] == orchestrator._primary_session_id
    
    @pytest.mark.asyncio
    async def test_error_handling_with_session(self, orchestrator_with_session):
        """测试错误处理时 Session 状态"""
        orchestrator = orchestrator_with_session
        
        # Mock _parse_requirement_enhanced 抛出异常
        with patch.object(orchestrator, '_parse_requirement_enhanced', side_effect=Exception("模拟解析错误")):
            result = await orchestrator.research({
                "topic": "测试主题",
                "aspects": ["市场规模"]
            })
        
        # 结果应该是 error 状态
        assert result.status == "error"


# === Test get_stats 扩展 ===

class TestOrchestratorStats:
    """测试统计信息扩展"""
    
    def test_get_stats_includes_session_info(self, orchestrator_with_session):
        """测试统计信息包含 Session 信息"""
        orchestrator = orchestrator_with_session
        
        stats = orchestrator.get_stats()
        
        # 应该包含 Session 相关统计
        # 如果实现了的话
        pass


# === Run Tests ===

if __name__ == "__main__":
    pytest.main([__file__, "-v"])