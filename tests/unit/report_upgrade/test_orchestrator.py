import pytest
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict
from pathlib import Path

from src.agents.fixed_agents.report_upgrade.orchestrator import (
    ReportOrchestrator, RetryPolicy, DATAPOINT_FIELDS, _is_vague_source,
    _checkpoint_filename,
)
from src.agents.fixed_agents.report_upgrade.models import (
    ChapterWriteOutput, ChapterReviewOutput, ChapterIssue,
    ReviewOutput, ReviewIssue, FixSuggestion,
    DataPoint, DataConflict, DataConflictResolution,
    DataGap, DataRepairResult,
)
from src.agents.fixed_agents.report_upgrade.data_registry import DataRegistry
from src.agents.fixed_agents.report_upgrade.prompt_manager import PromptManager


def make_chapter(chapter_id="ch1", title="市场规模", content="市场规模达2000亿元"):
    return ChapterWriteOutput(
        chapter_id=chapter_id, title=title, content=content,
        data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="iimedia.cn")],
        key_conclusions=["市场规模达2000亿"],
    )


def make_review_pass(score=85.0):
    return ChapterReviewOutput(passed=True, score=score, issues=[])


def make_review_fail(score=40.0):
    return ChapterReviewOutput(
        passed=False, score=score,
        issues=[ChapterIssue(category="data_support", severity="HIGH", location="p:1", description="无数据", suggestion="补充")],
    )


