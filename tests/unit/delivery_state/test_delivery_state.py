from src.core.storage.research_result_store import ResearchResultStore, ResearchStatus


def test_coverage_warning_keeps_artifact_available_but_not_formal(tmp_path):
    from src.core.orchestrator.orchestrator import _derive_delivery_state

    artifact = tmp_path / "report.html"
    artifact.write_text("<html><body>报告</body></html>", encoding="utf-8")

    state = _derive_delivery_state(
        quality_passed=True,
        structural_passed=False,
        artifact_path=artifact,
    )

    assert state["artifact_status"] == "ready"
    assert state["delivery_class"] == "available_with_warnings"
    assert state["formal_complete"] is False
    assert state["effective_quality_passed"] is False

    fallback_state = _derive_delivery_state(
        quality_passed=True,
        structural_passed=True,
        artifact_path=artifact,
        fallback_kind="fallback_markdown",
    )
    assert fallback_state["artifact_status"] == "ready"
    assert fallback_state["formal_complete"] is False
    assert fallback_state["delivery_class"] == "available_with_warnings"


def test_warning_delivery_is_distinct_from_formal_completion(tmp_path):
    store = ResearchResultStore(str(tmp_path))
    store.save_result(
        "delivery-test",
        {
            "title": "诊断报告",
            "topic": "诊断报告",
            "sections": [],
            "formal_complete": False,
            "quality_gate_status": "degraded",
            "delivery_class": "available_with_warnings",
            "artifact_status": "ready",
        },
        status=ResearchStatus.COMPLETED_WITH_WARNINGS,
    )

    result = store.load_result("delivery-test")
    metadata = store.load_metadata("delivery-test")

    assert result["formal_complete"] is False
    assert result["delivery_class"] == "available_with_warnings"
    assert result["artifact_status"] == "ready"
    assert metadata.delivery_class == "available_with_warnings"
    assert metadata.formal_complete is False
    assert metadata.quality_gate_status == "degraded"


def test_storage_record_preserves_warning_status_without_blocking_file(tmp_path):
    from src.core.orchestrator.output.storage_manager import StorageConfig, StorageManager

    manager = StorageManager(StorageConfig(base_path=tmp_path))
    record = manager.save(
        task_id="storage-warning",
        topic="报告",
        result={"sections": []},
        metadata={
            "formal_complete": False,
            "quality_gate_status": "degraded",
            "delivery_class": "available_with_warnings",
        },
    )

    assert record.status == "completed_with_warnings"
    assert record.result_path is not None and record.result_path.is_file()
