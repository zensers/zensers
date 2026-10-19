import re
from typing import Dict, List, Optional

from src.core.adjustment.revision_types import (
    AnalysisResult, RefType, RevisionOpType,
)


class PptRevisionRouter:

    DEFAULT_LEVEL_MAP = {
        RevisionOpType.REPLACE_TEXT: "L1",
        RevisionOpType.FIX_PUNCTUATION: "L1",
        RevisionOpType.CHANGE_CASE: "L1",
        RevisionOpType.UPDATE_TITLE: "L1",
        RevisionOpType.MODIFY_CHART: "L2",
        RevisionOpType.ADD_ELEMENT: "L2",
        RevisionOpType.DELETE_ELEMENT: "L2",
        RevisionOpType.MODIFY_TABLE: "L3",
        RevisionOpType.MODIFY: "L3",
        RevisionOpType.STYLE: "L3",
        RevisionOpType.ADD: "L4",
        RevisionOpType.DELETE: "L4",
        RevisionOpType.MERGE: "L4",
        RevisionOpType.SPLIT: "L4",
        RevisionOpType.SWAP: "L4",
        RevisionOpType.REORDER: "L4",
        RevisionOpType.DEDUP: "L4",
        RevisionOpType.COPY: "L4",
        RevisionOpType.TRANSLATE: "L4",
        RevisionOpType.REVIEW: "L0",
        RevisionOpType.UNKNOWN: "L3",
    }

    def __init__(self):
        from src.core.intent.revision_intent_analyzer import RevisionIntentAnalyzer
        self.intent_analyzer = RevisionIntentAnalyzer()

    async def route(self, user_message: str, slide_data_list: List[Dict],
                    ppt_context: Dict):
        from src.core.adjustment.ppt_report_adapter import PptReportAdapter
        from src.core.adjustment.ppt_revision_service import PptRevisionRequest

        report = PptReportAdapter(slide_data_list, ppt_context.get("task_id", ""))
        analysis = await self.intent_analyzer.analyze(user_message, report)

        if analysis.intents:
            action_type = analysis.intents[0].action_type
            level = self.DEFAULT_LEVEL_MAP.get(action_type, "L3")
        else:
            level = "L3"

        level = self._upgrade_if_needed(level, analysis, ppt_context)
        slide_index = self._extract_slide_index(analysis, ppt_context)
        slide_title = self._extract_slide_title(analysis, ppt_context)

        return PptRevisionRequest(
            task_id=ppt_context.get("task_id", ""),
            source="natural_language",
            slide_index=slide_index,
            slide_title=slide_title,
            description=user_message,
            intent_analysis=analysis,
            revision_level=level,
        )

    def _upgrade_if_needed(self, level: str, analysis: AnalysisResult,
                           ppt_context: Dict) -> str:
        if level == "L2" and analysis.intents:
            op = analysis.intents[0].action_type
            if op == RevisionOpType.MODIFY_CHART:
                if ppt_context.get("chart_size_changes", False):
                    level = "L3"
        if level == "L3" and analysis.intents:
            if ppt_context.get("affects_other_slides", False):
                level = "L4"
        return level

    def _extract_slide_index(self, analysis: AnalysisResult,
                             ppt_context: Dict) -> Optional[int]:
        if not analysis.intents:
            return ppt_context.get("current_slide_index")
        target = analysis.intents[0].target
        for ref in target.section_refs:
            if ref.ref_type == RefType.INDEX and ref.index is not None:
                return ref.index
        page_match = re.search(r'第(\d+)页|slide\s+(\d+)', target.raw_text, re.I)
        if page_match:
            num = int(page_match.group(1) or page_match.group(2))
            return max(0, num - 1)
        return ppt_context.get("current_slide_index")

    def _extract_slide_title(self, analysis: AnalysisResult,
                             ppt_context: Optional[Dict] = None) -> Optional[str]:
        if not analysis.intents:
            return None
        return analysis.intents[0].target.raw_text or None
