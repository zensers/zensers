from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .base import AtomicRevision
from ..revision_types import (
    RevisionOpType,
    ExecContext,
    ValidationResult,
    PreviewDiff,
    ExecutionResult,
    RollbackResult,
    SectionNode,
)


@dataclass
class DeleteOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.DELETE)
    _deleted_ids: list = field(default_factory=list, init=False, repr=False)
    _deleted_snapshots: List[Tuple[SectionNode, Optional[str], int]] = field(
        default_factory=list, init=False, repr=False
    )

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        ids = self._target_ids(ctx)
        return ValidationResult(valid=len(ids) > 0)

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        ids = self._target_ids(ctx)
        if not ids:
            return PreviewDiff()
        node = ctx.report_tree.find(ids[0])
        return PreviewDiff(before=node.section if node else None)

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        ids = self._target_ids(ctx)
        if not ids:
            return ExecutionResult(success=False, error="Target section not found")
        node = ctx.report_tree.find(ids[0])
        if not node:
            return ExecutionResult(success=False, error="Target section not found")

        parent_node = None
        child_index = -1
        if node.parent_id:
            parent_node = ctx.report_tree.find(node.parent_id)
            if parent_node:
                for i, c in enumerate(parent_node.children):
                    if c.id == node.id:
                        child_index = i
                        break
                parent_node.children = [c for c in parent_node.children if c.id != node.id]

        self._deleted_snapshots.append((node, node.parent_id, child_index))

        removed_ids = [node.id]
        for child in node.children:
            ctx.report_tree.node_map.pop(child.id, None)
            removed_ids.append(child.id)
        ctx.report_tree.node_map.pop(node.id, None)
        self._deleted_ids.extend(removed_ids)
        return ExecutionResult(success=True, affected_ids=removed_ids)

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        for node, parent_id, child_index in reversed(self._deleted_snapshots):
            ctx.report_tree.node_map[node.id] = node
            for child in node.children:
                ctx.report_tree.node_map[child.id] = child
            if parent_id and child_index >= 0:
                parent = ctx.report_tree.find(parent_id)
                if parent:
                    parent.children.insert(child_index, node)
        self._deleted_ids.clear()
        self._deleted_snapshots.clear()
        return RollbackResult(success=True)
