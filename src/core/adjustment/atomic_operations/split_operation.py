from __future__ import annotations
from types import SimpleNamespace
from uuid import uuid4
from dataclasses import dataclass, field
from typing import List, Optional

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
class SplitOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.SPLIT)
    _created_ids: List[str] = field(default_factory=list, init=False, repr=False)
    _original_content: Optional[str] = field(default=None, init=False, repr=False)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        ids = self._target_ids(ctx)
        split_point = self.action.parameters.get("split_point", "")
        return ValidationResult(
            valid=len(ids) > 0 and bool(split_point),
            errors=(
                []
                if len(ids) > 0 and bool(split_point)
                else (
                    ["Target section not found"]
                    if len(ids) == 0
                    else ["Split point not specified"]
                )
            ),
        )

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        ids = self._target_ids(ctx)
        if not ids:
            return PreviewDiff()
        node = ctx.report_tree.find(ids[0])
        return PreviewDiff(
            before=node.section if node else None,
            commit_message=f"SPLIT: {self.action.target.raw_text}",
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        ids = self._target_ids(ctx)
        if not ids:
            return ExecutionResult(success=False, error="Target section not found")
        target_node = ctx.report_tree.find(ids[0])
        if not target_node:
            return ExecutionResult(success=False, error="Target section not found")

        split_point = self.action.parameters.get("split_point", "")
        content = target_node.section.content or ""
        idx = content.find(split_point)
        if idx < 0:
            return ExecutionResult(
                success=False,
                error=f"Split point '{split_point}' not found in content",
            )

        self._original_content = content

        first_part = content[:idx].rstrip()
        second_part = content[idx:].lstrip()

        target_node.section.content = first_part

        new_id = str(uuid4())
        new_section = SimpleNamespace()
        new_section.id = new_id
        new_section.content = second_part
        if hasattr(target_node.section, "title"):
            new_section.title = getattr(target_node.section, "title", "")
        if self.action.parameters.get("new_title"):
            new_section.title = self.action.parameters["new_title"]
        new_node = SectionNode(
            id=new_id, section=new_section, parent_id=target_node.parent_id
        )
        ctx.report_tree.node_map[new_id] = new_node
        self._created_ids.append(new_id)
        if target_node.parent_id:
            parent = ctx.report_tree.node_map.get(target_node.parent_id)
            if parent:
                parent.children.append(new_node)
        else:
            new_node.parent_id = target_node.id
            target_node.children.insert(0, new_node)
        return ExecutionResult(
            success=True,
            created_ids=[new_id],
            affected_ids=[target_node.id],
        )

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        ids = self._target_ids(ctx)
        target_node = ctx.report_tree.find(ids[0]) if ids else None
        if target_node and self._original_content is not None:
            target_node.section.content = self._original_content
        for nid in self._created_ids:
            node = ctx.report_tree.find(nid)
            if node and node.parent_id:
                parent = ctx.report_tree.find(node.parent_id)
                if parent:
                    parent.children = [c for c in parent.children if c.id != nid]
            ctx.report_tree.node_map.pop(nid, None)
        self._created_ids.clear()
        self._original_content = None
        return RollbackResult(success=True)