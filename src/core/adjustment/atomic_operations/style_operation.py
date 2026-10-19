from __future__ import annotations
import re
from dataclasses import dataclass, field

_NUMBER_PATTERN = re.compile(
    r"(?<!\w)(\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?%?(?!\w)"
)

from .base import AtomicRevision
from ..revision_types import (
    RevisionOpType,
    ExecContext,
    ValidationResult,
    PreviewDiff,
    ExecutionResult,
    RollbackResult,
    DataValidation,
)


@dataclass
class StyleOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.STYLE)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        ids = self._target_ids(ctx)
        return ValidationResult(valid=len(ids) > 0)

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        ids = self._target_ids(ctx)
        if not ids:
            return PreviewDiff()
        target = ctx.report_tree.find(ids[0])
        return PreviewDiff(before=target.section.content if target else None)

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        ids = self._target_ids(ctx)
        if not ids:
            return ExecutionResult(success=False, error="Target not found")
        target = ctx.report_tree.find(ids[0])
        if not target:
            return ExecutionResult(success=False, error="Target not found")

        style_target = self.action.parameters.get("style", "technical")

        rewritten = await self._llm_rewrite(
            original_content=target.section.content or "",
            style=style_target,
            preserve_data=True,
        )

        data_validation = self._validate_data_preserved(
            target.section.content or "", rewritten
        )
        if data_validation.has_changes and data_validation.change_ratio > 0.1:
            return ExecutionResult(
                success=False,
                error=f"风格重写修改了 {data_validation.change_ratio:.1%} 的数据内容, 已拒绝",
                validation=data_validation,
            )

        old_content = target.section.content
        target.section.content = rewritten

        return ExecutionResult(
            success=True,
            diff=PreviewDiff(before=old_content, after=rewritten),
            affected_ids=[target.id],
            validation=data_validation,
        )

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        ids = self._target_ids(ctx)
        if ctx.snapshot_id and ids:
            await ctx.snapshot_manager.restore_nodes(ctx.snapshot_id, ids)
        return RollbackResult(success=True)

    async def _llm_rewrite(
        self,
        original_content: str,
        style: str,
        preserve_data: bool = True,
    ) -> str:
        return original_content

    def _validate_data_preserved(
        self, original: str, rewritten: str
    ) -> DataValidation:
        original_numbers = set(_NUMBER_PATTERN.findall(original))
        rewritten_numbers = set(_NUMBER_PATTERN.findall(rewritten))
        added = rewritten_numbers - original_numbers
        removed = original_numbers - rewritten_numbers
        total = max(len(original_numbers), 1)
        return DataValidation(
            has_changes=bool(added or removed),
            changes=list(added | removed),
            change_ratio=len(added | removed) / total,
        )