@pytest.mark.asyncio
async def test_checkpoint_restore_preserves_evidence_id(tmp_path, monkeypatch):
    task_id = "checkpoint-evidence"
    checkpoint_dir = tmp_path / "data" / task_id / "checkpoints"
    checkpoint_dir.mkdir(parents=True)
    payload = {
        "chapter_id": "ch1",
        "title": "规模",
        "content": "市场规模达到100亿元。",
        "data_points_used": [{
            "metric": "市场规模", "value": "100", "unit": "亿元",
            "source": "官方报告", "chapter_id": "ch1",
            "source_url": "https://example.test/report",
            "evidence_id": "ev-checkpoint",
            "provenance_id": "prov-checkpoint",
            "geographic_scope": "中国", "period": "2025年",
            "population": "目标市场", "evidence_status": "verified",
        }],
        "key_conclusions": [],
        "self_check_passed": True,
        "self_check_issues": [],
    }
    (checkpoint_dir / "chapter_1.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    restored = await ReportOrchestrator._restore_from_checkpoint(task_id)

    assert restored is not None
    assert restored[0][0].data_points_used[0].evidence_id == "ev-checkpoint"
    assert restored[0][0].data_points_used[0].provenance_id == "prov-checkpoint"


@pytest.mark.asyncio
async def test_checkpoint_write_supports_subsection_ids_on_windows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    chapter = make_chapter(chapter_id="section_0::sub_0_0")
    orchestrator = ReportOrchestrator.__new__(ReportOrchestrator)
    orchestrator._data_registry = MagicMock()
    orchestrator._data_registry.to_snapshot.return_value = {}

    await orchestrator._checkpoint_chapter("portable-checkpoint", chapter)

    checkpoint_dir = tmp_path / "data" / "portable-checkpoint" / "checkpoints"
    files = list(checkpoint_dir.glob("chapter_*.json"))
    assert len(files) == 1
    assert ":" not in files[0].name
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["chapter_id"] == "section_0::sub_0_0"
    assert files[0].name == _checkpoint_filename("section_0::sub_0_0")


@pytest.mark.asyncio
async def test_checkpoint_restore_ignores_stale_sections_from_previous_report(
    tmp_path, monkeypatch,
):
    task_id = "checkpoint-stale-sections"
    checkpoint_dir = tmp_path / "data" / task_id / "checkpoints"
    checkpoint_dir.mkdir(parents=True)
    for chapter_id, title in (("section_0_current", "当前章节"), ("section_0_old", "旧章节")):
        payload = {
            "chapter_id": chapter_id,
            "title": title,
            "content": f"{title}内容",
            "data_points_used": [],
            "key_conclusions": [],
        }
        (checkpoint_dir / f"chapter_{chapter_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8",
        )
    monkeypatch.chdir(tmp_path)

    restored = await ReportOrchestrator._restore_from_checkpoint(
        task_id, allowed_section_ids={"section_0_current"},
    )

    assert restored is not None
    assert [chapter.chapter_id for chapter in restored[0]] == ["section_0_current"]


@pytest.mark.asyncio
async def test_data_repair_evidence_is_written_back_to_structured_data_point(orchestrator):
    repaired_chapter = make_chapter()
    repaired_chapter.data_points_used[0].source = "官方机构"
    repair = DataRepairResult(
        gap=DataGap(chapter_id="ch1", metric="市场规模", context="缺少数据"),
        found=True,
        value="2000",
        unit="亿元",
        source="官方机构",
        source_title="官方市场报告",
        source_url="https://example.test/report",
        evidence_id="ev-1",
        provenance_id="prov-1",
        evidence_excerpt="2024年市场规模为2000亿元",
        locator="page=4",
        task_id="task-1",
        request_id="req-1",
        geographic_scope="中国",
        period="2024年",
        population="新能源汽车市场",
    )
    orchestrator._chapter_writer.patch_data.return_value = repaired_chapter

    chapters, patched_ids = await orchestrator._apply_data_repairs(
        [make_chapter()], [repair], [], {}
    )

    point = chapters[0].data_points_used[0]
    assert "ch1" in patched_ids
    assert point.source_url == "https://example.test/report"
    assert point.evidence_id == "ev-1"
    assert point.provenance_id == "prov-1"
    assert point.evidence_status == "verified"
    assert point.geographic_scope == "中国"
    assert point.period == "2024年"
    assert point.population == "新能源汽车市场"


@pytest.mark.asyncio
async def test_defense_repair_loop_reaudits_after_l3_search_repair(orchestrator, monkeypatch):
    first_report = {
        "sections": [],
        "defense_audit": {
            "passed": False,
            "issues": [{
                "layer": "L3",
                "code": "missing_source_url",
                "chapter_id": "ch1",
                "metric": "市场规模",
                "message": "缺少来源 URL",
            }],
        },
    }
    final_report = {
        "sections": [],
        "defense_audit": {"passed": True, "issues": [], "layers": {}},
    }
    repair = DataRepairResult(
        gap=DataGap(chapter_id="ch1", metric="市场规模", context="缺少来源 URL"),
        found=True,
        value="2000",
        unit="亿元",
        source="官方机构",
        source_title="官方市场报告",
        source_url="https://example.test/report",
        evidence_id="ev-1",
        provenance_id="prov-1",
        evidence_excerpt="市场规模为2000亿元",
    )

    monkeypatch.setattr(
        ReportOrchestrator,
        "_assemble_final_report",
        staticmethod(MagicMock(side_effect=[first_report, final_report])),
    )
    orchestrator._generate_exec_summary = AsyncMock(return_value="摘要")
    orchestrator._data_repair_agent.repair_batch = AsyncMock(return_value=[repair])
    orchestrator._apply_data_repairs = AsyncMock(return_value=([], {"ch1"}))

    result = await orchestrator._run_defense_repair_loop(
        chapters=[],
        review=make_global_review(),
        framework_config={},
        topic="新能源汽车",
        task_structure={"sections": []},
        original_sources=[],
        quality_report=None,
        conflicts_summary="无已知数据冲突。",
    )

    assert result["defense_audit"]["passed"] is True
    assert result["defense_loop"]["rounds"] == 1
    orchestrator._data_repair_agent.repair_batch.assert_awaited_once()


def test_repair_source_is_added_to_final_source_catalog():
    repair = DataRepairResult(
        gap=DataGap(chapter_id="ch1", metric="市场规模", context="缺少数据"),
        found=True,
        source="官方机构",
        source_title="官方市场报告",
        source_url="https://example.test/report",
        evidence_id="ev-1",
        provenance_id="prov-1",
        evidence_excerpt="市场规模为2000亿元",
        locator="page=4",
    )

    merged = ReportOrchestrator._merge_repair_sources(
        [{"title": "已有来源", "url": "https://existing.test"}], [repair]
    )

    assert len(merged) == 2
    assert merged[1] == {
        "title": "官方市场报告",
        "url": "https://example.test/report",
        "type": "web",
        "evidence_id": "ev-1",
        "provenance_id": "prov-1",
        "evidence_excerpt": "市场规模为2000亿元",
        "locator": "page=4",
    }


def test_defense_audit_builds_deduplicated_l2_l3_search_gaps_only():
    audit = {
        "passed": False,
        "issues": [
            {
                "layer": "L3", "code": "missing_source_url",
                "chapter_id": "ch1", "metric": "市场规模", "message": "缺少 URL",
            },
            {
                "layer": "L3", "code": "unverified_evidence",
                "chapter_id": "ch1", "metric": "市场规模", "message": "未验证",
            },
            {
                "layer": "L2", "code": "missing_period",
                "chapter_id": "ch1", "metric": "渗透率", "message": "缺少期间",
            },
            {
                "layer": "L4", "code": "scope_collision",
                "chapter_id": "ch1", "metric": "市场规模", "message": "口径冲突",
            },
            {
                "layer": "L3", "code": "missing_source_url",
                "chapter_id": "", "metric": "无章节指标", "message": "无法定位",
            },
        ],
    }

    gaps = ReportOrchestrator._build_defense_search_gaps(audit)

    # P2-F（复审修订）：L2 元数据缺失（缺期间等）不再派发 search_evidence
    # ——范畴错误纠偏，元数据走证据目录回填通路。只剩 L3 的搜索缺口。
    assert len(gaps) == 1
    assert {(gap.chapter_id, gap.metric) for gap in gaps} == {
        ("ch1", "市场规模")
    }
    assert {gap.metric: gap.audit_layer for gap in gaps} == {
        "市场规模": "L3",
    }


def test_missing_chapter_coverage_is_promoted_to_p0_search_gap():
    audit = {
        "passed": False,
        "issues": [{
            "layer": "coverage", "code": "missing_topic",
            "chapter_id": "summary", "topic": "核心结论",
            "section_title": "摘要与核心结论", "message": "摘要内容缺失",
        }],
    }

    gaps = ReportOrchestrator._build_defense_search_gaps(audit)

    assert len(gaps) == 1
    assert gaps[0].chapter_id == "summary"
    assert gaps[0].metric == "核心结论"
    assert gaps[0].audit_layer == "coverage"
    assert gaps[0].search_keywords[1] == "摘要与核心结论"


def test_post_write_coverage_audit_finds_placeholder_chapter_before_l1_l5():
    from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput

    orchestrator = ReportOrchestrator.__new__(ReportOrchestrator)
    orchestrator._coverage_checker = MagicMock()
    chapters = [ChapterWriteOutput(
        chapter_id="summary", title="摘要与核心结论",
        content="本章节数据不足，无法生成完整分析",
    )]
    issues = orchestrator._build_report_coverage_issues(chapters, {
        "sections": [{"section_id": "summary", "name": "摘要与核心结论"}],
    })

    assert issues[0]["layer"] == "coverage"
    assert issues[0]["code"] == "chapter_content_missing"
    assert issues[0]["chapter_id"] == "summary"


def test_post_write_coverage_audit_uses_manifest_and_detects_missing_leaf():
    from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput

    orchestrator = ReportOrchestrator.__new__(ReportOrchestrator)
    orchestrator._coverage_checker = MagicMock()
    chapters = [ChapterWriteOutput(
        chapter_id="section_0::tam", title="TAM",
        content="市场规模为100亿元。",
    )]
    issues = orchestrator._build_report_coverage_issues(chapters, {
        # Deliberately provide a misleading parent tree.  The manifest must
        # remain authoritative for the coverage audit.
        "sections": [{"section_id": "section_0", "name": "市场规模"}],
        "section_manifest": [
            {"section_id": "section_0::tam", "title": "TAM", "role": "analysis"},
            {"section_id": "section_0::cagr", "title": "CAGR", "role": "analysis"},
        ],
    })

    assert [issue["chapter_id"] for issue in issues] == ["section_0::cagr"]


def test_post_write_coverage_audit_rejects_failed_chapter_even_with_text():
    from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput

    orchestrator = ReportOrchestrator.__new__(ReportOrchestrator)
    orchestrator._coverage_checker = MagicMock()
    chapters = [ChapterWriteOutput(
        chapter_id="section_0::tam", title="TAM",
        content="系统已记录该章节失败状态。", status="failed",
    )]
    issues = orchestrator._build_report_coverage_issues(chapters, {
        "section_manifest": [{"section_id": "section_0::tam", "title": "TAM", "role": "analysis"}],
    })

    assert issues[0]["code"] == "chapter_content_missing"


def test_final_assembly_never_serializes_empty_chapter_content():
    from src.agents.fixed_agents.report_upgrade.models import ChapterWriteOutput, ReviewOutput

    report = ReportOrchestrator._assemble_final_report(
        chapters=[ChapterWriteOutput(
            chapter_id="section_0::tam", title="TAM", content="",
        )],
        exec_summary="",
        review=ReviewOutput(overall_score=0),
        topic="新能源汽车",
    )

    section = report["sections"][0]
    assert section["content"]
    assert section["status"] == "failed"


def test_report_writer_restore_and_audit_share_manifest_only_chapter_set():
    specs = ReportOrchestrator._report_chapter_specs({
        "sections": [],
        "section_manifest": [
            {"section_id": "section_0::tam", "title": "TAM", "role": "analysis"},
            {"section_id": "synthesis_0", "title": "摘要", "role": "synthesis", "output_slot": "exec_summary"},
        ],
    })
    assert [spec["section_id"] for spec in specs] == ["section_0::tam", "synthesis_0"]
    assert specs[1]["section_role"] == "synthesis"


def test_report_writer_honors_routing_manifest_order_and_keeps_synthesis_last():
    specs = ReportOrchestrator._report_chapter_specs({
        "sections": [],
        "section_manifest": [
            {"section_id": "synthesis_0", "title": "摘要", "role": "synthesis", "execution_order": 3},
            {"section_id": "section_1", "title": "竞争格局", "role": "analysis", "execution_order": 1},
            {"section_id": "section_0", "title": "市场规模", "role": "analysis", "execution_order": 0},
        ],
    })
    assert [spec["section_id"] for spec in specs] == ["section_0", "section_1", "synthesis_0"]


def test_synthesis_chapters_are_expanded_after_data_chapters():
    specs = ReportOrchestrator._iter_report_chapter_specs([
        {"section_id": "summary", "section_name": "摘要", "section_role": "synthesis"},
        {"section_id": "market", "section_name": "市场规模", "section_role": "analysis"},
    ])

    assert [spec["section_id"] for spec in specs] == ["market", "summary"]


def test_l1_missing_chapter_binding_is_repaired_structurally():
    chapters = [
        ChapterWriteOutput(
            chapter_id="ch1",
            title="市场规模",
            content="市场规模达2000亿元",
            data_points_used=[DataPoint(
                metric="市场规模", value="2000", unit="亿元", source="官方机构",
                chapter_id="",
            )],
        )
    ]
    audit = {
        "passed": False,
        "issues": [{
            "layer": "L1",
            "code": "missing_chapter_binding",
            "chapter_id": "ch1",
            "metric": "市场规模",
        }],
    }

    actions = ReportOrchestrator._apply_defense_structural_repairs(chapters, audit)

    assert actions == [{
        "layer": "L1",
        "type": "bind_chapter",
        "chapter_id": "ch1",
        "metric": "市场规模",
    }]
    assert chapters[0].data_points_used[0].chapter_id == "ch1"


def test_defense_audit_builds_scoped_l4_rewrite_actions():
    audit = {
        "passed": False,
        "issues": [
            {
                "layer": "L4",
                "code": "scope_collision",
                "chapter_id": "ch1",
                "message": "全球和国内口径混用",
            },
            {
                "layer": "L4",
                "code": "unlabeled_future_value",
                "chapter_id": "ch2",
                "message": "2030年未标注预测",
            },
            {
                "layer": "L5",
                "code": "unresolved_registry_conflict",
                "chapter_id": "",
                "message": "存在冲突",
            },
        ],
    }

    actions = ReportOrchestrator._build_defense_rewrite_actions(audit)

    assert actions == [
        {
            "layer": "L4",
            "type": "rewrite_scope",
            "chapter_id": "ch1",
            "code": "scope_collision",
            "instruction": "全球和国内口径混用",
        },
        {
            "layer": "L4",
            "type": "rewrite_scope",
            "chapter_id": "ch2",
            "code": "unlabeled_future_value",
            "instruction": "2030年未标注预测",
        },
    ]


def test_unbound_numeric_claim_creates_l3_rewrite_action():
    actions = ReportOrchestrator._build_defense_rewrite_actions({
        "issues": [{
            "layer": "L3",
            "code": "unbound_numeric_claim",
            "chapter_id": "market",
            "message": "正文定量断言 29% 未绑定结构化数据点",
        }],
    })
    assert actions == [{
        "layer": "L3",
        "type": "rewrite_scope",
        "chapter_id": "market",
        "code": "unbound_numeric_claim",
        "instruction": "正文定量断言 29% 未绑定结构化数据点",
    }]


def test_content_safety_repairs_remove_unbound_numbers_and_split_scopes():
    chapter = ChapterWriteOutput(
        chapter_id="market",
        title="市场",
        content="全球市场增长29%，国内市场增长15%。",
        data_points_used=[DataPoint(
            metric="国内增长", value="15", unit="%", source="来源",
            chapter_id="market",
        )],
    )
    repaired = ReportOrchestrator._apply_defense_content_safety_repairs(
        [chapter], {
            "issues": [
                {"chapter_id": "market", "code": "unbound_numeric_claim"},
                {"chapter_id": "market", "code": "scope_collision"},
            ],
        },
    )
    assert repaired
    assert "29%" not in chapter.content
    assert "当前数据尚缺少可核验的结构化证据" in chapter.content


def test_l5_action_comes_from_structured_registry_conflict():
    registry = DataRegistry()
    registry.register("市场规模", "2000", "亿元", "ch1", "来源A")
    registry.register("市场规模", "1800", "亿元", "ch2", "来源B")
    audit = {
        "passed": False,
        "issues": [{
            "layer": "L5",
            "code": "unresolved_registry_conflict",
            "message": "存在未解决冲突",
        }],
    }

    actions = ReportOrchestrator._build_defense_conflict_actions(
        audit, registry.get_conflicts()
    )

    assert actions == [{
        "layer": "L5",
        "type": "resolve_conflict",
        "metric": "市场规模",
    }]


def test_l5_loop_rejects_unverified_conflict_fallback():
    resolution = DataConflictResolution(
        conflict=DataConflict(metric="市场规模", entries=[]),
        canonical_value="2000",
        canonical_unit="亿元",
        canonical_source="来源A",
        reason="No search skill available, using first entry",
        chapters_to_update=["ch2"],
    )

    assert ReportOrchestrator._is_safe_conflict_resolution(resolution) is False


@pytest.mark.asyncio
async def test_defense_repair_loop_resolves_registry_conflict(orchestrator, monkeypatch):
    orchestrator._data_registry.register("市场规模", "2000", "亿元", "ch1", "来源A")
    orchestrator._data_registry.register("市场规模", "1800", "亿元", "ch2", "来源B")
    first_report = {
        "sections": [],
        "defense_audit": {
            "passed": False,
            "issues": [{
                "layer": "L5",
                "code": "unresolved_registry_conflict",
                "message": "存在未解决冲突",
            }],
        },
    }
    final_report = {
        "sections": [],
        "defense_audit": {"passed": True, "issues": [], "layers": {}},
    }
    resolution = DataConflictResolution(
        conflict=orchestrator._data_registry.get_conflicts()[0],
        canonical_value="2000",
        canonical_unit="亿元",
        canonical_source="来源A",
        reason="官方来源优先",
        chapters_to_update=["ch2"],
    )
    monkeypatch.setattr(
        ReportOrchestrator,
        "_assemble_final_report",
        staticmethod(MagicMock(side_effect=[first_report, final_report])),
    )
    orchestrator._generate_exec_summary = AsyncMock(return_value="摘要")
    orchestrator._conflict_resolver.resolve = AsyncMock(return_value=resolution)
    orchestrator._apply_data_repairs = AsyncMock(return_value=([], {"ch2"}))

    result = await orchestrator._run_defense_repair_loop(
        chapters=[],
        review=make_global_review(),
        framework_config={},
        topic="新能源汽车",
        task_structure={"sections": []},
        original_sources=[],
        quality_report=None,
        conflicts_summary="存在未解决冲突",
    )

    assert result["defense_audit"]["passed"] is True
    orchestrator._conflict_resolver.resolve.assert_awaited_once()


@pytest.mark.asyncio
async def test_none_conflict_resolution_is_ignored(orchestrator):
    chapters, patched = await orchestrator._apply_data_repairs(
        chapters=[],
        repair_results=[],
        conflict_resolutions=[None],  # resolver failure must not abort the report
        framework_config={},
    )

    assert chapters == []
    assert patched == set()


def test_resolve_chapter_id_accepts_multi_location_issue(orchestrator):
    chapters = [
        ChapterWriteOutput(chapter_id="ch1", title="市场规模", content="内容"),
        ChapterWriteOutput(chapter_id="ch2", title="竞争格局", content="内容"),
    ]

    assert orchestrator._resolve_chapter_id(["ch2", "ch1"], chapters) == "ch2"


@pytest.mark.asyncio
async def test_phase4_batches_structured_repairs_per_chapter(orchestrator, monkeypatch):
    """Several discovered metrics must result in one chapter patch call."""
    chapter = make_chapter()
    issues = [
        ReviewIssue(
            dimension="data_support", severity="HIGH", location="ch1",
            description="缺少市场规模", evidence="补充",
        ),
        ReviewIssue(
            dimension="data_support", severity="HIGH", location="ch1",
            description="缺少增长率", evidence="补充",
        ),
    ]
    review = make_global_review(issues=issues)

    monkeypatch.setattr(
        ReportOrchestrator,
        "_diagnose_issue_source",
        staticmethod(lambda issue, raw: SimpleNamespace(source_layer="L1_missing")),
    )
    monkeypatch.setattr(
        "src.core.entity_resolver.get_entity_resolver",
        lambda: SimpleNamespace(resolve=AsyncMock(return_value=[])),
    )
    orchestrator._try_fill_data_gap = AsyncMock(side_effect=[
        {"source": "source-a", "data": {"metric": "市场规模", "value": "100"}},
        {"source": "source-b", "data": {"metric": "增长率", "value": "10%"}},
    ])
    orchestrator._extract_chapter_data = MagicMock(return_value=({}, ""))
    orchestrator._find_section_spec = MagicMock(return_value={"section_id": "ch1"})
    orchestrator._aggregated_result = MockAggregationResult()
    orchestrator._skill_registry = None
    orchestrator._acquire_evidence_batch = AsyncMock(return_value=[])
    orchestrator._apply_data_repairs = AsyncMock(return_value=([chapter], set()))
    monkeypatch.setattr(
        ReportOrchestrator, "_build_anchor_patch_instructions",
        staticmethod(lambda *args, **kwargs: []),
    )
    orchestrator._chapter_writer.patch_data.return_value = chapter

    await orchestrator._phase4_fix_and_optimize(
        [chapter], review, {}, "新能源汽车",
    )

    assert orchestrator._try_fill_data_gap.await_count == 2
    assert orchestrator._chapter_writer.patch_data.await_count == 1
    instructions = orchestrator._chapter_writer.patch_data.await_args.kwargs["patch_instructions"]
    assert len(instructions) == 2


def make_global_review(score=75.0, issues=None):
    return ReviewOutput(
        overall_score=score,
        dimension_scores={"data_consistency": 70},
        issues=issues or [],
        fix_suggestions=[],
    )


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
def orchestrator(mock_writer, mock_reviewer, mock_global_reviewer,
                 mock_data_repair, mock_conflict_resolver, mock_prompts):
    return ReportOrchestrator(
        chapter_writer=mock_writer,
        chapter_reviewer=mock_reviewer,
        global_reviewer=mock_global_reviewer,
        data_repair_agent=mock_data_repair,
        conflict_resolver=mock_conflict_resolver,
        prompt_manager=mock_prompts,
    )


def make_task_structure(num_sections=2):
    sections = []
    for i in range(num_sections):
        sections.append({
            "section_id": f"ch{i+1}",
            "section_name": f"章节{i+1}",
            "section_role": "analysis",
            "content_dependency": [],
        })
    return {"topic": "新能源汽车", "sections": sections}


class MockAggregationResult:
    def __init__(self):
        self.layered_content = {}
        self.content_provenance = {}
        self.sources = [{"title": "测试来源", "url": "https://example.com", "type": "web"}]


class TestRetryPolicy:
    def test_get_delay(self):
        assert RetryPolicy.get_delay(0) == 1.0
        assert RetryPolicy.get_delay(1) == 2.0
        assert RetryPolicy.get_delay(2) == 4.0


class TestReportOrchestratorGenerateReport:
    @pytest.mark.asyncio
    async def test_single_chapter_pass_review(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer):
        mock_writer.write.return_value = make_chapter()
        mock_reviewer.review.return_value = make_review_pass()
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(1),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        assert result["topic"] == "新能源汽车"
        assert len(result["sections"]) == 1
        assert "sources" in result
        assert len(result["sources"]) == 1

    @pytest.mark.asyncio
    async def test_chapter_fails_review_then_rewrites(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer):
        ch1 = make_chapter()
        ch1_rewritten = make_chapter(content="重写后内容")
        mock_writer.write.return_value = ch1
        mock_writer.rewrite.return_value = ch1_rewritten
        mock_reviewer.review.side_effect = [
            ChapterReviewOutput(
                passed=False, score=40,
                issues=[ChapterIssue(category="logic", severity="HIGH", location="p:1", description="逻辑问题", suggestion="补充推理")],
            ),
            make_review_pass(),
        ]
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(1),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        assert len(result["sections"]) == 1

    @pytest.mark.asyncio
    async def test_multiple_chapters(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer):
        ch1 = make_chapter("ch1", "市场规模")
        ch2 = make_chapter("ch2", "竞争格局", "竞争格局分析")
        mock_writer.write.side_effect = [ch1, ch2]
        mock_reviewer.review.return_value = make_review_pass()
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(2),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        assert len(result["sections"]) == 2


class TestReportOrchestratorExtractChapterData:
    def test_extract_from_provenance(self, orchestrator):
        agg = MockAggregationResult()
        agg.content_provenance = {"key1": {"section_target": "ch1"}}
        agg.layered_content = {"analysis": {"key1": {"data": "内容"}}}
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "ch1", [])
        assert chapter_data == {"data": "内容"}
        assert raw_summary == ""

    def test_extract_from_layered_content_fallback(self, orchestrator):
        agg = MockAggregationResult()
        agg.content_provenance = {}
        agg.layered_content = {"analysis": {"ch1_market": {"data": "市场规模"}}}
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "ch1", [])
        assert chapter_data == {"data": "市场规模"}

    def test_extract_returns_empty_when_not_found(self, orchestrator):
        agg = MockAggregationResult()
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "ch99", [])
        assert chapter_data == {}
        assert raw_summary == ""


