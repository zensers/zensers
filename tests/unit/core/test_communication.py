"""
MessageBus 和 SharedMemory 的单元测试
"""
import pytest
import asyncio
from typing import Any, List


class TestMessageBus:
    """MessageBus 测试类"""
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_message_bus_init(self):
        """测试 MessageBus 可以初始化"""
        from src.core.communication import MessageBus
        
        bus = MessageBus()
        assert bus is not None
        assert isinstance(bus, MessageBus)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_publish_subscribe(self):
        """测试发布-订阅基本功能"""
        from src.core.communication import MessageBus, Event
        
        bus = MessageBus()
        received_messages: List[Event] = []
        
        async def handler(event: Event):
            received_messages.append(event)
        
        # 订阅主题
        await bus.subscribe("test.topic", handler)
        
        # 发布事件
        event = Event(type="test", data={"message": "hello"})
        await bus.publish("test.topic", event)
        
        # 等待异步处理
        await asyncio.sleep(0.1)
        
        # 验证消息被接收
        assert len(received_messages) == 1
        assert received_messages[0].type == "test"
        assert received_messages[0].data["message"] == "hello"
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        """测试多个订阅者都能收到消息"""
        from src.core.communication import MessageBus, Event
        
        bus = MessageBus()
        received_by_handler1: List[Event] = []
        received_by_handler2: List[Event] = []
        
        async def handler1(event: Event):
            received_by_handler1.append(event)
        
        async def handler2(event: Event):
            received_by_handler2.append(event)
        
        # 两个订阅者订阅同一主题
        await bus.subscribe("test.topic", handler1)
        await bus.subscribe("test.topic", handler2)
        
        # 发布事件
        event = Event(type="test", data={"message": "broadcast"})
        await bus.publish("test.topic", event)
        
        # 等待异步处理
        await asyncio.sleep(0.1)
        
        # 验证两个订阅者都收到
        assert len(received_by_handler1) == 1
        assert len(received_by_handler2) == 1
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_different_topics(self):
        """测试不同主题的消息不会混淆"""
        from src.core.communication import MessageBus, Event
        
        bus = MessageBus()
        topic1_messages: List[Event] = []
        topic2_messages: List[Event] = []
        
        async def handler1(event: Event):
            topic1_messages.append(event)
        
        async def handler2(event: Event):
            topic2_messages.append(event)
        
        # 订阅不同主题
        await bus.subscribe("topic1", handler1)
        await bus.subscribe("topic2", handler2)
        
        # 只向 topic1 发布
        event = Event(type="test", data={"message": "only for topic1"})
        await bus.publish("topic1", event)
        
        # 等待异步处理
        await asyncio.sleep(0.1)
        
        # 验证只有 topic1 收到
        assert len(topic1_messages) == 1
        assert len(topic2_messages) == 0


