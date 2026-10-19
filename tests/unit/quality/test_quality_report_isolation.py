import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_html_used_for_quality_checks_does_not_mutate_authoritative_report():
    from src.agents.fixed_agents.quality_check_agent import QualityCheckAgent

    agent = QualityCheckAgent(agent_id="quality-isolation")
    agent.publish_event = AsyncMock()
    agent.write_shared_state = AsyncMock()
    agent._report_progress = MagicMock()
    agent._check_completeness = MagicMock(return_value={"passed": True, "issues": [], "suggestions": []})
    agent._check_accuracy = MagicMock(return_value={"issues": [], "suggestions": []})
    agent._check_consistency = MagicMock(return_value={"issues": [], "suggestions": []})
    agent._check_format = MagicMock(return_value={"issues": [], "suggestions": []})
    agent._calculate_score = MagicMock(return_value=100.0)

    report = {"title": "报告", "content": "正文", "sections": []}
    result = await agent.execute({
        "report": report,
        "html_content": "<html>预览内容</html>",
    })

    assert result["passed"] is True
    assert report == {"title": "报告", "content": "正文", "sections": []}
    checked_report = agent._check_completeness.call_args.args[0]
    assert "预览内容" in checked_report["content"]

