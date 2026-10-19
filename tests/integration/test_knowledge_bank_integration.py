# -*- coding: utf-8 -*-
"""
知识银行集成测试

测试完整的知识银行功能
"""

import pytest
from pathlib import Path
import asyncio


class TestKnowledgeBankEndToEnd:
    """端到端测试"""
    
    @pytest.mark.asyncio
    async def test_full_research_cycle(self, tmp_path):
        """完整研究周期测试"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        from src.core.memory.auto_extraction import KnowledgeExtractor
        from src.core.memory.research_enhancer import ResearchEnhancer
        
        # 1. 初始化知识银行
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # 验证初始化
        assert bank.user_id == "user_001"
        
        # 2. 第一次研究：没有历史知识
        enhancer = ResearchEnhancer(knowledge_bank=bank)
        
        request1 = {
            "topic": "动力电池行业",
            "requirements": ["市场规模", "主要企业"]
        }
        
        enriched1 = await enhancer.enrich_request(request1)
        
        # 应该没有相关知识
        assert "relevant_knowledge" in enriched1
        
        # 3. 存储研究结果
        result1 = {
            "research_id": "research_001",
            "topic": "动力电池行业分析",
            "entities": [
                {"name": "宁德时代", "type": "company", "description": "电池制造商"},
                {"name": "比亚迪", "type": "company", "description": "新能源汽车"}
            ],
            "data_points": [
                {"metric": "市场份额", "value": "37%", "year": "2023"}
            ],
            "relations": [
                {"source": "宁德时代", "target": "比亚迪", "type": "competitor"}
            ]
        }
        
        stored = await enhancer.store_results(result1)
        
        # 验证存储成功
        assert stored["entities_added"] >= 2
        assert stored["relations_added"] >= 1
        
        # 4. 第二次研究：应该有历史知识
        request2 = {
            "topic": "电池行业竞争分析",
            "requirements": ["竞争格局"]
        }
        
        enriched2 = await enhancer.enrich_request(request2)
        
        # 应该找到之前存储的实体
        assert "relevant_knowledge" in enriched2
        
        # 5. 验证知识银行统计
        stats = bank.get_knowledge_stats()
        
        assert stats["entity_count"] >= 2
        assert stats["relation_count"] >= 1
        
        bank.close()
    
    @pytest.mark.asyncio
    async def test_knowledge_extraction_and_storage(self, tmp_path):
        """知识提取和存储测试"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        from src.core.memory.auto_extraction import KnowledgeExtractor
        
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        extractor = KnowledgeExtractor(knowledge_bank=bank)
        
        # 模拟研究结果
        research_content = """
        宁德时代是全球最大的动力电池制造商，市场份额达37%。
        2023年营收超过4000亿元，主要客户包括特斯拉、宝马等车企。
        宁德时代与比亚迪在动力电池市场形成双寡头竞争格局。
        """
        
        # 提取知识
        extracted = await extractor.extract_from_research({
            "content": research_content
        })
        
        # 验证提取结果
        assert len(extracted["entities"]) >= 1 or len(extracted["data_points"]) >= 1
        
        # 存储到知识银行
        if extracted["entities"]:
            result = await extractor.deposit_entities(extracted["entities"])
            assert result["added"] >= 1
        
        # 验证知识银行有数据
        stats = bank.get_knowledge_stats()
        assert stats["entity_count"] >= 1 or stats["data_point_count"] >= 1
        
        bank.close()
    
    @pytest.mark.asyncio
    async def test_conversation_with_knowledge_bank(self, tmp_path):
        """对话与知识银行集成测试"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        from src.core.dialogue.conversation_manager import ConversationManager
        
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # 添加一些知识
        bank.entities.add_entity("company", "阿里巴巴", description="电商平台")
        
        # 创建对话管理器
        manager = ConversationManager(user_id="user_001", knowledge_bank=bank)
        
        # 处理消息
        response = await manager.process_message("研究电商行业")
        
        # 验证响应
        assert "state" in response
        assert "message" in response
        
        # 验证上下文保存
        assert manager.state_machine.get_context("user_input") == "研究电商行业"
        
        bank.close()


class TestKnowledgeBankCLI:
    """CLI集成测试"""
    
    def test_knowledge_summary_via_cli(self, tmp_path):
        """通过CLI查看知识摘要"""
        from typer.testing import CliRunner
        from src.cli.main import app
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        
        # 创建知识银行并添加数据
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        bank.entities.add_entity("company", "Test Company")
        
        # 运行CLI命令
        result = runner.invoke(app, [
            "knowledge", "summary",
            "--user-id", "user_001",
            "--db-path", str(db_path)
        ])
        
        # 验证命令成功
        assert result.exit_code == 0
        
        bank.close()
    
    def test_knowledge_export_via_cli(self, tmp_path):
        """通过CLI导出知识"""
        from typer.testing import CliRunner
        from src.cli.main import app
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        
        runner = CliRunner()
        db_path = tmp_path / "test.db"
        export_path = tmp_path / "export.json"
        
        # 创建知识银行并添加数据
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        bank.entities.add_entity("company", "Test Company")
        
        # 运行CLI命令
        result = runner.invoke(app, [
            "knowledge", "export",
            "--user-id", "user_001",
            "--db-path", str(db_path),
            "--output", str(export_path)
        ])
        
        # 验证命令成功
        assert result.exit_code == 0
        assert export_path.exists()
        
        bank.close()


class TestKnowledgeBankPerformance:
    """性能测试"""
    
    def test_large_number_of_entities(self, tmp_path):
        """大量实体测试"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # 添加100个实体
        for i in range(100):
            bank.entities.add_entity("company", f"Company {i}")
        
        # 验证统计
        stats = bank.get_knowledge_stats()
        assert stats["entity_count"] == 100
        
        # 搜索测试
        results = bank.entities.search_entities("Company")
        assert len(results) >= 10
        
        bank.close()
    
    def test_entity_duplicate_handling(self, tmp_path):
        """实体重复处理测试"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # 多次添加同一实体
        e1 = bank.entities.add_entity("company", "Test Company")
        e2 = bank.entities.add_entity("company", "Test Company")
        e3 = bank.entities.add_entity("company", "Test Company")
        
        # 应该返回相同的ID
        assert e1 == e2 == e3
        
        # 提及次数应该是3
        entity = bank.entities.get_entity(e1)
        assert entity["mention_count"] == 3
        
        bank.close()


class TestKnowledgeBankDataIntegrity:
    """数据完整性测试"""
    
    def test_database_persistence(self, tmp_path):
        """数据库持久化测试"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        
        db_path = tmp_path / "test.db"
        
        # 创建并添加数据
        bank1 = UserKnowledgeBank("user_001", db_path=str(db_path))
        e1 = bank1.entities.add_entity("company", "Test Company")
        bank1.close()
        
        # 重新打开验证数据持久化
        bank2 = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        stats = bank2.get_knowledge_stats()
        assert stats["entity_count"] == 1
        
        entity = bank2.entities.get_entity(e1)
        assert entity["name"] == "Test Company"
        
        bank2.close()
    
    def test_cascade_delete(self, tmp_path):
        """级联删除测试"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # 添加实体和关系
        e1 = bank.entities.add_entity("company", "Company A")
        e2 = bank.entities.add_entity("company", "Company B")
        r = bank.relations.add_relation(e1, e2, "competitor")
        
        # 清空实体
        bank.clear_entities()
        
        # 验证实体被清空
        stats = bank.get_knowledge_stats()
        assert stats["entity_count"] == 0
        
        bank.close()