from __future__ import annotations
from dataclasses import dataclass, field

from .base import AtomicRevision
from ..revision_types import (
    RevisionOpType, ExecContext, ValidationResult,
    PreviewDiff, ExecutionResult, RollbackResult,
)
from ..markdown_table_parser import ImageParser


@dataclass
class ModifyChartOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.MODIFY_CHART)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        return ValidationResult(valid=True)

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        return PreviewDiff()

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        img_index = self.action.parameters.get("img_index", 1) - 1
        new_alt = self.action.parameters.get("alt", "")
        new_src = self.action.parameters.get("src", "")

        global_idx = 0
        for node in ctx.report_tree.node_map.values():
            content = getattr(node.section, "content", "")
            if not content or "![" not in content:
                continue
            images = ImageParser.find_images(content)
            for local_idx, img in enumerate(images):
                if global_idx == img_index:
                    old_text = img["img_text"]
                    if new_src and new_alt:
                        new_text = f"![{new_alt}]({new_src})"
                    elif new_src:
                        new_text = f"![{img['alt']}]({new_src})"
                    elif new_alt:
                        new_text = f"![{new_alt}]({img['src']})"
                    else:
                        return ExecutionResult(success=False, error="No changes specified")
                    node.section.content = content.replace(old_text, new_text, 1)
                    return ExecutionResult(success=True)
                global_idx += 1

        return ExecutionResult(
            success=False, error=f"Image #{img_index + 1} not found"
        )

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        if ctx.snapshot_id:
            await ctx.snapshot_manager.restore_nodes(ctx.snapshot_id, [])
        return RollbackResult(success=True)
