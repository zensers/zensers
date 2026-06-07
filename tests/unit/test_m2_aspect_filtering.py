"""
M2 tests: P1-1 fallback 数据注入按 aspect 过滤。

Scope:
1. _filter_data_by_aspect() 按 aspect 关键词过滤 data_points
2. 同义词扩展（财务 → 营收, 利润, 毛利率 等）
3. 相关性评分排序
4. 空 aspect / 无匹配数据时的降级行为
"""
import pytest


class TestM2FilterDataByAspect:
    """_filter_data_by_aspect 单元测试"""

    def test_basic_aspect_match(self):
        """aspect 关键词正确匹配 data_point"""
        from src.core.orchestrator.execution.engine import ExecutionEngine

        engine = ExecutionEngine.__new__(ExecutionEngine)
        data_points = [
            {"content": "2024年营收5000亿元，同比增长20%", "title": "营收数据"},
            {"content": "公司在新能源领域持续加大投入", "title": "行业趋势"},
        ]
        result = engine._filter_data_by_aspect(data_points, "section_财务")
        assert len(result) == 1
        assert "营收" in result[0]["content"]

    def test_aspect_no_match_returns_limited(self):
        """无匹配时降级到全量限 200"""
        from src.core.orchestrator.execution.engine import ExecutionEngine

        engine = ExecutionEngine.__new__(ExecutionEngine)
        data_points = [
            {"content": "公司在新能源领域持续加大投入", "title": "行业趋势"},
            {"content": "政策环境有利于行业发展", "title": "政策"},
        ]
        result = engine._filter_data_by_aspect(data_points, "section_财务")
        assert len(result) == 2  # 降级返回全量
        assert len(result) <= 200

    def test_synonym_expansion(self):
        """同义词扩展：财务 → 营收/利润/毛利率"""
        from src.core.orchestrator.execution.engine import ExecutionEngine

        engine = ExecutionEngine.__new__(ExecutionEngine)
        data_points = [
            {"content": "毛利率达到25.3%", "title": ""},
            {"content": "公司在新能源领域发展", "title": ""},
        ]
        result = engine._filter_data_by_aspect(data_points, "section_财务")
        assert len(result) == 1
        assert "毛利率" in result[0]["content"]

    def test_销量_synonym(self):
        """同义词扩展：销量 → 出货/交付/市占率"""
        from src.core.orchestrator.execution.engine import ExecutionEngine

        engine = ExecutionEngine.__new__(ExecutionEngine)
        data_points = [
            {"content": "2024年全年出货量302万辆", "title": ""},
            {"content": "公司持续加大研发投入", "title": ""},
        ]
        result = engine._filter_data_by_aspect(data_points, "section_销量")
        assert len(result) == 1
        assert "出货" in result[0]["content"]

    def test_研发_synonym(self):
        """同义词扩展：研发 → R&D/专利/技术创新"""
        from src.core.orchestrator.execution.engine import ExecutionEngine

        engine = ExecutionEngine.__new__(ExecutionEngine)
        data_points = [
            {"content": "2024年R&D投入200亿元", "title": ""},
            {"content": "公司海外收入占比提升至40%", "title": ""},
        ]
        result = engine._filter_data_by_aspect(data_points, "section_研发投入")
        assert len(result) == 1
        assert "R&D" in result[0]["content"]

    def test_empty_aspect_returns_limited(self):
        """aspect 为空时返回前 200 条"""
        from src.core.orchestrator.execution.engine import ExecutionEngine

        engine = ExecutionEngine.__new__(ExecutionEngine)
        data_points = [{"content": f"数据点{i}", "title": ""} for i in range(300)]
        result = engine._filter_data_by_aspect(data_points, "")
        assert len(result) == 200

    def test_scored_by_relevance(self):
        """相关性高的排在前面"""
        from src.core.orchestrator.execution.engine import ExecutionEngine

        engine = ExecutionEngine.__new__(ExecutionEngine)
        data_points = [
            {"content": "行业一般信息", "title": ""},
            {"content": "营收5000亿，利润大幅增长", "title": ""},
            {"content": "利润100亿", "title": ""},
            {"content": "无关内容", "title": ""},
        ]
        result = engine._filter_data_by_aspect(data_points, "section_财务")
        # 结果应优先返回高相关性的
        assert len(result) >= 1
        # 第一个应该是相关度最高的（同时匹配"营收"和"利润"）
        assert "营收" in result[0]["content"] or "利润" in result[0]["content"]

    def test_empty_data_points(self):
        """空 data_points 返回空列表"""
        from src.core.orchestrator.execution.engine import ExecutionEngine

        engine = ExecutionEngine.__new__(ExecutionEngine)
        result = engine._filter_data_by_aspect([], "section_财务")
        assert result == []
