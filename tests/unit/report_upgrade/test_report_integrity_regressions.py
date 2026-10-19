"""Regression tests for the report evidence/data-bus integrity contract.

These tests intentionally describe the required behavior before the fixes are
implemented.  Keep them deterministic: no network and no LLM calls.
"""

import pytest

from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, DataPoint, ReviewOutput
from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator
from src.core.agents.generic_agent import GenericAgent
from src.services.chart_generator import ChartConfig, ChartGenerator, ChartType
from src.services.chart_planner import ChartPlan
from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent
from src.core.orchestrator.orchestrator import ResearchOrchestrator


def test_unbound_numbers_are_not_promoted_to_data_points():
    chapter = ChapterWriteOutput(
        chapter_id="ch1",
        title="市场规模",
        content="预计到2030年市场规模达到9560亿美元。",
        data_points_used=[],
    )

    data_points = ReportOrchestrator._extract_and_validate_data_points(chapter)

    assert data_points == [], (
        "正文数字没有结构化证据时只能产生校验问题，不能生成 source 为空的 DataPoint"
    )


def test_grounding_attaches_provenance_from_source_catalog():
    sources = [{
        "source_id": "src_1",
        "title": "官方统计",
        "url": "https://example.test/statistics",
        "evidence_id": "ev_1",
        "provenance_id": "prov_1",
        "evidence_excerpt": "官方统计显示销量为100万辆。",
    }]
    points = [{
        "metric": "销量",
        "value": "100",
        "unit": "万辆",
        "source_id": "src_1",
        "evidence_id": "ev_1",
    }]

    result = ReportOrchestrator._ground_data_point_sources(points, sources, chapter_id="ch1")

    assert result[0]["source_url"] == "https://example.test/statistics"
    assert result[0]["provenance_id"] == "prov_1"
    assert result[0]["evidence_id"] == "ev_1"
    assert result[0]["evidence_status"] == "verified"


def test_source_url_without_evidence_excerpt_is_not_verified():
    sources = [{
        "source_id": "src_1",
        "title": "官方统计",
        "url": "https://example.test/statistics",
        "evidence_id": "ev_1",
        "provenance_id": "prov_1",
        # No excerpt/content/locator: this is only a discovered source.
    }]
    points = [{
        "metric": "销量", "value": "100", "unit": "万辆",
        "source_id": "src_1", "evidence_id": "ev_1",
    }]

    result = ReportOrchestrator._ground_data_point_sources(points, sources, chapter_id="ch1")

    assert result[0]["evidence_status"] == "unverified"


def test_future_forecast_year_is_preserved():
    content = "预计2030年市场规模达到9560亿美元，规划期延续至2035年。"

    validated = GenericAgent._validate_output_dates(content, "test-agent")

    assert "2030年" in validated
    assert "2035年" in validated
    assert "2026年" not in validated


def test_line_chart_uses_years_and_scenarios_contract():
    generator = ChartGenerator()
    config = ChartConfig(
        chart_type=ChartType.LINE,
        title="市场规模趋势",
        data={
            "years": ["2022", "2023", "2024"],
            "scenarios": {"市场规模": [100, 120, 150]},
        },
    )

    result = generator.generate(config)

    assert result.success is True, result.error


def test_document_agent_downgrades_sparse_year_datapoints_to_bar_chart(tmp_path, monkeypatch):
    captured = []

    class FakeChartGenerator:
        def __init__(self, **kwargs):
            pass

        def generate(self, config):
            captured.append(config)
            return type("Result", (), {"success": True, "image_path": "chart.png"})()

    monkeypatch.setattr("src.services.chart_generator.ChartGenerator", FakeChartGenerator)
    agent = DocumentGenerationAgent("test-doc", storage_path=str(tmp_path))
    report = {
        "sections": [{
            "id": "s1",
            "title": "市场规模",
            "data_points": [
                {"metric": "市场规模2022年", "value": "100", "unit": "亿美元"},
                {"metric": "市场规模2023年", "value": "120", "unit": "亿美元"},
                {"metric": "市场规模2024年", "value": "150", "unit": "亿美元"},
            ],
        }]
    }

    agent._html_charts_from_datapoints(report)

    assert captured
    assert captured[0].chart_type is ChartType.BAR
    assert captured[0].data == {
        "categories": ["市场规模2022年", "市场规模2023年", "市场规模2024年"],
        "values": [100.0, 120.0, 150.0],
    }


