from __future__ import annotations
import copy
import dataclasses
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
class CompositeOperation(AtomicRevision):
    op_type: RevisionOpType = field(init=False)
    sub_operations: list[AtomicRevision] = field(default_factory=list)

    def __post_init__(self):
        first_real = next(
            (s.op_type for s in self.sub_operations if s.op_type != RevisionOpType.UNKNOWN),
            None,
        )
        self.op_type = first_real or RevisionOpType.MODIFY

    async def validate(self, ctx: ExecContext) -> ValidationResult:
        for op in self.sub_operations:
            result = await op.validate(ctx)
            if not result.valid:
                return ValidationResult(valid=False, errors=result.errors)
        return ValidationResult(valid=True)

    async def preview(self, ctx: ExecContext) -> PreviewDiff:
        sub_diffs = []
        for op in self.sub_operations:
            sub_diffs.append(await op.preview(ctx))
        return PreviewDiff(
            before=sub_diffs,
            commit_message=f"复合操作: {len(self.sub_operations)} 步",
        )

    async def execute(self, ctx: ExecContext) -> ExecutionResult:
        results: list[ExecutionResult] = []
        ctx_snapshots: list[ExecContext] = []
        for i, op in enumerate(self.sub_operations):
            sub_ctx = dataclasses.replace(
                ctx,
                operation_index=i,
                total_operations=len(self.sub_operations),
            )
            result = await op.execute(sub_ctx)
            results.append(result)
            ctx_snapshots.append(copy.deepcopy(sub_ctx))
            if not result.success:
                for j in range(i - 1, -1, -1):
                    await self.sub_operations[j].rollback(ctx_snapshots[j])
                if i == 0:
                    await self.sub_operations[0].rollback(sub_ctx)
                return ExecutionResult(success=False, sub_results=results)

        return ExecutionResult(success=True, sub_results=results)

    async def rollback(self, ctx: ExecContext) -> RollbackResult:
        failed: list[int] = []
        for i in range(len(self.sub_operations) - 1, -1, -1):
            try:
                sub_ctx = dataclasses.replace(
                    ctx,
                    operation_index=i,
                    total_operations=len(self.sub_operations),
                )
                result = await self.sub_operations[i].rollback(sub_ctx)
                if not result.success:
                    failed.append(i)
            except Exception:
                failed.append(i)
        return RollbackResult(
            success=len(failed) == 0,
            error=f"Rollback failed for sub-ops {failed}" if failed else None,
        )
