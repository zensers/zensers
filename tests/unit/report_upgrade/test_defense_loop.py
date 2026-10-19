from src.agents.fixed_agents.report_upgrade.defense_loop import DefenseLoopController


def _audit(*issues, passed=False):
    return {
        "passed": passed,
        "issues": list(issues),
    }


def test_passed_audit_stops_before_any_repair():
    controller = DefenseLoopController(max_rounds=3)

    decision = controller.evaluate(_audit(passed=True), executable_actions=[])

    assert decision.status == "passed"
    assert decision.should_repair is False


def test_missing_executable_action_blocks_instead_of_looping():
    controller = DefenseLoopController(max_rounds=3)

    decision = controller.evaluate(
        _audit({"layer": "L3", "code": "missing_source_url"}),
        executable_actions=[],
    )

    assert decision.status == "deliver_with_warnings"
    assert decision.termination_reason == "no_actions"
    assert decision.should_repair is False


def test_malformed_action_is_not_treated_as_executable():
    controller = DefenseLoopController(max_rounds=3)

    decision = controller.evaluate(
        _audit({"layer": "L3", "code": "missing_source_url"}),
        executable_actions=[{}],
    )

    assert decision.status == "deliver_with_warnings"
    assert decision.termination_reason == "no_actions"
    assert decision.should_repair is False


def test_same_issue_signature_after_repair_blocks_as_no_progress():
    controller = DefenseLoopController(max_rounds=3)
    audit = _audit({"layer": "L3", "code": "missing_source_url", "chapter_id": "ch1"})

    first = controller.evaluate(audit, executable_actions=[{"layer": "L3", "type": "search_evidence"}])
    second = controller.evaluate(audit, executable_actions=[{"layer": "L3", "type": "search_evidence"}])

    assert first.status == "repair"
    assert first.should_repair is True
    assert second.status == "deliver_with_warnings"
    assert second.termination_reason == "no_progress"
    assert second.should_repair is False


def test_max_rounds_is_hard_limit():
    controller = DefenseLoopController(max_rounds=1)
    first = controller.evaluate(
        _audit({"layer": "L4", "code": "scope_collision"}),
        executable_actions=[{"layer": "L4", "type": "rewrite_scope"}],
    )
    second = controller.evaluate(
        _audit({"layer": "L4", "code": "different_issue"}),
        executable_actions=[{"layer": "L4", "type": "rewrite_scope"}],
    )

    assert first.status == "repair"
    assert second.status == "deliver_with_warnings"
    assert second.termination_reason == "max_rounds"
    assert controller.rounds == 1


def test_repairs_all_failing_layers_in_one_controlled_batch():
    controller = DefenseLoopController(max_rounds=4)
    audit = _audit(
        {"layer": "L1", "code": "missing_chapter_binding"},
        {"layer": "L3", "code": "missing_source_url"},
    )

    decision = controller.evaluate(
        audit,
        executable_actions=[
            {"layer": "L1", "type": "bind_chapter"},
            {"layer": "L3", "type": "search_evidence"},
        ],
    )

    assert decision.status == "repair"
    assert decision.stages == ("L1", "L3")
    assert decision.actions == (
        {"layer": "L1", "type": "bind_chapter"},
        {"layer": "L3", "type": "search_evidence"},
    )


def test_unresolved_batch_is_delivered_with_warnings_after_no_progress():
    controller = DefenseLoopController(max_rounds=4)
    first = controller.evaluate(
        _audit({"layer": "L1", "code": "missing_chapter_binding"}),
        executable_actions=[{"layer": "L1", "type": "bind_chapter"}],
    )
    second = controller.evaluate(
        _audit(
            {"layer": "L1", "code": "missing_chapter_binding"},
            {"layer": "L2", "code": "missing_period"},
        ),
        executable_actions=[
            {"layer": "L2", "type": "add_period"},
            {"layer": "L1", "type": "bind_chapter"},
        ],
    )

    assert second.status == "repair"
    third = controller.evaluate(
        _audit(
            {"layer": "L1", "code": "missing_chapter_binding"},
            {"layer": "L2", "code": "missing_period"},
        ),
        executable_actions=[
            {"layer": "L1", "type": "bind_chapter"},
            {"layer": "L2", "type": "add_period"},
        ],
    )

    assert first.stages == ("L1",)
    assert third.status == "deliver_with_warnings"
    assert third.termination_reason == "no_progress"


def test_processed_issue_is_not_repaired_again_after_signature_changes():
    controller = DefenseLoopController(max_rounds=4)
    first_issue = {
        "layer": "L4",
        "code": "scope_collision",
        "chapter_id": "ch1",
        "metric": "market_size",
    }
    first_action = {
        "layer": "L4",
        "type": "rewrite_scope",
        "chapter_id": "ch1",
        "code": "scope_collision",
    }

    first = controller.evaluate(_audit(first_issue), [first_action])
    assert first.should_repair is True
    controller.mark_actions_processed(first.actions)

    second = controller.evaluate(
        _audit(
            first_issue,
            {"layer": "L3", "code": "missing_period", "chapter_id": "ch2", "metric": "growth"},
        ),
        [
            first_action,
            {"layer": "L3", "type": "search_evidence", "chapter_id": "ch2", "metric": "growth"},
        ],
    )

    assert second.should_repair is True
    assert second.actions == (
        {"layer": "L3", "type": "search_evidence", "chapter_id": "ch2", "metric": "growth"},
    )


def test_issue_state_is_resolved_when_issue_disappears():
    controller = DefenseLoopController(max_rounds=2)
    issue = {"layer": "L3", "code": "missing_period", "chapter_id": "ch1", "metric": "period"}
    action = {"layer": "L3", "type": "search_evidence", "chapter_id": "ch1", "metric": "period"}

    decision = controller.evaluate(_audit(issue), [action])
    controller.mark_actions_processed(decision.actions)
    resolved = controller.evaluate(_audit(passed=True), [])

    assert resolved.status == "passed"
    assert controller.issue_states[controller.issue_key(issue)] == "resolved"


def test_new_audit_issue_after_evidence_repair_is_bounded_to_new_scope():
    """Evidence changes may reveal a new issue, but must not replay old work."""
    controller = DefenseLoopController(max_rounds=3)
    original = {
        "layer": "L3",
        "code": "missing_source_url",
        "chapter_id": "ch1",
        "metric": "market_size",
    }
    repair = {
        "layer": "L3",
        "type": "search_evidence",
        "chapter_id": "ch1",
        "metric": "market_size",
    }

    first = controller.evaluate(_audit(original), [repair])
    controller.mark_actions_processed(first.actions)

    # The supplement makes the old URL issue disappear but exposes a distinct
    # evidence excerpt issue.  Only the new issue may schedule work.
    second_issue = {
        "layer": "L3",
        "code": "missing_evidence_excerpt",
        "chapter_id": "ch1",
        "metric": "market_size",
    }
    second = controller.evaluate(
        _audit(second_issue),
        [repair, {
            "layer": "L3",
            "type": "extract_evidence",
            "chapter_id": "ch1",
            "metric": "market_size",
        }],
    )

    assert second.status == "repair"
    assert second.actions == ({
        "layer": "L3",
        "type": "extract_evidence",
        "chapter_id": "ch1",
        "metric": "market_size",
    },)