def test_document_agent_groups_chart_datapoints_by_unit(tmp_path, monkeypatch):
    captured = []

    class FakeChartGenerator:
        def __init__(self, **kwargs):
            pass

        def generate(self, config):
            captured.append(config)
            return type("Result", (), {"success": True, "image_path": str(tmp_path / f"chart{len(captured)}.png")})()

    monkeypatch.setattr("src.services.chart_generator.ChartGenerator", FakeChartGenerator)
    agent = DocumentGenerationAgent("test-doc", storage_path=str(tmp_path))
    report = {
        "sections": [{
            "id": "s1",
            "title": "财务与销量",
            "data_points": [
                {"metric": "营业收入2024年", "value": "100", "unit": "亿元"},
                {"metric": "营业收入2025年", "value": "120", "unit": "亿元"},
                {"metric": "销量2024年", "value": "20", "unit": "万辆"},
                {"metric": "销量2025年", "value": "25", "unit": "万辆"},
            ],
        }]
    }

    agent._html_charts_from_datapoints(report)

    assert len(captured) == 2
    chart_categories = [set(config.data["categories"]) for config in captured]
    assert {"营业收入2024年", "营业收入2025年"} in chart_categories
    assert {"销量2024年", "销量2025年"} in chart_categories


def test_document_agent_skips_same_unit_but_unrelated_metrics(tmp_path, monkeypatch):
    captured = []

    class FakeChartGenerator:
        def __init__(self, **kwargs):
            pass

        def generate(self, config):
            captured.append(config)
            return type("Result", (), {"success": True, "image_path": str(tmp_path / "chart.png")})()

    monkeypatch.setattr("src.services.chart_generator.ChartGenerator", FakeChartGenerator)
    agent = DocumentGenerationAgent("test-doc", storage_path=str(tmp_path))
    report = {
        "sections": [{
            "id": "s1",
            "title": "指标对比",
            "data_points": [
                {"metric": "营业收入同比", "value": "20", "unit": "%"},
                {"metric": "海外收入占比", "value": "50", "unit": "%"},
                {"metric": "销量同比增速", "value": "30", "unit": "%"},
            ],
        }]
    }

    agent._html_charts_from_datapoints(report)

    assert captured == []


def test_document_agent_normalizes_html_chart_assets_to_relative_paths(tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    output_dir = tmp_path / "html"
    html = f'<img src="{source}" alt="chart">'

    agent = DocumentGenerationAgent("test-doc", storage_path=str(tmp_path))
    normalized = agent._prepare_html_chart_assets(html, output_dir)

    assert 'src="charts/source.png"' in normalized
    assert (output_dir / "charts" / "source.png").read_bytes() == b"png"


@pytest.mark.asyncio
async def test_html_chart_generation_uses_llm_planner_not_numeric_extraction(monkeypatch, tmp_path):
    planner_calls = []

    class FakePlanner:
        def __init__(self, **kwargs):
            pass

        async def plan(self, **kwargs):
            planner_calls.append(kwargs)
            return [ChartPlan(
                chart_type=ChartType.LINE,
                title="LLM 识别的市场规模趋势",
                subtitle="官方统计",
                data={"years": ["2024", "2025"], "scenarios": {"市场规模": [100, 120]}},
                caption="市场规模保持增长",
                xlabel="年份",
                ylabel="亿元",
                confidence=0.9,
                reason="章节论点需要验证趋势",
                insertion_anchor="市场规模",
                anchor_type="after_paragraph",
                unit="亿元",
            )]

    class FakeGenerator:
        def __init__(self, **kwargs):
            pass

        def generate(self, config):
            return type("Result", (), {"success": True, "image_path": str(tmp_path / "planned.png")})()

    monkeypatch.setattr("src.services.chart_planner.ChartPlannerAgent", FakePlanner)
    monkeypatch.setattr("src.services.chart_generator.ChartGenerator", FakeGenerator)
    agent = DocumentGenerationAgent("test-doc", storage_path=str(tmp_path))

    report = {"topic": "新能源汽车", "sections": [{
        "id": "s1", "title": "市场规模", "content": "市场处于扩张阶段。",
        "data_points": [
            {"metric": "收入", "value": "100", "unit": "亿元"},
            {"metric": "销量", "value": "20", "unit": "万辆"},
        ],
    }]}

    result = await agent._generate_charts_for_html(report)

    assert len(planner_calls) == 1
    assert result["sections"][0]["charts"][0]["title"] == "LLM 识别的市场规模趋势"


def test_downstream_consistency_is_a_blocking_result_not_warning_only():
    patched = ChapterWriteOutput(
        chapter_id="ch1",
        title="市场规模",
        content="市场规模达2000亿元",
        data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="A")],
    )
    downstream = ChapterWriteOutput(
        chapter_id="ch2",
        title="概述",
        content="市场规模约1800亿元",
    )

    result = ReportOrchestrator._verify_downstream_consistency([patched, downstream], {"ch1"})

    assert result["stale_chapter_ids"] == ["ch2"]
    assert result["blocking"] is True


