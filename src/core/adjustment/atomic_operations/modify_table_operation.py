from __future__ import annotations
from dataclasses import dataclass, field

from .base import AtomicRevision
from ..revision_types import (
    RevisionOpType, ExecContext, ValidationResult,
    PreviewDiff, ExecutionResult, RollbackResult,
)
from ..markdown_table_parser import MarkdownTableParser


@dataclass
class ModifyTableOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.MODIFY_TABLE)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        return ValidationResult(valid=True)

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        return PreviewDiff()

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        table_index = self.action.parameters.get("table_index", 1) - 1  # 1-based → 0-based
        row = self.action.parameters.get("row", 0) - 1
        col = self.action.parameters.get("col", 0) - 1
        value = self.action.parameters.get("value", self.action.content or "")

        global_idx = 0
        for node in ctx.report_tree.node_map.values():
            content = getattr(node.section, "content", "")
            if not content or "|" not in content:
                continue
            tables = MarkdownTableParser.find_tables(content)
            for local_idx in range(len(tables)):
                if global_idx == table_index:
                    new_content = MarkdownTableParser.set_cell(
                        content, local_idx, row, col, value
                    )
                    if new_content != content:
                        node.section.content = new_content
                        return ExecutionResult(success=True)
                    return ExecutionResult(
                        success=False, error="Cell not modified"
                    )
                global_idx += 1

        return ExecutionResult(
            success=False, error=f"Table #{table_index + 1} not found"
        )

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        if ctx.snapshot_id:
            await ctx.snapshot_manager.restore_nodes(ctx.snapshot_id, [])
        return RollbackResult(success=True)
