"""
KnowledgeManager 单元测试
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.core.memory.knowledge_manager import KnowledgeManager
from src.core.memory.config import KnowledgeConfig


class TestKnowledgeManager:
    """KnowledgeManager 测试类"""
    
    @pytest.fixture
    def mock_knowledge_bank(self):
        """创建模拟 KnowledgeBank"""
        mock_bank = Mock()
        mock_bank.get_knowledge_summary = AsyncMock(return_value={
            "stats": {
                "total_research": 5,
                "entities_known": 45,
                "relations_understood": 28,
                "insights_gained": 12
            }
        })
        mock_bank.deposit_from_research = AsyncMock(return_value={"status": "success"})
        mock_bank.get_relevant_knowledge = AsyncMock(return_value={
            "entities": [{"name": "实体1"}],
            "relations": [],
            "summary": "找到 1 个相关实体"
        })
        mock_bank.search_all = Mock(return_value={
            "entities": [{"name": "特斯拉"}],
            "relations": [],
            "data_points": []
        })
        mock_bank.import_file = Mock(return_value=Mock(status="success", file_path="test.pdf"))
        mock_bank.import_directory = Mock(return_value=[
            Mock(status="success", file_path="file1.pdf"),
            Mock(status="success", file_path="file2.pdf")
        ])
        mock_bank.compile_research = Mock(return_value=Mock(get_stats=Mock(return_value={"pages": 5})))
        mock_bank.detect_contradictions = Mock(return_value=[
            Mock(entity_name="特斯拉", attribute="revenue", value_1="100", value_2="200")
        ])
        mock_bank.record_learning = Mock(return_value={
            "learning_id": "learning_001",
            "status": "recorded"
        })
        mock_bank.auto_promote_learnings = Mock(return_value=[
            {"learning_id": "learning_001", "promoted": True}
        ])
        mock_bank.export_to_dict = Mock(return_value={"entities": [], "relations": []})
        mock_bank.export_to_file = Mock()
        mock_bank.close = Mock()
        return mock_bank
    
    @pytest.fixture
    def mock_core_memory(self):
        """创建模拟 CoreMemory"""
        mock_core = Mock()
        mock_core.close = Mock()
        return mock_core
    
    @pytest.fixture
    def config(self):
        """创建测试配置"""
        return KnowledgeConfig(
            max_top_entities=30,
            enable_knowledge_compiler=True,
            enable_contradiction_detector=True
        )
    
    def test_init_with_config(self, config, mock_knowledge_bank, mock_core_memory):
        """测试使用配置初始化"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                assert manager.user_id == "test_user"
                assert manager.config == config
    
    def test_init_with_default_config(self, mock_knowledge_bank, mock_core_memory):
        """测试使用默认配置初始化"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user")
                
                assert manager.user_id == "test_user"
                assert isinstance(manager.config, KnowledgeConfig)
    
    def test_context_manager(self, config, mock_knowledge_bank, mock_core_memory):
        """测试上下文管理器"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                with KnowledgeManager(user_id="test_user", config=config) as manager:
                    assert manager is not None
    
    @pytest.mark.asyncio
    async def test_deposit(self, config, mock_knowledge_bank, mock_core_memory):
        """测试存入知识"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                result = await manager.deposit(
                    research_id="research_001",
                    content={
                        "topic": "测试主题",
                        "content": "测试内容",
                        "entities": ["实体1", "实体2"]
                    }
                )
                
                assert result is not None
                mock_knowledge_bank.deposit_from_research.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_relevant_knowledge(self, config, mock_knowledge_bank, mock_core_memory):
        """测试获取相关知识"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                result = await manager.get_relevant_knowledge(
                    query="测试查询",
                    max_items=10
                )
                
                assert "entities" in result
                assert "summary" in result
    
    @pytest.mark.asyncio
    async def test_get_summary(self, config, mock_knowledge_bank, mock_core_memory):
        """测试获取概览"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                result = await manager.get_summary()
                
                assert "stats" in result
                assert result["stats"]["total_research"] == 5
    
    def test_search(self, config, mock_knowledge_bank, mock_core_memory):
        """测试搜索"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                result = manager.search("特斯拉")
                
                assert "entities" in result
                assert len(result["entities"]) == 1
    
    def test_search_with_filters(self, config, mock_knowledge_bank, mock_core_memory):
        """测试带过滤条件的搜索"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                result = manager.search(
                    query="特斯拉",
                    filters={"type": "company"},
                    limit=50
                )
                
                assert "entities" in result
    
    def test_import_file(self, config, mock_knowledge_bank, mock_core_memory):
        """测试导入文件"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                result = manager.import_file("test.pdf")
                
                assert result.status == "success"
    
    def test_import_directory(self, config, mock_knowledge_bank, mock_core_memory):
        """测试导入目录"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                results = manager.import_directory("reports/", recursive=True)
                
                assert len(results) == 2
    
    def test_record_learning(self, config, mock_knowledge_bank, mock_core_memory):
        """测试记录学习"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                result = manager.record_learning(
                    category="correction",
                    content="用户纠正内容",
                    priority="high"
                )
                
                assert result["status"] == "recorded"
    
    def test_promote_learnings(self, config, mock_knowledge_bank, mock_core_memory):
        """测试晋升学习记录"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                result = manager.promote_learnings()
                
                assert len(result) == 1
    
    def test_compile(self, config, mock_knowledge_bank, mock_core_memory):
        """测试编译"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                result = manager.compile("测试内容")
                
                assert result.get_stats()["pages"] == 5
    
    def test_detect_contradictions(self, config, mock_knowledge_bank, mock_core_memory):
        """测试矛盾检测"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                result = manager.detect_contradictions()
                
                assert len(result) == 1
    
    @pytest.mark.asyncio
    async def test_run_dream_mode(self, config, mock_knowledge_bank, mock_core_memory):
        """测试做梦模式"""
        mock_dream_report = {
            "status": "completed",
            "duration_ms": 1500,
            "phases": ["compression", "extraction", "promotion"]
        }
        
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                # Mock the dynamic import inside run_dream_mode
                with patch('src.core.memory.dream.DreamMode') as MockDreamMode:
                    mock_dream_instance = Mock()
                    mock_dream_instance.run = Mock(return_value=mock_dream_report)
                    MockDreamMode.return_value = mock_dream_instance
                    
                    manager = KnowledgeManager(user_id="test_user", config=config)
                    
                    result = await manager.run_dream_mode(trigger="manual")
                    
                    assert result["status"] == "completed"
    
    def test_export(self, config, mock_knowledge_bank, mock_core_memory):
        """测试导出"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                result = manager.export()
                
                assert "entities" in result
    
    def test_knowledge_bank_property(self, config, mock_knowledge_bank, mock_core_memory):
        """测试 knowledge_bank 属性"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                assert manager.knowledge_bank == mock_knowledge_bank
    
    def test_core_memory_property(self, config, mock_knowledge_bank, mock_core_memory):
        """测试 core_memory 属性"""
        with patch('src.core.memory.knowledge_manager.UserKnowledgeBank', return_value=mock_knowledge_bank):
            with patch('src.core.memory.knowledge_manager.CoreMemory', return_value=mock_core_memory):
                manager = KnowledgeManager(user_id="test_user", config=config)
                
                assert manager.core_memory == mock_core_memory