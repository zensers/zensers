from __future__ import annotations
from dataclasses import dataclass, field

from .base import AtomicRevision
from ..revision_types import (
    RevisionOpType, ExecContext, ValidationResult,
    PreviewDiff, ExecutionResult, RollbackResult,
)
from ..markdown_table_parser import MarkdownTableParser, ImageParser


@dataclass
class DeleteElementOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.DELETE_ELEMENT)
    _deleted_text: str = field(default="", init=False, repr=False)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        return ValidationResult(valid=True)

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        return PreviewDiff()

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        elem_type = self.action.parameters.get("element_type", "table")
        elem_index = self.action.parameters.get("element_index", 1) - 1

        global_idx = 0
        for node in ctx.report_tree.node_map.values():
            content = getattr(node.section, "content", "")
            if not content:
                continue

            if elem_type == "table":
                tables = MarkdownTableParser.find_tables(content)
                for local_idx, t in enumerate(tables):
                    if global_idx == elem_index:
                        self._deleted_text = t["table_text"]
                        node.section.content = content.replace(t["table_text"], "", 1)
                        return ExecutionResult(success=True)
                    global_idx += 1

            elif elem_type in ("chart", "image"):
                images = ImageParser.find_images(content)
                for local_idx, img in enumerate(images):
                    if global_idx == elem_index:
                        self._deleted_text = img["img_text"]
                        node.section.content = content.replace(img["img_text"], "", 1)
                        return ExecutionResult(success=True)
                    global_idx += 1

        return ExecutionResult(
            success=False,
            error=f"{elem_type} #{elem_index + 1} not found"
        )

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        if ctx.snapshot_id:
            await ctx.snapshot_manager.restore_nodes(ctx.snapshot_id, [])
        return RollbackResult(success=True)