class TestReportOrchestratorExtractValidateDataPoints:
    def test_does_not_promote_unbound_content_numbers(self, orchestrator):
        ch = ChapterWriteOutput(chapter_id="ch1", title="测试", content="市场规模达到2000亿元，增速15%")
        dps = orchestrator._extract_and_validate_data_points(ch)
        assert dps == []

    def test_does_not_promote_unbound_english_numbers(self, orchestrator):
        ch = ChapterWriteOutput(chapter_id="ch1", title="测试", content="Revenue reached 5.2 billion USD")
        dps = orchestrator._extract_and_validate_data_points(ch)
        assert dps == []

    def test_no_duplicate_extraction(self, orchestrator):
        dp = DataPoint(metric="市场规模", value="2000", unit="亿元", source="iimedia.cn")
        ch = ChapterWriteOutput(
            chapter_id="ch1", title="测试", content="市场规模达2000亿元",
            data_points_used=[dp],
        )
        dps = orchestrator._extract_and_validate_data_points(ch)
        metric_2000_count = sum(1 for d in dps if d.value == "2000" and d.unit == "亿元")
        assert metric_2000_count == 1


class TestReportOrchestratorPrecedingSummary:
    def test_append_and_truncate(self, orchestrator):
        orchestrator._MAX_PRECEDING_SUMMARY_LENGTH = 50
        ch1 = make_chapter()
        ch1.key_conclusions = ["A" * 30]
        result = orchestrator._append_preceding_summary("", ch1)
        assert len(result) <= 50

    def test_rebuild(self, orchestrator):
        chapters = [make_chapter(), make_chapter("ch2", "竞争格局")]
        summary = orchestrator._rebuild_preceding_summary(chapters)
        assert "市场规模" in summary
        assert "竞争格局" in summary


