"""
端到端验证测试：用更真实的AggregationResult结构验证数据流对接。

关键发现：
1. layered_content 的 key 是 agent_id（如 "phase_2_agent_1"），不是 section_id
2. content_provenance 的 key 也是 agent_id，ContentProvenance.section_target 才是 section_id
3. research_result_cache.json 是 to_dict() 输出，不含 layered_content/content_provenance
4. 真实运行时 aggregated 对象有这两个属性
"""
import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock
from dataclasses import dataclass, field

from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterWriteOutput, ChapterReviewOutput, ReviewOutput, DataPoint,
)
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager


@dataclass
class RealContentProvenance:
    source_key: str
    stage: str = "analysis"
    agent_type: str = ""
    section_target: str = ""


class RealAggregationResult:
    """模拟真实AggregationResult对象的结构"""
    def __init__(self):
        self.data = {"sections": []}
        self.conflicts = []
        self.stats = {}
        self.sources = [
            {"title": "AI测试行业报告", "url": "https://example.com/report1", "type": "web", "agent_id": "phase_2_agent_1"},
            {"title": "软件测试趋势", "url": "https://example.com/report2", "type": "web", "agent_id": "phase_2_agent_2"},
        ]
        self.layered_content = {
            "analysis": {
                "phase_2_agent_1": {
                    "content": "## 市场规模\n2026年全球软件测试市场规模达到约2000亿元人民币，同比增长15%。",
                    "charts": [],
                    "data_points": [{"metric": "市场规模", "value": "2000", "unit": "亿元"}],
                },
                "phase_2_agent_2": {
                    "content": "## 竞争格局\n头部测试工具厂商集中度持续提升，Top5厂商市场份额超过60%。",
                    "charts": [],
                    "data_points": [{"metric": "Top5份额", "value": "60", "unit": "%"}],
                },
                "phase_2_agent_3": {
                    "content": "## 发展趋势\nAI原生测试、测试左移、技能分化三大趋势并行演进。",
                    "charts": [],
                },
            },
        }
        self.content_provenance = {
            "phase_2_agent_1": RealContentProvenance(
                source_key="phase_2_agent_1",
                stage="analysis",
                agent_type="analysis",
                section_target="section_market_size",
            ),
            "phase_2_agent_2": RealContentProvenance(
                source_key="phase_2_agent_2",
                stage="analysis",
                agent_type="analysis",
                section_target="section_competitive_landscape",
            ),
            "phase_2_agent_3": RealContentProvenance(
                source_key="phase_2_agent_3",
                stage="analysis",
                agent_type="analysis",
                section_target="section_development_trends",
            ),
        }


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def mock_writer():
    return AsyncMock()


@pytest.fixture
def mock_reviewer():
    return AsyncMock()


@pytest.fixture
def mock_global_reviewer():
    return AsyncMock()


@pytest.fixture
def mock_data_repair():
    return AsyncMock()


@pytest.fixture
def mock_conflict_resolver():
    return AsyncMock()


@pytest.fixture
def mock_prompts(tmp_path):
    (tmp_path / "exec_summary.tmpl").write_text("${topic} ${all_conclusions}", encoding="utf-8")
    return PromptManager(prompts_dir=tmp_path)


@pytest.fixture
def orchestrator(mock_llm, mock_writer, mock_reviewer, mock_global_reviewer,
                 mock_data_repair, mock_conflict_resolver, mock_prompts):
    return ReportOrchestrator(
        llm_skill=mock_llm,
        chapter_writer=mock_writer,
        chapter_reviewer=mock_reviewer,
        global_reviewer=mock_global_reviewer,
        data_repair_agent=mock_data_repair,
        conflict_resolver=mock_conflict_resolver,
        prompt_manager=mock_prompts,
    )


class TestRealAggregationResultStructure:
    def test_layered_content_keys_are_agent_ids(self):
        agg = RealAggregationResult()
        for stage_content in agg.layered_content.values():
            for key in stage_content.keys():
                assert "agent" in key or "__meta" in key, f"Expected agent_id key, got: {key}"

    def test_provenance_section_target_differs_from_key(self):
        agg = RealAggregationResult()
        for key, prov in agg.content_provenance.items():
            assert key != prov.section_target, "provenance key (agent_id) != section_target (section_id)"

    def test_provenance_is_dataclass_not_dict(self):
        agg = RealAggregationResult()
        for prov in agg.content_provenance.values():
            assert hasattr(prov, 'section_target'), "ContentProvenance is a dataclass with section_target attribute"


