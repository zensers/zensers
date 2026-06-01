from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

from ..revision_types import (
    RevisionOpType,
    RevisionAction,
    ExecContext,
    ValidationResult,
    PreviewDiff,
    ExecutionResult,
    RollbackResult,
    ImpactEstimate,
    RefType,
)


@dataclass
class AtomicRevision(ABC):
    op_type: RevisionOpType = field(init=False)
    action: RevisionAction | None = None

    def __post_init__(self):
        if not hasattr(self, "op_type") or self.op_type is None:
            raise TypeError("子类必须设置 op_type 类属性或 __post_init__ 中赋值")

    def _target_ids(self, ctx: ExecContext) -> List[str]:
        """从已解析的 section_refs 获取目标 UUID，避免重复定位"""
        if self.action is None or not self.action.target:
            return []
        uuid_refs = [
            ref.uuid for ref in self.action.target.section_refs
            if ref.ref_type == RefType.UUID and ref.uuid
        ]
        if uuid_refs:
            return uuid_refs
        return []

    @abstractmethod
    async def validate(self, ctx: ExecContext) -> ValidationResult: ...

    @abstractmethod
    async def preview(self, ctx: ExecContext) -> PreviewDiff: ...

    @abstractmethod
    async def execute(self, ctx: ExecContext) -> ExecutionResult: ...

    @abstractmethod
    async def rollback(self, ctx: ExecContext) -> RollbackResult: ...

    def estimate_impact(self, ctx: ExecContext) -> ImpactEstimate:
        if self.action:
            return ImpactEstimate(
                affected_sections=[self.action.target.raw_text]
            )
        return ImpactEstimate()
