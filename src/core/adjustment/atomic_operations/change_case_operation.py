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


@dataclass
class ChangeCaseOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.CHANGE_CASE)
    _replaced_nodes: list = field(default_factory=list, init=False, repr=False)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        target_case = self.action.parameters.get("target_case", "")
        return ValidationResult(valid=target_case in ("upper", "lower", "title"))

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        target_case = self.action.parameters.get("target_case", "")
        return PreviewDiff(
            commit_message=f"CHANGE_CASE: convert to {target_case}",
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        target_case = self.action.parameters.get("target_case", "")
        if target_case not in ("upper", "lower", "title"):
            return ExecutionResult(success=False, error=f"Invalid target_case: {target_case}")

        affected = []
        self._replaced_nodes = []
        for nid, node in ctx.report_tree.node_map.items():
            if nid == "_root":
                continue
            title = getattr(node.section, "title", "")
            if not title:
                continue
            original = title
            if target_case == "upper":
                node.section.title = title.upper()
            elif target_case == "lower":
                node.section.title = title.lower()
            elif target_case == "title":
                node.section.title = title.title()
            if node.section.title != original:
                affected.append(nid)
                self._replaced_nodes.append((nid, original))

        if not affected:
            return ExecutionResult(success=False, error="No titles changed")
        return ExecutionResult(success=True, affected_ids=affected)

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        for nid, original_title in self._replaced_nodes:
            node = ctx.report_tree.find(nid)
            if node:
                node.section.title = original_title
        self._replaced_nodes.clear()
        return RollbackResult(success=True)