class TestReportOrchestratorAssembleFinalReport:
    def test_assemble_with_sources(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        sources = [{"title": "来源1", "url": "https://a.com"}]
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题", sources)
        assert result["sources"][0]["title"] == "来源1"
        assert result["sources"][0]["url"] == "https://a.com"
        assert result["sources"][0]["evidence_id"].startswith("ev_")
        assert result["sources"][0]["provenance_id"].startswith("prov_")

    def test_assemble_without_sources(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题")
        assert result["sources"] == []

    def test_assemble_sections_have_data_points(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题")
        assert len(result["sections"][0]["data_points"]) == 1


class TestReportOrchestratorCheckpoint:
    @pytest.mark.asyncio
    async def test_checkpoint_and_restore(self, orchestrator, tmp_path):
        with patch.object(orchestrator, '_checkpoint_chapter'):
            pass

        checkpoint_dir = tmp_path / "data" / "test_task" / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        ch = make_chapter()
        chapter_data = {
            "chapter_id": ch.chapter_id,
            "title": ch.title,
            "content": ch.content,
            "data_points_used": [asdict(dp) for dp in ch.data_points_used],
            "key_conclusions": ch.key_conclusions,
            "self_check_passed": ch.self_check_passed,
            "self_check_issues": ch.self_check_issues,
            "data_registry_snapshot": DataRegistry().to_snapshot(),
            "timestamp": "2026-06-26T00:00:00",
        }
        (checkpoint_dir / "chapter_ch1.json").write_text(
            json.dumps(chapter_data, ensure_ascii=False), encoding="utf-8"
        )

        with patch('src.agents.fixed_agents.report_upgrade.orchestrator.Path') as mock_path_cls:
            mock_path_cls.return_value = tmp_path / "data"
            restored = await orchestrator._restore_from_checkpoint("test_task")

        assert restored is not None
        chapters, snapshot = restored
        assert len(chapters) == 1
        assert chapters[0].chapter_id == "ch1"


class TestReportOrchestratorVerifyDownstreamConsistency:
    def test_warns_on_inconsistent_value(self, orchestrator, caplog):
        patched_ch = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="市场规模达2000亿元",
            data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="A")],
        )
        other_ch = ChapterWriteOutput(
            chapter_id="ch2", title="概述", content="市场规模约1800亿元",
        )
        import logging
        with caplog.at_level(logging.WARNING):
            result = orchestrator._verify_downstream_consistency([patched_ch, other_ch], {"ch1"})
        assert result["blocking"] is True
        assert result["stale_chapter_ids"] == ["ch2"]
        assert len(caplog.records) == 1

    def test_no_warning_when_consistent(self, orchestrator, caplog):
        patched_ch = ChapterWriteOutput(
            chapter_id="ch1", title="市场规模", content="市场规模达2000亿元",
            data_points_used=[DataPoint(metric="市场规模", value="2000", unit="亿元", source="A")],
        )
        other_ch = ChapterWriteOutput(
            chapter_id="ch2", title="概述", content="市场增速15%",
        )
        import logging
        with caplog.at_level(logging.WARNING):
            result = orchestrator._verify_downstream_consistency([patched_ch, other_ch], {"ch1"})
        assert result["blocking"] is False
        assert result["stale_chapter_ids"] == []
        assert len(caplog.records) == 0


