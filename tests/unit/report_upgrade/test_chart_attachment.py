import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator


@pytest.mark.asyncio
async def test_final_report_attaches_llm_planned_rendered_chart():
    planner = MagicMock()
    planner.plan = AsyncMock(return_value=[SimpleNamespace(
        chart_type="bar",
        title="市场规模对比",
        subtitle="单位：亿元",
        data={"categories": ["A", "B"], "values": [10, 20]},
        caption="市场规模",
        xlabel="地区",
        ylabel="亿元",
        reason="比较两个市场的规模差异",
        insertion_anchor="市场规模",
        anchor_type="section_end",
        unit="亿元",
        data_source="content",
    )])
    generator = MagicMock()
    generator.generate.return_value = SimpleNamespace(
        success=True,
        image_path="output/charts/market_size.png",
        error=None,
    )
    orchestrator = ReportOrchestrator(
        chapter_writer=MagicMock(),
        chapter_reviewer=MagicMock(),
        global_reviewer=MagicMock(),
        chart_planner=planner,
        chart_generator=generator,
    )

    report = await orchestrator._plan_and_render_charts({
        "topic": "新能源汽车",
        "sections": [{"id": "s1", "title": "市场规模", "content": "A市场规模高于B市场。", "charts": []}],
    })

    assert report["sections"][0]["charts"][0]["path"].endswith("market_size.png")
    planner.plan.assert_awaited_once()
    generator.generate.assert_called_once()


@pytest.mark.asyncio
async def test_chart_planner_can_skip_chart_without_breaking_report():
    planner = MagicMock()
    planner.plan = AsyncMock(return_value=[])
    generator = MagicMock()
    orchestrator = ReportOrchestrator(
        chapter_writer=MagicMock(),
        chapter_reviewer=MagicMock(),
        global_reviewer=MagicMock(),
        chart_planner=planner,
        chart_generator=generator,
    )

    report = await orchestrator._plan_and_render_charts({
        "topic": "新能源汽车",
        "sections": [{"title": "结论", "content": "暂无足够数据。"}],
    })

    assert report["sections"][0]["charts"] == []
    generator.generate.assert_not_called()


def test_defense_rewrite_issues_are_merged_per_chapter():
    actions = ReportOrchestrator._build_defense_rewrite_actions({
        "issues": [
            {"layer": "L4", "code": "scope_collision", "chapter_id": "s1", "message": "全球与中国口径混用"},
            {"layer": "L4", "code": "unbound_numeric_claim", "chapter_id": "s1", "message": "数字缺少证据"},
            {"layer": "L4", "code": "unlabeled_future_value", "chapter_id": "s2", "message": "预测值未标注"},
        ]
    })

    assert len(actions) == 2
    s1 = next(action for action in actions if action["chapter_id"] == "s1")
    assert "scope_collision" in s1["code"]
    assert "unbound_numeric_claim" in s1["code"]
    assert "全球与中国口径混用" in s1["instruction"]
    assert "数字缺少证据" in s1["instruction"]
