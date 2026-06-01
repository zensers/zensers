from __future__ import annotations
from dataclasses import dataclass, field

from .base import AtomicRevision
from ..revision_types import (
    RevisionOpType, ExecContext, ValidationResult,
    PreviewDiff, ExecutionResult, RollbackResult,
)


@dataclass
class AddElementOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.ADD_ELEMENT)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        ids = self._target_ids(ctx)
        return ValidationResult(valid=len(ids) > 0)

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        return PreviewDiff()

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        ids = self._target_ids(ctx)
        if not ids:
            return ExecutionResult(success=False, error="Target section not found")
        node = ctx.report_tree.find(ids[0])
        if not node:
            return ExecutionResult(success=False, error="Target section not found")

        new_content = self.action.content or ""
        if not new_content.strip():
            return ExecutionResult(success=False, error="No content to add")

        existing = getattr(node.section, "content", "")
        if existing:
            node.section.content = existing.rstrip() + "\n\n" + new_content + "\n"
        else:
            node.section.content = new_content + "\n"
        return ExecutionResult(success=True)

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        if ctx.snapshot_id:
            await ctx.snapshot_manager.restore_nodes(ctx.snapshot_id, [])
        return RollbackResult(success=True)