class TestReportOrchestratorUnderstandFramework:
    def test_produces_narrative_context(self, orchestrator):
        ts = make_task_structure(2)
        fc = {"name": "行业研究"}
        result = orchestrator._understand_framework(ts, fc)
        assert "新能源汽车" in result
        assert "章节1" in result
        assert "章节2" in result


class TestReportOrchestratorExtractMetric:
    def test_extracts_from_brackets(self, orchestrator):
        assert orchestrator._extract_metric("「市场规模」数据缺失") == "市场规模"

    def test_fallback_to_prefix(self, orchestrator):
        result = orchestrator._extract_metric("数据缺失无引号")
        assert len(result) <= 20


class TestIsVagueSource:
    def test_empty_is_vague(self):
        assert _is_vague_source("") is True
        assert _is_vague_source("   ") is True

    def test_vague_patterns(self):
        assert _is_vague_source("行业综合数据") is True
        assert _is_vague_source("综合数据") is True
        assert _is_vague_source("公开数据") is True
        assert _is_vague_source("市场数据") is True
        assert _is_vague_source("研究报告") is True

    def test_specific_source_not_vague(self):
        assert _is_vague_source("iimedia.cn") is False
        assert _is_vague_source("中国汽车工业协会") is False
        assert _is_vague_source("乘联会") is False

    def test_list_source_is_normalized_without_crashing(self):
        grounded = ReportOrchestrator._ground_data_point_sources(
            [{"metric": "市场规模", "value": "100", "source": ["来源A", "来源B"]}],
            [{"title": "来源A", "url": "https://example.test/a"}],
            chapter_id="ch1",
        )

        assert grounded[0]["chapter_id"] == "ch1"
        assert isinstance(grounded[0]["source"], str)


