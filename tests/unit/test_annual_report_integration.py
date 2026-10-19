"""Integration tests: 端到端年报分析链路
验证: 1) 动态aspect章节生成 2) supplement_with_api降级 3) 全链路数据流
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.skills.analysis.annual_report_parser import AnnualReportParserSkill


@pytest.fixture
def skill():
    return AnnualReportParserSkill()


class TestEndToEndDynamicAspects:
    def test_framework_aspects_flow_to_decomposition(self, skill):
        sections = [
            {"title": "管理层讨论与分析", "content": "公司营收增长20%", "section_type": "overview", "importance": 1},
            {"title": "财务报表", "content": "营业收入100亿", "section_type": "financial", "importance": 1},
            {"title": "风险因素", "content": "市场竞争加剧", "section_type": "risk", "importance": 2},
        ]
        framework = skill._generate_fallback_framework(sections)
        assert len(framework["aspects"]) > 0
        assert "aspect_to_profile" in framework
        for name in framework["aspects"]:
            assert name in framework["aspect_to_profile"]

    def test_multi_report_cross_year_in_final_output(self, skill):
        reports = [
            {
                "meta": {"file_path": "a.pdf", "year": 2022, "page_count": 10},
                "sections": [{"title": "Financial", "content": "营收100亿", "section_type": "financial", "importance": 1}],
                "financial_tables": {
                    "income": [{"科目": "营业收入", "2022": 100.0}, {"科目": "净利润", "2022": 20.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
                "analysis_framework": {"aspects": ["财务分析"], "aspect_to_profile": {"财务分析": "financial_analyst"}},
            },
            {
                "meta": {"file_path": "b.pdf", "year": 2023, "page_count": 10},
                "sections": [{"title": "Financial", "content": "营收120亿", "section_type": "financial", "importance": 1}],
                "financial_tables": {
                    "income": [{"科目": "营业收入", "2023": 120.0}, {"科目": "净利润", "2023": 25.0}],
                    "balance": [], "cashflow": [], "key_metrics": [],
                },
                "analysis_framework": {},
            },
        ]
        merged = skill._merge_reports(reports)
        assert "cross_year" in merged
        assert "营业收入_yoy_2023" in merged["cross_year"]["cross_year_summary"]
        assert "净利润_yoy_2023" in merged["cross_year"]["cross_year_summary"]
        yoy = merged["cross_year"]["cross_year_summary"]["营业收入_yoy_2023"]
        assert abs(yoy - 20.0) < 0.1

    def test_dynamic_aspects_cover_all_section_types(self, skill):
        sections = [
            {"title": "公司简介", "content": "xyz", "section_type": "overview", "importance": 1},
            {"title": "财务数据", "content": "xyz", "section_type": "financial", "importance": 1},
            {"title": "风险提示", "content": "xyz", "section_type": "risk", "importance": 1},
            {"title": "公司治理", "content": "xyz", "section_type": "governance", "importance": 2},
        ]
        framework = skill._generate_fallback_framework(sections)
        aspect_names = framework["aspects"]
        assert len(aspect_names) >= 3
        assert len(framework["aspect_to_profile"]) == len(aspect_names)


class TestSupplementWithApiDegrade:
    def test_bad_tables_set_supplement_flag(self, skill):
        reports = [
            {
                "meta": {"file_path": "a.pdf"},
                "sections": [],
                "financial_tables": {"income": [], "balance": [], "cashflow": [], "key_metrics": []},
                "analysis_framework": {},
            },
        ]
        merged = skill._merge_reports(reports)
        validation = merged["table_validation"]
        assert len(validation.get("warnings", [])) > 0
        assert any("stock_data" in w for w in validation["warnings"])

    def test_good_tables_no_stock_data_warning(self, skill):
        reports = [
            {
                "meta": {"file_path": "a.pdf"},
                "sections": [],
                "financial_tables": {
                    "income": [{"科目": "营业收入", "2023": "100"}, {"科目": "净利润", "2023": "20"}, {"科目": "营业成本", "2023": "60"}],
                    "balance": [{"科目": "总资产", "2023": "500"}, {"科目": "负债", "2023": "200"}, {"科目": "权益", "2023": "300"}],
                    "cashflow": [{"科目": "经营现金流", "2023": "30"}, {"科目": "投资现金流", "2023": "-10"}, {"科目": "筹资现金流", "2023": "5"}],
                    "key_metrics": [],
                },
                "analysis_framework": {},
            },
        ]
        merged = skill._merge_reports(reports)
        validation = merged["table_validation"]
        stock_warnings = [w for w in validation.get("warnings", []) if "stock_data" in w]
        assert len(stock_warnings) == 0

    def test_orchestrator_sets_supplement_with_api(self):
        from src.core.orchestrator.orchestrator import ResearchOrchestrator
        mock_parse_result = {
            "success": True,
            "message": "ok",
            "data": {
                "sections": [],
                "financial_tables": {"income": [], "balance": [], "cashflow": [], "key_metrics": []},
                "analysis_framework": {"aspects": ["财务分析"], "aspect_to_profile": {"财务分析": "financial_analyst"}},
                "table_validation": {"needs_manual_review": [], "warnings": ["income: 未提取到任何表格数据，将补充stock_data API数据"]},
                "meta": {"file_path": "test.pdf"},
            },
        }
        with patch.object(ResearchOrchestrator, '__init__', lambda self: None):
            orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
            orch._shared_memory = MagicMock()
            orch._shared_memory.write = AsyncMock()
            orch._skills_registry = {"annual_report_parser": MagicMock()}
            orch._skills_registry["annual_report_parser"].execute = AsyncMock(return_value=mock_parse_result)

            requirement = MagicMock()
            requirement.analysis_mode = "annual_report"
            requirement.dynamic_fields = {
                "analysis_mode": "annual_report",
                "file_ids": [{"id": "file1", "path": "test.pdf"}],
            }

            with patch(
                "src.skills.analysis.annual_report_parser.AnnualReportParserSkill"
            ) as parser_cls:
                parser_cls.return_value.execute = AsyncMock(
                    return_value=mock_parse_result
                )
                result = asyncio.run(
                    orch._preparse_annual_report(requirement, "annual-report-test")
                )
            assert result is True
            assert requirement.dynamic_fields.get("supplement_with_api") is True


class TestFullPipelineDataFlow:
    def test_parser_output_matches_shared_memory_schema(self, skill):
        report = {
            "meta": {"file_path": "a.pdf", "year": 2023, "page_count": 10, "has_bookmarks": True},
            "sections": [{"title": "MD&A", "content": "营收增长", "section_type": "overview", "importance": 1}],
            "financial_tables": {
                "income": [{"科目": "营业收入", "2023": 100.0}],
                "balance": [], "cashflow": [], "key_metrics": [],
            },
            "analysis_framework": {
                "aspects": ["财务分析"],
                "aspect_to_profile": {"财务分析": "financial_analyst"},
            },
        }
        merged = skill._merge_reports([report])
        assert "sections" in merged
        assert "financial_tables" in merged
        assert "analysis_framework" in merged
        assert "table_validation" in merged
        assert "meta" in merged
        assert merged["analysis_framework"]["aspect_to_profile"]["财务分析"] == "financial_analyst"

    def test_token_truncation_preserves_key_data(self):
        from src.core.agents.generic_agent import GenericAgent
        spec = type("Spec", (), {
            "name": "test_agent", "role": "analyst", "skills": [],
            "context": {}, "max_retries": 1, "timeout": 30,
        })()
        agent = GenericAgent(spec)
        doc_context = "公司简介\n\n" + "详细描述" * 500 + "\n\n"
        doc_context += "| 指标 | 2023 |\n|------|------|\n| 营业收入 | 100 |\n| 净利润 | 20 |\n"
        result = agent._truncate_by_tokens(doc_context, max_tokens=200, preserve_tables=True)
        assert "营业收入" in result
        assert "净利润" in result
