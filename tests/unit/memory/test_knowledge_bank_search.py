"""测试知识银行检索功能"""

import pytest
from pathlib import Path
from src.core.memory.knowledge_bank import UserKnowledgeBank


class TestKnowledgeBankSearch:
    """测试综合搜索"""
    
    @pytest.fixture
    def bank_with_data(self, tmp_path):
        """创建带数据的知识银行"""
        db_path = tmp_path / "test_knowledge.db"
        bank = UserKnowledgeBank("user_001", db_path=str(db_path))
        
        # 添加实体
        bank.entities.add_entity("company", "阿里巴巴", description="中国电商平台")
        bank.entities.add_entity("company", "腾讯", aliases=["腾讯控股"])
        
        # 添加关系
        bank.relations.add_relation("entity_001", "entity_002", "competitor", context="市场竞争")
        
        # 添加数据点
        bank.data_points.add_data_point("entity_001", "营收", "5000亿", unit="人民币")
        
        yield bank
        bank.close()
    
    def test_search_all_entities(self, bank_with_data):
        """测试搜索实体"""
        results = bank_with_data.search_all("阿里")
        
        assert "entities" in results
        assert len(results["entities"]) >= 1
        
        # 应包含阿里巴巴
        names = [e["name"] for e in results["entities"]]
        assert "阿里巴巴" in names
    
    def test_search_all_relations(self, bank_with_data):
        """测试搜索关系"""
        results = bank_with_data.search_all("竞争")
        
        assert "relations" in results
        assert len(results["relations"]) >= 1
        
        # 应包含竞争关系
        contexts = [r["context"] for r in results["relations"]]
        assert any("竞争" in c for c in contexts)
    
    def test_search_all_data_points(self, bank_with_data):
        """测试搜索数据点"""
        results = bank_with_data.search_all("5000")
        
        assert "data_points" in results
        assert len(results["data_points"]) >= 1
        
        # 应包含5000亿的数据点
        values = [d["metric_value"] for d in results["data_points"]]
        assert any("5000" in v for v in values)
    
    def test_search_all_empty_query(self, bank_with_data):
        """测试空查询返回所有知识"""
        results = bank_with_data.search_all("")
        
        assert "entities" in results
        assert "relations" in results
        assert "data_points" in results
        
        # 应返回所有数据
        assert len(results["entities"]) >= 2
        assert len(results["relations"]) >= 1
        assert len(results["data_points"]) >= 1
    
    def test_search_all_with_limit(self, bank_with_data):
        """测试限制结果数量"""
        results = bank_with_data.search_all("", limit=1)
        
        # 每类最多1个结果
        assert len(results["entities"]) <= 1
        assert len(results["relations"]) <= 1
        assert len(results["data_points"]) <= 1


class TestKnowledgeBankStats:
    """测试知识统计"""
    
    @pytest.fixture
    def bank_with_data(self, tmp_path):
        """创建带数据的知识银行"""
        db_path = tmp_path / "test_knowledge.db"
        bank = UserKnowledgeBank("user_002", db_path=str(db_path))
        
        # 添加实体
        bank.entities.add_entity("company", "阿里巴巴")
        bank.entities.add_entity("company", "腾讯")
        bank.entities.add_entity("industry", "电商")
        
        # 添加关系
        bank.relations.add_relation("entity_001", "entity_002", "competitor")
        bank.relations.add_relation("entity_001", "entity_003", "belongs_to")
        
        # 添加数据点
        bank.data_points.add_data_point("entity_001", "营收", "5000亿")
        bank.data_points.add_data_point("entity_002", "营收", "3000亿")
        
        yield bank
        bank.close()
    
    def test_get_knowledge_stats(self, bank_with_data):
        """测试获取知识统计"""
        stats = bank_with_data.get_knowledge_stats()
        
        assert "entity_count" in stats
        assert "relation_count" in stats
        assert "data_point_count" in stats
        
        assert stats["entity_count"] == 3
        assert stats["relation_count"] == 2
        assert stats["data_point_count"] == 2
    
    def test_get_entities_summary(self, bank_with_data):
        """测试获取实体概览"""
        summary = bank_with_data.get_entities_summary()
        
        assert "by_type" in summary
        assert "total" in summary
        
        # 按类型统计
        assert "company" in summary["by_type"]
        assert "industry" in summary["by_type"]
        
        assert summary["by_type"]["company"] == 2
        assert summary["by_type"]["industry"] == 1
        assert summary["total"] == 3
    
    def test_get_top_entities(self, bank_with_data):
        """测试获取高频实体"""
        # 多次提及阿里巴巴
        bank_with_data.entities.add_entity("company", "阿里巴巴")  # 第2次
        bank_with_data.entities.add_entity("company", "阿里巴巴")  # 第3次
        
        top_entities = bank_with_data.get_top_entities(limit=5)
        
        assert len(top_entities) <= 5
        
        # 阿里巴巴应该是高频实体
        top_names = [e["name"] for e in top_entities]
        assert "阿里巴巴" in top_names


