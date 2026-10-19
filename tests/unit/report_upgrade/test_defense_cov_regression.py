from src.agents.fixed_agents.report_upgrade.defense_loop import DefenseLoopController
from src.agents.fixed_agents.report_upgrade.defense_audit import ReportDefenseAudit


def test_coverage_action_is_executable_and_has_lifecycle_statuses():
    controller = DefenseLoopController(max_rounds=2)
    issue = {
        "layer": "coverage",
        "code": "missing_topic",
        "chapter_id": "ch1",
        "topic": "竞争格局",
    }
    action = {
        "layer": "coverage",
        "type": "search_evidence",
        "chapter_id": "ch1",
        "metric": "竞争格局",
    }

    decision = controller.evaluate({"passed": False, "issues": [issue]}, [action])

    assert decision.should_repair is True
    assert decision.actions == (action,)
    assert controller.action_lifecycle[0]["status"] == "planned"

    controller.mark_actions_processed(decision.actions)
    controller.finalize_action_verification({"passed": True, "issues": []})
    assert controller.action_lifecycle[0]["status"] == "verified"


def test_failed_and_unresolved_action_states_are_retained():
    controller = DefenseLoopController(max_rounds=2)
    action = {
        "layer": "coverage",
        "type": "search_evidence",
        "chapter_id": "ch1",
        "metric": "竞争格局",
    }
    decision = controller.evaluate(
        {"passed": False, "issues": [{"layer": "coverage", "code": "missing_topic", "chapter_id": "ch1"}]},
        [action],
    )
    controller.mark_actions_failed(decision.actions)
    controller.finalize_action_verification({"passed": False, "issues": [{"layer": "coverage", "code": "missing_topic", "chapter_id": "ch1"}]})
    assert controller.action_lifecycle[0]["status"] == "failed"

    controller = DefenseLoopController(max_rounds=2)
    decision = controller.evaluate(
        {"passed": False, "issues": [{"layer": "coverage", "code": "missing_topic", "chapter_id": "ch1"}]},
        [action],
    )
    controller.mark_actions_processed(decision.actions)
    controller.finalize_action_verification({"passed": False, "issues": [{"layer": "coverage", "code": "missing_topic", "chapter_id": "ch1"}]})
    assert controller.action_lifecycle[0]["status"] == "unresolved"


def test_audit_exposes_formal_and_diagnostic_status():
    result = ReportDefenseAudit().audit({"sections": []})
    assert result["formal_status"] == "passed"
    assert result["diagnostic_status"] == "clean"


def test_evidence_search_actions_are_correlated_to_their_own_gap():
    from src.agents.fixed_agents.report_upgrade.models import DataGap, DataRepairResult
    from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator

    actions = [
        {"type": "search_evidence", "chapter_id": "ch1", "metric": "规模"},
        {"type": "search_evidence", "chapter_id": "ch2", "metric": "份额"},
    ]
    results = [
        DataRepairResult(
            gap=DataGap("ch1", "规模", "ctx"), found=True, value="100",
        ),
        DataRepairResult(
            gap=DataGap("ch2", "份额", "ctx"), found=False,
        ),
    ]

    successful, failed = ReportOrchestrator._classify_evidence_search_actions(actions, results)

    assert successful == [actions[0]]
    assert failed == [actions[1]]
