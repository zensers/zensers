from __future__ import annotations
from dataclasses import dataclass, field

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
class ModifyOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.MODIFY)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        ids = self._target_ids(ctx)
        return ValidationResult(valid=len(ids) > 0)

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        ids = self._target_ids(ctx)
        if not ids:
            return PreviewDiff()
        node = ctx.report_tree.find(ids[0])
        return PreviewDiff(
            before=node.section.content if node else None,
            after=self.action.content,
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        ids = self._target_ids(ctx)
        if not ids:
            return ExecutionResult(success=False, error="Target section not found")
        node = ctx.report_tree.find(ids[0])
        if not node:
            return ExecutionResult(success=False, error="Target section not found")
        old_content = node.section.content
        node.section.content = self.action.content or ""
        return ExecutionResult(
            success=True,
            affected_ids=[node.id],
            diff=PreviewDiff(before=old_content, after=node.section.content),
        )

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        ids = self._target_ids(ctx)
        if ctx.snapshot_id and ids:
            await ctx.snapshot_manager.restore_nodes(ctx.snapshot_id, ids)
        return RollbackResult(success=True)
