from __future__ import annotations

from ..revision_types import RevisionOpType, RevisionAction, RevisionPlan
from .base import AtomicRevision
from .modify_operation import ModifyOperation
from .delete_operation import DeleteOperation
from .add_operation import AddOperation
from .copy_operation import CopyOperation
from .merge_operation import MergeOperation
from .split_operation import SplitOperation
from .swap_operation import SwapOperation
from .reorder_operation import ReorderOperation
from .dedup_operation import DedupOperation
from .style_operation import StyleOperation
from .review_operation import ReviewOperation
from .modify_table_operation import ModifyTableOperation
from .modify_chart_operation import ModifyChartOperation
from .add_element_operation import AddElementOperation
from .delete_element_operation import DeleteElementOperation
from .translate_operation import TranslateOperation
from .update_title_operation import UpdateTitleOperation
from .replace_text_operation import ReplaceTextOperation
from .change_case_operation import ChangeCaseOperation
from .fix_punctuation_operation import FixPunctuationOperation


class AtomicOperationFactory:
    _OP_MAP = {
        RevisionOpType.MODIFY: ModifyOperation,
        RevisionOpType.DELETE: DeleteOperation,
        RevisionOpType.ADD: AddOperation,
        RevisionOpType.COPY: CopyOperation,
        RevisionOpType.MERGE: MergeOperation,
        RevisionOpType.SPLIT: SplitOperation,
        RevisionOpType.SWAP: SwapOperation,
        RevisionOpType.REORDER: ReorderOperation,
        RevisionOpType.DEDUP: DedupOperation,
        RevisionOpType.STYLE: StyleOperation,
        RevisionOpType.REVIEW: ReviewOperation,
        RevisionOpType.MODIFY_TABLE: ModifyTableOperation,
        RevisionOpType.MODIFY_CHART: ModifyChartOperation,
        RevisionOpType.ADD_ELEMENT: AddElementOperation,
        RevisionOpType.DELETE_ELEMENT: DeleteElementOperation,
        RevisionOpType.TRANSLATE: TranslateOperation,
        RevisionOpType.UPDATE_TITLE: UpdateTitleOperation,
        RevisionOpType.REPLACE_TEXT: ReplaceTextOperation,
        RevisionOpType.CHANGE_CASE: ChangeCaseOperation,
        RevisionOpType.FIX_PUNCTUATION: FixPunctuationOperation,
    }

    def create(self, action: RevisionAction) -> AtomicRevision | None:
        op_class = self._OP_MAP.get(action.action_type)
        if not op_class:
            return None
        return op_class(action=action)

    def create_from_plan(self, plan: RevisionPlan) -> list[AtomicRevision]:
        return [self.create(action) for action in plan.actions]