def test_canonical_update_propagates_to_downstream_chapter():
    patched = ChapterWriteOutput(
        chapter_id="ch1", title="市场规模", content="市场规模达2000亿元",
        data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="A")],
    )
    downstream = ChapterWriteOutput(
        chapter_id="ch2", title="概述", content="市场规模约1800亿元",
    )

    result = ReportOrchestrator._propagate_canonical_updates(
        [patched, downstream], {"ch1"}
    )

    assert "2000亿元" in downstream.content
    assert "1800亿元" not in downstream.content
    assert result["unresolved_chapter_ids"] == []


def test_latest_repaired_preview_path_replaces_stale_path():
    result = {"document_path": "E:/reports/repaired.html"}

    latest = ResearchOrchestrator._latest_preview_path(
        "E:/reports/original.html", result
    )

    assert latest == "E:/reports/repaired.html"


def test_unstructured_quality_adjustment_does_not_pollute_report_content():
    section = {"id": "s1", "title": "市场规模", "content": "原始正文"}

    applied = ResearchOrchestrator._apply_quality_adjustment(
        section, "请补充数据来源"
    )

    assert applied is False
    assert section["content"] == "原始正文"
    assert "[修复]" not in section["content"]


def test_quality_issue_requires_stable_section_and_structured_operation():
    """Defense findings must not become ungrounded prose appended to a chapter."""
    issues = [
        {
            "type": "defense_audit",
            "layer": "L3",
            "chapter_id": "ch1",
            "message": "缺少 source_url",
        },
        {
            "type": "defense_audit",
            "layer": "L3",
            "chapter_id": "ch1",
            "repair": {"replace": "旧值", "replacement": "新值"},
        },
        {
            "type": "defense_audit",
            "layer": "L5",
            "chapter_id": "",
            "repair": {"replace": "A", "replacement": "B"},
        },
    ]

    adjustments = ResearchOrchestrator._build_quality_adjustments(
        issues, suggestions=[], document_path="report.html"
    )

    assert adjustments == [{
        "section": "ch1",
        "section_id": "ch1",
        "adjustment": {"replace": "旧值", "replacement": "新值"},
        "document_path": "report.html",
        "revision_type": "minor",
    }]


def test_claim_namespace_is_scoped_by_task_chapter_and_section():
    first = GenericAgent._build_claim_canonical_key(
        task_id="task_a", chapter_id="chapter_1", section_id="market", claim_id="0"
    )
    second = GenericAgent._build_claim_canonical_key(
        task_id="task_b", chapter_id="chapter_2", section_id="policy", claim_id="0"
    )

    assert first != second
    assert "claim::0" not in first
    assert "claim::0" not in second


def test_quality_and_coverage_warnings_do_not_block_artifact_export():
    assert ResearchOrchestrator._quality_allows_formal_export(
        quality_passed=False, artifact_kind="formal"
    ) is True
    assert ResearchOrchestrator._quality_allows_formal_export(
        quality_passed=False, artifact_kind="formal", structural_passed=False
    ) is True
    assert ResearchOrchestrator._quality_allows_formal_export(
        quality_passed=False, artifact_kind="diagnostic"
    ) is True


def test_report_assembly_populates_manifest_synthesis_slots():
    chapter = ChapterWriteOutput(
        chapter_id="ch1",
        title="市场规模",
        content="市场规模达到100亿元。",
        key_conclusions=["市场规模达到100亿元"],
    )

    result = ReportOrchestrator._assemble_final_report(
        [chapter], "执行摘要内容", ReviewOutput(overall_score=90), "测试主题"
    )

    assert result["exec_summary"] == "执行摘要内容"
    assert "市场规模达到100亿元" in result["conclusion"]
