"""
IMP-1: DATA_COLLECTION 阶段实际调用 news_search
IMP-2: stock_data 失败时降级到搜索补充

原子变更：IMP-1 + IMP-2 必须同时上线。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestIMP2StructuredFallbackQueries:
    """IMP-2: _generate_structured_fallback_queries 生成针对性降级查询词"""

    @pytest.fixture
    def agent(self):
        from src.core.agents.generic_agent import GenericAgent
        agent = GenericAgent.__new__(GenericAgent)
        agent.agent_id = "imp2_unit"
        return agent

    def test_financial_aspect_generates_fallback(self, agent):
        queries = agent._generate_structured_fallback_queries(
            topic="比亚迪财务分析", aspect="Financial Analysis"
        )
        assert len(queries) >= 2
        assert any("财务" in q or "financial" in q.lower() for q in queries)
        assert any("比亚迪" in q for q in queries)

    def test_valuation_aspect_generates_fallback(self, agent):
        queries = agent._generate_structured_fallback_queries(
            topic="比亚迪估值分析", aspect="Valuation Analysis"
        )
        assert len(queries) >= 2
        assert any("估值" in q or "valuation" in q.lower() for q in queries)

    def test_risk_aspect_generates_fallback(self, agent):
        queries = agent._generate_structured_fallback_queries(
            topic="新能源汽车行业", aspect="Risk Analysis"
        )
        assert len(queries) >= 2
        assert any("风险" in q or "risk" in q.lower() for q in queries)

    def test_general_aspect_has_minimum_queries(self, agent):
        queries = agent._generate_structured_fallback_queries(
            topic="新能源汽车政策", aspect="Policy Environment"
        )
        assert len(queries) >= 2

    def test_queries_include_current_year(self, agent):
        from datetime import date
        year = str(date.today().year)
        queries = agent._generate_structured_fallback_queries(
            topic="比亚迪", aspect="Financial Analysis"
        )
        assert any(year in q for q in queries)

    def test_no_duplicate_year_suffix(self, agent):
        from datetime import date
        year = str(date.today().year)
        queries = agent._generate_structured_fallback_queries(
            topic="比亚迪", aspect="Financial Analysis"
        )
        for q in queries:
            assert q.count(year) <= 1, f"Year {year} appears more than once in: {q}"

    def test_no_double_space_when_aspect_empty(self, agent):
        queries = agent._generate_structured_fallback_queries(topic="比亚迪", aspect="")
        for q in queries:
            assert "  " not in q, f"Double space in query: {q}"

    def test_no_duplicate_queries(self, agent):
        queries = agent._generate_structured_fallback_queries(
            topic="比亚迪财务分析", aspect="Financial Analysis"
        )
        assert len(queries) == len(set(queries))

    def test_chinese_financial_keywords_match(self, agent):
        queries = agent._generate_structured_fallback_queries(
            topic="比亚迪", aspect="财务分析"
        )
        assert any("财务" in q for q in queries)

    def test_chinese_valuation_keywords_match(self, agent):
        queries = agent._generate_structured_fallback_queries(
            topic="比亚迪", aspect="估值分析"
        )
        assert any("估值" in q for q in queries)


class TestIMP1NewsSearchInCollectionCode:
    """IMP-1: 验证 DATA_COLLECTION 代码中 news_search 调用逻辑"""

    def test_news_search_code_exists_in_research_branch(self):
        """验证 generic_agent.py research 分支有 news_search 调用"""
        from pathlib import Path
        agent_path = Path(__file__).resolve().parent.parent.parent / "src" / "core" / "agents" / "generic_agent.py"
        content = agent_path.read_text(encoding="utf-8")
        research_start = content.find("Phase 1: DATA_COLLECTION")
        assert research_start > 0
        research_end = content.find("Phase 2: DATA_VALIDATION")
        research_code = content[research_start:research_end]
        assert "news_search" in research_code, "DATA_COLLECTION must reference news_search"
        assert "news_skill" in research_code, "DATA_COLLECTION must use news_skill"

    def test_news_data_points_have_source_type(self):
        """验证 news_search 数据点标记 source_type=news"""
        from pathlib import Path
        agent_path = Path(__file__).resolve().parent.parent.parent / "src" / "core" / "agents" / "generic_agent.py"
        content = agent_path.read_text(encoding="utf-8")
        assert '"source_type": "news"' in content, "news data points must have source_type=news"

    def test_news_search_failure_caught(self):
        """验证 news_search 失败有 try-except"""
        from pathlib import Path
        agent_path = Path(__file__).resolve().parent.parent.parent / "src" / "core" / "agents" / "generic_agent.py"
        content = agent_path.read_text(encoding="utf-8")
        research_start = content.find("Phase 1: DATA_COLLECTION")
        research_end = content.find("Phase 2: DATA_VALIDATION")
        research_code = content[research_start:research_end]
        assert "news_err" in research_code, "news_search failure must be caught"


class TestIMP2FallbackInCollectionCode:
    """IMP-2: 验证 stock_data 降级逻辑"""

    def test_structured_data_fetched_flag_exists(self):
        """验证 _structured_data_fetched 追踪变量存在"""
        from pathlib import Path
        agent_path = Path(__file__).resolve().parent.parent.parent / "src" / "core" / "agents" / "generic_agent.py"
        content = agent_path.read_text(encoding="utf-8")
        research_start = content.find("Phase 1: DATA_COLLECTION")
        research_end = content.find("Phase 2: DATA_VALIDATION")
        research_code = content[research_start:research_end]
        assert "_structured_data_fetched" in research_code

    def test_fallback_queries_injected_when_structured_unavailable(self):
        """验证 stock_data 不可用时注入降级查询词"""
        from pathlib import Path
        agent_path = Path(__file__).resolve().parent.parent.parent / "src" / "core" / "agents" / "generic_agent.py"
        content = agent_path.read_text(encoding="utf-8")
        assert "_generate_structured_fallback_queries" in content
        assert "not _structured_data_fetched" in content

    def test_generate_structured_fallback_queries_method_exists(self):
        """验证 _generate_structured_fallback_queries 方法存在"""
        from src.core.agents.generic_agent import GenericAgent
        assert hasattr(GenericAgent, '_generate_structured_fallback_queries')
        assert callable(getattr(GenericAgent, '_generate_structured_fallback_queries'))
