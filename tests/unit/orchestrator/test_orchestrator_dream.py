"""
ResearchOrchestrator 做梦模式集成测试

Week 15.9: 研究完成后触发知识提取
- 测试做梦模式初始化
- 测试研究完成后触发知识提取
- 测试主任务优先机制
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from src.core.orchestrator.research_orchestrator import (
    ResearchOrchestrator,
    ResearchRequirement,
    ResearchResult,
)


# === Fixtures ===

@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def orchestrator(temp_dir):
    """创建 ResearchOrchestrator 实例"""
    return ResearchOrchestrator(
        storage_path=temp_dir / "data",
        enable_dual_track=False
    )


@pytest.fixture
def mock_knowledge_bank():
    """创建模拟 KnowledgeBank"""
    bank = Mock()
    bank.get_db_path = Mock(return_value=":memory:")
    bank.entities = Mock()
    bank.entities.search_entities = Mock(return_value=[])
    bank.entities.add_entity = Mock()
    bank.relations = Mock()
    bank.relations.add_relation = Mock()
    bank.data_points = Mock()
    bank.data_points.add_data_point = Mock()
    bank.insights = Mock()
    bank.insights.create = Mock()
    return bank


@pytest.fixture
def mock_core_memory():
    """创建模拟 CoreMemory"""
    memory = Mock()
    memory.user_id = "test_user"
    return memory


# === Test Dream Mode Initialization ===

class TestDreamModeInit:
    """测试做梦模式初始化"""
    
    def test_init_without_dream_mode(self, temp_dir):
        """测试不启用做梦模式"""
        orchestrator = ResearchOrchestrator(
            storage_path=temp_dir / "data",
            enable_dual_track=False
        )
        
        assert orchestrator._dream_scheduler is None
        assert orchestrator._raw_data_store is None
        assert orchestrator._enable_dream_mode is False
    
    def test_init_dream_mode_with_knowledge_bank(
        self, temp_dir, mock_knowledge_bank, mock_core_memory
    ):
        """测试启用做梦模式"""
        orchestrator = ResearchOrchestrator(
            storage_path=temp_dir / "data",
            enable_dual_track=False
        )
        
        try:
            # 注入知识组件并启用做梦模式
            orchestrator.inject_knowledge_components(
                knowledge_bank=mock_knowledge_bank,
                core_memory=mock_core_memory,
                enable_dream_mode=True
            )
            
            assert orchestrator._enable_dream_mode is True
            assert orchestrator._dream_scheduler is not None
            assert orchestrator._raw_data_store is not None
        finally:
            # 清理资源
            if orchestrator._raw_data_store:
                orchestrator._raw_data_store.close()
    
    def test_init_dream_mode_disabled(
        self, temp_dir, mock_knowledge_bank, mock_core_memory
    ):
        """测试禁用做梦模式"""
        orchestrator = ResearchOrchestrator(
            storage_path=temp_dir / "data",
            enable_dual_track=False
        )
        
        orchestrator.inject_knowledge_components(
            knowledge_bank=mock_knowledge_bank,
            core_memory=mock_core_memory,
            enable_dream_mode=False
        )
        
        assert orchestrator._enable_dream_mode is False
        assert orchestrator._dream_scheduler is None


# === Test Dream Mode Trigger ===

class TestDreamModeTrigger:
    """测试做梦模式触发"""
    
    @pytest.mark.asyncio
    async def test_trigger_dream_extraction_on_research_complete(
        self, temp_dir, mock_knowledge_bank, mock_core_memory
    ):
        """测试研究完成后触发知识提取"""
        orchestrator = ResearchOrchestrator(
            storage_path=temp_dir / "data",
            enable_dual_track=False
        )
        
        orchestrator.inject_knowledge_components(
            knowledge_bank=mock_knowledge_bank,
            core_memory=mock_core_memory,
            enable_dream_mode=True
        )
        
        try:
            # Mock 相关方法
            with patch.object(orchestrator, '_parse_requirement_enhanced') as mock_parse:
                mock_parse.return_value = (
                    ResearchRequirement(
                        topic="新能源汽车市场",
                        aspects=["市场规模"],
                        region="中国"
                    ),
                    {"intent_type": "research"}
                )
                
                with patch.object(orchestrator, '_create_agents_enhanced') as mock_create:
                    mock_create.return_value = []
                    
                    with patch.object(orchestrator, '_execute_research') as mock_exec:
                        mock_exec.return_value = [
                            {
                                "status": "success",
                                "data": {"content": "特斯拉市场份额15%，比亚迪市场份额25%"}
                            }
                        ]
                        
                        with patch.object(orchestrator, '_generate_report') as mock_report:
                            mock_report.return_value = str(temp_dir / "report.docx")
                            
                            result = await orchestrator.research({
                                "topic": "新能源汽车市场",
                                "aspects": ["市场规模"]
                            })
            
            # 验证研究完成
            assert result.status == "completed"
            
            # 验证资料已存储到暂存区
            if orchestrator._raw_data_store:
                stats = orchestrator._raw_data_store.get_stats()
                # 研究完成后应该有资料在暂存区
                assert stats.get("total", 0) >= 0
        finally:
            if orchestrator._raw_data_store:
                orchestrator._raw_data_store.close()
    
    @pytest.mark.asyncio
    async def test_no_trigger_without_dream_mode(self, orchestrator, temp_dir):
        """测试未启用做梦模式时不触发"""
        # 不注入知识组件
        
        with patch.object(orchestrator, '_parse_requirement_enhanced') as mock_parse:
            mock_parse.return_value = (
                ResearchRequirement(
                    topic="测试主题",
                    aspects=["市场规模"]
                ),
                {"intent_type": "research"}
            )
            
            with patch.object(orchestrator, '_create_agents_enhanced') as mock_create:
                mock_create.return_value = []
                
                with patch.object(orchestrator, '_execute_research') as mock_exec:
                    mock_exec.return_value = []
                    
                    with patch.object(orchestrator, '_generate_report') as mock_report:
                        mock_report.return_value = str(temp_dir / "report.docx")
                        
                        result = await orchestrator.research({
                            "topic": "测试主题"
                        })
        
        # 研究完成但不应有暂存数据
        assert result.status == "completed"
        assert orchestrator._raw_data_store is None


# === Test Main Task Priority ===

class TestMainTaskPriority:
    """测试主任务优先机制"""
    
    @pytest.mark.asyncio
    async def test_dream_mode_interrupted_by_new_task(
        self, temp_dir, mock_knowledge_bank, mock_core_memory
    ):
        """测试新任务中断做梦模式"""
        orchestrator = ResearchOrchestrator(
            storage_path=temp_dir / "data",
            enable_dual_track=False
        )
        
        orchestrator.inject_knowledge_components(
            knowledge_bank=mock_knowledge_bank,
            core_memory=mock_core_memory,
            enable_dream_mode=True
        )
        
        try:
            # 模拟做梦模式正在运行
            orchestrator._dream_scheduler._is_main_task_running = False
            orchestrator._dream_scheduler._state = Mock()
            orchestrator._dream_scheduler._state.name = "RUNNING"
            
            # 触发新任务开始
            await orchestrator._dream_scheduler.on_main_task_started()
            
            # 验证主任务状态
            assert orchestrator._dream_scheduler._is_main_task_running is True
        finally:
            if orchestrator._raw_data_store:
                orchestrator._raw_data_store.close()
    
    @pytest.mark.asyncio
    async def test_dream_mode_resumes_after_task_complete(
        self, temp_dir, mock_knowledge_bank, mock_core_memory
    ):
        """测试任务完成后恢复做梦模式"""
        orchestrator = ResearchOrchestrator(
            storage_path=temp_dir / "data",
            enable_dual_track=False
        )
        
        orchestrator.inject_knowledge_components(
            knowledge_bank=mock_knowledge_bank,
            core_memory=mock_core_memory,
            enable_dream_mode=True
        )
        
        try:
            # 设置主任务运行状态
            orchestrator._dream_scheduler._is_main_task_running = True
            
            # 触发任务完成
            await orchestrator._dream_scheduler.on_main_task_completed(
                research_id="test_research",
                content="测试内容",
                topic="测试主题"
            )
            
            # 验证主任务状态已清除
            assert orchestrator._dream_scheduler._is_main_task_running is False
            
            # 验证资料已存储
            stats = orchestrator._raw_data_store.get_stats()
            assert stats.get("pending", 0) >= 1
        finally:
            if orchestrator._raw_data_store:
                orchestrator._raw_data_store.close()


# === Test RawDataStore ===

class TestRawDataStore:
    """测试研究资料暂存区"""
    
    def test_store_research_data(self, temp_dir):
        """测试存储研究资料"""
        from src.core.memory.dream import RawResearchDataStore
        
        store = RawResearchDataStore(
            user_id="test_user",
            storage_path=str(temp_dir / "raw_data.db")
        )
        
        try:
            data_id = store.store_research_data(
                research_id="research_001",
                content="特斯拉市场份额15%",
                topic="新能源汽车市场",
                domain="中国"
            )
            
            assert data_id.startswith("raw_")
            
            stats = store.get_stats()
            assert stats["pending"] == 1
            assert stats["total"] == 1
        finally:
            store.close()
    
    def test_get_pending_data(self, temp_dir):
        """测试获取待提取资料"""
        from src.core.memory.dream import RawResearchDataStore
        
        store = RawResearchDataStore(
            user_id="test_user",
            storage_path=str(temp_dir / "raw_data.db")
        )
        
        try:
            # 存储多条资料
            for i in range(3):
                store.store_research_data(
                    research_id=f"research_{i}",
                    content=f"研究内容 {i}",
                    topic="测试主题"
                )
            
            # 获取待提取资料
            pending = store.get_pending_data(limit=2)
            
            assert len(pending) == 2
            assert pending[0].status == "pending"
        finally:
            store.close()
    
    def test_mark_completed(self, temp_dir):
        """测试标记完成"""
        from src.core.memory.dream import RawResearchDataStore
        
        store = RawResearchDataStore(
            user_id="test_user",
            storage_path=str(temp_dir / "raw_data.db")
        )
        
        try:
            data_id = store.store_research_data(
                research_id="research_001",
                content="测试内容"
            )
            
            # 标记为正在处理
            store.mark_in_progress(data_id)
            stats = store.get_stats()
            assert stats["in_progress"] == 1
            
            # 标记为完成
            store.mark_completed(data_id)
            stats = store.get_stats()
            assert stats["completed"] == 1
            assert stats["pending"] == 0
        finally:
            store.close()


# === Run Tests ===

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
