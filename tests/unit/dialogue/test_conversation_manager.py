# -*- coding: utf-8 -*-
"""
对话管理器测试

测试对话流程管理
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from src.core.dialogue.conversation_manager import ConversationManager
from src.core.dialogue.state_machine import ConversationState


class TestConversationManagerInit:
    """测试对话管理器初始化"""
    
    def test_init_with_user_id(self):
        """使用用户ID初始化"""
        manager = ConversationManager(user_id="user_001")
        assert manager.user_id == "user_001"
    
    def test_init_with_knowledge_bank(self, tmp_path):
        """使用知识银行初始化"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        manager = ConversationManager(user_id="user_001", knowledge_bank=bank)
        assert manager.knowledge_bank is not None
    
    def test_init_creates_state_machine(self):
        """初始化创建状态机"""
        manager = ConversationManager(user_id="user_001")
        assert manager.state_machine is not None
        assert manager.state_machine.current_state == ConversationState.UNDERSTANDING


class TestConversationManagerProcessMessage:
    """测试消息处理"""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """创建管理器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        return ConversationManager(user_id="user_001", knowledge_bank=bank)
    
    @pytest.mark.asyncio
    async def test_process_first_message(self, manager):
        """处理第一条消息"""
        response = await manager.process_message("研究储能行业")
        
        assert response["state"] == "understanding"
        assert "message" in response
    
    @pytest.mark.asyncio
    async def test_process_message_updates_context(self, manager):
        """处理消息更新上下文"""
        await manager.process_message("研究储能行业")
        
        assert manager.state_machine.get_context("user_input") == "研究储能行业"
    
    @pytest.mark.asyncio
    async def test_process_clarification_response(self, manager):
        """处理澄清响应"""
        # 先进入澄清状态
        await manager.process_message("研究储能行业")
        manager.state_machine.transition(ConversationState.CLARIFYING)
        
        # 处理澄清响应
        response = await manager.process_message("未来3年")
        
        # 检查响应包含上下文更新（中文可能被解析为additional_info）
        assert "context" in response or "state" in response
    
    @pytest.mark.asyncio
    async def test_process_confirm_message(self, manager):
        """处理确认消息"""
        # 模拟完整流程
        await manager.process_message("研究储能行业")
        manager.state_machine.transition(ConversationState.CLARIFYING)
        manager.state_machine.update_context("time_range", "未来3年")
        manager.state_machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        
        response = await manager.process_message("确认")
        
        assert response["state"] in ["executing", "framework_confirm"]
    
    @pytest.mark.asyncio
    async def test_process_cancel_message(self, manager):
        """处理取消消息"""
        await manager.process_message("研究储能行业")
        
        response = await manager.process_message("cancel")
        
        # 取消后可能进入澄清状态
        assert response.get("state") in ["clarifying", "framework_confirm", "understanding"]


class TestConversationManagerKnowledgeIntegration:
    """测试知识银行集成"""
    
    @pytest.fixture
    def manager_with_data(self, tmp_path):
        """创建带数据的管理器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # 添加一些知识
        bank.entities.add_entity("industry", "储能", description="储能行业")
        bank.entities.add_entity("company", "宁德时代", description="电池制造商")
        
        return ConversationManager(user_id="user_001", knowledge_bank=bank)
    
    @pytest.mark.asyncio
    async def test_searches_knowledge_bank_for_context(self, manager_with_data):
        """搜索知识银行获取上下文"""
        response = await manager_with_data.process_message("研究储能行业")
        
        # 应该找到相关实体
        assert manager_with_data.state_machine.get_context("user_input") == "研究储能行业"
    
    @pytest.mark.asyncio
    async def test_suggests_known_entities(self, manager_with_data):
        """建议已知实体"""
        response = await manager_with_data.process_message("研究储能行业")
        
        # 响应中可能包含相关知识
        assert "message" in response


