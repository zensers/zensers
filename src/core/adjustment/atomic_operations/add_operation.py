from __future__ import annotations
from types import SimpleNamespace
from typing import List
from uuid import uuid4
from dataclasses import dataclass, field

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
class AddOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.ADD)
    _created_ids: List[str] = field(default_factory=list, init=False, repr=False)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        ids = self._target_ids(ctx)
        position = self.action.parameters.get("position", "last")
        if ids:
            parent = ctx.report_tree.find(ids[0])
            if parent:
                return ValidationResult(valid=True)
        if position in ("first", "last") and ctx.report_tree.root:
            return ValidationResult(valid=True)
        if position and ids:
            return ValidationResult(valid=True)
        return ValidationResult(valid=False, errors=["Invalid insertion position"])

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        return PreviewDiff(
            before=None,
            after=self.action.content,
            commit_message=f"ADD: {self.action.target.raw_text}",
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        parent_id = self.action.parameters.get("parent_id", "")
        if parent_id:
            parent_node = ctx.report_tree.find(parent_id)
        else:
            ids = self._target_ids(ctx)
            target = ctx.report_tree.find(ids[0]) if ids else None
            if not target or not target.parent_id:
                return ExecutionResult(success=False, error="Target location not found")
            parent_node = target
        if not parent_node:
            return ExecutionResult(success=False, error="Parent node not found")

        new_id = str(uuid4())
        new_section = SimpleNamespace()
        new_section.id = new_id
        new_section.content = self.action.content or ""
        new_section.title = self.action.parameters.get("title", "")
        new_node = SectionNode(id=new_id, section=new_section, parent_id=parent_node.id)
        position = self.action.parameters.get("position", "last")
        if position == "first":
            parent_node.children.insert(0, new_node)
        else:
            parent_node.children.append(new_node)
        ctx.report_tree.node_map[new_id] = new_node
        self._created_ids.append(new_id)
        return ExecutionResult(success=True, created_ids=[new_id])

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        for nid in self._created_ids:
            node = ctx.report_tree.find(nid)
            if node and node.parent_id:
                parent = ctx.report_tree.find(node.parent_id)
                if parent:
                    parent.children = [c for c in parent.children if c.id != nid]
                ctx.report_tree.node_map.pop(nid, None)
        self._created_ids.clear()
        return RollbackResult(success=True)