class TestCleanKeyFindings:
    def test_strips_markdown(self, orchestrator):
        raw = "# 执行摘要\n\n**核心发现一：** 内容\n\n**核心发现二：** 内容2"
        result = orchestrator._clean_key_findings(raw)
        assert all(not line.startswith("#") for line in result)
        assert all("**" not in line for line in result)

    def test_removes_empty_lines(self, orchestrator):
        raw = "第一行\n\n第二行\n\n第三行"
        result = orchestrator._clean_key_findings(raw)
        assert "" not in result

    def test_max_10_lines(self, orchestrator):
        raw = "\n".join(f"第{i}行" for i in range(20))
        result = orchestrator._clean_key_findings(raw)
        assert len(result) <= 10


class TestGroundDataPointSources:
    def test_vague_source_is_not_replaced_by_unrelated_source(self, orchestrator):
        dps = [{"metric": "销量", "value": "1200", "unit": "万辆", "source": "行业综合数据"}]
        sources = [{"title": "中国汽车工业协会", "url": "https://caam.org.cn", "type": "web"}]
        result = orchestrator._ground_data_point_sources(dps, sources)
        assert result[0]["source"] == ""
        assert result[0]["source_url"] == ""
        assert result[0]["evidence_status"] == "unverified"

    def test_specific_source_kept(self, orchestrator):
        dps = [{"metric": "销量", "value": "1200", "unit": "万辆", "source": "iimedia.cn"}]
        sources = [{"title": "中国汽车工业协会", "url": "https://caam.org.cn", "type": "web"}]
        result = orchestrator._ground_data_point_sources(dps, sources)
        assert result[0]["source"] == "iimedia.cn"

    def test_no_sources_available(self, orchestrator):
        dps = [{"metric": "销量", "value": "1200", "unit": "万辆", "source": "行业综合数据"}]
        result = orchestrator._ground_data_point_sources(dps, [])
        assert result[0]["source"] == ""
        assert result[0]["evidence_status"] == "unverified"