class TestSharedMemory:
    """SharedMemory 测试类"""
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_shared_memory_init(self):
        """测试 SharedMemory 可以初始化"""
        from src.core.communication import SharedMemory
        
        memory = SharedMemory()
        assert memory is not None
        assert isinstance(memory, SharedMemory)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_read_write(self):
        """测试基本的读写操作"""
        from src.core.communication import SharedMemory
        
        memory = SharedMemory()
        
        # 写入数据
        await memory.write("key1", {"data": "value1"})
        
        # 读取数据
        result = await memory.read("key1")
        
        assert result == {"data": "value1"}
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_read_nonexistent_key(self):
        """测试读取不存在的key返回None"""
        from src.core.communication import SharedMemory
        
        memory = SharedMemory()
        
        result = await memory.read("nonexistent")
        
        assert result is None
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_existing_key(self):
        """测试更新已有key的值"""
        from src.core.communication import SharedMemory
        
        memory = SharedMemory()
        
        # 先写入
        await memory.write("key1", "original")
        
        # 再更新
        await memory.write("key1", "updated")
        
        # 读取
        result = await memory.read("key1")
        
        assert result == "updated"
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """测试并发访问安全"""
        from src.core.communication import SharedMemory
        
        memory = SharedMemory()
        results = []
        
        async def writer(value: int):
            await memory.write(f"key_{value}", value)
        
        async def reader(key: str):
            result = await memory.read(key)
            results.append(result)
        
        # 并发写入
        await asyncio.gather(*[writer(i) for i in range(10)])
        
        # 并发读取
        await asyncio.gather(*[reader(f"key_{i}") for i in range(10)])
        
        # 验证所有数据正确
        assert len(results) == 10
        assert set(results) == set(range(10))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_canonical_memory_isolated_by_async_task_scope(self):
        """Concurrent research sessions must not overwrite canonical metrics."""
        from src.core.communication import SharedMemory, set_memory_scope

        memory = SharedMemory()

        async def session(scope, value):
            set_memory_scope(scope)
            await memory.write_canonical(
                metric="revenue_2025",
                value=value,
                caliber="search_result",
                source=scope,
                publisher=scope,
            )
            entry = await memory.get_canonical("revenue_2025")
            return entry["value"]

        values = await asyncio.gather(
            session("session_a", 100),
            session("session_b", 200),
        )

        assert values == [100, 200]

        set_memory_scope("session_a")
        assert memory.get_canonical_sync("revenue_2025")["value"] == 100
        set_memory_scope("session_b")
        assert memory.get_canonical_sync("revenue_2025")["value"] == 200
        set_memory_scope(None)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_canonical_bus_events_are_filtered_by_scope(self):
        from src.core.communication import MessageBus, SharedMemory, set_memory_scope
        from src.core.orchestrator.execution.data_collector import DataCollector

        bus = MessageBus()
        memory = SharedMemory(message_bus=bus)
        collector_a = DataCollector(scope="session_a")
        collector_b = DataCollector(scope="session_b")
        await bus.subscribe("data.canonical.updated", collector_a.on_canonical_updated)
        await bus.subscribe("data.canonical.updated", collector_b.on_canonical_updated)

        async def publish(scope, value):
            set_memory_scope(scope)
            await memory.write_canonical(
                metric="margin_2025", value=value,
                caliber="search_result", source=scope, publisher=scope,
            )

        await asyncio.gather(publish("session_a", 10), publish("session_b", 20))

        assert collector_a.get_canonical_data()["margin_2025"]["value"] == 10
        assert collector_b.get_canonical_data()["margin_2025"]["value"] == 20
        set_memory_scope(None)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rejected_same_caliber_conflict_is_published(self):
        from src.core.communication import MessageBus, SharedMemory

        bus = MessageBus()
        events = []

        async def handler(event):
            events.append(event)

        await bus.subscribe("data.conflict.detected", handler)
        memory = SharedMemory(message_bus=bus)
        await memory.write_canonical("sales", 100, "search_result", "source-a", "agent-a")
        conflict = await memory.write_canonical("sales", 120, "search_result", "source-b", "agent-b")

        assert conflict is not None
        await asyncio.sleep(0)
        assert len(events) == 1
        assert events[0].data["metric"] == "sales"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rejected_lower_priority_conflict_is_published(self):
        from src.core.communication import MessageBus, SharedMemory

        bus = MessageBus()
        events = []

        async def handler(event):
            events.append(event)

        await bus.subscribe("data.conflict.detected", handler)
        memory = SharedMemory(message_bus=bus)
        await memory.write_canonical("sales", 100, "structured_source", "source-a", "agent-a")
        conflict = await memory.write_canonical("sales", 120, "search_result", "source-b", "agent-b")

        assert conflict is not None
        assert (await memory.get_canonical("sales"))["value"] == 100
        await asyncio.sleep(0)
        assert len(events) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rejected_same_value_lower_priority_write_is_silent(self):
        from src.core.communication import MessageBus, SharedMemory

        bus = MessageBus()
        events = []

        async def handler(event):
            events.append(event)

        await bus.subscribe("data.canonical.updated", handler)
        await bus.subscribe("data.conflict.detected", handler)
        memory = SharedMemory(message_bus=bus)
        await memory.write_canonical("sales", 100, "structured_source", "source-a", "agent-a")
        result = await memory.write_canonical("sales", 100, "search_result", "source-b", "agent-b")

        assert result is None
        assert (await memory.get_canonical("sales"))["source"] == "source-a"
        await asyncio.sleep(0)
        assert len(events) == 1
        assert events[0].type == "data.canonical.updated"

    @pytest.mark.unit
    def test_resolve_shared_memory_uses_configured_container_instance(self):
        from src.core.communication import SharedMemory, resolve_shared_memory
        from src.core.container import configure_container, reset_container

        memory = SharedMemory()
        configure_container(shared_memory=memory)
        try:
            assert resolve_shared_memory() is memory
        finally:
            reset_container()


