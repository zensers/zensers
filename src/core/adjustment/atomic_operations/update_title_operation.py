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
class UpdateTitleOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.UPDATE_TITLE)
    _old_title: str = field(default="", init=False, repr=False)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        return ValidationResult(valid=bool(self.action.content))

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        if ctx.report_tree.root and ctx.report_tree.root.section:
            old_title = getattr(ctx.report_tree.root.section, "title", "")
        else:
            old_title = ""
        return PreviewDiff(
            before=old_title,
            after=self.action.content,
            commit_message=f"UPDATE_TITLE: {old_title} -> {self.action.content}",
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        if ctx.report_tree.root and ctx.report_tree.root.section:
            self._old_title = getattr(ctx.report_tree.root.section, "title", "")
            ctx.report_tree.root.section.title = self.action.content or ""
            return ExecutionResult(
                success=True,
                affected_ids=[ctx.report_tree.root.id],
                diff=PreviewDiff(before=self._old_title, after=self.action.content),
            )
        return ExecutionResult(success=False, error="Report root not found")

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        if ctx.report_tree.root and ctx.report_tree.root.section and self._old_title:
            ctx.report_tree.root.section.title = self._old_title
        return RollbackResult(success=True)