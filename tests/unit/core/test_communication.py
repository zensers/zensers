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
