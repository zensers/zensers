"""Tests for revision type definitions."""
import pytest
from datetime import datetime
from uuid import UUID
from src.core.adjustment.revision_types import (
    ExecutionStatus, Choice, MergeStrategy, CommitStatus,
    RevisionOpType, RefType, ConflictType, LocationStrategy,
    SnapshotType, RevisionAction, RevisionTarget, SectionRef,
    SectionNode, ReportTree, AnalysisResult, RevisionPlan,
    ExecutionFlow, PreviewDiff, RevisionCommit, RevisionSession,
    Conflict, PlanConflictError, RevisionAbortedException,
    SnapshotId, StructuralImpact, ExecutionResult,
    RollbackResult, PlanExecutionResult
)


class TestEnums:
    def test_execution_status_values(self):
        assert ExecutionStatus.PREVIEW_READY.value == "preview_ready"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert len(ExecutionStatus) == 8

    def test_revision_op_type_values(self):
        assert RevisionOpType.MODIFY.value == "modify"
        assert RevisionOpType.UNKNOWN.value == "unknown"
        assert len(RevisionOpType) == 12

    def test_choice_default_abort(self):
        assert Choice.ABORT.value == "abort"
        assert Choice.ACCEPT.value == "accept"


class TestDataclasses:
    def test_revision_action_creation(self):
        target = RevisionTarget(
            raw_text="第三段",
            section_refs=[],
            location_strategy=LocationStrategy.KEYWORD,
            is_ambiguous=False,
        )
        action = RevisionAction(
            action_id="test_id",
            action_type=RevisionOpType.MODIFY,
            target=target,
        )
        assert action.action_id == "test_id"
        assert action.action_type == RevisionOpType.MODIFY
        assert action.target.raw_text == "第三段"

    def test_report_tree_find(self):
        node = SectionNode(id="sec_1", section="section_obj")
        tree = ReportTree(root=node, node_map={"sec_1": node})
        assert tree.find("sec_1") is node
        assert tree.find("nonexistent") is None

    def test_report_tree_find_by_index(self):
        child = SectionNode(id="child_1", section="child")
        parent = SectionNode(id="parent", section="parent", children=[child])
        tree = ReportTree(node_map={"parent": parent, "child_1": child})
        found = tree.find_by_index("parent", 0)
        assert found is child
        assert tree.find_by_index("parent", 99) is None
        assert tree.find_by_index("nonexistent", 0) is None

    def test_report_tree_collect_sections(self):
        c1 = SectionNode(id="c1", section="sec1")
        c2 = SectionNode(id="c2", section="sec2")
        parent = SectionNode(id="p", section="parent", children=[c1, c2])
        tree = ReportTree(root=parent, node_map={"p": parent, "c1": c1, "c2": c2})
        collected = []
        tree._collect_sections(tree.root, collected)
        assert collected == ["parent", "sec1", "sec2"]

    def test_execution_flow_default_failed(self):
        flow = ExecutionFlow()
        assert flow.status == ExecutionStatus.FAILED

    def test_plan_conflict_error(self):
        err = PlanConflictError("conflict")
        assert str(err) == "conflict"
        assert err.conflicts == []

    def test_revision_session_creates_uuid(self):
        session = RevisionSession(user_message="test")
        UUID(hex=session.session_id)
        assert session.user_message == "test"

    def test_snapshot_id_type(self):
        sid: SnapshotId = "abc123"
        assert isinstance(sid, str)

    def test_structural_impact_renumbering_default(self):
        impact = StructuralImpact(
            affected_sections=["s1"],
            toc_changes=[],
            cross_refs_broken=[],
            data_refs_affected=[],
        )
        assert impact.renumbering_required is False

    def test_conflict_creation(self):
        c = Conflict(
            type=ConflictType.CIRCULAR_DEPENDENCY,
            description="A depends on B, B depends on A",
            involved_action_ids=["a1", "b1"],
        )
        assert c.type == ConflictType.CIRCULAR_DEPENDENCY

    def test_revision_plan_creation(self):
        plan = RevisionPlan(
            plan_id="p1",
            actions=[],
            dependency_graph={},
            id_remap_table={},
        )
        assert plan.snapshot_required is True
        assert plan.conflicts == []
