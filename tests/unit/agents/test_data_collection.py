"""数据采集Agent测试."""

import pytest
from datetime import datetime
from typing import Dict, Any


class TestDataCollectionAgent:
    """测试数据采集Agent."""
    
    @pytest.fixture
    def agent(self, tmp_path):
        """创建Agent实例."""
        from src.agents.data_collection import DataCollectionAgent
        return DataCollectionAgent(
            agent_id="test-agent",
            storage_path=str(tmp_path)
        )
    
    def test_agent_initialization(self, agent):
        """测试Agent初始化."""
        assert agent.agent_id == "test-agent"
        assert agent.name == "DataCollectionAgent"
        assert agent.status == "idle"
    
    def test_validate_requirements_valid(self, agent):
        """测试有效需求验证."""
        requirements = {
            "topic": "AI industry",
            "data_types": ["market_size", "companies"],
            "sources": ["government", "industry_reports"],
            "time_range": {"start": "2024-01", "end": "2024-12"}
        }
        
        result = agent.validate_requirements(requirements)
        assert result["valid"] == True
        assert len(result["errors"]) == 0
    
    def test_validate_requirements_invalid(self, agent):
        """测试无效需求验证."""
        requirements = {
            "topic": "",  # 空主题
            "data_types": [],  # 空数据类型
        }
        
        result = agent.validate_requirements(requirements)
        assert result["valid"] == False
        assert len(result["errors"]) > 0
    
    def test_build_search_queries(self, agent):
        """测试构建搜索查询."""
        requirements = {
            "topic": "新能源汽车",
            "data_types": ["market_size", "policy"],
            "time_range": {"start": "2024-01", "end": "2024-12"}
        }
        
        queries = agent.build_search_queries(requirements)
        
        assert len(queries) > 0
        assert all("topic" in q for q in queries)
        assert all("data_type" in q for q in queries)
    
    def test_collect_data_mock(self, agent, monkeypatch):
        """测试数据收集（模拟）."""
        # 模拟数据提供者
        def mock_fetch(query, params=None):
            return {
                "query": query,
                "results": [
                    {"title": "Test", "content": "Test content", "source": "test"}
                ],
                "timestamp": datetime.now().isoformat()
            }
        
        # 注入模拟
        if agent.data_provider:
            monkeypatch.setattr(agent.data_provider, "fetch", mock_fetch)
        
        task = {
            "topic": "test",
            "data_types": ["news"],
            "max_results": 5
        }
        
        result = agent.collect_data(task)
        
        assert result["status"] == "success"
        assert "data" in result
        assert "collected_at" in result
    
    def test_process_raw_data(self, agent):
        """测试原始数据处理."""
        raw_data = [
            {"title": "  Test Title  ", "content": "Content", "source": "gov.cn"},
            {"title": "", "content": "No title", "source": "unknown"},
        ]
        
        processed = agent.process_raw_data(raw_data)
        
        assert len(processed) == 2
        assert processed[0]["title"] == "Test Title"  # 清理过
        assert processed[0]["source_tier"] == "tier1"  # 政府网站
    
    def test_validate_data_quality(self, agent):
        """测试数据质量验证."""
        data = [
            {"title": "Good", "content": "Content" * 50, "source": "gov.cn"},
            {"title": "Bad", "content": "Short", "source": "unknown"},
        ]
        
        result = agent.validate_data_quality(data)
        
        assert result["passed"] == True
        assert result["total"] == 2
        assert result["valid_count"] >= 1
        assert "issues" in result
    
    def test_full_workflow(self, agent, monkeypatch):
        """测试完整工作流."""
        # 模拟所有外部依赖
        def mock_fetch(query, params=None):
            return {
                "results": [
                    {"title": "Test", "content": "Content" * 100, "source": "gov.cn"}
                ]
            }
        
        if agent.data_provider:
            monkeypatch.setattr(agent.data_provider, "fetch", mock_fetch)
        
        # 执行任务
        task = {
            "topic": "AI industry",
            "data_types": ["market_size", "companies"],
            "sources": ["government"],
            "time_range": {"start": "2024-01", "end": "2024-12"},
            "max_results": 10
        }
        
        # 执行完整流程
        validation = agent.validate_requirements(task)
        assert validation["valid"] == True
        
        collection = agent.collect_data(task)
        assert collection["status"] == "success"
        
        print(f"Full workflow test passed!")


class TestDataSourceRegistry:
    """测试数据源注册表."""
    
    def test_register_source(self):
        """测试注册数据源."""
        from src.agents.data_collection import DataSourceRegistry
        
        registry = DataSourceRegistry()
        
        registry.register(
            name="test_source",
            source_type="api",
            config={"url": "https://api.example.com"},
            priority=1
        )
        
        source = registry.get("test_source")
        assert source["name"] == "test_source"
        assert source["source_type"] == "api"
    
    def test_get_sources_by_type(self):
        """测试按类型获取数据源."""
        from src.agents.data_collection import DataSourceRegistry
        
        registry = DataSourceRegistry()
        registry.register("api1", "api", {}, 1)
        registry.register("api2", "api", {}, 2)
        registry.register("db1", "database", {}, 3)
        
        api_sources = registry.get_by_type("api")
        assert len(api_sources) == 2
    
    def test_source_priority(self):
        """测试数据源优先级."""
        from src.agents.data_collection import DataSourceRegistry
        
        registry = DataSourceRegistry()
        registry.register("low", "api", {}, 3)
        registry.register("high", "api", {}, 1)
        registry.register("mid", "api", {}, 2)
        
        sources = registry.get_all_sorted()
        assert sources[0]["name"] == "high"
        assert sources[1]["name"] == "mid"
        assert sources[2]["name"] == "low"
