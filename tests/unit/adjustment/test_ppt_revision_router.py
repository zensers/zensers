import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.adjustment.ppt_revision_router import PptRevisionRouter
from src.core.adjustment.revision_types import (
    RevisionOpType, RevisionAction, RevisionTarget, SectionRef,
    RefType, AnalysisResult,
)


def _make_analysis(action_type: RevisionOpType, raw_text: str = "test",
                   section_refs=None, needs_clarification=False):
    refs = section_refs or []
    target = RevisionTarget(
        raw_text=raw_text,
        section_refs=refs,
        location_strategy=MagicMock(),
        is_ambiguous=False,
    )
    action = RevisionAction(
        action_id="a1",
        action_type=action_type,
        target=target,
    )
    return AnalysisResult(intents=[action], needs_clarification=needs_clarification)


class TestDefaultLevelMap:
    def test_l1_replace_text(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.REPLACE_TEXT] == "L1"

    def test_l1_fix_punctuation(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.FIX_PUNCTUATION] == "L1"

    def test_l1_change_case(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.CHANGE_CASE] == "L1"

    def test_l1_update_title(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.UPDATE_TITLE] == "L1"

    def test_l2_modify_chart(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.MODIFY_CHART] == "L2"

    def test_l2_add_element(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.ADD_ELEMENT] == "L2"

    def test_l2_delete_element(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.DELETE_ELEMENT] == "L2"

    def test_l3_modify_table(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.MODIFY_TABLE] == "L3"

    def test_l3_modify(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.MODIFY] == "L3"

    def test_l3_style(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.STYLE] == "L3"

    def test_l4_add(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.ADD] == "L4"

    def test_l4_delete(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.DELETE] == "L4"

    def test_l4_merge(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.MERGE] == "L4"

    def test_l4_split(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.SPLIT] == "L4"

    def test_l4_swap(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.SWAP] == "L4"

    def test_l4_reorder(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.REORDER] == "L4"

    def test_l4_dedup(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.DEDUP] == "L4"

    def test_l4_copy(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.COPY] == "L4"

    def test_l4_translate(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.TRANSLATE] == "L4"

    def test_l0_review(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.REVIEW] == "L0"

    def test_l3_unknown(self):
        assert PptRevisionRouter.DEFAULT_LEVEL_MAP[RevisionOpType.UNKNOWN] == "L3"

    def test_all_21_optypes_covered(self):
        all_optypes = set(RevisionOpType)
        mapped_optypes = set(PptRevisionRouter.DEFAULT_LEVEL_MAP.keys())
        assert all_optypes == mapped_optypes


class TestUpgradeIfNeeded:
    def test_l2_chart_size_change_upgrades_to_l3(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = _make_analysis(RevisionOpType.MODIFY_CHART)
        ctx = {"chart_size_changes": True}
        assert router._upgrade_if_needed("L2", analysis, ctx) == "L3"

    def test_l2_chart_no_size_change_stays_l2(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = _make_analysis(RevisionOpType.MODIFY_CHART)
        ctx = {}
        assert router._upgrade_if_needed("L2", analysis, ctx) == "L2"

    def test_l3_affects_other_slides_upgrades_to_l4(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = _make_analysis(RevisionOpType.MODIFY)
        ctx = {"affects_other_slides": True}
        assert router._upgrade_if_needed("L3", analysis, ctx) == "L4"

    def test_l3_no_cross_slide_stays_l3(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = _make_analysis(RevisionOpType.MODIFY)
        ctx = {}
        assert router._upgrade_if_needed("L3", analysis, ctx) == "L3"

    def test_l1_not_upgraded(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = _make_analysis(RevisionOpType.REPLACE_TEXT)
        ctx = {"chart_size_changes": True, "affects_other_slides": True}
        assert router._upgrade_if_needed("L1", analysis, ctx) == "L1"


class TestExtractSlideIndex:
    def test_index_ref_returns_index(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        refs = [SectionRef(uuid="s1", ref_type=RefType.INDEX, index=2)]
        analysis = _make_analysis(RevisionOpType.MODIFY, section_refs=refs)
        assert router._extract_slide_index(analysis, {}) == 2

    def test_chinese_page_number(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = _make_analysis(RevisionOpType.MODIFY, raw_text="修改第5页的标题")
        assert router._extract_slide_index(analysis, {}) == 4

    def test_english_slide_number(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = _make_analysis(RevisionOpType.MODIFY, raw_text="change slide 3 title")
        assert router._extract_slide_index(analysis, {}) == 2

    def test_fallback_to_context(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = _make_analysis(RevisionOpType.MODIFY, raw_text="修改标题")
        ctx = {"current_slide_index": 5}
        assert router._extract_slide_index(analysis, ctx) == 5

    def test_no_index_returns_none(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = _make_analysis(RevisionOpType.MODIFY, raw_text="修改标题")
        assert router._extract_slide_index(analysis, {}) is None

    def test_no_intents_fallback_to_context(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = AnalysisResult(intents=[])
        ctx = {"current_slide_index": 3}
        assert router._extract_slide_index(analysis, ctx) == 3

    def test_no_intents_no_context_returns_none(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = AnalysisResult(intents=[])
        assert router._extract_slide_index(analysis, {}) is None


class TestExtractSlideTitle:
    def test_returns_raw_text(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = _make_analysis(RevisionOpType.MODIFY, raw_text="市场规模")
        assert router._extract_slide_title(analysis) == "市场规模"

    def test_empty_raw_text_returns_none(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = _make_analysis(RevisionOpType.MODIFY, raw_text="")
        assert router._extract_slide_title(analysis) is None

    def test_no_intents_returns_none(self):
        router = PptRevisionRouter.__new__(PptRevisionRouter)
        analysis = AnalysisResult(intents=[])
        assert router._extract_slide_title(analysis) is None