class TestGetCanonicalSyncPrefixFallback:
    """Test get_canonical_sync prefix fallback removal (defect 3.10)"""

    @pytest.mark.unit
    async def test_exact_match_returns_correct_value(self):
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        await memory.write_canonical(
            metric="净利润_2024", value=100.0,
            caliber="structured_source", source="年报", publisher="agent1",
        )
        result = memory.get_canonical_sync("净利润_2024")
        assert result is not None
        assert result["value"] == 100.0

    @pytest.mark.unit
    async def test_missing_exact_match_returns_none_not_prefix_fallback(self):
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        await memory.write_canonical(
            metric="净利润_2024", value=100.0,
            caliber="structured_source", source="年报", publisher="agent1",
        )
        result = memory.get_canonical_sync("净利润_2025")
        assert result is None

    @pytest.mark.unit
    async def test_prefix_fallback_does_not_return_wrong_year(self):
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        await memory.write_canonical(
            metric="营收_2024", value=500.0,
            caliber="structured_source", source="年报", publisher="agent1",
        )
        result = memory.get_canonical_sync("营收_2025")
        assert result is None

    @pytest.mark.unit
    async def test_different_prefix_no_cross_match(self):
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        await memory.write_canonical(
            metric="毛利率_2024", value=30.0,
            caliber="structured_source", source="年报", publisher="agent1",
        )
        result = memory.get_canonical_sync("净利率_2024")
        assert result is None


class TestCanonicalKeyWriteProtection:
    """Test canonical key write protection via non-canonical paths (defect 2.2)"""

    @pytest.mark.unit
    def test_set_canonical_key_logs_warning(self, caplog):
        import logging
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        with caplog.at_level(logging.WARNING):
            memory.set("canonical:净利润_2024", {"value": 100.0})
        assert any("canonical" in r.message.lower() and "non-quality-controlled" in r.message.lower()
                    for r in caplog.records)

    @pytest.mark.unit
    def test_set_canonical_registry_prefix_logs_warning(self, caplog):
        import logging
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        with caplog.at_level(logging.WARNING):
            memory.set("_canonical_registry", {"净利润": 100.0})
        assert any("canonical" in r.message.lower() and "non-quality-controlled" in r.message.lower()
                    for r in caplog.records)

    @pytest.mark.unit
    def test_set_non_canonical_key_no_warning(self, caplog):
        import logging
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        with caplog.at_level(logging.WARNING):
            memory.set("search_results", [1, 2, 3])
        assert not any("canonical" in r.message.lower() for r in caplog.records)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_write_canonical_key_logs_warning(self, caplog):
        import logging
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        with caplog.at_level(logging.WARNING):
            await memory.write("canonical:净利润_2024", {"value": 100.0})
        assert any("canonical" in r.message.lower() and "non-quality-controlled" in r.message.lower()
                    for r in caplog.records)


class TestWriteCanonicalSourceValidation:
    """Test write_canonical source_type validation (defect 3.1)"""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_source_type_logs_warning(self, caplog):
        import logging
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        with caplog.at_level(logging.WARNING):
            await memory.write_canonical(
                metric="净利润_2024", value=100.0,
                caliber="unknown_source_type", source="test", publisher="agent1",
            )
        assert any("source_type" in r.message and "not in SOURCE_PRIORITY" in r.message
                    for r in caplog.records)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_valid_source_type_no_warning(self, caplog):
        import logging
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        with caplog.at_level(logging.WARNING):
            await memory.write_canonical(
                metric="净利润_2024", value=100.0,
                caliber="structured_source", source="test", publisher="agent1",
            )
        assert not any("source_type" in r.message for r in caplog.records)


class TestNonNumericCanonicalConflictDetection:
    """Test conflict detection for non-numeric canonical data (defect 4.4)"""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_same_caliber_string_conflict_detected(self):
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        await memory.write_canonical(
            metric="target_market", value="新能源汽车",
            caliber="llm_inference", source="agent1", publisher="风险",
        )
        conflict = await memory.write_canonical(
            metric="target_market", value="传统燃油车",
            caliber="llm_inference", source="agent2", publisher="风险",
        )
        assert conflict is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cross_priority_string_conflict_recorded(self):
        """Different-priority string values should still generate a conflict event for audit"""
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        await memory.write_canonical(
            metric="target_market", value="新能源汽车",
            caliber="llm_inference", source="agent1", publisher="风险",
        )
        conflict = await memory.write_canonical(
            metric="target_market", value="传统燃油车",
            caliber="structured_source", source="年报", publisher="agent1",
        )
        assert conflict is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dict_statement_conflict_detected(self):
        from src.core.communication import SharedMemory

        memory = SharedMemory()
        await memory.write_canonical(
            metric="claim:风险:0",
            value={"statement": "市场前景乐观", "confidence": "HIGH"},
            caliber="llm_inference", source="agent1", publisher="风险",
        )
        conflict = await memory.write_canonical(
            metric="claim:风险:0",
            value={"statement": "市场前景悲观", "confidence": "HIGH"},
            caliber="llm_inference", source="agent2", publisher="风险",
        )
        assert conflict is not None
