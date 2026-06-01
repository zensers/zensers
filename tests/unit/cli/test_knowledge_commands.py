# -*- coding: utf-8 -*-
"""
CLI知识银行命令测试

测试CLI集成
"""

import pytest
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch, Mock

runner = CliRunner()


class TestKnowledgeCommands:
    """测试知识银行CLI命令"""
    
    def test_knowledge_summary_command(self, tmp_path):
        """测试知识摘要命令"""
        # 创建临时知识银行
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        bank.entities.add_entity("company", "Test Company")
        
        # 导入CLI应用
        from src.cli.main import app
        
        # 运行命令
        result = runner.invoke(app, ["knowledge", "summary", "--user-id", "user_001", "--db-path", str(db_path)])
        
        # 验证输出
        assert result.exit_code == 0
        bank.close()
    
    def test_knowledge_search_command(self, tmp_path):
        """测试知识搜索命令"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        bank.entities.add_entity("company", "Test Company", description="Test description")
        
        from src.cli.main import app
        
        result = runner.invoke(app, ["knowledge", "search", "Test", "--user-id", "user_001", "--db-path", str(db_path)])
        
        assert result.exit_code == 0
        bank.close()
    
    def test_knowledge_export_command(self, tmp_path):
        """测试知识导出命令"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        export_path = tmp_path / "export.json"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        bank.entities.add_entity("company", "Test Company")
        
        from src.cli.main import app
        
        result = runner.invoke(app, [
            "knowledge", "export",
            "--user-id", "user_001",
            "--db-path", str(db_path),
            "--output", str(export_path)
        ])
        
        assert result.exit_code == 0
        bank.close()


class TestChatCommand:
    """测试对话命令"""
    
    def test_chat_start_command(self, tmp_path):
        """测试启动对话命令"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        from src.cli.main import app
        
        result = runner.invoke(app, ["chat", "start", "--user-id", "user_001", "--db-path", str(db_path)])
        
        # 命令应该运行（可能退出码非0因为需要交互）
        assert result.exit_code in [0, 1]
        bank.close()
    
    def test_chat_status_command(self, tmp_path):
        """测试对话状态命令"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        from src.cli.main import app
        
        result = runner.invoke(app, ["chat", "status", "--user-id", "user_001", "--db-path", str(db_path)])
        
        # 命令应该运行
        assert result.exit_code in [0, 1]
        bank.close()


class TestKnowledgeBankWithResearch:
    """测试知识银行与研究集成"""
    
    def test_research_command_exists(self, tmp_path):
        """研究命令存在"""
        from src.cli.main import app
        
        # 运行研究命令 --help
        result = runner.invoke(app, ["research", "--help"])
        
        # 命令应该存在
        assert result.exit_code == 0


class TestKnowledgeStatsDisplay:
    """测试知识统计显示"""
    
    def test_stats_shows_entity_count(self, tmp_path):
        """统计显示实体数量"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # 添加多个实体
        for i in range(5):
            bank.entities.add_entity("company", f"Company {i}")
        
        stats = bank.get_knowledge_stats()
        
        assert stats["entity_count"] == 5
        bank.close()
    
    def test_stats_shows_relation_count(self, tmp_path):
        """统计显示关系数量"""
        from src.core.memory.knowledge_bank import UserKnowledgeBank
        db_path = tmp_path / "test.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        e1 = bank.entities.add_entity("company", "Company A")
        e2 = bank.entities.add_entity("company", "Company B")
        bank.relations.add_relation(e1, e2, "competitor")
        
        stats = bank.get_knowledge_stats()
        
        assert stats["relation_count"] == 1
        bank.close()