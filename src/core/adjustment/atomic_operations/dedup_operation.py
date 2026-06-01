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
class DedupOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.DEDUP)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        dup_pair = self.action.parameters.get("duplicate_pair")
        if not dup_pair:
            source_ids = []
            target_ids = self._target_ids(ctx)
            if self.action.source:
                locator = SectionLocatorV2()
                source_ids = await locator.resolve_to_ids(
                    self.action.source, ctx.report_tree
                )
            return ValidationResult(
                valid=len(target_ids) > 0 and len(source_ids) > 0,
                errors=(
                    []
                    if len(target_ids) > 0 and len(source_ids) > 0
                    else ["Source or target section not found"]
                ),
            )
        return ValidationResult(valid=True)

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        ids = self._target_ids(ctx)
        source_ids = []
        if self.action.source:
            locator = SectionLocatorV2()
            source_ids = await locator.resolve_to_ids(
                self.action.source, ctx.report_tree
            )
        return PreviewDiff(
            before={"target_ids": ids, "source_ids": source_ids},
            commit_message=f"DEDUP: {self.action.target.raw_text}",
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        dup_pair = self.action.parameters.get("duplicate_pair", {})
        primary_id = dup_pair.get("primary_id") if isinstance(dup_pair, dict) else None
        secondary_id = dup_pair.get("secondary_id") if isinstance(dup_pair, dict) else None
        if not primary_id and not secondary_id:
            target_ids = self._target_ids(ctx)
            source_ids = []
            if self.action.source:
                locator = SectionLocatorV2()
                source_ids = await locator.resolve_to_ids(
                    self.action.source, ctx.report_tree
                )
            if target_ids:
                secondary_id = target_ids[0]
            if source_ids:
                primary_id = source_ids[0]
        if not primary_id or not secondary_id:
            return ExecutionResult(
                success=False, error="Could not determine primary/secondary sections"
            )
        secondary_node = ctx.report_tree.node_map.get(secondary_id)
        if not secondary_node:
            return ExecutionResult(
                success=False, error="Secondary section not found"
            )
        if secondary_node.parent_id:
            parent = ctx.report_tree.node_map.get(secondary_node.parent_id)
            if parent:
                parent.children = [
                    c for c in parent.children if c.id != secondary_id
                ]
        ctx.report_tree.node_map.pop(secondary_id, None)
        return ExecutionResult(
            success=True,
            affected_ids=[primary_id, secondary_id],
        )

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        if ctx.snapshot_id:
            await ctx.snapshot_manager.restore_nodes(ctx.snapshot_id, [])
        return RollbackResult(success=True)
