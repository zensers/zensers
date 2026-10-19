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
try:
    from ..section_locator_v2 import SectionLocatorV2
except ImportError:
    class SectionLocatorV2:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "SectionLocatorV2 not available — implement section_locator_v2.py"
            )
        async def resolve_to_ids(self, *args, **kwargs):
            raise ImportError(
                "SectionLocatorV2 not available — implement section_locator_v2.py"
            )


@dataclass
class SwapOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.SWAP)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        ids_a = self._target_ids(ctx)
        ids_b = (
            await SectionLocatorV2().resolve_to_ids(self.action.source, ctx.report_tree)
            if self.action.source
            else []
        )
        return ValidationResult(
            valid=len(ids_a) > 0 and len(ids_b) > 0,
            errors=(
                []
                if len(ids_a) > 0 and len(ids_b) > 0
                else ["One or both SWAP targets not found"]
            ),
        )

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        ids_a = self._target_ids(ctx)
        ids_b = (
            await SectionLocatorV2().resolve_to_ids(self.action.source, ctx.report_tree)
            if self.action.source
            else []
        )
        return PreviewDiff(
            before={"target": ids_a, "source": ids_b},
            commit_message=f"SWAP: {ids_a} ↔ {ids_b}",
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        ids_a = self._target_ids(ctx)
        ids_b = (
            await SectionLocatorV2().resolve_to_ids(self.action.source, ctx.report_tree)
            if self.action.source
            else []
        )
        if not ids_a or not ids_b:
            return ExecutionResult(
                success=False, error="SWAP target not found"
            )
        node_a = ctx.report_tree.find(ids_a[0])
        node_b = ctx.report_tree.find(ids_b[0])
        if not node_a or not node_b:
            return ExecutionResult(
                success=False, error="SWAP target not found"
            )
        node_a.section.content, node_b.section.content = (
            node_b.section.content,
            node_a.section.content,
        )
        return ExecutionResult(
            success=True,
            affected_ids=[node_a.id, node_b.id],
        )

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        # SWAP rollback 使用快照恢复，禁止再次执行 SWAP
        ids_a = self._target_ids(ctx)
        ids_b = (
            await SectionLocatorV2().resolve_to_ids(self.action.source, ctx.report_tree)
            if self.action.source
            else []
        )
        node_ids = ids_a + ids_b
        if ctx.snapshot_id and node_ids:
            await ctx.snapshot_manager.restore_nodes(
                ctx.snapshot_id, node_ids
            )
        return RollbackResult(success=True)