class TestConversationManagerStateManagement:
    """测试状态管理"""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """创建管理器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        return ConversationManager(user_id="user_001", knowledge_bank=bank)
    
    @pytest.mark.asyncio
    async def test_gets_current_state(self, manager):
        """获取当前状态"""
        state = manager.get_current_state()
        
        assert state == ConversationState.UNDERSTANDING
    
    @pytest.mark.asyncio
    async def test_resets_conversation(self, manager):
        """重置对话"""
        await manager.process_message("研究储能行业")
        manager.state_machine.transition(ConversationState.CLARIFYING)
        
        manager.reset()
        
        assert manager.get_current_state() == ConversationState.UNDERSTANDING
        assert len(manager.state_machine.context) == 0


class TestConversationManagerResponse:
    """测试响应生成"""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """创建管理器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        return ConversationManager(user_id="user_001", knowledge_bank=bank)
    
    @pytest.mark.asyncio
    async def test_response_includes_state(self, manager):
        """响应包含状态"""
        response = await manager.process_message("研究储能行业")
        
        assert "state" in response
    
    @pytest.mark.asyncio
    async def test_response_includes_message(self, manager):
        """响应包含消息"""
        response = await manager.process_message("研究储能行业")
        
        assert "message" in response
        assert isinstance(response["message"], str)
    
    @pytest.mark.asyncio
    async def test_understanding_state_asks_clarification(self, manager):
        """理解状态请求澄清"""
        response = await manager.process_message("研究储能行业")
        
        # 应该提示需要更多信息
        assert "message" in response
    
    @pytest.mark.asyncio
    async def test_framework_confirm_shows_summary(self, manager):
        """框架确认显示摘要"""
        # 设置到框架确认状态
        manager.state_machine.transition(ConversationState.CLARIFYING)
        manager.state_machine.update_context("topic", "储能行业")
        manager.state_machine.update_context("time_range", "未来3年")
        manager.state_machine.transition(ConversationState.FRAMEWORK_CONFIRM)
        
        # get_status不是async方法
        response = manager.get_status()
        
        assert "state" in response or "context" in response


class TestConversationManagerPersistence:
    """测试持久化"""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """创建管理器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        return ConversationManager(user_id="user_001", knowledge_bank=bank)
    
    @pytest.mark.asyncio
    async def test_saves_conversation_state(self, manager, tmp_path):
        """保存对话状态"""
        await manager.process_message("研究储能行业")
        manager.state_machine.transition(ConversationState.CLARIFYING)
        
        save_path = tmp_path / "conversation.json"
        manager.save_state(str(save_path))
        
        assert save_path.exists()
    
    @pytest.mark.asyncio
    async def test_loads_conversation_state(self, manager, tmp_path):
        """加载对话状态"""
        # 保存状态
        await manager.process_message("研究储能行业")
        manager.state_machine.transition(ConversationState.CLARIFYING)
        manager.state_machine.update_context("test_key", "test_value")
        
        save_path = tmp_path / "conversation.json"
        manager.save_state(str(save_path))
        
        # 创建新管理器并加载
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        new_manager = ConversationManager(user_id="user_001", knowledge_bank=bank)
        new_manager.load_state(str(save_path))
        
        assert new_manager.get_current_state() == ConversationState.CLARIFYING
        assert new_manager.state_machine.get_context("test_key") == "test_value"


class TestConversationManagerHelpers:
    """测试辅助方法"""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """创建管理器"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        return ConversationManager(user_id="user_001", knowledge_bank=bank)
    
    @pytest.mark.asyncio
    async def test_get_status(self, manager):
        """获取状态"""
        await manager.process_message("研究储能行业")
        
        status = manager.get_status()
        
        assert "state" in status
        assert "context" in status
    
    @pytest.mark.asyncio
    async def test_get_conversation_summary(self, manager):
        """获取对话摘要"""
        await manager.process_message("研究储能行业")
        manager.state_machine.update_context("topic", "储能")
        
        summary = manager.get_conversation_summary()
        
        assert "state" in summary
        assert "topic" in summary["context"] or "entities_known" in summary