class TestKnowledgeBankExport:
    """测试知识导出"""
    
    @pytest.fixture
    def bank_with_data(self, tmp_path):
        """创建带数据的知识银行"""
        db_path = tmp_path / "test_knowledge.db"
        bank = UserKnowledgeBank("user_003", db_path=str(db_path))
        
        # 添加实体
        bank.entities.add_entity("company", "阿里巴巴", description="中国电商平台")
        bank.entities.add_entity("company", "腾讯")
        
        # 添加关系
        bank.relations.add_relation("entity_001", "entity_002", "competitor", context="市场竞争")
        
        # 添加数据点
        bank.data_points.add_data_point("entity_001", "营收", "5000亿", unit="人民币")
        
        yield bank
        bank.close()
    
    def test_export_to_dict(self, bank_with_data):
        """测试导出为字典"""
        data = bank_with_data.export_to_dict()
        
        assert "user_id" in data
        assert "entities" in data
        assert "relations" in data
        assert "data_points" in data
        
        assert data["user_id"] == "user_003"
        assert len(data["entities"]) >= 2
        assert len(data["relations"]) >= 1
        assert len(data["data_points"]) >= 1
    
    def test_export_to_json_file(self, bank_with_data, tmp_path):
        """测试导出为JSON文件"""
        export_path = tmp_path / "export.json"
        
        bank_with_data.export_to_json(str(export_path))
        
        # 验证文件存在
        assert export_path.exists()
        
        # 验证内容
        import json
        with open(export_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert "user_id" in data
        assert "entities" in data
    
    def test_export_entities_only(self, bank_with_data, tmp_path):
        """测试仅导出实体"""
        export_path = tmp_path / "entities.json"
        
        bank_with_data.export_entities(str(export_path))
        
        # 验证文件存在
        assert export_path.exists()
        
        # 验证内容
        import json
        with open(export_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 仅包含实体
        assert "entities" in data
        assert "relations" not in data


class TestKnowledgeBankClear:
    """测试清空知识"""
    
    @pytest.fixture
    def bank_with_data(self, tmp_path):
        """创建带数据的知识银行"""
        db_path = tmp_path / "test_knowledge.db"
        bank = UserKnowledgeBank("user_004", db_path=str(db_path))
        
        # 添加数据
        bank.entities.add_entity("company", "阿里巴巴")
        bank.relations.add_relation("entity_001", "entity_002", "competitor")
        bank.data_points.add_data_point("entity_001", "营收", "5000亿")
        
        yield bank
        bank.close()
    
    def test_clear_all(self, bank_with_data):
        """测试清空所有知识"""
        # 先确认有数据
        stats_before = bank_with_data.get_knowledge_stats()
        assert stats_before["entity_count"] > 0
        
        # 清空
        bank_with_data.clear_all()
        
        # 验证清空
        stats_after = bank_with_data.get_knowledge_stats()
        assert stats_after["entity_count"] == 0
        assert stats_after["relation_count"] == 0
        assert stats_after["data_point_count"] == 0
    
    def test_clear_entities_only(self, bank_with_data):
        """测试仅清空实体"""
        bank_with_data.clear_entities()
        
        stats = bank_with_data.get_knowledge_stats()
        assert stats["entity_count"] == 0
        
        # 关系和数据点应保留（因为它们依赖实体ID，可能被级联删除）
        # 这里我们只检查实体被清空
    
    def test_clear_data_points_only(self, bank_with_data):
        """测试仅清空数据点"""
        bank_with_data.clear_data_points()
        
        stats = bank_with_data.get_knowledge_stats()
        assert stats["data_point_count"] == 0
        
        # 实体和关系应保留
        assert stats["entity_count"] > 0