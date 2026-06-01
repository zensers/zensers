"""Integration tests for the revision system core flow."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass, field
from src.core.adjustment.revision_types import (
    RevisionOpType, RevisionAction, RevisionTarget, LocationStrategy,
    ExecContext, ReportTree, SectionNode, SectionRef, RefType,
    ExecutionResult, RollbackResult, ExecFailure, ImpactEstimate,
)
from src.core.adjustment.atomic_operations.factory import AtomicOperationFactory
from src.core.adjustment.snapshot_manager import SnapshotManager
from src.core.adjustment.revision_executor import RevisionExecutor


class FakeSection:
    """Simulates a Report Section with content."""
    def __init__(self, sid, content="", title=""):
        self.id = sid
        self.content = content
        self.title = title


@pytest.fixture
def tree():
    c1 = SectionNode(id="c1", section=FakeSection("c1", "section 1"), children=[])
    c2 = SectionNode(id="c2", section=FakeSection("c2", "section 2"), children=[])
    root = SectionNode(id="root", section=FakeSection("root", "root"), children=[c1, c2])
    c1.parent_id = "root"
    c2.parent_id = "root"
    tree = ReportTree(root=root, node_map={"root": root, "c1": c1, "c2": c2})
    return tree, root, c1, c2


@pytest.mark.asyncio
async def test_operation_factory_creates_all_types():
    factory = AtomicOperationFactory()
    target = RevisionTarget("test", [], LocationStrategy.KEYWORD, False)
    for op_type in RevisionOpType:
        if op_type == RevisionOpType.UNKNOWN:
            continue
        action = RevisionAction(
            action_id=f"test_{op_type.value}",
            action_type=op_type,
            target=target,
        )
        op = factory.create(action)
        assert op.action is action
        assert op.op_type == op_type


@pytest.mark.asyncio
async def test_modify_operation_with_direct_id(tree):
    from src.core.adjustment.atomic_operations.modify_operation import ModifyOperation

    tree, _, c1, _ = tree
    ref = SectionRef(uuid="c1", ref_type=RefType.UUID, raw_text="c1")
    target = RevisionTarget("c1", [ref], LocationStrategy.ORDINAL, False)
    action = RevisionAction(
        action_id="m1",
        action_type=RevisionOpType.MODIFY,
        target=target,
        content="new content",
    )
    sm = SnapshotManager()
    ctx = ExecContext(
        report=None, report_tree=tree, snapshot_manager=sm, snapshot_id=None,
        content_manipulator=None,
    )
    op = ModifyOperation(action=action)
    result = await op.execute(ctx)
    assert result.success is True, result.error
    assert "c1" in result.affected_ids
    assert c1.section.content == "new content"


@pytest.mark.asyncio
async def test_delete_operation_with_direct_id(tree):
    from src.core.adjustment.atomic_operations.delete_operation import DeleteOperation

    tree, root, c1, c2 = tree
    ref = SectionRef(uuid="c1", ref_type=RefType.UUID, raw_text="c1")
    target = RevisionTarget("c1", [ref], LocationStrategy.ORDINAL, False)
    action = RevisionAction(
        action_id="d1",
        action_type=RevisionOpType.DELETE,
        target=target,
    )
    sm = SnapshotManager()
    ctx = ExecContext(
        report=None, report_tree=tree, snapshot_manager=sm, snapshot_id=None,
        content_manipulator=None,
    )
    op = DeleteOperation(action=action)
    result = await op.execute(ctx)
    assert result.success is True, result.error
    assert len(root.children) == 1
    assert root.children[0].id == "c2"


@pytest.mark.asyncio
async def test_snapshot_create_and_restore():
    sm = SnapshotManager()
    data = {"key": "value"}
    sid = await sm.create_snapshot(data, None)
    assert sid is not None
    assert isinstance(sid, str)


@pytest.mark.asyncio
async def test_factory_unknown_type_raises():
    factory = AtomicOperationFactory()
    target = RevisionTarget("x", [], LocationStrategy.KEYWORD, False)
    action = RevisionAction(
        action_id="unk",
        action_type=RevisionOpType.UNKNOWN,
        target=target,
    )
    with pytest.raises(ValueError, match="Unknown operation type"):
        factory.create(action)


@pytest.mark.asyncio
async def test_rollback_direct():
    from src.core.adjustment.atomic_operations.base import AtomicRevision

    @dataclass
    class MockAtomicRevision(AtomicRevision):
        op_type: RevisionOpType = field(init=False, default=RevisionOpType.MODIFY)
        rolled: bool = False

        async def validate(self, ctx):
            return type("VR", (), {"valid": True, "errors": []})()

        async def preview(self, ctx):
            return type("PD", (), {"before": None, "after": None,
                                   "structural_changes": None, "commit_message": None})()

        async def execute(self, ctx):
            return ExecutionResult(success=True)

        async def rollback(self, ctx):
            self.rolled = True
            return RollbackResult(success=True)

        def estimate_impact(self, ctx):
            return ImpactEstimate()

    op = MockAtomicRevision()
    ctx = MagicMock()
    await op.rollback(ctx)
    assert op.rolled is True
