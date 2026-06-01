"""
ResultCollector 单元测试

测试事件驱动的结果收集机制
"""
import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

# 测试目标模块
from src.core.agents.result_collector import ResultCollector
from src.core.communication import MessageBus, Event, SharedMemory


class TestResultCollector:
    """测试 ResultCollector 结果收集器"""
    
    @pytest.mark.asyncio
    async def test_create_collector(self):
        """测试创建收集器"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        
        assert collector.parent_session_id == "parent_001"
        assert len(collector._results) == 0
    
    @pytest.mark.asyncio
    async def test_setup_subscribes_to_events(self):
        """测试setup订阅事件"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        # 检查是否订阅了completed事件
        count = message_bus.get_subscriber_count("session.parent_001.agent.completed")
        assert count == 1
    
    @pytest.mark.asyncio
    async def test_handle_agent_completed(self):
        """测试处理Agent完成事件"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        event = Event(
            type="agent.completed",
            data={
                "session_id": "session_001",
                "agent_id": "agent_001",
                "result": {"output": "success"}
            }
        )
        
        # 发布事件
        await message_bus.publish("session.parent_001.agent.completed", event)
        
        # 等待事件处理
        await asyncio.sleep(0.1)
        
        # 检查结果
        assert "session_001" in collector._results
        assert collector._results["session_001"]["result"] == {"output": "success"}
    
    @pytest.mark.asyncio
    async def test_wait_for_agent_immediate_result(self):
        """测试等待已有结果的Agent"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        # 先添加结果
        collector._results["session_001"] = {
            "session_id": "session_001",
            "agent_id": "agent_001",
            "result": {"done": True}
        }
        
        # 等待应该立即返回
        result = await collector.wait_for_agent("session_001", timeout=1.0)
        
        assert result is not None
        assert result["session_id"] == "session_001"
    
    @pytest.mark.asyncio
    async def test_wait_for_agent_timeout(self):
        """测试等待超时"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        result = await collector.wait_for_agent("nonexistent", timeout=0.5)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_wait_for_agent_event_triggered(self):
        """测试事件触发等待完成"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        async def delayed_complete():
            await asyncio.sleep(0.2)
            event = Event(
                type="agent.completed",
                data={
                    "session_id": "session_001",
                    "agent_id": "agent_001",
                    "result": {"output": "delayed"}
                }
            )
            await message_bus.publish("session.parent_001.agent.completed", event)
        
        # 启动延迟任务
        task = asyncio.create_task(delayed_complete())
        
        # 等待结果
        result = await collector.wait_for_agent("session_001", timeout=2.0)
        
        await task  # 确保任务完成
        
        assert result is not None
        assert result["result"]["output"] == "delayed"
    
    @pytest.mark.asyncio
    async def test_wait_for_all(self):
        """测试等待所有Agent"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        # 先添加两个结果
        collector._results["session_001"] = {
            "session_id": "session_001",
            "result": {"data": 1}
        }
        collector._results["session_002"] = {
            "session_id": "session_002",
            "result": {"data": 2}
        }
        
        results = await collector.wait_for_all(
            ["session_001", "session_002"],
            timeout=1.0
        )
        
        assert len(results) == 2
        assert results["session_001"]["result"]["data"] == 1
        assert results["session_002"]["result"]["data"] == 2
    
    @pytest.mark.asyncio
    async def test_wait_for_all_with_timeout(self):
        """测试等待所有Agent（部分超时）"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        # 只添加一个结果
        collector._results["session_001"] = {
            "session_id": "session_001",
            "result": {"data": 1}
        }
        
        results = await collector.wait_for_all(
            ["session_001", "session_002", "session_003"],
            timeout=0.5
        )
        
        assert len(results) == 3
        assert results["session_001"] is not None
        assert results["session_002"] is None  # 超时
        assert results["session_003"] is None  # 超时
    
    @pytest.mark.asyncio
    async def test_get_results(self):
        """测试获取所有结果"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        collector._results["session_001"] = {"data": 1}
        collector._results["session_002"] = {"data": 2}
        
        results = collector.get_results()
        
        assert len(results) == 2
        assert "session_001" in results
        assert "session_002" in results
    
    @pytest.mark.asyncio
    async def test_clear_results(self):
        """测试清空结果"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        collector._results["session_001"] = {"data": 1}
        
        collector.clear()
        
        assert len(collector._results) == 0
    
    @pytest.mark.asyncio
    async def test_multiple_completions(self):
        """测试多个Agent完成"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        # 发布多个完成事件
        for i in range(5):
            event = Event(
                type="agent.completed",
                data={
                    "session_id": f"session_{i:03d}",
                    "agent_id": f"agent_{i:03d}",
                    "result": {"index": i}
                }
            )
            await message_bus.publish("session.parent_001.agent.completed", event)
        
        # 等待事件处理
        await asyncio.sleep(0.2)
        
        assert len(collector._results) == 5
    
    @pytest.mark.asyncio
    async def test_result_has_timestamp(self):
        """测试结果包含时间戳"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        event = Event(
            type="agent.completed",
            data={
                "session_id": "session_001",
                "agent_id": "agent_001",
                "result": {"output": "success"}
            }
        )
        
        await message_bus.publish("session.parent_001.agent.completed", event)
        await asyncio.sleep(0.1)
        
        result = collector._results["session_001"]
        assert "completed_at" in result


