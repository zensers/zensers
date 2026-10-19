from __future__ import annotations
import re
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
class FixPunctuationOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.FIX_PUNCTUATION)
    _replaced_nodes: list = field(default_factory=list, init=False, repr=False)

    _CN_PUNCT = {
        ',': '，', ':': '：', ';': '；', '!': '！', '?': '？',
        '(': '（', ')': '）',
    }
    _EN_PUNCT = {v: k for k, v in _CN_PUNCT.items()}

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        rule = self.action.parameters.get("punct_rule", "")
        return ValidationResult(valid=rule in ("cn2en", "en2cn"))

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        rule = self.action.parameters.get("punct_rule", "")
        return PreviewDiff(
            commit_message=f"FIX_PUNCTUATION: {rule}",
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        rule = self.action.parameters.get("punct_rule", "")
        if rule not in ("cn2en", "en2cn"):
            return ExecutionResult(success=False, error=f"Invalid punct_rule: {rule}")

        punct_map = self._CN_PUNCT if rule == "en2cn" else self._EN_PUNCT
        affected = []
        self._replaced_nodes = []
        for nid, node in ctx.report_tree.node_map.items():
            if nid == "_root":
                continue
            content = getattr(node.section, "content", "")
            if not content:
                continue
            original = content
            for old, new in punct_map.items():
                content = content.replace(old, new)
            if content != original:
                node.section.content = content
                affected.append(nid)
                self._replaced_nodes.append((nid, original))

        if not affected:
            return ExecutionResult(success=False, error="No punctuation changes needed")
        return ExecutionResult(success=True, affected_ids=affected)

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        for nid, original_content in self._replaced_nodes:
            node = ctx.report_tree.find(nid)
            if node:
                node.section.content = original_content
        self._replaced_nodes.clear()
        return RollbackResult(success=True)