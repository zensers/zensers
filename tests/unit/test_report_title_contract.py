"""Regression tests for report title consistency across quality checks and API data."""

from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent
from src.core.orchestrator.aggregation.result_aggregator import AggregationResult


def test_quality_check_accepts_top_level_html_heading():
    """A generated HTML report with <h1> must not be reported as title-less."""
    agent = QualityCheckAgent(agent_id="title-contract", storage_path="data")

    result = agent._check_format(
        {
            "title": "鸡蛋价格走势",
            "content": "<html><head><title>鸡蛋价格走势</title></head>"
            "<body><h1>鸡蛋价格走势</h1></body></html>",
        },
        agent.DEFAULT_STANDARDS,
    )

    assert not any(
        issue.get("message") == "Report is missing a top-level heading"
        for issue in result["issues"]
    )


def test_aggregated_report_preserves_top_level_title():
    """The structured report returned to the API must expose its title."""
    result = AggregationResult(data={"topic": "鸡蛋价格走势"}).to_dict()

    assert result["title"] == "鸡蛋价格走势"
