from __future__ import annotations
from copy import deepcopy
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
    RevisionTarget,
    LocationStrategy,
    SectionNode,
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
class CopyOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.COPY)
    _created_ids: List[str] = field(default_factory=list, init=False, repr=False)

    async def _resolve_parent(
        self, ctx: ExecContext, parent_ref: str
    ) -> SectionNode | None:
        locator = SectionLocatorV2()
        node = ctx.report_tree.find(parent_ref)
        if node:
            return node
        target = RevisionTarget(
            raw_text=parent_ref,
            section_refs=[],
            location_strategy=LocationStrategy.KEYWORD,
            is_ambiguous=False,
        )
        ids = await locator.resolve_to_ids(target, ctx.report_tree)
        return ctx.report_tree.find(ids[0]) if ids else None

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        resolved = self._target_ids(ctx)
        target_parent_id = self.action.parameters.get("target_parent", "")
        if target_parent_id:
            parent_node = await self._resolve_parent(ctx, target_parent_id)
            return ValidationResult(
                valid=len(resolved) > 0 and parent_node is not None,
                errors=(
                    []
                    if len(resolved) > 0
                    else ["Source section not found"]
                ),
            )
        return ValidationResult(
            valid=len(resolved) > 0,
            errors=[] if len(resolved) > 0 else ["Source section not found"],
        )

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        ids = self._target_ids(ctx)
        if not ids:
            return PreviewDiff()
        src = ctx.report_tree.find(ids[0])
        return PreviewDiff(before=src.section if src else None)

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        source_ids = self._target_ids(ctx)
        if not source_ids:
            return ExecutionResult(success=False, error="Source section not found")
        source = ctx.report_tree.find(source_ids[0])
        if not source:
            return ExecutionResult(success=False, error="Source section not found")

        new_section = deepcopy(source.section)
        new_id = str(uuid4())
        new_section.id = new_id
        if hasattr(new_section, "metadata") and hasattr(new_section.metadata, "source"):
            new_section.metadata.source = source.section.id

        target_parent_id = self.action.parameters.get("target_parent", "")
        target_parent = await self._resolve_parent(ctx, target_parent_id)
        if not target_parent:
            return ExecutionResult(success=False, error="Target parent not found")

        position = self.action.parameters.get("position", "last")
        new_node = SectionNode(
            id=new_id,
            section=new_section,
            parent_id=target_parent.id,
        )
        ctx.report_tree.node_map[new_node.id] = new_node
        self._created_ids = [new_node.id]
        if position == "first":
            target_parent.children.insert(0, new_node)
        else:
            target_parent.children.append(new_node)
        return ExecutionResult(
            success=True,
            created_ids=[new_node.id],
            affected_ids=[source.id, target_parent.id],
        )

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        for node_id in self._created_ids:
            node = ctx.report_tree.node_map.get(node_id)
            if node and node.parent_id:
                parent = ctx.report_tree.node_map.get(node.parent_id)
                if parent:
                    parent.children = [c for c in parent.children if c.id != node_id]
            ctx.report_tree.node_map.pop(node_id, None)
        return RollbackResult(success=True)
