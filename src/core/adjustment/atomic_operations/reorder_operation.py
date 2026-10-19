from __future__ import annotations
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from .base import AtomicRevision
from ..revision_types import (
    RevisionOpType,
    ExecContext,
    ValidationResult,
    PreviewDiff,
    ExecutionResult,
    RollbackResult,
)


@dataclass
class ReorderOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.REORDER)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        ids = self._target_ids(ctx)
        if not ids:
            return ValidationResult(valid=False, errors=["Target section not found"])
        node = ctx.report_tree.find(ids[0])
        if not node or not node.parent_id:
            return ValidationResult(valid=False, errors=["Section has no parent"])
        parent = ctx.report_tree.node_map.get(node.parent_id)
        if not parent:
            return ValidationResult(valid=False, errors=["Parent node not found"])
        raw_index = self.action.parameters.get("new_index")
        try:
            new_index = int(raw_index) if raw_index is not None else None
        except (TypeError, ValueError):
            new_index = None
        if new_index is not None and 0 <= new_index < len(parent.children):
            return ValidationResult(valid=True)
        position = self.action.parameters.get("position")
        if position in ("first", "last"):
            return ValidationResult(valid=True)
        return ValidationResult(valid=False, errors=["Invalid target position"])

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        ids = self._target_ids(ctx)
        return PreviewDiff(
            before={"target_ids": ids},
            commit_message=f"REORDER: {self.action.target.raw_text}",
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        ids = self._target_ids(ctx)
        if not ids:
            return ExecutionResult(success=False, error="Target section not found")
        node = ctx.report_tree.find(ids[0])
        if not node or not node.parent_id:
            return ExecutionResult(success=False, error="Section has no parent")
        parent = ctx.report_tree.node_map.get(node.parent_id)
        if not parent:
            return ExecutionResult(success=False, error="Parent node not found")

        parent.children = [c for c in parent.children if c.id != node.id]

        raw_index = self.action.parameters.get("new_index")
        try:
            new_index = int(raw_index) if raw_index is not None else None
        except (TypeError, ValueError):
            new_index = None
        position = self.action.parameters.get("position")
        if new_index is not None and 0 <= new_index <= len(parent.children):
            parent.children.insert(new_index, node)
        elif position == "first":
            parent.children.insert(0, node)
        else:
            if new_index is not None:
                logger.warning("Invalid target index for REORDER, defaulting to 'last'")
            parent.children.append(node)
        return ExecutionResult(
            success=True,
            affected_ids=[node.id, parent.id],
        )

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        if ctx.snapshot_id:
            resolved = self._target_ids(ctx)
            await ctx.snapshot_manager.restore_nodes(ctx.snapshot_id, resolved)
        return RollbackResult(success=True)
