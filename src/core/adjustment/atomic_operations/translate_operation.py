from __future__ import annotations
from dataclasses import dataclass, field

from .base import AtomicRevision
from ..revision_types import (
    RevisionOpType, ExecContext, ValidationResult,
    PreviewDiff, ExecutionResult, RollbackResult,
)


@dataclass
class TranslateOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False, default=RevisionOpType.TRANSLATE)

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        return ValidationResult(valid=True)

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        return PreviewDiff()

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        target_lang = self.action.parameters.get("target_lang", "en")

        texts = []
        for node in ctx.report_tree.node_map.values():
            content = getattr(node.section, "content", "")
            if content.strip():
                texts.append(content)

        if not texts:
            return ExecutionResult(success=False, error="No content to translate")

        translated_texts = await self._llm_translate_batch(texts, target_lang)

        idx = 0
        for node in ctx.report_tree.node_map.values():
            content = getattr(node.section, "content", "")
            if content.strip() and idx < len(translated_texts):
                node.section.content = translated_texts[idx]
                idx += 1

        return ExecutionResult(success=True)

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        if ctx.snapshot_id:
            await ctx.snapshot_manager.restore_nodes(ctx.snapshot_id, [])
        return RollbackResult(success=True)

    async def _llm_translate_batch(
        self, texts: list[str], target_lang: str
    ) -> list[str]:
        from src.core.llm_client import call_llm
        from src.config.llm_profiles import RoutingHint

        combined = "\n\n---SEPARATOR---\n\n".join(texts)
        prompt = (
            f"Translate the following text to {target_lang}. "
            f"Preserve all Markdown formatting, table structures, and "
            f"the SEPARATOR markers between sections.\n\n{combined}"
        )
        result = await call_llm(
            prompt=prompt,
            system_prompt="You are a professional translator.",
            max_tokens=8192,
            temperature=0.3,
            routing_hint=RoutingHint(action="translation"),
        )
        if not result.get("success"):
            raise RuntimeError(f"Translation failed: {result.get('error')}")

        translated = result.get("content", "")
        parts = translated.split("---SEPARATOR---")
        result_texts = []
        for original, part in zip(texts, parts):
            result_texts.append(part.strip() if part.strip() else original)
        while len(result_texts) < len(texts):
            result_texts.append(texts[len(result_texts)])
        return result_texts