class TestExtractChapterDataWithRealStructure:
    def test_extracts_via_provenance_section_target(self, orchestrator):
        agg = RealAggregationResult()
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "section_market_size", [])
        assert chapter_data is not None
        assert "content" in chapter_data
        assert "市场规模" in chapter_data["content"]

    def test_extracts_competitive_landscape(self, orchestrator):
        agg = RealAggregationResult()
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "section_competitive_landscape", [])
        assert "竞争格局" in chapter_data["content"]

    def test_extracts_development_trends(self, orchestrator):
        agg = RealAggregationResult()
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "section_development_trends", [])
        assert "发展趋势" in chapter_data["content"]

    def test_unknown_section_returns_empty(self, orchestrator):
        agg = RealAggregationResult()
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "nonexistent_section", [])
        assert chapter_data == {}

    def test_provenance_dict_fallback(self, orchestrator):
        agg = RealAggregationResult()
        agg.content_provenance = {
            "phase_2_agent_1": {"section_target": "section_market_size"},
        }
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "section_market_size", [])
        assert "市场规模" in chapter_data["content"]


class TestSourcesPreservedWithRealData:
    def test_sources_from_real_aggregation(self, orchestrator):
        agg = RealAggregationResult()
        chapters = [
            ChapterWriteOutput(
                chapter_id="section_market_size", title="市场规模", content="内容",
                data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="iimedia.cn")],
                key_conclusions=["市场规模达2000亿"],
            ),
        ]
        review = ReviewOutput(overall_score=85.0)
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "软件测试", agg.sources)
        assert len(result["sources"]) == 2
        assert result["sources"][0]["title"] == "AI测试行业报告"


class TestFullPipelineWithRealStructure:
    @pytest.mark.asyncio
    async def test_e2e_with_agent_id_keys(
        self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer, mock_llm,
    ):
        agg = RealAggregationResult()
        task_structure = {
            "topic": "软件测试行业",
            "sections": [
                {"section_id": "section_market_size", "section_name": "市场规模",
                 "section_role": "analysis", "content_dependency": []},
                {"section_id": "section_competitive_landscape", "section_name": "竞争格局",
                 "section_role": "analysis", "content_dependency": []},
                {"section_id": "section_development_trends", "section_name": "发展趋势",
                 "section_role": "analysis", "content_dependency": []},
            ],
        }

        written_chapters = []
        for sec in task_structure["sections"]:
            ch = ChapterWriteOutput(
                chapter_id=sec["section_id"],
                title=sec["section_name"],
                content=f"{sec['section_name']}分析内容",
                data_points_used=[],
                key_conclusions=[f"{sec['section_name']}结论"],
            )
            written_chapters.append(ch)

        mock_writer.write.side_effect = written_chapters
        mock_reviewer.review.return_value = ChapterReviewOutput(passed=True, score=85.0)
        mock_global_reviewer.review.return_value = ReviewOutput(overall_score=85.0)
        mock_llm.execute.return_value = {"success": True, "content": "执行摘要"}

        result = await orchestrator.generate_report(
            task_structure=task_structure,
            framework_config={"name": "行业研究"},
            aggregated_result=agg,
            topic="软件测试行业",
        )

        assert result["topic"] == "软件测试行业"
        assert len(result["sections"]) == 3
        assert len(result["sources"]) == 2
        assert result["sections"][0]["id"] == "section_market_size"
        assert result["sections"][1]["id"] == "section_competitive_landscape"
        assert result["sections"][2]["id"] == "section_development_trends"

        serialized = json.dumps(result, ensure_ascii=False)
        re_parsed = json.loads(serialized)
        assert re_parsed["topic"] == "软件测试行业"


class TestDataPointExtractionFromRealContent:
    def test_extracts_chinese_data_from_real_content(self, orchestrator):
        content = "2026年全球软件测试市场规模达到约2000亿元人民币，同比增长15%。"
        ch = ChapterWriteOutput(chapter_id="ch1", title="市场规模", content=content)
        dps = orchestrator._extract_and_validate_data_points(ch)
        values = [dp.value for dp in dps]
        assert "2000" in values
        assert "15" in values

    def test_extracts_percentage(self, orchestrator):
        content = "头部测试工具厂商集中度持续提升，Top5厂商市场份额超过60%。"
        ch = ChapterWriteOutput(chapter_id="ch1", title="竞争格局", content=content)
        dps = orchestrator._extract_and_validate_data_points(ch)
        assert any(dp.value == "60" and "%" in dp.unit for dp in dps)
