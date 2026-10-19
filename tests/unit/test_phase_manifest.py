"""TDD contracts for auditable research phase manifests."""

import json
from unittest import mock

import pytest


def test_manifest_records_required_boundary_fields(tmp_path):
    from src.core.diagnostics.phase_manifest import PhaseManifestStore

    store = PhaseManifestStore(
        task_id="research-1", session_id="session-1", root=tmp_path, run_id="run-1"
    )
    store.record(
        "PHASE_START", phase="report_generation", batch_id="batch-1",
        agent_id="agent-1", section_id="section_0", checkpoint_id="cp-1",
        input_count=3,
    )
    manifest = json.loads((tmp_path / "research-1" / "diagnostic_manifest.json").read_text())
    event = manifest["phases"][0]

    assert event["event"] == "PHASE_START"
    assert event["session_id"] == "session-1"
    assert event["task_id"] == "research-1"
    assert event["run_id"] == "run-1"
    assert event["phase"] == "report_generation"
    assert event["batch_id"] == "batch-1"
    assert event["agent_id"] == "agent-1"
    assert event["section_id"] == "section_0"
    assert event["checkpoint_id"] == "cp-1"


def test_manifest_rejects_boundary_event_without_phase(tmp_path):
    from src.core.diagnostics.phase_manifest import PhaseManifestStore

    store = PhaseManifestStore("task-1", "session-1", tmp_path, "run-1")
    with pytest.raises(ValueError, match="phase"):
        store.record("PHASE_COMPLETE")


def test_manifest_rejects_path_like_task_id(tmp_path):
    from src.core.diagnostics.phase_manifest import PhaseManifestStore

    with pytest.raises(ValueError):
        PhaseManifestStore("..\\outside", "session-1", tmp_path)


def test_progress_phase_events_are_written_to_manifest():
    from src.core.progress_streamer import ProgressStreamer

    with mock.patch(
        "src.core.progress_streamer.PhaseManifestStore", create=True
    ) as manifest_cls:
        ProgressStreamer.start_phase("manifest-task", "analysis", "Analysis")
        ProgressStreamer.complete_phase("manifest-task", "analysis")

    calls = manifest_cls.return_value.record.call_args_list
    assert [call.args[0] for call in calls] == ["PHASE_START", "PHASE_COMPLETE"]
