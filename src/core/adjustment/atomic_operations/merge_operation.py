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
    MergeStrategy,
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
class MergeOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.MERGE)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        target_ids = self._target_ids(ctx)
        source_ids = []
        if self.action.source:
            locator = SectionLocatorV2()
            source_ids = await locator.resolve_to_ids(self.action.source, ctx.report_tree)
        return ValidationResult(
            valid=len(target_ids) > 0 and len(source_ids) > 0,
            errors=(
                []
                if len(target_ids) > 0 and len(source_ids) > 0
                else ["One or both MERGE targets not found"]
            ),
        )

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        target_ids = self._target_ids(ctx)
        source_ids = []
        if self.action.source:
            locator = SectionLocatorV2()
            source_ids = await locator.resolve_to_ids(self.action.source, ctx.report_tree)
        target_node = ctx.report_tree.find(target_ids[0]) if target_ids else None
        source_node = ctx.report_tree.find(source_ids[0]) if source_ids else None
        return PreviewDiff(
            before={"target": target_node.section if target_node else None,
                    "source": source_node.section if source_node else None},
            commit_message=f"MERGE: {self.action.target.raw_text}",
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        target_ids = self._target_ids(ctx)
        source_ids = []
        if self.action.source:
            locator = SectionLocatorV2()
            source_ids = await locator.resolve_to_ids(self.action.source, ctx.report_tree)
        if not target_ids or not source_ids:
            return ExecutionResult(success=False, error="Merge target or source not found")
        target_node = ctx.report_tree.find(target_ids[0])
        source_node = ctx.report_tree.find(source_ids[0])
        if not target_node or not source_node:
            return ExecutionResult(success=False, error="Merge target or source not found")

        default_strategy = MergeStrategy.UNION
        strategy_name = self.action.parameters.get("strategy", default_strategy.value)
        try:
            strategy = MergeStrategy(strategy_name)
        except ValueError:
            strategy = default_strategy
        target_content = target_node.section.content or ""
        source_content = source_node.section.content or ""
        if strategy == MergeStrategy.OURS:
            merged = target_content
        elif strategy == MergeStrategy.THEIRS:
            merged = source_content
        else:
            merged = target_content + "\n\n" + source_content
        target_node.section.content = merged

        parent = ctx.report_tree.node_map.get(source_node.parent_id) if source_node.parent_id else None
        if parent:
            parent.children = [c for c in parent.children if c.id != source_node.id]
        ctx.report_tree.node_map.pop(source_node.id, None)
        return ExecutionResult(
            success=True,
            affected_ids=[target_node.id, source_node.id],
        )

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        if ctx.snapshot_id:
            await ctx.snapshot_manager.restore_nodes(ctx.snapshot_id, [])
        return RollbackResult(success=True)
