import pytest


@pytest.mark.asyncio
async def test_canonical_registry_keeps_scoped_metrics_separate():
    from src.core.data.canonical_registry import CanonicalDataEntry, CanonicalDataRegistry

    registry = CanonicalDataRegistry()
    await registry.register(CanonicalDataEntry(
        metric="市场份额", value=12.0, unit="%", year="2025",
        period="2025Q1", geographic_scope="全球", population="智能手机出货量",
        evidence_id="ev-global-q1",
    ))
    await registry.register(CanonicalDataEntry(
        metric="市场份额", value=18.0, unit="%", year="2025",
        period="2025Q1", geographic_scope="中国", population="智能手机出货量",
        evidence_id="ev-cn-q1",
    ))

    global_entry = await registry.get(
        "市场份额", year="2025", period="2025Q1",
        geographic_scope="全球", population="智能手机出货量",
        evidence_id="ev-global-q1", unit="%",
    )
    china_entry = await registry.get(
        "市场份额", year="2025", period="2025Q1",
        geographic_scope="中国", population="智能手机出货量",
        evidence_id="ev-cn-q1", unit="%",
    )

    assert global_entry is not None and global_entry.value == 12.0
    assert china_entry is not None and china_entry.value == 18.0


@pytest.mark.asyncio
async def test_canonical_registry_conflicts_same_scope_across_source_urls():
    from src.core.data.canonical_registry import CanonicalDataEntry, CanonicalDataRegistry

    registry = CanonicalDataRegistry()
    await registry.register(CanonicalDataEntry(
        metric="出货量", value=100.0, unit="万台", year="2025",
        period="2025Q1", geographic_scope="中国", source="source-a",
        source_url="https://a.example/report",
    ))
    conflict = await registry.register(CanonicalDataEntry(
        metric="出货量", value=120.0, unit="万台", year="2025",
        period="2025Q1", geographic_scope="中国", source="source-b",
        source_url="https://b.example/report",
    ))

    assert conflict is not None
    assert len(registry.get_all()) == 1


def test_parse_entry_key_preserves_provenance_identity():
    from src.core.data.canonical_registry import CanonicalDataEntry, _entry_key, parse_entry_key

    key = _entry_key(CanonicalDataEntry(
        metric="出货量", value=100.0, year="2025", provenance_id="prov-1",
    ))

    assert parse_entry_key(key)["provenance_id"] == "prov-1"


def test_html_finalizer_classifies_dirty_artifact_without_blocking_generation():
    from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent

    result = DocumentGenerationAgent._finalize_html_contract(
        "<html><body>当前数据尚缺少可核验的结构化证据</body></html>",
        {"formal_complete": True, "quality_gate_status": "passed"},
    )

    assert result["artifact_status"] == "ready"
    assert result["formal_complete"] is False
    assert result["delivery_class"] == "available_with_warnings"
    assert result["finalizer_passed"] is False


def test_warning_artifact_has_user_visible_diagnostic_label():
    from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent

    html = DocumentGenerationAgent._add_delivery_banner("<html><body>内容</body></html>")
    assert "诊断版 / 草稿版" in html


def test_html_finalizer_checks_section_titles_against_manifest():
    from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent

    result = DocumentGenerationAgent._finalize_html_contract(
        "<html><body><h2>临时标题</h2></body></html>",
        {
            "title": "报告",
            "sections": [{"id": "s1", "title": "临时标题", "content": "正文"}],
            "section_manifest": [{"section_id": "s1", "title": "正式标题", "output_slot": "body"}],
        },
    )
    assert "title_manifest" in result["issues"]
    assert result["formal_complete"] is False


def test_html_contract_repair_removes_non_content_artifacts_and_keeps_delivery_non_blocking():
    from src.agents.fixed_agents.document_generation_agent import DocumentGenerationAgent

    report = {
        "formal_complete": True,
        "quality_gate_status": "passed",
        "sections": [{"id": "s4", "title": "数据精准修补"}],
        "section_manifest": [{
            "section_id": "s4", "title": "竞争格局", "output_slot": "body",
        }],
    }
    html = (
        "<html><body><h2>数据精准修补</h2>"
        "<p>当前数据尚缺少可核验的结构化证据</p>"
        "<p>**结论**</p>"
        "<p>|指标|数值|</p><table><tr><th>指标</th></tr></table>"
        "</body></html>"
    )

    repaired = DocumentGenerationAgent._repair_html_contract(html, report)
    normalized = DocumentGenerationAgent._normalize_report_titles_for_render(report)
    finalizer = DocumentGenerationAgent._finalize_html_contract(repaired, normalized)

    assert "当前数据尚缺少可核验的结构化证据" not in repaired
    assert "数据精准修补" not in repaired
    assert "**" not in repaired
    assert "<table" not in repaired
    assert finalizer["issues"] == []
    assert finalizer["artifact_status"] == "ready"
