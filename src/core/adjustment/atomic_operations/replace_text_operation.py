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
class ReplaceTextOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.REPLACE_TEXT)
    _replaced_nodes: list = field(default_factory=list, init=False, repr=False)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        old_text = self.action.parameters.get("old_text", "")
        new_text = self.action.content or ""
        return ValidationResult(valid=bool(old_text))

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        old_text = self.action.parameters.get("old_text", "")
        new_text = self.action.content or ""
        return PreviewDiff(
            before=old_text,
            after=new_text,
            commit_message=f"REPLACE_TEXT: '{old_text}' -> '{new_text}'",
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        old_text = self.action.parameters.get("old_text", "")
        new_text = self.action.content or ""
        if not old_text:
            return ExecutionResult(success=False, error="old_text parameter is empty")

        affected = []
        self._replaced_nodes = []
        for nid, node in ctx.report_tree.node_map.items():
            content = getattr(node.section, "content", "")
            if content and old_text in content:
                original = content
                node.section.content = content.replace(old_text, new_text)
                affected.append(nid)
                self._replaced_nodes.append((nid, original))

        if not affected:
            return ExecutionResult(
                success=False,
                error=f"Text '{old_text}' not found in any section",
            )
        return ExecutionResult(success=True, affected_ids=affected)

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        for nid, original_content in self._replaced_nodes:
            node = ctx.report_tree.find(nid)
            if node:
                node.section.content = original_content
        self._replaced_nodes.clear()
        return RollbackResult(success=True)