class TestResultCollectorIntegration:
    """测试 ResultCollector 与 AgentSession 集成"""
    
    @pytest.mark.asyncio
    async def test_collector_with_registry(self):
        """测试收集器与注册表协作"""
        from src.core.agents.agent_session import AgentSession, AgentSessionRegistry, AgentSessionStatus
        
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        # 创建注册表
        registry = AgentSessionRegistry(parent_session_id="parent_001")
        
        # 创建收集器
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        # 创建Session
        session = AgentSession(
            session_id="session_001",
            agent_id="agent_001"
        )
        registry.register(session)
        
        # 更新状态并发布事件
        registry.update_status(
            "session_001",
            AgentSessionStatus.COMPLETED,
            progress=1.0,
            result={"output": "success"}
        )
        
        # 发布完成事件
        event = Event(
            type="agent.completed",
            data={
                "session_id": "session_001",
                "agent_id": "agent_001",
                "result": {"output": "success"}
            }
        )
        await message_bus.publish("session.parent_001.agent.completed", event)
        
        # 等待处理
        await asyncio.sleep(0.1)
        
        # 验证结果
        result = await collector.wait_for_agent("session_001", timeout=1.0)
        assert result is not None


class TestResultCollectorEdgeCases:
    """测试边缘情况"""
    
    @pytest.mark.asyncio
    async def test_duplicate_session_completion(self):
        """测试重复的Session完成事件"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        # 发送两次相同的事件
        event1 = Event(
            type="agent.completed",
            data={
                "session_id": "session_001",
                "agent_id": "agent_001",
                "result": {"output": "first"}
            }
        )
        await message_bus.publish("session.parent_001.agent.completed", event1)
        await asyncio.sleep(0.1)
        
        # 第二次事件覆盖第一次
        event2 = Event(
            type="agent.completed",
            data={
                "session_id": "session_001",
                "agent_id": "agent_001",
                "result": {"output": "second"}
            }
        )
        await message_bus.publish("session.parent_001.agent.completed", event2)
        await asyncio.sleep(0.1)
        
        # 结果应该被更新
        assert collector._results["session_001"]["result"]["output"] == "second"
    
    @pytest.mark.asyncio
    async def test_empty_result(self):
        """测试空结果"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        event = Event(
            type="agent.completed",
            data={
                "session_id": "session_001",
                "agent_id": "agent_001",
                "result": None
            }
        )
        await message_bus.publish("session.parent_001.agent.completed", event)
        await asyncio.sleep(0.1)
        
        assert "session_001" in collector._results
        assert collector._results["session_001"]["result"] is None
    
    @pytest.mark.asyncio
    async def test_large_result(self):
        """测试大量结果"""
        message_bus = MessageBus()
        shared_memory = SharedMemory()
        
        collector = ResultCollector(
            parent_session_id="parent_001",
            message_bus=message_bus,
            shared_memory=shared_memory
        )
        await collector.setup()
        
        large_data = {"data": list(range(10000))}
        event = Event(
            type="agent.completed",
            data={
                "session_id": "session_001",
                "agent_id": "agent_001",
                "result": large_data
            }
        )
        await message_bus.publish("session.parent_001.agent.completed", event)
        await asyncio.sleep(0.1)
        
        result = collector._results["session_001"]
        assert len(result["result"]["data"]) == 10000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])