class TestAssembleFinalReportP3P5:
    def test_chapter_sources_populated(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        sources = [{"title": "来源1", "url": "https://a.com", "type": "web"}]
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题", sources)
        assert len(result["sections"][0]["sources"]) == 1
        assert result["sections"][0]["sources"][0]["title"] == "来源1"

    def test_chapter_sources_empty_when_no_original(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        result = orchestrator._assemble_final_report(chapters, "摘要", review, "主题")
        assert result["sections"][0]["sources"] == []

    def test_key_findings_cleaned(self, orchestrator):
        chapters = [make_chapter()]
        review = make_global_review()
        raw_summary = "# 执行摘要\n\n**核心发现一：** 测试\n\n**核心发现二：** 测试2"
        result = orchestrator._assemble_final_report(chapters, raw_summary, review, "主题")
        assert all("**" not in f for f in result["key_findings"])
        assert all(not f.startswith("#") for f in result["key_findings"])

    def test_vague_data_point_source_grounded(self, orchestrator):
        ch = ChapterWriteOutput(
            chapter_id="ch1", title="测试", content="销量1200万辆",
            data_points_used=[DataPoint(metric="销量", value="1200", unit="万辆", source="行业综合数据")],
            key_conclusions=["销量1200万"],
        )
        sources = [{"title": "乘联会", "url": "https://cpcaauto.com", "type": "web"}]
        result = orchestrator._assemble_final_report([ch], "摘要", make_global_review(), "主题", sources)
        assert result["sections"][0]["data_points"][0]["source"] == ""
        assert result["sections"][0]["data_points"][0]["evidence_status"] == "unverified"


class TestAuditFixesB1toB8:
    def test_extract_raw_summary_body_is_dict(self, orchestrator):
        meta = {"data_points": [{"title": "测试", "content": {"key": "val"}}]}
        result = ReportOrchestrator._extract_raw_summary(meta)
        assert "key" in result

    def test_extract_raw_summary_body_is_list(self, orchestrator):
        meta = {"data_points": [{"title": "测试", "content": [1, 2, 3]}]}
        result = ReportOrchestrator._extract_raw_summary(meta)
        assert "1" in result

    def test_verify_downstream_consistency_float_value(self, orchestrator):
        patched = ChapterWriteOutput(
            chapter_id="ch1", title="测试", content="营收1502.25亿元",
            data_points_used=[DataPoint(metric="营收", value=1502.25, unit="亿元", source="财报")],
        )
        other = ChapterWriteOutput(
            chapter_id="ch2", title="其他", content="营收1502.25亿元",
        )
        ReportOrchestrator._verify_downstream_consistency([patched, other], {"ch1"})

    def test_assemble_final_report_sources_with_href(self, orchestrator):
        ch = ChapterWriteOutput(
            chapter_id="ch1", title="测试", content="测试",
            data_points_used=[DataPoint(metric="测试", value="1", unit="个", source="行业综合数据")],
        )
        sources = [{"title": "来源", "href": "https://a.com", "type": "web"}]
        result = orchestrator._assemble_final_report([ch], "摘要", make_global_review(), "主题", sources)
        assert result["sections"][0]["sources"][0]["url"] == "https://a.com"

    def test_ground_data_point_sources_with_href(self, orchestrator):
        dps = [{"metric": "测试", "value": "1", "unit": "个", "source": "行业综合数据"}]
        sources = [{"title": "来源", "href": "https://a.com"}]
        result = ReportOrchestrator._ground_data_point_sources(dps, sources)
        assert result[0]["source"] == ""
        assert result[0]["source_url"] == ""
        assert result[0]["evidence_status"] == "unverified"

    def test_extract_chapter_data_tracks_matched_key(self, orchestrator):
        agg = MagicMock()
        agg.layered_content = {"analysis": {
            "phase_2_agent_0": "精炼内容",
            "phase_2_agent_0__meta": {"data_points": [{"title": "测试", "content": "原始数据"}]},
        }}
        agg.content_provenance = {"phase_2_agent_0": MagicMock(section_target="核心财务指标")}
        chapter_data, raw_summary = orchestrator._extract_chapter_data(agg, "核心财务指标", [])
        assert chapter_data == {"content": "精炼内容"}
        assert "测试" in raw_summary

    def test_split_chapter_data_str_with_meta(self, orchestrator):
        lc = {"analysis": {
            "agent_0": "内容文本",
            "agent_0__meta": {"data_points": [{"title": "DP1", "content": "数据"}]},
        }}
        refined, raw_summary = ReportOrchestrator._split_chapter_data("内容文本", "agent_0", lc)
        assert refined == {"content": "内容文本"}
        assert "DP1" in raw_summary


class TestBuildAnchorPatchInstructions:
    def test_fabricated_data_instruction(self, orchestrator):
        issues = [ChapterIssue(
            category="data_anchoring", severity="CRITICAL",
            location="p:2", description="编造数据：营收5000亿",
            suggestion="删除该数值",
        )]
        result = ReportOrchestrator._build_anchor_patch_instructions(issues, {})
        assert len(result) == 1
        assert "删除" in result[0]

    def test_vague_source_instruction(self, orchestrator):
        issues = [ChapterIssue(
            category="data_anchoring", severity="HIGH",
            location="p:3", description="模糊来源：据行业分析",
            suggestion="替换为具体来源",
        )]
        result = ReportOrchestrator._build_anchor_patch_instructions(issues, {})
        assert len(result) == 1
        assert "补充具体来源" in result[0]

    def test_data_gap_instruction(self, orchestrator):
        issues = [ChapterIssue(
            category="data_anchoring", severity="HIGH",
            location="p:4", description="未标注数据缺口",
            suggestion="标注数据缺口",
        )]
        result = ReportOrchestrator._build_anchor_patch_instructions(issues, {})
        assert len(result) == 1
        assert "标注数据缺口" in result[0]

    def test_multiple_issues(self, orchestrator):
        issues = [
            ChapterIssue(category="data_anchoring", severity="CRITICAL", location="p:1", description="编造数据", suggestion=""),
            ChapterIssue(category="data_anchoring", severity="HIGH", location="p:2", description="模糊来源", suggestion=""),
        ]
        result = ReportOrchestrator._build_anchor_patch_instructions(issues, {})
        assert len(result) == 2

    def test_empty_issues(self, orchestrator):
        result = ReportOrchestrator._build_anchor_patch_instructions([], {})
        assert result == []


class TestReviewPatchSeparation:
    @pytest.mark.asyncio
    async def test_anchor_issues_trigger_patch_not_rewrite(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer):
        ch1 = make_chapter()
        ch1_patched = make_chapter(content="修补后内容")
        mock_writer.write.return_value = ch1
        mock_writer.patch_data.return_value = ch1_patched
        mock_reviewer.review.side_effect = [
            ChapterReviewOutput(
                passed=False, score=40,
                issues=[ChapterIssue(category="data_anchoring", severity="CRITICAL", location="p:1", description="编造数据", suggestion="删除")],
            ),
            make_review_pass(),
        ]
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(1),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        mock_writer.patch_data.assert_called_once()
        mock_writer.rewrite.assert_not_called()

    @pytest.mark.asyncio
    async def test_logic_issues_trigger_rewrite(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer):
        ch1 = make_chapter()
        ch1_rewritten = make_chapter(content="重写后内容")
        mock_writer.write.return_value = ch1
        mock_writer.rewrite.return_value = ch1_rewritten
        mock_reviewer.review.side_effect = [
            ChapterReviewOutput(
                passed=False, score=40,
                issues=[ChapterIssue(category="logic", severity="CRITICAL", location="p:1", description="逻辑跳跃", suggestion="补充推理")],
            ),
            make_review_pass(),
        ]
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(1),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        mock_writer.rewrite.assert_called_once()

    @pytest.mark.asyncio
    async def test_patch_score_drop_keeps_original(self, orchestrator, mock_writer, mock_reviewer, mock_global_reviewer):
        # I1 组装口终检以 min_length=37 把关：夹具正文需达到该下限，才能
        # 验证"补丁评分下滑时保留原文（而非补丁内容）"这一真实契约。
        # 正文不含裸数字，避免 L3 unbound_numeric_claim 触发 defense 重写
        # 路径（那会覆盖掉本测要验证的质量环回退行为）。
        original_content = "市场规模持续扩大，增长动能稳步增强，渗透率不断提升，竞争格局逐步优化，头部集中度进一步巩固。"
        ch1 = make_chapter(content=original_content)
        ch1_patched = make_chapter(content="修补后内容")
        mock_writer.write.return_value = ch1
        mock_writer.patch_data.return_value = ch1_patched
        mock_reviewer.review.side_effect = [
            ChapterReviewOutput(
                passed=False, score=50,
                issues=[ChapterIssue(category="data_anchoring", severity="CRITICAL", location="p:1", description="编造数据", suggestion="删除")],
            ),
            ChapterReviewOutput(passed=False, score=30, issues=[]),
            make_review_pass(),
        ]
        mock_global_reviewer.review.return_value = make_global_review()
        mock_global_reviewer.verify_issues.return_value = []

        result = await orchestrator.generate_report(
            task_structure=make_task_structure(1),
            framework_config={"name": "行业研究"},
            aggregated_result=MockAggregationResult(),
            topic="新能源汽车",
        )
        assert result["sections"][0]["content"] == original_content


class TestBaseContentExtraction:
    def test_base_content_from_chapter_data(self, orchestrator):
        agg = MockAggregationResult()
        agg.content_provenance = {"key1": {"section_target": "ch1"}}
        agg.layered_content = {"analysis": {"key1": {"content": "分析Agent的专业输出"}}}
        chapter_data, _ = orchestrator._extract_chapter_data(agg, "ch1", [])
        assert chapter_data.get("content") == "分析Agent的专业输出"

    def test_base_content_from_string_data(self, orchestrator):
        agg = MockAggregationResult()
        agg.content_provenance = {"key1": {"section_target": "ch1"}}
        agg.layered_content = {"analysis": {"key1": "分析Agent的字符串输出"}}
        chapter_data, _ = orchestrator._extract_chapter_data(agg, "ch1", [])
        assert chapter_data.get("content") == "分析Agent的字符串输出"


class TestSourceEvidenceIdentity:
    def test_legacy_sources_receive_stable_evidence_and_provenance_ids(self):
        sources = [{
            "title": "Legacy source",
            "url": "https://example.test/report",
            "snippet": "A cited excerpt",
        }]
        first = ReportOrchestrator._ensure_source_evidence_identity(sources, task_id="task-1")
        second = ReportOrchestrator._ensure_source_evidence_identity(sources, task_id="task-1")
        assert first[0]["evidence_id"].startswith("ev_")
        assert first[0]["provenance_id"].startswith("prov_")
        assert first[0]["evidence_id"] == second[0]["evidence_id"]
        assert first[0]["provenance_id"] == second[0]["provenance_id"]

    def test_existing_ids_are_preserved_and_data_point_can_be_grounded(self):
        source = {
            "title": "Known source",
            "url": "https://example.test/known",
            "evidence_id": "ev_existing",
            "provenance_id": "prov_existing",
        }
        normalized = ReportOrchestrator._ensure_source_evidence_identity([source], task_id="task-1")
        assert normalized[0]["evidence_id"] == "ev_existing"
        assert normalized[0]["provenance_id"] == "prov_existing"
        point = [{"metric": "m", "value": "1", "source_url": source["url"]}]
        grounded = ReportOrchestrator._ground_data_point_sources(point, normalized)
        assert grounded[0]["evidence_id"] == "ev_existing"
        assert grounded[0]["provenance_id"] == "prov_existing"


class TestFlattenSectionDataPoints:
    """F1: top-level data_points must be the report's quantitative spine.

    ses_92c64980: the persisted top-level field held research-phase evidence
    husks (title/content/url; metric and value both None) because the final
    report dict carried no top-level data_points at all.
    """

    def test_flattens_section_data_points_in_order(self):
        sections = [
            {"data_points": [{"metric": "市场规模", "value": "3759.3亿美元", "source_url": "u1"}]},
            {"data_points": [{"metric": "下载量", "value": "100亿次", "source_url": "u2"}]},
        ]
        flat = ReportOrchestrator._flatten_section_data_points(sections)
        assert [dp["metric"] for dp in flat] == ["市场规模", "下载量"]

    def test_skips_evidence_husks(self):
        sections = [{
            "data_points": [
                {"title": "搜索证据", "content": "正文片段", "url": "https://x.test/a"},
                {"metric": "规模", "value": "1.2万亿", "source": "新华社"},
            ],
        }]
        flat = ReportOrchestrator._flatten_section_data_points(sections)
        assert len(flat) == 1
        assert flat[0]["metric"] == "规模"

    def test_dedupes_by_identity(self):
        dp = {"metric": "CAGR", "value": "26.60%", "source_url": "u1"}
        sections = [{"data_points": [dict(dp), dict(dp)]}]
        assert len(ReportOrchestrator._flatten_section_data_points(sections)) == 1

    def test_tolerates_malformed_entries(self):
        sections = [{"data_points": [None, "junk", {"metric": "m", "value": "v"}]}, None, {}]
        assert ReportOrchestrator._flatten_section_data_points(sections) == [{"metric": "m", "value": "v"}]

    def test_empty_sections_yield_empty_list(self):
        assert ReportOrchestrator._flatten_section_data_points([]) == []
        assert ReportOrchestrator._flatten_section_data_points(None) == []


class TestDeepSectionEvidence:
    def _orchestrator(self, deep_mode_service):
        from src.agents.fixed_agents.report_upgrade.orchestrator import ReportOrchestrator

        orchestrator = ReportOrchestrator.__new__(ReportOrchestrator)
        orchestrator._deep_mode_service = deep_mode_service
        return orchestrator

    def test_reads_service_and_folds_leaf_id(self):
        class _FakeDeepService:
            def get_section_evidence(self, section_id):
                if section_id == "section_5":
                    return {"tables": "| 公司 | 市场份额 |", "gap_notes": []}
                return {"tables": "", "gap_notes": []}

        orchestrator = self._orchestrator(_FakeDeepService())

        evidence = orchestrator._deep_section_evidence(
            {"section_id": "section_5::sub_5_0", "parent_section_id": ""}
        )
        assert evidence == {"tables": "| 公司 | 市场份额 |", "gap_notes": []}

    def test_empty_evidence_returns_empty_dict(self):
        class _EmptyDeepService:
            def get_section_evidence(self, section_id):
                return {"tables": "", "gap_notes": []}

        orchestrator = self._orchestrator(_EmptyDeepService())

        assert orchestrator._deep_section_evidence(
            {"section_id": "section_6::sub_6_0", "parent_section_id": ""}
        ) == {}

    def test_missing_service_returns_empty_dict(self):
        orchestrator = self._orchestrator(None)

        assert orchestrator._deep_section_evidence({"section_id": "section_5"}) == {}
