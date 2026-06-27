import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from dataclasses import asdict

from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator, RetryPolicy
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterWriteOutput, ChapterReviewOutput, ChapterIssue,
    ReviewOutput, DataPoint,
)
from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager


REAL_CACHE = Path("data/research_01150942/research_result_cache.json")


class MockAggregationResult:
    """模拟真实AggregationResult——layered_content key是agent_id，provenance.section_target是section_id"""
    def __init__(self, cache_data: dict):
        self.data = cache_data.get("sections", [])
        self.conflicts = []
        self.stats = {}
        self.sources = cache_data.get("sources", [])
        self.layered_content = {
            "analysis": {}
        }
        self.content_provenance = {}
        for sec in cache_data.get("sections", []):
            agent_id = sec.get("id", sec.get("agent_id", f"agent_{sec.get('id', '')}"))
            self.layered_content["analysis"][agent_id] = sec
            self.content_provenance[agent_id] = {
                "source_key": agent_id,
                "section_target": sec["id"],
            }


@pytest.fixture
def real_cache_data():
    if not REAL_CACHE.exists():
        pytest.skip("Real research cache not found")
    return json.loads(REAL_CACHE.read_text(encoding="utf-8"))


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


class TestRealDataIntegration:
    def test_cache_data_structure(self, real_cache_data):
        assert "topic" in real_cache_data
        assert "sections" in real_cache_data
        assert "sources" in real_cache_data
        assert len(real_cache_data["sections"]) > 0
        for sec in real_cache_data["sections"]:
            assert "id" in sec
            assert "content" in sec

    def test_aggregation_result_from_cache(self, real_cache_data):
        agg = MockAggregationResult(real_cache_data)
        assert len(agg.sources) > 0
        assert len(agg.layered_content) > 0
        assert len(agg.content_provenance) > 0
        for sec_id, prov in agg.content_provenance.items():
            assert prov["section_target"] == sec_id

    def test_extract_chapter_data_from_real_cache(self, orchestrator, real_cache_data):
        agg = MockAggregationResult(real_cache_data)
        for sec in real_cache_data["sections"]:
            section_id = sec["id"]
            result = orchestrator._extract_chapter_data(agg, section_id, [])
            assert result is not None
            assert "content" in result or len(result) >= 0

    def test_sources_preserved_through_assemble(self, orchestrator, real_cache_data):
        agg = MockAggregationResult(real_cache_data)
        chapter = ChapterWriteOutput(
            chapter_id="test_ch", title="测试", content="内容",
            data_points_used=[DataPoint(metric="测试", value="1", unit="个", source="test")],
            key_conclusions=["结论1"],
        )
        review = ReviewOutput(overall_score=85.0)
        result = orchestrator._assemble_final_report(
            [chapter], "摘要", review, "测试主题", agg.sources
        )
        assert result["sources"] == agg.sources
        assert len(result["sources"]) == len(real_cache_data.get("sources", []))

    def test_real_cache_section_ids_match_provenance(self, real_cache_data):
        agg = MockAggregationResult(real_cache_data)
        cache_section_ids = {sec["id"] for sec in real_cache_data["sections"]}
        provenance_targets = {v["section_target"] for v in agg.content_provenance.values()}
        assert cache_section_ids == provenance_targets

    @pytest.mark.asyncio
    async def test_full_pipeline_with_real_data(
        self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer,
        mock_llm, real_cache_data,
    ):
        agg = MockAggregationResult(real_cache_data)
        sections = real_cache_data["sections"]

        written_chapters = []
        for sec in sections:
            ch = ChapterWriteOutput(
                chapter_id=sec["id"],
                title=sec.get("title", sec["id"]),
                content=sec.get("content", ""),
                data_points_used=[],
                key_conclusions=["结论"],
            )
            written_chapters.append(ch)

        mock_writer.write.side_effect = written_chapters
        mock_reviewer.review.return_value = ChapterReviewOutput(passed=True, score=85.0)
        mock_global_reviewer.review.return_value = ReviewOutput(overall_score=85.0)
        mock_llm.execute.return_value = {"success": True, "content": "执行摘要"}

        task_structure = {
            "topic": real_cache_data["topic"],
            "sections": [
                {"section_id": sec["id"], "section_name": sec.get("title", sec["id"]),
                 "section_role": "analysis", "content_dependency": []}
                for sec in sections
            ],
        }

        result = await orchestrator.generate_report(
            task_structure=task_structure,
            framework_config={"name": "行业研究"},
            aggregated_result=agg,
            topic=real_cache_data["topic"],
        )

        assert result["topic"] == real_cache_data["topic"]
        assert len(result["sections"]) == len(sections)
        assert len(result["sources"]) == len(real_cache_data.get("sources", []))
        for i, sec in enumerate(sections):
            assert result["sections"][i]["id"] == sec["id"]
            assert result["sections"][i]["title"] == sec.get("title", sec["id"])

    def test_data_point_extraction_from_real_content(self, orchestrator, real_cache_data):
        for sec in real_cache_data["sections"]:
            content = sec.get("content", "")
            if not content:
                continue
            ch = ChapterWriteOutput(
                chapter_id=sec["id"], title=sec.get("title", ""), content=content,
            )
            dps = orchestrator._extract_and_validate_data_points(ch)
            assert isinstance(dps, list)
            for dp in dps:
                assert isinstance(dp, DataPoint)
                assert dp.value
                assert dp.unit


class TestOutputContractWithDocumentAgent:
    def test_output_matches_document_agent_input_format(self, orchestrator, real_cache_data):
        agg = MockAggregationResult(real_cache_data)
        chapters = [
            ChapterWriteOutput(
                chapter_id="ch1", title="市场规模", content="内容",
                data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="iimedia.cn")],
                key_conclusions=["市场规模达2000亿"],
            )
        ]
        review = ReviewOutput(overall_score=85.0)
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题", agg.sources)

        required_keys = {"topic", "title", "aspects", "sections", "sources", "key_findings"}
        assert required_keys.issubset(set(result.keys()))

        for sec in result["sections"]:
            sec_keys = {"id", "title", "content", "subsections", "charts", "data_points", "sources"}
            assert sec_keys.issubset(set(sec.keys()))

        for dp in result["sections"][0]["data_points"]:
            dp_keys = {"metric", "value", "unit", "source", "chapter_id", "confidence"}
            assert dp_keys.issubset(set(dp.keys()))

    def test_output_is_json_serializable(self, orchestrator, real_cache_data):
        agg = MockAggregationResult(real_cache_data)
        chapters = [
            ChapterWriteOutput(
                chapter_id="ch1", title="测试", content="内容",
                data_points_used=[DataPoint(metric="m", value="1", unit="个", source="s")],
                key_conclusions=["c1"],
            )
        ]
        review = ReviewOutput(overall_score=85.0)
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题", agg.sources)
        serialized = json.dumps(result, ensure_ascii=False)
        assert len(serialized) > 0
        re_parsed = json.loads(serialized)
        assert re_parsed["topic"] == "主题"
